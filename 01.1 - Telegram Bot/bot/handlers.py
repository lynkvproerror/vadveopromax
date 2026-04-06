"""
Telegram Bot Handlers
======================
Processes commands and callback queries from Telegram.
Uses raw Telegram Bot API via requests (no python-telegram-bot dependency).
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

import hmac as _hmac
import hashlib
import base64

from . import security, formatters
from .firebase_ops import FirebaseOps
from .keygen import generate_key, LicenseTier, UserRole

log = logging.getLogger("veo.bot.handlers")

# ─── Name Decryption (matches admin app) ───────────────────────
_MID_KEY_SALT = b'VEO_MID_KEY_ENCRYPT_2026_v1'


def _decrypt_name(encrypted_b64: str, machine_id: str) -> str:
    """Decrypt _ecn field → real client name (XOR + HMAC-SHA256)."""
    try:
        derived = _hmac.new(_MID_KEY_SALT, machine_id.encode(), hashlib.sha256).digest()
        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(encrypted_bytes))
        return decrypted.decode('utf-8')
    except Exception:
        return ''


def _encrypt_name(plaintext: str, machine_id: str) -> str:
    """Encrypt client name → _ecn field (XOR + HMAC-SHA256). Matches admin app."""
    if not plaintext:
        return ''
    try:
        derived = _hmac.new(_MID_KEY_SALT, machine_id.encode(), hashlib.sha256).digest()
        data = plaintext.encode('utf-8')
        encrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(data))
        return base64.b64encode(encrypted).decode('ascii')
    except Exception:
        return ''

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

_ops: Optional[FirebaseOps] = None


def _get_ops() -> FirebaseOps:
    global _ops
    if _ops is None:
        _ops = FirebaseOps()
    return _ops


# ─── Telegram API Helpers ────────────────────────────────────

def handle_app(chat_id: int, args: str) -> None:
    """Handle /app command — switch between VEO and GROK collections.
    Usage: /app veo, /app grok, /app (show current)
    """
    ops = _get_ops()
    if not args.strip():
        _send(chat_id, f"📱 *Active App:* `{ops.current_app}`\n\nUsage: `/app veo` hoặc `/app grok`")
        return
    
    app_name = args.strip().upper()
    try:
        ops.set_app(app_name)
        emoji = {"VEO": "🔵", "GROK": "🟡"}.get(app_name, "⚪")
        _send(chat_id, f"{emoji} Đã chuyển sang *{app_name}*\n\nTất cả commands sẽ dùng collections của {app_name}.")
    except ValueError as e:
        _send(chat_id, f"❌ {e}\n\nUsage: `/app veo` hoặc `/app grok`")

def _send(chat_id: int, text: str, parse_mode: str = "Markdown",
          reply_markup: dict = None, auto_delete: int = 0) -> dict:
    """Send a Telegram message."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        resp = requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)
        result = resp.json()

        # Auto-delete sensitive messages
        if auto_delete > 0 and result.get("ok"):
            msg_id = result["result"]["message_id"]
            # Note: auto-delete requires a scheduled mechanism.
            # In serverless, we can only log intent here.
            # Full key is visible for limited time in Telegram.
            log.info(f"[TG] Sent auto-delete msg {msg_id} ({auto_delete}s)")

        return result
    except Exception as e:
        log.error(f"[TG] Send error: {e}")
        return {}


def _answer_callback(callback_query_id: str, text: str = "") -> None:
    """Answer a callback query (dismiss loading indicator)."""
    try:
        requests.post(
            f"{TG_API}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id, "text": text},
            timeout=5,
        )
    except Exception:
        pass


