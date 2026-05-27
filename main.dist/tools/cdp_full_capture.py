"""
CDP Full Traffic Capture — captures ALL headers including Authorization.

Usage:
  1. Make sure Chrome is running with --remote-debugging-port=9222
     (VEO Pro Max already does this)
  2. Run:  python tools/cdp_full_capture.py
  3. Perform actions on labs.google (submit, poll, download, etc.)
  4. Press Ctrl+C to stop — saves full_capture_YYYY-MM-DD_HHmmss.json

Output includes:
  - Authorization: Bearer ya29... (NOT stripped like HAR export)
  - Cookie headers
  - x-client-data, x-browser-validation (auto-injected by Chrome)
  - Request/response bodies
"""

import asyncio
import json
import time
import sys
from datetime import datetime
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets

try:
    import aiohttp
except ImportError:
    print("Installing aiohttp...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "aiohttp"])
    import aiohttp

CDP_PORT = 9222
FILTER_DOMAINS = ["aisandbox-pa.googleapis.com", "labs.google"]


class CDPFullCapture:
    def __init__(self):
        self.entries = []
        self._pending = {}       # requestId -> entry
        self._extra_info = {}    # requestId -> extra headers
        self._response_bodies = {}

    async def capture(self, duration_seconds=600):
        """Capture traffic, printing live and collecting entries."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:{CDP_PORT}/json") as resp:
                pages = await resp.json()

        if not pages:
            print("❌ No browser pages found. Is Chrome running with --remote-debugging-port?")
            return

        # Pick labs.google page preferentially
        target = None
        for p in pages:
            url = p.get("url", "")
            if "labs.google" in url:
                target = p
                break
        if not target:
            target = pages[0]

        ws_url = target["webSocketDebuggerUrl"]
        print(f"✅ Connected: {target['url'][:80]}")
        print(f"⏱  Capturing for up to {duration_seconds}s — press Ctrl+C to stop early\n")

        msg_id = 0

        async with websockets.connect(ws_url, max_size=100 * 1024 * 1024) as ws:
            # Enable Network domain with full request interception
            msg_id += 1
            await ws.send(json.dumps({
                "id": msg_id,
                "method": "Network.enable",
                "params": {"maxPostDataSize": 65536}
            }))
            await ws.recv()

            start = time.time()
            count = 0

            try:
                while time.time() - start < duration_seconds:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    data = json.loads(raw)
                    method = data.get("method", "")
                    params = data.get("params", {})

                    if method == "Network.requestWillBeSent":
                        self._handle_request(params)

                    elif method == "Network.requestWillBeSentExtraInfo":
                        # Raw network-level headers (after Chrome auto-injection)
                        rid = params.get("requestId", "")
                        self._extra_info[rid] = params.get("headers", {})
                        # Merge into pending entry if exists
                        if rid in self._pending:
                            self._pending[rid]["_extraHeaders"] = params.get("headers", {})

                    elif method == "Network.responseReceived":
                        self._handle_response(params)
                        count += 1

                    elif method == "Network.loadingFinished":
                        rid = params.get("requestId", "")
                        if rid in self._pending:
                            # Try to get response body
                            try:
                                msg_id += 1
                                await ws.send(json.dumps({
                                    "id": msg_id,
                                    "method": "Network.getResponseBody",
                                    "params": {"requestId": rid}
                                }))
                                body_resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                                body_data = json.loads(body_resp)
                                if "result" in body_data:
                                    body_text = body_data["result"].get("body", "")
                                    if rid in self._pending:
                                        self._pending[rid]["_responseBody"] = body_text[:5000]
                            except Exception:
                                pass

                            # Finalize entry
                            entry = self._pending.pop(rid, None)
                            if entry:
                                self.entries.append(entry)

            except KeyboardInterrupt:
                print("\n\n⏹  Capture stopped by user.")

            # Flush remaining pending entries
            for rid, entry in self._pending.items():
                self.entries.append(entry)
            self._pending.clear()

            # Disable Network
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": "Network.disable", "params": {}}))

        print(f"\n📊 Captured {len(self.entries)} entries")

    def _handle_request(self, params):
        req = params.get("request", {})
        url = req.get("url", "")

        if not any(d in url for d in FILTER_DOMAINS):
            return

        rid = params.get("requestId", "")
        headers = req.get("headers", {})

        entry = {
            "startedDateTime": datetime.utcnow().isoformat() + "Z",
            "requestId": rid,
            "request": {
                "method": req.get("method", ""),
                "url": url,
                "headers": headers,
                "postData": req.get("postData", ""),
            },
            "response": {},
        }

        # Merge extra info if already received
        if rid in self._extra_info:
            entry["_extraHeaders"] = self._extra_info.pop(rid)

        self._pending[rid] = entry

        # Live print
        auth = headers.get("Authorization", headers.get("authorization", "NONE"))
        if auth != "NONE":
            auth_display = auth[:20] + "..." + auth[-10:] if len(auth) > 35 else auth
        else:
            auth_display = "NONE"

        xcd = headers.get("x-client-data", "—")[:30]
        xbv = headers.get("x-browser-validation", "—")[:30]
        short_url = url.split("?")[0].split("/")[-1][:50]

        print(f"  🔵 {req.get('method', '?'):5} {short_url:50} Auth={auth_display}")
        if xcd != "—" or xbv != "—":
            print(f"       XCD={xcd}  XBV={xbv}")

    def _handle_response(self, params):
        rid = params.get("requestId", "")
        if rid not in self._pending:
            return

        resp = params.get("response", {})
        self._pending[rid]["response"] = {
            "status": resp.get("status", 0),
            "statusText": resp.get("statusText", ""),
            "headers": resp.get("headers", {}),
        }

        url = resp.get("url", self._pending[rid]["request"]["url"])
        status = resp.get("status", 0)
        short_url = url.split("?")[0].split("/")[-1][:50]

        emoji = "✅" if 200 <= status < 300 else ("↗️" if status == 307 else "❌")
        print(f"  {emoji} {status} {short_url}")

    def save(self, filepath=None):
        """Save captured entries as JSON with full headers."""
        if not filepath:
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            filepath = f"full_capture_{ts}.json"

        # Build clean output
        output = {
            "captureInfo": {
                "tool": "CDP Full Capture",
                "capturedAt": datetime.utcnow().isoformat() + "Z",
                "entryCount": len(self.entries),
                "note": "Authorization headers are INCLUDED (not stripped like HAR export)",
            },
            "entries": [],
        }

        for e in self.entries:
            clean = {
                "startedDateTime": e.get("startedDateTime", ""),
                "request": {
                    "method": e["request"]["method"],
                    "url": e["request"]["url"],
                    "headers": e["request"]["headers"],
                },
                "response": {
                    "status": e.get("response", {}).get("status", 0),
                    "statusText": e.get("response", {}).get("statusText", ""),
                    "headers": e.get("response", {}).get("headers", {}),
                },
            }

            # Include postData if present
            post_data = e["request"].get("postData", "")
            if post_data:
                clean["request"]["postData"] = post_data

            # Include extra headers (network-level, after Chrome injection)
            if "_extraHeaders" in e:
                clean["request"]["networkLevelHeaders"] = e["_extraHeaders"]

            # Include response body if captured
            if "_responseBody" in e:
                clean["response"]["body"] = e["_responseBody"]

            output["entries"].append(clean)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Saved {len(self.entries)} entries → {filepath}")

        # Print summary
        auth_count = sum(
            1 for e in self.entries
            if e["request"]["headers"].get("Authorization")
            or e["request"]["headers"].get("authorization")
        )
        print(f"   Entries with Authorization: {auth_count}/{len(self.entries)}")

        return filepath


async def main():
    capture = CDPFullCapture()
    await capture.capture(duration_seconds=600)  # 10 minutes max
    if capture.entries:
        capture.save()
    else:
        print("No entries captured.")


if __name__ == "__main__":
    print("=" * 60)
    print("CDP Full Traffic Capture")
    print("Captures ALL headers including Authorization")
    print("=" * 60)
    print()
    asyncio.run(main())
