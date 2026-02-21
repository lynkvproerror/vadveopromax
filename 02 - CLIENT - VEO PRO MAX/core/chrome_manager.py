"""
VEO Pro Max — Persistent Chrome Manager

Manages Chrome processes that survive app restarts.
Launch via subprocess.Popen (DETACHED_PROCESS), reconnect via CDP port.

PID file: {profile_path}/.chrome_pid.json
CDP endpoint: http://127.0.0.1:{port}
"""

import json
import logging
import os
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional, Dict, List, Any

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

CDP_PORT_BASE = 9222
CDP_PORT_MAX = 9250
PID_FILE_NAME = ".chrome_pid.json"
CHROME_STARTUP_TIMEOUT = 30  # seconds to wait for CDP port to respond (30s for cold boot)


# ── Chrome for Testing (CfT) ───────────────────────────────────────────
# Chrome branded builds (137+) removed --load-extension flag.
# CfT is an official Google binary that supports --load-extension.
# We auto-download CfT on first launch and prefer it over branded Chrome.

CFT_API_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
CFT_PLATFORM = "win64"


def _get_cft_dir() -> Path:
    """Get the Chrome for Testing directory (inside app dir)."""
    return Path(__file__).resolve().parent.parent / "chrome-for-testing"


def _find_cft_exe() -> Optional[str]:
    """Find Chrome for Testing executable if already downloaded."""
    cft_dir = _get_cft_dir()
    # CfT zip extracts to chrome-win64/chrome.exe
    candidate = cft_dir / "chrome-win64" / "chrome.exe"
    if candidate.exists():
        return str(candidate)
    # Also check direct location
    candidate2 = cft_dir / "chrome.exe"
    if candidate2.exists():
        return str(candidate2)
    return None


_cft_download_lock = threading.Lock()  # Prevent concurrent downloads


def download_chrome_for_testing(progress_callback=None) -> Optional[str]:
    """Download Chrome for Testing from Google's API.
    
    Thread-safe: uses a lock to prevent concurrent downloads.
    Downloads the latest stable CfT binary, extracts it, and returns
    the path to the chrome.exe executable.
    
    Args:
        progress_callback: Optional callable(message: str) for progress updates.
        
    Returns:
        Path to chrome.exe if successful, None on failure.
    """
    # Check if already downloaded (fast path, no lock needed)
    existing = _find_cft_exe()
    if existing:
        log.info(f"[ChromeManager] CfT already downloaded: {existing}")
        return existing
    
    # Acquire lock — only one thread downloads at a time
    with _cft_download_lock:
        # Re-check after acquiring lock (another thread may have finished)
        existing = _find_cft_exe()
        if existing:
            log.info(f"[ChromeManager] CfT downloaded by another thread: {existing}")
            return existing
        
        return _do_cft_download(progress_callback)


