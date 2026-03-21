"""
Anti-Tamper Runtime Guards v1.0
================================

Multi-layer runtime protection against cracking, hooking, and debugging.
All guards are Python-based (Phase 2). Rust-native versions (Phase 3) will replace them.

Protection layers:
1. AntiMonkeyPatch — detect function replacement at runtime
2. AntiExtraction — detect if running from extracted PyInstaller bundle
3. ProcessVerifier — verify parent process is legitimate
4. ProxyDetector — detect MITM proxy (Fiddler, Burp, mitmproxy)
5. VMSnapshotDetector — detect VM snapshot restore (time consistency)
6. SandboxDetector — detect Sandboxie/Windows Sandbox

Usage:
    from security.anti_tamper import run_all_guards

    # At startup (after critical modules imported):
    result = run_all_guards()
    if not result['passed']:
        log.critical(f"Security guard FAILED: {result['failures']}")
"""

import sys
import os
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# ============================================================
# GUARD 1: Anti Monkey Patch
# ============================================================

class AntiMonkeyPatch:
    """
    Detect runtime function/module replacement.

    Stores id() of critical objects at registration time.
    Periodic verify() checks if any id has changed (= object replaced).
    """

    _originals: Dict[str, int] = {}

    @classmethod
    def register(cls, module_name: str, attr_names: list):
        """Register module attributes to protect."""
        module = sys.modules.get(module_name)
        if not module:
            return
        for name in attr_names:
            obj = getattr(module, name, None)
            if obj is not None:
                key = f"{module_name}.{name}"
                cls._originals[key] = id(obj)

    @classmethod
    def verify(cls) -> List[str]:
        """Check if any protected attribute was replaced. Returns list of tampered keys."""
        tampered = []
        for key, original_id in cls._originals.items():
            module_name, attr_name = key.rsplit('.', 1)
            module = sys.modules.get(module_name)
            if not module:
                tampered.append(key)
                continue
            current = getattr(module, attr_name, None)
            if current is None or id(current) != original_id:
                tampered.append(key)
        return tampered


# ============================================================
# GUARD 2: Anti Extraction
# ============================================================

class AntiExtraction:
    """Detect if running from extracted PyInstaller/Nuitka bundle."""

    @staticmethod
    def check() -> dict:
        """
        Returns:
            {'safe': bool, 'flags': list[str]}
        """
        flags = []

        # Check 1: Running under python interpreter (not compiled binary)
        exe_name = os.path.basename(sys.executable).lower()
        if exe_name in ("python", "python3", "pythonw",
                         "python.exe", "python3.exe", "pythonw.exe"):
            # In dev mode this is normal — only flag in production
            if getattr(sys, 'frozen', False):
                flags.append("python_runtime_in_frozen")

        # Check 2: Running from temp directory (PyInstaller extraction)
        exe_path = sys.executable
        temp_indicators = ["/var/folders/", "/private/tmp/", "/tmp/", "\\Temp\\", "\\tmp\\"]
        if any(ind in exe_path for ind in temp_indicators):
            if getattr(sys, 'frozen', False):
                flags.append("temp_directory")

        # Check 3: _MEIPASS exists but bundle integrity unknown
        if hasattr(sys, '_MEIPASS'):
            bundle_dir = sys._MEIPASS
            # Check if there are .pyc files exposed (shouldn't be in Nuitka build)
            pyc_count = sum(1 for _ in Path(bundle_dir).rglob("*.pyc"))
            if pyc_count > 50:
                flags.append(f"exposed_pyc_files_{pyc_count}")

        return {
            'safe': len(flags) == 0,
            'flags': flags,
        }


# ============================================================
# GUARD 3: Process Verifier
# ============================================================

