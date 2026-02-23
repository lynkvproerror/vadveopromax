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


# ── Extension Detection (Single Source of Truth) ─────────────────────────

def _is_our_extension(target: dict) -> bool:
    """Check if a CDP target belongs to OUR extension (not any random one).
    
    Verifies:
    - URL is chrome-extension://
    - Target type is service_worker or background_page
    - Title contains EXTENSION_NAME *or* URL contains background.js
    """
    url = target.get("url", "")
    title = target.get("title", "")
    target_type = target.get("type", "")
    
    if "chrome-extension://" not in url:
        return False
    if target_type not in ("service_worker", "background_page"):
        return False
    # Verify identity: title match OR background.js in URL
    if EXTENSION_NAME.lower() in title.lower():
        return True
    if "background.js" in url:
        return True
    return False


def is_extension_loaded(port: int) -> bool:
    """Check if OUR extension is loaded by querying CDP /json targets.
    
    Verifies the service_worker title matches EXTENSION_NAME to avoid
    false positives from other installed extensions.
    
    Returns:
        True if our extension service worker is detected.
    """
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read())
        
        for t in targets:
            if _is_our_extension(t):
                log.debug(f"[ExtMgr] Extension loaded: {t.get('url', '')}")
                return True
    except Exception as e:
        log.debug(f"[ExtMgr] CDP check error: {e}")
    
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
    
    # ── Step 4: Submit the path by sending Enter to the edit control ──
    # NOTE: BM_CLICK on the OK button does NOT use the filename text!
    # It selects whatever is highlighted in the folder tree view.
    # Instead, send VK_RETURN directly to the edit control via PostMessage.
    # This is NOT keyboard simulation (SendInput) — it's a targeted window message.
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    VK_RETURN = 0x0D
    
    # lParam for Enter key: scan code 0x1C, repeat count 1
    ENTER_DOWN_LPARAM = (0x1C << 16) | 1          # 0x001C0001
    ENTER_UP_LPARAM = (0x1C << 16) | 1 | (3 << 30)  # 0xC01C0001 (bit 30+31 set)
    
    # First Enter: navigates to the folder path
    log.info(f"[ExtMgr] Sending Enter to edit control to navigate...")
    user32.PostMessageW(target_edit, WM_KEYDOWN, VK_RETURN, ENTER_DOWN_LPARAM)
    time.sleep(0.05)
    user32.PostMessageW(target_edit, WM_KEYUP, VK_RETURN, ENTER_UP_LPARAM)
    time.sleep(2.0)
    
    # Check if dialog is still open
    if user32.IsWindow(dialog_hwnd):
        # Re-verify the path is still set (dialog may have cleared it after navigation)
        _set_and_verify_text(target_edit, folder_path_normalized, retries=1)
        time.sleep(0.3)
        
        # Second Enter: confirms the folder selection
        log.info("[ExtMgr] Dialog still open — sending Enter again to confirm...")
        user32.PostMessageW(target_edit, WM_KEYDOWN, VK_RETURN, ENTER_DOWN_LPARAM)
        time.sleep(0.05)
        user32.PostMessageW(target_edit, WM_KEYUP, VK_RETURN, ENTER_UP_LPARAM)
        time.sleep(1.5)
    
    # Verify dialog dismissed
    if user32.IsWindow(dialog_hwnd):
        # Final fallback: try BM_CLICK on OK button
        log.warning("[ExtMgr] Dialog still open — trying BM_CLICK on OK...")
        ok_btn = user32.GetDlgItem(dialog_hwnd, IDOK)
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
        
        # Step 5: Clean up extensions tabs (safe — avoids killing Chrome)
        time.sleep(2)
        _cleanup_extensions_tabs(port)
        
        # Step 6: Verify extension loaded
        time.sleep(2)
        if is_extension_loaded(port):
            log.info("[ExtMgr] ✅ Extension installed and verified!")
            return True
        
        # Give more time
        time.sleep(3)
        if is_extension_loaded(port):
            log.info("[ExtMgr] ✅ Extension installed (delayed verification)")
            return True
        
        log.warning("[ExtMgr] ⚠️ Install flow completed but extension not detected")
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


def reinstall_extension(port: int, extension_dir: str, **kwargs) -> bool:
    """Uninstall then reinstall extension.
    
    Args:
        port: Chrome CDP port
        extension_dir: Absolute path to extension directory
    
    Returns:
        True if reinstall succeeded
    """
    log.info(f"[ExtMgr] 🔄 Reinstalling extension...")
    
    # Step 1: Uninstall (if present)
    if is_extension_loaded(port):
        if not uninstall_extension(port):
            log.warning("[ExtMgr] Uninstall failed — trying install anyway")
        time.sleep(2)
    
    # Step 2: Install
    return install_extension(port, extension_dir)


def install_if_needed(port: int, extension_dir: str, **kwargs) -> bool:
    """Install extension if missing, or reinstall if version outdated.
    
    Checks:
    1. Is extension loaded at all? → install
    2. Is installed version != local version? → reinstall
    
    Drop-in replacement for auto_install_extension.auto_install_extension_if_needed().
    Called from chrome_manager.launch_chrome() and ensure_chrome_running().
    
    Args:
        port: Chrome CDP port
        extension_dir: Absolute path to extension directory
    
    Returns:
        True if extension is (or becomes) loaded and up-to-date
    """
    if not is_extension_loaded(port):
        log.info("[ExtMgr] Extension not loaded — installing...")
        return install_extension(port, extension_dir)
    
    # Version check: compare installed vs local manifest
    local_ver = get_local_extension_version()
    if local_ver:
        installed_ver = _get_installed_extension_version(port)
        if installed_ver and installed_ver != local_ver:
            log.warning(f"[ExtMgr] ⚠️ Version mismatch: installed={installed_ver}, local={local_ver} — reinstalling...")
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

