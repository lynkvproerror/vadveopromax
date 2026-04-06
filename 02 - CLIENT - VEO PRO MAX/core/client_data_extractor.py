"""
VEO Pro Max — x-client-data Extractor

Extracts x-client-data from the machine's default Chrome profile.

x-client-data is computed at runtime by Chrome's Variations Service.
It depends on Chrome version + OS, NOT the Google account.
Fresh profiles produce short values (8 chars); mature profiles produce
full values (50+ chars) needed for reCAPTCHA trust scoring.

Strategy (ordered by preference):
1. Scan running Chrome processes for CDP port → extract via CDP
2. Copy Variations files from default profile → launch temp Chrome → capture
3. Launch temp Chrome with default profile (if Chrome not running)
"""

import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Minimum length for a "good" x-client-data value
from config.constants import MIN_VALID_XCD
MIN_GOOD_LENGTH = MIN_VALID_XCD  # Shared constant (50)

# Files needed for Chrome Variations Service (copy from default profile)
VARIATIONS_FILES = [
    "Local State",
    "Variations",
]


def _get_default_chrome_user_data_dir() -> Optional[str]:
    """Get user's default Chrome User Data directory on Windows."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return None
    chrome_dir = os.path.join(local_app_data, "Google", "Chrome", "User Data")
    if os.path.isdir(chrome_dir):
        return chrome_dir
    return None


def _find_cdp_port_from_running_chrome() -> Optional[int]:
    """Scan running Chrome processes for one with --remote-debugging-port.
    
    Returns the CDP port if found, None otherwise.
    Only considers Chrome instances using the DEFAULT user data dir
    (not our managed app profiles).
    """
    try:
        import psutil
    except ImportError:
        log.debug("[ClientDataExtractor] psutil not available, skipping process scan")
        return None
    
    default_dir = _get_default_chrome_user_data_dir()
    
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info["name"] or "").lower()
            if "chrome" not in name:
                continue
            
            cmdline = proc.cmdline()
            cmdline_str = " ".join(cmdline)
            
            # Skip our managed browser profiles
            if "browser_session_" in cmdline_str:
                continue
            
            # Look for --remote-debugging-port=NNNN
            for arg in cmdline:
                if arg.startswith("--remote-debugging-port="):
                    try:
                        port = int(arg.split("=", 1)[1])
                        # Verify CDP is responding
                        req = urllib.request.Request(
                            f"http://127.0.0.1:{port}/json/version", method="GET"
                        )
                        with urllib.request.urlopen(req, timeout=2) as resp:
                            if resp.status == 200:
                                log.info(
                                    f"[ClientDataExtractor] Found Chrome CDP on port {port} "
                                    f"(PID={proc.info['pid']})"
                                )
                                return port
                    except (ValueError, IndexError, Exception):
                        pass
                    break
        except Exception:
            continue
    
    return None


def _extract_via_cdp(port: int) -> Optional[str]:
    """Connect to a Chrome CDP endpoint and extract x-client-data.
    
    Navigates to a Google page → captures x-client-data from
    Network.requestWillBeSentExtraInfo CDP events.
    
    Uses a thread to avoid conflict with asyncio event loop.
    
    Returns the x-client-data value or None.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("[ClientDataExtractor] Playwright not available")
        return None
    
    def _do_extract():
        """Run in a thread to avoid asyncio loop conflict."""
        client_data = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                
                contexts = browser.contexts
                if not contexts:
                    log.warning("[ClientDataExtractor] No browser contexts found")
                    browser.close()
                    return None
                
                context = contexts[0]
                
                # Create a new page for capture (don't disturb existing tabs)
                page = context.new_page()
                
                # Set up CDP header capture
                captured = {}
                try:
                    cdp = context.new_cdp_session(page)
                    
                    def on_extra_info(event):
                        nonlocal captured
                        headers = event.get("headers", {})
                        for key, val in headers.items():
                            if key.lower() == "x-client-data" and val:
                                captured["x-client-data"] = val
                    
                    cdp.on("Network.requestWillBeSentExtraInfo", on_extra_info)
                    cdp.send("Network.enable")
                except Exception as e:
                    log.warning(f"[ClientDataExtractor] CDP session error: {e}")
                    page.close()
                    browser.close()
                    return None
                
                # Navigate to a Google page to trigger x-client-data header
                try:
                    page.goto(
                        "https://labs.google/fx/tools/flow",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    page.wait_for_timeout(3000)
                except Exception as e:
                    log.debug(f"[ClientDataExtractor] Navigation partial: {e}")
                
                client_data = captured.get("x-client-data")
                
                # Clean up - close only our tab
                try:
                    page.close()
                except Exception:
                    pass
                
                # Don't close the browser — it's not ours
                browser.close()  # Just disconnects, doesn't kill Chrome
        
        except Exception as e:
            log.warning(f"[ClientDataExtractor] CDP extraction failed: {e}")
        
        return client_data
    
    # Run in a thread to avoid "Sync API inside asyncio loop" error
    import asyncio
    try:
        asyncio.get_running_loop()
        # We're inside an async loop — must use a thread
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_extract)
            return future.result(timeout=30)
    except RuntimeError:
        # No async loop — safe to call directly
        return _do_extract()


