#!/usr/bin/env python3
"""
VEO Pro Max — macOS Build Release Script v1.0
================================================

Compiles the Python application (folder 04 - MAC) into a standalone
macOS .app bundle using Nuitka, then organizes output to folder 04.2.

Usage:
    python build_release_macos.py             # Full build (standalone .app)
    python build_release_macos.py --hash-only # Generate hashes only
    python build_release_macos.py --check     # Check dependencies
    python build_release_macos.py --dmg       # Also create .dmg installer

Requirements:
    pip install nuitka ordered-set zstandard
    Xcode Command Line Tools: xcode-select --install

Output:
    04.2 - macOS final build/
    ├── VEO_Pro_Max.app/              # macOS App Bundle
    │   └── Contents/
    │       ├── MacOS/VEO_Pro_Max     # Native binary
    │       ├── Resources/            # Icons, assets
    │       └── Frameworks/           # Bundled .dylib
    ├── VEO_Pro_Max_v{VER}_macOS.zip  # Distribution ZIP
    ├── VEO_Pro_Max_v{VER}_macOS.dmg  # (optional) DMG installer
    ├── version.json
    └── build_info.json
"""

import sys
import os
import json
import hashlib
import shutil
import subprocess
import argparse
import platform
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════
#  Paths
# ═══════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent  # #NEW VEO API
PROJECT_ROOT = BASE_DIR / "04 - MAC"
OUTPUT_DIR = BASE_DIR / "04.2 - macOS final build"
MAIN_PY = PROJECT_ROOT / "main.py"

# GitHub config (same as Windows — shared public repo)
GITHUB_REPO = "lynkvproerror/vadveopromax"

# Fix encoding
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


# ═══════════════════════════════════════════════════════════
#  1) Dependency Check
# ═══════════════════════════════════════════════════════════

def check_dependencies() -> dict:
    """Check if all macOS build dependencies are available."""
    results = {}

    # Python
    results['python'] = {
        'version': sys.version.split()[0],
        'ok': True,
    }

    # Architecture
    arch = platform.machine()
    results['architecture'] = {
        'value': arch,
        'ok': arch in ('arm64', 'x86_64'),
        'note': 'arm64 (Apple Silicon) or x86_64 (Intel)',
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

    # C compiler (clang from Xcode)
    has_compiler = False
    for compiler in ['clang', 'gcc', 'cc']:
        if shutil.which(compiler):
            results['c_compiler'] = {'name': compiler, 'ok': True}
            has_compiler = True
            break
    if not has_compiler:
        results['c_compiler'] = {
            'name': None, 'ok': False,
            'note': 'Install: xcode-select --install',
        }

    # Xcode Command Line Tools
    xcode_ok = False
    try:
        r = subprocess.run(
            ['xcode-select', '-p'],
            capture_output=True, text=True, timeout=5,
        )
        xcode_ok = r.returncode == 0
    except Exception:
        pass
    results['xcode_clt'] = {
        'ok': xcode_ok,
        'note': 'xcode-select --install' if not xcode_ok else '',
    }

    # codesign (for optional signing)
    results['codesign'] = {
        'ok': shutil.which('codesign') is not None,
        'note': 'Required for app signing (optional for dev builds)',
    }

    return results


# ═══════════════════════════════════════════════════════════
#  2) Hash Generation
# ═══════════════════════════════════════════════════════════

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


def inject_integrity_hashes(hashes: dict) -> bool:
    """Inject computed hashes into integrity_check.py BEFORE Nuitka compile."""
    target = PROJECT_ROOT / "security" / "integrity_check.py"
    backup = target.with_suffix('.py.bak')

    if not target.exists():
        print("  [SKIP] integrity_check.py not found")
        return False

    shutil.copy2(target, backup)

    lines = []
    for path, hash_val in hashes.items():
        lines.append(f'    "{path}": "{hash_val}",')
    dict_content = "{\n" + "\n".join(lines) + "\n}"

    source = target.read_text(encoding='utf-8')

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
    """Restore original integrity_check.py after compile."""
    target = PROJECT_ROOT / "security" / "integrity_check.py"
    backup = target.with_suffix('.py.bak')
    if backup.exists():
        shutil.copy2(backup, target)
        backup.unlink()
        print("  [OK] Restored original integrity_check.py")


# ═══════════════════════════════════════════════════════════
#  3) Version Helpers
# ═══════════════════════════════════════════════════════════

def _read_app_version() -> str:
    """Read APP_VERSION from constants.py without importing."""
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
        "platform": "macOS",
        "architecture": platform.machine(),
        "macos_version": platform.mac_ver()[0],
        "critical_file_hashes": hashes,
        "build_number": int(datetime.now().timestamp()),
    }


