"""
License Validation API — Server-Side Hardware Attestation
==========================================================
Vercel serverless function that validates license keys with
server-side hardware verification.

Client sends RAW hardware components → server independently
computes machine_id hash → server verifies against stored binding.

This prevents machine_id spoofing attacks where an attacker patches
the client binary to fake get_machine_id().

Route: POST /api/license/validate
"""

import json
import hashlib
import hmac as hmac_lib
import logging
import os
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler

# Add parent dir to path for bot imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veo.api.license")

# ── Constants ──────────────────────────────────────────────────

# HMAC secret for request token validation (must match client)
_HMAC_DERIVE_KEY = b'veo_rest_derive_2026'
_HMAC_DERIVE_SUFFIX = '||REST_HMAC'

# App collection mapping
_APP_COLLECTIONS = {
    "veo": {"lic": "_lic", "mid_to_key": "_mid_to_key", "blocked": "_blocked_machines"},
    "grok": {"lic": "_lic_grok", "mid_to_key": "_grok_mid_to_key", "blocked": "_grok_blocked_machines"},
}

# API secret for client authentication (shared secret, NOT user-specific)
# Set via environment variable: LICENSE_API_SECRET
# Client must send this in X-Api-Secret header


# ── Hardware Verification ──────────────────────────────────────

def compute_machine_id(hw: dict) -> str:
    """
    Recompute machine_id from raw hardware components.
    MUST match HardwareFingerprint.get_machine_id() on client.
    
    Client formula (license_client.py:208-216):
        combined = '|'.join([cpu_id, mb_serial, mb_uuid, bios_serial, disk_serial])
        return sha256(combined).hexdigest()
    """
    combined = '|'.join([
        hw.get('cpu_id', ''),
        hw.get('mb_serial', ''),
        hw.get('mb_uuid', ''),
        hw.get('bios_serial', ''),
        hw.get('disk_serial', ''),
    ])
    return hashlib.sha256(combined.encode()).hexdigest()


def hash_component(value: str) -> str:
    """Hash individual hw component for storage (privacy)."""
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def verify_hw_components(hw: dict, stored_hw: dict) -> bool:
    """
    Verify each hardware component against stored hashes.
    Returns True only if ALL components match.
    """
    for key in ('cpu_id', 'mb_serial', 'mb_uuid', 'bios_serial', 'disk_serial'):
        sent_value = hw.get(key, '')
        stored_hash = stored_hw.get(key, '')
        if not stored_hash:
            continue  # Component not stored yet (first bind)
        if hash_component(sent_value) != stored_hash:
            return False
    return True


# ── Request Token Verification ─────────────────────────────────

