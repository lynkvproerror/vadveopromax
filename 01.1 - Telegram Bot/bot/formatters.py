"""
Message Formatting Helpers
==========================
Format Telegram messages with Vietnamese text and emoji.
"""

from datetime import datetime


# ─── Tier Display ──────────────────────────────────────────────

TIER_NAMES = {
    "TRIA": "Trial (3 ngày)",
    "1M": "1 Tháng",
    "3M": "3 Tháng",
    "6M": "6 Tháng",
    "1Y": "1 Năm",
    "LT": "Vĩnh viễn",
}

TIER_DAYS = {
    "TRIA": 3, "1M": 30, "3M": 90,
    "6M": 180, "1Y": 365, "LT": 36500,
}

ROLE_NAMES = {0: "TRIAL", 1: "PREMIUM", 2: "TESTER"}


def tier_display(code: str) -> str:
    return TIER_NAMES.get(code, code or "?")


def role_display(code) -> str:
    return ROLE_NAMES.get(int(code) if code else 1, "?")


# ─── Key Masking ───────────────────────────────────────────────

def mask_key(key: str) -> str:
    """Mask license key: show first and last segment only."""
    parts = key.split("-")
    if len(parts) >= 9:
        return f"{parts[0]}-****-****-****-****-****-****-{parts[7]}-{parts[8]}"
    if len(parts) >= 4:
        return f"{parts[0]}-****-...-{parts[-1]}"
    return key[:4] + "****"


def mask_mid(mid: str) -> str:
    """Show first 8 chars of MID."""
    return mid[:8] + "..." if len(mid) > 8 else mid


# ─── Date Formatting ──────────────────────────────────────────

def fmt_date(dt_str) -> str:
    """Format ISO date string to readable format."""
    try:
        if dt_str is None:
            return datetime.now().strftime("%d/%m/%Y %H:%M")
        if isinstance(dt_str, str):
            raw = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
        elif hasattr(dt_str, "strftime"):
            dt = dt_str
        else:
            return str(dt_str)[:10]
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt_str)[:16]


def fmt_remaining(dt_str: str) -> str:
    """Format remaining days until expiry."""
    try:
        if isinstance(dt_str, str):
            raw = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
        elif hasattr(dt_str, "replace"):
            dt = dt_str
        else:
            return "?"
        delta = dt - datetime.now()
        days = delta.days
        if days < 0:
            return "⛔ Đã hết hạn"
        if days == 0:
            return "⚠️ Hết hạn hôm nay"
        return f"📅 Còn {days} ngày"
    except Exception:
        return "?"


# ─── Message Templates ────────────────────────────────────────

def fmt_status(summary: dict) -> str:
    return (
        "📊 *Tổng quan License*\n\n"
        f"🟢 Active: *{summary.get('active', 0)}*\n"
        f"🔴 Revoked: *{summary.get('revoked', 0)}*\n"
        f"⚫ Expired: *{summary.get('expired', 0)}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 Tổng License: *{summary.get('total', 0)}*\n"
        f"💎 Premium: *{summary.get('premium', 0)}*\n"
        f"🧪 Tester: *{summary.get('tester', 0)}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🆓 Trial: *{summary.get('trial_active', 0)}* active"
        + (f", {summary.get('trial_upgraded', 0)} upgraded" if summary.get('trial_upgraded') else "")
        + f" / {summary.get('trial_total', 0)} tổng\n"
        f"🏪 Seller: *{summary.get('seller_total', 0)}*"
    )


def fmt_health(health: dict) -> str:
    p = "✅" if health.get("primary") else "❌"
    b = "✅" if health.get("backup") else "❌"
    return (
        "🏥 *Health Check*\n\n"
        f"Primary DB: {p}\n"
        f"Backup DB:  {b}"
    )


def fmt_license(data: dict, key_id: str = "") -> str:
    """Format license info for display."""
    mid = data.get("_mid") or data.get("machine_id") or "?"
    name = data.get("_cn") or data.get("client_name") or ""
    tier = data.get("_t") or data.get("tier") or "?"
    role = data.get("_role") or data.get("role", 1)
    status = data.get("_st", "?")
    exp = data.get("_exp") or data.get("expires") or ""

    status_emoji = {"a": "🟢 Active", "r": "🔴 Revoked", "e": "⚫ Expired"}.get(
        status, f"❓ {status}"
    )

    lines = ["📋 *License Info*\n"]
    if key_id:
        lines.append(f"🔑 Key: `{mask_key(key_id)}`")
    lines.append(f"🖥️ MID: `{mask_mid(mid)}`")
    if name and name != "***":
        lines.append(f"👤 Tên: {name}")
    lines.append(f"📦 Gói: *{tier_display(tier)}* | Role: {role_display(role)}")
    lines.append(f"🔹 Status: {status_emoji}")
    if exp:
        lines.append(f"⏰ Hết hạn: {fmt_date(exp)}")
        lines.append(f"   {fmt_remaining(exp)}")

    return "\n".join(lines)


def fmt_request(data: dict) -> str:
    """Format upgrade request for notification."""
    mid = data.get("machine_id") or data.get("_doc_id") or "?"
    name = data.get("client_name") or ""
    tier = data.get("tier") or "?"
    email = data.get("email") or ""
    time_str = data.get("requested_at") or data.get("client_submitted_at") or ""

    lines = [
        "🆕 *Yêu cầu nâng cấp!*\n",
        f"👤 Tên: {name}" if name else "",
        f"🖥️ MID: `{mask_mid(mid)}`",
        f"📦 Gói: *{tier_display(tier)}*",
        f"📧 Email: {email}" if email else "",
        f"⏰ Thời gian: {fmt_date(time_str)}" if time_str else "",
    ]

    return "\n".join(line for line in lines if line)


def fmt_approve_success(key: str, tier: str, days: int, expires: str, name: str = "") -> str:
    header = "✅ *Đã tạo key thành công!*\n\n"
    name_line = f"👤 {name}\n" if name else ""
    return (
        f"{header}"
        f"{name_line}"
        f"🔑 `{key}`\n"
        f"📦 {tier_display(tier)} ({days} ngày)\n"
        f"⏰ Hết hạn: {fmt_date(expires)}\n\n"
        f"_🗑️ Tin nhắn này tự xóa sau 60s_"
    )