# ═══════════════════════════════════════════════════════════
#  4) Nuitka Compilation
# ═══════════════════════════════════════════════════════════

def run_nuitka_build():
    """Run Nuitka compilation for macOS .app bundle."""
    print(f"\n[BUILD] Starting Nuitka compilation (macOS standalone)...")
    print(f"   Entry point: {MAIN_PY}")
    print(f"   Output: {OUTPUT_DIR}")
    print(f"   Architecture: {platform.machine()}")

    cmd = [
        sys.executable, "-m", "nuitka",

        # Standalone mode (macOS .app bundle)
        "--standalone",

        # ═══ macOS-specific ═══
        "--macos-create-app-bundle",
        "--macos-app-name=VEO Pro Max",
        f"--macos-app-version={_read_app_version()}",
        "--macos-app-mode=gui",

        # Auto-accept downloads
        "--assume-yes-for-downloads",

        # PySide6 plugin
        "--enable-plugin=pyside6",

        # Exclude heavy ML packages not needed
        "--nofollow-import-to=torch",
        "--nofollow-import-to=tensorflow",
        "--nofollow-import-to=numpy",
        "--nofollow-import-to=scipy",
        "--nofollow-import-to=matplotlib",
        "--nofollow-import-to=pandas",
        "--nofollow-import-to=cv2",
        "--nofollow-import-to=sklearn",

        # Exclude unused packages
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

        # Output
        f"--output-dir={OUTPUT_DIR}",

        # Product info
        "--product-name=VEO Pro Max",
        f"--product-version={_read_app_version()}",
        "--company-name=VEO Studio",
        "--file-description=VEO Pro Max - AI Video Generator",
        "--copyright=Copyright 2026 VEO Studio",

        # Performance + anti-reverse
        "--jobs=4",
        "--lto=yes",

        # Remove build artifacts
        "--remove-output",

        # Entry point
        str(MAIN_PY),
    ]

    # macOS icon (.icns format)
    icon_path = PROJECT_ROOT / "assets" / "icon.icns"
    if icon_path.exists():
        cmd.insert(-1, f"--macos-app-icon={icon_path}")
    else:
        # Try to convert from .ico if .icns doesn't exist
        ico_path = PROJECT_ROOT / "assets" / "icon.ico"
        if ico_path.exists():
            print(f"  [WARN] .icns not found, using .ico (may not work)")
            # Nuitka may handle ico → icns conversion
            cmd.insert(-1, f"--macos-app-icon={ico_path}")

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


# ═══════════════════════════════════════════════════════════
#  5) Post-Build: Organize & Deploy
# ═══════════════════════════════════════════════════════════

