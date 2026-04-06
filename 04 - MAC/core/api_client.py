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
# Video seeds (T2V, I2V, R2V) — HAR verified range
SEED_MIN = 5000
SEED_MAX = 24999

# Image seeds (T2I, I2I) — F12 verified 2026-03-15: 11229, 14587, 134141, 219035, 304242, 541405
IMAGE_SEED_MIN = 10000
IMAGE_SEED_MAX = 999999


def generate_random_seed() -> int:
    """Generate a random seed for video workflows (5000-24999)."""
    return random.randint(SEED_MIN, SEED_MAX)


def generate_random_image_seed() -> int:
    """Generate a random seed for image workflows (1-999999)."""
    return random.randint(IMAGE_SEED_MIN, IMAGE_SEED_MAX)


def validate_seed(seed: int) -> int:
    """Validate and clamp seed to video range."""
    if not isinstance(seed, int):
        raise ValueError("Seed must be an integer")
    return max(SEED_MIN, min(SEED_MAX, seed))


def validate_image_seed(seed: int) -> int:
    """Validate and clamp seed to image range."""
    if not isinstance(seed, int):
        raise ValueError("Seed must be an integer")
    return max(IMAGE_SEED_MIN, min(IMAGE_SEED_MAX, seed))


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
        
        Per HAR analysis (verified 2026-02-22):
        - Content-Type: text/plain;charset=UTF-8 (NOT application/json!)
        - Origin + Referer required for CORS
        - Authorization: Bearer {token}
        - x-browser-* headers included for fingerprinting
        
        IMPORTANT: _request uses data=json.dumps() NOT json=data,
        because aiohttp json= silently overrides Content-Type to application/json.
        
        Args:
            access_token: OAuth2 access token.
            extra_headers: Additional headers to merge.
            account_headers: Per-account x-browser-* headers dict.
        """
        headers = {
            "Content-Type": "text/plain;charset=UTF-8",
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
        session_id: str = "",
    ) -> Dict[str, Any]:
        """Build clientContext for API requests.
        
        Per HAR analysis (verified ground truth):
        - tool: "PINHOLE" for video/image, "ASSET_MANAGER" for uploads
        - sessionId: ";{timestamp_ms}"
        - projectId: only for generate endpoints, NOT for upload/upscale
        - userPaygateTier: only for video generate endpoints
        - recaptchaContext: REQUIRED for all generation calls (HAR verified)
        
        HAR-verified clientContext per endpoint:
          batchAsyncGenerateVideoText:     sessionId + tool + paygateTier + recaptcha
          batchGenerateImages:             sessionId + tool + projectId + recaptcha
          uploadUserImage:                 sessionId + tool (ASSET_MANAGER only)
          batchAsyncGenerateVideoUpsampleVideo: sessionId + projectId + tool + paygateTier + recaptcha
        
        F12 2026-03-16: All images in a T2I batch share the SAME sessionId.
        Pass session_id to reuse across batch; omit to auto-generate.
        """
        import time
        import uuid as _uuid
        ctx: Dict[str, Any] = {
            "sessionId": session_id or f";{int(time.time() * 1000)}",
        }
        # tool: included when specified (most endpoints except upscale)
        if tool:
            ctx["tool"] = tool
        # projectId: only include when explicitly provided (HAR: not in upload/upscale)
        if project_id:
            ctx["projectId"] = project_id
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
        # RAW version does NOT append ?key= — match that behavior exactly
        url = f"{self.base_url}{endpoint}"
        headers = self._build_headers(access_token=access_token, account_headers=account_headers)
        
        try:
            session = await self._get_session()
            
            import logging
            _log = logging.getLogger(__name__)
            
            # CRITICAL: Use data=json.dumps() NOT json=data
            # aiohttp json= overrides Content-Type to application/json
            # but HAR shows website sends text/plain;charset=UTF-8
            body = json.dumps(data) if data else None
            async with session.request(method, url, headers=headers, data=body) as resp:
                self._call_count += 1
                response_code = resp.status
                response_text = await resp.text()
                
                # On 403: dump full request details at WARNING level for diagnosis
                if response_code == 403:
                    _log.warning(f"[403 DEBUG] {method} {url}")
                    # Mask tokens for readability
                    safe_headers = {k: (v[:40] + '...' if len(str(v)) > 40 else v) for k, v in headers.items()}
                    _log.warning(f"[403 DEBUG] Headers: {json.dumps(safe_headers, indent=2, ensure_ascii=False)}")
                    if data:
                        import copy
                        dump = copy.deepcopy(data)
                        if "clientContext" in dump and "recaptchaContext" in dump.get("clientContext", {}):
                            t = dump["clientContext"]["recaptchaContext"].get("token", "")
                            dump["clientContext"]["recaptchaContext"]["token"] = f"<{len(t)}chars>"
                        _log.warning(f"[403 DEBUG] Body: {json.dumps(dump, indent=2, default=str, ensure_ascii=False)}")
                
                # On 401: log auth diagnosis info
                if response_code == 401:
                    has_auth = 'Authorization' in headers
                    auth_prefix = headers.get('Authorization', '')[:20] if has_auth else 'MISSING'
                    # /v1/credits intentionally sends NO auth (HAR: API key only, no Bearer)
                    # → DEBUG to avoid log spam. All other 401s remain WARNING.
                    is_expected_no_auth = '/v1/credits' in endpoint
                    log_fn = _log.debug if (is_expected_no_auth and not has_auth) else _log.warning
                    log_fn(f"[401 DEBUG] {method} {url} — auth_header={auth_prefix}...")
                
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
    
    def build_request_body(
        self,
        workflow_type: str,
        prompt: str,
        project_id: str = "",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        model: str = "veo_3_1_t2v_fast_ultra",
        output_count: int = 4,
        seed: Optional[int] = None,
        paygate_tier: str = "PAYGATE_TIER_TWO",
        image_uris: Optional[List[str]] = None,
        batch_id: str = "",
        session_id: str = "",
    ) -> Tuple[str, Dict[str, Any]]:
        """Build full request body for Extension-based submission.
        
        Returns (endpoint_key, body) where body does NOT contain
        recaptchaContext — Extension injects fresh token from page context.
        
        Args:
            workflow_type: T2V, I2V, R2V, T2I, F2V
            prompt: Generation prompt
            project_id: TRPC project ID
            aspect_ratio: Video/image aspect ratio
            model: Model key
            output_count: Number of outputs (1-4)
            seed: Optional deterministic seed
            paygate_tier: Paygate tier
            image_uris: Image media IDs (for I2V, R2V, F2V)
            batch_id: F12 verified: all images in T2I batch share same batchId
            session_id: F12 verified: all images in T2I batch share same sessionId
            
        Returns:
            Tuple of (endpoint_key, body_dict)
            endpoint_key: 'T2V', 'I2V_SINGLE', 'I2V_DUAL', 'R2V', 'T2I'
        """
        import uuid as _uuid
        
        # Build clientContext WITHOUT recaptchaContext
        client_ctx = self._build_client_context(
            recaptcha_token="",  # Extension adds fresh token
            project_id=project_id,
            paygate_tier=paygate_tier,
            include_recaptcha=False,  # Key: no reCAPTCHA in body
        )
        
        # Build requests[] array based on workflow type
        wt = workflow_type.upper()
        
        if wt in ("T2V", "F2V"):
            requests_list = []
            for idx in range(min(output_count, 4)):
                actual_seed = (seed + idx) if seed is not None else generate_random_seed()
                req_item = {
                    "aspectRatio": aspect_ratio,
                    "seed": validate_seed(actual_seed),
                    # F12 2026-03-15: video now uses structuredPrompt (not textInput.prompt)
                    "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                    "videoModelKey": model,
                    "metadata": {},  # F12: empty object
                }
                # F2V: add start image
                if wt == "F2V" and image_uris:
                    req_item["startImage"] = {
                        "mediaId": image_uris[0]
                    }
                requests_list.append(req_item)
            
            if wt == "F2V" and image_uris:
                endpoint = "I2V_SINGLE"
            else:
                endpoint = "T2V"
            
            return endpoint, {
                "mediaGenerationContext": {"batchId": str(_uuid.uuid4())},
                "clientContext": client_ctx,
                "requests": requests_list,
                "useV2ModelConfig": True,
            }
        
        elif wt == "I2V":
            requests_list = []
            for idx in range(min(output_count, 4)):
                actual_seed = (seed + idx) if seed is not None else generate_random_seed()
                req_item = {
                    "aspectRatio": aspect_ratio,
                    "seed": validate_seed(actual_seed),
                    "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                    "videoModelKey": model,
                    "metadata": {},
                }
                if image_uris and len(image_uris) >= 2:
                    req_item["startImage"] = {"mediaId": image_uris[0]}
                    req_item["endImage"] = {"mediaId": image_uris[1]}
                    endpoint = "I2V_DUAL"
                elif image_uris and len(image_uris) == 1:
                    req_item["startImage"] = {"mediaId": image_uris[0]}
                    endpoint = "I2V_SINGLE"
                else:
                    return "I2V_SINGLE", {}  # Error: no images
                requests_list.append(req_item)
            
            return endpoint, {
                "mediaGenerationContext": {"batchId": str(_uuid.uuid4())},
                "clientContext": client_ctx,
                "requests": requests_list,
                "useV2ModelConfig": True,
            }
        
        elif wt == "R2V":
            requests_list = []
            for idx in range(min(output_count, 4)):
                actual_seed = (seed + idx) if seed is not None else generate_random_seed()
                # HAR verified: referenceImages[] with imageUsageType + mediaId
                ref_images = [
                    {"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": uri}
                    for uri in (image_uris or [])[:3]
                ]
                requests_list.append({
                    "aspectRatio": aspect_ratio,
                    "seed": validate_seed(actual_seed),
                    "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                    "videoModelKey": model,
                    "metadata": {},
                    "referenceImages": ref_images,
                })
            
            return "R2V", {
                "mediaGenerationContext": {"batchId": str(_uuid.uuid4())},
                "clientContext": client_ctx,
                "requests": requests_list,
                "useV2ModelConfig": True,
            }
        
        elif wt in ("T2I", "I2I"):
            # HAR verified: T2I uses different field names from video
            # - URL: projects/{projectId}/flowMedia:batchGenerateImages
            # - Array: "requests" (not "imageRequests")
            # - Fields: imageModelName, imageAspectRatio, prompt, seed
            # - Each request[] has its own nested clientContext
            # - clientContext uses tool=PINHOLE, NO userPaygateTier
            
            # Convert VIDEO_ASPECT_RATIO → IMAGE_ASPECT_RATIO
            img_ar = aspect_ratio.replace("VIDEO_ASPECT_RATIO_", "IMAGE_ASPECT_RATIO_")
            if not img_ar.startswith("IMAGE_ASPECT_RATIO_"):
                img_ar = "IMAGE_ASPECT_RATIO_LANDSCAPE"
            
            # T2I clientContext: sessionId + projectId + tool only (no paygateTier)
            # F12 2026-03-16: all images in batch share same sessionId
            t2i_ctx = self._build_client_context(
                recaptcha_token="",
                project_id=project_id,
                paygate_tier="",   # HAR: no userPaygateTier for T2I
                tool="PINHOLE",
                include_recaptcha=False,
                session_id=session_id,  # F12: reuse across batch
            )
            
            # F12 2026-03-15: Website sends 1 request per image, NOT all in batch.
            # build_request_body returns body for 1 image only.
            # Caller should loop with output_count=1 for each image in batch.
            actual_seed = seed if seed is not None else generate_random_image_seed()
            
            # HAR: imageInputs is ALWAYS present
            # T2I: [] (empty), I2I: [{name, imageInputType}]
            image_inputs = []
            if image_uris:
                image_inputs = [
                    {
                        "name": uri,
                        "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE",
                    }
                    for uri in image_uris
                ]
            
            req_item = {
                "clientContext": t2i_ctx,   # HAR: nested per-request
                "seed": validate_image_seed(actual_seed),
                "imageModelName": model or "GEM_PIX_2",  # Sidebar default: 🔥 Nano Banana Pro
                "imageAspectRatio": img_ar,
                "imageInputs": image_inputs,  # HAR: always present
                "structuredPrompt": {"parts": [{"text": prompt}]},
            }
            
            # F12 2026-03-16: all images in batch share same batchId
            import uuid as _uuid_t2i
            effective_batch_id = batch_id or str(_uuid_t2i.uuid4())
            return "T2I", {
                "clientContext": t2i_ctx,
                "mediaGenerationContext": {"batchId": effective_batch_id},
                "useNewMedia": True,
                "requests": [req_item],  # F12: exactly 1 item per HTTP request
            }
        
        else:
            return "T2V", {}  # Unknown workflow

    def build_upscale_body(
        self,
        video_media_id: str,
        target_resolution: str = "VIDEO_RESOLUTION_1080P",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        seed: Optional[int] = None,
        scene_id: Optional[str] = None,
        project_id: str = "",
        paygate_tier: str = "PAYGATE_TIER_TWO",
    ) -> Dict[str, Any]:
        """Build upscale video body for Extension submission.
        
        HAR verified 2026-03-11: upscale uses FULL clientContext:
        projectId + tool (PINHOLE) + userPaygateTier + sessionId.
        Extension adds recaptchaContext.
        Also requires: mediaGenerationContext.batchId, useV2ModelConfig.
        
        Args:
            scene_id: Used as workflowId in metadata.
            project_id: TRPC project UUID (required by API).
            paygate_tier: Account tier (default PAYGATE_TIER_TWO).
        """
        import uuid as _uuid
        import time as _time
        
        actual_seed = seed if seed is not None else generate_random_seed()
        model_map = {
            "VIDEO_RESOLUTION_1080P": "veo_3_1_upsampler_1080p",
            "VIDEO_RESOLUTION_4K": "veo_3_1_upsampler_4k",
        }
        model_key = model_map.get(target_resolution, "veo_3_1_upsampler_1080p")
        
        # HAR: metadata uses workflowId (not sceneId)
        effective_workflow_id = scene_id or str(_uuid.uuid4())
        
        # HAR verified: full clientContext (Extension injects recaptchaContext)
        client_ctx = self._build_client_context(
            recaptcha_token="",
            project_id=project_id,
            paygate_tier=paygate_tier,
            tool="PINHOLE",
            include_recaptcha=False,
        )
        
        return {
            "mediaGenerationContext": {"batchId": str(_uuid.uuid4())},
            "clientContext": client_ctx,
            "requests": [{
                "resolution": target_resolution,
                "aspectRatio": aspect_ratio,
                "seed": validate_seed(actual_seed),
                "videoModelKey": model_key,
                "metadata": {"workflowId": effective_workflow_id},
                "videoInput": {"mediaId": video_media_id},
            }],
            "useV2ModelConfig": True,
        }
    
    def build_status_body(
        self,
        operations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build status check body for Extension submission.
        
        HAR verified: NO clientContext, NO recaptchaContext needed for polling.
        Just the operations[] array.
        """
        return {
            "operations": operations,
        }
    
    def build_upscale_image_body(
        self,
        media_id: str,
        project_id: str = "",
        target_resolution: str = "UPSAMPLE_IMAGE_RESOLUTION_4K",
        paygate_tier: str = "PAYGATE_TIER_TWO",
    ) -> Dict[str, Any]:
        """Build image upscale body for Extension submission.
        
        HAR verified: uses mediaId + targetResolution + clientContext.
        clientContext has: sessionId, projectId, tool (PINHOLE).
        NO userPaygateTier (HAR verified).
        Extension adds recaptchaContext.
        """
        return {
            "mediaId": media_id,
            "targetResolution": target_resolution,
            "clientContext": self._build_client_context(
                recaptcha_token="",
                project_id=project_id,
                paygate_tier=paygate_tier,  # HAR: userPaygateTier REQUIRED
                include_recaptcha=False,
            ),
        }


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
                # F12 2026-03-15: video uses structuredPrompt
                "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                "videoModelKey": model,
                "metadata": {},  # F12: empty object
            })
        
        data = {
            "mediaGenerationContext": {"batchId": str(uuid.uuid4())},
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
            "useV2ModelConfig": True,
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
                "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                "videoModelKey": model,
                "startImage": {"mediaId": image_media_id},
                "metadata": {},
            })
        
        data = {
            "mediaGenerationContext": {"batchId": str(uuid.uuid4())},
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
            "useV2ModelConfig": True,
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
                "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                "videoModelKey": model,
                "startImage": {"mediaId": start_image_media_id},
                "endImage": {"mediaId": end_image_media_id},
                "metadata": {},
            })
        
        data = {
            "mediaGenerationContext": {"batchId": str(uuid.uuid4())},
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
            "useV2ModelConfig": True,
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
                "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
                "videoModelKey": model,
                "referenceImages": ref_images,
                "metadata": {},
            })
        
        data = {
            "mediaGenerationContext": {"batchId": str(uuid.uuid4())},
            "clientContext": self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier=paygate_tier
            ),
            "requests": requests_list,
            "useV2ModelConfig": True,
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
        
        F12 2026-03-15 verified: Website sends 1 HTTP request PER IMAGE,
        NOT all images in 1 request. Each request has:
        - 1 item in requests[] with unique seed + fresh reCAPTCHA
        - Same batchId shared across all requests in the batch
        - Response: {"media": [{"image": {"generatedImage": {...}}}]}
        """
        import uuid as _uuid_gen
        import logging
        _log = logging.getLogger(__name__)
        
        endpoint = f"/v1/projects/{project_id}/flowMedia:batchGenerateImages"
        batch_id = str(_uuid_gen.uuid4())  # F12: same batchId for entire batch
        
        all_media = []
        last_error = None
        
        for idx in range(min(output_count, 4)):
            actual_seed = seed if seed is not None else generate_random_image_seed()
            
            # Build fresh clientContext per request
            client_ctx = self._build_client_context(
                recaptcha_token, project_id=project_id, paygate_tier="",
            )
            
            # F12: each request has exactly 1 item in requests[]
            req_item = {
                "clientContext": client_ctx,
                "seed": validate_image_seed(actual_seed),
                "imageModelName": model,
                "imageAspectRatio": aspect_ratio,
                "imageInputs": image_inputs if image_inputs else [],
                "structuredPrompt": {"parts": [{"text": prompt}]},
            }
            
            data = {
                "clientContext": client_ctx,
                "mediaGenerationContext": {"batchId": batch_id},
                "useNewMedia": True,
                "requests": [req_item],  # F12: exactly 1 item per HTTP request
            }
            
            _log.info(f"[T2I] Sending image {idx+1}/{min(output_count, 4)} seed={actual_seed}")
            
            resp = await self._request(
                "POST",
                endpoint,
                access_token,
                recaptcha_token,
                data,
                account_headers=account_headers,
            )
            
            if resp.success and resp.data:
                media_items = resp.data.get("media", [])
                all_media.extend(media_items)
                _log.info(f"[T2I] Image {idx+1} OK, got {len(media_items)} media items")
            else:
                _log.warning(f"[T2I] Image {idx+1} failed: {resp.error}")
                last_error = resp.error
                # Continue trying remaining images even if one fails
        
        # Aggregate all successful media into single response
        if all_media:
            return APIResponse(
                success=True,
                data={"media": all_media},
                response_code=200,
            )
        else:
            return APIResponse(
                success=False,
                error=last_error or "No images generated",
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
        HAR verified 2026-03-11: requires full clientContext + mediaGenerationContext
        + useV2ModelConfig + metadata.workflowId.
        
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
        
        # HAR verified 2026-03-11: upscale needs FULL clientContext
        # (projectId + tool + paygateTier + sessionId + recaptchaContext)
        upscale_ctx = self._build_client_context(
            recaptcha_token=recaptcha_token,
            project_id=project_id,
            paygate_tier=paygate_tier,
            tool="PINHOLE",
        )
        
        data = {
            "mediaGenerationContext": {"batchId": str(uuid.uuid4())},
            "clientContext": upscale_ctx,
            "requests": [{
                "resolution": target_resolution,
                "aspectRatio": aspect_ratio,
                "seed": validate_seed(actual_seed),
                "videoModelKey": model_key,
                "metadata": {"workflowId": str(uuid.uuid4())},
                "videoInput": {"mediaId": video_media_id},
            }],
            "useV2ModelConfig": True,
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
            f"{APIEndpoints.CREDITS}",  # _request auto-appends ?key=
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
        file_name: str = "",
        account_headers: Optional[Dict[str, str]] = None,
    ) -> APIResponse:
        """Upload a user image to get a mediaGenerationId.
        
        Endpoint: /v1/flow/uploadImage (Sync) — F12 verified 2026-03-15
        
        F12 verified payload structure (I2I upload):
        - Request: {clientContext, imageBytes, isUserUploaded, isHidden, mimeType, fileName}
        - clientContext uses tool="PINHOLE", NO reCAPTCHA, NO userPaygateTier
        - Response: {mediaGenerationId: {mediaGenerationId: "CAMaJ..."}, width, height}
        
        The returned mediaGenerationId is used as startImage.mediaId in I2V calls,
        referenceImages[].mediaId in R2V calls, and imageInputs[].name in I2I calls.
        """
        data = {
            "clientContext": self._build_client_context(
                recaptcha_token,
                tool="PINHOLE",
                include_recaptcha=False,
                paygate_tier="",
            ),
            "imageBytes": image_base64,
            "isUserUploaded": True,
            "isHidden": False,
            "mimeType": mime_type,
        }
        if file_name:
            data["fileName"] = file_name
        
        return await self._request(
            "POST",
            APIEndpoints.UPLOAD,
            access_token,
            recaptcha_token,
            data,
            account_headers=account_headers,
        )
