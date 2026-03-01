#!/usr/bin/env python3
"""
VEO Pro Max — Build Release Script v2.0
========================================

Compiles the Python application (folder 02) into a standalone
executable using Nuitka, then organizes output to folder 03.

Usage:
    python scripts/build_release.py             # Full build (standalone)
    python scripts/build_release.py --onefile   # Single exe (slower startup)
    python scripts/build_release.py --hash-only # Generate hashes only
    python scripts/build_release.py --check     # Check dependencies

Requirements:
    pip install nuitka ordered-set zstandard

Output (standalone mode):
    03 - Final App Client/
    +-- VEO_Pro_Max.exe              # Main executable
    +-- config/locales/              # Language files
    +-- assets/                      # Icons, images
    +-- data/                        # App data
    +-- extension/                   # Chrome extension
    +-- _internal/                   # All DLLs, .pyd, libs (clean!)
    +-- version.json
    +-- build_info.json

Output (onefile mode):
    03 - Final App Client/
    +-- VEO_Pro_Max.exe              # Single self-extracting exe
    +-- version.json
    +-- build_info.json
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

# Fix encoding for Vietnamese characters in constants
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


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
    """Generate SHA-256 hashes for all critical security files."""
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
            print(f"  OK {rel_path}: {h.hexdigest()[:16]}...")
        else:
            print(f"  WARN {rel_path}: NOT FOUND")

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


def run_nuitka_build(onefile: bool = False):
    """Run Nuitka compilation."""
    mode_str = "onefile" if onefile else "standalone"
    print(f"\n[BUILD] Starting Nuitka compilation ({mode_str})...")
    print(f"   Entry point: {MAIN_PY}")
    print(f"   Output: {OUTPUT_DIR}")

    cmd = [
        sys.executable, "-m", "nuitka",

        # Output mode
        "--onefile" if onefile else "--standalone",

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

        # Exclude unused packages (installed in env but not used by app)
        "--nofollow-import-to=customtkinter",
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=bcrypt",
        "--nofollow-import-to=zstandard",
        "--nofollow-import-to=firebase_admin",
        "--nofollow-import-to=google.cloud",
        "--nofollow-import-to=google.auth",
        "--nofollow-import-to=grpc",

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

        # Product info (shows in exe Properties > Details)
        "--product-name=VEO Pro Max",
        "--product-version=2.2.0",
        "--company-name=VEO Studio",
        "--file-description=VEO Pro Max - AI Video Generator",
        "--copyright=Copyright 2026 VEO Studio",

        # Performance
        "--jobs=4",

        # Remove build artifacts
        "--remove-output",

        # Entry point
        str(MAIN_PY),
    ]

    # Icon (conditional — copy to safe path to avoid Nuitka # parsing bug)
    icon_path = PROJECT_ROOT / "assets" / "icon.ico"
    if icon_path.exists():
        safe_icon = Path.home() / ".veoauto" / "icon.ico"
        safe_icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon_path, safe_icon)
        cmd.insert(-1, f"--windows-icon-from-ico={safe_icon}")

    # Filter empty strings
    cmd = [c for c in cmd if c]

    print(f"\n   Command: {' '.join(cmd[:5])}...")

    try:
        subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
        print("\n[OK] Nuitka compilation successful!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[FAIL] Nuitka compilation FAILED (exit code {e.returncode})")
        return False
    except FileNotFoundError:
        print("\n[FAIL] Nuitka not found. Install with: pip install nuitka")
        return False


def organize_dist_folder():
    """
    Post-build cleanup: hide runtime DLLs and library folders using
    Windows hidden attribute so Explorer only shows the main exe
    and user-facing data folders.

    NOTE: We do NOT move files — Nuitka requires DLLs at the same
    level as the exe. Instead we set Windows 'hidden' attribute.

    Visible in Explorer:
        VEO_Pro_Max.exe
        config/
        assets/
        extension/

    Hidden (still loadable by exe):
        python313.dll
        qt6core.dll
        PySide6/
        aiohttp/
        ...
    """
    dist_dir = OUTPUT_DIR / "main.dist"
    if not dist_dir.exists():
        print("  WARN main.dist not found, skipping cleanup")
        return

    # Items to keep VISIBLE (user-facing)
    KEEP_VISIBLE = {
        "VEO_Pro_Max.exe",
        "config",
        "assets",
        "data",
        "extension",
    }

    hidden_count = 0

    for item in sorted(dist_dir.iterdir()):
        if item.name in KEEP_VISIBLE:
            continue

        try:
            # Set Windows hidden attribute via attrib command
            subprocess.run(
                ["attrib", "+H", "+S", str(item)],
                capture_output=True, check=False
            )
            hidden_count += 1
        except Exception as e:
            print(f"  WARN Could not hide {item.name}: {e}")

    print(f"  [HIDDEN] {hidden_count} items marked as hidden in Explorer")

    # Print what user will see
    print(f"\n  User-visible in Explorer:")
    for item in sorted(dist_dir.iterdir()):
        if item.name in KEEP_VISIBLE:
            if item.is_dir():
                children = sum(1 for _ in item.rglob("*"))
                print(f"     [DIR]  {item.name}/ ({children} items)")
            else:
                size_mb = item.stat().st_size / (1024 * 1024)
                print(f"     [FILE] {item.name} ({size_mb:.1f} MB)")


def copy_release_files():
    """Copy release files to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files_to_copy = [("version.json", "version.json")]

    # Optional files
    for name in ["CHANGELOG.md", "README.md"]:
        src = PROJECT_ROOT / name
        if src.exists():
            files_to_copy.append((name, name))

    for src_name, dst_name in files_to_copy:
        src = PROJECT_ROOT / src_name
        dst = OUTPUT_DIR / dst_name
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  Copied {src_name} -> {dst_name}")