def organize_app_bundle():
    """Post-build: Copy extension and data into .app bundle Resources."""
    app_bundle = OUTPUT_DIR / "VEO_Pro_Max.app"
    if not app_bundle.exists():
        # Nuitka may create it as main.app
        alt = OUTPUT_DIR / "main.app"
        if alt.exists():
            alt.rename(app_bundle)
            print(f"  [OK] Renamed main.app → VEO_Pro_Max.app")
        else:
            print("  [WARN] .app bundle not found!")
            return

    resources = app_bundle / "Contents" / "Resources"
    resources.mkdir(parents=True, exist_ok=True)

    # Copy extension into Resources
    ext_src = PROJECT_ROOT / "extension"
    ext_dst = resources / "extension"
    if ext_src.exists() and not ext_dst.exists():
        shutil.copytree(ext_src, ext_dst)
        print(f"  [OK] Extension copied into .app bundle")

    print(f"  [OK] App bundle organized: {app_bundle}")


def fix_python_dylib():
    """Fix DYLD crash: copy Python framework dylib → .app/Contents/MacOS/Python.

    Nuitka links the compiled binary against @executable_path/Python (the Python
    framework dylib). On macOS, DYLD looks for it at:
        <.app>/Contents/MacOS/Python

    If that file is missing, the app crashes immediately on launch with:
        Termination Reason: DYLD, Code 1, Library not loaded: @executable_path/Python

    This function locates the active Python's shared library and copies it there.
    """
    import sysconfig

    app_bundle = OUTPUT_DIR / "VEO_Pro_Max.app"
    macos_dir = app_bundle / "Contents" / "MacOS"

    if not macos_dir.exists():
        print("  [SKIP] .app/Contents/MacOS not found")
        return

    dest = macos_dir / "Python"
    if dest.exists():
        print(f"  [OK] @executable_path/Python already present ({dest.stat().st_size // 1024} KB)")
        return

    # Strategy 1: sys.prefix/Python  (framework builds — most common on macOS)
    candidate = Path(sys.prefix) / "Python"
    if candidate.is_file():
        shutil.copy2(candidate, dest)
        dest.chmod(0o755)
        print(f"  [OK] Copied Python dylib (framework): {candidate}")
        return

    # Strategy 2: LIBDIR / LDLIBRARY
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    ldlib = sysconfig.get_config_var("LDLIBRARY") or ""
    candidate = Path(libdir) / ldlib
    if candidate.is_file():
        shutil.copy2(candidate, dest)
        dest.chmod(0o755)
        print(f"  [OK] Copied Python dylib (LDLIBRARY): {candidate}")
        return

    # Strategy 3: libpython{ver}.dylib / .so
    pyver = sysconfig.get_config_var("LDVERSION") or sysconfig.get_config_var("py_version_short")
    for ext in ("dylib", "so"):
        candidate = Path(libdir) / f"libpython{pyver}.{ext}"
        if candidate.is_file():
            shutil.copy2(candidate, dest)
            dest.chmod(0o755)
            print(f"  [OK] Copied Python dylib (libpython): {candidate}")
            return

    # Strategy 4: Walk sys.prefix looking for any Python/libpython*.dylib
    for root, dirs, files in os.walk(sys.prefix):
        for fname in files:
            if fname == "Python" or (fname.startswith("libpython") and fname.endswith("dylib")):
                candidate = Path(root) / fname
                shutil.copy2(candidate, dest)
                dest.chmod(0o755)
                print(f"  [OK] Copied Python dylib (walk): {candidate}")
                return

    print("  [WARN] Could not find Python dylib — app may crash with DYLD error on launch!")
    print(f"         sys.prefix={sys.prefix}")
    print(f"         LIBDIR={libdir}, LDLIBRARY={ldlib}")


