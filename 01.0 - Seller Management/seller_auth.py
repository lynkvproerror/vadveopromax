"""
Seller Authentication & Firebase Backend
Handles: login, permissions, session tokens, audit trail, brute-force protection
"""

import os
import sys
import hashlib
import hmac as _hmac
import base64
import json
import socket
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# Seller app is self-contained — no cross-folder imports needed

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False


# ============================================================
# MACHINE ID (same logic as client app)
# ============================================================

def get_machine_id() -> str:
    """Get unique machine identifier (Windows WMI)."""
    try:
        import subprocess
        result = subprocess.run(
            ['wmic', 'csproduct', 'get', 'UUID'],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line and line != 'UUID':
                return hashlib.sha256(line.encode()).hexdigest().upper()
    except Exception:
        pass
    # Fallback: hostname + username + MAC (harder to guess than just hostname)
    import uuid
    fallback = f"{socket.gethostname()}_{os.getlogin()}_{uuid.getnode()}"
    return hashlib.sha256(fallback.encode()).hexdigest().upper()


def get_display_mid(mid: str) -> str:
    """Short display version of MID."""
    return f"{mid[:8]}...{mid[-4:]}"


# ============================================================
# ENCRYPTION (shared with admin — XOR + HMAC-SHA256)
# ============================================================

# Obfuscated secrets (XOR 0x5A encoded, not plaintext in source)
_MID_KEY_SALT = bytes(a ^ 0x5A for a in bytes.fromhex('0c1f150517131e05111f03051f141908030a0e05686a686c052c6b'))
_SELLER_SALT = bytes(a ^ 0x5A for a in bytes.fromhex('0c1f1505091f16161f08051b0f0e1205686a686c052c6b'))
_SESSION_SECRET = bytes(a ^ 0x5A for a in bytes.fromhex('0c1f1505091f16161f0805091f090913151405686a686c052c6b'))


def encrypt_with_mid(plaintext: str, machine_id: str, salt: bytes = _MID_KEY_SALT) -> str:
    """Encrypt string using HMAC-SHA256(salt, MID) as XOR key. Returns base64."""
    derived = _hmac.new(salt, machine_id.encode(), hashlib.sha256).digest()
    data = plaintext.encode('utf-8')
    encrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(data))
    return base64.b64encode(encrypted).decode('ascii')


def decrypt_with_mid(encrypted_b64: str, machine_id: str, salt: bytes = _MID_KEY_SALT) -> str:
    """Decrypt base64 string using HMAC-SHA256(salt, MID) as XOR key."""
    try:
        derived = _hmac.new(salt, machine_id.encode(), hashlib.sha256).digest()
        encrypted = base64.b64decode(encrypted_b64)
        decrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(encrypted))
        return decrypted.decode('utf-8')
    except Exception:
        return ''


# ============================================================
# SESSION TOKEN
# ============================================================

_SESSION_DURATION = 1800  # 30 minutes


def generate_session_token(mid: str, level: int) -> str:
    """Generate session token bound to MID + level. Valid 30 min."""
    import time
    ts = str(int(time.time()))
    msg = f"{mid}|{level}|{ts}".encode()
    sig = _hmac.new(_SESSION_SECRET, msg, hashlib.sha256).hexdigest()[:32]
    return f"{ts}:{level}:{sig}"


def verify_session_token(mid: str, token: str) -> tuple:
    """Verify session token. Returns (valid, level) or (False, 0)."""
    try:
        import time
        parts = token.split(':')
        if len(parts) != 3:
            return False, 0
        ts, level_str, sig = parts
        level = int(level_str)
        
        # Check expiry
        age = int(time.time()) - int(ts)
        if age < 0 or age > _SESSION_DURATION:
            return False, 0
        
        # Verify HMAC
        msg = f"{mid}|{level}|{ts}".encode()
        expected = _hmac.new(_SESSION_SECRET, msg, hashlib.sha256).hexdigest()[:32]
        if not _hmac.compare_digest(sig, expected):
            return False, 0
        
        return True, level
    except Exception:
        return False, 0


# ============================================================
# SELLER PERMISSIONS
# ============================================================

class SellerPermissions:
    """Permission enforcement for seller levels."""
    
    LEVEL_1_ACTIONS = frozenset({
        'view_requests', 'approve_trial', 'view_summary',
        'change_password', 'view_keys_readonly'
    })
    LEVEL_2_ACTIONS = LEVEL_1_ACTIONS | frozenset({
        'approve_paid', 'confirm_payment', 'edit_client_name',
        'revoke_key', 'view_keys', 'manage_server_config'
    })
    
    def __init__(self, level: int):
        self.level = level
    
    def can(self, action: str) -> bool:
        allowed = self.LEVEL_2_ACTIONS if self.level >= 2 else self.LEVEL_1_ACTIONS
        return action in allowed
    
    @property
    def level_name(self) -> str:
        return "Manager" if self.level >= 2 else "Basic"


# ============================================================
# SELLER FIREBASE MANAGER
# ============================================================

