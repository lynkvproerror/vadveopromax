"""
VEO Pro Max — Extension Manager (CDP-based)

Manages Chrome extension install/uninstall/reinstall using CDP WebSocket
and Win32 APIs. Replaces pywinauto-based auto_install_extension.py.

Strategy:
- Install: CDP Runtime.evaluate on chrome://extensions shadow DOM
           + Win32 SendInput for OS folder picker dialog
- Uninstall: CDP Runtime.evaluate to click Remove on extension card
- Reinstall: uninstall → wait → install

Works for both branded Chrome and CfT, but:
- CfT uses --load-extension flag → install/uninstall not needed (just restart)
- Branded Chrome v137+ requires this module for extension management
"""

import json
import logging
import os
import time
import threading
import urllib.request
import urllib.error
import websocket  # pip install websocket-client
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Extension name from manifest.json — used for identification
EXTENSION_NAME = "VEO Pro Max Bridge"

# Per-port lock prevents concurrent installs hitting the same folder picker
_install_locks = {}
_install_locks_guard = threading.Lock()

# Throttle DEBUG log: track which ports have already been logged as "loaded"
# so we don't spam every 5s poll cycle. Reset on install/uninstall.
_extension_logged_ports: set = set()


# ── Extension Detection (Single Source of Truth) ─────────────────────────

def _is_our_extension(target: dict) -> bool:
    """Check if a CDP target belongs to OUR extension (not any random one).
    
    Verifies:
    - URL is chrome-extension://
    - Target type is service_worker or background_page
    - Title contains EXTENSION_NAME, OR URL contains background.js
      (Chrome CDP returns SW title as 'Service Worker chrome-extension://ID/background.js'
       — NOT the extension name from manifest.json)
    """
    url = target.get("url", "")
    title = target.get("title", "")
    target_type = target.get("type", "")
    
    if "chrome-extension://" not in url:
        return False
    if target_type not in ("service_worker", "background_page"):
        return False
    # Match by extension name in title (if Chrome provides it)
    if EXTENSION_NAME.lower() in title.lower():
        return True
    # Match by background.js URL (Chrome uses 'Service Worker chrome-extension://ID/background.js' as title)
    if "background.js" in url and target_type == "service_worker":
        return True
    return False


def is_extension_loaded(port: int) -> bool:
    """Check if OUR extension is loaded by querying CDP /json targets.
    
    Verifies the service_worker title matches EXTENSION_NAME to avoid
    false positives from other installed extensions.
    
    Uses _extension_logged_ports to throttle DEBUG logging:
    only logs the first detection after a previous miss/reset.
    
    Returns:
        True if our extension service worker is detected.
    """
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        for t in targets:
            if _is_our_extension(t):
                # Throttle: only log first detection per port (avoid 5s spam)
                if port not in _extension_logged_ports:
                    log.debug(f"[ExtMgr] Extension loaded: {t.get('url', '')}")
                    _extension_logged_ports.add(port)
                return True
    except Exception as e:
        log.debug(f"[ExtMgr] CDP check error: {e}")
    
    # Extension not found — reset log throttle so next detection is logged
    _extension_logged_ports.discard(port)
    return False


def get_extension_id(port: int) -> Optional[str]:
    """Get OUR installed extension ID from CDP /json targets.
    
    Returns:
        Extension ID string (e.g. 'abcdef...') or None if not found.
    """
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        for t in targets:
            if _is_our_extension(t):
                url = t.get("url", "")
                ext_id = url.split("chrome-extension://")[1].split("/")[0]
                log.info(f"[ExtMgr] Extension ID: {ext_id}")
                return ext_id
    except Exception as e:
        log.debug(f"[ExtMgr] get_extension_id error: {e}")
    
    return None


def get_local_extension_version() -> Optional[str]:
    """Read version from local extension/manifest.json."""
    manifest = Path(__file__).resolve().parent.parent / "extension" / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return data.get("version")
    except Exception:
        return None


# ── CDP Tab Management ──────────────────────────────────────────────────

def _open_extensions_page(port: int) -> Optional[str]:
    """Open chrome://extensions — reuses existing tab if available.
    
    Returns:
        WebSocket debugger URL for the extensions tab, or None on failure.
    """
    # First: check if an extensions tab already exists
    existing = _get_extensions_ws_url(port)
    if existing:
        log.info(f"[ExtMgr] Reusing existing chrome://extensions tab, ws={existing[:60]}...")
        return existing
    
    # Open a NEW extensions tab
    url = f"http://127.0.0.1:{port}/json/new?chrome://extensions"
    
    # Chrome CDP /json/new requires PUT (newer versions).
    # Fall back to GET for older versions.
    for method in ("PUT", "GET"):
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=5) as resp:
                tab_info = json.loads(resp.read())
            ws_url = tab_info.get("webSocketDebuggerUrl", "")
            log.info(f"[ExtMgr] Opened chrome://extensions tab ({method}), ws={ws_url[:60]}...")
            return ws_url
        except urllib.error.HTTPError as e:
            if e.code == 405 and method == "PUT":
                log.debug(f"[ExtMgr] /json/new PUT returned 405, trying GET...")
                continue
            log.error(f"[ExtMgr] Failed to open chrome://extensions ({method}): {e}")
            return None
        except Exception as e:
            log.error(f"[ExtMgr] Failed to open chrome://extensions ({method}): {e}")
            return None
    
    return None


