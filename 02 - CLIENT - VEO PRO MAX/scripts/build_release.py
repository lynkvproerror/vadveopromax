#!/usr/bin/env python3
"""
VEO Pro Max — Build Release Script v1.0
========================================

Compiles the Python application (folder 02) into a standalone
executable using Nuitka, then copies output to folder 03.

Usage:
    python scripts/build_release.py             # Full build
    python scripts/build_release.py --hash-only # Generate hashes only
    python scripts/build_release.py --check     # Check dependencies

Requirements:
    pip install nuitka ordered-set zstandard
    (Nuitka will auto-download a C compiler if needed — MinGW64)

Output:
    03 - Final App Client/
    ├── VEO_Pro_Max.exe          # Compiled binary
    ├── VEO_Pro_Max.dist/        # Dependencies
    ├── version.json             # Updated with build info
    ├── build_info.json          # SHA-256 hashes + metadata
    ├── CHANGELOG.md
    └── README.md
"""

import sys
import os
import json
import hashlib
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent  # 02 - CLIENT - VEO PRO MAX
OUTPUT_DIR = PROJECT_ROOT.parent / "03 - Final App Client"
MAIN_PY = PROJECT_ROOT / "main.py"


def check_dependencies() -> dict:
    """Check if all build dependencies are available."""
    results = {}

    # Python
    results['python'] = {
        'version': sys.version.split()[0],
        'ok': True,
    }

    # Nuitka
    try:
        import nuitka
        results['nuitka'] = {
            'version': getattr(nuitka, '__version__', 'unknown'),
            'ok': True,
        }
    except ImportError:
        results['nuitka'] = {'version': None, 'ok': False}

    # PySide6
    try:
        import PySide6
        results['pyside6'] = {
            'version': PySide6.__version__,
            'ok': True,
        }
    except ImportError:
        results['pyside6'] = {'version': None, 'ok': False}

    # C compiler
    has_compiler = False
    for compiler in ['cl.exe', 'gcc.exe', 'cc']:
        if shutil.which(compiler):
            results['c_compiler'] = {'name': compiler, 'ok': True}
            has_compiler = True
            break
    if not has_compiler:
        results['c_compiler'] = {
            'name': None, 'ok': False,
            'note': 'Nuitka will auto-download MinGW64 on first build',
        }

    return results


def generate_hashes() -> dict:
    """
    Generate SHA-256 hashes for all critical security files.
    Used to populate integrity_check.py CRITICAL_FILES dict in production.
    """
    security_dir = PROJECT_ROOT / "security"
    hashes = {}

    critical_files = [
        "security/license_client.py",
        "security/firebase_rest_client.py",
        "security/trial_protection.py",
        "security/_encrypted_keys.py",
        "security/_encrypted_api_keys.py",
        "security/permissions.py",
        "security/integrity_check.py",
        "security/anti_tamper.py",
    ]

    for rel_path in critical_files:
        filepath = PROJECT_ROOT / rel_path
        if filepath.exists():
            h = hashlib.sha256()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            hashes[rel_path] = h.hexdigest()
            print(f"  ✅ {rel_path}: {h.hexdigest()[:16]}...")
        else:
            print(f"  ⚠️ {rel_path}: NOT FOUND")

    return hashes


def generate_build_info(hashes: dict) -> dict:
    """Generate build metadata."""
    from config.constants import AppConstants

    return {
        "build_time": datetime.now().isoformat(),
        "app_version": AppConstants.APP_VERSION,
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "critical_file_hashes": hashes,
        "build_number": int(datetime.now().timestamp()),
    }


def run_nuitka_build():
    """Run Nuitka compilation."""
    print("\n🔨 Starting Nuitka compilation...")
    print(f"   Entry point: {MAIN_PY}")
    print(f"   Output: {OUTPUT_DIR}")

    # Nuitka command for PySide6 standalone app
    cmd = [
        sys.executable, "-m", "nuitka",

        # Output mode
        "--standalone",

        # Auto-accept downloads (MinGW64, ccache)
        "--assume-yes-for-downloads",

        # PySide6 plugin (auto-includes Qt DLLs)
        "--enable-plugin=pyside6",

        # Exclude heavy ML packages not needed by app
        "--nofollow-import-to=torch",
        "--nofollow-import-to=tensorflow",
        "--nofollow-import-to=numpy",
        "--nofollow-import-to=scipy",
        "--nofollow-import-to=matplotlib",
        "--nofollow-import-to=pandas",
        "--nofollow-import-to=cv2",
        "--nofollow-import-to=PIL",
        "--nofollow-import-to=sklearn",

        # Include packages that may not be auto-detected
        "--include-package=security",
        "--include-package=config",
        "--include-package=core",
        "--include-package=ui",
        "--include-package=services",
        "--include-package=utils",

        # Include data files
        "--include-data-dir=config/locales=config/locales",
        "--include-data-dir=assets=assets",
        "--include-data-dir=data=data",

        # Output name
        "--output-filename=VEO_Pro_Max.exe",

        # Output directory
        f"--output-dir={OUTPUT_DIR}",

        # Windows options
        "--windows-console-mode=disable",
        "--windows-icon-from-ico=assets/icon.ico" if (PROJECT_ROOT / "assets" / "icon.ico").exists() else "",

        # Performance
        "--jobs=4",

        # Remove build artifacts
        "--remove-output",

        # Entry point
        str(MAIN_PY),
    ]

    # Filter empty strings
    cmd = [c for c in cmd if c]

    print(f"\n   Command: {' '.join(cmd[:5])}...")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            check=True,
            # Stream output live
        )
        print("\n✅ Nuitka compilation successful!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Nuitka compilation FAILED (exit code {e.returncode})")
        return False
    except FileNotFoundError:
        print("\n❌ Nuitka not found. Install with: pip install nuitka")
        return False


