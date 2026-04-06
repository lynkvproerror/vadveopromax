"""
VEO Pro Max - Queue DTO Contracts

Single source of truth for data transferred between Controller → UI.
Both layers import from this module, ensuring field names always match.

Key principle: No hardcoded string keys. If a field is missing here,
it doesn't exist in the contract.

Usage:
    Controller: builds DTOs, calls to_dict() for signal emission
    UI: reads from dict using same field names defined here
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Any
from datetime import datetime


@dataclass(slots=True)
class VideoSlotDTO:
    """Per-video output state — maps to one thumbnail slot in Queue UI.
    
    Border color semantics:
    - gray:   pending / no download yet
    - yellow: 720p downloaded, no upscale
    - blue:   upscaled (1080p/4K)
    - red:    upscale failed
    - purple: currently upscaling
    """
    index: int = 0
    quality: str = ""
    upscale_status: str = ""
    upscale_error: str = ""
    best_file: str = ""
    border_color: str = "gray"
    thumbnail_path: str = ""
    task_id: str = ""
    target_quality: str = "1080p"
    upscale_poll_count: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TaskDTO:
    """Per-task state — maps to one row in Queue UI.
    
    Field names here are the CANONICAL names used in both
    Controller (get_queue_groups) and UI (td.get / td[]).
    """
    id: str = ""
    index: int = 0
    prompt: str = ""
    status: str = "pending"
    stage: str = ""
    is_upscaling: bool = False
    progress: int = 0
    mode: str = "T2V"
    has_continuation: bool = False
    parent_id: Optional[str] = None
    error: str = ""
    output_count: int = 4
    output_files: List[str] = field(default_factory=list)
    thumbnails: List[str] = field(default_factory=list)     # ← canonical name
    image_paths: List[str] = field(default_factory=list)
    continuation_frame: str = ""
    upscale_status: str = ""
    upscale_error: str = ""
    image_upload_status: str = ""
    download_quality: str = "720p"
    status_text: str = ""
    started_at: Any = None   # datetime or ISO string
    completed_at: Any = None # datetime or ISO string
    elapsed_seconds: float = 0.0  # computed per-task processing time
    retry_progress: int = -1       # replacement task progress (-1 = not retrying)
    retry_status_text: str = ""    # replacement task status text
    video_outputs: List[VideoSlotDTO] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        # Serialize datetimes to ISO strings for JSON safety
        for key in ('started_at', 'completed_at'):
            if isinstance(d.get(key), datetime):
                d[key] = d[key].isoformat()
        return d


@dataclass(slots=True)
class GroupDTO:
    """Task group — maps to one collapsible section in Queue UI."""
    id: str = ""
    name: str = ""
    status: str = ""
    progress: int = 0
    completed: int = 0
    total: int = 0
    mode: str = "T2V"
    model: str = ""
    output_folder: str = ""
    project_name: str = ""
    aspect_ratio: str = ""
    output_count: int = 4
    download_quality: str = "720p"
    created_at: Any = None  # datetime or str
    elapsed_seconds: float = 0.0  # computed: total processing time for this group
    eta_seconds: float = 0.0      # computed: estimated remaining time for this group
    tasks: List[TaskDTO] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "progress": self.progress,
            "completed": self.completed,
            "total": self.total,
            "mode": self.mode,
            "model": self.model,
            "output_folder": self.output_folder,
            "project_name": self.project_name,
            "aspect_ratio": self.aspect_ratio,
            "output_count": self.output_count,
            "download_quality": self.download_quality,
            "created_at": self.created_at,
            "elapsed_seconds": self.elapsed_seconds,
            "eta_seconds": self.eta_seconds,
            "tasks": [t if isinstance(t, dict) else t.to_dict() for t in self.tasks],
        }
        return d
