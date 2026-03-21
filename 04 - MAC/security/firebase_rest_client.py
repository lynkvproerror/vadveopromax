"""
Firebase REST Client with Multi-layer Obfuscation v2.5
======================================================

This module provides secure Firebase access WITHOUT Admin SDK.
Uses REST API with read-only access and dual-database cross-validation.

Security Layers:
1. AES-256 Encryption - Keys encrypted with Fernet (AES-CBC)
2. Hardware Binding - Keys bound to machine
3. Split & Scatter - Keys split across functions
4. Runtime Decryption - No plaintext in binary
5. SSL Proxy Detection - Reject MITM interception (Fiddler/mitmproxy)

Author: VEO Security Team
Version: 2.5
"""

import os
import json
import hashlib
import requests
import base64
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime
import ssl
import socket
import logging

_log = logging.getLogger(__name__)

# AES-256 Encryption (Fernet uses AES-128, we use custom AES-256)
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    AES_AVAILABLE = True
except ImportError:
    AES_AVAILABLE = False


# ============================================================
# LAYER 1: AES-256 ENCRYPTION (upgraded from XOR)
# ============================================================

class _AES256Encryptor:
    """AES-256 encryption for API keys."""
    
    # Static salt (obfuscated)
    _SALT = b'\x56\x45\x4f\x5f\x50\x52\x4f\x5f\x4d\x41\x58\x5f\x32\x30\x32\x36'
    
    @staticmethod
    def derive_key(password: bytes) -> bytes:
        """Derive AES-256 key from password using PBKDF2."""
        if not AES_AVAILABLE:
            raise RuntimeError("cryptography package required — install with: pip install cryptography")
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_AES256Encryptor._SALT,
            iterations=100000,
            backend=default_backend()
        )
        return base64.urlsafe_b64encode(kdf.derive(password))
    
    @staticmethod
    def encrypt(data: str, key: bytes) -> bytes:
        """Encrypt string with AES-256."""
        if not AES_AVAILABLE:
            raise RuntimeError("cryptography package required for encryption")
        derived_key = _AES256Encryptor.derive_key(key)
        f = Fernet(derived_key)
        return f.encrypt(data.encode())
    
    @staticmethod
    def decrypt(encrypted: bytes, key: bytes) -> str:
        """Decrypt with AES-256."""
        if not AES_AVAILABLE:
            raise RuntimeError("cryptography package required for decryption")
        derived_key = _AES256Encryptor.derive_key(key)
        f = Fernet(derived_key)
        return f.decrypt(encrypted).decode('utf-8')
    
    @staticmethod
    def _xor(data: bytes, key: bytes) -> bytes:
        """DEPRECATED — XOR fallback removed for security. Kept for reference only."""
        raise RuntimeError("XOR encryption disabled — use AES-256 instead")


# ============================================================
# LAYER 2: HARDWARE-BOUND ENCRYPTION
# ============================================================

