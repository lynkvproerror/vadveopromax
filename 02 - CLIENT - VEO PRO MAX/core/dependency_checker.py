"""
VEO Pro Max - Dependency Checker

Checks and installs missing Python packages + Google Chrome
during startup. All subprocess calls run completely hidden
(no visible terminal window).
"""

import importlib
import logging
import os
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path
from typing import Callable, Optional, Tuple

log = logging.getLogger(__name__)

# ── Import name overrides (pip_name → import_name) ──
# Only needed when pip install name ≠ Python import name.
# All other packages: import name = pip_name.lower().replace("-", "_")
_IMPORT_NAME_MAP = {
    "PySide6": "PySide6",
    "Pillow": "PIL",
    "opencv-python": "cv2",
    "python-docx": "docx",
    "websocket-client": "websocket",
}


def _parse_requirements() -> list:
    """Parse requirements.txt → list of (pip_name, import_name).

    Single source of truth: just edit requirements.txt,
    startup auto-install picks it up automatically.
    Skips comments, blank lines, commented-out optional packages.
    """
    req_file = Path(__file__).resolve().parent.parent / "requirements.txt"
    if not req_file.exists():
        log.warning(f"[DependencyChecker] requirements.txt not found: {req_file}")
        return list(_IMPORT_NAME_MAP.items())

    packages = []
    try:
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Extract package name before version specifiers (>=, ==, <, ~=, [)
            pip_name = line.split(">=")[0].split("==")[0].split("<")[0].split("~=")[0].split("[")[0].strip()
            if not pip_name:
                continue
            import_name = _IMPORT_NAME_MAP.get(pip_name, pip_name.lower().replace("-", "_"))
            packages.append((pip_name, import_name))
    except Exception as e:
        log.error(f"[DependencyChecker] Failed to parse requirements.txt: {e}")
        return list(_IMPORT_NAME_MAP.items())

    return packages

# Google Chrome silent installer URL (Enterprise MSI — always latest stable)
CHROME_INSTALLER_URL = (
    "https://dl.google.com/chrome/install/googlechromestandaloneenterprise64.msi"
)


def _hidden_startupinfo() -> subprocess.STARTUPINFO:
    """Return STARTUPINFO that hides the console window completely."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return si


def _hidden_flags() -> int:
    """Return creation flags to hide the console window."""
    return subprocess.CREATE_NO_WINDOW


# ═══════════════════════════════════════════════════════════
#  1) Pip package checking + install
# ═══════════════════════════════════════════════════════════

def _is_package_installed(import_name: str) -> bool:
    """Check if a Python package is importable."""
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


def _install_pip_package(pip_name: str) -> bool:
    """Install a pip package silently. Returns True on success.
    
    NOTE: Skipped in compiled (Nuitka/frozen) mode — all packages
    are already bundled in the standalone binary.
    """
    # In compiled mode, pip install doesn't work (self-execution error)
    if getattr(sys, 'frozen', False) or '__compiled__' in dir():
        log.debug(f"  ⏭️ {pip_name}: skipped (compiled mode)")
        return False
    
    try:
        log.info(f"Installing {pip_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_name, "--quiet"],
            startupinfo=_hidden_startupinfo(),
            creationflags=_hidden_flags(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            log.info(f"  ✓ {pip_name} installed successfully")
            return True
        else:
            log.error(f"  ✗ {pip_name} install failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        log.error(f"  ✗ {pip_name} install error: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#  2) Google Chrome detection + install
# ═══════════════════════════════════════════════════════════

def _find_chrome_path() -> Optional[str]:
    """Detect Google Chrome installation on Windows.
    
    Checks:
    1. Windows Registry (App Paths)
    2. Common installation directories
    
    Returns path to chrome.exe if found, None otherwise.
    """
    # Method 1: Registry
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
    ]
    for hive, key_path in registry_keys:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                path, _ = winreg.QueryValueEx(key, "")
                if path and Path(path).exists():
                    return path
        except (OSError, FileNotFoundError):
            continue
    
    # Method 2: Common paths
    common_paths = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in common_paths:
        if p.exists():
            return str(p)
    
    return None


def _install_chrome(callback: Optional[Callable] = None) -> bool:
    """Download and silently install Google Chrome.
    
    Uses the Enterprise MSI installer for silent install support.
    Returns True on success.
    """
    try:
        # Download installer
        if callback:
            callback(55, "📥 Downloading Google Chrome...")
        
        temp_dir = tempfile.mkdtemp(prefix="veo_chrome_")
        msi_path = Path(temp_dir) / "chrome_installer.msi"
        
        log.info("Downloading Google Chrome installer...")
        
        # Use urllib (stdlib) to avoid dependency on requests/aiohttp
        import urllib.request
        urllib.request.urlretrieve(CHROME_INSTALLER_URL, str(msi_path))
        
        if not msi_path.exists() or msi_path.stat().st_size < 1_000_000:
            log.error("Chrome download failed or file too small")
            return False
        
        log.info(f"Chrome installer downloaded: {msi_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        # Silent install via msiexec
        if callback:
            callback(65, "⚙️ Installing Google Chrome...")
        
        log.info("Installing Chrome silently...")
        result = subprocess.run(
            ["msiexec", "/i", str(msi_path), "/quiet", "/norestart"],
            startupinfo=_hidden_startupinfo(),
            creationflags=_hidden_flags(),
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        # Cleanup installer
        try:
            msi_path.unlink(missing_ok=True)
            Path(temp_dir).rmdir()
        except Exception:
            pass
        
        if result.returncode == 0:
            log.info("  ✓ Google Chrome installed successfully")
            return True
        else:
            log.error(f"  ✗ Chrome install failed (code {result.returncode}): {result.stderr[:200]}")
            return False
            
    except Exception as e:
        log.error(f"  ✗ Chrome install error: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════

def ensure_critical_deps():
    """Check PySide6 before any Qt import. Called at very start of main.py.
    
    If PySide6 is missing, install it silently (no splash available yet).
    """
    if not _is_package_installed("PySide6"):
        log.warning("[DependencyChecker] PySide6 not found — installing...")
        _install_pip_package("PySide6")


def check_all_dependencies(callback: Optional[Callable] = None):
    """Check and install all missing dependencies.
    
    Called after splash is visible. Progress is reported via callback(percent, status).
    
    Progress layout:
      0-60%  → pip packages
      60-100% → Google Chrome
    
    Note: Playwright Chromium driver is NOT needed — app uses channel="chrome"
    which controls the real Chrome installation via CDP. The playwright pip
    package (API library) is included in REQUIRED_PACKAGES above.
    
    Args:
        callback: func(percent: int, status: str) to update splash progress
    """
    log.info("=== Dependency Check ===")
    
    # ── Phase 1: pip packages (0-60%) ──
    missing_packages = []
    for pip_name, import_name in _parse_requirements():
        if not _is_package_installed(import_name):
            missing_packages.append(pip_name)
    
    if missing_packages:
        step_size = 60 // max(len(missing_packages), 1)
        for i, pip_name in enumerate(missing_packages):
            pct = int(i * step_size)
            if callback:
                callback(pct, f"📦 Installing {pip_name}...")
            _install_pip_package(pip_name)
        log.info(f"  Installed {len(missing_packages)} missing package(s)")
    else:
        log.info("  All pip packages OK")
    
    if callback:
        callback(60, "✅ Python packages ready")
    
    # ── Phase 2: Google Chrome (60-100%) ──
    chrome_path = _find_chrome_path()
    if chrome_path:
        log.info(f"  Chrome found: {chrome_path}")
        if callback:
            callback(100, "✅ Google Chrome found")
    else:
        log.warning("  Chrome NOT found — installing...")
        success = _install_chrome(callback)
        if success:
            if callback:
                callback(100, "✅ Google Chrome installed")
        else:
            log.error("  Chrome installation failed — browser features may not work")
            if callback:
                callback(100, "⚠️ Chrome install failed")
    
    log.info("=== Dependency Check Complete ===")

