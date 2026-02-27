"""
Structured Account Logger — Auto-tagging + per-account log files.

Intercepts existing log messages from core.engine, core.extension_bridge, etc.
and automatically:
1. Detects which account the message belongs to (from email patterns)
2. Tags the message with an activity type ([SUBMIT], [POLL], [DL720], etc.)
3. Routes to a per-account log file in logs/accounts/

Tags:
  [SUBMIT]  - API submit (prompt or upscale request)
  [POLL]    - Operation polling (status checks)
  [DL720]   - Download 720p video
  [UPSCL]   - Upscale request/status
  [DL4K]    - Download upscaled video
  [WS]      - WebSocket / Extension Bridge protocol
  [RECAP]   - reCAPTCHA token operations
  [FOREMN]  - Foreman lifecycle (pick, dispatch, retry)
  [COOL]    - Cooldown / recovery
  [ENGINE]  - General engine events

Usage:
    from core.account_logger import install_account_logging
    install_account_logging()  # Call once at startup
"""

import logging
import re
import os
from pathlib import Path
from datetime import datetime

# ── Tag detection patterns ──────────────────────────────────────────
# Order matters: first match wins. Most specific patterns first.
_TAG_PATTERNS = [
    # Submit
    ("SUBMIT", re.compile(
        r"submit|Submitted|📦 Request body|body summary|"
        r"submit_prompt|result\.success|operation_name|"
        r"adaptive delay.*submit attempt|Slot #\d|ops →",
        re.IGNORECASE,
    )),
    # Upscale
    ("UPSCL", re.compile(
        r"[Uu]pscale|upsampled|submit_upscale|UpscaleQueue|"
        r"Upscale \d+/\d+",
    )),
    # Download 4K/1080p (check before 720p)
    ("DL4K", re.compile(
        r"Downloaded.*(1080p|4[kK]|upscaled)|download.*final|"
        r"file_final",
    )),
    # Download 720p
    ("DL720", re.compile(
        r"Downloaded.*720p|download|Downloaded:|SUCCESSFUL",
    )),
    # Polling
    ("POLL", re.compile(
        r"MEDIA_GENERATION_STATUS|PENDING|ACTIVE|poll|"
        r"\[Worker:.*#\d\]|ops\[\d\]",
    )),
    # Cooldown
    ("COOL", re.compile(
        r"[Cc]ooldown|consecutive|Recovery|Phase \d|"
        r"escalat|backed off|circuit.?breaker|ABORT",
    )),
    # reCAPTCHA
    ("RECAP", re.compile(
        r"reCAPTCHA|recaptcha|grecaptcha|token.*\d+ chars|"
        r"403.*Forbidden|403.*evaluation|tokenLength|"
        r"pre-?warm",
    )),
    # WebSocket
    ("WS", re.compile(
        r"websocket|ExtensionBridge|headers_update|"
        r"content_heartbeat|simulate_activity|"
        r"keepalive|ping|pong",
        re.IGNORECASE,
    )),
    # Foreman
    ("FOREMN", re.compile(
        r"[Ff]oreman|Picked task|Supervisor|foreman-|"
        r"Spawned|Stagger|startup done|clearance|"
        r"requeueing|requeue",
    )),
]

# Email extraction pattern
_EMAIL_RE = re.compile(
    r'[\w.+-]+@[\w.-]+\.\w+'
)

# ── Per-account file handlers ───────────────────────────────────────
_account_handlers: dict[str, logging.FileHandler] = {}
_log_dir: Path | None = None
_installed = False


def _get_log_dir() -> Path:
    global _log_dir
    if _log_dir is None:
        _log_dir = Path(__file__).parent.parent / "logs" / "accounts"
        _log_dir.mkdir(parents=True, exist_ok=True)
    return _log_dir


def _short_email(email: str) -> str:
    return email.split("@")[0][:12]


def _detect_tag(message: str) -> str:
    """Detect activity tag from log message content."""
    for tag, pattern in _TAG_PATTERNS:
        if pattern.search(message):
            return tag
    return "ENGINE"


def _extract_email(message: str) -> str | None:
    """Extract email address from log message."""
    m = _EMAIL_RE.search(message)
    return m.group(0) if m else None


def _get_account_handler(email: str) -> logging.FileHandler:
    """Get or create file handler for an account."""
    if email in _account_handlers:
        return _account_handlers[email]
    
    log_dir = _get_log_dir()
    safe_name = email.replace("@", "_at_").replace(".", "_")
    filepath = log_dir / f"{safe_name}.log"
    
    handler = logging.FileHandler(filepath, encoding="utf-8", mode="a")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    _account_handlers[email] = handler
    
    # Session separator
    handler.stream.write(
        f"\n{'='*70}\n"
        f"  Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"  Account: {email}\n"
        f"{'='*70}\n\n"
    )
    handler.stream.flush()
    
    return handler


class AccountLogInterceptor(logging.Handler):
    """Intercepts log records, adds tags, routes to per-account files.
    
    Attached to root logger or specific loggers (core.engine, etc.)
    Does NOT affect console output — just adds per-account file routing.
    """
    
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] [%(tag)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
    
    def emit(self, record: logging.LogRecord):
        try:
            msg = record.getMessage()
            email = _extract_email(msg)
            if not email:
                return  # No account context → skip
            
            tag = _detect_tag(msg)
            
            # Write to per-account file
            handler = _get_account_handler(email)
            
            # Create a modified record with tag
            tagged_record = logging.LogRecord(
                name=record.name,
                level=record.levelno,
                pathname=record.pathname,
                lineno=record.lineno,
                msg=f"[{tag:<6s}] {msg}",
                args=(),
                exc_info=record.exc_info,
            )
            handler.emit(tagged_record)
        except Exception:
            pass  # Never crash the app due to logging


def install_account_logging():
    """Install the account log interceptor. Call once at startup.
    
    Attaches to core.engine, core.extension_bridge, core.api_client loggers
    to intercept their messages and route to per-account files.
    """
    global _installed
    if _installed:
        return
    _installed = True
    
    interceptor = AccountLogInterceptor()
    
    # Attach to key loggers
    for logger_name in [
        "core.engine",
        "core.extension_bridge",
        "core.api_client",
        "core.account_manager",
        "core.adaptive_burst",
        "core.recaptcha_pool",
        "core.app_controller",
        "core.dispatcher",
    ]:
        logging.getLogger(logger_name).addHandler(interceptor)
    
    logging.getLogger("core.engine").info(
        "[AccountLogger] Per-account logging installed → logs/accounts/"
    )


def cleanup_account_logging():
    """Close all per-account file handlers. Call on shutdown."""
    for email, handler in _account_handlers.items():
        try:
            handler.close()
        except Exception:
            pass
    _account_handlers.clear()
