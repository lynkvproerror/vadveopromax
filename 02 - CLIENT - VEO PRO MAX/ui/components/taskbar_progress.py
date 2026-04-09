"""
Windows Taskbar Progress Indicator — ITaskbarList3 COM interface.

Shows a progress bar overlay on the application's taskbar icon.
Uses ctypes to call the Windows Shell COM API directly because
PySide6 (Qt6) removed the QWinTaskbarButton class that was available in Qt5.

States:
  - NOPROGRESS:    No progress shown (idle)
  - INDETERMINATE: Pulsing green animation (working, unknown ETA)
  - NORMAL:        Green progress bar (0-100%)
  - ERROR:         Red progress bar (task failed)
  - PAUSED:        Yellow progress bar (paused)

VTable layout (verified against Windows SDK shobjidl_core.h):
  IUnknown:       0=QueryInterface, 1=AddRef, 2=Release
  ITaskbarList:   3=HrInit, 4=AddTab, 5=DeleteTab, 6=ActivateTab, 7=SetActiveAlt
  ITaskbarList2:  8=MarkFullscreenWindow
  ITaskbarList3:  9=SetProgressValue, 10=SetProgressState, ...

Usage:
    from ui.components.taskbar_progress import TaskbarProgress

    tb = TaskbarProgress(hwnd)
    tb.set_progress(35, 100)      # 35% green bar
    tb.set_state(tb.PAUSED)       # yellow bar
    tb.set_state(tb.NOPROGRESS)   # clear
"""

import ctypes
import ctypes.wintypes
import logging
import sys

log = logging.getLogger("veo.ui.taskbar")

# ───────────────────────────────────────────────────────────────
# Constants
# ───────────────────────────────────────────────────────────────

# Progress states (TBPFLAG enum from shobjidl_core.h)
TBPF_NOPROGRESS = 0x00
TBPF_INDETERMINATE = 0x01
TBPF_NORMAL = 0x02
TBPF_ERROR = 0x04
TBPF_PAUSED = 0x08

# COM GUIDs
CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_ITaskbarList3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"

# VTable indices (from Windows SDK shobjidl_core.h)
_VTBL_HRINIT = 3
_VTBL_SET_PROGRESS_VALUE = 9   # ITaskbarList3::SetProgressValue
_VTBL_SET_PROGRESS_STATE = 10  # ITaskbarList3::SetProgressState


# ───────────────────────────────────────────────────────────────
# COM GUID helper
# ───────────────────────────────────────────────────────────────

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_string(s: str) -> '_GUID':
    """Convert a GUID string like '{...}' to a _GUID struct."""
    guid = _GUID()
    hr = ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(guid))
    if hr != 0:
        raise OSError(f"CLSIDFromString failed for {s}: HRESULT {hr:#010x}")
    return guid


# ───────────────────────────────────────────────────────────────
# Raw ITaskbarList3 wrapper via ctypes vtable
# ───────────────────────────────────────────────────────────────

class _RawTaskbarList3:
    """Minimal ctypes wrapper around ITaskbarList3 COM vtable.
    
    Calls COM methods by reading function pointers directly from the
    vtable at the correct indices.
    """

    def __init__(self, com_ptr: ctypes.c_void_p):
        self._ptr = com_ptr
        
        # COM object layout: ptr -> vtable_ptr -> [fn0, fn1, fn2, ...]
        # Step 1: Read the vtable pointer (first pointer-sized value at *ptr)
        vtable_pp = ctypes.cast(com_ptr, ctypes.POINTER(ctypes.c_void_p))
        vtable_addr = vtable_pp[0]
        
        # Step 2: Cast vtable address to array of function pointers
        self._vtable = ctypes.cast(vtable_addr, ctypes.POINTER(ctypes.c_void_p))
        
        # Step 3: Call HrInit (index 3) — required before any other call
        _HrInit = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)
        hr = _HrInit(self._vtable[_VTBL_HRINIT])(self._ptr)
        if hr != 0:
            log.warning(f"[TaskbarProgress] HrInit failed: HRESULT {hr:#010x}")
        else:
            log.debug("[TaskbarProgress] HrInit OK")

    def SetProgressValue(self, hwnd, completed, total):
        """ITaskbarList3::SetProgressValue(hwnd, ullCompleted, ullTotal)."""
        _Fn = ctypes.WINFUNCTYPE(
            ctypes.HRESULT,       # return
            ctypes.c_void_p,      # this
            ctypes.wintypes.HWND, # hwnd
            ctypes.c_ulonglong,   # ullCompleted
            ctypes.c_ulonglong,   # ullTotal
        )
        fn = _Fn(self._vtable[_VTBL_SET_PROGRESS_VALUE])
        hr = fn(self._ptr, hwnd, completed, total)
        if hr != 0:
            log.debug(f"[TaskbarProgress] SetProgressValue({completed}/{total}) HRESULT={hr:#010x}")
        return hr

    def SetProgressState(self, hwnd, flags):
        """ITaskbarList3::SetProgressState(hwnd, tbpFlags)."""
        _Fn = ctypes.WINFUNCTYPE(
            ctypes.HRESULT,       # return
            ctypes.c_void_p,      # this
            ctypes.wintypes.HWND, # hwnd
            ctypes.c_int,         # tbpFlags
        )
        fn = _Fn(self._vtable[_VTBL_SET_PROGRESS_STATE])
        hr = fn(self._ptr, hwnd, flags)
        if hr != 0:
            log.debug(f"[TaskbarProgress] SetProgressState({flags:#04x}) HRESULT={hr:#010x}")
        return hr


