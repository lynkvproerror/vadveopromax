"""
Remedy Registry — Error-specific recovery chains + orchestrator.

Each ErrorType maps to a chain of Remedy actions, tried in order.
After each remedy, account health is verified. If healthy → resume.
If all remedies exhausted → failover to another account via CreditWindow.

Replaces the old Phase 0-3 state machine in engine.py.

Changes vs original:
  FIX-1: xcd_valid is WARNING-ONLY — does not block healthy verdict.
          xcd=28 during Chrome Variations cold-start enrollment caused
          infinite remedy loops because health never returned True.
  FIX-2: check_recaptcha_ready timeout reduced 10s → 3s inside health check.
          probe timeout reduced 10s → 5s.
          Tab-reloading fast-bail added to avoid waiting on a page mid-load.
  FIX-3: skip_probe=True for fast/early remedies (reload_page, borrow_headers,
          simulate_activity, reload_tab, refresh_token) — probe is only
          meaningful after reCAPTCHA widget has fully re-initialized.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Any

from core.error_classifier import ErrorType, classify_error, ERROR_CREDIT_COST
from config.constants import MIN_VALID_XCD

log = logging.getLogger(__name__)

_recovery_locks: Dict[str, asyncio.Lock] = {}
_last_recovery_ts: Dict[str, float] = {}
_last_recovery_result: Dict[str, "RecoveryResult"] = {}
_RECOVERY_DEDUP_WINDOW_SEC = 5.0


# ── Data Classes ──────────────────────────────────────────────

@dataclass
class HealthResult:
    """Result of account health verification."""
    healthy: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)


@dataclass
class RecoveryResult:
    """Result of recovery attempt."""
    success: bool
    error_type: ErrorType = ErrorType.UNKNOWN
    remedy_used: Optional[str] = None
    attempts: int = 0
    failover: bool = False
    backoff: int = 5


@dataclass
class Remedy:
    """A single recovery action."""
    name: str
    description: str
    wait_after: float = 0.0  # seconds to wait after action


# ── Health Verification ───────────────────────────────────────

async def verify_account_health(
    account,
    ext_bridge,
    skip_probe: bool = False,
) -> HealthResult:
    """Multi-check account health after a remedy.

    Args:
        account: AccountManager instance.
        ext_bridge: ExtensionBridge instance (may be None).
        skip_probe: If True, skip the probe request check.

    Returns:
        HealthResult with pass/fail for each check.

    NOTE (FIX-1): xcd_valid is a *warning-only* diagnostic field.
    It does NOT block the healthy verdict when reCAPTCHA is ready.
    Chrome Variations Service takes 15-60s to enroll after Cold Start;
    treating xcd_short as a health failure caused an infinite remedy loop
    (all remedies "ran" but health never returned True → account was
    wrongly suspended despite reCAPTCHA working fine).
    """
    checks = {}
    email = account.email

    # 1. Extension connected?
    if ext_bridge:
        checks["extension"] = ext_bridge.is_connected(email)
    else:
        checks["extension"] = False

    # 2. x-client-data — collect best available value (WARNING-ONLY, FIX-1)
    xcd = ""
    if hasattr(account, 'get_browser_headers'):
        try:
            hdrs = account.get_browser_headers() or {}
            xcd = (hdrs.get("x-client-data", "") or "")
        except Exception:
            xcd = ""
    if ext_bridge and hasattr(ext_bridge, '_header_cache'):
        cache = ext_bridge._header_cache.get(email, {})
        cached_xcd = cache.get("x-client-data", "") or ""
        if len(cached_xcd) > len(xcd):
            xcd = cached_xcd
    session_xcd = getattr(getattr(account, 'session', None), 'client_data', '') or ''
    if len(session_xcd) > len(xcd):
        xcd = session_xcd
    xcd_ok = len(xcd) >= MIN_VALID_XCD
    if not xcd_ok:
        log.debug(
            f"[Health] {email}: xcd={len(xcd)} chars < {MIN_VALID_XCD} "
            f"(Chrome Variations still enrolling — non-blocking, FIX-1)"
        )

    # FIX-2: Fast-bail when tab is actively reloading — skip 3s timeout
    _tab_reloading = False
    if ext_bridge and hasattr(ext_bridge, '_tab_reloading_emails'):
        _tab_reloading = email in getattr(ext_bridge, '_tab_reloading_emails', set())
    if _tab_reloading:
        log.debug(f"[Health] {email}: tab is reloading — fast-fail recaptcha check (FIX-2)")
        checks["recaptcha_ready"] = False
        failed = [k for k, v in checks.items() if not v]
        return HealthResult(healthy=False, checks=checks, failed=failed)

    # 3. reCAPTCHA ready? — FIX-2: timeout 10s → 3s to avoid event-loop stall
    if ext_bridge and checks.get("extension"):
        try:
            ready = await ext_bridge.check_recaptcha_ready(email, timeout=3.0)
            checks["recaptcha_ready"] = ready
        except Exception:
            checks["recaptcha_ready"] = False
    else:
        checks["recaptcha_ready"] = False

    # 4. Probe: token generation — gated on recaptcha_ready (FIX-1: NOT on xcd_valid)
    _can_probe = (
        not skip_probe
        and checks.get("extension")
        and checks.get("recaptcha_ready")
        and ext_bridge
    )
    if _can_probe:
        try:
            # FIX-2: probe timeout 10s → 5s
            token = await ext_bridge.request_recaptcha(email, timeout=5.0)
            checks["probe_ok"] = bool(token and len(token) > 100)
        except Exception:
            checks["probe_ok"] = False
    elif not skip_probe:
        checks["probe_ok"] = False

    # FIX-1: Mandatory keys = extension + recaptcha_ready [+ probe_ok]
    # xcd_valid is deliberately excluded from mandatory to prevent cold-start loops.
    mandatory_keys = ["extension", "recaptcha_ready"]
    if not skip_probe:
        mandatory_keys.append("probe_ok")

    # ★ FIX L2: Check OAuth token freshness (non-blocking diagnostic)
    # If token is expired/missing, flag it but don't block — extension submit
    # doesn't need Bearer token. Only aiohttp fallback path needs it.
    token_ok = True
    try:
        session = getattr(account, '_session', None) or getattr(account, 'session', None)
        if session:
            token = getattr(session, 'access_token', None) or ""
            expires = getattr(session, 'token_expires', None)
            if not token:
                token_ok = False
            elif expires and time.time() > expires:
                token_ok = False
    except Exception:
        token_ok = False
    checks["token_fresh"] = token_ok

    failed_mandatory = [k for k in mandatory_keys if not checks.get(k)]

    # Include xcd and token as diagnostic info, not blocking failures
    all_failed = list(failed_mandatory)
    if not xcd_ok:
        all_failed.append("xcd_short_warning")
    if not token_ok:
        all_failed.append("token_stale_warning")

    return HealthResult(
        healthy=len(failed_mandatory) == 0,
        checks={**checks, "xcd_valid": xcd_ok},
        failed=all_failed,
    )


# ── Remedy Actions ────────────────────────────────────────────
# Each action is an async function(account, ext_bridge, **kwargs) → bool

async def _remedy_borrow_headers(account, ext_bridge, **kwargs):
    """Borrow x-client-data from another healthy account."""
    try:
        multi_account = kwargs.get("multi_account")
        if multi_account and hasattr(multi_account, 'fix_short_client_data'):
            multi_account.fix_short_client_data()
            log.info(f"[Remedy] {account.email}: borrowed x-client-data from healthy account")
            return True
    except Exception as e:
        log.warning(f"[Remedy] borrow_headers failed: {e}")
    return False


async def _remedy_reload_page(account, ext_bridge, **kwargs):
    """Navigate to /tools/flow to reload reCAPTCHA widget."""
    if ext_bridge:
        try:
            await ext_bridge._trigger_refresh(
                account.email, "smart_recovery_reload", level="full"
            )
            log.info(f"[Remedy] {account.email}: triggered full page reload")
            return True
        except Exception as e:
            log.warning(f"[Remedy] reload_page failed: {e}")
    return False


async def _remedy_soft_recovery(account, ext_bridge, **kwargs):
    """Soft browser recovery — navigate about:blank → VEO → re-init reCAPTCHA."""
    try:
        result = await account.soft_recover_browser()
        log.info(f"[Remedy] {account.email}: soft recovery → {'OK' if result else 'FAIL'}")
        return bool(result)
    except Exception as e:
        log.warning(f"[Remedy] soft_recovery failed: {e}")
    return False


async def _remedy_hard_restart(account, ext_bridge, **kwargs):
    """Hard browser restart — kill Chrome + relaunch."""
    try:
        result = await account.restart_browser()
        log.info(f"[Remedy] {account.email}: hard restart → {'OK' if result else 'FAIL'}")
        return bool(result)
    except Exception as e:
        log.warning(f"[Remedy] hard_restart failed: {e}")
    return False


async def _remedy_reload_tab(account, ext_bridge, **kwargs):
    """Reload the active VEO tab (respects 30s cooldown)."""
    if ext_bridge:
        try:
            await ext_bridge._trigger_refresh(
                account.email, "remedy_reload_tab", level="full"
            )
            log.info(f"[Remedy] {account.email}: tab reloaded via _trigger_refresh")
            return True
        except Exception as e:
            log.warning(f"[Remedy] reload_tab failed: {e}")
    return False


async def _remedy_refresh_token(account, ext_bridge, **kwargs):
    """Refresh OAuth access token — actually extract a new token.
    
    ★ FIX C2: Was only calling _trigger_refresh (page reload) which does NOT
    actually request a new access token. Now calls ensure_valid_token() first
    to get a real fresh Bearer token, then falls back to page reload.
    """
    email = account.email
    refreshed = False
    
    # Step 1: Try to get a REAL new access token via extension/token_manager
    try:
        if hasattr(account, 'ensure_valid_token'):
            new_token = await account.ensure_valid_token()
            if new_token:
                log.info(f"[Remedy] {email}: ✅ OAuth token refreshed ({len(new_token)} chars)")
                refreshed = True
    except Exception as e:
        log.debug(f"[Remedy] {email}: ensure_valid_token failed: {e}")
    
    # Step 2: Also trigger page reload to refresh cookies/headers
    if ext_bridge:
        try:
            await ext_bridge._trigger_refresh(
                email, "remedy_refresh_token", level="full"
            )
            if not refreshed:
                log.info(f"[Remedy] {email}: token refresh via page reload (fallback)")
                refreshed = True
        except Exception as e:
            log.warning(f"[Remedy] refresh_token page reload failed: {e}")
    
    return refreshed


async def _remedy_simulate_activity(account, ext_bridge, **kwargs):
    """Simulate user activity to warm up reCAPTCHA.
    
    ★ Cold profile enhancement: if the account hasn't established trust
    yet (_second_submit_ok not set), do 3x simulate_activity to rebuild
    behavioral history. Warm accounts get 1x (faster recovery).
    """
    if ext_bridge and ext_bridge.is_connected(account.email):
        try:
            # Check if account is still "cold" (trust not yet established)
            # Access supervisor's _second_submit_ok via engine reference
            _is_cold = True
            engine = getattr(account, '_engine', None)
            if engine and hasattr(engine, '_supervisors'):
                supervisor = engine._supervisors.get(account.email)
                if supervisor and supervisor._second_submit_ok.is_set():
                    _is_cold = False
            
            passes = 3 if _is_cold else 1
            log.info(
                f"[Remedy] {account.email}: simulate_activity "
                f"x{passes} ({'cold profile' if _is_cold else 'warm'})"
            )
            
            for i in range(passes):
                await ext_bridge.simulate_activity(account.email, timeout=5.0)
                if i < passes - 1:
                    await asyncio.sleep(2.0)
            
            await asyncio.sleep(2.0)
            log.info(f"[Remedy] {account.email}: simulated activity + warmup complete")
            return True
        except Exception as e:
            log.warning(f"[Remedy] simulate_activity failed: {e}")
    return False


async def _remedy_suspend(account, ext_bridge, **kwargs):
    """Suspend account via CreditWindow — always 'succeeds' as a last resort."""
    credit_window = kwargs.get("credit_window")
    dispatcher = kwargs.get("dispatcher")

    if credit_window:
        email = account.email
        # Force suspend
        h = credit_window._ensure(email)
        h.credits = 0
        h.suspended = True
        h.suspended_at = time.time()
        h.total_suspensions += 1

        # Migrate tasks
        if dispatcher and hasattr(dispatcher, 'migrate_tasks'):
            dispatcher.migrate_tasks(email)

        log.warning(
            f"[Remedy] {email}: ⛔ SUSPENDED + tasks migrated "
            f"(suspension #{h.total_suspensions})"
        )
    return True  # Always "succeeds" — recovery ends here


# ── Remedy Chains ─────────────────────────────────────────────

# Map action names to async functions
_ACTIONS = {
    "borrow_headers": _remedy_borrow_headers,
    "reload_page": _remedy_reload_page,
    "soft_recovery": _remedy_soft_recovery,
    "hard_restart": _remedy_hard_restart,
    "reload_tab": _remedy_reload_tab,
    "refresh_token": _remedy_refresh_token,
    "simulate_activity": _remedy_simulate_activity,
    "suspend": _remedy_suspend,
}

REMEDY_CHAINS: Dict[ErrorType, List[Remedy]] = {

    ErrorType.RECAPTCHA_403: [
        # wait_after 8s: cần thời gian đủ để reCAPTCHA Enterprise build trust score
        # trước khi health check verify probe_ok (tham chiếu: reference không dùng skip_probe)
        Remedy("simulate_activity", "Warm up tab before reload", 8),
        Remedy("reload_page", "Full page reload → fresh reCAPTCHA context", 10),
        Remedy("borrow_headers", "Copy x-client-data from healthy account", 0),
        Remedy("soft_recovery", "Navigate away + back → reset reCAPTCHA", 8),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
        # ★ FIX C1: hard_restart was defined but never used in any chain.
        # Nuclear option before suspend: kill Chrome + relaunch fresh PID.
        Remedy("hard_restart", "Kill Chrome + relaunch — fresh PID/session", 20),
        Remedy("suspend", "Suspend account + migrate tasks", 0),
    ],

    ErrorType.RECAPTCHA_TIMEOUT: [
        # ★ FIX: soft_recovery FIRST — only remedy that can fix dead DOM
        # Old order wasted 18s on simulate_activity+reload_tab on broken page
        Remedy("soft_recovery", "Navigate away/back — fix dead DOM first", 10),
        Remedy("simulate_activity", "Warm up tab after recovery", 5),
        Remedy("reload_tab", "Reload active tab", 5),
        Remedy("soft_recovery", "Extended soft recovery — full page reload", 15),
        Remedy("hard_restart", "Kill Chrome + relaunch — last resort", 20),
    ],

    ErrorType.TOKEN_TOO_SHORT: [
        Remedy("reload_page", "Navigate to /tools/flow for reCAPTCHA", 5),
        Remedy("soft_recovery", "Fresh reCAPTCHA context via soft recovery", 8),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
    ],

    ErrorType.TAB_FROZEN: [
        # ★ FIX: soft_recovery first — dead tabs can't respond to reload_tab
        Remedy("soft_recovery", "Navigate away/back — recover dead tab", 10),
        Remedy("reload_tab", "Reload tab after recovery", 5),
        Remedy("simulate_activity", "Warm up recovered tab", 5),
        Remedy("soft_recovery", "Extended soft recovery", 15),
        Remedy("hard_restart", "Kill Chrome + relaunch — last resort", 20),
    ],

    ErrorType.XCD_STUCK: [
        Remedy("borrow_headers", "Copy x-client-data from healthy account", 0),
        Remedy("reload_page", "Trigger Variations enrollment", 10),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
    ],

    ErrorType.AUTH_EXPIRED: [
        Remedy("refresh_token", "Refresh OAuth token via extension", 5),
        Remedy("reload_page", "Reload page for fresh cookies", 10),
        # ★ FIX C1: Escalate to hard_restart when token+reload fail
        Remedy("hard_restart", "Kill Chrome + relaunch for fresh auth", 20),
    ],

    ErrorType.NETWORK_ERROR: [
        # Network errors: just requeue, don't penalize account
    ],

    ErrorType.UNKNOWN: [
        Remedy("reload_tab", "Reload tab as general fix", 5),
        Remedy("soft_recovery", "Soft recovery as fallback", 8),
    ],
}


# ── Recovery Orchestrator ─────────────────────────────────────

def _clone_recovery_result(result: RecoveryResult) -> RecoveryResult:
    return replace(result)


def _get_recent_recovery_result(email: str, error_type: ErrorType) -> Optional[RecoveryResult]:
    ts = _last_recovery_ts.get(email, 0.0)
    if ts <= 0.0:
        return None
    if (time.monotonic() - ts) > _RECOVERY_DEDUP_WINDOW_SEC:
        return None
    cached = _last_recovery_result.get(email)
    if not cached or cached.error_type != error_type:
        return None
    return _clone_recovery_result(cached)


def _store_recovery_result(email: str, result: RecoveryResult):
    _last_recovery_ts[email] = time.monotonic()
    _last_recovery_result[email] = _clone_recovery_result(result)


async def execute_recovery(
    account,
    error_msg: str,
    context: Optional[dict] = None,
    ext_bridge=None,
    dispatcher=None,
    credit_window=None,
    multi_account=None,
) -> RecoveryResult:
    """Diagnose → Remedy → Verify → Resume or Failover.

    Main entry point — replaces the old Phase 0-3 state machine.

    Args:
        account: AccountManager for the failing account.
        error_msg: Raw error string from the failed submit.
        context: Optional dict with extra signals (token_len, tab_state, xcd_len).
        ext_bridge: ExtensionBridge instance.
        dispatcher: Dispatcher instance (for task migration).
        credit_window: CreditWindow instance (for credit tracking).
        multi_account: MultiAccountManager (for borrowing headers).

    Returns:
        RecoveryResult with success, remedy_used, failover flag, backoff.
    """
    email = account.email
    ctx = context or {}

    # Step 1: Classify error
    error_type = classify_error(error_msg, ctx)

    log.info(
        f"[Recovery] {email}: classified '{error_msg[:80]}' → {error_type.value}"
    )

    cached = _get_recent_recovery_result(email, error_type)
    if cached is not None:
        log.info(
            f"[Recovery] {email}: dedup cache hit "
            f"({error_type.value}, <{_RECOVERY_DEDUP_WINDOW_SEC:.0f}s)"
        )
        return cached

    lock = _recovery_locks.setdefault(email, asyncio.Lock())
    if lock.locked():
        log.info(
            f"[Recovery] {email}: skipped — another foreman is already "
            f"running recovery for {error_type.value}"
        )
        return RecoveryResult(
            success=False,
            error_type=error_type,
            remedy_used=None,
            attempts=0,
            failover=False,
            backoff=10,
        )

    async with lock:
        cached = _get_recent_recovery_result(email, error_type)
        if cached is not None:
            log.info(
                f"[Recovery] {email}: dedup cache hit after lock "
                f"({error_type.value})"
            )
            return cached

        # Step 2: Deduct credits
        if credit_window:
            cost = ERROR_CREDIT_COST.get(error_type, 1)
            suspended = credit_window.record_error(email, cost)
            if suspended:
                # Account just got suspended by credit deduction alone
                if dispatcher and hasattr(dispatcher, 'migrate_tasks'):
                    dispatcher.migrate_tasks(email)
                result = RecoveryResult(
                    success=False,
                    error_type=error_type,
                    remedy_used=None,
                    attempts=0,
                    failover=True,
                    backoff=0,
                )
                _store_recovery_result(email, result)
                return result

        # Step 3: Get remedy chain
        chain = REMEDY_CHAINS.get(error_type, [])

        if not chain:
            result = RecoveryResult(
                success=False,
                error_type=error_type,
                attempts=0,
                backoff=5,
            )
            _store_recovery_result(email, result)
            return result

        # Step 4: Try remedies one by one
        kwargs = {
            "credit_window": credit_window,
            "dispatcher": dispatcher,
            "multi_account": multi_account,
        }

        # skip_probe chỉ áp dụng cho các remedies kích hoạt reload thực sự:
        # reload_page/reload_tab trigger full page reload → widget cần 10-30s re-init.
        # simulate_activity KHÔNG skip probe: nó chỉ warm up + 8s wait, và sau đó
        # health check phải xác nhận probe_ok (token thực sự) trước khi return success.
        # borrow_headers và refresh_token cũng không trigger reload → probe vẫn hợp lệ.
        # Tham chiếu: reference code (2024-03) luôn dùng skip_probe=False cho tất cả.
        _skip_probe_remedies = {
            "reload_page",
            "reload_tab",
            "soft_recovery",
        }

        for i, remedy in enumerate(chain):
            log.info(
                f"[Recovery] {email}: trying remedy {i+1}/{len(chain)} "
                f"'{remedy.name}' — {remedy.description}"
            )

            # Execute remedy action
            action_fn = _ACTIONS.get(remedy.name)
            if not action_fn:
                log.warning(f"[Recovery] Unknown remedy action: {remedy.name}")
                continue

            try:
                action_ok = await action_fn(account, ext_bridge, **kwargs)
            except Exception as e:
                log.warning(f"[Recovery] Remedy '{remedy.name}' raised: {e}")
                action_ok = False

            # If this was the suspend remedy, we're done (failover)
            if remedy.name == "suspend":
                result = RecoveryResult(
                    success=False,
                    error_type=error_type,
                    remedy_used="suspend",
                    attempts=i + 1,
                    failover=True,
                    backoff=0,
                )
                _store_recovery_result(email, result)
                return result

            if not action_ok:
                log.warning(
                    f"[Recovery] Remedy '{remedy.name}' returned False, trying next"
                )
                continue

            # Wait after action
            if remedy.wait_after > 0:
                await asyncio.sleep(remedy.wait_after)

            # Verify health — skip probe chỉ cho reload remedies (widget đang re-init)
            _use_skip_probe = remedy.name in _skip_probe_remedies
            health = await verify_account_health(
                account, ext_bridge, skip_probe=_use_skip_probe
            )

            if health.healthy:
                log.info(
                    f"[Recovery] {email}: ✅ remedy '{remedy.name}' "
                    f"fixed the issue (attempt {i+1}/{len(chain)})"
                )
                # Give back some credits for successful self-heal
                if credit_window:
                    credit_window.record_success(email)

                result = RecoveryResult(
                    success=True,
                    error_type=error_type,
                    remedy_used=remedy.name,
                    attempts=i + 1,
                    backoff=max(3, int(remedy.wait_after)),
                )
                _store_recovery_result(email, result)
                return result

            log.warning(
                f"[Recovery] {email}: remedy '{remedy.name}' → "
                f"still unhealthy (failed: {health.failed})"
            )

        # Step 5: All remedies exhausted without explicit suspend
        # Force suspend
        log.warning(
            f"[Recovery] {email}: all {len(chain)} remedies exhausted "
            f"→ forcing suspension"
        )
        if credit_window:
            h = credit_window._ensure(email)
            h.credits = 0
            h.suspended = True
            h.suspended_at = time.time()
            h.total_suspensions += 1

        if dispatcher and hasattr(dispatcher, 'migrate_tasks'):
            dispatcher.migrate_tasks(email)

        result = RecoveryResult(
            success=False,
            error_type=error_type,
            remedy_used=None,
            attempts=len(chain),
            failover=True,
            backoff=0,
        )
        _store_recovery_result(email, result)
        return result
