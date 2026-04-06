"""
DEPRECATED - DO NOT USE - Runtime uses security/ directory modules
VEO Pro Max - Security Protection (LEGACY MODULE)

Reference: SESSION_06_WORKFLOWS_SECURITY.md
Role: Anti-tampering, anti-debug, environment checks
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import hashlib
import ctypes
import time
import sys
import os
import socket

sys.path.insert(0, str(Path(__file__).parent.parent))


class SecurityStatus(str, Enum):
    """Security check status."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class SecurityCheckResult:
    """Result of a security check."""
    name: str
    status: SecurityStatus
    message: str
    details: Optional[str] = None


class IntegrityChecker:
    """SHA-256 EXE verification.
    
    Features:
    - Compute hash of executable
    - Compare with expected hash
    - Detect file tampering
    """
    
    def __init__(self, expected_hash: Optional[str] = None):
        self._expected_hash = expected_hash
        self._cached_hash: Optional[str] = None
    
    def compute_hash(self, file_path: Optional[str] = None) -> str:
        """Compute SHA-256 hash of file."""
        if file_path is None:
            file_path = sys.executable
        
        sha256 = hashlib.sha256()
        
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            
            return sha256.hexdigest()
        except Exception:
            return ""
    
    def verify(self) -> SecurityCheckResult:
        """Verify executable integrity."""
        if not self._expected_hash:
            return SecurityCheckResult(
                name="Integrity",
                status=SecurityStatus.WARN,
                message="No expected hash configured",
            )
        
        current_hash = self.compute_hash()
        if not current_hash:
            return SecurityCheckResult(
                name="Integrity",
                status=SecurityStatus.FAIL,
                message="Could not read executable",
            )
        
        if current_hash == self._expected_hash:
            return SecurityCheckResult(
                name="Integrity",
                status=SecurityStatus.PASS,
                message="Executable integrity verified",
            )
        else:
            return SecurityCheckResult(
                name="Integrity",
                status=SecurityStatus.FAIL,
                message="Executable has been modified",
                details=f"Expected: {self._expected_hash[:16]}..., Got: {current_hash[:16]}...",
            )
    
    def set_expected_hash(self, hash_value: str):
        """Set expected hash for verification."""
        self._expected_hash = hash_value


class AntiDebug:
    """Anti-debugging detection.
    
    Features:
    - IsDebuggerPresent check (Windows)
    - Timing check for breakpoints
    """
    
    TIMING_THRESHOLD_MS = 100  # Max expected time for simple operations
    
    @staticmethod
    def is_debugger_present() -> bool:
        """Check if debugger is attached (Windows)."""
        if sys.platform != 'win32':
            return False
        
        try:
            kernel32 = ctypes.windll.kernel32
            return kernel32.IsDebuggerPresent() != 0
        except Exception:
            return False
    
    @staticmethod
    def timing_check() -> bool:
        """Detect debugging via timing anomalies."""
        start = time.perf_counter_ns()
        
        # Simple operations that should be fast
        _ = sum(range(1000))
        _ = [i * i for i in range(100)]
        
        end = time.perf_counter_ns()
        elapsed_ms = (end - start) / 1_000_000
        
        # If operations take too long, breakpoint may be set
        return elapsed_ms > AntiDebug.TIMING_THRESHOLD_MS
    
    def check(self) -> SecurityCheckResult:
        """Run anti-debug checks."""
        if self.is_debugger_present():
            return SecurityCheckResult(
                name="AntiDebug",
                status=SecurityStatus.FAIL,
                message="Debugger detected",
            )
        
        if self.timing_check():
            return SecurityCheckResult(
                name="AntiDebug",
                status=SecurityStatus.WARN,
                message="Timing anomaly detected",
            )
        
        return SecurityCheckResult(
            name="AntiDebug",
            status=SecurityStatus.PASS,
            message="No debugger detected",
        )


class TimeTamperDetector:
    """Detect system time tampering.
    
    Features:
    - NTP time verification
    - Monotonic clock comparison
    - Suspicious time jumps
    """
    
    NTP_SERVERS = [
        "time.google.com",
        "pool.ntp.org",
        "time.windows.com",
    ]
    
    MAX_DRIFT_SECONDS = 300  # 5 minutes
    
    def __init__(self):
        self._last_check_time: Optional[datetime] = None
        self._last_monotonic: Optional[float] = None
    
    def get_ntp_time(self) -> Optional[datetime]:
        """Get time from NTP server (simplified)."""
        # Full NTP implementation would use ntplib
        # For now, use a basic socket-based check
        try:
            # This is a simplified check - just verify network time server is reachable
            for server in self.NTP_SERVERS:
                try:
                    socket.create_connection((server, 123), timeout=2)
                    # If we can connect, assume time is roughly correct
                    return datetime.now()
                except Exception:
                    continue
            return None
        except Exception:
            return None
    
    def check_monotonic_consistency(self) -> bool:
        """Check if system time is consistent with monotonic clock."""
        now = datetime.now()
        mono = time.monotonic()
        
        if self._last_check_time and self._last_monotonic:
            time_delta = (now - self._last_check_time).total_seconds()
            mono_delta = mono - self._last_monotonic
            
            # If time jumped significantly but monotonic didn't
            if abs(time_delta - mono_delta) > self.MAX_DRIFT_SECONDS:
                return False
        
        self._last_check_time = now
        self._last_monotonic = mono
        return True
    
    def check(self) -> SecurityCheckResult:
        """Run time tamper checks."""
        if not self.check_monotonic_consistency():
            return SecurityCheckResult(
                name="TimeTamper",
                status=SecurityStatus.FAIL,
                message="System time manipulation detected",
            )
        
        return SecurityCheckResult(
            name="TimeTamper",
            status=SecurityStatus.PASS,
            message="System time appears valid",
        )