def _close_extensions_tab(port: int):
    """Close the chrome://extensions tab after operation."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        for t in targets:
            if "chrome://extensions" in t.get("url", ""):
                tab_id = t.get("id", "")
                if tab_id:
                    close_url = f"http://127.0.0.1:{port}/json/close/{tab_id}"
                    # Try PUT first (newer Chrome), fall back to GET
                    for method in ("PUT", "GET"):
                        try:
                            close_req = urllib.request.Request(close_url, method=method)
                            urllib.request.urlopen(close_req, timeout=3)
                            log.info(f"[ExtMgr] Closed chrome://extensions tab ({method})")
                            return
                        except urllib.error.HTTPError as e:
                            if e.code == 405:
                                continue
                            break
                    break
    except Exception as e:
        log.debug(f"[ExtMgr] Could not close extensions tab: {e}")


def _cleanup_extensions_tabs(port: int):
    """Close ALL chrome://extensions tabs safely.
    
    Counts total tabs first — if extensions tab is the ONLY tab,
    navigates to about:blank instead of closing (to keep Chrome alive).
    """
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        # Separate extensions tabs from other tabs
        ext_tabs = []
        other_tabs = []
        for t in targets:
            url = t.get("url", "")
            t_type = t.get("type", "")
            if t_type == "page":
                if "chrome://extensions" in url:
                    ext_tabs.append(t)
                else:
                    other_tabs.append(t)
        
        if not ext_tabs:
            return
        
        # If closing all ext tabs would leave Chrome with zero pages, keep one
        if not other_tabs and len(ext_tabs) >= 1:
            # Navigate the first one to about:blank, close the rest
            first_ws = ext_tabs[0].get("webSocketDebuggerUrl", "")
            if first_ws:
                try:
                    _cdp_evaluate(first_ws, "window.location.href = 'about:blank';")
                    log.info("[ExtMgr] Navigated extensions tab → about:blank (last tab)")
                except Exception:
                    pass
            ext_tabs = ext_tabs[1:]  # Close the remaining ones
        
        # Close all remaining extensions tabs
        for t in ext_tabs:
            tab_id = t.get("id", "")
            if tab_id:
                close_url = f"http://127.0.0.1:{port}/json/close/{tab_id}"
                for method in ("PUT", "GET"):
                    try:
                        close_req = urllib.request.Request(close_url, method=method)
                        urllib.request.urlopen(close_req, timeout=3)
                        log.info(f"[ExtMgr] Closed extensions tab {tab_id[:8]}... ({method})")
                        break
                    except urllib.error.HTTPError as e:
                        if e.code == 405:
                            continue
                        break
                    except Exception:
                        break
        
        closed = len(ext_tabs) + (1 if not other_tabs else 0)
        log.info(f"[ExtMgr] Cleaned up {closed} extensions tab(s)")
        
    except Exception as e:
        log.debug(f"[ExtMgr] Tab cleanup error: {e}")


def _get_extensions_ws_url(port: int) -> Optional[str]:
    """Find the WebSocket URL for an already-open chrome://extensions tab."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        for t in targets:
            if "chrome://extensions" in t.get("url", ""):
                return t.get("webSocketDebuggerUrl", "")
    except Exception as e:
        log.debug(f"[ExtMgr] Could not find extensions tab: {e}")
    return None


# ── CDP WebSocket Commands ──────────────────────────────────────────────

def _cdp_evaluate(ws_url: str, expression: str, timeout: float = 10.0) -> dict:
    """Execute JavaScript via CDP Runtime.evaluate over WebSocket.
    
    Args:
        ws_url: WebSocket debugger URL for the target tab
        expression: JavaScript expression to evaluate
        timeout: WebSocket timeout in seconds
    
    Returns:
        CDP response dict with 'result' key
    """
    ws = None
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout)
        msg = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            }
        })
        ws.send(msg)
        response = json.loads(ws.recv())
        return response
    except Exception as e:
        log.error(f"[ExtMgr] CDP evaluate error: {e}")
        return {"error": str(e)}
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass


# ── Shadow DOM JavaScript ───────────────────────────────────────────────

# chrome://extensions uses Polymer web components with nested shadow DOMs.
# These selectors are stable across Chrome versions and locale-independent.

JS_TOGGLE_DEVELOPER_MODE = """
(function() {
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return 'no_manager';
    
    const toolbar = mgr.shadowRoot.querySelector('extensions-toolbar');
    if (!toolbar || !toolbar.shadowRoot) return 'no_toolbar';
    
    const toggle = toolbar.shadowRoot.querySelector('#devMode');
    if (!toggle) return 'no_toggle';
    
    if (!toggle.checked) {
        toggle.click();
        return 'toggled_on';
    }
    return 'already_on';
})()
"""

JS_CLICK_LOAD_UNPACKED = """
(function() {
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return 'no_manager';
    
    const toolbar = mgr.shadowRoot.querySelector('extensions-toolbar');
    if (!toolbar || !toolbar.shadowRoot) return 'no_toolbar';
    
    const btn = toolbar.shadowRoot.querySelector('#loadUnpacked');
    if (!btn) return 'no_button';
    
    btn.click();
    return 'clicked';
})()
"""

def _js_click_remove_extension(ext_id: str) -> str:
    """Generate JS to click Remove button for a specific extension."""
    return f"""
(function() {{
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return 'no_manager';
    
    const itemsList = mgr.shadowRoot.querySelector('extensions-item-list');
    if (!itemsList || !itemsList.shadowRoot) return 'no_items_list';
    
    const items = itemsList.shadowRoot.querySelectorAll('extensions-item');
    for (const item of items) {{
        if (item.id === '{ext_id}') {{
            const removeBtn = item.shadowRoot.querySelector('#removeButton');
            if (removeBtn) {{
                removeBtn.click();
                return 'clicked_remove';
            }}
            return 'no_remove_button';
        }}
    }}
    return 'extension_not_found';
}})()
"""

JS_CONFIRM_REMOVE_DIALOG = """
(function() {
    // The remove dialog is a cr-dialog inside extensions-manager
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return 'no_manager';
    
    // Try to find and click the confirm button in the remove dialog
    const dialogs = mgr.shadowRoot.querySelectorAll('cr-dialog, extensions-dialog');
    for (const dlg of dialogs) {
        if (dlg && dlg.shadowRoot) {
            const confirmBtn = dlg.shadowRoot.querySelector('.action-button') 
                            || dlg.shadowRoot.querySelector('#confirm');
            if (confirmBtn) {
                confirmBtn.click();
                return 'confirmed';
            }
        }
        // Also check direct children
        const confirmBtn = dlg.querySelector('.action-button')
                        || dlg.querySelector('#confirm');
        if (confirmBtn) {
            confirmBtn.click();
            return 'confirmed';
        }
    }
    
    // Fallback: find any visible dialog confirm button
    const allBtns = mgr.shadowRoot.querySelectorAll('.action-button, [slot="button-container"] .action-button');
    for (const btn of allBtns) {
        if (btn.offsetParent !== null) {  // visible
            btn.click();
            return 'confirmed_fallback';
        }
    }
    
    return 'no_dialog';
})()
"""


