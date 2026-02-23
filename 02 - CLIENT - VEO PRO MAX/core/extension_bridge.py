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
        self._pending_request_conns: Dict[str, ExtensionConnection] = {}  # GAP #9: requestId → connection owner
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

        # Rate-limit stale header debug logs (prevent log spam)
        self._stale_log_times: Dict[str, float] = {}  # email → last log timestamp
        _STALE_LOG_INTERVAL = 60  # Log stale headers at most once per 60s per email

        # Frozen tab escalation tracking
        self._frozen_tab_counts: Dict[str, int] = {}  # email → consecutive frozen events
        self._frozen_tab_first_at: Dict[str, float] = {}  # email → timestamp of first frozen event in window
        self._FROZEN_ESCALATION_THRESHOLD = 3  # After N consecutive frozen events → escalate
        self._FROZEN_WINDOW = 300  # 5 min window for counting frozen events
        self._refresh_cooldown_times: Dict[str, float] = {}  # email → last refresh trigger timestamp (centralized)

        # Callbacks (set by AccountManager/AppController)
        self.on_headers_update: Optional[Callable] = None    # (email, headers, access_token)
        self.on_extension_connect: Optional[Callable] = None  # (email)
        self.on_extension_disconnect: Optional[Callable] = None  # (email)
        self.on_unregistered_connection: Optional[Callable] = None  # () — called when a new connection hasn't registered after delay
        self.on_readiness_token: Optional[Callable] = None  # (email, token) — cache trial-execute token
        self.on_account_logged_out: Optional[Callable] = None  # (email, reason) — account logout detected
        self.on_tab_dead: Optional[Callable] = None  # (email, reason) — tab declared dead after retries

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

    async def _trigger_refresh(self, email: str, reason: str, level: str = "lightweight"):
        """Centralized refresh trigger — single entry point for all callers.
        
        Consolidates scattered refresh triggers (Concurrency Analysis §15.3):
        - tab_frozen handler
        - heartbeat loop (missing content heartbeat)
        - refresh_manager (stale headers)
        
        Args:
            email: Account email
            reason: Human-readable reason for logging
            level: "lightweight" or "full"
        """
        # Global cooldown: 30s between ANY refresh attempt per email
        now = time.time()
        last = self._refresh_cooldown_times.get(email, 0)
        if now - last < 30:
            return  # Cooldown active — skip
        self._refresh_cooldown_times[email] = now
        # ★ Reset content heartbeat — prevent heartbeat_loop from detecting
        # stale pre-reload timestamp and triggering ANOTHER recovery
        self._content_heartbeats[email] = now

        log.info(f"[ExtensionBridge] 🔄 Refresh [{level}] for {email} — {reason}")

        try:
            if level == "full":
                await self.refresh_headers(email, timeout=10)
            else:
                await self.refresh_headers_lightweight(email, timeout=10)
        except Exception as e:
            log.debug(f"[ExtensionBridge] Refresh failed for {email}: {e}")

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

    def get_cached_headers(self, email: str, max_age_seconds: int = 180) -> Optional[Dict[str, str]]:
        """Get latest cached headers for an email (from auto-push).
        
        Args:
            email: Account email to look up.
            max_age_seconds: Max age in seconds before headers are considered stale.
                             Default 180 (3 minutes) — GAP #4: synced with Extension's
                             3-minute HEADER_REFRESH_ALARM cycle. Set 0 to skip freshness check.
        
        Returns:
            Headers dict if fresh, None if stale or not found.
        """
        for conn in self._connections:
            if email in conn.headers:
                # Freshness check
                if max_age_seconds > 0 and email in conn.headers_updated_at:
                    age = (datetime.now() - conn.headers_updated_at[email]).total_seconds()
                    if age > max_age_seconds:
                        # Rate-limit stale debug log: once per 60s per email
                        now_ts = time.time()
                        last_log = self._stale_log_times.get(email, 0)
                        if now_ts - last_log >= 60:
                            log.debug(
                                f"[ExtensionBridge] Cached headers for {email} are stale "
                                f"({age:.0f}s > {max_age_seconds}s)"
                            )
                            self._stale_log_times[email] = now_ts
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
            conn = self._find_connection(email)
            self._pending_requests[request_id] = future
            self._pending_request_conns[request_id] = conn  # GAP #9: tag with connection

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
                        # GAP #3: Let Extension handle tab reload (it has direct
                        # chrome.tabs.reload access). App only tracks count and
                        # resets counter — avoids double reload (11s wasted).
                        if count >= self._SHORT_TOKEN_RELOAD_THRESHOLD:
                            log.warning(
                                f"[ExtensionBridge] 🔄 Short token threshold reached for {email} — "
                                f"Extension will auto-reload tab (App skips duplicate reload)"
                            )
                            self._short_token_counts[email] = 0
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
                        # GAP #3: Let Extension handle tab reload (direct chrome.tabs.reload).
                        # App-side only tracks count — no duplicate reload.
                        if count >= self._SHORT_TOKEN_RELOAD_THRESHOLD:
                            log.warning(
                                f"[ExtensionBridge] 🔄 Short token threshold reached for {email} — "
                                f"Extension will auto-reload tab (App skips duplicate reload)"
                            )
                            self._short_token_counts[email] = 0
                    else:
                        log.warning(f"[ExtensionBridge] reCAPTCHA failed for {email}: {error}")
                    return None
            except asyncio.TimeoutError:
                log.error(f"[ExtensionBridge] reCAPTCHA request timed out for {email} ({timeout}s)")
                return None
            finally:
                self._pending_requests.pop(request_id, None)
                self._pending_request_conns.pop(request_id, None)  # GAP #9

    async def submit_prompt(
        self,
        email: str,
        endpoint: str,
        body: dict,
        needs_recaptcha: bool = True,
        timeout: float = 35.0,
    ) -> Optional[dict]:
        """Submit prompt via Extension — reCAPTCHA + API call from page context.

        Extension generates reCAPTCHA token and sends fetch() from the real
        labs.google page. Token is used immediately (<100ms), all browser
        headers (x-client-data, x-browser-*) are auto-added by Chrome.

        Args:
            email: Account email to submit for
            endpoint: Endpoint key (T2V, I2V_SINGLE, I2V_DUAL, R2V, T2I,
                      STATUS, UPSCALE_VIDEO, UPLOAD)
            body: Pre-built request body dict (WITHOUT recaptchaContext —
                  Extension adds fresh token). Must include clientContext
                  (sessionId, tool, projectId, paygateTier) and requests[].
            needs_recaptcha: Whether to generate reCAPTCHA token (default True)
            timeout: Max seconds to wait for response (default 35s —
                     reCAPTCHA 3-5s + API 2-10s + buffer)

        Returns:
            dict with keys: success, status, statusText, data, tokenLength, error
            or None if failed/timeout
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] No connection for {email} — cannot submit prompt")
            return None

        # Pre-warm: simulate activity if tab has been idle >60s
        last_hb = self._content_heartbeats.get(email, 0)
        if last_hb and (time.time() - last_hb) > 60:
            log.debug(f"[ExtensionBridge] Tab idle >60s for {email} — simulating activity before submit")
            try:
                await self.simulate_activity(email, timeout=3.0)
                await asyncio.sleep(0.5)
            except Exception:
                pass

        # Serialize submissions per account (same lock as reCAPTCHA)
        if email not in self._recaptcha_locks:
            self._recaptcha_locks[email] = asyncio.Lock()

        async with self._recaptcha_locks[email]:
            request_id = str(uuid.uuid4())
            future = asyncio.get_running_loop().create_future()
            conn = self._find_connection(email)
            if not conn:
                log.warning(f"[ExtensionBridge] Connection lost for {email} during submit_prompt")
                return None
            self._pending_requests[request_id] = future
            self._pending_request_conns[request_id] = conn

            try:
                await self._ws_send(conn, {
                    'action': 'submit_prompt',
                    'requestId': request_id,
                    'email': email,
                    'endpoint': endpoint,
                    'payload': {'body': body},
                    'needsRecaptcha': needs_recaptcha,
                })

                result = await asyncio.wait_for(future, timeout=timeout)

                success = result.get('success', False)
                status = result.get('status', 0)
                error = result.get('error', '')
                token_len = result.get('tokenLength', 0)

                if success:
                    log.info(
                        f"[ExtensionBridge] ✅ submit_prompt {endpoint} for {email}: "
                        f"HTTP {status} (token {token_len} chars)"
                    )
                    # Reset short token counter on success
                    self._short_token_counts[email] = 0
                    return result
                else:
                    # Check if it's a reCAPTCHA issue
                    if error and ('too short' in error.lower() or 'recaptcha' in error.lower()):
                        self._short_token_counts[email] = self._short_token_counts.get(email, 0) + 1
                        count = self._short_token_counts[email]
                        log.warning(
                            f"[ExtensionBridge] ❌ submit_prompt reCAPTCHA failed for {email}: "
                            f"{error} — consecutive #{count}"
                        )
                    else:
                        log.warning(
                            f"[ExtensionBridge] ❌ submit_prompt {endpoint} for {email}: "
                            f"HTTP {status} — {error}"
                        )
                    return result

            except asyncio.TimeoutError:
                log.error(
                    f"[ExtensionBridge] submit_prompt timed out for {email} "
                    f"({timeout}s) — endpoint={endpoint}"
                )
                return None
            finally:
                self._pending_requests.pop(request_id, None)
                self._pending_request_conns.pop(request_id, None)

    async def submit_upscale(
        self,
        email: str,
        body: dict,
        timeout: float = 35.0,
    ) -> Optional[dict]:
        """Submit upscale request via Extension page context.
        
        Reuses the submit_prompt handler in background.js with
        endpoint='UPSCALE_VIDEO'. Extension injects fresh reCAPTCHA token.
        
        Args:
            email: Account email
            body: Pre-built body from api_client.build_upscale_body()
            timeout: Max wait time
            
        Returns:
            dict with {success, status, data, error} or None on timeout
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] submit_upscale: no connection for {email}")
            return None
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        self._pending_request_conns[request_id] = conn
        
        try:
            await self._ws_send(conn, {
                'action': 'submit_prompt',
                'requestId': request_id,
                'email': email,
                'endpoint': 'UPSCALE_VIDEO',
                'payload': {'body': body},
                'needsRecaptcha': True,
            })
            
            result = await asyncio.wait_for(future, timeout=timeout)
            
            success = result.get('success', False)
            status = result.get('status', 0)
            error = result.get('error', '')
            
            if success:
                log.info(
                    f"[ExtensionBridge] ✅ submit_upscale for {email}: HTTP {status}"
                )
            else:
                log.warning(
                    f"[ExtensionBridge] ❌ submit_upscale for {email}: "
                    f"HTTP {status} — {error}"
                )
            return result
            
        except asyncio.TimeoutError:
            log.error(
                f"[ExtensionBridge] submit_upscale timed out for {email} ({timeout}s)"
            )
            return None
        finally:
            self._pending_requests.pop(request_id, None)
            self._pending_request_conns.pop(request_id, None)

    async def submit_status_check(
        self,
        email: str,
        body: dict,
        timeout: float = 20.0,
    ) -> Optional[dict]:
        """Submit status poll request via Extension page context.
        
        Reuses the submit_prompt handler in background.js with
        endpoint='STATUS'. No reCAPTCHA needed for polling.
        
        Args:
            email: Account email
            body: Pre-built body from api_client.build_status_body()
            timeout: Max wait time
            
        Returns:
            dict with {success, status, data, error} or None on timeout
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] submit_status_check: no connection for {email}")
            return None
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        self._pending_request_conns[request_id] = conn
        
        try:
            await self._ws_send(conn, {
                'action': 'submit_prompt',
                'requestId': request_id,
                'email': email,
                'endpoint': 'STATUS',
                'payload': {'body': body},
                'needsRecaptcha': False,
            })
            
            result = await asyncio.wait_for(future, timeout=timeout)
            
            success = result.get('success', False)
            if not success:
                log.debug(
                    f"[ExtensionBridge] submit_status_check for {email}: "
                    f"HTTP {result.get('status', 0)} — {result.get('error', '')}"
                )
            return result
            
        except asyncio.TimeoutError:
            log.debug(
                f"[ExtensionBridge] submit_status_check timed out for {email} ({timeout}s)"
            )
            return None
        finally:
            self._pending_requests.pop(request_id, None)
            self._pending_request_conns.pop(request_id, None)

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
                    if self.on_readiness_token:
                        try:
                            self.on_readiness_token(email, token)
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

    async def probe_browser_headers(self, email: str, timeout: float = 10.0) -> bool:
        """Probe for x-browser-validation by triggering a cross-origin fetch.

        Injects a script into the VEO page that makes a fetch to
        aisandbox-pa.googleapis.com. Chrome adds x-browser-validation
        to cross-origin requests, which the webRequest listener captures.

        Returns True if x-browser-validation was captured.
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
                'action': 'probe_browser_headers',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)
            has_validation = result.get('hasValidation', False)
            global_val = result.get('globalValidation')
            if has_validation:
                log.info(f"[ExtensionBridge] ✅ x-browser-validation captured for {email}")
            else:
                log.warning(f"[ExtensionBridge] ⚠️ x-browser-validation NOT captured after probe (globalValidation={global_val})")
            return has_validation
        except asyncio.TimeoutError:
            log.debug(f"[ExtensionBridge] Browser header probe timed out for {email}")
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
            # GAP #8: Cleanup stale state when tab is closed
            email = msg.get('email', '')
            log.info(f"[ExtensionBridge] Tab closed for {email} — cleaning up cached state")
            if email:
                # Clear cached data for this email on the connection
                conn.headers.pop(email, None)
                conn.headers_updated_at.pop(email, None)
                conn.access_tokens.pop(email, None)
                # Clear global state for this email
                self._content_heartbeats.pop(email, None)
                self._recaptcha_readiness.pop(email, None)
                self._short_token_counts.pop(email, None)
                self._frozen_tab_counts.pop(email, None)
                self._frozen_tab_first_at.pop(email, None)
                log.info(f"[ExtensionBridge] 🧹 Cleaned up all cached state for {email}")

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

            # Escalation tracking: count consecutive frozen events within window
            now_ts = time.time()
            first_at = self._frozen_tab_first_at.get(email, 0)
            if now_ts - first_at > self._FROZEN_WINDOW:
                # Reset window
                self._frozen_tab_counts[email] = 0
                self._frozen_tab_first_at[email] = now_ts

            self._frozen_tab_counts[email] = self._frozen_tab_counts.get(email, 0) + 1
            count = self._frozen_tab_counts[email]

            if count >= self._FROZEN_ESCALATION_THRESHOLD:
                # Escalated: multiple frozen events → tab is truly dead
                log.warning(
                    f"[ExtensionBridge] 💀 Tab DEAD for {email} "
                    f"({count} frozen events in {self._FROZEN_WINDOW}s) — browser restart needed"
                )
                # Only notify once per window
                if count == self._FROZEN_ESCALATION_THRESHOLD:
                    try:
                        if self.on_tab_dead:
                            self.on_tab_dead(email, f"Tab frozen {count}x in {self._FROZEN_WINDOW}s")
                    except Exception:
                        pass
            else:
                # ★ Suppress false frozen events caused by an in-progress reload.
                # After refresh_headers() reloads the tab, the old heartbeat timestamp
                # is stale → extension detects "frozen" → fires ANOTHER recovery.
                # If _trigger_refresh cooldown is still active, this frozen event
                # is a false positive from the reload, not a new freeze.
                last_refresh = self._refresh_cooldown_times.get(email, 0)
                if time.time() - last_refresh < 30:
                    log.debug(
                        f"[ExtensionBridge] 🥶 Tab frozen for {email} suppressed — "
                        f"refresh already in-progress ({time.time() - last_refresh:.0f}s ago)"
                    )
                else:
                    log.warning(
                        f"[ExtensionBridge] 🥶 Tab frozen for {email} "
                        f"(no heartbeat for {elapsed // 1000}s) — "
                        f"recovery attempt {count}/{self._FROZEN_ESCALATION_THRESHOLD}"
                    )
                    # Active recovery via centralized trigger
                    asyncio.ensure_future(self._trigger_refresh(
                        email,
                        f"frozen tab recovery {count}/{self._FROZEN_ESCALATION_THRESHOLD}",
                        level="lightweight" if count == 1 else "full"
                    ))

        elif action == 'recaptcha_ready':
            # Layer 1: Response to check_recaptcha_ready request
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'submit_prompt_result':
            # Response to submit_prompt — full API response from page context
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

        elif action == 'probe_browser_headers_result':
            # Response to probe_browser_headers request
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
            try:
                if self.on_account_logged_out:
                    self.on_account_logged_out(email, reason)
            except Exception:
                pass

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

        elif action == 'tab_dead':
            # Extension gave up reloading this tab (3 attempts failed in 5min)
            email = msg.get('email', '')
            attempts = msg.get('reloadAttempts', 0)
            log.error(
                f"[ExtensionBridge] 💀 Tab DEAD for {email} — "
                f"{attempts} reload attempts failed. Browser restart recommended."
            )
            # Reset frozen counters so escalation doesn't double-fire
            self._frozen_tab_counts.pop(email, None)
            self._frozen_tab_first_at.pop(email, None)
            try:
                if self.on_tab_dead:
                    self.on_tab_dead(email, f"Extension declared tab dead after {attempts} reload attempts")
            except Exception:
                pass

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
            
            # Fix 2 + GAP #9: Only resolve futures belonging to THIS connection
            # (previously cleared ALL futures, causing cross-connection errors)
            cleared = 0
            for req_id, owner_conn in list(self._pending_request_conns.items()):
                if owner_conn is conn:
                    future = self._pending_requests.get(req_id)
                    if future and not future.done():
                        future.set_result({'error': 'Extension disconnected', 'token': None})
                    self._pending_requests.pop(req_id, None)
                    self._pending_request_conns.pop(req_id, None)
                    cleared += 1
            if cleared:
                log.debug(f"[ExtensionBridge] Cleared {cleared} pending request(s) for disconnected connection")

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
                    
                    # Python-side content heartbeat check:
                    # If connected but no heartbeat for 120s+, try recovery
                    for email in conn.registered_emails:
                        last_hb = self._content_heartbeats.get(email, 0)
                        if last_hb and (time.time() - last_hb) > 120:
                            asyncio.ensure_future(self._trigger_refresh(
                                email,
                                f"content heartbeat missing {time.time() - last_hb:.0f}s",
                                level="lightweight"
                            ))
                    
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
