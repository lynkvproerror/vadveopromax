"""
VEO Pro Max - Download Manager

Reference: SESSION_05_BACKEND_FEATURES.md
Role: Async file downloads with progress tracking
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, List
from pathlib import Path
from datetime import datetime
import asyncio
import aiohttp
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class DownloadProgress:
    """Progress info for a download."""
    url: str
    output_path: str
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: str = "pending"  # pending, downloading, completed, failed
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def progress_percent(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    output_path: Optional[str] = None
    file_size: int = 0
    error: Optional[str] = None
    download_time: float = 0.0


class DownloadManager:
    """Async download manager with parallel download support.
    
    Features:
    - Parallel downloads with semaphore
    - Progress callback support
    - Streaming downloads for large files
    - Session management
    """
    
    DEFAULT_MAX_PARALLEL = 3
    DEFAULT_CHUNK_SIZE = 8192
    DEFAULT_TIMEOUT = 300  # 5 minutes
    
    def __init__(
        self,
        max_parallel: int = DEFAULT_MAX_PARALLEL,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self._max_parallel = max_parallel
        self._chunk_size = chunk_size
        self._timeout = timeout
        
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Active downloads
        self._active_downloads: dict[str, DownloadProgress] = {}
        
        # Callbacks
        self._on_progress: Optional[Callable[[DownloadProgress], None]] = None
        self._on_complete: Optional[Callable[[DownloadResult], None]] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    def set_progress_callback(self, callback: Callable[[DownloadProgress], None]):
        """Set callback for progress updates."""
        self._on_progress = callback
    
    def set_complete_callback(self, callback: Callable[[DownloadResult], None]):
        """Set callback for download completion."""
        self._on_complete = callback
    
    async def download(
        self,
        url: str,
        output_path: str,
        headers: Optional[dict] = None,
    ) -> DownloadResult:
        """Download a single file.
        
        Args:
            url: URL to download
            output_path: Path to save file
            headers: Optional request headers
        
        Returns:
            DownloadResult
        """
        async with self._semaphore:
            return await self._download_file(url, output_path, headers)
    
    async def _download_file(
        self,
        url: str,
        output_path: str,
        headers: Optional[dict] = None,
    ) -> DownloadResult:
        """Internal download implementation."""
        progress = DownloadProgress(
            url=url,
            output_path=output_path,
            status="downloading",
            started_at=datetime.now(),
        )
        self._active_downloads[url] = progress
        
        try:
            session = await self._get_session()
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return DownloadResult(
                        success=False,
                        error=f"HTTP {response.status}: {response.reason}",
                    )
                
                # Get file size if available
                total_size = response.content_length or 0
                progress.total_bytes = total_size
                
                # Ensure output directory exists
                output = Path(output_path)
                output.parent.mkdir(parents=True, exist_ok=True)
                
                # Stream to file
                downloaded = 0
                with open(output, 'wb') as f:
                    async for chunk in response.content.iter_chunked(self._chunk_size):
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress.downloaded_bytes = downloaded
                        
                        if self._on_progress:
                            self._on_progress(progress)
                
                # Complete
                progress.status = "completed"
                progress.completed_at = datetime.now()
                
                download_time = (progress.completed_at - progress.started_at).total_seconds()
                
                result = DownloadResult(
                    success=True,
                    output_path=output_path,
                    file_size=downloaded,
                    download_time=download_time,
                )
                
                if self._on_complete:
                    self._on_complete(result)
                
                return result
                
        except asyncio.TimeoutError:
            progress.status = "failed"
            progress.error = "Download timed out"
            return DownloadResult(success=False, error="Download timed out")
            
        except aiohttp.ClientError as e:
            progress.status = "failed"
            progress.error = str(e)
            return DownloadResult(success=False, error=str(e))
            
        except Exception as e:
            progress.status = "failed"
            progress.error = str(e)
            return DownloadResult(success=False, error=str(e))
            
        finally:
            if url in self._active_downloads:
                del self._active_downloads[url]
    
    async def download_batch(
        self,
        downloads: List[tuple[str, str]],  # [(url, output_path), ...]
        headers: Optional[dict] = None,
    ) -> List[DownloadResult]:
        """Download multiple files in parallel.
        
        Args:
            downloads: List of (url, output_path) tuples
            headers: Optional request headers
        
        Returns:
            List of DownloadResult in same order as input
        """
        tasks = [
            self.download(url, output_path, headers)
            for url, output_path in downloads
        ]
        
        return await asyncio.gather(*tasks)
    
    def get_active_downloads(self) -> List[DownloadProgress]:
        """Get list of active downloads."""
        return list(self._active_downloads.values())
    
    def get_active_count(self) -> int:
        """Get number of active downloads."""
        return len(self._active_downloads)
    
    async def cancel_all(self):
        """Cancel all active downloads."""
        # Close session to cancel in-flight requests
        await self.close()
        self._active_downloads.clear()


# Convenience function
async def download_file(
    url: str,
    output_path: str,
    headers: Optional[dict] = None,
) -> DownloadResult:
    """Download a single file without manager instance."""
    manager = DownloadManager(max_parallel=1)
    try:
        return await manager.download(url, output_path, headers)
    finally:
        await manager.close()