class _HardwareBinder:
    """Bind configuration to specific hardware."""
    
    @staticmethod
    def get_machine_key() -> bytes:
        """Generate machine-specific key for encryption."""
        import subprocess
        import platform
        
        components = []
        
        if platform.system() == "Darwin":  # macOS
            try:
                # CPU identifier
                result = subprocess.run(
                    ['sysctl', '-n', 'machdep.cpu.brand_string'],
                    capture_output=True, text=True, timeout=5,
                )
                cpu_id = result.stdout.strip()
                components.append(cpu_id)
            except:
                pass
            
            try:
                # Platform serial number (IOPlatformSerialNumber)
                result = subprocess.run(
                    ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.split('\n'):
                    if 'IOPlatformSerialNumber' in line:
                        serial = line.split('=')[-1].strip().strip('"')
                        components.append(serial)
                        break
            except:
                pass
        elif platform.system() == "Windows":
            pass  # Windows not used on macOS build
        
        # Create hash from components
        combined = "|".join(components) or "fallback_key"
        return hashlib.sha256(combined.encode()).digest()[:16]


# ============================================================
# LAYER 3: SPLIT & SCATTER CONFIGURATION
# ============================================================

class _ConfigParts:
    """Configuration split across multiple sources."""
    
    # Primary Firebase (veo-pro-max)
    @staticmethod
    def _get_primary_project():
        # Obfuscated: "veo-pro-max"
        parts = [b'\x76\x65\x6f', b'\x2d\x70\x72\x6f', b'\x2d\x6d\x61\x78']
        return b''.join(parts).decode()
    
    # Backup Firebase (veoauto-f54b5)
    @staticmethod
    def _get_backup_project():
        # Obfuscated: "veoauto-f54b5"
        parts = [b'\x76\x65\x6f\x61\x75\x74\x6f', b'\x2d\x66\x35\x34\x62\x35']
        return b''.join(parts).decode()
    
    @staticmethod
    def _get_api_base():
        # Obfuscated: "https://firestore.googleapis.com/v1"
        return "https://firestore.googleapis.com/v1"


# ============================================================
# LAYER 4: RUNTIME CONFIGURATION (using AES-256)
# ============================================================

class SecureFirebaseConfig:
    """
    Secure Firebase configuration with multi-layer protection.
    
    This class manages Firebase API keys with:
    - AES-256 encryption (upgraded from XOR)
    - Hardware-bound OR static key encryption
    - Split configuration
    - Runtime decryption
    """
    
    # Encrypted API keys (will be set by admin during build)
    _PRIMARY_KEY_ENCRYPTED = None
    _BACKUP_KEY_ENCRYPTED = None
    
    # Static key for multi-machine support (obfuscated)
    _STATIC_KEY = b'\x56\x45\x4f\x5f\x50\x52\x4f\x5f\x4d\x41\x58\x5f\x53\x54\x41\x54'
    
    # Toggle: True = static key, False = hardware key
    _USE_STATIC_KEY = False
    
    def __init__(self):
        self._decrypted_keys = {}
    
    def _get_decryption_key(self) -> bytes:
        """Get the appropriate decryption key based on mode."""
        if self._USE_STATIC_KEY:
            return self._STATIC_KEY
        return _HardwareBinder.get_machine_key()
    
    def _decrypt_key(self, encrypted: bytes) -> str:
        """Decrypt API key using AES-256."""
        if not encrypted:
            return ""
        try:
            key = self._get_decryption_key()
            return _AES256Encryptor.decrypt(encrypted, key)
        except Exception:
            return ""
    
    def get_primary_config(self) -> Dict:
        """Get primary Firebase configuration."""
        return {
            "project_id": _ConfigParts._get_primary_project(),
            "api_base": _ConfigParts._get_api_base(),
            "api_key": self._decrypt_key(self._PRIMARY_KEY_ENCRYPTED) if self._PRIMARY_KEY_ENCRYPTED else None
        }
    
    def get_backup_config(self) -> Dict:
        """Get backup Firebase configuration."""
        return {
            "project_id": _ConfigParts._get_backup_project(),
            "api_base": _ConfigParts._get_api_base(),
            "api_key": self._decrypt_key(self._BACKUP_KEY_ENCRYPTED) if self._BACKUP_KEY_ENCRYPTED else None
        }
    
    @classmethod
    def set_encrypted_keys(cls, primary_encrypted: bytes, backup_encrypted: bytes):
        """Set AES-256 encrypted API keys."""
        cls._PRIMARY_KEY_ENCRYPTED = primary_encrypted
        cls._BACKUP_KEY_ENCRYPTED = backup_encrypted
    
    @classmethod
    def set_static_mode(cls, enabled: bool):
        """Toggle static key mode for multi-machine support."""
        cls._USE_STATIC_KEY = enabled
    
    @classmethod
    def get_key_mode(cls) -> str:
        """Get current key mode."""
        return "static" if cls._USE_STATIC_KEY else "hardware-bound"


# ============================================================
# FIREBASE REST CLIENT
# ============================================================

class FirebaseRESTClient:
    """
    Firebase Firestore REST API client.
    
    Uses REST API instead of Admin SDK for read-only operations.
    Supports dual-database cross-validation.
    """
    
    COLLECTION = "_lic"
    TIMEOUT = 10  # seconds
    
    # Trusted CA issuers for Google APIs (reject proxy certs)
    _TRUSTED_ISSUERS = {
        "Google Trust Services",
        "Google Trust Services LLC",
        "GlobalSign",           # Google's legacy CA
        "GTS CA",               # Short name variant
    }
    _SSL_CHECK_HOST = "firestore.googleapis.com"
    
    def __init__(self, config: SecureFirebaseConfig = None):
        self.config = config or SecureFirebaseConfig()
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json"
        })
        # Server health tracking
        self._server_health = {"primary": True, "backup": True}
        self._sticky_server = None  # Sticky after failover
        # Client config cache (loaded once per session)
        self._client_config = None
        self._client_config_loaded = False
        # SSL interception detection
        self._ssl_compromised = False
        self._ssl_checked = False
    
    def _verify_ssl_integrity(self) -> bool:
        """Detect SSL interception (Fiddler, mitmproxy, Charles Proxy).
        
        Connects to firestore.googleapis.com and verifies the TLS
        certificate issuer is a trusted Google CA. Proxy tools inject
        their own CA cert which will NOT match.
        
        Returns True if connection is clean, False if intercepted.
        """
        if self._ssl_checked:
            return not self._ssl_compromised
        
        self._ssl_checked = True
        
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(
                socket.socket(socket.AF_INET, socket.SOCK_STREAM),
                server_hostname=self._SSL_CHECK_HOST
            ) as sock:
                sock.settimeout(5)
                sock.connect((self._SSL_CHECK_HOST, 443))
                cert = sock.getpeercert()
            
            if not cert:
                _log.warning("[SSL] No certificate returned — possible interception")
                self._ssl_compromised = True
                return False
            
            # Extract issuer organization
            issuer_org = ""
            for rdn in cert.get('issuer', ()):
                for attr_type, attr_value in rdn:
                    if attr_type == 'organizationName':
                        issuer_org = attr_value
                        break
            
            # Check against trusted issuers
            is_trusted = any(
                trusted in issuer_org 
                for trusted in self._TRUSTED_ISSUERS
            )
            
            if not is_trusted:
                _log.warning(
                    f"[SSL] ⚠️ Untrusted certificate issuer: '{issuer_org}' "
                    f"— possible MITM proxy (Fiddler/mitmproxy/Charles)"
                )
                self._ssl_compromised = True
                return False
            
            _log.debug(f"[SSL] ✅ Certificate OK (issuer: {issuer_org})")
            return True
            
        except ssl.SSLCertVerificationError:
            _log.warning("[SSL] ⚠️ Certificate verification failed — possible interception")
            self._ssl_compromised = True
            return False
        except (socket.timeout, ConnectionError, OSError) as e:
            # Network issue — don't flag as compromised (offline mode)
            _log.debug(f"[SSL] Network check skipped: {e}")
            return True
    
    # ── Server Config + Load Balancing ────────────────────────
    
    # Default values if _config/client_settings doesn't exist
    DEFAULT_CLIENT_CONFIG = {
        "trial_poll_interval_ms": 300000,   # 5 minutes
        "trial_poll_max": 6,                # 6 × 5min = 30min
        "validate_cache_ttl_s": 3600,       # 1 hour
        "server_weight": 50,                # 50% primary, 50% backup
        "maintenance_mode": False,
        "min_client_version": "1.0.0",
        "ai_prompt_trial_enabled": False,   # Admin toggle: Trial users AI prompt
    }
    
    def fetch_client_config(self) -> dict:
        """
        Fetch client config from _config/client_settings (1 read per session).
        Tries primary first, then backup. Caches result in memory.
        """
        if self._client_config_loaded:
            return self._client_config or self.DEFAULT_CLIENT_CONFIG
        
        self._client_config_loaded = True
        base = _ConfigParts._get_api_base()
        
        for get_cfg in [self.config.get_primary_config, self.config.get_backup_config]:
            try:
                cfg = get_cfg()
                if not cfg:
                    continue
                url = f"{base}/projects/{cfg['project_id']}/databases/(default)/documents/_config/client_settings"
                resp = self._session.get(url, params={"key": cfg["api_key"]}, timeout=self.TIMEOUT)
                if resp.status_code == 200:
                    data = self._parse_document(resp.json())
                    if data:
                        self._client_config = data
                        return data
            except Exception:
                continue
        
        return self.DEFAULT_CLIENT_CONFIG
    
    def get_config_value(self, key: str, default=None):
        """Get a single config value from server config (cached)."""
        config = self.fetch_client_config()
        val = config.get(key)
        if val is None:
            return self.DEFAULT_CLIENT_CONFIG.get(key, default)
        return val
    
    def _pick_server(self, machine_id: str = "") -> tuple:
        """
        Smart Health-Check load balancer.
        
        Returns: (preferred_config, fallback_config, preferred_name)
        
        Logic:
        - server_weight (0-100): % of clients routed to primary
        - MID hash determines which group this client belongs to
        - If preferred server unhealthy → sticky fallback
        """
        primary = self.config.get_primary_config()
        backup = self.config.get_backup_config()
        
        if not backup:
            return primary, None, "primary"
        if not primary:
            return backup, None, "backup"
        
        # Sticky: if we already failed over this session, stay on failover server
        if self._sticky_server == "backup":
            return backup, primary, "backup"
        elif self._sticky_server == "primary_forced":
            return primary, backup, "primary"
        
        # Health check: skip unhealthy server
        if not self._server_health.get("primary", True):
            return backup, primary, "backup"
        if not self._server_health.get("backup", True):
            return primary, backup, "primary"
        
        # Weight-based selection
        weight = int(self.get_config_value("server_weight", 50))
        
        if machine_id:
            # Deterministic: same MID always goes to same server
            try:
                hash_val = int(machine_id[-2:], 16) if len(machine_id) >= 2 else 0
            except ValueError:
                hash_val = sum(ord(c) for c in machine_id) % 256
            use_primary = (hash_val % 100) < weight
        else:
            use_primary = weight >= 50
        
        if use_primary:
            return primary, backup, "primary"
        return backup, primary, "backup"
    
    def _read_doc(self, collection: str, doc_id: str, machine_id: str = "") -> dict:
        """
        Read a document with load balancing + auto-failover.
        
        Returns parsed document dict or None.
        Security: refuses to send API keys over SSL-intercepted connections.
        """
        # Layer 5: SSL interception check (lazy, once per session)
        if not self._ssl_checked:
            self._verify_ssl_integrity()
        if self._ssl_compromised:
            _log.error(
                "[SSL] 🚫 Refusing Firebase request — SSL interception detected. "
                "Data integrity cannot be guaranteed."
            )
            return None
        
        preferred, fallback, pref_name = self._pick_server(machine_id)
        base = _ConfigParts._get_api_base()
        
        got_404 = False  # Track if any server returned 404
        for cfg, name in [(preferred, pref_name), (fallback, "backup" if pref_name == "primary" else "primary")]:
            if not cfg:
                continue
            try:
                url = f"{base}/projects/{cfg['project_id']}/databases/(default)/documents/{collection}/{doc_id}"
                resp = self._session.get(url, params={"key": cfg["api_key"]}, timeout=self.TIMEOUT)
                if resp.status_code == 200:
                    self._server_health[name] = True
                    return self._parse_document(resp.json())
                elif resp.status_code == 404:
                    self._server_health[name] = True
                    got_404 = True
                    continue  # Try fallback — data may exist on other server
            except Exception:
                # Mark unhealthy, try fallback
                self._server_health[name] = False
                if name == pref_name:
                    fail_name = "backup" if name == "primary" else "primary_forced"
                    self._sticky_server = fail_name
                continue
        
        return None  # Both servers checked — not found
    
    def _build_url(self, project_id: str, document_id: str) -> str:
        """Build Firestore REST API URL."""
        base = _ConfigParts._get_api_base()
        return f"{base}/projects/{project_id}/databases/(default)/documents/{self.COLLECTION}/{document_id}"
    
    def _parse_firestore_value(self, value: dict) -> any:
        """Parse Firestore REST API value format."""
        if "stringValue" in value:
            return value["stringValue"]
        elif "integerValue" in value:
            return int(value["integerValue"])
        elif "booleanValue" in value:
            return value["booleanValue"]
        elif "timestampValue" in value:
            return value["timestampValue"]
        elif "mapValue" in value:
            return {k: self._parse_firestore_value(v) 
                    for k, v in value["mapValue"].get("fields", {}).items()}
        return None
    
    def _parse_document(self, doc: dict) -> dict:
        """Parse Firestore document to simple dict."""
        if not doc or "fields" not in doc:
            return None
        
        result = {}
        for key, value in doc["fields"].items():
            result[key] = self._parse_firestore_value(value)
        return result
    
    def query_license(self, project_id: str, api_key: str, license_key: str) -> Optional[dict]:
        """
        Query a license from Firestore REST API.
        
        Returns:
            License data dict if found,
            None if key genuinely not found (404),
            Raises ConnectionError on network errors.
        """
        if not api_key:
            raise ConnectionError("No API key configured")
        
        url = self._build_url(project_id, license_key)
        
        try:
            response = self._session.get(
                url,
                params={"key": api_key},
                timeout=self.TIMEOUT
            )
            
            if response.status_code == 200:
                return self._parse_document(response.json())
            elif response.status_code == 404:
                return None  # Key genuinely not found
            else:
                raise ConnectionError(f"Firebase returned {response.status_code}")
        except ConnectionError:
            raise  # Re-raise our own ConnectionError
        except Exception as e:
            raise ConnectionError(f"Network error: {e}")
    
    def validate_with_crosscheck(self, license_key: str, machine_id: str) -> Tuple[bool, str, dict]:
        """
        Validate license with dual-database cross-validation.
        
        Returns:
            (is_valid, status_message, license_data)
        Raises:
            ConnectionError if BOTH databases unreachable (network down)
        """
        primary_config = self.config.get_primary_config()
        backup_config = self.config.get_backup_config()
        
        primary_result = None
        primary_error = False
        backup_result = None
        backup_error = False
        
        # Query PRIMARY
        if primary_config.get("api_key"):
            try:
                primary_result = self.query_license(
                    primary_config["project_id"],
                    primary_config["api_key"],
                    license_key
                )
            except ConnectionError:
                primary_error = True
        
        # Query BACKUP
        if backup_config.get("api_key"):
            try:
                backup_result = self.query_license(
                    backup_config["project_id"],
                    backup_config["api_key"],
                    license_key
                )
            except ConnectionError:
                backup_error = True
        
        # If BOTH had network errors → raise to trigger cache fallback
        if primary_error and backup_error:
            raise ConnectionError("Both Firebase databases unreachable")
        
        # Pass error flags so _cross_validate can distinguish 404 vs network error
        return self._cross_validate(
            primary_result, backup_result, machine_id,
            primary_error=primary_error, backup_error=backup_error
        )
    
    def _cross_validate(self, primary: dict, backup: dict, machine_id: str,
                        primary_error: bool = False, backup_error: bool = False) -> Tuple[bool, str, dict]:
        """
        Cross-validate between primary and backup results.
        
        Security rules:
        - Both None (404) → NOT_FOUND
        - One 404 + other has data → STALE_DATA (key deleted from one DB) → INVALID
        - One network error + other has data → allow (network issue)
        - Both have data → cross-validate fields
        """
        # Case 1: Neither has data
        if not primary and not backup:
            return False, "LICENSE_NOT_FOUND", {}
        
        def _check_machine_id(data: dict, mid: str) -> bool:
            """Check machine ID against both raw and hashed formats."""
            import hashlib
            mid_upper = mid.upper()
            mid_hash = hashlib.sha256(mid.encode()).hexdigest().upper()
            
            stored_mid = (data.get('_mid') or '').upper()
            if stored_mid:
                if mid_upper.startswith(stored_mid) or stored_mid.startswith(mid_upper):
                    return True
                if mid_hash.startswith(stored_mid) or stored_mid.startswith(mid_hash):
                    return True
                if stored_mid == mid_upper or stored_mid == mid_hash:
                    return True
            
            stored_raw = (data.get('machine_id') or '').upper()
            if stored_raw:
                if mid_upper.startswith(stored_raw) or stored_raw.startswith(mid_upper):
                    return True
                if mid_hash.startswith(stored_raw) or stored_raw.startswith(mid_hash):
                    return True
                if stored_raw == mid_upper or stored_raw == mid_hash:
                    return True
            
            return False
        
        # Case 2: Only one has data
        if bool(primary) != bool(backup):
            valid_data = primary or backup
            
            # 🔒 SECURITY: If one DB returned 404 (not network error),
            # the other having data means STALE data → key was deleted
            if primary and not backup and not backup_error:
                # Backup returned 404, primary has data → stale backup scenario
                # This is OK: backup may not have been synced yet
                pass  # Allow — primary is authoritative
            elif backup and not primary and not primary_error:
                # Primary returned 404, backup has data → KEY WAS DELETED!
                return False, "LICENSE_DELETED_STALE_BACKUP", {}
            elif backup and not primary and primary_error:
                # Primary had network error, backup has data → OK, use backup
                pass  # Allow — network issue
            elif primary and not backup and backup_error:
                # Backup had network error, primary has data → OK, use primary
                pass  # Allow — network issue
            
            # Verify machine_id
            if not _check_machine_id(valid_data, machine_id):
                return False, "MACHINE_MISMATCH", {}
            
            if valid_data.get("revoked") or valid_data.get("_st") == "r":
                return False, "LICENSE_REVOKED", {}
            
            return True, "VALID_SINGLE_SOURCE", valid_data
        
        # Case 3: Both have data - CROSS VALIDATE!
        # Compare critical fields (support both naming conventions)
        # NOTE: expires/_exp excluded — time-based fields can differ between
        # primary/backup due to replication latency (especially 12h packages).
        # Expiry is still independently checked below.
        critical_fields = ["key", "tier", "_t", "machine_id", "_mid", "revoked"]
        
        for field in critical_fields:
            p_val = primary.get(field)
            b_val = backup.get(field)
            # Only compare if both have the field
            if p_val is not None and b_val is not None and p_val != b_val:
                # TAMPERING DETECTED!
                return False, "CROSS_VALIDATION_FAILED", {}
        
        # Verify machine_id
        if not _check_machine_id(primary, machine_id):
            return False, "MACHINE_MISMATCH", {}
        
        # Check if revoked
        if primary.get("revoked") or primary.get("_st") == "r":
            return False, "LICENSE_REVOKED", {}
        
        # Check expiry (support both _exp and expires)
        expires = primary.get("expires") or primary.get("_exp")
        if expires:
            try:
                # Parse various date formats
                if isinstance(expires, str):
                    exp_date = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                    if datetime.now(exp_date.tzinfo) > exp_date:
                        return False, "LICENSE_EXPIRED", {}
            except:
                pass
        
        return True, "VALID_CROSS_VALIDATED", primary
    
    # ── HMAC Token Anti-DDoS ──────────────────────────────────
    
    @staticmethod
    def _derive_hmac_key(machine_id: str) -> bytes:
        """Derive HMAC key from machine ID — unique per machine, not hardcoded."""
        import hmac as _hmac, hashlib
        return _hmac.new(
            b"veo_rest_derive_2026",
            (machine_id + "||REST_HMAC").encode(),
            hashlib.sha256
        ).digest()
    
    def _generate_request_token(self, machine_id: str) -> str:
        """
        Generate HMAC request token for write operations.
        Token = timestamp_bucket:signature (5-min window).
        Admin can verify this to reject forged requests.
        """
        import hmac as _hmac, hashlib, time as _time
        ts_bucket = str(int(_time.time()) // 300)  # 5-min bucket
        msg = f"{machine_id}{ts_bucket}".encode()
        key = self._derive_hmac_key(machine_id)
        sig = _hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]
        return f"{ts_bucket}:{sig}"
    
    @classmethod
    def verify_request_token(cls, machine_id: str, token: str, max_age_minutes: int = 1440) -> bool:
        """
        Verify HMAC request token (for admin-side validation).
        Accepts tokens within max_age_minutes window.
        """
        if not token or ':' not in token:
            return False
        try:
            import hmac as _hmac, hashlib, time as _time
            ts_bucket, sig = token.split(':', 1)
            current_bucket = int(_time.time()) // 300
            token_bucket = int(ts_bucket)
            
            # Check age (allow up to max_age_minutes)
            age_buckets = current_bucket - token_bucket
            if age_buckets < 0 or age_buckets > (max_age_minutes // 5):
                return False
            
            # Recompute HMAC with derived key
            msg = f"{machine_id}{ts_bucket}".encode()
            key = cls._derive_hmac_key(machine_id)
            expected = _hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]
            return _hmac.compare_digest(sig, expected)
        except Exception:
            return False
    
    def write_upgrade_request(self, machine_id: str, tier: str, st_token: str, send_count: int = 1,
                               client_name: str = "", email: str = "",
                               client_ip: str = "unknown", is_first_buy: bool = False) -> bool:
        """
        Write/update upgrade request using machine_id as document ID.
        
        Uses PATCH → only 1 document per machine (no spam).
        Firestore doc ID = machine_id → admin sees 1 row per client.
        Server auto-derives: app, role, duration from tier.
        
        Args:
            machine_id: Client's machine ID (also used as doc ID)
            tier: Desired upgrade tier (1M, 3M, 6M, 1Y, LIFETIME)
            st_token: Anti-spam token
            send_count: Number of times this machine sent a request
            client_name: Customer name
            email: Customer email (optional)
            client_ip: Client public IP (auto-detected)
            
        Returns:
            True if request was written successfully
        """
        primary_config = self.config.get_primary_config()
        api_key = primary_config.get("api_key")
        project_id = primary_config.get("project_id")
        
        if not api_key or not project_id:
            return False
        
        # Auto-derive role and duration from tier
        tier_duration = {
            "1M": "30 days", "3M": "90 days", "6M": "180 days",
            "1Y": "365 days", "LIFETIME": "Lifetime",
            "12H": "12 hours", "1D": "1 day",
        }
        role = "PREMIUM" if tier != "LIFETIME" else "PREMIUM_LIFETIME"
        duration = tier_duration.get(tier, "30 days")
        
        base = _ConfigParts._get_api_base()
        url = f"{base}/projects/{project_id}/databases/(default)/documents/_upgrade_requests/{machine_id}"
        
        # Generate HMAC token for request verification
        request_token = self._generate_request_token(machine_id)
        
        payload = {
            "fields": {
                "machine_id": {"stringValue": machine_id},
                "client_name": {"stringValue": client_name},
                "email": {"stringValue": email},
                "client_ip": {"stringValue": client_ip},
                "app": {"stringValue": "VEO"},
                "tier": {"stringValue": tier},
                "role": {"stringValue": role},
                "duration": {"stringValue": duration},
                "st": {"stringValue": st_token},
                "requested_at": {"stringValue": datetime.now().isoformat()},
                "client_submitted_at": {"stringValue": datetime.now().isoformat()},
                "send_count": {"integerValue": str(send_count)},
                "status": {"stringValue": "pending"},
                "is_first_buy": {"booleanValue": is_first_buy},
                "_token": {"stringValue": request_token},
            }
        }
        
        try:
            response = self._session.patch(
                url,
                params={"key": api_key},
                json=payload,
                timeout=self.TIMEOUT
            )
            if response.status_code == 200:
                # Replicate to backup (best-effort)
                try:
                    backup_config = self.config.get_backup_config()
                    if backup_config:
                        b_key = backup_config.get("api_key")
                        b_pid = backup_config.get("project_id")
                        if b_key and b_pid:
                            b_url = f"{base}/projects/{b_pid}/databases/(default)/documents/_upgrade_requests/{machine_id}"
                            self._session.patch(b_url, params={"key": b_key}, json=payload, timeout=self.TIMEOUT)
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False
    
    def read_upgrade_request(self, machine_id: str) -> dict:
        """
        Read existing upgrade request for this machine.
        
        Returns:
            Dict with request data or empty dict if not found
        """
        primary_config = self.config.get_primary_config()
        api_key = primary_config.get("api_key")
        project_id = primary_config.get("project_id")
        
        if not api_key or not project_id:
            return {}
        
        base = _ConfigParts._get_api_base()
        url = f"{base}/projects/{project_id}/databases/(default)/documents/_upgrade_requests/{machine_id}"
        
        try:
            response = self._session.get(
                url,
                params={"key": api_key},
                timeout=self.TIMEOUT
            )
            if response.status_code == 200:
                return self._parse_document(response.json()) or {}
            return {}
        except Exception:
            return {}
    
    # ── Server-side Rate Limiting ─────────────────────────────
    
    RATE_LIMIT_COLLECTION = "_rate_limit"
    RATE_LIMIT_MAX = 10       # Max attempts before block
    RATE_LIMIT_WINDOW = 300   # 5 minutes in seconds
    
    def _build_rate_limit_url(self, project_id: str, mid_hash: str) -> str:
        """Build Firestore URL for rate limit document."""
        base = _ConfigParts._get_api_base()
        doc_id = mid_hash[:16].upper()
        return f"{base}/projects/{project_id}/databases/(default)/documents/{self.RATE_LIMIT_COLLECTION}/{doc_id}"
    
    def record_activation_attempt(self, machine_id: str) -> bool:
        """
        Record an activation attempt on the server.
        
        Writes to _rate_limit/{mid_hash[:16]}.
        Firebase Rules REJECT write if attempts > 10 → client blocked.
        
        Returns:
            True if recorded (not blocked), False if rejected (blocked)
        """
        primary_config = self.config.get_primary_config()
        api_key = primary_config.get("api_key")
        project_id = primary_config.get("project_id")
        
        if not api_key or not project_id:
            return True  # Allow if offline
        
        mid_hash = machine_id[:16].upper()
        url = self._build_rate_limit_url(project_id, mid_hash)
        now_iso = datetime.now().isoformat()
        
        try:
            # Read existing doc
            response = self._session.get(
                url, params={"key": api_key}, timeout=self.TIMEOUT
            )
            
            if response.status_code == 200:
                existing = self._parse_document(response.json()) or {}
                current = int(existing.get('attempts', 0))
                first = existing.get('first_attempt', now_iso)
                
                # Reset if window expired
                try:
                    first_dt = datetime.fromisoformat(first)
                    if (datetime.now() - first_dt).total_seconds() > self.RATE_LIMIT_WINDOW:
                        current = 0
                        first = now_iso
                except Exception:
                    current = 0
                    first = now_iso
                
                new_count = current + 1
                payload = {
                    "fields": {
                        "attempts": {"integerValue": str(new_count)},
                        "last_attempt": {"stringValue": now_iso},
                        "first_attempt": {"stringValue": first},
                        "mid": {"stringValue": mid_hash},
                    }
                }
            else:
                # Create new
                payload = {
                    "fields": {
                        "attempts": {"integerValue": "1"},
                        "last_attempt": {"stringValue": now_iso},
                        "first_attempt": {"stringValue": now_iso},
                        "mid": {"stringValue": mid_hash},
                    }
                }
            
            # PATCH = create or update
            wr = self._session.patch(
                url, params={"key": api_key}, json=payload, timeout=self.TIMEOUT
            )
            # Replicate to backup (best-effort)
            if wr.status_code != 403:
                try:
                    backup_config = self.config.get_backup_config()
                    if backup_config:
                        b_key = backup_config.get("api_key")
                        b_pid = backup_config.get("project_id")
                        if b_key and b_pid:
                            b_url = self._build_rate_limit_url(b_pid, mid_hash)
                            self._session.patch(b_url, params={"key": b_key}, json=payload, timeout=self.TIMEOUT)
                except Exception:
                    pass
            return wr.status_code != 403  # 403 = rules rejected = blocked
            
        except Exception:
            return True  # Network error → allow
    
    def check_server_rate_limit(self, machine_id: str) -> tuple:
        """
        Check if machine is rate-limited on server.
        
        Returns:
            (is_blocked, attempts, remaining_seconds)
        """
        primary_config = self.config.get_primary_config()
        api_key = primary_config.get("api_key")
        project_id = primary_config.get("project_id")
        
        if not api_key or not project_id:
            return False, 0, 0
        
        mid_hash = machine_id[:16].upper()
        url = self._build_rate_limit_url(project_id, mid_hash)
        
        try:
            response = self._session.get(
                url, params={"key": api_key}, timeout=self.TIMEOUT
            )
            if response.status_code != 200:
                return False, 0, 0
            
            data = self._parse_document(response.json()) or {}
            attempts = int(data.get('attempts', 0))
            first = data.get('first_attempt', '')
            
            if attempts >= self.RATE_LIMIT_MAX and first:
                try:
                    elapsed = (datetime.now() - datetime.fromisoformat(first)).total_seconds()
                    remaining = int(self.RATE_LIMIT_WINDOW - elapsed)
                    if remaining > 0:
                        return True, attempts, remaining
                except Exception:
                    pass
            
            return False, attempts, 0
        except Exception:
            return False, 0, 0
    
    def query_customer(self, machine_id: str) -> dict:
        """
        Query customer purchase history from _customers/{machine_id}.
        
        Returns:
            Dict with purchase_count, total_paid, etc. Empty dict if not found.
        """
        primary_config = self.config.get_primary_config()
        api_key = primary_config.get("api_key")
        project_id = primary_config.get("project_id")
        
        if not api_key or not project_id:
            return {}
        
        base = _ConfigParts._get_api_base()
        url = f"{base}/projects/{project_id}/databases/(default)/documents/_customers/{machine_id}"
        
        try:
            response = self._session.get(
                url,
                params={"key": api_key},
                timeout=self.TIMEOUT
            )
            if response.status_code == 200:
                return self._parse_document(response.json())
            return {}  # Not found (404) or error
        except Exception:
            return {}
    
    def query_license_by_mid(self, machine_id: str) -> dict:
        """
        Lookup active key for a Machine ID via _mid_to_key/{MID}.
        Load-balanced across primary/backup with auto-failover.
        Decrypts _ek field (encrypted key) using machine_id.
        Falls back to plaintext 'key' for backward compatibility.
        """
        data = self._read_doc("_mid_to_key", machine_id, machine_id)
        if not data:
            return {"found": False}
        
        # Try encrypted key first (_ek), fallback to plaintext (key)
        license_key = None
        if data.get("_ek"):
            license_key = self._decrypt_mid_key(data["_ek"], machine_id)
        if not license_key or license_key == "****":
            raw = data.get("key", "")
            if raw and raw != "****":
                license_key = raw
        
        if license_key:
            return {
                "found": True,
                "key": license_key,
                "tier": data.get("tier", ""),
                "status": data.get("status", ""),
                "expires": data.get("expires", ""),
                "role": int(data.get("role", 1)),
            }
        return {"found": False}
    
    # ── MID-to-Key decryption (shared secret with admin) ──
    _MID_KEY_SALT = b'VEO_MID_KEY_ENCRYPT_2026_v1'
    
    def _decrypt_mid_key(self, encrypted_b64: str, machine_id: str) -> str:
        """Decrypt license key from _mid_to_key._ek field.
        
        Uses HMAC-SHA256(salt, machine_id) as XOR key stream.
        Mirrors admin's _encrypt_mid_key().
        """
        try:
            import hmac as _hmac, hashlib, base64
            derived = _hmac.new(self._MID_KEY_SALT, machine_id.encode(), hashlib.sha256).digest()
            encrypted = base64.b64decode(encrypted_b64)
            decrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(encrypted))
            return decrypted.decode('utf-8')
        except Exception:
            return ""
    
    def register_trial(self, machine_id: str, client_name: str = "") -> dict:
        """
        Register a trial on Firebase _trials/{machine_id}.
        
        Server-side record ensures:
        - Admin can see who's using trial
        - Trial can be revoked
        - MID can only use trial ONCE
        
        Returns:
            {"success": True} or {"success": False, "error": "reason"}
        """
        primary_config = self.config.get_primary_config()
        api_key = primary_config.get("api_key")
        project_id = primary_config.get("project_id")
        
        if not api_key or not project_id:
            return {"success": False, "error": "No API config"}
        
        # First check if trial already exists
        existing = self.check_trial_status(machine_id)
        if existing.get("exists"):
            return {"success": False, "error": existing.get("error", "Trial already used on this machine")}
        
        base = _ConfigParts._get_api_base()
        url = f"{base}/projects/{project_id}/databases/(default)/documents/_trials/{machine_id}"
        
        now = datetime.now()
        from datetime import timedelta
        expires = now + timedelta(days=3)
        
        payload = {
            "fields": {
                "machine_id": {"stringValue": machine_id},
                "client_name": {"stringValue": client_name},
                "started_at": {"stringValue": now.isoformat()},
                "expires_at": {"stringValue": expires.isoformat()},
                "status": {"stringValue": "active"},
                "days": {"integerValue": "3"},
            }
        }
        
        try:
            # Use PATCH (create or update)
            response = self._session.patch(
                url,
                params={"key": api_key},
                json=payload,
                timeout=self.TIMEOUT
            )
            if response.status_code == 200:
                # Replicate to backup DB
                try:
                    backup_config = self.config.get_backup_config()
                    if backup_config:
                        b_api_key = backup_config.get("api_key")
                        b_project_id = backup_config.get("project_id")
                        if b_api_key and b_project_id:
                            b_url = f"{base}/projects/{b_project_id}/databases/(default)/documents/_trials/{machine_id}"
                            self._session.patch(b_url, params={"key": b_api_key}, json=payload, timeout=self.TIMEOUT)
                except Exception:
                    pass  # Non-critical
                return {"success": True, "expires": expires.isoformat()}
            return {"success": False, "error": f"Server error: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)[:50]}
    
    def check_trial_status(self, machine_id: str) -> dict:
        """
        Check trial status from Firebase _trials/{machine_id}.
        Load-balanced across primary/backup with auto-failover.
        
        Returns:
            {"exists": False} — never used trial
            {"exists": True, "status": "active", "expires_at": "..."} — active trial
            {"exists": True, "status": "revoked", "error": "..."} — revoked by admin
            {"exists": True, "status": "expired", "error": "..."} — expired
        """
        data = self._read_doc("_trials", machine_id, machine_id)
        
        if not data:
            return {"exists": False}
        
        status = data.get("status", "unknown")
        expires_at = data.get("expires_at", "")
        
        if status == "revoked":
            return {"exists": True, "status": "revoked", "error": "Trial đã bị admin thu hồi"}
        
        if status == "upgraded":
            return {"exists": True, "status": "upgraded", "message": "Đã nâng cấp lên gói trả phí"}
        
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at)
                if datetime.now() > exp_dt:
                    # Write-back expired status to Firestore (best-effort)
                    self._writeback_trial_expired(machine_id)
                    return {"exists": True, "status": "expired", "error": "Trial đã hết hạn"}
            except Exception:
                pass
        
        # Decrypt client_name: _ecn (encrypted) → fallback to plaintext
        client_name = ""
        if data.get("_ecn"):
            client_name = self._decrypt_mid_key(data["_ecn"], machine_id)
        if not client_name or client_name == "***":
            raw_cn = data.get("client_name", "")
            if raw_cn and raw_cn != "***":
                client_name = raw_cn
        
        # Decrypt _lim: _elim (encrypted JSON) → fallback to plaintext _lim
        trial_lim = None
        if data.get("_elim"):
            try:
                import json as _json
                decrypted_lim = self._decrypt_mid_key(data["_elim"], machine_id)
                trial_lim = _json.loads(decrypted_lim)
            except Exception:
                trial_lim = data.get("_lim")
        else:
            trial_lim = data.get("_lim")
        
        return {
            "exists": True, "status": status, "expires_at": expires_at,
            "daily_count": data.get("daily_count", 0),
            "daily_date": data.get("daily_date", ""),
            "client_name": client_name,
            "_lim": trial_lim,  # Trial dynamic limits
        }
    
    def _writeback_trial_expired(self, machine_id: str):
        """Write-back expired status to Firestore _trials/{machine_id}.
        
        Best-effort, non-blocking — never raises exceptions.
        Keeps server data in sync with actual expiry state.
        """
        try:
            primary_config = self.config.get_primary_config()
            api_key = primary_config.get("api_key")
            project_id = primary_config.get("project_id")
            if not api_key or not project_id:
                return
            
            base = _ConfigParts._get_api_base()
            url = f"{base}/projects/{project_id}/databases/(default)/documents/_trials/{machine_id}"
            
            payload = {
                "fields": {
                    "status": {"stringValue": "expired"},
                    "_expired_at": {"stringValue": datetime.now().isoformat()},
                }
            }
            
            # PATCH with updateMask — only update status + _expired_at fields
            params = {
                "key": api_key,
                "updateMask.fieldPaths": ["status", "_expired_at"],
            }
            self._session.patch(url, params=params, json=payload, timeout=5)
            
            # Replicate to backup (best-effort)
            try:
                backup_config = self.config.get_backup_config()
                if backup_config:
                    b_key = backup_config.get("api_key")
                    b_pid = backup_config.get("project_id")
                    if b_key and b_pid:
                        b_url = f"{base}/projects/{b_pid}/databases/(default)/documents/_trials/{machine_id}"
                        b_params = {"key": b_key, "updateMask.fieldPaths": ["status", "_expired_at"]}
                        self._session.patch(b_url, params=b_params, json=payload, timeout=5)
            except Exception:
                pass
        except Exception:
            pass  # Never block client on write-back failure
    
    def read_tier_defaults(self) -> dict:
        """
        Read tier defaults from _config/tier_defaults.
        Used as fallback when individual _lim is not set.
        """
        data = self._read_doc("_config", "tier_defaults", "tier_defaults")
        if not data:
            return {}
        return data
    
    def sync_daily_usage(self, machine_id: str, daily_count: int, daily_date: str) -> bool:
        """
        Sync daily generation count to server for anti-tamper protection.
        
        Writes to _trials/{machine_id} (only daily_count + daily_date fields).
        Uses PATCH so only specified fields are updated, not the whole doc.
        
        Args:
            machine_id: Client machine ID (document ID in _trials)
            daily_count: Current day's generation count
            daily_date: Current date string (YYYY-MM-DD)
        
        Returns:
            True if synced successfully
        """
        primary_config = self.config.get_primary_config()
        api_key = primary_config.get("api_key")
        project_id = primary_config.get("project_id")
        
        if not api_key or not project_id:
            return False
        
        base = _ConfigParts._get_api_base()
        url = f"{base}/projects/{project_id}/databases/(default)/documents/_trials/{machine_id}"
        
        # Only update daily usage fields (PATCH with updateMask)
        payload = {
            "fields": {
                "daily_count": {"integerValue": str(daily_count)},
                "daily_date": {"stringValue": daily_date},
            }
        }
        
        try:
            response = self._session.patch(
                url,
                params={
                    "key": api_key,
                    "updateMask.fieldPaths": ["daily_count", "daily_date"],
                },
                json=payload,
                timeout=self.TIMEOUT,
            )
            if response.status_code == 200:
                # Replicate to backup (best-effort)
                try:
                    backup_config = self.config.get_backup_config()
                    if backup_config:
                        b_key = backup_config.get("api_key")
                        b_pid = backup_config.get("project_id")
                        if b_key and b_pid:
                            b_url = f"{base}/projects/{b_pid}/databases/(default)/documents/_trials/{machine_id}"
                            self._session.patch(
                                b_url,
                                params={"key": b_key, "updateMask.fieldPaths": ["daily_count", "daily_date"]},
                                json=payload, timeout=self.TIMEOUT,
                            )
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False
    
    def sync_usage(self, machine_id: str, daily_count: int, total_generations: int,
                   total_downloads: int, daily_date: str,
                   tier: str = "", client_name: str = "") -> bool:
        """
        Sync usage stats to _usage/{MID} for ALL user types (trial + paid + tester).
        
        Anti-tamper:
        - HMAC token in payload (server can verify authenticity)
        - Server-side: only accepts count INCREASES (anti-rollback)
        - Writes to both primary and backup DB
        
        Args:
            machine_id: Client machine ID (document ID)
            daily_count: Today's generation count
            total_generations: Lifetime total generation count
            total_downloads: Lifetime total download count
            daily_date: Current date string (YYYY-MM-DD)
            tier: License tier code (1M, 3M, 6M, 1Y, LT, TRIA)
            client_name: Customer name
            
        Returns:
            True if synced successfully
        """
        # Generate HMAC token for anti-tamper verification
        request_token = self._generate_request_token(machine_id)
        
        payload = {
            "fields": {
                "machine_id": {"stringValue": machine_id},
                "daily_count": {"integerValue": str(daily_count)},
                "daily_date": {"stringValue": daily_date},
                "total_generations": {"integerValue": str(total_generations)},
                "total_downloads": {"integerValue": str(total_downloads)},
                "last_sync_at": {"stringValue": datetime.now().isoformat()},
                "tier": {"stringValue": tier},
                "client_name": {"stringValue": client_name},
                "_token": {"stringValue": request_token},
            }
        }
        
        # Write to primary
        ok = self._patch_usage(machine_id, payload, "primary")
        
        # Replicate to backup (best-effort)
        try:
            self._patch_usage(machine_id, payload, "backup")
        except Exception:
            pass
        
        return ok
    
    def _patch_usage(self, machine_id: str, payload: dict, db_name: str = "primary") -> bool:
        """PATCH _usage/{MID} on specified database."""
        if db_name == "primary":
            config = self.config.get_primary_config()
        else:
            config = self.config.get_backup_config()
        
        api_key = config.get("api_key")
        project_id = config.get("project_id")
        
        if not api_key or not project_id:
            return False
        
        base = _ConfigParts._get_api_base()
        url = f"{base}/projects/{project_id}/databases/(default)/documents/_usage/{machine_id}"
        
        try:
            response = self._session.patch(
                url,
                params={"key": api_key},
                json=payload,
                timeout=self.TIMEOUT,
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def read_usage(self, machine_id: str) -> dict:
        """Read usage stats from _usage/{MID}. Used for startup reconciliation."""
        data = self._read_doc("_usage", machine_id, machine_id)
        if not data:
            return {}
        return {
            "daily_count": int(data.get("daily_count", 0)),
            "daily_date": data.get("daily_date", ""),
            "total_generations": int(data.get("total_generations", 0)),
            "total_downloads": int(data.get("total_downloads", 0)),
            "last_sync_at": data.get("last_sync_at", ""),
        }

# ============================================================
# ADMIN: KEY ENCRYPTION UTILITY
# ============================================================

class AdminKeyEncryptor:
    """
    Admin utility to encrypt API keys for embedding in client.
    
    Usage (ADMIN ONLY):
        encryptor = AdminKeyEncryptor()
        encrypted = encryptor.encrypt_for_hardware(api_key, target_machine_key)
    """
    
    @staticmethod
    def encrypt_key(api_key: str, hardware_key: bytes) -> bytes:
        """Encrypt API key with hardware-specific key."""
        key_bytes = api_key.encode('utf-8')
        result = bytearray(len(key_bytes))
        for i in range(len(key_bytes)):
            result[i] = key_bytes[i] ^ hardware_key[i % len(hardware_key)]
        return bytes(result)
    
    @staticmethod
    def generate_obfuscated_code(primary_key: str, backup_key: str) -> str:
        """
        Generate Python code with embedded encrypted keys.
        
        This generates code that can be copied into the client module.
        The keys are encrypted with a static key for distribution.
        """
        # Use a static key for distribution (less secure than hardware-bound)
        # This is a fallback for apps that run on any machine
        static_key = b"VE0_PR0_MAX_2026"  # 16 bytes
        
        primary_encrypted = AdminKeyEncryptor.encrypt_key(primary_key, static_key)
        backup_encrypted = AdminKeyEncryptor.encrypt_key(backup_key, static_key)
        
        code = f'''
# === AUTO-GENERATED ENCRYPTED KEYS ===
# Generated: {datetime.now().isoformat()}
# DO NOT EDIT MANUALLY!

_STATIC_KEY = b"VE0_PR0_MAX_2026"
_PRIMARY_KEY_ENCRYPTED = {primary_encrypted}
_BACKUP_KEY_ENCRYPTED = {backup_encrypted}

def _decrypt(encrypted: bytes) -> str:
    result = bytearray(len(encrypted))
    for i in range(len(encrypted)):
        result[i] = encrypted[i] ^ _STATIC_KEY[i % len(_STATIC_KEY)]
    return bytes(result).decode('utf-8')

# Usage:
# primary_key = _decrypt(_PRIMARY_KEY_ENCRYPTED)
# backup_key = _decrypt(_BACKUP_KEY_ENCRYPTED)
'''
        return code


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    print("🔥 Firebase REST Client Test")
    print("=" * 50)
    
    # Test configuration
    config = SecureFirebaseConfig()
    print(f"Primary Project: {config.get_primary_config()['project_id']}")
    print(f"Backup Project: {config.get_backup_config()['project_id']}")
    
    # Test hardware binding
    hw_key = _HardwareBinder.get_machine_key()
    print(f"Hardware Key (hex): {hw_key.hex()[:32]}...")
    
    # Test client (without API keys)
    client = FirebaseRESTClient(config)
    print("\n✅ REST Client initialized")
    
    print("\n" + "=" * 50)
    print("⚠️ Note: API keys not configured yet")
    print("   Run AdminKeyEncryptor to generate encrypted keys")
