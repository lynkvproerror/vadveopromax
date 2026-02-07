"""
VEO Pro Max - VEO API Client

Reference: CORE_MODULES_SPEC.md, SEED_MANAGEMENT.md, BROWSER_HEADERS.md
All VEO API endpoints for video/image generation
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import aiohttp
import asyncio
import json
import base64
import sys
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import APIEndpoints, WorkflowType, AspectRatio


# === SEED CONSTANTS ===
SEED_MIN = 0
SEED_MAX = 32767


def generate_random_seed() -> int:
    """Generate a random seed in valid range (0-32767)."""
    return random.randint(SEED_MIN, SEED_MAX)


def validate_seed(seed: int) -> int:
    """Validate and clamp seed to valid range."""
    if not isinstance(seed, int):
        raise ValueError("Seed must be an integer")
    return max(SEED_MIN, min(SEED_MAX, seed))


# === BROWSER HEADERS ===
class BrowserHeaders:
    """Browser fingerprint headers required for VEO API.
    
    Reference: BROWSER_HEADERS.md
    All x-browser-* headers are MANDATORY to avoid 403 Forbidden.
    """
    
    # Static headers (hardcoded)
    STATIC = {
        "x-browser-channel": "stable",
        "x-browser-copyright": "Copyright 2026 Google LLC. All Rights reserved.",
        "x-browser-year": "2026"
    }
    
    def __init__(self):
        self._validation: Optional[str] = None
        self._client_data: Optional[str] = None
    
    def set_dynamic_headers(self, validation: str, client_data: str = None):
        """Set dynamic headers from HAR extraction or Playwright capture."""
        self._validation = validation
        self._client_data = client_data
    
    def get_all_headers(self) -> Dict[str, str]:
        """Return complete headers dict for API requests."""
        headers = self.STATIC.copy()
        if self._validation:
            headers["x-browser-validation"] = self._validation
        if self._client_data:
            headers["x-client-data"] = self._client_data
        return headers
    
    def extract_from_har(self, har_path: str) -> bool:
        """Extract dynamic headers from HAR file."""
        try:
            with open(har_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for entry in data.get('log', {}).get('entries', []):
                req = entry.get('request', {})
                if 'googleapis.com' not in req.get('url', ''):
                    continue
                
                for h in req.get('headers', []):
                    name = h['name'].lower()
                    if name == 'x-browser-validation':
                        self._validation = h['value']
                    elif name == 'x-client-data':
                        self._client_data = h['value']
                
                if self._validation:
                    return True
            
            return False
        except Exception:
            return False


@dataclass
class APIResponse:
    """Standard API response wrapper."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    response_code: int = 0


