"""
VEO Pro Max - Queue Log Translator

Subscribes to EventManager events and translates raw technical messages
into user-friendly Vietnamese console log entries for the Queue tab.

Architecture:
- Listens to EventManager events (pub/sub, no interference with existing callbacks)
- Pattern-matches raw messages → maps to simple Vietnamese wording
- Anti-spam: deduplicates identical messages within a 3s window
- Anti-spam: coalesces upscale progress into milestone updates only
- Emits translated entries via Qt Signal → ConsoleLogWidget

Reference: plan_queue_console_log_panel_20260413.md
"""

import re
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Callable

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


# ── Log Entry ────────────────────────────────────────────────

@dataclass
class ConsoleLogEntry:
    """A single console log entry for the Queue UI."""
    timestamp: str          # "11:33:21"
    category: str           # "Browser", "XCD", "Submit Prompt", ...
    level: str              # "info", "success", "warning", "error"
    user_message: str       # Vietnamese user-facing text
    raw_message: str = ""   # Original technical message for debug


# ── Category Constants ───────────────────────────────────────

CAT_BROWSER = "Browser"
CAT_EXTENSION = "Extension"
CAT_XCD = "XCD"
CAT_TOKEN = "Token"
CAT_RECAPTCHA = "reCAPTCHA"
CAT_SUBMIT = "Submit"
CAT_UPSCALE = "Upscale"
CAT_DOWNLOAD = "Download"
CAT_ERROR = "Lỗi"
CAT_QUEUE = "Queue"
CAT_ACCOUNT = "Account"

# ── Level Constants ──────────────────────────────────────────

LVL_INFO = "info"
LVL_SUCCESS = "success"
LVL_WARNING = "warning"
LVL_ERROR = "error"


# ── Pattern Rules ────────────────────────────────────────────
# Each rule: (pattern_regex, category, level, user_message_template)
# {0} = first capture group, {task_id} = task_id from event data, etc.

