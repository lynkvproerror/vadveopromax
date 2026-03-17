"""
Image Enhancer — Subprocess-based enhancement service.

Runs enhance_worker.py in a separate process to isolate VRAM usage.
Provides both sync and async APIs with progress callbacks.
"""

import asyncio
import json
import logging
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from enum import Enum

log = logging.getLogger(__name__)


class EnhanceMode(str, Enum):
    """Image enhancement modes."""
    UPSCALE_2X = "upscale_2x"
    UPSCALE_4X = "upscale_4x"
    FACE_RESTORE = "face_restore"
    FULL = "full"


class EnhanceResult:
    """Result of an enhancement operation."""
    
    def __init__(self, success: bool, output_path: Optional[str] = None, 
                 error: Optional[str] = None, mode: Optional[str] = None):
        self.success = success
        self.output_path = output_path
        self.error = error
        self.mode = mode
    
    def __repr__(self):
        if self.success:
            return f"EnhanceResult(ok, output={self.output_path})"
        return f"EnhanceResult(fail, error={self.error})"


class ImageEnhancer:
    """Image enhancement service using subprocess isolation.
    
    Spawns enhance_worker.py as a separate process to keep VRAM usage
    isolated from the main application. If the worker OOMs, the main
    app continues running.
    
    Usage:
        enhancer = ImageEnhancer(gpu_detector, model_manager)
        
        # Sync (blocking)
        result = enhancer.enhance_sync("input.jpg", "output.png", EnhanceMode.UPSCALE_4X)
        
        # Async
        result = await enhancer.enhance_async("input.jpg", "output.png", EnhanceMode.UPSCALE_4X,
                                               progress_callback=lambda p, s: print(f"{p}% {s}"))
    """
    
    def __init__(self, gpu_detector=None, model_manager=None):
        self._gpu_detector = gpu_detector
        self._model_manager = model_manager
        self._worker_script = Path(__file__).resolve().parent / 'enhance_worker.py'
        self._active_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
    
    @property
    def available(self) -> bool:
        """True if enhancer can be used (GPU + models ready)."""
        if self._gpu_detector and not self._gpu_detector.available:
            return False
        if self._model_manager and not self._model_manager.all_installed:
            return False
        if not self._worker_script.exists():
            return False
        return True
    
    @property
    def gpu_available(self) -> bool:
        """True if GPU is available (regardless of models)."""
        if self._gpu_detector:
            return self._gpu_detector.available or False
        return False
    
    @property 
    def models_ready(self) -> bool:
        """True if all models are installed."""
        if self._model_manager:
            return self._model_manager.all_installed
        return False
    
    def enhance_sync(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        mode: EnhanceMode = EnhanceMode.UPSCALE_4X,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        timeout: int = 300,
    ) -> EnhanceResult:
        """Enhance an image synchronously (blocking).
        
        Args:
            input_path: Path to input image
            output_path: Path to save output (auto-generated if None)
            mode: Enhancement mode
            progress_callback: fn(percent, status_text)
            timeout: Max seconds to wait
            
        Returns:
            EnhanceResult with success status and output path
        """
        input_path = str(Path(input_path).resolve())
        
        if not Path(input_path).exists():
            return EnhanceResult(False, error=f"Input not found: {input_path}")
        
        # Auto-generate output path
        if not output_path:
            inp = Path(input_path)
            output_path = str(inp.parent / f"{inp.stem}_enhanced{inp.suffix}")
        
        output_path = str(Path(output_path).resolve())
        
        # Build command
        cmd = [
            sys.executable,
            str(self._worker_script),
            '--input', input_path,
            '--output', output_path,
            '--mode', mode.value,
        ]
        
        # Add models dir if available
        if self._model_manager:
            cmd.extend(['--models-dir', str(self._model_manager.models_dir)])
        
        try:
            with self._lock:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                )
                self._active_process = process
            
            # Read progress from stdout
            last_error = None
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    pct = data.get('progress', 0)
                    status = data.get('status', '')
                    
                    if pct < 0:
                        last_error = status
                    elif progress_callback:
                        progress_callback(pct, status)
                        
                except json.JSONDecodeError:
                    continue
            
            process.wait(timeout=timeout)
            
            with self._lock:
                self._active_process = None
            
            if process.returncode == 0 and Path(output_path).exists():
                return EnhanceResult(True, output_path=output_path, mode=mode.value)
            else:
                stderr = process.stderr.read() if process.stderr else ''
                error = last_error or stderr or f"Worker exited with code {process.returncode}"
                return EnhanceResult(False, error=error, mode=mode.value)
                
        except subprocess.TimeoutExpired:
            process.kill()
            with self._lock:
                self._active_process = None
            return EnhanceResult(False, error=f"Enhancement timed out after {timeout}s")
        except Exception as e:
            with self._lock:
                self._active_process = None
            return EnhanceResult(False, error=str(e))
    
    async def enhance_async(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        mode: EnhanceMode = EnhanceMode.UPSCALE_4X,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        timeout: int = 300,
    ) -> EnhanceResult:
        """Enhance an image asynchronously (non-blocking).
        
        Runs the subprocess in a thread pool to avoid blocking the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.enhance_sync(input_path, output_path, mode, progress_callback, timeout)
        )
    
    def cancel(self):
        """Cancel the currently running enhancement."""
        with self._lock:
            if self._active_process:
                try:
                    self._active_process.kill()
                    log.info("Enhancement cancelled")
                except Exception:
                    pass
                self._active_process = None
    
    @property
    def is_running(self) -> bool:
        """True if an enhancement is currently in progress."""
        with self._lock:
            return self._active_process is not None
