"""
Cron: Check Pending Requests
==============================
Called by cron-job.org every 5 minutes.
Sends Telegram notification if new pending requests exist.
Route: /api/cron/check_pending
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from http.server import BaseHTTPRequestHandler

import requests

from bot.firebase_ops import FirebaseOps
from bot.security import verify_cron_secret
from bot import formatters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veo.api.cron")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = os.environ.get("TELEGRAM_ADMIN_IDS", "")
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Track already-notified requests (in-memory, resets on cold start)
_notified: set = set()


def _send_to_admins(text: str, reply_markup: dict = None):
    """Send message to all admin IDs."""
    for admin_id in ADMIN_IDS.split(","):
        admin_id = admin_id.strip()
        if not admin_id.isdigit():
            continue
        payload = {
            "chat_id": int(admin_id),
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            requests.post(f"{TG_API}/sendMessage", json=payload, timeout=10)
        except Exception as e:
            log.warning(f"[CRON] Send to {admin_id} failed: {e}")


def _request_buttons(mid: str, request_id: str, tier: str = "") -> dict:
    """Build inline buttons for request notification.

    NOTE: Telegram limits callback_data to 64 bytes.
    MID and request_id are truncated to 16 chars (prefix matching in webhook handler).
    """
    m = mid[:16]
    r = request_id[:16]
    if tier.upper() in ("TRIAL", "FREE", "TRIA", "12H", "1D"):
        # Trial: direct approve (no payment needed)
        return {
            "inline_keyboard": [
                [
                    {"text": "✅ Duyệt Trial", "callback_data": f"approve:{m}:{r}:TRIA:3"},
                    {"text": "❌ Từ chối", "callback_data": f"reject:{m}:{r}"},
                ],
                [
                    {"text": "🚫 Block", "callback_data": f"action:block:{m}"},
                    {"text": "🔍 Xem chi tiết", "callback_data": f"lookup:{m}"},
                ],
            ]
        }
    else:
        # Paid tier: tier picker
        return {
            "inline_keyboard": [
                [
                    {"text": "💰 Chọn gói", "callback_data": f"pick_tier:{m}:{r}"},
                    {"text": "❌ Từ chối", "callback_data": f"reject:{m}:{r}"},
                ],
                [
                    {"text": "🚫 Block", "callback_data": f"action:block:{m}"},
                    {"text": "🔍 Xem chi tiết", "callback_data": f"lookup:{m}"},
                ],
            ]
        }


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            # Verify cron secret
            if not verify_cron_secret(dict(self.headers)):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"error":"forbidden"}')
                return

            ops = FirebaseOps()
            pending = ops.get_pending_requests()

            new_count = 0
            for req in pending:
                req_id = req.get("_doc_id", "")
                if req_id in _notified:
                    continue

                mid = req.get("machine_id") or req_id
                tier = req.get("tier", "") or req.get("tier_requested", "")
                text = formatters.fmt_request(req)
                buttons = _request_buttons(mid, req_id, tier)
                _send_to_admins(text, buttons)
                _notified.add(req_id)
                new_count += 1

            # Cleanup old notified (prevent memory leak)
            if len(_notified) > 200:
                _notified.clear()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "pending_total": len(pending),
                "new_notified": new_count,
            }).encode())

        except Exception as e:
            log.error(f"[CRON] Error: {e}", exc_info=True)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())

    def do_POST(self):
        """Also accept POST from some cron services."""
        self.do_GET()

    def log_message(self, format, *args):
        log.info(format % args)
