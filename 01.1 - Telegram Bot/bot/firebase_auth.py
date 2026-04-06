"""
Firebase Auth REST Client
=========================
Authenticate bot account via Firebase Auth REST API.
No Admin SDK needed — uses email/password sign-in.
Returns ID token for authenticated Firestore REST API calls.
"""

import os
import time
import requests
import logging

log = logging.getLogger("veo.bot.auth")


class FirebaseAuth:
    """Firebase Auth REST API client for bot authentication."""

    AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    REFRESH_URL = "https://securetoken.googleapis.com/v1/token"

    # Token refresh buffer (refresh 5 min before expiry)
    _REFRESH_BUFFER = 300

    def __init__(self, api_key: str = ""):
        self._email = os.environ.get("FIREBASE_BOT_EMAIL", "").strip()
        self._password = os.environ.get("FIREBASE_BOT_PASSWORD", "").strip()
        self._api_key = api_key.strip() if api_key else os.environ.get("FIREBASE_PRIMARY_API_KEY", "").strip()

        # Cached tokens
        self._id_token: str = ""
        self._refresh_token: str = ""
        self._token_expiry: float = 0
        self._uid: str = ""

    def get_id_token(self) -> str:
        """Get valid ID token (auto-refresh if expired).

        Returns:
            ID token string for Authorization header.

        Raises:
            RuntimeError: If authentication fails.
        """
        if self._id_token and time.time() < (self._token_expiry - self._REFRESH_BUFFER):
            return self._id_token

        # Try refresh first (faster, no password needed)
        if self._refresh_token:
            try:
                return self._refresh_id_token()
            except Exception:
                pass  # Fall through to full login

        return self._sign_in()

    def get_uid(self) -> str:
        """Get bot's Firebase UID (for audit logging)."""
        if not self._uid:
            self.get_id_token()  # Triggers login
        return self._uid

    def _sign_in(self) -> str:
        """Sign in with email/password → get ID token."""
        if not self._email or not self._password or not self._api_key:
            raise RuntimeError(
                "Missing FIREBASE_BOT_EMAIL, FIREBASE_BOT_PASSWORD, "
                "or FIREBASE_PRIMARY_API_KEY environment variables"
            )

        resp = requests.post(
            self.AUTH_URL,
            params={"key": self._api_key},
            json={
                "email": self._email,
                "password": self._password,
                "returnSecureToken": True,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            error = resp.json().get("error", {})
            msg = error.get("message", resp.text[:100])
            raise RuntimeError(f"Firebase Auth failed: {msg}")

        data = resp.json()
        self._id_token = data["idToken"]
        self._refresh_token = data["refreshToken"]
        self._token_expiry = time.time() + int(data.get("expiresIn", 3600))
        self._uid = data.get("localId", "")

        log.info(f"[AUTH] ✅ Signed in as {self._email} (UID: {self._uid[:8]}...)")
        return self._id_token

    def _refresh_id_token(self) -> str:
        """Refresh ID token using refresh token."""
        resp = requests.post(
            self.REFRESH_URL,
            params={"key": self._api_key},
            json={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            raise RuntimeError("Token refresh failed")

        data = resp.json()
        self._id_token = data["id_token"]
        self._refresh_token = data["refresh_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 3600))

        log.debug("[AUTH] 🔄 Token refreshed")
        return self._id_token

    def get_auth_headers(self) -> dict:
        """Get headers with Bearer token for REST API calls."""
        token = self.get_id_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
