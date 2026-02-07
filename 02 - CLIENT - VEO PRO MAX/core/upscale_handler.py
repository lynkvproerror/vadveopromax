"""
VEO Pro Max - Upscale Handler

Reference: SESSION_05_BACKEND_FEATURES.md
Role: Video upscaling with polling
"""

from dataclasses import dataclass
from typing import Optional, Callable
from datetime import datetime
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.api_client import VEOApiClient, APIResponse


@dataclass
class UpscaleResult:
    """Result of upscale operation."""
    success: bool
    output_uri: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0


class UpscaleHandler:
    """Handles video upscaling operations.
    
    Features:
    - Upscale 720p → 1080p/4K
    - Poll until complete (5s interval)
    - Timeout handling (10 min max)
    """
    
    DEFAULT_POLL_INTERVAL = 5.0  # seconds
    DEFAULT_TIMEOUT = 600.0      # 10 minutes
    
    def __init__(
        self,
        api_client: VEOApiClient,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self._api_client = api_client
        self._poll_interval = poll_interval
        self._timeout = timeout
        
        self._on_progress: Optional[Callable[[str, str], None]] = None
    
    def set_progress_callback(self, callback: Callable[[str, str], None]):
        """Set callback for progress updates.
        
        Callback receives (operation_name, status).
        """
        self._on_progress = callback
    
    async def upscale_video(
        self,
        access_token: str,
        recaptcha_token: str,
        video_uri: str,
        target_resolution: str = "1080p",
    ) -> UpscaleResult:
        """Upscale a video and wait for completion.
        
        Args:
            access_token: Bearer token
            recaptcha_token: reCAPTCHA token
            video_uri: URI of video to upscale
            target_resolution: Target resolution (1080p, 4K)
        
        Returns:
            UpscaleResult
        """
        start_time = datetime.now()
        
        # Start upscale
        response = await self._api_client.upscale_video(
            access_token=access_token,
            recaptcha_token=recaptcha_token,
            video_uri=video_uri,
            target_resolution=target_resolution,
        )
        
        if not response.success:
            return UpscaleResult(success=False, error=response.error)
        
        # Extract operation name
        data = response.data or {}
        operations = data.get("operations", [])
        
        if not operations:
            return UpscaleResult(success=False, error="No operation returned from API")
        
        operation_name = operations[0].get("name")
        if not operation_name:
            return UpscaleResult(success=False, error="No operation name in response")
        
        # Poll for completion
        result = await self._poll_until_complete(
            access_token,
            recaptcha_token,
            operation_name,
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        result.duration_seconds = duration
        
        return result
    
    async def _poll_until_complete(
        self,
        access_token: str,
        recaptcha_token: str,
        operation_name: str,
    ) -> UpscaleResult:
        """Poll status until complete or timeout."""
        start_time = datetime.now()
        
        while True:
            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed >= self._timeout:
                return UpscaleResult(success=False, error="Upscale operation timed out")
            
            # Check status
            response = await self._api_client.check_status(
                access_token=access_token,
                recaptcha_token=recaptcha_token,
                operation_names=[operation_name],
            )
            
            if not response.success:
                return UpscaleResult(success=False, error=response.error)
            
            # Parse status
            data = response.data or {}
            statuses = data.get("operationStatuses", [])
            
            if not statuses:
                return UpscaleResult(success=False, error="No status in response")
            
            status = statuses[0]
            state = status.get("state", "UNKNOWN")
            
            # Report progress
            if self._on_progress:
                self._on_progress(operation_name, state)
            
            if state == "SUCCEEDED":
                # Extract output
                result_data = status.get("result", {})
                output_uri = result_data.get("videoUri")
                return UpscaleResult(success=True, output_uri=output_uri)
            
            elif state == "FAILED":
                error_msg = status.get("error", {}).get("message", "Upscale failed")
                return UpscaleResult(success=False, error=error_msg)
            
            elif state == "CANCELLED":
                return UpscaleResult(success=False, error="Operation cancelled")
            
            # Still processing, wait and poll again
            await asyncio.sleep(self._poll_interval)
    
    async def check_upscale_status(
        self,
        access_token: str,
        recaptcha_token: str,
        operation_name: str,
    ) -> tuple[str, Optional[str]]:
        """Check status of an upscale operation.
        
        Returns: (state, output_uri or error_message)
        """
        response = await self._api_client.check_status(
            access_token=access_token,
            recaptcha_token=recaptcha_token,
            operation_names=[operation_name],
        )
        
        if not response.success:
            return "ERROR", response.error
        
        data = response.data or {}
        statuses = data.get("operationStatuses", [])
        
        if not statuses:
            return "UNKNOWN", None
        
        status = statuses[0]
        state = status.get("state", "UNKNOWN")
        
        if state == "SUCCEEDED":
            output_uri = status.get("result", {}).get("videoUri")
            return state, output_uri
        elif state == "FAILED":
            error_msg = status.get("error", {}).get("message")
            return state, error_msg
        
        return state, None
