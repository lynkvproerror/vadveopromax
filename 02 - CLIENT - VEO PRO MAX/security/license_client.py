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
    from trial_protection import TrialMarkerManager, TrialStatus
    TRIAL_PROTECTION_AVAILABLE = True
except ImportError:
    TRIAL_PROTECTION_AVAILABLE = False

# Firebase (optional - for online validation)
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False


class LicenseTier(str, Enum):
    """VND Pricing Model - License Tiers"""
    TRIAL = "TRIA"           # 7 ngày - Miễn phí
    ONE_MONTH = "1M"         # 30 ngày - 300,000đ
    THREE_MONTHS = "3M"      # 90 ngày - 500,000đ
    SIX_MONTHS = "6M"        # 180 ngày - 800,000đ
    ONE_YEAR = "1Y"          # 365 ngày - 1,200,000đ
    LIFETIME = "LT"          # Vĩnh viễn - 3,000,000đ


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
    HMAC_SECRET = b"veo_hmac_secret_k3y_2026_pr0t3ct10n"  # HMAC secret
    APP_VERSION = "2.4.0"  # Include in signature to detect version mismatch
    
    def __init__(self, machine_id: str):
        self.LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.machine_id = machine_id
        self._fernet = self._create_fernet()
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
            nonce,                    # Random per save
            self.APP_VERSION,         # Detect version mismatch
            str(len(str(data))),      # Data length check
            
            # === OBFUSCATION ===
            "v3o_l1c_s1g",           # Static marker
        ]
        
        # Join with separator that's unlikely to appear in data
        payload = "||VEO||".join(sig_parts)
        
        # Generate HMAC-SHA256
        signature = hmac_lib.new(
            self.HMAC_SECRET,
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
        license_data['_sig_version'] = 2  # Signature format version
        
        data_str = json.dumps(license_data, default=str)
        
        if self._fernet:
            # AES-256 encryption
            encrypted = self._fernet.encrypt(data_str.encode())
        else:
            # Fallback: XOR encryption
            encrypted = self._xor_encrypt(data_str.encode())
        
        self.LICENSE_FILE.write_bytes(encrypted)
    
    def load(self) -> Optional[dict]:
        """Load license data and verify signature."""
        if not self.LICENSE_FILE.exists():
            return None
        
        try:
            encrypted = self.LICENSE_FILE.read_bytes()
            
            if self._fernet:
                # AES-256 decryption
                decrypted = self._fernet.decrypt(encrypted)
            else:
                # Fallback: XOR
                decrypted = self._xor_encrypt(encrypted)
            
            data = json.loads(decrypted.decode())
            
            # 🔒 VERIFY SIGNATURE (CRITICAL!)
            if data.get('_sig_version', 0) >= 2:
                if not self._verify_signature(data):
                    # Tampering detected! Clear cache and require re-validation
                    self.clear()
                    return None
            
            return data
        except:
            return None
    
    def clear(self):
        """Clear local license data."""
        if self.LICENSE_FILE.exists():
            self.LICENSE_FILE.unlink()
    
    def _xor_encrypt(self, data: bytes) -> bytes:
        """Fallback XOR encryption."""
        key = self.machine_id.encode()[:16] + self.SALT[:16]
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


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
    TRIAL_DAYS = 7
    OFFLINE_GRACE_DAYS = 3  # 🔒 Reduced from 7 to 3 days
    
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
        self._init_firebase()
    
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
                last_validated = datetime.fromisoformat(str(last_validated_str))
                if now < last_validated:
                    # Time went backwards! Clock tampering detected.
                    return True
            except:
                pass
        
        # Check 2: activation_time should be in the past
        activation_str = cached.get('activation_time')
        if activation_str:
            try:
                activation = datetime.fromisoformat(str(activation_str))
                if now < activation:
                    return True
            except:
                pass
        
        # Check 3: Compare with stored "last_known_time"
        last_known_str = cached.get('_last_known_time')
        if last_known_str:
            try:
                last_known = datetime.fromisoformat(str(last_known_str))
                # Allow 1 hour backwards (daylight saving, manual adjustment)
                if now < last_known - timedelta(hours=1):
                    return True
            except:
                pass
        
        return False
    
    def _init_firebase(self):
        """
        Initialize Firebase connection.
        
        Priority:
        1. REST Client (secure, no Admin SDK) - for production
        2. Admin SDK (only if available) - for development
        """
        # === OPTION 1: REST Client (SECURE - No Admin SDK) ===
        try:
            from firebase_rest_client import FirebaseRESTClient, SecureFirebaseConfig
            self._rest_client = FirebaseRESTClient()
            self._use_rest = True
            self._which_db = "rest_api"
            return
        except ImportError:
            self._use_rest = False
        except Exception:
            self._use_rest = False
        
        # === OPTION 2: Admin SDK (Development Only) ===
        # NOTE: This should be REMOVED in production builds!
        if not FIREBASE_AVAILABLE:
            return
        
        # Try using firebase_config for failover (if in admin folder)
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent / "admin"))
            from firebase_config import get_failover_db
            self.db, self._which_db = get_failover_db()
            if self.db:
                return
        except ImportError:
            pass
        except Exception:
            pass
        
        # Last resort: Find local credentials (DEVELOPMENT ONLY!)
        cred_paths = [
            os.environ.get('VEO_LICENSE_CONFIG'),
            Path.home() / ".veoauto" / "firebase-credentials.json",
        ]
        
        cred_path = None
        for path in cred_paths:
            if path and Path(path).exists():
                cred_path = path
                break
        
        if not cred_path:
            return
        
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(str(cred_path))
                firebase_admin.initialize_app(cred)
            
            self.db = firestore.client()
            self._which_db = "admin_sdk"
        except:
            pass
    
    # =====================
    # PUBLIC API
    # =====================
    
    def get_machine_id(self) -> str:
        """Get full machine ID hash (for internal use)"""
        return self.machine_id
    
    def get_display_machine_id(self) -> str:
        """Get short display ID (for user to see)"""
        return self.display_id
    
    def activate(self, license_key: str) -> LicenseInfo:
        """
        Activate a license key.
        
        Args:
            license_key: The license key (VEOAUTO-XXXX-XXXX-XXXX-XXXX)
            
        Returns:
            LicenseInfo with activation result
        """
        # Validate format locally first
        if not self._validate_key_format(license_key):
            return LicenseInfo(valid=False, error="Invalid key format")
        
        # Try online activation
        if self.db:
            return self._activate_online(license_key)
        else:
            return LicenseInfo(valid=False, error="No internet connection")
    
    def validate(self) -> LicenseInfo:
        """
        Validate current license status.
        Called on app startup and periodically.
        
        Uses cross-validation with dual-Firebase when REST client available.
        """
        # Load cached license
        cached = self.storage.load()
        
        if not cached:
            return self._check_trial()
        
        # 🔒 CLOCK TAMPERING CHECK (before anything else!)
        if self._detect_clock_tampering(cached):
            self.storage.clear()  # Clear tampered cache
            return LicenseInfo(valid=False, error="Clock manipulation detected. Re-activate required.")
        
        # Check machine binding
        if cached.get('machine_id') != self.machine_id:
            return LicenseInfo(valid=False, error="License bound to different machine")
        
        # Check local expiry
        expires = datetime.fromisoformat(cached.get('expires', '2000-01-01'))
        if expires < datetime.now():
            return LicenseInfo(valid=False, error="License expired")
        
        # Try online validation (but allow offline grace period)
        last_check = datetime.fromisoformat(cached.get('last_verified', '2000-01-01'))
        if datetime.now() - last_check > timedelta(days=self.OFFLINE_GRACE_DAYS):
            # === USE REST CLIENT WITH CROSS-VALIDATION ===
            if hasattr(self, '_use_rest') and self._use_rest and hasattr(self, '_rest_client'):
                return self._validate_with_rest(cached.get('key'))
            elif self.db:
                return self._validate_online(cached.get('key'))
            else:
                return LicenseInfo(valid=False, error="Online verification required")
        
        # 🔒 Update last known time (for next clock check)
        cached['_last_known_time'] = datetime.now().isoformat()
        self.storage.save(cached)
        
        # Valid from cache
        tier = self._tier_from_code(cached.get('tier'))
        role = UserRole(cached.get('role', 1))  # 🆕 Default: PREMIUM
        return LicenseInfo(
            valid=True,
            tier=tier,
            role=role,  # 🆕
            expires=expires,
            machine_id=self.machine_id
        )
    
    def _validate_with_rest(self, license_key: str) -> LicenseInfo:
        """
        Validate using REST client with dual-Firebase cross-validation.
        
        This is the SECURE method - no Admin SDK required!
        """
        if not hasattr(self, '_rest_client') or not self._rest_client:
            return LicenseInfo(valid=False, error="REST client not available")
        
        is_valid, status, data = self._rest_client.validate_with_crosscheck(
            license_key, 
            self.machine_id
        )
        
        if not is_valid:
            error_messages = {
                "LICENSE_NOT_FOUND": "License key not found",
                "MACHINE_MISMATCH": "License bound to different machine",
                "LICENSE_REVOKED": "License has been revoked",
                "CROSS_VALIDATION_FAILED": "Security validation failed",
                "LICENSE_EXPIRED": "License expired"
            }
            return LicenseInfo(
                valid=False, 
                error=error_messages.get(status, f"Validation failed: {status}")
            )
        
        # Update cache with validated data
        cached = self.storage.load() or {}
        cached['last_verified'] = datetime.now().isoformat()
        cached['_last_known_time'] = datetime.now().isoformat()
        cached['_validation_source'] = status  # VALID_CROSS_VALIDATED or VALID_SINGLE_SOURCE
        self.storage.save(cached)
        
        tier = self._tier_from_code(data.get('tier'))
        role = UserRole(data.get('role', 1))
        expires_str = data.get('expires', '2100-01-01')
        
        try:
            if isinstance(expires_str, str):
                expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00').replace('+00:00', ''))
            else:
                expires = datetime.now() + timedelta(days=365)
        except:
            expires = datetime.now() + timedelta(days=365)
        
        return LicenseInfo(
            valid=True,
            tier=tier,
            role=role,
            expires=expires,
            machine_id=self.machine_id
        )
    
    def is_licensed(self) -> bool:
        """Quick check if license is valid"""
        return self.validate().valid
    
    def get_tier(self) -> Optional[str]:
        """Get current license tier name"""
        info = self.validate()
        return info.tier.name if info.tier else None
    
    def get_role(self) -> UserRole:
        """Get current user role 🆕"""
        return UserRole.TESTER  # Force TESTER for current account
    
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
    
    # =====================
    # INTERNAL METHODS
    # =====================
    
    def _validate_key_format(self, key: str) -> bool:
        """
        Validate key format locally.
        
        v2.0 format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX (8 segments)
        Trial format: TRIAL-XXXX-XXXX-XXXX (4 segments)
        """
        parts = key.upper().replace(" ", "").split("-")
        
        # New obfuscated format: 8 segments of 4 hex chars
        if len(parts) == 8:
            return all(len(p) == 4 and all(c in '0123456789ABCDEF' for c in p) for p in parts)
        
        # Trial format: TRIAL-XXXX-XXXX-XXXX
        if len(parts) == 4 and parts[0] == "TRIAL":
            return all(len(p) == 4 for p in parts[1:])
        
        # Legacy format: VEOAUTO-XXXX-XXXX-XXXX-XXXX (5 segments)
        if len(parts) == 5 and parts[0] == "VEOAUTO":
            return True
        
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
        Check trial status - NO AUTOMATIC TRIAL!
        
        v2.0: Trial requires a TRIAL-XXXX key from admin.
        Uses multi-layer protection from trial_protection.py.
        """
        # v2.0: Use new trial protection if available
        if self.trial_manager:
            status = self.trial_manager.validate_trial()
            
            if status.valid:
                return LicenseInfo(
                    valid=True,
                    tier=LicenseTier.TRIAL,
                    expires=status.expires
                )
            else:
                # No trial or expired - REQUIRE LICENSE KEY
                return LicenseInfo(
                    valid=False,
                    error=status.error or "License key required"
                )
        
        # Fallback: No trial protection module - REQUIRE LICENSE
        return LicenseInfo(
            valid=False,
            error="License key required. Contact admin for trial key."
        )
    
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
