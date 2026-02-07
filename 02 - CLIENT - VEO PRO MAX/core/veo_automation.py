"""
VEO Pro Max - VEO Automation Handler

Automates VEO generation workflows via browser.
"""

from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from enum import Enum
import asyncio
import re
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.browser_manager import BrowserManager, BrowserSession, BrowserConfig
from core.event_manager import EventType, emit_event
from config.constants import WorkflowType, AspectRatio, VideoModel


class VEOSelectors:
    """CSS/XPath selectors for VEO UI elements."""
    
    # Prompt input
    PROMPT_INPUT = 'textarea[aria-label*="prompt"], textarea[placeholder*="Describe"]'
    
    # Aspect ratio buttons
    ASPECT_LANDSCAPE = 'button[aria-label*="Landscape"], button:has-text("16:9")'
    ASPECT_PORTRAIT = 'button[aria-label*="Portrait"], button:has-text("9:16")'
    ASPECT_SQUARE = 'button[aria-label*="Square"], button:has-text("1:1")'
    
    # Model selector
    MODEL_SELECTOR = 'button[aria-label*="model"], [data-testid="model-selector"]'
    
    # Generate button
    GENERATE_BUTTON = 'button:has-text("Generate"), button[aria-label*="Generate"]'
    
    # Image upload
    IMAGE_UPLOAD_INPUT = 'input[type="file"][accept*="image"]'
    IMAGE_UPLOAD_BUTTON = 'button:has-text("Upload"), button[aria-label*="Upload image"]'
    
    # Video upload
    VIDEO_UPLOAD_INPUT = 'input[type="file"][accept*="video"]'
    
    # Duration selector
    DURATION_5S = 'button:has-text("5s"), button[aria-label*="5 seconds"]'
    DURATION_8S = 'button:has-text("8s"), button[aria-label*="8 seconds"]'
    
    # Output count
    OUTPUT_1 = 'button:has-text("1 video")'
    OUTPUT_2 = 'button:has-text("2 videos")'
    OUTPUT_4 = 'button:has-text("4 videos")'
    
    # Queue indicators
    GENERATING_INDICATOR = '.generating, [data-state="generating"]'
    COMPLETE_INDICATOR = '.complete, [data-state="complete"]'
    ERROR_INDICATOR = '.error, [data-state="error"]'
    
    # Download buttons
    DOWNLOAD_BUTTON = 'button:has-text("Download"), button[aria-label*="Download"]'
    DOWNLOAD_720P = 'button:has-text("720p")'
    DOWNLOAD_1080P = 'button:has-text("1080p")'
    
    # reCAPTCHA
    RECAPTCHA_FRAME = 'iframe[src*="recaptcha"]'
    RECAPTCHA_CHECKBOX = '#recaptcha-anchor'


class VEOState(str, Enum):
    """VEO automation state."""
    IDLE = "idle"
    FILLING_FORM = "filling_form"
    UPLOADING = "uploading"
    GENERATING = "generating"
    POLLING = "polling"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class VEOGenerationRequest:
    """A VEO generation request."""
    prompt: str
    workflow: WorkflowType
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    model: VideoModel = VideoModel.VEO_FAST_31
    output_count: int = 4
    duration: int = 8
    image_path: Optional[str] = None
    video_path: Optional[str] = None


