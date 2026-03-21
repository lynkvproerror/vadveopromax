"""
Enhance Worker — Standalone subprocess for image enhancement.

This script is designed to be run as a SEPARATE PROCESS to isolate
VRAM usage from the main application. Communication is via command-line args.

Usage:
    python enhance_worker.py --input image.jpg --output enhanced.png --mode upscale_4x
    python enhance_worker.py --input image.jpg --output enhanced.png --mode face_restore
    python enhance_worker.py --input image.jpg --output enhanced.png --mode full
    
Exit codes:
    0 = success
    1 = general error
    2 = model not found
    3 = CUDA not available
    4 = OOM error

Progress is printed to stdout as JSON lines:
    {"progress": 50, "status": "Upscaling..."}
    {"progress": 100, "status": "Done", "output": "enhanced.png"}
"""

import sys
import os
import json
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)


def emit(progress: int, status: str, **kwargs):
    """Emit progress JSON to stdout for parent process to read."""
    data = {"progress": progress, "status": status, **kwargs}
    print(json.dumps(data), flush=True)


def find_models_dir() -> Path:
    """Find the models directory relative to this script."""
    # This script lives in core/ → go up to CLIENT root → assets/models/
    script_dir = Path(__file__).resolve().parent
    models_dir = script_dir.parent / 'assets' / 'models'
    if models_dir.exists():
        return models_dir
    # Fallback: check if passed as environment variable
    env_dir = os.environ.get('ENHANCER_MODELS_DIR')
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    return models_dir  # Return expected path even if it doesn't exist


def enhance_upscale(input_path: str, output_path: str, scale: int, models_dir: Path) -> bool:
    """Upscale image using Real-ESRGAN."""
    try:
        emit(10, f"Loading Real-ESRGAN {scale}x model...")
        
        import torch
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
        
        # Select model file
        if scale == 4:
            model_name = 'RealESRGAN_x4plus.pth'
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        else:
            model_name = 'RealESRGAN_x2plus.pth'
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
        
        model_path = models_dir / model_name
        if not model_path.exists():
            emit(-1, f"Model not found: {model_path}")
            return False
        
        emit(20, "Initializing upscaler...")
        
        # Use tile-based processing for large images (avoid OOM)
        upsampler = RealESRGANer(
            scale=scale,
            model_path=str(model_path),
            model=model,
            tile=256,             # Tile size — 256px tiles to fit in 4GB VRAM
            tile_pad=10,
            pre_pad=0,
            half=True,            # FP16 for speed + less VRAM
            gpu_id=0,
        )
        
        emit(40, "Processing image...")
        
        import cv2
        import numpy as np
        
        img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            emit(-1, f"Cannot read image: {input_path}")
            return False
        
        emit(50, f"Upscaling {img.shape[1]}x{img.shape[0]} → {img.shape[1]*scale}x{img.shape[0]*scale}...")
        
        output, _ = upsampler.enhance(img, outscale=scale)
        
        emit(90, "Saving result...")
        cv2.imwrite(output_path, output)
        
        # Cleanup GPU memory
        del upsampler
        torch.cuda.empty_cache()
        
        emit(100, "Done", output=output_path)
        return True
        
    except torch.cuda.OutOfMemoryError:
        emit(-1, "GPU out of memory — try reducing image size")
        return False
    except Exception as e:
        emit(-1, f"Upscale error: {e}")
        return False


def enhance_face(input_path: str, output_path: str, models_dir: Path) -> bool:
    """Restore faces using GFPGAN."""
    try:
        emit(10, "Loading GFPGAN model...")
        
        import torch
        from gfpgan import GFPGANer
        
        model_path = models_dir / 'GFPGANv1.4.pth'
        if not model_path.exists():
            emit(-1, f"Model not found: {model_path}")
            return False
        
        emit(20, "Initializing face restorer...")
        
        restorer = GFPGANer(
            model_path=str(model_path),
            upscale=1,            # Don't upscale, just restore
            arch='clean',
            channel_multiplier=2,
            bg_upsampler=None,
        )
        
        emit(40, "Processing faces...")
        
        import cv2
        
        img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            emit(-1, f"Cannot read image: {input_path}")
            return False
        
        emit(50, "Restoring face details...")
        
        _, _, output = restorer.enhance(
            img,
            has_aligned=False,
            only_center_face=False,
            paste_back=True,
        )
        
        emit(90, "Saving result...")
        cv2.imwrite(output_path, output)
        
        del restorer
        torch.cuda.empty_cache()
        
        emit(100, "Done", output=output_path)
        return True
        
    except torch.cuda.OutOfMemoryError:
        emit(-1, "GPU out of memory")
        return False
    except Exception as e:
        emit(-1, f"Face restore error: {e}")
        return False


