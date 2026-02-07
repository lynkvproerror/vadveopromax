"""
VEO Pro Max - Worker (THỢ)

Reference: MULTITHREADING_ARCHITECTURE.md
Role: Execute individual tasks using assigned account

Architecture: Asyncio (Hybrid with ProcessPoolExecutor for CPU tasks)
"""

from typing import Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.dispatcher import Task, TaskState
from core.account_manager import AccountManager
from core.api_client import VEOApiClient, APIResponse
from config.constants import WorkflowType


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
    operation_name: Optional[str] = None
    output_uris: list = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.output_uris is None:
            self.output_uris = []


class Worker:
    """THỢ - Executes individual tasks.
    
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
    ) -> WorkerResult:
        """Execute a task using the assigned account.
        
        Args:
            task: The task to execute
            account: Account manager with valid tokens
        
        Returns:
            WorkerResult with success/failure info
        """
        self.state = WorkerState.BUSY
        self._current_task = task
        
        try:
            # Get tokens
            access_token = account.get_access_token()
            recaptcha_token = account.get_recaptcha_token()
            
            if not access_token or not recaptcha_token:
                return WorkerResult(
                    success=False,
                    error="Invalid tokens - refresh required"
                )
            
            # Report starting
            self._report_progress(task.id, 10)
            
            # Route to appropriate API method
            result = await self._execute_workflow(
                task,
                access_token,
                recaptcha_token,
                account.project_id
            )
            
            # Report completion
            self._report_progress(task.id, 100)
            
            return result
            
        except Exception as e:
            self.state = WorkerState.ERROR
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
    ) -> WorkerResult:
        """Execute the appropriate workflow based on task type."""
        
        workflow = task.workflow_type
        
        if workflow == WorkflowType.T2V:
            response = await self._api_client.generate_video_t2v(
                access_token=access_token,
                recaptcha_token=recaptcha_token,
                prompt=task.prompt,
                aspect_ratio=task.aspect_ratio,
                duration_seconds=task.duration_seconds,
                model=task.model,
                output_count=task.output_count,
                seed=task.seed,  # Pass seed for reproducibility
            )
            
        elif workflow == WorkflowType.I2V:
            if len(task.image_uris) >= 2:
                # Dual frame (start + end)
                response = await self._api_client.generate_video_i2v_dual(
                    access_token=access_token,
                    recaptcha_token=recaptcha_token,
                    prompt=task.prompt,
                    start_image_uri=task.image_uris[0],
                    end_image_uri=task.image_uris[1],
                    aspect_ratio=task.aspect_ratio,
                    duration_seconds=task.duration_seconds,
                    model=task.model,
                    output_count=task.output_count,
                    seed=task.seed,  # Pass seed for reproducibility
                )
            elif len(task.image_uris) == 1:
                # Single frame
                response = await self._api_client.generate_video_i2v_single(
                    access_token=access_token,
                    recaptcha_token=recaptcha_token,
                    prompt=task.prompt,
                    image_uri=task.image_uris[0],
                    aspect_ratio=task.aspect_ratio,
                    duration_seconds=task.duration_seconds,
                    model=task.model,
                    output_count=task.output_count,
                    seed=task.seed,  # Pass seed for reproducibility
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
                reference_image_uris=task.image_uris[:3],
                aspect_ratio=task.aspect_ratio,
                duration_seconds=task.duration_seconds,
                model=task.model,
                output_count=task.output_count,
                seed=task.seed,  # Pass seed for reproducibility
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
                output_count=task.output_count,
            )
            
        elif workflow == WorkflowType.F2V:
            # Frames to Video (continuation)
            if len(task.image_uris) >= 1:
                response = await self._api_client.generate_video_i2v_single(
                    access_token=access_token,
                    recaptcha_token=recaptcha_token,
                    prompt=task.prompt,
                    image_uri=task.image_uris[0],
                    frame_position="START",
                    aspect_ratio=task.aspect_ratio,
                    duration_seconds=task.duration_seconds,
                    model=task.model,
                    output_count=task.output_count,
                    seed=task.seed,  # Pass seed for reproducibility
                )
            else:
                return WorkerResult(success=False, error="F2V requires continuation frame")
            
        else:
            return WorkerResult(success=False, error=f"Unknown workflow: {workflow}")
        
        # Process response
        return self._process_response(response)
    
    def _process_response(self, response: APIResponse) -> WorkerResult:
        """Process API response into WorkerResult."""
        if not response.success:
            return WorkerResult(success=False, error=response.error)
        
        data = response.data or {}
        
        # Extract operation name(s) for async operations
        operation_name = None
        if "operations" in data:
            ops = data["operations"]
            if ops and len(ops) > 0:
                operation_name = ops[0].get("name")
        
        # Extract direct outputs for sync operations (like T2I)
        output_uris = []
        if "generatedImages" in data:
            for img in data["generatedImages"]:
                if "imageUri" in img:
                    output_uris.append(img["imageUri"])
        
        return WorkerResult(
            success=True,
            operation_name=operation_name,
            output_uris=output_uris,
        )
    
    def _report_progress(self, task_id: str, progress: int):
        """Report progress to callback."""
        if self._on_progress:
            self._on_progress(task_id, progress)
    
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