class ProcessVerifier:
    """Verify parent process is a legitimate launcher."""

    # Trusted parent processes on macOS
    TRUSTED_PARENTS = {
        "launchd", "bash", "zsh", "sh", "fish",
        "terminal", "iterm2", "alacritty", "warp",
        "code", "cursor",  # IDEs (dev mode)
        "windsurf", "trae",
        "python", "python3", "pythonw",  # Dev mode
        "open",  # macOS open command
    }

    @staticmethod
    def check() -> dict:
        """
        Returns:
            {'safe': bool, 'parent': str, 'flags': list[str]}
        """
        flags = []
        parent_name = "unknown"

        try:
            ppid = os.getppid()

            # macOS: use ps to get parent process name
            import subprocess
            result = subprocess.run(
                ['ps', '-p', str(ppid), '-o', 'comm='],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # ps returns full path, extract basename
                parent_name = os.path.basename(result.stdout.strip()).lower()

            # In production (frozen), parent should be trusted
            if getattr(sys, 'frozen', False):
                if parent_name not in ProcessVerifier.TRUSTED_PARENTS:
                    flags.append(f"untrusted_parent_{parent_name}")

        except Exception as e:
            log.debug(f"[ProcessVerifier] Check failed (non-fatal): {e}")

        return {
            'safe': len(flags) == 0,
            'parent': parent_name,
            'flags': flags,
        }


# ============================================================
# GUARD 4: Proxy Detector (Anti-MITM)
# ============================================================

class ProxyDetector:
    """Detect system proxy that could intercept HTTPS traffic."""

    @staticmethod
    def check() -> dict:
        """
        Returns:
            {'safe': bool, 'proxy': str, 'flags': list[str]}
        """
        flags = []
        proxy_info = "none"

        # Check 1: macOS networksetup proxy settings
        try:
            import subprocess
            result = subprocess.run(
                ['networksetup', '-getwebproxy', 'Wi-Fi'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                output = result.stdout
                if 'Enabled: Yes' in output:
                    # Extract server and port
                    server = port = ''
                    for line in output.split('\n'):
                        if line.startswith('Server:'):
                            server = line.split(':',1)[-1].strip()
                        elif line.startswith('Port:'):
                            port = line.split(':',1)[-1].strip()
                    proxy_info = f"{server}:{port}"
                    # Common MITM proxy ports
                    mitm_ports = ["8080", "8888", "8443", "9090", "8082"]
                    if any(port == p for p in mitm_ports):
                        flags.append(f"mitm_proxy_{proxy_info}")
        except Exception:
            pass

        # Check 2: Environment variables
        for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
            val = os.environ.get(var, '')
            if val:
                flags.append(f"env_proxy_{var}={val}")
                proxy_info = val

        return {
            'safe': len(flags) == 0,
            'proxy': proxy_info,
            'flags': flags,
        }


# ============================================================
# GUARD 5: VM Snapshot Detector
# ============================================================

class VMSnapshotDetector:
    """Detect VM snapshot restore via time consistency checks."""

    _last_mono: Optional[float] = None
    _last_wall: Optional[float] = None

    @classmethod
    def check(cls) -> dict:
        """
        Returns:
            {'safe': bool, 'flags': list[str]}
        """
        flags = []
        mono_now = time.monotonic()
        wall_now = time.time()

        if cls._last_mono is not None and cls._last_wall is not None:
            # Expected wall clock based on monotonic elapsed
            expected_wall = cls._last_wall + (mono_now - cls._last_mono)
            drift = abs(wall_now - expected_wall)

            if drift > 300:  # >5 min drift = VM snapshot restore likely
                flags.append(f"time_drift_{drift:.0f}s")

            # Monotonic went backwards = process restart/snapshot
            if mono_now < cls._last_mono:
                flags.append("monotonic_backwards")

        # Update baseline
        cls._last_mono = mono_now
        cls._last_wall = wall_now

        return {
            'safe': len(flags) == 0,
            'flags': flags,
        }


# ============================================================
# GUARD 6: Sandbox Detector
# ============================================================

class SandboxDetector:
    """Detect sandbox environments on macOS."""

    @staticmethod
    def check() -> dict:
        """
        Returns:
            {'safe': bool, 'flags': list[str]}
        """
        flags = []

        # Check 1: macOS App Sandbox detection
        try:
            # Check if running inside macOS sandbox
            home = str(Path.home())
            if '/Library/Containers/' in home:
                flags.append("macos_app_sandbox")
        except Exception:
            pass

        # Check 2: Known sandbox environment variables
        sandbox_vars = {
            "SANDBOX_INITED": "sandboxie_env",
            "APP_SANDBOX_CONTAINER_ID": "macos_sandbox",
        }
        for var, label in sandbox_vars.items():
            if os.environ.get(var):
                flags.append(label)

        return {
            'safe': len(flags) == 0,
            'flags': flags,
        }


# ============================================================
# GUARD 7: Debugger / Reverse Engineering Detector
# ============================================================

class DebuggerDetector:
    """Detect debuggers and reverse engineering tools."""

    # Known RE tool process names (lowercase) — macOS versions
    RE_TOOLS = {
        "lldb", "gdb",
        "ida", "ida64", "idaq", "idaq64",
        "ghidra", "ghidrarun",
        "hopper",  # Hopper disassembler (macOS)
        "wireshark",
        "charles",  # Charles Proxy
        "proxyman",  # Proxyman (macOS)
        "mitmproxy", "mitmdump", "mitmweb",
        "frida", "frida-server",
        "radare2", "r2",
        "dtrace",
    }

    @staticmethod
    def check() -> dict:
        """
        Returns:
            {'safe': bool, 'flags': list[str]}
        """
        flags = []

        # Check 1: macOS sysctl P_TRACED flag (detects lldb, gdb, dtrace)
        try:
            import ctypes
            import ctypes.util
            import struct
            
            libc = ctypes.CDLL(ctypes.util.find_library("c"))
            CTL_KERN = 1
            KERN_PROC = 14
            KERN_PROC_PID = 1
            
            mib = (ctypes.c_int * 4)(CTL_KERN, KERN_PROC, KERN_PROC_PID, os.getpid())
            buf_size = ctypes.c_size_t(0)
            libc.sysctl(mib, 4, None, ctypes.byref(buf_size), None, 0)
            buf = ctypes.create_string_buffer(buf_size.value)
            libc.sysctl(mib, 4, buf, ctypes.byref(buf_size), None, 0)
            
            p_flag = struct.unpack_from("i", buf.raw, 32)[0]
            if p_flag & 0x00000800:  # P_TRACED
                flags.append("debugger_attached")
        except Exception:
            pass

        # Check 2: Scan for RE tool processes (only in production)
        if getattr(sys, 'frozen', False):
            try:
                import subprocess
                result = subprocess.run(
                    ['ps', 'aux'],
                    capture_output=True, text=True, timeout=5,
                )
                running = {
                    os.path.basename(l.split()[10]).lower()
                    for l in result.stdout.split('\n')
                    if l.strip() and len(l.split()) > 10
                }
                detected = running & DebuggerDetector.RE_TOOLS
                if detected:
                    flags.extend(f"re_tool_{p}" for p in detected)
            except Exception:
                pass

        return {
            'safe': len(flags) == 0,
            'flags': flags,
        }


# ============================================================
# ORCHESTRATOR
# ============================================================

def register_critical_modules():
    """Register critical security modules for monkey-patch detection.

    Call AFTER all security imports are complete (in app startup).
    """
    AntiMonkeyPatch.register('security.license_client', [
        'LicenseClient', 'HardwareFingerprint', 'LicenseStorage',
        'UserRole', 'LicenseInfo',
    ])
    AntiMonkeyPatch.register('security.firebase_rest_client', [
        'FirebaseRESTClient', 'SecureFirebaseConfig',
        '_AES256Encryptor', '_HardwareBinder',
    ])
    AntiMonkeyPatch.register('security.trial_protection', [
        'TrialMarkerManager', 'TimeVerifier',
    ])
    AntiMonkeyPatch.register('security.integrity_check', [
        'verify_startup_integrity',
    ])
    log.debug(f"[AntiMonkeyPatch] Registered {len(AntiMonkeyPatch._originals)} protected attributes")


def run_all_guards(production_mode: bool = False) -> dict:
    """
    Run all security guards.

    Args:
        production_mode: If True, treat all failures as critical.
                         If False (dev mode), only log warnings.

    Returns:
        {
            'passed': bool,
            'total_guards': int,
            'failures': list[str],
            'details': dict,
        }
    """
    result = {
        'passed': True,
        'total_guards': 0,
        'failures': [],
        'details': {},
    }

    # Determine if we're in production (frozen/compiled)
    is_frozen = getattr(sys, 'frozen', False)
    effective_production = production_mode or is_frozen

    # severity: 'critical' → hard-block, 'warning' → log only
    guards = [
        ("anti_monkey_patch", "critical", lambda: {
            'safe': len(AntiMonkeyPatch.verify()) == 0,
            'flags': AntiMonkeyPatch.verify(),
        }),
        ("anti_extraction", "critical", AntiExtraction.check),
        ("debugger_detector", "critical", DebuggerDetector.check),
        ("process_verifier", "warning", ProcessVerifier.check),
        ("proxy_detector", "warning", ProxyDetector.check),
        ("vm_snapshot", "warning", VMSnapshotDetector.check),
        ("sandbox_detector", "warning", SandboxDetector.check),
    ]

    for name, severity, check_fn in guards:
        result['total_guards'] += 1
        try:
            guard_result = check_fn()
            guard_result['severity'] = severity
            result['details'][name] = guard_result

            if not guard_result.get('safe', True):
                flags = guard_result.get('flags', [])
                if effective_production:
                    if severity == 'critical':
                        result['passed'] = False
                        result['failures'].extend([f"{name}:{f}" for f in flags])
                        log.warning(f"[AntiTamper] 🔴 {name} CRITICAL: {flags}")
                    else:
                        result['warnings'] = result.get('warnings', [])
                        result['warnings'].extend([f"{name}:{f}" for f in flags])
                        log.warning(f"[AntiTamper] ⚠️ {name} WARNING: {flags}")
                else:
                    log.debug(f"[AntiTamper] {name} flagged (dev mode, ignored): {flags}")
        except Exception as e:
            log.debug(f"[AntiTamper] {name} error (non-fatal): {e}")
            result['details'][name] = {'safe': True, 'flags': [], 'error': str(e)}

    if result['passed']:
        log.debug(f"[AntiTamper] ✅ All {result['total_guards']} guards passed")
    else:
        log.critical(
            f"[AntiTamper] ❌ {len(result['failures'])} guard(s) failed: "
            f"{result['failures']}"
        )

    return result
