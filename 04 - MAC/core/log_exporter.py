"""
VEO Pro Max - Log Exporter

Auto-exports structured session logs when processing stops.
Only active for TESTER role accounts.

Features:
- Captures all Python log records via a custom logging.Handler
- Categorizes errors: DOWNLOAD_FAILURE, RECAPTCHA_FAILURE, UPSCALE_403, etc.
- Generates JSON report with summary stats + categorized errors
- Saves to logs/reports/session_{timestamp}.json
"""

import logging
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

log = logging.getLogger(__name__)


# ─── Error Categories ───────────────────────────────────────────────

class ErrorCategory:
    DOWNLOAD_FAILURE = "DOWNLOAD_FAILURE"
    RECAPTCHA_FAILURE = "RECAPTCHA_FAILURE"
    UPSCALE_403 = "UPSCALE_403"
    AUTH_ERROR = "AUTH_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    GENERAL_ERROR = "GENERAL_ERROR"


# ─── Pattern matchers for categorization ─────────────────────────────

_CATEGORY_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (ErrorCategory.DOWNLOAD_FAILURE, re.compile(
        r"Download FAILED|Download failed.*HTTP|Download partial|no local file.*download failed",
        re.IGNORECASE
    )),
    (ErrorCategory.RECAPTCHA_FAILURE, re.compile(
        r"reCAPTCHA.*timed out|reCAPTCHA.*failed|Token too short|"
        r"reCAPTCHA evaluation failed|reCAPTCHA.*expired.*refresh failed",
        re.IGNORECASE
    )),
    (ErrorCategory.UPSCALE_403, re.compile(
        r"upscale.*403|Upscale.*submit.*failed.*403|upscale.*reCAPTCHA.*failed",
        re.IGNORECASE
    )),
    (ErrorCategory.AUTH_ERROR, re.compile(
        r"HTTP 401|UNAUTHENTICATED|token expired|access token.*invalid",
        re.IGNORECASE
    )),
    (ErrorCategory.NETWORK_ERROR, re.compile(
        r"ConnectionError|TimeoutError|ConnectTimeout|network.*error|"
        r"Cannot connect|connection refused",
        re.IGNORECASE
    )),
]


def _categorize(message: str) -> Optional[str]:
    """Categorize a log message by error type."""
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(message):
            return category
    return None


# ─── Log Record Collector ──────────────────────────────────────────

@dataclass
class LogRecord:
    timestamp: str
    level: str
    logger: str
    message: str
    category: Optional[str] = None


class _ExporterHandler(logging.Handler):
    """Lightweight handler that stores log records for later export.
    
    Only captures WARNING/ERROR/CRITICAL to keep memory usage low.
    """
    
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: List[LogRecord] = []
        self._start_time: Optional[datetime] = None
    
    def emit(self, record: logging.LogRecord):
        if self._start_time is None:
            self._start_time = datetime.now()
        
        msg = self.format(record)
        category = _categorize(msg)
        
        self.records.append(LogRecord(
            timestamp=datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            level=record.levelname,
            logger=record.name,
            message=msg,
            category=category,
        ))
    
    def clear(self):
        self.records.clear()
        self._start_time = None


# ─── Log Exporter ──────────────────────────────────────────────────

class LogExporter:
    """Structured log exporter for TESTER accounts.
    
    Usage:
        exporter = LogExporter(base_dir=Path("logs"))
        exporter.start()   # attach to root logger
        # ... app runs ...
        exporter.export(dispatcher)  # generate JSON report
        exporter.stop()    # detach from root logger
    """
    
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir / "reports"
        self._handler = _ExporterHandler()
        self._handler.setFormatter(logging.Formatter(
            "[%(levelname)-5s] %(asctime)s - %(name)s - %(message)s",
            datefmt="%H:%M:%S",
        ))
        self._attached = False
    
    def start(self):
        """Attach to root logger to capture warnings/errors."""
        if not self._attached:
            logging.getLogger().addHandler(self._handler)
            self._attached = True
            self._handler.clear()
            log.info("[LogExporter] Started — capturing warnings/errors")
    
    def stop(self):
        """Detach from root logger."""
        if self._attached:
            logging.getLogger().removeHandler(self._handler)
            self._attached = False
    
    def export(self, dispatcher=None) -> Optional[Path]:
        """Generate structured JSON report from captured log records.
        
        Args:
            dispatcher: Optional Dispatcher instance for task stats.
            
        Returns:
            Path to generated report, or None if no records.
        """
        records = self._handler.records
        if not records:
            log.info("[LogExporter] No warnings/errors captured — skipping export")
            return None
        
        # Build summary
        now = datetime.now()
        start_time = self._handler._start_time or now
        duration = now - start_time
        
        # Categorize errors
        categorized: Dict[str, List[Dict]] = defaultdict(list)
        uncategorized: List[Dict] = []
        
        for rec in records:
            entry = {
                "time": rec.timestamp,
                "level": rec.level,
                "logger": rec.logger,
                "message": rec.message,
            }
            if rec.category:
                categorized[rec.category].append(entry)
            else:
                uncategorized.append(entry)
        
        # Task stats from dispatcher
        task_stats = {}
        if dispatcher:
            try:
                tasks = dispatcher.get_all_tasks()
                total = len(tasks)
                completed = sum(1 for t in tasks if t.state.value == "completed")
                failed = sum(1 for t in tasks if t.state.value == "failed")
                task_stats = {
                    "total_tasks": total,
                    "completed": completed,
                    "failed": failed,
                    "success_rate": f"{completed/total*100:.1f}%" if total > 0 else "N/A",
                }
            except Exception:
                pass
        
        # Build report
        report = {
            "session": {
                "export_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration": str(duration).split('.')[0],  # HH:MM:SS
            },
            "summary": {
                "total_warnings_errors": len(records),
                "by_category": {
                    cat: len(entries) for cat, entries in categorized.items()
                },
                "uncategorized_count": len(uncategorized),
                **task_stats,
            },
            "errors": {
                cat: {
                    "count": len(entries),
                    "entries": entries[:20],  # Cap at 20 per category
                }
                for cat, entries in categorized.items()
            },
        }
        
        if uncategorized:
            report["uncategorized"] = uncategorized[:20]
        
        # Write to file
        self._base_dir.mkdir(parents=True, exist_ok=True)
        filename = f"session_{now.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self._base_dir / filename
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            log.info(
                f"[LogExporter] ✅ Report exported: {filepath.name} "
                f"({len(records)} records, "
                f"{len(categorized)} categories)"
            )
            return filepath
        except Exception as e:
            log.error(f"[LogExporter] Export failed: {e}")
            return None