_TRANSLATION_RULES: List[tuple] = [
    # ── Browser ──
    (r"browser.*launch", CAT_BROWSER, LVL_INFO, "Trình duyệt đã mở"),
    (r"browser.*connect", CAT_BROWSER, LVL_SUCCESS, "Trình duyệt đã kết nối"),
    (r"browser.*disconnect", CAT_BROWSER, LVL_WARNING, "Trình duyệt bị ngắt kết nối"),
    (r"tab.*reload", CAT_BROWSER, LVL_INFO, "Trình duyệt đang tải lại"),
    (r"browser.*recover", CAT_BROWSER, LVL_SUCCESS, "Trình duyệt đã khôi phục"),

    # ── Extension ──
    (r"extension.*connect", CAT_EXTENSION, LVL_SUCCESS, "Extension đã kết nối"),
    (r"extension.*register", CAT_EXTENSION, LVL_SUCCESS, "Extension đã sẵn sàng"),
    (r"extension.*disconnect", CAT_EXTENSION, LVL_WARNING, "Extension bị ngắt kết nối"),
    (r"bridge.*connect", CAT_EXTENSION, LVL_SUCCESS, "App đã kết nối với Extension"),
    (r"no.*extension|extension.*not.*found", CAT_EXTENSION, LVL_ERROR, "Chưa kết nối được Extension"),

    # ── XCD ──
    (r"x-client-data.*ready|xcd.*ready|x-client-data.*valid", CAT_XCD, LVL_SUCCESS, "Đã sẵn sàng"),
    (r"x-client-data.*short|xcd.*short|x-client-data.*missing|xcd.*missing", CAT_XCD, LVL_WARNING, "Chưa sẵn sàng"),

    # ── Token ──
    (r"access.?token.*ready|token.*valid", CAT_TOKEN, LVL_SUCCESS, "Đã sẵn sàng"),
    (r"token.*short|token.*invalid|token.*missing", CAT_TOKEN, LVL_WARNING, "Chưa đủ điều kiện"),

    # ── reCAPTCHA ──
    (r"recaptcha.*ready|grecaptcha.*ready", CAT_RECAPTCHA, LVL_SUCCESS, "Đã sẵn sàng"),
    (r"recaptcha.*not.*ready|recaptcha.*unhealthy", CAT_RECAPTCHA, LVL_WARNING, "Chưa sẵn sàng"),
    (r"short.*token|recaptcha.*short", CAT_RECAPTCHA, LVL_WARNING, "Chưa đủ điều kiện"),

    # ── User Actions (retry, delete, clean) ──
    (r"retry failed tasks (\d+)", CAT_QUEUE, LVL_INFO, "Đang thử lại {0} tác vụ lỗi"),
    (r"retry failed videos (\d+)", CAT_QUEUE, LVL_INFO, "Đang thử lại {0} video lỗi"),
    (r"delete all groups (\d+)", CAT_QUEUE, LVL_WARNING, "Đã xoá {0} nhóm tác vụ"),
    (r"clean completed (\d+)", CAT_QUEUE, LVL_INFO, "Đã dọn {0} tác vụ hoàn tất"),
    (r"auto retry submitted (\d+)", CAT_QUEUE, LVL_INFO, "Tự động thử lại {0} video lỗi"),

    # ── Submit ──
    (r"submit.*prompt.*success|prompt.*submitted", CAT_SUBMIT, LVL_SUCCESS, "Prompt = Thành công"),
    (r"submit.*prompt.*fail", CAT_SUBMIT, LVL_ERROR, "Prompt = Thất bại"),
    (r"submit.*upscale.*success|upscale.*submitted", CAT_SUBMIT, LVL_SUCCESS, "Upscale = Thành công"),
    (r"submit.*upscale.*fail", CAT_SUBMIT, LVL_ERROR, "Upscale = Thất bại"),
    (r"request.*queued|queued.*for.*processing", CAT_QUEUE, LVL_INFO, "Yêu cầu đã vào hàng đợi"),

    # ── Upscale progress ──
    (r"upscale.*enqueue", CAT_UPSCALE, LVL_INFO, "Đã vào hàng đợi upscale"),
    (r"upscal.+(\d+)/(\d+)", CAT_UPSCALE, LVL_INFO, "Đang xử lý {0}"),
    (r"upscale download complete", CAT_UPSCALE, LVL_SUCCESS, "Upscale hoàn tất — đã lưu"),
    (r"upscal.*complete|upscale.*success|upscaled.*to", CAT_UPSCALE, LVL_SUCCESS, "Hoàn tất"),
    (r"upscal.*paus|upscale.*recovery", CAT_UPSCALE, LVL_WARNING, "Tạm dừng để khôi phục"),
    (r"download.*upscal", CAT_DOWNLOAD, LVL_INFO, "Đang tải video đã upscale"),

    # ── Download ──
    (r"download.*720p.*complete|720p.*saved", CAT_DOWNLOAD, LVL_SUCCESS, "Video 720p đã lưu"),
    (r"download.*fail", CAT_DOWNLOAD, LVL_ERROR, "Tải xuống thất bại"),

    # ── Video generation errors (per-video, not per-task) ──
    (r"video generation failed.*HIGH_TRAFFIC", CAT_ERROR, LVL_WARNING, "Video lỗi: Server quá tải"),
    (r"video generation failed.*SAFETY", CAT_ERROR, LVL_WARNING, "Video lỗi: Vi phạm nội dung"),
    (r"video generation failed.*TIMEOUT|video generation failed.*timed?\s*out", CAT_ERROR, LVL_WARNING, "Video lỗi: Hết thời gian chờ"),
    (r"video generation failed", CAT_ERROR, LVL_WARNING, "Video lỗi: Tạo video thất bại"),

    # ── Errors ──
    (r"403|unauthorized", CAT_ERROR, LVL_ERROR, "Không thể gửi yêu cầu, vui lòng thử lại"),
    (r"missing.*header", CAT_ERROR, LVL_ERROR, "Trình duyệt chưa sẵn sàng"),
    (r"account.*paus.*recover|account.*recovery", CAT_ACCOUNT, LVL_WARNING, "Tài khoản đang được khôi phục"),
    (r"account.*unpaus|account.*resumed", CAT_ACCOUNT, LVL_SUCCESS, "Tài khoản đã khôi phục"),
]

# Pre-compile patterns
_COMPILED_RULES = [
    (re.compile(pattern, re.IGNORECASE), cat, lvl, msg)
    for pattern, cat, lvl, msg in _TRANSLATION_RULES
]


