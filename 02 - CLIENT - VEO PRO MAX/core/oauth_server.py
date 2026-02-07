"""
Google OAuth 2.0 Authorization Code Flow for VEO Pro Max.

Based on Antigravity-Manager implementation.
Handles OAuth authentication, token exchange, and auto-refresh.
"""

import asyncio
import json
import socket
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable
from pathlib import Path

import requests


# ==================== GOOGLE OAUTH CONFIG ====================
# Same credentials as Antigravity-Manager for compatibility
GOOGLE_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs"
]


# ==================== DATA CLASSES ====================

# Use canonical SubscriptionType from session.py
from core.session import SubscriptionType


@dataclass
class TokenResponse:
    """Response from Google OAuth token endpoint."""
    access_token: str
    expires_in: int
    token_type: str = "Bearer"
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    
    @property
    def expires_at(self) -> datetime:
        """Calculate expiration datetime."""
        return datetime.now().timestamp() + self.expires_in


@dataclass
class UserInfo:
    """User information from Google."""
    email: str
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    picture: Optional[str] = None
    
    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.given_name and self.family_name:
            return f"{self.given_name} {self.family_name}"
        return self.given_name or self.family_name or self.email.split("@")[0]


@dataclass
class OAuthResult:
    """Result of OAuth flow."""
    success: bool
    token_response: Optional[TokenResponse] = None
    user_info: Optional[UserInfo] = None
    error: Optional[str] = None


@dataclass 
class CallbackResult:
    """Result from OAuth callback."""
    success: bool
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


# ==================== OAUTH FUNCTIONS ====================

def get_auth_url(redirect_uri: str, state: str) -> str:
    """
    Generate Google OAuth authorization URL.
    
    Args:
        redirect_uri: Callback URL (e.g., http://localhost:PORT/oauth-callback)
        state: Random state for CSRF protection
        
    Returns:
        Full authorization URL to open in browser
    """
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",  # Important: get refresh_token
        "prompt": "consent",       # Force consent to get refresh_token
        "include_granted_scopes": "true",
        "state": state,
    }
    
    query = urllib.parse.urlencode(params)
    return f"{GOOGLE_AUTH_URL}?{query}"


def exchange_code(code: str, redirect_uri: str) -> TokenResponse:
    """
    Exchange authorization code for tokens.
    
    Args:
        code: Authorization code from callback
        redirect_uri: Same redirect_uri used in auth request
        
    Returns:
        TokenResponse with access_token and refresh_token
        
    Raises:
        Exception if exchange fails
    """
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    
    response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        token = TokenResponse(
            access_token=result["access_token"],
            expires_in=result.get("expires_in", 3600),
            token_type=result.get("token_type", "Bearer"),
            refresh_token=result.get("refresh_token"),
            scope=result.get("scope"),
        )
        
        print(f"[OAuth] Token exchange successful!")
        print(f"[OAuth] access_token: {token.access_token[:20]}...")
        print(f"[OAuth] refresh_token: {'✓' if token.refresh_token else '✗ Missing'}")
        
        if not token.refresh_token:
            print("[OAuth] ⚠️ Warning: No refresh_token. User may need to revoke access and retry.")
            
        return token
    else:
        error = response.text
        raise Exception(f"Token exchange failed: {error}")


def refresh_access_token(refresh_token: str) -> TokenResponse:
    """
    Refresh access_token using refresh_token.
    
    Args:
        refresh_token: Long-lived refresh token
        
    Returns:
        New TokenResponse with fresh access_token
        
    Raises:
        Exception if refresh fails
    """
    data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    
    print(f"[OAuth] Refreshing access token...")
    response = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        token = TokenResponse(
            access_token=result["access_token"],
            expires_in=result.get("expires_in", 3600),
            token_type=result.get("token_type", "Bearer"),
            # Note: refresh_token may not be returned on refresh
            refresh_token=result.get("refresh_token") or refresh_token,
        )
        
        print(f"[OAuth] Token refreshed! Expires in {token.expires_in}s")
        return token
    else:
        error = response.text
        raise Exception(f"Token refresh failed: {error}")


def get_user_info(access_token: str) -> UserInfo:
    """
    Get user info from Google.
    
    Args:
        access_token: Valid access token
        
    Returns:
        UserInfo with email, name, picture
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(GOOGLE_USERINFO_URL, headers=headers, timeout=15)
    
    if response.status_code == 200:
        data = response.json()
        return UserInfo(
            email=data.get("email", ""),
            name=data.get("name"),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
            picture=data.get("picture"),
        )
    else:
        raise Exception(f"Failed to get user info: {response.text}")


# ==================== CALLBACK SERVER ====================

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Handle GET request (OAuth callback)."""
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/oauth-callback":
            params = urllib.parse.parse_qs(parsed.query)
            
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]
            
            if error:
                self.server.callback_result = CallbackResult(
                    success=False,
                    error=error
                )
                self._send_error_page(error)
            elif code:
                # Verify state
                if state == self.server.expected_state:
                    self.server.callback_result = CallbackResult(
                        success=True,
                        code=code,
                        state=state
                    )
                    self._send_success_page()
                else:
                    self.server.callback_result = CallbackResult(
                        success=False,
                        error="State mismatch (CSRF protection)"
                    )
                    self._send_error_page("State mismatch")
            else:
                self.server.callback_result = CallbackResult(
                    success=False,
                    error="No authorization code received"
                )
                self._send_error_page("No code")
                
            self.server.should_stop = True
            
        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()
    
    def _send_success_page(self):
        """Send success HTML page."""
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>VEO Pro Max - Đăng nhập thành công</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }
        .container {
            text-align: center;
            padding: 60px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
        }
        .icon { font-size: 80px; margin-bottom: 20px; animation: bounce 0.5s; }
        @keyframes bounce {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.2); }
        }
        h1 { color: #4ade80; margin-bottom: 15px; }
        p { color: #94a3b8; }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">✅</div>
        <h1>Đăng nhập thành công!</h1>
        <p>Bạn có thể đóng tab này và quay lại ứng dụng.</p>
        <p style="margin-top: 10px; font-size: 12px;">Tab sẽ tự đóng sau 3 giây...</p>
    </div>
    <script>setTimeout(function() { window.close(); }, 3000);</script>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))
    
    def _send_error_page(self, error: str):
        """Send error HTML page."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>VEO Pro Max - Lỗi</title>
    <style>
        body {{
            font-family: 'Segoe UI', sans-serif;
            background: #1a1a2e;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{ text-align: center; padding: 40px; }}
        .icon {{ font-size: 60px; }}
        h1 {{ color: #ef4444; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">❌</div>
        <h1>Đăng nhập thất bại</h1>
        <p>{error}</p>
    </div>
</body>
</html>"""
        
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


