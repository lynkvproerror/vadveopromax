"""
VEO Pro Max - Orchestration Engine

Reference: ARCHITECTURE_OVERVIEW.md (lines 94-120)
Role: Connects ĐẠI CHỦ ↔ THẦU ↔ THỢ into a working pipeline

Architecture: Hybrid Asyncio + ProcessPoolExecutor
- asyncio Event Loop (Main): ĐẠI CHỦ, THẦU, TaskGroup
- asyncio.TaskGroup: manages Worker coroutines
- ProcessPoolExecutor: CPU-bound tasks (ffmpeg, image processing)
"""

from typing import Optional, List, Callable
from concurrent.futures import ProcessPoolExecutor
import asyncio
import base64
import os
import random
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.multi_account import MultiAccountManager
from core.account_manager import AccountManager
from core.dispatcher import Dispatcher, Task, TaskState
from core.worker import Worker, WorkerResult
from core.api_client import VEOApiClient
from core.frame_extractor import FrameExtractor
from core.trpc_client import TRPCClient

log = logging.getLogger(__name__)


class Engine:
    """Orchestration Engine - Connects all layers.
    
    Pipeline flow:
    1. Dispatcher.get_next_task()  →  get ready task from queue
    2. MultiAccountManager.acquire_slot()  →  get available account
    3. ProjectManager.get_or_create_project()  →  ensure project exists
    4. Worker.execute(task, account)  →  run API calls
    5. AccountManager.release_slot()  →  return slot to pool
    6. Dispatcher.complete_task() / fail_task()  →  update state
    """
    
    def __init__(
        self,
        account_manager: MultiAccountManager,
        dispatcher: Dispatcher,
        api_client: VEOApiClient,
        max_cpu_workers: Optional[int] = None,
        profiles_controller=None,
    ):
        self._account_manager = account_manager
        self._dispatcher = dispatcher
        self._api_client = api_client
        # A1/A2: ProjectManager is now per-account (CHỦ owns it)
        # No longer a shared singleton here
        self._frame_extractor = FrameExtractor()
        self._profiles_controller = profiles_controller  # For auto re-login
        
        # Workers are now created per-account in start() — no global max_workers
        self._process_pool = ProcessPoolExecutor(
            max_workers=max_cpu_workers or os.cpu_count() or 4
        )
        
        self._workers: List[Worker] = []
        self._running = False
        self._stop_event = asyncio.Event()
        
        # Continuation settings (forwarded from AppController.start_processing)
        self._continuation_enabled = True  # C5: global toggle
        self._extract_point_ms = 750       # Default extract point
        
        # Callbacks for UI updates
        self._on_task_started: Optional[Callable] = None
        self._on_task_completed: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def stop(self):
        """Stop the engine gracefully.
        
        Sets the stop event, causing all worker loops to exit.
        The start() method's finally block handles browser cleanup.
        """
        if not self._running:
            return
        
        log.info("Engine stop requested — signaling workers to exit")
        self._stop_event.set()
        
        # Give workers a moment to finish current iteration
        await asyncio.sleep(0.5)
    
    async def start(self):
        """Start the engine main loop.
        
        Per-Account Worker Architecture:
        1. Start persistent browsers for all accounts (reCAPTCHA refresh)
        2. For each enabled account (CHỦ), create N worker coroutines
           where N = account.max_slots (0-4, configurable per-account)
        3. All workers pull from the SAME global task queue (THẦU)
           → cross-project, cross-account work distribution
        """
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        
        # Start persistent browsers for reCAPTCHA refresh
        try:
            await self._account_manager.startup_browsers(headless=True)
        except Exception as e:
            log.error(f"Failed to start browsers: {e}")
        
        # Diagnostic logging
        total_accounts = len(self._account_manager._accounts)
        ready_tasks = self._dispatcher.ready_count
        log.info(f"Engine starting: {total_accounts} accounts, {ready_tasks} ready tasks in queue")
        
        if total_accounts == 0:
            log.error("No accounts in pool — did sync_profiles_to_runtime() succeed?")
            self._running = False
            return
        
        if ready_tasks == 0:
            log.warning("Ready queue is EMPTY — workers will idle until tasks are submitted")
        
        try:
            async with asyncio.TaskGroup() as tg:
                # Create workers PER ACCOUNT based on each account's max_slots
                for account in self._account_manager._accounts:
                    if not account.is_enabled or account.max_slots == 0:
                        log.info(f"Account {account.email}: skipped (enabled={account.is_enabled}, slots={account.max_slots})")
                        continue
                    
                    for i in range(account.max_slots):
                        worker = Worker(
                            worker_id=f"worker-{account.email[:8]}-{i}",
                            api_client=self._api_client,
                            on_progress=self._on_progress,
                        )
                        self._workers.append(worker)
                        tg.create_task(self._account_worker_loop(worker, account))
                    
                    log.info(f"Account {account.email}: {account.max_slots} workers created (retry={account.retry_count}, timeout={account.request_timeout}s)")
        except* Exception as eg:
            for exc in eg.exceptions:
                if not isinstance(exc, asyncio.CancelledError):
                    log.error(f"Worker error: {exc}")
        finally:
            # Shutdown browsers on engine stop
            try:
                await self._account_manager.shutdown_browsers()
            except Exception as e:
                log.error(f"Browser shutdown error: {e}")
            self._running = False
            self._workers.clear()
    
    async def _account_worker_loop(self, worker: Worker, account: AccountManager):
        """Worker loop bound to a specific account (CHỦ).
        
        Each worker is dedicated to ONE account but pulls tasks from 
        the GLOBAL task queue (THẦU). This ensures:
        - Per-account slot limit is respected (max_slots)
        - Cross-project work distribution (any worker can take any task)
        - No task duplication (atomic get_next_task)
        - Per-account retry and timeout settings
        
        Retry logic: exponential backoff for non-auth errors.
        Timeout: asyncio.wait_for wraps execute call.
        """
        while not self._stop_event.is_set():
            try:
                # Step 1: Acquire slot from THIS account
                if not account.acquire_slot():
                    await asyncio.sleep(0.5)
                    continue
                
                try:
                    # Step 2: Get next task from GLOBAL queue (THẦU)
                    task = self._dispatcher.get_next_task()
                    if not task:
                        account.release_slot()
                        await asyncio.sleep(0.5)
                        continue
                    
                    # D2: Account affinity check — continuation tasks must run on same account
                    if task.required_account and task.required_account != account.email:
                        # Re-queue for correct account, release our slot
                        self._dispatcher.submit_task(task)
                        account.release_slot()
                        await asyncio.sleep(0.1)
                        continue
                    
                    # Step 3: Lazy browser start if not yet initialized
                    if not account._browser_session or not account._browser_session.is_ready:
                        try:
                            await account.ensure_browser(headless=True)
                        except Exception as e:
                            log.warning(f"Browser start failed for {account.email}: {e} (continuing without persistent browser)")
                    
                    # Step 4: Preemptive reCAPTCHA refresh
                    if not account.get_recaptcha_token():
                        try:
                            token = await account.refresh_recaptcha()
                            if not token:
                                log.warning(f"reCAPTCHA refresh failed for {account.email}, proceeding anyway")
                        except Exception as e:
                            log.warning(f"reCAPTCHA refresh error for {account.email}: {e}")
                    
                    # Step 5: Ensure project exists (CHỦ's ProjectManager)
                    if not account.project_id:
                        trpc_client = None
                        if account._browser_session and account._browser_session.is_ready:
                            trpc_client = TRPCClient(account._browser_session._page)
                        
                        project_id = await account.project_manager.get_or_create_project(
                            email=account.email,
                            access_token=account.get_access_token(),
                            api_client=self._api_client,
                            trpc_client=trpc_client,
                        )
                        if project_id:
                            account.set_project_id(project_id)
                    
                    # Step 5.5: Auto-detect paygate tier (once per account)
                    if account.paygate_tier == "PAYGATE_TIER_NOT_PAID":
                        await account.fetch_paygate_tier(self._api_client)
                    
                    # Notify UI
                    task.assigned_account = account.email
                    task.project_id = account.project_id
                    if self._on_task_started:
                        self._on_task_started(task)
                    
                    # Step 6: Anti-Detect Spam — random delay
                    if getattr(self, '_anti_detect_enabled', True):
                        delay_min = getattr(self, '_anti_detect_delay_min', 1.0)
                        delay_max = getattr(self, '_anti_detect_delay_max', 5.0)
                        delay = random.uniform(delay_min, delay_max)
                        log.debug(f"Worker {worker.worker_id}: anti-detect delay {delay:.6f}s before submit")
                        await asyncio.sleep(delay)
                    
                    # Step 7: Execute with RETRY + TIMEOUT
                    max_retries = account.retry_count
                    timeout = account.request_timeout
                    result = None
                    
                    for attempt in range(max_retries + 1):
                        try:
                            result = await asyncio.wait_for(
                                worker.execute(task, account, paygate_tier=account.paygate_tier),
                                timeout=timeout,
                            )
                        except asyncio.TimeoutError:
                            result = WorkerResult(
                                success=False,
                                error=f"Request timed out after {timeout}s"
                            )
                        
                        if result.success:
                            break  # Success — exit retry loop
                        
                        # Auth errors → special handling, no retry
                        if self._is_auth_error(result.error or ""):
                            break
                        
                        # Non-auth error — retry with backoff
                        task.retry_attempts = attempt + 1
                        if attempt < max_retries:
                            backoff = min(2 ** (attempt + 1), 30)
                            log.warning(
                                f"Worker {worker.worker_id}: task {task.id} failed "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {result.error}. "
                                f"Retrying in {backoff}s..."
                            )
                            await asyncio.sleep(backoff)
                    
                    # Step 8: Process final result
                    if result and result.success:
                        # For async operations, start polling
                        if result.operation_name:
                            task.operation_name = result.operation_name
                            task.state = TaskState.WAITING_POLL
                            await self._poll_operation(task, account)
                        else:
                            # Sync operation (T2I) - already complete
                            self._dispatcher.complete_task(
                                task.id,
                                output_uris=result.output_uris,
                            )
                            if self._on_task_completed:
                                self._on_task_completed(task)
                    elif result:
                        error_msg = result.error or "Unknown error"
                        
                        if self._is_auth_error(error_msg):
                            # Auth error → attempt auto re-login
                            log.warning(f"Auth error for {account.email}: {error_msg}")
                            log.info(f"Attempting auto re-login for {account.email}...")
                            
                            relogin_ok = await self._try_auto_relogin(account.email)
                            
                            if relogin_ok:
                                log.info(f"✅ Re-login OK for {account.email}, re-queuing task {task.id}")
                                task.state = TaskState.READY
                                task.assigned_account = None
                                self._dispatcher.submit_task(task)
                            else:
                                log.error(f"❌ Re-login failed for {account.email}")
                                self._dispatcher.fail_task(
                                    task.id,
                                    f"{error_msg} (auto re-login failed)"
                                )
                                if self._on_task_failed:
                                    self._on_task_failed(task, error_msg)
                        else:
                            # Non-auth error after all retries exhausted
                            retry_info = f" (after {task.retry_attempts} retries)" if task.retry_attempts > 0 else ""
                            final_error = f"{error_msg}{retry_info}"
                            log.error(f"Task {task.id} PERMANENTLY FAILED: {final_error}")
                            self._dispatcher.fail_task(task.id, final_error)
                            if self._on_task_failed:
                                self._on_task_failed(task, final_error)
                
                finally:
                    # Release slot AFTER task fully complete (including polling)
                    await self._account_manager.release_slot(account.email)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Worker {worker.worker_id} unexpected error: {e}")
                await asyncio.sleep(1.0)
    
    async def _poll_operation(self, task: Task, account: AccountManager):
        """Poll for async operation completion.
        
        Uses exponential backoff within reasonable bounds.
        """
        from config.constants import AppConstants
        
        poll_interval = AppConstants.POLL_INTERVAL
        max_poll_time = AppConstants.MAX_POLL_TIME
        elapsed = 0
        
        while elapsed < max_poll_time and not self._stop_event.is_set():
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            try:
                # Doc §6.20: Track current status for each operation
                current_status = getattr(task, '_poll_status', 'MEDIA_GENERATION_STATUS_PENDING')
                
                response = await self._api_client.check_status(
                    access_token=account.get_access_token(),
                    recaptcha_token="",  # Not needed for polling (HAR verified)
                    operations=[{
                        "operation": {"name": task.operation_name},
                        "sceneId": getattr(task, 'scene_id', ''),
                        "status": current_status,
                    }],
                    account_headers=account.get_api_headers(),  # Issue 10: per-account headers
                )
                
                if not response.success:
                    continue
                
                # Doc §6.20: Status is per-operation inside operations[]
                ops = response.data.get("operations", [])
                if not ops:
                    continue
                
                # Check if ALL operations are SUCCESSFUL
                all_successful = all(
                    op.get("status") == "MEDIA_GENERATION_STATUS_SUCCESSFUL"
                    for op in ops
                )
                any_failed = any(
                    op.get("status") == "MEDIA_GENERATION_STATUS_FAILED"
                    for op in ops
                )
                
                # Update tracked status for next poll request
                if ops:
                    task._poll_status = ops[0].get("status", current_status)
                
                if all_successful:
                    # Extract output URIs from operations[].servingBaseUri
                    output_uris = self._extract_output_uris(response.data)
                    
                    # Auto-upscale if quality > 720p
                    if task.download_quality != "720p" and output_uris:
                        upscaled = await self._auto_upscale(
                            task, account, output_uris
                        )
                        if upscaled:
                            output_uris = upscaled
                    
                    # Download videos to output_folder
                    local_paths = await self._download_outputs(task, output_uris)
                    if local_paths:
                        task.output_uris = local_paths  # Replace URLs with local paths
                    
                    # FFmpeg pipeline: extract frame for continuation children
                    continuation_frame_uri = None
                    if (
                        self._continuation_enabled  # C5: respect settings toggle
                        and self._dispatcher.has_children(task.id)
                        and output_uris
                    ):
                        continuation_frame_uri = await self._extract_continuation_frame(
                            task, account, output_uris[0]
                        )
                    
                    self._dispatcher.complete_task(
                        task.id,
                        output_uris=output_uris,
                        continuation_frame_uri=continuation_frame_uri,
                    )
                    if self._on_task_completed:
                        self._on_task_completed(task)
                    return
                
                elif any_failed:
                    failed_op = next(op for op in ops if op.get("status") == "MEDIA_GENERATION_STATUS_FAILED")
                    error = failed_op.get("error", {}).get("message", "Generation failed")
                    self._dispatcher.fail_task(task.id, str(error))
                    if self._on_task_failed:
                        self._on_task_failed(task, str(error))
                    return
                
                else:
                    # Still ACTIVE or PENDING
                    progress = min(90, int(elapsed / max_poll_time * 90))
                    self._dispatcher.update_progress(task.id, progress)
                    
            except Exception:
                continue
        
        # Timeout
        self._dispatcher.fail_task(task.id, f"Polling timeout ({max_poll_time}s)")
    
    def _extract_output_uris(self, data: dict) -> list:
        """Extract output URIs from poll response.
        
        Per HAR §3.3.3: URIs are deeply nested:
          operations[].operation.metadata.video.fifeUrl  (video download)
          operations[].operation.metadata.video.servingBaseUri  (thumbnail)
          operations[].operation.metadata.image.generatedImage.fifeUrl  (image)
        """
        uris = []
        for op in data.get("operations", []):
            metadata = (
                op.get("operation", {})
                .get("metadata", {})
            )
            # Video result
            video = metadata.get("video", {})
            if video:
                uri = video.get("fifeUrl") or video.get("servingBaseUri")
                if uri:
                    uris.append(uri)
                    continue
            # Image result
            image = metadata.get("image", {}).get("generatedImage", {})
            if image:
                uri = image.get("fifeUrl")
                if uri:
                    uris.append(uri)
        return uris
    
    async def _extract_continuation_frame(
        self, task: Task, account: AccountManager, video_uri: str
    ) -> Optional[str]:
        """FFmpeg pipeline: download → extract → base64 → upload → mediaId.
        
        Returns uploaded mediaId (image URI) or None on error.
        """
        try:
            if not self._frame_extractor.is_available:
                log.warning("FFmpeg not available, skipping continuation frame extraction")
                return None
            
            # 1. Download video to temp file
            import aiohttp
            import tempfile
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_uri) as resp:
                    if resp.status != 200:
                        log.error(f"Failed to download video: HTTP {resp.status}")
                        return None
                    video_bytes = await resp.read()
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(
                suffix=".mp4", delete=False, dir=str(self._frame_extractor.get_temp_dir())
            ) as tmp:
                tmp.write(video_bytes)
                video_path = tmp.name
            
            # 2. Extract frame via FFmpeg (CPU-bound, run in process pool)
            # C3: VEO only uses start frame input → always extract from END
            loop = asyncio.get_event_loop()
            frame_path = await loop.run_in_executor(
                self._process_pool,
                self._frame_extractor.extract_frame,
                video_path,
                None,  # auto-generate output path
                task.extract_point_ms,  # C4: use Task field directly
                True   # C3: always from_end=True (VEO start frame)
            )
            
            # Cleanup temp video
            Path(video_path).unlink(missing_ok=True)
            
            if not frame_path:
                log.error("Frame extraction failed")
                return None
            
            # 3. Base64 encode
            with open(frame_path, "rb") as f:
                frame_b64 = base64.b64encode(f.read()).decode()
            
            # Cleanup temp frame
            Path(frame_path).unlink(missing_ok=True)
            
            # 4. Upload image to VEO API
            # Use account's own reCAPTCHA token (not the old module)
            recaptcha_token = account.get_recaptcha_token() or ""
            if not recaptcha_token:
                token = await account.refresh_recaptcha()
                recaptcha_token = token or ""
            
            upload_resp = await self._api_client.upload_image(
                access_token=account.get_access_token(),
                recaptcha_token=recaptcha_token,
                image_base64=frame_b64,
                account_headers=account.get_api_headers(),  # Issue 10: per-account headers
            )
            
            if upload_resp.success:
                # HAR verified: response is {"mediaGenerationId": {"mediaGenerationId": "..."}}
                mgid = upload_resp.data.get("mediaGenerationId", {})
                if isinstance(mgid, dict):
                    media_id = mgid.get("mediaGenerationId")
                else:
                    media_id = mgid  # Fallback if flat string
                log.info(f"Continuation frame uploaded: {media_id}")
                return media_id
            else:
                log.error(f"Frame upload failed: {upload_resp.error}")
                return None
            
        except Exception as e:
            log.error(f"Continuation frame pipeline error: {e}")
            return None
    
    async def _auto_upscale(
        self, task: Task, account: AccountManager, output_uris: list
    ) -> list:
        """Auto-upscale videos if download_quality > 720p.
        
        Protocol §3.3.3: batchAsyncGenerateVideoUpsampleVideo
        Maps quality → VIDEO_RESOLUTION_* enum.
        """
        quality_map = {
            "1080p": "VIDEO_RESOLUTION_1080P",
            "4K": "VIDEO_RESOLUTION_4K",
        }
        resolution = quality_map.get(task.download_quality)
        if not resolution:
            return output_uris  # 720p or unknown → no upscale
        
        model_map = {
            "VIDEO_RESOLUTION_1080P": "veo_3_1_upsampler_1080p",
            "VIDEO_RESOLUTION_4K": "veo_3_1_upsampler_4k",
        }
        
        upscaled_uris = []
        for uri in output_uris:
            try:
                # Need mediaId from the URI — extract from poll response
                # The uri here is fifeUrl; we need a mediaId for upscale
                # For now, use the operation metadata approach
                recaptcha_token = account.get_recaptcha_token() or ""
                if not recaptcha_token:
                    token = await account.refresh_recaptcha()
                    recaptcha_token = token or ""
                
                from core.api_client import generate_random_seed
                resp = await self._api_client.upscale_video(
                    access_token=account.get_access_token() or "",
                    recaptcha_token=recaptcha_token,
                    media_id=uri,  # fifeUrl doubles as mediaId in some flows
                    resolution=resolution,
                    aspect_ratio=task.aspect_ratio,
                    seed=generate_random_seed(),
                    account_headers=account.get_api_headers(),
                )
                
                if resp.success:
                    # Poll upscale operation
                    ops = resp.data.get("operations", [])
                    if ops:
                        op_name = ops[0].get("operation", {}).get("name", "")
                        if op_name:
                            # Simple poll loop for upscale
                            for _ in range(60):  # max 5 min
                                await asyncio.sleep(5)
                                poll_resp = await self._api_client.check_status(
                                    access_token=account.get_access_token() or "",
                                    recaptcha_token="",
                                    operations=[{
                                        "operation": {"name": op_name},
                                        "status": "MEDIA_GENERATION_STATUS_PENDING",
                                    }],
                                    account_headers=account.get_api_headers(),
                                )
                                if poll_resp.success:
                                    poll_ops = poll_resp.data.get("operations", [])
                                    if poll_ops and poll_ops[0].get("status") == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                                        upscaled_uri = self._extract_output_uris(poll_resp.data)
                                        if upscaled_uri:
                                            upscaled_uris.extend(upscaled_uri)
                                        break
                                    elif poll_ops and poll_ops[0].get("status") == "MEDIA_GENERATION_STATUS_FAILED":
                                        log.error(f"Upscale failed for {uri}")
                                        upscaled_uris.append(uri)  # Fallback to original
                                        break
                else:
                    log.warning(f"Upscale request failed: {resp.error}, using original")
                    upscaled_uris.append(uri)
            except Exception as e:
                log.error(f"Upscale error: {e}, using original")
                upscaled_uris.append(uri)
        
        return upscaled_uris if upscaled_uris else output_uris
    
    async def _download_outputs(self, task: Task, output_uris: list) -> list:
        """Download output URIs to output_folder.
        
        Naming convention from AppSettings:
        {row_digits-padded index}{separator}{timestamp}_{quality}.mp4
        """
        from config.settings import get_settings
        settings = get_settings()
        
        output_folder = settings.output_folder
        if not output_folder:
            log.debug("No output_folder configured, skipping download")
            return []
        
        output_path = Path(output_folder)
        output_path.mkdir(parents=True, exist_ok=True)
        
        local_paths = []
        import aiohttp
        from datetime import datetime
        
        async with aiohttp.ClientSession() as session:
            for i, uri in enumerate(output_uris):
                try:
                    # Build filename
                    parts = []
                    idx_str = str(i + 1).zfill(settings.row_digits)
                    parts.append(idx_str)
                    
                    if settings.include_timestamp:
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        parts.append(ts)
                    
                    if settings.include_quality:
                        parts.append(task.download_quality)
                    
                    if settings.include_model:
                        # Shorten model key for filename
                        model_short = task.model.replace("veo_3_1_", "v31_").replace("_fast_", "_")
                        parts.append(model_short)
                    
                    sep = settings.separator
                    filename = sep.join(parts) + ".mp4"
                    filepath = output_path / filename
                    
                    # Avoid overwrite — add suffix if exists
                    counter = 1
                    while filepath.exists():
                        filepath = output_path / f"{sep.join(parts)}_{counter}.mp4"
                        counter += 1
                    
                    # Download
                    async with session.get(uri) as resp:
                        if resp.status == 200:
                            with open(filepath, "wb") as f:
                                async for chunk in resp.content.iter_chunked(8192):
                                    f.write(chunk)
                            local_paths.append(str(filepath))
                            log.info(f"Downloaded: {filepath.name}")
                        else:
                            log.error(f"Download failed: HTTP {resp.status} for {uri[:80]}")
                            
                except Exception as e:
                    log.error(f"Download error: {e}")
        
        return local_paths
    
    def _is_auth_error(self, error_msg: str) -> bool:
        """Check if error indicates authentication failure.
        
        Matches common auth error patterns from VEO API:
        - HTTP 401/403
        - Token expired/invalid
        - UNAUTHENTICATED gRPC status
        """
        if not error_msg:
            return False
        lower = error_msg.lower()
        auth_keywords = [
            "401", "403", "unauthorized", "unauthenticated",
            "token expired", "token invalid", "invalid credentials",
            "session expired", "authentication failed",
        ]
        return any(kw in lower for kw in auth_keywords)
    
    async def _try_auto_relogin(self, email: str) -> bool:
        """Attempt auto re-login via ProfilesController.
        
        Uses stored credentials (if available) to re-authenticate.
        Updates account tokens on success.
        
        Returns:
            True if re-login succeeded and tokens updated
        """
        if not self._profiles_controller:
            log.warning("No ProfilesController — cannot auto re-login")
            return False
        
        try:
            # ProfilesController.auto_relogin is sync, run in thread
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._profiles_controller.auto_relogin,
                email,
            )
            
            if result:
                log.info(f"Auto re-login OK for {email}, updating account tokens")
                # Refresh the account's tokens from updated profile
                account = self._account_manager.get_account(email)
                if account:
                    profile = self._profiles_controller.get_profile(email)
                    if profile and profile.get("access_token"):
                        account.update_access_token(
                            profile["access_token"],
                            expires_in=profile.get("expires_in", 3599),
                        )
                return True
            return False
            
        except Exception as e:
            log.error(f"Auto re-login error for {email}: {e}")
            return False
    
    def set_callbacks(
        self,
        on_started: Optional[Callable] = None,
        on_completed: Optional[Callable] = None,
        on_failed: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ):
        """Set UI callbacks."""
        self._on_task_started = on_started
        self._on_task_completed = on_completed
        self._on_task_failed = on_failed
        self._on_progress = on_progress
    
    def get_status(self) -> dict:
        """Get engine status summary."""
        return {
            "running": self._running,
            "workers": [w.get_status() for w in self._workers],
            "accounts": self._account_manager.get_status_summary(),
            "queue": self._dispatcher.get_status_summary(),
        }
