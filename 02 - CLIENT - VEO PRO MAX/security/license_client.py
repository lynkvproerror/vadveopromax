"""
License Client v2.2 - Complete client-side license management for VEO App
Includes: Hardware fingerprint, Firebase validation, License storage, Trial protection, Role-based permissions

SECURITY UPDATES v2.2:
- Added UserRole support (Trial/Premium/Tester)
- Role-based feature visibility
- Multi-layer trial protection
- AES-256 encryption for local storage
- Clock manipulation detection

Roles:
- TRIAL (0): Limited (1 cookie, 2 threads, 10 prompts)
- PREMIUM (1): Unlimited
- TESTER (2): Unlimited + Dev Console + Beta features

Usage in VEO App:
    from license_client import LicenseClient, UserRole
    
    client = LicenseClient()
    machine_id = client.get_machine_id()  # Display to user
    result = client.activate("XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
    
    if client.is_licensed():
        tier = client.get_tier()   # "THREE_MONTHS", "ONE_YEAR", etc.
        role = client.get_role()   # 0, 1, or 2
        if client.can_see_dev_console():
            # Show Dev Console tab
"""

import hashlib
import platform
import subprocess
import json
import os
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass
from enum import Enum

# Cryptography for AES encryption
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Trial protection module
try:
    from security.trial_protection import TrialMarkerManager, TrialStatus
    TRIAL_PROTECTION_AVAILABLE = True
except ImportError:
    try:
        from trial_protection import TrialMarkerManager, TrialStatus
        TRIAL_PROTECTION_AVAILABLE = True
    except ImportError:
        TRIAL_PROTECTION_AVAILABLE = False

# Firebase REST Client (secure, no Admin SDK)
# firebase_admin is intentionally NOT imported here — client uses REST API only

# LicenseTier — single source: config.constants
# Import from canonical location; fallback for standalone usage
try:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from config.constants import LicenseTier
except ImportError:
    class LicenseTier(str, Enum):
        """VND Pricing Model - License Tiers (fallback)"""
        TRIAL = "TRIA"
        ONE_MONTH = "1M"
        THREE_MONTHS = "3M"
        SIX_MONTHS = "6M"
        ONE_YEAR = "1Y"
        LIFETIME = "LT"


from enum import IntEnum

class UserRole(IntEnum):
    """
    User permission roles for feature access control.
    
    TRIAL: Limited features (during trial period)
    PREMIUM: Full features (paid users)
    TESTER: Full features + Dev Console + Beta (trusted testers)
    """
    TRIAL = 0       # 1 cookie, 2 threads, 10 prompts
    PREMIUM = 1     # Unlimited
    TESTER = 2      # Unlimited + Dev Console + Beta features
    
    @property
    def can_see_dev_console(self) -> bool:
        return self == UserRole.TESTER
    
    @property
    def can_see_beta(self) -> bool:
        return self == UserRole.TESTER
    
    @property
    def can_see_advanced_settings(self) -> bool:
        return self == UserRole.TESTER


@dataclass
class LicenseInfo:
    """License information structure with role"""
    valid: bool
    tier: Optional[LicenseTier] = None
    role: UserRole = UserRole.TRIAL  # 🆕 User role
    expires: Optional[datetime] = None
    machine_id: Optional[str] = None
    error: Optional[str] = None
    limits_override: Optional[dict] = None  # _lim from Firebase


@dataclass
class UsageStats:
    """Usage statistics for license enforcement."""
    total_generations: int = 0
    today_generations: int = 0
    total_downloads: int = 0
    last_generation_at: Optional[datetime] = None
    last_reset_date: Optional[str] = None  # YYYY-MM-DD
class HardwareFingerprint:
    """
    Generate unique machine identifier from STABLE hardware sources.
    Prevents: HDD clone, HDD transfer to another PC, VM cloning.
    
    Components USED in fingerprint (stable):
    - CPU: Processor ID (unique per CPU)
    - Motherboard: Serial, UUID, BIOS serial
    - Disk: Serial number of boot drive
    
    Components EXCLUDED (too unstable for licensing):
    - Network: MAC addresses change with adapters
    - GPU: Users upgrade GPUs
    - RAM: Users upgrade RAM
    """
    
    @staticmethod
    def get_all_components() -> Dict[str, str]:
        """Collect all hardware identifiers"""
        components = {}
        
        if platform.system() != 'Windows':
            return {"error": "Only Windows supported"}
        
        # 1. CPU ID
        try:
            output = subprocess.check_output(
                'wmic cpu get processorid', shell=True, stderr=subprocess.DEVNULL
            ).decode()
            components['cpu_id'] = output.split('\n')[1].strip()
        except:
            components['cpu_id'] = 'unknown'
        
        # 2. Motherboard Serial
        try:
            output = subprocess.check_output(
                'wmic baseboard get serialnumber', shell=True, stderr=subprocess.DEVNULL
            ).decode()
            components['mb_serial'] = output.split('\n')[1].strip()
        except:
            components['mb_serial'] = 'unknown'
        
        # 3. Motherboard UUID
        try:
            output = subprocess.check_output(
                'wmic csproduct get uuid', shell=True, stderr=subprocess.DEVNULL
            ).decode()
            components['mb_uuid'] = output.split('\n')[1].strip()
        except:
            components['mb_uuid'] = 'unknown'
        
        # 4. BIOS Serial
        try:
            output = subprocess.check_output(
                'wmic bios get serialnumber', shell=True, stderr=subprocess.DEVNULL
            ).decode()
            components['bios_serial'] = output.split('\n')[1].strip()
        except:
            components['bios_serial'] = 'unknown'
        
        # 5. Boot Disk Serial
        try:
            output = subprocess.check_output(
                'wmic diskdrive where "Index=0" get serialnumber', 
                shell=True, stderr=subprocess.DEVNULL
            ).decode()
            components['disk_serial'] = output.split('\n')[1].strip()
        except:
            components['disk_serial'] = 'unknown'
        
        return components
    
    @staticmethod
    def get_machine_id() -> str:
        """Generate unique machine fingerprint hash"""
        components = HardwareFingerprint.get_all_components()
        
        # Combine STABLE components only
        combined = '|'.join([
            components.get('cpu_id', ''),
            components.get('mb_serial', ''),
            components.get('mb_uuid', ''),
            components.get('bios_serial', ''),
            components.get('disk_serial', ''),
        ])
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    @staticmethod
    def get_display_id() -> str:
        """Short 8-char ID for display to user"""
        machine_id = HardwareFingerprint.get_machine_id()
        return machine_id[:8].upper()


