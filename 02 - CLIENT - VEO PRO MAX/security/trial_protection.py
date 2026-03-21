"""
Trial Protection v3.0 - Multi-Layer Anti-Crack System (Windows Hardened)
Implements: Credential Manager, NTFS ADS, Registry, file markers, time verification

Features:
- Trial KEY required (no automatic trial)
- 3 file marker locations (hidden + attrib +H +S)
- 2 Windows Registry locations + shadow Crypto key
- Windows Credential Manager (very hard to find/delete)
- NTFS Alternate Data Streams (invisible in Explorer)
- Self-healing: auto-restores deleted markers
- Firebase backup (online verification planned)
- Clock manipulation detection
"""

import os
import sys
import json
import subprocess
import hashlib
import ctypes
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
    Multi-layer trial marker system (v3.0 Hardened).
    
    Storage locations (priority order):
    1. Firebase: _trials/{machine_id_hash} (online, cannot be deleted)
    2. Credential Manager: VEO_Trial_Marker (very hard to find/delete)
    3. NTFS ADS: hidden data stream on USERPROFILE (invisible in Explorer)
    4. Registry: HKCU\\Software\\VEO\\Trial
    5. Registry: HKCU\\Software\\Classes\\.veo\\Shell
    6. Shadow: HKCU\\Software\\Microsoft\\Cryptography\\VEO
    7-9. File markers (hidden + system attributes)
    
    Self-healing: if ANY marker survives, ALL others are auto-restored.
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
    # CREDENTIAL MANAGER MARKER (very hard to find/delete)
    # =========================================================================
    
    _CRED_TARGET = "VEO_Trial_Marker"
    
    def _write_credential_marker(self, trial_start: datetime):
        """Write trial start to Windows Credential Manager + shadow registry.
        
        User must open Control Panel > Credential Manager and know
        the exact target name to find and delete this. <1% of users know how.
        """
        encoded = self._encode_timestamp(trial_start)
        value = f"{self._marker_hash}:{encoded}"
        try:
            subprocess.run(
                ['cmdkey', '/generic:' + self._CRED_TARGET,
                 '/user:VEO', '/pass:' + value],
                capture_output=True, timeout=5,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except Exception:
            pass
        # Also write to shadow registry (deeply hidden path)
        self._write_credential_shadow(trial_start)
    
    def _read_credential_marker(self) -> Optional[datetime]:
        """Read trial start from shadow registry key."""
        try:
            key = winreg.OpenKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Cryptography\VEO",
                0, winreg.KEY_READ
            )
            encoded, _ = winreg.QueryValueEx(key, "_d")
            hash_val, _ = winreg.QueryValueEx(key, "_h")
            winreg.CloseKey(key)
            if hash_val == self._marker_hash:
                return self._decode_timestamp(encoded)
        except Exception:
            pass
        return None
    
    def _write_credential_shadow(self, trial_start: datetime):
        """Write to a deeply-hidden registry location (looks like Windows system key)."""
        encoded = self._encode_timestamp(trial_start)
        try:
            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Cryptography\VEO",
                0, winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "_d", 0, winreg.REG_SZ, encoded)
            winreg.SetValueEx(key, "_h", 0, winreg.REG_SZ, self._marker_hash)
            winreg.CloseKey(key)
        except Exception:
            pass
    
    # =========================================================================
    # NTFS ALTERNATE DATA STREAMS (invisible in Explorer)
    # =========================================================================
    
    def _get_ads_paths(self) -> list:
        """Get NTFS Alternate Data Stream paths.
        
        ADS are completely invisible in Windows Explorer, dir command,
        and most file managers. Only detectable via 'dir /R' or PowerShell.
        """
        home = str(Path.home())
        return [
            os.path.join(home, f"NTUSER.DAT:{self._CRED_TARGET}"),
            os.path.join(home, "Desktop.ini:veo_ts"),
        ]
    
    def _write_ads_markers(self, trial_start: datetime):
        """Write trial start as NTFS Alternate Data Streams.
        
        NTFS ADS are invisible in Explorer and most tools.
        User would need to know ADS exists, the exact stream name,
        and how to use 'more < file:stream' to read it.
        """
        encoded = self._encode_timestamp(trial_start)
        value = f"{self._marker_hash}:{encoded}"
        
        for ads_path in self._get_ads_paths():
            try:
                with open(ads_path, 'w') as f:
                    f.write(value)
            except Exception:
                continue
    
    def _read_ads_markers(self) -> Optional[datetime]:
        """Read trial start from NTFS Alternate Data Streams."""
        for ads_path in self._get_ads_paths():
            try:
                with open(ads_path, 'r') as f:
                    content = f.read().strip()
                hash_part, encoded = content.split(":")
                if hash_part == self._marker_hash:
                    return self._decode_timestamp(encoded)
            except Exception:
                continue
        return None
    
    # =========================================================================
    # FIREBASE MARKERS (Online backup)
    # =========================================================================
    
    def _write_firebase_marker(self, trial_start: datetime):
        """Write trial start to Firebase via REST API.
        NOTE: Legacy v1 disabled. Trial v2 uses register_trial() via admin/seller approve.
        """
        pass  # v1 disabled
    
    def _read_firebase_marker(self) -> Optional[datetime]:
        """Read trial start from Firebase via REST API.
        NOTE: Legacy v1 disabled. Trial v2 uses check_trial_status() via admin/seller approve.
        """
        return None  # v1 disabled
    
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
        
        # Write to ALL locations (redundancy = resilience)
        self._write_credential_marker(now)   # Credential Manager + shadow key
        self._write_ads_markers(now)          # NTFS ADS (invisible)
        self._write_registry_markers(now)     # Standard registry
        self._write_file_markers(now)         # Hidden files
        self._write_firebase_marker(now)      # Online backup (future)
        
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
        
        Priority: Firebase > Credential > ADS > Registry > Files
        If found in a lower-priority source, re-write to ALL sources
        (self-healing: restores markers that user deleted).
        """
        # Firebase first (cannot be deleted by user)
        fb = self._read_firebase_marker()
        if fb:
            self._heal_markers(fb)
            return fb
        
        # Credential Manager second (very hard to find)
        cred = self._read_credential_marker()
        if cred:
            self._heal_markers(cred)
            return cred
        
        # NTFS ADS third (invisible in Explorer)
        ads = self._read_ads_markers()
        if ads:
            self._heal_markers(ads)
            return ads
        
        # Registry fourth
        reg = self._read_registry_markers()
        if reg:
            self._heal_markers(reg)
            return reg
        
        # Files last (easiest to delete)
        fl = self._read_file_markers()
        if fl:
            self._heal_markers(fl)
            return fl
        
        return None
    
    def _heal_markers(self, trial_start: datetime):
        """Re-write trial markers to ALL locations (self-healing).
        
        If user deleted some markers but not all, this restores them.
        Called whenever trial_start is found from any source.
        """
        try:
            self._write_credential_marker(trial_start)
        except Exception:
            pass
        try:
            self._write_ads_markers(trial_start)
        except Exception:
            pass
        try:
            self._write_registry_markers(trial_start)
        except Exception:
            pass
        try:
            self._write_file_markers(trial_start)
        except Exception:
            pass
    
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
    print("Trial Protection v3.0 - Test (Windows Hardened)")
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
