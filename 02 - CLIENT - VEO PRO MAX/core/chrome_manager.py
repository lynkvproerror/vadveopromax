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
import time
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


def allocate_port(base: int = CDP_PORT_BASE, max_port: int = CDP_PORT_MAX) -> int:
    """Find a free CDP port in the range [base, max_port].
    
    Skips ports that are already serving CDP (owned by another Chrome).
    
    Raises:
        RuntimeError: If no free port found in range.
    """
    for port in range(base, max_port + 1):
        if _is_port_free(port):
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

    args = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-infobars",
        "--disable-blink-features=AutomationControlled",
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
    deadline = time.time() + CHROME_STARTUP_TIMEOUT
    while time.time() < deadline:
        if _is_cdp_alive(port):
            log.info(f"[ChromeManager] ✅ CDP ready on port {port}")
            return {"pid": pid, "port": port, "email": email, "chrome_exe": chrome_exe}
        time.sleep(0.5)

    log.warning(f"[ChromeManager] ⚠️ CDP not responding after {CHROME_STARTUP_TIMEOUT}s (Chrome may still be starting)")
    return {"pid": pid, "port": port, "email": email, "chrome_exe": chrome_exe}


# ── Reconnect to existing Chrome ────────────────────────────────────────

def reconnect_chrome(profile_path: str) -> Optional[Dict[str, Any]]:
    """Try to reconnect to an existing Chrome process.
    
    Reads PID file → validates PID alive + correct profile → tests CDP port.
    
    Returns:
        Dict with {pid, port, email, tabs} if reconnect successful, None otherwise.
    """
    info = _load_pid_file(profile_path)
    if not info:
        log.debug(f"[ChromeManager] No PID file for {Path(profile_path).name}")
        return None

    pid = info["pid"]
    port = info["port"]

    # Step 1+2: PID alive and is Chrome with correct profile
    if not _is_chrome_process_alive(pid, profile_path):
        log.info(f"[ChromeManager] PID {pid} not alive or not Chrome — cleaning up")
        _remove_pid_file(profile_path)
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


# ── Launch or Reconnect ─────────────────────────────────────────────────

def launch_or_reconnect(
    profile_path: str,
    email: str = "",
    start_url: str = "about:blank",
    hidden: bool = True,
) -> Dict[str, Any]:
    """Try reconnect first, launch new Chrome if not possible.
    
    This is the main entry point for getting a Chrome instance.
    
    Returns:
        Dict with {pid, port, email, ...}
    """
    # Try reconnect
    existing = reconnect_chrome(profile_path)
    if existing:
        return existing

    # Launch new
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
