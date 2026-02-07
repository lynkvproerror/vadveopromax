"""
Token Manager for VEO Pro Max.

Handles automatic token refresh for all profiles.
Based on ACCOUNT_SESSION_MANAGEMENT.md specifications.
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Callable

from core.oauth_server import refresh_access_token, TokenResponse


class TokenManager:
    """
    Manages OAuth tokens for all profiles with auto-refresh.
    
    Token Lifecycle (from docs):
    - Access Token: ~60 min lifetime
    - Refresh Zone: After 50 min, refresh before expiry
    - Refresh Token: Long-lived, used to get new access tokens
    """
    
    REFRESH_BUFFER_SECONDS = 600  # Refresh 10 min before expiry (50 min mark)
    CHECK_INTERVAL_SECONDS = 60   # Check every minute
    
    def __init__(self, tokens_path: Optional[Path] = None):
        """
        Initialize token manager.
        
        Args:
            tokens_path: Path to tokens.json file.
                        Defaults to config/tokens.json
        """
        if tokens_path is None:
            tokens_path = Path(__file__).parent.parent / "config" / "tokens.json"
        
        self.tokens_path = Path(tokens_path)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: Dict[str, Callable] = {}
        
        # Ensure directory exists
        self.tokens_path.parent.mkdir(parents=True, exist_ok=True)
    
    def set_callback(self, on_token_refreshed: Optional[Callable[[str], None]] = None):
        """Set callback for token refresh events."""
        if on_token_refreshed:
            self._callbacks["token_refreshed"] = on_token_refreshed
    
    def start(self):
        """Start the auto-refresh background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()
        print("[TokenManager] Started auto-refresh loop")
    
    def stop(self):
        """Stop the auto-refresh thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("[TokenManager] Stopped")
    
    def _refresh_loop(self):
        """Background loop to check and refresh tokens."""
        while self._running:
            try:
                self._check_and_refresh_all()
            except Exception as e:
                print(f"[TokenManager] Error in refresh loop: {e}")
            
            # Sleep for check interval
            for _ in range(self.CHECK_INTERVAL_SECONDS):
                if not self._running:
                    break
                time.sleep(1)
    
    def _check_and_refresh_all(self):
        """Check all tokens and refresh if needed."""
        tokens = self._load_tokens()
        
        if not tokens:
            return
        
        now = datetime.now().timestamp()
        updated = False
        
        for email, token_data in tokens.items():
            expires_at = token_data.get("expires_at", 0)
            refresh_token = token_data.get("refresh_token", "")
            
            # Check if token needs refresh (10 min buffer)
            if expires_at - now < self.REFRESH_BUFFER_SECONDS:
                if refresh_token:
                    print(f"[TokenManager] Token expiring soon for {email}, refreshing...")
                    
                    try:
                        new_token = refresh_access_token(refresh_token)
                        
                        # Update token data
                        token_data["access_token"] = new_token.access_token
                        token_data["expires_at"] = new_token.expires_at
                        token_data["updated_at"] = datetime.now().isoformat()
                        
                        # If new refresh_token provided, update it
                        if new_token.refresh_token:
                            token_data["refresh_token"] = new_token.refresh_token
                        
                        updated = True
                        print(f"[TokenManager] ✅ Refreshed token for {email}")
                        
                        # Notify callback
                        if "token_refreshed" in self._callbacks:
                            self._callbacks["token_refreshed"](email)
                            
                    except Exception as e:
                        print(f"[TokenManager] ❌ Failed to refresh token for {email}: {e}")
        
        if updated:
            self._save_tokens(tokens)
    
    def _load_tokens(self) -> Dict:
        """Load tokens from file."""
        if not self.tokens_path.exists():
            return {}
        
        try:
            with open(self.tokens_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[TokenManager] Error loading tokens: {e}")
            return {}
    
    def _save_tokens(self, tokens: Dict):
        """Save tokens to file."""
        try:
            with open(self.tokens_path, 'w', encoding='utf-8') as f:
                json.dump(tokens, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[TokenManager] Error saving tokens: {e}")
    
    def get_valid_token(self, email: str) -> Optional[str]:
        """
        Get a valid access token for an email.
        
        If token is expired or expiring soon, refreshes it first.
        
        Args:
            email: Email address of the profile
            
        Returns:
            Valid access_token or None if not available
        """
        tokens = self._load_tokens()
        token_data = tokens.get(email)
        
        if not token_data:
            print(f"[TokenManager] No tokens found for {email}")
            return None
        
        access_token = token_data.get("access_token", "")
        expires_at = token_data.get("expires_at", 0)
        refresh_token = token_data.get("refresh_token", "")
        
        now = datetime.now().timestamp()
        
        # Check if still valid (with buffer)
        if expires_at - now > self.REFRESH_BUFFER_SECONDS:
            return access_token
        
        # Need to refresh
        if not refresh_token:
            print(f"[TokenManager] No refresh_token for {email}")
            return None
        
        print(f"[TokenManager] Token expired/expiring for {email}, refreshing...")
        
        try:
            new_token = refresh_access_token(refresh_token)
            
            # Update stored tokens
            token_data["access_token"] = new_token.access_token
            token_data["expires_at"] = new_token.expires_at
            token_data["updated_at"] = datetime.now().isoformat()
            
            if new_token.refresh_token:
                token_data["refresh_token"] = new_token.refresh_token
            
            tokens[email] = token_data
            self._save_tokens(tokens)
            
            print(f"[TokenManager] ✅ Token refreshed for {email}")
            return new_token.access_token
            
        except Exception as e:
            print(f"[TokenManager] ❌ Refresh failed for {email}: {e}")
            return None
    
    def remove_tokens(self, email: str):
        """Remove tokens for an email."""
        tokens = self._load_tokens()
        
        if email in tokens:
            del tokens[email]
            self._save_tokens(tokens)
            print(f"[TokenManager] Removed tokens for {email}")
    
    def get_all_emails(self) -> list:
        """Get list of all emails with stored tokens."""
        tokens = self._load_tokens()
        return list(tokens.keys())


# Global token manager instance
_token_manager: Optional[TokenManager] = None


def get_token_manager() -> TokenManager:
    """Get or create global TokenManager instance."""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager


def init_token_manager(tokens_path: Optional[Path] = None) -> TokenManager:
    """Initialize and start the token manager."""
    global _token_manager
    _token_manager = TokenManager(tokens_path)
    _token_manager.start()
    return _token_manager