def encrypt_workflow_data():
    """Encrypt workflow .md files in the dist output."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from encrypt_data import encrypt_directory
        
        # Find data dir in app bundle
        app_bundle = OUTPUT_DIR / "VEO_Pro_Max.app"
        data_dir = app_bundle / "Contents" / "Resources" / "data"
        
        if not data_dir.exists():
            # Try main.dist layout
            data_dir = OUTPUT_DIR / "main.dist" / "data"
        
        if data_dir.exists():
            count = encrypt_directory(data_dir)
            if count > 0:
                print(f"  [OK] {count} workflow files encrypted")
            else:
                print("  [SKIP] No .md files found in data/")
        else:
            print("  [SKIP] data/ directory not found in output")
    except ImportError:
        print("  [WARN] encrypt_data.py not found — shipping plaintext!")
    except Exception as e:
        print(f"  [ERR] Encryption failed: {e}")


def obfuscate_extension():
    """Obfuscate extension JS files."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from obfuscate_extension import process_extension
        
        app_bundle = OUTPUT_DIR / "VEO_Pro_Max.app"
        ext_dir = app_bundle / "Contents" / "Resources" / "extension"
        
        if not ext_dir.exists():
            ext_dir = OUTPUT_DIR / "main.dist" / "extension"
        
        if ext_dir.exists():
            if process_extension(ext_dir):
                print(f"  [OK] Extension obfuscated")
            else:
                print("  [SKIP] Extension obfuscation skipped")
        else:
            print("  [SKIP] extension/ not found in output")
    except ImportError:
        print("  [WARN] obfuscate_extension.py not found — shipping plain JS!")
    except Exception as e:
        print(f"  [ERR] Obfuscation failed: {e}")


# ═══════════════════════════════════════════════════════════
#  6) Code Signing (Optional)
# ═══════════════════════════════════════════════════════════

