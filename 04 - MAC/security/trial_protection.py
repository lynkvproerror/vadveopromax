"""
Trial Protection v3.0 - Multi-Layer Anti-Crack System (macOS Hardened)
Implements: Keychain, xattr, file markers, Firebase backup, time verification

Features:
- Trial KEY required (no automatic trial)
- 3 file marker locations (hidden dot-files)
- macOS Keychain marker (very hard to find/delete)
- xattr marker on Home folder (invisible in Finder)
- Firebase backup (online verification — planned)
- Clock manipulation detection
"""

import os
import sys
import json
import subprocess
import hashlib
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
    
    Storage locations (priority order):
    1. Firebase: _trials/{machine_id_hash} (online, cannot be deleted by user)
    2. macOS Keychain: com.veo.trial (very hard to find/delete)
    3. xattr: com.veo.trial.ts on Home folder (invisible in Finder)
    4. File: ~/.veoauto/.trial (hidden dot-file)
    5. File: ~/Library/Application Support/VEO/.trial.dat (hidden)
    6. File: /tmp/.veo_trial.bin (volatile)
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
        """Get all file marker paths (macOS)."""
        return [
            Path.home() / ".veoauto" / ".trial",
            Path.home() / "Library" / "Application Support" / "VEO" / ".trial.dat",
            Path("/tmp") / ".veo_trial.bin",
        ]
    
    def _write_file_markers(self, trial_start: datetime):
        """Write trial start to all file locations."""
        encoded = self._encode_timestamp(trial_start)
        content = f"{self._marker_hash}:{encoded}"
        
        for path in self._get_file_paths():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                
                # On macOS, dot-prefix already hides files in Finder
                # No additional hiding needed
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
    # KEYCHAIN MARKER (macOS — very hard to find/delete)
    # =========================================================================
    
    _KEYCHAIN_SERVICE = "com.veo.trial"
    _KEYCHAIN_ACCOUNT = "VEO_Trial_Marker"
    
    def _write_keychain_marker(self, trial_start: datetime):
        """Write trial start to macOS Keychain.
        
        User must open Keychain Access.app and know the exact service name
        to find and delete this. 99% of users won't know how.
        """
        encoded = self._encode_timestamp(trial_start)
        value = f"{self._marker_hash}:{encoded}"
        try:
            # Delete existing entry first (ignore errors)
            subprocess.run(
                ['security', 'delete-generic-password',
                 '-a', self._KEYCHAIN_ACCOUNT,
                 '-s', self._KEYCHAIN_SERVICE],
                capture_output=True, timeout=5,
            )
            # Add new entry
            subprocess.run(
                ['security', 'add-generic-password',
                 '-a', self._KEYCHAIN_ACCOUNT,
                 '-s', self._KEYCHAIN_SERVICE,
                 '-w', value,
                 '-U'],  # Update if exists
                capture_output=True, timeout=5,
            )
        except Exception:
            pass  # Non-fatal: other markers still work
    
    def _read_keychain_marker(self) -> Optional[datetime]:
        """Read trial start from macOS Keychain."""
        try:
            result = subprocess.run(
                ['security', 'find-generic-password',
                 '-a', self._KEYCHAIN_ACCOUNT,
                 '-s', self._KEYCHAIN_SERVICE,
                 '-w'],  # Output password value only
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                content = result.stdout.strip()
                hash_part, encoded = content.split(":")
                if hash_part == self._marker_hash:
                    return self._decode_timestamp(encoded)
        except Exception:
            pass
        return None
    
    # =========================================================================
    # XATTR MARKER (invisible metadata on Home folder)
    # =========================================================================
    
    _XATTR_KEY = "com.veo.trial.ts"
    _XATTR_KEY2 = "com.apple.cs.veo"  # Blends with Apple code-signing attrs
    
    def _write_xattr_markers(self, trial_start: datetime):
        """Write trial start as extended attributes on Home folder.
        
        xattr is invisible in Finder. User would need to know:
        1. That xattr exists on their Home folder
        2. The exact attribute name
        3. How to use `xattr -d` to remove it
        """
        encoded = self._encode_timestamp(trial_start)
        value = f"{self._marker_hash}:{encoded}"
        home = str(Path.home())
        
        for attr_name in (self._XATTR_KEY, self._XATTR_KEY2):
            try:
                subprocess.run(
                    ['xattr', '-w', attr_name, value, home],
                    capture_output=True, timeout=5,
                )
            except Exception:
                continue
    
    def _read_xattr_markers(self) -> Optional[datetime]:
        """Read trial start from extended attributes on Home folder."""
        home = str(Path.home())
        
        for attr_name in (self._XATTR_KEY, self._XATTR_KEY2):
            try:
                result = subprocess.run(
                    ['xattr', '-p', attr_name, home],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    content = result.stdout.strip()
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
        
        # Write to ALL locations (redundancy = resilience)
        self._write_keychain_marker(now)   # Hardest to find/delete
        self._write_xattr_markers(now)     # Invisible in Finder
        self._write_file_markers(now)      # Hidden dot-files
        self._write_firebase_marker(now)   # Online backup (future)
        
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
        
        Priority: Firebase > Keychain > xattr > Files
        If found in a lower-priority source, re-write to ALL higher-priority
        sources (self-healing: restores markers that user deleted).
        """
        results = {}
        
        # Collect from all sources (don't short-circuit)
        results['firebase'] = self._read_firebase_marker()
        results['keychain'] = self._read_keychain_marker()
        results['xattr'] = self._read_xattr_markers()
        results['files'] = self._read_file_markers()
        
        # Find the first non-None value (by priority)
        trial_start = None
        for source in ('firebase', 'keychain', 'xattr', 'files'):
            if results[source] is not None:
                trial_start = results[source]
                break
        
        if trial_start is None:
            return None
        
        # Self-healing: restore any MISSING markers
        missing = [k for k, v in results.items() if v is None]
        if missing:
            self._heal_markers(trial_start, missing)
        
        return trial_start
    
    def _heal_markers(self, trial_start: datetime, missing: list):
        """Re-write ONLY missing trial markers (self-healing).
        
        Only writes to locations where markers were deleted.
        Avoids redundant writes on every call.
        """
        if 'keychain' in missing:
            try:
                self._write_keychain_marker(trial_start)
            except Exception:
                pass
        if 'xattr' in missing:
            try:
                self._write_xattr_markers(trial_start)
            except Exception:
                pass
        if 'files' in missing:
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
    print("Trial Protection v3.0 - Test (macOS Hardened)")
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
