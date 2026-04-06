"""
VEO Pro Max - Single Instance Lock

Prevents multiple instances of the application from running simultaneously.
Uses Windows Named Mutex (primary) with lock file fallback.

Security: Prevents users from opening multiple windows to bypass
worker/account limits enforced by license tier.

Extended:
- kill_zombie_veo_instances(): Kill background VEO processes with no visible window
  (zombie = previous run that crashed / didn't shut down port cleanly)
- restore_existing_veo_window(): Bring real running VEO window to foreground
"""

import sys
import os
import logging

log = logging.getLogger(__name__)

# Lock file location
_LOCK_DIR = os.path.join(os.path.expanduser("~"), ".veoauto")
_LOCK_FILE = os.path.join(_LOCK_DIR, ".instance.lock")

# Windows Mutex name (Global = cross-session)
_MUTEX_NAME = "Global\\VEOProMaxSingleInstance"

# Window title prefix used to identify real VEO windows
_WINDOW_TITLE_PREFIX = "VEO PRO MAX"

# Known compiled exe names (case-insensitive match)
_EXE_NAMES = {"veo_pro_max.exe", "veo pro max.exe", "veopromax.exe"}


# ── Win32 Helpers ────────────────────────────────────────────────

def _find_hwnd_by_title_prefix(prefix: str) -> list:
    """Enumerate all top-level windows whose title starts with `prefix`.

    Returns list of (hwnd, pid) tuples for matching windows.
    """
    results = []
    if sys.platform != "win32":
        return results
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32

        EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        matches = []

        def _cb(hwnd, _lparam):
            try:
                length = user32.GetWindowTextLengthW(hwnd) + 1
                buf = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hwnd, buf, length)
                title = buf.value
                if title.upper().startswith(prefix.upper()):
                    pid = wt.DWORD(0)
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    matches.append((hwnd, pid.value))
            except Exception:
                pass
            return True  # Continue enumeration

        proc = EnumWindowsProc(_cb)
        user32.EnumWindows(proc, 0)
        return matches
    except Exception as e:
        log.debug(f"[SingleInstance] _find_hwnd_by_title_prefix error: {e}")
        return []


def _find_veo_pids_by_exe() -> list:
    """Find all PIDs running a VEO Pro Max executable (excluding current PID).

    Uses Win32 CreateToolhelp32Snapshot — works in compiled (Nuitka) builds.
    Returns list of int PIDs.
    """
    if sys.platform != "win32":
        return []
    current_pid = os.getpid()
    results = []
    try:
        import ctypes
        import ctypes.wintypes as wt
        kernel32 = ctypes.windll.kernel32
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize",             wt.DWORD),
                ("cntUsage",           wt.DWORD),
                ("th32ProcessID",      wt.DWORD),
                ("th32DefaultHeapID",  ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID",       wt.DWORD),
                ("cntThreads",         wt.DWORD),
                ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase",     ctypes.c_long),
                ("dwFlags",            wt.DWORD),
                ("szExeFile",          ctypes.c_wchar * 260),
            ]

        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        INVALID = ctypes.c_void_p(-1).value
        if snap == INVALID:
            return results

        try:
            pe = PROCESSENTRY32W()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
                while True:
                    exe_lower = pe.szExeFile.lower()
                    is_veo = any(exe_lower == name for name in _EXE_NAMES)
                    if is_veo and pe.th32ProcessID != current_pid:
                        results.append(pe.th32ProcessID)
                    if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                        break
        finally:
            kernel32.CloseHandle(snap)
    except Exception as e:
        log.debug(f"[SingleInstance] _find_veo_pids_by_exe error: {e}")
    return results