def _edit_message(chat_id: int, message_id: int, text: str,
                  reply_markup: dict = None) -> None:
    """Edit an existing message."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(f"{TG_API}/editMessageText", json=payload, timeout=10)
    except Exception as e:
        log.error(f"[TG] Edit error: {e}")


def _delete_message(chat_id: int, message_id: int) -> None:
    """Delete a message."""
    try:
        requests.post(
            f"{TG_API}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=5,
        )
    except Exception:
        pass


# ─── Main Menu Keyboard ──────────────────────────────────────

def _main_menu() -> dict:
    """Build main menu with color-coded function buttons."""
    return {
        "inline_keyboard": [
            # ── Row 1: Monitoring (Blue) ──
            [
                {"text": "📊 Tổng quan", "callback_data": "menu:status"},
                {"text": "🏥 Health", "callback_data": "menu:health"},
            ],
            # ── Row 2: Lists & Requests (Green) ──
            [
                {"text": "📋 Danh sách", "callback_data": "menu:list"},
                {"text": "📬 Chờ duyệt", "callback_data": "menu:pending"},
            ],
            # ── Row 3: Actions (Orange) ──
            [
                {"text": "🔍 Tra cứu MID", "callback_data": "menu:lookup_prompt"},
                {"text": "🔑 Tạo key mới", "callback_data": "menu:create_prompt"},
            ],
            # ── Row 4: More actions ──
            [
                {"text": "⏱️ Gia hạn", "callback_data": "menu:extend_prompt"},
                {"text": "🔴 Thu hồi key", "callback_data": "menu:revoke_prompt"},
            ],
            # ── Row 5: Admin Settings ──
            [
                {"text": "⚙️ Cài đặt", "callback_data": "menu:config"},
                {"text": "💰 Bảng giá", "callback_data": "menu:pricing"},
                {"text": "🔄 Sync", "callback_data": "menu:sync"},
            ],
        ]
    }


def _seller_menu(level: int = 2) -> dict:
    """Build seller menu with restricted options."""
    buttons = [
        [
            {"text": "📊 Tổng quan", "callback_data": "menu:seller_status"},
            {"text": "📋 Danh sách", "callback_data": "menu:seller_list"},
        ],
        [
            {"text": "📬 Chờ duyệt", "callback_data": "menu:seller_pending"},
            {"text": "🔍 Tra cứu MID", "callback_data": "menu:lookup_prompt"},
        ],
        [
            {"text": "🔑 Tạo key mới", "callback_data": "seller:sell_prompt"},
            {"text": "📋 Key đã tạo", "callback_data": "seller:mykeys"},
        ],
    ]
    if level >= 2:
        buttons.append([
            {"text": "🔴 Thu hồi key", "callback_data": "menu:revoke_prompt"},
        ])
    return {"inline_keyboard": buttons}


# ─── Inline Keyboard Builders ────────────────────────────────

def _tier_buttons(mid: str, request_id: str = "") -> dict:
    """Build tier selection inline keyboard with package emojis."""
    prefix = f"approve:{mid}:{request_id}"
    return {
        "inline_keyboard": [
            [
                {"text": "📦 1 Tháng", "callback_data": f"{prefix}:1M:30"},
                {"text": "📦 3 Tháng", "callback_data": f"{prefix}:3M:90"},
            ],
            [
                {"text": "📦 6 Tháng", "callback_data": f"{prefix}:6M:180"},
                {"text": "📦 1 Năm", "callback_data": f"{prefix}:1Y:365"},
            ],
            [
                {"text": "💎 Vĩnh viễn", "callback_data": f"{prefix}:LT:36500"},
            ],
            [
                {"text": "❌ Hủy", "callback_data": f"cancel:{mid}"},
            ],
        ]
    }


def _request_buttons(mid: str, request_id: str, tier: str = "") -> dict:
    """Build action buttons for a new request notification.

    NOTE: Telegram limits callback_data to 64 bytes.
    MID and request_id are truncated to 16 chars (prefix matching used in handlers).
    """
    m = mid[:16]
    r = request_id[:16]
    if tier.upper() in ("TRIAL", "FREE", "TRIA", "12H", "1D"):
        # Trial: direct approve (no payment needed)
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ Duyệt Trial", "callback_data": f"approve:{m}:{r}:TRIA:3"},
                    {"text": "🔴 Từ chối", "callback_data": f"reject:{m}:{r}"},
                ],
                [
                    {"text": "🚫 Block", "callback_data": f"action:block:{m}"},
                    {"text": "🔍 Chi tiết", "callback_data": f"lookup:{m}"},
                ],
            ]
        }
    else:
        # Paid tier: payment confirmation → tier picker
        return {
            "inline_keyboard": [
                [
                    {"text": "💰 Chọn gói", "callback_data": f"pick_tier:{m}:{r}"},
                    {"text": "🔴 Từ chối", "callback_data": f"reject:{m}:{r}"},
                ],
                [
                    {"text": "🚫 Block", "callback_data": f"action:block:{m}"},
                    {"text": "🔍 Chi tiết", "callback_data": f"lookup:{m}"},
                ],
            ]
        }


def _license_action_buttons(mid: str, key: str) -> dict:
    """Build action buttons shown after license lookup."""
    # Truncate key for callback_data (max 64 bytes)
    key_short = key[:32] if len(key) > 32 else key
    return {
        "inline_keyboard": [
            [
                {"text": "⏱️ Gia hạn", "callback_data": f"action:extend:{mid}"},
                {"text": "🔴 Thu hồi", "callback_data": f"action:revoke:{key_short}"},
            ],
            [
                {"text": "📋 Menu", "callback_data": "menu:main"},
            ],
        ]
    }


# ─── Command Handlers ─────────────────────────────────────────

def handle_start(chat_id: int, role: str = "admin", seller_data: dict = None) -> None:
    if role == "seller":
        name = seller_data.get("name", "") if seller_data else ""
        level = seller_data.get("level", 1) if seller_data else 1
        _send(
            chat_id,
            (
                f"🏠 *Seller Menu* — {name} (L{level})\n\n"
                "Chọn chức năng bên dưới:\n"
            ),
            reply_markup=_seller_menu(level),
        )
    else:
        _send(
            chat_id,
            (
                "🤖 *VEO License Bot*\n\n"
                "Quản lý license từ Telegram 24/7.\n"
                "Chọn chức năng bên dưới hoặc gõ lệnh:\n\n"
                "📊 Monitoring  │  📬 Requests\n"
                "🔑 Key mgmt    │  🔧 Maintenance\n"
            ),
            reply_markup=_main_menu(),
        )


def handle_status(chat_id: int, role: str = "admin") -> None:
    ops = _get_ops()
    summary = ops.get_summary()

    if role == "seller":
        # Seller sees filtered status — no tester/seller counts
        text = (
            "📊 *Tổng quan License*\n\n"
            f"🟢 Active: *{summary.get('active', 0)}*\n"
            f"🔴 Revoked: *{summary.get('revoked', 0)}*\n"
            f"⚫ Expired: *{summary.get('expired', 0)}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📦 Tổng License: *{summary.get('total', 0)}*\n"
            f"💎 Premium: *{summary.get('premium', 0)}*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🆓 Trial: *{summary.get('trial_active', 0)}* active"
            + (f", {summary.get('trial_upgraded', 0)} upgraded" if summary.get('trial_upgraded') else "")
            + f" / {summary.get('trial_total', 0)} tổng"
        )
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "📋 Trial", "callback_data": "lcat:trial"},
                    {"text": "💎 Premium", "callback_data": "lcat:premium"},
                ],
                [{"text": "📋 Menu", "callback_data": "seller:menu"}],
            ]
        }
    else:
        text = formatters.fmt_status(summary)
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🟢 Active", "callback_data": "list:a"},
                    {"text": "⚫ Expired", "callback_data": "list:e"},
                    {"text": "🔴 Revoked", "callback_data": "list:r"},
                ],
                [
                    {"text": "📋 Tất cả", "callback_data": "list:all"},
                    {"text": "📋 Menu", "callback_data": "menu:main"},
                ],
            ]
        }
    _send(chat_id, text, reply_markup=buttons)


def handle_list(chat_id: int, filter_status: str = "all", role: str = "admin") -> None:
    """Show category picker or status-filtered list."""
    # If filter_status is a status code (a/e/r), show filtered list directly
    if filter_status in ("a", "e", "r"):
        _list_by_status(chat_id, filter_status)
        return

    if role == "seller":
        # Seller only sees Trial + Premium
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🆓 Trial", "callback_data": "lcat:trial"},
                    {"text": "💎 Premium", "callback_data": "lcat:premium"},
                ],
                [{"text": "📋 Menu", "callback_data": "seller:menu"}],
            ]
        }
    else:
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🆓 Trial", "callback_data": "lcat:trial"},
                    {"text": "💎 Premium", "callback_data": "lcat:premium"},
                ],
                [
                    {"text": "🧪 Tester", "callback_data": "lcat:tester"},
                    {"text": "🏪 Seller", "callback_data": "lcat:seller"},
                ],
                [
                    {"text": "📋 Tất cả", "callback_data": "lcat:all"},
                    {"text": "📋 Menu", "callback_data": "menu:main"},
                ],
            ]
        }
    _send(
        chat_id,
        "📋 *Danh sách License*\n\nChọn loại danh sách:",
        reply_markup=buttons,
    )


def _list_by_status(chat_id: int, status_filter: str) -> None:
    """Show license list filtered by status (a=active, e=expired, r=revoked)."""
    ops = _get_ops()
    all_keys = ops.list_docs(ops.COLLECTION, page_size=500)

    # Auto-detect expired by date (status may still be 'a' but _exp past)
    now = datetime.now()
    for k in all_keys:
        if k.get("_st") == "a":
            exp_str = k.get("_exp", "")
            if exp_str:
                try:
                    exp_dt = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
                    if exp_dt.tzinfo:
                        exp_dt = exp_dt.replace(tzinfo=None)
                    if exp_dt < now:
                        k["_st"] = "e"  # Mark as expired in-memory
                except Exception:
                    pass

    items = [k for k in all_keys if k.get("_st") == status_filter]

    status_labels = {"a": ("🟢", "Active"), "e": ("⚫", "Expired"), "r": ("🔴", "Revoked")}
    emoji, label = status_labels.get(status_filter, ("❓", "?"))

    if not items:
        _send(chat_id, f"{emoji} *{label}* — 0 items\n\nKhông có dữ liệu.")
        return

    # Decrypt names
    for item in items:
        ecn = item.get("_ecn", "")
        mid = item.get("_mid", "")
        if ecn and mid and (not item.get("_cn") or item.get("_cn") == "***"):
            item["_cn"] = _decrypt_name(ecn, mid)

    title = f"{emoji} *{label}* — {len(items)} items"
    lines = [title, ""]
    status_emoji = {"a": "🟢", "r": "🔴", "e": "⚫"}
    item_buttons = []

    for lic in items[:20]:
        mid = lic.get("_mid", "") or "?"
        name = lic.get("_cn", "") or ""
        tier = lic.get("_t", "") or "?"
        st = lic.get("_st", "?")
        se = status_emoji.get(st, "❓")
        exp = lic.get("_exp", "")

        display_name = name if name and name != "***" else formatters.mask_mid(mid)
        tier_text = formatters.tier_display(tier)
        line = f"{se} `{formatters.mask_mid(mid)}` | {tier_text}"
        if name and name != "***":
            line += f" | {name}"
        if exp and st == "a":
            line += f"\n    {formatters.fmt_remaining(str(exp))}"
        lines.append(line)

        btn_text = f"{se} {display_name} — {tier_text}"
        if len(btn_text) > 40:
            btn_text = btn_text[:37] + "..."
        mid_key = mid[:16]
        item_buttons.append([
            {"text": btn_text, "callback_data": f"litem:{mid_key}:all"}
        ])

    if len(items) > 20:
        lines.append(f"\n_... và {len(items) - 20} mục khác_")

    item_buttons.append([
        {"text": "🔙 Tổng quan", "callback_data": "menu:status"},
        {"text": "📋 Menu", "callback_data": "menu:main"},
    ])

    _send(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": item_buttons})


def _list_by_role(chat_id: int, role_filter: str) -> None:
    """Show license list filtered by role — matches admin app logic."""
    ops = _get_ops()

    if role_filter == "trial":
        # Trial = from _trials collection (like admin app)
        items = ops.list_docs(ops.col("trials"), page_size=100)
        # Decrypt _ecn → client_name
        for item in items:
            ecn = item.get("_ecn", "")
            mid = item.get("machine_id", "") or item.get("_doc_id", "")
            if ecn and mid:
                item["client_name"] = _decrypt_name(ecn, mid)
        emoji, label = "🆓", "Trial"
        is_trial = True
    elif role_filter == "seller":
        # Seller = from _sellers collection
        items = ops.list_docs("_sellers", page_size=100)
        emoji, label = "🏪", "Seller"
        is_trial = False
    else:
        # Premium and Tester = from _lic collection
        all_keys = ops.list_docs(ops.COLLECTION, page_size=500)
        is_trial = False
        if role_filter == "tester":
            items = [k for k in all_keys if k.get("_role") == 2]
            emoji, label = "🧪", "Tester"
        elif role_filter == "premium":
            items = [k for k in all_keys if k.get("_role", 1) != 2]
            emoji, label = "💎", "Premium"
        else:  # "all"
            items = all_keys
            emoji, label = "📋", "Tất cả"
        # Decrypt _ecn → _cn for _lic items
        for item in items:
            ecn = item.get("_ecn", "")
            mid = item.get("_mid", "")
            if ecn and mid and (not item.get("_cn") or item.get("_cn") == "***"):
                item["_cn"] = _decrypt_name(ecn, mid)

    if not items:
        _send(chat_id, f"{emoji} *{label}* — 0 items\n\nKhông có dữ liệu.")
        return

    # Count by status
    if is_trial:
        active = [k for k in items if k.get("status", "active") == "active"]
        inactive = [k for k in items if k.get("status", "active") != "active"]
    else:
        active = [k for k in items if k.get("_st") == "a"]
        inactive = [k for k in items if k.get("_st") != "a"]

    title = f"{emoji} *{label}* — {len(active)} active"
    if inactive:
        title += f", {len(inactive)} inactive"

    # Build list
    lines = [title, ""]
    status_emoji = {"a": "🟢", "r": "🔴", "e": "⚫", "active": "🟢", "expired": "⚫", "revoked": "🔴", "upgraded": "⬆️"}
    item_buttons = []
    display_list = active[:15] + inactive[:5]

    for lic in display_list:
        if is_trial:
            mid = lic.get("_doc_id", "") or lic.get("id", "") or "?"
            name = lic.get("client_name", "") or ""
            tier = "Trial"
            st = lic.get("status", "active")
            se = status_emoji.get(st, "❓")
            exp = lic.get("expires_at", "")
        elif role_filter == "seller":
            mid = lic.get("machine_id", "") or lic.get("_doc_id", "") or "?"
            name = lic.get("name", "") or ""
            tier = "Seller"
            st = "a" if lic.get("active", True) else "r"
            se = status_emoji.get(st, "❓")
            exp = ""
        else:
            mid = lic.get("_mid", "") or "?"
            name = lic.get("_cn", "") or ""
            tier = lic.get("_t", "") or "?"
            st = lic.get("_st", "?")
            se = status_emoji.get(st, "❓")
            exp = lic.get("_exp", "")

        display_name = name if name and name != "***" else formatters.mask_mid(mid)
        tier_text = formatters.tier_display(tier) if not is_trial and role_filter != "seller" else tier
        line = f"{se} `{formatters.mask_mid(mid)}` | {tier_text}"
        if name and name != "***":
            line += f" | {name}"
        if exp and st in ("a", "active"):
            line += f"\n    {formatters.fmt_remaining(str(exp))}"
        lines.append(line)

        # Button — use first 16 chars of MID as identifier
        btn_text = f"{se} {display_name} — {tier_text}"
        if len(btn_text) > 40:
            btn_text = btn_text[:37] + "..."
        mid_key = mid[:16]
        item_buttons.append([
            {"text": btn_text, "callback_data": f"litem:{mid_key}:{role_filter}"}
        ])

    if len(items) > 20:
        lines.append(f"\n_... và {len(items) - 20} mục khác_")

    item_buttons.append([
        {"text": "🔙 Chọn loại", "callback_data": "menu:list"},
        {"text": "📋 Menu", "callback_data": "menu:main"},
    ])

    _send(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": item_buttons})


def _find_lic_by_prefix(ops, mid_prefix: str):
    """Find a license by MID prefix (handles truncated callback_data)."""
    # Try exact match via _mid_to_key first
    lic = ops.get_license_by_mid(mid_prefix)
    if lic:
        return lic

    # Prefix search in _lic collection
    all_keys = ops.list_docs(ops.COLLECTION, page_size=500)
    for k in all_keys:
        mid = k.get("_mid", "") or ""
        if mid.startswith(mid_prefix):
            k["_doc_id"] = k.get("_doc_id", "")
            return k
    return None


def _resolve_full_mid(ops, prefix: str) -> str:
    """Resolve truncated MID prefix to full MID.

    Searches _lic, _trials, _sellers collections.
    Returns full MID or the prefix itself if not found.
    """
    # Try _lic via _mid_to_key first
    lic = _find_lic_by_prefix(ops, prefix)
    if lic:
        return lic.get("_mid", prefix) or prefix

    # Try _trials
    trials = ops.list_docs(ops.col("trials"), page_size=100)
    for t in trials:
        doc_id = t.get("_doc_id", "") or ""
        if doc_id.startswith(prefix):
            return doc_id

    # Try _sellers
    sellers = ops.list_docs("_sellers", page_size=100)
    for s in sellers:
        sid = s.get("machine_id", "") or s.get("_doc_id", "") or ""
        if sid.startswith(prefix):
            return sid

    return prefix


def _show_item_actions(chat_id: int, mid_prefix: str, role_filter: str, viewer_role: str = "admin") -> None:
    """Show license detail + role-specific action buttons."""
    ops = _get_ops()

    if role_filter == "trial":
        # Look up in _trials collection
        trials = ops.list_docs(ops.col("trials"), page_size=100)
        trial = None
        for t in trials:
            doc_id = t.get("_doc_id", "") or ""
            if doc_id.startswith(mid_prefix):
                trial = t
                break
        if not trial:
            _send(chat_id, f"❌ Không tìm thấy trial cho `{mid_prefix}...`")
            return
        mid = trial.get("_doc_id", "") or mid_prefix
        name = trial.get("client_name", "")
        email = trial.get("email", "")
        status = trial.get("status", "active")
        is_blocked = ops.is_machine_blocked(mid)
        text = (
            f"🆓 *Trial Info*\n\n"
            f"🖥️ MID: `{formatters.mask_mid(mid)}`\n"
            + (f"👤 Tên: {name}\n" if name else "")
            + (f"📧 Email: {email}\n" if email else "")
            + f"🔹 Status: {status}\n"
            + (f"🚫 *BLOCKED*\n" if is_blocked else "")
        )
        exp = trial.get("expires_at", "")
        if exp:
            text += f"⏰ Hết hạn: {formatters.fmt_date(str(exp))}\n"
            text += f"   {formatters.fmt_remaining(str(exp))}\n"

        m = mid[:16]
        buttons = [
            [
                {"text": "⬆️ Nâng cấp Premium", "callback_data": f"action:upgrade:{m}"},
            ],
        ]
        if viewer_role == "admin":
            if is_blocked:
                buttons.append([{"text": "🔓 Unlock Machine", "callback_data": f"action:unblock:{m}"}])
            else:
                buttons.append([{"text": "🚫 Block Machine", "callback_data": f"action:block:{m}"}])
        buttons.append([
            {"text": "🔙 Danh sách", "callback_data": f"lcat:{role_filter}"},
            {"text": "📋 Menu", "callback_data": "menu:main"},
        ])
        _send(chat_id, text, reply_markup={"inline_keyboard": buttons})
        return

    if role_filter == "seller":
        sellers = ops.list_docs("_sellers", page_size=100)
        seller = None
        for s in sellers:
            sid = s.get("machine_id", "") or s.get("_doc_id", "") or ""
            if sid.startswith(mid_prefix):
                seller = s
                break
        if not seller:
            _send(chat_id, f"❌ Không tìm thấy seller `{mid_prefix}...`")
            return
        full_mid = seller.get("machine_id", "") or seller.get("_doc_id", "") or mid_prefix
        name = seller.get("name", "")
        level = seller.get("level", 1)
        status = seller.get("status", "active")
        tg_id = seller.get("telegram_id", "")
        login_count = seller.get("login_count", 0)
        created_at = seller.get("created_at", "")
        is_blocked = ops.is_machine_blocked(full_mid)

        st_emoji = "🟢" if status == "active" else "🔴"
        text = (
            f"🏪 *Seller Info*\n\n"
            f"👤 Tên: *{name}*\n"
            f"🏷️ Level: *L{level}* {'(Manager)' if level >= 2 else '(Basic)'}\n"
            f"🔹 Status: {st_emoji} {status}\n"
            f"🖥️ MID: `{formatters.mask_mid(full_mid)}`\n"
            + (f"🚫 *BLOCKED*\n" if is_blocked else "")
            + (f"📱 Telegram: `{tg_id}`\n" if tg_id else "📱 Telegram: _chưa liên kết_\n")
            + (f"🔢 Đã login: {login_count} lần\n" if login_count else "")
            + (f"📅 Tạo: {formatters.fmt_date(created_at)}\n" if created_at else "")
        )

        m = full_mid[:16]
        buttons = [
            [{"text": "📋 Copy MID", "callback_data": f"action:sellermid:{m}"}],
        ]
        if not tg_id:
            buttons.append([{"text": "🔗 Liên kết Telegram", "callback_data": f"action:linkprompt:{m}"}])
        if viewer_role == "admin":
            if is_blocked:
                buttons.append([{"text": "🔓 Unlock Machine", "callback_data": f"action:unblock:{m}"}])
            else:
                buttons.append([{"text": "🚫 Block Machine", "callback_data": f"action:block:{m}"}])
        buttons.append([
            {"text": "🔙 Danh sách", "callback_data": f"lcat:{role_filter}"},
            {"text": "📋 Menu", "callback_data": "menu:main"},
        ])
        _send(chat_id, text, reply_markup={"inline_keyboard": buttons})
        return

    # Premium / Tester / All — lookup in _lic
    lic = _find_lic_by_prefix(ops, mid_prefix)

    if not lic:
        _send(chat_id, f"❌ Không tìm thấy license cho `{mid_prefix}...`")
        return

    key_id = lic.get("_doc_id", "")
    mid = lic.get("_mid", mid_prefix) or mid_prefix
    st = lic.get("_st", "?")
    role = lic.get("_role", 1)
    is_blocked = ops.is_machine_blocked(mid)

    # Decrypt name if needed
    ecn = lic.get("_ecn", "")
    if ecn and mid and (not lic.get("_cn") or lic.get("_cn") == "***"):
        lic["_cn"] = _decrypt_name(ecn, mid)

    text = formatters.fmt_license(lic, key_id)
    if is_blocked:
        text += "\n🚫 *BLOCKED*"

    # Build action buttons filtered by viewer role
    m = mid[:16]
    k = key_id[:24]
    buttons = []

    if viewer_role == "admin":
        # Admin sees all buttons
        if key_id:
            buttons.append([{"text": "📋 Copy Key", "callback_data": f"action:showkey:{m}"}])

        if st == "a":
            if role == 0:  # Trial in _lic
                buttons.append([
                    {"text": "⬆️ Nâng cấp", "callback_data": f"action:upgrade:{m}"},
                    {"text": "⏱️ Gia hạn", "callback_data": f"action:extend:{m}"},
                ])
                buttons.append([{"text": "🔴 Thu hồi", "callback_data": f"action:revoke:{k}"}])
            elif role == 2:  # Tester
                buttons.append([
                    {"text": "⏱️ Gia hạn", "callback_data": f"action:extend:{m}"},
                    {"text": "💎 → Premium", "callback_data": f"action:chrole:{m}:1"},
                ])
                buttons.append([{"text": "🔴 Thu hồi", "callback_data": f"action:revoke:{k}"}])
            else:  # Premium
                buttons.append([
                    {"text": "⏱️ Gia hạn", "callback_data": f"action:extend:{m}"},
                    {"text": "🔴 Thu hồi", "callback_data": f"action:revoke:{k}"},
                ])
                buttons.append([{"text": "🧪 → Tester", "callback_data": f"action:chrole:{m}:2"}])
        elif st == "r":
            buttons.append([{"text": "🔑 Tạo key mới", "callback_data": f"action:newkey:{m}"}])
        elif st == "e":
            buttons.append([
                {"text": "🔑 Tạo key mới", "callback_data": f"action:newkey:{m}"},
                {"text": "⏱️ Gia hạn", "callback_data": f"action:extend:{m}"},
            ])

        # Block/Unlock button for admin
        if is_blocked:
            buttons.append([{"text": "🔓 Unlock Machine", "callback_data": f"action:unblock:{m}"}])
        else:
            buttons.append([{"text": "🚫 Block Machine", "callback_data": f"action:block:{m}"}])
    else:
        # Seller sees limited buttons — Copy Key, Tạo key mới, Thu hồi (L2)
        if key_id:
            buttons.append([{"text": "📋 Copy Key", "callback_data": f"action:showkey:{m}"}])
        if st in ("a", "e") and k:
            buttons.append([{"text": "🔴 Thu hồi", "callback_data": f"action:revoke:{k}"}])
        if st in ("r", "e"):
            buttons.append([{"text": "🔑 Tạo key mới", "callback_data": f"action:newkey:{m}"}])

    buttons.append([
        {"text": "🔙 Danh sách", "callback_data": f"lcat:{role_filter}"},
        {"text": "📋 Menu", "callback_data": "menu:main"},
    ])

    _send(chat_id, text, reply_markup={"inline_keyboard": buttons})


def handle_health(chat_id: int) -> None:
    ops = _get_ops()
    health = ops.check_health()
    _send(chat_id, formatters.fmt_health(health))


def handle_pending(chat_id: int) -> None:
    ops = _get_ops()
    pending = ops.get_pending_requests()

    if not pending:
        _send(chat_id, "✅ Không có request nào đang chờ.")
        return

    # Decrypt client names for display
    for req in pending:
        ecn = req.get("_ecn", "")
        mid = req.get("machine_id") or req.get("_doc_id", "")
        if ecn and mid and not req.get("client_name"):
            req["client_name"] = _decrypt_name(ecn, mid)

    _send(chat_id, f"📬 *{len(pending)} request(s) đang chờ:*")

    for req in pending[:10]:  # Max 10 to avoid spam
        mid = req.get("machine_id") or req.get("_doc_id") or "?"
        request_id = req.get("_doc_id", mid)
        tier = req.get("tier", "")
        text = formatters.fmt_request(req)
        # NOTE: _request_buttons truncates MID/request_id to 16 chars
        # to stay within Telegram's 64-byte callback_data limit
        buttons = _request_buttons(mid, request_id, tier)
        _send(chat_id, text, reply_markup=buttons)


def handle_lookup(chat_id: int, args: str) -> None:
    mid = security.validate_mid(args)
    if not mid:
        _send(chat_id, "❌ MID không hợp lệ. Ví dụ: `/lookup 3946C15B`")
        return

    ops = _get_ops()

    # Try _mid_to_key first, then direct collection scan
    lic = ops.get_license_by_mid(mid)

    if not lic:
        _send(chat_id, f"❌ Không tìm thấy license cho MID `{formatters.mask_mid(mid)}`")
        return

    key_id = lic.get("_doc_id", "")
    buttons = _license_action_buttons(mid, key_id)
    _send(chat_id, formatters.fmt_license(lic, key_id), reply_markup=buttons)


def handle_approve_command(chat_id: int, args: str) -> None:
    """Handle /approve <MID> command — shows tier picker."""
    mid = security.validate_mid(args)
    if not mid:
        _send(chat_id, "❌ Cú pháp: `/approve <MID>`\nVí dụ: `/approve 3946C15B`")
        return

    buttons = _tier_buttons(mid)
    _send(
        chat_id,
        f"📋 *Duyệt license cho MID:* `{formatters.mask_mid(mid)}`\n\nChọn gói:",
        reply_markup=buttons,
    )


def handle_reject_command(chat_id: int, args: str) -> None:
    """Handle /reject <MID> [reason]."""
    parts = args.split(maxsplit=1)
    if not parts:
        _send(chat_id, "❌ Cú pháp: `/reject <MID> [lý do]`")
        return

    mid = security.validate_mid(parts[0])
    if not mid:
        _send(chat_id, "❌ MID không hợp lệ.")
        return

    reason = parts[1] if len(parts) > 1 else "Không đủ điều kiện"

    ops = _get_ops()
    # Find and reject the request
    pending = ops.get_pending_requests()
    found = None
    for req in pending:
        req_mid = req.get("machine_id") or req.get("_doc_id", "")
        if mid in req_mid:
            found = req
            break

    if not found:
        _send(chat_id, f"❌ Không tìm thấy request pending cho MID `{formatters.mask_mid(mid)}`")
        return

    request_id = found.get("_doc_id", "")
    ops.write_doc(ops.REQUEST_COLLECTION, request_id, {
        "status": "rejected",
        "rejected_by": "telegram_bot",
        "reject_reason": reason,
        "rejected_at": datetime.utcnow().isoformat() + "Z",
    })
    _send(chat_id, f"❌ Đã từ chối request cho `{formatters.mask_mid(mid)}`\nLý do: {reason}")


def handle_create(chat_id: int, args: str) -> None:
    """Handle /create <MID> <tier> <days>."""
    parts = args.split()
    if len(parts) < 3:
        _send(chat_id, (
            "❌ Cú pháp: `/create <MID> <tier> <days>`\n"
            "Tiers: `1M`, `3M`, `6M`, `1Y`, `LT`\n"
            "Ví dụ: `/create 3946C15B 3M 90`"
        ))
        return

    mid = security.validate_mid(parts[0])
    tier_code = security.validate_tier(parts[1])
    days = security.validate_days(parts[2])

    if not mid:
        _send(chat_id, "❌ MID không hợp lệ.")
        return
    if not tier_code:
        _send(chat_id, "❌ Tier không hợp lệ. Dùng: `1M`, `3M`, `6M`, `1Y`, `LT`")
        return
    if not days:
        _send(chat_id, "❌ Số ngày không hợp lệ (1-36500).")
        return

    _do_create_license(chat_id, mid, tier_code, days)


def handle_revoke(chat_id: int, args: str) -> None:
    """Handle /revoke <key>."""
    key = security.validate_key(args)
    if not key:
        _send(chat_id, "❌ Key không hợp lệ.")
        return

    ops = _get_ops()
    lic = ops.get_license(key)
    if not lic:
        _send(chat_id, f"❌ Key không tồn tại: `{formatters.mask_key(key)}`")
        return

    success = ops.revoke_license(key, reason="telegram_bot")
    mid = lic.get("_mid", "")
    if mid:
        ops.delete_mid_to_key(mid)

    if success:
        _send(chat_id, f"🔴 Đã thu hồi key `{formatters.mask_key(key)}`")
    else:
        _send(chat_id, f"❌ Lỗi khi thu hồi key.")


def handle_extend(chat_id: int, args: str) -> None:
    """Handle /extend <MID> <days>. Reactivates expired keys + recreates _mid_to_key."""
    parts = args.split()
    if len(parts) < 2:
        _send(chat_id, "❌ Cú pháp: `/extend <MID> <days>`\nVí dụ: `/extend 3946C15B 30`")
        return

    mid = security.validate_mid(parts[0])
    days = security.validate_days(parts[1])

    if not mid or not days:
        _send(chat_id, "❌ Input không hợp lệ.")
        return

    ops = _get_ops()
    lic = ops.get_license_by_mid(mid)

    # Fallback: scan _lic collection by _mid (if _mid_to_key was deleted)
    if not lic:
        all_keys = ops.list_docs(ops.COLLECTION, page_size=500)
        for k in all_keys:
            if k.get("_mid", "") == mid or k.get("_mid", "").startswith(mid):
                lic = k
                lic["_doc_id"] = k.get("_doc_id", "")
                break

    if not lic:
        _send(chat_id, f"❌ Không tìm thấy license cho MID `{formatters.mask_mid(mid)}`")
        return

    key_id = lic.get("_doc_id", "")
    exp_str = lic.get("_exp", "")
    old_dur = lic.get("_dur", 0) or 0
    old_status = lic.get("_st", "a")

    try:
        if isinstance(exp_str, str):
            old_exp = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
            if old_exp.tzinfo:
                old_exp = old_exp.replace(tzinfo=None)
        else:
            old_exp = datetime.now()
    except Exception:
        old_exp = datetime.now()

    now = datetime.now()
    base = old_exp if old_exp > now else now
    new_exp = base + timedelta(days=days)

    # 🔧 FIX: Always set _st="a" (reactivate expired/revoked keys)
    update_data = {
        "_exp": new_exp.isoformat() + "Z",
        "_dur": old_dur + days,
        "_st": "a",
        "_nt": f"Extended +{days}d by telegram_bot (was {old_dur}d, st:{old_status})",
    }
    ops.write_doc(ops.COLLECTION, key_id, update_data)

    # 🔧 FIX: Recreate _mid_to_key so client can find key again
    tier_code = lic.get("_t", "")
    role_code = lic.get("_role", 1)
    ops.write_mid_to_key(mid, key_id, tier_code, role_code, expires=new_exp.isoformat() + "Z")

    reactivated = " (🔄 reactivated!)" if old_status != "a" else ""
    _send(chat_id, (
        f"⏱ *Đã gia hạn!*{reactivated}\n\n"
        f"🖥️ MID: `{formatters.mask_mid(mid)}`\n"
        f"📅 +{days} ngày (tổng {old_dur + days}d)\n"
        f"⏰ Hết hạn mới: {formatters.fmt_date(new_exp.isoformat())}"
    ))


# ─── Core: Approve Trial (matches Admin GUI) ─────────────────

_TRIAL_DEFAULTS_FALLBACK = {
    "days": 3, "ac": 1, "fm": 2, "wk": 8, "op": 4, "dg": 100, "pb": 10,
}


def _do_approve_trial(
    chat_id: int, mid: str, request_id: str = "",
    client_name: str = "", approved_by: dict = None,
) -> None:
    """Approve TRIAL request — writes _trials/{MID}, no key created.

    Mirrors admin GUI approve_request() for TRIAL tier.
    Client polls `_trials/{MID}` on startup → auto-activates.
    """
    ops = _get_ops()
    now = datetime.now()

    # Read trial template from _config/tier_defaults
    trial_tmpl = _TRIAL_DEFAULTS_FALLBACK.copy()
    try:
        tier_defaults = ops.read_doc("_config", "tier_defaults")
        if tier_defaults and "TRIAL" in tier_defaults:
            td = tier_defaults["TRIAL"]
            if isinstance(td, str):
                td = json.loads(td)
            trial_tmpl.update(td)
    except Exception:
        pass

    trial_days = trial_tmpl.get("days", 3)
    trial_lim = {
        "ac": trial_tmpl.get("ac", 1),
        "fm": trial_tmpl.get("fm", 2),
        "wk": trial_tmpl.get("wk", 8),
        "op": trial_tmpl.get("op", 4),
        "dg": trial_tmpl.get("dg", 100),
        "pb": trial_tmpl.get("pb", 10),
    }

    # Read client_submitted_at from request data
    client_time_str = ""
    if request_id:
        req_data = ops.read_doc(ops.REQUEST_COLLECTION, request_id)
        if req_data:
            client_time_str = req_data.get("client_submitted_at", "")
            if not client_name:
                client_name = req_data.get("client_name", "")

    try:
        base_time = datetime.fromisoformat(client_time_str) if client_time_str else now
    except Exception:
        base_time = now

    trial_data = {
        "machine_id": mid,
        "_ecn": _encrypt_name(client_name, mid) if client_name else "",
        "client_name": client_name,
        "started_at": base_time.isoformat(),
        "expires_at": (base_time + timedelta(days=trial_days)).isoformat(),
        "status": "active",
        "days": trial_days,
        "approved_by": "telegram_bot",
        "client_submitted_at": client_time_str or now.isoformat(),
        "_elim": _encrypt_name(json.dumps(trial_lim), mid),
        "_lim": None,
    }

    success = ops.write_doc(ops.col("trials"), mid, trial_data)

    if success:
        # Delete request doc
        if request_id:
            ops.delete_request(request_id)

        # Audit
        audit = {
            "action": "approve_trial",
            "mid_masked": formatters.mask_mid(mid),
            "days": trial_days,
            "timestamp": now.isoformat() + "Z",
        }
        if approved_by:
            audit["approved_by"] = approved_by
        ops.write_doc("_bot_audit", f"trial_{int(time.time())}", audit)

        exp_display = (base_time + timedelta(days=trial_days)).strftime("%Y-%m-%d %H:%M")
        _send(chat_id, (
            f"✅ *Trial đã kích hoạt!*\n\n"
            f"🖥️ MID: `{formatters.mask_mid(mid)}`\n"
            + (f"👤 {client_name}\n" if client_name else "")
            + f"📦 Trial {trial_days} ngày\n"
            f"⏰ Hết hạn: {exp_display}\n\n"
            f"_Client chỉ cần tắt/mở lại app._"
        ))
    else:
        _send(chat_id, "❌ Lỗi ghi _trials. Kiểm tra /health")


# ─── Core: Create License (Paid tiers — extend-or-create) ────

def _do_create_license(
    chat_id: int, mid: str, tier_code: str, days: int,
    request_id: str = "", client_name: str = "",
    approved_by: dict = None,
) -> None:
    """Create or extend license for PAID tiers.

    Extend-or-Create logic (matches Admin GUI):
    - If active key exists → extend expiry (time stacking)
    - If no active key → create new
    - Always writes _mid_to_key + marks trial as upgraded
    """
    ops = _get_ops()
    now = datetime.now()
    tier = LicenseTier.from_code(tier_code)

    # ── Check existing active key (extend-or-create) ──
    existing = ops.get_license_by_mid(mid)
    if existing and existing.get("_st") == "a":
        # ═══ EXTEND: Stack time onto existing key ═══
        key_id = existing.get("_key_id") or existing.get("_doc_id", "")
        old_exp_str = existing.get("_exp", "")
        old_dur = 0
        try:
            old_dur = int(existing.get("_dur", 0) or 0)
        except (ValueError, TypeError):
            pass

        # Parse old expiry
        try:
            old_exp = datetime.fromisoformat(old_exp_str.replace("Z", "")) if old_exp_str else now
        except Exception:
            old_exp = now
        base = old_exp if old_exp > now else now
        new_exp = base + timedelta(days=days)

        extend_data = {
            "_exp": new_exp.isoformat() + "Z",
            "_dur": old_dur + days,
            "_t": tier_code,
            "_nt": f"Extended +{days}d by telegram_bot (was {old_dur}d)",
        }
        ok = ops.write_doc(ops.COLLECTION, key_id, extend_data)

        if ok:
            # Update _mid_to_key expiry
            ops.write_doc(ops.col("mid_to_key"), mid, {
                "expires": new_exp.isoformat() + "Z",
                "updated_at": now.isoformat() + "Z",
            })

            if request_id:
                ops.delete_request(request_id)

            # Mark trial as upgraded
            _mark_trial_upgraded(ops, mid, key_id)

            ops.write_doc("_bot_audit", f"extend_{int(time.time())}", {
                "action": "extend_license",
                "mid_masked": formatters.mask_mid(mid),
                "tier": tier_code, "days_added": days,
                "total_days": old_dur + days,
                "new_exp": new_exp.isoformat() + "Z",
                "timestamp": now.isoformat() + "Z",
                **(approved_by or {}),
            })

            _send(chat_id, (
                f"✅ *Đã gia hạn thành công!*\n\n"
                f"🖥️ MID: `{formatters.mask_mid(mid)}`\n"
                + (f"👤 {client_name}\n" if client_name else "")
                + f"📦 {formatters.tier_display(tier_code)} +{days} ngày\n"
                f"⏱ Tổng: {old_dur + days} ngày\n"
                f"⏰ Hết hạn mới: {new_exp.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"_Client chỉ cần tắt/mở lại app._"
            ))
        else:
            _send(chat_id, "❌ Lỗi extend. Kiểm tra /health")
        return

    # ═══ CREATE: No existing key → create new ═══
    try:
        key, metadata = generate_key(mid, tier, days, UserRole.PREMIUM)
    except RuntimeError as e:
        _send(chat_id, f"❌ Keygen error: {e}")
        return

    lic_data = {
        "_t": metadata["tier"],
        "_st": "a",
        "_cr": now.isoformat() + "Z",
        "_exp": metadata["expires"] + "Z" if "Z" not in metadata["expires"] else metadata["expires"],
        "_mid": mid,
        "_cn": client_name,
        "_ecn": _encrypt_name(client_name, mid) if client_name else "",
        "_nt": f"Created by telegram_bot" + (f" (req: {request_id})" if request_id else ""),
        "_dur": days,
        "_role": 1,
        "_app": "VEO",
    }

    # Lifetime rolling expiry
    if tier == LicenseTier.LIFETIME:
        lic_data["_exp"] = (now + timedelta(days=90)).isoformat() + "Z"
        lic_data["_lt_rolling"] = True

    success = ops.create_license(key, lic_data)

    if success:
        # Write _mid_to_key
        ops.write_mid_to_key(mid, key, tier_code, 1, expires=lic_data.get('_exp', ''))

        # Delete request
        if request_id:
            ops.delete_request(request_id)

        # Mark trial as upgraded
        _mark_trial_upgraded(ops, mid, key)

        # Audit
        audit = {
            "action": "create_license",
            "key_masked": formatters.mask_key(key),
            "mid_masked": formatters.mask_mid(mid),
            "tier": tier_code,
            "days": days,
            "timestamp": now.isoformat() + "Z",
        }
        if approved_by:
            audit["approved_by"] = approved_by
        ops.write_doc("_bot_audit", f"create_{int(time.time())}", audit)

        _send(chat_id, (
            f"✅ *Đã tạo license thành công!*\n\n"
            f"🖥️ MID: `{formatters.mask_mid(mid)}`\n"
            + (f"👤 {client_name}\n" if client_name else "")
            + f"📦 {formatters.tier_display(tier_code)} ({days} ngày)\n"
            f"⏰ Hết hạn: {formatters.fmt_date(metadata['expires'])}\n\n"
            f"_Client chỉ cần tắt/mở lại app._"
        ))
    else:
        _send(chat_id, "❌ Lỗi ghi Firebase. Kiểm tra /health")


def _mark_trial_upgraded(ops, mid: str, key: str) -> None:
    """Mark trial as upgraded if exists (best-effort)."""
    try:
        trial = ops.read_doc(ops.col("trials"), mid)
        if trial and trial.get("status") == "active":
            ops.write_doc(ops.col("trials"), mid, {
                "status": "upgraded",
                "upgraded_to": key,
                "upgraded_at": datetime.now().isoformat() + "Z",
            })
    except Exception:
        pass


# ─── Admin Config / Pricing / Sync Handlers ──────────────────

def handle_config(chat_id: int) -> None:
    """Show config dashboard (_config/client_settings)."""
    ops = _get_ops()
    config = ops.read_config()
    defaults = ops.DEFAULT_CONFIG

    lines = ["⚙️ *Cấu hình Server*\n"]

    # maintenance_mode
    maint = config.get("maintenance_mode", defaults["maintenance_mode"])
    maint_icon = "✅ ON" if maint else "❌ OFF"
    is_default = "maintenance_mode" not in config
    lines.append(f"🔧 Bảo trì: *{maint_icon}*" + (" _(default)_" if is_default else ""))

    # min_client_version
    ver = config.get("min_client_version", defaults["min_client_version"])
    is_default = "min_client_version" not in config
    lines.append(f"📦 Min version: *{ver}*" + (" _(default)_" if is_default else ""))

    # server_weight
    weight = config.get("server_weight", defaults["server_weight"])
    is_default = "server_weight" not in config
    lines.append(f"⚖️ Server weight: *{weight}*" + (" _(default)_" if is_default else ""))

    # trial settings
    poll_ms = config.get("trial_poll_interval_ms", defaults["trial_poll_interval_ms"])
    poll_max = config.get("trial_poll_max", defaults["trial_poll_max"])
    cache_ttl = config.get("validate_cache_ttl_s", defaults["validate_cache_ttl_s"])
    lines.append(f"⏱️ Trial poll: *{poll_ms}ms* × *{poll_max}*")
    lines.append(f"💾 Cache TTL: *{cache_ttl}s*")

    # Any extra fields from Firebase
    extra_keys = set(config.keys()) - set(defaults.keys())
    for ek in sorted(extra_keys):
        lines.append(f"🔹 {ek}: *{config[ek]}*")

    buttons = {
        "inline_keyboard": [
            [
                {"text": "🔧 Bảo trì ON" if not maint else "🔧 Bảo trì OFF",
                 "callback_data": "cfg:maint_on" if not maint else "cfg:maint_off"},
                {"text": "📦 Version", "callback_data": "cfg:version"},
            ],
            [
                {"text": "⚖️ Weight", "callback_data": "cfg:weight"},
                {"text": "💰 Bảng giá", "callback_data": "pricing:view"},
            ],
            [
                {"text": "📋 Menu", "callback_data": "menu:main"},
            ],
        ]
    }
    _send(chat_id, "\n".join(lines), reply_markup=buttons)


def handle_pricing(chat_id: int) -> None:
    """Show pricing table from Firebase or defaults."""
    ops = _get_ops()
    stored = ops.read_pricing()
    defaults = ops.DEFAULT_PRICING

    lines = ["💰 *Bảng giá License*\n"]
    tier_order = ["1M", "3M", "6M", "1Y", "LT"]

    # --- Lần mua đầu ---
    lines.append("🆕 *Lần mua đầu:*")
    for tc in tier_order:
        di = defaults.get(tc, {})
        si = stored.get(tc, {}) if isinstance(stored.get(tc), dict) else {}
        label = di.get("label", tc)
        days = di.get("days", "?")
        fp = si.get("first_price", di.get("first_price", 0))
        src = "" if "first_price" in si else " _(default)_"
        p_fmt = f"{int(fp):,}đ".replace(",", ".") if isinstance(fp, (int, float)) else str(fp)
        emoji = "💎" if tc == "LT" else "📦"
        if tc == "LT":
            lines.append(f"  {emoji} {label} — *{p_fmt}*{src}")
        else:
            lines.append(f"  {emoji} {label} — *{p_fmt}* ({days} ngày){src}")

    # --- Lần mua thường ---
    lines.append("\n🔒 *Lần mua thường:*")
    for tc in tier_order:
        di = defaults.get(tc, {})
        si = stored.get(tc, {}) if isinstance(stored.get(tc), dict) else {}
        label = di.get("label", tc)
        days = di.get("days", "?")
        np = si.get("normal_price", di.get("normal_price", 0))
        src = "" if "normal_price" in si else " _(default)_"
        p_fmt = f"{int(np):,}đ".replace(",", ".") if isinstance(np, (int, float)) else str(np)
        emoji = "💎" if tc == "LT" else "📦"
        if tc == "LT":
            lines.append(f"  {emoji} {label} — *{p_fmt}*{src}")
        else:
            lines.append(f"  {emoji} {label} — *{p_fmt}* ({days} ngày){src}")

    btn_rows = []
    for i in range(0, len(tier_order), 2):
        row = []
        for tc in tier_order[i:i+2]:
            lbl = defaults.get(tc, {}).get("label", tc)
            row.append({"text": f"✏️ {lbl}", "callback_data": f"pricing:edit:{tc}"})
        btn_rows.append(row)
    btn_rows.append([
        {"text": "⚙️ Cài đặt", "callback_data": "menu:config"},
        {"text": "📋 Menu", "callback_data": "menu:main"},
    ])

    _send(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": btn_rows})


def handle_sync(chat_id: int) -> None:
    """Show sync status: doc counts on primary vs backup."""
    ops = _get_ops()
    _send(chat_id, "🔄 Đang kiểm tra...")

    counts = ops.get_db_doc_counts()
    p = counts.get("primary", {})
    b = counts.get("backup", {})
    p_proj = counts.get("primary_project", "?")[:16]
    b_proj = counts.get("backup_project", "?")[:16]

    col_labels = {
        ops.col("lic"): "📋 License",
        ops.col("trials"): "🆓 Trial",
        "_sellers": "🏪 Seller",
    }

    lines = ["🔄 *Sync Status*\n"]
    lines.append(f"*Primary:* `{p_proj}`")
    for col, label in col_labels.items():
        cnt = p.get(col, -1)
        lines.append(f"  {label}: *{cnt}* docs" if cnt >= 0 else f"  {label}: ❌ error")

    lines.append(f"\n*Backup:* `{b_proj}`")
    has_diff = False
    for col, label in col_labels.items():
        cnt_b = b.get(col, -1)
        cnt_p = p.get(col, -1)
        if cnt_b >= 0 and cnt_p >= 0:
            diff = cnt_b - cnt_p
            if diff == 0:
                lines.append(f"  {label}: *{cnt_b}* docs ✅")
            else:
                has_diff = True
                lines.append(f"  {label}: *{cnt_b}* docs ⚠️ ({diff:+d})")
        elif cnt_b >= 0:
            lines.append(f"  {label}: *{cnt_b}* docs")
        else:
            lines.append(f"  {label}: ❌ error")

    buttons = {
        "inline_keyboard": [
            [
                {"text": "🔄 Sync Now" if has_diff else "🔄 Force Sync",
                 "callback_data": "sync:run"},
                {"text": "🔃 Refresh", "callback_data": "menu:sync"},
            ],
            [
                {"text": "⚙️ Cài đặt", "callback_data": "menu:config"},
                {"text": "📋 Menu", "callback_data": "menu:main"},
            ],
        ]
    }
    _send(chat_id, "\n".join(lines), reply_markup=buttons)


def handle_setversion(chat_id: int, args: str) -> None:
    """Set min_client_version on Firebase."""
    version = args.strip()
    if not version:
        _send(chat_id, "❌ Cần version.\n\nVí dụ: `/setversion 2.3.2`")
        return

    ops = _get_ops()
    ok = ops.write_config("min_client_version", version)
    if ok:
        _send(chat_id, f"✅ Đã set `min_client_version` = *{version}*\n\n_Cập nhật cả primary + backup._")
    else:
        _send(chat_id, "❌ Lỗi ghi Firebase.")


def handle_setprice(chat_id: int, args: str) -> None:
    """Set tier pricing on Firebase (first_price and/or normal_price)."""
    parts = args.strip().split()
    if len(parts) < 2:
        _send(chat_id, (
            "❌ Cần tier và giá.\n\n"
            "*Sửa cả 2 giá:*\n"
            "`/setprice <tier> <lần đầu> <thường>`\n"
            "VD: `/setprice 1M 200000 300000`\n\n"
            "*Sửa 1 loại:*\n"
            "`/setprice <tier> first <giá>`\n"
            "`/setprice <tier> normal <giá>`\n"
            "VD: `/setprice 1M first 200000`\n\n"
            "*Tiers:* `1M` `3M` `6M` `1Y` `LT`"
        ))
        return

    tier_code = parts[0].upper()
    valid_tiers = {"1M", "3M", "6M", "1Y", "LT"}
    if tier_code not in valid_tiers:
        _send(chat_id, f"❌ Tier không hợp lệ: `{tier_code}`\n\n*Tiers:* `1M` `3M` `6M` `1Y` `LT`")
        return

    ops = _get_ops()
    label = ops.DEFAULT_PRICING.get(tier_code, {}).get("label", tier_code)

    # Format: /setprice 1M first 200000  OR  /setprice 1M normal 300000
    if len(parts) >= 3 and parts[1].lower() in ("first", "normal"):
        price_type = parts[1].lower()
        try:
            price = int(parts[2].replace(",", "").replace(".", ""))
        except ValueError:
            _send(chat_id, "❌ Giá phải là số. Ví dụ: `200000`")
            return

        if price_type == "first":
            ok = ops.write_pricing(tier_code, first_price=price)
            type_label = "lần mua đầu"
        else:
            ok = ops.write_pricing(tier_code, normal_price=price)
            type_label = "lần mua thường"

        if ok:
            p_fmt = f"{price:,}đ".replace(",", ".")
            _send(chat_id, f"✅ Đã set giá *{type_label}* của *{label}* = *{p_fmt}*")
        else:
            _send(chat_id, "❌ Lỗi ghi Firebase.")
        return

    # Format: /setprice 1M 200000 300000  (both prices)
    try:
        first_p = int(parts[1].replace(",", "").replace(".", ""))
    except ValueError:
        _send(chat_id, "❌ Giá lần đầu phải là số. Ví dụ: `200000`")
        return

    normal_p = None
    if len(parts) >= 3:
        try:
            normal_p = int(parts[2].replace(",", "").replace(".", ""))
        except ValueError:
            _send(chat_id, "❌ Giá thường phải là số. Ví dụ: `300000`")
            return

    ok = ops.write_pricing(tier_code, first_price=first_p, normal_price=normal_p)
    if ok:
        fp_fmt = f"{first_p:,}đ".replace(",", ".")
        msg = f"✅ *{label}*\n  Lần đầu: *{fp_fmt}*"
        if normal_p is not None:
            np_fmt = f"{normal_p:,}đ".replace(",", ".")
            msg += f"\n  Thường: *{np_fmt}*"
        _send(chat_id, msg)
    else:
        _send(chat_id, "❌ Lỗi ghi Firebase.")


# ─── Callback Query Handler ───────────────────────────────────

def handle_callback(update: dict) -> None:
    """Process inline button callbacks."""
    cb = update.get("callback_query", {})
    if not cb:
        return

    cb_id = cb.get("id", "")
    data = cb.get("data", "")
    user = cb.get("from", {})
    user_id = user.get("id", 0)
    chat_id = cb.get("message", {}).get("chat", {}).get("id", 0)
    msg_id = cb.get("message", {}).get("message_id", 0)

    # ── Multi-role auth for callbacks ──
    ops = _get_ops()
    role, seller_data = security.get_user_role(user_id, ops)
    if role == "none":
        _answer_callback(cb_id, "⛔ Không có quyền")
        return

    parts = data.split(":")

    # ── Seller-specific callbacks ──
    if parts[0] == "seller":
        if role not in ("seller", "admin"):
            _answer_callback(cb_id, "⛔ Không có quyền")
            return
        _answer_callback(cb_id)
        if parts[1] == "sell_prompt":
            _send(chat_id, (
                "🔑 *Tạo key mới*\n\n"
                "Gửi lệnh theo format:\n"
                "`/sell <MID> <tier>`\n\n"
                "*Tiers:* `1M` `3M` `6M` `1Y` `LT`\n"
                "Ví dụ: `/sell 3946C15B 3M`"
            ))
        elif parts[1] == "mykeys":
            handle_mykeys(chat_id, seller_data)
        elif parts[1] == "menu":
            handle_start(chat_id, "seller", seller_data)
        return

    # ── Admin-only callbacks (except shared ones) ──
    admin_only_prefixes = {"reject"}
    if parts[0] in admin_only_prefixes and role != "admin":
        _answer_callback(cb_id, "⛔ Chỉ admin mới dùng được")
        return

    # ── Seller list restriction: only trial + premium ──
    if role == "seller" and parts[0] == "lcat" and len(parts) >= 2:
        allowed_cats = {"trial", "premium"}
        if parts[1] not in allowed_cats:
            _answer_callback(cb_id, "⛔ Seller chỉ xem Trial và Premium")
            return

    if parts[0] == "pick_tier" and len(parts) >= 3:
        # Show tier picker — resolve truncated MID/request_id
        ops = _get_ops()
        mid = _resolve_full_mid(ops, parts[1])
        request_id = _resolve_full_mid(ops, parts[2])
        _answer_callback(cb_id)
        _edit_message(
            chat_id, msg_id,
            f"📋 Chọn gói cho `{formatters.mask_mid(mid)}`:",
            reply_markup=_tier_buttons(mid, request_id),
        )

    elif parts[0] == "approve" and len(parts) >= 5:
        # approve:MID:REQUEST_ID:TIER:DAYS — resolve truncated IDs
        ops = _get_ops()
        mid = _resolve_full_mid(ops, parts[1])
        request_id = _resolve_full_mid(ops, parts[2])
        tier_code = parts[3]
        days = int(parts[4])
        _answer_callback(cb_id, f"⏳ Đang tạo key {tier_code}...")

        # Build approver info for audit
        approver = {
            "telegram_id": user_id,
            "role": role,
        }
        if role == "seller":
            approver["seller_name"] = seller_data.get("name", "")
            approver["seller_mid"] = seller_data.get("_doc_id", "")[:16]

        # Get client name from request if possible
        ops = _get_ops()
        client_name = ""
        if request_id:
            req_data = ops.read_doc(ops.REQUEST_COLLECTION, request_id)
            if req_data:
                client_name = req_data.get("client_name", "")

        # Route: TRIAL → _do_approve_trial, PAID → _do_create_license
        if tier_code.upper() in ("TRIA", "TRIAL", "FREE"):
            _do_approve_trial(chat_id, mid, request_id, client_name, approved_by=approver)
        else:
            _do_create_license(chat_id, mid, tier_code, days, request_id, client_name, approved_by=approver)

    elif parts[0] == "reject" and len(parts) >= 3:
        # Resolve truncated MID/request_id
        ops = _get_ops()
        mid = _resolve_full_mid(ops, parts[1])
        request_id = _resolve_full_mid(ops, parts[2])
        _answer_callback(cb_id, "❌ Đã từ chối")
        ops.write_doc(ops.REQUEST_COLLECTION, request_id, {
            "status": "rejected",
            "rejected_by": "telegram_bot",
            "rejected_at": datetime.utcnow().isoformat() + "Z",
        })
        _edit_message(chat_id, msg_id, f"❌ Đã từ chối request `{formatters.mask_mid(mid)}`")

    elif parts[0] == "lookup" and len(parts) >= 2:
        # Resolve truncated MID prefix from callback_data
        ops = _get_ops()
        mid = _resolve_full_mid(ops, parts[1])
        _answer_callback(cb_id)
        handle_lookup(chat_id, mid)

    elif parts[0] == "lcat" and len(parts) >= 2:
        _answer_callback(cb_id)
        _list_by_role(chat_id, parts[1])

    elif parts[0] == "litem" and len(parts) >= 3:
        _answer_callback(cb_id)
        mid = parts[1]
        role_filter = parts[2]
        _show_item_actions(chat_id, mid, role_filter, viewer_role=role)

    elif parts[0] == "list" and len(parts) >= 2:
        _answer_callback(cb_id)
        status_code = parts[1]  # "a", "e", "r", or "all"
        if status_code in ("a", "e", "r"):
            # Status filter: route directly to _list_by_status
            _list_by_status(chat_id, status_code)
        elif status_code == "all":
            # "Tất cả" from status overview: show all licenses directly
            _list_by_role(chat_id, "all")
        elif role == "seller":
            handle_list(chat_id, status_code, role="seller")
        else:
            handle_list(chat_id, status_code)

    elif parts[0] == "menu":
        _answer_callback(cb_id)
        action = parts[1] if len(parts) > 1 else "main"
        if action == "main" or action == "start":
            if role == "seller":
                handle_start(chat_id, "seller", seller_data)
            else:
                handle_start(chat_id)
        elif action == "status":
            if role == "seller":
                handle_status(chat_id, role="seller")
            else:
                handle_status(chat_id)
        elif action == "health":
            handle_health(chat_id)
        elif action == "pending":
            handle_pending(chat_id)
        elif action == "config":
            if role != "admin":
                _send(chat_id, "⛔ Chỉ admin mới dùng được.")
            else:
                handle_config(chat_id)
        elif action == "pricing":
            if role != "admin":
                _send(chat_id, "⛔ Chỉ admin mới dùng được.")
            else:
                handle_pricing(chat_id)
        elif action == "sync":
            if role != "admin":
                _send(chat_id, "⛔ Chỉ admin mới dùng được.")
            else:
                handle_sync(chat_id)
        elif action == "list":
            if role == "seller":
                handle_list(chat_id, "all", role="seller")
            else:
                handle_list(chat_id, "all")
        # ── Seller-specific menu callbacks ──
        elif action == "seller_status":
            handle_status(chat_id, role="seller")
        elif action == "seller_list":
            # Show trial + premium filter buttons
            btns = {
                "inline_keyboard": [
                    [
                        {"text": "🆓 Trial", "callback_data": "lcat:trial"},
                        {"text": "💎 Premium", "callback_data": "lcat:premium"},
                    ],
                    [{"text": "📋 Menu", "callback_data": "seller:menu"}],
                ]
            }
            _send(chat_id, "📋 *Chọn danh sách:*", reply_markup=btns)
        elif action == "seller_pending":
            handle_pending(chat_id)
        elif action == "lookup_prompt":
            _send(chat_id, "🔍 *Tra cứu license*\n\nGửi MID cần tra cứu:\n`/lookup <MID>`\n\nVí dụ: `/lookup 3946C15B`")
        elif action == "create_prompt":
            _send(chat_id, (
                "🔑 *Tạo key mới*\n\n"
                "Gửi lệnh theo format:\n"
                "`/create <MID> <tier> <days>`\n\n"
                "*Tiers:* `1M` `3M` `6M` `1Y` `LT`\n"
                "Ví dụ: `/create 3946C15B 3M 90`"
            ))
        elif action == "extend_prompt":
            _send(chat_id, "⏱️ *Gia hạn key*\n\nGửi lệnh:\n`/extend <MID> <days>`\n\nVí dụ: `/extend 3946C15B 30`")
        elif action == "revoke_prompt":
            _send(chat_id, "🔴 *Thu hồi key*\n\nGửi lệnh:\n`/revoke <KEY>`")

    # ── Config callbacks (admin-only) ──
    elif parts[0] == "cfg" and len(parts) >= 2:
        _answer_callback(cb_id)
        if role != "admin":
            _send(chat_id, "⛔ Chỉ admin mới dùng được.")
            return
        cfg_action = parts[1]
        if cfg_action == "maint_on":
            ops.write_config("maintenance_mode", True)
            _send(chat_id, "✅ *Bảo trì:* ĐÃ BẬT\n\n_Client sẽ thấy thông báo bảo trì._")
        elif cfg_action == "maint_off":
            ops.write_config("maintenance_mode", False)
            _send(chat_id, "✅ *Bảo trì:* ĐÃ TẮT\n\n_Client hoạt động bình thường._")
        elif cfg_action == "version":
            _send(chat_id, "📦 *Set min version*\n\nGửi lệnh:\n`/setversion <version>`\n\nVí dụ: `/setversion 2.3.2`")
        elif cfg_action == "weight":
            buttons = {
                "inline_keyboard": [
                    [
                        {"text": "30", "callback_data": "cfg:w:30"},
                        {"text": "50", "callback_data": "cfg:w:50"},
                        {"text": "70", "callback_data": "cfg:w:70"},
                        {"text": "100", "callback_data": "cfg:w:100"},
                    ],
                    [{"text": "⚙️ Quay lại", "callback_data": "menu:config"}],
                ]
            }
            _send(chat_id, "⚖️ *Chọn server weight:*", reply_markup=buttons)
        elif cfg_action == "w" and len(parts) >= 3:
            try:
                weight_val = int(parts[2])
                ops.write_config("server_weight", weight_val)
                _send(chat_id, f"✅ *Server weight:* {weight_val}")
            except ValueError:
                _send(chat_id, "❌ Giá trị không hợp lệ.")

    # ── Pricing callbacks (admin-only) ──
    elif parts[0] == "pricing" and len(parts) >= 2:
        _answer_callback(cb_id)
        if role != "admin":
            _send(chat_id, "⛔ Chỉ admin mới dùng được.")
            return
        if parts[1] == "view":
            handle_pricing(chat_id)
        elif parts[1] == "edit" and len(parts) >= 3:
            tier_code = parts[2]
            label = ops.DEFAULT_PRICING.get(tier_code, {}).get("label", tier_code)
            _send(chat_id, (
                f"✏️ *Sửa giá: {label}*\n\n"
                f"*Cả 2 giá:*\n`/setprice {tier_code} <lần đầu> <thường>`\n"
                f"VD: `/setprice {tier_code} 200000 300000`\n\n"
                f"*Chỉ lần đầu:*\n`/setprice {tier_code} first <giá>`\n\n"
                f"*Chỉ thường:*\n`/setprice {tier_code} normal <giá>`"
            ))

    # ── Sync callbacks (admin-only) ──
    elif parts[0] == "sync" and len(parts) >= 2:
        _answer_callback(cb_id)
        if role != "admin":
            _send(chat_id, "⛔ Chỉ admin mới dùng được.")
            return
        if parts[1] == "run":
            _send(chat_id, "🔄 Đang sync...")
            total_synced = 0
            total_errors = 0
            results = []
            for col in [ops.col("lic"), ops.col("trials"), "_sellers", "_config", ops.col("mid_to_key"), ops.col("blocked")]:
                stats = ops.sync_collection(col)
                total_synced += stats["synced"]
                total_errors += stats["errors"]
                if stats["synced"] > 0 or stats["errors"] > 0:
                    results.append(f"  `{col}`: +{stats['synced']} synced, {stats['errors']} errors")
            if results:
                _send(chat_id, f"✅ *Sync hoàn tất*\n\n" + "\n".join(results))
            else:
                _send(chat_id, "✅ *Sync hoàn tất* — Không có gì cần sync.")

    elif parts[0] == "action" and len(parts) >= 3:
        _answer_callback(cb_id)
        act = parts[1]
        target = parts[2]

        # ── Permission check for actions ──
        admin_only_actions = {
            "extend", "upgrade", "confirmpay", "chrole",
            "linkprompt", "sellermid", "block", "unblock",
        }
        # Revoke: admin always, seller L2 only for own keys
        if act in admin_only_actions and role != "admin":
            _send(chat_id, "⛔ Chỉ admin mới dùng được chức năng này.")
            return
        if act == "revoke" and role == "seller":
            level = seller_data.get("level", 1)
            if level < 2:
                _send(chat_id, "⛔ Seller Level 1 không có quyền thu hồi key.")
                return

        if act == "extend":
            _send(chat_id, f"⏱️ *Gia hạn key cho MID:* `{formatters.mask_mid(target)}`\n\nGửi số ngày:\n`/extend {target} <days>`")
        elif act == "revoke":
            _send(chat_id, f"🔴 *Thu hồi key:* `{formatters.mask_key(target)}`\n\nXác nhận:\n`/revoke {target}`")
        elif act == "sellermid":
            # Show full MID for copying
            sellers = ops.list_docs("_sellers", page_size=100)
            full_mid = target
            seller_name = ""
            for s in sellers:
                sid = s.get("machine_id", "") or s.get("_doc_id", "")
                if sid.startswith(target):
                    full_mid = sid
                    seller_name = s.get("name", "")
                    break
            _send(chat_id, (
                f"🏪 *Seller MID*\n\n"
                + (f"👤 {seller_name}\n" if seller_name else "")
                + f"📋 Tap để copy:\n`{full_mid}`\n\n"
                f"_🗑️ Copy xong nhớ xóa tin nhắn này!_"
            ), auto_delete=120)
        elif act == "linkprompt":
            # Show /linkseller command template
            sellers = ops.list_docs("_sellers", page_size=100)
            full_mid = target
            seller_name = ""
            for s in sellers:
                sid = s.get("machine_id", "") or s.get("_doc_id", "")
                if sid.startswith(target):
                    full_mid = sid
                    seller_name = s.get("name", "")
                    break
            _send(chat_id, (
                f"🔗 *Liên kết Telegram cho {seller_name}*\n\n"
                f"Gửi lệnh:\n"
                f"`/linkseller <telegram_id> {full_mid}`\n\n"
                f"💡 Seller mở chat với bot, gửi bất kỳ tin nhắn → bot trả về Telegram ID."
            ))
        elif act == "showkey":
            # Show full serial key for copying
            lic = _find_lic_by_prefix(ops, target)
            if lic:
                key_id = lic.get("_doc_id", "")
                name = lic.get("_cn", "") or ""
                if name == "***":
                    ecn = lic.get("_ecn", "")
                    mid = lic.get("_mid", "")
                    if ecn and mid:
                        name = _decrypt_name(ecn, mid)
                _send(chat_id, (
                    f"🔑 *Serial Key*\n\n"
                    + (f"👤 {name}\n" if name and name != '***' else "")
                    + f"📋 Tap để copy:\n`{key_id}`\n\n"
                    f"_🗑️ Copy xong nhớ xóa tin nhắn này!_"
                ), auto_delete=120)
            else:
                _send(chat_id, f"❌ Không tìm thấy key cho `{target}...`")
        elif act == "upgrade":
            # Show payment confirmation step
            _send(
                chat_id,
                f"⬆️ *Nâng cấp MID:* `{formatters.mask_mid(target)}`\n\n"
                f"Xác nhận thanh toán trước khi tạo key:",
                reply_markup={"inline_keyboard": [
                    [{"text": "💰 Đã thanh toán — Chọn gói", "callback_data": f"action:confirmpay:{target}"}],
                    [{"text": "❌ Hủy", "callback_data": "menu:main"}],
                ]},
            )
        elif act == "confirmpay":
            # Payment confirmed → show tier picker
            _send(
                chat_id,
                f"✅ *Xác nhận thanh toán OK*\n\nChọn gói cho `{formatters.mask_mid(target)}`:",
                reply_markup=_tier_buttons(target),
            )
        elif act == "newkey":
            # Show tier picker for new key creation
            _send(
                chat_id,
                f"🔑 *Tạo key mới cho MID:* `{formatters.mask_mid(target)}`\n\nChọn gói:",
                reply_markup=_tier_buttons(target),
            )
        elif act == "chrole" and len(parts) >= 4:
            new_role = int(parts[3])
            role_name = formatters.ROLE_NAMES.get(new_role, "?")
            ops = _get_ops()
            lic = ops.get_license_by_mid(target)
            if lic:
                key_id = lic.get("_doc_id", "")
                ops.write_doc(ops.COLLECTION, key_id, {"_role": new_role})
                _send(chat_id, f"✅ Đã đổi role → *{role_name}* cho MID `{formatters.mask_mid(target)}`")
            else:
                _send(chat_id, f"❌ Không tìm thấy license cho MID `{formatters.mask_mid(target)}`")
        elif act == "block":
            # Block machine — find full MID via prefix
            ops = _get_ops()
            full_mid = _resolve_full_mid(ops, target)
            success = ops.block_machine(full_mid, reason="Blocked via Telegram bot")
            if success:
                _send(chat_id, f"🚫 Đã *BLOCK* machine `{formatters.mask_mid(full_mid)}`")
            else:
                _send(chat_id, f"❌ Không thể block machine `{formatters.mask_mid(target)}`")
        elif act == "unblock":
            # Unblock machine — find full MID via prefix
            ops = _get_ops()
            full_mid = _resolve_full_mid(ops, target)
            success = ops.unblock_machine(full_mid)
            if success:
                _send(chat_id, f"🔓 Đã *UNLOCK* machine `{formatters.mask_mid(full_mid)}`")
            else:
                _send(chat_id, f"❌ Không thể unlock machine `{formatters.mask_mid(target)}`")

    elif parts[0] == "cancel":
        _answer_callback(cb_id, "Đã hủy")
        _delete_message(chat_id, msg_id)

    else:
        _answer_callback(cb_id, "❓ Unknown action")


# ─── Seller Commands ───────────────────────────────────────────

def handle_sell(chat_id: int, args: str, seller_data: dict) -> None:
    """Seller creates a key: /sell <MID> <tier>."""
    parts = args.split(None, 2)  # Split into max 3 parts: MID, tier, [name]
    if len(parts) < 2:
        _send(chat_id, (
            "🔑 *Tạo key mới*\n\n"
            "Gửi lệnh theo format:\n"
            "`/sell <MID> <tier> [tên khách]`\n\n"
            "*Tiers:* `1M` `3M` `6M` `1Y` `LT`\n"
            "Ví dụ: `/sell 3946C15B 3M Nguyễn Văn A`"
        ))
        return

    mid_raw = parts[0]
    tier_raw = parts[1]

    mid = security.validate_mid(mid_raw)
    if not mid:
        _send(chat_id, "❌ MID không hợp lệ. 8-64 ký tự hex.")
        return

    tier = security.validate_tier(tier_raw)
    if not tier:
        _send(chat_id, f"❌ Tier không hợp lệ. Dùng: `1M` `3M` `6M` `1Y` `LT`")
        return

    days_map = {"TRIA": 5, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "LT": 36500}
    days = days_map.get(tier, 30)

    seller_mid = seller_data.get("machine_id", "") or seller_data.get("_doc_id", "")
    seller_name = seller_data.get("name", "")
    client_name = parts[2].strip() if len(parts) > 2 else ""

    # Create key with seller attribution
    ops = _get_ops()
    tier_obj = LicenseTier.from_code(tier)
    try:
        key, metadata = generate_key(mid, tier_obj, days, UserRole.PREMIUM)
    except RuntimeError as e:
        _send(chat_id, f"❌ Keygen error: {e}")
        return

    now = datetime.now()
    lic_data = {
        "_t": metadata["tier"],
        "_st": "a",
        "_cr": now.isoformat() + "Z",
        "_exp": metadata["expires"] + "Z" if "Z" not in metadata["expires"] else metadata["expires"],
        "_mid": mid,
        "_cn": client_name,
        "_ecn": _encrypt_name(client_name, mid) if client_name else "",
        "_nt": f"Created by seller:{seller_name}",
        "_dur": days,
        "_role": 1,
        "_app": "VEO",
        "_approved_by": f"seller:{seller_mid}",
    }

    if tier_obj == LicenseTier.LIFETIME:
        lic_data["_exp"] = (now + timedelta(days=90)).isoformat() + "Z"
        lic_data["_lt_rolling"] = True

    success = ops.create_license(key, lic_data)
    if success:
        ops.write_mid_to_key(mid, key, tier, 1, expires=lic_data.get('_exp', ''))
        ops.write_doc("_bot_audit", f"seller_create_{int(time.time())}", {
            "action": "seller_create_license",
            "seller_mid": formatters.mask_mid(seller_mid),
            "seller_name": seller_name,
            "key_masked": formatters.mask_key(key),
            "mid_masked": formatters.mask_mid(mid),
            "tier": tier,
            "days": days,
            "timestamp": now.isoformat() + "Z",
        })
        _send(chat_id, (
            f"✅ *Đã tạo key thành công!*\n\n"
            f"📋 Tap để copy:\n`{key}`\n"
            f"📦 {formatters.tier_display(tier)} ({days} ngày)\n"
            f"⏰ Hết hạn: {formatters.fmt_date(metadata['expires'])}\n\n"
            f"_🗑️ Copy key rồi xóa tin nhắn này!_"
        ), auto_delete=120)
    else:
        _send(chat_id, "❌ Lỗi ghi Firebase.")


def handle_mykeys(chat_id: int, seller_data: dict) -> None:
    """Show keys created by this seller."""
    ops = _get_ops()
    seller_mid = seller_data.get("machine_id", "") or seller_data.get("_doc_id", "")
    all_keys = ops.list_docs(ops.COLLECTION, page_size=500)

    my_keys = [k for k in all_keys if k.get("_approved_by", "") == f"seller:{seller_mid}"]

    if not my_keys:
        _send(chat_id, "📋 *Key đã tạo*\n\nChưa tạo key nào.")
        return

    status_emoji = {"a": "🟢", "r": "🔴", "e": "⚫"}
    lines = [f"📋 *Key đã tạo* ({len(my_keys)})", ""]

    for lic in my_keys[:20]:
        mid = lic.get("_mid", "") or "?"
        tier = lic.get("_t", "") or "?"
        st = lic.get("_st", "?")
        name = lic.get("_cn", "") or ""
        se = status_emoji.get(st, "❓")

        # Decrypt name if needed
        if name == "***" or not name:
            ecn = lic.get("_ecn", "")
            if ecn and mid:
                name = _decrypt_name(ecn, mid)

        line = f"{se} `{formatters.mask_mid(mid)}` | {formatters.tier_display(tier)}"
        if name and name != "***":
            line += f" | {name}"
        if lic.get("_exp") and st == "a":
            line += f"\n    {formatters.fmt_remaining(str(lic['_exp']))}"
        lines.append(line)

    if len(my_keys) > 20:
        lines.append(f"\n_... và {len(my_keys) - 20} key khác_")

    _send(chat_id, "\n".join(lines))


def handle_linkseller(chat_id: int, args: str) -> None:
    """Admin links a seller's Telegram account: /linkseller <telegram_id> <seller_MID>"""
    parts = args.split()
    if len(parts) < 2:
        _send(chat_id, (
            "🏪 *Liên kết Seller*\n\n"
            "`/linkseller <telegram_id> <seller_MID>`\n\n"
            "Ví dụ: `/linkseller 789456123 abc123def456`"
        ))
        return

    try:
        tg_id = int(parts[0])
    except ValueError:
        _send(chat_id, "❌ Telegram ID phải là số.")
        return

    seller_mid = parts[1].strip()
    ops = _get_ops()

    # Check seller exists
    seller = ops.read_doc("_sellers", seller_mid)
    if not seller:
        _send(chat_id, f"❌ Không tìm thấy seller với MID `{formatters.mask_mid(seller_mid)}`")
        return

    # Write telegram_id to seller doc
    ops.write_doc("_sellers", seller_mid, {"telegram_id": tg_id})
    security.invalidate_seller_cache()

    seller_name = seller.get("name", "")
    level = seller.get("level", 1)

    _send(chat_id, (
        f"✅ *Đã liên kết!*\n\n"
        f"🏪 Seller: {seller_name} (L{level})\n"
        f"📱 Telegram ID: `{tg_id}`\n\n"
        f"Seller giờ có thể nhắn /start cho bot."
    ))

    # Send welcome to seller
    try:
        _send(tg_id, (
            f"🎉 *Chào mừng, {seller_name}!*\n\n"
            f"Bạn đã được liên kết với hệ thống VEO License.\n"
            f"Gõ /start để bắt đầu."
        ))
    except Exception:
        pass  # Seller may not have started bot yet


