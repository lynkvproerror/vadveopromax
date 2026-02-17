"""
VEO Pro Max — Extension Bridge (WebSocket Server)

Bridges the Chrome Extension to the Python app via WebSocket.
Extension intercepts real x-browser-* headers + reCAPTCHA tokens from VEO web,
sends them to this server, which then feeds them to AccountManager.

Protocol:
  Extension → App:
    {"action": "register", "email": "...", "tabId": 123}
    {"action": "headers_update", "email": "...", "headers": {...}, "accessToken": "..."}
    {"action": "recaptcha_token", "requestId": "...", "token": "...", "error": null}
    {"action": "access_token", "requestId": "...", "token": "...", "email": "..."}
    {"action": "tab_closed", "email": "...", "tabId": 123}
    {"action": "pong"}

  App → Extension:
    {"action": "request_recaptcha", "requestId": "...", "email": "..."}
    {"action": "request_headers", "email": "..."}
    {"action": "request_access_token", "requestId": "...", "email": "..."}
    {"action": "ping"}

Dependencies: websockets
"""

import asyncio
import json
import logging
import uuid
from typing import Optional, Dict, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

try:
    import websockets
    from websockets.asyncio.server import serve as ws_serve
except ImportError:
    websockets = None
    ws_serve = None

log = logging.getLogger(__name__)


# ── Extension Connection State ──────────────────────────────────────────

@dataclass
class ExtensionConnection:
    """State for a single Extension WebSocket connection."""
    ws: Any  # websockets.WebSocketServerProtocol
    registered_emails: list = field(default_factory=list)
    headers: Dict[str, Dict[str, str]] = field(default_factory=dict)  # email → headers
    headers_updated_at: Dict[str, datetime] = field(default_factory=dict)  # email → timestamp
    access_tokens: Dict[str, str] = field(default_factory=dict)  # email → token
    connected_at: datetime = field(default_factory=datetime.now)


# ── Extension Bridge ────────────────────────────────────────────────────