class SellerFirebaseManager:
    """Firebase operations for seller app (restricted access)."""
    
    SELLERS_COLLECTION = "_sellers"
    LIC_COLLECTION = "_lic"
    TRIALS_COLLECTION = "_trials"
    REQUEST_COLLECTION = "_upgrade_requests"
    AUDIT_COLLECTION = "_seller_audit"
    
    TIER_DEFAULTS_FALLBACK = {
        "TRIAL":   {"days": 3, "ac": 1,  "fm": 2,  "wk": 8,  "op": 4, "dg": 100},
        "PREMIUM": {"days": 0, "ac": -1, "fm": -1, "wk": 20, "op": 4, "dg": -1},
        "TESTER":  {"days": 0, "ac": -1, "fm": -1, "wk": 20, "op": 4, "dg": -1},
    }
    
    PRICING_FALLBACK = {
        "first_buy": {"1M": 200000, "3M": 400000, "6M": 600000, "1Y": 1000000, "LT": 3000000},
        "normal":    {"1M": 300000, "3M": 500000, "6M": 800000, "1Y": 1200000, "LT": 3000000},
    }
    
    def __init__(self):
        self.db = None
        self.backup_db = None
        self.connected = False
        self.which_db = None
        self._seller_data = None  # Cached seller profile
        self._session_token = None
        self._permissions = None
        self._seller_mid = None   # Authenticated seller MID
        self._last_status_check = None  # Last time status was re-verified
    
    def connect(self) -> bool:
        """Connect to Firebase (same dual-Firebase as admin)."""
        if not FIREBASE_AVAILABLE:
            return False
        try:
            from firebase_config import get_failover_db, get_backup_db
            self.db, self.which_db = get_failover_db()
            if self.db:
                self.connected = True
                self.backup_db = get_backup_db() if self.which_db == "primary" else None
                return True
        except ImportError:
            pass
        except Exception:
            pass
        return False
    
    # ── Authentication ──────────────────────────────────
    
    def authenticate(self, machine_id: str, password: str) -> dict:
        """
        Authenticate seller by MID + password.
        
        Returns:
            {"success": True, "level": 1|2, "name": "...", "token": "..."}
            {"success": False, "error": "reason", "locked_until": "..."}
        """
        if not self.connected:
            return {"success": False, "error": "Không thể kết nối Firebase"}
        
        try:
            doc = self.db.collection(self.SELLERS_COLLECTION).document(machine_id).get()
            if not doc.exists:
                return {"success": False, "error": "Máy này chưa được đăng ký làm Seller"}
            
            data = doc.to_dict()
            
            # Check status
            status = data.get('status', 'active')
            if status == 'suspended':
                return {"success": False, "error": "Tài khoản đã bị tạm ngưng. Liên hệ Admin."}
            if status == 'revoked':
                return {"success": False, "error": "Tài khoản đã bị thu hồi."}
            
            # Brute-force check
            failed = data.get('failed_attempts', 0)
            locked_until = data.get('locked_until', '')
            if locked_until:
                try:
                    lock_dt = datetime.fromisoformat(locked_until)
                    if datetime.now() < lock_dt:
                        remaining = int((lock_dt - datetime.now()).total_seconds())
                        return {
                            "success": False,
                            "error": f"Tài khoản bị khóa. Thử lại sau {remaining}s.",
                            "locked_until": locked_until
                        }
                    else:
                        # Lock expired → reset
                        failed = 0
                except Exception:
                    pass
            
            # Decrypt password and verify
            epw = data.get('_epw', '')
            if not epw:
                return {"success": False, "error": "Seller chưa được cấp mật khẩu"}
            
            stored_password = decrypt_with_mid(epw, machine_id, _SELLER_SALT)
            # Use HMAC-safe comparison instead of plaintext ==
            pw_match = stored_password and _hmac.compare_digest(
                hashlib.sha256((stored_password + machine_id).encode()).digest(),
                hashlib.sha256((password + machine_id).encode()).digest()
            )
            if not pw_match:
                # Increment failed attempts
                failed += 1
                updates = {'failed_attempts': failed}
                
                if failed >= 10:
                    updates['status'] = 'suspended'
                    updates['locked_until'] = (datetime.now() + timedelta(hours=24)).isoformat()
                elif failed >= 5:
                    updates['locked_until'] = (datetime.now() + timedelta(minutes=15)).isoformat()
                elif failed >= 3:
                    updates['locked_until'] = (datetime.now() + timedelta(seconds=30)).isoformat()
                
                doc.reference.update(updates)
                
                remaining = 10 - failed
                return {"success": False, "error": f"Sai mật khẩu. Còn {remaining} lần thử."}
            
            # Success → reset failed attempts, update login info
            level = data.get('level', 1)
            name = data.get('name', '')
            
            # Decrypt name if encrypted
            esn = data.get('_esn', '')
            if esn:
                decrypted_name = decrypt_with_mid(esn, machine_id, _SELLER_SALT)
                if decrypted_name:
                    name = decrypted_name
            
            token = generate_session_token(machine_id, level)
            
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "unknown"
            
            doc.reference.update({
                'failed_attempts': 0,
                'locked_until': '',
                'last_login': datetime.now().isoformat(),
                'last_login_ip': ip,
                'login_count': (data.get('login_count', 0) or 0) + 1,
            })
            
            self._seller_data = data
            self._seller_data['name'] = name
            self._session_token = token
            self._permissions = SellerPermissions(level)
            self._seller_mid = machine_id
            self._last_status_check = datetime.now()
            
            return {
                "success": True,
                "level": level,
                "name": name,
                "token": token,
                "app_filter": data.get('app_filter', ['VEO']),
            }
        
        except Exception as e:
            return {"success": False, "error": "Lỗi xác thực. Thử lại sau."}
    
    # ── Session & Status Verification ───────────────────
    
    def _verify_session(self) -> dict:
        """
        Verify session token is still valid + re-check seller status from Firebase.
        Called before every write operation.
        Returns {"valid": True} or {"valid": False, "error": "..."}
        """
        # 1. Verify session token (HMAC + expiry)
        if not self._session_token or not self._seller_mid:
            return {"valid": False, "error": "Phiên đăng nhập không hợp lệ"}
        
        valid, _ = verify_session_token(self._seller_mid, self._session_token)
        if not valid:
            return {"valid": False, "error": "Phiên hết hạn. Đăng nhập lại."}
        
        # 2. Re-check seller status from Firebase (every 5 min)
        now = datetime.now()
        if (not self._last_status_check or 
            (now - self._last_status_check).total_seconds() > 300):
            try:
                doc = self.db.collection(self.SELLERS_COLLECTION).document(self._seller_mid).get()
                if doc.exists:
                    data = doc.to_dict()
                    status = data.get('status', 'active')
                    level = data.get('level', 1)
                    
                    if status != 'active':
                        self._permissions = None
                        return {"valid": False, "error": f"Tài khoản bị {status}. Liên hệ Admin."}
                    
                    # Update permissions if level changed
                    self._permissions = SellerPermissions(level)
                    self._last_status_check = now
                else:
                    return {"valid": False, "error": "Seller không tồn tại"}
            except Exception:
                pass  # Allow if can't check — token still valid
        
        return {"valid": True}
    
    # ── Password Management ────────────────────────────
    
    def change_password(self, machine_id: str, old_password: str, new_password: str) -> dict:
        """Seller changes own password."""
        if not self.connected:
            return {"success": False, "error": "Không kết nối"}
        
        try:
            doc = self.db.collection(self.SELLERS_COLLECTION).document(machine_id).get()
            if not doc.exists:
                return {"success": False, "error": "Seller không tồn tại"}
            
            data = doc.to_dict()
            stored = decrypt_with_mid(data.get('_epw', ''), machine_id, _SELLER_SALT)
            # HMAC-safe comparison
            pw_match = stored and _hmac.compare_digest(
                hashlib.sha256((stored + machine_id).encode()).digest(),
                hashlib.sha256((old_password + machine_id).encode()).digest()
            )
            if not pw_match:
                return {"success": False, "error": "Mật khẩu cũ không đúng"}
            
            if len(new_password) < 6:
                return {"success": False, "error": "Mật khẩu mới phải >= 6 ký tự"}
            
            new_epw = encrypt_with_mid(new_password, machine_id, _SELLER_SALT)
            updates = {
                '_epw': new_epw,
                'password_plain': '***',
                'last_pw_change': datetime.now().isoformat(),
            }
            doc.reference.update(updates)
            if self.backup_db:
                try:
                    self.backup_db.collection(self.SELLERS_COLLECTION).document(machine_id).update(updates)
                except Exception:
                    pass
            
            self._log_action(machine_id, 'change_password', machine_id)
            return {"success": True}
        except Exception:
            return {"success": False, "error": "Lỗi đổi mật khẩu. Thử lại sau."}
    
    # ── Config Loaders (match admin) ────────────────────────
    
    def load_tier_defaults(self) -> dict:
        """Load tier defaults from _config/tier_defaults (same as admin)."""
        if not self.connected:
            return dict(self.TIER_DEFAULTS_FALLBACK)
        try:
            doc = self.db.collection("_config").document("tier_defaults").get()
            if doc.exists:
                data = doc.to_dict()
                for tier, defaults in self.TIER_DEFAULTS_FALLBACK.items():
                    if tier not in data:
                        data[tier] = defaults
                return data
            return dict(self.TIER_DEFAULTS_FALLBACK)
        except Exception:
            return dict(self.TIER_DEFAULTS_FALLBACK)
    
    def load_pricing_config(self) -> dict:
        """Load pricing from _config/pricing (same as admin)."""
        if not self.connected:
            return dict(self.PRICING_FALLBACK)
        try:
            doc = self.db.collection("_config").document("pricing").get()
            if doc.exists:
                return doc.to_dict()
            return dict(self.PRICING_FALLBACK)
        except Exception:
            return dict(self.PRICING_FALLBACK)
    
    # ── Client Settings (Server Config) ─────────────────
    
    CLIENT_SETTINGS_DEFAULTS = {
        "trial_poll_interval_ms": 300000,
        "trial_poll_max": 6,
        "validate_cache_ttl_s": 3600,
        "server_weight": 50,
        "maintenance_mode": False,
        "min_client_version": "1.0.0",
        "ai_prompt_trial_enabled": False,
    }
    
    def get_client_settings(self) -> dict:
        """Read _config/client_settings from Firebase."""
        if not self.connected:
            return dict(self.CLIENT_SETTINGS_DEFAULTS)
        try:
            doc = self.db.collection("_config").document("client_settings").get()
            if doc.exists:
                data = doc.to_dict()
                # Fill missing keys with defaults
                for k, v in self.CLIENT_SETTINGS_DEFAULTS.items():
                    if k not in data:
                        data[k] = v
                return data
            return dict(self.CLIENT_SETTINGS_DEFAULTS)
        except Exception:
            return dict(self.CLIENT_SETTINGS_DEFAULTS)
    
    def update_client_settings(self, updates: dict, seller_mid: str) -> dict:
        """Update _config/client_settings in Firebase (Level 2 only).
        
        Writes to both primary and backup databases.
        Returns {"success": True} or {"success": False, "error": "..."}.
        """
        sv = self._verify_session()
        if not sv.get('valid'):
            return {"success": False, "error": sv.get('error', 'Session expired')}
        if not self._permissions or not self._permissions.can('manage_server_config'):
            return {"success": False, "error": "Không có quyền (cần Level 2)"}
        if not self.connected:
            return {"success": False, "error": "Không kết nối"}
        
        try:
            ref = self.db.collection("_config").document("client_settings")
            ref.set(updates, merge=True)
            
            if self.backup_db:
                try:
                    self.backup_db.collection("_config").document("client_settings").set(updates, merge=True)
                except Exception:
                    pass
            
            self._log_action(seller_mid, 'update_client_settings', 'client_settings',
                             str(updates))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": f"Lỗi cập nhật: {e}"}
    
    # ── Request Operations ─────────────────────────────
    
    def get_pending_requests(self, app_filter: list = None) -> list:
        """Get pending upgrade requests from both primary + backup (merged)."""
        if not self.connected:
            return []
        requests = {}
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            # Query primary
            query = self.db.collection(self.REQUEST_COLLECTION).where(filter=FieldFilter('status', '==', 'pending'))
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                data['_source'] = 'primary'
                if app_filter and data.get('app', 'VEO') not in app_filter:
                    continue
                requests[doc.id] = data
            
            # Also query backup (request might only exist there)
            if self.backup_db:
                try:
                    bq = self.backup_db.collection(self.REQUEST_COLLECTION).where(filter=FieldFilter('status', '==', 'pending'))
                    for doc in bq.stream():
                        if doc.id not in requests:  # Deduplicate
                            data = doc.to_dict()
                            data['id'] = doc.id
                            data['_source'] = 'backup'
                            if app_filter and data.get('app', 'VEO') not in app_filter:
                                continue
                            requests[doc.id] = data
                except Exception:
                    pass
        except Exception:
            pass
        return list(requests.values())
    
    def _claim_request(self, request_id: str, claimed_by: str) -> tuple:
        """
        Atomically claim a request using Firestore transaction.
        Allows re-claim by same person or after 5-min stale timeout.
        Returns (data: dict, error: str|None).
        """
        doc_ref = self.db.collection(self.REQUEST_COLLECTION).document(request_id)
        
        @firestore.transactional
        def _do_claim(transaction):
            doc = doc_ref.get(transaction=transaction)
            if not doc.exists:
                return None, "Request not found (đã xử lý xong)"
            data = doc.to_dict()
            status = data.get('status', '')
            
            if status == 'pending':
                transaction.update(doc_ref, {
                    'status': 'processing',
                    '_claimed_by': claimed_by,
                    '_claimed_at': datetime.now().isoformat(),
                })
                data['id'] = doc.id
                return data, None
            
            if status == 'processing':
                prev_claimer = data.get('_claimed_by', '')
                claimed_at = data.get('_claimed_at', '')
                
                # Allow re-claim by same person
                if prev_claimer == claimed_by:
                    data['id'] = doc.id
                    return data, None
                
                # Allow re-claim after 5-min stale timeout
                try:
                    ct = datetime.fromisoformat(claimed_at) if claimed_at else None
                    if ct and (datetime.now() - ct).total_seconds() > 300:
                        transaction.update(doc_ref, {
                            'status': 'processing',
                            '_claimed_by': claimed_by,
                            '_claimed_at': datetime.now().isoformat(),
                        })
                        data['id'] = doc.id
                        return data, None
                except Exception:
                    pass
                
                return None, f"Request đang được xử lý bởi {prev_claimer}"
            
            return None, f"Request status: {status} (không phải pending)"
        
        try:
            transaction = self.db.transaction()
            return _do_claim(transaction)
        except Exception:
            return None, "Lỗi claim request"
    
    def approve_trial(self, request_id: str, seller_mid: str) -> dict:
        """Approve a trial request (Level 1+2) — with transaction lock."""
        # Session + permission verify
        sv = self._verify_session()
        if not sv.get('valid'):
            return {"success": False, "error": sv.get('error', 'Session expired')}
        if not self._permissions or not self._permissions.can('approve_trial'):
            return {"success": False, "error": "Không có quyền"}
        
        if not self.connected:
            return {"success": False, "error": "Không kết nối"}
        
        try:
            # ── Atomic claim (prevent duplicate processing) ──
            data, claim_err = self._claim_request(request_id, f"seller:{seller_mid[:16]}")
            if claim_err:
                return {"success": False, "error": claim_err}
            
            if data.get('tier', '') != 'TRIAL':
                return {"success": False, "error": "Chỉ được duyệt TRIAL request"}
            
            # Self-approve prevention
            if data.get('machine_id', '') == seller_mid:
                return {"success": False, "error": "Không thể tự approve request của mình"}
            
            machine_id = data.get('machine_id', '')
            client_name = data.get('client_name', '')
            client_time_str = data.get('client_submitted_at', '')
            
            try:
                base_time = datetime.fromisoformat(client_time_str) if client_time_str else datetime.now()
            except Exception:
                base_time = datetime.now()
            
            # ── FIX: Read trial days + limits from server templates ──
            try:
                templates = self.load_tier_defaults()
                trial_tmpl = templates.get("TRIAL", {})
            except Exception:
                trial_tmpl = self.TIER_DEFAULTS_FALLBACK.get("TRIAL", {})
            
            trial_days = trial_tmpl.get("days", 3)
            trial_lim = {
                "ac": trial_tmpl.get("ac", 1),
                "fm": trial_tmpl.get("fm", 2),
                "wk": trial_tmpl.get("wk", 8),
                "op": trial_tmpl.get("op", 4),
                "dg": trial_tmpl.get("dg", 100),
            }
            
            import json as _json
            trial_data = {
                "machine_id": machine_id,
                "_ecn": encrypt_with_mid(client_name, machine_id),
                "client_name": client_name,
                "started_at": base_time.isoformat(),
                "expires_at": (base_time + timedelta(days=trial_days)).isoformat(),
                "status": "active",
                "days": trial_days,
                "approved_by": f"seller:{seller_mid[:16]}",
                "client_submitted_at": client_time_str or datetime.now().isoformat(),
                "_app": data.get('app', 'VEO'),
                "email": data.get('email', ''),
                "_elim": encrypt_with_mid(_json.dumps(trial_lim), machine_id),
                "_lim": None,
            }
            
            self.db.collection("_trials").document(machine_id).set(trial_data)
            if self.backup_db:
                try:
                    self.backup_db.collection("_trials").document(machine_id).set(trial_data)
                except Exception:
                    pass
            
            doc_ref = self.db.collection(self.REQUEST_COLLECTION).document(request_id)
            doc_ref.delete()
            if self.backup_db:
                try:
                    self.backup_db.collection(self.REQUEST_COLLECTION).document(request_id).delete()
                except Exception:
                    pass
            
            self._log_action(seller_mid, 'approve_trial', machine_id, f"Trial {trial_days}d for {client_name}")
            
            return {"success": True, "message": f"✅ Trial {trial_days} ngày cho {client_name}"}
        except Exception:
            return {"success": False, "error": "Lỗi approve trial. Thử lại sau."}
    
    def approve_paid(self, request_id: str, seller_mid: str, tier_code: str, days: int) -> dict:
        """
        Approve paid request — matches admin flow:
        1. Extend-or-Create (stack time if key exists)
        2. Write _customers purchase history
        3. Mark _trials as upgraded
        4. Lifetime rolling expiry
        """
        # Session + permission verify
        sv = self._verify_session()
        if not sv.get('valid'):
            return {"success": False, "error": sv.get('error', 'Session expired')}
        if not self._permissions or not self._permissions.can('approve_paid'):
            return {"success": False, "error": "Không có quyền (cần Level 2)"}
        
        if not self.connected:
            return {"success": False, "error": "Không kết nối"}
        
        try:
            # ── Atomic claim (prevent duplicate processing) ──
            data, claim_err = self._claim_request(request_id, f"seller:{seller_mid[:16]}")
            if claim_err:
                return {"success": False, "error": claim_err}
            
            machine_id = data.get('machine_id', '')
            client_name = data.get('client_name', '')
            app_id = data.get('app', 'VEO')
            
            # FIX: Payment check — must be paid before approve (match admin)
            if not data.get('paid', False):
                return {"success": False, "error": "Yêu cầu chưa được xác nhận thanh toán. Vui lòng đánh dấu 'Đã thanh toán' trước."}
            
            # Self-approve prevention
            if machine_id == seller_mid:
                return {"success": False, "error": "Không thể tự approve request của mình"}
            
            from license_keygen import LicenseKeyGenerator, LicenseTier
            tier_map = {
                '1M': LicenseTier.MONTH_1, '3M': LicenseTier.MONTH_3,
                '6M': LicenseTier.MONTH_6, '1Y': LicenseTier.YEAR_1,
                'LT': LicenseTier.LIFETIME,
            }
            tier = tier_map.get(tier_code)
            if not tier:
                return {"success": False, "error": f"Tier không hợp lệ"}
            
            # Client submit time for expiry calc
            client_time_str = data.get('client_submitted_at', '')
            try:
                client_base = datetime.fromisoformat(client_time_str) if client_time_str else datetime.now()
            except Exception:
                client_base = datetime.now()
            
            # ══ FIX 1: Extend-or-Create ══
            existing_key_id = None
            existing_data = None
            try:
                from google.cloud.firestore_v1.base_query import FieldFilter
                results = list(self.db.collection(self.LIC_COLLECTION)
                    .where(filter=FieldFilter('_mid', '==', machine_id))
                    .where(filter=FieldFilter('_st', '==', 'a'))
                    .stream())
                if results:
                    existing_key_id = results[0].id
                    existing_data = results[0].to_dict()
            except Exception:
                pass
            
            if existing_key_id and existing_data:
                # ── Block extend if MID is a Tester ──
                if existing_data.get('_role', 1) == 2:
                    return {"success": False, "error": "MID này là Tester (role=2). Không thể extend bằng gói trả phí."}
                
                # ── EXTEND: Cộng dồn thời gian ──
                old_exp = existing_data.get('_exp')
                now = datetime.now()
                
                if hasattr(old_exp, 'timestamp'):
                    old_exp_naive = datetime.fromtimestamp(old_exp.timestamp())
                    base = old_exp_naive if old_exp_naive > now else now
                elif isinstance(old_exp, datetime):
                    if old_exp.tzinfo is not None:
                        old_exp = old_exp.replace(tzinfo=None)
                    base = old_exp if old_exp > now else now
                else:
                    base = now
                
                new_exp = base + timedelta(days=days)
                old_dur = existing_data.get('_dur', 0) or 0
                
                update_data = {
                    '_exp': new_exp,
                    '_dur': old_dur + days,
                    '_t': tier_code,
                    '_nt': f"Extended +{days}d by seller:{seller_mid[:16]} (was {old_dur}d)",
                }
                self.db.collection(self.LIC_COLLECTION).document(existing_key_id).update(update_data)
                if self.backup_db:
                    try:
                        self.backup_db.collection(self.LIC_COLLECTION).document(existing_key_id).update(update_data)
                    except Exception:
                        pass
                
                key = existing_key_id
                result_msg = f"⏱ Extended +{days} ngày (tổng {old_dur + days}d)\nHết hạn: {new_exp.strftime('%Y-%m-%d')}"
            else:
                # ── CREATE: Tạo key mới ──
                key, metadata = LicenseKeyGenerator.generate(machine_id, tier, days)
                
                lic_data = {
                    "_t": metadata['tier'],
                    "_st": "a",
                    "_cr": firestore.SERVER_TIMESTAMP,
                    "_exp": client_base + timedelta(days=days),
                    "_mid": machine_id,
                    "_cn": client_name,
                    "_role": 1,
                    "_app": app_id,
                    "_dur": days,
                    "_approved_by": f"seller:{seller_mid[:16]}",
                    "_client_submitted": client_time_str or '',
                }
                
                # ══ FIX 4: Lifetime rolling expiry ══
                if tier == LicenseTier.LIFETIME:
                    lic_data['_exp'] = client_base + timedelta(days=90)
                    lic_data['_lt_rolling'] = True
                
                self.db.collection(self.LIC_COLLECTION).document(key).set(lic_data)
                if self.backup_db:
                    try:
                        self.backup_db.collection(self.LIC_COLLECTION).document(key).set(lic_data)
                    except Exception:
                        pass
                
                result_msg = f"✅ Key {tier_code} tạo cho {client_name}"
            
            # ══ FIX 3: Write _customers purchase history ══
            # ══ FIX: Read pricing from server config ══
            try:
                pricing = self.load_pricing_config()
                FIRST_BUY = pricing.get('first_buy', self.PRICING_FALLBACK['first_buy'])
                NORMAL = pricing.get('normal', self.PRICING_FALLBACK['normal'])
                
                cust_ref = self.db.collection("_customers").document(machine_id)
                cust_doc = cust_ref.get()
                prev_count = 0
                prev_paid = 0
                if cust_doc.exists:
                    cd = cust_doc.to_dict()
                    prev_count = cd.get('purchase_count', 0)
                    prev_paid = cd.get('total_paid', 0)
                
                amount = FIRST_BUY.get(tier_code, 0) if prev_count == 0 else NORMAL.get(tier_code, 0)
                
                purchase_entry = {
                    "tier": tier_code, "amount": amount,
                    "at": datetime.now().isoformat(),
                    "key": key[:8] + "****", "days": days,
                }
                cust_update = {
                    "machine_id": machine_id,
                    "_ecn": encrypt_with_mid(client_name, machine_id),
                    "client_name": client_name,
                    "purchase_count": prev_count + 1,
                    "_etp": encrypt_with_mid(str(prev_paid + amount), machine_id),
                    "total_paid": 0,  # Masked — real value in _etp
                    "last_purchase_at": datetime.now().isoformat(),
                }
                if prev_count == 0:
                    cust_update["first_purchase_at"] = datetime.now().isoformat()
                
                cust_ref.set(cust_update, merge=True)
                if self.backup_db:
                    try:
                        self.backup_db.collection("_customers").document(machine_id).set(cust_update, merge=True)
                    except Exception:
                        pass
            except Exception:
                pass
            
            # ══ FIX 2: Mark trial as upgraded ══
            try:
                trial_ref = self.db.collection(self.TRIALS_COLLECTION).document(machine_id)
                trial_doc = trial_ref.get()
                if trial_doc.exists:
                    trial_update = {"status": "upgraded", "upgraded_to": key, "upgraded_at": datetime.now().isoformat()}
                    trial_ref.update(trial_update)
                    if self.backup_db:
                        try:
                            self.backup_db.collection(self.TRIALS_COLLECTION).document(machine_id).update(trial_update)
                        except Exception:
                            pass
            except Exception:
                pass
            
            # Write _mid_to_key lookup
            mid_key_data = {
                "_ek": encrypt_with_mid(key, machine_id),
                "key": "****",
                "tier": tier_code,
                "status": "a",
                "role": 1,
                "expires": (datetime.now() + timedelta(days=days)).isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            self.db.collection("_mid_to_key").document(machine_id).set(mid_key_data)
            if self.backup_db:
                try:
                    self.backup_db.collection("_mid_to_key").document(machine_id).set(mid_key_data)
                except Exception:
                    pass
            
            # Delete request doc
            doc_ref.delete()
            if self.backup_db:
                try:
                    self.backup_db.collection(self.REQUEST_COLLECTION).document(request_id).delete()
                except Exception:
                    pass
            
            self._log_action(seller_mid, 'approve_paid', machine_id,
                           f"Key: {key[:8]}**** tier={tier_code} days={days}")
            
            return {"success": True, "key": key, "message": result_msg}
        except Exception:
            return {"success": False, "error": "Lỗi tạo key. Thử lại sau."}
    
    def revoke_key(self, key_id: str, seller_mid: str) -> dict:
        """Revoke a license key (Level 2 only)."""
        # Session + permission verify
        sv = self._verify_session()
        if not sv.get('valid'):
            return {"success": False, "error": sv.get('error', 'Session expired')}
        if not self._permissions or not self._permissions.can('revoke_key'):
            return {"success": False, "error": "Không có quyền (cần Level 2)"}
        
        if not self.connected:
            return {"success": False, "error": "Không kết nối"}
        
        try:
            doc_ref = self.db.collection(self.LIC_COLLECTION).document(key_id)
            doc = doc_ref.get()
            if not doc.exists:
                return {"success": False, "error": "Key không tồn tại"}
            
            data = doc.to_dict()
            if data.get('_st') == 'r':
                return {"success": False, "error": "Key đã bị revoke trước đó"}
            
            updates = {
                '_st': 'r',
                '_revoked_at': datetime.now().isoformat(),
                '_revoked_by': f"seller:{seller_mid[:16]}",
            }
            doc_ref.update(updates)
            if self.backup_db:
                try:
                    self.backup_db.collection(self.LIC_COLLECTION).document(key_id).update(updates)
                except Exception:
                    pass
            
            self._log_action(seller_mid, 'revoke_key', key_id[:16], f"Revoked key {key_id[:8]}****")
            return {"success": True, "message": f"✅ Key {key_id[:8]}**** đã bị thu hồi"}
        except Exception:
            return {"success": False, "error": "Lỗi revoke key. Thử lại sau."}
    
    # ── Read Operations ────────────────────────────────
    
    def get_active_keys(self, app_filter: list = None) -> list:
        """Get license keys (server-side filtered by app). Auto-expires stale active keys."""
        if not self.connected:
            return []
        keys = []
        now = datetime.now()
        try:
            query = self.db.collection(self.LIC_COLLECTION)
            # Server-side filter: only load matching apps
            if app_filter and len(app_filter) == 1:
                from google.cloud.firestore_v1.base_query import FieldFilter
                query = query.where(filter=FieldFilter('_app', '==', app_filter[0]))
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                # Client-side fallback for multi-app filter
                if app_filter and len(app_filter) > 1:
                    if data.get('_app', 'VEO') not in app_filter:
                        continue
                # Auto-expire: if _st='a' but _exp < now → update Firestore
                if data.get('_st') == 'a':
                    exp = data.get('_exp')
                    if exp:
                        try:
                            if hasattr(exp, 'timestamp'):
                                exp_dt = datetime.fromtimestamp(exp.timestamp())
                            elif isinstance(exp, datetime):
                                exp_dt = exp.replace(tzinfo=None) if exp.tzinfo else exp
                            else:
                                exp_dt = None
                            if exp_dt and now > exp_dt:
                                try:
                                    doc.reference.update({
                                        '_st': 'e',
                                        '_expired_at': firestore.SERVER_TIMESTAMP
                                    })
                                    if self.backup_db:
                                        try:
                                            self.backup_db.collection(self.LIC_COLLECTION).document(doc.id).update({
                                                '_st': 'e',
                                                '_expired_at': firestore.SERVER_TIMESTAMP
                                            })
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                data['_st'] = 'e'
                        except Exception:
                            pass
                keys.append(data)
        except Exception:
            pass
        return keys
    
    def get_all_trials(self, app_filter: list = None) -> list:
        """Get trial records. Auto-expires stale 'active' trials in Firestore."""
        if not self.connected:
            return []
        trials = []
        now = datetime.now()
        try:
            # No server-side _app filter — many trials don't have this field
            query = self.db.collection(self.TRIALS_COLLECTION)
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                # Decrypt name
                ecn = data.get('_ecn', '')
                mid = data.get('machine_id', '') or doc.id
                if ecn and mid:
                    data['client_name'] = decrypt_with_mid(ecn, mid)
                # Auto-expire: if status='active' but expires_at < now → update Firestore
                if data.get('status') == 'active':
                    expires_at = data.get('expires_at', '')
                    if expires_at:
                        try:
                            exp_dt = datetime.fromisoformat(expires_at)
                            if now > exp_dt:
                                # Update Firestore (best-effort)
                                try:
                                    doc.reference.update({
                                        'status': 'expired',
                                        '_expired_at': now.isoformat()
                                    })
                                    if self.backup_db:
                                        try:
                                            self.backup_db.collection(self.TRIALS_COLLECTION).document(doc.id).update({
                                                'status': 'expired',
                                                '_expired_at': now.isoformat()
                                            })
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                data['status'] = 'expired'
                        except (ValueError, TypeError):
                            pass
                # Client-side app filter (treat missing _app as match)
                if app_filter:
                    doc_app = data.get('_app', '')
                    if doc_app and doc_app not in app_filter:
                        continue
                trials.append(data)
        except Exception:
            pass
        return trials
    
    def get_summary(self, app_filter: list = None) -> dict:
        """Get overview statistics (optimized — server-side filter)."""
        if not self.connected:
            return {}
        try:
            # Use filtered queries instead of loading full collections
            from google.cloud.firestore_v1.base_query import FieldFilter
            key_query = self.db.collection(self.LIC_COLLECTION)
            if app_filter and len(app_filter) == 1:
                key_query = key_query.where(filter=FieldFilter('_app', '==', app_filter[0]))
            keys = list(key_query.stream())
            
            req_query = self.db.collection(self.REQUEST_COLLECTION).where(filter=FieldFilter('status', '==', 'pending'))
            pending = len(list(req_query.stream()))
            
            trial_query = self.db.collection(self.TRIALS_COLLECTION)
            trials = list(trial_query.stream())
            
            active_keys = sum(1 for d in keys if d.to_dict().get('_st') == 'a')
            active_trials = 0
            now = datetime.now()
            for d in trials:
                td = d.to_dict()
                if td.get('status') != 'active':
                    continue
                # Check actual expiry, not just status field
                expires_at = td.get('expires_at', '')
                if expires_at:
                    try:
                        if now > datetime.fromisoformat(expires_at):
                            continue  # Actually expired
                    except (ValueError, TypeError):
                        pass
                active_trials += 1
            
            return {
                "total_keys": len(keys),
                "active_keys": active_keys,
                "total_trials": len(trials),
                "active_trials": active_trials,
                "pending_requests": pending,
            }
        except Exception:
            return {}
    
    # ── Audit Trail ────────────────────────────────────
    
    def _log_action(self, seller_mid: str, action: str, target: str, detail: str = ""):
        """Log seller action to _seller_audit collection."""
        if not self.connected:
            return
        try:
            ip = "unknown"
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                pass
            
            entry = {
                "seller_mid": seller_mid[:16],
                "action": action,
                "target": target[:16] if target else "",
                "detail": detail[:200],
                "timestamp": datetime.now().isoformat(),
                "ip": ip,
            }
            # Sign with HMAC
            msg = json.dumps(entry, sort_keys=True).encode()
            entry["_sig"] = _hmac.new(_SESSION_SECRET, msg, hashlib.sha256).hexdigest()[:32]
            
            self.db.collection(self.AUDIT_COLLECTION).add(entry)
            if self.backup_db:
                try:
                    self.backup_db.collection(self.AUDIT_COLLECTION).add(entry)
                except Exception:
                    pass
        except Exception:
            pass
