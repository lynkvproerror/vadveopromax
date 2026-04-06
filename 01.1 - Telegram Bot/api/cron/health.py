"""
Cron: Health Check (Keep-Alive)
================================
Public endpoint — no secret required.
Returns 200 OK always. Used by external cron services
to prevent Vercel from disabling the project.

Route: /api/cron/health
"""

import json
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "ok": True,
            "service": "veo-license-bot",
            "status": "alive",
        }).encode())

    def do_POST(self):
        self.do_GET()

    def log_message(self, format, *args):
        pass  # Suppress logs for health checks
