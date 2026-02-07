"""
VEO Pro Max - Media Handler

Reference: CORE_MODULES_SPEC.md
Role: Image processing, base64 encoding, aspect ratio detection
"""

from typing import Optional, Tuple
from pathlib import Path
from enum import Enum
import base64
import io
import sys

# PIL is optional for image processing
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import AspectRatio


class ImageFormat(str, Enum):
    """Supported image formats."""
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"


class MediaHandler:
    """Handles media file operations.
    
    Features:
    - Image to base64 encoding with JPEG conversion
    - Aspect ratio detection
    - File downloading with streaming
    - Base64 image saving
    """
    
    JPEG_QUALITY = 90
    MAX_DIMENSION = 2048
    
    @staticmethod
    def image_to_base64(
        image_path: str,
        convert_to_jpeg: bool = True,
        max_dimension: Optional[int] = None
    ) -> Optional[Tuple[str, str]]:
        """Convert image file to base64.
        
        Args:
            image_path: Path to image file
            convert_to_jpeg: Convert to JPEG for smaller size
            max_dimension: Max width/height (resize if larger)
        
        Returns:
            Tuple of (base64_string, mime_type) or None on error
        """
        if not HAS_PIL:
            # Fallback: direct file read without processing
            return MediaHandler._raw_file_to_base64(image_path)
        
        try:
            path = Path(image_path)
            if not path.exists():
                return None
            
            with Image.open(path) as img:
                # Convert RGBA to RGB for JPEG
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Resize if needed
                max_dim = max_dimension or MediaHandler.MAX_DIMENSION
                if max(img.size) > max_dim:
                    ratio = max_dim / max(img.size)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                
                # Convert to bytes
                buffer = io.BytesIO()
                fmt = "JPEG" if convert_to_jpeg else path.suffix[1:].upper()
                if fmt not in ("JPEG", "PNG", "WEBP"):
                    fmt = "JPEG"
                
                img.save(buffer, format=fmt, quality=MediaHandler.JPEG_QUALITY)
                buffer.seek(0)
                
                # Encode to base64
                b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                mime_type = {
                    "JPEG": ImageFormat.JPEG.value,
                    "PNG": ImageFormat.PNG.value,
                    "WEBP": ImageFormat.WEBP.value,
                }.get(fmt, ImageFormat.JPEG.value)
                
                return b64, mime_type
                
        except Exception:
            return None
    
    @staticmethod
    def _raw_file_to_base64(file_path: str) -> Optional[Tuple[str, str]]:
        """Fallback: Read file directly without PIL processing."""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            with open(path, 'rb') as f:
                data = f.read()
            
            b64 = base64.b64encode(data).decode('utf-8')
            
            # Detect mime type from extension
            ext = path.suffix.lower()
            mime_type = {
                ".jpg": ImageFormat.JPEG.value,
                ".jpeg": ImageFormat.JPEG.value,
                ".png": ImageFormat.PNG.value,
                ".webp": ImageFormat.WEBP.value,
            }.get(ext, ImageFormat.JPEG.value)
            
            return b64, mime_type
            
        except Exception:
            return None
    
    @staticmethod
    def detect_aspect_ratio(image_path: str) -> Optional[str]:
        """Detect image aspect ratio.
        
        Returns: "LANDSCAPE" | "PORTRAIT" | "SQUARE" | None
        """
        if not HAS_PIL:
            return None
        
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                
                ratio = width / height
                
                if 0.95 <= ratio <= 1.05:
                    return "SQUARE"
                elif ratio > 1.05:
                    return "LANDSCAPE"
                else:
                    return "PORTRAIT"
                    
        except Exception:
            return None
    
    @staticmethod
    def get_image_dimensions(image_path: str) -> Optional[Tuple[int, int]]:
        """Get image dimensions.
        
        Returns: (width, height) or None
        """
        if not HAS_PIL:
            return None
        
        try:
            with Image.open(image_path) as img:
                return img.size
        except Exception:
            return None
    
    @staticmethod
    def save_base64_image(
        base64_data: str,
        output_path: str,
        mime_type: str = ImageFormat.JPEG.value
    ) -> bool:
        """Decode base64 and save to file.
        
        Returns True if successful.
        """
        try:
            # Remove data URL prefix if present
            if "," in base64_data:
                base64_data = base64_data.split(",", 1)[1]
            
            data = base64.b64decode(base64_data)
            
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'wb') as f:
                f.write(data)
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    async def download_file(
        url: str,
        output_path: str,
        session = None,
        chunk_size: int = 8192
    ) -> bool:
        """Download file with streaming.
        
        Returns True if successful.
        """
        import aiohttp
        
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use provided session or create new
            should_close = False
            if session is None:
                session = aiohttp.ClientSession()
                should_close = True
            
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return False
                    
                    with open(path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(chunk_size):
                            f.write(chunk)
                    
                    return True
            finally:
                if should_close:
                    await session.close()
                    
        except Exception:
            return False
    
    @staticmethod
    def get_file_size(file_path: str) -> int:
        """Get file size in bytes."""
        try:
            return Path(file_path).stat().st_size
        except Exception:
            return 0
    
    @staticmethod
    def is_valid_image(file_path: str) -> bool:
        """Check if file is a valid image."""
        if not HAS_PIL:
            # Fallback: check extension
            ext = Path(file_path).suffix.lower()
            return ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
        
        try:
            with Image.open(file_path) as img:
                img.verify()
            return True
        except Exception:
            return False