def main():
    parser = argparse.ArgumentParser(description="VEO Pro Max Build Script")
    parser.add_argument("--check", action="store_true", help="Check dependencies only")
    parser.add_argument("--hash-only", action="store_true", help="Generate hashes only")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Nuitka compilation")
    parser.add_argument("--onefile", action="store_true", help="Build single exe (slower startup)")
    parser.add_argument("--skip-organize", action="store_true", help="Skip post-build folder cleanup")
    args = parser.parse_args()

    print("=" * 60)
    print("  VEO Pro Max -- Build Release Script v2.0")
    print("=" * 60)

    # Step 1: Check deps
    print("\n[1] Checking dependencies...")
    deps = check_dependencies()
    all_ok = True
    for name, info in deps.items():
        status = "OK" if info['ok'] else "MISSING"
        version = info.get('version') or info.get('name') or 'missing'
        note = f" ({info['note']})" if 'note' in info else ""
        print(f"  [{status}] {name}: {version}{note}")
        if not info['ok'] and name != 'c_compiler':
            all_ok = False

    if args.check:
        sys.exit(0 if all_ok else 1)

    if not all_ok:
        print("\n[FAIL] Missing dependencies. Install with:")
        if not deps.get('nuitka', {}).get('ok'):
            print("   pip install nuitka ordered-set zstandard")
        sys.exit(1)

    # Step 2: Generate hashes
    print("\n[2] Generating file integrity hashes...")
    hashes = generate_hashes()

    # Step 3: Save build info
    sys.path.insert(0, str(PROJECT_ROOT))
    build_info = generate_build_info(hashes)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_info_path = OUTPUT_DIR / "build_info.json"
    with open(build_info_path, 'w') as f:
        json.dump(build_info, f, indent=2)
    print(f"\n[3] Build info saved: {build_info_path}")

    if args.hash_only:
        print("\n[DONE] Hash generation complete (--hash-only mode)")
        sys.exit(0)

    # Step 4: Nuitka compilation
    if not args.skip_compile:
        success = run_nuitka_build(onefile=args.onefile)
        if not success:
            sys.exit(1)
    else:
        print("\n[SKIP] Skipping Nuitka compilation (--skip-compile)")

    # Step 5: Copy release files
    print("\n[5] Copying release files...")
    copy_release_files()

    # Step 5.5: Obfuscate and deploy extension
    print("\n[5.5] Obfuscating and deploying extension...")
    try:
        from obfuscate_extension import process_extension
        ext_output = OUTPUT_DIR / "main.dist" / "extension"
        if process_extension(ext_output):
            print(f"  [OK] Extension deployed to: {ext_output}")
        else:
            print("  [SKIP] Extension deployment skipped (source not found)")
    except ImportError:
        ext_script = SCRIPT_DIR / "obfuscate_extension.py"
        if ext_script.exists():
            subprocess.run([sys.executable, str(ext_script)], cwd=str(PROJECT_ROOT))
        else:
            print("  [SKIP] obfuscate_extension.py not found")

    # Step 6: Organize dist folder (standalone only)
    if not args.onefile and not args.skip_organize:
        print("\n[6] Organizing build output...")
        organize_dist_folder()
    elif args.onefile:
        print("\n[6] Onefile mode -- no cleanup needed")

    # Step 7: Update version.json with build info
    version_file = OUTPUT_DIR / "version.json"
    if version_file.exists():
        with open(version_file) as f:
            version_data = json.load(f)
        version_data['build_number'] = build_info['build_number']
        version_data['build_time'] = build_info['build_time']
        with open(version_file, 'w') as f:
            json.dump(version_data, f, indent=2)
        print(f"  Updated version.json with build info")

    print("\n" + "=" * 60)
    print(f"  [DONE] BUILD COMPLETE -- Output: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
