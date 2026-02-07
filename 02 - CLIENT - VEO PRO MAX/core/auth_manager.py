"""
VEO Pro Max - Auth Manager

Reference: ACCOUNT_SESSION_MANAGEMENT.md
Role: Token storage/loading, expiry checks, auto-extract from browser
"""

from typing import Optional, Callable, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession, SubscriptionType, PaygateTier
from config.constants import TokenLifetime


class AuthManager:
    """Manages authentication tokens for VEO accounts.
    
    Features:
    - Token storage/loading from file
    - Bearer token expiry checks (60s buffer)
    - reCAPTCHA token age checks (80s threshold)
    - Token extraction from Playwright browser
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self._storage_dir = storage_dir or Path.home() / ".veoauto" / "sessions"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        
        self._sessions: Dict[str, AccountSession] = {}
    
    def get_session_file(self, email: str) -> Path:
        """Get session file path for email."""
        safe_email = re.sub(r'[^a-zA-Z0-9]', '_', email)
        return self._storage_dir / f"{safe_email}.json"
    
    def save_session(self, session: AccountSession) -> bool:
        """Save session to file.
        
        Returns True if saved successfully.
        """
        try:
            file_path = self.get_session_file(session.email)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2)
            
            self._sessions[session.email] = session
            return True
        except Exception:
            return False
    
    def load_session(self, email: str) -> Optional[AccountSession]:
        """Load session from file.
        
        Returns None if not found or expired.
        """
        # Check cache first
        if email in self._sessions:
            return self._sessions[email]
        
        file_path = self.get_session_file(email)
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            session = AccountSession.from_dict(data)
            self._sessions[email] = session
            return session
        except Exception:
            return None
    
    def get_all_sessions(self) -> list[AccountSession]:
        """Get all saved sessions."""
        sessions = []
        for file_path in self._storage_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                session = AccountSession.from_dict(data)
                sessions.append(session)
            except Exception:
                continue
        return sessions
    
    def delete_session(self, email: str) -> bool:
        """Delete session file."""
        try:
            file_path = self.get_session_file(email)
            if file_path.exists():
                file_path.unlink()
            
            if email in self._sessions:
                del self._sessions[email]
            
            return True
        except Exception:
            return False
    
    def get_bearer_token(self, session: AccountSession) -> Optional[str]:
        """Get valid bearer token.
        
        Returns None if expired.
        Uses 60s buffer before actual expiry.
        """
        buffer = timedelta(seconds=60)
        if datetime.now() >= (session.token_expires - buffer):
            return None
        
        return session.access_token
    
    def get_recaptcha_token(self, session: AccountSession) -> Optional[str]:
        """Get valid reCAPTCHA token.
        
        Returns None if older than 80 seconds.
        """
        if session.needs_recaptcha_refresh:
            return None
        
        return session.recaptcha_token
    
    def is_token_expired(self, session: AccountSession) -> bool:
        """Check if access token is expired (with buffer)."""
        return session.is_token_expired
    
    def needs_recaptcha_refresh(self, session: AccountSession) -> bool:
        """Check if reCAPTCHA needs refresh."""
        return session.needs_recaptcha_refresh
    
    def update_access_token(
        self,
        email: str,
        token: str,
        expires_in: int = TokenLifetime.ACCESS_TOKEN
    ):
        """Update access token for a session."""
        session = self._sessions.get(email)
        if session:
            session.access_token = token
            session.token_expires = datetime.now() + timedelta(seconds=expires_in)
            self.save_session(session)
    
    def update_recaptcha_token(self, email: str, token: str):
        """Update reCAPTCHA token for a session."""
        session = self._sessions.get(email)
        if session:
            session.update_recaptcha(token)
            self.save_session(session)
    
    # === PLAYWRIGHT EXTRACTION ===
    
    def extract_tokens_from_page_data(self, next_data: dict) -> Optional[AccountSession]:
        """Extract tokens from __NEXT_DATA__ JSON.
        
        This is typically extracted from the aistudio.google.com page.
        
        Args:
            next_data: Parsed __NEXT_DATA__ JSON object
        
        Returns:
            AccountSession if extraction successful
        """
        try:
            # Navigate to the auth data
            props = next_data.get("props", {})
            page_props = props.get("pageProps", {})
            user_data = page_props.get("user", {})
            
            email = user_data.get("email", "")
            access_token = user_data.get("accessToken", "")
            
            # Token expiry - typically 1 hour
            token_expires = datetime.now() + timedelta(hours=1)
            
            if not email or not access_token:
                return None
            
            return AccountSession(
                email=email,
                access_token=access_token,
                token_expires=token_expires,
            )
        except Exception:
            return None
    
    def parse_sku_from_response(self, response_data: dict) -> tuple[SubscriptionType, PaygateTier, int]:
        """Parse SKU info from API response.
        
        Returns (subscription_type, paygate_tier, credits)
        """
        sku = SubscriptionType.UNKNOWN
        tier = PaygateTier.UNKNOWN
        credits = 0
        
        try:
            if "subscriptionType" in response_data:
                sku = SubscriptionType(response_data["subscriptionType"])
        except ValueError:
            pass
        
        try:
            if "paygateTier" in response_data:
                tier = PaygateTier(response_data["paygateTier"])
        except ValueError:
            pass
        
        credits = response_data.get("credits", 0)
        
        return sku, tier, credits
    
    # === UNIFIED TOKEN EXTRACTION ===
    
    async def extract_all_from_browser(
        self,
        profile_path: str,
        headless: bool = True,
    ) -> Optional[AccountSession]:
        """
        Extract all tokens from browser and create session.
        
        Uses TokenExtractor to get:
        - Access Token
        - reCAPTCHA Token
        - x-browser-validation header
        - x-client-data header
        
        Args:
            profile_path: Chrome profile directory
            headless: Run browser headless
            
        Returns:
            AccountSession with all tokens, or None if failed
        """
        from core.token_extractor import TokenExtractor
        
        extractor = TokenExtractor()
        await extractor.initialize()
        
        try:
            tokens = await extractor.extract_all(profile_path, headless=headless)
            if not tokens:
                return None
            
            # Create session
            session = AccountSession(
                email=tokens.email,
                access_token=tokens.access_token,
                token_expires=datetime.now() + timedelta(seconds=tokens.expires_in),
            )
            session.update_recaptcha(tokens.recaptcha_token)
            
            # Store browser headers for later use
            self._browser_headers = {
                "x-browser-validation": tokens.browser_validation,
                "x-client-data": tokens.client_data,
            }
            
            # Save session
            self.save_session(session)
            self._sessions[session.email] = session
            
            return session
            
        finally:
            await extractor.close()
    
    def get_browser_headers(self) -> Dict[str, str]:
        """Get stored browser headers from last extraction."""
        return getattr(self, '_browser_headers', {})
