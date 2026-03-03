"""
VEO Pro Max - Single Instance Lock

Prevents multiple instances of the application from running simultaneously.
Uses Windows Named Mutex (primary) with lock file fallback.

Security: Prevents users from opening multiple windows to bypass
worker/account limits enforced by license tier.
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


class SingleInstanceLock:
    """Ensures only one instance of VEO Pro Max can run at a time.
    
    Layer 1: Windows Named Mutex (CreateMutexW)
      - OS-level, auto-released on process exit/crash
      - Works across all user sessions
    
    Layer 2: Lock file with PID (~/.veoauto/.instance.lock)
      - Fallback when ctypes/Win32 unavailable
      - Stale lock detection via PID check
    """
    
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
                    return result
                # Fall through to Layer 2 if mutex failed
            except Exception as e:
                log.debug(f"Mutex acquire failed, falling back to lock file: {e}")
        
        # Layer 2: Lock file with PID
        return self._acquire_lockfile()
    
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
