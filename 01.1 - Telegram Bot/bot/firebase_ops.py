"""
Firebase Operations via REST API
=================================
CRUD operations on Firestore using authenticated REST API.
Writes to both Primary and Backup databases.
No Admin SDK needed.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import requests

from .firebase_auth import FirebaseAuth

log = logging.getLogger("veo.bot.ops")

# Firestore REST API base
_API_BASE = "https://firestore.googleapis.com/v1"


APP_COLLECTIONS = {
    "VEO": {
        "lic": "_lic",
        "trials": "_trials",
        "upgrade_requests": "_upgrade_requests",
        "rate_limit": "_rate_limit",
        "usage": "_usage",
        "mid_to_key": "_mid_to_key",
        "customers": "_customers",
        "blocked": "_blocked_machines",
    },
    "GROK": {
        "lic": "_lic_grok",
        "trials": "_grok_trials",
        "upgrade_requests": "_grok_upgrade_requests",
        "rate_limit": "_grok_rate_limit",
        "usage": "_grok_usage",
        "mid_to_key": "_grok_mid_to_key",
        "customers": "_grok_customers",
        "blocked": "_grok_blocked_machines",
    },
}


class FirebaseOps:
    """Firestore CRUD via REST API with dual-DB support."""

    COLLECTION = "_lic"
    REQUEST_COLLECTION = "_upgrade_requests"
    TIMEOUT = 10

    def __init__(self):
        self._primary_project = os.environ.get("FIREBASE_PRIMARY_PROJECT", "").strip()
        self._backup_project = os.environ.get("FIREBASE_BACKUP_PROJECT", "").strip()
        self._primary_api_key = os.environ.get("FIREBASE_PRIMARY_API_KEY", "").strip()
        self._backup_api_key = os.environ.get("FIREBASE_BACKUP_API_KEY", "").strip()
        self._current_app = "VEO"

        # Separate auth per project (each Firebase project has its own user pool)
        self.auth = FirebaseAuth(self._primary_api_key)
        self._backup_auth = FirebaseAuth(self._backup_api_key) if self._backup_api_key else None

    # ── App selector ──────────────────────────────────────

    def set_app(self, app_name: str):
        """Switch active app (VEO / GROK). Changes all collection targets."""
        app_name = app_name.upper()
        if app_name not in APP_COLLECTIONS:
            raise ValueError(f"Unknown app: {app_name}")
        self._current_app = app_name
        self.COLLECTION = APP_COLLECTIONS[app_name]["lic"]
        self.REQUEST_COLLECTION = APP_COLLECTIONS[app_name]["upgrade_requests"]

    def col(self, name: str) -> str:
        """Get collection name for current app."""
        return APP_COLLECTIONS[self._current_app][name]

    @property
    def current_app(self) -> str:
        return self._current_app

    def _get_auth_for(self, project: str) -> FirebaseAuth:
        """Get the correct auth instance for the given project."""
        if project == self._backup_project and self._backup_auth:
            return self._backup_auth
        return self.auth

    # ─── URL builders ──────────────────────────────────────────

    def _doc_url(self, project: str, collection: str, doc_id: str) -> str:
        return f"{_API_BASE}/projects/{project}/databases/(default)/documents/{collection}/{doc_id}"

    def _collection_url(self, project: str, collection: str) -> str:
        return f"{_API_BASE}/projects/{project}/databases/(default)/documents/{collection}"

    # ─── Firestore value parsing ───────────────────────────────

    def _parse_value(self, value: dict):
        if "stringValue" in value:
            return value["stringValue"]
        if "integerValue" in value:
            return int(value["integerValue"])
        if "booleanValue" in value:
            return value["booleanValue"]
        if "timestampValue" in value:
            return value["timestampValue"]
        if "doubleValue" in value:
            return float(value["doubleValue"])
        if "mapValue" in value:
            return {
                k: self._parse_value(v)
                for k, v in value["mapValue"].get("fields", {}).items()
            }
        if "nullValue" in value:
            return None
        return None

    def _parse_doc(self, doc: dict) -> Optional[dict]:
        if not doc or "fields" not in doc:
            return None
        return {k: self._parse_value(v) for k, v in doc["fields"].items()}

    def _to_firestore_value(self, val) -> dict:
        if val is None:
            return {"nullValue": None}
        if isinstance(val, bool):
            return {"booleanValue": val}
        if isinstance(val, int):
            return {"integerValue": str(val)}
        if isinstance(val, float):
            return {"doubleValue": val}
        if isinstance(val, str):
            return {"stringValue": val}
        if isinstance(val, datetime):
            return {"timestampValue": val.isoformat() + "Z"}
        if isinstance(val, dict):
            return {
                "mapValue": {
                    "fields": {k: self._to_firestore_value(v) for k, v in val.items()}
                }
            }
        return {"stringValue": str(val)}

    def _to_firestore_doc(self, data: dict) -> dict:
        return {"fields": {k: self._to_firestore_value(v) for k, v in data.items()}}

    # ─── Core READ ─────────────────────────────────────────────

    def read_doc(self, collection: str, doc_id: str) -> Optional[dict]:
        """Read a document from primary (fallback to backup if 404 or error)."""
        for project, api_key in [
            (self._primary_project, self._primary_api_key),
            (self._backup_project, self._backup_api_key),
        ]:
            if not project or not api_key:
                continue
            try:
                url = self._doc_url(project, collection, doc_id)
                headers = self._get_auth_for(project).get_auth_headers()
                resp = requests.get(url, headers=headers, timeout=self.TIMEOUT)
                if resp.status_code == 200:
                    return self._parse_doc(resp.json())
                if resp.status_code == 404:
                    continue  # Try backup — data may exist on other server
            except Exception as e:
                log.warning(f"[OPS] Read {collection}/{doc_id} from {project}: {e}")
                continue
        return None

    def list_docs(self, collection: str, page_size: int = 100) -> list:
        """List documents from a collection (merged from both DBs, deduplicated)."""
        seen_ids = {}  # doc_id -> parsed data (dedup)
        for project, api_key in [
            (self._primary_project, self._primary_api_key),
            (self._backup_project, self._backup_api_key),
        ]:
            if not project:
                continue
            try:
                url = self._collection_url(project, collection)
                headers = self._get_auth_for(project).get_auth_headers()
                resp = requests.get(
                    url, headers=headers,
                    params={"pageSize": page_size},
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    docs = resp.json().get("documents", [])
                    for doc in docs:
                        parsed = self._parse_doc(doc)
                        if parsed:
                            # Extract doc ID from name path
                            name = doc.get("name", "")
                            doc_id = name.split("/")[-1] if "/" in name else name
                            parsed["_doc_id"] = doc_id
                            if doc_id not in seen_ids:
                                seen_ids[doc_id] = parsed
            except Exception as e:
                log.warning(f"[OPS] List {collection} from {project}: {e}")
                continue
        return list(seen_ids.values())

    # ─── Core WRITE (dual-DB) ──────────────────────────────────

    def write_doc(self, collection: str, doc_id: str, data: dict) -> bool:
        """Write/merge fields into document on BOTH primary and backup.

        Uses updateMask to merge only specified fields (not replace entire doc).
        """
        payload = self._to_firestore_doc(data)
        # Build updateMask so PATCH merges instead of replacing
        mask_params = [("updateMask.fieldPaths", k) for k in data.keys()]
        success = False

        for project, label in [
            (self._primary_project, "primary"),
            (self._backup_project, "backup"),
        ]:
            if not project:
                continue
            try:
                url = self._doc_url(project, collection, doc_id)
                headers = self._get_auth_for(project).get_auth_headers()
                resp = requests.patch(
                    url, headers=headers, json=payload,
                    params=mask_params, timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    success = True
                    log.info(f"[OPS] ✅ Write {collection}/{doc_id[:16]}... → {label}")
                else:
                    log.warning(f"[OPS] ⚠️ Write {label} failed: {resp.status_code} {resp.text[:80]}")
            except Exception as e:
                log.warning(f"[OPS] ⚠️ Write {label} error: {e}")

        return success

    def delete_doc(self, collection: str, doc_id: str) -> bool:
        """Delete document from both DBs."""
        success = False
        for project, label in [
            (self._primary_project, "primary"),
            (self._backup_project, "backup"),
        ]:
            if not project:
                continue
            try:
                url = self._doc_url(project, collection, doc_id)
                headers = self._get_auth_for(project).get_auth_headers()
                resp = requests.delete(url, headers=headers, timeout=self.TIMEOUT)
                if resp.status_code in (200, 404):
                    success = True
            except Exception as e:
                log.warning(f"[OPS] Delete {label} error: {e}")
        return success

    # ─── License Operations ────────────────────────────────────

    def get_license(self, key: str) -> Optional[dict]:
        return self.read_doc(self.COLLECTION, key)

    def get_license_by_mid(self, mid: str) -> Optional[dict]:
        """Find active license by Machine ID (via _mid_to_key index)."""
        index = self.read_doc(self.col("mid_to_key"), mid)
        if index and index.get("key"):
            key = index["key"]
            lic = self.get_license(key)
            if lic:
                lic["_doc_id"] = key
            return lic
        return None

    def create_license(self, key: str, data: dict) -> bool:
        return self.write_doc(self.COLLECTION, key, data)

    def revoke_license(self, key: str, reason: str = "bot_admin") -> bool:
        return self.write_doc(self.COLLECTION, key, {
            "_st": "r",
            "_rv_at": datetime.utcnow().isoformat() + "Z",
            "_rv_reason": reason,
        })

    _MID_KEY_SALT = b'VEO_MID_KEY_ENCRYPT_2026_v1'

    def _encrypt_for_mid(self, plaintext: str, mid: str) -> str:
        """Encrypt plaintext using HMAC-SHA256 XOR (matches seller/admin)."""
        import hmac as _hmac, hashlib, base64
        derived = _hmac.new(self._MID_KEY_SALT, mid.encode(), hashlib.sha256).digest()
        encrypted = bytes(b ^ derived[i % len(derived)]
                          for i, b in enumerate(plaintext.encode('utf-8')))
        return base64.b64encode(encrypted).decode('ascii')

    def write_mid_to_key(self, mid: str, key: str, tier: str, role: int,
                         expires: str = "") -> bool:
        data = {
            "_ek": self._encrypt_for_mid(key, mid),
            "key": "****",
            "tier": tier,
            "role": role,
            "status": "a",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if expires:
            data["expires"] = expires
        return self.write_doc(self.col("mid_to_key"), mid, data)

    def delete_mid_to_key(self, mid: str) -> bool:
        return self.delete_doc(self.col("mid_to_key"), mid)

    # ─── Request Operations ────────────────────────────────────

    def get_pending_requests(self) -> list:
        """Get all pending upgrade requests."""
        all_reqs = self.list_docs(self.REQUEST_COLLECTION)
        return [r for r in all_reqs if r.get("status") == "pending"]

    def claim_request(self, request_id: str, admin_name: str) -> Tuple[bool, Optional[dict]]:
        """Atomically claim a request (prevent duplicate processing)."""
        data = self.read_doc(self.REQUEST_COLLECTION, request_id)
        if not data:
            return False, None
        if data.get("status") != "pending":
            return False, None

        # Mark as processing
        self.write_doc(self.REQUEST_COLLECTION, request_id, {
            "status": "processing",
            "_claimed_by": admin_name,
            "_claimed_at": datetime.utcnow().isoformat() + "Z",
        })
        return True, data

    def delete_request(self, request_id: str) -> bool:
        return self.delete_doc(self.REQUEST_COLLECTION, request_id)

    # ─── Trial Operations ──────────────────────────────────────

    def create_trial(self, mid: str, data: dict) -> bool:
        return self.write_doc(self.col("trials"), mid, data)

    # ─── Machine Block Operations ──────────────────────────────

    BLOCKED_COLLECTION = "_blocked_machines"  # Legacy, prefer col('blocked')

    def block_machine(self, mid: str, reason: str = "",
                      blocked_by: str = "telegram_bot") -> bool:
        """Block a machine ID — prevents license usage."""
        return self.write_doc(self.col("blocked"), mid, {
            "blocked": True,
            "reason": reason,
            "blocked_by": blocked_by,
            "blocked_at": datetime.utcnow().isoformat() + "Z",
        })

    def unblock_machine(self, mid: str) -> bool:
        """Unblock a machine ID — removes from blocked list."""
        return self.delete_doc(self.col("blocked"), mid)

    def is_machine_blocked(self, mid: str) -> bool:
        """Check if a machine ID is blocked."""
        data = self.read_doc(self.col("blocked"), mid)
        return bool(data and data.get("blocked"))

    # ─── Customer Operations ───────────────────────────────────

    def write_customer(self, mid: str, data: dict) -> bool:
        return self.write_doc(self.col("customers"), mid, data)

    def get_customer(self, mid: str) -> Optional[dict]:
        return self.read_doc(self.col("customers"), mid)

    # ─── Summary ───────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Get license counts by status + role breakdown.

        Auto-detects expired by _exp date (not just _st field).
        """
        all_keys = self.list_docs(self.COLLECTION, page_size=500)
        trials = self.list_docs(self.col("trials"), page_size=200)
        sellers = self.list_docs("_sellers", page_size=100)

        summary = {
            "active": 0, "revoked": 0, "expired": 0, "total": len(all_keys),
            "premium": 0, "tester": 0,
            "trial_active": 0, "trial_upgraded": 0, "trial_total": len(trials),
            "seller_total": len(sellers),
        }

        now = datetime.now()
        for key in all_keys:
            st = key.get("_st", "")
            role = key.get("_role", 1)

            # Auto-detect expired by date (status may still be 'a')
            if st == "a":
                exp_str = key.get("_exp", "")
                if exp_str:
                    try:
                        exp_dt = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
                        if exp_dt.tzinfo:
                            exp_dt = exp_dt.replace(tzinfo=None)
                        if exp_dt < now:
                            st = "e"  # Treat as expired
                    except Exception:
                        pass

            if st == "r":
                summary["revoked"] += 1
            elif st == "e":
                summary["expired"] += 1
            elif st == "a":
                summary["active"] += 1
            if role == 2:
                summary["tester"] += 1
            else:
                summary["premium"] += 1

        for t in trials:
            st = t.get("status", "active")
            if st == "active":
                summary["trial_active"] += 1
            elif st == "upgraded":
                summary["trial_upgraded"] += 1

        return summary

    # ─── Health Check ──────────────────────────────────────────

    def check_health(self) -> dict:
        """Check connectivity to both DBs."""
        result = {"primary": False, "backup": False}

        for project, label in [
            (self._primary_project, "primary"),
            (self._backup_project, "backup"),
        ]:
            if not project:
                continue
            try:
                url = f"{_API_BASE}/projects/{project}/databases/(default)/documents/_config/client_settings"
                headers = self._get_auth_for(project).get_auth_headers()
                resp = requests.get(url, headers=headers, timeout=5)
                result[label] = resp.status_code in (200, 404)
            except Exception:
                pass

        return result

    # ─── Config Management (_config/client_settings) ──────────

    CONFIG_COLLECTION = "_config"
    CONFIG_DOC = "client_settings"
    PRICING_DOC = "pricing"

    DEFAULT_CONFIG = {
        "min_client_version": "1.0.0",
        "maintenance_mode": False,
        "server_weight": 50,
        "trial_poll_interval_ms": 300000,
        "trial_poll_max": 6,
        "validate_cache_ttl_s": 3600,
    }

    DEFAULT_PRICING = {
        "1M":  {"label": "1 Tháng",   "first_price": 200000,   "normal_price": 300000,   "days": 30},
        "3M":  {"label": "3 Tháng",   "first_price": 400000,   "normal_price": 500000,   "days": 90},
        "6M":  {"label": "6 Tháng",   "first_price": 600000,   "normal_price": 800000,   "days": 180},
        "1Y":  {"label": "1 Năm",     "first_price": 1000000,  "normal_price": 1200000,  "days": 365},
        "LT":  {"label": "Vĩnh viễn", "first_price": 3000000,  "normal_price": 3000000,  "days": 36500},
    }

    def read_config(self) -> dict:
        """Read _config/client_settings from primary DB."""
        data = self.read_doc(self.CONFIG_COLLECTION, self.CONFIG_DOC)
        if data:
            # Remove internal fields
            data.pop("_doc_id", None)
            return data
        return {}

    def write_config(self, key: str, value) -> bool:
        """Write a single config value to _config/client_settings (both DBs)."""
        return self.write_doc(self.CONFIG_COLLECTION, self.CONFIG_DOC, {key: value})

    def read_pricing(self) -> dict:
        """Read _config/pricing from primary DB."""
        data = self.read_doc(self.CONFIG_COLLECTION, self.PRICING_DOC)
        if data:
            data.pop("_doc_id", None)
            return data
        return {}

    def write_pricing(self, tier_code: str, first_price: int = None, normal_price: int = None) -> bool:
        """Write pricing for a tier to _config/pricing (both DBs).

        Args:
            tier_code: Tier code (1M, 3M, 6M, 1Y, LT)
            first_price: First purchase price (None = don't change)
            normal_price: Normal/regular purchase price (None = don't change)
        """
        tier_data = self.DEFAULT_PRICING.get(tier_code, {}).copy()
        if first_price is not None:
            tier_data["first_price"] = first_price
        if normal_price is not None:
            tier_data["normal_price"] = normal_price
        return self.write_doc(self.CONFIG_COLLECTION, self.PRICING_DOC, {tier_code: tier_data})

    # ─── Sync Operations ──────────────────────────────────────

    def get_db_doc_counts(self) -> dict:
        """Get document counts per collection on both primary and backup."""
        collections = [self.COLLECTION, self.col("trials"), "_sellers"]
        result = {"primary": {}, "backup": {}, "primary_project": "", "backup_project": ""}

        for project, api_key, label in [
            (self._primary_project, self._primary_api_key, "primary"),
            (self._backup_project, self._backup_api_key, "backup"),
        ]:
            if not project:
                continue
            result[f"{label}_project"] = project
            for col in collections:
                try:
                    url = self._collection_url(project, col)
                    headers = self._get_auth_for(project).get_auth_headers()
                    resp = requests.get(
                        url, headers=headers,
                        params={"pageSize": 500},
                        timeout=self.TIMEOUT,
                    )
                    if resp.status_code == 200:
                        docs = resp.json().get("documents", [])
                        result[label][col] = len(docs)
                    else:
                        result[label][col] = -1  # Error
                except Exception:
                    result[label][col] = -1

        return result

    def sync_collection(self, collection: str) -> dict:
        """Sync missing docs from primary → backup for a collection.

        Returns: {"synced": int, "errors": int, "skipped": int}
        """
        stats = {"synced": 0, "errors": 0, "skipped": 0}

        if not self._primary_project or not self._backup_project:
            return stats

        # Get all doc IDs from both
        primary_docs = {}
        backup_ids = set()

        try:
            # Read primary
            url = self._collection_url(self._primary_project, collection)
            headers = self._get_auth_for(self._primary_project).get_auth_headers()
            resp = requests.get(url, headers=headers, params={"pageSize": 500}, timeout=self.TIMEOUT)
            if resp.status_code == 200:
                for doc in resp.json().get("documents", []):
                    name = doc.get("name", "")
                    doc_id = name.split("/")[-1] if "/" in name else name
                    parsed = self._parse_doc(doc)
                    if parsed:
                        primary_docs[doc_id] = parsed

            # Read backup IDs
            url = self._collection_url(self._backup_project, collection)
            headers = self._get_auth_for(self._backup_project).get_auth_headers()
            resp = requests.get(url, headers=headers, params={"pageSize": 500}, timeout=self.TIMEOUT)
            if resp.status_code == 200:
                for doc in resp.json().get("documents", []):
                    name = doc.get("name", "")
                    doc_id = name.split("/")[-1] if "/" in name else name
                    backup_ids.add(doc_id)

        except Exception as e:
            log.warning(f"[OPS] Sync read error: {e}")
            return stats

        # Write missing docs to backup
        for doc_id, data in primary_docs.items():
            if doc_id in backup_ids:
                stats["skipped"] += 1
                continue
            try:
                data.pop("_doc_id", None)
                payload = self._to_firestore_doc(data)
                url = self._doc_url(self._backup_project, collection, doc_id)
                headers = self._get_auth_for(self._backup_project).get_auth_headers()
                resp = requests.patch(url, headers=headers, json=payload, timeout=self.TIMEOUT)
                if resp.status_code == 200:
                    stats["synced"] += 1
                else:
                    stats["errors"] += 1
            except Exception:
                stats["errors"] += 1

        return stats
