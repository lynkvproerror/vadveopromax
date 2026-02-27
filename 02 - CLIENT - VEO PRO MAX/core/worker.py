"""
VEO Pro Max - PromptExecutor (formerly Worker / THỢ)

Reference: MULTITHREADING_ARCHITECTURE.md
Role: Execute individual tasks using assigned account

Architecture: Asyncio (Hybrid with ProcessPoolExecutor for CPU tasks)
"""

from typing import Optional, List, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.dispatcher import Task, TaskState
from core.account_manager import AccountManager
from core.api_client import VEOApiClient, APIResponse
from config.constants import WorkflowType

log = logging.getLogger(__name__)


class WorkerState(str, Enum):
    """Worker thread states."""
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class WorkerResult:
    """Result from worker execution."""
    success: bool
    operation_name: Optional[str] = None       # First op name (backward compat)
    scene_id: Optional[str] = None             # First scene ID (backward compat)
    operation_names: List[str] = None           # ALL op names (ordered)
    scene_ids: List[str] = None                 # ALL scene IDs (ordered)
    output_uris: list = None
    media_ids: list = None                      # T2I: mediaIds for upscale API
    error: Optional[str] = None
    data: dict = None                           # Raw response data (for debugging)
    
    def __post_init__(self):
        if self.output_uris is None:
            self.output_uris = []
        if self.operation_names is None:
            self.operation_names = []
        if self.scene_ids is None:
            self.scene_ids = []
        if self.media_ids is None:
            self.media_ids = []