# ── Win32 Safe Path Helper ───────────────────────────────────────────────

def _get_safe_path(folder_path: str) -> str:
    r"""Copy extension to a clean TEMP path for folder picker dialogs.
    
    When the extension path contains special characters (#, etc.) that
    cause Chrome's folder picker dialog to fail, copy the extension to
    %TEMP%\veo_extension (clean path, no special chars).
    
    Returns:
        Clean TEMP path, or original path if copy fails.
    """
    import tempfile
    import shutil
    
    safe_dir = os.path.join(tempfile.gettempdir(), "veo_extension")
    
    try:
        # Remove old copy
        if os.path.exists(safe_dir):
            shutil.rmtree(safe_dir, ignore_errors=True)
        
        # Copy extension to clean path
        shutil.copytree(folder_path, safe_dir)
        
        # Verify manifest exists in copy
        if os.path.isfile(os.path.join(safe_dir, "manifest.json")):
            log.info(f"[ExtMgr] Copied extension to safe path: {safe_dir}")
            return safe_dir
        else:
            log.warning(f"[ExtMgr] Copy missing manifest.json: {safe_dir}")
    except Exception as e:
        log.warning(f"[ExtMgr] _get_safe_path copy error: {e}")
    
    return folder_path  # Fallback to original


# ── Win32 Folder Picker (100% Keyboard-Free) ────────────────────────────

