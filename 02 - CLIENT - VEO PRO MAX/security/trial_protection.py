"""
Trial Protection v2.0 - Multi-Layer Anti-Crack System
Implements: Registry markers, multiple file markers, Firebase backup, time verification

Features:
- Trial KEY required (no automatic trial)
- 3 file marker locations (hidden)
- 2 Windows Registry locations
- Firebase backup (online verification)
- Clock manipulation detection
"""

import os
import sys
import json
import hashlib
import winreg
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class TrialStatus:
    """Trial validation result"""
    valid: bool
    days_remaining: int = 0
    started: Optional[datetime] = None
    expires: Optional[datetime] = None
    error: Optional[str] = None


class TimeVerifier:
    """
    Multi-source time verification to detect clock manipulation.
    """
    
    MAX_DRIFT_SECONDS = 300  # 5 minutes tolerance
    
    def __init__(self):
        self._cached_offset: Optional[float] = None
        self._last_check: Optional[datetime] = None
    
    def _get_http_time(self) -> Optional[float]:
        """Get time from HTTP headers (Google/Cloudflare)."""
        urls = ["https://www.google.com", "https://www.cloudflare.com"]
        
        for url in urls:
            try:
                req = urllib.request.Request(url, method="HEAD")
                req.add_header("User-Agent", "VEO/1.0")
                
                with urllib.request.urlopen(req, timeout=3) as response:
                    date_str = response.headers.get("Date")
                    if date_str:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(date_str)
                        return dt.timestamp()
            except:
                continue
        return None
    
    def _get_firebase_time(self) -> Optional[float]:
        """Get time from Firebase server via REST API."""
        try:
            from firebase_rest_client import FirebaseRESTClient
            client = FirebaseRESTClient()
            # Use HTTP time as fallback — REST client doesn't expose server timestamp
            return None  # Graceful fallback to HTTP time
        except:
            return None
    
    def verify(self) -> Tuple[bool, float]:
        """
        Verify system time.
        
        Returns:
            (is_valid: bool, offset_seconds: float)
        """
        import time
        
        # Try HTTP time first (most available)
        trusted = self._get_http_time()
        
        if trusted is None:
            trusted = self._get_firebase_time()
        
        if trusted is None:
            # No source available - allow (offline mode)
            return True, 0.0
        
        offset = time.time() - trusted
        self._cached_offset = offset
        self._last_check = datetime.now()
        
        return abs(offset) < self.MAX_DRIFT_SECONDS, offset
    
    def get_verified_now(self) -> datetime:
        """Get current time corrected for offset."""
        if self._cached_offset is not None:
            return datetime.now() - timedelta(seconds=self._cached_offset)
        return datetime.now()


