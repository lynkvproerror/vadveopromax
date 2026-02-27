# 🛡️ Trial & Time Protection - Implementation Guide

> **Version**: 1.0  
> **Created**: 2026-02-02  
> **Purpose**: Trial reset prevention và clock manipulation detection

---

## 📋 Overview

Hai vấn đề cần giải quyết:
1. **[M6] Trial Reset Prevention**: User xóa marker files để reset trial
2. **[M7] Clock Manipulation Detection**: User đặt lại thời gian hệ thống

---

## 🔐 [M6] Trial Reset Prevention

### Current Implementation (3 Marker Files)

```python
# Current locations (documented in WORKFLOW_ANTI_CRACK_PROTECTION.md)
MARKER_LOCATIONS = [
    Path.home() / ".veo_trial",                    # User home
    Path(os.environ.get("APPDATA", "")) / ".veo",  # AppData
    Path(os.environ.get("LOCALAPPDATA", "")) / ".veo_trial.dat"  # LocalAppData
]
```

**Problem**: User có thể tìm và xóa tất cả files này.

### ✅ Enhanced Solution: Registry + Hidden Markers

```python
"""
Trial Reset Prevention v2.0
Multi-layer marker system with Windows Registry
"""

import os
import winreg
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

class TrialMarkerManager:
    """
    Multi-layer trial marker system.
    
    Markers are stored in:
    1. File system (3 hidden locations)
    2. Windows Registry (2 locations)  
    3. Firebase (if online)
    """
    
    REGISTRY_KEYS = [
        (winreg.HKEY_CURRENT_USER, r"Software\VEO\Trial"),
        (winreg.HKEY_CURRENT_USER, r"Software\Classes\.veo\DefaultIcon"),  # Hidden in file association
    ]
    
    FILE_MARKERS = [
        Path.home() / ".veo_trial",
        Path(os.environ.get("APPDATA", "")) / ".veo" / "trial.dat",
        Path(os.environ.get("LOCALAPPDATA", "")) / "VEO" / ".trial",
    ]
    
    def __init__(self, machine_id: str):
        self.machine_id = machine_id
        self._marker_hash = self._generate_marker_hash()
    
    def _generate_marker_hash(self) -> str:
        """Generate unique marker based on machine ID and install time."""
        data = f"{self.machine_id}:trial_start"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _encode_timestamp(self, dt: datetime) -> str:
        """Encode timestamp with obfuscation."""
        ts = int(dt.timestamp())
        # XOR with marker hash for obfuscation
        encoded = ts ^ int(self._marker_hash[:8], 16)
        return f"{encoded:x}"
    
    def _decode_timestamp(self, encoded: str) -> Optional[datetime]:
        """Decode obfuscated timestamp."""
        try:
            decoded = int(encoded, 16) ^ int(self._marker_hash[:8], 16)
            return datetime.fromtimestamp(decoded)
        except (ValueError, OSError):
            return None
    
    # =========================================================================
    # FILE MARKERS
    # =========================================================================
    
    def write_file_markers(self, trial_start: datetime):
        """Write trial start to all file locations."""
        encoded = self._encode_timestamp(trial_start)
        content = f"{self._marker_hash}:{encoded}"
        
        for path in self.FILE_MARKERS:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                
                # Hide file on Windows
                if os.name == 'nt':
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(str(path), 2)  # FILE_ATTRIBUTE_HIDDEN
            except Exception:
                continue
    
    def read_file_markers(self) -> Optional[datetime]:
        """Read trial start from any available file."""
        for path in self.FILE_MARKERS:
            try:
                if path.exists():
                    content = path.read_text().strip()
                    hash_part, encoded = content.split(":")
                    if hash_part == self._marker_hash:
                        return self._decode_timestamp(encoded)
            except Exception:
                continue
        return None
    
    # =========================================================================
    # REGISTRY MARKERS
    # =========================================================================
    
    def write_registry_markers(self, trial_start: datetime):
        """Write trial start to Windows Registry."""
        encoded = self._encode_timestamp(trial_start)
        
        for root_key, key_path in self.REGISTRY_KEYS:
            try:
                # Create key if not exists
                key = winreg.CreateKeyEx(root_key, key_path, 0, winreg.KEY_WRITE)
                
                # Write encoded value (looks like random data)
                winreg.SetValueEx(key, "Data", 0, winreg.REG_SZ, encoded)
                winreg.SetValueEx(key, "Hash", 0, winreg.REG_SZ, self._marker_hash)
                
                winreg.CloseKey(key)
            except Exception:
                continue
    
    def read_registry_markers(self) -> Optional[datetime]:
        """Read trial start from Registry."""
        for root_key, key_path in self.REGISTRY_KEYS:
            try:
                key = winreg.OpenKeyEx(root_key, key_path, 0, winreg.KEY_READ)
                
                encoded, _ = winreg.QueryValueEx(key, "Data")
                hash_val, _ = winreg.QueryValueEx(key, "Hash")
                
                winreg.CloseKey(key)
                
                if hash_val == self._marker_hash:
                    return self._decode_timestamp(encoded)
            except Exception:
                continue
        return None
    
    # =========================================================================
    # FIREBASE MARKERS (Online)
    # =========================================================================
    
    def write_firebase_marker(self, trial_start: datetime):
        """Write trial start to Firebase (if authenticated)."""
        try:
            from firebase_admin import firestore
            db = firestore.client()
            
            mid_hash = hashlib.sha256(self.machine_id.encode()).hexdigest()[:16]
            
            db.collection("_trials").document(mid_hash).set({
                "start": trial_start.isoformat(),
                "created": firestore.SERVER_TIMESTAMP
            })
        except Exception:
            pass  # Silently fail if no Firebase
    
    def read_firebase_marker(self) -> Optional[datetime]:
        """Read trial start from Firebase."""
        try:
            from firebase_admin import firestore
            db = firestore.client()
            
            mid_hash = hashlib.sha256(self.machine_id.encode()).hexdigest()[:16]
            doc = db.collection("_trials").document(mid_hash).get()
            
            if doc.exists:
                return datetime.fromisoformat(doc.to_dict()["start"])
        except Exception:
            pass
        return None
    
    # =========================================================================
    # MAIN API
    # =========================================================================
    
    def initialize_trial(self) -> datetime:
        """
        Initialize trial - called on first run.
        
        Returns:
            Trial start datetime
        """
        now = datetime.now()
        
        # Write to all locations
        self.write_file_markers(now)
        self.write_registry_markers(now)
        self.write_firebase_marker(now)
        
        return now
    
    def get_trial_start(self) -> Optional[datetime]:
        """
        Get trial start from any available source.
        
        Priority: Firebase > Registry > File
        (Firebase is most tamper-resistant)
        """
        # Try Firebase first (most reliable)
        fb_start = self.read_firebase_marker()
        if fb_start:
            return fb_start
        
        # Try Registry
        reg_start = self.read_registry_markers()
        if reg_start:
            return reg_start
        
        # Try files
        file_start = self.read_file_markers()
        if file_start:
            return file_start
        
        # No marker found - could be first run or tampering
        return None
    
    def is_trial_valid(self, trial_days: int = 7) -> tuple[bool, int]:
        """
        Check if trial is still valid.
        
        Returns:
            (is_valid: bool, days_remaining: int)
        """
        start = self.get_trial_start()
        
        if start is None:
            # First run - initialize trial
            start = self.initialize_trial()
        
        elapsed = (datetime.now() - start).days
        remaining = max(0, trial_days - elapsed)
        
        return remaining > 0, remaining


# Usage example
if __name__ == "__main__":
    from machine_id import get_machine_id
    
    manager = TrialMarkerManager(get_machine_id())
    is_valid, days = manager.is_trial_valid()
    
    if is_valid:
        print(f"✅ Trial active: {days} days remaining")
    else:
        print("❌ Trial expired - please purchase license")
```