def copy_release_files():
    """Copy release files to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        ("version.json", "version.json"),
        ("CHANGELOG.md", "CHANGELOG.md") if (OUTPUT_DIR / "CHANGELOG.md").exists() else None,
        ("README.md", "README.md") if (OUTPUT_DIR / "README.md").exists() else None,
    ]

    for item in files_to_copy:
        if item is None:
            continue
        src_name, dst_name = item
        src = PROJECT_ROOT / src_name
        dst = OUTPUT_DIR / dst_name
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  📄 Copied {src_name} → {dst_name}")


def main():
    parser = argparse.ArgumentParser(description="VEO Pro Max Build Script")
    parser.add_argument("--check", action="store_true", help="Check dependencies only")
    parser.add_argument("--hash-only", action="store_true", help="Generate hashes only")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Nuitka compilation")
    args = parser.parse_args()

    print("=" * 60)
    print("  VEO Pro Max — Build Release Script v1.0")
    print("=" * 60)

    # Step 1: Check deps
    print("\n📋 Checking dependencies...")
    deps = check_dependencies()
    all_ok = True
    for name, info in deps.items():
        status = "✅" if info['ok'] else "❌"
        version = info.get('version') or info.get('name') or 'missing'
        note = f" ({info['note']})" if 'note' in info else ""
        print(f"  {status} {name}: {version}{note}")
        if not info['ok'] and name != 'c_compiler':  # C compiler auto-downloads
            all_ok = False

    if args.check:
        sys.exit(0 if all_ok else 1)

    if not all_ok:
        print("\n❌ Missing dependencies. Install with:")
        if not deps.get('nuitka', {}).get('ok'):
            print("   pip install nuitka ordered-set zstandard")
        sys.exit(1)

    # Step 2: Generate hashes
    print("\n🔐 Generating file integrity hashes...")
    hashes = generate_hashes()

    # Step 3: Save build info
    sys.path.insert(0, str(PROJECT_ROOT))
    build_info = generate_build_info(hashes)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_info_path = OUTPUT_DIR / "build_info.json"
    with open(build_info_path, 'w') as f:
        json.dump(build_info, f, indent=2)
    print(f"\n📄 Build info saved: {build_info_path}")

    if args.hash_only:
        print("\n✅ Hash generation complete (--hash-only mode)")
        sys.exit(0)

    # Step 4: Nuitka compilation
    if not args.skip_compile:
        success = run_nuitka_build()
        if not success:
            sys.exit(1)
    else:
        print("\n⏭️ Skipping Nuitka compilation (--skip-compile)")

    # Step 5: Copy release files
    print("\n📦 Copying release files...")
    copy_release_files()

    # Step 5.5: Obfuscate and deploy extension
    print("\n🔒 Obfuscating and deploying extension...")
    try:
        from obfuscate_extension import process_extension
        ext_output = OUTPUT_DIR / "main.dist" / "extension"
        if process_extension(ext_output):
            print(f"  ✅ Extension deployed to: {ext_output}")
        else:
            print("  ⚠️ Extension deployment skipped (source not found)")
    except ImportError:
        # Fallback: try running as subprocess
        import subprocess
        ext_script = SCRIPT_DIR / "obfuscate_extension.py"
        if ext_script.exists():
            subprocess.run([sys.executable, str(ext_script)], cwd=str(PROJECT_ROOT))
        else:
            print("  ⚠️ obfuscate_extension.py not found")

    # Step 6: Update version.json with build info
    version_file = OUTPUT_DIR / "version.json"
    if version_file.exists():
        with open(version_file) as f:
            version_data = json.load(f)
        version_data['build_number'] = build_info['build_number']
        version_data['build_time'] = build_info['build_time']
        with open(version_file, 'w') as f:
            json.dump(version_data, f, indent=2)
        print(f"  📄 Updated version.json with build info")

    print("\n" + "=" * 60)
    print(f"  ✅ BUILD COMPLETE — Output: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
