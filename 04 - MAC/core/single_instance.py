"""
VEO Pro Max - Single Instance Lock (macOS)

Prevents multiple instances of the application from running simultaneously.
Uses fcntl file lock (primary) with PID lock file fallback.

Security: Prevents users from opening multiple windows to bypass
worker/account limits enforced by license tier.
"""

import sys
import os
import logging
import fcntl

log = logging.getLogger(__name__)

# Lock file location
_LOCK_DIR = os.path.join(os.path.expanduser("~"), ".veoauto")
_LOCK_FILE = os.path.join(_LOCK_DIR, ".instance.lock")
_FLOCK_FILE = os.path.join(_LOCK_DIR, ".instance.flock")


class SingleInstanceLock:
    """Ensures only one instance of VEO Pro Max can run at a time.
    
    Layer 1: fcntl file lock (POSIX)
      - OS-level, auto-released on process exit/crash
      - Works across all user sessions
    
    Layer 2: Lock file with PID (~/.veoauto/.instance.lock)
      - Fallback when fcntl unavailable
      - Stale lock detection via PID check
    """
    
    def __init__(self):
        self._lock_fd = None
        self._acquired = False
    
    def acquire(self) -> bool:
        """Try to acquire single-instance lock.
        
        Returns:
            True if this is the only instance (lock acquired).
            False if another instance is already running.
        """
        # Layer 1: fcntl file lock (POSIX)
        try:
            result = self._acquire_flock()
            if result is not None:
                return result
            # Fall through to Layer 2 if flock failed
        except Exception as e:
            log.debug(f"flock acquire failed, falling back to lock file: {e}")
        
        # Layer 2: Lock file with PID
        return self._acquire_lockfile()
    
    def release(self):
        """Release the single-instance lock."""
        # Release flock
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except Exception:
                pass
            self._lock_fd = None
        
        # Remove lock file
        try:
            if os.path.exists(_LOCK_FILE):
                os.remove(_LOCK_FILE)
        except Exception:
            pass
        
        # Remove flock file
        try:
            if os.path.exists(_FLOCK_FILE):
                os.remove(_FLOCK_FILE)
        except Exception:
            pass
        
        self._acquired = False
    
    def _acquire_flock(self):
        """Try POSIX file lock via fcntl. Returns True/False or None if unavailable."""
        os.makedirs(_LOCK_DIR, exist_ok=True)
        
        try:
            fd = os.open(_FLOCK_FILE, os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # We own the lock
            self._lock_fd = fd
            self._acquired = True
            
            # Write PID for reference
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, str(os.getpid()).encode())
            
            log.info("[SingleInstance] flock acquired — this is the only instance")
            return True
        except (IOError, OSError):
            # Another instance holds the lock
            log.info("[SingleInstance] flock already held — another instance is running")
            try:
                os.close(fd)
            except Exception:
                pass
            return False
    
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
        # Unix: use os.kill(pid, 0)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def show_already_running_dialog():
    """Show a message indicating app is already running.
    
    On macOS, uses osascript for native dialog. Falls back to console.
    This is called BEFORE QApplication is created.
    """
    title = "VEO Pro Max"
    message = (
        "⚠️ VEO Pro Max đã đang chạy!\n\n"
        "Chỉ được phép mở 1 cửa sổ ứng dụng.\n"
        "Vui lòng sử dụng cửa sổ đang mở."
    )
    
    try:
        import subprocess
        # macOS native dialog via osascript
        script = f'display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK" with icon caution'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=10
        )
        return
    except Exception:
        pass
    
    # Fallback: print to console
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"  {message}")
    print(f"{'='*50}\n")
