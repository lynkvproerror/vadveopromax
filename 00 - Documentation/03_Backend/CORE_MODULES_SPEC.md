# VEO Pro Max - Core Modules Specification

**Scope**: Pure API modules replacing Playwright-based browser.py

---

## Module Overview

| Module | Purpose | Lines (Est.) |
|--------|---------|--------------|
| `api_client.py` | HTTP API wrapper for all VEO endpoints | ~600 |
| `auth_manager.py` | Token storage, validation, refresh | ~220 |
| `token_extractor.py` | Unified token extraction from headless browser | ~375 |
| `media_handler.py` | Image/video processing utilities | ~80 |
| `queue_manager.py` | Task queue (reused from original) | 86 |

---

## 1. api_client.py

### Class: VEOApiClient

```python
class VEOApiClient:
    """Pure HTTP client for VEO API - replaces Playwright browser.py"""
    
    BASE_URL = "https://aisandbox-pa.googleapis.com"
    
    def __init__(self, project_id: str, auth_manager: AuthManager):
        self.project_id = project_id
        self.auth_manager = auth_manager
        self.session = requests.Session()
    
    def _build_standard_headers(self) -> dict:
        """Build complete headers including auth and browser fingerprint"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_manager.get_bearer_token()}"
        }
        # Add x-browser-* headers
        headers.update(self.auth_manager.get_x_browser_headers())
        return headers
    
    def _get_client_context(self, recaptcha_token: str = None, tool: str = "PINHOLE") -> dict:
        """Build clientContext object for API requests"""
        context = {
            "sessionId": f";{int(time.time() * 1000)}",
            "projectId": self.project_id,
            "tool": tool
        }
        if recaptcha_token:
            context["recaptchaContext"] = {
                "token": recaptcha_token,
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
            }
        return context
    
    def _generate_scene_id(self) -> str:
        """Generate UUID for scene tracking"""
        return str(uuid.uuid4())
```

### Public Methods

| Method | Endpoint | Sync/Async | Returns |
|--------|----------|------------|---------|
| `upload_image()` | `/v1:uploadUserImage` | Sync | `mediaId` |
| `generate_video_t2v()` | `/v1/video:batchAsyncGenerateVideoText` | Async | `operation_id` |
| `generate_video_i2v_single()` | `/v1/video:batchAsyncGenerateVideoStartImage` | Async | `operation_id` |
| `generate_video_i2v_dual()` | `/v1/video:batchAsyncGenerateVideoStartAndEndImage` | Async | `operation_id` |
| `generate_video_r2v()` | `/v1/video:batchAsyncGenerateVideoReferenceImages` | Async | `operation_id` |
| `generate_image()` | `/v1/projects/{id}/flowMedia:batchGenerateImages` | **Sync** | `[urls]` |
| `upscale_video()` | `/v1/video:batchAsyncGenerateVideoUpsampleVideo` | Async | `operation_id` |
| `upscale_image()` | `/v1/flow/upsampleImage` | Async | `job_id` |
| `check_status()` | `/v1/video:batchCheckAsyncVideoGenerationStatus` | Sync | `status_dict` |
| `download_media()` | Direct URL | Sync | `bool` |

### Method Signatures

