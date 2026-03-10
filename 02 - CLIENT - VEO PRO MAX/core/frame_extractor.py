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
        """Find FFmpeg executable, auto-downloading if not found.
        
        Search order:
        1. System PATH
        2. Common Windows locations
        3. Portable copy in ~/.veoauto/ffmpeg/
        4. Auto-download portable FFmpeg (first time only)
        """
        import logging
        log = logging.getLogger(__name__)
        
        # 1. System PATH
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        
        # 2. Common Windows locations
        common_paths = [
            Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        ]
        for path in common_paths:
            if path.exists():
                return str(path)
        
        # 3. Portable copy in ~/.veoauto/ffmpeg/
        portable_dir = Path.home() / ".veoauto" / "ffmpeg"
        portable_ffmpeg = portable_dir / "ffmpeg.exe"
        if portable_ffmpeg.exists():
            return str(portable_ffmpeg)
        
        # 4. Auto-download portable FFmpeg
        try:
            log.info("[FFmpeg] Not found — auto-downloading portable FFmpeg...")
            return FrameExtractor._auto_download_ffmpeg(portable_dir)
        except Exception as e:
            log.warning(f"[FFmpeg] Auto-download failed: {e}")
            return None
    
    @staticmethod
    def _auto_download_ffmpeg(install_dir: Path) -> Optional[str]:
        """Download portable FFmpeg to install_dir with retry + progress + verify.
        
        Features:
        - 3 retries with exponential backoff (5s, 15s, 30s)
        - Chunked download with progress logging (~10MB intervals)
        - Post-install `ffmpeg -version` verification
        - Cleanup on failure, re-download on verify failure
        
        Uses BtbN/FFmpeg-Builds from GitHub (Windows x64 GPL).
        """
        import logging
        import zipfile
        import urllib.request
        import urllib.error
        import ssl
        import io
        import time
        log = logging.getLogger(__name__)
        
        install_dir.mkdir(parents=True, exist_ok=True)
        
        # SSL context with certifi fallback (for Nuitka-compiled apps)
        ssl_ctx = None
        try:
            ssl_ctx = ssl.create_default_context()
            if not ssl_ctx.get_ca_certs():
                raise RuntimeError("No CA certs")
        except Exception:
            try:
                import certifi
                ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                log.warning("[FFmpeg] SSL: Using unverified context")
        
        # Primary + fallback URLs
        URLS = [
            (
                "https://github.com/BtbN/FFmpeg-Builds/releases/download/"
                "latest/ffmpeg-master-latest-win64-gpl.zip"
            ),
            (
                "https://github.com/GyanD/codexffmpeg/releases/download/"
                "7.1/ffmpeg-7.1-essentials_build.zip"
            ),
        ]
        
        MAX_RETRIES = 3
        BACKOFF = [5, 15, 30]  # seconds
        CHUNK_SIZE = 1024 * 1024  # 1MB chunks
        PROGRESS_INTERVAL_MB = 10
        
        ffmpeg_path = install_dir / "ffmpeg.exe"
        
        for url_idx, url in enumerate(URLS):
            for attempt in range(MAX_RETRIES):
                try:
                    attempt_label = f"attempt {attempt + 1}/{MAX_RETRIES}"
                    if url_idx > 0:
                        attempt_label += f" (mirror {url_idx + 1})"
                    
                    log.info(f"[FFmpeg] ⬇️ Downloading ({attempt_label})...")
                    log.info(f"[FFmpeg]   URL: {url[:80]}...")
                    
                    # — Chunked download with progress —
                    req = urllib.request.Request(url, headers={
                        "User-Agent": "VEO-Pro-Max/2.3.1"
                    })
                    
                    with urllib.request.urlopen(req, timeout=120, context=ssl_ctx) as resp:
                        total = int(resp.headers.get("Content-Length", 0))
                        total_mb = total / 1024 / 1024 if total else 0
                        log.info(
                            f"[FFmpeg]   Size: {total_mb:.1f} MB"
                            if total else "[FFmpeg]   Size: unknown"
                        )
                        
                        chunks = []
                        downloaded = 0
                        last_progress_mb = 0
                        
                        while True:
                            chunk = resp.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            chunks.append(chunk)
                            downloaded += len(chunk)
                            current_mb = downloaded / 1024 / 1024
                            
                            # Log progress every ~10MB
                            if current_mb - last_progress_mb >= PROGRESS_INTERVAL_MB:
                                pct = f" ({downloaded * 100 // total}%)" if total else ""
                                log.info(f"[FFmpeg]   📥 {current_mb:.0f} MB downloaded{pct}")
                                last_progress_mb = current_mb
                        
                        data = b"".join(chunks)
                    
                    final_mb = len(data) / 1024 / 1024
                    log.info(f"[FFmpeg] ✅ Download complete: {final_mb:.1f} MB")
                    
                    # — Extract —
                    log.info("[FFmpeg] 📦 Extracting ffmpeg.exe + ffprobe.exe...")
                    try:
                        with zipfile.ZipFile(io.BytesIO(data)) as zf:
                            extracted = 0
                            for name in zf.namelist():
                                basename = Path(name).name.lower()
                                if basename in ("ffmpeg.exe", "ffprobe.exe"):
                                    target = install_dir / basename
                                    with zf.open(name) as src, open(target, "wb") as dst:
                                        dst.write(src.read())
                                    size_mb = target.stat().st_size / 1024 / 1024
                                    log.info(f"[FFmpeg]   ✅ {basename} ({size_mb:.1f} MB) → {target}")
                                    extracted += 1
                            
                            if extracted == 0:
                                log.error("[FFmpeg] ❌ No ffmpeg.exe found in archive")
                                continue  # Try next attempt
                    except zipfile.BadZipFile:
                        log.error(f"[FFmpeg] ❌ Corrupt archive ({attempt_label})")
                        if attempt < MAX_RETRIES - 1:
                            log.info(f"[FFmpeg] ⏳ Retrying in {BACKOFF[attempt]}s...")
                            time.sleep(BACKOFF[attempt])
                        continue
                    
                    # — Verify: run ffmpeg -version —
                    if ffmpeg_path.exists():
                        verified = FrameExtractor._verify_ffmpeg(str(ffmpeg_path))
                        if verified:
                            log.info(f"[FFmpeg] ✅ Verified — auto-installed to {install_dir}")
                            return str(ffmpeg_path)
                        else:
                            log.error("[FFmpeg] ❌ Verification failed — ffmpeg may be corrupted")
                            # Delete and retry
                            FrameExtractor._cleanup_ffmpeg(install_dir)
                            if attempt < MAX_RETRIES - 1:
                                log.info(f"[FFmpeg] ⏳ Re-downloading in {BACKOFF[attempt]}s...")
                                time.sleep(BACKOFF[attempt])
                            continue
                    else:
                        log.error("[FFmpeg] ❌ ffmpeg.exe missing after extraction")
                        continue
                        
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
                    log.error(f"[FFmpeg] ❌ Download failed ({attempt_label}): {e}")
                    if attempt < MAX_RETRIES - 1:
                        log.info(f"[FFmpeg] ⏳ Retrying in {BACKOFF[attempt]}s...")
                        time.sleep(BACKOFF[attempt])
                    continue
                except Exception as e:
                    log.error(f"[FFmpeg] ❌ Unexpected error ({attempt_label}): {e}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(BACKOFF[attempt])
                    continue
            
            # All retries exhausted for this URL — try next mirror
            log.warning(f"[FFmpeg] ⚠️ All {MAX_RETRIES} attempts failed for URL {url_idx + 1}")
        
        # All URLs exhausted
        log.error("[FFmpeg] ❌ All download sources failed — FFmpeg not available")
        FrameExtractor._cleanup_ffmpeg(install_dir)
        return None
    
    @staticmethod
    def _verify_ffmpeg(ffmpeg_path: str) -> bool:
        """Verify FFmpeg works by running `ffmpeg -version`.
        
        Returns True if ffmpeg runs successfully and outputs version info.
        """
        import logging
        log = logging.getLogger(__name__)
        try:
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and "ffmpeg version" in result.stdout:
                # Extract version line
                version_line = result.stdout.split("\n")[0].strip()
                log.info(f"[FFmpeg] 🔍 {version_line}")
                return True
            else:
                log.error(f"[FFmpeg] ffmpeg -version returned code {result.returncode}")
                return False
        except Exception as e:
            log.error(f"[FFmpeg] Verification error: {e}")
            return False
    
    @staticmethod
    def _cleanup_ffmpeg(install_dir: Path):
        """Remove corrupted/partial FFmpeg files."""
        for f in install_dir.glob("*.exe"):
            try:
                f.unlink()
            except Exception:
                pass
    
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
