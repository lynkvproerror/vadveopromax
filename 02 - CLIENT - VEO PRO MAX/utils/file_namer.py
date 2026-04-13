"""
VEO Pro Max - File Namer

Reference: SESSION_05_BACKEND_FEATURES.md
Role: Generate consistent file names for outputs
"""

from typing import Optional
from datetime import datetime
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class FileNamer:
    """Generate consistent file names for VEO outputs.
    
    Features:
    - Sanitize illegal characters
    - Video naming: {task}_{row}_{output}_{quality}_{timestamp}.mp4
    - Image naming: {task}_{row}_{output}_{timestamp}.png
    - Continuation frame: cont_{row}_{timestamp}.png
    - Conflict resolution (_1, _2, ...)
    """
    
    # Illegal characters for file names (Windows)
    ILLEGAL_CHARS = r'[<>:"/\\|?*\x00-\x1f]'
    
    # Max filename length (excluding extension)
    MAX_NAME_LENGTH = 100
    
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = base_dir
    
    def set_base_dir(self, base_dir: Path):
        """Set base directory for output files."""
        self._base_dir = base_dir
    
    @staticmethod
    def sanitize(name: str, replace_spaces: bool = True) -> str:
        """Sanitize a string for use as filename.
        
        Args:
            name: Original string
            replace_spaces: Replace spaces with underscores
        
        Returns:
            Sanitized string
        """
        # Remove illegal characters
        sanitized = re.sub(FileNamer.ILLEGAL_CHARS, '', name)
        
        # Replace spaces
        if replace_spaces:
            sanitized = sanitized.replace(' ', '_')
        
        # Remove multiple underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Strip leading/trailing underscores
        sanitized = sanitized.strip('_')
        
        # Truncate if too long
        if len(sanitized) > FileNamer.MAX_NAME_LENGTH:
            sanitized = sanitized[:FileNamer.MAX_NAME_LENGTH]
        
        return sanitized or "unnamed"
    
    @staticmethod
    def _timestamp() -> str:
        """Generate timestamp string."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def video_name(
        self,
        task_name: str,
        row_index: int,
        output_index: int = 1,
        quality: str = "720p",
        extension: str = ".mp4",
    ) -> str:
        """Generate video filename.
        
        Format: {task}_{row}_{output}_{quality}_{timestamp}.mp4
        
        Args:
            task_name: Name of the task/project
            row_index: Prompt row index
            output_index: Output number (1-4)
            quality: Video quality (720p, 1080p, 4K)
            extension: File extension
        
        Returns:
            Formatted filename
        """
        task = self.sanitize(task_name)[:30]
        timestamp = self._timestamp()
        
        name = f"{task}_{row_index:03d}_{output_index}_{quality}_{timestamp}"
        return f"{name}{extension}"
    
    def image_name(
        self,
        task_name: str,
        row_index: int,
        output_index: int = 1,
        extension: str = ".png",
    ) -> str:
        """Generate image filename.
        
        Format: {task}_{row}_{output}_{timestamp}.png
        
        Args:
            task_name: Name of the task/project
            row_index: Prompt row index
            output_index: Output number (1-4)
            extension: File extension
        
        Returns:
            Formatted filename
        """
        task = self.sanitize(task_name)[:30]
        timestamp = self._timestamp()
        
        name = f"{task}_{row_index:03d}_{output_index}_{timestamp}"
        return f"{name}{extension}"
    
    def continuation_frame_name(
        self,
        row_index: int,
        extension: str = ".png",
    ) -> str:
        """Generate continuation frame filename.
        
        Format: cont_{row}_{timestamp}.png
        
        Args:
            row_index: Source row index
            extension: File extension
        
        Returns:
            Formatted filename
        """
        timestamp = self._timestamp()
        return f"cont_{row_index:03d}_{timestamp}{extension}"
    
    def upscaled_name(
        self,
        original_name: str,
        target_quality: str = "1080p",
    ) -> str:
        """Generate upscaled video filename.
        
        Format: {original_base}_{quality}_upscaled.mp4
        
        Args:
            original_name: Original filename
            target_quality: Target quality
        
        Returns:
            Formatted filename
        """
        path = Path(original_name)
        base = path.stem
        ext = path.suffix or ".mp4"
        
        # Remove old quality suffix if present
        base = re.sub(r'_(720p|1080p|4K)', '', base)
        
        return f"{base}_{target_quality}_upscaled{ext}"
    
    def ensure_unique(self, file_path: str) -> str:
        """Ensure filename is unique by adding numeric suffix.
        
        If file exists: name.ext → name_1.ext → name_2.ext ...
        
        Convention unified with core.output_naming.ensure_unique_path().
        
        Args:
            file_path: Proposed file path
        
        Returns:
            Unique file path
        """
        path = Path(file_path)
        
        if not path.exists():
            return file_path
        
        base = path.stem
        ext = path.suffix
        parent = path.parent
        
        # Check for existing numeric suffix
        match = re.match(r'(.+)_(\d+)$', base)
        if match:
            base_name = match.group(1)
            counter = int(match.group(2))
        else:
            base_name = base
            counter = 0
        
        # Find next available number
        while True:
            counter += 1
            new_name = f"{base_name}_{counter}{ext}"
            new_path = parent / new_name
            
            if not new_path.exists():
                return str(new_path)
            
            if counter > 9999:  # Safety limit
                # Use timestamp as fallback
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                return str(parent / f"{base_name}_{timestamp}{ext}")
    
    def full_path(
        self,
        filename: str,
        subfolder: Optional[str] = None,
    ) -> Path:
        """Get full path for a filename.
        
        Args:
            filename: The filename
            subfolder: Optional subfolder within base_dir
        
        Returns:
            Full Path object
        """
        if self._base_dir is None:
            return Path(filename)
        
        if subfolder:
            return self._base_dir / subfolder / filename
        
        return self._base_dir / filename
    
    def create_output_structure(self, project_name: str) -> dict:
        """Create output folder structure for a project.
        
        Returns dict with folder paths.
        """
        if self._base_dir is None:
            raise ValueError("Base directory not set")
        
        safe_name = self.sanitize(project_name)
        project_dir = self._base_dir / safe_name
        
        folders = {
            "root": project_dir,
            "videos": project_dir / "videos",
            "images": project_dir / "images",
            "frames": project_dir / "frames",
            "logs": project_dir / "logs",
        }
        
        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)
        
        return {k: str(v) for k, v in folders.items()}