```python
def __init__(self, project_id: str, auth_manager: AuthManager):
    """
    Initialize API client.
    
    Args:
        project_id: VEO project UUID
        auth_manager: AuthManager instance for token handling
    """
    
def upload_image(
    self, 
    image_bytes: bytes, 
    aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE"
) -> str:
    """
    Upload image for I2V/R2V workflows.
    
    Returns:
        mediaId (Base64 encoded identifier)
    """

def generate_video_t2v(
    self,
    prompt: str,
    model: str = "veo_3_1_t2v_fast_landscape_ultra",
    aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
    count: int = 4,
    seed: int = None  # 0-32767, auto-generate if None
) -> list:
    """
    Text-to-Video generation.
    
    Reference: SEED_MANAGEMENT.md - seed is REQUIRED (0-32767)
    Reference: BROWSER_HEADERS.md - x-browser-* headers are MANDATORY
    
    Payload Example:
    ```json
    {
        "clientContext": {
            "tool": "VEGA_WEB",
            "recaptchaToken": "..."
        },
        "requests": [{
            "textInput": {"prompt": "..."},
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "durationSeconds": 8,
            "videoModelKey": "veo_3_1_t2v_fast_landscape_ultra",
            "numberOfVideos": 4,
            "seed": 25325
        }]
    }
    ```
    
    Headers Required:
    - Authorization: Bearer {access_token}
    - x-browser-validation: {hash}
    - x-browser-channel: stable
    - x-browser-year: 2026
    - x-browser-copyright: Copyright 2026 Google LLC...
    """

    - generate_video_image(prompt, image_id, is_end_frame=False, recaptcha_token=None):
        """
        Handles both Single Frame (I2V) and Start/End Frame (F2V).
        Requires recaptcha_token and x-browser-* headers.
        
        Payload uses `imageInputMediaId` for single frame,
        `startImageId` + `endImageId` for dual frame.
        """

    - upscale_video(media_id, resolution, recaptcha_token):
        """
        Payload:
        {
            "clientContext": _get_client_context(recaptcha_token),
            "requests": [{
                "videoInput": {"mediaId": ...},
                "resolution": "VIDEO_RESOLUTION_1080P" | "VIDEO_RESOLUTION_4K"
            }]
        }
        """

    - check_status(operation_name):
        "Returns status enum"

    - get_media_download_url(media_id):
        """
        Uses GET /v1/media/{media_id}?key={api_key}

        Returns: Direct download URL (or streams content)
        """

    - _get_client_context(recaptcha_token):
        """
        Returns:
        {
            "tool": "PINHOLE",
            "recaptchaContext": {"token": recaptcha_token}
        }
        """
    """

def generate_video_r2v(
    self,
    media_ids: list,
    prompt: str,
    model: str = "veo_3_1_r2v_fast_landscape_ultra",
    count: int = 4
) -> list:
    """
    Reference-to-Video (Ingredients) generation.
    
    Args:
        media_ids: 1-3 uploaded image mediaIds
    """

def check_status(
    self,
    operation_id: str,
    scene_id: str
) -> dict:
    """
    Poll generation status.
    
    Returns:
        {
            "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
            "video_url": "https://...",
            "remaining_credits": 43890
        }
    """

def wait_for_completion(
    self,
    operation_id: str,
    scene_id: str,
    max_attempts: int = 60,
    interval: int = 5
) -> dict:
    """
    Poll until completion or timeout.
    """
```

### Error Handling

```python
class VEOApiError(Exception):
    """Base exception for VEO API errors."""
    
class AuthenticationError(VEOApiError):
    """401 - Token expired or invalid."""
    
class RateLimitError(VEOApiError):
    """429 - Too many requests."""
    
class ContentPolicyError(VEOApiError):
    """403 - Content policy violation."""
```

---

## 2. auth_manager.py

### Class: AuthManager

```python
class AuthManager:
    """
    Token management with dual input methods:
    - A) Manual paste from DevTools
    - B) Playwright auto-extraction
    """
```

> [!NOTE]
> ### Phân Vai AuthManager vs AccountManager (CHỦ)
> 
> | Trách nhiệm | `AuthManager` | `AccountManager` (CHỦ) |
> |-------------|---------------|------------------------|
> | Trích xuất token từ browser | ✅ Thực thi | ❌ |
> | Lưu/load token từ file | ✅ | ❌ |
> | Quyết định khi nào refresh | ❌ | ✅ (gọi callback) |
> | Quản lý reCAPTCHA | ✅ Thực thi | ❌ |
> | Semaphore 4 slot | ❌ | ✅ |
> | Project ID cache | ❌ | ✅ |
> 
> **AuthManager** = thợ lấy chìa khóa | **AccountManager** = chủ nhà quyết định khi nào cần chìa mới

### Public Methods

| Method | Purpose |
|--------|---------|
| `get_token()` | Return current valid token |
| `set_token()` | Store token manually (Method A) |
| `extract_token_playwright()` | Auto-extract via Playwright (Method B) |
| `is_expired()` | Check token validity |
| `get_headers()` | Return auth headers dict |
| `refresh_token()` | Re-extract if expired (Method B) |

### Implementation Notes

```python
from dataclasses import dataclass
from pathlib import Path
import json
import time

@dataclass
class TokenData:
    token: str
    expires_at: float
    project_id: str
    extraction_method: str  # "manual" or "playwright"

class AuthManager:
    # Updated 2026-02-07: Storage path changed to ~/.veoauto/sessions/
    TOKEN_FILE = Path("~/.veoauto/sessions").expanduser()
    
    def __init__(self):
        self._token_data: TokenData = None
        self._api_key: str = None  # For GET /media requests
        self._recaptcha_token: str = None  # For video generation requests
        self._load_from_file()
    
    def get_bearer_token(self) -> str:
        if self.is_expired():
            raise AuthenticationError("Token expired")
        return self._token_data.token
    
    def get_api_key(self) -> str:
        return self._api_key

    def get_recaptcha_token(self) -> str:
        return self._recaptcha_token

    def update_recaptcha_token(self, new_token: str):
        self._recaptcha_token = new_token
    
    def set_token(self, token: str, project_id: str, api_key: str, expires_in: int = 3600):
        """Method A: Manual token input."""
        self._token_data = TokenData(
            token=token,
            expires_at=time.time() + expires_in,
            project_id=project_id,
            extraction_method="manual"
        )
        self._save_to_file()
    
    def extract_token_playwright(self, profile_path: str = None) -> str:
        """
        Method B: Auto-extract using Playwright.
        
        1. Launch browser with profile
        2. Navigate to labs.google.com/flow
        3. Extract Bearer token from network requests
        4. Store and return token
        """
        # Implementation uses Playwright's network interception
        pass
    
    def get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_token()}"}
    
    def is_expired(self) -> bool:
        if not self._token_data:
            return True
        return time.time() > self._token_data.expires_at - 60  # 1 min buffer
```