def _type_folder_path_win32(folder_path: str, delay: float = 0.05):
    """Set folder path in Chrome's 'Load unpacked' dialog and confirm.
    
    100% keyboard-free: uses only Win32 message APIs (SendMessageW).
    No SendInput, no keyboard simulation, no clipboard.
    
    Strategy:
    1. FindWindowW("#32770") — find the dialog
    2. GetDlgItem(1148) — find "File name" ComboBox
    3. SendMessageW(WM_SETTEXT) — set path text
    4. GetDlgItem(1) — find OK/Open button
    5. SendMessageW(BM_CLICK) — click OK (× 2: navigate then confirm)
    """
    import ctypes
    import ctypes.wintypes
    
    user32 = ctypes.windll.user32
    
    # ── Win32 Constants ──
    WM_SETTEXT = 0x000C
    BM_CLICK = 0x00F5
    CB_SETCURSEL = 0x014E
    WM_COMMAND = 0x0111
    BN_CLICKED = 0
    IDOK = 1                     # Standard OK/Open button ID
    FILE_NAME_COMBO_ID = 1148    # "File name:" ComboBoxEx32
    
    # ── Step 1: Wait for and find folder picker dialog ──
    log.info("[ExtMgr] Waiting for folder picker dialog...")
    dialog_hwnd = None
    
    for attempt in range(20):  # Wait up to 10 seconds
        time.sleep(0.5)
        
        # Enumerate all #32770 (standard dialog) windows
        hwnd = user32.FindWindowW("#32770", None)
        while hwnd:
            title_len = user32.GetWindowTextLengthW(hwnd)
            if title_len > 0:
                title_buf = ctypes.create_unicode_buffer(title_len + 1)
                user32.GetWindowTextW(hwnd, title_buf, title_len + 1)
                title = title_buf.value.lower()
                # Chrome's folder picker — locale-aware keywords
                if any(kw in title for kw in (
                    "open", "select", "browse", "folder", "load",
                    "öffnen", "chọn", "mở", "tải", "parcourir"
                )):
                    dialog_hwnd = hwnd
                    log.info(f"[ExtMgr] Found dialog: '{title_buf.value}' (HWND={hwnd})")
                    break
            hwnd = user32.FindWindowExW(None, hwnd, "#32770", None)
        
        if dialog_hwnd:
            break
    
    if not dialog_hwnd:
        log.error("[ExtMgr] ❌ Could not find folder picker dialog after 10s")
        return False
    
    # ── Step 2: Find the "File name" edit control ──
    target_edit = None
    
    # Method A: GetDlgItem(1148) → ComboBoxEx32 → traverse to Edit
    combo_hwnd = user32.GetDlgItem(dialog_hwnd, FILE_NAME_COMBO_ID)
    if combo_hwnd:
        child = combo_hwnd
        for _ in range(3):
            inner = user32.FindWindowExW(child, None, "ComboBox", None)
            if inner:
                child = inner
                continue
            inner = user32.FindWindowExW(child, None, "Edit", None)
            if inner:
                child = inner
                break
        target_edit = child
        log.info(f"[ExtMgr] Found filename control via GetDlgItem (HWND={target_edit})")
    
    # Method B: Enumerate all child windows, find Edit controls
    if not target_edit:
        found_edits = []
        
        @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _enum_children(child_hwnd, lparam):
            class_buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(child_hwnd, class_buf, 64)
            cls = class_buf.value
            if cls in ("Edit", "ComboBox", "ComboBoxEx32"):
                found_edits.append((child_hwnd, cls))
            return True
        
        user32.EnumChildWindows(dialog_hwnd, _enum_children, 0)
        
        if found_edits:
            # The file name edit is usually the last Edit control
            for hwnd_c, cls in reversed(found_edits):
                if cls == "Edit":
                    target_edit = hwnd_c
                    break
            if not target_edit:
                target_edit = found_edits[-1][0]
            log.info(f"[ExtMgr] Found filename control via enum (HWND={target_edit})")
    
    if not target_edit:
        log.error("[ExtMgr] ❌ Could not find filename edit control in dialog")
        return False
    
    # ── Step 3: Set the path text directly via WM_SETTEXT ──
    # Normalize to backslashes for Windows folder picker dialog
    folder_path_normalized = str(folder_path).replace("/", "\\")
    
    # Convert to junction-based safe path if path contains special characters
    # (#, etc.) that cause the folder picker's navigation to fail
    if any(c in folder_path_normalized for c in '#'):
        log.warning(f"[ExtMgr] Path has '#' — creating junction: {folder_path_normalized}")
        folder_path_normalized = _get_safe_path(folder_path_normalized)
        log.warning(f"[ExtMgr] Using path for dialog: {folder_path_normalized}")
    
    WM_GETTEXT = 0x000D
    WM_GETTEXTLENGTH = 0x000E
    EM_SETSEL = 0x00B1
    WM_SETFOCUS = 0x0007
    
    def _set_and_verify_text(edit_hwnd, path_text, retries=3):
        """Set text on edit control and verify it was accepted."""
        for attempt in range(retries):
            # Focus the control
            user32.SendMessageW(edit_hwnd, WM_SETFOCUS, 0, 0)
            time.sleep(0.1)
            
            # Select all existing text
            user32.SendMessageW(edit_hwnd, EM_SETSEL, 0, -1)
            time.sleep(0.05)
            
            # Set the new text
            path_wstr = ctypes.c_wchar_p(path_text)
            user32.SendMessageW(edit_hwnd, WM_SETTEXT, 0, path_wstr)
            time.sleep(0.3)
            
            # Verify by reading back
            text_len = user32.SendMessageW(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)
            if text_len > 0:
                buf = ctypes.create_unicode_buffer(text_len + 1)
                user32.SendMessageW(edit_hwnd, WM_GETTEXT, text_len + 1, buf)
                actual = buf.value.strip()
                # Check if path matches (case-insensitive, ignore trailing slash)
                if actual.rstrip("\\").lower() == path_text.rstrip("\\").lower():
                    log.info(f"[ExtMgr] ✅ Path verified in edit control (attempt {attempt+1}): {actual}")
                    return True
                else:
                    log.warning(f"[ExtMgr] ⚠️ Path mismatch (attempt {attempt+1}): expected='{path_text}' actual='{actual}'")
            else:
                log.warning(f"[ExtMgr] ⚠️ Edit control empty after WM_SETTEXT (attempt {attempt+1})")
            
            time.sleep(0.3)
        
        log.error(f"[ExtMgr] ❌ Could not set folder path after {retries} attempts")
        return False
    
    if not _set_and_verify_text(target_edit, folder_path_normalized):
        return False
    
    log.info(f"[ExtMgr] Set folder path via WM_SETTEXT: {folder_path_normalized}")
    
    # ── Step 4: Navigate and confirm the folder selection ──
    # BM_CLICK alone selects what's in the TREE VIEW (defaults to D:\Downloads).
    # Enter alone navigates but then clears the filename field.
    # HYBRID: Enter navigates the tree to our path → BM_CLICK confirms it.
    
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    VK_RETURN = 0x0D
    IDOK = 1
    BM_CLICK = 0x00F5
    
    # lParam for Enter key: scan code 0x1C, repeat count 1
    ENTER_DOWN_LPARAM = (0x1C << 16) | 1
    ENTER_UP_LPARAM = (0x1C << 16) | 1 | (3 << 30)
    
    # Step 4a: Press Enter on edit control → navigates folder tree to our path
    # CRITICAL: Wait for dialog to process WM_SETTEXT before pressing Enter.
    # Without delay, Enter navigates to the PREVIOUS path (race condition).
    time.sleep(1.0)  # Let dialog fully process the new text
    
    # Re-verify text is still set (defensive)
    _set_and_verify_text(target_edit, folder_path_normalized, retries=1)
    time.sleep(0.5)
    
    log.info(f"[ExtMgr] Pressing Enter to navigate to: {folder_path_normalized}")
    user32.SendMessageW(target_edit, WM_KEYDOWN, VK_RETURN, ENTER_DOWN_LPARAM)
    time.sleep(0.05)
    user32.SendMessageW(target_edit, WM_KEYUP, VK_RETURN, ENTER_UP_LPARAM)
    time.sleep(2.0)
    
    if not user32.IsWindow(dialog_hwnd):
        # Enter might have already confirmed (unlikely but handle it)
        log.info(f"[ExtMgr] ✅ Folder selected via Enter: {folder_path_normalized}")
        return True
    
    # Step 4b: Click "Select Folder" button — tree is now on our folder
    ok_btn = user32.GetDlgItem(dialog_hwnd, IDOK)
    if ok_btn:
        log.info("[ExtMgr] Clicking Select Folder to confirm navigated directory...")
        user32.SendMessageW(ok_btn, BM_CLICK, 0, 0)
        time.sleep(1.5)
    
    if not user32.IsWindow(dialog_hwnd):
        log.info(f"[ExtMgr] ✅ Folder picker completed: {folder_path_normalized}")
        return True
    
    # Fallback: re-set path and try Enter one more time
    log.warning("[ExtMgr] Dialog still open — retry: re-set path + Enter")
    _set_and_verify_text(target_edit, folder_path_normalized, retries=1)
    time.sleep(0.3)
    user32.PostMessageW(target_edit, WM_KEYDOWN, VK_RETURN, ENTER_DOWN_LPARAM)
    time.sleep(0.05)
    user32.PostMessageW(target_edit, WM_KEYUP, VK_RETURN, ENTER_UP_LPARAM)
    time.sleep(2.0)
    
    if user32.IsWindow(dialog_hwnd):
        # Final: click OK
        if ok_btn:
            user32.SendMessageW(ok_btn, BM_CLICK, 0, 0)
            time.sleep(1.0)
    
    if user32.IsWindow(dialog_hwnd):
        log.warning("[ExtMgr] ⚠️ Dialog still open after all attempts")
        return False
    
    log.info(f"[ExtMgr] ✅ Folder picker completed: {folder_path_normalized}")
    return True


# ── Public API ──────────────────────────────────────────────────────────