def _do_cft_download(progress_callback=None) -> Optional[str]:
    """Internal: perform the actual CfT download (called under lock)."""
    import zipfile
    import io
    
    cft_dir = _get_cft_dir()
    
    def _progress(msg):
        log.info(f"[ChromeManager] {msg}")
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass
    
    try:
        # Step 1: Get download URL from API
        _progress("📥 Downloading Chrome for Testing (first-time setup)...")
        req = urllib.request.Request(CFT_API_URL, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            api_data = json.loads(resp.read().decode())
        
        stable = api_data.get("channels", {}).get("Stable", {})
        version = stable.get("version", "unknown")
        downloads = stable.get("downloads", {}).get("chrome", [])
        
        download_url = None
        for d in downloads:
            if d.get("platform") == CFT_PLATFORM:
                download_url = d.get("url")
                break
        
        if not download_url:
            _progress(f"❌ No CfT download for platform {CFT_PLATFORM}")
            return None
        
        _progress(f"📥 Downloading Chrome for Testing v{version} ({CFT_PLATFORM})...")
        
        # Step 2: Download the zip with progress
        req = urllib.request.Request(download_url, method="GET")
        with urllib.request.urlopen(req, timeout=300) as resp:
            content_length = resp.headers.get("Content-Length")
            total_mb = int(content_length) / (1024 * 1024) if content_length else 0
            
            chunks = []
            downloaded = 0
            last_report = 0
            chunk_size = 65536  # 64KB chunks
            
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                downloaded += len(chunk)
                downloaded_mb = downloaded / (1024 * 1024)
                
                # Report progress every 5MB
                if downloaded_mb - last_report >= 5:
                    last_report = downloaded_mb
                    if total_mb > 0:
                        pct = min(99, int(downloaded_mb / total_mb * 100))
                        _progress(f"📥 Downloading... {downloaded_mb:.0f}/{total_mb:.0f} MB ({pct}%)")
                    else:
                        _progress(f"📥 Downloading... {downloaded_mb:.0f} MB")
            
            zip_data = b"".join(chunks)
        
        size_mb = len(zip_data) / (1024 * 1024)
        _progress(f"📦 Downloaded {size_mb:.1f} MB, extracting...")
        
        # Step 3: Extract
        cft_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            zf.extractall(str(cft_dir))
        
        # Step 4: Verify
        exe_path = _find_cft_exe()
        if exe_path:
            _progress(f"✅ Chrome for Testing v{version} installed: {exe_path}")
            # Save version info
            (cft_dir / "version.txt").write_text(version, encoding="utf-8")
            return exe_path
        else:
            _progress("❌ Extraction succeeded but chrome.exe not found")
            return None
        
    except Exception as e:
        _progress(f"❌ CfT download failed: {type(e).__name__}: {e}")
        log.error(f"[ChromeManager] CfT download error: {e}")
        return None


def find_chrome_exe() -> Optional[str]:
    """Locate Chrome for Testing executable.
    
    Chrome for Testing (CfT) is the ONLY supported browser.
    CfT supports --load-extension (required for Extension Bridge).
    Chrome branded v137+ removed this flag — NOT supported.
    CfT is auto-downloaded on first launch if not present.
    """
    # 1. Check if CfT is already downloaded
    cft = _find_cft_exe()
    if cft:
        return cft
    
    # 2. Try auto-download CfT (requires internet on first run)
    cft = download_chrome_for_testing()
    if cft:
        return cft
    
    # 3. No CfT available — clear error (no Chrome branded fallback)
    log.error(
        "[ChromeManager] ❌ Chrome for Testing not found and auto-download failed. "
        "Please ensure internet connection for first-time setup, "
        "or manually place CfT in: " + str(_get_cft_dir())
    )
    return None


# ── Port allocation ─────────────────────────────────────────────────────

def _is_port_free(port: int) -> bool:
    """Check if a TCP port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def _is_cdp_alive(port: int) -> bool:
    """Check if a CDP endpoint is responding on the given port."""
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/version", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


# Track ports allocated within this process to prevent race conditions
# when multiple Chrome launches happen in rapid succession
_allocated_ports: set = set()


def allocate_port(base: int = CDP_PORT_BASE, max_port: int = CDP_PORT_MAX) -> int:
    """Find a free CDP port in the range [base, max_port].
    
    Skips ports that are already serving CDP (owned by another Chrome)
    AND ports already allocated in this session (not yet bound by Chrome).
    
    Raises:
        RuntimeError: If no free port found in range.
    """
    for port in range(base, max_port + 1):
        if port in _allocated_ports:
            continue  # Already given out this session
        if _is_port_free(port):
            _allocated_ports.add(port)
            return port
        # Port occupied — might be our old Chrome, skip
    raise RuntimeError(f"No free CDP port in range {base}-{max_port}")


# ── PID file I/O ────────────────────────────────────────────────────────

def _pid_file_path(profile_path: str) -> Path:
    return Path(profile_path) / PID_FILE_NAME


def _save_pid_file(profile_path: str, pid: int, port: int, email: str, chrome_exe: str):
    """Save PID + port info for later reconnect."""
    data = {
        "pid": pid,
        "port": port,
        "email": email,
        "chrome_exe": chrome_exe,
        "launched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    pid_path = _pid_file_path(profile_path)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pid_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    log.info(f"[ChromeManager] PID file saved: {pid_path}")


def _load_pid_file(profile_path: str) -> Optional[Dict]:
    """Load PID file, returns None if missing/corrupt."""
    pid_path = _pid_file_path(profile_path)
    if not pid_path.exists():
        return None
    try:
        with open(pid_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _remove_pid_file(profile_path: str):
    """Delete PID file."""
    pid_path = _pid_file_path(profile_path)
    try:
        pid_path.unlink(missing_ok=True)
    except Exception:
        pass


# ── Process validation ───────────────────────────────────────────────────

def _is_chrome_process_alive(pid: int, profile_path: str) -> bool:
    """Validate that PID is a Chrome process using the correct profile.
    
    3-step validation:
    1. PID exists
    2. Process name contains "chrome"
    3. Command line contains the profile path (prevents PID reuse false positive)
    """
    try:
        import psutil
    except ImportError:
        # Fallback: just check PID exists
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False

        name = proc.name().lower()
        if "chrome" not in name:
            return False

        # Check cmdline for profile path match
        try:
            cmdline = " ".join(proc.cmdline())
            profile_name = Path(profile_path).name
            if profile_name in cmdline:
                return True
            # Fallback: if we can't read cmdline (access denied), trust PID + name
            return True
        except (psutil.AccessDenied, psutil.ZombieProcess):
            return True

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


# ── Extension Detection ──────────────────────────────────────────────────
# Check if extension is loaded by querying CDP /json targets.


def _is_extension_loaded(port: int) -> bool:
    """Check if our extension is already loaded by querying CDP /json targets.
    
    Looks for service_worker or background_page targets with chrome-extension:// URL.
    
    Returns:
        True if extension service worker is detected.
    """
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read().decode())
        
        for target in targets:
            url = target.get("url", "")
            target_type = target.get("type", "")
            if url.startswith("chrome-extension://") and target_type in ("service_worker", "background_page"):
                ext_id = url.split("/")[2] if len(url.split("/")) > 2 else "unknown"
                log.info(f"[ChromeManager] Extension already loaded: {ext_id} (type={target_type})")
                return True
        
        return False
    except Exception as e:
        log.debug(f"[ChromeManager] Could not check extension status: {e}")
        return False


# ── Pre-set Developer Mode in Chrome Profile ─────────────────────────────
# chrome://extensions page hangs when --enable-unsafe-extension-debugging
# is used with --remote-debugging-port. Pre-setting developer_mode in the
# profile's Preferences file fixes this and ensures chrome://extensions loads.

def _ensure_developer_mode(profile_path: str):
    """Pre-set Developer Mode = ON in Chrome profile Preferences.
    
    This allows chrome://extensions to load properly and show
    unpacked extensions installed via CDP. Works for both existing
    and new profiles.
    
    Args:
        profile_path: Chrome user-data-dir path
    """
    prefs_dir = Path(profile_path) / "Default"
    prefs_file = prefs_dir / "Preferences"
    
    try:
        prefs_dir.mkdir(parents=True, exist_ok=True)
        
        # Read existing preferences or start fresh
        prefs = {}
        if prefs_file.exists():
            try:
                raw = prefs_file.read_text(encoding="utf-8")
                if raw.strip():
                    prefs = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                log.warning("[ChromeManager] ⚠️ Corrupt Preferences file — resetting")
                prefs = {}
        
        # Check if already set
        ext_prefs = prefs.get("extensions", {}).get("ui", {})
        if ext_prefs.get("developer_mode") is True:
            return  # Already enabled
        
        # Set developer_mode = true
        prefs.setdefault("extensions", {}).setdefault("ui", {})["developer_mode"] = True
        
        # Write back
        prefs_file.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
        log.info(f"[ChromeManager] ✅ Developer Mode pre-set for {Path(profile_path).name}")
        
    except Exception as e:
        log.warning(f"[ChromeManager] ⚠️ Could not set developer mode: {e}")


# ── Windows Efficiency Mode ──────────────────────────────────────────────

def _disable_efficiency_mode(pid: int):
    """Disable Windows Efficiency Mode for a process.
    
    Windows 11 puts hidden/background processes into Efficiency Mode,
    throttling CPU and lowering priority. This causes WebSocket heartbeat
    delays and Extension responsiveness issues.
    """
    if os.name != 'nt':
        return
    try:
        import ctypes
        from ctypes import wintypes
        
        kernel32 = ctypes.windll.kernel32
        
        PROCESS_SET_INFORMATION = 0x0200
        ProcessPowerThrottling = 4  # PROCESS_INFORMATION_CLASS
        PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
        
        class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.ULONG),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]
        
        handle = kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
        if not handle:
            return
        
        try:
            state = PROCESS_POWER_THROTTLING_STATE()
            state.Version = PROCESS_POWER_THROTTLING_CURRENT_VERSION
            state.ControlMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED
            state.StateMask = 0  # 0 = disable throttling
            
            kernel32.SetProcessInformation(
                handle,
                ProcessPowerThrottling,
                ctypes.byref(state),
                ctypes.sizeof(state),
            )
            log.info(f"[ChromeManager] ⚡ Disabled Efficiency Mode for PID {pid}")
        finally:
            kernel32.CloseHandle(handle)
    except Exception as e:
        log.debug(f"[ChromeManager] Could not disable Efficiency Mode: {e}")


# ── Launch Chrome ────────────────────────────────────────────────────────

def launch_chrome(
    profile_path: str,
    email: str = "",
    port: Optional[int] = None,
    start_url: str = "about:blank",
    hidden: bool = True,
) -> Dict[str, Any]:
    """Launch a detached Chrome process with CDP enabled.
    
    The Chrome process survives app exit (DETACHED_PROCESS flag).
    Extension is installed via CDP HTTP AFTER Chrome launches and CDP is ready.
    
    Args:
        profile_path: Path to Chrome user-data-dir
        email: Account email (stored in PID file for reference)
        port: CDP port to use (auto-allocated if None)
        start_url: Initial URL to open
        hidden: If True, launch off-screen (--window-position=-32000,-32000)
    
    Returns:
        Dict with {pid, port, email, chrome_exe}
    
    Raises:
        RuntimeError: If Chrome executable not found or launch fails
    """
    chrome_exe = find_chrome_exe()
    if not chrome_exe:
        raise RuntimeError("Chrome executable not found on this system")

    if port is None:
        port = allocate_port()

    # Pre-set Developer Mode so chrome://extensions loads properly
    _ensure_developer_mode(profile_path)

    # Resolve Extension path (inside client app directory)
    _client_dir = Path(__file__).resolve().parent.parent  # 02 - CLIENT - VEO PRO MAX/
    _extension_dir = _client_dir / "extension"
    _has_extension = _extension_dir.exists() and (_extension_dir / "manifest.json").exists()

    args = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_path}",
        "--remote-allow-origins=*",
        "--enable-extensions",
        "--enable-unsafe-extension-debugging",  # Required for unpacked extensions (CDP-installed)
        "--no-first-run",
        "--no-default-browser-check",
        # ── Anti-throttle: prevent Memory Saver, tab discarding, background throttling ──
        "--disable-features=TabDiscarding,MemorySaver,UseEcoQoSForBackgroundProcess",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]

    # Add --load-extension flag as supplementary install method.
    # This flag was removed from Chrome 137+ official builds but still works on
    # Chromium and Chrome for Testing. If not supported, Chrome silently ignores it.
    if _has_extension:
        args.insert(-1, f"--load-extension={_extension_dir}")
        log.info(f"[ChromeManager] Added --load-extension flag: {_extension_dir}")

    if hidden:
        args.append("--window-position=-32000,-32000")

    args.append(start_url)

    log.info(f"[ChromeManager] Launching Chrome: port={port}, profile={Path(profile_path).name}")
    log.info(f"[ChromeManager] Chrome args: {' '.join(args[:8])}...")

    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP = fully independent
    creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        args,
        creationflags=creation_flags,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    pid = proc.pid
    log.info(f"[ChromeManager] Chrome launched: PID={pid}, port={port}")

    # Disable Windows Efficiency Mode for Chrome process
    _disable_efficiency_mode(pid)

    # Save PID file for reconnect
    _save_pid_file(profile_path, pid, port, email, chrome_exe)

    # Wait for CDP to become responsive
    cdp_ready = False
    deadline = time.time() + CHROME_STARTUP_TIMEOUT
    log.warning(f"[ChromeManager] Waiting for CDP on port {port} (timeout={CHROME_STARTUP_TIMEOUT}s)...")
    while time.time() < deadline:
        if _is_cdp_alive(port):
            log.info(f"[ChromeManager] CDP ready on port {port}")
            cdp_ready = True
            break
        time.sleep(0.5)

    if not cdp_ready:
        log.warning(f"[ChromeManager] CDP NOT responding after {CHROME_STARTUP_TIMEOUT}s on port {port}")
        log.warning(f"[ChromeManager] CDP not responding after {CHROME_STARTUP_TIMEOUT}s")

    # Extension loads via --load-extension flag at launch time.
    # Chrome branded builds (145+) don't support CDP Extensions.loadUnpacked,
    # so we rely solely on the --load-extension flag.
    if _has_extension:
        log.info(f"[ChromeManager] Extension loaded via --load-extension flag")
    elif not _has_extension:
        log.warning(f"[ChromeManager] No extension directory found — skipping install")

    return {"pid": pid, "port": port, "email": email, "chrome_exe": chrome_exe}


# ── Orphan Chrome Discovery ─────────────────────────────────────────────

def _find_orphan_chrome(profile_path: str) -> Optional[Dict[str, Any]]:
    """Scan running Chrome processes to find one using the given profile path.
    
    Handles orphan Chromes that survive app restarts (DETACHED_PROCESS)
    but whose PID files were cleaned up. Extracts the CDP port from
    the process command line and validates CDP is responding.
    
    Returns:
        Dict with {pid, port, email} if found and CDP alive, None otherwise.
    """
    try:
        import psutil
    except ImportError:
        return None
    
    profile_name = Path(profile_path).name
    
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if "chrome" not in (proc.info["name"] or "").lower():
                continue
            
            cmdline = proc.cmdline()
            cmdline_str = " ".join(cmdline)
            
            # Check if this Chrome uses our profile path
            if profile_name not in cmdline_str:
                continue
            
            # Extract --remote-debugging-port=NNNN
            port = None
            for arg in cmdline:
                if arg.startswith("--remote-debugging-port="):
                    try:
                        port = int(arg.split("=", 1)[1])
                    except (ValueError, IndexError):
                        pass
                    break
            
            if port is None:
                continue
            
            # Verify CDP is actually responding
            if not _is_cdp_alive(port):
                continue
            
            pid = proc.info["pid"]
            log.info(f"[ChromeManager] 🔍 Found orphan Chrome: PID={pid}, port={port}, profile={profile_name}")
            
            # Recreate PID file so future reconnects work
            _save_pid_file(profile_path, pid, port, "", "")
            
            return {"pid": pid, "port": port, "email": ""}
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return None


# ── Reconnect to existing Chrome ────────────────────────────────────────

def reconnect_chrome(profile_path: str) -> Optional[Dict[str, Any]]:
    """Try to reconnect to an existing Chrome process.
    
    Reads PID file → validates PID alive + correct profile → tests CDP port.
    Falls back to scanning running processes for orphan Chromes.
    
    Returns:
        Dict with {pid, port, email, tabs} if reconnect successful, None otherwise.
    """
    info = _load_pid_file(profile_path)
    if not info:
        log.debug(f"[ChromeManager] No PID file for {Path(profile_path).name}")
        # Fallback: scan running processes for orphan Chrome
        orphan = _find_orphan_chrome(profile_path)
        if orphan:
            tabs = get_cdp_tabs(orphan["port"])
            log.info(f"[ChromeManager] 🔗 Reconnected to orphan Chrome PID={orphan['pid']}, port={orphan['port']}, {len(tabs)} tab(s)")
            orphan["tabs"] = tabs
            return orphan
        return None

    pid = info["pid"]
    port = info["port"]

    # Step 1+2: PID alive and is Chrome with correct profile
    if not _is_chrome_process_alive(pid, profile_path):
        log.info(f"[ChromeManager] PID {pid} not alive or not Chrome — cleaning up")
        _remove_pid_file(profile_path)
        # Fallback: scan running processes for orphan Chrome
        orphan = _find_orphan_chrome(profile_path)
        if orphan:
            tabs = get_cdp_tabs(orphan["port"])
            log.info(f"[ChromeManager] 🔗 Reconnected to orphan Chrome PID={orphan['pid']}, port={orphan['port']}, {len(tabs)} tab(s)")
            orphan["tabs"] = tabs
            return orphan
        return None

    # Step 3: CDP port responding
    if not _is_cdp_alive(port):
        log.info(f"[ChromeManager] PID {pid} alive but CDP port {port} not responding")
        _remove_pid_file(profile_path)
        return None

    # Success — get tab info
    tabs = get_cdp_tabs(port)
    log.info(f"[ChromeManager] 🔗 Reconnected to Chrome PID={pid}, port={port}, {len(tabs)} tab(s)")

    return {
        "pid": pid,
        "port": port,
        "email": info.get("email", ""),
        "tabs": tabs,
    }


# Per-profile launch lock — prevents two threads from launching Chrome
# on the same profile simultaneously (e.g. debug browser + RecaptchaBrowserSession)
_launch_locks: Dict[str, threading.Lock] = {}
_launch_locks_guard = threading.Lock()

def launch_or_reconnect(
    profile_path: str,
    email: str = "",
    start_url: str = "about:blank",
    hidden: bool = True,
) -> Dict[str, Any]:
    """Try reconnect first, launch new Chrome if not possible.
    
    This is the main entry point for getting a Chrome instance.
    Thread-safe: uses per-profile lock to prevent duplicate Chrome launches.
    
    Returns:
        Dict with {pid, port, email, ...}
    """
    # Per-profile lock prevents race condition between concurrent callers
    with _launch_locks_guard:
        if profile_path not in _launch_locks:
            _launch_locks[profile_path] = threading.Lock()
        lock = _launch_locks[profile_path]
    
    with lock:
        # Pre-set Developer Mode for this profile (idempotent, fast)
        _ensure_developer_mode(profile_path)

        # Check if extension needs to be installed
        _client_dir = Path(__file__).resolve().parent.parent
        _extension_dir = _client_dir / "extension"
        _has_extension = (
            _extension_dir.exists()
            and (_extension_dir / "manifest.json").exists()
        )

        # Try reconnect
        existing = reconnect_chrome(profile_path)
        if existing:
            # On reconnect, extension persists as long as Chrome stays alive
            # (DETACHED_PROCESS — it never restarts). Just check & log status.
            if _has_extension:
                port = existing.get("port")
                if port and _is_extension_loaded(port):
                    log.info(f"[ChromeManager] Reconnected — extension already loaded on port {port}")
                else:
                    # Extension not detected yet — likely still initializing or Chrome
                    # was restarted externally. --load-extension flag needs a relaunch.
                    log.info(f"[ChromeManager] Reconnected — extension not detected on port {port} (may still be initializing)")
            # Enforce tab limit on reconnect (prevents tab accumulation)
            enforce_tab_limit(existing.get("port", 0))
            return existing

        # Launch new (will install extension after CDP ready)
        log.info(f"[ChromeManager] No existing Chrome found — launching new instance")
        result = launch_chrome(profile_path, email=email, start_url=start_url, hidden=hidden)
        # Enforce tab limit on new launch (close any extra tabs from start_url)
        enforce_tab_limit(result.get("port", 0))
        return result


# ── Tab management ───────────────────────────────────────────────────────

def get_cdp_tabs(port: int) -> List[Dict]:
    """Get list of tabs from CDP endpoint.
    
    Returns list of tab info dicts with: id, title, url, webSocketDebuggerUrl.
    Only returns 'page' type targets (no service workers, etc.).
    """
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return [t for t in data if t.get("type") == "page"]
    except Exception as e:
        log.warning(f"[ChromeManager] Failed to list tabs on port {port}: {e}")
        return []


def has_tab_with_url(port: int, url_fragment: str) -> bool:
    """Check if any tab contains the given URL fragment."""
    tabs = get_cdp_tabs(port)
    return any(url_fragment in tab.get("url", "") for tab in tabs)


# ── Tab Limiter ──────────────────────────────────────────────────────────
# Enforce max 3 tabs per Chrome instance: Gmail, YouTube, Google Flow.
# Prevents tab accumulation from multiple CDP reconnects and new_page() calls.

# URL fragments that identify the 3 allowed tabs
ALLOWED_TAB_URLS = [
    "mail.google.com",       # Gmail
    "youtube.com",           # YouTube
    "labs.google",           # Google Flow (labs.google/fx/tools/flow)
]

MAX_TABS = 3


def _close_cdp_tab(port: int, tab_id: str) -> bool:
    """Close a single tab via CDP HTTP API.

    Uses the /json/close/{targetId} endpoint that works without WebSocket.

    Args:
        port: CDP port
        tab_id: Target ID of the tab to close

    Returns:
        True if tab closed successfully
    """
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/close/{tab_id}", method="GET"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception as e:
        log.debug(f"[ChromeManager] Could not close tab {tab_id}: {e}")
        return False


def _is_tab_allowed(tab: Dict, allowed_urls: List[str] = ALLOWED_TAB_URLS) -> bool:
    """Check if a tab's URL matches one of the allowed URL fragments."""
    url = tab.get("url", "")
    return any(fragment in url for fragment in allowed_urls)


def close_excess_tabs(
    port: int,
    max_tabs: int = MAX_TABS,
    allowed_urls: List[str] = ALLOWED_TAB_URLS,
) -> int:
    """Close excess tabs to enforce the tab limit.

    Strategy:
    1. Keep tabs whose URL matches an allowed fragment (up to max_tabs).
    2. Close all about:blank and unrecognized tabs first.
    3. If still over limit, close the oldest non-essential tabs.

    Args:
        port: CDP port of the Chrome instance
        max_tabs: Maximum number of tabs to keep (default 3)
        allowed_urls: URL fragments for tabs that should be kept

    Returns:
        Number of tabs closed
    """
    tabs = get_cdp_tabs(port)
    if len(tabs) <= max_tabs:
        return 0  # Already within limit

    log.info(f"[ChromeManager] Tab cleanup: {len(tabs)} tabs found (max={max_tabs})")

    # Categorize tabs
    allowed_tabs = []      # Tabs matching allowed URLs
    blank_tabs = []        # about:blank tabs
    other_tabs = []        # Unrecognized tabs

    for tab in tabs:
        url = tab.get("url", "")
        if url in ("about:blank", "chrome://newtab/", ""):
            blank_tabs.append(tab)
        elif _is_tab_allowed(tab, allowed_urls):
            allowed_tabs.append(tab)
        else:
            other_tabs.append(tab)

    # Build close list: prioritize closing blank > other > excess allowed
    to_close = []

    # 1. Close all blank tabs (never needed)
    to_close.extend(blank_tabs)

    # 2. Close unrecognized tabs
    to_close.extend(other_tabs)

    # 3. If allowed tabs exceed limit, keep only the first max_tabs
    if len(allowed_tabs) > max_tabs:
        # Keep first max_tabs (ordered as Chrome returns them = oldest first)
        to_close.extend(allowed_tabs[max_tabs:])
        allowed_tabs = allowed_tabs[:max_tabs]

    # Don't close more than necessary — we need at least 1 tab alive
    remaining = len(tabs) - len(to_close)
    if remaining < 1:
        # Keep at least one tab (the first allowed or first overall)
        if to_close:
            to_close.pop(0)

    # Execute closures
    closed = 0
    for tab in to_close:
        tab_id = tab.get("id", "")
        tab_url = tab.get("url", "?")[:60]
        if tab_id and _close_cdp_tab(port, tab_id):
            closed += 1
            log.debug(f"[ChromeManager] Closed tab: {tab_url}")

    if closed > 0:
        remaining_tabs = get_cdp_tabs(port)
        log.info(
            f"[ChromeManager] Tab cleanup complete: closed {closed}, "
            f"remaining {len(remaining_tabs)} tab(s)"
        )

    return closed


def enforce_tab_limit(port: int) -> int:
    """Convenience wrapper: enforce max 3 tabs on a Chrome instance.

    Called automatically after launch_or_reconnect() to prevent tab accumulation.

    Returns:
        Number of tabs closed (0 if already within limit)
    """
    return close_excess_tabs(port, max_tabs=MAX_TABS, allowed_urls=ALLOWED_TAB_URLS)


# ── Kill Chrome ──────────────────────────────────────────────────────────

def kill_chrome(profile_path: str) -> bool:
    """Kill the Chrome process for a profile and clean up PID file.
    
    Returns:
        True if process was killed, False if it wasn't running.
    """
    info = _load_pid_file(profile_path)
    if not info:
        return False

    pid = info["pid"]

    try:
        import psutil
        try:
            proc = psutil.Process(pid)
            if "chrome" in proc.name().lower():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    proc.kill()
                log.info(f"[ChromeManager] 🔒 Chrome PID={pid} terminated")
        except psutil.NoSuchProcess:
            log.info(f"[ChromeManager] Chrome PID={pid} already dead")
    except ImportError:
        # Fallback without psutil
        try:
            os.kill(pid, 9)
            log.info(f"[ChromeManager] Chrome PID={pid} killed (no psutil)")
        except OSError:
            pass

    _remove_pid_file(profile_path)
    return True


def kill_all_managed_chromes(profiles_dir: str):
    """Kill all Chrome processes managed by us (scan for PID files)."""
    profiles_path = Path(profiles_dir)
    if not profiles_path.exists():
        return

    for pid_file in profiles_path.rglob(PID_FILE_NAME):
        profile_path = str(pid_file.parent)
        kill_chrome(profile_path)
