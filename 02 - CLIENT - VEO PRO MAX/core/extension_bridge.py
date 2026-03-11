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
from collections import deque

# websockets v16 State enum for connection health checks
try:
    from websockets.protocol import State as WsState
except ImportError:
    WsState = None
from dataclasses import dataclass, field
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import MIN_VALID_XCD

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
    # Real tokens are 1742-2169+ chars; garbage tokens from
    # uninitialized grecaptcha must be rejected early.
    MIN_TOKEN_LENGTH = 1500

    def __init__(self, port: int = 8765):
        self._port = port
        self._server = None  # websockets server
        self._connections: list[ExtensionConnection] = []
        self._pending_requests: Dict[str, asyncio.Future] = {}  # requestId → Future
        self._pending_request_conns: Dict[str, ExtensionConnection] = {}  # GAP #9: requestId → connection owner
        self._recaptcha_locks: Dict[str, asyncio.Lock] = {}  # email → Lock (serialize per-account)
        self._heartbeat_task: Optional[asyncio.Task] = None  # Fix 5: heartbeat loop
        self._watchdog_task: Optional[asyncio.Task] = None    # Auto-restart watchdog
        self._restart_count: int = 0                          # Consecutive restart attempts
        self._MAX_RESTARTS = 5                                # Max consecutive restarts before giving up
        self._stopping = False                                # True when stop() is called
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

        # Round-trip timing: track when each request was sent
        self._pending_request_times: Dict[str, float] = {}  # requestId → time.time() when sent
        self._pending_request_actions: Dict[str, str] = {}  # requestId → action name
        self._pending_request_emails: Dict[str, str] = {}  # requestId → email

        # ── Debug message log (ring buffer for DevConsole) ──
        self._message_log: deque = deque(maxlen=500)  # {dir, action, email, ts, payload_preview}
        
        # Health summary: periodic aggregated log instead of per-heartbeat spam
        self._last_health_log: float = 0  # timestamp of last health summary log
        self._HEALTH_LOG_INTERVAL = 60  # Log health summary every 60s

        # ── Fix B: Request dedup for check_recaptcha_ready ──
        # Prevents N foremen × M checks = N*M concurrent WebSocket requests
        self._check_ready_inflight: Dict[str, asyncio.Task] = {}  # email → running Task
        self._check_ready_cache: Dict[str, tuple] = {}  # email → (result: bool, timestamp)

        # Callbacks (set by AccountManager/AppController)
        self.on_headers_update: Optional[Callable] = None    # (email, headers, access_token)
        self.on_extension_connect: Optional[Callable] = None  # (email)
        self.on_extension_disconnect: Optional[Callable] = None  # (email)
        self.on_unregistered_connection: Optional[Callable] = None  # () — called when a new connection hasn't registered after delay
        self.on_readiness_token: Optional[Callable] = None  # (email, token) — cache trial-execute token
        self.on_account_logged_out: Optional[Callable] = None  # (email, reason) — account logout detected
        self.on_tab_dead: Optional[Callable] = None  # (email, reason) — tab declared dead after retries
        self.on_extension_lost: Optional[Callable] = None  # () — all connections lost for extended period

        # Extension-lost detection state
        self._had_connections = False  # True once at least one connection registered
        self._connections_lost_at: float = 0  # Timestamp when connections dropped to zero
        self._EXTENSION_LOST_TIMEOUT = 60  # Wait 60s before firing on_extension_lost
        self._extension_lost_fired = False  # Prevent re-firing until reconnected

    @property
    def port(self) -> int:
        return self._port

    def is_connected(self, email: str) -> bool:
        """Check if any Extension has registered this email AND connection is alive."""
        return any(
            email in conn.registered_emails and self._is_ws_open(conn.ws)
            for conn in self._connections
        )
    
    def is_recaptcha_healthy(self, email: str) -> bool:
        """Check if reCAPTCHA is currently healthy for this account.
        
        Unhealthy = consecutive short token count >= threshold.
        Used by PA3 fair-share to exclude dead accounts from average,
        and by upscale queue for failover decisions.
        """
        return self._short_token_counts.get(email, 0) < self._SHORT_TOKEN_RELOAD_THRESHOLD
    
    def get_consecutive_recaptcha_failures(self, email: str) -> int:
        """Get number of consecutive reCAPTCHA short-token failures."""
        return self._short_token_counts.get(email, 0)
    
    def is_submit_ready(self, email: str) -> tuple:
        """Instant real-time readiness check. No WebSocket call.
        
        Uses cached data from content heartbeats + header auto-push.
        Returns (ready: bool, reason: str).
        
        Checks:
        1. Extension connected (WebSocket alive)
        2. x-client-data ≥ MIN_VALID_XCD (Chrome Variations ready)
        3. reCAPTCHA warm (content heartbeat reports ready)
        """
        from config.constants import MIN_VALID_XCD
        
        # Check 1: Extension connected?
        if not self.is_connected(email):
            return (False, "extension_disconnected")
        
        # Check 2: x-client-data ≥ 50?
        headers = self.get_cached_headers(email, max_age_seconds=0)  # any age OK
        xcd = (headers or {}).get('x-client-data', '') or ''
        if len(xcd) < MIN_VALID_XCD:
            return (False, f"xcd_short ({len(xcd)} chars)")
        
        # Check 3: reCAPTCHA warm? (from content heartbeat)
        if not self._recaptcha_readiness.get(email, False):
            return (False, "recaptcha_cold")
        
        return (True, "ok")
    
    async def trigger_hard_navigation(self, email: str) -> bool:
        """Force navigate tab to VEO URL — nuclear recovery for stuck reCAPTCHA.
        
        Used when lightweight refresh (refresh_headers) fails to recover the
        reCAPTCHA widget. Full page navigation forces Chrome to re-download
        and re-initialize the grecaptcha Enterprise widget.
        
        Returns True if navigation succeeded.
        """
        VEO_URL = "https://labs.google/fx/vi/tools/flow"
        log.warning(
            f"[ExtensionBridge] 🔄 Hard navigation for {email} → {VEO_URL} "
            f"(reCAPTCHA recovery)"
        )
        result = await self.navigate_to_url(email, VEO_URL, timeout=35.0)
        if result and result.get('success'):
            # Reset short token counter — give the new page a fresh start
            self._short_token_counts[email] = 0
            log.info(
                f"[ExtensionBridge] ✅ Hard navigation complete for {email} "
                f"(load time: {result.get('loadTime', '?')}s)"
            )
            return True
        else:
            log.error(
                f"[ExtensionBridge] ❌ Hard navigation failed for {email}: "
                f"{(result or {}).get('error', 'no response')}"
            )
            return False
    
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
        
        log.debug(f"[ExtensionBridge] ⏳ Waiting for Extension reconnection: {email} (timeout={timeout}s)")
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            log.debug(f"[ExtensionBridge] ✅ Extension reconnected: {email}")
            return True
        except asyncio.TimeoutError:
            log.debug(f"[ExtensionBridge] ⏰ Extension wait timed out: {email} ({timeout}s)")
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

        # Suppress verbose websockets logs including harmless handshake probe errors
        # (Extension sometimes probes the port before completing HTTP handshake)
        logging.getLogger("websockets").setLevel(logging.CRITICAL)
        logging.getLogger("websockets.server").setLevel(logging.CRITICAL)

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
                    max_size=50 * 1024 * 1024,  # 50MB — 4K image upscale returns ~10-15MB base64
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
        # Start server watchdog (auto-restart on crash/port loss)
        self._watchdog_task = asyncio.create_task(self._server_watchdog())
        self._restart_count = 0
        self._stopping = False

    async def stop(self):
        """Stop WebSocket server and close all connections."""
        self._stopping = True
        
        # Stop watchdog
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
        
        # Fix 5: Stop heartbeat (properly await to avoid 'Task destroyed' warning)
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
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

    def cancel_pending_requests(self):
        """Cancel all pending requests without stopping the server or connections.
        
        Called when engine stops (Dừng button) to flush in-flight requests.
        Extension + WebSocket server stay alive for instant restart.
        """
        cancelled = 0
        for request_id, future in list(self._pending_requests.items()):
            if not future.done():
                future.cancel()
                cancelled += 1
        self._pending_requests.clear()
        self._pending_request_conns.clear()
        self._pending_request_times.clear()
        self._pending_request_actions.clear()
        self._pending_request_emails.clear()
        if cancelled:
            log.info(f"[ExtensionBridge] Cancelled {cancelled} pending request(s) (server still running)")

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
                self._cleanup_request_timing(request_id)
                self._pending_requests.pop(request_id, None)
                self._pending_request_conns.pop(request_id, None)  # GAP #9

    async def request_gemini_key(self, email: str, timeout: float = 30.0) -> Optional[str]:
        """Request Gemini API key provisioning via Extension.

        Extension navigates to AI Studio, runs gRPC-web JS to list/create
        projects and API keys, then returns the key.

        Args:
            email: Account email to provision key for
            timeout: Max seconds to wait (default 30s — includes page navigation)

        Returns:
            API key string (AIza...) or None if failed
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] No connection for {email} — cannot provision Gemini key")
            return None

        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        self._pending_request_conns[request_id] = conn

        try:
            await self._ws_send(conn, {
                'action': 'provision_gemini_key',
                'requestId': request_id,
                'email': email,
            })

            result = await asyncio.wait_for(future, timeout=timeout)

            if result.get('success') and result.get('key', '').startswith('AIza'):
                source = result.get('source', 'unknown')
                key = result['key']
                log.info(f"[ExtensionBridge] 🔑 Gemini key {source} for {email}: {key[:10]}...")
                return key
            else:
                error = result.get('error', 'unknown')
                msg = result.get('msg', '')
                log.warning(f"[ExtensionBridge] Gemini key provision failed for {email}: {error} — {msg}")
                return None
        except asyncio.TimeoutError:
            log.error(f"[ExtensionBridge] Gemini key request timed out for {email} ({timeout}s)")
            return None
        except Exception as e:
            log.error(f"[ExtensionBridge] Gemini key request error for {email}: {e}")
            return None
        finally:
            self._cleanup_request_timing(request_id)
            self._pending_requests.pop(request_id, None)
            self._pending_request_conns.pop(request_id, None)

    async def navigate_to_url(
        self, email: str, url: str, timeout: float = 35.0
    ) -> Optional[dict]:
        """Navigate the Extension tab to a specific URL.
        
        Uses chrome.tabs.update (extension-level) for clean navigation.
        Waits for page load to complete (document.readyState === 'complete').
        
        Args:
            email: Account email to identify the tab.
            url: Target URL to navigate to.
            timeout: Max seconds to wait for navigation + load.
            
        Returns:
            dict with {success, loadTime, url, timedOut} or None if failed.
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] navigate_to_url: no connection for {email}")
            return None
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        self._pending_request_conns[request_id] = conn
        
        try:
            log.info(f"[ExtensionBridge] 📍 Navigating {email} to: {url}")
            await self._ws_send(conn, {
                'action': 'navigate_tab',
                'requestId': request_id,
                'email': email,
                'url': url,
            })
            
            result = await asyncio.wait_for(future, timeout=timeout)
            
            if result.get('success'):
                log.info(
                    f"[ExtensionBridge] ✅ Navigation complete for {email}: "
                    f"{result.get('loadTime', '?')}s"
                )
            else:
                error = result.get('error', 'unknown')
                log.warning(
                    f"[ExtensionBridge] ❌ Navigation failed for {email}: {error}"
                )
            return result
            
        except asyncio.TimeoutError:
            log.error(
                f"[ExtensionBridge] navigate_to_url timed out for {email} ({timeout}s)"
            )
            return None
        finally:
            self._cleanup_request_timing(request_id)
            self._pending_requests.pop(request_id, None)
            self._pending_request_conns.pop(request_id, None)

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

        # NOTE: x-client-data is NOT checked here because Extension-based submit
        # uses page-context fetch — Chrome auto-adds the real x-client-data header.
        # The cached value (from CDP) may be 8 chars but the actual request has the full header.

        # Guard: ALWAYS simulate activity before submit (prevent bot detection)
        try:
            await self.simulate_activity(email, timeout=3.0)
            await asyncio.sleep(0.3)
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
                    # Guard 3: Validate token length even on success
                    if token_len > 0 and token_len < self.MIN_TOKEN_LENGTH:
                        log.warning(
                            f"[ExtensionBridge] ⚠️ submit_prompt {endpoint} for {email}: "
                            f"HTTP {status} SUCCESS but token only {token_len} chars "
                            f"(need ≥{self.MIN_TOKEN_LENGTH}) — may be rejected by Google"
                        )
                        self._short_token_counts[email] = self._short_token_counts.get(email, 0) + 1
                    else:
                        log.info(
                            f"[ExtensionBridge] ✅ submit_prompt {endpoint} for {email}: "
                            f"HTTP {status} (token {token_len} chars)"
                        )
                        # Reset short token counter on success with valid token
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
                self._cleanup_request_timing(request_id)
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
        
        # NOTE: x-client-data NOT checked — Extension page-context fetch auto-adds it
        
        # Guard: ALWAYS simulate activity before upscale (prevent bot detection)
        try:
            await self.simulate_activity(email, timeout=3.0)
            await asyncio.sleep(0.3)
        except Exception:
            pass
        
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
            token_len = result.get('tokenLength', 0)
            
            if success:
                # Guard 3: Validate token length on upscale success
                if token_len > 0 and token_len < self.MIN_TOKEN_LENGTH:
                    log.warning(
                        f"[ExtensionBridge] ⚠️ submit_upscale for {email}: "
                        f"HTTP {status} but token only {token_len} chars "
                        f"(need ≥{self.MIN_TOKEN_LENGTH})"
                    )
                else:
                    log.info(
                        f"[ExtensionBridge] ✅ submit_upscale for {email}: "
                        f"HTTP {status} (token {token_len} chars)"
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
            self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
            self._pending_requests.pop(request_id, None)
            self._pending_request_conns.pop(request_id, None)

    async def relay_fetch(
        self,
        email: str,
        url: str,
        method: str = 'POST',
        body: dict = None,
        headers: dict = None,
        credentials: str = 'include',
        timeout: float = 15.0,
    ) -> Optional[dict]:
        """Relay a generic fetch() through Extension's page context.
        
        Executes fetch() in the VEO tab via chrome.scripting.executeScript.
        Cookies are auto-attached by the browser (same origin for labs.google).
        
        Use cases:
        - TRPC calls (project.createProject, project.getProjects)
        - checkAppAvailability (aisandbox-pa)
        - Any API that requires browser cookies/headers
        
        Args:
            email: Account email to identify the tab
            url: Full URL to fetch
            method: HTTP method (GET, POST, etc.)
            body: Request body dict (will be JSON.stringify'd)
            headers: Additional headers dict
            credentials: Fetch credentials mode ('include' for cookies)
            timeout: Max seconds to wait for response
            
        Returns:
            dict with {success, status, data, error} or None on timeout
        """
        conn = self._find_connection(email)
        if not conn:
            log.warning(f"[ExtensionBridge] relay_fetch: no connection for {email}")
            return None
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        self._pending_request_conns[request_id] = conn
        
        try:
            await self._ws_send(conn, {
                'action': 'relay_fetch',
                'requestId': request_id,
                'email': email,
                'url': url,
                'method': method,
                'body': body,
                'headers': headers or {},
                'credentials': credentials,
            })
            
            result = await asyncio.wait_for(future, timeout=timeout)
            
            success = result.get('success', False)
            status = result.get('status', 0)
            
            if success:
                log.debug(
                    f"[ExtensionBridge] ✅ relay_fetch for {email}: "
                    f"HTTP {status} → {url[:80]}"
                )
            else:
                error = result.get('error', '')
                log.warning(
                    f"[ExtensionBridge] ❌ relay_fetch for {email}: "
                    f"HTTP {status} — {error} → {url[:80]}"
                )
            return result
            
        except asyncio.TimeoutError:
            log.error(
                f"[ExtensionBridge] relay_fetch timed out for {email} "
                f"({timeout}s) → {url[:80]}"
            )
            return None
        finally:
            self._cleanup_request_timing(request_id)
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
                self._cleanup_request_timing(request_id)
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
                self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
            self._pending_requests.pop(request_id, None)
            return False

    async def check_recaptcha_ready(self, email: str, timeout: float = 10.0) -> bool:
        """Layer 1: Ask Extension if grecaptcha is ready on the VEO page.
        
        Deduplicated: concurrent calls for same email share one WebSocket request.
        Cached: results valid for 3 seconds to avoid redundant checks.
        """
        import time as _time
        _CACHE_TTL = 3.0  # seconds
        
        # ── Cache hit: return recent result without WebSocket call ──
        cached = self._check_ready_cache.get(email)
        if cached and (_time.time() - cached[1]) < _CACHE_TTL:
            return cached[0]
        
        # ── In-flight dedup: if another caller is already checking, piggyback ──
        inflight = self._check_ready_inflight.get(email)
        if inflight and not inflight.done():
            try:
                return await asyncio.wait_for(asyncio.shield(inflight), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return False
        
        # ── No inflight: create the actual check task ──
        task = asyncio.ensure_future(self._do_check_recaptcha_ready(email, timeout))
        self._check_ready_inflight[email] = task
        try:
            result = await task
            # Cache the result
            self._check_ready_cache[email] = (result, _time.time())
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError):
            self._check_ready_cache[email] = (False, _time.time())
            return False
        finally:
            self._check_ready_inflight.pop(email, None)
    
    async def _do_check_recaptcha_ready(self, email: str, timeout: float = 10.0) -> bool:
        """Internal: actual WebSocket check for reCAPTCHA readiness."""
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
                
                if token_len == 0 or (token and len(token) < self.MIN_TOKEN_LENGTH):
                    log.warning(
                        f"[ExtensionBridge] ⚠️ grecaptcha reports ready but trial token "
                        f"is {token_len} chars (need ≥{self.MIN_TOKEN_LENGTH}) — overriding to NOT ready for {email}"
                    )
                    return False
                
                log.info(
                    f"[ExtensionBridge] ✅ grecaptcha ready for {email} "
                    f"(trial token: {token_len} chars)"
                )
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
            self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
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
            self._cleanup_request_timing(request_id)
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

        # ── Debug log capture ──
        self._log_message('IN', action, msg.get('email', msg.get('requestId', '')), msg)

        if action == 'register':
            email = msg.get('email', '')
            ext_version = msg.get('version', '')
            if email and email not in conn.registered_emails:
                conn.registered_emails.append(email)
                log.info(f"[ExtensionBridge] 📧 Extension registered: {email} (v{ext_version})")
                
                # ★ Reset frozen/refresh tracking — new browser session starts fresh
                old_count = self._frozen_tab_counts.pop(email, 0)
                self._frozen_tab_first_at.pop(email, None)
                self._refresh_cooldown_times.pop(email, None)
                if old_count > 0:
                    log.info(f"[ExtensionBridge] 🔄 Frozen counter reset for {email} (was {old_count})")
                
                if self.on_extension_connect:
                    try:
                        self.on_extension_connect(email)
                    except Exception:
                        pass
                # Signal waiters (wait_for_extension)
                event = self._connection_events.get(email)
                if event:
                    event.set()
            
            # ── Version mismatch check ──
            # NOTE: We do NOT send reload_extension here because chrome.runtime.reload()
            # only reloads from the OLD installed path (stale temp copy), not the updated source.
            # Instead, we log the mismatch. The existing install_if_needed() / ensure_all_extensions()
            # pipeline handles proper CDP-based reinstall with fresh file copy.
            if ext_version:
                try:
                    from core.extension_manager import get_local_extension_version
                    local_ver = get_local_extension_version()
                    if local_ver and ext_version != local_ver:
                        # Debounce: only log once per version per email
                        debounce_key = f"{email}:{ext_version}"
                        if not hasattr(self, '_version_mismatch_logged'):
                            self._version_mismatch_logged = set()
                        if debounce_key not in self._version_mismatch_logged:
                            self._version_mismatch_logged.add(debounce_key)
                            log.warning(
                                f"[ExtensionBridge] ⚠️ Version mismatch for {email}: "
                                f"running={ext_version}, local={local_ver} "
                                f"(will be updated by ensure_all_extensions)"
                            )
                    else:
                        log.debug(f"[ExtensionBridge] Extension v{ext_version} matches local v{local_ver}")
                        # Clear debounce on successful match
                        if hasattr(self, '_version_mismatch_logged'):
                            self._version_mismatch_logged.discard(f"{email}:{ext_version}")
                except Exception as e:
                    log.debug(f"[ExtensionBridge] Version check error: {e}")

        elif action == 'headers_update':
            email = msg.get('email', '')
            headers = msg.get('headers', {})
            access_token = msg.get('accessToken')

            if email:
                # Guard: don't downgrade x-client-data in bridge cache
                # Chrome Variations Service needs ~15s after launch; Extension
                # sends truncated 8-char value during that window.
                MIN_XCD = MIN_VALID_XCD  # Shared constant (50)
                new_xcd = headers.get('x-client-data', '')
                old_headers = conn.headers.get(email, {})
                old_xcd = old_headers.get('x-client-data', '')
                if old_xcd and len(old_xcd) >= MIN_XCD and new_xcd and len(new_xcd) < MIN_XCD:
                    log.debug(
                        f"[ExtensionBridge] x-client-data downgrade blocked for {email}: "
                        f"keeping {len(old_xcd)} chars, rejected {len(new_xcd)} chars"
                    )
                    headers = {**headers, 'x-client-data': old_xcd}
                conn.headers[email] = headers
                conn.headers_updated_at[email] = datetime.now()
                if access_token:
                    # Only cache Bearer tokens — SAPISIDHASH causes 403 on VEO API
                    if access_token.startswith('Bearer '):
                        conn.access_tokens[email] = access_token
                    else:
                        log.debug(f"[ExtensionBridge] Non-Bearer token ignored for {email}: {access_token[:20]}...")

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
                # Only cache Bearer tokens — SAPISIDHASH causes 403 on VEO API
                if token.startswith('Bearer ') or not token.startswith('SAPISIDHASH'):
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
                    # Only cache Bearer tokens — SAPISIDHASH causes 403 on VEO API
                    if access_token.startswith('Bearer '):
                        conn.access_tokens[email] = access_token
                    else:
                        log.debug(f"[ExtensionBridge] Non-Bearer token ignored (headers): {access_token[:20]}...")

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

            # ★ Suppress FIRST — don't count false positives from in-progress refresh.
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
                return  # Don't increment counter for false positives

            # Escalation tracking: count genuine frozen events within window
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

        elif action == 'relay_fetch_result':
            # Response to relay_fetch — generic fetch from page context
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

        elif action == 'navigate_tab_result':
            request_id = msg.get('requestId')
            if request_id and request_id in self._pending_requests:
                future = self._pending_requests[request_id]
                if not future.done():
                    future.set_result(msg)

        elif action == 'provision_gemini_key_result':
            # Response to provision_gemini_key request
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
        # Track send time for round-trip timing
        request_id = data.get('requestId')
        if request_id:
            self._pending_request_times[request_id] = time.time()
            self._pending_request_actions[request_id] = data.get('action', '?')
            self._pending_request_emails[request_id] = data.get('email', '?')
        # Fix 1: Catch broken pipe / connection errors
        try:
            await conn.ws.send(payload)
            # ── Debug log capture ──
            self._log_message('OUT', data.get('action', '?'), data.get('email', '?'), data)
        except Exception as e:
            log.warning(f"[ExtensionBridge] Send failed ({e}), cleaning up connection")
            # Clean up timing on send failure
            if request_id:
                self._pending_request_times.pop(request_id, None)
                self._pending_request_actions.pop(request_id, None)
                self._pending_request_emails.pop(request_id, None)
            await self._disconnect(conn, "send-error")
            raise
    
    def _cleanup_request_timing(self, request_id: str):
        """Clean up round-trip timing data for a completed request and log if slow."""
        sent_at = self._pending_request_times.pop(request_id, None)
        action = self._pending_request_actions.pop(request_id, '?')
        email = self._pending_request_emails.pop(request_id, '?')
        if sent_at:
            elapsed = time.time() - sent_at
            if elapsed > 10.0:
                log.warning(
                    f"[ExtBridge] ⏱️ SLOW response: {action} for {email} "
                    f"took {elapsed:.1f}s (requestId={request_id[:8]})"
                )
            elif elapsed > 5.0:
                log.info(
                    f"[ExtBridge] ⏱️ Response: {action} for {email} "
                    f"took {elapsed:.1f}s"
                )

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
            self._cleanup_request_timing(request_id)
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
                
                # Fix #1: Sweep stale pending requests (>60s)
                # When extension is reinstalled, _pending_request_conns mapping
                # may be missing → futures leak until timeout. This sweep catches them.
                stale_reqs = [
                    rid for rid, t in self._pending_request_times.items()
                    if time.time() - t > 60
                ]
                if stale_reqs:
                    for rid in stale_reqs:
                        future = self._pending_requests.pop(rid, None)
                        if future and not future.done():
                            future.set_result({'error': 'Request expired (60s)', 'token': None})
                        self._cleanup_request_timing(rid)
                        self._pending_request_conns.pop(rid, None)
                    log.warning(f"[ExtensionBridge] 🧹 Swept {len(stale_reqs)} stale pending request(s)")
            
                # Extension-lost detection: if had connections before but now empty
                active_count = len(self._connections)
                if self._had_connections and active_count == 0:
                    if self._connections_lost_at == 0:
                        self._connections_lost_at = time.time()
                    elif (time.time() - self._connections_lost_at) > self._EXTENSION_LOST_TIMEOUT:
                        # Fix #3: Retry recovery every 120s instead of fire-once.
                        # If first recovery fails, app would be stuck permanently.
                        _RETRY_INTERVAL = 120  # seconds between retries
                        _since_lost = time.time() - self._connections_lost_at
                        _should_fire = (
                            not self._extension_lost_fired  # First fire at 60s
                            or (_since_lost - self._EXTENSION_LOST_TIMEOUT) % _RETRY_INTERVAL < 15  # Retry every 120s (15s window)
                        )
                        if _should_fire:
                            self._extension_lost_fired = True
                            _attempt = max(1, int((_since_lost - self._EXTENSION_LOST_TIMEOUT) / _RETRY_INTERVAL) + 1)
                            log.warning(
                                f"[ExtensionBridge] 🚨 All connections lost for "
                                f"{_since_lost:.0f}s — triggering recovery (attempt #{_attempt})"
                            )
                            if self.on_extension_lost:
                                try:
                                    self.on_extension_lost()
                                except Exception as e:
                                    log.error(f"[ExtensionBridge] on_extension_lost error: {e}")
                elif active_count > 0:
                    self._connections_lost_at = 0
                    if self._extension_lost_fired:
                        log.info("[ExtensionBridge] ✅ Extension reconnected after recovery")
                        self._extension_lost_fired = False
                    self._had_connections = True
                
                # Health summary: one-line periodic log (replaces per-heartbeat spam)
                now_ts = time.time()
                if now_ts - self._last_health_log >= self._HEALTH_LOG_INTERVAL:
                    self._last_health_log = now_ts
                    parts = []
                    for conn2 in self._connections:
                        for email in conn2.registered_emails:
                            hb_ago = now_ts - self._content_heartbeats.get(email, 0)
                            warm = '✅' if self._recaptcha_readiness.get(email, False) else '❌'
                            status = '✅' if hb_ago < 30 else ('⚠️' if hb_ago < 60 else '❌')
                            short_email = email.split('@')[0][:12]
                            parts.append(f"{short_email}={status}(hb={hb_ago:.0f}s,cap={warm})")
                    pending = len(self._pending_requests)
                    conns = len(self._connections)
                    summary = ', '.join(parts) if parts else 'no accounts'
                    log.info(
                        f"[ExtBridge] 📊 Health: {summary} | "
                        f"conns={conns}, pending={pending}"
                    )
                
                # Fix B: Periodic unregistered connection detection
                # If connections exist but none have registered emails after 15s,
                # fire on_unregistered_connection for auto-assign.
                # Catches cases where _delayed_assign_check was lost during SW restart.
                unregistered = [
                    c for c in self._connections
                    if not c.registered_emails
                    and self._is_ws_open(c.ws)
                    and (time.time() - c.last_activity) > 15
                ]
                if unregistered and self.on_unregistered_connection:
                    log.info(
                        f"[ExtensionBridge] ⚠️ {len(unregistered)} unregistered "
                        f"connection(s) detected — triggering auto-assign"
                    )
                    try:
                        self.on_unregistered_connection()
                    except Exception as e:
                        log.error(f"[ExtensionBridge] Auto-assign trigger error: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[ExtensionBridge] Heartbeat error: {e}")
                await asyncio.sleep(5)


    # ── Status ──────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Get bridge status for DevConsole."""
        now = time.time()
        diag = self.get_connection_diagnosis()
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
            'diagnosis': diag,
        }

    def _log_message(self, direction: str, action: str, email: str, data: dict):
        """Record a message to the debug ring buffer."""
        # Truncate payload for memory efficiency
        preview = {}
        for k, v in data.items():
            if k in ('action', 'email', 'requestId'):
                preview[k] = v
            elif isinstance(v, str) and len(v) > 100:
                preview[k] = v[:100] + '...'
            elif isinstance(v, dict):
                preview[k] = f'{{...{len(v)} keys}}'
            elif isinstance(v, list):
                preview[k] = f'[...{len(v)} items]'
            else:
                preview[k] = v
        
        self._message_log.append({
            'dir': direction,
            'action': action,
            'email': str(email)[:50],
            'ts': time.time(),
            'preview': preview,
        })

    def get_message_log(self, last_n: int = 200) -> list:
        """Get recent messages for DevConsole Extension Debug page."""
        items = list(self._message_log)
        return items[-last_n:] if len(items) > last_n else items

    def get_connection_diagnosis(self) -> dict:
        """Diagnose why extension is not connected.
        
        Returns dict with:
            - status: 'healthy' | 'server_down' | 'no_connections' | 'no_emails'
            - reason: Human-readable reason (Vietnamese)
            - fix: Suggested fix action
            - severity: 'ok' | 'warning' | 'error'
        """
        # Case E: Server failed to start (all ports occupied)
        if self._server is None:
            # Check if ports are occupied
            port_info = self._check_ports_available()
            if port_info['all_occupied']:
                return {
                    'status': 'server_down',
                    'reason': f'Tất cả port {self.FALLBACK_PORTS} bị chiếm bởi process khác',
                    'fix': f'Đóng process dùng port {port_info["occupied_ports"]} hoặc restart máy',
                    'severity': 'error',
                }
            return {
                'status': 'server_down',
                'reason': 'WebSocket server chưa khởi động',
                'fix': 'Restart ứng dụng',
                'severity': 'error',
            }
        
        # Case C+D: Server running but no connections
        if len(self._connections) == 0:
            lost_duration = ""
            if self._connections_lost_at > 0:
                elapsed = time.time() - self._connections_lost_at
                lost_duration = f" ({elapsed:.0f}s)"
            
            # Check if we ever had connections
            if self._had_connections:
                return {
                    'status': 'no_connections',
                    'reason': f'Extension mất kết nối{lost_duration}',
                    'fix': 'Kiểm tra: (1) Extension có bật không (icon vàng trên Chrome), '
                           '(2) Chrome có đang chạy không, '
                           '(3) Firewall có chặn localhost:8765 không',
                    'severity': 'warning',
                }
            else:
                return {
                    'status': 'no_connections',
                    'reason': 'Extension chưa từng kết nối',
                    'fix': 'Kiểm tra: (1) Extension đã cài chưa, '
                           '(2) Extension có bật không, '
                           '(3) Đúng Chrome profile chưa, '
                           f'(4) Firewall có chặn port {self._port} không',
                    'severity': 'error',
                }
        
        # Case F: Connected but no registered emails
        emails = self.get_connected_emails()
        if not emails:
            return {
                'status': 'no_emails',
                'reason': 'Extension kết nối nhưng chưa đăng ký email',
                'fix': 'Mở tab VEO (veo.google.com) trong Chrome để extension tự đăng ký',
                'severity': 'warning',
            }
        
        # Check for preserved (stale) headers — extension was connected but headers may be old
        stale_emails = []
        now = time.time()
        for email in emails:
            last_hb = self._content_heartbeats.get(email, 0)
            if last_hb and (now - last_hb) > 60:
                stale_emails.append(email)
        
        if stale_emails:
            return {
                'status': 'healthy',
                'reason': f'Kết nối OK, nhưng heartbeat cũ cho: {", ".join(stale_emails)}',
                'fix': 'Reload tab VEO hoặc kiểm tra content.js',
                'severity': 'warning',
            }
        
        return {
            'status': 'healthy',
            'reason': f'Kết nối tốt: {len(self._connections)} connection(s), '
                       f'{len(emails)} email(s): {", ".join(emails)}',
            'fix': '',
            'severity': 'ok',
        }
    
    # ── Server Watchdog (auto-restart on crash/port loss) ────────────────
    
    async def _server_watchdog(self):
        """Background task: check server health every 15s, auto-restart if dead.
        
        Detects:
        - Server object gone (crash)
        - Server port no longer bound (stolen by another process)
        - Server .sockets empty (closed unexpectedly)
        
        Recovery:
        1. Try to kill the process occupying our port
        2. Restart server on same port or fallback
        3. Extension auto-reconnects via fast port scan (offscreen.js)
        """
        WATCHDOG_INTERVAL = 15  # seconds
        log.info("[ExtensionBridge] 🐕 Server watchdog started")
        
        while not self._stopping:
            try:
                await asyncio.sleep(WATCHDOG_INTERVAL)
                if self._stopping:
                    break
                
                # Check server health
                if self._server is None:
                    log.warning("[ExtensionBridge] 🐕 Watchdog: server is None — restarting...")
                    await self._restart_server()
                    continue
                
                # Check if server is still serving (sockets bound)
                server_alive = False
                try:
                    sockets = self._server.sockets
                    server_alive = sockets is not None and len(sockets) > 0
                except Exception:
                    server_alive = False
                
                if not server_alive:
                    log.warning(
                        f"[ExtensionBridge] 🐕 Watchdog: server sockets dead "
                        f"(port {self._port}) — restarting..."
                    )
                    await self._restart_server()
                    continue
                
                # Server healthy — reset restart counter
                if self._restart_count > 0:
                    self._restart_count = 0
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[ExtensionBridge] 🐕 Watchdog error: {e}")
                await asyncio.sleep(WATCHDOG_INTERVAL)
        
        log.info("[ExtensionBridge] 🐕 Server watchdog stopped")
    
    async def _restart_server(self):
        """Restart the WebSocket server after a crash or port loss.
        
        Steps:
        1. Close old server gracefully
        2. Try to kill process occupying our preferred port
        3. Re-bind using port fallback logic (same as start())
        4. Extension reconnects automatically via fast port scan
        
        Preserves: callbacks, _preserved_headers, all state except _server.
        """
        self._restart_count += 1
        
        if self._restart_count > self._MAX_RESTARTS:
            log.error(
                f"[ExtensionBridge] ❌ Max restarts ({self._MAX_RESTARTS}) reached — "
                f"giving up. Manual restart required."
            )
            return
        
        log.warning(
            f"[ExtensionBridge] 🔄 Restarting WebSocket server "
            f"(attempt {self._restart_count}/{self._MAX_RESTARTS})..."
        )
        
        # Step 1: Close old server
        old_port = self._port
        if self._server:
            try:
                self._server.close()
                await asyncio.wait_for(self._server.wait_closed(), timeout=3.0)
            except Exception:
                pass
            self._server = None
        
        # Step 2: Try to reclaim our port by killing the occupying process
        self._kill_port_holder(old_port)
        await asyncio.sleep(1)  # Give OS time to release the port
        
        # Step 3: Re-bind using port fallback
        # Suppress verbose websockets logs
        logging.getLogger("websockets").setLevel(logging.CRITICAL)
        logging.getLogger("websockets.server").setLevel(logging.CRITICAL)
        
        # Try preferred port first, then fallbacks
        ports_to_try = [old_port] + [p for p in self.FALLBACK_PORTS if p != old_port]
        
        last_error = None
        for port in ports_to_try:
            try:
                self._server = await ws_serve(
                    self._handle_connection,
                    '127.0.0.1',
                    port,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=50 * 1024 * 1024,
                )
                self._port = port
                log.info(
                    f"[ExtensionBridge] ✅ WebSocket server restarted on "
                    f"ws://127.0.0.1:{port} (attempt {self._restart_count})"
                )
                # Extension will auto-reconnect via fast port scan
                return
            except OSError as e:
                last_error = e
                log.warning(f"[ExtensionBridge] Port {port} still unavailable: {e}")
                continue
        
        # All ports failed — will retry on next watchdog cycle
        log.error(
            f"[ExtensionBridge] ❌ All ports failed during restart. "
            f"Will retry in 15s. Last error: {last_error}"
        )
    
    @staticmethod
    def _kill_port_holder(port: int):
        """Try to kill the process occupying a specific port (Windows only).
        
        Best-effort: logs warning if unable to kill. Does NOT kill our own process.
        """
        import os
        import subprocess
        try:
            # Find PID using netstat
            result = subprocess.run(
                ['netstat', '-ano', '-p', 'TCP'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
            my_pid = os.getpid()
            for line in result.stdout.splitlines():
                if f'127.0.0.1:{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    pid = int(parts[-1])
                    if pid == my_pid:
                        continue  # Don't kill ourselves
                    log.warning(
                        f"[ExtensionBridge] 🔪 Killing process PID={pid} "
                        f"occupying port {port}..."
                    )
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(pid)],
                        capture_output=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                    )
                    log.info(f"[ExtensionBridge] ✅ Killed PID={pid}")
                    return
        except Exception as e:
            log.debug(f"[ExtensionBridge] Could not kill port holder: {e}")

    def _check_ports_available(self) -> dict:
        """Check which ports are available/occupied."""
        import socket
        occupied = []
        for port in self.FALLBACK_PORTS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(('127.0.0.1', port))
                sock.close()
            except OSError:
                occupied.append(port)
                sock.close()
        return {
            'all_occupied': len(occupied) == len(self.FALLBACK_PORTS),
            'occupied_ports': occupied,
        }

    def is_recaptcha_ready(self, email: str) -> bool:
        """Check if reCAPTCHA is warm/ready for an email (from content.js reports)."""
        return self._recaptcha_readiness.get(email, False)

