# 📥 Download Manager & Upscale Flow

**Location**: `03_Backend/DOWNLOAD_MANAGER.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-03

---

## 1. Overview

Download Manager xử lý việc tải video/image từ VEO API và quản lý upscale requests.

---

## 2. Download Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       DOWNLOAD FLOW                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐                                                │
│  │ Generation   │                                                │
│  │ Complete     │                                                │
│  └──────┬───────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐     ┌──────────────┐                          │
│  │ Get Media    │────►│ Check        │                          │
│  │ URLs         │     │ Quality      │                          │
│  └──────────────┘     └──────┬───────┘                          │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │ 720p Ready   │     │ Need 1080p   │     │ Need 4K      │     │
│  │ (Default)    │     │ Upscale      │     │ Upscale      │     │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘     │
│         │                    │                    │             │
│         │                    ▼                    ▼             │
│         │             ┌──────────────┐     ┌──────────────┐     │
│         │             │ Upscale API  │     │ Upscale API  │     │
│         │             │ + Poll       │     │ + Poll       │     │
│         │             └──────┬───────┘     └──────┬───────┘     │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    DOWNLOAD QUEUE                        │    │
│  │  • Parallel downloads (max 3)                            │    │
│  │  • Resume on failure                                     │    │
│  │  • Progress tracking                                     │    │
│  └──────────────────────────────────────────────────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐                                                │
│  │ Save to      │                                                │
│  │ Output Dir   │                                                │
│  └──────────────┘                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Quality Settings

### 3.1 Video Quality Options

| Quality | Resolution | Requires Upscale | API Call |
|---------|------------|------------------|----------|
| **720p** | 1280x720 | ❌ No | Direct download |
| **1080p** | 1920x1080 | ✅ Yes | `CMD_UPSCALE_VIDEO` |
| **4K** | 3840x2160 | ✅ Yes | `CMD_UPSCALE_VIDEO` |

### 3.2 Image Quality Options

| Quality | Resolution | Requires Upscale | API Call |
|---------|------------|------------------|----------|
| **Base** | ~1024px | ❌ No | Direct download |
| **2K** | 2048px | ✅ Yes | `CMD_UPSCALE_IMAGE` |
| **4K** | 4096px | ✅ Yes | `CMD_UPSCALE_IMAGE` |

---

## 4. Implementation

### 4.1 Download Manager Class

```python
import aiohttp
import aiofiles
import asyncio
from pathlib import Path
from typing import Optional, Callable

class DownloadManager:
    """
    Manages video/image downloads with parallel processing.
    """
    
    MAX_PARALLEL_DOWNLOADS = 3
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self._semaphore = asyncio.Semaphore(self.MAX_PARALLEL_DOWNLOADS)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def download(
        self,
        url: str,
        filename: str,
        progress_callback: Callable[[int, int], None] = None
    ) -> str:
        """
        Download file from URL.
        
        Args:
            url: Source URL
            filename: Output filename
            progress_callback: (downloaded_bytes, total_bytes)
            
        Returns:
            Path to downloaded file
        """
        async with self._semaphore:
            output_path = self.output_dir / filename
            
            async with self._get_session().get(url) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                async with aiofiles.open(output_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(self.CHUNK_SIZE):
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback:
                            progress_callback(downloaded, total_size)
            
            return str(output_path)
    
    async def download_batch(
        self,
        items: list[dict],  # [{"url": str, "filename": str}, ...]
        progress_callback: Callable[[int, int, str], None] = None
    ) -> list[str]:
        """
        Download multiple files in parallel.
        """
        tasks = [
            self.download(
                item['url'],
                item['filename'],
                lambda d, t, f=item['filename']: progress_callback(d, t, f)
            )
            for item in items
        ]
        
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        if self._session:
            await self._session.close()
```

### 4.2 Upscale Handler

```python
class UpscaleHandler:
    """
    Handles video/image upscaling before download.
    """
    
    POLL_INTERVAL = 5  # seconds
    MAX_POLL_TIME = 600  # 10 minutes
    
    def __init__(self, api_client, browser_manager):
        self.api = api_client
        self.browser = browser_manager
    
    async def upscale_video(
        self,
        media_id: str,
        target_resolution: str,  # "1080p" or "4K"
        progress_callback: Callable[[str], None] = None
    ) -> str:
        """
        Upscale video to target resolution.
        
        Returns:
            URL of upscaled video
        """
        # Get reCAPTCHA token
        token = await self.browser.get_recaptcha_token()
        
        # Start upscale
        operation_id = await self.api.upscale_video(
            media_id=media_id,
            resolution=target_resolution,
            recaptcha_token=token
        )
        
        # Poll until complete
        start_time = time.time()
        while time.time() - start_time < self.MAX_POLL_TIME:
            status = await self.api.check_status(operation_id)
            
            if status['state'] == 'COMPLETED':
                return status['result']['url']
            elif status['state'] == 'FAILED':
                raise UpscaleError(status.get('error', 'Unknown error'))
            
            if progress_callback:
                progress_callback(status.get('progress', 'Processing...'))
            
            await asyncio.sleep(self.POLL_INTERVAL)
        
        raise TimeoutError("Upscale timed out")
```

---

## 5. Download Progress UI

### 5.1 Status Column Display

| State | Display | Description |
|-------|---------|-------------|
| **Queued** | `⏳ Queue` | Waiting for slot |
| **Upscaling** | `📈 50% Upscaling` | Upscale in progress |
| **Downloading** | `⬇️ 75% (12MB/16MB)` | Download progress |
| **Complete** | `✅ Done` | File ready |
| **Failed** | `❌ Download Failed` | Error occurred |

### 5.2 Output Column Display

```
┌───────────────────────────────────────────────────────────────┐
│ Videos Column (when complete):                                │
│                                                               │
│ 4 outputs:  [▶️] [▶️] [▶️] [▶️]                               │
│             ↑    ↑    ↑    ↑                                 │
│          Click to preview / open file                        │
│                                                               │
│ Or with upscale: [▶️📈] ← 1080p/4K indicator                 │
└───────────────────────────────────────────────────────────────┘
```

---

## 6. Settings (TAB_07)

| Setting | Values | Default | Description |
|---------|--------|---------|-------------|
| `download_quality` | 720p/1080p/4K | 1080p | Target video quality |
| `auto_upscale` | On/Off | Off | Auto-upscale after gen |
| `parallel_downloads` | 1-5 | 3 | Concurrent downloads |
| `output_folder` | Path | ~/VEO_Output | Save location |

---

## Cross-References

- [MULTITHREADING_ARCHITECTURE.md](./MULTITHREADING_ARCHITECTURE.md) - Download threading
- [ERROR_HANDLING_STRATEGY.md](./ERROR_HANDLING_STRATEGY.md) - Download errors
- [TAB_06_QUEUE_MANAGER.md](../01_UI_UX/TAB_06_QUEUE_MANAGER.md) - Download UI
