"""
VEO Pro Max - Account Recovery Coordinator

Single source of truth for all browser/account recovery actions.
All modules that need recovery (engine, upscale_queue, watchdog, etc.)
must request recovery through this coordinator via report_signal().

Architecture ref: RECOVERY_COORDINATOR_AND_ASYNC_ERROR_OWNERSHIP_REPORT §7.1B

Design:
- One coordinator instance per engine
- Serialized recovery per account (only one recovery at a time)
- Mandatory drain-and-remedy sequence before any browser action
- State machine tracks account health
"""

import asyncio
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.engine import Engine
    from core.upscale_queue import UpscaleQueue

log = logging.getLogger(__name__)


# ── State Machine ──────────────────────────────────────────────────

class AccountState(str, enum.Enum):
    """Health state of an account's browser/session."""
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"                  # Temporary backoff (rate limit, etc.)
    RECOVERING_SOFT = "recovering_soft"    # Tab reload / hard navigation
    RECOVERING_HARD = "recovering_hard"    # Soft failed, escalating
    BROWSER_RESTARTING = "browser_restarting"  # Full browser restart
    PAUSED = "paused"                      # Manually paused by user
    SICK = "sick"                          # ★ P1-2: All recovery exhausted — quarantined


# Recovery states where lease freeze applies
RECOVERING_STATES = frozenset({
    AccountState.RECOVERING_SOFT,
    AccountState.RECOVERING_HARD,
    AccountState.BROWSER_RESTARTING,
})

# All non-healthy states (lease freeze applies to ALL of these)
BLOCKED_STATES = RECOVERING_STATES | frozenset({AccountState.SICK})


# ── Signal ─────────────────────────────────────────────────────────

class SignalSeverity(str, enum.Enum):
    LOW = "low"       # Info/warning, may not need recovery
    MEDIUM = "medium" # Likely needs soft recovery
    HIGH = "high"     # Needs hard recovery or restart
    CRITICAL = "critical"  # Browser dead, must restart


@dataclass
class RecoverySignal:
    """Signal sent by modules requesting account recovery.
    
    Modules detect problems and send signals here.
    Only the coordinator decides what action to take.
    """
    account_email: str
    source: str      # "engine", "upscale_queue", "watchdog", "extension_bridge"
    error_type: str  # "recaptcha_not_ready", "403", "tab_dead", "poll_timeout", etc.
    severity: SignalSeverity = SignalSeverity.MEDIUM
    task_id: Optional[str] = None
    detail: str = ""
    timestamp: float = field(default_factory=time.time)


# ── Coordinator ────────────────────────────────────────────────────