def kill_zombie_veo_instances() -> int:
    """Kill VEO Pro Max background processes that have NO visible window.

    'Zombie' = a previous run that crashed or didn't fully shut down.
    These processes lock the WebSocket port and Named Mutex, blocking
    a fresh startup from getting correct extension/browser connections.

    Strategy:
      1. Enumerate all VEO Pro Max windows by title → {PIDs with real windows}
      2. Enumerate all VEO Pro Max exe processes → all VEO PIDs
      3. PIDs in step 2 but NOT in step 1 = zombies → TerminateProcess

    Returns: number of zombie processes killed.
    """
    if sys.platform != "win32":
        return 0

    current_pid = os.getpid()

    # Step 1: PIDs that have a visible VEO window
    window_pids = {pid for (_hwnd, pid) in _find_hwnd_by_title_prefix(_WINDOW_TITLE_PREFIX)}

    # Step 2: All VEO Pro Max exe PIDs (compiled mode)
    veo_pids = _find_veo_pids_by_exe()

    # Step 2b: Also check lock file PID as fallback (dev mode / python.exe)
    try:
        if os.path.exists(_LOCK_FILE):
            with open(_LOCK_FILE, "r") as f:
                file_pid = int(f.read().strip())
            if file_pid != current_pid and file_pid not in window_pids:
                if file_pid not in veo_pids:
                    veo_pids.append(file_pid)
    except Exception:
        pass

    killed = 0
    try:
        import ctypes
        import ctypes.wintypes as wt
        kernel32 = ctypes.windll.kernel32
        PROCESS_TERMINATE = 0x0001
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        for pid in veo_pids:
            if pid == current_pid:
                continue  # Never kill ourselves
            if pid in window_pids:
                continue  # Has visible window — leave it alone

            # Zombie: VEO process but no visible window → kill
            log.info(f"[SingleInstance] 🧟 Killing zombie VEO Pro Max PID={pid} (no window)")
            handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                try:
                    success = kernel32.TerminateProcess(handle, 0)
                    if success:
                        killed += 1
                        log.info(f"[SingleInstance] ✅ Killed zombie PID={pid}")
                    else:
                        log.warning(f"[SingleInstance] ⚠️ Failed to terminate PID={pid}")
                finally:
                    kernel32.CloseHandle(handle)
            else:
                log.debug(f"[SingleInstance] Could not open PID={pid} (already dead?)")

    except Exception as e:
        log.warning(f"[SingleInstance] kill_zombie_veo_instances error: {e}")

    if killed:
        log.info(f"[SingleInstance] Killed {killed} zombie VEO instance(s)")
    return killed


def restore_existing_veo_window() -> bool:
    """Bring the existing VEO Pro Max window to the foreground.

    Called when mutex conflict is detected and a real instance is running.
    Uses Win32 ShowWindow + SetForegroundWindow.

    Returns True if a window was found and brought to front.
    """
    if sys.platform != "win32":
        return False

    windows = _find_hwnd_by_title_prefix(_WINDOW_TITLE_PREFIX)
    if not windows:
        log.info("[SingleInstance] restore_existing_veo_window: no window found")
        return False

    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32

        hwnd, pid = windows[0]
        SW_RESTORE = 9
        SW_SHOW    = 5

        # Restore if minimized, then bring to front
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.SetActiveWindow(hwnd)

        log.info(f"[SingleInstance] ✅ Restored existing VEO window HWND={hwnd} PID={pid}")
        return True
    except Exception as e:
        log.warning(f"[SingleInstance] restore_existing_veo_window error: {e}")
        return False


# ════════════════════════════════════════════════════════════════
#  SingleInstanceLock
# ════════════════════════════════════════════════════════════════

