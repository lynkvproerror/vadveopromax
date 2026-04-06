"""
Real-time Notification Endpoint
================================
Client app calls this when a new upgrade request is submitted.
Triggers instant Telegram alert to admin.

Route: POST /api/notify/new_request
Body: {"mid": "...", "client_name": "...", "tier_requested": "...", "request_id": "..."}
Header: X-Notify-Key: <FIREBASE_PRIMARY_API_KEY> (lightweight auth)
"""

import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veo.api.notify")


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            # Auth — prefer dedicated NOTIFY_SECRET, fallback to API key
            notify_key = self.headers.get("X-Notify-Key", "").strip()
            expected = (
                os.environ.get("NOTIFY_SECRET", "").strip()
                or os.environ.get("FIREBASE_PRIMARY_API_KEY", "").strip()
            )
            if not expected or notify_key != expected:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"error":"forbidden"}')
                return

            # Read body
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}

            mid = body.get("mid", "unknown")
            client_name = body.get("client_name", "")
            tier = body.get("tier_requested", "")
            request_id = body.get("request_id", mid)

            # Send Telegram alert to all admins
            from bot.handlers import _send, _request_buttons
            from bot import security, formatters

            admin_ids = security.get_admin_ids()
            masked_mid = formatters.mask_mid(mid) if len(mid) > 4 else mid

            text = (
                "🔔 *REQUEST MỚI!*\n\n"
                f"🖥️ MID: `{masked_mid}`\n"
                + (f"👤 Tên: {client_name}\n" if client_name else "")
                + (f"📦 Gói yêu cầu: {tier}\n" if tier else "")
                + f"⏰ {formatters.fmt_date(None)}\n"
            )

            buttons = _request_buttons(mid, request_id, tier)

            for admin_id in admin_ids:
                _send(admin_id, text, reply_markup=buttons)

            log.info(f"[NOTIFY] Alert sent for MID {mid[:8]}... to {len(admin_ids)} admin(s)")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "alerted": len(admin_ids)}).encode())

        except Exception as e:
            log.error(f"[NOTIFY] Error: {e}", exc_info=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"internal_error"}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok","service":"notify"}')

    def log_message(self, format, *args):
        log.info(format % args)
