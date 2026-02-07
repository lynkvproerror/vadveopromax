"""
VEO Pro Max - App Controller

Central controller connecting UI with core engine.
"""

from typing import Optional, Dict, Any, Callable, List
from datetime import datetime
from pathlib import Path
import asyncio
import threading
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Core imports
from core.session import AccountSession
from core.multi_account import MultiAccountManager
from core.account_manager import AccountManager
from core.dispatcher import Dispatcher, Task, TaskGroup, TaskState
from core.worker import Worker, WorkerResult
from core.api_client import VEOApiClient
from core.auth_manager import AuthManager
from core.error_handler import ErrorHandler
from core.session_monitor import SessionMonitor, SessionEvent
from core.refresh_manager import CookieRefreshManager
from core.batch_parser import BatchParser, ParsedPrompt
from core.import_validator import ImportValidator
from core.download_manager import DownloadManager

# Services
from services.license_client import LicenseClient
from services.permissions import PermissionsSystem, Role, Feature

# Config
from config.settings import AppSettings
from config.constants import WorkflowType


class AppState:
    """Application state container."""
    
    def __init__(self):
        self.is_running = False
        self.is_processing = False
        self.current_workflow: Optional[str] = None
        self.active_account: Optional[str] = None
        self.queue_count = 0
        self.completed_count = 0
        self.error_count = 0