def verify_request_token(machine_id: str, token: str, max_age_minutes: int = 30) -> bool:
    """
    Verify HMAC request token from client.
    Matches FirebaseRESTClient._generate_request_token() on client.
    """
    if not token or ':' not in token:
        return False
    try:
        ts_bucket, sig = token.split(':', 1)
        current_bucket = int(time.time()) // 300
        token_bucket = int(ts_bucket)

        # Check age
        age_buckets = current_bucket - token_bucket
        if age_buckets < 0 or age_buckets > (max_age_minutes // 5):
            return False

        # Recompute HMAC with derived key
        derived_key = hmac_lib.new(
            _HMAC_DERIVE_KEY,
            (machine_id + _HMAC_DERIVE_SUFFIX).encode(),
            hashlib.sha256
        ).digest()
        msg = f"{machine_id}{ts_bucket}".encode()
        expected = hmac_lib.new(derived_key, msg, hashlib.sha256).hexdigest()[:32]
        return hmac_lib.compare_digest(sig, expected)
    except Exception:
        return False


# ── Core Validation Logic ──────────────────────────────────────

def handle_validate(body: dict) -> dict:
    """
    Main validation handler.
    
    Args:
        body: {
            "action": "activate" | "validate",
            "license_key": "XXXX-...",
            "hw": {"cpu_id": ..., "mb_serial": ..., "mb_uuid": ..., "bios_serial": ..., "disk_serial": ...},
            "app": "veo" | "grok",  (optional, default "veo")
            "_token": "timestamp:hmac"  (HMAC request token)
        }
    
    Returns:
        {"valid": bool, "tier": str, "expires": str, "role": int, ...}
    """
    from bot.firebase_ops import FirebaseOps

    # ── Extract & validate inputs ──
    action = body.get("action", "validate")
    license_key = (body.get("license_key") or "").strip()
    hw = body.get("hw") or {}
    app = (body.get("app") or "veo").lower()
    token = body.get("_token", "")

    if not license_key:
        return {"valid": False, "error": "missing_license_key"}

    if app not in _APP_COLLECTIONS:
        return {"valid": False, "error": "invalid_app"}

    # ── Validate hardware components ──
    required_hw = ('cpu_id', 'mb_serial', 'mb_uuid', 'bios_serial', 'disk_serial')
    for key in required_hw:
        val = hw.get(key, '')
        if not val or not isinstance(val, str) or len(val) < 2:
            return {"valid": False, "error": f"missing_hw_{key}"}

    # ── Compute machine_id from hardware ──
    computed_mid = compute_machine_id(hw)
    log.info(f"[VALIDATE] key={license_key[:8]}... mid={computed_mid[:12]}... action={action}")

    # ── Verify request token (MANDATORY) ──
    # HMAC token proves the caller has the same derive key as the real client.
    # Without this, anyone who knows the URL can probe license keys.
    if not verify_request_token(computed_mid, token):
        log.warning(f"[VALIDATE] ⛔ Missing/invalid HMAC token for {computed_mid[:12]}...")
        return {"valid": False, "error": "invalid_token"}
    
    # ── Firebase operations ──
    ops = FirebaseOps()
    collections = _APP_COLLECTIONS[app]

    # Check if machine is blocked
    blocked = ops.read_doc(collections["blocked"], computed_mid)
    if blocked and blocked.get("blocked"):
        log.warning(f"[VALIDATE] 🚫 Blocked machine: {computed_mid[:12]}...")
        return {"valid": False, "error": "machine_blocked"}

    # Read license document
    lic_collection = collections["lic"]
    lic_data = ops.read_doc(lic_collection, license_key)

    # ── UNIFIED ERROR: All failures return same error to prevent enumeration ──
    # Attacker cannot distinguish between:
    #   - key doesn't exist
    #   - key exists but wrong machine
    #   - key revoked / expired
    _FAIL = {"valid": False, "error": "validation_failed"}

    if not lic_data:
        log.info(f"[VALIDATE] Key not found: {license_key[:8]}...")
        return _FAIL

    # ── Check revoked ──
    if lic_data.get("_st") == "r" or lic_data.get("revoked"):
        log.info(f"[VALIDATE] License revoked: {license_key[:8]}...")
        return _FAIL

    # ── Check expiry ──
    exp_str = lic_data.get("_exp") or lic_data.get("expires") or ""
    if exp_str:
        try:
            if isinstance(exp_str, str):
                exp_dt = datetime.fromisoformat(exp_str.replace('Z', '+00:00'))
                if exp_dt.tzinfo:
                    exp_dt = exp_dt.replace(tzinfo=None)
                if exp_dt < datetime.now():
                    log.info(f"[VALIDATE] License expired: {license_key[:8]}...")
                    return _FAIL
        except Exception:
            pass

    # ── Machine ID verification ──
    stored_mid = (lic_data.get("_mid") or lic_data.get("machine_id") or "").lower()

    if stored_mid and stored_mid != computed_mid:
        log.warning(
            f"[VALIDATE] ❌ Machine mismatch! "
            f"stored={stored_mid[:12]}... computed={computed_mid[:12]}..."
        )
        return _FAIL

    # ── Hardware component verification ──
    stored_hw = lic_data.get("_hw") or {}

    if stored_hw:
        # Subsequent validation: verify each component matches
        if not verify_hw_components(hw, stored_hw):
            log.warning(
                f"[VALIDATE] ❌ Hardware component mismatch for {computed_mid[:12]}... "
                f"— possible spoofing attempt"
            )
            return _FAIL
        log.info(f"[VALIDATE] ✅ Hardware components verified for {computed_mid[:12]}...")
    else:
        # First-time binding: store hashed hw components
        if stored_mid == computed_mid:
            hw_to_store = {
                "cpu_id": hash_component(hw["cpu_id"]),
                "mb_serial": hash_component(hw["mb_serial"]),
                "mb_uuid": hash_component(hw["mb_uuid"]),
                "bios_serial": hash_component(hw["bios_serial"]),
                "disk_serial": hash_component(hw["disk_serial"]),
            }
            ops.write_doc(lic_collection, license_key, {
                "_hw": hw_to_store,
                "_hw_bound_at": datetime.utcnow().isoformat() + "Z",
            })
            log.info(f"[VALIDATE] 🔐 First-time HW binding for {computed_mid[:12]}...")

    # ── Build response ──
    tier_code = lic_data.get("_t") or lic_data.get("tier") or "TRIA"
    role = lic_data.get("_role") or lic_data.get("role") or 1
    client_name = lic_data.get("_cn") or lic_data.get("client_name") or ""
    lim = lic_data.get("_lim")

    response = {
        "valid": True,
        "tier": tier_code,
        "role": role,
        "expires": exp_str,
        "client_name": client_name,
        "machine_id": computed_mid,
        "_hw_bound": bool(stored_hw or (stored_mid == computed_mid)),
    }

    if lim:
        response["_lim"] = lim

    log.info(f"[VALIDATE] ✅ Valid: key={license_key[:8]}... tier={tier_code}")
    return response


# ── Vercel Handler ─────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for license validation."""

    def do_POST(self):
        try:
            # ── Verify API secret ──
            api_secret = os.environ.get("LICENSE_API_SECRET", "").strip()
            if api_secret:
                client_secret = self.headers.get("X-Api-Secret", "").strip()
                if client_secret != api_secret:
                    log.warning("[LICENSE_API] ⛔ Invalid API secret")
                    self._send_json(403, {"valid": False, "error": "forbidden"})
                    return

            # ── Read body ──
            length = int(self.headers.get("Content-Length", 0))
            if length > 10000:  # 10KB max body
                self._send_json(413, {"valid": False, "error": "body_too_large"})
                return

            body_raw = self.rfile.read(length)
            if not body_raw:
                self._send_json(400, {"valid": False, "error": "empty_body"})
                return

            body = json.loads(body_raw)

            # ── Handle validation ──
            result = handle_validate(body)
            self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_json(400, {"valid": False, "error": "invalid_json"})
        except Exception as e:
            log.error(f"[LICENSE_API] Error: {e}", exc_info=True)
            self._send_json(500, {"valid": False, "error": "internal_error"})

    def do_GET(self):
        """Health check."""
        self._send_json(200, {"status": "ok", "service": "veo-license-validate"})

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        log.info(format % args)