def _extract_via_temp_chrome() -> Optional[str]:
    """Launch a temporary hidden Chrome with Variations data from default profile.
    
    1. Copy 'Local State' from user's default Chrome profile to temp dir
    2. Launch Chrome with temp profile (gets Variations from Local State)
    3. Navigate to Google → capture x-client-data
    4. Kill temp Chrome
    
    Returns x-client-data value or None.
    """
    from core.chrome_manager import find_chrome_exe
    
    default_dir = _get_default_chrome_user_data_dir()
    if not default_dir:
        log.info("[ClientDataExtractor] Default Chrome profile not found")
        return None
    
    chrome_exe = find_chrome_exe()
    if not chrome_exe:
        log.info("[ClientDataExtractor] Chrome executable not found")
        return None
    
    # Create temp directory with copied Variations files
    temp_dir = tempfile.mkdtemp(prefix="veo_cd_extract_")
    
    try:
        # Copy Local State (contains variations_compressed_seed)
        for filename in VARIATIONS_FILES:
            src = os.path.join(default_dir, filename)
            if os.path.isfile(src):
                dst = os.path.join(temp_dir, filename)
                shutil.copy2(src, dst)
                log.debug(f"[ClientDataExtractor] Copied {filename}")
        
        # Also copy Default profile's Variations data if it exists
        default_profile = os.path.join(default_dir, "Default")
        if os.path.isdir(default_profile):
            temp_profile = os.path.join(temp_dir, "Default")
            os.makedirs(temp_profile, exist_ok=True)
            # Copy Preferences (may contain variations state)
            pref_src = os.path.join(default_profile, "Preferences")
            if os.path.isfile(pref_src):
                shutil.copy2(pref_src, os.path.join(temp_profile, "Preferences"))
        
        # Find a free port for CDP
        port = _find_free_port()
        if not port:
            log.warning("[ClientDataExtractor] No free CDP port available")
            return None
        
        # Launch Chrome hidden
        args = [
            chrome_exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={temp_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "about:blank",
        ]
        
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            args,
            creationflags=creation_flags,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        log.info(f"[ClientDataExtractor] Temp Chrome launched: PID={proc.pid}, port={port}")
        
        # Fully hide Chrome window (including taskbar) via Win32 API
        from config.settings import get_settings as _get_settings
        _s = _get_settings()
        if getattr(_s, 'smart_hide_enabled', True) or getattr(_s, 'hide_all_browsers', False):
            _hide_process_windows(proc.pid)
        
        # Wait for CDP to be ready
        deadline = time.time() + 15
        cdp_ready = False
        while time.time() < deadline:
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/json/version", method="GET"
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        cdp_ready = True
                        break
            except Exception:
                pass
            time.sleep(0.5)
        
        if not cdp_ready:
            log.warning("[ClientDataExtractor] Temp Chrome CDP not responding")
            _kill_process(proc.pid)
            return None
        
        # Extract via CDP
        client_data = _extract_via_cdp(port)
        
        # Kill temp Chrome
        _kill_process(proc.pid)
        
        return client_data
    
    finally:
        # Clean up temp directory (best effort)
        try:
            # Give Chrome time to release locks
            time.sleep(1)
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def _hide_process_windows(pid: int, retries: int = 5):
    """Hide all windows belonging to a process (and its children) using Win32 API.
    
    Uses ShowWindow(hwnd, SW_HIDE) to fully remove from screen AND taskbar.
    Retries because Chrome child processes may create windows slightly after launch.
    """
    try:
        import ctypes
        import ctypes.wintypes
        
        user32 = ctypes.windll.user32
        SW_HIDE = 0
        
        def _get_child_pids(parent_pid: int) -> set:
            """Get all child PIDs of a process."""
            pids = {parent_pid}
            try:
                import psutil
                try:
                    parent = psutil.Process(parent_pid)
                    for child in parent.children(recursive=True):
                        pids.add(child.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            except ImportError:
                pass
            return pids
        
        for attempt in range(retries):
            time.sleep(0.5)  # Wait for windows to appear
            
            target_pids = _get_child_pids(pid)
            hidden_count = 0
            
            # Enumerate all top-level windows
            @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            def enum_callback(hwnd, lparam):
                nonlocal hidden_count
                # Get the PID that owns this window
                window_pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                
                if window_pid.value in target_pids:
                    if user32.IsWindowVisible(hwnd):
                        user32.ShowWindow(hwnd, SW_HIDE)
                        hidden_count += 1
                return True
            
            user32.EnumWindows(enum_callback, 0)
            
            if hidden_count > 0:
                log.debug(f"[ClientDataExtractor] Hidden {hidden_count} Chrome window(s) (attempt {attempt + 1})")
    
    except Exception as e:
        log.debug(f"[ClientDataExtractor] ShowWindow hide failed: {e}")


def _find_free_port() -> Optional[int]:
    """Find a free port for temporary CDP Chrome (range 9260-9280)."""
    for port in range(9260, 9280):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def _kill_process(pid: int):
    """Kill a process by PID."""
    try:
        import psutil
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
        except psutil.NoSuchProcess:
            pass
    except ImportError:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def extract_client_data_from_machine() -> str:
    """Main entry point: extract x-client-data from machine's Chrome.
    
    Tries strategies in order:
    1. Scan for running Chrome with CDP → extract
    2. Launch temp Chrome with default profile Variations data → extract
    
    Returns:
        x-client-data string (50+ chars) on success, "" on failure.
    """
    # Strategy 1: Try existing Chrome with CDP port
    port = _find_cdp_port_from_running_chrome()
    if port:
        log.info(f"[ClientDataExtractor] Strategy 1: Extracting from running Chrome on port {port}")
        result = _extract_via_cdp(port)
        if result and len(result) >= MIN_GOOD_LENGTH:
            log.info(f"[ClientDataExtractor] ✅ Got x-client-data from running Chrome ({len(result)} chars)")
            return result
        elif result:
            log.info(f"[ClientDataExtractor] Running Chrome has short x-client-data ({len(result)} chars)")
    
    # Strategy 2: Launch temp Chrome with default profile's Variations data
    log.info("[ClientDataExtractor] Strategy 2: Launching temp Chrome with default profile variations...")
    result = _extract_via_temp_chrome()
    if result and len(result) >= MIN_GOOD_LENGTH:
        log.info(f"[ClientDataExtractor] ✅ Got x-client-data from temp Chrome ({len(result)} chars)")
        return result
    elif result:
        log.info(f"[ClientDataExtractor] Temp Chrome returned short x-client-data ({len(result)} chars)")
        return result  # Better than nothing
    
    log.warning("[ClientDataExtractor] ❌ All strategies failed to extract x-client-data")
    return ""