@dataclass
class VEOGenerationResult:
    """Result of a VEO generation."""
    success: bool
    request: VEOGenerationRequest
    output_urls: List[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    
    def __post_init__(self):
        if self.output_urls is None:
            self.output_urls = []


class VEOAutomationHandler:
    """Automate VEO generation via browser.
    
    Features:
    - Form filling automation
    - Image/video upload
    - Generation polling
    - Download orchestration
    """
    
    POLL_INTERVAL_SEC = 5
    MAX_WAIT_SEC = 600  # 10 minutes
    
    def __init__(self, browser_manager: BrowserManager):
        self._browser = browser_manager
        self._state = VEOState.IDLE
        
        # Callbacks
        self._on_state_changed: Optional[Callable[[VEOState], None]] = None
        self._on_progress: Optional[Callable[[str, int], None]] = None
    
    @property
    def state(self) -> VEOState:
        return self._state
    
    def set_callbacks(
        self,
        on_state_changed: Optional[Callable[[VEOState], None]] = None,
        on_progress: Optional[Callable[[str, int], None]] = None,
    ):
        """Set callbacks."""
        self._on_state_changed = on_state_changed
        self._on_progress = on_progress
    
    def _set_state(self, state: VEOState):
        """Update state."""
        self._state = state
        if self._on_state_changed:
            self._on_state_changed(state)
    
    async def generate(
        self,
        session: BrowserSession,
        request: VEOGenerationRequest,
    ) -> VEOGenerationResult:
        """Execute a generation workflow.
        
        Args:
            session: Browser session to use
            request: Generation request
        
        Returns:
            VEOGenerationResult
        """
        start_time = datetime.now()
        page = session.page
        
        if not page:
            return VEOGenerationResult(
                success=False,
                request=request,
                error="No page available",
            )
        
        try:
            # Navigate to VEO if needed
            if "aistudio.google.com" not in page.url:
                await self._browser.navigate_to_veo(session.id)
            
            # Fill form
            self._set_state(VEOState.FILLING_FORM)
            await self._fill_form(page, request)
            
            # Upload media if needed
            if request.workflow in (WorkflowType.I2V, WorkflowType.I2I):
                self._set_state(VEOState.UPLOADING)
                await self._upload_image(page, request.image_path)
            elif request.workflow == WorkflowType.R2V:
                self._set_state(VEOState.UPLOADING)
                await self._upload_video(page, request.video_path)
            
            # Click generate
            self._set_state(VEOState.GENERATING)
            await self._click_generate(page)
            
            # Poll for completion
            self._set_state(VEOState.POLLING)
            output_urls = await self._poll_completion(page)
            
            # Calculate duration
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            self._set_state(VEOState.COMPLETE)
            
            return VEOGenerationResult(
                success=True,
                request=request,
                output_urls=output_urls,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            self._set_state(VEOState.ERROR)
            return VEOGenerationResult(
                success=False,
                request=request,
                error=str(e),
            )
    
    async def _fill_form(self, page, request: VEOGenerationRequest):
        """Fill the generation form."""
        # Enter prompt
        await self._browser.humanized_delay()
        prompt_input = page.locator(VEOSelectors.PROMPT_INPUT)
        await prompt_input.fill(request.prompt)
        
        # Set aspect ratio
        aspect_selector = {
            AspectRatio.LANDSCAPE: VEOSelectors.ASPECT_LANDSCAPE,
            AspectRatio.PORTRAIT: VEOSelectors.ASPECT_PORTRAIT,
            AspectRatio.SQUARE: VEOSelectors.ASPECT_SQUARE,
        }.get(request.aspect_ratio, VEOSelectors.ASPECT_LANDSCAPE)
        
        try:
            await page.click(aspect_selector, timeout=5000)
        except Exception:
            pass  # Aspect may already be selected
        
        # Set duration
        duration_selector = VEOSelectors.DURATION_8S if request.duration >= 8 else VEOSelectors.DURATION_5S
        try:
            await page.click(duration_selector, timeout=5000)
        except Exception:
            pass
        
        # Set output count
        output_selector = {
            1: VEOSelectors.OUTPUT_1,
            2: VEOSelectors.OUTPUT_2,
            4: VEOSelectors.OUTPUT_4,
        }.get(request.output_count, VEOSelectors.OUTPUT_4)
        
        try:
            await page.click(output_selector, timeout=5000)
        except Exception:
            pass
    
    async def _upload_image(self, page, image_path: str):
        """Upload an image for I2V."""
        if not image_path or not Path(image_path).exists():
            raise ValueError(f"Image not found: {image_path}")
        
        await self._browser.humanized_delay()
        
        # Click upload button to reveal input
        try:
            await page.click(VEOSelectors.IMAGE_UPLOAD_BUTTON, timeout=5000)
        except Exception:
            pass
        
        # Set file input
        file_input = page.locator(VEOSelectors.IMAGE_UPLOAD_INPUT)
        await file_input.set_input_files(image_path)
        
        # Wait for upload
        await asyncio.sleep(2)
    
    async def _upload_video(self, page, video_path: str):
        """Upload a video for R2V."""
        if not video_path or not Path(video_path).exists():
            raise ValueError(f"Video not found: {video_path}")
        
        await self._browser.humanized_delay()
        
        file_input = page.locator(VEOSelectors.VIDEO_UPLOAD_INPUT)
        await file_input.set_input_files(video_path)
        
        # Wait for upload processing
        await asyncio.sleep(5)
    
    async def _click_generate(self, page):
        """Click the generate button."""
        await self._browser.humanized_delay()
        await page.click(VEOSelectors.GENERATE_BUTTON)
    
    async def _poll_completion(self, page) -> List[str]:
        """Poll for generation completion.
        
        Returns list of output URLs.
        """
        elapsed = 0
        
        while elapsed < self.MAX_WAIT_SEC:
            # Check for completion
            try:
                complete = await page.locator(VEOSelectors.COMPLETE_INDICATOR).count()
                if complete > 0:
                    break
            except Exception:
                pass
            
            # Check for error
            try:
                error = await page.locator(VEOSelectors.ERROR_INDICATOR).count()
                if error > 0:
                    raise Exception("Generation failed")
            except Exception:
                pass
            
            # Update progress
            progress = min(95, int((elapsed / self.MAX_WAIT_SEC) * 100))
            if self._on_progress:
                self._on_progress("generating", progress)
            
            await asyncio.sleep(self.POLL_INTERVAL_SEC)
            elapsed += self.POLL_INTERVAL_SEC
        
        # Extract output URLs
        return await self._extract_output_urls(page)
    
    async def _extract_output_urls(self, page) -> List[str]:
        """Extract video URLs from completed generation."""
        urls = []
        
        # Look for video elements or download links
        try:
            videos = await page.locator("video source").all()
            for video in videos:
                src = await video.get_attribute("src")
                if src:
                    urls.append(src)
        except Exception:
            pass
        
        # Also check data attributes
        try:
            elements = await page.locator("[data-video-url]").all()
            for elem in elements:
                url = await elem.get_attribute("data-video-url")
                if url:
                    urls.append(url)
        except Exception:
            pass
        
        return urls
    
    async def download_outputs(
        self,
        page,
        output_dir: str,
        quality: str = "720p",
    ) -> List[str]:
        """Download generated outputs.
        
        Returns list of downloaded file paths.
        """
        self._set_state(VEOState.DOWNLOADING)
        
        downloaded = []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Click download buttons
        download_selector = VEOSelectors.DOWNLOAD_720P if quality == "720p" else VEOSelectors.DOWNLOAD_1080P
        
        try:
            buttons = await page.locator(VEOSelectors.DOWNLOAD_BUTTON).all()
            
            for i, button in enumerate(buttons):
                # Click to reveal quality options
                await button.click()
                await asyncio.sleep(1)
                
                # Wait for download
                async with page.expect_download() as download_info:
                    try:
                        await page.click(download_selector, timeout=5000)
                    except Exception:
                        # Try direct download
                        await button.click()
                    
                    download = await download_info.value
                    save_path = output_path / f"output_{i+1}.mp4"
                    await download.save_as(str(save_path))
                    downloaded.append(str(save_path))
        except Exception:
            pass
        
        self._set_state(VEOState.COMPLETE)
        return downloaded