class ExtensionBridge:
    """WebSocket server bridging Chrome Extension to VEO Pro Max app.

    Usage:
        bridge = ExtensionBridge(port=8765)
        bridge.on_headers_update = lambda email, headers: ...
        await bridge.start()  # runs forever in background

        # Request reCAPTCHA token on demand:
        token = await bridge.request_recaptcha("user@gmail.com", timeout=15)
    """

    def __init__(self, port: int = 8765):
        self._port = port
        self._server = None  # websockets server
        self._connections: list[ExtensionConnection] = []
        self._pending_requests: Dict[str, asyncio.Future] = {}  # requestId → Future

        # Callbacks (set by AccountManager/AppController)
        self.on_headers_update: Optional[Callable] = None    # (email, headers, access_token)
        self.on_extension_connect: Optional[Callable] = None  # (email)
        self.on_extension_disconnect: Optional[Callable] = None  # (email)

    @property
    def port(self) -> int:
        return self._port

    def is_connected(self, email: str) -> bool:
        """Check if any Extension has registered this email."""
        return any(
            email in conn.registered_emails
            for conn in self._connections
        )

    def get_connected_emails(self) -> list[str]:
        """Get list of all registered emails across all connections."""
        emails = set()
        for conn in self._connections:
            emails.update(conn.registered_emails)
        return list(emails)

    def get_cached_headers(self, email: str, max_age_seconds: int = 300) -> Optional[Dict[str, str]]:
        """Get latest cached headers for an email (from auto-push).
        
        Args:
            email: Account email to look up.
            max_age_seconds: Max age in seconds before headers are considered stale.
                             Default 300 (5 minutes). Set 0 to skip freshness check.
        
        Returns:
            Headers dict if fresh, None if stale or not found.
        """
        for conn in self._connections:
            if email in conn.headers:
                # Freshness check
                if max_age_seconds > 0 and email in conn.headers_updated_at:
                    age = (datetime.now() - conn.headers_updated_at[email]).total_seconds()
                    if age > max_age_seconds:
                        log.debug(
                            f"[ExtensionBridge] Cached headers for {email} are stale "
                            f"({age:.0f}s > {max_age_seconds}s)"
                        )
                        return None
                return conn.headers[email]
        return None

    def get_cached_access_token(self, email: str) -> Optional[str]:
        """Get latest cached access token for an email."""
        for conn in self._connections:
            if email in conn.access_tokens:
                return conn.access_tokens[email]
        return None

    async def start(self):
        """Start WebSocket server (non-blocking, runs in background)."""
        if not websockets:
            log.error("[ExtensionBridge] websockets library not installed! pip install websockets")
            return

        self._server = await ws_serve(
            self._handle_connection,
            '127.0.0.1',
            self._port,
        )
        log.info(f"[ExtensionBridge] ✅ WebSocket server listening on ws://127.0.0.1:{self._port}")

    async def stop(self):
        """Stop WebSocket server and close all connections."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        for conn in self._connections:
            try:
                await conn.ws.close()
            except Exception:
                pass
        self._connections.clear()
        log.info("[ExtensionBridge] Server stopped")

    async def request_recaptcha(self, email: str, timeout: float = 15.0) -> Optional[str]:
        """Request reCAPTCHA token from Extension for a specific email.

        Sends request to Extension → Extension calls grecaptcha.execute()
        on the real VEO page → returns fresh token.

        Args:
            email: Account email to get token for
            timeout: Max seconds to wait for response

        Returns:
            reCAPTCHA token string, or None if failed
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] No Extension connected for {email}")
            return None

        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws_send(conn, {
                'action': 'request_recaptcha',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            token = result.get('token')
            error = result.get('error')

            if error:
                log.warning(f"[ExtensionBridge] reCAPTCHA failed for {email}: {error}")
                return None

            if token:
                log.info(f"[ExtensionBridge] ✅ reCAPTCHA token for {email}: {len(token)} chars")
            return token

        except asyncio.TimeoutError:
            log.error(f"[ExtensionBridge] reCAPTCHA request timed out for {email} ({timeout}s)")
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    async def request_access_token(self, email: str, timeout: float = 10.0) -> Optional[str]:
        """Request access token extraction from Extension.

        Extension extracts from __NEXT_DATA__ on the real VEO page.
        """
        conn = self._find_connection(email)
        if not conn:
            return None

        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws_send(conn, {
                'action': 'request_access_token',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            return result.get('token')
        except asyncio.TimeoutError:
            log.error(f"[ExtensionBridge] Access token request timed out for {email}")
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    async def request_headers(self, email: str, timeout: float = 5.0) -> Optional[Dict[str, str]]:
        """Request current headers from Extension."""
        conn = self._find_connection(email)
        if not conn:
            return None

        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws_send(conn, {
                'action': 'request_headers',
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            return result.get('headers')
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    async def refresh_headers(self, email: str = None, timeout: float = 15.0) -> int:
        """Trigger VEO tab reload to capture fresh headers.

        Sends refresh_headers to Extension → Extension reloads matching VEO tabs
        → webRequest captures fresh headers → auto-pushed via headers_update.

        Args:
            email: Optional email to refresh only matching tabs. None = all tabs.
            timeout: Max seconds to wait for response.

        Returns:
            Number of tabs reloaded, or 0 if failed.
        """
        if not self._connections:
            log.warning("[ExtensionBridge] No Extension connected for refresh")
            return 0

        conn = self._connections[0]  # Any connection
        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws_send(conn, {
                'action': 'refresh_headers',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            tabs_reloaded = result.get('tabsReloaded', 0)
            log.info(f"[ExtensionBridge] 🔄 Refreshed headers: {tabs_reloaded} tab(s) reloaded")
            return tabs_reloaded
        except asyncio.TimeoutError:
            log.error(f"[ExtensionBridge] Header refresh timed out ({timeout}s)")
            return 0
        finally:
            self._pending_requests.pop(request_id, None)


    # ── WebSocket Connection Handler ────────────────────────────────────

    async def _handle_connection(self, ws):
        """Handle a new WebSocket connection (using websockets library)."""
        peer = ws.remote_address
        conn = ExtensionConnection(ws=ws)
        self._connections.append(conn)
        log.info(f"[ExtensionBridge] 🔌 Extension connected from {peer}")

        try:
            async for message in ws:
                try:
                    msg = json.loads(message)
                    await self._handle_message(conn, msg)
                except json.JSONDecodeError:
                    log.warning(f"[ExtensionBridge] Invalid JSON: {str(message)[:100]}")
        except websockets.exceptions.ConnectionClosed as e:
            log.debug(f"[ExtensionBridge] Connection closed from {peer}: {e}")
        except Exception as e:
            log.error(f"[ExtensionBridge] Unexpected error from {peer}: {e}")
        finally:
            await self._disconnect(conn, peer)

    async def _handle_message(self, conn: ExtensionConnection, msg: dict):
        """Process a message from the Extension."""
        action = msg.get('action', '')

        if action == 'register':
            email = msg.get('email', '')
            if email and email not in conn.registered_emails:
                conn.registered_emails.append(email)
                log.info(f"[ExtensionBridge] 📧 Extension registered: {email}")
                if self.on_extension_connect:
                    try:
                        self.on_extension_connect(email)
                    except Exception:
                        pass

        elif action == 'headers_update':
            email = msg.get('email', '')
            headers = msg.get('headers', {})
            access_token = msg.get('accessToken')

            if email:
                conn.headers[email] = headers
                conn.headers_updated_at[email] = datetime.now()
                if access_token:
                    conn.access_tokens[email] = access_token

                log.debug(
                    f"[ExtensionBridge] Headers update for {email}: "
                    f"{list(headers.keys())}"
                )

                if self.on_headers_update:
                    try:
                        self.on_headers_update(email, headers, access_token)
                    except Exception as e:
                        log.error(f"[ExtensionBridge] on_headers_update callback error: {e}")

        elif action == 'recaptcha_token':
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'access_token':
            request_id = msg.get('requestId')
            email = msg.get('email', '')
            token = msg.get('token')
            
            # Cache the token regardless
            if email and token:
                conn.access_tokens[email] = token
            
            if request_id and request_id in self._pending_requests:
                # Response to a specific request
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)
            elif email and token and self.on_headers_update:
                # Unsolicited push (e.g. on WS connect) — notify app
                log.info(f"[ExtensionBridge] 🔑 Unsolicited access token for {email}")
                try:
                    self.on_headers_update(email, {}, token)
                except Exception:
                    pass

        elif action == 'headers':
            # Response to request_headers — also resolves as pending request
            email = msg.get('email', '')
            headers = msg.get('headers', {})
            access_token = msg.get('accessToken')

            if email:
                conn.headers[email] = headers
                if access_token:
                    conn.access_tokens[email] = access_token

            # Check if this is a response to a pending request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'tab_closed':
            email = msg.get('email', '')
            log.info(f"[ExtensionBridge] Tab closed for {email}")

        elif action == 'pong':
            pass  # Keepalive response

        elif action == 'headers_refreshed':
            # Response to refresh_headers request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

    async def _disconnect(self, conn: Optional[ExtensionConnection], peer):
        """Clean up a disconnected Extension."""
        if conn and conn in self._connections:
            self._connections.remove(conn)

            for email in conn.registered_emails:
                log.info(f"[ExtensionBridge] 📧 Extension disconnected: {email}")
                if self.on_extension_disconnect:
                    try:
                        self.on_extension_disconnect(email)
                    except Exception:
                        pass

            try:
                await conn.ws.close()
            except Exception:
                pass

    def _find_connection(self, email: str) -> Optional[ExtensionConnection]:
        """Find the Extension connection handling this email."""
        for conn in self._connections:
            if email in conn.registered_emails:
                return conn
        # Fallback: any connected extension
        if self._connections:
            return self._connections[0]
        return None

    async def _ws_send(self, conn: ExtensionConnection, data: dict):
        """Send a JSON message via WebSocket."""
        payload = json.dumps(data)
        await conn.ws.send(payload)


    # ── Status ──────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get bridge status for DevConsole."""
        return {
            'running': self._server is not None,
            'port': self._port,
            'connections': len(self._connections),
            'emails': self.get_connected_emails(),
            'cached_headers': {
                email: list(headers.keys())
                for conn in self._connections
                for email, headers in conn.headers.items()
            },
        }
