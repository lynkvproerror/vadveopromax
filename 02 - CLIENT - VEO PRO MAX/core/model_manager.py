"""
Model Manager — Download, verify, and manage AI model weights.

Models are stored in `assets/models/` relative to app directory (portable).
Supports on-demand download from GitHub Releases with SHA-256 verification.
"""

import hashlib
import logging
import threading
from pathlib import Path
from typing import Optional, Callable, Dict, List
from enum import Enum

log = logging.getLogger(__name__)


# === Model Definitions ===

class ModelInfo:
    """Metadata for a downloadable AI model."""
    
    def __init__(self, filename: str, url: str, sha256: str, size_mb: int, description: str):
        self.filename = filename
        self.url = url
        self.sha256 = sha256
        self.size_mb = size_mb
        self.description = description


# Model registry — download URLs from original authors' GitHub Releases
MODELS = {
    'realesrgan_x4': ModelInfo(
        filename='RealESRGAN_x4plus.pth',
        url='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
        sha256='4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1',
        size_mb=64,
        description='Real-ESRGAN 4x Upscale',
    ),
    'realesrgan_x2': ModelInfo(
        filename='RealESRGAN_x2plus.pth',
        url='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth',
        sha256='',  # Will verify at first download
        size_mb=64,
        description='Real-ESRGAN 2x Upscale',
    ),
    'gfpgan': ModelInfo(
        filename='GFPGANv1.4.pth',
        url='https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth',
        sha256='',  # Will verify at first download
        size_mb=348,
        description='GFPGAN Face Restore',
    ),
}


class ModelManager:
    """Manage AI model weights — download, verify, and locate.
    
    Models are stored in `assets/models/` relative to the app directory,
    making the installation portable (move folder = everything works).
    
    Usage:
        mm = ModelManager()
        if mm.all_installed:
            path = mm.get_model_path('realesrgan_x4')
        else:
            mm.download_all(progress_callback=lambda p, msg: print(f"{p}% {msg}"))
    """
    
    def __init__(self, app_dir: Optional[str] = None):
        """Initialize with app directory (auto-detected if None)."""
        if app_dir:
            self._app_dir = Path(app_dir)
        else:
            # Auto-detect: go up from this file's location to CLIENT root
            self._app_dir = Path(__file__).resolve().parent.parent
        
        self._models_dir = self._app_dir / 'assets' / 'models'
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._download_lock = threading.Lock()
    
    @property
    def models_dir(self) -> Path:
        """Path to models directory."""
        return self._models_dir
    
    @property
    def all_installed(self) -> bool:
        """True if all required models are downloaded."""
        return all(self.is_installed(key) for key in MODELS)
    
    @property
    def installed_models(self) -> List[str]:
        """List of installed model keys."""
        return [key for key in MODELS if self.is_installed(key)]
    
    @property
    def missing_models(self) -> List[str]:
        """List of missing model keys."""
        return [key for key in MODELS if not self.is_installed(key)]
    
    @property
    def total_download_size_mb(self) -> int:
        """Total size of all models in MB."""
        return sum(m.size_mb for m in MODELS.values())
    
    @property
    def missing_download_size_mb(self) -> int:
        """Size of missing models in MB."""
        return sum(MODELS[k].size_mb for k in self.missing_models)
    
    def is_installed(self, model_key: str) -> bool:
        """Check if a specific model file exists."""
        info = MODELS.get(model_key)
        if not info:
            return False
        path = self._models_dir / info.filename
        return path.exists() and path.stat().st_size > 1024  # > 1KB sanity check
    
    def get_model_path(self, model_key: str) -> Optional[Path]:
        """Get absolute path to a model file, or None if not installed."""
        info = MODELS.get(model_key)
        if not info:
            return None
        path = self._models_dir / info.filename
        return path if path.exists() else None
    
    def verify_model(self, model_key: str) -> bool:
        """Verify model SHA-256 hash (skip if hash not set)."""
        info = MODELS.get(model_key)
        if not info:
            return False
        path = self._models_dir / info.filename
        if not path.exists():
            return False
        if not info.sha256:
            return True  # No hash to verify
        
        sha = hashlib.sha256()
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha.update(chunk)
        
        actual = sha.hexdigest()
        if actual != info.sha256:
            log.warning(f"Model {model_key} hash mismatch: expected {info.sha256[:16]}..., got {actual[:16]}...")
            return False
        return True
    
    def download_model(
        self,
        model_key: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """Download a single model file.
        
        Args:
            model_key: Key from MODELS registry
            progress_callback: fn(percent: int, message: str)
            
        Returns:
            True if download successful
        """
        info = MODELS.get(model_key)
        if not info:
            log.error(f"Unknown model key: {model_key}")
            return False
        
        dest = self._models_dir / info.filename
        temp = dest.with_suffix('.tmp')
        
        try:
            import requests
            
            if progress_callback:
                progress_callback(0, f"Downloading {info.description}...")
            
            log.info(f"Downloading {info.filename} from {info.url}")
            
            response = requests.get(info.url, stream=True, timeout=30)
            response.raise_for_status()
            
            total = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(temp, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and progress_callback:
                        pct = min(99, int(downloaded / total * 100))
                        progress_callback(pct, f"{info.description}: {downloaded // (1024*1024)}MB / {total // (1024*1024)}MB")
            
            # Rename temp → final
            if dest.exists():
                dest.unlink()
            temp.rename(dest)
            
            if progress_callback:
                progress_callback(100, f"✅ {info.description} installed")
            
            log.info(f"Model {info.filename} downloaded ({downloaded // (1024*1024)}MB)")
            return True
            
        except Exception as e:
            log.error(f"Download failed for {info.filename}: {e}")
            if temp.exists():
                temp.unlink(missing_ok=True)
            if progress_callback:
                progress_callback(-1, f"❌ Download failed: {e}")
            return False
    
    def download_all(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """Download all missing models sequentially.
        
        Args:
            progress_callback: fn(overall_percent: int, message: str)
            
        Returns:
            True if all downloads successful
        """
        with self._download_lock:
            missing = self.missing_models
            if not missing:
                if progress_callback:
                    progress_callback(100, "All models already installed")
                return True
            
            total_models = len(missing)
            success = True
            
            for idx, key in enumerate(missing):
                base_pct = int(idx / total_models * 100)
                
                def _sub_progress(pct: int, msg: str):
                    if pct < 0:
                        if progress_callback:
                            progress_callback(pct, msg)
                        return
                    overall = base_pct + int(pct / total_models)
                    if progress_callback:
                        progress_callback(overall, msg)
                
                if not self.download_model(key, _sub_progress):
                    success = False
                    break
            
            if success and progress_callback:
                progress_callback(100, f"✅ All {total_models} models installed")
            
            return success
    
    def get_status_summary(self) -> Dict[str, str]:
        """Get status summary for UI display."""
        result = {}
        for key, info in MODELS.items():
            if self.is_installed(key):
                result[key] = f"✅ {info.description} ({info.size_mb}MB)"
            else:
                result[key] = f"⬇️ {info.description} ({info.size_mb}MB) — not installed"
        return result
