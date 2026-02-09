"""
VEO Pro Max - App Controller

Central controller connecting UI with core engine.
"""

from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
import threading
import logging
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
from core.engine import Engine

# Services
from services.license_client import LicenseClient
from services.permissions import PermissionsSystem, Role, Feature

# Config
from config.settings import AppSettings
from config.constants import WorkflowType


def _wf_display(wt) -> str:
    """Extract clean display name from workflow_type (enum or string)."""
    if hasattr(wt, 'name'):
        return wt.name  # WorkflowType enum → "T2V"
    s = str(wt)
    if '.' in s:
        return s.split('.')[-1]  # "WorkflowType.T2V" → "T2V"
    return s.upper()


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
        
        # Engine — replaces manual threading.Thread worker management
        # Engine uses asyncio.TaskGroup for proper async worker coroutines
        self._engine = Engine(
            account_manager=self._multi_account,
            dispatcher=self._dispatcher,
            api_client=self._api_client,
        )
        
        # Event callbacks (set by UI)
        self._on_task_completed: Optional[Callable[[Task], None]] = None
        self._on_task_failed: Optional[Callable[[Task, str], None]] = None
        self._on_progress: Optional[Callable[[str, int], None]] = None
        self._on_queue_updated: List[Callable[[Dict], None]] = []
        self._on_account_changed: Optional[Callable[[str], None]] = None
        self._on_status_changed: Optional[Callable[[str], None]] = None
        
        # Async event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        
        # ProfilesController reference (set by UI via set_profiles_controller)
        self._profiles_controller = None
        
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
        
        # Stop Engine (replaces old self._workers loop)
        self._run_async(self._engine.stop())
        
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
        """Add an account to the manager.
        
        MultiAccountManager.add_account() accepts AccountSession and
        wraps it in AccountManager internally (per architecture §6.1).
        """
        if not self._permissions.check_limit("max_cookies", len(self._multi_account._accounts)):
            return False
        
        # Correct: pass AccountSession, not AccountManager
        # add_account is async — run via background loop
        future = self._run_async(self._multi_account.add_account(session))
        if future:
            try:
                result = future.result(timeout=5.0)
                if not result:
                    return False
            except Exception:
                return False
        
        self._session_monitor.register_session(session)
        self._refresh_manager.register_session(session)
        
        self._notify_status(f"Account added: {session.email}")
        return True
    
    def remove_account(self, email: str) -> bool:
        """Remove an account."""
        # remove_account is async — run via background loop
        future = self._run_async(self._multi_account.remove_account(email))
        result = False
        if future:
            try:
                result = future.result(timeout=10.0)
            except Exception:
                pass
        
        self._session_monitor.unregister_session(email)
        self._refresh_manager.unregister_session(email)
        return result
    
    def toggle_account(self, email: str, enabled: bool) -> bool:
        """Enable or disable an account without removing it.
        
        Disabled accounts won't be selected for task dispatch.
        """
        account = self._multi_account.get_account(email)
        if not account:
            return False
        
        if enabled:
            account.enable()
            self._notify_status(f"Account enabled: {email}")
        else:
            account.disable()
            self._notify_status(f"Account disabled: {email}")
        return True
    
    def get_accounts(self) -> List[Dict]:
        """Get list of accounts with status."""
        status = self._multi_account.get_status_summary()
        return status.get('accounts', [])
    
    def set_profiles_controller(self, profiles_controller):
        """Set the ProfilesController reference.
        
        Called by UI layer (TabSettings) to bridge persistence → runtime.
        """
        self._profiles_controller = profiles_controller
    
    def sync_profiles_to_runtime(self):
        """Sync profiles from ProfilesController → MultiAccountManager.
        
        Issue E fix: Called before start_processing() to ensure the runtime
        dispatch pool matches the persisted profiles state.
        
        Logic:
        1. Get all profiles from ProfilesController
        2. For each ready + enabled profile not yet in MultiAccountManager:
           create AccountSession and add_account
        3. For each profile already in MultiAccountManager:
           sync enabled/disabled state
        4. Remove runtime accounts that no longer exist in profiles
        """
        log = logging.getLogger(__name__)
        
        if not self._profiles_controller:
            log.debug("No ProfilesController set, skipping sync")
            return
        
        profiles = self._profiles_controller.get_all_profiles()
        profile_emails = {p['email'] for p in profiles}
        
        for p in profiles:
            email = p.get('email', '')
            is_ready = p.get('is_ready', False)
            is_enabled = p.get('is_enabled', True)
            
            existing = self._multi_account.get_account(email)
            
            if existing:
                # Sync enabled/disabled state
                if is_enabled and not existing.is_enabled:
                    existing.enable()
                elif not is_enabled and existing.is_enabled:
                    existing.disable()
            elif is_ready and is_enabled:
                # Profile is ready but not in runtime pool — add it
                try:
                    profile_obj = self._profiles_controller.get_profile(email)
                    if not profile_obj:
                        continue
                    
                    # Build AccountSession from ChromeProfile
                    from core.session import (
                        AccountSession, SubscriptionType, PaygateTier
                    )
                    
                    # Parse token expiry if available
                    token_expires = datetime.now() + timedelta(hours=1)
                    if profile_obj.token_expires_at:
                        try:
                            token_expires = datetime.fromisoformat(
                                profile_obj.token_expires_at
                            )
                        except (ValueError, TypeError):
                            pass
                    
                    session = AccountSession(
                        email=email,
                        access_token=getattr(profile_obj, 'access_token', '') or '',
                        token_expires=token_expires,
                        profile_path=profile_obj.browser_profile_path or profile_obj.profile_path,
                    )
                    
                    # Set SKU/tier if available
                    try:
                        session.sku = SubscriptionType(profile_obj.sku)
                    except (ValueError, KeyError):
                        pass
                    try:
                        session.paygate_tier = PaygateTier(profile_obj.paygate_tier)
                    except (ValueError, KeyError):
                        pass
                    
                    session.credits = profile_obj.credits
                    session.max_slots = getattr(profile_obj, 'max_slots', 4)
                    
                    # Add to runtime via async
                    future = self._run_async(
                        self._multi_account.add_account(session)
                    )
                    if future:
                        try:
                            future.result(timeout=3.0)
                            log.info(f"Synced profile → runtime: {email}")
                        except Exception as e:
                            log.warning(f"Failed to sync {email}: {e}")
                            
                except Exception as e:
                    log.warning(f"Error syncing profile {email}: {e}")
        
        # Remove runtime accounts that no longer exist in profiles
        for acc in list(self._multi_account._accounts):
            if acc.email not in profile_emails:
                future = self._run_async(
                    self._multi_account.remove_account(acc.email)
                )
                if future:
                    try:
                        future.result(timeout=5.0)
                        log.info(f"Removed stale runtime account: {acc.email}")
                    except Exception:
                        pass
        
        log.info(
            f"Profile sync complete: {self._multi_account.account_count} accounts, "
            f"{len(self._multi_account.ready_accounts)} ready"
        )
    
    def set_account_max_slots(self, email: str, max_slots: int):
        """Set max_slots on runtime AccountManager for a given email.
        
        Called by UI when user changes Slots SpinBox.
        """
        acc = self._multi_account.get_account(email)
        if acc:
            acc.set_max_slots(max_slots)
            logging.getLogger(__name__).info(
                f"Runtime max_slots for {email} → {max_slots}"
            )
    
    @staticmethod
    def _map_aspect_ratio(raw: str, workflow: "WorkflowType") -> str:
        """Map sidebar aspect ratio name to correct API enum.
        
        Video endpoints expect VIDEO_ASPECT_RATIO_* prefix.
        Image endpoints expect IMAGE_ASPECT_RATIO_* prefix.
        """
        is_image = workflow in (WorkflowType.T2I, WorkflowType.I2I)
        prefix = "IMAGE_ASPECT_RATIO" if is_image else "VIDEO_ASPECT_RATIO"
        
        raw_upper = raw.upper()
        if "LANDSCAPE" in raw_upper:
            return f"{prefix}_LANDSCAPE"
        elif "PORTRAIT" in raw_upper:
            return f"{prefix}_PORTRAIT"
        elif "SQUARE" in raw_upper:
            return f"{prefix}_SQUARE"
        # Already in full enum format?
        if raw_upper.startswith(("VIDEO_ASPECT_RATIO", "IMAGE_ASPECT_RATIO")):
            return raw
        return f"{prefix}_LANDSCAPE"  # Safe fallback
    
    @staticmethod
    def _default_model(workflow: "WorkflowType") -> str:
        """Return correct default model for workflow type."""
        if workflow in (WorkflowType.T2I, WorkflowType.I2I):
            return "GEM_PIX_2"
        return "veo_3_1_t2v_fast_landscape_ultra"
    
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
        # Apply batch size limit from role
        max_batch = self._permissions.limits.max_prompts_per_batch
        if max_batch > 0:
            prompts = prompts[:max_batch]
        
        # Map settings to correct API values
        raw_ar = (settings or {}).get("aspect_ratio", "LANDSCAPE")
        aspect_ratio = self._map_aspect_ratio(raw_ar, workflow)
        model = (settings or {}).get("model", self._default_model(workflow))
        output_count = (settings or {}).get("outputs_per_prompt", 4)
        
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
                workflow_type=workflow.name,  # "T2V" not WorkflowType.T2V
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                model=model,
                output_count=output_count,
                duration_seconds=(settings or {}).get("duration", 8),
                image_uris=images or [],
                parent_task_id=parent_task_id,
                extract_point_ms=(settings or {}).get("extract_point_ms", 750),
                download_quality=(settings or {}).get("download_quality", "720p"),
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
        continuation_map = {}
        for i, p in enumerate(prompts):
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tags') and p.image_tags:
                all_images.extend(p.image_tags[:3])  # Max 3 images per prompt
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                continuation_map[i] = p.continuation_from - 1
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.R2V,
            images=all_images if all_images else None,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None
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
        """Start processing queue via Engine.
        
        Engine uses asyncio.TaskGroup for proper async worker management.
        The Engine.start() coroutine runs in the background async loop.
        """
        if self.state.is_processing:
            return
        
        self.state.is_processing = True
        
        # Issue E: Sync profiles to runtime before starting
        self.sync_profiles_to_runtime()
        
        # Per-account worker settings (max_slots, retry_count, request_timeout)
        # are now read directly from each AccountManager at runtime.
        # No global max_workers needed.
        
        # Anti-Detect Spam settings (global — applies to all accounts)
        self._engine._anti_detect_enabled = getattr(self.settings, 'anti_detect_enabled', True)
        self._engine._anti_detect_delay_min = getattr(self.settings, 'anti_detect_delay_min', 1.0)
        self._engine._anti_detect_delay_max = getattr(self.settings, 'anti_detect_delay_max', 5.0)
        
        # D1: Continuation Frame settings (global)
        self._engine._continuation_enabled = getattr(self.settings, 'continuation_enabled', True)
        self._engine._extract_point_ms = getattr(self.settings, 'extract_point_ms', 750)
        
        # Wire engine callbacks
        self._engine._on_progress = self._handle_progress
        self._engine._on_task_completed = lambda task: self._handle_task_completed(task)
        self._engine._on_task_failed = lambda task, err: self._handle_task_failed(task, err)
        
        # Start Engine in the async loop
        self._run_async(self._engine.start())
        
        self._notify_status("Processing started")
    
    def stop_processing(self):
        """Stop processing via Engine."""
        self.state.is_processing = False
        
        # Stop Engine
        self._run_async(self._engine.stop())
        
        self._notify_status("Processing stopped")
    
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
        status = self.get_queue_status()
        for cb in self._on_queue_updated:
            try:
                cb(status)
            except Exception:
                pass
    
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
    
    def get_queue_items(self) -> List[Dict]:
        """Get all queue items for UI display."""
        items = []
        for task in self._dispatcher.get_all_tasks():
            items.append({
                "id": task.id,
                "prompt": task.prompt,
                "status": task.state.value,
                "progress": task.progress,
                "mode": _wf_display(task.workflow_type) if task.workflow_type else "T2V",
                "project": task.project_id or "Default",
                "error": task.error,
                "created_at": task.created_at,
            })
        return items
    
    def get_queue_groups(self) -> List[Dict]:
        """Get queue groups with child tasks for hierarchical UI display."""
        groups = self._dispatcher.get_all_groups()
        result = []
        for gid, group in groups.items():
            completed = sum(1 for t in group.tasks if t.state == TaskState.COMPLETED)
            total = len(group.tasks)
            # Detect mode/model from first task
            first = group.tasks[0] if group.tasks else None
            result.append({
                "id": gid,
                "name": group.name,
                "status": group.status,
                "progress": group.progress,
                "completed": completed,
                "total": total,
                "mode": _wf_display(first.workflow_type) if first else "T2V",
                "model": (first.model if first else ""),
                "created_at": group.created_at,
                "tasks": [
                    {
                        "id": t.id,
                        "index": i + 1,
                        "prompt": t.prompt,
                        "status": t.state.value,
                        "progress": t.progress,
                        "mode": _wf_display(t.workflow_type) if t.workflow_type else "T2V",
                        "has_continuation": t.parent_task_id is not None,
                        "parent_id": t.parent_task_id,
                        "error": t.error,
                    }
                    for i, t in enumerate(group.tasks)
                ],
            })
        return result
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a specific task."""
        return self._dispatcher.cancel_task(task_id)
    
    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task."""
        return self._dispatcher.retry_task(task_id)
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks."""
        return self._dispatcher.retry_all_failed()
    
    def clear_all_tasks(self) -> int:
        """Clear all non-running tasks."""
        return self._dispatcher.clear_all()
    
    def clear_completed_tasks(self):
        """Clear completed/failed/cancelled tasks."""
        self._dispatcher.clear_completed()
    
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
        if not hasattr(self, '_on_queue_updated') or not isinstance(self._on_queue_updated, list):
            self._on_queue_updated = []
        self._on_queue_updated.append(callback)
    
    def set_status_callback(self, callback: Callable[[str], None]):
        self._on_status_changed = callback
    
    # === SESSION PERSISTENCE ===
    
    def save_full_session(self, tabs_data: dict) -> bool:
        """Save full session: tab states + queue state.
        
        Args:
            tabs_data: {"t2v": {...}, "i2v": {...}, ...} from MainWindow
        
        Returns:
            True if saved successfully
        """
        from core.session_manager import SessionManager
        sm = SessionManager()
        
        # Export queue state from dispatcher
        queue_data = self._dispatcher.export_state()
        
        return sm.save_session({
            "tabs": tabs_data,
            "queue": queue_data,
        })
    
    def restore_session(self) -> dict:
        """Restore session from disk.
        
        Returns:
            Full session data dict (tabs + queue).
            Dispatcher queue is automatically restored.
        """
        from core.session_manager import SessionManager
        sm = SessionManager()
        
        data = sm.load_session()
        if not data:
            return {}
        
        # Restore queue into dispatcher
        queue_data = data.get("queue", {})
        if queue_data:
            count = self._dispatcher.import_state(queue_data)
            if count > 0:
                self._notify_queue_updated()
        
        return data
    
    def get_cache_stats(self) -> dict:
        """Get cache folder statistics."""
        from core.session_manager import SessionManager
        sm = SessionManager()
        cache_folder = self._settings.cache_folder if self._settings else None
        return sm.get_cache_stats(cache_folder or None)
    
    def clean_cache(self, max_age_days: int = 7) -> dict:
        """Clean old cache files."""
        from core.session_manager import SessionManager
        sm = SessionManager()
        cache_folder = self._settings.cache_folder if self._settings else None
        return sm.clean_cache(max_age_days, cache_folder or None)
    
    def clear_cache(self) -> dict:
        """Clear all cache files."""
        from core.session_manager import SessionManager
        sm = SessionManager()
        cache_folder = self._settings.cache_folder if self._settings else None
        return sm.clear_cache(cache_folder or None)
