"""
VEO Pro Max - Orchestration Engine

Reference: ARCHITECTURE_OVERVIEW.md (lines 94-120)
Role: Connects ĐẠI CHỦ ↔ THẦU ↔ THỢ into a working pipeline

Architecture: Hybrid Asyncio + ProcessPoolExecutor
- asyncio Event Loop (Main): ĐẠI CHỦ, THẦU, TaskGroup
- asyncio.TaskGroup: manages Worker coroutines
- ProcessPoolExecutor: CPU-bound tasks (ffmpeg, image processing)
"""

from typing import Optional, List, Dict, Callable
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
        self._task_available = asyncio.Event()  # Bug 14: signal workers when new task arrives
        self._relogin_locks: Dict[str, asyncio.Lock] = {}  # Per-account re-login dedup
        self._account_rate_locks: Dict[str, asyncio.Lock] = {}  # Bug 13: per-account rate limiter
        
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
        
        Bug 7 fix: Re-queue tasks in RUNNING/WAITING_POLL state so they
        can be picked up when engine restarts (Resume).
        Sets the stop event, causing all worker loops to exit.
        The start() method's finally block handles browser cleanup.
        """
        if not self._running:
            return
        
        log.info("Engine stop requested — signaling workers to exit")
        self._stop_event.set()
        self._task_available.set()  # Wake up any waiting workers
        
        # Bug 7: Re-queue tasks stuck in RUNNING or WAITING_POLL
        requeued = 0
        for task in self._dispatcher.get_all_tasks():
            if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                task.state = TaskState.READY
                task.assigned_account = None
                self._dispatcher.requeue_task(task)
                requeued += 1
        if requeued:
            log.info(f"Re-queued {requeued} tasks that were RUNNING/WAITING_POLL")
        
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
        self._task_available.clear()
        
        # Bug 14: Wire dispatcher's on_task_ready to wake up waiting workers
        self._dispatcher._on_task_ready = lambda task: self._task_available.set()
        
        # Inject profiles_controller into accounts for debug browser sharing
        if self._profiles_controller:
            for acc in self._account_manager._accounts:
                acc.set_profiles_controller(self._profiles_controller)
        
        # Start persistent browsers for reCAPTCHA refresh
        # If debug browsers are already open, ensure_browser() will ATTACH to them
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
            # Disconnect Playwright from persistent Chrome (Chrome keeps running)
            try:
                await self._account_manager.shutdown_browsers()
            except Exception as e:
                log.error(f"Browser disconnect error: {e}")
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
                        # Bug 14: Wait for task notification instead of busy-polling
                        self._task_available.clear()
                        try:
                            await asyncio.wait_for(
                                self._task_available.wait(),
                                timeout=2.0,  # Check stop_event every 2s
                            )
                        except asyncio.TimeoutError:
                            pass
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
                    
                    # Bug 11 fix: Removed redundant reCAPTCHA refresh here.
                    # Worker.execute() already handles reCAPTCHA refresh (step B5).
                    # Having it in both places caused double-refresh and wasted 200-500ms.
                    
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
                        else:
                            log.warning(f"⚠️ No projectId for {account.email} — generation requests may fail (TRPC createProject returned None)")
                    
                    # Step 5.5: Auto-detect paygate tier (once per account)
                    if account.paygate_tier == "PAYGATE_TIER_TWO":
                        await account.fetch_paygate_tier(self._api_client)
                    
                    # Notify UI
                    task.assigned_account = account.email
                    task.project_id = account.project_id
                    if self._on_task_started:
                        self._on_task_started(task)
                    
                    # Bug 13: Per-account rate limiter — serialize requests per account
                    # Ensures 4 workers on same account don't submit simultaneously
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Lock()
                    
                    # Step 7: Execute with RETRY + TIMEOUT
                    # Rate lock held ONLY during anti-detect delay + API call,
                    # released between retries so other workers can proceed.
                    max_retries = account.retry_count
                    timeout = account.request_timeout
                    result = None
                    
                    for attempt in range(max_retries + 1):
                        # Lock: covers anti-detect delay + single API call only
                        async with self._account_rate_locks[account.email]:
                            # Step 6: Anti-Detect Spam — random delay (SERIALIZED per account)
                            if getattr(self, '_anti_detect_enabled', True):
                                delay_min = getattr(self, '_anti_detect_delay_min', 1.0)
                                delay_max = getattr(self, '_anti_detect_delay_max', 5.0)
                                delay = random.uniform(delay_min, delay_max)
                                log.debug(f"Worker {worker.worker_id}: anti-detect delay {delay:.6f}s before submit")
                                await asyncio.sleep(delay)
                        
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
                            
                            # reCAPTCHA tokens are single-use: consumed by Google
                            # on EVERY request (success OR failure).
                            # Invalidate immediately so next call gets a fresh token.
                            account.invalidate_recaptcha()
                        # Rate lock released here — other workers can now submit
                        
                        if result.success:
                            break  # Success — exit retry loop
                        
                        # Auth errors → special handling, no retry
                        if self._is_auth_error(result.error or ""):
                            break
                        
                        # Non-auth error — retry with backoff (OUTSIDE rate lock)
                        task.retry_attempts = attempt + 1
                        if attempt < max_retries:
                            backoff = min(2 ** (attempt + 1), 30)
                            
                            # Auto browser restart on persistent reCAPTCHA failures
                            # After 2 consecutive 403s, full restart: kill Chrome → relaunch → fresh PID
                            error_lower = (result.error or "").lower()
                            if attempt == 2 and "recaptcha" in error_lower:
                                log.warning(
                                    f"🔄 Worker {worker.worker_id}: reCAPTCHA failed {attempt + 1}x consecutively. "
                                    f"Full browser restart (kill + relaunch)..."
                                )
                                try:
                                    restart_ok = await account.restart_browser()
                                    if restart_ok:
                                        log.info(
                                            f"✅ Worker {worker.worker_id}: Browser fully restarted for {account.email}. "
                                            f"Fresh PID, tokens, reCAPTCHA. Retrying..."
                                        )
                                    else:
                                        log.error(f"❌ Worker {worker.worker_id}: Browser restart returned False")
                                    backoff = 5  # Give extra time after restart
                                except Exception as restart_err:
                                    log.error(f"❌ Browser restart failed: {restart_err}")
                            
                            log.warning(
                                f"Worker {worker.worker_id}: task {task.id} failed "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {result.error}. "
                                f"Retrying in {backoff}s..."
                            )
                            await asyncio.sleep(backoff)
                    
                    # Bug 18: Release slot IMMEDIATELY after submit
                    # API is async — server processes in background, no need to hold slot during polling
                    account.release_slot()
                    
                    # Step 8: Process final result
                    log.info(f"[Engine] Task {task.id}: result.success={result.success if result else 'NO_RESULT'}, "
                             f"operation_name={result.operation_name if result else 'N/A'}")
                    if result and result.success:
                        # For async operations, start polling (slot already released)
                        if result.operation_name:
                            task.operation_name = result.operation_name
                            task.scene_id = result.scene_id or ""
                            task.state = TaskState.WAITING_POLL
                            log.info(f"[Engine] Task {task.id}: → POLLING {result.operation_name} (scene={task.scene_id[:8]}...)")
                            await self._poll_operation(task, account)
                        else:
                            # Sync operation (T2I) - already complete
                            log.info(f"[Engine] Task {task.id}: → SYNC COMPLETE (no operation_name)")
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
                            
                            relogin_ok = await self._try_auto_relogin(account.email, account)
                            
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
                
                except Exception as inner_e:
                    # Release slot if still held due to error before the release point
                    try:
                        account.release_slot()
                    except Exception:
                        pass
                    raise inner_e
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Worker {worker.worker_id} unexpected error: {e}")
                await asyncio.sleep(1.0)
    
    async def _poll_operation(self, task: Task, account: AccountManager):
        """Poll for async operation completion.
        
        Progress stages (status-based, not time-based):
          5%  - Token validation (worker)
         10%  - reCAPTCHA refresh (worker)
         15%  - Submitting to API (worker)
         20%  - API accepted request (worker)
         25%  - Polling started (PENDING)
         30%  - Server queued (PENDING, 2nd+ poll)
         40%  - Server processing (ACTIVE, 1st seen)
         45-80% - Server processing (ACTIVE, ramping with polls)
         85%  - All operations SUCCESSFUL
         90%  - Downloading outputs
         95%  - Download complete / upscaling
        100%  - Fully done
        """
        from config.constants import AppConstants
        
        poll_interval = AppConstants.POLL_INTERVAL
        max_poll_time = AppConstants.MAX_POLL_TIME
        elapsed = 0
        
        # Track status transitions for progress
        active_poll_count = 0   # How many polls returned ACTIVE
        pending_poll_count = 0  # How many polls returned PENDING
        last_status = "MEDIA_GENERATION_STATUS_PENDING"
        
        # Initial: polling started
        self._dispatcher.update_progress(task.id, 25, "⏳ Waiting in queue")
        
        while elapsed < max_poll_time and not self._stop_event.is_set():
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            try:
                current_status = getattr(task, '_poll_status', 'MEDIA_GENERATION_STATUS_PENDING')
                
                response = await self._api_client.check_status(
                    access_token=account.get_access_token(),
                    recaptcha_token="",  # Not needed for polling (HAR verified)
                    operations=[{
                        "operation": {"name": task.operation_name},
                        "sceneId": getattr(task, 'scene_id', ''),
                        "status": current_status,
                    }],
                    account_headers=account.get_api_headers(),
                )
                
                if not response.success:
                    continue
                
                ops = response.data.get("operations", [])
                if not ops:
                    continue
                
                # Check statuses
                all_successful = all(
                    op.get("status") == "MEDIA_GENERATION_STATUS_SUCCESSFUL"
                    for op in ops
                )
                any_failed = any(
                    op.get("status") == "MEDIA_GENERATION_STATUS_FAILED"
                    for op in ops
                )
                
                # Get current server status
                server_status = ops[0].get("status", current_status) if ops else current_status
                
                # Update tracked status for next poll request
                if ops:
                    task._poll_status = server_status
                
                if all_successful:
                    # === Stage: All SUCCESSFUL (85%) ===
                    self._dispatcher.update_progress(task.id, 85, "✅ Generation complete")
                    
                    output_details = self._extract_output_details(response.data)
                    output_uris = [d["fifeUrl"] for d in output_details]
                    media_ids = [d["mediaId"] for d in output_details]
                    
                    # === Stage: Download 720p originals (86%) ===
                    self._dispatcher.update_progress(task.id, 86, "⬇️ Downloading 720p")
                    local_720p = await self._download_outputs(
                        task, output_uris, quality_subfolder="720p"
                    )
                    
                    # === Stage: Auto-upscale if needed (88-92%) ===
                    upscale_paths = []
                    if task.download_quality != "720p" and media_ids:
                        self._dispatcher.update_progress(task.id, 88, "⬆️ Upscaling")
                        upscaled_uris = await self._auto_upscale(
                            task, account, output_uris, media_ids
                        )
                        if upscaled_uris:
                            self._dispatcher.update_progress(
                                task.id, 92, f"⬇️ Downloading {task.download_quality}"
                            )
                            upscale_paths = await self._download_outputs(
                                task, upscaled_uris,
                                quality_subfolder=task.download_quality,
                            )
                    
                    # Prefer upscaled paths, fallback to 720p
                    final_paths = upscale_paths if upscale_paths else local_720p
                    if final_paths:
                        task.output_uris = final_paths
                    
                    # === Stage: Post-processing (95%) ===
                    self._dispatcher.update_progress(task.id, 95, "🎬 Post-processing")
                    continuation_frame_uri = None
                    if (
                        self._continuation_enabled
                        and self._dispatcher.has_children(task.id)
                        and output_uris
                    ):
                        continuation_frame_uri = await self._extract_continuation_frame(
                            task, account, output_uris[0]
                        )
                    
                    # === Stage: Complete (100%) ===
                    self._dispatcher.update_progress(task.id, 100, "✅ Done")
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
                    # === Status-based progress mapping ===
                    if server_status == "MEDIA_GENERATION_STATUS_PENDING":
                        pending_poll_count += 1
                        progress = min(35, 25 + pending_poll_count * 2)
                        status_label = "⏳ Queued on server"
                    elif server_status == "MEDIA_GENERATION_STATUS_ACTIVE":
                        active_poll_count += 1
                        progress = min(80, 40 + int(active_poll_count * 5))
                        status_label = "🔥 Processing"
                    else:
                        progress = min(80, 25 + int(elapsed / max_poll_time * 55))
                        status_label = "⏳ Working"
                    
                    self._dispatcher.update_progress(task.id, progress, status_label)
                    
                    # Log status transition
                    if server_status != last_status:
                        log.info(f"Task {task.id}: {last_status} → {server_status} ({progress}%)")
                        last_status = server_status
                    
            except Exception:
                continue
        
        # Timeout
        self._dispatcher.fail_task(task.id, f"Polling timeout ({max_poll_time}s)")
    
    def _extract_output_details(self, data: dict) -> list:
        """Extract output details from poll response.
        
        Returns list of {fifeUrl, mediaId} dicts.
        - fifeUrl: download URL for the video/image
        - mediaId: metadata.name (protobuf Base64), needed for upscale API
        
        HAR-verified paths:
          operations[].operation.metadata.name           → mediaId for upscale
          operations[].operation.metadata.video.fifeUrl  → download URL
        """
        results = []
        for op in data.get("operations", []):
            metadata = op.get("operation", {}).get("metadata", {})
            media_id = metadata.get("name", "")  # protobuf Base64
            
            # Video result
            video = metadata.get("video", {})
            if video:
                uri = video.get("fifeUrl") or video.get("servingBaseUri", "")
                if uri:
                    results.append({"fifeUrl": uri, "mediaId": media_id})
                    continue
            # Image result
            image = metadata.get("image", {}).get("generatedImage", {})
            if image:
                uri = image.get("fifeUrl", "")
                if uri:
                    results.append({"fifeUrl": uri, "mediaId": media_id})
        return results
    
    def _extract_output_uris(self, data: dict) -> list:
        """Backward-compatible wrapper: extract fifeUrls only."""
        return [d["fifeUrl"] for d in self._extract_output_details(data)]
    
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
        self, task: Task, account: AccountManager,
        output_uris: list, media_ids: list,
    ) -> list:
        """Auto-upscale videos if download_quality > 720p.
        
        HAR-verified flow:
        1. Submit upscale with videoInput.mediaId = metadata.name (protobuf Base64)
        2. Poll with status tracking (PENDING → ACTIVE → SUCCESSFUL)
        3. Progress reporting 88% → 90%
        4. Timeout fallback: skip (720p already saved separately)
        
        Args:
            output_uris: fifeUrls (720p download URLs) — for fallback logging only
            media_ids: metadata.name values (protobuf Base64) — for upscale API
        
        Returns:
            List of upscaled fifeUrls, empty list if all fail.
        """
        quality_map = {
            "1080p": "VIDEO_RESOLUTION_1080P",
            "4K": "VIDEO_RESOLUTION_4K",
        }
        resolution = quality_map.get(task.download_quality)
        if not resolution:
            return []  # 720p or unknown → no upscale needed
        
        from core.api_client import generate_random_seed
        total = len(media_ids)
        upscaled_uris = []
        
        for idx, media_id in enumerate(media_ids):
            video_label = f"{idx + 1}/{total}"
            if not media_id:
                log.warning(f"Upscale {video_label}: no mediaId, skipping")
                continue
            
            try:
                # Get fresh reCAPTCHA token
                recaptcha_token = account.get_recaptcha_token() or ""
                if not recaptcha_token:
                    token = await account.refresh_recaptcha()
                    recaptcha_token = token or ""
                
                # Submit upscale request with correct mediaId
                resp = await self._api_client.upscale_video(
                    access_token=account.get_access_token() or "",
                    recaptcha_token=recaptcha_token,
                    video_media_id=media_id,  # HAR-verified: metadata.name
                    target_resolution=resolution,
                    aspect_ratio=task.aspect_ratio,
                    seed=generate_random_seed(),
                    account_headers=account.get_api_headers(),
                )
                
                if not resp.success:
                    log.warning(f"Upscale {video_label} request failed: {resp.error}")
                    continue
                
                # Extract operation name for polling
                ops = resp.data.get("operations", [])
                if not ops:
                    log.warning(f"Upscale {video_label}: no operation returned")
                    continue
                
                op_name = ops[0].get("operation", {}).get("name", "")
                scene_id = ops[0].get("sceneId", "")
                if not op_name:
                    log.warning(f"Upscale {video_label}: no operation name")
                    continue
                
                log.info(f"Upscale {video_label} started: op={op_name}")
                
                # Poll upscale with status tracking + progress
                poll_status = "MEDIA_GENERATION_STATUS_PENDING"
                max_polls = 60  # 60 × 5s = max 5 min
                
                for poll_num in range(max_polls):
                    await asyncio.sleep(5)
                    
                    # Progress: map to 88-90% range
                    progress = min(90, 88 + int(poll_num * 0.5))
                    self._dispatcher.update_progress(
                        task.id, progress,
                        f"⬆️ Upscaling {video_label}"
                    )
                    
                    poll_resp = await self._api_client.check_status(
                        access_token=account.get_access_token() or "",
                        recaptcha_token="",
                        operations=[{
                            "operation": {"name": op_name},
                            "sceneId": scene_id,
                            "status": poll_status,  # Track actual status
                        }],
                        account_headers=account.get_api_headers(),
                    )
                    
                    if not poll_resp.success:
                        continue
                    
                    poll_ops = poll_resp.data.get("operations", [])
                    if not poll_ops:
                        continue
                    
                    server_status = poll_ops[0].get("status", "")
                    
                    # Track status transition
                    if server_status != poll_status:
                        log.info(f"Upscale {video_label}: {poll_status} → {server_status}")
                        poll_status = server_status
                    
                    if server_status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                        upscaled = self._extract_output_uris(poll_resp.data)
                        if upscaled:
                            upscaled_uris.extend(upscaled)
                            log.info(f"Upscale {video_label} done ✅")
                        break
                    
                    elif server_status == "MEDIA_GENERATION_STATUS_FAILED":
                        error = poll_ops[0].get("error", {}).get("message", "unknown")
                        log.error(f"Upscale {video_label} failed: {error}")
                        break
                else:
                    # Timeout — 720p already saved separately, just log
                    log.warning(f"Upscale {video_label} timeout (5 min), 720p already saved")
            
            except Exception as e:
                log.error(f"Upscale {video_label} error: {e}")
        
        return upscaled_uris
    
    async def _download_outputs(
        self, task: Task, output_uris: list,
        quality_subfolder: str = "",
    ) -> list:
        """Download output URIs to output_folder/project_name/quality_subfolder/.
        
        Folder structure (Option A):
          output_folder/project_name/720p/001a_..._720p.mp4
          output_folder/project_name/4K/001a_..._4K.mp4
        
        Naming convention:
        - Single output:   {NNN}_{timestamp}_{quality}.mp4
        - Multi output:    {NNN}{variant}_{timestamp}_{quality}.mp4
        """
        from config.settings import get_settings
        settings = get_settings()
        
        # Prefer task-level output_folder (from sidebar), fallback to global settings
        output_folder = getattr(task, 'output_folder', '') or settings.output_folder
        if not output_folder:
            log.debug("No output_folder configured, skipping download")
            return []
        
        # Create project subfolder + quality subfolder
        project_name = getattr(task, 'project_name', '') or "Untitled"
        if quality_subfolder:
            output_path = Path(output_folder) / project_name / quality_subfolder
        else:
            output_path = Path(output_folder) / project_name
        output_path.mkdir(parents=True, exist_ok=True)
        
        local_paths = []
        import aiohttp
        from datetime import datetime
        
        # Global prompt index (1-based, 3-digit padded)
        prompt_num = getattr(task, 'prompt_index', 0) + 1
        idx_str = str(prompt_num).zfill(3)
        
        # Variant suffixes for multi-output
        variant_letters = "abcdefghijklmnopqrstuvwxyz"
        is_multi = len(output_uris) > 1
        
        async with aiohttp.ClientSession() as session:
            for i, uri in enumerate(output_uris):
                try:
                    # Build filename parts
                    parts = []
                    
                    # Index + variant suffix
                    if is_multi and i < len(variant_letters):
                        parts.append(f"{idx_str}{variant_letters[i]}")
                    else:
                        parts.append(idx_str)
                    
                    if settings.include_timestamp:
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        parts.append(ts)
                    
                    if settings.include_quality:
                        # Use actual quality (subfolder name), not target quality
                        file_quality = quality_subfolder or task.download_quality
                        parts.append(file_quality)
                    
                    if settings.include_model:
                        model_short = task.model.replace("veo_3_1_", "v31_").replace("_fast_", "_")
                        parts.append(model_short)
                    
                    sep = settings.separator
                    filename = sep.join(parts) + ".mp4"
                    filepath = output_path / filename
                    
                    # Avoid overwrite — add numeric suffix if exists
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
                            log.info(f"Downloaded: {filepath.name} → {output_path}")
                        else:
                            log.error(f"Download failed: HTTP {resp.status} for {uri[:80]}")
                        
                except Exception as e:
                    log.error(f"Download error: {e}")
        
        return local_paths
    
    def _is_auth_error(self, error_msg: str) -> bool:
        """Check if error indicates authentication failure.
        
        Only matches REAL auth errors that can be fixed by re-login:
        - HTTP 401 / UNAUTHENTICATED
        - Token expired/invalid
        
        Does NOT match:
        - HTTP 403 reCAPTCHA failures (re-login won't fix these)
        - Generic 403 permission errors
        """
        if not error_msg:
            return False
        lower = error_msg.lower()
        
        # Exclude reCAPTCHA errors — re-login won't help
        if "recaptcha" in lower:
            return False
        
        auth_keywords = [
            "401", "unauthorized", "unauthenticated",
            "token expired", "token invalid", "invalid credentials",
            "session expired", "authentication failed",
            "credentials_missing",
        ]
        return any(kw in lower for kw in auth_keywords)
    
    async def _try_auto_relogin(self, email: str, account: 'AccountManager') -> bool:
        """Attempt auto re-login via ProfilesController.
        
        Strategy:
        1. If debug browser is open → reload page to refresh session, extract
           fresh access_token from __NEXT_DATA__ (NO new browser needed)
        2. If no debug browser → close headless, launch new browser for re-login
        
        Returns:
            True if re-login succeeded and tokens updated
        """
        if not self._profiles_controller:
            log.warning("No ProfilesController — cannot auto re-login")
            return False
        
        # Per-account lock — only ONE worker attempts re-login at a time
        if email not in self._relogin_locks:
            self._relogin_locks[email] = asyncio.Lock()
        
        lock = self._relogin_locks[email]
        
        if lock.locked():
            log.info(f"Re-login already in progress for {email}, waiting...")
            async with lock:
                if account._browser_session and account._browser_session.is_ready:
                    return True
                return False
        
        async with lock:
            try:
                # ── Strategy 1: Debug browser is open → refresh token from existing page ──
                debug_page = self._profiles_controller.get_debug_browser_page(email)
                if debug_page:
                    log.info(f"[{email}] Debug browser open — refreshing token via page reload...")
                    
                    try:
                        # Send 'refresh_token' command via queue to reload page and re-extract token
                        entry = self._profiles_controller._debug_browsers.get(email) if hasattr(self._profiles_controller, '_debug_browsers') else None
                        if entry and entry.get("cmd_queue"):
                            entry["cmd_queue"].put("refresh_token")
                            
                            # Wait for token to be refreshed (up to 15 seconds)
                            loop = asyncio.get_event_loop()
                            for _ in range(30):
                                await asyncio.sleep(0.5)
                                # Check if fresh token is available
                                profile = self._profiles_controller.get_profile(email)
                                token = getattr(profile, "access_token", None) if profile else None
                                if token and len(token) > 100:
                                    account.update_access_token(token, expires_in=3599)
                                    log.info(f"[{email}] ✅ Access token refreshed from debug browser ({len(token)} chars)")
                                    
                                    # Re-attach to debug browser
                                    await account.ensure_browser(headless=True)
                                    return True
                        
                        # Fallback: try direct JS extraction from the page
                        log.info(f"[{email}] Trying direct JS token extraction from debug page...")
                        # Use run_in_executor since page operations are sync
                        def _extract_from_page():
                            try:
                                page = debug_page
                                page.reload(wait_until="networkidle", timeout=15000)
                                page.wait_for_timeout(2000)
                                
                                # Extract access_token from __NEXT_DATA__
                                result = page.evaluate("""() => {
                                    try {
                                        const nd = document.getElementById('__NEXT_DATA__');
                                        if (nd) {
                                            const data = JSON.parse(nd.textContent);
                                            const token = data?.props?.pageProps?.userInfo?.accessToken
                                                       || data?.props?.pageProps?.session?.accessToken;
                                            return token || null;
                                        }
                                    } catch {}
                                    return null;
                                }""")
                                return result
                            except Exception as e:
                                log.warning(f"[{email}] JS token extraction failed: {e}")
                                return None
                        
                        token = await loop.run_in_executor(None, _extract_from_page)
                        if token and len(token) > 100:
                            account.update_access_token(token, expires_in=3599)
                            log.info(f"[{email}] ✅ Access token extracted via JS ({len(token)} chars)")
                            await account.ensure_browser(headless=True)
                            return True
                        
                        log.warning(f"[{email}] Could not refresh token from debug browser")
                        return False
                        
                    except Exception as e:
                        log.error(f"[{email}] Token refresh from debug browser failed: {e}")
                        return False
                
                # ── Strategy 2: No debug browser → full re-login with credentials ──
                log.info(f"Closing Engine browser for {email} before re-login...")
                await account.close_browser()
                
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self._profiles_controller.auto_relogin,
                    email,
                )
                
                if result:
                    log.info(f"Auto re-login OK for {email}, updating account tokens")
                    profile = self._profiles_controller.get_profile(email)
                    access_token = getattr(profile, "access_token", None) if profile else None
                    if access_token:
                        account.update_access_token(
                            access_token,
                            expires_in=getattr(profile, "expires_in", 3599),
                        )
                    
                    log.info(f"Re-opening headless browser for {email}...")
                    try:
                        await account.ensure_browser(headless=True)
                    except Exception as e:
                        log.warning(f"Browser re-open failed for {email}: {e}")
                    
                    return True
                
                # Re-login failed — still re-open browser for reCAPTCHA attempts
                log.warning(f"Re-login failed for {email}, re-opening browser anyway")
                try:
                    await account.ensure_browser(headless=True)
                except Exception:
                    pass
                return False
                
            except Exception as e:
                log.error(f"Auto re-login error for {email}: {e}")
                try:
                    await account.ensure_browser(headless=True)
                except Exception:
                    pass
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
