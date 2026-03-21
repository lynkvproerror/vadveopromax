"""
GPU Detector — Background CUDA detection (zero startup cost).

Runs `torch.cuda.is_available()` in a daemon thread so the main UI
thread never blocks. The result is cached after first detection.
"""

import threading
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)


class GPUDetector:
    """Detect NVIDIA CUDA GPU capability without blocking app startup.
    
    Usage:
        detector = GPUDetector()        # starts background detection
        ...                             # app continues loading
        if detector.available:          # True / False / None (still checking)
            print(detector.gpu_info)    # {'name': 'RTX 4070', 'vram_mb': 8192}
    """
    
    def __init__(self, auto_start: bool = True):
        self._result: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()
        self._detected = threading.Event()
        if auto_start:
            self.start()
    
    def start(self):
        """Start background GPU detection thread."""
        t = threading.Thread(target=self._detect, daemon=True, name="gpu-detector")
        t.start()
    
    def _detect(self):
        """Run GPU detection (called in background thread)."""
        try:
            import torch
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                with self._lock:
                    self._result = {
                        'available': True,
                        'name': torch.cuda.get_device_name(0),
                        'vram_mb': props.total_mem // (1024 * 1024),
                        'cuda_version': torch.version.cuda or 'unknown',
                        'torch_version': torch.__version__,
                    }
                log.info(
                    f"GPU detected: {self._result['name']} "
                    f"({self._result['vram_mb']}MB VRAM, "
                    f"CUDA {self._result['cuda_version']})"
                )
            else:
                with self._lock:
                    self._result = {
                        'available': False,
                        'reason': 'No CUDA-capable GPU found',
                    }
                log.info("No CUDA GPU available — Image Enhancer disabled")
        except ImportError:
            with self._lock:
                self._result = {
                    'available': False,
                    'reason': 'PyTorch not installed',
                    'install_hint': 'pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121',
                }
            log.info("PyTorch not installed — Image Enhancer disabled")
        except Exception as e:
            with self._lock:
                self._result = {
                    'available': False,
                    'reason': f'Detection error: {e}',
                }
            log.warning(f"GPU detection error: {e}")
        finally:
            self._detected.set()
    
    @property
    def available(self) -> Optional[bool]:
        """True if GPU ready, False if not, None if still detecting."""
        with self._lock:
            if self._result is None:
                return None
            return self._result.get('available', False)
    
    @property
    def gpu_info(self) -> Optional[Dict[str, Any]]:
        """Full GPU info dict, or None if still detecting."""
        with self._lock:
            return self._result.copy() if self._result else None
    
    @property
    def display_text(self) -> str:
        """Human-readable GPU status for Settings UI."""
        with self._lock:
            if self._result is None:
                return "🔍 Detecting GPU..."
            if self._result.get('available'):
                name = self._result['name']
                vram = self._result['vram_mb']
                return f"✅ {name} — {vram}MB VRAM"
            reason = self._result.get('reason', 'Unknown')
            return f"❌ {reason}"
    
    @property
    def install_hint(self) -> Optional[str]:
        """PyTorch install command if not installed."""
        with self._lock:
            if self._result:
                return self._result.get('install_hint')
            return None
    
    def wait_for_result(self, timeout: float = 30.0) -> bool:
        """Block until detection completes (for testing/CLI use)."""
        return self._detected.wait(timeout)
