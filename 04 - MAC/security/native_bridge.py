"""
Native Security Bridge v1.0
============================

Python bridge to veo_security.pyd (Rust native module).
Falls back to Python implementations if .pyd not available.

Usage:
    from security.native_bridge import NativeSecurity

    ns = NativeSecurity()
    if ns.available:
        result = ns.full_security_check()
"""

import sys
import logging
from pathlib import Path
from typing import Tuple, List, Dict, Optional

log = logging.getLogger(__name__)

# Try to import native module
_NATIVE_AVAILABLE = False
try:
    import veo_security as _native
    _NATIVE_AVAILABLE = True
    log.info(f"[NativeSecurity] ✅ Rust module loaded (v{_native._internal_version()})")
except ImportError:
    _native = None
    log.debug("[NativeSecurity] Rust module not available — using Python fallbacks")


class NativeSecurity:
    """Bridge to Rust native security module with Python fallbacks."""

    @property
    def available(self) -> bool:
        """Whether the Rust native module is loaded."""
        return _NATIVE_AVAILABLE

    @property
    def version(self) -> str:
        """Native module version."""
        if _NATIVE_AVAILABLE:
            return _native._internal_version()
        return "python-fallback"

    # ── Anti-Debug ────────────────────────────────────────────

    def is_debugger_attached(self) -> bool:
        if _NATIVE_AVAILABLE:
            return _native.is_debugger_attached()
        # Python fallback: macOS sysctl check for P_TRACED flag
        try:
            import ctypes
            import ctypes.util
            
            libc = ctypes.CDLL(ctypes.util.find_library("c"))
            
            # sysctl CTL_KERN.KERN_PROC.KERN_PROC_PID
            import os
            import struct
            
            CTL_KERN = 1
            KERN_PROC = 14
            KERN_PROC_PID = 1
            
            mib = (ctypes.c_int * 4)(CTL_KERN, KERN_PROC, KERN_PROC_PID, os.getpid())
            buf_size = ctypes.c_size_t(0)
            
            # Get buffer size
            libc.sysctl(mib, 4, None, ctypes.byref(buf_size), None, 0)
            buf = ctypes.create_string_buffer(buf_size.value)
            libc.sysctl(mib, 4, buf, ctypes.byref(buf_size), None, 0)
            
            # P_TRACED flag offset in kinfo_proc.kp_proc.p_flag:
            #   x86_64 (Intel Mac): offset 32
            #   arm64  (M-chip)   : offset 24
            import platform
            _p_flag_offset = 24 if platform.machine() == "arm64" else 32
            if buf_size.value <= _p_flag_offset + 4:
                return False  # Buffer too small — safe fallback
            p_flag = struct.unpack_from("i", buf.raw, _p_flag_offset)[0]
            return bool(p_flag & 0x00000800)
        except Exception:
            return False

    def timing_check(self) -> bool:
        if _NATIVE_AVAILABLE:
            return _native.timing_check()
        # Python fallback: less accurate but functional
        import time
        start = time.perf_counter()
        x = 0
        for i in range(10000):
            x = (x + i) * 31 & 0xFFFFFFFF
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms > 50

    def full_anti_debug_check(self) -> Tuple[bool, List[str]]:
        if _NATIVE_AVAILABLE:
            return _native.full_anti_debug_check()
        # Python fallback
        flags = []
        if self.is_debugger_attached():
            flags.append("debugger_attached")
        if self.timing_check():
            flags.append("timing_anomaly")
        return (len(flags) > 0, flags)

    # ── Integrity Check ───────────────────────────────────────

    def hash_file(self, path: str) -> str:
        if _NATIVE_AVAILABLE:
            return _native.hash_file(path)
        # Python fallback
        import hashlib
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

    def verify_file_hash(self, path: str, expected: str) -> bool:
        if _NATIVE_AVAILABLE:
            return _native.verify_file_hash(path, expected)
        return self.hash_file(path) == expected

    # ── HWID ──────────────────────────────────────────────────

    def get_native_cpuid(self) -> str:
        if _NATIVE_AVAILABLE:
            return _native.get_native_cpuid()
        return "python_fallback"

    def native_machine_id(self) -> str:
        if _NATIVE_AVAILABLE:
            return _native.native_machine_id()
        # Python fallback: use existing HardwareFingerprint
        try:
            from security.license_client import HardwareFingerprint
            return HardwareFingerprint.get_machine_id()  # Fixed: generate() doesn't exist
        except Exception:
            return "fallback_no_hwid"

    # ── Frida Detection ───────────────────────────────────────

    def detect_frida(self) -> Tuple[bool, List[str]]:
        if _NATIVE_AVAILABLE:
            return _native.detect_frida()
        # Python fallback: port check only
        flags = []
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)
            if s.connect_ex(('127.0.0.1', 27042)) == 0:
                flags.append("frida_port_27042")
            s.close()
        except Exception:
            pass
        return (len(flags) > 0, flags)

    # ── DLL Injection Detection ───────────────────────────────

    def detect_injected_dlls(self) -> Tuple[bool, List[str]]:
        if _NATIVE_AVAILABLE:
            return _native.detect_injected_dlls()
        # Python fallback: limited check via psutil
        flags = []
        try:
            import psutil
            proc = psutil.Process()
            blacklist = ["cheatengine", "x64dbg", "ollydbg"]
            for dll in proc.memory_maps():
                dll_lower = dll.path.lower()
                for bl in blacklist:
                    if bl in dll_lower:
                        flags.append(f"injected_dll_{dll_lower}")
        except Exception:
            pass
        return (len(flags) > 0, flags)

    # ── Combined Check ────────────────────────────────────────

    def full_security_check(self) -> dict:
        """Run all native security checks."""
        result = {
            'passed': True,
            'native': _NATIVE_AVAILABLE,
            'version': self.version,
            'checks': {},
        }

        if _NATIVE_AVAILABLE:
            try:
                all_passed, details = _native.full_security_check()
                result['passed'] = all_passed
                for name, passed, flags in details:
                    result['checks'][name] = {
                        'passed': passed,
                        'flags': flags,
                    }
                return result
            except Exception as e:
                log.error(f"[NativeSecurity] Full check error: {e}")

        # Python fallback — run each check individually
        checks = [
            ("anti_debug", self.full_anti_debug_check),
            ("frida_detection", self.detect_frida),
            ("dll_injection", self.detect_injected_dlls),
        ]

        for name, check_fn in checks:
            try:
                detected, flags = check_fn()
                if detected:
                    result['passed'] = False
                result['checks'][name] = {
                    'passed': not detected,
                    'flags': flags,
                }
            except Exception as e:
                result['checks'][name] = {
                    'passed': True,
                    'flags': [],
                    'error': str(e),
                }

        return result


# Singleton
_instance = None

def get_native_security() -> NativeSecurity:
    global _instance
    if _instance is None:
        _instance = NativeSecurity()
    return _instance
