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
import time
import uuid
from typing import Optional, Dict, Callable, Any

# websockets v16 State enum for connection health checks
try:
    from websockets.protocol import State as WsState
except ImportError:
    WsState = None
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
    last_activity: float = field(default_factory=time.time)  # For zombie detection


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

    # Layer 5: Minimum valid reCAPTCHA token length.
    # Real tokens are 2000+ chars; 330-char garbage tokens from
    # uninitialized grecaptcha must be rejected early.
    MIN_TOKEN_LENGTH = 1000

    def __init__(self, port: int = 8765):
        self._port = port
        self._server = None  # websockets server
        self._connections: list[ExtensionConnection] = []
        self._pending_requests: Dict[str, asyncio.Future] = {}  # requestId → Future
        self._recaptcha_locks: Dict[str, asyncio.Lock] = {}  # email → Lock (serialize per-account)
        self._heartbeat_task: Optional[asyncio.Task] = None  # Fix 5: heartbeat loop
        self._preserved_headers: Dict[str, Dict[str, str]] = {}  # Survive disconnects
        self._headers_debounce_timers: Dict[str, asyncio.TimerHandle] = {}  # email → pending timer
        self._headers_debounce_latest: Dict[str, tuple] = {}  # email → (headers, access_token)
        self._connection_events: Dict[str, asyncio.Event] = {}  # email → Event for wait_for_extension()

        # Content heartbeat tracking
        self._content_heartbeats: Dict[str, float] = {}  # email → last heartbeat timestamp
        self._recaptcha_readiness: Dict[str, bool] = {}  # email → True if reCAPTCHA is warm

        # Short token tracking: auto-reload tab after repeated garbage tokens
        self._short_token_counts: Dict[str, int] = {}  # email → consecutive short token count
        self._SHORT_TOKEN_RELOAD_THRESHOLD = 3

        # Callbacks (set by AccountManager/AppController)
        self.on_headers_update: Optional[Callable] = None    # (email, headers, access_token)
        self.on_extension_connect: Optional[Callable] = None  # (email)
        self.on_extension_disconnect: Optional[Callable] = None  # (email)
        self.on_unregistered_connection: Optional[Callable] = None  # () — called when a new connection hasn't registered after delay
        self._on_readiness_token: Optional[Callable] = None  # (email, token) — cache trial-execute token

    @property
    def port(self) -> int:
        return self._port

    def is_connected(self, email: str) -> bool:
        """Check if any Extension has registered this email AND connection is alive."""
        return any(
            email in conn.registered_emails and self._is_ws_open(conn.ws)
            for conn in self._connections
        )
    
    async def wait_for_extension(self, email: str, timeout: float = 30.0) -> bool:
        """Wait for Extension to connect/reconnect for a specific email.
        
        Uses asyncio.Event — zero CPU, instant wakeup on connect.
        Multiple callers waiting for same email share the same Event,
        all wake up simultaneously when Extension registers.
        
        Args:
            email: Account email to wait for.
            timeout: Max seconds to wait.
            
        Returns:
            True if connected within timeout, False if timeout.
        """
        if self.is_connected(email):
            return True
        
        # Reuse existing event if another worker is already waiting
        if email not in self._connection_events:
            self._connection_events[email] = asyncio.Event()
        event = self._connection_events[email]
        
        log.info(f"[ExtensionBridge] ⏳ Waiting for Extension reconnection: {email} (timeout={timeout}s)")
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            log.info(f"[ExtensionBridge] ✅ Extension reconnected: {email}")
            return True
        except asyncio.TimeoutError:
            log.warning(f"[ExtensionBridge] ⏰ Extension wait timed out: {email} ({timeout}s)")
            return False
        finally:
            # Cleanup — safe even if other waiters exist (they already got the event)
            self._connection_events.pop(email, None)
    
    @staticmethod
    def _is_ws_open(ws) -> bool:
        """Check if a WebSocket connection is open (websockets v16+ compatible).
        
        websockets v16 removed the `.open` property on ServerConnection.
        Use `.state` attribute with State.OPEN instead.
        """
        try:
            if hasattr(ws, 'state'):
                return ws.state.name == 'OPEN'
            # Fallback for older websockets versions
            if hasattr(ws, 'open'):
                return ws.open
            return False
        except Exception:
            return False

    def get_connected_emails(self) -> list[str]:
        """Get list of all registered emails across all connections."""
        emails = set()
        for conn in self._connections:
            emails.update(conn.registered_emails)
        return list(emails)

    async def assign_email(self, email: str) -> bool:
        """Tell an unregistered extension connection which email it belongs to.
        
        Finds the first connection that hasn't registered any emails yet,
        sends an assign_email message, and registers the email locally.
        
        This is the server-side fallback when content.js email detection fails
        (e.g. VEO page doesn't have __NEXT_DATA__ or avatar with email).
        
        Args:
            email: Account email to assign to a connection.
            
        Returns:
            True if assignment was sent, False if no unregistered connection.
        """
        # Skip if this email is already registered
        if self.is_connected(email):
            return True
        
        # Find an unregistered connection
        for conn in self._connections:
            if not conn.registered_emails:
                try:
                    await self._ws_send(conn, {
                        'action': 'assign_email',
                        'email': email,
                    })
                    conn.registered_emails.append(email)
                    log.info(f"[ExtensionBridge] 📧 Assigned email to extension: {email}")
                    if self.on_extension_connect:
                        try:
                            self.on_extension_connect(email)
                        except Exception:
                            pass
                    # Signal waiters (wait_for_extension)
                    event = self._connection_events.get(email)
                    if event:
                        event.set()
                    return True
                except Exception as e:
                    log.error(f"[ExtensionBridge] Failed to assign email: {e}")
                    return False
        
        log.debug(f"[ExtensionBridge] No unregistered connection available for {email}")
        return False

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
        # Fallback: preserved headers from last disconnected session
        if email in self._preserved_headers:
            log.debug(f"[ExtensionBridge] Using preserved headers for {email} (extension disconnected)")
            return self._preserved_headers[email]
        return None

    def get_cached_access_token(self, email: str) -> Optional[str]:
        """Get latest cached access token for an email."""
        for conn in self._connections:
            if email in conn.access_tokens:
                return conn.access_tokens[email]
        return None

    # Port fallback list: try primary → backup1 → backup2
    FALLBACK_PORTS = [8765, 8766, 8767]
    
    async def start(self):
        """Start WebSocket server (non-blocking, runs in background).
        
        Auto port fallback: tries ports 8765 → 8766 → 8767.
        If primary port is occupied (e.g. another instance), falls back automatically.
        """
        if not websockets:
            log.error("[ExtensionBridge] websockets library not installed! pip install websockets")
            return

        # Try ports in order until one works
        last_error = None
        for port in self.FALLBACK_PORTS:
            try:
                self._server = await ws_serve(
                    self._handle_connection,
                    '127.0.0.1',
                    port,
                    ping_interval=20,   # WebSocket-level ping every 20s
                    ping_timeout=10,    # Close if no pong within 10s
                    close_timeout=5,    # Clean close handshake timeout
                )
                self._port = port
                if port != self.FALLBACK_PORTS[0]:
                    log.warning(
                        f"[ExtensionBridge] ⚠️ Primary port {self.FALLBACK_PORTS[0]} occupied, "
                        f"using fallback port {port}"
                    )
                log.info(f"[ExtensionBridge] ✅ WebSocket server listening on ws://127.0.0.1:{port}")
                break
            except OSError as e:
                last_error = e
                log.warning(f"[ExtensionBridge] Port {port} unavailable: {e}")
                continue
        else:
            # All ports failed
            log.error(
                f"[ExtensionBridge] ❌ All ports {self.FALLBACK_PORTS} unavailable! "
                f"Last error: {last_error}"
            )
            return
        
        # Start app-level heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        """Stop WebSocket server and close all connections."""
        # Fix 5: Stop heartbeat
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        
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

    async def request_recaptcha(self, email: str, timeout: float = 25.0) -> Optional[str]:
        """Request reCAPTCHA token from Extension for a specific email.

        Sends request to Extension → Extension calls grecaptcha.execute()
        on the real VEO page → returns fresh token.
        
        Auto-simulates activity if tab has been idle >60s to prevent
        cold-start failures.

        Args:
            email: Account email to get token for
            timeout: Max seconds to wait for response

        Returns:
            reCAPTCHA token string, or None if failed
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] No connection for {email} — cannot request reCAPTCHA")
            return None

        # Pre-warm: simulate activity if tab has been idle >60s
        last_hb = self._content_heartbeats.get(email, 0)
        if last_hb and (time.time() - last_hb) > 60:
            log.debug(f"[ExtensionBridge] Tab idle >60s for {email} — simulating activity before reCAPTCHA")
            try:
                await self.simulate_activity(email, timeout=3.0)
                await asyncio.sleep(0.5)  # Brief pause after simulation
            except Exception:
                pass  # Best effort — don't block reCAPTCHA

        # Serialize reCAPTCHA requests per account to avoid race conditions
        if email not in self._recaptcha_locks:
            self._recaptcha_locks[email] = asyncio.Lock()

        async with self._recaptcha_locks[email]:
            request_id = str(uuid.uuid4())
            future = asyncio.get_running_loop().create_future()
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

                if token:
                    # Layer 5: Validate token length
                    if len(token) < self.MIN_TOKEN_LENGTH:
                        # Track consecutive short tokens
                        self._short_token_counts[email] = self._short_token_counts.get(email, 0) + 1
                        count = self._short_token_counts[email]
                        log.warning(
                            f"[ExtensionBridge] ❌ reCAPTCHA token too short for {email}: "
                            f"{len(token)} chars (min {self.MIN_TOKEN_LENGTH}) — "
                            f"consecutive #{count}"
                        )
                        # Auto-reload tab after threshold consecutive short tokens
                        if count >= self._SHORT_TOKEN_RELOAD_THRESHOLD:
                            log.warning(
                                f"[ExtensionBridge] 🔄 Triggering tab reload for {email} — "
                                f"{count} consecutive short tokens (reCAPTCHA widget broken)"
                            )
                            self._short_token_counts[email] = 0
                            # Reload via refresh_headers (reloads VEO tab)
                            asyncio.create_task(self._reload_tab_for_recaptcha(email))
                        return None
                    # Valid token — reset counter
                    self._short_token_counts[email] = 0
                    log.info(f"[ExtensionBridge] ✅ reCAPTCHA token for {email}: {len(token)} chars")
                    return token
                else:
                    # Check if this is a "too short" error from extension
                    # Extension sends token=null with error="Token too short (330 chars)"
                    if error and 'too short' in str(error).lower():
                        self._short_token_counts[email] = self._short_token_counts.get(email, 0) + 1
                        count = self._short_token_counts[email]
                        log.warning(
                            f"[ExtensionBridge] ❌ reCAPTCHA token too short for {email}: "
                            f"{error} — consecutive #{count}"
                        )
                        # Auto-reload tab after threshold consecutive short tokens
                        if count >= self._SHORT_TOKEN_RELOAD_THRESHOLD:
                            log.warning(
                                f"[ExtensionBridge] 🔄 Triggering tab reload for {email} — "
                                f"{count} consecutive short tokens (reCAPTCHA widget broken)"
                            )
                            self._short_token_counts[email] = 0
                            asyncio.create_task(self._reload_tab_for_recaptcha(email))
                    else:
                        log.warning(f"[ExtensionBridge] reCAPTCHA failed for {email}: {error}")
                    return None
            except asyncio.TimeoutError:
                log.error(f"[ExtensionBridge] reCAPTCHA request timed out for {email} ({timeout}s)")
                return None
            finally:
                self._pending_requests.pop(request_id, None)

    async def _reload_tab_for_recaptcha(self, email: str):
        """Reload VEO tab to re-initialize broken reCAPTCHA widget.
        
        Called when consecutive short tokens (330 chars) indicate the
        grecaptcha Enterprise widget is partially initialized.
        Sends refresh_headers to extension → chrome.tabs.reload → wait for re-init.
        """
        try:
            conn = self._find_connection(email)
            if not conn:
                log.debug(f"[ExtensionBridge] Cannot reload tab for {email}: no connection")
                return
            
            request_id = str(uuid.uuid4())
            future = asyncio.get_running_loop().create_future()
            self._pending_requests[request_id] = future
            
            await self._ws_send(conn, {
                'action': 'refresh_headers',
                'requestId': request_id,
                'email': email,
            })
            
            try:
                await asyncio.wait_for(future, timeout=10)
                log.info(
                    f"[ExtensionBridge] 🔄 Tab reloaded for {email} — "
                    f"waiting 6s for reCAPTCHA re-init"
                )
            except asyncio.TimeoutError:
                log.debug(f"[ExtensionBridge] Tab reload response timed out for {email}")
            finally:
                self._pending_requests.pop(request_id, None)
            
            # Wait for page + reCAPTCHA script to fully initialize
            await asyncio.sleep(6)
        except Exception as e:
            log.debug(f"[ExtensionBridge] Tab reload failed for {email}: {e}")

    async def reload_extension(self, email: str, timeout: float = 15.0) -> bool:
        """Hot-reload the extension from disk via chrome.runtime.reload().
        
        This reloads background.js + content.js without killing Chrome.
        The extension will disconnect its WebSocket, then reconnect after reload.
        
        Args:
            email: Account email to find the connection
            timeout: Max seconds to wait for reconnection after reload
            
        Returns:
            True if extension reloaded and reconnected successfully.
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] Cannot reload extension for {email}: no connection")
            return False
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        
        try:
            log.info(f"[ExtensionBridge] 🔄 Reloading extension for {email}...")
            await self._ws_send(conn, {
                'action': 'reload_extension',
                'requestId': request_id,
            })
            
            # Wait for ack (extension sends it before reload)
            try:
                await asyncio.wait_for(future, timeout=3)
            except asyncio.TimeoutError:
                pass  # Extension may have reloaded before sending ack
            finally:
                self._pending_requests.pop(request_id, None)
            
            # Wait for extension to reload and reconnect
            log.info(f"[ExtensionBridge] ⏳ Waiting for extension reconnection ({timeout}s)...")
            reconnected = await self.wait_for_extension(email, timeout=timeout)
            
            if reconnected:
                log.info(f"[ExtensionBridge] ✅ Extension reloaded and reconnected for {email}")
            else:
                log.warning(f"[ExtensionBridge] ⚠️ Extension reloaded but did not reconnect within {timeout}s")
            return reconnected
            
        except Exception as e:
            log.error(f"[ExtensionBridge] Extension reload failed for {email}: {e}")
            self._pending_requests.pop(request_id, None)
            return False

    async def check_recaptcha_ready(self, email: str, timeout: float = 10.0) -> bool:
        """Layer 1: Ask Extension if grecaptcha is ready on the VEO page.
        
        Extension checks:
        - typeof grecaptcha !== 'undefined'
        - grecaptcha.execute is a function
        - page is fully loaded (document.readyState === 'complete')
        
        This is deterministic — we get a real answer from the page
        instead of waiting a fixed timeout.
        
        Returns:
            True if grecaptcha is ready, False if not ready or timeout.
        """
        conn = self._find_connection(email)
        if not conn:
            log.info(f"[ExtensionBridge] reCAPTCHA check: no connection for {email}")
            return False
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        
        try:
            await self._ws_send(conn, {
                'action': 'check_recaptcha_ready',
                'requestId': request_id,
                'email': email,
            })
            result = await asyncio.wait_for(future, timeout=timeout)
            ready = result.get('ready', False)
            
            if ready:
                # Trial-execute returned a valid token — cache it
                token = result.get('token')
                details = result.get('details', {})
                token_len = details.get('tokenLength', 0)
                
                # Sanity check: if extension says "ready" but trial token is
                # 0 or too short, the widget is NOT actually ready.
                # This catches the old background.js bug where Promise chains
                # weren't properly serialized via chrome.scripting.
                if token_len == 0 or (token and len(token) < 500):
                    log.warning(
                        f"[ExtensionBridge] ⚠️ grecaptcha reports ready but trial token "
                        f"is {token_len} chars — overriding to NOT ready for {email}"
                    )
                    return False
                
                log.info(
                    f"[ExtensionBridge] ✅ grecaptcha ready for {email} "
                    f"(trial token: {token_len} chars)"
                )
                # Pass token to callback for caching in reCAPTCHA pool
                if token and len(token) > self.MIN_TOKEN_LENGTH:
                    if hasattr(self, '_on_readiness_token') and self._on_readiness_token:
                        try:
                            self._on_readiness_token(email, token)
                            log.debug(
                                f"[ExtensionBridge] Cached readiness-check token "
                                f"for {email} ({len(token)} chars)"
                            )
                        except Exception as e:
                            log.debug(f"[ExtensionBridge] Token cache callback failed: {e}")
            else:
                details = result.get('details', {})
                error = details.get('error', '')
                token_len = details.get('tokenLength', 0)
                log.info(
                    f"[ExtensionBridge] ⏳ grecaptcha NOT ready for {email}: "
                    f"loaded={details.get('grecaptchaLoaded', '?')} "
                    f"enterprise={details.get('enterpriseLoaded', '?')} "
                    f"execute={details.get('executeAvailable', '?')} "
                    f"page={details.get('pageLoaded', '?')} "
                    f"tokenLen={token_len}"
                    f"{f' error={error}' if error else ''}"
                )
            return ready
        except asyncio.TimeoutError:
            log.warning(
                f"[ExtensionBridge] check_recaptcha_ready TIMEOUT ({timeout}s) for {email} — "
                f"extension did not respond (tab may be frozen/suspended)"
            )
            return False
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
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws_send(conn, {
                'action': 'request_access_token',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            if isinstance(result, dict):
                return result.get('token')
            elif isinstance(result, str):
                return result  # Extension returned token directly
            return None
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
        future = asyncio.get_running_loop().create_future()
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
        future = asyncio.get_running_loop().create_future()
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
            log.warning(f"[ExtensionBridge] Header refresh timed out ({timeout}s) — non-fatal, CDP may capture headers directly")
            return 0
        finally:
            self._pending_requests.pop(request_id, None)

    async def refresh_headers_lightweight(self, email: str = None, timeout: float = 10.0) -> bool:
        """Lightweight header refresh — trigger fetch() instead of page reload.

        Content.js fires a small fetch to VEO API, which triggers
        onBeforeSendHeaders in background.js to capture fresh headers.
        Much faster and less disruptive than full page reload.

        Falls back to full refresh_headers() if lightweight fails.
        """
        if not self._connections:
            return False

        conn = self._find_connection(email) if email else self._connections[0]
        if not conn:
            return False

        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws_send(conn, {
                'action': 'refresh_headers_lightweight',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            success = result.get('success', False)
            if success:
                log.debug(f"[ExtensionBridge] 🔄 Lightweight header refresh OK for {email}")
                return True
            else:
                # Fall back to full reload
                log.debug(f"[ExtensionBridge] Lightweight refresh failed, falling back to full reload")
                await self.refresh_headers(email)
                return True
        except asyncio.TimeoutError:
            log.debug(f"[ExtensionBridge] Lightweight refresh timed out for {email}")
            return False
        finally:
            self._pending_requests.pop(request_id, None)

    async def simulate_activity(self, email: str, timeout: float = 5.0) -> bool:
        """Ask Extension to simulate mouse/scroll activity on the VEO tab.

        Useful before reCAPTCHA requests to wake up idle tabs and
        prevent Chrome from considering the page inactive.
        """
        conn = self._find_connection(email)
        if not conn:
            return False

        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._ws_send(conn, {
                'action': 'simulate_activity',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            return result.get('success', False)
        except (asyncio.TimeoutError, Exception):
            return False
        finally:
            self._pending_requests.pop(request_id, None)


    # ── WebSocket Connection Handler ────────────────────────────────────

    async def _handle_connection(self, ws):
        """Handle a new WebSocket connection (using websockets library)."""
        peer = ws.remote_address
        conn = ExtensionConnection(ws=ws)
        self._connections.append(conn)
        log.info(f"[ExtensionBridge] 🔌 Extension connected from {peer}")

        # Schedule delayed auto-assign check: if after 5s the connection
        # still hasn't registered an email, notify AppController so it can
        # assign one from known profiles. This handles late-connecting extensions.
        asyncio.ensure_future(self._delayed_assign_check(conn, peer))

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

    async def _delayed_assign_check(self, conn: ExtensionConnection, peer):
        """Wait, then fire callback if connection is still unregistered."""
        await asyncio.sleep(5)
        if conn in self._connections and not conn.registered_emails:
            log.info(f"[ExtensionBridge] ⏰ Connection from {peer} still unregistered after 5s")
            if self.on_unregistered_connection:
                try:
                    self.on_unregistered_connection()
                except Exception as e:
                    log.error(f"[ExtensionBridge] on_unregistered_connection callback error: {e}")

    async def _handle_message(self, conn: ExtensionConnection, msg: dict):
        """Process a message from the Extension."""
        conn.last_activity = time.time()  # Track for zombie detection
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
                # Signal waiters (wait_for_extension)
                event = self._connection_events.get(email)
                if event:
                    event.set()

        elif action == 'headers_update':
            email = msg.get('email', '')
            headers = msg.get('headers', {})
            access_token = msg.get('accessToken')

            if email:
                conn.headers[email] = headers
                conn.headers_updated_at[email] = datetime.now()
                if access_token:
                    conn.access_tokens[email] = access_token

                # Debounce: coalesce rapid updates (2s window per email)
                # Store latest data and schedule callback
                self._headers_debounce_latest[email] = (headers, access_token)
                
                # Cancel previous timer if exists
                if email in self._headers_debounce_timers:
                    self._headers_debounce_timers[email].cancel()
                
                def _fire_debounced(e=email):
                    self._headers_debounce_timers.pop(e, None)
                    latest = self._headers_debounce_latest.pop(e, None)
                    if latest and self.on_headers_update:
                        h, at = latest
                        try:
                            log.debug(f"[ExtensionBridge] Headers update for {e}: {list(h.keys())}")
                            self.on_headers_update(e, h, at)
                        except Exception as err:
                            log.error(f"[ExtensionBridge] on_headers_update callback error: {err}")
                
                try:
                    loop = asyncio.get_running_loop()
                    self._headers_debounce_timers[email] = loop.call_later(2.0, _fire_debounced)
                except RuntimeError:
                    # No event loop — fire immediately
                    _fire_debounced()

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

        elif action == 'content_heartbeat':
            # Content script is alive — track per-email
            email = msg.get('email', '')
            if email:
                self._content_heartbeats[email] = time.time()
                conn.last_activity = time.time()

        elif action == 'recaptcha_warmth':
            # Content script reports reCAPTCHA readiness
            email = msg.get('email', '')
            ready = msg.get('ready', False)
            if email:
                self._recaptcha_readiness[email] = ready
                conn.last_activity = time.time()
                if ready:
                    log.debug(f"[ExtensionBridge] 🔥 reCAPTCHA warm for {email}")

        elif action == 'tab_frozen':
            # Background detected frozen tab (missed heartbeats)
            email = msg.get('email', '')
            elapsed = msg.get('elapsedMs', 0)
            log.warning(
                f"[ExtensionBridge] 🥶 Tab frozen for {email} "
                f"(no heartbeat for {elapsed // 1000}s) — auto-reloading"
            )

        elif action == 'recaptcha_ready':
            # Layer 1: Response to check_recaptcha_ready request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'headers_refreshed':
            # Response to refresh_headers request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'headers_refreshed_lightweight':
            # Response to refresh_headers_lightweight request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'activity_simulated':
            # Response to simulate_activity request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'account_logged_out':
            email = msg.get('email', '')
            reason = msg.get('reason', 'unknown')
            log.warning(f"[ExtensionBridge] 🔴 Account LOGGED OUT: {email} (reason: {reason})")
            # Emit event for engine/UI to handle
            try:
                from core.event_bus import emit_event, EventType
                emit_event(EventType.ACCOUNT_STATUS_CHANGED, {
                    "email": email,
                    "status": "logged_out",
                    "reason": reason,
                }, source="extension_bridge")
            except Exception:
                pass  # EventType might not have ACCOUNT_STATUS_CHANGED

        elif action == 'tab_discarded':
            email = msg.get('email', '')
            log.warning(
                f"[ExtensionBridge] ⚠️ Tab discarded by Memory Saver: {email} — "
                f"Extension will auto-reload"
            )

        elif action == 'tab_alive':
            # Response to check_tab_alive request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'extension_reloaded':
            # Response to reload_extension request (sent just before chrome.runtime.reload())
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'zombie_tab':
            tab_id = msg.get('tabId')
            log.warning(f"[ExtensionBridge] ⚠️ Zombie tab detected: tab {tab_id} — no email after 30s")

    async def _disconnect(self, conn: Optional[ExtensionConnection], peer):
        """Clean up a disconnected Extension."""
        if conn and conn in self._connections:
            # Preserve last-known good headers before removing connection
            for email, headers in conn.headers.items():
                if headers:
                    self._preserved_headers[email] = headers.copy()
                    log.debug(f"[ExtensionBridge] Preserved {len(headers)} headers for {email} on disconnect")
            
            self._connections.remove(conn)

            for email in conn.registered_emails:
                log.info(f"[ExtensionBridge] 📧 Extension disconnected: {email}")
                if self.on_extension_disconnect:
                    try:
                        self.on_extension_disconnect(email)
                    except Exception:
                        pass
            
            # Fix 2: Resolve all pending futures with error so callers don't hang
            for req_id, future in list(self._pending_requests.items()):
                if not future.done():
                    future.set_result({'error': 'Extension disconnected', 'token': None})
            self._pending_requests.clear()

            try:
                # Temporarily suppress websockets logger during close to prevent
                # cascading errors when event loop transport is already destroyed
                ws_logger = logging.getLogger("websockets")
                old_level = ws_logger.level
                ws_logger.setLevel(logging.CRITICAL + 1)  # Suppress all
                try:
                    await conn.ws.close()
                finally:
                    ws_logger.setLevel(old_level)
            except Exception:
                pass

    def _find_connection(self, email: str) -> Optional[ExtensionConnection]:
        """Find the Extension connection handling this email."""
        for conn in self._connections:
            if email in conn.registered_emails and self._is_ws_open(conn.ws):
                return conn
        # Fallback: any open connection
        for conn in self._connections:
            if self._is_ws_open(conn.ws):
                return conn
        return None

    async def _ws_send(self, conn: ExtensionConnection, data: dict):
        """Send a JSON message via WebSocket."""
        payload = json.dumps(data)
        # Fix 1: Catch broken pipe / connection errors
        try:
            await conn.ws.send(payload)
        except Exception as e:
            log.warning(f"[ExtensionBridge] Send failed ({e}), cleaning up connection")
            await self._disconnect(conn, "send-error")
            raise
    
    async def check_tab_alive(self, email: str, timeout: float = 5.0) -> bool:
        """Check if the VEO tab for this email is still alive (not discarded/frozen).
        
        Sends a lightweight ping via Extension → content.js.
        Returns False if tab is discarded/dead/unresponsive.
        """
        conn = self._find_connection(email)
        if not conn:
            return False
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        
        try:
            await self._ws_send(conn, {
                'action': 'check_tab_alive',
                'requestId': request_id,
                'email': email,
            })
            result = await asyncio.wait_for(future, timeout=timeout)
            return result.get('alive', False)
        except (asyncio.TimeoutError, Exception):
            return False
        finally:
            self._pending_requests.pop(request_id, None)

    async def _heartbeat_loop(self):
        """App-level heartbeat — send ping + detect zombie connections.
        
        Sends ping every 15s. Also checks last_activity to detect
        zombie connections (WS alive but Extension unresponsive for 45s+).
        
        With content.js sending heartbeats every 20s, missing 2 consecutive
        heartbeats (45s) indicates a frozen or dead connection.
        """
        while True:
            try:
                await asyncio.sleep(15)
                dead = []
                for conn in list(self._connections):
                    if not self._is_ws_open(conn.ws):
                        dead.append(conn)
                        continue
                    
                    # Zombie detection: no activity for 45s+ (reduced from 90s
                    # because content.js now sends heartbeats every 20s)
                    since_last = time.time() - conn.last_activity
                    if since_last > 45:
                        log.warning(
                            f"[ExtensionBridge] ⚠️ Zombie connection: "
                            f"{conn.registered_emails} (no activity {since_last:.0f}s)"
                        )
                        dead.append(conn)
                        continue
                    
                    try:
                        await conn.ws.send(json.dumps({'action': 'ping'}))
                    except Exception:
                        dead.append(conn)
                
                # Clean up dead/zombie connections
                for conn in dead:
                    log.info(f"[ExtensionBridge] 💀 Dead/zombie connection cleaned up")
                    await self._disconnect(conn, "heartbeat-dead")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[ExtensionBridge] Heartbeat error: {e}")
                await asyncio.sleep(5)


    # ── Status ──────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get bridge status for DevConsole."""
        now = time.time()
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
            'content_heartbeats': {
                email: f"{now - ts:.0f}s ago"
                for email, ts in self._content_heartbeats.items()
            },
            'recaptcha_readiness': dict(self._recaptcha_readiness),
        }

    def is_recaptcha_ready(self, email: str) -> bool:
        """Check if reCAPTCHA is warm/ready for an email (from content.js reports)."""
        return self._recaptcha_readiness.get(email, False)
