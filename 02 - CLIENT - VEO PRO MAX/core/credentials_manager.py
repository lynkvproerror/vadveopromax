import logging

log = logging.getLogger(__name__)
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
        """Save encrypted credentials for an account.
        
        Storage format: {"accounts": {email: {email, password}}}
        
        Args:
            email: Google account email
            password: Google account password
            
        Returns:
            True if saved successfully
        """
        if not self._fernet:
            log.error("[CredentialsManager] ❌ cryptography package not installed")
            return False
        
        try:
            # Load existing accounts to merge
            all_accounts = self._load_all_raw() or {}
            
            # Add/update this account (email is the key, no need to store it again)
            all_accounts[email] = {
                "password": password
            }
            
            # Wrap under "accounts" key for clarity
            storage = {"accounts": all_accounts}
            
            # Serialize and encrypt
            json_bytes = json.dumps(storage).encode('utf-8')
            encrypted = self._fernet.encrypt(json_bytes)
            
            # Save to file
            self.storage_path.write_bytes(encrypted)
            log.info(f"[CredentialsManager] ✅ Credentials saved for {email}")
            return True
            
        except Exception as e:
            log.error(f"[CredentialsManager] ❌ Failed to save: {e}")
            return False
    
    def _load_all_raw(self) -> Optional[Dict[str, Any]]:
        """Load all account credentials as dict keyed by email.
        
        Storage format: {"accounts": {email: {email, password}}}
        Handles backward compat with old formats.
        
        Returns:
            Dict mapping email -> {email, password}, or None
        """
        if not self._fernet or not self.storage_path.exists():
            return None
        
        try:
            encrypted = self.storage_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode('utf-8'))
            
            # Current format: {"accounts": {email: {...}}}
            if isinstance(data, dict) and "accounts" in data:
                return data["accounts"]
            
            # Legacy v2: {email: {email, password}} (flat dict without wrapper)
            if isinstance(data, dict) and "email" not in data and "password" not in data:
                return data
            
            # Legacy v1: {email, password} (single entry)
            if isinstance(data, dict) and "email" in data and "password" in data:
                return {data["email"]: data}
            
            return data
        except Exception:
            return None
    
    def load_credentials(self) -> Optional[Dict[str, str]]:
        """Load and decrypt credentials (returns first entry).
        
        Returns:
            Dict with 'email' and 'password', or None if not found/error
        """
        all_accounts = self._load_all_raw()
        if not all_accounts:
            return None
        
        # Return first entry, reconstruct email from key
        for email, creds in all_accounts.items():
            log.info(f"[CredentialsManager] ✅ Loaded credentials for {email}")
            return {"email": email, "password": creds.get("password", "")}
        return None
    
    def load_credentials_for(self, email: str) -> Optional[Dict[str, str]]:
        """Load credentials for a specific email.
        
        Args:
            email: Email to look up
            
        Returns:
            Dict with 'email' and 'password', or None
        """
        all_accounts = self._load_all_raw()
        if not all_accounts:
            return None
        
        creds = all_accounts.get(email)
        if creds:
            log.info(f"[CredentialsManager] ✅ Loaded credentials for {email}")
            return {"email": email, "password": creds.get("password", "")}
        return None
    
    def has_credentials_for(self, email: str) -> bool:
        """Check if credentials exist for a specific email."""
        all_creds = self._load_all_raw()
        return bool(all_creds and email in all_creds)
    
    def delete_credentials_for(self, email: str) -> bool:
        """Delete stored credentials for a specific email.
        
        Removes only this email's entry, preserves others.
        
        Args:
            email: Email to delete credentials for
            
        Returns:
            True if deleted successfully
        """
        if not self._fernet:
            return False
        
        try:
            all_accounts = self._load_all_raw()
            if not all_accounts or email not in all_accounts:
                return False
            
            del all_accounts[email]
            log.info(f"[CredentialsManager] 🗑️ Deleted credentials for {email}")
            
            if not all_accounts:
                # No more accounts — delete the file entirely
                if self.storage_path.exists():
                    self.storage_path.unlink()
                return True
            
            # Re-save remaining accounts
            storage = {"accounts": all_accounts}
            json_bytes = json.dumps(storage).encode('utf-8')
            encrypted = self._fernet.encrypt(json_bytes)
            self.storage_path.write_bytes(encrypted)
            return True
            
        except Exception as e:
            log.error(f"[CredentialsManager] ❌ Failed to delete for {email}: {e}")
            return False
    
    def delete_credentials(self) -> bool:
        """Delete ALL stored credentials.
        
        Returns:
            True if deleted successfully
        """
        try:
            if self.storage_path.exists():
                self.storage_path.unlink()
                log.info("[CredentialsManager] ✅ All credentials deleted")
            return True
        except Exception as e:
            log.error(f"[CredentialsManager] ❌ Failed to delete: {e}")
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
