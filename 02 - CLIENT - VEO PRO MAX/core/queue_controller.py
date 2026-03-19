"""
VEO Pro Max - Queue Controller

Controller for Queue Manager tab.
"""

from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.dispatcher import Dispatcher, Task, TaskGroup, TaskState
from core.download_manager import DownloadManager, DownloadResult
from core.upscale_handler import UpscaleHandler
from core.event_manager import EventType, emit_event
from utils.file_namer import FileNamer


@dataclass
class QueueItemView:
    """Queue item for UI display."""
    id: str
    prompt: str
    workflow: str
    status: str
    progress: int
    outputs: List[str]
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class QueueController:
    """Controller for queue management.
    
    Manages:
    - Queue display and filtering
    - Task actions (cancel, retry, priority)
    - Download management
    - Batch operations
    """
    
    def __init__(self, dispatcher: Dispatcher):
        self._dispatcher = dispatcher
        self._download_manager = DownloadManager()
        self._upscale_handler = UpscaleHandler()
        self._file_namer = FileNamer()
        
        # Download tracking
        self._downloads: Dict[str, DownloadResult] = {}
        
        # Callbacks
        self._on_queue_changed: Optional[Callable[[List[QueueItemView]], None]] = None
        self._on_download_progress: Optional[Callable[[str, int], None]] = None
    
    def set_callbacks(
        self,
        on_queue_changed: Optional[Callable[[List[QueueItemView]], None]] = None,
        on_download_progress: Optional[Callable[[str, int], None]] = None,
    ):
        """Set UI callbacks."""
        self._on_queue_changed = on_queue_changed
        self._on_download_progress = on_download_progress
    
    # === QUEUE DISPLAY ===
    
    def get_queue_items(
        self,
        status_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[QueueItemView]:
        """Get queue items for display.
        
        Args:
            status_filter: Filter by status (pending, running, completed, failed)
            limit: Max items to return
        """
        all_tasks = self._dispatcher.get_all_tasks()
        
        # Filter by status
        if status_filter:
            state_map = {
                "pending": [TaskState.PENDING, TaskState.WAITING, TaskState.READY],
                "running": [TaskState.RUNNING],
                "completed": [TaskState.COMPLETED],
                "failed": [TaskState.FAILED, TaskState.CANCELLED],
            }
            allowed_states = state_map.get(status_filter, [])
            all_tasks = [t for t in all_tasks if t.state in allowed_states]
        
        # Convert to view items
        items = []
        for task in all_tasks[:limit]:
            # ★ FIX: Combine task.state with upscale_status for accurate display
            display_status = task.state.value
            if task.state == TaskState.COMPLETED and getattr(task, 'video_outputs', None):
                upscale_statuses = [
                    getattr(vo, 'upscale_status', '') for vo in task.video_outputs
                ]
                if any(s in ("submitting", "polling") for s in upscale_statuses):
                    display_status = "upscaling"
                elif any(s == "failed" for s in upscale_statuses):
                    # Check if task wanted upscale but it failed
                    wants_upscale = getattr(task, 'download_quality', '720p') != '720p'
                    if wants_upscale:
                        display_status = "upscale_failed"
            item = QueueItemView(
                id=task.id,
                prompt=task.prompt[:50] + "..." if len(task.prompt) > 50 else task.prompt,
                workflow=str(task.workflow_type) if task.workflow_type else "unknown",
                status=display_status,
                progress=task.progress,
                outputs=task.output_uris or [],
                created_at=task.created_at or datetime.now(),
                completed_at=task.completed_at,
                error=task.error,
            )
            items.append(item)
        
        return items
    
    def get_queue_stats(self) -> Dict:
        """Get queue statistics."""
        return self._dispatcher.get_status_summary()
    
    # === TASK ACTIONS ===
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        return self._dispatcher.cancel_task(task_id)
    
    def cancel_group(self, group_id: str) -> int:
        """Cancel all tasks in a group.
        
        Returns count of cancelled tasks.
        """
        return self._dispatcher.cancel_group(group_id)
    
    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task."""
        return self._dispatcher.retry_task(task_id)
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks.
        
        Returns count of retried tasks.
        """
        return self._dispatcher.retry_all_failed()
    
    def auto_sweep(self) -> dict:
        """Auto-sweep: scan ALL tasks for incomplete work and retry.
        
        Checks:
        1. FAILED tasks → retry_all_failed()
        2. COMPLETED tasks with video quality='failed' → force_retry_all_failed_videos()
        3. COMPLETED tasks with missing 720p files → flag as incomplete
        4. COMPLETED tasks with upscale_status='failed' → flag as incomplete
        
        Returns:
            {"retried_tasks": N, "retried_videos": M, "still_incomplete": K}
        """
        import logging
        log = logging.getLogger("queue_controller")
        
        retried_tasks = 0
        retried_videos = 0
        still_incomplete = 0
        
        # Phase 1: Retry all FAILED tasks
        retried_tasks = self._dispatcher.retry_all_failed()
        
        # Phase 2: Retry failed video slots (within COMPLETED tasks)
        retried_videos = self._dispatcher.force_retry_all_failed_videos()
        
        # Phase 3: Count remaining incomplete items
        for task in self._dispatcher._all_tasks.values():
            if task.replace_target:
                continue  # Skip replacement tasks
            
            if task.state == TaskState.FAILED:
                still_incomplete += 1
                continue
            
            if task.state != TaskState.COMPLETED:
                continue  # Only check completed tasks
            
            if not task.video_outputs:
                continue
            
            for vo in task.video_outputs:
                # Missing base file download (720p for video, 1K for image)
                if vo.quality not in ("failed", "retrying") and not vo.file_720p:
                    still_incomplete += 1
                    break
                # Failed upscale (when upscale was expected)
                if vo.upscale_status == "failed":
                    still_incomplete += 1
                    break
                # Generation failed
                if vo.quality == "failed":
                    still_incomplete += 1
                    break
                # ★ Image upscale incomplete: task wants 2K but image still at 1K
                is_image = getattr(task, 'workflow_type', '') in ('T2I', 'I2I')
                wants_upscale = getattr(task, 'download_quality', '720p') in ('1080p', '4K', '2K')
                if is_image and wants_upscale and vo.quality == "1K" and not vo.file_upscaled:
                    if vo.upscale_status not in ("submitting", "polling", "success"):
                        still_incomplete += 1
                        break
                # ★ Video upscale incomplete: task wants 1080p/4K but video still at 720p
                if not is_image and wants_upscale and vo.quality == "720p" and not vo.file_upscaled:
                    if vo.upscale_status not in ("submitting", "polling", "success"):
                        still_incomplete += 1
                        break
        
        total_retried = retried_tasks + retried_videos
        if total_retried > 0:
            log.info(
                f"[AutoSweep] Retried {retried_tasks} task(s), "
                f"{retried_videos} video(s), "
                f"{still_incomplete} still incomplete"
            )
        
        return {
            "retried_tasks": retried_tasks,
            "retried_videos": retried_videos,
            "still_incomplete": still_incomplete,
        }
    
    def set_priority(self, task_id: str, priority: int) -> bool:
        """Set task priority (higher = sooner)."""
        return self._dispatcher.set_priority(task_id, priority)
    
    def clear_completed(self) -> int:
        """Clear completed tasks from queue.
        
        Returns count of cleared tasks.
        """
        return self._dispatcher.clear_completed()
    
    def clear_all(self) -> int:
        """Clear all tasks from queue.
        
        Returns count of cleared tasks.
        """
        return self._dispatcher.clear_all()
    
    # === DOWNLOAD MANAGEMENT ===
    
    async def download_output(
        self,
        url: str,
        output_dir: str,
        filename: Optional[str] = None,
    ) -> DownloadResult:
        """Download a single output file.
        
        Args:
            url: URL to download
            output_dir: Output directory
            filename: Optional filename (auto-generated if None)
        
        Returns:
            DownloadResult
        """
        if not filename:
            filename = self._file_namer.video_name("output", 1)
        
        output_path = str(Path(output_dir) / filename)
        
        result = await self._download_manager.download(
            url=url,
            output_path=output_path,
            progress_callback=lambda p: self._handle_download_progress(url, p),
        )
        
        self._downloads[url] = result
        
        emit_event(
            EventType.DOWNLOAD_COMPLETED if result.success else EventType.DOWNLOAD_FAILED,
            {"url": url, "path": result.path, "error": result.error},
        )
        
        return result
    
    async def download_all_outputs(
        self,
        output_dir: str,
        urls: Optional[List[str]] = None,
    ) -> List[DownloadResult]:
        """Download all completed outputs.
        
        Args:
            output_dir: Output directory
            urls: Specific URLs to download (all completed if None)
        
        Returns:
            List of DownloadResult
        """
        if urls is None:
            # Get all completed task outputs
            completed = self._dispatcher.get_completed_tasks()
            urls = []
            for task in completed:
                if task.output_uris:
                    urls.extend(task.output_uris)
        
        results = []
        for i, url in enumerate(urls):
            filename = self._file_namer.video_name("batch", i + 1)
            result = await self.download_output(url, output_dir, filename)
            results.append(result)
        
        return results
    
    def _handle_download_progress(self, url: str, progress: int):
        """Handle download progress update."""
        if self._on_download_progress:
            self._on_download_progress(url, progress)
    
    # === UPSCALE ===
    
    async def upscale_video(
        self,
        video_url: str,
        target_quality: str = "1080p",
    ) -> Dict:
        """Submit video for upscaling.
        
        Returns operation info.
        """
        # This would integrate with VEO API upscale endpoint
        # For now return placeholder
        return {
            "submitted": True,
            "url": video_url,
            "target_quality": target_quality,
        }
    
    # === EXPORT ===
    
    def export_completed_list(self, output_path: str) -> bool:
        """Export list of completed outputs to file.
        
        Args:
            output_path: Path to save list
        
        Returns:
            Success status
        """
        try:
            completed = self._dispatcher.get_completed_tasks()
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("# Completed Outputs\n\n")
                for task in completed:
                    f.write(f"## {task.id}\n")
                    f.write(f"Prompt: {task.prompt}\n")
                    if task.output_uris:
                        for uri in task.output_uris:
                            f.write(f"- {uri}\n")
                    f.write("\n")
            
            return True
        except Exception:
            return False
