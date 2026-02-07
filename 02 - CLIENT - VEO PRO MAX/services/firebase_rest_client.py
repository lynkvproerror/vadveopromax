"""
VEO Pro Max - Firebase REST Client

Reference: SESSION_06_WORKFLOWS_SECURITY.md
Role: License validation via Firebase REST API
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import hashlib
import base64
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Cryptography imports (optional)
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

import aiohttp


@dataclass
class FirebaseConfig:
    """Firebase configuration."""
    api_key: str
    database_url: str
    backup_url: Optional[str] = None


@dataclass
class LicenseData:
    """License data from Firebase."""
    key: str
    email: Optional[str] = None
    tier: str = "trial"
    machine_id: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    active: bool = False
    features: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.features is None:
            self.features = {}


class FirebaseRESTClient:
    """Read-only Firebase REST API client.
    
    Features:
    - AES-256 encryption with PBKDF2
    - Hardware-bound decryption
    - Cross-validation (Primary vs Backup)
    """
    
    PBKDF2_ITERATIONS = 100000
    SALT_SIZE = 16
    IV_SIZE = 16
    
    def __init__(self, config: FirebaseConfig, machine_id: Optional[str] = None):
        self._config = config
        self._machine_id = machine_id or self._get_machine_id()
        self._session: Optional[aiohttp.ClientSession] = None
    
    @staticmethod
    def _get_machine_id() -> str:
        """Generate unique machine ID."""
        import platform
        
        info = [
            platform.node(),
            platform.machine(),
            platform.processor(),
        ]
        return hashlib.sha256("|".join(info).encode()).hexdigest()[:32]
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    # === AES-256 Encryption ===
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key using PBKDF2."""
        if not HAS_CRYPTO:
            # Fallback: simple hash-based key
            combined = password.encode() + salt
            return hashlib.sha256(combined).digest()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # AES-256
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(password.encode())
    
    def encrypt_data(self, data: str, password: str) -> str:
        """Encrypt data with AES-256-CBC.
        
        Args:
            data: Plain text to encrypt
            password: Encryption password
        
        Returns:
            Base64 encoded: salt + iv + ciphertext
        """
        if not HAS_CRYPTO:
            # Fallback: base64 encode with simple XOR
            return self._simple_encrypt(data, password)
        
        import os
        salt = os.urandom(self.SALT_SIZE)
        iv = os.urandom(self.IV_SIZE)
        key = self._derive_key(password, salt)
        
        # Pad data to block size
        block_size = 16
        padding_len = block_size - (len(data.encode()) % block_size)
        padded_data = data.encode() + bytes([padding_len] * padding_len)
        
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        combined = salt + iv + ciphertext
        return base64.b64encode(combined).decode()
    
    def decrypt_data(self, encrypted: str, password: str) -> Optional[str]:
        """Decrypt data with AES-256-CBC.
        
        Args:
            encrypted: Base64 encoded encrypted data
            password: Decryption password
        
        Returns:
            Decrypted string or None on failure
        """
        if not HAS_CRYPTO:
            return self._simple_decrypt(encrypted, password)
        
        try:
            combined = base64.b64decode(encrypted)
            salt = combined[:self.SALT_SIZE]
            iv = combined[self.SALT_SIZE:self.SALT_SIZE + self.IV_SIZE]
            ciphertext = combined[self.SALT_SIZE + self.IV_SIZE:]
            
            key = self._derive_key(password, salt)
            
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Remove padding
            padding_len = padded_data[-1]
            data = padded_data[:-padding_len]
            
            return data.decode()
        except Exception:
            return None
    
    def _simple_encrypt(self, data: str, password: str) -> str:
        """Fallback simple encryption."""
        key_hash = hashlib.sha256(password.encode()).digest()
        data_bytes = data.encode()
        result = bytes([b ^ key_hash[i % 32] for i, b in enumerate(data_bytes)])
        return base64.b64encode(result).decode()
    
    def _simple_decrypt(self, encrypted: str, password: str) -> Optional[str]:
        """Fallback simple decryption."""
        try:
            key_hash = hashlib.sha256(password.encode()).digest()
            data = base64.b64decode(encrypted)
            result = bytes([b ^ key_hash[i % 32] for i, b in enumerate(data)])
            return result.decode()
        except Exception:
            return None
    
    def hardware_bound_encrypt(self, data: str) -> str:
        """Encrypt data bound to this machine."""
        return self.encrypt_data(data, self._machine_id)
    
    def hardware_bound_decrypt(self, encrypted: str) -> Optional[str]:
        """Decrypt data bound to this machine."""
        return self.decrypt_data(encrypted, self._machine_id)
    
    # === Firebase REST API ===
    
    async def read_path(self, path: str) -> Optional[Dict]:
        """Read data from Firebase path.
        
        Args:
            path: Database path (e.g., "licenses/ABC123")
        
        Returns:
            Data dict or None on error
        """
        session = await self._get_session()
        url = f"{self._config.database_url}/{path}.json"
        params = {"auth": self._config.api_key}
        
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except Exception:
            return None
    
    async def validate_license(self, license_key: str) -> Optional[LicenseData]:
        """Validate a license key against Firebase.
        
        Args:
            license_key: The license key to validate
        
        Returns:
            LicenseData if valid, None otherwise
        """
        # Normalize key
        clean_key = license_key.replace("-", "").upper()
        
        # Try primary database
        data = await self.read_path(f"licenses/{clean_key}")
        
        # Try backup if primary fails
        if data is None and self._config.backup_url:
            backup_url = self._config.backup_url
            session = await self._get_session()
            url = f"{backup_url}/licenses/{clean_key}.json"
            
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
            except Exception:
                pass
        
        if not data:
            return None
        
        # Parse license data
        return self._parse_license_data(license_key, data)
    
    def _parse_license_data(self, key: str, data: Dict) -> LicenseData:
        """Parse raw Firebase data into LicenseData."""
        created_at = None
        expires_at = None
        
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except Exception:
                pass
        
        if data.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(data["expires_at"])
            except Exception:
                pass
        
        return LicenseData(
            key=key,
            email=data.get("email"),
            tier=data.get("tier", "trial"),
            machine_id=data.get("machine_id"),
            created_at=created_at,
            expires_at=expires_at,
            active=data.get("active", False),
            features=data.get("features", {}),
        )
    
    async def cross_validate(self, license_key: str) -> bool:
        """Cross-validate license between primary and backup.
        
        Returns True only if both sources agree.
        """
        if not self._config.backup_url:
            # No backup, just validate primary
            result = await self.validate_license(license_key)
            return result is not None and result.active
        
        # Check primary
        clean_key = license_key.replace("-", "").upper()
        primary_data = await self.read_path(f"licenses/{clean_key}")
        
        # Check backup
        session = await self._get_session()
        backup_url = self._config.backup_url
        backup_data = None
        
        try:
            async with session.get(
                f"{backup_url}/licenses/{clean_key}.json",
                timeout=10
            ) as resp:
                if resp.status == 200:
                    backup_data = await resp.json()
        except Exception:
            pass
        
        # Both must agree
        if not primary_data or not backup_data:
            return False
        
        return (
            primary_data.get("active") == backup_data.get("active") == True
            and primary_data.get("tier") == backup_data.get("tier")
        )