class OAuthCallbackServer:
    """
    Localhost HTTP server for OAuth callback.
    
    Listens for Google OAuth redirect and captures authorization code.
    """
    
    def __init__(self):
        self.server: Optional[HTTPServer] = None
        self.port: int = 0
        self.state: str = ""
        self.redirect_uri: str = ""
        self._thread: Optional[threading.Thread] = None
        
    def start(self) -> str:
        """
        Start the callback server.
        
        Returns:
            redirect_uri to use in OAuth request
        """
        # Find available port
        self.port = self._find_free_port()
        self.state = self._generate_state()
        self.redirect_uri = f"http://localhost:{self.port}/oauth-callback"
        
        # Create server
        self.server = HTTPServer(("127.0.0.1", self.port), OAuthCallbackHandler)
        self.server.callback_result = None
        self.server.should_stop = False
        self.server.expected_state = self.state
        
        # Start in thread
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        
        print(f"[OAuthServer] Started on port {self.port}")
        return self.redirect_uri
    
    def _find_free_port(self) -> int:
        """Find an available port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    
    def _generate_state(self) -> str:
        """Generate random state for CSRF protection."""
        import uuid
        return str(uuid.uuid4())
    
    def _run_server(self):
        """Server loop."""
        while not self.server.should_stop:
            self.server.handle_request()
    
    def wait_for_callback(self, timeout: int = 300) -> CallbackResult:
        """
        Wait for OAuth callback.
        
        Args:
            timeout: Max seconds to wait
            
        Returns:
            CallbackResult with code or error
        """
        start = time.time()
        
        while time.time() - start < timeout:
            if self.server and self.server.callback_result:
                return self.server.callback_result
            time.sleep(0.5)
        
        return CallbackResult(success=False, error="Timeout waiting for callback")
    
    def stop(self):
        """Stop the server."""
        if self.server:
            self.server.should_stop = True
            # Wake up the server
            try:
                requests.get(f"http://localhost:{self.port}/health", timeout=1)
            except:
                pass
            self.server.server_close()
            self.server = None
            print("[OAuthServer] Stopped")
    
    @property
    def auth_url(self) -> str:
        """Get the full OAuth authorization URL."""
        return get_auth_url(self.redirect_uri, self.state)


# ==================== COMPLETE OAUTH FLOW ====================

def run_oauth_flow(timeout: int = 300) -> OAuthResult:
    """
    Run complete OAuth flow.
    
    1. Start localhost callback server
    2. Generate and open OAuth URL
    3. Wait for callback with code
    4. Exchange code for tokens
    5. Get user info
    
    Args:
        timeout: Max seconds to wait for user to complete login
        
    Returns:
        OAuthResult with tokens and user info
    """
    server = OAuthCallbackServer()
    
    try:
        # 1. Start server
        redirect_uri = server.start()
        auth_url = server.auth_url
        
        print(f"[OAuth] Opening browser for authentication...")
        print(f"[OAuth] URL: {auth_url[:80]}...")
        
        # 2. Open browser
        webbrowser.open(auth_url)
        
        # 3. Wait for callback
        print(f"[OAuth] Waiting for callback (timeout: {timeout}s)...")
        result = server.wait_for_callback(timeout=timeout)
        
        if not result.success:
            return OAuthResult(success=False, error=result.error)
        
        # 4. Exchange code for tokens
        print(f"[OAuth] Exchanging code for tokens...")
        token_response = exchange_code(result.code, redirect_uri)
        
        if not token_response.refresh_token:
            return OAuthResult(
                success=False,
                error="No refresh_token received. Please revoke app access in Google settings and try again."
            )
        
        # 5. Get user info
        print(f"[OAuth] Getting user info...")
        user_info = get_user_info(token_response.access_token)
        
        print(f"[OAuth] ✅ Success! Logged in as: {user_info.email}")
        
        return OAuthResult(
            success=True,
            token_response=token_response,
            user_info=user_info
        )
        
    except Exception as e:
        print(f"[OAuth] Error: {e}")
        return OAuthResult(success=False, error=str(e))
        
    finally:
        server.stop()


# ==================== TESTING ====================

if __name__ == "__main__":
    print("Testing OAuth flow...")
    result = run_oauth_flow(timeout=120)
    
    if result.success:
        print(f"\n✅ SUCCESS!")
        print(f"Email: {result.user_info.email}")
        print(f"Name: {result.user_info.display_name}")
        print(f"Access Token: {result.token_response.access_token[:30]}...")
        print(f"Refresh Token: {result.token_response.refresh_token[:30]}...")
    else:
        print(f"\n❌ FAILED: {result.error}")