---

## ⏰ [M7] Clock Manipulation Detection

### Current Implementation (NTP Check)

```python
# Current: Check NTP time server
import ntplib
ntp_time = ntplib.NTPClient().request('pool.ntp.org').tx_time
```

**Problem**: NTP có thể bị block bởi firewall.

### ✅ Enhanced Solution: Multi-Source Time Verification

```python
"""
Clock Manipulation Detection v2.0
Multi-source time verification with fallbacks
"""

import time
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple
import urllib.request
import json

class TimeVerifier:
    """
    Verify system time against multiple trusted sources.
    
    Sources (in priority order):
    1. Firebase server timestamp
    2. World Time API
    3. Google/Cloudflare headers
    4. NTP pool
    
    Fallback: Allow if NO source reachable (offline mode)
    """
    
    MAX_DRIFT_SECONDS = 300  # 5 minutes tolerance
    
    def __init__(self):
        self._cached_offset: Optional[float] = None
        self._last_check: Optional[datetime] = None
        self._check_interval = timedelta(hours=1)
    
    # =========================================================================
    # TIME SOURCES
    # =========================================================================
    
    def _get_firebase_time(self) -> Optional[float]:
        """Get time from Firebase server timestamp."""
        try:
            from firebase_admin import firestore
            db = firestore.client()
            
            # Write and read server timestamp
            ref = db.collection("_time_check").document("ping")
            ref.set({"ts": firestore.SERVER_TIMESTAMP})
            doc = ref.get()
            
            server_time = doc.to_dict()["ts"]
            return server_time.timestamp()
        except Exception:
            return None
    
    def _get_worldtime_api(self) -> Optional[float]:
        """Get time from WorldTimeAPI (free, no API key)."""
        try:
            url = "http://worldtimeapi.org/api/timezone/Etc/UTC"
            req = urllib.request.Request(url, headers={"User-Agent": "VEO/1.0"})
            
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read())
                return data["unixtime"]
        except Exception:
            return None
    
    def _get_http_header_time(self) -> Optional[float]:
        """Get time from HTTP Date header (Google/Cloudflare)."""
        urls = [
            "https://www.google.com",
            "https://www.cloudflare.com",
            "https://www.microsoft.com"
        ]
        
        for url in urls:
            try:
                req = urllib.request.Request(url, method="HEAD")
                req.add_header("User-Agent", "VEO/1.0")
                
                with urllib.request.urlopen(req, timeout=3) as response:
                    date_str = response.headers.get("Date")
                    if date_str:
                        # Parse HTTP date format
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(date_str)
                        return dt.timestamp()
            except Exception:
                continue
        
        return None
    
    def _get_ntp_time(self) -> Optional[float]:
        """Get time from NTP pool."""
        try:
            import ntplib
            client = ntplib.NTPClient()
            response = client.request('pool.ntp.org', version=3, timeout=3)
            return response.tx_time
        except Exception:
            return None
    
    # =========================================================================
    # VERIFICATION
    # =========================================================================
    
    def _get_trusted_time(self) -> Optional[float]:
        """Get time from first available trusted source."""
        sources = [
            ("Firebase", self._get_firebase_time),
            ("WorldTimeAPI", self._get_worldtime_api),
            ("HTTP Headers", self._get_http_header_time),
            ("NTP", self._get_ntp_time),
        ]
        
        for name, getter in sources:
            try:
                result = getter()
                if result:
                    print(f"⏰ Time source: {name}")
                    return result
            except Exception:
                continue
        
        return None
    
    def verify_system_time(self, force: bool = False) -> Tuple[bool, str]:
        """
        Verify system time against trusted sources.
        
        Args:
            force: Force check even if recently verified
            
        Returns:
            (is_valid: bool, message: str)
        """
        now = datetime.now()
        
        # Use cached result if recent
        if not force and self._last_check and self._cached_offset is not None:
            if (now - self._last_check) < self._check_interval:
                is_valid = abs(self._cached_offset) < self.MAX_DRIFT_SECONDS
                return is_valid, f"Cached: offset {self._cached_offset:.0f}s"
        
        # Get trusted time
        trusted_time = self._get_trusted_time()
        
        if trusted_time is None:
            # No source available - allow offline mode
            return True, "Offline mode - no time sources available"
        
        # Calculate offset
        system_time = time.time()
        offset = system_time - trusted_time
        
        self._cached_offset = offset
        self._last_check = now
        
        # Check drift
        if abs(offset) > self.MAX_DRIFT_SECONDS:
            return False, f"Clock drift detected: {offset:.0f}s"
        
        return True, f"Time verified: offset {offset:.1f}s"
    
    def get_verified_time(self) -> datetime:
        """
        Get current time, corrected for any known offset.
        
        Use this instead of datetime.now() for license checks.
        """
        if self._cached_offset is not None:
            # Correct for offset
            return datetime.now() - timedelta(seconds=self._cached_offset)
        else:
            # Verify first
            self.verify_system_time()
            if self._cached_offset is not None:
                return datetime.now() - timedelta(seconds=self._cached_offset)
            return datetime.now()


# Integration with license checking
class SecureLicenseChecker:
    """License checker with time verification."""
    
    def __init__(self):
        self.time_verifier = TimeVerifier()
    
    def check_expiry(self, expiry_date: datetime) -> Tuple[bool, str]:
        """
        Check if license is expired using verified time.
        """
        # Verify system time first
        time_valid, time_msg = self.time_verifier.verify_system_time()
        
        if not time_valid:
            return False, f"⚠️ {time_msg}"
        
        # Use verified time for comparison
        current = self.time_verifier.get_verified_time()
        
        if current > expiry_date:
            return False, "License expired"
        
        days_left = (expiry_date - current).days
        return True, f"Valid: {days_left} days remaining"


# Usage
if __name__ == "__main__":
    verifier = TimeVerifier()
    is_valid, msg = verifier.verify_system_time()
    
    if is_valid:
        print(f"✅ {msg}")
    else:
        print(f"❌ {msg}")
        print("Please correct your system time to continue.")
```

