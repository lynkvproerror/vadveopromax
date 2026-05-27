from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from cloakbrowser import launch


ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "logs"
DEFAULT_URL = "https://labs.google/fx/tools/flow"
INTERESTING_HOST_TOKENS = (
    "labs.google",
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "flow-content.google",
)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    base = f"{parts.scheme}://{parts.netloc}{parts.path}"
    if parts.fragment:
        return f"{base}#..."
    return base


def is_interesting_url(url: str) -> bool:
    value = (url or "").lower()
    return any(token in value for token in INTERESTING_HOST_TOKENS)


class MonitorLogger:
    def __init__(self, path: Path):
        self.path = path
        self._fp = path.open("a", encoding="utf-8", buffering=1)

    def log(self, message: str) -> None:
        line = f"[{now_text()}] {message}"
        print(line)
        self._fp.write(line + "\n")

    def close(self) -> None:
        try:
            self._fp.close()
        except Exception:
            pass


def attach_page_events(page, logger: MonitorLogger) -> None:
    page_id = id(page)
    attached = getattr(page, "_cloak_monitor_attached", False)
    if attached:
        return
    setattr(page, "_cloak_monitor_attached", True)

    def on_domcontentloaded():
        logger.log(f"[Page {page_id}] domcontentloaded url={sanitize_url(page.url)}")

    def on_load():
        logger.log(f"[Page {page_id}] load url={sanitize_url(page.url)}")

    def on_console(msg):
        try:
            text = msg.text
        except Exception:
            text = "<unreadable console message>"
        logger.log(f"[Page {page_id}] console[{msg.type}] {text[:500]}")

    def on_page_error(exc):
        logger.log(f"[Page {page_id}] pageerror {exc}")

    def on_request(req):
        try:
            url = req.url
            if not is_interesting_url(url):
                return
            logger.log(
                f"[Page {page_id}] -> {req.method} {sanitize_url(url)} "
                f"type={req.resource_type}"
            )
        except Exception as exc:
            logger.log(f"[Page {page_id}] request-hook error {exc}")

    def on_response(resp):
        try:
            url = resp.url
            if not is_interesting_url(url):
                return
            logger.log(
                f"[Page {page_id}] <- {resp.status} {sanitize_url(url)} "
                f"type={resp.request.resource_type}"
            )
        except Exception as exc:
            logger.log(f"[Page {page_id}] response-hook error {exc}")

    def on_request_failed(req):
        try:
            url = req.url
            if not is_interesting_url(url):
                return
            failure = req.failure
            failure_text = ""
            if failure:
                failure_text = failure.get("errorText", "")
            logger.log(
                f"[Page {page_id}] FAILED {req.method} {sanitize_url(url)} "
                f"type={req.resource_type} error={failure_text}"
            )
        except Exception as exc:
            logger.log(f"[Page {page_id}] requestfailed-hook error {exc}")

    def on_framenavigated(frame):
        if frame.parent_frame is not None:
            return
        logger.log(f"[Page {page_id}] navigated url={sanitize_url(frame.url)}")

    page.on("domcontentloaded", on_domcontentloaded)
    page.on("load", on_load)
    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)
    page.on("framenavigated", on_framenavigated)
    logger.log(f"[Page {page_id}] attached current_url={sanitize_url(page.url)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch CloakBrowser headed and log safe realtime diagnostics."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Initial URL to open.")
    parser.add_argument(
        "--humanize",
        action="store_true",
        help="Enable CloakBrowser humanize mode.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"cloakbrowser_live_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logger = MonitorLogger(log_path)
    logger.log("Starting CloakBrowser live monitor")
    logger.log(f"Log file: {log_path}")
    logger.log("Sensitive headers, cookies, auth tokens, and request bodies are intentionally not logged")

    browser = None
    context = None
    try:
        launch_kwargs = {
            "headless": False,
        }
        if args.humanize:
            launch_kwargs["humanize"] = True
        browser = launch(**launch_kwargs)
        logger.log("CloakBrowser launch OK")
        context = browser.new_context()
        logger.log("Browser context created")

        def on_new_page(page):
            logger.log(f"[Context] new page url={sanitize_url(page.url)}")
            attach_page_events(page, logger)

        context.on("page", on_new_page)
        page = context.new_page()
        attach_page_events(page, logger)
        logger.log(f"Navigating to {sanitize_url(args.url)}")
        page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
        logger.log("Navigation started; interact with the browser window directly")
        logger.log("Press Ctrl+C in this console window or close all pages to stop the monitor")

        while True:
            pages = list(context.pages)
            if not pages:
                logger.log("No pages remain; stopping monitor")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.log("Interrupted by user")
    except Exception as exc:
        logger.log(f"Monitor crashed: {exc}")
        return 1
    finally:
        try:
            if context is not None:
                context.close()
        except Exception as exc:
            logger.log(f"context close error: {exc}")
        try:
            if browser is not None:
                browser.close()
        except Exception as exc:
            logger.log(f"browser close error: {exc}")
        logger.log("Monitor stopped")
        logger.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