def install_extension(port: int, extension_dir: str, **kwargs) -> bool:
    """Install unpacked extension into Chrome via CDP + Win32.
    
    Thread-safe: uses per-port lock to prevent concurrent installs.
    Handles hidden browsers: shows Chrome temporarily for Win32 dialog.
    
    Steps:
    1. Open chrome://extensions via CDP
    2. Toggle Developer Mode ON via shadow DOM JS
    3. Click "Load unpacked" via shadow DOM JS
    4. Handle folder picker dialog via Win32 (keyboard-free)
    5. Clean up extensions tabs (safe — avoids killing Chrome)
    6. Verify extension loaded via CDP
    
    Args:
        port: Chrome CDP port
        extension_dir: Absolute path to extension directory
    
    Returns:
        True if extension installed successfully
    """
    # Per-port lock prevents concurrent installs hitting the same folder picker
    with _install_locks_guard:
        if port not in _install_locks:
            _install_locks[port] = threading.Lock()
        lock = _install_locks[port]
    
    with lock:
        return _install_extension_impl(port, extension_dir)


def _show_chrome_for_install(port: int) -> bool:
    """Show Chrome window if hidden (Win32 folder picker needs visible window).
    
    Returns True if it was hidden (so caller can re-hide after install).
    """
    import ctypes
    user32 = ctypes.windll.user32
    SW_SHOW = 5
    
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        for t in targets:
            if t.get("type") == "page":
                title = t.get("title", "")
                if title:
                    hwnd = user32.FindWindowW(None, title)
                    if hwnd and not user32.IsWindowVisible(hwnd):
                        user32.ShowWindow(hwnd, SW_SHOW)
                        user32.SetForegroundWindow(hwnd)
                        time.sleep(0.5)
                        log.info(f"[ExtMgr] Temporarily showed Chrome window for install")
                        return True
    except Exception:
        pass
    return False


def _hide_chrome_after_install(port: int):
    """Re-hide Chrome window after install."""
    import ctypes
    user32 = ctypes.windll.user32
    SW_HIDE = 0
    
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        for t in targets:
            if t.get("type") == "page":
                title = t.get("title", "")
                if title:
                    hwnd = user32.FindWindowW(None, title)
                    if hwnd:
                        user32.ShowWindow(hwnd, SW_HIDE)
                        log.info(f"[ExtMgr] Re-hid Chrome window after install")
                        return
    except Exception:
        pass