class SingleInstanceLock:
    """Ensures only one instance of VEO Pro Max can run at a time.
    
    Layer 1: Windows Named Mutex (CreateMutexW)
      - OS-level, auto-released on process exit/crash
      - Works across all user sessions
    
    Layer 2: Lock file with PID (~/.veoauto/.instance.lock)
      - Fallback when ctypes/Win32 unavailable
      - Stale lock detection via PID check
    
    NOTE: The global instance is stored in _global_lock for cleanup
    from any code path (especially os._exit which skips finally blocks).
    """
    
    # Module-level reference for cleanup from anywhere
    _global_lock = None
    
    def __init__(self):
        self._mutex_handle = None
        self._acquired = False
    
    def acquire(self) -> bool:
        """Try to acquire single-instance lock.
        
        Returns:
            True if this is the only instance (lock acquired).
            False if another instance is already running.
        """
        # Layer 1: Windows Named Mutex
        if sys.platform == "win32":
            try:
                result = self._acquire_mutex()
                if result is not None:
                    if result:
                        SingleInstanceLock._global_lock = self
                    return result
                # Fall through to Layer 2 if mutex failed
            except Exception as e:
                log.debug(f"Mutex acquire failed, falling back to lock file: {e}")
        
        # Layer 2: Lock file with PID
        result = self._acquire_lockfile()
        if result:
            SingleInstanceLock._global_lock = self
        return result
    
    def release(self):
        """Release the single-instance lock."""
        # Release mutex
        if self._mutex_handle:
            try:
                import ctypes
                import ctypes.wintypes as wt
                kernel32 = ctypes.windll.kernel32
                kernel32.ReleaseMutex.restype = wt.BOOL
                kernel32.ReleaseMutex.argtypes = [wt.HANDLE]
                kernel32.CloseHandle.restype = wt.BOOL
                kernel32.CloseHandle.argtypes = [wt.HANDLE]
                kernel32.ReleaseMutex(self._mutex_handle)
                kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None
        
        # Remove lock file
        try:
            if os.path.exists(_LOCK_FILE):
                os.remove(_LOCK_FILE)
        except Exception:
            pass
        
        self._acquired = False
    
    def _acquire_mutex(self):
        """Try Windows Named Mutex. Returns True/False or None if unavailable."""
        import ctypes
        import ctypes.wintypes as wt
        
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        
        # Declare proper types for 64-bit Windows compatibility
        kernel32.CreateMutexW.restype = wt.HANDLE
        kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
        kernel32.GetLastError.restype = wt.DWORD
        kernel32.CloseHandle.restype = wt.BOOL
        kernel32.CloseHandle.argtypes = [wt.HANDLE]
        kernel32.ReleaseMutex.restype = wt.BOOL
        kernel32.ReleaseMutex.argtypes = [wt.HANDLE]
        
        # CreateMutexW(lpMutexAttributes, bInitialOwner, lpName)
        handle = kernel32.CreateMutexW(None, True, _MUTEX_NAME)
        
        if not handle:
            return None  # Failed to create, fall back
        
        last_error = kernel32.GetLastError()
        
        if last_error == ERROR_ALREADY_EXISTS:
            # Another instance already holds this mutex
            kernel32.CloseHandle(handle)
            log.info("[SingleInstance] Mutex already exists — another instance is running")
            return False
        
        # We own the mutex
        self._mutex_handle = handle
        self._acquired = True
        log.info("[SingleInstance] Mutex acquired — this is the only instance")
        return True
    
    def _acquire_lockfile(self) -> bool:
        """Lock file with PID check (fallback)."""
        os.makedirs(_LOCK_DIR, exist_ok=True)
        
        # Check existing lock file
        if os.path.exists(_LOCK_FILE):
            try:
                with open(_LOCK_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                
                # Check if that PID is still alive
                if self._is_pid_alive(old_pid):
                    log.info(f"[SingleInstance] Lock file exists, PID {old_pid} is alive")
                    return False
                else:
                    # Stale lock — process crashed
                    log.info(f"[SingleInstance] Stale lock file (PID {old_pid} dead), removing")
                    os.remove(_LOCK_FILE)
            except (ValueError, OSError):
                # Corrupted lock file, remove it
                try:
                    os.remove(_LOCK_FILE)
                except OSError:
                    pass
        
        # Write our PID
        try:
            with open(_LOCK_FILE, "w") as f:
                f.write(str(os.getpid()))
            self._acquired = True
            log.info(f"[SingleInstance] Lock file created (PID {os.getpid()})")
            return True
        except OSError as e:
            log.warning(f"[SingleInstance] Failed to create lock file: {e}")
            return True  # Allow running if can't create lock
    
    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a process with given PID is still running."""
        if sys.platform == "win32":
            try:
                import ctypes
                import ctypes.wintypes as wt
                kernel32 = ctypes.windll.kernel32
                kernel32.OpenProcess.restype = wt.HANDLE
                kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
                kernel32.CloseHandle.restype = wt.BOOL
                kernel32.CloseHandle.argtypes = [wt.HANDLE]
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION, False, pid
                )
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                pass
        
        # Unix fallback
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def show_already_running_dialog():
    """Show a native message box indicating app is already running.
    
    Uses Win32 MessageBoxW directly — does NOT require QApplication.
    This is called BEFORE QApplication is created.
    """
    title = "VEO Pro Max"
    message = (
        "⚠️ VEO Pro Max đã đang chạy!\n\n"
        "Chỉ được phép mở 1 cửa sổ ứng dụng.\n"
        "Vui lòng sử dụng cửa sổ đang mở."
    )
    
    if sys.platform == "win32":
        try:
            import ctypes
            MB_OK = 0x0
            MB_ICONWARNING = 0x30
            MB_TOPMOST = 0x40000
            ctypes.windll.user32.MessageBoxW(
                None, message, title,
                MB_OK | MB_ICONWARNING | MB_TOPMOST
            )
            return
        except Exception:
            pass
    
    # Fallback: print to console
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"  {message}")
    print(f"{'='*50}\n")


def release_global():
    """Release the global SingleInstance lock.
    
    Call this before os._exit() to ensure the mutex is freed.
    Safe to call multiple times or when no lock is held.
    """
    lock = SingleInstanceLock._global_lock
    if lock:
        try:
            lock.release()
        except Exception:
            pass
        SingleInstanceLock._global_lock = None


# Register atexit handler as safety net (works for normal exit, not os._exit)
import atexit
atexit.register(release_global)