def codesign_app(identity: str = "-"):
    """Sign the .app bundle with a developer identity.
    
    Args:
        identity: "-" for ad-hoc signing (no Apple Developer account needed),
                  or "Developer ID Application: Your Name (TEAMID)" for distribution.
    """
    app_bundle = OUTPUT_DIR / "VEO_Pro_Max.app"
    if not app_bundle.exists():
        print("  [SKIP] .app not found for signing")
        return False

    print(f"  Signing with identity: {identity}")

    # Sign all frameworks first
    frameworks_dir = app_bundle / "Contents" / "Frameworks"
    if frameworks_dir.exists():
        for dylib in frameworks_dir.rglob("*.dylib"):
            subprocess.run(
                ["codesign", "--force", "--sign", identity,
                 "--timestamp", str(dylib)],
                capture_output=True,
            )
        for framework in frameworks_dir.rglob("*.framework"):
            subprocess.run(
                ["codesign", "--force", "--sign", identity,
                 "--timestamp", "--deep", str(framework)],
                capture_output=True,
            )

    # Sign the main app
    result = subprocess.run(
        ["codesign", "--force", "--sign", identity,
         "--timestamp", "--deep", "--options", "runtime",
         str(app_bundle)],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        print(f"  [OK] App signed successfully")
        return True
    else:
        print(f"  [WARN] Signing failed: {result.stderr}")
        return False


# ═══════════════════════════════════════════════════════════
#  7) Create Distribution Archives
# ═══════════════════════════════════════════════════════════

def create_release_zip(version: str):
    """Create release ZIP containing the .app bundle."""
    import zipfile

    app_bundle = OUTPUT_DIR / "VEO_Pro_Max.app"
    if not app_bundle.exists():
        print("  [ERR] VEO_Pro_Max.app not found")
        return None

    zip_path = OUTPUT_DIR / f"VEO_Pro_Max_v{version}_macOS.zip"
    if zip_path.exists():
        zip_path.unlink()

    file_count = 0
    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        for root_str, dirs, files in os.walk(str(app_bundle)):
            for f in files:
                fp = os.path.join(root_str, f)
                arcname = os.path.relpath(fp, str(OUTPUT_DIR))
                zf.write(fp, arcname)
                file_count += 1

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {zip_path.name}: {size_mb:.1f} MB ({file_count} files)")
    return zip_path


def create_extension_zip(ext_version: str):
    """Create extension-only ZIP (~50KB)."""
    import zipfile

    ext_dir = OUTPUT_DIR / "VEO_Pro_Max.app" / "Contents" / "Resources" / "extension"
    if not ext_dir.exists():
        ext_dir = PROJECT_ROOT / "extension"
    if not ext_dir.exists():
        print("  [SKIP] extension/ not found")
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


def create_dmg(version: str):
    """Create DMG installer (optional, requires hdiutil)."""
    app_bundle = OUTPUT_DIR / "VEO_Pro_Max.app"
    if not app_bundle.exists():
        print("  [SKIP] .app not found for DMG creation")
        return None

    dmg_path = OUTPUT_DIR / f"VEO_Pro_Max_v{version}_macOS.dmg"
    if dmg_path.exists():
        dmg_path.unlink()

    # Create temp directory for DMG contents
    import tempfile
    dmg_staging = Path(tempfile.mkdtemp(prefix="veo_dmg_"))

    try:
        # Copy .app to staging
        shutil.copytree(app_bundle, dmg_staging / "VEO Pro Max.app")

        # Create symlink to /Applications for drag-and-drop install
        os.symlink("/Applications", dmg_staging / "Applications")

        # Create DMG
        result = subprocess.run(
            ["hdiutil", "create", str(dmg_path),
             "-volname", "VEO Pro Max",
             "-srcfolder", str(dmg_staging),
             "-ov", "-format", "UDZO"],  # Compressed
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode == 0:
            size_mb = dmg_path.stat().st_size / (1024 * 1024)
            print(f"  [OK] {dmg_path.name}: {size_mb:.1f} MB")
            return dmg_path
        else:
            print(f"  [ERR] hdiutil failed: {result.stderr[:200]}")
            return None
    finally:
        shutil.rmtree(dmg_staging, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
#  8) Version JSON
# ═══════════════════════════════════════════════════════════

def generate_version_json(build_info: dict) -> dict:
    """Generate version.json with macOS-specific download URLs."""
    version = build_info["app_version"]
    ext_version = _read_extension_version()
    tag = f"v{version}"
    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/VEO_Pro_Max_v{version}_macOS.zip"
    ext_download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/VEO_Extension_v{ext_version}.zip"

    changelog_file = SCRIPT_DIR / "CHANGELOG.txt"
    changelog = ""
    if changelog_file.exists():
        changelog = changelog_file.read_text(encoding='utf-8').strip()
    if not changelog:
        changelog = f"VEO Pro Max v{version} for macOS"

    version_data = {
        "version": version,
        "ext_version": ext_version,
        "platform": "macOS",
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
    print(f"  platform: macOS ({platform.machine()})")

    return version_data


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="VEO Pro Max macOS Build Script")
    parser.add_argument("--check", action="store_true", help="Check dependencies only")
    parser.add_argument("--hash-only", action="store_true", help="Generate hashes only")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Nuitka compilation")
    parser.add_argument("--skip-sign", action="store_true", help="Skip code signing")
    parser.add_argument("--skip-publish", action="store_true", help="Skip ZIP + Git")
    parser.add_argument("--dmg", action="store_true", help="Create DMG installer")
    parser.add_argument("--sign-identity", default="-",
                        help='Code signing identity ("-" for ad-hoc)')
    args = parser.parse_args()

    print("=" * 60)
    print("  VEO Pro Max — macOS Build Release Script v1.0")
    print(f"  Architecture: {platform.machine()}")
    print(f"  macOS: {platform.mac_ver()[0]}")
    print("=" * 60)

    # ── Step 1: Check deps ──
    print("\n[1] Checking dependencies...")
    deps = check_dependencies()
    all_ok = True
    for name, info in deps.items():
        status = "OK" if info['ok'] else "MISSING"
        version = info.get('version') or info.get('value') or info.get('name') or 'N/A'
        note = f" ({info['note']})" if info.get('note') else ""
        print(f"  [{status}] {name}: {version}{note}")
        if not info['ok'] and name not in ('c_compiler', 'codesign'):
            all_ok = False

    if args.check:
        sys.exit(0 if all_ok else 1)

    if not all_ok:
        print("\n[FAIL] Missing dependencies:")
        if not deps.get('nuitka', {}).get('ok'):
            print("   pip install nuitka ordered-set zstandard")
        if not deps.get('xcode_clt', {}).get('ok'):
            print("   xcode-select --install")
        sys.exit(1)

    # ── Step 2: Generate hashes ──
    print("\n[2] Generating file integrity hashes...")
    hashes = generate_hashes()

    # ── Step 3: Save build info ──
    build_info = generate_build_info(hashes)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_info_path = OUTPUT_DIR / "build_info.json"
    with open(build_info_path, 'w', encoding='utf-8') as f:
        json.dump(build_info, f, indent=2)
    print(f"\n[3] Build info saved: {build_info_path}")

    if args.hash_only:
        print("\n[DONE] Hash generation complete (--hash-only mode)")
        sys.exit(0)

    # ── Step 3.5: Inject integrity hashes ──
    print("\n[3.5] Injecting integrity hashes into integrity_check.py...")
    hashes_injected = inject_integrity_hashes(hashes)

    # ── Step 4: Nuitka compilation ──
    if not args.skip_compile:
        success = run_nuitka_build()
        if not success:
            restore_integrity_check()
            sys.exit(1)
    else:
        print("\n[SKIP] Skipping Nuitka compilation (--skip-compile)")

    # ── Step 4.5: Restore integrity_check.py ──
    if hashes_injected:
        print("\n[4.5] Restoring original integrity_check.py...")
        restore_integrity_check()

    # ── Step 5: Organize .app bundle ──
    print("\n[5] Organizing .app bundle...")
    organize_app_bundle()

    # ── Step 5.1: Fix @executable_path/Python (DYLD crash prevention) ──
    print("\n[5.1] Fixing @executable_path/Python...")
    fix_python_dylib()

    # ── Step 5.5: Obfuscate extension ──
    print("\n[5.5] Obfuscating extension...")
    obfuscate_extension()

    # ── Step 5.8: Encrypt workflow data ──
    print("\n[5.8] Encrypting workflow data...")
    encrypt_workflow_data()

    # ── Step 6: Code signing ──
    if not args.skip_sign:
        print(f"\n[6] Code signing (identity: {args.sign_identity})...")
        codesign_app(args.sign_identity)
    else:
        print("\n[6] Skipping code signing (--skip-sign)")

    # ── Step 6.5: Generate version.json ──
    print("\n[6.5] Generating version.json...")
    generate_version_json(build_info)

    # ── Step 7: Create ZIPs ──
    if not args.skip_publish:
        version = build_info["app_version"]

        print(f"\n[7] Creating release archives...")
        zip_path = create_release_zip(version)
        ext_version = _read_extension_version()
        ext_zip_path = create_extension_zip(ext_version)

        # Update version.json with SHA-256
        if zip_path or ext_zip_path:
            version_path = OUTPUT_DIR / "version.json"
            if version_path.exists():
                vdata = json.loads(version_path.read_text(encoding="utf-8"))
                if zip_path:
                    sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
                    vdata["sha256"] = sha256
                    print(f"  [OK] version.json sha256: {sha256[:16]}...")
                if ext_zip_path:
                    ext_sha256 = hashlib.sha256(ext_zip_path.read_bytes()).hexdigest()
                    vdata["ext_sha256"] = ext_sha256
                else:
                    vdata["ext_download_url"] = ""
                    vdata["ext_sha256"] = ""
                version_path.write_text(
                    json.dumps(vdata, indent=4, ensure_ascii=False), encoding="utf-8"
                )

        # Optional DMG
        if args.dmg:
            print(f"\n[7.5] Creating DMG installer...")
            create_dmg(version)
    else:
        print("\n[SKIP] Steps 7+ skipped (--skip-publish)")

    print("\n" + "=" * 60)
    print(f"  [DONE] macOS BUILD COMPLETE — Output: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