def _install_extension_impl(port: int, extension_dir: str) -> bool:
    """Internal implementation — actually installs the extension."""
    log.info(f"[ExtMgr] 🔧 Installing extension: {extension_dir}")
    
    # Temporarily show Chrome window if hidden (Win32 dialog needs it visible)
    was_hidden = _show_chrome_for_install(port)
    
    try:
        # Step 1: Open chrome://extensions
        ws_url = _open_extensions_page(port)
        if not ws_url:
            return False
        
        # Wait for page to load
        time.sleep(2.5)
        
        # Re-fetch ws_url in case it changed
        ws_url = _get_extensions_ws_url(port) or ws_url
        
        # Step 2: Toggle Developer Mode ON
        result = _cdp_evaluate(ws_url, JS_TOGGLE_DEVELOPER_MODE)
        dev_mode_result = result.get("result", {}).get("result", {}).get("value", "unknown")
        log.info(f"[ExtMgr] Developer Mode: {dev_mode_result}")
        
        if dev_mode_result == "toggled_on":
            time.sleep(1)  # Wait for UI to update after toggle
        
        # Step 3: Click "Load unpacked"
        result = _cdp_evaluate(ws_url, JS_CLICK_LOAD_UNPACKED)
        load_result = result.get("result", {}).get("result", {}).get("value", "unknown")
        log.info(f"[ExtMgr] Load Unpacked: {load_result}")
        
        if load_result != "clicked":
            log.error(f"[ExtMgr] ❌ Failed to click Load Unpacked: {load_result}")
            return False
        
        # Step 4: Handle folder picker via Win32 (keyboard-free)
        picker_ok = _type_folder_path_win32(extension_dir)
        if picker_ok is False:
            log.error("[ExtMgr] ❌ Folder picker failed")
            return False
        
        # Step 5: Wait for Chrome to process the loaded extension
        # DON'T close extensions tab yet — Chrome needs it to finish registration
        time.sleep(3)
        
        # Step 5b: Check if extension card appeared in DOM (diagnostic)
        ws_url = _get_extensions_ws_url(port)
        if ws_url:
            try:
                ext_name = EXTENSION_NAME
                js_check = f"""
(function() {{
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return 'no_manager';
    
    const itemsList = mgr.shadowRoot.querySelector('extensions-item-list')
                   || mgr.shadowRoot.querySelector('#items-list');
    if (!itemsList || !itemsList.shadowRoot) return 'no_items_list';
    
    const cards = itemsList.shadowRoot.querySelectorAll('extensions-item');
    for (const card of cards) {{
        if (!card.shadowRoot) continue;
        const nameEl = card.shadowRoot.querySelector('#name');
        if (nameEl && nameEl.textContent.trim() === '{ext_name}') {{
            // Check for errors
            const errBtn = card.shadowRoot.querySelector('#errors-button');
            const hasErrors = errBtn && errBtn.offsetParent !== null;
            const enableToggle = card.shadowRoot.querySelector('#enableToggle');
            const isEnabled = enableToggle ? enableToggle.checked : null;
            return JSON.stringify({{
                id: card.id,
                hasErrors: hasErrors,
                isEnabled: isEnabled,
            }});
        }}
    }}
    return 'not_found';
}})()
"""
                result = _cdp_evaluate(ws_url, js_check, timeout=5.0)
                card_info = result.get("result", {}).get("result", {}).get("value", "unknown")
                log.info(f"[ExtMgr] Post-install card check: {card_info}")
                
                # If extension has errors, read the actual error messages
                if isinstance(card_info, str) and card_info not in ("not_found", "no_manager", "no_items_list", "unknown"):
                    import json as _json
                    try:
                        info = _json.loads(card_info)
                        if info.get("hasErrors"):
                            log.warning(f"[ExtMgr] ⚠️ Extension has errors! ID={info.get('id')}")
                            # Read error details by clicking Errors button and reading error list
                            ext_id = info.get("id", "")
                            js_errors = f"""
(function() {{
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return 'no_manager';
    const itemsList = mgr.shadowRoot.querySelector('extensions-item-list')
                   || mgr.shadowRoot.querySelector('#items-list');
    if (!itemsList || !itemsList.shadowRoot) return 'no_items';
    const cards = itemsList.shadowRoot.querySelectorAll('extensions-item');
    for (const card of cards) {{
        if (card.id !== '{ext_id}') continue;
        if (!card.shadowRoot) return 'no_shadow';
        // Click errors button to expand
        const errBtn = card.shadowRoot.querySelector('#errors-button');
        if (errBtn) errBtn.click();
        // Read error section
        const errSection = card.shadowRoot.querySelector('extensions-error-list');
        if (errSection && errSection.shadowRoot) {{
            const items = errSection.shadowRoot.querySelectorAll('.error-message');
            const errors = [];
            items.forEach(el => errors.push(el.textContent.trim().substring(0, 200)));
            return JSON.stringify(errors);
        }}
        // Fallback: try to read any visible error text
        const allText = card.shadowRoot.textContent || '';
        const errMatch = allText.match(/Error[^\\n]{{0,300}}/gi);
        return JSON.stringify(errMatch || ['no_error_text_found']);
    }}
    return 'card_not_found';
}})()
"""
                            err_result = _cdp_evaluate(ws_url, js_errors, timeout=5.0)
                            err_text = err_result.get("result", {}).get("result", {}).get("value", "unknown")
                            log.warning(f"[ExtMgr] Extension errors: {err_text}")
                    except Exception as e:
                        log.debug(f"[ExtMgr] Error reading extension errors: {e}")
                        
            except Exception as e:
                log.debug(f"[ExtMgr] Post-install DOM check error: {e}")
        
        # Step 6: Verify extension loaded — poll up to 15s (1s interval)
        # Keep extensions tab open during polling — Chrome needs it for initial registration
        for verify_attempt in range(15):
            time.sleep(1)
            if is_extension_loaded(port):
                log.info(f"[ExtMgr] ✅ Extension installed and verified! (after {verify_attempt + 1}s)")
                _cleanup_extensions_tabs(port)
                
                # Step 6b: Wake the service worker — ensure it connects WebSocket
                # MV3 SW may have ws stuck in bad state (CONNECTING on wrong port)
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        targets = json.loads(resp.read())
                    for t in targets:
                        if t.get("type") == "service_worker" and "chrome-extension://" in t.get("url", ""):
                            sw_ws = t.get("webSocketDebuggerUrl", "")
                            if sw_ws:
                                log.info(f"[ExtMgr] 🔌 Waking service worker via CDP: {sw_ws[:60]}...")
                                # Diagnostic + force reconnect + inject content.js
                                js_wake = """
(function() {
    const info = {
        ws_state: ws ? ws.readyState : 'null',
        wsConnected: wsConnected,
        portIndex: currentPortIndex,
        tabCount: Object.keys(tabState).length,
    };
    // Force-reset and reconnect on correct port
    try { if (ws) ws.close(); } catch(e) {}
    ws = null;
    wsConnected = false;
    currentPortIndex = 0;
    connectWebSocket();
    // Re-inject content.js into VEO tabs (needed for reCAPTCHA)
    injectExistingTabs();
    return JSON.stringify(info);
})()
"""
                                result = _cdp_evaluate(sw_ws, js_wake, timeout=5.0)
                                diag = result.get("result", {}).get("result", {}).get("value", "unknown")
                                log.info(f"[ExtMgr] ✅ SW wake-up result: {diag}")
                            break
                except Exception as e:
                    log.debug(f"[ExtMgr] SW wake-up error (non-fatal): {e}")
                
                return True
        
        # Step 7: Diagnostic — log what CDP /json shows
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                targets = json.loads(resp.read())
            ext_targets = [t for t in targets if "chrome-extension://" in t.get("url", "")]
            log.warning(f"[ExtMgr] ⚠️ Extension targets in CDP: {len(ext_targets)}")
            for t in ext_targets:
                log.warning(f"[ExtMgr]   type={t.get('type')} title={t.get('title')!r} url={t.get('url','')[:80]}")
        except Exception:
            pass
        
        _cleanup_extensions_tabs(port)
        log.warning("[ExtMgr] ⚠️ Install flow completed but extension not detected after 15s")
        return False
        
    except Exception as e:
        log.error(f"[ExtMgr] ❌ Install error: {e}")
        return False
    finally:
        # Re-hide Chrome if it was hidden before install
        if was_hidden:
            _hide_chrome_after_install(port)


def uninstall_extension(port: int, ext_id: Optional[str] = None) -> bool:
    """Uninstall extension from Chrome via CDP.
    
    Steps:
    1. Get extension ID (if not provided)
    2. Open chrome://extensions via CDP
    3. Click Remove button on extension card via shadow DOM JS
    4. Confirm removal dialog
    5. Verify extension removed
    
    Args:
        port: Chrome CDP port
        ext_id: Extension ID to remove (auto-detected if None)
    
    Returns:
        True if extension removed successfully
    """
    # Get extension ID
    if not ext_id:
        ext_id = get_extension_id(port)
    
    if not ext_id:
        log.warning("[ExtMgr] No extension found to uninstall")
        return True  # Nothing to uninstall = success
    
    log.info(f"[ExtMgr] 🗑️ Uninstalling extension: {ext_id}")
    
    try:
        # Step 1: Open chrome://extensions
        ws_url = _open_extensions_page(port)
        if not ws_url:
            return False
        
        time.sleep(2.5)
        ws_url = _get_extensions_ws_url(port) or ws_url
        
        # Step 2: Click Remove on extension card
        js_remove = _js_click_remove_extension(ext_id)
        result = _cdp_evaluate(ws_url, js_remove)
        remove_result = result.get("result", {}).get("result", {}).get("value", "unknown")
        log.info(f"[ExtMgr] Remove click: {remove_result}")
        
        if remove_result not in ("clicked_remove",):
            log.error(f"[ExtMgr] ❌ Failed to click Remove: {remove_result}")
            _cleanup_extensions_tabs(port)
            return False
        
        # Step 3: Confirm removal dialog
        time.sleep(1)
        result = _cdp_evaluate(ws_url, JS_CONFIRM_REMOVE_DIALOG)
        confirm_result = result.get("result", {}).get("result", {}).get("value", "unknown")
        log.info(f"[ExtMgr] Confirm dialog: {confirm_result}")
        
        # Step 4: Close extensions tab
        time.sleep(1)
        _cleanup_extensions_tabs(port)
        
        # Step 5: Verify extension removed
        time.sleep(2)
        if not is_extension_loaded(port):
            log.info("[ExtMgr] ✅ Extension uninstalled successfully!")
            return True
        
        log.warning("[ExtMgr] ⚠️ Extension still detected after uninstall")
        return False
        
    except Exception as e:
        log.error(f"[ExtMgr] ❌ Uninstall error: {e}")
        _cleanup_extensions_tabs(port)
        return False


