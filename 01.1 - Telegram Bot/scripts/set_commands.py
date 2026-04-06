"""
Register Telegram Bot Commands Menu
====================================
Sets the "/" command menu that appears in Telegram chat.
Supports scoped menus: Admin vs Default users.

Run: python scripts/set_commands.py
"""

import os
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    from dotenv import load_dotenv
    load_dotenv()
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ─── Admin commands ───────────────────────────────────────────
ADMIN_COMMANDS = [
    {"command": "start", "description": "📋 Menu chính"},
    {"command": "status", "description": "📊 Tổng quan license"},
    {"command": "list", "description": "📋 Danh sách license"},
    {"command": "health", "description": "🏥 Kiểm tra kết nối"},
    {"command": "pending", "description": "📬 Chờ duyệt"},
    {"command": "lookup", "description": "🔍 Tra cứu MID"},
    {"command": "create", "description": "🔑 Tạo key mới"},
    {"command": "approve", "description": "✅ Duyệt nâng cấp"},
    {"command": "reject", "description": "❌ Từ chối nâng cấp"},
    {"command": "extend", "description": "⏱️ Gia hạn license"},
    {"command": "revoke", "description": "🔴 Thu hồi key"},
    {"command": "linkseller", "description": "🔗 Liên kết seller"},
    {"command": "config", "description": "⚙️ Cài đặt"},
    {"command": "pricing", "description": "💰 Bảng giá"},
    {"command": "sync", "description": "🔄 Sync"},
]

# ─── Seller commands ──────────────────────────────────────────
SELLER_COMMANDS = [
    {"command": "start", "description": "🏠 Menu"},
    {"command": "status", "description": "📊 Tổng quan"},
    {"command": "list", "description": "📋 Danh sách"},
    {"command": "pending", "description": "📬 Chờ duyệt"},
    {"command": "approve", "description": "✅ Duyệt nâng cấp"},
    {"command": "sell", "description": "🔑 Tạo key mới"},
    {"command": "mykeys", "description": "📋 Key đã tạo"},
    {"command": "lookup", "description": "🔍 Tra cứu MID"},
    {"command": "revoke", "description": "🔴 Thu hồi key"},
]

# ─── Default (unregistered users) ─────────────────────────────
DEFAULT_COMMANDS = [
    {"command": "start", "description": "Bắt đầu"},
]


def set_commands():
    """Register command menus via Telegram Bot API."""
    
    # 1. Set default commands (all users)
    r = requests.post(f"{API}/setMyCommands", json={
        "commands": DEFAULT_COMMANDS,
        "scope": {"type": "default"},
    })
    print(f"[Default] {r.json()}")

    # 2. Set admin commands (specific admin IDs)
    admin_ids = os.environ.get("TELEGRAM_ADMIN_IDS", "").strip()
    for aid in admin_ids.split(","):
        aid = aid.strip()
        if aid.isdigit():
            r = requests.post(f"{API}/setMyCommands", json={
                "commands": ADMIN_COMMANDS,
                "scope": {"type": "chat", "chat_id": int(aid)},
            })
            print(f"[Admin {aid}] {r.json()}")

    # 3. Set all-chats commands (fallback for sellers)
    r = requests.post(f"{API}/setMyCommands", json={
        "commands": SELLER_COMMANDS,
        "scope": {"type": "all_private_chats"},
    })
    print(f"[Private chats] {r.json()}")

    print("\n✅ Done! Commands registered.")
    print(f"\nAdmin commands: {len(ADMIN_COMMANDS)}")
    print(f"Seller commands: {len(SELLER_COMMANDS)}")
    print(f"Default commands: {len(DEFAULT_COMMANDS)}")


if __name__ == "__main__":
    set_commands()
