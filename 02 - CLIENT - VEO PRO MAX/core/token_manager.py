import logging

log = logging.getLogger(__name__)
"""
Token Manager for VEO Pro Max.

Handles access token tracking and expiry detection for all profiles.
Based on ACCOUNT_SESSION_MANAGEMENT.md specifications.

Tokens are refreshed via browser session (no OAuth).
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Callable


class TokenManager:
    """
    Manages access tokens for all profiles with expiry tracking.
    
    Token Lifecycle (from docs):
    - Access Token: ~60 min lifetime
    - Refresh Zone: After 50 min, flag for refresh
    - Refresh is handled by browser session re-login
    """
    
    REFRESH_BUFFER_SECONDS = 600  # Flag refresh 10 min before expiry
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
        log.info("[TokenManager] Started auto-refresh loop")
    
    def stop(self):
        """Stop the auto-refresh thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        log.info("[TokenManager] Stopped")
    
    def _refresh_loop(self):
        """Background loop to check token expiry."""
        while self._running:
            try:
                self._check_and_flag_expiring()
            except Exception as e:
                log.error(f"[TokenManager] Error in refresh loop: {e}")
            
            # Sleep for check interval
            for _ in range(self.CHECK_INTERVAL_SECONDS):
                if not self._running:
                    break
                time.sleep(1)
    
    def _check_and_flag_expiring(self):
        """Check all tokens and notify if expiring soon."""
        tokens = self._load_tokens()
        
        if not tokens:
            return
        
        now = datetime.now().timestamp()
        
        for email, token_data in tokens.items():
            expires_at = token_data.get("expires_at", 0)
            
            # Check if token needs refresh (10 min buffer)
            if expires_at - now < self.REFRESH_BUFFER_SECONDS:
                log.info(f"[TokenManager] Token expired/expiring for {email}, refreshing...")
                
                # Notify callback — browser session will handle refresh
                if "token_refreshed" in self._callbacks:
                    try:
                        self._callbacks["token_refreshed"](email)
                        log.info(f"[TokenManager] ✅ Token refreshed for {email}")
                    except Exception as e:
                        log.error(f"[TokenManager] ❌ Failed to refresh token for {email}: {e}")
    
    def _load_tokens(self) -> Dict:
        """Load tokens from file."""
        if not self.tokens_path.exists():
            return {}
        
        try:
            with open(self.tokens_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"[TokenManager] Error loading tokens: {e}")
            return {}
    
    def _save_tokens(self, tokens: Dict):
        """Save tokens to file."""
        try:
            with open(self.tokens_path, 'w', encoding='utf-8') as f:
                json.dump(tokens, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"[TokenManager] Error saving tokens: {e}")
    
    def save_token(self, email: str, access_token: str, expires_in: int = 3599):
        """Save/update token for an email (from browser session).
        
        Args:
            email: Account email
            access_token: The access token
            expires_in: Seconds until expiry (default ~1h)
        """
        tokens = self._load_tokens()
        tokens[email] = {
            "access_token": access_token,
            "expires_at": datetime.now().timestamp() + expires_in,
            "updated_at": datetime.now().isoformat(),
        }
        self._save_tokens(tokens)
    
    def get_valid_token(self, email: str) -> Optional[str]:
        """
        Get a valid access token for an email.
        
        Returns None if token is expired.
        
        Args:
            email: Email address of the profile
            
        Returns:
            Valid access_token or None if expired/not available
        """
        tokens = self._load_tokens()
        token_data = tokens.get(email)
        
        if not token_data:
            log.info(f"[TokenManager] No tokens found for {email}")
            return None
        
        access_token = token_data.get("access_token", "")
        expires_at = token_data.get("expires_at", 0)
        
        now = datetime.now().timestamp()
        
        # Check if still valid (with buffer)
        if expires_at - now > self.REFRESH_BUFFER_SECONDS:
            return access_token
        
        # Token expired — needs browser re-login
        log.info(f"[TokenManager] Token expired/expiring for {email}, needs browser refresh")
        return None
    
    def remove_tokens(self, email: str):
        """Remove tokens for an email."""
        tokens = self._load_tokens()
        
        if email in tokens:
            del tokens[email]
            self._save_tokens(tokens)
            log.info(f"[TokenManager] Removed tokens for {email}")
    
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