def _find_extension_id_via_dom(port: int) -> Optional[str]:
    """Find our extension ID via chrome://extensions page DOM.
    
    Unlike get_extension_id() which needs an active service_worker in CDP /json,
    this works even when the MV3 service worker is suspended — searches
    extension cards by name in the shadow DOM.
    
    Returns:
        Extension ID string or None if not found.
    """
    ws_url = _open_extensions_page(port)
    if not ws_url:
        return None
    
    time.sleep(2.5)
    ws_url = _get_extensions_ws_url(port) or ws_url
    
    ext_name = EXTENSION_NAME  # "VEO Pro Max Bridge"
    js = f"""
(function() {{
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return null;
    
    const itemsList = mgr.shadowRoot.querySelector('extensions-item-list')
                   || mgr.shadowRoot.querySelector('#items-list');
    if (!itemsList || !itemsList.shadowRoot) return null;
    
    const cards = itemsList.shadowRoot.querySelectorAll('extensions-item');
    for (const card of cards) {{
        if (!card.shadowRoot) continue;
        const nameEl = card.shadowRoot.querySelector('#name');
        if (nameEl && nameEl.textContent.trim() === '{ext_name}') {{
            return card.id;  // extension ID
        }}
    }}
    return null;
}})()
"""
    try:
        result = _cdp_evaluate(ws_url, js, timeout=5.0)
        ext_id = result.get("result", {}).get("result", {}).get("value")
        if ext_id:
            log.info(f"[ExtMgr] Found extension via DOM: {ext_id}")
        else:
            log.debug(f"[ExtMgr] Extension not found in DOM")
        return ext_id
    except Exception as e:
        log.debug(f"[ExtMgr] DOM extension search error: {e}")
        return None
    finally:
        _cleanup_extensions_tabs(port)


def reinstall_extension(port: int, extension_dir: str, **kwargs) -> bool:
    """Uninstall then reinstall extension.
    
    Uses DOM-based detection to find existing extension even when
    MV3 service worker is suspended (CDP /json won't show it).
    
    Args:
        port: Chrome CDP port
        extension_dir: Absolute path to extension directory
    
    Returns:
        True if reinstall succeeded
    """
    log.info(f"[ExtMgr] 🔄 Reinstalling extension...")
    
    # Step 1: Find existing extension via DOM (works with suspended service workers)
    ext_id = get_extension_id(port)  # Try fast CDP /json first
    if not ext_id:
        ext_id = _find_extension_id_via_dom(port)  # Fallback: DOM search
    
    # Step 2: Uninstall if found
    if ext_id:
        log.info(f"[ExtMgr] Found existing extension {ext_id} — removing before reinstall")
        if not uninstall_extension(port, ext_id=ext_id):
            log.warning("[ExtMgr] Uninstall failed — trying install anyway")
        time.sleep(2)
    else:
        log.info("[ExtMgr] No existing extension found — fresh install")
    
    # Step 3: Install
    return install_extension(port, extension_dir)


def _update_unpacked_extension(port: int, extension_dir: str) -> bool:
    """Update unpacked extension files and trigger Chrome to reload them.
    
    For version updates, this is MUCH faster and more reliable than
    uninstall+reinstall (which has confirm dialog issues on Chrome v137+).
    
    Steps:
    1. Refresh temp copy (if # path) with updated source files
    2. Click the extension's "Update" (↻) button via chrome://extensions DOM
    3. Verify new version loaded
    
    Returns:
        True if update succeeded, False if should fall back to reinstall.
    """
    ext_id = get_extension_id(port)
    if not ext_id:
        log.debug("[ExtMgr] Cannot update — no extension ID found")
        return False
    
    # Step 1: Refresh temp copy if path has special characters
    if any(c in extension_dir for c in '#'):
        _get_safe_path(extension_dir)  # This deletes old temp + copies fresh
        log.info("[ExtMgr] Refreshed temp extension copy for update")
    
    # Step 2: Open chrome://extensions and click the update/reload button
    ws_url = _open_extensions_page(port)
    if not ws_url:
        return False
    
    time.sleep(2.0)
    ws_url = _get_extensions_ws_url(port) or ws_url
    
    # Click the "Update" button on the extension toolbar OR the per-extension reload
    js_update = f"""
(function() {{
    const mgr = document.querySelector('extensions-manager');
    if (!mgr || !mgr.shadowRoot) return 'no_manager';
    
    // Method 1: Click per-extension reload/update button
    const itemsList = mgr.shadowRoot.querySelector('extensions-item-list')
                   || mgr.shadowRoot.querySelector('#items-list');
    if (itemsList && itemsList.shadowRoot) {{
        const items = itemsList.shadowRoot.querySelectorAll('extensions-item');
        for (const item of items) {{
            if (item.id === '{ext_id}' && item.shadowRoot) {{
                // Try reload button (present for unpacked extensions)
                const reloadBtn = item.shadowRoot.querySelector('#reload-button')
                               || item.shadowRoot.querySelector('[title="Reload"]')
                               || item.shadowRoot.querySelector('cr-icon-button[iron-icon="cr:refresh"]');
                if (reloadBtn) {{
                    reloadBtn.click();
                    return 'clicked_reload';
                }}
            }}
        }}
    }}
    
    // Method 2: Click global "Update" button in toolbar
    const toolbar = mgr.shadowRoot.querySelector('extensions-toolbar');
    if (toolbar && toolbar.shadowRoot) {{
        const updateBtn = toolbar.shadowRoot.querySelector('#updateNow')
                       || toolbar.shadowRoot.querySelector('#update-button');
        if (updateBtn) {{
            updateBtn.click();
            return 'clicked_global_update';
        }}
        // Method 3: Trigger the update via Dev mode reload
        const devToggle = toolbar.shadowRoot.querySelector('#devMode');
        // Dev mode should already be on; try the "Update" 
    }}
    
    return 'no_update_button';
}})()
"""
    try:
        result = _cdp_evaluate(ws_url, js_update, timeout=5.0)
        update_result = result.get("result", {}).get("result", {}).get("value", "unknown")
        log.info(f"[ExtMgr] Update click result: {update_result}")
        
        if update_result in ("clicked_reload", "clicked_global_update"):
            # Wait for Chrome to process the reload
            time.sleep(3)
            
            # Verify new version
            _cleanup_extensions_tabs(port)
            new_ver = _get_installed_extension_version(port)
            local_ver = get_local_extension_version()
            if new_ver and new_ver == local_ver:
                log.info(f"[ExtMgr] ✅ Extension updated to v{new_ver} via reload")
                return True
            else:
                log.warning(f"[ExtMgr] Update click succeeded but version still {new_ver} (expected {local_ver})")
                return False
        else:
            log.debug(f"[ExtMgr] No update button found: {update_result}")
            _cleanup_extensions_tabs(port)
            return False
    except Exception as e:
        log.debug(f"[ExtMgr] Extension update error: {e}")
        _cleanup_extensions_tabs(port)
        return False