# ─── Admin Utility Commands ────────────────────────────────────

def handle_audit(chat_id: int, args: str) -> None:
    """Handle /audit [N] — show last N audit log entries."""
    n = 10
    if args.strip().isdigit():
        n = min(int(args.strip()), 50)

    ops = _get_ops()
    audits = ops.list_docs("_bot_audit", page_size=n + 20)
    # Sort by timestamp descending
    audits.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    audits = audits[:n]

    if not audits:
        _send(chat_id, "📋 *Audit Log* — Không có dữ liệu.")
        return

    lines = [f"📋 *Audit Log* — {len(audits)} entries gần nhất", ""]
    for a in audits:
        action = a.get("action", "?")
        ts = formatters.fmt_date(a.get("timestamp", ""))
        mid = a.get("mid_masked", "")
        tier = a.get("tier", "")
        line = f"• `{action}` | {ts}"
        if mid:
            line += f" | {mid}"
        if tier:
            line += f" | {tier}"
        approver = a.get("approved_by", {})
        if isinstance(approver, dict) and approver.get("seller_name"):
            line += f" | by:{approver['seller_name']}"
        lines.append(line)

    _send(chat_id, "\n".join(lines))


def handle_key_lookup(chat_id: int, args: str) -> None:
    """Handle /key <key> — lookup license by key directly."""
    key = security.validate_key(args)
    if not key:
        _send(chat_id, "❌ Cú pháp: `/key <license_key>`")
        return

    ops = _get_ops()
    lic = ops.get_license(key)
    if not lic:
        _send(chat_id, f"❌ Key không tồn tại: `{formatters.mask_key(key)}`")
        return

    lic["_doc_id"] = key
    # Decrypt name if needed
    ecn = lic.get("_ecn", "")
    mid = lic.get("_mid", "")
    if ecn and mid and (not lic.get("_cn") or lic.get("_cn") == "***"):
        lic["_cn"] = _decrypt_name(ecn, mid)

    buttons = _license_action_buttons(mid, key)
    _send(chat_id, formatters.fmt_license(lic, key), reply_markup=buttons)