class LicenseStorage:
    """
    Local encrypted license storage with AES-256 + HMAC integrity.
    Falls back to XOR if cryptography not available.
    
    Security layers:
    - AES-256 encryption (machine-bound key)
    - HMAC-SHA256 signature (tamper detection)
    - Multiple fields in signature (hard to forge)
    """
    
    LICENSE_FILE = Path.home() / ".veoauto" / "license.dat"
    SALT = b"veo_license_salt_2026"  # Static salt (machine-bound key generated at runtime)
    # APP_VERSION: imported from canonical AppConstants to avoid mismatches
    try:
        from config.constants import AppConstants as _AC
        APP_VERSION = _AC.APP_VERSION
    except ImportError:
        APP_VERSION = "1.0.0"  # Fallback — keep in sync with constants.py
    
    @staticmethod
    def _derive_hmac_key(machine_id: str) -> bytes:
        """Derive HMAC key from machine ID — unique per machine, not hardcoded."""
        import hmac as hmac_lib
        return hmac_lib.new(
            b"veo_lic_derive_2026",
            (machine_id + "||HMAC_DERIVE").encode(),
            hashlib.sha256
        ).digest()
    
    
    def __init__(self, machine_id: str):
        self.LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.machine_id = machine_id
        self._hmac_key = self._derive_hmac_key(machine_id)
        self._fernet = self._create_fernet()
        if not self._fernet:
            import warnings
            warnings.warn("[Security] cryptography package missing — license storage DISABLED", stacklevel=2)
        # Cache hardware components for signature
        self._hw_components = HardwareFingerprint.get_all_components()
    
    def _create_fernet(self) -> Optional[object]:
        """Create Fernet cipher with machine-bound key."""
        if not CRYPTO_AVAILABLE:
            return None
        
        try:
            # Derive key from machine ID (machine-bound)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.SALT,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self.machine_id.encode()))
            return Fernet(key)
        except:
            return None
    
    def _generate_signature(self, data: dict) -> str:
        """
        Generate HMAC-SHA256 signature from MULTIPLE fields.
        Hard to forge because attacker must know:
        - All hardware components
        - Exact field order
        - HMAC secret (obfuscated in code)
        - Random nonce (unique per save)
        """
        import hmac as hmac_lib
        import secrets
        
        # Generate random nonce (stored in data, included in signature)
        nonce = data.get('_nonce') or secrets.token_hex(16)
        data['_nonce'] = nonce
        
        # Build signature payload with 12+ fields
        # Calculate data length EXCLUDING ALL signature meta-fields for consistency
        # CRITICAL: This list MUST match between save() and load() verification!
        _SIG_META = ('_sig', '_sig_version', '_nonce', '_app_version', '_last_known_time')
        data_for_len = {k: v for k, v in data.items() if k not in _SIG_META}
        sig_parts = [
            # === CORE LICENSE DATA ===
            str(data.get('key', '')),
            str(data.get('tier', '')),
            str(data.get('role', '')),
            str(data.get('expires', '')),
            str(data.get('last_validated', '')),
            
            # === HARDWARE BINDING ===
            self.machine_id,
            self._hw_components.get('cpu_id', ''),
            self._hw_components.get('mb_serial', ''),
            self._hw_components.get('disk_serial', ''),
            self._hw_components.get('bios_serial', ''),
            
            # === ANTI-TAMPER ===
            nonce,                        # Random per save
            "VEO_SIG_V3",                 # Static marker (version-agnostic)
            str(len(str(data_for_len))),  # Data length (excluding meta-fields)
            
            # === OBFUSCATION ===
            "v3o_l1c_s1g",               # Static marker
        ]
        
        # Join with separator that's unlikely to appear in data
        payload = "||VEO||".join(sig_parts)
        
        # Generate HMAC-SHA256
        signature = hmac_lib.new(
            self._hmac_key,
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _verify_signature(self, data: dict) -> bool:
        """Verify HMAC signature. Returns False if tampered."""
        stored_sig = data.get('_sig')
        if not stored_sig:
            return False  # No signature = tampered or old format
        
        # Regenerate signature (nonce already in data)
        expected_sig = self._generate_signature(data)
        
        # Constant-time comparison
        import hmac as hmac_lib
        return hmac_lib.compare_digest(stored_sig, expected_sig)
    
    def save(self, license_data: dict):
        """Save license data locally (AES-256 encrypted + HMAC signed)."""
        # Add signature BEFORE encryption
        license_data['_sig'] = self._generate_signature(license_data)
        license_data['_sig_version'] = 3  # v3: version-agnostic signature
        license_data['_app_version'] = self.APP_VERSION  # Informational only
        
        data_str = json.dumps(license_data, default=str)
        
        if self._fernet:
            encrypted = self._fernet.encrypt(data_str.encode())
        else:
            # No fallback — cryptography package REQUIRED
            raise RuntimeError("Cannot save license: cryptography package not installed")
        
        self.LICENSE_FILE.write_bytes(encrypted)
    
    def load(self) -> Optional[dict]:
        """Load license data, verify signature, and auto-migrate old formats."""
        if not self.LICENSE_FILE.exists():
            return None
        
        try:
            encrypted = self.LICENSE_FILE.read_bytes()
            
            if self._fernet:
                decrypted = self._fernet.decrypt(encrypted)
            else:
                # No fallback — reject without cryptography
                return None
            
            data = json.loads(decrypted.decode())
            
            # 🔒 VERIFY SIGNATURE
            if self._verify_signature(data):
                return data
            
            # 🔄 MIGRATION: old sig_version (v2) used APP_VERSION in signature
            # → fails when app upgrades. Try to migrate by re-signing.
            old_version = data.get('_sig_version', 0)
            if old_version <= 2 and data.get('key'):
                log.info(f"[LicenseStorage] Migrating license from sig v{old_version} → v3")
                # Re-sign with new version-agnostic format
                data.pop('_sig', None)
                data.pop('_nonce', None)
                self.save(data)  # save() uses v3 signature
                log.info("[LicenseStorage] ✅ License migrated successfully")
                return data
            
            # Signature invalid and not migratable → tampered
            self.clear()
            return None
        except:
            return None
    
    def clear(self):
        """Clear local license data."""
        if self.LICENSE_FILE.exists():
            self.LICENSE_FILE.unlink()
    
    # XOR fallback REMOVED for security — cryptography package required


class LicenseClient:
    """
    Complete client-side license management v2.2.
    
    Features:
    - Hardware fingerprint generation
    - Local license caching (AES-256 encrypted + HMAC signed)
    - Online validation with Firebase
    - Trial requires KEY (no automatic trial)
    - Multi-layer trial protection
    - Clock manipulation detection
    - HMAC signature verification
    """
    
    COLLECTION = "_lic"
    TRIAL_DAYS = 3
    OFFLINE_GRACE_DAYS = 7  # 🔒 Offline grace period
    
    def __init__(self):
        self.machine_id = HardwareFingerprint.get_machine_id()
        self.display_id = HardwareFingerprint.get_display_id()
        self.storage = LicenseStorage(self.machine_id)  # Pass machine_id for AES key
        self.db = None
        
        # Trial protection
        self.trial_manager = None
        if TRIAL_PROTECTION_AVAILABLE:
            self.trial_manager = TrialMarkerManager(self.machine_id)
        
        self._cached_license: Optional[dict] = None
        self._last_known_time: Optional[datetime] = None  # 🔒 Clock detection
        self._validate_cache: Optional['LicenseInfo'] = None  # Validate result cache
        self._validate_cache_time: Optional[datetime] = None   # Cache timestamp
        self._VALIDATE_CACHE_TTL = 60  # seconds
        self._usage = UsageStats()
        self._usage_file = Path.home() / ".veoauto" / "usage.json"
        self._load_usage()
        self._init_firebase()
    
    @staticmethod
    def _safe_parse_dt(dt_str: str, default: str = '2000-01-01') -> 'datetime':
        """Parse ISO datetime string → naive datetime (strips timezone if present).
        
        Prevents 'can't compare offset-naive and offset-aware' errors.
        Server may store timezone-aware strings; client uses naive datetimes.
        """
        try:
            raw = str(dt_str).replace('Z', '+00:00') if dt_str else default
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            return datetime.fromisoformat(default)
    
    def _detect_clock_tampering(self, cached: dict) -> bool:
        """
        🔒 Detect if system clock has been rolled back.
        Returns True if tampering detected.
        """
        now = datetime.now()
        
        # Check 1: last_validated should be in the past
        last_validated_str = cached.get('last_validated')
        if last_validated_str:
            try:
                last_validated = self._safe_parse_dt(last_validated_str)
                if now < last_validated:
                    # Time went backwards! Clock tampering detected.
                    return True
            except:
                pass
        
        # Check 2: activation_time should be in the past
        activation_str = cached.get('activation_time')
        if activation_str:
            try:
                activation = self._safe_parse_dt(activation_str)
                if now < activation:
                    return True
            except:
                pass
        
        # Check 3: Compare with stored "last_known_time"
        last_known_str = cached.get('_last_known_time')
        if last_known_str:
            try:
                last_known = self._safe_parse_dt(last_known_str)
                # Allow 1 hour backwards (daylight saving, manual adjustment)
                if now < last_known - timedelta(hours=1):
                    return True
            except:
                pass
        
        return False
    
    def _init_firebase(self):
        """
        Initialize Firebase connection.
        
        Uses absolute imports (security.xxx) which work in:
        - Dev mode: when cwd is project root
        - Compiled mode: Nuitka compiles security/ as a package
        Fallback to bare imports for legacy compatibility.
        """
        import logging
        _flog = logging.getLogger("veo.license")
        
        # === Step 1: Load encrypted API keys ===
        keys_loaded = False
        try:
            try:
                from security._encrypted_api_keys import set_runtime_keys
            except ImportError:
                from _encrypted_api_keys import set_runtime_keys
            keys_loaded = set_runtime_keys()
            _flog.info(f"[LICENSE] API keys loaded: {keys_loaded}")
        except Exception as e:
            _flog.error(f"[LICENSE] Failed to load API keys: {type(e).__name__}: {e}")
        
        if not keys_loaded:
            _flog.warning("[LICENSE] ⚠️ No Firebase API keys available — license validation limited to cache")
        
        # === Step 2: Create REST client ===
        try:
            try:
                from security.firebase_rest_client import FirebaseRESTClient
            except ImportError:
                from firebase_rest_client import FirebaseRESTClient
            
            self._rest_client = FirebaseRESTClient()
            self._use_rest = True
            self._which_db = "rest_api"
            _flog.info("[LICENSE] ✅ Firebase REST client initialized")
            return
        except ImportError as e:
            _flog.error(f"[LICENSE] REST client import failed: {e}")
            self._use_rest = False
        except Exception as e:
            _flog.error(f"[LICENSE] REST client init failed: {type(e).__name__}: {e}")
            self._use_rest = False
        
        # No connection available
        _flog.warning("[LICENSE] ⚠️ Firebase not available — offline mode only")
        self._use_rest = False
    
    # =====================
    # PUBLIC API
    # =====================
    
    def get_machine_id(self) -> str:
        """Get full machine ID hash (for internal use)"""
        return self.machine_id
    
    def get_display_machine_id(self) -> str:
        """Get short display ID (for user to see)"""
        return self.display_id
    
    def get_client_name(self) -> str:
        """Get client name from cached license data (loaded from Firebase _cn field)."""
        try:
            cached = self.storage.load()
            if cached:
                return cached.get('client_name', '')
        except Exception:
            pass
        return ""
    
    def activate(self, license_key: str) -> LicenseInfo:
        """
        Activate a license key.
        
        Flow:
        1. Validate format locally
        2. Validate via REST API (cross-check primary + backup Firebase)
        3. Save locally on success
        
        Args:
            license_key: The license key (XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX or TRIAL-XXXX-XXXX-XXXX)
            
        Returns:
            LicenseInfo with activation result
        """
        # Validate format locally first
        if not self._validate_key_format(license_key):
            return LicenseInfo(valid=False, error="Invalid key format")
        
        # Handle TRIAL keys separately
        if license_key.upper().startswith("TRIAL-"):
            return self.activate_trial(license_key)
        
        # Try online activation via REST client
        if hasattr(self, '_use_rest') and self._use_rest and hasattr(self, '_rest_client'):
            return self._activate_with_rest(license_key)
        
        # Fallback: create REST client directly
        try:
            try:
                from security._encrypted_api_keys import set_runtime_keys
            except ImportError:
                from _encrypted_api_keys import set_runtime_keys
            set_runtime_keys()
            try:
                from security.firebase_rest_client import FirebaseRESTClient
            except ImportError:
                from firebase_rest_client import FirebaseRESTClient
            self._rest_client = FirebaseRESTClient()
            self._use_rest = True
            return self._activate_with_rest(license_key)
        except Exception as e:
            return LicenseInfo(valid=False, error=f"Firebase connection unavailable: {str(e)[:40]}")
    
    def _activate_with_rest(self, license_key: str) -> LicenseInfo:
        """
        Activate license via REST API (no Admin SDK needed).
        
        Uses validate_with_crosscheck for dual-Firebase validation,
        then saves locally on success.
        """
        try:
            is_valid, status, data = self._rest_client.validate_with_crosscheck(
                license_key,
                self.machine_id
            )
            
            if not is_valid:
                error_messages = {
                    "LICENSE_NOT_FOUND": "License key not found",
                    "LICENSE_DELETED_STALE_BACKUP": "License key deleted from server",
                    "MACHINE_MISMATCH": "License bound to different machine",
                    "LICENSE_REVOKED": "License has been revoked",
                    "CROSS_VALIDATION_FAILED": "Security validation failed",
                    "LICENSE_EXPIRED": "License expired",
                }
                return LicenseInfo(
                    valid=False,
                    error=error_messages.get(status, f"Activation failed: {status}")
                )
            
            # Extract license data (map both naming conventions)
            tier_code = data.get('tier') or data.get('_t', 'TRIA')
            role_code = data.get('role') or data.get('_role', 1)
            expires_str = data.get('expires') or data.get('_exp', '2100-01-01')
            client_name = data.get('client_name') or data.get('_cn', '')
            
            try:
                if isinstance(expires_str, str):
                    raw = expires_str.replace('Z', '+00:00')
                    expires = datetime.fromisoformat(raw)
                    # Convert to local naive datetime for consistent comparison
                    if expires.tzinfo is not None:
                        expires = expires.replace(tzinfo=None)
                elif hasattr(expires_str, 'isoformat'):
                    expires = expires_str if isinstance(expires_str, datetime) else datetime.now() + timedelta(days=365)
                else:
                    expires = datetime.now() + timedelta(days=365)
            except Exception:
                expires = datetime.now() + timedelta(days=365)
            
            # 🔒 LIFETIME ROLLING EXPIRY: use 90-day window instead of far-future
            if tier_code == 'LT':
                expires = datetime.now() + timedelta(days=90)
            
            # Save locally (AES-256 encrypted + HMAC signed)
            save_data = {
                'key': license_key,
                'tier': tier_code,
                'role': role_code,
                'machine_id': self.machine_id,
                'expires': expires.isoformat(),
                'last_verified': datetime.now().isoformat(),
                '_last_known_time': datetime.now().isoformat(),
                '_validation_source': status,
                'client_name': client_name,
            }
            # Cache _lim (Level 1 security)
            server_lim = data.get('_lim')
            if server_lim:
                save_data['_lim'] = server_lim
            self.storage.save(save_data)
            self._invalidate_validate_cache()  # Force fresh validate()
            
            tier = self._tier_from_code(tier_code)
            role = UserRole(role_code)
            
            return LicenseInfo(
                valid=True,
                tier=tier,
                role=role,
                expires=expires,
                machine_id=self.machine_id,
                limits_override=server_lim
            )
            
        except ConnectionError as e:
            return LicenseInfo(valid=False, error=f"Network error: {str(e)[:40]}")
        except Exception as e:
            return LicenseInfo(valid=False, error=f"Activation failed: {str(e)}")
    
    def validate(self) -> LicenseInfo:
        """
        Validate current license status.
        Called on app startup and periodically.
        
        Uses cross-validation with dual-Firebase when REST client available.
        Uses in-memory cache (60s TTL) to avoid repeated file I/O.
        """
        # Check in-memory cache first (avoid repeated file I/O + crypto)
        if (self._validate_cache is not None 
            and self._validate_cache_time is not None
            and (datetime.now() - self._validate_cache_time).total_seconds() < self._VALIDATE_CACHE_TTL):
            return self._validate_cache
        
        result = self._validate_uncached()
        self._validate_cache = result
        self._validate_cache_time = datetime.now()
        return result
    
    def _invalidate_validate_cache(self):
        """Clear validate cache (call after activate/deactivate)."""
        self._validate_cache = None
        self._validate_cache_time = None
    
    def validate_online_now(self) -> 'LicenseInfo':
        """
        Force immediate online validation (bypass 5-min interval).
        Use at app startup to ensure key still exists on server.
        """
        # Clear in-memory cache
        self._invalidate_validate_cache()
        
        # Reset last_verified to force online check
        cached = self.storage.load()
        if cached:
            cached['last_verified'] = '2000-01-01T00:00:00'  # Force expired
            cached['_last_known_time'] = datetime.now().isoformat()  # Prevent false clock tampering
            self.storage.save(cached)
        
        # Now validate() will trigger online check immediately
        return self.validate()
    
    def _validate_uncached(self) -> LicenseInfo:
        """Actual validation logic (no cache)."""
        # Load cached license
        cached = self.storage.load()
        
        if not cached:
            return self._check_trial()
        
        # ✅ Trial cache: always re-query server for latest expires_at
        if cached.get('_is_trial') or str(cached.get('key', '')).startswith('TRIAL-'):
            return self._check_trial()
        
        # 🔒 CLOCK TAMPERING CHECK (before anything else!)
        if self._detect_clock_tampering(cached):
            self.storage.clear()  # Clear tampered cache
            return LicenseInfo(valid=False, error="Clock manipulation detected. Re-activate required.")
        
        # Check machine binding
        if cached.get('machine_id') != self.machine_id:
            return LicenseInfo(valid=False, error="License bound to different machine")
        
        # Check local expiry (Tester role=2 bypasses expiry)
        role_code = cached.get('role', 1)
        expires = self._safe_parse_dt(cached.get('expires', '2000-01-01'))
        if role_code != 2 and expires < datetime.now():
            return LicenseInfo(valid=False, error="License expired")
        
        # 🔒 ONLINE-FIRST VALIDATION
        # Try online every 5 min — if invalid, revoke + clear cache
        # If offline (network error), just use local cache (expires naturally)
        last_check = self._safe_parse_dt(cached.get('last_verified', '2000-01-01'))
        since_last_check = (datetime.now() - last_check).total_seconds()
        
        ONLINE_CHECK_INTERVAL = 300  # 5 minutes
        
        if since_last_check > ONLINE_CHECK_INTERVAL:
            online_result = None
            _use = getattr(self, '_use_rest', False)
            _has_rc = hasattr(self, '_rest_client') and self._rest_client is not None
            _has_db = bool(self.db)
            print(f"[LICENSE-DEBUG] _use_rest={_use}, _has_rest_client={_has_rc}, _has_db={_has_db}")
            
            if _use and _has_rc:
                try:
                    online_result = self._validate_with_rest(cached.get('key'))
                    print(f"[LICENSE-DEBUG] REST result: valid={online_result.valid}, error={getattr(online_result, 'error', None)}")
                except Exception as e:
                    print(f"[LICENSE-DEBUG] REST exception: {type(e).__name__}: {e}")
                    pass  # Network error → use cache
            elif _has_db:
                try:
                    online_result = self._validate_online(cached.get('key'))
                    print(f"[LICENSE-DEBUG] SDK result: valid={online_result.valid}")
                except Exception as e:
                    print(f"[LICENSE-DEBUG] SDK exception: {e}")
                    pass
            else:
                print("[LICENSE-DEBUG] ⚠️ NO online check method available — using cache only!")
            
            if online_result is not None:
                # If server says invalid → clear local cache!
                if not online_result.valid:
                    print(f"[LICENSE-DEBUG] ⛔ Clearing cache — server says invalid")
                    self.storage.clear()
                    self._invalidate_validate_cache()
                return online_result
        else:
            print(f"[LICENSE-DEBUG] Online check skipped — last check {since_last_check:.0f}s ago (interval={ONLINE_CHECK_INTERVAL}s)")
        
        # 🔒 Update last known time (for next clock check)
        cached['_last_known_time'] = datetime.now().isoformat()
        
        # 🔒 LIFETIME ROLLING EXPIRY: auto-extend 90 days on each successful cache read
        tier_code = cached.get('tier', '')
        if tier_code == 'LT':
            expires = datetime.now() + timedelta(days=90)
            cached['expires'] = expires.isoformat()
        
        self.storage.save(cached)
        
        # Valid from cache
        tier = self._tier_from_code(tier_code)
        role = UserRole(cached.get('role', 1))  # 🆕 Default: PREMIUM
        return LicenseInfo(
            valid=True,
            tier=tier,
            role=role,  # 🆕
            expires=self._safe_parse_dt(cached.get('expires', '2000-01-01')),
            machine_id=self.machine_id,
            limits_override=cached.get('_lim')
        )
    
    def _validate_with_rest(self, license_key: str) -> LicenseInfo:
        """
        Validate using REST client with dual-Firebase cross-validation.
        
        Raises ConnectionError if network is down (for cache fallback).
        """
        if not hasattr(self, '_rest_client') or not self._rest_client:
            raise ConnectionError("REST client not available")
        
        # Let ConnectionError propagate to caller for cache fallback
        is_valid, status, data = self._rest_client.validate_with_crosscheck(
            license_key, 
            self.machine_id
        )
        
        if not is_valid:
            error_messages = {
                "LICENSE_NOT_FOUND": "License key not found",
                "LICENSE_DELETED_STALE_BACKUP": "License key deleted from server",
                "MACHINE_MISMATCH": "License bound to different machine",
                "LICENSE_REVOKED": "License has been revoked",
                "CROSS_VALIDATION_FAILED": "Security validation failed",
                "LICENSE_EXPIRED": "License expired"
            }
            return LicenseInfo(
                valid=False, 
                error=error_messages.get(status, f"Validation failed: {status}")
            )
        
        # Update cache with validated data (SYNC tier/role from server!)
        cached = self.storage.load() or {}
        cached['last_verified'] = datetime.now().isoformat()
        cached['_last_known_time'] = datetime.now().isoformat()
        cached['_validation_source'] = status
        # Sync tier/role/name from server → cache
        cached['tier'] = data.get('_t') or data.get('tier') or cached.get('tier')
        cached['role'] = data.get('_role') or data.get('role') or cached.get('role')
        # Sync client_name from server (so title bar shows subscriber name)
        server_name = data.get('client_name') or data.get('_cn', '')
        if server_name:
            cached['client_name'] = server_name
        # Cache _lim (Level 1 security)
        server_lim = data.get('_lim')
        if server_lim:
            cached['_lim'] = server_lim
        
        # 🔒 LT ROLLING: client controls expiry, NOT server
        tier_code = cached.get('tier', '')
        if tier_code == 'LT':
            # Always set 90 days from now (ignore server _exp)
            cached['expires'] = (datetime.now() + timedelta(days=90)).isoformat()
        else:
            # Non-LT: sync expiry from server
            server_exp = data.get('_exp') or data.get('expires')
            if server_exp:
                if hasattr(server_exp, 'isoformat'):
                    cached['expires'] = server_exp.isoformat()
                elif isinstance(server_exp, str):
                    cached['expires'] = server_exp
        self.storage.save(cached)
        
        tier = self._tier_from_code(data.get('_t') or data.get('tier'))
        role = UserRole(data.get('_role') or data.get('role', 1))
        expires_str = data.get('expires') or data.get('_exp', '2100-01-01')
        
        try:
            if isinstance(expires_str, str):
                raw = expires_str.replace('Z', '+00:00')
                expires = datetime.fromisoformat(raw)
                if expires.tzinfo is not None:
                    expires = expires.replace(tzinfo=None)
            elif hasattr(expires_str, 'isoformat'):
                expires = expires_str if isinstance(expires_str, datetime) else datetime.now() + timedelta(days=365)
            else:
                expires = datetime.now() + timedelta(days=365)
        except:
            expires = datetime.now() + timedelta(days=365)
        
        return LicenseInfo(
            valid=True,
            tier=tier,
            role=role,
            expires=expires,
            machine_id=self.machine_id,
            limits_override=server_lim
        )
    
    def is_licensed(self) -> bool:
        """Quick check if license is valid"""
        return self.validate().valid
    
    def get_tier(self) -> Optional[str]:
        """Get current license tier name"""
        info = self.validate()
        return info.tier.name if info.tier else None
    
    def get_role(self) -> UserRole:
        """Get current user role from validated license"""
        info = self.validate()
        return info.role if info.valid else UserRole.TRIAL
    
    def can_see_dev_console(self) -> bool:
        """Check if user can see Dev Console 🆕"""
        return self.get_role() == UserRole.TESTER
    
    def can_see_beta(self) -> bool:
        """Check if user can see Beta features 🆕"""
        return self.get_role() == UserRole.TESTER
    
    def can_see_advanced_settings(self) -> bool:
        """Check if user can see Advanced Settings 🆕"""
        return self.get_role() == UserRole.TESTER
    
    def deactivate(self):
        """Deactivate (clear) local license"""
        self.storage.clear()
        self._cached_license = None
        self._invalidate_validate_cache()
    
    # =====================
    # INTERNAL METHODS
    # =====================
    
    # ── Checksum salt (obfuscated, split) ──
    _CK_P1 = b"V3O_PUB"
    _CK_P2 = b"_CK_2026"
    
    @classmethod
    def _get_checksum_salt(cls) -> bytes:
        return cls._CK_P1 + cls._CK_P2
    
    @staticmethod
    def _compute_public_checksum(core_hex: str) -> str:
        """Compute 4-char hex checksum from core key hex (same as admin keygen)."""
        payload = core_hex.upper().encode() + LicenseClient._get_checksum_salt()
        return hashlib.sha256(payload).hexdigest()[:4].upper()
    
    def _validate_key_format(self, key: str) -> bool:
        """
        Validate key format locally + checksum verification.
        
        v2.5 format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-CSUM (9 segments)
        v2.0 format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX (8 segments, legacy)
        Trial format: TRIAL-XXXX-XXXX-XXXX (4 segments)
        """
        parts = key.upper().replace(" ", "").split("-")
        
        # New format with checksum: 9 segments of 4 hex chars
        if len(parts) == 9:
            # Check all parts are 4 hex chars
            if not all(len(p) == 4 and all(c in '0123456789ABCDEF' for c in p) for p in parts):
                return False
            # Verify public checksum (9th segment)
            core_hex = "".join(parts[:8])
            expected = self._compute_public_checksum(core_hex)
            return parts[8] == expected
        
        # Legacy format: 8 segments of 4 hex chars (backward compatible)
        if len(parts) == 8:
            return all(len(p) == 4 and all(c in '0123456789ABCDEF' for c in p) for p in parts)
        
        # Trial format: TRIAL-XXXX-XXXX-XXXX (hex check)
        if len(parts) == 4 and parts[0] == "TRIAL":
            return all(len(p) == 4 and all(c in '0123456789ABCDEF' for c in p) for p in parts[1:])
        
        return False
    
    def _activate_online(self, key: str) -> LicenseInfo:
        """Activate license key via Firebase"""
        try:
            doc_ref = self.db.collection(self.COLLECTION).document(key)
            doc = doc_ref.get()
            
            if not doc.exists:
                return LicenseInfo(valid=False, error="Invalid license key")
            
            data = doc.to_dict()
            
            # Check status
            if data.get('_st') == 'r':
                return LicenseInfo(valid=False, error="License revoked")
            
            # Check if already bound to different machine
            bound_machine = data.get('_mid')
            if bound_machine and bound_machine != self.machine_id:
                return LicenseInfo(valid=False, error="License bound to different machine")
            
            # Check expiry
            exp = data.get('_exp')
            if exp and exp.timestamp() < datetime.now().timestamp():
                return LicenseInfo(valid=False, error="License expired")
            
            # Bind to this machine if not already
            if not bound_machine:
                doc_ref.update({
                    '_mid': self.machine_id,
                    '_st': 'a',  # active
                    '_act': firestore.SERVER_TIMESTAMP
                })
            
            # Save locally with role 🆕
            tier_code = data.get('_t', 'TRIA')
            role_code = data.get('_role', 1)  # 🆕 Default: PREMIUM
            expires = exp.isoformat() if exp else None
            
            self.storage.save({
                'key': key,
                'tier': tier_code,
                'role': role_code,  # 🆕
                'machine_id': self.machine_id,
                'expires': expires,
                'last_verified': datetime.now().isoformat()
            })
            
            tier = self._tier_from_code(tier_code)
            role = UserRole(role_code)  # 🆕
            return LicenseInfo(
                valid=True,
                tier=tier,
                role=role,  # 🆕
                expires=exp,
                machine_id=self.machine_id
            )
            
        except Exception as e:
            return LicenseInfo(valid=False, error=f"Activation failed: {str(e)}")
    
    def _validate_online(self, key: str) -> LicenseInfo:
        """Validate existing license online"""
        if not key or not self.db:
            return LicenseInfo(valid=False, error="Online validation unavailable")
        
        try:
            doc = self.db.collection(self.COLLECTION).document(key).get()
            
            if not doc.exists:
                return LicenseInfo(valid=False, error="License not found")
            
            data = doc.to_dict()
            
            if data.get('_st') == 'r':
                self.storage.clear()
                return LicenseInfo(valid=False, error="License revoked")
            
            if data.get('_mid') != self.machine_id:
                self.storage.clear()
                return LicenseInfo(valid=False, error="License transferred to another machine")
            
            exp = data.get('_exp')
            if exp and exp.timestamp() < datetime.now().timestamp():
                return LicenseInfo(valid=False, error="License expired")
            
            # Update last verified
            cached = self.storage.load()
            if cached:
                cached['last_verified'] = datetime.now().isoformat()
                self.storage.save(cached)
            
            tier = self._tier_from_code(data.get('_t'))
            return LicenseInfo(valid=True, tier=tier, expires=exp, machine_id=self.machine_id)
            
        except:
            # Network error - use cached
            return self.validate()
    
    def _check_trial(self) -> LicenseInfo:
        """
        Check trial status — SERVER-AUTHORITATIVE.
        
        Priority:
        1. Query Firebase _trials/{MID} for server-side trial record
        2. Falls back to local TrialMarkerManager ONLY if network unavailable
        """
        # ── Step 1: Query Firebase (authoritative) ──
        try:
            rest_client = getattr(self, '_rest_client', None)
            if rest_client and hasattr(rest_client, 'check_trial_status'):
                server_trial = rest_client.check_trial_status(self.machine_id)
                
                if server_trial.get("exists"):
                    status = server_trial.get("status", "unknown")
                    
                    if status == "revoked":
                        # Admin revoked trial → block
                        return LicenseInfo(
                            valid=False,
                            error="Trial đã bị thu hồi bởi admin"
                        )
                    
                    if status == "upgraded":
                        # Trial upgraded to paid → try auto-restore key from _mid_to_key
                        restored = self._try_restore_by_mid()
                        if restored:
                            return restored
                        # Auto-restore failed (no _mid_to_key entry)
                        # → Let the user enter key manually via activation dialog
                        # Do NOT block with hard error — user may have a valid _lic key
                        return LicenseInfo(
                            valid=False,
                            tier="TRIAL",
                            error="ENTER_KEY"
                        )
                    
                    if status == "expired":
                        return LicenseInfo(
                            valid=False,
                            error=server_trial.get("error", "Trial đã hết hạn")
                        )
                    
                    if status == "active":
                        # Active trial — use server expiry time
                        expires_str = server_trial.get("expires_at", "")
                        if expires_str:
                            try:
                                expires = self._safe_parse_dt(expires_str)
                                if datetime.now() > expires:
                                    self.storage.clear()  # Clear stale trial cache
                                    return LicenseInfo(
                                        valid=False,
                                        error="Bản dùng thử đã hết hạn"
                                    )
                                
                                # ✅ Cache trial data to license.dat (sync server → local)
                                self.storage.save({
                                    'key': f'TRIAL-{self.machine_id[:12]}',
                                    'tier': 'TRIA',
                                    'role': 0,
                                    'machine_id': self.machine_id,
                                    'expires': expires_str,
                                    'last_verified': datetime.now().isoformat(),
                                    '_last_known_time': datetime.now().isoformat(),
                                    '_is_trial': True,
                                    '_validation_source': 'server_trial',
                                })
                                
                                # Layer 3: Reconcile daily usage from server
                                self.reconcile_usage_from_server(server_trial)
                                
                                return LicenseInfo(
                                    valid=True,
                                    tier=LicenseTier.TRIAL,
                                    expires=expires,
                                    machine_id=self.machine_id
                                )
                            except Exception:
                                pass
                        
                        # Active but no expiry → valid
                        return LicenseInfo(
                            valid=True,
                            tier=LicenseTier.TRIAL,
                            machine_id=self.machine_id
                        )
                
                # No trial on server → try auto-restore paid key
                restored = self._try_restore_by_mid()
                if restored:
                    return restored
                return LicenseInfo(
                    valid=False,
                    error="License key required. Contact admin for trial key."
                )
                
        except Exception as e:
            print(f"[LICENSE-DEBUG] Firebase trial check failed: {e}")
            # Network error → fall through to local check
        
        # ── Step 2: Fallback to local TrialMarkerManager (offline only) ──
        if self.trial_manager:
            status = self.trial_manager.validate_trial()
            
            if status.valid:
                return LicenseInfo(
                    valid=True,
                    tier=LicenseTier.TRIAL,
                    expires=status.expires
                )
        
        # ── Step 3: Try auto-restore paid key by MID ──
        restored = self._try_restore_by_mid()
        if restored:
            return restored
        
        return LicenseInfo(
            valid=False,
            error="License key required. Contact admin for trial key."
        )
    
    def _try_restore_by_mid(self):
        """
        Try to auto-restore license from Firebase by Machine ID.
        
        Searches _lic collection for active key bound to this MID.
        If found: restores local cache (license.dat) and returns valid LicenseInfo.
        If not found: returns None.
        """
        try:
            rest_client = getattr(self, '_rest_client', None)
            if not rest_client or not hasattr(rest_client, 'query_license_by_mid'):
                return None
            
            result = rest_client.query_license_by_mid(self.machine_id)
            if not result.get("found"):
                return None
            
            key = result.get("key", "")
            tier_code = result.get("tier", "")
            role = result.get("role", 1)
            expires_str = result.get("expires", "")
            
            print(f"[LICENSE] Auto-restore: found key {key[:8]}... tier={tier_code}")
            
            # Restore local cache
            try:
                expires = datetime.fromisoformat(expires_str) if expires_str else datetime.now() + timedelta(days=30)
            except Exception:
                expires = datetime.now() + timedelta(days=30)
            
            cache_data = {
                'key': key,
                'tier': tier_code,
                'role': role,
                'expires': expires.isoformat(),
                'machine_id': self.machine_id,
                'last_verified': datetime.now().isoformat(),
            }
            self.storage.save(cache_data)
            
            tier = self._tier_from_code(tier_code)
            return LicenseInfo(
                valid=True,
                tier=tier,
                role=UserRole(role),
                expires=expires,
                machine_id=self.machine_id
            )
        except Exception as e:
            print(f"[LICENSE-DEBUG] Auto-restore failed: {e}")
            return None
    
    def activate_trial(self, trial_key: str) -> LicenseInfo:
        """
        Activate a trial key (TRIAL-XXXX-XXXX-XXXX).
        
        Trial keys are generated by admin and can only be used once per machine.
        """
        # Validate format
        if not trial_key.upper().startswith("TRIAL-"):
            return LicenseInfo(valid=False, error="Invalid trial key format")
        
        # Check if trial manager available
        if not self.trial_manager:
            return LicenseInfo(valid=False, error="Trial system not available")
        
        # Check if already has trial
        existing = self.trial_manager.get_trial_start()
        if existing:
            return LicenseInfo(valid=False, error="Trial already used on this machine")
        
        # TODO: Validate trial key against Firebase
        # For now, accept any TRIAL-XXXX-XXXX-XXXX format
        
        # Start trial with multi-layer protection
        status = self.trial_manager.start_trial()
        
        if status.valid:
            return LicenseInfo(
                valid=True,
                tier=LicenseTier.TRIAL,
                expires=status.expires
            )
        else:
            return LicenseInfo(valid=False, error=status.error)
    
    def _tier_from_code(self, code: str) -> Optional[LicenseTier]:
        """Convert tier code to enum"""
        for tier in LicenseTier:
            if tier.value == code:
                return tier
        return None
    
    # =====================
    # USAGE TRACKING
    # =====================
    
    @property
    def usage(self) -> UsageStats:
        """Get current usage stats."""
        return self._usage
    
    def _load_usage(self):
        """Load usage stats from file with HMAC verification."""
        if not self._usage_file.exists():
            return
        try:
            data = json.loads(self._usage_file.read_text())
            
            # Layer 1: Verify HMAC signature
            stored_sig = data.get("_sig", "")
            if stored_sig:
                expected_sig = self._compute_usage_hmac(data)
                if stored_sig != expected_sig:
                    # TAMPER DETECTED — set count to daily limit
                    print("[LICENSE] ⚠️ Usage file tampered — resetting to limit")
                    self._usage = UsageStats()
                    self._usage.today_generations = 100  # Assume max reached
                    self._usage.last_reset_date = datetime.now().strftime("%Y-%m-%d")
                    self._save_usage()
                    return
            
            self._usage = UsageStats(
                total_generations=data.get("total_generations", 0),
                today_generations=data.get("today_generations", 0),
                total_downloads=data.get("total_downloads", 0),
                last_reset_date=data.get("last_reset_date"),
            )
            # Reset daily counter if new day
            today = datetime.now().strftime("%Y-%m-%d")
            if self._usage.last_reset_date != today:
                self._usage.today_generations = 0
                self._usage.last_reset_date = today
                self._save_usage()  # Re-sign with new date
        except Exception:
            self._usage = UsageStats()
    
    def _compute_usage_hmac(self, data: dict) -> str:
        """Compute HMAC for usage data (hardware-bound)."""
        import hmac as _hmac, hashlib
        # Key = SHA256(machine_id + salt)
        key_material = (self.machine_id + "_USAGE_ANTI_TAMPER_v1").encode()
        key = hashlib.sha256(key_material).digest()
        
        # Message = date + today_gen + total_gen + total_dl
        msg = (
            f"{data.get('last_reset_date', '')}"
            f"|{data.get('today_generations', 0)}"
            f"|{data.get('total_generations', 0)}"
            f"|{data.get('total_downloads', 0)}"
        ).encode()
        
        return _hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]
    
    def _save_usage(self):
        """Save usage stats to file with HMAC signature."""
        data = {
            "total_generations": self._usage.total_generations,
            "today_generations": self._usage.today_generations,
            "total_downloads": self._usage.total_downloads,
            "last_reset_date": self._usage.last_reset_date,
        }
        # Layer 1: HMAC sign
        data["_sig"] = self._compute_usage_hmac(data)
        
        self._usage_file.parent.mkdir(parents=True, exist_ok=True)
        self._usage_file.write_text(json.dumps(data, indent=2))
    
    def _sync_usage_to_server(self):
        """Layer 2: Sync usage to Firebase _usage/{MID} for ALL user types.
        
        Sends: daily_count, total_generations, total_downloads, tier, client_name.
        Includes HMAC token for anti-tamper verification.
        Falls back to legacy sync_daily_usage() for _trials/ backward compat.
        """
        try:
            rest_client = getattr(self, '_rest_client', None)
            if not rest_client:
                return
            
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Get tier + client_name from cached license
            tier = ""
            client_name = ""
            try:
                cached = self.storage.load()
                if cached:
                    tier = cached.get('tier', '')
                    client_name = cached.get('client_name', '')
            except Exception:
                pass
            
            # Primary: sync_usage() → _usage/{MID} (ALL users)
            if hasattr(rest_client, 'sync_usage'):
                ok = rest_client.sync_usage(
                    self.machine_id,
                    self._usage.today_generations,
                    self._usage.total_generations,
                    self._usage.total_downloads,
                    today,
                    tier=tier,
                    client_name=client_name,
                )
                if ok:
                    print(f"[LICENSE] 📤 Synced usage: daily={self._usage.today_generations}, total={self._usage.total_generations}")
            
            # Legacy fallback: sync_daily_usage() → _trials/{MID}
            if hasattr(rest_client, 'sync_daily_usage'):
                rest_client.sync_daily_usage(
                    self.machine_id,
                    self._usage.today_generations,
                    today,
                )
        except Exception:
            pass  # Silent — network failures are OK
    
    def reconcile_usage_from_server(self, server_trial_data: dict = None):
        """Layer 3: Startup reconciliation — max(local, server).
        
        Sources (in priority order):
        1. _usage/{MID} — universal (all users)
        2. server_trial_data from _trials/{MID} — trial fallback
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Source 1: Read from _usage/{MID} (universal collection)
        try:
            rest_client = getattr(self, '_rest_client', None)
            if rest_client and hasattr(rest_client, 'read_usage'):
                usage_data = rest_client.read_usage(self.machine_id)
                if usage_data:
                    s_daily = usage_data.get("daily_count", 0)
                    s_date = usage_data.get("daily_date", "")
                    s_total = usage_data.get("total_generations", 0)
                    s_downloads = usage_data.get("total_downloads", 0)
                    
                    updated = False
                    
                    # Daily: max(local, server) if same date
                    if s_date == today and s_daily > self._usage.today_generations:
                        print(f"[LICENSE] 🔄 Server daily higher: {self._usage.today_generations} → {s_daily}")
                        self._usage.today_generations = s_daily
                        updated = True
                    
                    # Total: always use max
                    if s_total > self._usage.total_generations:
                        print(f"[LICENSE] 🔄 Server total higher: {self._usage.total_generations} → {s_total}")
                        self._usage.total_generations = s_total
                        updated = True
                    
                    # Downloads: always use max
                    if s_downloads > self._usage.total_downloads:
                        self._usage.total_downloads = s_downloads
                        updated = True
                    
                    if updated:
                        self._save_usage()
                    return  # Done — _usage/ is authoritative
        except Exception as e:
            print(f"[LICENSE] ⚠️ _usage reconcile failed: {e}")
        
        # Source 2: Fallback to _trials/ data (if provided)
        if server_trial_data:
            try:
                server_count = int(server_trial_data.get("daily_count", 0))
                server_date = server_trial_data.get("daily_date", "")
                
                if server_date == today and server_count > self._usage.today_generations:
                    print(f"[LICENSE] 🔄 Trial server count higher: {self._usage.today_generations} → {server_count}")
                    self._usage.today_generations = server_count
                    self._save_usage()
            except Exception:
                pass
    
    def log_generation(self):
        """Log a generation event (on 720p download success).
        
        Anti-tamper: HMAC-signed local + server sync every 10 gen.
        """
        self._usage.total_generations += 1
        self._usage.today_generations += 1
        self._usage.last_generation_at = datetime.now()
        self._usage.last_reset_date = datetime.now().strftime("%Y-%m-%d")
        self._save_usage()
        
        # Layer 2: Server sync every 10 generations or at daily limit
        daily_limit = self._get_daily_limit()
        should_sync = (
            self._usage.today_generations % 10 == 0
            or (daily_limit > 0 and self._usage.today_generations >= daily_limit)
        )
        if should_sync:
            self._sync_usage_to_server()
    
    def _get_daily_limit(self) -> int:
        """Get current daily generation limit from license/permissions."""
        try:
            info = self._validate_cache or self.validate()
            if info and info.limits_override:
                return int(info.limits_override.get('dg', 100))
        except Exception:
            pass
        return 100  # Fallback default
    
    def log_download(self):
        """Log a download event (720p file saved)."""
        self._usage.total_downloads += 1
        self._save_usage()


def main():
    """Demo: Show machine ID and license status"""
    print("=" * 60)
    print("VEO License Client - Machine Info")
    print("=" * 60)
    
    client = LicenseClient()
    
    print(f"\nMachine ID (full):    {client.get_machine_id()[:16]}...")
    print(f"Machine ID (display): {client.get_display_machine_id()}")
    
    print("\n" + "-" * 60)
    print("License Status:")
    
    info = client.validate()
    print(f"  Valid:   {info.valid}")
    print(f"  Tier:    {info.tier.name if info.tier else 'N/A'}")
    print(f"  Expires: {info.expires.date() if info.expires else 'N/A'}")
    print(f"  Error:   {info.error or 'None'}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
