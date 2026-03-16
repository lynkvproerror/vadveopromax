"""
Remedy Registry — Error-specific recovery chains + orchestrator.

Each ErrorType maps to a chain of Remedy actions, tried in order.
After each remedy, account health is verified. If healthy → resume.
If all remedies exhausted → failover to another account via CreditWindow.

Replaces the old Phase 0-3 state machine in engine.py.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from core.error_classifier import ErrorType, classify_error, ERROR_CREDIT_COST
from config.constants import MIN_VALID_XCD

log = logging.getLogger(__name__)


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
    """
    checks = {}
    email = account.email
    
    # 1. Extension connected?
    if ext_bridge:
        checks["extension"] = ext_bridge.is_connected(email)
    else:
        checks["extension"] = False
    
    # 2. x-client-data valid length?
    # Fix #4a: Threshold 100→40 to match _wait_for_account_ready MIN_GOOD.
    # HAR-verified: valid x-client-data is 48+ chars. 100 was too strict.
    if ext_bridge and hasattr(ext_bridge, '_header_cache'):
        cache = ext_bridge._header_cache.get(email, {})
        xcd = cache.get("x-client-data", "")
        checks["xcd_valid"] = len(xcd) > MIN_VALID_XCD
    else:
        checks["xcd_valid"] = True  # Can't check = assume OK
    
    # 3. reCAPTCHA ready?
    if ext_bridge and checks.get("extension"):
        try:
            ready = await ext_bridge.check_recaptcha_ready(email, timeout=10)
            checks["recaptcha_ready"] = ready
        except Exception:
            checks["recaptcha_ready"] = False
    else:
        checks["recaptcha_ready"] = False
    
    # 4. Probe request (only if all other checks pass)
    # Fix #4b: Use reCAPTCHA token generation as probe instead of
    # lightweight headers refresh. This actually tests the critical
    # path that fails in production (abc14 passed old probe but
    # failed first real task with 403).
    if not skip_probe and all(checks.values()) and ext_bridge:
        try:
            # Generate a real reCAPTCHA token — this tests the full
            # reCAPTCHA pipeline (widget loaded + evaluation OK)
            token = await ext_bridge.request_recaptcha(
                email, timeout=10
            )
            checks["probe_ok"] = bool(token and len(token) > 100)
        except Exception:
            checks["probe_ok"] = False
    elif not skip_probe:
        checks["probe_ok"] = False
    
    failed = [k for k, v in checks.items() if not v]
    
    return HealthResult(
        healthy=len(failed) == 0,
        checks=checks,
        failed=failed,
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
    """Reload the active VEO tab."""
    if ext_bridge:
        try:
            await ext_bridge.refresh_headers(account.email, timeout=10)
            log.info(f"[Remedy] {account.email}: tab reloaded via refresh_headers")
            return True
        except Exception as e:
            log.warning(f"[Remedy] reload_tab failed: {e}")
    return False


async def _remedy_refresh_token(account, ext_bridge, **kwargs):
    """Refresh OAuth access token via extension."""
    if ext_bridge:
        try:
            await ext_bridge.refresh_headers(account.email, timeout=15)
            log.info(f"[Remedy] {account.email}: token refreshed via extension")
            return True
        except Exception as e:
            log.warning(f"[Remedy] refresh_token failed: {e}")
    return False


async def _remedy_simulate_activity(account, ext_bridge, **kwargs):
    """Simulate user activity to warm up reCAPTCHA."""
    if ext_bridge and ext_bridge.is_connected(account.email):
        try:
            await ext_bridge.simulate_activity(account.email, timeout=5.0)
            await asyncio.sleep(2.0)
            log.info(f"[Remedy] {account.email}: simulated activity + warmup")
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
        Remedy("simulate_activity", "Warm up tab before reload", 2),
        Remedy("reload_page", "Full page reload → fresh reCAPTCHA context", 10),
        Remedy("borrow_headers", "Copy x-client-data from healthy account", 0),
        Remedy("soft_recovery", "Navigate away + back → reset reCAPTCHA", 8),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
        Remedy("suspend", "Suspend account + migrate tasks", 0),
    ],
    
    ErrorType.RECAPTCHA_TIMEOUT: [
        Remedy("simulate_activity", "Warm up tab with simulated activity", 3),
        Remedy("reload_tab", "Reload active tab", 5),
        Remedy("soft_recovery", "Soft browser recovery", 8),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
    ],
    
    ErrorType.TOKEN_TOO_SHORT: [
        Remedy("reload_page", "Navigate to /tools/flow for reCAPTCHA", 5),
        Remedy("soft_recovery", "Fresh reCAPTCHA context via soft recovery", 8),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
    ],
    
    ErrorType.TAB_FROZEN: [
        Remedy("reload_tab", "Reload frozen tab", 5),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
    ],
    
    ErrorType.XCD_STUCK: [
        Remedy("borrow_headers", "Copy x-client-data from healthy account", 0),
        Remedy("reload_page", "Trigger Variations enrollment", 10),
        Remedy("soft_recovery", "Extended soft recovery — navigate away/back", 15),
    ],
    
    ErrorType.AUTH_EXPIRED: [
        Remedy("refresh_token", "Refresh OAuth token via extension", 5),
        Remedy("reload_page", "Reload page for fresh cookies", 10),
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
    
    # Step 2: Deduct credits
    if credit_window:
        cost = ERROR_CREDIT_COST.get(error_type, 1)
        suspended = credit_window.record_error(email, cost)
        if suspended:
            # Account just got suspended by credit deduction alone
            if dispatcher and hasattr(dispatcher, 'migrate_tasks'):
                dispatcher.migrate_tasks(email)
            return RecoveryResult(
                success=False,
                error_type=error_type,
                remedy_used=None,
                attempts=0,
                failover=True,
                backoff=0,
            )
    
    # Step 3: Get remedy chain
    chain = REMEDY_CHAINS.get(error_type, [])
    
    if not chain:
        # No remedies registered (e.g. NETWORK_ERROR)
        return RecoveryResult(
            success=False,
            error_type=error_type,
            attempts=0,
            backoff=5,
        )
    
    # Step 4: Try remedies one by one
    kwargs = {
        "credit_window": credit_window,
        "dispatcher": dispatcher,
        "multi_account": multi_account,
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
            return RecoveryResult(
                success=False,
                error_type=error_type,
                remedy_used="suspend",
                attempts=i + 1,
                failover=True,
                backoff=0,
            )
        
        if not action_ok:
            log.warning(f"[Recovery] Remedy '{remedy.name}' returned False, trying next")
            continue
        
        # Wait after action
        if remedy.wait_after > 0:
            await asyncio.sleep(remedy.wait_after)
        
        # Verify health
        health = await verify_account_health(
            account, ext_bridge, skip_probe=False
        )
        
        if health.healthy:
            log.info(
                f"[Recovery] {email}: ✅ remedy '{remedy.name}' "
                f"fixed the issue (attempt {i+1}/{len(chain)})"
            )
            # Give back some credits for successful self-heal
            if credit_window:
                credit_window.record_success(email)
            
            return RecoveryResult(
                success=True,
                error_type=error_type,
                remedy_used=remedy.name,
                attempts=i + 1,
                backoff=max(3, int(remedy.wait_after)),
            )
        
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
    
    return RecoveryResult(
        success=False,
        error_type=error_type,
        remedy_used=None,
        attempts=len(chain),
        failover=True,
        backoff=0,
    )