def handle_cleanup(chat_id: int) -> None:
    """Handle /cleanup — scan & mark expired licenses."""
    ops = _get_ops()
    all_keys = ops.list_docs(ops.COLLECTION, page_size=500)
    now = datetime.now()
    marked = 0

    for lic in all_keys:
        if lic.get("_st") != "a":
            continue
        exp_str = lic.get("_exp", "")
        if not exp_str:
            continue
        try:
            exp_dt = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
            if exp_dt.tzinfo:
                exp_dt = exp_dt.replace(tzinfo=None)
            if exp_dt < now:
                key_id = lic.get("_doc_id", "")
                if key_id:
                    ops.write_doc(ops.COLLECTION, key_id, {"_st": "e"})
                    marked += 1
        except Exception:
            pass

    if marked:
        _send(chat_id, f"🧹 *Cleanup hoàn tất!*\n\n⚫ Đã đánh dấu *{marked}* key hết hạn → expired.")
    else:
        _send(chat_id, "✅ Không có key nào cần cleanup.")


def handle_orphans(chat_id: int) -> None:
    """Handle /orphans — find orphaned _mid_to_key entries (no matching _lic)."""
    ops = _get_ops()
    mid_entries = ops.list_docs(ops.col("mid_to_key"), page_size=500)
    all_keys = ops.list_docs(ops.COLLECTION, page_size=500)

    # Build set of valid (active) key IDs
    valid_keys = {k.get("_doc_id", "") for k in all_keys if k.get("_st") == "a"}

    orphans = []
    for entry in mid_entries:
        mid = entry.get("_doc_id", "")
        # Check if there is an active license pointing to this MID
        has_valid = any(
            k.get("_mid") == mid and k.get("_st") == "a"
            for k in all_keys
        )
        if not has_valid:
            orphans.append(mid)

    if not orphans:
        _send(chat_id, "✅ *Không có orphan* — tất cả _mid_to_key đều có license active.")
        return

    lines = [f"🔍 *Orphaned _mid_to_key* — {len(orphans)} entries", ""]
    for mid in orphans[:20]:
        lines.append(f"• `{formatters.mask_mid(mid)}`")
    if len(orphans) > 20:
        lines.append(f"\n_... và {len(orphans) - 20} mục khác_")
    lines.append("\n_Dùng `/extend <MID> <days>` để reactivate, hoặc xem xét xóa._")

    _send(chat_id, "\n".join(lines))