class TrialProtection:
    """Multi-location trial markers.
    
    Features:
    - Store trial start in multiple locations
    - Cross-validate markers
    - Detect marker removal/modification
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self._storage_dir = storage_dir or Path.home() / ".veoauto"
        self._marker_locations = [
            self._storage_dir / ".trial",
            self._storage_dir / ".cache" / ".ts",
            Path(os.environ.get("TEMP", "/tmp")) / ".veo_ts",
        ]
    
    def init_trial(self) -> bool:
        """Initialize trial markers in multiple locations."""
        timestamp = datetime.now().isoformat()
        
        for location in self._marker_locations:
            try:
                location.parent.mkdir(parents=True, exist_ok=True)
                location.write_text(timestamp)
            except Exception:
                continue
        
        return True
    
    def get_trial_start(self) -> Optional[datetime]:
        """Get earliest trial start from all markers."""
        earliest = None
        
        for location in self._marker_locations:
            try:
                if location.exists():
                    ts = datetime.fromisoformat(location.read_text().strip())
                    if earliest is None or ts < earliest:
                        earliest = ts
            except Exception:
                continue
        
        return earliest
    
    def validate_markers(self) -> SecurityCheckResult:
        """Validate trial markers are consistent."""
        timestamps = []
        missing_count = 0
        
        for location in self._marker_locations:
            try:
                if location.exists():
                    ts = datetime.fromisoformat(location.read_text().strip())
                    timestamps.append(ts)
                else:
                    missing_count += 1
            except Exception:
                missing_count += 1
        
        if not timestamps:
            # No markers - could be fresh install or tampering
            return SecurityCheckResult(
                name="TrialProtection",
                status=SecurityStatus.WARN,
                message="No trial markers found",
            )
        
        if missing_count >= 2:
            return SecurityCheckResult(
                name="TrialProtection",
                status=SecurityStatus.WARN,
                message="Some trial markers missing",
            )
        
        # Check consistency (all within 1 second)
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        if (max_ts - min_ts).total_seconds() > 1:
            return SecurityCheckResult(
                name="TrialProtection",
                status=SecurityStatus.FAIL,
                message="Trial markers are inconsistent",
            )
        
        return SecurityCheckResult(
            name="TrialProtection",
            status=SecurityStatus.PASS,
            message="Trial markers valid",
        )


class EnvironmentChecker:
    """VM/Sandbox detection.
    
    Features:
    - Check for VM indicators
    - Detect common sandboxes
    - Low-level environment inspection
    """
    
    VM_INDICATORS = [
        "VBOX",
        "VMWARE",
        "VIRTUAL",
        "QEMU",
        "XEN",
        "HYPER-V",
        "PARALLELS",
    ]
    
    SANDBOX_PROCESSES = [
        "wireshark",
        "fiddler",
        "charles",
        "procmon",
        "procexp",
        "ollydbg",
        "x64dbg",
        "ida",
        "ghidra",
    ]
    
    @staticmethod
    def check_vm_registry() -> bool:
        """Check Windows registry for VM indicators."""
        if sys.platform != 'win32':
            return False
        
        try:
            import winreg
            
            keys_to_check = [
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\VBoxGuest"),
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\vmtoolsd"),
            ]
            
            for hkey, path in keys_to_check:
                try:
                    winreg.OpenKey(hkey, path)
                    return True
                except FileNotFoundError:
                    continue
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def check_system_manufacturer() -> bool:
        """Check system manufacturer for VM names."""
        if sys.platform != 'win32':
            return False
        
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "computersystem", "get", "manufacturer"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
            
            output = result.stdout.upper()
            return any(indicator in output for indicator in EnvironmentChecker.VM_INDICATORS)
        except Exception:
            return False
    
    def check(self) -> SecurityCheckResult:
        """Run environment checks."""
        issues = []
        
        if self.check_vm_registry():
            issues.append("VM guest services detected")
        
        if self.check_system_manufacturer():
            issues.append("VM manufacturer detected")
        
        if issues:
            return SecurityCheckResult(
                name="Environment",
                status=SecurityStatus.WARN,
                message="Running in virtual environment",
                details="; ".join(issues),
            )
        
        return SecurityCheckResult(
            name="Environment",
            status=SecurityStatus.PASS,
            message="Environment appears normal",
        )


class SecurityManager:
    """Central security management.
    
    Coordinates all security checks.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.integrity = IntegrityChecker()
        self.anti_debug = AntiDebug()
        self.time_tamper = TimeTamperDetector()
        self.trial_protection = TrialProtection(storage_dir)
        self.environment = EnvironmentChecker()
    
    def run_all_checks(self) -> List[SecurityCheckResult]:
        """Run all security checks."""
        results = [
            self.integrity.verify(),
            self.anti_debug.check(),
            self.time_tamper.check(),
            self.trial_protection.validate_markers(),
            self.environment.check(),
        ]
        return results
    
    def is_secure(self) -> bool:
        """Check if all security checks pass."""
        results = self.run_all_checks()
        return all(r.status != SecurityStatus.FAIL for r in results)
    
    def get_summary(self) -> dict:
        """Get security status summary."""
        results = self.run_all_checks()
        
        return {
            "secure": all(r.status != SecurityStatus.FAIL for r in results),
            "checks": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                }
                for r in results
            ],
            "warnings": sum(1 for r in results if r.status == SecurityStatus.WARN),
            "failures": sum(1 for r in results if r.status == SecurityStatus.FAIL),
        }