class QueueLogTranslator(QObject):
    """Translates raw technical events into user-friendly console log entries.
    
    Usage:
        translator = QueueLogTranslator()
        translator.log_entry_signal.connect(console_widget.append_entry)
        # Events from EventManager are auto-subscribed
    """
    
    # Signal: (timestamp, category, level, user_message)
    log_entry_signal = Signal(str, str, str, str)
    
    # Anti-spam settings
    DEDUPE_WINDOW_SEC = 3.0     # Suppress identical messages within this window
    MAX_ENTRIES_PER_SEC = 5     # Rate limit
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_messages: Dict[str, float] = {}  # "cat|msg" → timestamp
        self._rate_counter = 0
        self._rate_window_start = 0.0
        self._subscribed = False
        
        # Subscribe to EventManager
        self._subscribe_events()
    
    def _subscribe_events(self):
        """Subscribe to relevant EventManager event types."""
        try:
            from core.event_manager import get_event_manager, EventType
            em = get_event_manager()
            
            # Task lifecycle
            em.subscribe(EventType.TASK_SUBMITTED, self._on_event)
            em.subscribe(EventType.TASK_STARTED, self._on_event)
            em.subscribe(EventType.TASK_COMPLETED, self._on_event)
            em.subscribe(EventType.TASK_FAILED, self._on_event)
            
            # Queue lifecycle
            em.subscribe(EventType.QUEUE_STARTED, self._on_event)
            em.subscribe(EventType.QUEUE_STOPPED, self._on_event)
            
            # Engine errors (watchdog, recovery)
            em.subscribe(EventType.ENGINE_ERROR, self._on_event)
            
            # UI status updates (from backend emit points)
            em.subscribe(EventType.UI_STATUS_UPDATE, self._on_event)
            
            self._subscribed = True
            log.debug("[QueueLogTranslator] Subscribed to EventManager")
        except Exception as e:
            log.warning(f"[QueueLogTranslator] Could not subscribe: {e}")
    
    def _on_event(self, event):
        """Handle an incoming event from EventManager."""
        try:
            from core.event_manager import EventType
            data = event.data or {}
            
            # ── Direct translation for known event types ──
            
            if event.type == EventType.TASK_SUBMITTED:
                count = data.get('count', 1)
                self._emit_entry(CAT_QUEUE, LVL_INFO,
                    f"Đã thêm {count} tác vụ vào hàng đợi",
                    raw=f"task_submitted count={count}")
                return
            
            if event.type == EventType.TASK_COMPLETED:
                task_id = data.get('task_id', '')
                outputs = data.get('outputs', 0)
                # Only log if not a replacement task (avoid spam)
                if '_retry_' not in task_id:
                    short_id = task_id.split('_')[-1] if '_' in task_id else task_id[:8]
                    self._emit_entry(CAT_QUEUE, LVL_SUCCESS,
                        f"Tác vụ #{short_id} hoàn tất ({outputs} video)",
                        raw=f"task_completed {task_id}")
                return
            
            if event.type == EventType.TASK_FAILED:
                task_id = data.get('task_id', '')
                error = data.get('error', '')
                if '_retry_' not in task_id:
                    short_id = task_id.split('_')[-1] if '_' in task_id else task_id[:8]
                    # Simplify error message
                    user_error = self._simplify_error(error)
                    self._emit_entry(CAT_ERROR, LVL_ERROR,
                        f"Tác vụ #{short_id}: {user_error}",
                        raw=f"task_failed {task_id}: {error[:100]}")
                return
            
            if event.type == EventType.QUEUE_STARTED:
                self._emit_entry(CAT_QUEUE, LVL_INFO,
                    "Hàng đợi đã bắt đầu xử lý",
                    raw="queue_started")
                return
            
            if event.type == EventType.QUEUE_STOPPED:
                self._emit_entry(CAT_QUEUE, LVL_INFO,
                    "Hàng đợi đã dừng",
                    raw="queue_stopped")
                return
            
            if event.type == EventType.ENGINE_ERROR:
                error_type = data.get('type', '')
                detail = data.get('detail', '')
                if 'watchdog' in error_type:
                    self._emit_entry(CAT_QUEUE, LVL_WARNING,
                        "Phát hiện tác vụ bị treo, đang khôi phục",
                        raw=f"watchdog: {detail[:80]}")
                elif 'recovery' in error_type:
                    account = data.get('account', '')
                    short_acc = account.split('@')[0] if '@' in account else account[:8]
                    self._emit_entry(CAT_ACCOUNT, LVL_WARNING,
                        f"Tài khoản {short_acc} đang được khôi phục",
                        raw=f"recovery: {detail[:80]}")
                return
            
            # ── UI_STATUS_UPDATE: pattern-match the message ──
            if event.type == EventType.UI_STATUS_UPDATE:
                message = data.get('message', '')
                if message:
                    self._translate_raw_message(message, data)
                return
                
        except Exception as e:
            log.debug(f"[QueueLogTranslator] Event handler error: {e}")
    
    def _translate_raw_message(self, raw_message: str, data: dict = None):
        """Try to match raw_message against translation rules."""
        for pattern, category, level, template in _COMPILED_RULES:
            match = pattern.search(raw_message)
            if match:
                # Format template with capture groups
                user_msg = template
                if match.groups():
                    # For upscale progress like "2/4"
                    groups = match.groups()
                    if len(groups) >= 2:
                        user_msg = template.format(f"{groups[0]}/{groups[1]}")
                    elif len(groups) == 1:
                        user_msg = template.format(groups[0])
                
                # Append context from data dict (task label, prompt, video)
                if data:
                    ctx = self._build_context_suffix(data)
                    if ctx:
                        user_msg = f"{user_msg} {ctx}"
                
                self._emit_entry(category, level, user_msg, raw=raw_message[:120])
                return
        
        # No match — skip (don't pollute console with unmapped messages)
    
    def _build_context_suffix(self, data: dict) -> str:
        """Build a context string from data dict fields.
        
        Returns e.g.: '(#3, v2)'
        """
        parts = []
        task_label = data.get('task_label')
        if task_label:
            parts.append(task_label)
        video_label = data.get('video_label')
        if video_label:
            parts.append(video_label)
        return f"({', '.join(parts)})" if parts else ""
    
    def _simplify_error(self, error: str) -> str:
        """Simplify a technical error message for user display."""
        error_lower = error.lower()
        if '403' in error or 'unauthorized' in error_lower:
            return "Không thể gửi yêu cầu"
        if 'high_traffic' in error_lower or 'public_error' in error_lower:
            return "Server đang quá tải"
        if 'timeout' in error_lower:
            return "Hết thời gian chờ"
        if 'recaptcha' in error_lower:
            return "reCAPTCHA chưa sẵn sàng"
        if 'download' in error_lower:
            return "Tải xuống thất bại"
        if 'cancelled' in error_lower or 'stopped' in error_lower:
            return "Đã huỷ"
        # Truncate technical errors
        return error[:60] if len(error) > 60 else error
    
    def _emit_entry(self, category: str, level: str, user_message: str,
                    raw: str = ""):
        """Emit a log entry after anti-spam checks."""
        now = time.monotonic()
        
        # Anti-spam: dedupe identical messages within window
        dedup_key = f"{category}|{user_message}"
        last_time = self._last_messages.get(dedup_key, 0)
        if now - last_time < self.DEDUPE_WINDOW_SEC:
            return  # Suppress duplicate
        self._last_messages[dedup_key] = now
        
        # Anti-spam: rate limit
        if now - self._rate_window_start > 1.0:
            self._rate_counter = 0
            self._rate_window_start = now
        self._rate_counter += 1
        if self._rate_counter > self.MAX_ENTRIES_PER_SEC:
            return  # Rate limited
        
        # Clean old dedupe entries (prevent memory leak)
        if len(self._last_messages) > 200:
            cutoff = now - self.DEDUPE_WINDOW_SEC * 2
            self._last_messages = {
                k: v for k, v in self._last_messages.items()
                if v > cutoff
            }
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_entry_signal.emit(timestamp, category, level, user_message)
    
    # ── Public API for direct injection ──
    
    def inject(self, category: str, level: str, message: str):
        """Manually inject a log entry (for testing or direct calls)."""
        self._emit_entry(category, level, message, raw=f"injected: {message}")