class PromptExecutor:
    """THỢ — Prompt executor.
    
    Receives: task + account + project_id
    Executes: API call with assigned account
    Reports: Progress back to Dispatcher
    """
    
    def __init__(
        self,
        worker_id: str,
        api_client: VEOApiClient,
        on_progress: Optional[Callable[[str, int], None]] = None,
        on_complete: Optional[Callable[[str, WorkerResult], None]] = None,
    ):
        self.worker_id = worker_id
        self._api_client = api_client
        self._on_progress = on_progress
        self._on_complete = on_complete
        
        self.state = WorkerState.IDLE
        self._current_task: Optional[Task] = None
        self._stop_event = asyncio.Event()
    
    @property
    def is_busy(self) -> bool:
        return self.state == WorkerState.BUSY
    
    @property
    def current_task_id(self) -> Optional[str]:
        return self._current_task.id if self._current_task else None
    
    async def execute(
        self,
        task: Task,
        account: AccountManager,
        paygate_tier: str = "PAYGATE_TIER_TWO",
    ) -> WorkerResult:
        """Execute a task using the assigned account.
        
        Args:
            task: The task to execute
            account: Account manager with valid tokens
            paygate_tier: Auto-detected from /v1/credits
        
        Returns:
            WorkerResult with success/failure info
        """
        self.state = WorkerState.BUSY
        self._current_task = task
        
        try:
            # === Stage 1: Token Validation (5%) ===
            self._report_progress(task.id, 5, "🔑 Validating tokens")
            
            # Gap #3 FIX: Use centralized ensure_valid_token() —
            # same method used by engine upscale path and upscale_queue.
            # Handles: check expiry → auto-refresh → return token or None.
            access_token = await account.ensure_valid_token()
            if not access_token:
                return WorkerResult(
                    success=False,
                    error="Access token expired and refresh failed"
                )
            
            recaptcha_token = account.get_recaptcha_token()
            
            log.debug(
                f"[Worker] access_token={'VALID(' + str(len(access_token)) + ' chars)' if access_token else 'NONE/EMPTY'}, "
                f"recaptcha={'VALID(' + str(len(recaptcha_token)) + ' chars)' if recaptcha_token else 'NONE/EMPTY'}, "
                f"token_expired={account._session.is_token_expired}"
            )
            
            # === Stage 2: reCAPTCHA Refresh (10%) ===
            # Bug #11 fix: Use per-account lock to serialize with upscale queue
            if not recaptcha_token or account.session.needs_recaptcha_refresh:
                self._report_progress(task.id, 8, "🔄 Refreshing reCAPTCHA")
                async with account.recaptcha_lock:
                    recaptcha_token = await account.refresh_recaptcha()
                if not recaptcha_token:
                    return WorkerResult(
                        success=False,
                        error="reCAPTCHA token expired and refresh failed"
                    )
            
            # Gap #1 fix: Validate reCAPTCHA quality
            # Garbage tokens (<1000 chars) from extension glitches cause 403
            # HAR verified: valid tokens are 1742-2169 chars
            if recaptcha_token and len(recaptcha_token) < 1000:
                log.warning(
                    f"[Worker] reCAPTCHA token too short ({len(recaptcha_token)} chars, need ≥1000), "
                    f"invalidating and retrying once"
                )
                account.invalidate_recaptcha()
                async with account.recaptcha_lock:
                    recaptcha_token = await account.refresh_recaptcha()
                if not recaptcha_token or len(recaptcha_token) < 1000:
                    return WorkerResult(
                        success=False,
                        error=f"reCAPTCHA token garbage ({len(recaptcha_token or '')} chars, need ≥1000)"
                    )
            
            self._report_progress(task.id, 10, "✅ reCAPTCHA ready")
            
            # === Stage 3: Submitting to API (15%) ===
            account_headers = account.get_api_headers()
            self._report_progress(task.id, 15, "📤 Submitting request")
            
            # Route to appropriate API method
            log.info(
                f"[Worker] Dispatching {task.workflow_type} task={task.id} "
                f"output_count={task.output_count} account={getattr(task, 'assigned_account', 'N/A')}"
            )
            result = await self._execute_workflow(
                task,
                access_token or "",
                recaptcha_token,
                account.project_id,
                account_headers=account_headers,
                paygate_tier=paygate_tier,
                # HAR verified: website does NOT send x-goog-request-params
            )
            
            # M2 FIX: Centralized reCAPTCHA invalidation — single-use tokens
            # must be consumed after EVERY API call (success or failure).
            # This replaces scattered invalidate calls in engine.py worker loop.
            account.invalidate_recaptcha()
            
            # === Stage 4: API Response Received (20%) ===
            self._report_progress(task.id, 20, "✅ Request accepted")
            
            if result.success:
                log.info(
                    f"[Worker] Task {task.id} accepted: "
                    f"ops={len(result.operation_names)} outputs={len(result.output_uris)}"
                )
            else:
                log.warning(
                    f"[Worker] Task {task.id} failed: {result.error}"
                )
            
            return result
            
        except Exception as e:
            self.state = WorkerState.ERROR
            log.error(f"[Worker] Task {task.id} exception: {e}", exc_info=True)
            return WorkerResult(success=False, error=str(e))
        finally:
            self.state = WorkerState.IDLE
            self._current_task = None
    
    async def _execute_workflow(
        self,
        task: Task,
        access_token: str,
        recaptcha_token: str,
        project_id: Optional[str],
        account_headers: Optional[dict] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        extra_headers: Optional[dict] = None,
    ) -> WorkerResult:
        """Execute the appropriate workflow based on task type."""
        
        # Merge extra headers (e.g. idempotency key) into account headers
        if extra_headers and account_headers:
            account_headers = {**account_headers, **extra_headers}
        elif extra_headers:
            account_headers = extra_headers
        
        # workflow_type is stored as name string ("T2V"), convert to enum
        wt = task.workflow_type
        try:
            workflow = WorkflowType[wt] if isinstance(wt, str) else wt
        except (KeyError, TypeError):
            # Bug 4 fix: Fallback to value-based lookup (e.g., "text_to_video")
            try:
                workflow = WorkflowType(wt) if isinstance(wt, str) else wt
            except (ValueError, TypeError):
                workflow = wt  # last resort fallback
        
        if workflow == WorkflowType.T2V:
            response = await self._api_client.generate_video_t2v(
                access_token=access_token,
                recaptcha_token=recaptcha_token,
                prompt=task.prompt,
                aspect_ratio=task.aspect_ratio,
                model=task.model,
                output_count=task.output_count,
                seed=task.seed,
                project_id=project_id or "",
                paygate_tier=paygate_tier,
                account_headers=account_headers,
            )
            
        elif workflow == WorkflowType.I2V:
            if len(task.image_uris) >= 2:
                # Dual frame (start + end)
                response = await self._api_client.generate_video_i2v_dual(
                    access_token=access_token,
                    recaptcha_token=recaptcha_token,
                    prompt=task.prompt,
                    start_image_media_id=task.image_uris[0],
                    end_image_media_id=task.image_uris[1],
                    aspect_ratio=task.aspect_ratio,
                    model=task.model,
                    output_count=task.output_count,
                    seed=task.seed,
                    project_id=project_id or "",
                    paygate_tier=paygate_tier,
                    account_headers=account_headers,
                )
            elif len(task.image_uris) == 1:
                # Single frame
                response = await self._api_client.generate_video_i2v_single(
                    access_token=access_token,
                    recaptcha_token=recaptcha_token,
                    prompt=task.prompt,
                    image_media_id=task.image_uris[0],
                    aspect_ratio=task.aspect_ratio,
                    model=task.model,
                    output_count=task.output_count,
                    seed=task.seed,
                    project_id=project_id or "",
                    paygate_tier=paygate_tier,
                    account_headers=account_headers,
                )
            else:
                return WorkerResult(success=False, error="I2V requires at least 1 image")
            
        elif workflow == WorkflowType.R2V:
            if not task.image_uris:
                return WorkerResult(success=False, error="R2V requires reference images")
            
            response = await self._api_client.generate_video_r2v(
                access_token=access_token,
                recaptcha_token=recaptcha_token,
                prompt=task.prompt,
                reference_image_media_ids=task.image_uris[:3],
                aspect_ratio=task.aspect_ratio,
                model=task.model,
                output_count=task.output_count,
                seed=task.seed,
                project_id=project_id or "",
                paygate_tier=paygate_tier,
                account_headers=account_headers,
            )
            
        elif workflow == WorkflowType.T2I:
            if not project_id:
                return WorkerResult(success=False, error="T2I requires project_id")
            
            response = await self._api_client.generate_image(
                access_token=access_token,
                recaptcha_token=recaptcha_token,
                project_id=project_id,
                prompt=task.prompt,
                aspect_ratio=task.aspect_ratio,
                model=task.model or "GEM_PIX_2",
                output_count=task.output_count,
                paygate_tier=paygate_tier,
                account_headers=account_headers,
            )
            
        elif workflow == WorkflowType.F2V:
            # Frames to Video (continuation)
            if len(task.image_uris) >= 1:
                # VEO uses continuation frame as START frame (always)
                # Extracted from end of previous video → start of next
                frame_pos = "START"
                response = await self._api_client.generate_video_i2v_single(
                    access_token=access_token,
                    recaptcha_token=recaptcha_token,
                    prompt=task.prompt,
                    image_media_id=task.image_uris[0],
                    aspect_ratio=task.aspect_ratio,
                    model=task.model,
                    output_count=task.output_count,
                    seed=task.seed,
                    project_id=project_id or "",
                    paygate_tier=paygate_tier,
                    account_headers=account_headers,
                )
            else:
                return WorkerResult(success=False, error="F2V requires continuation frame")
            
        elif workflow == WorkflowType.I2I:
            # Image to Image (edit/transform)
            if not project_id:
                return WorkerResult(success=False, error="I2I requires project_id")
            
            # Build imageInputs from uploaded image mediaGenerationIds
            # HAR: [{name: "CAMaJ...", imageInputType: "IMAGE_INPUT_TYPE_REFERENCE"}]
            image_inputs = []
            if task.image_uris:
                for uri in task.image_uris:
                    image_inputs.append({
                        "name": uri,
                        "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE",
                    })
            
            response = await self._api_client.generate_image(
                access_token=access_token,
                recaptcha_token=recaptcha_token,
                project_id=project_id,
                prompt=task.prompt,
                aspect_ratio=task.aspect_ratio,
                model=task.model or "GEM_PIX_2",
                output_count=task.output_count,
                image_inputs=image_inputs,
                paygate_tier=paygate_tier,
                account_headers=account_headers,
            )
        
        else:
            return WorkerResult(success=False, error=f"Unknown workflow: {workflow}")
        
        # Process response
        return self._process_response(response)
    
    def _process_response(self, response: APIResponse) -> WorkerResult:
        """Process API response into WorkerResult.
        
        Handles both:
        - Async video ops: {operations: [{operation: {name}, sceneId}]}
        - Sync image gen: {media: [{name, image: {generatedImage: {fifeUrl, mediaGenerationId}}}]}
        """
        if not response.success:
            return WorkerResult(success=False, error=response.error)
        
        data = response.data or {}
        
        # Extract ALL operation name(s) for async operations (video, ordered)
        operation_names = []
        scene_ids = []
        if "operations" in data:
            for op in data["operations"]:
                op_obj = op.get("operation", {})
                name = op_obj.get("name") if isinstance(op_obj, dict) else None
                if name:
                    operation_names.append(name)
                sid = op.get("sceneId", "")
                scene_ids.append(sid)
        
        # Extract direct outputs for sync operations
        output_uris = []
        media_ids = []
        
        # HAR: batchGenerateImages returns {media: [{image: {generatedImage: {fifeUrl, ...}}}]}
        if "media" in data:
            for item in data["media"]:
                gen_img = (item.get("image") or {}).get("generatedImage", {})
                fife_url = gen_img.get("fifeUrl", "")
                media_id = item.get("mediaId", "") or item.get("name", "")
                if fife_url:
                    output_uris.append(fife_url)
                    media_ids.append(media_id)
                elif media_id:
                    output_uris.append(media_id)
        
        # Fallback: older format with generatedImages
        if not output_uris and "generatedImages" in data:
            for img in data["generatedImages"]:
                if "imageUri" in img:
                    output_uris.append(img["imageUri"])
        
        return WorkerResult(
            success=True,
            operation_name=operation_names[0] if operation_names else None,
            scene_id=scene_ids[0] if scene_ids else None,
            operation_names=operation_names,
            scene_ids=scene_ids,
            output_uris=output_uris,
            media_ids=media_ids,
        )
    
    def _report_progress(self, task_id: str, progress: int, status_text: str = ""):
        """Report progress to callback."""
        if self._on_progress:
            self._on_progress(task_id, progress, status_text)
    
    def stop(self):
        """Signal worker to stop."""
        self._stop_event.set()
    
    def get_status(self) -> dict:
        """Get worker status."""
        return {
            "worker_id": self.worker_id,
            "state": self.state.value,
            "current_task": self.current_task_id,
        }


# Backward compat alias
Worker = PromptExecutor