class TrialMarkerManager:
    """
    Multi-layer trial marker system.
    
    Storage locations:
    1. File: %USERPROFILE%/.veoauto/.trial (hidden)
    2. File: %APPDATA%/VEO/.trial.dat (hidden)
    3. File: %LOCALAPPDATA%/VEO/trial.bin (hidden)
    4. Registry: HKCU\\Software\\VEO\\Trial
    5. Registry: HKCU\\Software\\Classes\\.veo\\Shell (hidden in file association)
    6. Firebase: _trials/{machine_id_hash}
    """
    
    TRIAL_DAYS = 7
    
    def __init__(self, machine_id: str):
        self.machine_id = machine_id
        self._marker_hash = self._generate_marker_hash()
        self.time_verifier = TimeVerifier()
    
    def _generate_marker_hash(self) -> str:
        """Generate unique marker based on machine ID."""
        data = f"{self.machine_id}:veo_trial_marker"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _encode_timestamp(self, dt: datetime) -> str:
        """Encode timestamp with obfuscation."""
        ts = int(dt.timestamp())
        xor_key = int(self._marker_hash[:8], 16)
        encoded = ts ^ xor_key
        return f"{encoded:x}"
    
    def _decode_timestamp(self, encoded: str) -> Optional[datetime]:
        """Decode obfuscated timestamp."""
        try:
            xor_key = int(self._marker_hash[:8], 16)
            decoded = int(encoded, 16) ^ xor_key
            return datetime.fromtimestamp(decoded)
        except:
            return None
    
    # =========================================================================
    # FILE MARKERS (3 locations)
    # =========================================================================
    
    def _get_file_paths(self) -> list:
        """Get all file marker paths."""
        return [
            Path.home() / ".veoauto" / ".trial",
            Path(os.environ.get("APPDATA", "")) / "VEO" / ".trial.dat",
            Path(os.environ.get("LOCALAPPDATA", "")) / "VEO" / "trial.bin",
        ]
    
    def _write_file_markers(self, trial_start: datetime):
        """Write trial start to all file locations."""
        encoded = self._encode_timestamp(trial_start)
        content = f"{self._marker_hash}:{encoded}"
        
        for path in self._get_file_paths():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                
                # Hide file on Windows
                if sys.platform == 'win32':
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(str(path), 2)
            except:
                continue
    
    def _read_file_markers(self) -> Optional[datetime]:
        """Read trial start from any file."""
        for path in self._get_file_paths():
            try:
                if path.exists():
                    content = path.read_text().strip()
                    hash_part, encoded = content.split(":")
                    if hash_part == self._marker_hash:
                        return self._decode_timestamp(encoded)
            except:
                continue
        return None
    
    # =========================================================================
    # REGISTRY MARKERS (2 locations)
    # =========================================================================
    
    def _get_registry_keys(self) -> list:
        """Get all registry key paths."""
        return [
            (winreg.HKEY_CURRENT_USER, r"Software\VEO\Trial"),
            (winreg.HKEY_CURRENT_USER, r"Software\Classes\.veo\Shell"),
        ]
    
    def _write_registry_markers(self, trial_start: datetime):
        """Write trial start to Windows Registry."""
        encoded = self._encode_timestamp(trial_start)
        
        for root_key, key_path in self._get_registry_keys():
            try:
                key = winreg.CreateKeyEx(root_key, key_path, 0, winreg.KEY_WRITE)
                winreg.SetValueEx(key, "Data", 0, winreg.REG_SZ, encoded)
                winreg.SetValueEx(key, "Hash", 0, winreg.REG_SZ, self._marker_hash)
                winreg.CloseKey(key)
            except:
                continue
    
    def _read_registry_markers(self) -> Optional[datetime]:
        """Read trial start from Registry."""
        for root_key, key_path in self._get_registry_keys():
            try:
                key = winreg.OpenKeyEx(root_key, key_path, 0, winreg.KEY_READ)
                encoded, _ = winreg.QueryValueEx(key, "Data")
                hash_val, _ = winreg.QueryValueEx(key, "Hash")
                winreg.CloseKey(key)
                
                if hash_val == self._marker_hash:
                    return self._decode_timestamp(encoded)
            except:
                continue
        return None
    
    # =========================================================================
    # FIREBASE MARKERS (Online backup)
    # =========================================================================
    
    def _write_firebase_marker(self, trial_start: datetime):
        """Write trial start to Firebase via REST API.
        NOTE: Legacy v1 — disabled. Trial v2 uses register_trial() via admin/seller approve.
        """
        pass  # v1 disabled — FirebaseRESTClient has no set_document()
    
    def _read_firebase_marker(self) -> Optional[datetime]:
        """Read trial start from Firebase via REST API.
        NOTE: Legacy v1 — disabled. Trial v2 uses check_trial_status() via admin/seller approve.
        """
        return None  # v1 disabled — FirebaseRESTClient has no get_document()
    
    # =========================================================================
    # MAIN API
    # =========================================================================
    
    def start_trial(self) -> TrialStatus:
        """
        Start a new trial period.
        Called when admin generates a trial key.
        
        Returns:
            TrialStatus with trial info
        """
        # Verify time first
        time_ok, offset = self.time_verifier.verify()
        if not time_ok:
            return TrialStatus(
                valid=False,
                error=f"Clock manipulation detected (offset: {offset:.0f}s)"
            )
        
        # Check if trial already exists (no restart!)
        existing = self.get_trial_start()
        if existing is not None:
            return TrialStatus(
                valid=False,
                error="Trial already used on this machine"
            )
        
        # Start new trial
        now = self.time_verifier.get_verified_now()
        
        # Write to ALL locations
        self._write_file_markers(now)
        self._write_registry_markers(now)
        self._write_firebase_marker(now)
        
        expires = now + timedelta(days=self.TRIAL_DAYS)
        
        return TrialStatus(
            valid=True,
            days_remaining=self.TRIAL_DAYS,
            started=now,
            expires=expires
        )
    
    def get_trial_start(self) -> Optional[datetime]:
        """
        Get trial start from any available source.
        
        Priority: Firebase > Registry > Files
        """
        # Firebase first (most tamper-resistant)
        fb = self._read_firebase_marker()
        if fb:
            return fb
        
        # Registry second
        reg = self._read_registry_markers()
        if reg:
            return reg
        
        # Files last
        return self._read_file_markers()
    
    def validate_trial(self) -> TrialStatus:
        """
        Validate current trial status.
        
        Returns:
            TrialStatus with validation result
        """
        # Verify time first
        time_ok, offset = self.time_verifier.verify()
        if not time_ok:
            return TrialStatus(
                valid=False,
                error=f"Clock manipulation detected (offset: {offset:.0f}s)"
            )
        
        # Get trial start from any source
        start = self.get_trial_start()
        
        if start is None:
            return TrialStatus(
                valid=False,
                error="No trial found - license key required"
            )
        
        # Calculate remaining days
        now = self.time_verifier.get_verified_now()
        expires = start + timedelta(days=self.TRIAL_DAYS)
        remaining = (expires - now).days
        
        if remaining <= 0:
            return TrialStatus(
                valid=False,
                days_remaining=0,
                started=start,
                expires=expires,
                error="Trial expired"
            )
        
        return TrialStatus(
            valid=True,
            days_remaining=remaining,
            started=start,
            expires=expires
        )


# Convenience function for license_client.py integration
def check_trial(machine_id: str) -> TrialStatus:
    """Check trial status with full protection."""
    manager = TrialMarkerManager(machine_id)
    return manager.validate_trial()


def activate_trial_key(machine_id: str, trial_key: str) -> TrialStatus:
    """
    Activate a trial key.
    
    Trial key format: TRIAL-XXXX-XXXX (generated by admin)
    """
    # Simple validation (real implementation would check Firebase)
    if not trial_key.upper().startswith("TRIAL-"):
        return TrialStatus(valid=False, error="Invalid trial key format")
    
    manager = TrialMarkerManager(machine_id)
    return manager.start_trial()


if __name__ == "__main__":
    print("=" * 60)
    print("Trial Protection v2.0 - Test")
    print("=" * 60)
    
    # Test with dummy machine ID
    machine_id = "TEST_MACHINE_ID"
    
    manager = TrialMarkerManager(machine_id)
    
    print(f"\nMachine ID: {machine_id}")
    print(f"Marker Hash: {manager._marker_hash}")
    
    # Check trial
    status = manager.validate_trial()
    
    print(f"\nTrial Status:")
    print(f"  Valid: {status.valid}")
    print(f"  Days remaining: {status.days_remaining}")
    print(f"  Error: {status.error or 'None'}")
    
    if not status.valid and "No trial found" in (status.error or ""):
        print("\n⚠️ Trial not started - Run start_trial() first")
    
    print("=" * 60)