class AccountRecoveryCoordinator:
    """Centralized recovery decision maker.
    
    All browser recovery actions (reload, hard_nav, restart) must go
    through this coordinator. Direct calls from engine/upscale_queue
    are forbidden (enforced by Tier 1 refactoring).
    
    Key guarantees:
    - One recovery at a time per account (serialized via asyncio.Lock)
    - Mandatory drain-and-remedy sequence (no RPC interruption)
    - Lease freeze during recovery (prevents watchdog false-expire)
    """
    
    # Drain timeout — how long to wait for in-flight RPCs
    DRAIN_TIMEOUT = 10.0  # seconds
    
    # Escalation: max soft attempts before going hard
    MAX_SOFT_ATTEMPTS = 2
    
    # Cooldown between recovery attempts for same account
    MIN_RECOVERY_INTERVAL = 30.0  # seconds
    
    def __init__(
        self,
        engine: 'Engine',
        upscale_queue: Optional['UpscaleQueue'] = None,
    ):
        self._engine = engine
        self._upscale_queue = upscale_queue
        
        # Per-account state tracking
        self._account_states: Dict[str, AccountState] = {}
        self._account_locks: Dict[str, asyncio.Lock] = {}
        
        # Recovery history for escalation logic
        self._soft_attempt_count: Dict[str, int] = {}  # email → count
        self._last_recovery_ts: Dict[str, float] = {}  # email → timestamp
        
        # Submit gate: accounts in this set are blocked from new submissions
        self._submit_blocked: set = set()
        
        # ★ P1-2: Track accounts where escalation exhausted all levels
        # and _mark_account_sick() was called. Prevents finally block
        # from undoing the quarantine.
        self._escalation_exhausted: Dict[str, bool] = {}
        
        log.info("[RecoveryCoordinator] Initialized")
    
    # ── Public API ─────────────────────────────────────────────────
    
    def set_upscale_queue(self, queue: 'UpscaleQueue'):
        """Late-bind upscale queue (may not exist at coordinator init time).
        
        Also injects a back-reference so UQ can report signals to coordinator.
        """
        self._upscale_queue = queue
        # ★ P1-3: Bidirectional binding — UQ needs coordinator ref for report_signal
        if queue is not None:
            queue._recovery_coordinator = self
    
    def is_account_recovering(self, email: Optional[str]) -> bool:
        """Check if account is ACTIVELY being recovered (transient state).
        
        Returns False for SICK (quarantined) accounts — those are terminal,
        not recovering. UI uses this to show 🔄 RECOVERING label.
        """
        if not email:
            return False
        return self._account_states.get(email, AccountState.HEALTHY) in RECOVERING_STATES
    
    def is_account_quarantined(self, email: Optional[str]) -> bool:
        """Check if account is quarantined (SICK — all recovery exhausted).
        
        Returns True only for terminal SICK state. UI uses this to show
        ⛔ QUARANTINED label (distinct from transient RECOVERING).
        """
        if not email:
            return False
        return self._account_states.get(email, AccountState.HEALTHY) == AccountState.SICK
    
    def is_account_blocked(self, email: Optional[str]) -> bool:
        """Check if account leases should be frozen (recovering OR sick).
        
        Used by has_live_background_owner() for lease freeze logic.
        """
        if not email:
            return False
        return self._account_states.get(email, AccountState.HEALTHY) in BLOCKED_STATES
    
    def is_submit_blocked(self, email: str) -> bool:
        """Check if submissions are blocked for this account.
        
        Called by engine._pre_submit_gate() to prevent new tasks
        from being submitted during recovery.
        """
        return email in self._submit_blocked
    
    def clear_quarantine(self, email: str):
        """Clear coordinator quarantine when account recovers externally.
        
        Called by engine when _sick_accounts is cleared (e.g. circuit
        breaker closes, browser auto-restarts). This unlatches the
        coordinator’s SICK state so account can resume normal operation.
        """
        was_sick = self._escalation_exhausted.pop(email, False)
        was_blocked = email in self._submit_blocked
        
        if was_sick or was_blocked:
            # Clear all quarantine state
            self._account_states[email] = AccountState.HEALTHY
            self._submit_blocked.discard(email)
            self._soft_attempt_count.pop(email, None)
            
            # Resume UpscaleQueue
            if self._upscale_queue:
                try:
                    self._upscale_queue.unpause_account(email)
                except Exception as _uq_err:
                    log.error(
                        f"[RecoveryCoordinator] [{email}] UQ unpause error: {_uq_err}"
                    )
            
            log.info(
                f"[RecoveryCoordinator] [{email}] Quarantine CLEARED — "
                f"state=HEALTHY, gate=OPEN, UQ=RESUMED"
            )
    
    def get_account_state(self, email: str) -> AccountState:
        """Get current health state of an account."""
        return self._account_states.get(email, AccountState.HEALTHY)
    
    def get_status(self) -> dict:
        """Return coordinator health info for StatusAggregator."""
        return {
            "account_states": {
                email: state.value
                for email, state in self._account_states.items()
                if state != AccountState.HEALTHY
            },
            "submit_blocked": list(self._submit_blocked),
            "soft_attempts": dict(self._soft_attempt_count),
        }
    
    # ── Signal Entry Point ─────────────────────────────────────────
    
    async def report_signal(self, signal: RecoverySignal):
        """Main entry point for all recovery requests.
        
        Modules call this instead of directly calling
        account.soft_recover_browser() or account.restart_browser().
        
        The coordinator decides:
        1. Is recovery needed? (debounce, dedup)
        2. What level of recovery? (soft → hard → restart)
        3. Execute drain-and-remedy sequence
        """
        email = signal.account_email
        
        log.info(
            f"[RecoveryCoordinator] Signal from {signal.source}: "
            f"{signal.error_type} for {email} "
            f"(severity={signal.severity.value}, task={signal.task_id or 'N/A'})"
        )
        
        # Debounce: skip if recovery was done recently
        last_ts = self._last_recovery_ts.get(email, 0)
        if time.time() - last_ts < self.MIN_RECOVERY_INTERVAL:
            state = self._account_states.get(email, AccountState.HEALTHY)
            if state in RECOVERING_STATES:
                log.info(
                    f"[RecoveryCoordinator] Skipping signal for {email} — "
                    f"recovery already in progress (state={state.value})"
                )
                return
        
        # Serialize: one recovery at a time per account
        lock = self._get_lock(email)
        if lock.locked():
            log.info(
                f"[RecoveryCoordinator] Signal queued for {email} — "
                f"another recovery in progress"
            )
        
        async with lock:
            await self._execute_recovery(signal)
    
    # ── Recovery Execution ─────────────────────────────────────────
    
    async def _execute_recovery(self, signal: RecoverySignal):
        """Execute the drain-and-remedy sequence for an account.
        
        11-step mandatory sequence:
        1.  close submit gate
        2.  pause UpscaleQueue
        3.  mark account RECOVERING
        4.  freeze all leases
        5.  wait/cancel in-flight ops (drain)
        6.  execute remedy action
        7.  startup probe
        8.  unfreeze leases
        9.  reopen submit gate
        10. resume UpscaleQueue
        11. mark account HEALTHY
        
        ★ P1-2 FIX: Steps 8-11 are SKIPPED when escalation exhausted
        all recovery levels and _mark_account_sick() was called.
        This preserves the quarantine state instead of undoing it.
        """
        email = signal.account_email
        
        # Determine recovery level
        level = self._determine_level(signal)
        
        log.warning(
            f"[RecoveryCoordinator] Starting {level.value} recovery for {email} "
            f"(trigger: {signal.error_type} from {signal.source})"
        )
        
        # ★ P1-B: LOW severity = lightweight recovery.
        # PreWarm's idle_prewarm should NOT disrupt active upscale workers.
        # Skip UQ pause + drain for LOW signals (simulate_activity + soft_recover only).
        is_lightweight = signal.severity == SignalSeverity.LOW
        
        try:
            # Step 1: Close submit gate
            self._submit_blocked.add(email)
            log.info(f"[RecoveryCoordinator] [{email}] Step 1: Submit gate CLOSED")
            
            # Step 2: Pause UpscaleQueue (skip for lightweight recovery)
            if self._upscale_queue and not is_lightweight:
                self._upscale_queue.pause_account(email)
                log.info(f"[RecoveryCoordinator] [{email}] Step 2: UpscaleQueue PAUSED")
            elif is_lightweight:
                log.info(f"[RecoveryCoordinator] [{email}] Step 2: SKIPPED (lightweight/LOW)")
            
            # Step 3: Mark RECOVERING
            self._account_states[email] = level
            log.info(f"[RecoveryCoordinator] [{email}] Step 3: State → {level.value}")
            
            # Step 4: Freeze leases (implicit via is_account_recovering)
            # has_live_background_owner() checks is_account_recovering() and
            # returns True regardless of heartbeat — this IS the freeze.
            log.info(f"[RecoveryCoordinator] [{email}] Step 4: Leases FROZEN")
            
            # Step 5: Drain in-flight operations (skip for lightweight recovery)
            if not is_lightweight:
                await self._drain_inflight(email)
                log.info(f"[RecoveryCoordinator] [{email}] Step 5: Drain complete")
            else:
                log.info(f"[RecoveryCoordinator] [{email}] Step 5: SKIPPED (lightweight/LOW)")
            
            # Step 6: Execute remedy action
            success = await self._execute_remedy(email, level)
            log.info(
                f"[RecoveryCoordinator] [{email}] Step 6: Remedy "
                f"{'SUCCEEDED' if success else 'FAILED'}"
            )
            
            # Step 7: Startup probe (verify browser health)
            if success:
                probe_ok = await self._startup_probe(email)
                log.info(
                    f"[RecoveryCoordinator] [{email}] Step 7: Probe "
                    f"{'PASSED' if probe_ok else 'FAILED'}"
                )
                if not probe_ok and level != AccountState.BROWSER_RESTARTING:
                    # Escalate: soft failed → try hard
                    log.warning(
                        f"[RecoveryCoordinator] [{email}] Probe failed after "
                        f"{level.value} — escalating"
                    )
                    await self._escalate(email, signal)
            else:
                if level != AccountState.BROWSER_RESTARTING:
                    await self._escalate(email, signal)
            
        except Exception as e:
            log.error(
                f"[RecoveryCoordinator] [{email}] Recovery error: {e}",
                exc_info=True
            )
        finally:
            # ★ P1-2 FIX: Check if escalation exhausted all levels and
            # _mark_account_sick() was called. If so, PRESERVE quarantine.
            is_sick = self._escalation_exhausted.get(email, False)
            
            if is_sick:
                # Account is quarantined — keep gate closed, UQ paused
                log.warning(
                    f"[RecoveryCoordinator] [{email}] Recovery EXHAUSTED — "
                    f"keeping gate CLOSED, UQ PAUSED (account is sick)"
                )
                self._last_recovery_ts[email] = time.time()
            else:
                # Recovery succeeded or partially worked — resume normal operation
                
                # Step 8: Unfreeze leases (implicit — state changes below)
                log.info(f"[RecoveryCoordinator] [{email}] Step 8: Leases UNFROZEN")
                
                # Step 9: Reopen submit gate
                self._submit_blocked.discard(email)
                log.info(f"[RecoveryCoordinator] [{email}] Step 9: Submit gate OPEN")
                
                # Step 10: Resume UpscaleQueue
                if self._upscale_queue:
                    try:
                        self._upscale_queue.unpause_account(email)
                    except Exception as _uq_err:
                        log.error(
                            f"[RecoveryCoordinator] [{email}] Step 10 UQ unpause error: {_uq_err}"
                        )
                    log.info(f"[RecoveryCoordinator] [{email}] Step 10: UpscaleQueue RESUMED")
                
                # Step 11: Mark HEALTHY
                self._account_states[email] = AccountState.HEALTHY
                self._last_recovery_ts[email] = time.time()
                log.info(f"[RecoveryCoordinator] [{email}] Step 11: State → HEALTHY")
    
    # ── Recovery Level Decision ────────────────────────────────────
    
    def _determine_level(self, signal: RecoverySignal) -> AccountState:
        """Decide recovery level based on signal + history."""
        email = signal.account_email
        
        # Critical signals → immediate browser restart
        if signal.severity == SignalSeverity.CRITICAL:
            return AccountState.BROWSER_RESTARTING
        
        # Check escalation history
        soft_count = self._soft_attempt_count.get(email, 0)
        
        if signal.severity == SignalSeverity.HIGH or soft_count >= self.MAX_SOFT_ATTEMPTS:
            self._soft_attempt_count[email] = 0  # Reset on escalation
            return AccountState.RECOVERING_HARD
        
        # Default: soft recovery
        self._soft_attempt_count[email] = soft_count + 1
        return AccountState.RECOVERING_SOFT
    
    async def _escalate(self, email: str, original_signal: RecoverySignal):
        """Escalate from current level to next level."""
        current = self._account_states.get(email, AccountState.HEALTHY)
        
        if current == AccountState.RECOVERING_SOFT:
            next_level = AccountState.RECOVERING_HARD
        elif current == AccountState.RECOVERING_HARD:
            next_level = AccountState.BROWSER_RESTARTING
        else:
            log.warning(
                f"[RecoveryCoordinator] [{email}] Cannot escalate beyond "
                f"{current.value} — marking sick"
            )
            # ★ P1-2: Set exhaustion flag BEFORE marking sick so
            # finally block preserves quarantine state
            self._escalation_exhausted[email] = True
            self._account_states[email] = AccountState.SICK
            
            # Mark account sick — all recovery exhausted
            if hasattr(self._engine, '_mark_account_sick'):
                self._engine._mark_account_sick(email)
            return
        
        log.warning(
            f"[RecoveryCoordinator] [{email}] Escalating: "
            f"{current.value} → {next_level.value}"
        )
        
        self._account_states[email] = next_level
        success = await self._execute_remedy(email, next_level)
        
        if not success and next_level != AccountState.BROWSER_RESTARTING:
            await self._escalate(email, original_signal)
    
    # ── Drain & Remedy ─────────────────────────────────────────────
    
    async def _drain_inflight(self, email: str):
        """Wait for in-flight RPCs to complete or timeout.
        
        This prevents recovery actions from interrupting active requests.
        """
        # For now: simple timeout wait. Future: cancel specific tasks.
        await asyncio.sleep(min(self.DRAIN_TIMEOUT, 5.0))
    
    async def _execute_remedy(self, email: str, level: AccountState) -> bool:
        """Execute the actual browser recovery action.
        
        ONLY place where browser recovery methods are called.
        All other modules request via report_signal().
        """
        account = self._get_account(email)
        if not account:
            log.error(f"[RecoveryCoordinator] Account {email} not found")
            return False
        
        try:
            if level == AccountState.RECOVERING_SOFT:
                # Soft: reload tab / hard navigation
                result = await account.soft_recover_browser()
                log.info(
                    f"[RecoveryCoordinator] [{email}] soft_recover_browser → "
                    f"{'OK' if result else 'FAILED'}"
                )
                return bool(result)
            
            elif level == AccountState.RECOVERING_HARD:
                # Hard: hard navigation (full page reload)
                bridge = getattr(self._engine, '_extension_bridge', None)
                if bridge:
                    result = await bridge.trigger_hard_navigation(email)
                    log.info(
                        f"[RecoveryCoordinator] [{email}] hard_navigation → "
                        f"{'OK' if result else 'FAILED'}"
                    )
                    return bool(result)
                # Fallback to soft if no bridge
                return bool(await account.soft_recover_browser())
            
            elif level == AccountState.BROWSER_RESTARTING:
                # Full browser restart
                result = await account.restart_browser()
                log.info(
                    f"[RecoveryCoordinator] [{email}] restart_browser → "
                    f"{'OK' if result else 'FAILED'}"
                )
                return bool(result)
            
        except Exception as e:
            log.error(
                f"[RecoveryCoordinator] [{email}] Remedy error "
                f"(level={level.value}): {e}"
            )
            return False
        
        return False
    
    async def _startup_probe(self, email: str) -> bool:
        """Verify browser health after recovery.
        
        All 4 gates must pass before account is marked HEALTHY:
        1. Extension connected
        2. All stale caches invalidated
        3. Live probe_browser_headers() → x-browser-validation non-empty
        4. Live check_recaptcha_ready() → trial token ≥1500 chars
        
        ★ FIX: Previous version used passive cache reads and returned True
        even when x-browser-validation was missing — caused premature queue
        resume and infinite reCAPTCHA loop (see debug_report_20260413).
        """
        account = self._get_account(email)
        if not account:
            return False
        
        try:
            bridge = getattr(self._engine, '_extension_bridge', None)
            if not bridge:
                # ★ FIX: Upscale depends on extension/reCAPTCHA — no bridge
                # means we cannot verify health. Returning True here previously
                # allowed premature resume. Now fail to force escalation.
                log.warning(
                    f"[RecoveryCoordinator] [{email}] Probe FAILED: "
                    f"no extension bridge available"
                )
                return False
            
            # ── Gate 1: Extension must be connected ──
            if not bridge.is_connected(email):
                log.warning(f"[RecoveryCoordinator] [{email}] Probe: extension not connected")
                return False
            
            # ── Gate 2: Invalidate ALL stale caches ──
            # Clears: conn.headers, _preserved_headers, _check_ready_cache,
            # _recaptcha_readiness, _check_ready_inflight, _short_token_counts
            bridge.invalidate_cached_headers(email)
            log.info(f"[RecoveryCoordinator] [{email}] Probe: all caches invalidated")
            
            # ── Gate 3: Live header probe → x-browser-validation ──
            # Must actively trigger a cross-origin fetch to capture the header,
            # not just read the (now-empty) cache.
            await asyncio.sleep(2.0)  # Give reloaded tab time to settle
            has_validation = await bridge.probe_browser_headers(email, timeout=10.0)
            if not has_validation:
                log.warning(
                    f"[RecoveryCoordinator] [{email}] Probe: "
                    f"x-browser-validation not captured — retrying in 5s"
                )
                await asyncio.sleep(5.0)
                has_validation = await bridge.probe_browser_headers(email, timeout=10.0)
            
            if not has_validation:
                log.warning(
                    f"[RecoveryCoordinator] [{email}] Probe FAILED: "
                    f"x-browser-validation still missing after 2 attempts"
                )
                return False
            
            log.info(f"[RecoveryCoordinator] [{email}] Probe: x-browser-validation ✅")
            
            # ── Gate 4: Live reCAPTCHA check with retry ──
            # Widget may need 5-10s to initialize after tab reload.
            # Try up to 3 times with 4s gaps (~16s total max).
            for attempt in range(3):
                ready = await bridge.check_recaptcha_ready(email, timeout=8.0)
                if ready:
                    log.info(
                        f"[RecoveryCoordinator] [{email}] Probe: "
                        f"reCAPTCHA ready ✅ (attempt {attempt + 1}/3)"
                    )
                    return True
                if attempt < 2:
                    log.info(
                        f"[RecoveryCoordinator] [{email}] Probe: "
                        f"reCAPTCHA not ready (attempt {attempt + 1}/3) — waiting 4s"
                    )
                    await asyncio.sleep(4.0)
            
            log.warning(
                f"[RecoveryCoordinator] [{email}] Probe FAILED: "
                f"reCAPTCHA not ready after 3 attempts"
            )
            return False
            
        except Exception as e:
            log.error(f"[RecoveryCoordinator] [{email}] Probe error: {e}")
            return False
    
    # ── Helpers ────────────────────────────────────────────────────
    
    def _get_lock(self, email: str) -> asyncio.Lock:
        """Get or create per-account lock."""
        if email not in self._account_locks:
            self._account_locks[email] = asyncio.Lock()
        return self._account_locks[email]
    
    def _get_account(self, email: str):
        """Get Account object from engine's account manager."""
        try:
            acc_mgr = getattr(self._engine, '_account_manager', None)
            if acc_mgr:
                for acc in acc_mgr._accounts:
                    if acc.email == email:
                        return acc
        except Exception:
            pass
        return None
