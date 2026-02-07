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
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.multi_account import MultiAccountManager
from core.account_manager import AccountManager
from core.dispatcher import Dispatcher, Task, TaskState
from core.worker import Worker, WorkerResult
from core.project_manager import ProjectManager
from core.api_client import VEOApiClient


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
        max_workers: int = 4,
        max_cpu_workers: Optional[int] = None,
    ):
        self._account_manager = account_manager
        self._dispatcher = dispatcher
        self._api_client = api_client
        self._project_manager = ProjectManager()
        
        self._max_workers = max_workers
        self._process_pool = ProcessPoolExecutor(
            max_workers=max_cpu_workers or os.cpu_count() or 4
        )
        
        self._workers: List[Worker] = []
        self._running = False
        self._stop_event = asyncio.Event()
        
        # Callbacks for UI updates
        self._on_task_started: Optional[Callable] = None
        self._on_task_completed: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def start(self):
        """Start the engine main loop.
        
        Creates a TaskGroup with max_workers concurrent worker coroutines.
        Each worker pulls tasks from the dispatcher and executes them.
        """
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        
        try:
            async with asyncio.TaskGroup() as tg:
                for i in range(self._max_workers):
                    worker = Worker(
                        worker_id=f"worker-{i}",
                        api_client=self._api_client,
                        on_progress=self._on_progress,
                    )
                    self._workers.append(worker)
                    tg.create_task(self._worker_loop(worker))
        except* Exception as eg:
            for exc in eg.exceptions:
                if not isinstance(exc, asyncio.CancelledError):
                    # Log error
                    pass
        finally:
            self._running = False
            self._workers.clear()
    
    async def stop(self):
        """Stop the engine gracefully."""
        self._stop_event.set()
        for worker in self._workers:
            worker.stop()
        self._process_pool.shutdown(wait=False)
    
    async def _worker_loop(self, worker: Worker):
        """Main loop for each worker coroutine.
        
        Continuously pulls tasks from dispatcher, acquires account slots,
        executes tasks, and releases slots.
        """
        while not self._stop_event.is_set():
            try:
                # Step 1: Get next ready task (non-blocking check)
                task = self._dispatcher.get_next_task(timeout=0.1)
                if not task:
                    await asyncio.sleep(0.5)  # Avoid busy loop
                    continue
                
                # Step 2: Acquire account slot
                account = await self._account_manager.acquire_slot()
                if not account:
                    # No account available, put task back
                    task.state = TaskState.READY
                    self._dispatcher.submit_task(task)
                    await asyncio.sleep(1.0)
                    continue
                
                # Step 3: Ensure project exists (for T2I etc.)
                if not account.project_id:
                    project_id = await self._project_manager.get_or_create_project(
                        email=account.email,
                        access_token=account.get_access_token(),
                        api_client=self._api_client,
                    )
                    if project_id:
                        account.set_project_id(project_id)
                
                # Notify UI
                task.assigned_account = account.email
                task.project_id = account.project_id
                if self._on_task_started:
                    self._on_task_started(task)
                
                # Step 4: Execute task
                result = await worker.execute(task, account)
                
                # Step 5: Release slot
                await self._account_manager.release_slot(account.email)
                
                # Step 6: Update dispatcher
                if result.success:
                    # For async operations, start polling
                    if result.operation_name:
                        task.operation_name = result.operation_name
                        task.state = TaskState.WAITING_POLL
                        # Poll for results
                        await self._poll_operation(task, account)
                    else:
                        # Sync operation (T2I) - already complete
                        self._dispatcher.complete_task(
                            task.id,
                            output_uris=result.output_uris,
                        )
                        if self._on_task_completed:
                            self._on_task_completed(task)
                else:
                    self._dispatcher.fail_task(task.id, result.error or "Unknown error")
                    if self._on_task_failed:
                        self._on_task_failed(task, result.error)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but keep worker alive
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
                response = await self._api_client.check_status(
                    access_token=account.get_access_token(),
                    operation_name=task.operation_name,
                )
                
                if not response.success:
                    continue
                
                status = response.data.get("status", "")
                
                if "SUCCESSFUL" in status:
                    # Extract output URIs
                    output_uris = self._extract_output_uris(response.data)
                    frame_uri = self._extract_last_frame_uri(response.data)
                    
                    self._dispatcher.complete_task(
                        task.id,
                        output_uris=output_uris,
                        continuation_frame_uri=frame_uri,
                    )
                    if self._on_task_completed:
                        self._on_task_completed(task)
                    return
                
                elif "FAILED" in status:
                    error = response.data.get("error", "Generation failed")
                    self._dispatcher.fail_task(task.id, str(error))
                    if self._on_task_failed:
                        self._on_task_failed(task, str(error))
                    return
                
                else:
                    # Still in progress
                    progress = min(90, int(elapsed / max_poll_time * 90))
                    self._dispatcher.update_progress(task.id, progress)
                    
            except Exception:
                continue
        
        # Timeout
        self._dispatcher.fail_task(task.id, f"Polling timeout ({max_poll_time}s)")
    
    def _extract_output_uris(self, data: dict) -> list:
        """Extract output URIs from poll response."""
        uris = []
        for video in data.get("generatedVideos", []):
            if "videoUri" in video:
                uris.append(video["videoUri"])
        for image in data.get("generatedImages", []):
            if "imageUri" in image:
                uris.append(image["imageUri"])
        return uris
    
    def _extract_last_frame_uri(self, data: dict) -> Optional[str]:
        """Extract last frame URI for continuation."""
        videos = data.get("generatedVideos", [])
        if videos:
            return videos[0].get("lastFrameUri")
        return None
    
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