---

## 🆕 [M7b] Extended Time Manipulation Defense (TimeValidator)

> [!IMPORTANT]
> Extends the multi-source `TimeVerifier` with **anchor-file monotonic checks** and **build-date validation**.
> Migrated from archive: detects clock rollback, forward manipulation, and time-before-build scenarios.

```python
import time
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

class TimeValidator:
    """
    Detect and prevent system clock manipulation.
    Uses multiple time sources + stored anchor for validation.
    """
    
    TIME_ANCHOR_FILE = Path.home() / ".veoauto" / ".time_anchor"
    MAX_BACKWARD_DRIFT = timedelta(hours=24)
    MAX_FORWARD_DRIFT = timedelta(days=30)
    
    def __init__(self, api_client):
        self.api = api_client
    
    def get_server_time(self) -> Optional[datetime]:
        """Get authoritative time from server"""
        try:
            response = self.api.get("/time")
            return datetime.fromisoformat(response.json()["timestamp"])
        except:
            return None
    
    def validate_system_time(self) -> dict:
        """
        Compare local time with server time and stored anchor.
        Detect clock rollback attempts.
        """
        local_time = datetime.now()
        
        # Check 1: Compare with server
        server_time = self.get_server_time()
        if server_time:
            drift = local_time - server_time
            
            if drift < -self.MAX_BACKWARD_DRIFT:
                return {
                    "valid": False,
                    "reason": "clock_rollback",
                    "message": "System clock appears to be set backwards"
                }
            
            if drift > self.MAX_FORWARD_DRIFT:
                return {
                    "valid": False,
                    "reason": "clock_forward",
                    "message": "System clock appears to be set far in the future"
                }
        
        # Check 2: Compare with stored anchor (monotonic check)
        anchor = self._load_anchor()
        if anchor:
            if local_time < anchor["timestamp"]:
                return {
                    "valid": False,
                    "reason": "time_went_backwards",
                    "message": "Time has gone backwards since last session"
                }
        
        # Check 3: Compare build date with system date
        build_date = datetime(2026, 1, 20)  # Set at compile time
        if local_time < build_date:
            return {
                "valid": False,
                "reason": "before_build_date",
                "message": "System time is before software build date"
            }
        
        # All checks passed - update anchor
        self._save_anchor(local_time, server_time)
        
        return {"valid": True}
    
    def _load_anchor(self) -> Optional[dict]:
        if not self.TIME_ANCHOR_FILE.exists():
            return None
        try:
            data = json.loads(self.TIME_ANCHOR_FILE.read_text())
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
            return data
        except:
            return None
    
    def _save_anchor(self, local_time: datetime, server_time: Optional[datetime]):
        data = {
            "timestamp": local_time.isoformat(),
            "server_time": server_time.isoformat() if server_time else None,
            "checksum": self._compute_checksum(local_time)
        }
        self.TIME_ANCHOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.TIME_ANCHOR_FILE.write_text(json.dumps(data))
    
    def _compute_checksum(self, dt: datetime) -> str:
        """Tamper-evident checksum"""
        secret = "veoauto_time_salt_2026"
        data = f"{dt.isoformat()}:{secret}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
```

