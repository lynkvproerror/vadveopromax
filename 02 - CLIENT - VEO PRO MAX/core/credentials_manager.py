"""
VEO Pro Max - Credentials Manager

Secure storage for Google account credentials using Fernet encryption.
"""

import os
import json
import hashlib
import platform
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None


class CredentialsManager:
    """Manages encrypted storage of Google credentials."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize credentials manager.
        
        Args:
            storage_path: Path to encrypted credentials file.
                         Defaults to config/credentials.enc
        """
        if storage_path is None:
            storage_path = Path(__file__).parent.parent / "config" / "credentials.enc"
        
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate encryption key from machine-specific data
        self._key = self._generate_key()
        self._fernet = Fernet(self._key) if Fernet else None
    
    def _generate_key(self) -> bytes:
        """Generate encryption key from machine-specific identifiers.
        
        Uses combination of:
        - Machine hostname
        - Username
        - A static salt
        
        Returns:
            Fernet-compatible 32-byte key (base64 encoded)
        """
        # Combine machine-specific data
        machine_id = f"{platform.node()}:{os.getlogin()}:veo_pro_max_salt_2024"
        
        # Create SHA256 hash
        hash_bytes = hashlib.sha256(machine_id.encode()).digest()
        
        # Fernet requires 32-byte base64-encoded key
        import base64
        return base64.urlsafe_b64encode(hash_bytes)
    
    def is_available(self) -> bool:
        """Check if encryption is available."""
        return self._fernet is not None
    
    def has_credentials(self) -> bool:
        """Check if credentials are stored."""
        return self.storage_path.exists()
    
    def save_credentials(self, email: str, password: str) -> bool:
        """Save encrypted credentials.
        
        Args:
            email: Google account email
            password: Google account password
            
        Returns:
            True if saved successfully
        """
        if not self._fernet:
            print("[CredentialsManager] ❌ cryptography package not installed")
            return False
        
        try:
            data = {
                "email": email,
                "password": password
            }
            
            # Serialize and encrypt
            json_bytes = json.dumps(data).encode('utf-8')
            encrypted = self._fernet.encrypt(json_bytes)
            
            # Save to file
            self.storage_path.write_bytes(encrypted)
            print(f"[CredentialsManager] ✅ Credentials saved for {email}")
            return True
            
        except Exception as e:
            print(f"[CredentialsManager] ❌ Failed to save: {e}")
            return False
    
    def load_credentials(self) -> Optional[Dict[str, str]]:
        """Load and decrypt credentials.
        
        Returns:
            Dict with 'email' and 'password', or None if not found/error
        """
        if not self._fernet:
            print("[CredentialsManager] ❌ cryptography package not installed")
            return None
        
        if not self.storage_path.exists():
            print("[CredentialsManager] ℹ️ No credentials stored")
            return None
        
        try:
            # Read and decrypt
            encrypted = self.storage_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            
            # Parse JSON
            data = json.loads(decrypted.decode('utf-8'))
            print(f"[CredentialsManager] ✅ Loaded credentials for {data.get('email', 'unknown')}")
            return data
            
        except Exception as e:
            print(f"[CredentialsManager] ❌ Failed to load: {e}")
            return None
    
    def delete_credentials(self) -> bool:
        """Delete stored credentials.
        
        Returns:
            True if deleted successfully
        """
        try:
            if self.storage_path.exists():
                self.storage_path.unlink()
                print("[CredentialsManager] ✅ Credentials deleted")
            return True
        except Exception as e:
            print(f"[CredentialsManager] ❌ Failed to delete: {e}")
            return False
    
    def get_stored_email(self) -> Optional[str]:
        """Get email from stored credentials without exposing password.
        
        Returns:
            Email string or None
        """
        creds = self.load_credentials()
        return creds.get("email") if creds else None


# Singleton instance
_manager: Optional[CredentialsManager] = None


def get_credentials_manager() -> CredentialsManager:
    """Get singleton credentials manager instance."""
    global _manager
    if _manager is None:
        _manager = CredentialsManager()
    return _manager