# ─── Main Dispatcher ───────────────────────────────────────────

def dispatch(update: dict) -> str:
    """Dispatch Telegram update to appropriate handler.

    Returns:
        Response text for logging.
    """
    # Handle callback queries (inline buttons)
    if "callback_query" in update:
        handle_callback(update)
        return "callback_processed"

    # Handle messages
    message = update.get("message", {})
    if not message:
        return "no_message"

    chat_id = message.get("chat", {}).get("id", 0)
    user_id = message.get("from", {}).get("id", 0)
    text = message.get("text", "").strip()

    if not chat_id or not text:
        return "empty"

    # ── Rate limit ──
    if not security.check_rate_limit(user_id):
        _send(chat_id, "⚠️ Rate limited. Vui lòng chờ.")
        return "rate_limited"

    # ── Multi-role auth ──
    ops = _get_ops()
    role, seller_data = security.get_user_role(user_id, ops)

    if role == "none":
        _send(chat_id, "⛔ Bạn không có quyền sử dụng bot này.")
        return "unauthorized"

    # ── Route commands ──
    cmd = text.split()[0].lower().replace("@vadacceptadminbot", "")
    args = text[len(cmd):].strip()

    if role == "admin":
        routes = {
            "/start": lambda: handle_start(chat_id),
            "/help": lambda: handle_start(chat_id),
            "/menu": lambda: handle_start(chat_id),
            "/status": lambda: handle_status(chat_id),
            "/health": lambda: handle_health(chat_id),
            "/pending": lambda: handle_pending(chat_id),
            "/list": lambda: handle_list(chat_id, args if args else "all"),
            "/lookup": lambda: handle_lookup(chat_id, args),
            "/approve": lambda: handle_approve_command(chat_id, args),
            "/reject": lambda: handle_reject_command(chat_id, args),
            "/create": lambda: handle_create(chat_id, args),
            "/revoke": lambda: handle_revoke(chat_id, args),
            "/extend": lambda: handle_extend(chat_id, args),
            "/audit": lambda: handle_audit(chat_id, args),
            "/key": lambda: handle_key_lookup(chat_id, args),
            "/cleanup": lambda: handle_cleanup(chat_id),
            "/orphans": lambda: handle_orphans(chat_id),
            "/sell": lambda: handle_sell(chat_id, args, {}),
            "/mykeys": lambda: handle_mykeys(chat_id, {}),
            "/linkseller": lambda: handle_linkseller(chat_id, args),
            "/config": lambda: handle_config(chat_id),
            "/pricing": lambda: handle_pricing(chat_id),
            "/setversion": lambda: handle_setversion(chat_id, args),
            "/setprice": lambda: handle_setprice(chat_id, args),
            "/sync": lambda: handle_sync(chat_id),
        }
    elif role == "seller":
        level = seller_data.get("level", 1)
        routes = {
            "/start": lambda: handle_start(chat_id, "seller", seller_data),
            "/help": lambda: handle_start(chat_id, "seller", seller_data),
            "/menu": lambda: handle_start(chat_id, "seller", seller_data),
            "/status": lambda: handle_status(chat_id, role="seller"),
            "/list": lambda: handle_list(chat_id, args if args else "trial", role="seller"),
            "/pending": lambda: handle_pending(chat_id),
            "/approve": lambda: handle_approve_command(chat_id, args),
            "/sell": lambda: handle_sell(chat_id, args, seller_data),
            "/mykeys": lambda: handle_mykeys(chat_id, seller_data),
            "/lookup": lambda: handle_lookup(chat_id, args),
        }
        # Level 2 (Manager) can also revoke
        if level >= 2:
            routes["/revoke"] = lambda: handle_revoke(chat_id, args)
    else:
        routes = {}

    handler = routes.get(cmd)
    if handler:
        try:
            handler()
            return f"cmd:{cmd}:{role}"
        except Exception as e:
            log.error(f"[BOT] Handler error for {cmd}: {e}", exc_info=True)
            _send(chat_id, f"❌ Lỗi: {e}")
            return f"error:{cmd}"

    if role == "seller":
        _send(chat_id, "❌ Lệnh không hợp lệ. Gõ /start để xem menu.")
    else:
        _send(chat_id, "❓ Lệnh không hợp lệ. Gõ /help để xem danh sách lệnh.")
    return "unknown_cmd"