### Time Validation Checks

| Check | Method | Detects |
|-------|--------|---------|
| Server time comparison | Compare local vs. server time | Forward/backward manipulation |
| Anchor file (monotonic) | Compare local vs. last saved | Clock rollback between sessions |
| Build date check | Compare local vs. compile date | Time set before app was built |

---

## 📋 Implementation Checklist

### [M6] Trial Reset Prevention
- [x] Multiple file markers (3 locations)
- [x] Windows Registry markers (2 locations)
- [x] Firebase markers (online backup)
- [x] Obfuscated timestamp encoding
- [x] Hidden file attributes

### [M7] Clock Manipulation Detection
- [x] Firebase server timestamp
- [x] WorldTimeAPI fallback
- [x] HTTP header time (Google/Cloudflare)
- [x] NTP fallback
- [x] Offline mode tolerance
- [x] Time offset caching

### [M7b] Extended Time Validation 🆕
- [x] Server time drift check (backward + forward)
- [x] Anchor file monotonic check
- [x] Build date validation
- [x] Tamper-evident checksum on anchor

---

## 🔗 Related Files

| File | Purpose |
|------|---------|
| `trial_protection.py` | Trial marker manager |
| `time_verification.py` | Clock manipulation detection |
| `time_validator.py` | Extended time validation (anchor + build date) |
| `license_client.py` | Integrate with license checking |

