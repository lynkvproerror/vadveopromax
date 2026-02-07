"""
VEO Pro Max - Generation Controller

Controller for generation tabs (T2V, I2V, R2V, T2I, I2I).
"""

from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import asyncio
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.dispatcher import Task, TaskState
from core.api_client import VEOApiClient
from core.media_handler import MediaHandler
from core.batch_parser import BatchParser, ParsedPrompt
from core.import_validator import ImportValidator
from core.event_manager import EventType, emit_event
from config.constants import WorkflowType, AspectRatio, VideoModel


@dataclass
class GenerationRequest:
    """A generation request from UI."""
    prompts: List[str]
    workflow: WorkflowType
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    model: VideoModel = VideoModel.VEO_FAST_31
    output_count: int = 4
    duration: int = 8
    image_paths: Optional[List[str]] = None
    reference_video: Optional[str] = None
    is_continuation: bool = False
    source_video: Optional[str] = None


@dataclass
class GenerationResult:
    """Result of a generation."""
    success: bool
    task_id: str
    output_uris: List[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.output_uris is None:
            self.output_uris = []


class GenerationController:
    """Controller for generation workflows.
    
    Manages:
    - Prompt handling from UI
    - Image/video preprocessing
    - Task submission
    - Result handling
    """
    
    def __init__(self, app_controller):
        self._app = app_controller
        self._media_handler = MediaHandler()
        self._batch_parser = BatchParser()
        self._validator = ImportValidator()
        
        # Pending requests
        self._pending: Dict[str, GenerationRequest] = {}
        
        # Callbacks
        self._on_generation_started: Optional[Callable[[str], None]] = None
        self._on_generation_completed: Optional[Callable[[GenerationResult], None]] = None
    
    def set_callbacks(
        self,
        on_started: Optional[Callable[[str], None]] = None,
        on_completed: Optional[Callable[[GenerationResult], None]] = None,
    ):
        """Set UI callbacks."""
        self._on_generation_started = on_started
        self._on_generation_completed = on_completed
    
    # === PROMPT HANDLING ===
    
    def parse_prompts_from_text(self, text: str) -> List[ParsedPrompt]:
        """Parse prompts from text input."""
        return self._batch_parser.parse_text(text)
    
    def parse_prompts_from_file(self, file_path: str) -> List[ParsedPrompt]:
        """Parse prompts from file (TXT/CSV)."""
        return self._batch_parser.parse_file(file_path)
    
    def validate_prompts(self, prompts: List[ParsedPrompt]) -> Dict:
        """Validate prompts and return validation result."""
        result = self._validator.validate_prompts(prompts)
        return {
            "valid": result.valid,
            "error_count": sum(1 for i in result.issues if i.severity.value == "error"),
            "warning_count": sum(1 for i in result.issues if i.severity.value == "warning"),
            "issues": [
                {
                    "line": i.line_number,
                    "severity": i.severity.value,
                    "message": i.message,
                }
                for i in result.issues
            ],
            "valid_prompts": [p.text for p in result.prompts],
        }
    
    # === IMAGE HANDLING ===
    
    def prepare_image(self, image_path: str) -> Optional[Dict]:
        """Prepare image for API upload.
        
        Returns dict with base64 and mime_type.
        """
        result = self._media_handler.image_to_base64(image_path)
        if result:
            base64_data, mime_type = result
            return {
                "base64": base64_data,
                "mime_type": mime_type,
                "original_path": image_path,
            }
        return None
    
    def get_image_info(self, image_path: str) -> Optional[Dict]:
        """Get image information."""
        return self._media_handler.get_image_info(image_path)
    
    def detect_aspect_ratio(self, image_path: str) -> Optional[AspectRatio]:
        """Detect aspect ratio from image."""
        info = self._media_handler.get_image_info(image_path)
        if not info:
            return None
        
        ratio = info["width"] / info["height"]
        if ratio > 1.5:
            return AspectRatio.LANDSCAPE
        elif ratio < 0.7:
            return AspectRatio.PORTRAIT
        else:
            return AspectRatio.SQUARE
    
    # === GENERATION SUBMISSION ===
    
    def submit_generation(self, request: GenerationRequest) -> str:
        """Submit generation request.
        
        Returns group_id for tracking.
        """
        # Validate workflow
        if request.workflow == WorkflowType.I2V and not request.image_paths:
            raise ValueError("Image required for I2V workflow")
        
        if request.workflow == WorkflowType.R2V and not request.reference_video:
            raise ValueError("Reference video required for R2V workflow")
        
        # Submit to app controller
        settings = {
            "aspect_ratio": request.aspect_ratio.value,
            "model": request.model.value,
            "output_count": request.output_count,
            "duration": request.duration,
        }
        
        group_id = self._app.submit_prompts(
            prompts=request.prompts,
            workflow=request.workflow,
            images=request.image_paths,
            settings=settings,
        )
        
        # Track request
        self._pending[group_id] = request
        
        # Emit event
        emit_event(
            EventType.TASK_SUBMITTED,
            {"group_id": group_id, "count": len(request.prompts)},
            source="GenerationController",
        )
        
        if self._on_generation_started:
            self._on_generation_started(group_id)
        
        return group_id
    
    def submit_t2v(
        self,
        prompts: List[str],
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        model: VideoModel = VideoModel.VEO_FAST_31,
        output_count: int = 4,
        duration: int = 8,
    ) -> str:
        """Submit Text-to-Video generation."""
        request = GenerationRequest(
            prompts=prompts,
            workflow=WorkflowType.T2V,
            aspect_ratio=aspect_ratio,
            model=model,
            output_count=output_count,
            duration=duration,
        )
        return self.submit_generation(request)
    
    def submit_i2v(
        self,
        prompts: List[str],
        image_paths: List[str],
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        model: VideoModel = VideoModel.VEO_FAST_31,
        output_count: int = 4,
        duration: int = 8,
    ) -> str:
        """Submit Image-to-Video generation."""
        request = GenerationRequest(
            prompts=prompts,
            workflow=WorkflowType.I2V,
            image_paths=image_paths,
            aspect_ratio=aspect_ratio,
            model=model,
            output_count=output_count,
            duration=duration,
        )
        return self.submit_generation(request)
    
    def submit_r2v(
        self,
        prompts: List[str],
        reference_video: str,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        model: VideoModel = VideoModel.VEO_FAST_31,
        output_count: int = 4,
    ) -> str:
        """Submit Reference-to-Video generation."""
        request = GenerationRequest(
            prompts=prompts,
            workflow=WorkflowType.R2V,
            reference_video=reference_video,
            aspect_ratio=aspect_ratio,
            model=model,
            output_count=output_count,
        )
        return self.submit_generation(request)
    
    def submit_continuation(
        self,
        prompts: List[str],
        source_video: str,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        duration: int = 8,
    ) -> str:
        """Submit continuation generation."""
        request = GenerationRequest(
            prompts=prompts,
            workflow=WorkflowType.CONTINUATION,
            source_video=source_video,
            is_continuation=True,
            aspect_ratio=aspect_ratio,
            duration=duration,
        )
        return self.submit_generation(request)
    
    # === STATUS ===
    
    def get_pending_count(self) -> int:
        """Get count of pending requests."""
        return len(self._pending)
    
    def clear_pending(self, group_id: str):
        """Clear a pending request."""
        if group_id in self._pending:
            del self._pending[group_id]