### Playwright Token Extraction (Method B)

```python
async def _extract_token_async(self, profile_path: str = None):
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            channel="chrome",  # Use real Chrome (Updated 2026-02-07)
            headless=False  # For login; True for refresh
        
        page = await browser.new_page()
        
        # Intercept API requests to capture token
        token = None
        
        async def capture_request(request):
            nonlocal token
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")
        
        page.on("request", capture_request)
        
        await page.goto("https://labs.google.com/flow")
        await page.wait_for_timeout(5000)  # Wait for API calls
        
        await browser.close()
        return token
```

---

## 3. media_handler.py

### Class: MediaHandler

```python
class MediaHandler:
    """Image/video processing utilities."""
```

### Static Methods

| Method | Purpose |
|--------|---------|
| `image_to_base64()` | Convert image file to Base64 JPEG |
| `detect_aspect_ratio()` | Determine image aspect ratio enum |
| `download_file()` | Download media from URL |
| `save_base64_image()` | Decode and save Base64 image |

### Implementation

```python
import base64
from pathlib import Path
from PIL import Image
import io
import requests

class MediaHandler:
    
    @staticmethod
    def image_to_base64(image_path: str) -> str:
        """
        Convert image to Base64 JPEG string.
        
        VEO requires:
        - JPEG format
        - Base64 encoded (starts with /9j/)
        """
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=95)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    @staticmethod
    def detect_aspect_ratio(image_path: str) -> str:
        """
        Detect aspect ratio and return VEO enum.
        
        Returns:
            IMAGE_ASPECT_RATIO_LANDSCAPE | PORTRAIT | SQUARE
        """
        with Image.open(image_path) as img:
            w, h = img.size
            ratio = w / h
            
            if ratio > 1.2:
                return "IMAGE_ASPECT_RATIO_LANDSCAPE"
            elif ratio < 0.8:
                return "IMAGE_ASPECT_RATIO_PORTRAIT"
            else:
                return "IMAGE_ASPECT_RATIO_SQUARE"
    
    @staticmethod
    def download_file(url: str, output_path: str, headers: dict = None) -> bool:
        """
        Download media file from URL.
        
        Args:
            url: Signed URL from VEO
            output_path: Local save path
            headers: Optional headers (for x-browser-* requirements)
        """
        try:
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"Download failed: {e}")
            return False
    
    @staticmethod
    def save_base64_image(base64_data: str, output_path: str) -> bool:
        """
        Decode Base64 and save as image file.
        
        Used for: Image generation responses, upscaled images
        """
        try:
            image_data = base64.b64decode(base64_data)
            with open(output_path, 'wb') as f:
                f.write(image_data)
            return True
        except Exception:
            return False
```

---

## 4. queue_manager.py

**Status**: ✅ Reuse directly from original project

**Source**: `PythonCustomTkinterSelemiumJavaScript/core/queue_manager.py`

**Changes Required**: None (pure Python, no Playwright dependencies)

---

## Dependencies

```
# requirements.txt
requests>=2.31.0
Pillow>=10.0.0
playwright>=1.40.0  # For Method B token extraction
```

---

## API Mapping Reference

| Documentation Guide | API Client Method |
|---------------------|-------------------|
| 02_TEXT_TO_VIDEO.md | `generate_video_t2v()` |
| 03_IMAGE_TO_VIDEO.md | `generate_video_i2v_single()`, `generate_video_i2v_dual()` |
| 04_INGREDIENTS_TO_VIDEO.md | `generate_video_r2v()` |
| 05_VIDEO_UPSCALING.md | `upscale_video()` |
| 06_IMAGE_GENERATION.md | `generate_image()` |
| 07_IMAGE_UPSCALING.md | `upscale_image()` |

---

**Last Updated**: 2026-02-07