def _create_taskbar_instance():
    """Create ITaskbarList3 COM instance via CoCreateInstance.
    
    Returns a _RawTaskbarList3 wrapper or None on failure.
    """
    if sys.platform != "win32":
        return None

    try:
        ole32 = ctypes.windll.ole32
        
        # CoInitialize (may already be initialized by Qt — that's OK, S_FALSE=1)
        hr_coinit = ole32.CoInitialize(None)
        log.debug(f"[TaskbarProgress] CoInitialize HRESULT={hr_coinit:#010x}")

        clsid = _guid_from_string(CLSID_TaskbarList)
        iid = _guid_from_string(IID_ITaskbarList3)

        CLSCTX_INPROC_SERVER = 0x1
        CLSCTX_LOCAL_SERVER = 0x4
        CLSCTX_ALL = CLSCTX_INPROC_SERVER | CLSCTX_LOCAL_SERVER

        p = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            CLSCTX_ALL,
            ctypes.byref(iid),
            ctypes.byref(p),
        )
        if hr != 0:
            log.warning(f"[TaskbarProgress] CoCreateInstance FAILED: HRESULT {hr:#010x}")
            return None

        log.info(f"[TaskbarProgress] CoCreateInstance OK, ptr={p.value:#x}")
        return _RawTaskbarList3(p)

    except Exception as e:
        log.warning(f"[TaskbarProgress] COM init exception: {e}", exc_info=True)
        return None


# ───────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────

class TaskbarProgress:
    """Windows taskbar progress controller.

    Wraps ITaskbarList3 COM interface to show a progress bar
    on the application's taskbar icon.

    Thread-safety: All methods should be called from the GUI thread.
    The MainWindow should instantiate this after show() so that
    the HWND is valid.
    """

    # Re-export states for convenience
    NOPROGRESS = TBPF_NOPROGRESS
    INDETERMINATE = TBPF_INDETERMINATE
    NORMAL = TBPF_NORMAL
    ERROR = TBPF_ERROR
    PAUSED = TBPF_PAUSED

    def __init__(self, hwnd: int = 0):
        self._hwnd = hwnd
        self._com = None
        self._state = TBPF_NOPROGRESS
        self._value = 0
        self._total = 0
        self._available = False

        if sys.platform != "win32":
            log.info("[TaskbarProgress] Not Windows — disabled")
            return

        try:
            self._com = _create_taskbar_instance()
            if self._com is not None:
                self._available = True
                log.info(f"[TaskbarProgress] Ready ✓ (hwnd={hwnd:#x})")
            else:
                log.warning("[TaskbarProgress] COM init returned None — disabled")
        except Exception as e:
            log.warning(f"[TaskbarProgress] Init failed: {e}", exc_info=True)

    @property
    def available(self) -> bool:
        return self._available

    def set_hwnd(self, hwnd: int):
        """Update window handle (call after window is shown)."""
        self._hwnd = hwnd
        log.debug(f"[TaskbarProgress] HWND updated to {hwnd:#x}")

    def set_progress(self, completed: int, total: int):
        """Set progress bar value (green normal bar).

        Args:
            completed: Number of completed items
            total: Total number of items
        """
        if not self._available or not self._hwnd:
            return

        # Auto-set NORMAL state when setting progress
        if self._state != TBPF_NORMAL:
            self.set_state(TBPF_NORMAL)

        self._value = completed
        self._total = total

        try:
            self._com.SetProgressValue(self._hwnd, completed, total)
        except Exception as e:
            log.debug(f"[TaskbarProgress] SetProgressValue error: {e}")

    def set_state(self, state: int):
        """Set progress bar state.

        Args:
            state: One of NOPROGRESS, INDETERMINATE, NORMAL, ERROR, PAUSED
        """
        if not self._available or not self._hwnd:
            return

        self._state = state
        try:
            self._com.SetProgressState(self._hwnd, state)
        except Exception as e:
            log.debug(f"[TaskbarProgress] SetProgressState error: {e}")

    def clear(self):
        """Remove progress bar from taskbar icon."""
        self.set_state(TBPF_NOPROGRESS)

    def set_error(self, completed: int = 0, total: int = 100):
        """Show red error progress on taskbar."""
        if not self._available or not self._hwnd:
            return
        self.set_state(TBPF_ERROR)
        try:
            self._com.SetProgressValue(self._hwnd, completed, total)
        except Exception:
            pass

    def set_paused(self, completed: int = 0, total: int = 100):
        """Show yellow paused progress on taskbar."""
        if not self._available or not self._hwnd:
            return
        self.set_state(TBPF_PAUSED)
        try:
            self._com.SetProgressValue(self._hwnd, completed, total)
        except Exception:
            pass

    def set_indeterminate(self):
        """Show pulsing indeterminate animation on taskbar."""
        self.set_state(TBPF_INDETERMINATE)