class AppController:
    """Central controller for VEO Pro Max.
    
    Connects UI components with core engine modules.
    Manages application lifecycle and state.
    """
    
    def __init__(self, settings: Optional[AppSettings] = None):
        # Settings
        self.settings = settings or AppSettings()
        
        # State
        self.state = AppState()
        
        # Core components
        self._multi_account = MultiAccountManager()
        self._dispatcher = Dispatcher()
        self._api_client = VEOApiClient()
        self._auth_manager = AuthManager()
        self._error_handler = ErrorHandler()
        self._session_monitor = SessionMonitor()
        self._refresh_manager = CookieRefreshManager()
        self._download_manager = DownloadManager()
        self._batch_parser = BatchParser()
        self._import_validator = ImportValidator()
        
        # Services
        self._license_client = LicenseClient()
        self._permissions = PermissionsSystem()
        
        # Workers (created on demand)
        self._workers: List[Worker] = []
        self._worker_threads: List[threading.Thread] = []
        
        # Event callbacks (set by UI)
        self._on_task_completed: Optional[Callable[[Task], None]] = None
        self._on_task_failed: Optional[Callable[[Task, str], None]] = None
        self._on_progress: Optional[Callable[[str, int], None]] = None
        self._on_queue_updated: Optional[Callable[[Dict], None]] = None
        self._on_account_changed: Optional[Callable[[str], None]] = None
        self._on_status_changed: Optional[Callable[[str], None]] = None
        
        # Async event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        
        # Setup callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Setup internal callbacks between components."""
        # Dispatcher callbacks
        self._dispatcher.set_callbacks(
            on_completed=self._handle_task_completed,
            on_failed=self._handle_task_failed,
        )
        
        # Session monitor
        self._session_monitor.set_expired_callback(self._handle_session_expired)
    
    # === LIFECYCLE ===
    
    def start(self):
        """Start the application controller."""
        if self.state.is_running:
            return
        
        self.state.is_running = True
        
        # Start async loop in background
        self._start_async_loop()
        
        # Start session monitoring
        self._session_monitor.start_monitoring()
        
        # Start refresh manager
        self._refresh_manager.start_auto_check()
        
        # Check license
        self._update_permissions()
        
        self._notify_status("Controller started")
    
    def stop(self):
        """Stop the application controller."""
        self.state.is_running = False
        self.state.is_processing = False
        
        # Stop monitoring
        self._session_monitor.stop_monitoring()
        self._refresh_manager.stop_auto_check()
        
        # Stop workers
        for worker in self._workers:
            worker.stop()
        
        # Stop async loop
        self._stop_async_loop()
        
        self._notify_status("Controller stopped")
    
    def _start_async_loop(self):
        """Start background async event loop."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
    
    def _stop_async_loop(self):
        """Stop background async event loop."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
    
    def _run_async(self, coro):
        """Run async coroutine in background loop."""
        if self._loop:
            return asyncio.run_coroutine_threadsafe(coro, self._loop)
        return None
    
    # === ACCOUNT MANAGEMENT ===
    
    def add_account(self, session: AccountSession) -> bool:
        """Add an account to the manager."""
        if not self._permissions.check_limit("max_cookies", len(self._multi_account._accounts)):
            return False
        
        manager = AccountManager(session)
        self._multi_account.add_account(manager)
        self._session_monitor.register_session(session)
        self._refresh_manager.register_session(session)
        
        self._notify_status(f"Account added: {session.email}")
        return True
    
    def remove_account(self, email: str):
        """Remove an account."""
        self._multi_account.remove_account(email)
        self._session_monitor.unregister_session(email)
        self._refresh_manager.unregister_session(email)
    
    def get_accounts(self) -> List[Dict]:
        """Get list of accounts with status."""
        status = self._multi_account.get_status_summary()
        return status.get('accounts', [])
    
    # === TASK MANAGEMENT ===
    
    def submit_prompts(
        self,
        prompts: List[str],
        workflow: WorkflowType,
        images: Optional[List[str]] = None,
        settings: Optional[Dict] = None,
        continuation_map: Optional[Dict[int, int]] = None,  # index -> parent_index
    ) -> str:
        """Submit prompts for processing.
        
        Returns group_id.
        """
        if not self._permissions.has_feature(Feature.BATCH_PROCESSING):
            prompts = prompts[:1]  # Limit to 1 for non-batch
        
        # Create task group
        group_id = f"group_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        tasks = []
        task_id_map = {}  # index -> task_id for continuation linking
        
        for i, prompt in enumerate(prompts):
            task_id = f"{group_id}_task_{i}"
            task_id_map[i] = task_id
            
            # Check if this prompt is continuation of another
            parent_task_id = None
            if continuation_map and i in continuation_map:
                parent_index = continuation_map[i]
                if parent_index in task_id_map:
                    parent_task_id = task_id_map[parent_index]
            
            task = Task(
                id=task_id,
                workflow_type=workflow,
                prompt=prompt,
                aspect_ratio=settings.get("aspect_ratio", "LANDSCAPE") if settings else "LANDSCAPE",
                model=settings.get("model", "veo-fast-3.1") if settings else "veo-fast-3.1",
                output_count=settings.get("output_count", 4) if settings else 4,
                duration_seconds=settings.get("duration", 8) if settings else 8,
                image_uris=images or [],
                parent_task_id=parent_task_id,
            )
            tasks.append(task)
        
        group = TaskGroup(id=group_id, name=f"Batch {len(tasks)}", tasks=tasks)
        self._dispatcher.submit_task_group(group)
        
        self.state.queue_count += len(tasks)
        self._notify_queue_updated()
        
        return group_id
    
    # === BATCH METHODS (called by UI tabs) ===
    
    def add_t2v_batch(self, prompts: List, settings: Dict) -> str:
        """Add Text-to-Video batch to queue.
        
        Args:
            prompts: List of PromptRow objects from UI
            settings: Sidebar settings dict
        """
        # Extract continuation chain
        continuation_map = {}
        for i, p in enumerate(prompts):
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                # continuation_from is 1-indexed, convert to 0-indexed
                continuation_map[i] = p.continuation_from - 1
        
        return self.submit_prompts(
            prompts=[p.text if hasattr(p, 'text') else str(p) for p in prompts],
            workflow=WorkflowType.T2V,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None
        )
    
    def add_i2v_batch(self, prompts: List, settings: Dict) -> str:
        """Add Image-to-Video batch to queue.
        
        Args:
            prompts: List of PromptRow objects with image_tag
            settings: Sidebar settings dict
        """
        images = []
        prompt_texts = []
        continuation_map = {}
        
        for i, p in enumerate(prompts):
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tag') and p.image_tag:
                images.append(p.image_tag)
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                continuation_map[i] = p.continuation_from - 1
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.I2V,
            images=images if images else None,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None
        )
    
    def add_r2v_batch(self, prompts: List, settings: Dict) -> str:
        """Add Ingredients/References-to-Video batch to queue.
        
        Args:
            prompts: List of PromptRow objects with image_tags (up to 3)
            settings: Sidebar settings dict
        """
        all_images = []
        prompt_texts = []
        for p in prompts:
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tags') and p.image_tags:
                all_images.extend(p.image_tags[:3])  # Max 3 images per prompt
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.R2V,
            images=all_images if all_images else None,
            settings=settings
        )
    
    def add_t2i_batch(self, prompts: List, settings: Dict) -> str:
        """Add Text-to-Image batch to queue.
        
        Args:
            prompts: List of PromptRow objects
            settings: Sidebar settings dict
        """
        return self.submit_prompts(
            prompts=[p.text if hasattr(p, 'text') else str(p) for p in prompts],
            workflow=WorkflowType.T2I,
            settings=settings
        )
    
    def add_i2i_batch(self, prompts: List, settings: Dict) -> str:
        """Add Image-to-Image batch to queue.
        
        Args:
            prompts: List of PromptRow objects with image_tag
            settings: Sidebar settings dict
        """
        images = []
        prompt_texts = []
        for p in prompts:
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tag') and p.image_tag:
                images.append(p.image_tag)
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.I2I,
            images=images if images else None,
            settings=settings
        )
    
    def activate_license(self, key: str) -> bool:
        """Activate license key.
        
        Args:
            key: License key string
            
        Returns:
            True if activation successful
        """
        if not hasattr(self, '_license_client') or not self._license_client:
            print(f"[WARN] License client not initialized, key: {key[:8]}...")
            return False
        
        result = self._license_client.activate(key)
        if result and hasattr(result, 'success') and result.success:
            self._update_permissions()
            self._notify_status("License activated successfully")
            return True
        
        self._notify_status("License activation failed")
        return False
    
    def start_processing(self):
        """Start processing queue."""
        if self.state.is_processing:
            return
        
        self.state.is_processing = True
        
        # Create workers based on limits
        max_workers = min(
            self._permissions.limits.max_threads,
            self._multi_account.total_capacity,
            4
        )
        
        for i in range(max_workers):
            worker = Worker(
                worker_id=f"worker_{i}",
                api_client=self._api_client,
                on_progress=self._handle_progress,
            )
            self._workers.append(worker)
        
        # Start worker threads
        for worker in self._workers:
            t = threading.Thread(target=self._worker_loop, args=(worker,), daemon=True)
            t.start()
            self._worker_threads.append(t)
        
        self._notify_status("Processing started")
    
    def stop_processing(self):
        """Stop processing queue."""
        self.state.is_processing = False
        
        for worker in self._workers:
            worker.stop()
        
        self._workers.clear()
        self._worker_threads.clear()
        
        self._notify_status("Processing stopped")
    
    def _worker_loop(self, worker: Worker):
        """Worker processing loop."""
        while self.state.is_processing:
            # Get next task
            task = self._dispatcher.get_next_task(timeout=1.0)
            if not task:
                continue
            
            # Get available account
            account = self._multi_account.get_available_account()
            if not account:
                # No account available, requeue task
                task.state = TaskState.READY
                continue
            
            # Execute task
            manager = self._multi_account._accounts.get(account.email)
            if manager and manager.acquire_slot():
                try:
                    # Run in async loop
                    future = self._run_async(worker.execute(task, manager))
                    if future:
                        result = future.result(timeout=300)
                        self._process_result(task, result)
                finally:
                    manager.release_slot()
    
    def _process_result(self, task: Task, result: WorkerResult):
        """Process worker result."""
        if result.success:
            self._dispatcher.complete_task(
                task.id,
                result.output_uris,
            )
            self.state.completed_count += 1
        else:
            self._dispatcher.fail_task(task.id, result.error or "Unknown error")
            self.state.error_count += 1
        
        self.state.queue_count = max(0, self.state.queue_count - 1)
        self._notify_queue_updated()
    
    # === EVENT HANDLERS ===
    
    def _handle_task_completed(self, task: Task):
        """Handle task completion."""
        if self._on_task_completed:
            self._on_task_completed(task)
    
    def _handle_task_failed(self, task: Task, error: str):
        """Handle task failure."""
        if self._on_task_failed:
            self._on_task_failed(task, error)
    
    def _handle_progress(self, task_id: str, progress: int):
        """Handle progress update."""
        self._dispatcher.update_progress(task_id, progress)
        if self._on_progress:
            self._on_progress(task_id, progress)
    
    def _handle_session_expired(self, email: str, event: SessionEvent):
        """Handle session expiry."""
        self._refresh_manager.request_refresh(email, event.value)
    
    def _notify_status(self, status: str):
        """Notify status change."""
        if self._on_status_changed:
            self._on_status_changed(status)
    
    def _notify_queue_updated(self):
        """Notify queue update."""
        if self._on_queue_updated:
            self._on_queue_updated(self.get_queue_status())
    
    # === PERMISSIONS ===
    
    def _update_permissions(self):
        """Update permissions from license."""
        if self._license_client.is_licensed:
            info = self._license_client.license_info
            if info:
                from config.constants import LicenseTier
                try:
                    tier = LicenseTier(info.tier.value)
                    self._permissions.set_role_from_tier(tier)
                except ValueError:
                    pass
    
    def has_feature(self, feature: Feature) -> bool:
        """Check if feature is available."""
        return self._permissions.has_feature(feature)
    
    # === GETTERS ===
    
    def get_queue_status(self) -> Dict:
        """Get current queue status."""
        return {
            "total": self.state.queue_count,
            "completed": self.state.completed_count,
            "errors": self.state.error_count,
            "is_processing": self.state.is_processing,
            **self._dispatcher.get_status_summary(),
        }
    
    def get_permissions_summary(self) -> Dict:
        """Get permissions summary."""
        return {
            "role": self._permissions.role.value,
            "limits": self._permissions.get_limits_summary(),
            "features": self._permissions.get_feature_status(),
        }
    
    # === UI CALLBACK SETTERS ===
    
    def set_task_completed_callback(self, callback: Callable[[Task], None]):
        self._on_task_completed = callback
    
    def set_task_failed_callback(self, callback: Callable[[Task, str], None]):
        self._on_task_failed = callback
    
    def set_progress_callback(self, callback: Callable[[str, int], None]):
        self._on_progress = callback
    
    def set_queue_updated_callback(self, callback: Callable[[Dict], None]):
        self._on_queue_updated = callback
    
    def set_status_callback(self, callback: Callable[[str], None]):
        self._on_status_changed = callback
