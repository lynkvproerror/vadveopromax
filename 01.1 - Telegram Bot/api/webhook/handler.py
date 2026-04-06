"""
Vercel Webhook Handler
======================
Entry point for Telegram webhook calls on Vercel.
Route: /api/webhook/<secret>
Security: URL path contains secret (no header check needed).
"""

import json
import logging
import sys
import os

# Add parent dir to path for bot imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from http.server import BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("veo.api.webhook")


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler."""

    def do_POST(self):
        try:
            # ── Verify Telegram origin ──
            secret = os.environ.get("WEBHOOK_SECRET", "").strip()
            if secret:
                header_secret = self.headers.get(
                    "X-Telegram-Bot-Api-Secret-Token", ""
                ).strip()
                if header_secret != secret:
                    log.warning("[WEBHOOK] ⛔ Invalid secret token — rejecting")
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b'{"error":"forbidden"}')
                    return

            # Read body
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            if not body:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true,"result":"empty_body"}')
                return

            update = json.loads(body)

            # Lazy import to catch import errors clearly
            from bot.handlers import dispatch
            result = dispatch(update)
            log.info(f"[WEBHOOK] Processed: {result}")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "result": result}).encode())

        except Exception as e:
            log.error(f"[WEBHOOK] Error: {e}", exc_info=True)
            self.send_response(200)  # Always 200 to avoid Telegram retries
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"internal_error"}')

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok","service":"veo-license-bot"}')

    def log_message(self, format, *args):
        """Override to use Python logging instead of stderr."""
        log.info(format % args)
