#!/usr/bin/env python3
"""
Build the Rust native security module (veo_security.pyd).

Usage:
    python scripts/build_rust_security.py          # Build + copy .pyd
    python scripts/build_rust_security.py --check  # Check Rust toolchain

Requirements:
    1. Install Rust: https://rustup.rs/
    2. pip install maturin
"""

import sys
import subprocess
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
RUST_DIR = PROJECT_ROOT / "rust_security"
SECURITY_DIR = PROJECT_ROOT / "security"


def check_rust():
    """Check if Rust toolchain is available."""
    checks = {}

    # rustc
    try:
        result = subprocess.run(['rustc', '--version'], capture_output=True, text=True, timeout=5)
        checks['rustc'] = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        checks['rustc'] = None

    # cargo
    try:
        result = subprocess.run(['cargo', '--version'], capture_output=True, text=True, timeout=5)
        checks['cargo'] = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        checks['cargo'] = None

    # maturin
    try:
        result = subprocess.run([sys.executable, '-m', 'maturin', '--version'], capture_output=True, text=True, timeout=5)
        checks['maturin'] = result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        checks['maturin'] = None

    return checks


def build():
    """Build the Rust module using maturin."""
    print("🔨 Building veo_security.pyd with maturin...")

    cmd = [
        sys.executable, "-m", "maturin", "build",
        "--release",
        "--manifest-path", str(RUST_DIR / "Cargo.toml"),
        "--out", str(RUST_DIR / "target" / "wheels"),
    ]

    result = subprocess.run(cmd, cwd=str(RUST_DIR))

    if result.returncode != 0:
        print("❌ Build failed!")
        sys.exit(1)

    # Find the built .pyd file
    wheel_dir = RUST_DIR / "target" / "wheels"
    pyd_files = list(wheel_dir.rglob("*.pyd")) + list(wheel_dir.rglob("*.so"))

    if pyd_files:
        pyd = pyd_files[0]
        dest = SECURITY_DIR / pyd.name
        shutil.copy2(pyd, dest)
        print(f"✅ Copied {pyd.name} → security/")
    else:
        # Try maturin develop instead (installs directly)
        print("📦 Trying maturin develop (install to site-packages)...")
        cmd2 = [
            sys.executable, "-m", "maturin", "develop",
            "--release",
            "--manifest-path", str(RUST_DIR / "Cargo.toml"),
        ]
        result2 = subprocess.run(cmd2, cwd=str(RUST_DIR))
        if result2.returncode == 0:
            print("✅ Module installed to Python paths")
        else:
            print("❌ maturin develop also failed")
            sys.exit(1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build Rust security module")
    parser.add_argument("--check", action="store_true", help="Check toolchain only")
    args = parser.parse_args()

    print("=" * 50)
    print("  VEO Security — Rust Module Builder")
    print("=" * 50)

    print("\n📋 Checking Rust toolchain...")
    checks = check_rust()
    all_ok = True
    for name, version in checks.items():
        status = "✅" if version else "❌"
        print(f"  {status} {name}: {version or 'NOT FOUND'}")
        if not version:
            all_ok = False

    if not all_ok:
        print("\n❌ Missing dependencies:")
        if not checks['rustc']:
            print("   Install Rust: https://rustup.rs/")
        if not checks['maturin']:
            print("   pip install maturin")
        if args.check:
            sys.exit(1)
        else:
            print("\n⚠️ Skipping build — install dependencies first")
            sys.exit(1)

    if args.check:
        print("\n✅ All dependencies available")
        sys.exit(0)

    build()


if __name__ == "__main__":
    main()
