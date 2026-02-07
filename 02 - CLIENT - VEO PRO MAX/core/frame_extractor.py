"""
VEO Pro Max - Frame Extractor

Reference: CORE_MODULES_SPEC.md
Role: Extract frames from video for continuation workflow
"""

from typing import Optional
from pathlib import Path
from datetime import datetime
import subprocess
import shutil
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class FrameExtractor:
    """Extracts frames from videos for continuation workflow.
    
    Features:
    - Extract frame at specified offset (default 750ms before end)
    - Output to temp folder or specified path
    - Cleanup old frames
    - Cross-account compatible (LOCAL operation)
    """
    
    DEFAULT_OFFSET_MS = 750  # Extract frame 750ms before video end
    FRAME_FORMAT = "jpg"
    FRAME_QUALITY = 2  # FFmpeg quality (2 = high, 31 = low)
    
    def __init__(self, temp_dir: Optional[Path] = None):
        self._temp_dir = temp_dir or Path(tempfile.gettempdir()) / "veoauto_frames"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        
        self._ffmpeg_path = self._find_ffmpeg()
    
    @property
    def is_available(self) -> bool:
        """Check if FFmpeg is available."""
        return self._ffmpeg_path is not None
    
    @staticmethod
    def _find_ffmpeg() -> Optional[str]:
        """Find FFmpeg executable."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        
        # Check common locations on Windows
        common_paths = [
            Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        ]
        
        for path in common_paths:
            if path.exists():
                return str(path)
        
        return None
    
    def get_video_duration(self, video_path: str) -> Optional[float]:
        """Get video duration in seconds using FFprobe."""
        if not self._ffmpeg_path:
            return None
        
        ffprobe = self._ffmpeg_path.replace("ffmpeg", "ffprobe")
        if not Path(ffprobe).exists():
            # Try ffprobe in same directory
            ffprobe = str(Path(self._ffmpeg_path).parent / "ffprobe.exe")
            if not Path(ffprobe).exists():
                ffprobe = shutil.which("ffprobe")
        
        if not ffprobe:
            return None
        
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return float(result.stdout.strip())
            return None
            
        except Exception:
            return None
    
    def extract_frame(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        offset_ms: Optional[int] = None,
        from_end: bool = True
    ) -> Optional[str]:
        """Extract a single frame from video.
        
        Args:
            video_path: Path to video file
            output_path: Where to save frame (auto-generated if None)
            offset_ms: Milliseconds offset (from end if from_end=True)
            from_end: If True, offset is from video end
        
        Returns:
            Path to extracted frame or None on error
        """
        if not self._ffmpeg_path:
            return None
        
        video_file = Path(video_path)
        if not video_file.exists():
            return None
        
        # Determine output path
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            output_path = str(self._temp_dir / f"frame_{timestamp}.{self.FRAME_FORMAT}")
        
        # Calculate timestamp
        offset = offset_ms if offset_ms is not None else self.DEFAULT_OFFSET_MS
        
        if from_end:
            duration = self.get_video_duration(video_path)
            if duration is None:
                # Default assumption: 8 second video
                duration = 8.0
            
            timestamp_sec = max(0, duration - (offset / 1000.0))
        else:
            timestamp_sec = offset / 1000.0
        
        try:
            result = subprocess.run(
                [
                    self._ffmpeg_path,
                    "-y",  # Overwrite output
                    "-ss", str(timestamp_sec),  # Seek to timestamp
                    "-i", video_path,
                    "-frames:v", "1",  # Extract 1 frame
                    "-q:v", str(self.FRAME_QUALITY),  # Quality
                    output_path
                ],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode == 0 and Path(output_path).exists():
                return output_path
            return None
            
        except Exception:
            return None
    
    def extract_last_frame(self, video_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """Extract the last frame of a video.
        
        Convenience method using default offset (750ms before end).
        """
        return self.extract_frame(video_path, output_path, self.DEFAULT_OFFSET_MS, from_end=True)
    
    def extract_first_frame(self, video_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """Extract the first frame of a video."""
        return self.extract_frame(video_path, output_path, 0, from_end=False)
    
    def cleanup_old_frames(self, max_age_hours: int = 24) -> int:
        """Delete frames older than specified age.
        
        Returns number of files deleted.
        """
        deleted = 0
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        
        try:
            for file in self._temp_dir.glob(f"*.{self.FRAME_FORMAT}"):
                if file.stat().st_mtime < cutoff:
                    file.unlink()
                    deleted += 1
        except Exception:
            pass
        
        return deleted
    
    def cleanup_all_frames(self) -> int:
        """Delete all temporary frames.
        
        Returns number of files deleted.
        """
        deleted = 0
        try:
            for file in self._temp_dir.glob(f"*.{self.FRAME_FORMAT}"):
                file.unlink()
                deleted += 1
        except Exception:
            pass
        
        return deleted
    
    def get_temp_dir(self) -> Path:
        """Get the temporary directory path."""
        return self._temp_dir
    
    def set_ffmpeg_path(self, path: str):
        """Manually set FFmpeg path."""
        if Path(path).exists():
            self._ffmpeg_path = path
