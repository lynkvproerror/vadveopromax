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
SEED_MAX = 9999  # n8n uses Math.floor(Math.random() * 10000) → 0-9999


def generate_random_seed() -> int:
    """Generate a random seed in valid range (0-9999, per n8n reference)."""
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
    
    Auth per VEO_Web_Client_Protocol_Analysis.md:
    - x-browser-* headers (via BrowserHeaders) — MANDATORY for all REST
    - reCAPTCHA token in body clientContext (for generation only)
    - Authorization: Bearer {access_token} — REQUIRED for all REST endpoints
    
    Reference: CORE_MODULES_SPEC.md, SEED_MANAGEMENT.md
    """
    
    def __init__(self, base_url: str = APIEndpoints.BASE_URL):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._browser_headers = BrowserHeaders()
        self._call_count = 0  # Track total API calls for performance panel
    
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
        access_token: str = "",
        extra_headers: Optional[Dict[str, str]] = None,
        account_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Build request headers for aisandbox-pa REST endpoints.
        
        Per n8n reference workflow:
        - Content-Type: application/json
        - Origin + Referer required for CORS
        - Authorization: raw token (NO Bearer prefix) for generate calls
        - x-browser-* headers included for fingerprinting
        
        Args:
            access_token: OAuth2 access token. Sent as raw token.
            extra_headers: Additional headers to merge.
            account_headers: Per-account x-browser-* headers dict.
        """
        headers = {
            "Content-Type": "application/json",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
        }
        # Authorization: Bearer token — required by Google aisandbox-pa API
        # (n8n uses a proxy that handles auth differently, we call Google directly)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        # Add x-browser-* headers (layered: static → global dynamic → per-account)
        # 1. Always include static headers (channel, year, copyright)
        headers.update(BrowserHeaders.STATIC)
        # 2. Overlay dynamic headers from global singleton (validation, client_data)
        global_headers = self._browser_headers.get_all_headers()
        for k, v in global_headers.items():
            if k not in BrowserHeaders.STATIC and v:  # only dynamic parts
                headers[k] = v
        # 3. Per-account headers from extension bridge — highest priority
        if account_headers:
            headers.update(account_headers)
        # Add extra headers if any
        if extra_headers:
            headers.update(extra_headers)
        return headers
    
    def _build_client_context(
        self,
        recaptcha_token: str,
        project_id: str = "",
        paygate_tier: str = "PAYGATE_TIER_TWO",
        tool: str = "PINHOLE",
        include_recaptcha: bool = True,
    ) -> Dict[str, Any]:
        """Build clientContext for API requests.
        
        Per HAR analysis (verified ground truth):
        - tool: "PINHOLE" for video/image, "ASSET_MANAGER" for uploads
        - sessionId: ";{timestamp_ms}"
        - projectId: UUID
        - userPaygateTier: account tier
        - recaptchaContext: REQUIRED for all generation calls (HAR verified)
        """
        import time
        import uuid as _uuid
        ctx: Dict[str, Any] = {
            "sessionId": f";{int(time.time() * 1000)}",
            "tool": tool,
        }
        # projectId: always included (n8n always sends it)
        # Fallback to generated UUID if not provided
        ctx["projectId"] = project_id if project_id else str(_uuid.uuid4())
        if paygate_tier:
            ctx["userPaygateTier"] = paygate_tier
        if include_recaptcha and recaptcha_token:
            # HAR verified: recaptchaContext requires both token AND applicationType
            ctx["recaptchaContext"] = {
                "token": recaptcha_token,
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
            }
        return ctx
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        access_token: str = "",
        recaptcha_token: str = "",
        data: Optional[Dict[str, Any]] = None,
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Make an API request.
        
        Args:
            access_token: OAuth2 token, sent as Authorization: Bearer header.
            recaptcha_token: Goes in body clientContext, not headers.
            account_headers: Per-account x-browser-* headers dict.
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._build_headers(access_token=access_token, account_headers=account_headers)
        
        try:
            session = await self._get_session()
            
            # DEBUG: dump request details for 403 diagnosis
            import logging
            _log = logging.getLogger(__name__)
            _log.debug(f"[API REQUEST] {method} {url}")
            _log.debug(f"[API HEADERS] {json.dumps(dict(headers), indent=2, ensure_ascii=False)}")
            if data:
                # Show clientContext structure (mask token)
                ctx = data.get("clientContext", {})
                rc = ctx.get("recaptchaContext", {})
                _log.debug(f"[API BODY] clientContext keys: {list(ctx.keys())}")
                if rc:
                    _log.debug(f"[API BODY] recaptchaContext: token={len(rc.get('token',''))}chars, applicationType={rc.get('applicationType','MISSING')}")
                _log.debug(f"[API BODY] top-level keys: {list(data.keys())}")
                # Full body dump (mask long tokens for readability)
                import copy
                dump = copy.deepcopy(data)
                if "clientContext" in dump and "recaptchaContext" in dump["clientContext"]:
                    t = dump["clientContext"]["recaptchaContext"].get("token", "")
                    dump["clientContext"]["recaptchaContext"]["token"] = f"<{len(t)}chars>"
                _log.debug(f"[API BODY FULL] {json.dumps(dump, indent=2, default=str, ensure_ascii=False)}")
            
            async with session.request(method, url, headers=headers, json=data) as resp:
                self._call_count += 1
                response_code = resp.status
                response_text = await resp.text()
                
                if response_code == 200:
                    try:
                        response_data = json.loads(response_text)
                        _log.info(f"[API RESPONSE] {response_code} keys={list(response_data.keys())}")
                        # Dump operations structure for debugging poll issue
                        if "operations" in response_data:
                            ops = response_data["operations"]
                            _log.info(f"[API RESPONSE] operations count={len(ops)}")
                            if ops:
                                first_op = ops[0]
                                _log.info(f"[API RESPONSE] ops[0] keys={list(first_op.keys())}")
                                _log.info(f"[API RESPONSE] ops[0] = {json.dumps(first_op, default=str, ensure_ascii=False)}")
                        return APIResponse(success=True, data=response_data, response_code=response_code)
                    except json.JSONDecodeError:
                        _log.warning(f"[API RESPONSE] {response_code} JSON decode failed, raw={response_text}")
                        return APIResponse(success=True, data={"raw": response_text}, response_code=response_code)
                else:
                    return APIResponse(
                        success=False,
                        error=f"HTTP {response_code}: {response_text}",
                        response_code=response_code
                    )
        except aiohttp.ClientError as e:
            return APIResponse(success=False, error=f"Request failed: {str(e)}")
        except Exception as e:
            return APIResponse(success=False, error=f"Unexpected error: {str(e)}")
    
    # ==================== IMAGE UPLOAD ====================
    # NOTE: upload_image() is defined in the UTILITY ENDPOINTS section (line ~859).
    # There was previously a duplicate here with incorrect fields (aspectRatio in
    # imageInput, missing paygate_tier=""). Removed per HAR analysis — the version
    # below is the canonical one matching HAR ground truth.
    
    # ==================== VIDEO GENERATION ====================
    
    async def generate_video_t2v(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        project_id: str = "",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        model: str = "veo_3_1_t2v_fast_ultra",
        output_count: int = 4,
        seed: Optional[int] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Text to Video generation.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoText (Async)
        HAR verified (Text to video 1.har): T2V sends 1 request item,
        server generates multiple outputs from that single item.
        
        Reference: SEED_MANAGEMENT.md - seed is required, range 0-32767
        """
        import uuid
        
        # Each output requires its own request item with unique seed + sceneId
        # (same pattern as I2V, R2V)
        requests_list = []
        for idx in range(min(output_count, 4)):
            if seed is not None:
                actual_seed = seed + idx  # Deterministic but unique per output
            else:
                actual_seed = generate_random_seed()
            requests_list.append({
                "aspectRatio": aspect_ratio,
                "seed": validate_seed(actual_seed),
                "textInput": {"prompt": prompt},
                "videoModelKey": model,
                "metadata": {"sceneId": str(uuid.uuid4())},
            })
        
        data = {
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
        }
        
        return await self._request(
            "POST",
            APIEndpoints.T2V,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    async def generate_video_i2v_single(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        image_media_id: str,
        project_id: str = "",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        model: str = "veo_3_1_i2v_s_fast_ultra_relaxed",
        output_count: int = 4,
        seed: Optional[int] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Image to Video with single start frame.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoStartImage (Async)
        HAR verified: uses startImage.mediaId (nested object)
        """
        import uuid
        
        requests_list = []
        for idx in range(min(output_count, 4)):
            # Bug 5 fix: When user provides a fixed seed, vary it per output
            # to avoid generating identical videos
            if seed is not None:
                actual_seed = seed + idx  # Deterministic but unique per output
            else:
                actual_seed = generate_random_seed()
            requests_list.append({
                "aspectRatio": aspect_ratio,
                "seed": validate_seed(actual_seed),
                "textInput": {"prompt": prompt},
                "videoModelKey": model,
                "startImage": {"mediaId": image_media_id},
                "metadata": {"sceneId": str(uuid.uuid4())},
            })
        
        data = {
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
        }
        
        return await self._request(
            "POST",
            APIEndpoints.I2V_SINGLE,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    async def generate_video_i2v_dual(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        start_image_media_id: str,
        end_image_media_id: str,
        project_id: str = "",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        model: str = "veo_3_1_i2v_s_fast_fl_ultra_relaxed",
        output_count: int = 4,
        seed: Optional[int] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Image to Video with start and end frames (F2V).
        
        Endpoint: /v1/video:batchAsyncGenerateVideoStartAndEndImage (Async)
        HAR verified: uses startImage.mediaId + endImage.mediaId (nested objects)
        Note: _fl_ = First+Last frame support
        """
        import uuid
        
        requests_list = []
        for idx in range(min(output_count, 4)):
            # Bug 5 fix: When user provides a fixed seed, vary it per output
            if seed is not None:
                actual_seed = seed + idx
            else:
                actual_seed = generate_random_seed()
            requests_list.append({
                "aspectRatio": aspect_ratio,
                "seed": validate_seed(actual_seed),
                "textInput": {"prompt": prompt},
                "videoModelKey": model,
                "startImage": {"mediaId": start_image_media_id},
                "endImage": {"mediaId": end_image_media_id},
                "metadata": {"sceneId": str(uuid.uuid4())},
            })
        
        data = {
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
        }
        
        return await self._request(
            "POST",
            APIEndpoints.I2V_DUAL,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    async def generate_video_r2v(
        self,
        access_token: str,
        recaptcha_token: str,
        prompt: str,
        reference_image_media_ids: List[str],  # 1-3 mediaIds
        project_id: str = "",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        model: str = "veo_3_1_r2v_fast_landscape_ultra_relaxed",
        output_count: int = 4,
        seed: Optional[int] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """References/Ingredients to Video.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoReferenceImages (Async)
        HAR verified: uses referenceImages[] array of objects with imageUsageType + mediaId
        """
        import uuid
        
        # Build referenceImages as array of objects (HAR verified)
        ref_images = [
            {"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": mid}
            for mid in reference_image_media_ids[:3]
        ]
        
        requests_list = []
        for idx in range(min(output_count, 4)):
            # Bug 5 fix: When user provides a fixed seed, vary it per output
            if seed is not None:
                actual_seed = seed + idx
            else:
                actual_seed = generate_random_seed()
            requests_list.append({
                "aspectRatio": aspect_ratio,
                "seed": validate_seed(actual_seed),
                "textInput": {"prompt": prompt},
                "videoModelKey": model,
                "referenceImages": ref_images,
                "metadata": {"sceneId": str(uuid.uuid4())},
            })
        
        data = {
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
        }
        
        return await self._request(
            "POST",
            APIEndpoints.R2V,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    # ==================== IMAGE GENERATION ====================
    
    async def generate_image(
        self,
        access_token: str,
        recaptcha_token: str,
        project_id: str,
        prompt: str,
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
        model: str = "GEM_PIX_2",
        output_count: int = 4,
        seed: Optional[int] = None,
        image_inputs: Optional[List[Dict[str, str]]] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Text-to-Image / Image-to-Image generation.
        
        Endpoint: /v1/projects/{id}/flowMedia:batchGenerateImages (Sync)
        
        HAR verified:
        - clientContext appears BOTH at top-level AND inside each request item
        - Each request item has: clientContext, seed, imageModelName, prompt, imageInputs
        - T2I: imageInputs = []
        - I2I: imageInputs = [{name: "mediaId", imageInputType: "IMAGE_INPUT_TYPE_REFERENCE"}]
        - Response: {"media": [{"image": {"generatedImage": {...}}}]}
        """
        endpoint = f"/v1/projects/{project_id}/flowMedia:batchGenerateImages"
        
        # Build shared clientContext — HAR: T2I top-level cc has NO userPaygateTier
        client_ctx = self._build_client_context(
            recaptcha_token, project_id=project_id, paygate_tier="",
        )
        
        # HAR verified: each request item has its own clientContext + seed
        # Field names: "prompt" (not "promptInputs"), "imageAspectRatio" (not "aspectRatio")
        requests_list = []
        for _ in range(min(output_count, 4)):
            actual_seed = seed if seed is not None else generate_random_seed()
            req_item = {
                "clientContext": client_ctx,
                "seed": validate_seed(actual_seed),
                "imageModelName": model,
                "prompt": prompt,
                "imageAspectRatio": aspect_ratio,
                "imageInputs": image_inputs if image_inputs else [],
            }
            requests_list.append(req_item)
        
        data = {
            "clientContext": client_ctx,
            "requests": requests_list,
        }
        
        return await self._request(
            "POST",
            endpoint,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    # ==================== STATUS CHECKING ====================
    
    async def check_status(
        self,
        access_token: str,
        recaptcha_token: str,
        operations: List[Dict[str, Any]],
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Check status of async operations.
        
        Endpoint: /v1/video:batchCheckAsyncVideoGenerationStatus
        HAR verified: uses operations[] array of objects (NOT operationNames)
        No clientContext needed for polling.
        
        Args:
            operations: List of operation dicts, each containing:
                - operation.name: operation ID string
                - sceneId: scene UUID
                - status: current status string
        """
        data = {
            "operations": operations,
        }
        
        return await self._request(
            "POST",
            APIEndpoints.STATUS,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    # ==================== UPSCALE ====================
    
    async def upscale_video(
        self,
        access_token: str,
        recaptcha_token: str,
        video_media_id: str,
        project_id: str = "",
        target_resolution: str = "VIDEO_RESOLUTION_1080P",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        seed: Optional[int] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Upscale video resolution.
        
        Endpoint: /v1/video:batchAsyncGenerateVideoUpsampleVideo (Async)
        HAR verified: requires seed, aspectRatio, videoModelKey, metadata
        
        Resolution options:
        - VIDEO_RESOLUTION_1080P → model: veo_3_1_upsampler_1080p
        - VIDEO_RESOLUTION_4K → model: veo_3_1_upsampler_4k
        """
        import uuid
        
        actual_seed = seed if seed is not None else generate_random_seed()
        
        # Map resolution to model key
        model_map = {
            "VIDEO_RESOLUTION_1080P": "veo_3_1_upsampler_1080p",
            "VIDEO_RESOLUTION_4K": "veo_3_1_upsampler_4k",
        }
        model_key = model_map.get(target_resolution, "veo_3_1_upsampler_1080p")
        
        # Bug 12 fix: Upscale clientContext = only sessionId + recaptchaContext
        # NO projectId, NO userPaygateTier, NO tool
        # HAR verified: website sends minimal context for upscale endpoint
        import time
        upscale_ctx: Dict[str, Any] = {
            "sessionId": f";{int(time.time() * 1000)}",
        }
        if recaptcha_token:
            upscale_ctx["recaptchaContext"] = {
                "token": recaptcha_token,
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
            }
        data = {
            "clientContext": upscale_ctx,
            "requests": [{
                "aspectRatio": aspect_ratio,
                "resolution": target_resolution,
                "seed": validate_seed(actual_seed),
                "videoInput": {"mediaId": video_media_id},
                "videoModelKey": model_key,
                "metadata": {"sceneId": str(uuid.uuid4())},
            }],
        }
        
        return await self._request(
            "POST",
            APIEndpoints.UPSCALE_VIDEO,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    # ==================== UTILITY ENDPOINTS (from HAR analysis) ====================
    
    async def get_credits(
        self,
        access_token: str,
        recaptcha_token: str = "",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Check account credits and subscription status.
        
        Endpoint: GET /v1/credits?key=API_KEY
        
        Per doc §3.3.1: GET request with API key as query param.
        No body, no reCAPTCHA, no Authorization.
        
        Returns: {"credits": 45000, "userPaygateTier": "...", "sku": "...", "serviceTier": "..."}
        """
        # Bug 9 fix: Don't send access_token — per HAR, /v1/credits uses
        # only API key as query param, no Authorization: Bearer header needed.
        # Sending expired token would cause 401, preventing credit/tier fetch.
        return await self._request(
            "GET",
            f"{APIEndpoints.CREDITS}?key={APIEndpoints.API_KEY}",
            "",  # Bug 9: No access_token → no Authorization: Bearer
            "",  # No reCAPTCHA needed
            account_headers=account_headers,
        )
    
    async def generate_gif(
        self,
        access_token: str,
        recaptcha_token: str,
        media_generation_id: str,
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Generate preview GIF for a video.
        
        Endpoint: /v1/video:generatePinholeGif (Sync)
        
        HAR verified:
        - Request: {"mediaGenerationId": "..."} — NO clientContext
        - Response: {"encodedGif": "base64_string..."} — Note: Can be >10MB
        """
        data = {
            "mediaGenerationId": media_generation_id,
        }
        
        return await self._request(
            "POST",
            APIEndpoints.GIF,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    async def check_app_status(
        self,
        access_token: str,
        recaptcha_token: str,
        account_headers: Optional[Dict[str, str]] = None,
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
            account_headers=account_headers,
        )
    
    async def upscale_image(
        self,
        access_token: str,
        recaptcha_token: str,
        media_id: str,
        project_id: str = "",
        target_resolution: str = "UPSAMPLE_IMAGE_RESOLUTION_4K",
        paygate_tier: str = "PAYGATE_TIER_TWO",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Upscale image resolution.
        
        Endpoint: /v1/flow/upsampleImage (POST)
        
        HAR verified:
        - Request: {mediaId, targetResolution, clientContext}
        - Uses 'mediaId' (NOT mediaGenerationId)
        - Response: {"encodedImage": "base64..."}
        
        Resolution options:
        - UPSAMPLE_IMAGE_RESOLUTION_2K
        - UPSAMPLE_IMAGE_RESOLUTION_4K
        """
        data = {
            "mediaId": media_id,
            "targetResolution": target_resolution,
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.IMAGE_UPSCALE_FLOW,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
    
    async def upload_image(
        self,
        access_token: str,
        recaptcha_token: str,
        image_base64: str,
        mime_type: str,
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Upload a user image to get a mediaGenerationId.
        
        Endpoint: /v1:uploadUserImage (Sync)
        
        HAR verified:
        - Request: {imageInput: {rawImageBytes, mimeType, isUserUploaded, aspectRatio}, clientContext}
        - clientContext uses tool="ASSET_MANAGER", NO reCAPTCHA, NO userPaygateTier
        - Response: {mediaGenerationId: {mediaGenerationId: "CAMaJ..."}, width, height}
        
        The returned mediaGenerationId is used as startImage.mediaId in I2V calls,
        referenceImages[].mediaId in R2V calls, and imageInputs[].name in I2I calls.
        """
        data = {
            "imageInput": {
                "rawImageBytes": image_base64,
                "mimeType": mime_type,
                "isUserUploaded": True,
                "aspectRatio": aspect_ratio,
            },
            "clientContext": self._build_client_context(
                recaptcha_token,
                tool="ASSET_MANAGER",
                include_recaptcha=False,
                paygate_tier="",
            ),
        }
        
        return await self._request(
            "POST",
            APIEndpoints.UPLOAD,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