def enhance_full(input_path: str, output_path: str, models_dir: Path) -> bool:
    """Full pipeline: 4x upscale + face restore."""
    try:
        emit(5, "Loading models for full enhancement...")
        
        import torch
        import cv2
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
        from gfpgan import GFPGANer
        
        # 1. Setup Real-ESRGAN
        esrgan_path = models_dir / 'RealESRGAN_x4plus.pth'
        gfpgan_path = models_dir / 'GFPGANv1.4.pth'
        
        if not esrgan_path.exists():
            emit(-1, f"Model not found: {esrgan_path}")
            return False
        if not gfpgan_path.exists():
            emit(-1, f"Model not found: {gfpgan_path}")
            return False
        
        emit(10, "Initializing Real-ESRGAN 4x...")
        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        upsampler = RealESRGANer(
            scale=4,
            model_path=str(esrgan_path),
            model=model,
            tile=256,
            tile_pad=10,
            pre_pad=0,
            half=True,
            gpu_id=0,
        )
        
        # 2. Setup GFPGAN (with Real-ESRGAN as background upsampler)
        emit(20, "Initializing GFPGAN...")
        face_enhancer = GFPGANer(
            model_path=str(gfpgan_path),
            upscale=4,
            arch='clean',
            channel_multiplier=2,
            bg_upsampler=upsampler,
        )
        
        # 3. Process
        emit(30, "Reading input image...")
        img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            emit(-1, f"Cannot read image: {input_path}")
            return False
        
        emit(40, f"Full enhance: {img.shape[1]}x{img.shape[0]}...")
        
        _, _, output = face_enhancer.enhance(
            img,
            has_aligned=False,
            only_center_face=False,
            paste_back=True,
        )
        
        emit(85, "Saving result...")
        cv2.imwrite(output_path, output)
        
        # Cleanup
        del face_enhancer
        del upsampler
        torch.cuda.empty_cache()
        
        emit(100, "Done", output=output_path)
        return True
        
    except torch.cuda.OutOfMemoryError:
        emit(-1, "GPU out of memory — image may be too large for 'full' mode, try 'upscale_2x'")
        return False
    except Exception as e:
        emit(-1, f"Full enhance error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Image Enhancement Worker')
    parser.add_argument('--input', required=True, help='Input image path')
    parser.add_argument('--output', required=True, help='Output image path')
    parser.add_argument('--mode', required=True, 
                        choices=['upscale_2x', 'upscale_4x', 'face_restore', 'full'],
                        help='Enhancement mode')
    parser.add_argument('--models-dir', default=None, help='Models directory override')
    args = parser.parse_args()
    
    # Validate input
    if not Path(args.input).exists():
        emit(-1, f"Input file not found: {args.input}")
        sys.exit(1)
    
    # Ensure output directory exists
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    
    # Find models
    models_dir = Path(args.models_dir) if args.models_dir else find_models_dir()
    if not models_dir.exists():
        emit(-1, f"Models directory not found: {models_dir}")
        sys.exit(2)
    
    # Check CUDA
    try:
        import torch
        if not torch.cuda.is_available():
            emit(-1, "CUDA not available")
            sys.exit(3)
    except ImportError:
        emit(-1, "PyTorch not installed")
        sys.exit(3)
    
    # Run enhancement
    emit(0, f"Starting {args.mode} enhancement...")
    
    success = False
    if args.mode == 'upscale_2x':
        success = enhance_upscale(args.input, args.output, 2, models_dir)
    elif args.mode == 'upscale_4x':
        success = enhance_upscale(args.input, args.output, 4, models_dir)
    elif args.mode == 'face_restore':
        success = enhance_face(args.input, args.output, models_dir)
    elif args.mode == 'full':
        success = enhance_full(args.input, args.output, models_dir)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
