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


# ── Find Chrome executable ─────────────────────────────────────────────

def find_chrome_exe() -> Optional[str]:
    """Locate Chrome executable on Windows."""
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
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


# ── Install Extension via CDP HTTP ───────────────────────────────────────
# Chrome 137+ removed --load-extension flag. Instead, we install the extension
# AFTER Chrome launches by calling Extensions.loadUnpacked via CDP WebSocket
# on the already-running debug port. Pure Python — no Node.js needed.

EXTENSION_MARKER = ".veo_extension_installed"
_install_locks: Dict[str, threading.Lock] = {}  # Per-profile install lock
_install_locks_guard = threading.Lock()          # Guard for _install_locks dict


def _is_extension_installed(profile_path: str) -> bool:
    """Check if the extension was already installed for this profile."""
    marker = Path(profile_path) / EXTENSION_MARKER
    return marker.exists()


def _mark_extension_installed(profile_path: str, ext_id: str):
    """Create marker file to indicate extension is installed."""
    marker = Path(profile_path) / EXTENSION_MARKER
    marker.write_text(ext_id, encoding="utf-8")


def _install_extension_via_cdp(port: int, extension_path: str, profile_path: str) -> bool:
    """Install unpacked extension via CDP WebSocket on an already-running Chrome.
    
    Connects to Chrome's debug port, gets the WebSocket URL, sends
    Extensions.loadUnpacked command, and waits for the extension ID.
    
    Args:
        port: Chrome's --remote-debugging-port
        extension_path: Absolute path to the extension directory
        profile_path: Chrome profile path (for marker file)
        
    Returns:
        True if extension was installed successfully
    """
    # Per-profile lock prevents concurrent installs
    with _install_locks_guard:
        if profile_path not in _install_locks:
            _install_locks[profile_path] = threading.Lock()
        lock = _install_locks[profile_path]
    
    with lock:
        # Skip if already installed (check INSIDE lock for thread safety)
        if _is_extension_installed(profile_path):
            log.info("[ChromeManager] ✅ Extension already installed (skipping)")
            return True
        
        return _do_cdp_extension_install(port, extension_path, profile_path)


def _do_cdp_extension_install(port: int, extension_path: str, profile_path: str) -> bool:
    """Internal: perform extension install via CDP WebSocket (called under lock)."""
    import websocket  # websocket-client library
    
    log.info("[ChromeManager] 🔧 Installing extension via CDP HTTP...")
    print("[ChromeManager] 🔧 Installing extension via CDP HTTP...")
    
    try:
        # Step 1: Get WebSocket debugger URL from CDP
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/version", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            version_info = json.loads(resp.read().decode())
        
        ws_url = version_info.get("webSocketDebuggerUrl")
        if not ws_url:
            log.error("[ChromeManager] ❌ No webSocketDebuggerUrl in CDP response")
            print("[ChromeManager] ❌ CDP did not return WebSocket URL")
            return False
        
        log.info(f"[ChromeManager] CDP WebSocket: {ws_url}")
        
        # Step 2: Connect via WebSocket and send Extensions.loadUnpacked
        # Normalize path to forward slashes (Chrome CDP requires this)
        ext_path_normalized = extension_path.replace("\\", "/")
        
        ws = websocket.create_connection(ws_url, timeout=10)
        try:
            # Send the CDP command
            cdp_command = json.dumps({
                "id": 1,
                "method": "Extensions.loadUnpacked",
                "params": {"path": ext_path_normalized}
            })
            ws.send(cdp_command)
            log.info("[ChromeManager] Sent Extensions.loadUnpacked command")
            
            # Wait for response (with timeout)
            ws.settimeout(15)
            while True:
                response_text = ws.recv()
                response = json.loads(response_text)
                
                # Look for our command response (id: 1)
                if response.get("id") == 1:
                    if response.get("result", {}).get("id"):
                        ext_id = response["result"]["id"]
                        _mark_extension_installed(profile_path, ext_id)
                        log.info(f"[ChromeManager] ✅ Extension installed via CDP HTTP: {ext_id}")
                        print(f"[ChromeManager] ✅ Extension installed: {ext_id}")
                        return True
                    elif response.get("error"):
                        error_msg = response["error"].get("message", "Unknown error")
                        log.error(f"[ChromeManager] ❌ CDP install failed: {error_msg}")
                        print(f"[ChromeManager] ❌ Extension install failed: {error_msg}")
                        return False
                    else:
                        log.warning(f"[ChromeManager] ⚠️ Unexpected CDP response: {response}")
                        return False
                
                # Skip events (method responses without id matching ours)
                
        finally:
            ws.close()
    
    except ImportError:
        log.error("[ChromeManager] ❌ websocket-client not installed. Run: pip install websocket-client")
        print("[ChromeManager] ❌ Missing dependency: pip install websocket-client")
        return False
    except Exception as e:
        log.error(f"[ChromeManager] ❌ Extension install via CDP failed: {e}")
        print(f"[ChromeManager] ❌ Extension install failed: {e}")
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
    ]

    if hidden:
        args.append("--window-position=-32000,-32000")

    args.append(start_url)

    log.info(f"[ChromeManager] Launching Chrome: port={port}, profile={Path(profile_path).name}")

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

    # Save PID file for reconnect
    _save_pid_file(profile_path, pid, port, email, chrome_exe)

    # Wait for CDP to become responsive
    cdp_ready = False
    deadline = time.time() + CHROME_STARTUP_TIMEOUT
    while time.time() < deadline:
        if _is_cdp_alive(port):
            log.info(f"[ChromeManager] ✅ CDP ready on port {port}")
            cdp_ready = True
            break
        time.sleep(0.5)

    if not cdp_ready:
        log.warning(f"[ChromeManager] ⚠️ CDP not responding after {CHROME_STARTUP_TIMEOUT}s")

    # Install extension AFTER Chrome is running (via CDP HTTP — no Node.js needed)
    if cdp_ready and _has_extension:
        _install_extension_via_cdp(port, str(_extension_dir), profile_path)

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
            # Install extension on reconnected Chrome if needed (no kill+relaunch!)
            if _has_extension and not _is_extension_installed(profile_path):
                port = existing.get("port")
                if port:
                    _install_extension_via_cdp(port, str(_extension_dir), profile_path)
            return existing

        # Launch new (will install extension after CDP ready)
        return launch_chrome(profile_path, email=email, start_url=start_url, hidden=hidden)


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