def install_if_needed(port: int, extension_dir: str, **kwargs) -> bool:
    """Install extension if missing, or update/reinstall if version outdated.
    
    Checks:
    1. Is extension loaded at all? → install
    2. Is installed version != local version? → update (fast) → reinstall (fallback)
    
    Drop-in replacement for auto_install_extension.auto_install_extension_if_needed().
    Called from chrome_manager.launch_chrome() and ensure_chrome_running().
    
    Args:
        port: Chrome CDP port
        extension_dir: Absolute path to extension directory
    
    Returns:
        True if extension is (or becomes) loaded and up-to-date
    """
    # Retry a few times — on startup, service worker may take seconds to register
    loaded = is_extension_loaded(port)
    if not loaded:
        for attempt in range(1, 4):
            time.sleep(2)
            loaded = is_extension_loaded(port)
            if loaded:
                log.debug(f"[ExtMgr] Extension appeared after {attempt * 2}s wait")
                break
    
    if not loaded:
        log.info("[ExtMgr] Extension not loaded after retries — reinstalling (will remove stale if any)...")
        return reinstall_extension(port, extension_dir)
    
    # Version check: compare installed vs local manifest
    local_ver = get_local_extension_version()
    if local_ver:
        installed_ver = _get_installed_extension_version(port)
        if installed_ver and installed_ver != local_ver:
            log.warning(f"[ExtMgr] ⚠️ Version mismatch: installed={installed_ver}, local={local_ver}")
            
            # Try fast update first (refresh files + reload button)
            if _update_unpacked_extension(port, extension_dir):
                return True
            
            # Fallback: full reinstall
            log.warning(f"[ExtMgr] Fast update failed — falling back to full reinstall")
            return reinstall_extension(port, extension_dir)
        elif installed_ver:
            log.info(f"[ExtMgr] Extension v{installed_ver} up-to-date — skipping")
        else:
            # Could not read installed version — assume OK
            log.info(f"[ExtMgr] Extension loaded (version unknown), local v{local_ver} — skipping")
    else:
        log.info(f"[ExtMgr] Extension already installed — skipping")
    
    return True


def _get_installed_extension_version(port: int) -> Optional[str]:
    """Read the version of our installed extension via chrome.management CDP API.
    
    Uses Runtime.evaluate on the extensions page to query the extension version
    from the chrome.management API.
    
    Returns:
        Version string (e.g. '2.0') or None if cannot determine.
    """
    ext_id = get_extension_id(port)
    if not ext_id:
        return None
    
    # Use CDP to evaluate chrome.management.get() on the extensions page
    ws_url = _open_extensions_page(port)
    if not ws_url:
        return None
    
    time.sleep(1.5)
    ws_url = _get_extensions_ws_url(port) or ws_url
    
    try:
        js = f"""
        new Promise((resolve) => {{
            if (chrome && chrome.management && chrome.management.get) {{
                chrome.management.get('{ext_id}', (info) => {{
                    resolve(info ? info.version : null);
                }});
            }} else {{
                // Fallback: read from DOM
                const mgr = document.querySelector('extensions-manager');
                if (!mgr || !mgr.shadowRoot) {{ resolve(null); return; }}
                const itemsList = mgr.shadowRoot.querySelector('#items-list');
                if (!itemsList || !itemsList.shadowRoot) {{ resolve(null); return; }}
                const cards = itemsList.shadowRoot.querySelectorAll('extensions-item');
                for (const card of cards) {{
                    if (card.id === '{ext_id}' && card.shadowRoot) {{
                        const verEl = card.shadowRoot.querySelector('#version');
                        if (verEl) {{ resolve(verEl.textContent.trim()); return; }}
                    }}
                }}
                resolve(null);
            }}
        }})
        """
        result = _cdp_evaluate(ws_url, js, timeout=8.0)
        version = result.get("result", {}).get("result", {}).get("value")
        
        # Clean up extensions tab
        _cleanup_extensions_tabs(port)
        
        if version:
            log.info(f"[ExtMgr] Installed extension version: {version}")
        return version
    except Exception as e:
        log.debug(f"[ExtMgr] Could not read extension version: {e}")
        _cleanup_extensions_tabs(port)
        return None