class VEOApiClient:
    """VEO API client for all generation endpoints.
    
    All methods require:
    - access_token: Bearer token from Google auth
    - recaptcha_token: reCAPTCHA v3 token
    - x-browser headers (via BrowserHeaders)
    
    Reference: CORE_MODULES_SPEC.md, SEED_MANAGEMENT.md
    """
    
    def __init__(self, base_url: str = APIEndpoints.BASE_URL):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._browser_headers = BrowserHeaders()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def set_browser_headers(self, validation: str, client_data: str = None):
        """Set dynamic browser headers for API requests.
        
        Args:
            validation: x-browser-validation token (CRITICAL)
            client_data: x-client-data token (optional)
        """
        self._browser_headers.set_dynamic_headers(validation, client_data)
    
    def load_headers_from_har(self, har_path: str) -> bool:
        """Load browser headers from HAR file."""
        return self._browser_headers.extract_from_har(har_path)
    
    def set_headers_from_extractor(self, tokens: 'ExtractedTokens'):
        """
        Set browser headers from TokenExtractor result.
        
        Args:
            tokens: ExtractedTokens from token_extractor.extract_tokens()
            
        Example:
            tokens = await extract_tokens(profile_path)
            client.set_headers_from_extractor(tokens)
        """
        self._browser_headers.set_dynamic_headers(
            validation=tokens.browser_validation,
            client_data=tokens.client_data,
        )

    def _build_headers(
        self,
        access_token: str,
        recaptcha_token: str,
        extra_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build request headers including x-browser-* headers."""
        # Core headers
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-goog-recaptcha-token": recaptcha_token,
        }
        # Add x-browser-* headers (MANDATORY)
        headers.update(self._browser_headers.get_all_headers())
        # Add extra headers if any
        if extra_headers:
            headers.update(extra_headers)
        return headers
    
    def _build_client_context(self, recaptcha_token: str) -> Dict[str, Any]:
        """Build clientContext for API requests."""
        return {
            "tool": "VEGA_WEB",
            "recaptchaToken": recaptcha_token,
        }
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        recaptcha_token: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> APIResponse:
        """Make an API request."""
        url = f"{self.base_url}{endpoint}"
        headers = self._build_headers(access_token, recaptcha_token)
        
        try:
            session = await self._get_session()
            
            async with session.request(method, url, headers=headers, json=data) as resp:
                response_code = resp.status
                response_text = await resp.text()
                
                if response_code == 200:
                    try:
                        response_data = json.loads(response_text)
                        return APIResponse(success=True, data=response_data, response_code=response_code)
                    except json.JSONDecodeError:
                        return APIResponse(success=True, data={"raw": response_text}, response_code=response_code)
                else:
                    return APIResponse(
                        success=False,
                        error=f"HTTP {response_code}: {response_text[:500]}",
                        response_code=response_code
                    )
        except aiohttp.ClientError as e:
            return APIResponse(success=False, error=f"Request failed: {str(e)}")
        except Exception as e:
            return APIResponse(success=False, error=f"Unexpected error: {str(e)}")
    
    # ==================== IMAGE UPLOAD ====================
    
    async def upload_image(
        self,
        access_token: str,
        recaptcha_token: str,
        image_base64: str,
        mime_type: str = "image/jpeg",
    ) -> APIResponse:
        """Upload image to VEO.
        
        Endpoint: /v1:uploadUserImage (Sync)
        
        Returns: {"imageId": "...", "imageUri": "..."}
        """
        data = {
            "imageBytes": image_base64,
            "mimeType": mime_type,
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.UPLOAD,
            access_token,
            recaptcha_token,
            data
        )
    
    # ==================== VIDEO GENERATION ====================
    
    async def generate_video_t2v(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        duration_seconds: int = 8,
        model: str = "veo_3_1_t2v_fast_landscape_ultra",
        output_count: int = 4,
        seed: Optional[int] = None,
    ) -> APIResponse:
        """Text to Video generation.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoText (Async)
        
        Reference: SEED_MANAGEMENT.md - seed is required, range 0-32767
        """
        # Generate seed if not provided
        actual_seed = seed if seed is not None else generate_random_seed()
        
        data = {
            "requests": [{
                "textInput": {"prompt": prompt},
                "aspectRatio": aspect_ratio,
                "durationSeconds": duration_seconds,
                "videoModelKey": model,
                "numberOfVideos": output_count,
                "seed": validate_seed(actual_seed),
            }],
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.T2V,
            access_token,
            recaptcha_token,
            data
        )
    
    async def generate_video_i2v_single(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        image_uri: str,
        frame_position: str = "START",  # START or END
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        duration_seconds: int = 8,
        model: str = "veo_3_1_i2v_s_fast_ultra",
        output_count: int = 4,
        seed: Optional[int] = None,
    ) -> APIResponse:
        """Image to Video with single frame.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoStartImage (Async)
        
        Reference: SEED_MANAGEMENT.md - seed is required
        """
        actual_seed = seed if seed is not None else generate_random_seed()
        
        data = {
            "requests": [{
                "textInput": {"prompt": prompt},
                "imageInputMediaId": image_uri,
                "framePosition": frame_position,
                "aspectRatio": aspect_ratio,
                "durationSeconds": duration_seconds,
                "videoModelKey": model,
                "numberOfVideos": output_count,
                "seed": validate_seed(actual_seed),
            }],
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        endpoint = APIEndpoints.I2V_SINGLE
        
        return await self._request(
            "POST",
            endpoint,
            access_token,
            recaptcha_token,
            data
        )
    
    async def generate_video_i2v_dual(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        start_image_uri: str,
        end_image_uri: str,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        duration_seconds: int = 8,
        model: str = "veo_3_1_i2v_s_fast_fl_ultra",
        output_count: int = 4,
        seed: Optional[int] = None,
    ) -> APIResponse:
        """Image to Video with start and end frames.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoStartAndEndImage (Async)
        
        Reference: SEED_MANAGEMENT.md - seed is required
        Note: _fl_ = First+Last frame support
        """
        actual_seed = seed if seed is not None else generate_random_seed()
        
        data = {
            "requests": [{
                "textInput": {"prompt": prompt},
                "startImageId": start_image_uri,
                "endImageId": end_image_uri,
                "aspectRatio": aspect_ratio,
                "durationSeconds": duration_seconds,
                "videoModelKey": model,
                "numberOfVideos": output_count,
                "seed": validate_seed(actual_seed),
            }],
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.I2V_DUAL,
            access_token,
            recaptcha_token,
            data
        )
    
    async def generate_video_r2v(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        reference_image_uris: List[str],  # 1-3 images
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        duration_seconds: int = 8,
        model: str = "veo_3_1_r2v_fast_landscape_ultra",
        output_count: int = 4,
        seed: Optional[int] = None,
    ) -> APIResponse:
        """References/Ingredients to Video.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoReferenceImages (Async)
        
        Reference: SEED_MANAGEMENT.md - seed is required
        """
        actual_seed = seed if seed is not None else generate_random_seed()
        
        data = {
            "requests": [{
                "textInput": {"prompt": prompt},
                "referenceImageIds": reference_image_uris[:3],  # Max 3
                "aspectRatio": aspect_ratio,
                "durationSeconds": duration_seconds,
                "videoModelKey": model,
                "numberOfVideos": output_count,
                "seed": validate_seed(actual_seed),
            }],
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.R2V,
            access_token,
            recaptcha_token,
            data
        )
    
    # ==================== IMAGE GENERATION ====================
    
    async def generate_image(
        self,
        access_token: str,
        recaptcha_token: str,
        project_id: str,
        prompt: str,
        aspect_ratio: str = "LANDSCAPE",
        output_count: int = 4,
    ) -> APIResponse:
        """Text to Image generation.
        
        Endpoint: /v1/projects/{id}/flowMedia:batchGenerateImages (Sync)
        """
        endpoint = f"/v1/projects/{project_id}/flowMedia:batchGenerateImages"
        
        data = {
            "requests": [{
                "prompt": prompt,
                "aspectRatio": aspect_ratio,
                "numberOfImages": output_count,
            }],
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            endpoint,
            access_token,
            recaptcha_token,
            data
        )
    
    # ==================== STATUS CHECKING ====================
    
    async def check_status(
        self,
        access_token: str,
        recaptcha_token: str,
        operation_names: List[str],
    ) -> APIResponse:
        """Check status of async operations.
        
        Endpoint: /v1/video:batchCheckAsyncVideoGenerationStatus
        """
        data = {
            "operationNames": operation_names,
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.STATUS,
            access_token,
            recaptcha_token,
            data
        )
    
    # ==================== UPSCALE ====================
    
    async def upscale_video(
        self,
        access_token: str,
        recaptcha_token: str,
        video_uri: str,
        target_resolution: str = "VIDEO_RESOLUTION_1080P",
    ) -> APIResponse:
        """Upscale video resolution.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoUpsampleVideo (Async)
        
        Resolution options:
        - VIDEO_RESOLUTION_1080P
        - VIDEO_RESOLUTION_4K
        """
        data = {
            "requests": [{
                "videoInput": {"mediaId": video_uri},
                "resolution": target_resolution,
            }],
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.UPSCALE_VIDEO,
            access_token,
            recaptcha_token,
            data
        )
    
    # ==================== UTILITY ENDPOINTS (from HAR analysis) ====================
    
    async def get_credits(
        self,
        access_token: str,
        recaptcha_token: str,
    ) -> APIResponse:
        """Check account credits and subscription status.
        
        Endpoint: /v1/credits (GET)
        
        Returns: {"credits": {"available": 100, "used": 50}, "subscription": {...}}
        """
        return await self._request(
            "GET",
            APIEndpoints.CREDITS,
            access_token,
            recaptcha_token,
        )
    
    async def generate_gif(
        self,
        access_token: str,
        recaptcha_token: str,
        media_generation_id: str,
    ) -> APIResponse:
        """Generate preview GIF for a video.
        
        Endpoint: /v1/video:generatePinholeGif (Sync)
        
        Returns: {"pinholeGif": "base64_string..."} - Note: Can be >10MB
        """
        data = {
            "mediaGenerationId": media_generation_id,
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.GIF,
            access_token,
            recaptcha_token,
            data
        )
    
    async def check_app_status(
        self,
        access_token: str,
        recaptcha_token: str,
    ) -> APIResponse:
        """Check if VEO API is available.
        
        Endpoint: /v1:checkAppAvailability (POST)
        
        Use for health check before starting batch operations.
        """
        return await self._request(
            "POST",
            APIEndpoints.APP_STATUS,
            access_token,
            recaptcha_token,
            {},
        )
    
    async def upscale_image(
        self,
        access_token: str,
        recaptcha_token: str,
        media_generation_id: str,
        target_resolution: str = "IMAGE_RESOLUTION_4K",
    ) -> APIResponse:
        """Upscale image resolution.
        
        Endpoint: /v1/flow/upsampleImage (POST)
        
        Resolution options:
        - IMAGE_RESOLUTION_2K
        - IMAGE_RESOLUTION_4K
        """
        data = {
            "mediaGenerationId": media_generation_id,
            "targetResolution": target_resolution,
            "clientContext": self._build_client_context(recaptcha_token),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.IMAGE_UPSCALE_FLOW,
            access_token,
            recaptcha_token,
            data
        )
