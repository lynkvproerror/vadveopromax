#!/usr/bin/env python3
"""
VEO Pro Max — Build Release Script v2.0
========================================

Compiles the Python application (folder 02) into a standalone
executable using Nuitka, then organizes output to folder 03.

Usage:
    python build_release.py             # Full build (standalone)
    python build_release.py --onefile   # Single exe (slower startup)
    python build_release.py --hash-only # Generate hashes only
    python build_release.py --check     # Check dependencies

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
import tempfile
from pathlib import Path
from datetime import datetime

# Paths
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent  # #NEW VEO API
PROJECT_ROOT = BASE_DIR / "02 - CLIENT - VEO PRO MAX"
OUTPUT_DIR = BASE_DIR / "03 - Final App Client"
MAIN_PY = PROJECT_ROOT / "main.py"

# GitHub config (must match auto_updater.py)
GITHUB_REPO = "lynkvproerror/vadveopromax"

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


def inject_integrity_hashes(hashes: dict):
    """V1 FIX: Inject computed hashes into integrity_check.py BEFORE Nuitka compile.
    
    This patches the CRITICAL_FILES dict from {} to actual SHA-256 hashes.
    After Nuitka compile, call restore_integrity_check() to undo.
    """
    target = PROJECT_ROOT / "security" / "integrity_check.py"
    backup = target.with_suffix('.py.bak')
    
    if not target.exists():
        print("  [SKIP] integrity_check.py not found")
        return False
    
    # Backup original
    import shutil
    shutil.copy2(target, backup)
    
    # Build replacement dict literal
    lines = []
    for path, hash_val in hashes.items():
        lines.append(f'    "{path}": "{hash_val}",')
    dict_content = "{\n" + "\n".join(lines) + "\n}"
    
    # Read and replace the empty CRITICAL_FILES dict
    source = target.read_text(encoding='utf-8')
    
    # Pattern: CRITICAL_FILES: Dict[str, str] = {\n...\n}
    import re
    pattern = r'(CRITICAL_FILES:\s*Dict\[str,\s*str\]\s*=\s*)\{[^}]*\}'
    replacement = f'\\1{dict_content}'
    new_source, count = re.subn(pattern, replacement, source, flags=re.DOTALL)
    
    if count == 0:
        print("  [WARN] Could not find CRITICAL_FILES pattern to inject")
        backup.unlink(missing_ok=True)
        return False
    
    target.write_text(new_source, encoding='utf-8')
    print(f"  [OK] Injected {len(hashes)} hashes into integrity_check.py")
    return True


def restore_integrity_check():
    """Restore original integrity_check.py after Nuitka compile."""
    target = PROJECT_ROOT / "security" / "integrity_check.py"
    backup = target.with_suffix('.py.bak')
    if backup.exists():
        import shutil
        shutil.copy2(backup, target)
        backup.unlink()
        print("  [OK] Restored original integrity_check.py")


def sync_extension_version(app_version: str) -> bool:
    """[MANUAL USE ONLY] Sync extension manifest.json version with APP_VERSION.
    
    NOT used automatically in build pipeline — App and Extension versions
    are INDEPENDENT (see BUILD_RULES.md Rule #2b). Only bump manifest.json
    manually when extension code actually changes.
    """
    manifest = PROJECT_ROOT / "extension" / "manifest.json"
    backup = manifest.with_suffix('.json.bak')
    
    if not manifest.exists():
        print("  [SKIP] extension/manifest.json not found")
        return False
    
    import shutil
    shutil.copy2(manifest, backup)
    
    data = json.loads(manifest.read_text(encoding='utf-8'))
    old_ver = data.get('version', '0.0.0')
    
    if old_ver == app_version:
        print(f"  [OK] Extension version already synced: {app_version}")
        backup.unlink(missing_ok=True)
        return False  # No restore needed
    
    data['version'] = app_version
    manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"  [OK] Extension version synced: {old_ver} → {app_version}")
    return True


def restore_extension_manifest():
    """Restore original extension/manifest.json after compile."""
    manifest = PROJECT_ROOT / "extension" / "manifest.json"
    backup = manifest.with_suffix('.json.bak')
    if backup.exists():
        import shutil
        shutil.copy2(backup, manifest)
        backup.unlink()
        print("  [OK] Restored original extension/manifest.json")


def _read_app_version() -> str:
    """Read APP_VERSION from constants.py without importing (avoids encoding issues)."""
    import re
    constants_file = PROJECT_ROOT / "config" / "constants.py"
    text = constants_file.read_text(encoding='utf-8')
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else "0.0.0"


def _read_extension_version() -> str:
    """Read extension version from manifest.json."""
    manifest = PROJECT_ROOT / "extension" / "manifest.json"
    if not manifest.exists():
        return "0.0.0"
    data = json.loads(manifest.read_text(encoding='utf-8'))
    return data.get("version", "0.0.0")


def generate_build_info(hashes: dict) -> dict:
    """Generate build metadata."""
    return {
        "build_time": datetime.now().isoformat(),
        "app_version": _read_app_version(),
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
        # NOTE: Pillow (PIL) IS used by engine.py, media_handler.py, image_library.py
        # Do NOT exclude it!
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
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=test",

        # Include packages that may not be auto-detected
        "--include-package=security",
        "--include-package=config",
        "--include-package=core",
        "--include-package=ui",
        "--include-package=services",
        "--include-package=utils",

        # Include data files (non-Python resources)
        "--include-data-dir=config/locales=config/locales",
        "--include-data-dir=assets=assets",
        "--include-data-dir=data=data",
        "--include-data-dir=ui/img=ui/img",
        "--include-data-dir=extension=extension",
        "--include-data-dir=tools=tools",  # Bundle FFmpeg binaries (Rule #11)

        # Output name
        "--output-filename=VEO_Pro_Max.exe",

        # Output directory
        f"--output-dir={OUTPUT_DIR}",

        # Windows options
        "--windows-console-mode=disable",

        # Product info (shows in exe Properties > Details)
        "--product-name=VEO Pro Max",
        f"--product-version={_read_app_version()}",
        "--company-name=VEO Studio",
        "--file-description=VEO Pro Max - AI Video Generator",
        "--copyright=Copyright 2026 VEO Studio",

        # Performance + anti-reverse
        "--jobs=4",
        "--lto=yes",  # V6: Link-Time Optimization (harder to reverse engineer)

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
        "tools",  # FFmpeg bundled (Rule #11)
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
    """Copy optional release files (NOT version.json — that is auto-generated)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for name in ["CHANGELOG.md", "README.md"]:
        src = PROJECT_ROOT / name
        dst = OUTPUT_DIR / name
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  Copied {name}")


def generate_version_json(build_info: dict, changelog: str = "") -> dict:
    """Auto-generate version.json v2 with dual version tracking.

    Tracks both APP_VERSION and extension version independently.
    See BUILD_RULES.md Rule #2b for versioning convention.
    """
    version = build_info["app_version"]
    ext_version = _read_extension_version()
    tag = f"v{version}"  # GitHub tag based on app version
    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/VEO_Pro_Max_{tag}.zip"
    ext_download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/VEO_Extension_v{ext_version}.zip"

    # Read changelog from file if exists, otherwise use provided string
    changelog_file = SCRIPT_DIR / "CHANGELOG.txt"
    if changelog_file.exists():
        changelog = changelog_file.read_text(encoding='utf-8').strip()
    elif not changelog:
        changelog = f"VEO Pro Max v{version}"

    version_data = {
        "version": version,
        "ext_version": ext_version,
        "release_date": datetime.now().strftime("%Y-%m-%d"),
        "changelog": changelog,
        "download_url": download_url,
        "ext_download_url": ext_download_url,
        "sha256": "",
        "ext_sha256": "",
        "min_version": "1.0.0",
        "force_update": False,
        "build_number": build_info["build_number"],
        "build_time": build_info["build_time"],
    }

    version_path = OUTPUT_DIR / "version.json"
    with open(version_path, 'w', encoding='utf-8') as f:
        json.dump(version_data, f, indent=4, ensure_ascii=False)

    print(f"  app_version: {version}")
    print(f"  ext_version: {ext_version}")
    print(f"  download_url: {download_url}")
    print(f"  ext_download_url: {ext_download_url}")
    print(f"  changelog: {changelog[:80]}..." if len(changelog) > 80 else f"  changelog: {changelog}")

    return version_data


def main():
    parser = argparse.ArgumentParser(description="VEO Pro Max Build Script")
    parser.add_argument("--check", action="store_true", help="Check dependencies only")
    parser.add_argument("--hash-only", action="store_true", help="Generate hashes only")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Nuitka compilation")
    parser.add_argument("--onefile", action="store_true", help="Build single exe (slower startup)")
    parser.add_argument("--skip-organize", action="store_true", help="Skip post-build folder cleanup")
    parser.add_argument("--skip-publish", action="store_true", help="Skip ZIP + Git + GitHub release")
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
    with open(build_info_path, 'w', encoding='utf-8') as f:
        json.dump(build_info, f, indent=2)
    print(f"\n[3] Build info saved: {build_info_path}")

    if args.hash_only:
        print("\n[DONE] Hash generation complete (--hash-only mode)")
        sys.exit(0)

    # Step 3.5: Inject integrity hashes into source BEFORE compile
    print("\n[3.5] Injecting integrity hashes into integrity_check.py...")
    hashes_injected = inject_integrity_hashes(hashes)

    # NOTE: Extension version is INDEPENDENT from APP_VERSION (BUILD_RULES.md Rule #2b)
    # Bump manifest.json manually when extension code changes, NOT auto-synced.

    # Step 4: Nuitka compilation
    if not args.skip_compile:
        success = run_nuitka_build(onefile=args.onefile)
        if not success:
            restore_integrity_check()  # Restore even on failure
            sys.exit(1)
    else:
        print("\n[SKIP] Skipping Nuitka compilation (--skip-compile)")
    
    # Step 4.5: Restore original integrity_check.py (source stays clean)
    if hashes_injected:
        print("\n[4.5] Restoring original integrity_check.py...")
        restore_integrity_check()

    # Step 5: Copy optional release files + generate version.json
    print("\n[5] Copying release files...")
    copy_release_files()

    print("\n[5.1] Generating version.json (from APP_VERSION)...")
    generate_version_json(build_info)

    # Step 5.8: Encrypt workflow data (replace .md → .enc in dist)
    print("\n[5.8] Encrypting workflow data...")
    try:
        from encrypt_data import encrypt_directory
        data_dir = OUTPUT_DIR / "main.dist" / "data"
        if data_dir.exists():
            count = encrypt_directory(data_dir)
            if count > 0:
                print(f"  [OK] {count} workflow files encrypted")
            else:
                print("  [SKIP] No .md files found in data/")
        else:
            print("  [SKIP] data/ directory not found in dist")
    except ImportError:
        print("  [WARN] encrypt_data.py not found — shipping plaintext!")
    except Exception as e:
        print(f"  [ERR] Encryption failed: {e}")

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

    # ── Steps 7-9: ZIP + Git + GitHub Release ──
    if not args.skip_publish:
        version = build_info["app_version"]

        # Step 7: Create ZIPs (full + extension-only)
        print(f"\n[7] Creating release ZIPs...")
        zip_path = create_release_zip(version)
        ext_version = _read_extension_version()
        ext_zip_path = create_extension_zip(ext_version)

        if zip_path or ext_zip_path:
            # Update version.json with SHA-256 of both ZIPs
            version_path = OUTPUT_DIR / "version.json"
            if version_path.exists():
                vdata = json.loads(version_path.read_text(encoding="utf-8"))
                if zip_path:
                    sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
                    vdata["sha256"] = sha256
                    print(f"  [OK] version.json sha256 (full): {sha256[:16]}...")
                if ext_zip_path:
                    ext_sha256 = hashlib.sha256(ext_zip_path.read_bytes()).hexdigest()
                    vdata["ext_sha256"] = ext_sha256
                    print(f"  [OK] version.json ext_sha256: {ext_sha256[:16]}...")
                else:
                    # Extension ZIP not created → clear URL to prevent 404 on client
                    vdata["ext_download_url"] = ""
                    vdata["ext_sha256"] = ""
                    print("  [WARN] Extension ZIP not created — cleared ext_download_url")
                version_path.write_text(
                    json.dumps(vdata, indent=4, ensure_ascii=False), encoding="utf-8"
                )

        # Step 8: Git push
        print(f"\n[8] Git push to remote...")
        git_push_release(version)

        # Step 9: GitHub Release (upload both ZIPs)
        print(f"\n[9] Creating GitHub Release...")
        zip_files = [p for p in [zip_path, ext_zip_path] if p and p.exists()]
        if zip_files:
            github_create_release(version, zip_files)
        else:
            print("  [SKIP] No ZIP files to upload")

        # Step 9.5: Push version.json to PUBLIC repo (vadveopromax)
        # Origin = private repo (veo-pro-max), but clients fetch from PUBLIC repo.
        # Without this step, clients would never see the update!
        print(f"\n[9.5] Pushing version.json to PUBLIC repo (vadveopromax)...")
        push_version_to_public_repo()
    else:
        print("\n[SKIP] Steps 7-9 skipped (--skip-publish)")

    print("\n" + "=" * 60)
    print(f"  [DONE] BUILD + PUBLISH COMPLETE -- Output: {OUTPUT_DIR}")
    print("=" * 60)


# ═══════════════════════════════════════════════════════════
#  7) ZIP creation
# ═══════════════════════════════════════════════════════════

def create_release_zip(version: str):
    """Create full release ZIP from main.dist/ with VEO_Pro_Max/ root structure."""
    import zipfile

    dist_dir = OUTPUT_DIR / "main.dist"
    if not dist_dir.exists():
        print("  [ERR] main.dist/ not found")
        return None

    zip_path = OUTPUT_DIR / f"VEO_Pro_Max_v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    file_count = 0
    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        for root_str, dirs, files in os.walk(str(dist_dir)):
            for f in files:
                fp = os.path.join(root_str, f)
                arcname = 'VEO_Pro_Max/' + os.path.relpath(fp, str(dist_dir))
                zf.write(fp, arcname)
                file_count += 1

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {zip_path.name}: {size_mb:.1f} MB ({file_count} files)")
    return zip_path


def create_extension_zip(ext_version: str):
    """Create lightweight extension-only ZIP (~50KB).
    
    Used for extension-only updates — client downloads this small file
    instead of the full 67MB ZIP when only extension code changed.
    """
    import zipfile

    ext_dir = OUTPUT_DIR / "main.dist" / "extension"
    if not ext_dir.exists():
        print("  [SKIP] extension/ not found in main.dist")
        return None

    zip_path = OUTPUT_DIR / f"VEO_Extension_v{ext_version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    file_count = 0
    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        for root_str, dirs, files in os.walk(str(ext_dir)):
            for f in files:
                fp = os.path.join(root_str, f)
                arcname = 'extension/' + os.path.relpath(fp, str(ext_dir))
                zf.write(fp, arcname)
                file_count += 1

    size_kb = zip_path.stat().st_size / 1024
    print(f"  [OK] {zip_path.name}: {size_kb:.0f} KB ({file_count} files)")
    return zip_path


# ═══════════════════════════════════════════════════════════
#  8) Git push
# ═══════════════════════════════════════════════════════════

def git_push_release(version: str):
    """Git add, commit, push the output folder."""
    output_rel = "03 - Final App Client"

    if not shutil.which("git"):
        print("  [SKIP] git not found in PATH")
        return

    try:
        subprocess.run(
            ["git", "add", output_rel],
            cwd=str(BASE_DIR), check=True, capture_output=True
        )
        result = subprocess.run(
            ["git", "status", "--porcelain", output_rel],
            cwd=str(BASE_DIR), capture_output=True, text=True
        )
        if not result.stdout.strip():
            print("  [SKIP] No changes to commit")
            return

        subprocess.run(
            ["git", "commit", "-m", f"Release v{version}"],
            cwd=str(BASE_DIR), check=True, capture_output=True
        )
        print(f"  [OK] Committed: Release v{version}")

        print("  Pushing to remote...")
        result = subprocess.run(
            ["git", "push"],
            cwd=str(BASE_DIR), capture_output=True, text=True, timeout=600
        )
        if result.returncode == 0:
            print("  [OK] Pushed to remote")
        else:
            print(f"  [WARN] Push issue: {result.stderr[:200]}")
    except Exception as e:
        print(f"  [ERR] Git error: {e}")


# ═══════════════════════════════════════════════════════════
#  9) GitHub Release
# ═══════════════════════════════════════════════════════════

def github_create_release(version: str, zip_files: list):
    """Create GitHub release via gh CLI or print manual instructions.
    
    Args:
        version: App version string
        zip_files: List of Path objects to upload as release assets
    """
    tag = f"v{version}"
    changelog = ""
    changelog_file = SCRIPT_DIR / "CHANGELOG.txt"
    if changelog_file.exists():
        changelog = changelog_file.read_text(encoding="utf-8").strip()

    if shutil.which("gh"):
        try:
            cmd = [
                "gh", "release", "create", tag,
                "--repo", GITHUB_REPO,
                "--title", f"VEO Pro Max {tag}",
                "--notes", changelog or f"VEO Pro Max {tag}",
            ] + [p.name for p in zip_files]
            result = subprocess.run(
                cmd, cwd=str(OUTPUT_DIR),
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                names = ', '.join(p.name for p in zip_files)
                print(f"  [OK] Release {tag} created + uploaded: {names}")
                return
            else:
                print(f"  [WARN] gh failed: {result.stderr[:200]}")
        except Exception as e:
            print(f"  [WARN] gh error: {e}")

    # Fallback: manual instructions
    assets = ' '.join(f'"{p}"' for p in zip_files)
    print(f"\n  ┌─────────────────────────────────────────┐")
    print(f"  │  MANUAL: gh CLI not found                │")
    print(f"  │  Install: winget install GitHub.cli       │")
    print(f"  │  Login:   gh auth login                   │")
    print(f"  └─────────────────────────────────────────┘")
    print(f"  gh release create {tag} --title \"VEO Pro Max {tag}\" \\")
    print(f"    --notes-file \"{changelog_file}\" {assets}")
    print(f"")
    print(f"  Or: https://github.com/{GITHUB_REPO}/releases/new?tag={tag}")


# ═══════════════════════════════════════════════════════════
#  9.5) Push version.json to PUBLIC repo
# ═══════════════════════════════════════════════════════════

def push_version_to_public_repo():
    """Push version.json to the PUBLIC distribution repo (vadveopromax).
    
    The private repo (origin=veo-pro-max) and public repo (vadveopromax)
    have UNRELATED git histories, so normal `git push` won't work.
    Instead, use GitHub Contents API via `gh` CLI to update the file.
    
    This is CRITICAL: without this, clients will never see the update!
    """
    version_path = OUTPUT_DIR / "version.json"
    if not version_path.exists():
        print("  [SKIP] version.json not found in output")
        return
    
    if not shutil.which("gh"):
        print("  [WARN] gh CLI not found — update version.json on vadveopromax manually!")
        print(f"  File: {version_path}")
        return
    
    try:
        import base64
        
        # Read local version.json content
        content_bytes = version_path.read_bytes()
        content_b64 = base64.b64encode(content_bytes).decode("ascii")
        
        # Get current file SHA from public repo (required for update)
        result = subprocess.run(
            ["gh", "api", f"repos/{GITHUB_REPO}/contents/version.json",
             "--jq", ".sha"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "GH_PROMPT_DISABLED": "true"},
        )
        
        if result.returncode != 0:
            print(f"  [ERR] Cannot get current SHA: {result.stderr[:100]}")
            return
        
        current_sha = result.stdout.strip()
        
        # Read version for commit message
        vdata = json.loads(content_bytes.decode("utf-8"))
        version = vdata.get("version", "?")
        
        # Build API request body
        body = json.dumps({
            "message": f"Update version.json to v{version}",
            "content": content_b64,
            "sha": current_sha,
        })
        
        # Write body to temp file (avoid shell escaping issues)
        body_path = os.path.join(tempfile.gettempdir(), "gh_version_body.json")
        with open(body_path, "w", encoding="utf-8") as f:
            f.write(body)
        
        # Update via GitHub Contents API
        result = subprocess.run(
            ["gh", "api", f"repos/{GITHUB_REPO}/contents/version.json",
             "--method", "PUT",
             "--input", body_path,
             "--jq", ".commit.sha"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "GH_PROMPT_DISABLED": "true"},
        )
        
        # Cleanup temp file
        try:
            os.unlink(body_path)
        except Exception:
            pass
        
        if result.returncode == 0:
            commit_sha = result.stdout.strip()[:12]
            print(f"  [OK] version.json v{version} pushed to {GITHUB_REPO} (commit: {commit_sha})")
        else:
            print(f"  [ERR] API update failed: {result.stderr[:200]}")
            print(f"  Manual: update version.json at https://github.com/{GITHUB_REPO}")
            
    except Exception as e:
        print(f"  [ERR] Push to public repo failed: {e}")
        print(f"  Manual: copy {version_path} to https://github.com/{GITHUB_REPO}")


if __name__ == "__main__":
    main()

