"""
VEO Pro Max - Auto Updater v2

Supports granular updates:
- Full ZIP: when app version changes (~67MB, requires restart)
- Extension-only: when only extension version changes (~50KB, no restart)
- Pending update: deferred full updates apply on next app startup

GitHub Repo: https://github.com/lynkvproerror/vadveopromax
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time as _time
import zipfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer, QThread

log = logging.getLogger(__name__)


# ★ E7+R4-3: Lazy-cached SSL context with thread-safe lock
_ssl_context_cache = None
_ssl_lock = threading.Lock()

def _create_ssl_context():
    """Create or return cached SSL context with certifi fallback."""
    global _ssl_context_cache
    if _ssl_context_cache is not None:
        return _ssl_context_cache
    with _ssl_lock:
        # Double-check after acquiring lock
        if _ssl_context_cache is not None:
            return _ssl_context_cache
        import ssl
        try:
            ctx = ssl.create_default_context()
            if ctx.get_ca_certs():
                _ssl_context_cache = ctx
                return ctx
        except Exception:
            pass
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
            _ssl_context_cache = ctx
            return ctx
        except ImportError:
            pass
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        log.warning("SSL: Using unverified context (certifi not available)")
        _ssl_context_cache = ctx
        return ctx


# GitHub raw URL for version manifest
GITHUB_REPO = "lynkvproerror/vadveopromax"
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000  # 30 minutes
PENDING_UPDATE_FILE = Path.home() / ".veoauto" / "pending_update.json"


def _safe_extractall(zf: zipfile.ZipFile, dest: str):
    """Extract ZIP with path traversal protection (R2-5)."""
    dest_path = Path(dest).resolve()
    for member in zf.namelist():
        member_path = (dest_path / member).resolve()
        if not str(member_path).startswith(str(dest_path)):
            raise ValueError(
                f"ZIP path traversal detected: {member!r} escapes {dest}"
            )
    zf.extractall(dest)


def _cleanup_old_temp_dirs():
    """★ E6: Remove orphaned veo_update_*/veo_extract_*/veo_ext_update_* temp dirs.
    
    Called at startup to reclaim disk space from crashed/killed downloads.
    ★ R12-5: Skip dirs modified within 60s (may belong to active downloads).
    """
    try:
        tmp = tempfile.gettempdir()
        now = _time.time()
        for name in os.listdir(tmp):
            if name.startswith(("veo_update_", "veo_extract_", "veo_ext_update_")):
                full = os.path.join(tmp, name)
                if os.path.isdir(full):
                    try:
                        # ★ R12-5: Skip recently-modified dirs (active download)
                        mtime = os.path.getmtime(full)
                        if now - mtime < 60:
                            log.debug(f"Skipping fresh temp dir: {name} (age={now - mtime:.0f}s)")
                            continue
                        shutil.rmtree(full, ignore_errors=True)
                        log.debug(f"Cleaned orphaned temp dir: {name}")
                    except Exception:
                        pass
    except Exception:
        pass


class UpdateInfo:
    """Parsed update information from version.json v2."""
    
    def __init__(self, data: dict):
        # App version
        self.version: str = data.get("version", "0.0.0")
        self.download_url: str = data.get("download_url", "")
        self.sha256: str = data.get("sha256", "")
        # Extension version
        self.ext_version: str = data.get("ext_version", "0.0.0")
        self.ext_download_url: str = data.get("ext_download_url", "")
        self.ext_sha256: str = data.get("ext_sha256", "")
        # Metadata
        self.release_date: str = data.get("release_date", "")
        self.changelog: str = data.get("changelog", "")
        self.min_version: str = data.get("min_version", "0.0.0")
        self.force_update: bool = data.get("force_update", False)
        # Determined by _on_check_result: "full", "ext_only", "none"
        self.update_type: str = "none"
    
    def __repr__(self):
        return f"UpdateInfo(app=v{self.version}, ext=v{self.ext_version}, type={self.update_type})"


def compare_versions(current: str, remote: str) -> int:
    """Compare semantic versions.
    
    Handles pre-release suffixes (e.g., "2.3.2-beta" → "2.3.2").
    Returns:
        -1 if current < remote (update available)
         0 if current == remote
         1 if current > remote
    """
    def parse(v: str):
        # Strip prefix 'v' and any pre-release suffix (-beta, -rc1, etc.)
        import re
        clean = re.split(r'[-+]', v.replace("v", ""), maxsplit=1)[0]
        parts = clean.split(".")
        # Pad to 3 parts
        while len(parts) < 3:
            parts.append("0")
        # ★ E8: Sanitize non-numeric parts (e.g. "2a" → 2)
        def safe_int(p: str) -> int:
            digits = re.sub(r'[^0-9]', '', p)
            return int(digits) if digits else 0
        return tuple(safe_int(p) for p in parts[:3])
    
    try:
        c = parse(current)
        r = parse(remote)
        if c < r:
            return -1
        elif c > r:
            return 1
        return 0
    except (ValueError, IndexError):
        return 0


def get_local_extension_version() -> str:
    """Read extension version from bundled extension/manifest.json."""
    try:
        if getattr(sys, "frozen", False):
            # ★ R9-P8: Use resolve() for symlink/junction consistency (matches _get_app_dir)
            ext_manifest = Path(sys.executable).resolve().parent / "extension" / "manifest.json"
        else:
            ext_manifest = Path(__file__).resolve().parent.parent / "extension" / "manifest.json"
        
        if ext_manifest.exists():
            data = json.loads(ext_manifest.read_text(encoding='utf-8'))
            return data.get("version", "0.0.0")
    except Exception as e:
        log.debug(f"Failed to read extension version: {e}")
    return "0.0.0"


class UpdateCheckWorker(QThread):
    """Background thread to check for updates (non-blocking)."""
    
    finished = Signal(object)  # UpdateInfo or None
    error = Signal(str)
    
    def run(self):
        import urllib.request
        import time
        
        ctx = _create_ssl_context()
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # ★ R5-2: Cache-bust GitHub CDN (serves stale for up to 300s)
                bust_url = f"{VERSION_URL}?_t={int(_time.time())}"
                req = urllib.request.Request(
                    bust_url,
                    headers={
                        "User-Agent": "VEO-Pro-Max-Updater/2.0",
                        "Cache-Control": "no-cache, no-store",
                        "Pragma": "no-cache",
                    }
                )
                
                with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                
                info = UpdateInfo(data)
                self.finished.emit(info)
                return  # Success — exit
                
            except Exception as e:
                last_error = e
                log.debug(f"Update check attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 1s, 2s backoff
        
        # All retries exhausted
        err_str = str(last_error) if last_error else "Unknown error"
        # Friendly message for common connection errors
        if "Remote end closed" in err_str or "ConnectionReset" in err_str:
            err_str = "Kết nối bị ngắt — thử lại sau"
        elif "urlopen error" in err_str:
            err_str = "Không thể kết nối — kiểm tra mạng"
        elif "SSL" in err_str or "certificate" in err_str.lower():
            err_str = "Lỗi SSL — kiểm tra proxy/antivirus"
        
        log.debug(f"Update check failed after {max_retries} attempts: {last_error}")
        self.error.emit(err_str)


class UpdateDownloadWorker(QThread):
    """Background thread to download update ZIP (full or extension-only)."""
    
    progress = Signal(int)      # 0-100 percentage
    finished = Signal(str)      # Path to downloaded file
    error = Signal(str)
    
    def __init__(self, url: str, sha256: str = "", filename: str = "update.zip"):
        super().__init__()
        self.url = url
        self.expected_sha256 = sha256
        self.filename = filename
    
    def run(self):
        tmp_dir = None  # Sentinel for cleanup
        try:
            import urllib.request
            import hashlib
            
            ctx = _create_ssl_context()
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "VEO-Pro-Max-Updater/2.0"}
            )
            
            # Download to temp file
            tmp_dir = tempfile.mkdtemp(prefix="veo_update_")
            tmp_path = os.path.join(tmp_dir, self.filename)
            
            # ★ R4-5: 600s timeout for slow connections (67MB @ 1Mbps = ~9min)
            with urllib.request.urlopen(req, timeout=600, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                
                # Check disk space (need 3x for download + extract + margin)
                if total > 0:
                    try:
                        free = shutil.disk_usage(tmp_dir).free
                        needed = total * 3
                        if free < needed:
                            shutil.rmtree(tmp_dir, ignore_errors=True)
                            self.error.emit(
                                f"Insufficient disk space!\n"
                                f"Need: {needed // 1024 // 1024} MB\n"
                                f"Free: {free // 1024 // 1024} MB"
                            )
                            return
                    except Exception:
                        pass
                
                downloaded = 0
                sha = hashlib.sha256()
                _last_pct = -1
                
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)  # 1MB chunks
                        if not chunk:
                            break
                        f.write(chunk)
                        sha.update(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded / total * 100)
                            if pct != _last_pct:
                                self.progress.emit(min(pct, 99))
                                _last_pct = pct
                        else:
                            # ★ U3: No Content-Length → emit MB-based progress
                            mb = downloaded // (1024 * 1024)
                            if mb != _last_pct:
                                # Cap at 95% for indeterminate, real 100% emitted after
                                self.progress.emit(min(mb, 95))
                                _last_pct = mb
            
            # Verify SHA-256 if provided
            if self.expected_sha256:
                actual = sha.hexdigest()
                if actual.lower() != self.expected_sha256.lower():
                    # SHA mismatch → clean up downloaded file
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    self.error.emit(
                        f"SHA-256 mismatch!\n"
                        f"Expected: {self.expected_sha256[:16]}...\n"
                        f"Got: {actual[:16]}..."
                    )
                    return
            else:
                log.warning("SHA-256 not provided — skipping integrity check")
            
            self.progress.emit(100)
            self.finished.emit(tmp_path)
            
        except Exception as e:
            log.error(f"Update download failed: {e}")
            # Cleanup temp dir on failure
            if tmp_dir and os.path.isdir(tmp_dir):
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass
            self.error.emit(str(e))


class AutoUpdater(QObject):
    """Main auto-update controller v2.
    
    Supports:
    - Full update (app version changed) → download full ZIP → restart or defer
    - Extension-only update → download ext ZIP → hot-replace, no restart
    - Pending updates → apply deferred updates on next startup
    """
    
    # Signals
    update_available = Signal(object)   # UpdateInfo (with update_type set)
    up_to_date = Signal()               # Already on latest version
    download_progress = Signal(int)     # 0-100
    download_complete = Signal(str)     # Path to ZIP
    download_error = Signal(str)
    update_applied = Signal()           # Ready to restart (full update)
    ext_update_applied = Signal()       # Extension hot-replaced (no restart)
    check_error = Signal(str)           # Version check error
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self.check_now)
        self._check_worker: Optional[UpdateCheckWorker] = None
        self._download_worker: Optional[UpdateDownloadWorker] = None
        self._latest_info: Optional[UpdateInfo] = None
        self._periodic_started = False  # ★ E4: guard against stacking timers
        
        # ★ E6+R4-7+R11-3: Defer cleanup to background thread (avoid blocking UI)
        threading.Thread(target=_cleanup_old_temp_dirs, daemon=True).start()
    
    @property
    def latest_info(self) -> Optional[UpdateInfo]:
        return self._latest_info
    
    def start_periodic_check(self):
        """Start checking for updates every 30 minutes."""
        # ★ E4: Prevent stacking timers on repeated calls
        if self._periodic_started:
            return
        self._periodic_started = True
        # Initial check after 10 seconds (let app fully load)
        QTimer.singleShot(10_000, self.check_now)
        self._check_timer.start(UPDATE_CHECK_INTERVAL_MS)
    
    def stop_periodic_check(self):
        self._check_timer.stop()
        self._periodic_started = False  # ★ E4: allow restart after stop
    
    def check_now(self):
        """Check for updates immediately (non-blocking)."""
        if self._check_worker and self._check_worker.isRunning():
            # ★ R10-3: Detect stuck worker (>30s) and force-terminate
            started = getattr(self._check_worker, '_started_at', 0)
            if started and (_time.time() - started > 30):
                log.warning("Check worker stuck >30s — terminating")
                self._check_worker.terminate()
                self._check_worker.wait(1000)
            else:
                return  # Already checking
        
        # ★ U4: Cleanup old worker to prevent memory leak
        if self._check_worker is not None:
            try:
                # ★ R12-4: Targeted disconnect — avoid detaching Qt internal QThread.finished
                self._check_worker.finished.disconnect(self._on_check_result)
                self._check_worker.error.disconnect(self._on_check_error)
            except (RuntimeError, TypeError):
                pass
            self._check_worker.deleteLater()
        
        self._check_worker = UpdateCheckWorker()
        self._check_worker._started_at = _time.time()  # ★ R10-3: track start time
        self._check_worker.finished.connect(self._on_check_result)
        self._check_worker.error.connect(self._on_check_error)
        self._check_worker.start()
    
    def download_update(self, info: Optional[UpdateInfo] = None):
        """Download the appropriate update (full or ext-only)."""
        info = info or self._latest_info
        if not info:
            self.download_error.emit("No update info available")
            return
        
        if self._download_worker and self._download_worker.isRunning():
            return  # Already downloading
        
        # Choose URL/SHA based on update type
        if info.update_type == "full":
            url = info.download_url
            sha = info.sha256
            filename = f"VEO_Pro_Max_v{info.version}.zip"
        elif info.update_type == "ext_only":
            url = info.ext_download_url
            sha = info.ext_sha256
            filename = f"VEO_Extension_v{info.ext_version}.zip"
        else:
            self.download_error.emit("No update available")
            return
        
        if not url:
            self.download_error.emit(f"No download URL for {info.update_type}")
            return
        
        # ★ U4+R8-3: Cleanup old download worker — wait before disconnect
        if self._download_worker is not None:
            try:
                self._download_worker.wait(100)  # ★ R8-3: let worker finish
                # ★ R13-1: Targeted disconnect — avoid detaching Qt internal QThread.finished
                self._download_worker.progress.disconnect(self.download_progress.emit)
                self._download_worker.finished.disconnect(self._on_download_complete)
                self._download_worker.error.disconnect(self.download_error.emit)
            except (RuntimeError, TypeError):
                pass
            self._download_worker.deleteLater()
        
        self._download_worker = UpdateDownloadWorker(
            url=url, sha256=sha, filename=filename
        )
        self._download_worker.progress.connect(self.download_progress.emit)
        self._download_worker.finished.connect(self._on_download_complete)
        self._download_worker.error.connect(self.download_error.emit)
        self._download_worker.start()
    
    def apply_update(self, zip_path: str):
        """Apply FULL update: extract ZIP, create updater script, restart.
        
        Strategy (CLEAN UPDATE — macOS):
        1. Validate ZIP integrity (★ R5-1)
        2. Extract ZIP to temp folder
        3. Write Bash script that waits for exit, replaces app, restarts
        4. Exit current app
        """
        # ★ R9-P6: Prevent concurrent apply calls (pending + manual button race)
        if getattr(self, '_applying_update', False):
            log.warning("apply_update already in progress — ignoring duplicate call")
            return
        self._applying_update = True
        try:
            # ★ R5-1: Validate ZIP integrity before destructive operations
            try:
                with zipfile.ZipFile(zip_path, "r") as zf_test:
                    bad = zf_test.testzip()
                    if bad is not None:
                        self._cleanup_zip(zip_path)
                        self.download_error.emit(
                            f"ZIP corrupted: bad file {bad!r}\n"
                            f"Please re-download the update."
                        )
                        return
            except (zipfile.BadZipFile, Exception) as ze:
                self._cleanup_zip(zip_path)
                self.download_error.emit(
                    f"ZIP file invalid: {ze}\nPlease re-download."
                )
                return
            
            app_dir = self._get_app_dir()
            extract_dir = tempfile.mkdtemp(prefix="veo_extract_")
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extractall(zf, extract_dir)
            
            # Find root of extracted content
            extracted_items = os.listdir(extract_dir)
            if len(extracted_items) == 1 and os.path.isdir(
                os.path.join(extract_dir, extracted_items[0])
            ):
                source_dir = os.path.join(extract_dir, extracted_items[0])
            else:
                source_dir = extract_dir
            
            # ★ R8-P4: Validate source_dir contains expected binary
            exe_name = os.path.basename(sys.executable)
            if not os.path.isfile(os.path.join(source_dir, exe_name)):
                # Try subdirectories (ZIP might have extra nesting)
                found = False
                for item in os.listdir(source_dir):
                    candidate = os.path.join(source_dir, item)
                    if os.path.isdir(candidate) and os.path.isfile(
                        os.path.join(candidate, exe_name)
                    ):
                        source_dir = candidate
                        found = True
                        log.info(f"Source binary found in subdirectory: {source_dir}")
                        break
                if not found:
                    log.error(f"Extracted ZIP does not contain {exe_name}")
                    self.download_error.emit(
                        f"ZIP không chứa {exe_name}\n"
                        f"Vui lòng tải lại bản cập nhật."
                    )
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    return
            
            # ★ E1: Write paths to JSON sidecar (injection-safe)
            sh_path = os.path.join(tempfile.gettempdir(), "veo_updater.sh")
            json_path = os.path.join(tempfile.gettempdir(), "veo_updater_paths.json")
            exe_full = os.path.join(app_dir, exe_name)
            pid = os.getpid()
            log_path = os.path.join(tempfile.gettempdir(), "veo_update.log")
            
            # Write all paths to JSON (no injection possible)
            paths_data = {
                "appDir": app_dir,
                "srcDir": source_dir,
                "exePath": exe_full,
                "zipPath": zip_path,
                "extrDir": extract_dir,
                "logFile": log_path,
                "pid": pid,
            }
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(paths_data, jf, ensure_ascii=False)
            
            # ── macOS Bash updater script ──
            sh_content = f"""#!/bin/bash
set +e  # Continue on errors (like PS $ErrorActionPreference = 'Continue')

# ★ Read paths from JSON sidecar (uses python -c for JSON parsing)
JSON_PATH='{json_path}'
APP_DIR=$(python3 -c "import json; d=json.load(open('$JSON_PATH')); print(d['appDir'])")
SRC_DIR=$(python3 -c "import json; d=json.load(open('$JSON_PATH')); print(d['srcDir'])")
EXE_PATH=$(python3 -c "import json; d=json.load(open('$JSON_PATH')); print(d['exePath'])")
ZIP_PATH=$(python3 -c "import json; d=json.load(open('$JSON_PATH')); print(d['zipPath'])")
EXTR_DIR=$(python3 -c "import json; d=json.load(open('$JSON_PATH')); print(d['extrDir'])")
LOG_FILE=$(python3 -c "import json; d=json.load(open('$JSON_PATH')); print(d['logFile'])")
APP_PID=$(python3 -c "import json; d=json.load(open('$JSON_PATH')); print(d['pid'])")

log_msg() {{
    local ts
    ts=$(date '+%H:%M:%S')
    echo "$ts $1" >> "$LOG_FILE"
    echo "$1"
}}

log_msg '=== VEO Pro Max Clean Updater (macOS) ==='

# ★ R7: Write start marker — proves script launched
MARKER_FILE="${{TMPDIR:-/tmp}}/veo_update_marker.txt"
echo "started $(date '+%Y-%m-%d %H:%M:%S')" > "$MARKER_FILE"
log_msg 'Marker: started'

log_msg 'Waiting for app to exit...'

# ★ R7: Wait for app process to exit (60s timeout)
WAIT_COUNT=0
while kill -0 "$APP_PID" 2>/dev/null; do
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [ "$WAIT_COUNT" -ge 30 ]; then
        log_msg 'WARNING: App did not exit within 60s — continuing anyway'
        break
    fi
    sleep 2
done

if ! kill -0 "$APP_PID" 2>/dev/null; then
    log_msg 'App process exited.'
else
    log_msg "App PID $APP_PID still running after wait."
fi

# ★ R7: Fallback — wait for any matching process to exit by name
EXE_NAME=$(basename "$EXE_PATH")
for w in $(seq 1 10); do
    if ! pgrep -x "$EXE_NAME" > /dev/null 2>&1; then
        break
    fi
    log_msg "App still running (by name '$EXE_NAME'), waiting 2s... ($w/10)"
    sleep 2
done

# ★ R8-P1: Force-kill if STILL running
if pgrep -x "$EXE_NAME" > /dev/null 2>&1; then
    log_msg "FORCE KILLING $EXE_NAME (still running after 20s wait)"
    pkill -9 -x "$EXE_NAME" 2>/dev/null || true
    sleep 3
    log_msg 'Force kill done.'
else
    # Extra safety wait for file handles to release
    sleep 3
fi

# ★ FIX R5: Kill orphan Chrome processes using our browser profiles
log_msg 'Killing orphan Chrome processes...'
CHROME_KILLED=0
PROFILES_DIR1="$HOME/.veoauto/browser_profiles"
PROFILES_DIR2="$APP_DIR/config/browser_profiles"

for PROFILES_DIR in "$PROFILES_DIR1" "$PROFILES_DIR2"; do
    if [ ! -d "$PROFILES_DIR" ]; then
        continue
    fi
    log_msg "Scanning $PROFILES_DIR for Chrome PID files..."
    # Find .chrome_pid.json files and kill tracked Chrome processes
    find "$PROFILES_DIR" -name '.chrome_pid.json' -type f 2>/dev/null | while read -r PID_FILE; do
        CHROME_PID=$(python3 -c "import json; print(json.load(open('$PID_FILE')).get('pid',''))" 2>/dev/null)
        if [ -n "$CHROME_PID" ] && kill -0 "$CHROME_PID" 2>/dev/null; then
            # Check if it's actually Chrome
            PROC_NAME=$(ps -p "$CHROME_PID" -o comm= 2>/dev/null || true)
            if echo "$PROC_NAME" | grep -qi "chrome"; then
                # Kill process and all children
                pkill -P "$CHROME_PID" 2>/dev/null || true
                kill -9 "$CHROME_PID" 2>/dev/null || true
                CHROME_KILLED=$((CHROME_KILLED + 1))
                log_msg "Killed Chrome tree PID=$CHROME_PID"
            fi
        fi
    done
    
    # ★ Nuclear fallback — kill Chrome processes using our browser_profiles
    for CPID in $(pgrep -i "Google Chrome" 2>/dev/null || true); do
        CMD_LINE=$(ps -p "$CPID" -o command= 2>/dev/null || true)
        if echo "$CMD_LINE" | grep -q "$PROFILES_DIR"; then
            pkill -P "$CPID" 2>/dev/null || true
            kill -9 "$CPID" 2>/dev/null || true
            CHROME_KILLED=$((CHROME_KILLED + 1))
            log_msg "Nuclear: killed Chrome PID=$CPID"
        fi
    done
done

# ★ FIX R5: Kill orphan node processes from Playwright
for NPID in $(pgrep -x "node" 2>/dev/null || true); do
    NODE_PATH=$(ps -p "$NPID" -o command= 2>/dev/null || true)
    if echo "$NODE_PATH" | grep -q "$APP_DIR"; then
        kill -9 "$NPID" 2>/dev/null || true
        log_msg "Killed orphan node PID=$NPID"
    fi
done

sleep 2
log_msg "Chrome cleanup done ($CHROME_KILLED killed)."

# ★ R6: Validate source directory BEFORE any file operations
log_msg "Source dir: $SRC_DIR"
log_msg "App dir:    $APP_DIR"
log_msg "Exe path:   $EXE_PATH"
SRC_COUNT=$(find "$SRC_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
log_msg "Source file count: $SRC_COUNT"
if [ "$SRC_COUNT" -eq 0 ]; then
    log_msg 'FATAL: Source directory is EMPTY — aborting update!'
    exit 1
fi

# ★ Rule #11: Backup tools/ BEFORE delete (FFmpeg ~200MB, survives updates)
TOOLS_DIR="$APP_DIR/tools"
TOOLS_BACKUP="${{TMPDIR:-/tmp}}/veo_tools_backup"
TOOLS_BACKED_UP=0
if [ -d "$TOOLS_DIR" ]; then
    log_msg 'Backing up tools/ directory...'
    rm -rf "$TOOLS_BACKUP" 2>/dev/null || true
    if cp -R "$TOOLS_DIR" "$TOOLS_BACKUP" 2>/dev/null; then
        TOOLS_BACKED_UP=1
        TOOL_COUNT=$(find "$TOOLS_BACKUP" -type f 2>/dev/null | wc -l | tr -d ' ')
        log_msg "Tools backed up ($TOOL_COUNT files)"
    else
        log_msg 'Tools backup failed — will rely on auto-download'
    fi
fi

log_msg 'Deleting old app folder...'
if rm -rf "$APP_DIR" 2>/dev/null; then
    log_msg 'Old app folder deleted.'
else
    log_msg 'WARNING: Could not fully delete old folder — will overwrite'
    # Log surviving files
    find "$APP_DIR" -type f 2>/dev/null | head -20 | while read -r f; do
        log_msg "  STILL EXISTS: $f"
    done
fi

log_msg "Copying new files from $SRC_DIR to $APP_DIR ..."
mkdir -p "$APP_DIR"

# ★ Use rsync as PRIMARY (macOS equivalent of robocopy /MIR)
# --archive = preserve permissions, timestamps, symlinks
# --delete = remove files not in source (like /PURGE)
# --exclude = skip tools/ (managed separately)
log_msg 'Using rsync mirror...'
RSYNC_LOG=$(rsync -a --delete --exclude='tools/' "$SRC_DIR/" "$APP_DIR/" 2>&1) || true
echo "$RSYNC_LOG" >> "$LOG_FILE"
RSYNC_EXIT=$?
if [ "$RSYNC_EXIT" -eq 0 ]; then
    log_msg "rsync completed successfully."
else
    log_msg "rsync had errors (exit=$RSYNC_EXIT) — falling back to cp..."
    cp -R "$SRC_DIR/"* "$APP_DIR/" 2>/dev/null || true
    log_msg 'cp fallback done.'
fi

# ★ R6: Post-copy verification — compare file counts
DST_COUNT=$(find "$APP_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
log_msg "Destination file count after copy: $DST_COUNT (source had: $SRC_COUNT)"
if [ -f "$EXE_PATH" ]; then
    EXE_SIZE=$(du -m "$EXE_PATH" 2>/dev/null | cut -f1)
    log_msg "Destination binary: $EXE_PATH (${{EXE_SIZE}}MB)"
else
    log_msg "CRITICAL: Binary NOT found in destination after copy: $EXE_PATH"
fi

# ★ R7: Compare version.json
SRC_VER_FILE="$SRC_DIR/version.json"
DST_VER_FILE="$APP_DIR/version.json"
if [ -f "$SRC_VER_FILE" ] && [ -f "$DST_VER_FILE" ]; then
    SV=$(python3 -c "import json; print(json.load(open('$SRC_VER_FILE')).get('version','?'))" 2>/dev/null)
    DV=$(python3 -c "import json; print(json.load(open('$DST_VER_FILE')).get('version','?'))" 2>/dev/null)
    if [ "$SV" = "$DV" ]; then
        log_msg "Version match: $SV ✓"
    else
        log_msg "VERSION MISMATCH! Source=$SV Dest=$DV — update may have failed"
    fi
elif [ -f "$SRC_VER_FILE" ]; then
    log_msg 'WARNING: version.json exists in source but NOT in destination'
fi

# ★ Rule #11: Restore tools/ from backup
if [ "$TOOLS_BACKED_UP" -eq 1 ]; then
    NEW_TOOLS="$APP_DIR/tools"
    if [ ! -f "$NEW_TOOLS/ffmpeg/ffmpeg" ]; then
        log_msg 'Restoring tools/ from backup (new ZIP has no FFmpeg)...'
        rm -rf "$NEW_TOOLS" 2>/dev/null || true
        if cp -R "$TOOLS_BACKUP" "$NEW_TOOLS" 2>/dev/null; then
            log_msg 'Tools restored successfully.'
        else
            log_msg 'Tools restore failed — FFmpeg will auto-download on next launch'
        fi
    else
        log_msg 'New ZIP already bundles FFmpeg — using new version.'
    fi
    rm -rf "$TOOLS_BACKUP" 2>/dev/null || true
fi

# ★ Make binary executable
chmod +x "$EXE_PATH" 2>/dev/null || true

# ★ Verify binary exists before restart
if [ ! -f "$EXE_PATH" ]; then
    log_msg "FATAL: Binary not found at $EXE_PATH — update FAILED!"
    # Try to find any executable
    FOUND_EXE=$(find "$APP_DIR" -maxdepth 1 -type f -perm +111 2>/dev/null | head -1)
    if [ -n "$FOUND_EXE" ]; then
        EXE_PATH="$FOUND_EXE"
        log_msg "Found alternate binary: $EXE_PATH"
    else
        log_msg 'No executable found — cannot restart. Manual intervention needed.'
        exit 1
    fi
fi

# Cleanup
log_msg 'Cleaning up temp files...'
rm -rf "$EXTR_DIR" 2>/dev/null || true
rm -f "$ZIP_PATH" 2>/dev/null || true
rm -f "$JSON_PATH" 2>/dev/null || true

# ★ R7: Write completion marker
echo "completed $(date '+%Y-%m-%d %H:%M:%S')" > "$MARKER_FILE"
log_msg 'Marker: completed'

# Restart
log_msg "Starting: $EXE_PATH"
open "$EXE_PATH" 2>/dev/null || "$EXE_PATH" &
log_msg 'App restarted. Clean update complete!'

sleep 2
rm -f "$0" 2>/dev/null || true
"""
            
            with open(sh_path, "w", encoding="utf-8") as f:
                f.write(sh_content)
            os.chmod(sh_path, 0o755)
            
            # Launch updater Bash script and exit
            log.info(f"Launching updater: {sh_path}")
            subprocess.Popen(
                ["/bin/bash", sh_path],
                start_new_session=True,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # ★ R8-P0: Clear pending AFTER Popen succeeds
            self.clear_pending_update()
            
            self.update_applied.emit()
            
            # ★ FIX R3: Kill all Chrome processes BEFORE exit
            try:
                from core.chrome_manager import kill_all_managed_chromes
                killed_any = False
                for bp_dir in [
                    os.path.join(str(Path.home()), ".veoauto", "browser_profiles"),
                    os.path.join(self._get_app_dir(), "config", "browser_profiles"),
                ]:
                    if os.path.isdir(bp_dir):
                        kill_all_managed_chromes(bp_dir)
                        log.info(f"Pre-update: killed Chrome in {bp_dir}")
                        killed_any = True
                if not killed_any:
                    log.debug("Pre-update: no browser_profiles dirs found")
            except Exception as e:
                log.warning(f"Pre-update Chrome kill failed: {e}")
            
            # Exit the app (3s delay for Chrome kill + file handle release)
            QTimer.singleShot(3000, lambda: os._exit(0))
            
        except Exception as e:
            log.error(f"Failed to apply update: {e}")
            if 'extract_dir' in locals():
                shutil.rmtree(extract_dir, ignore_errors=True)
            self.download_error.emit(f"Apply failed: {e}")
    
    def apply_extension_update(self, zip_path: str):
        """Hot-replace extension/ folder only. NO restart needed.
        
        ★ R5-4+R6-1: Runs in a QThread worker to avoid blocking the UI.
        Uses QThread (not threading.Thread) so signals auto-marshal to main thread.
        """
        # ★ R9-1: Guard against double-click / concurrent ext update
        if hasattr(self, '_ext_worker') and self._ext_worker is not None:
            if self._ext_worker.isRunning():
                log.debug("Extension update already in progress — ignoring")
                return
            # ★ R7-2: Cleanup old ext worker to prevent memory leak
            try:
                # ★ R14-1: Targeted disconnect — avoid detaching Qt internal QThread.finished
                self._ext_worker.ext_done.disconnect(self._on_ext_update_done)
                self._ext_worker.ext_error.disconnect(self.download_error.emit)
            except (RuntimeError, TypeError):
                pass
            self._ext_worker.deleteLater()
        
        # ★ R6-1: Use QThread so signals are delivered on main thread
        self._ext_worker = _ExtUpdateWorker(self, zip_path)
        # ★ R10-2: Use bound method instead of closure (avoids strong self capture)
        self._ext_worker.ext_done.connect(self._on_ext_update_done)
        self._ext_worker.ext_error.connect(self.download_error.emit)
        self._ext_worker.start()
    
    def _on_ext_update_done(self):
        """★ R8-4+R10-2: Clear stale info after successful ext update."""
        self._latest_info = None
        self.ext_update_applied.emit()
    
    # ── Pending Update (defer full update to next startup) ──
    
    def save_pending_update(self, zip_path: str, version: str, sha256: str = ""):
        """Save pending update marker for deferred full update.
        
        Copies ZIP to ~/.veoauto/updates/ (persistent across reboots).
        Cleans up any existing pending update before saving new one.
        """
        try:
            # Copy ZIP to persistent location (temp may be cleaned)
            updates_dir = PENDING_UPDATE_FILE.parent / "updates"
            updates_dir.mkdir(parents=True, exist_ok=True)
            
            persistent_zip = updates_dir / Path(zip_path).name
            shutil.copy2(zip_path, str(persistent_zip))
            log.info(f"Copied update ZIP to persistent location: {persistent_zip}")
            
            # ★ R17-4+R12-1: Clear old pending AFTER copy succeeds, but skip
            # deleting old ZIP if it's the same path (same-version re-defer)
            try:
                if PENDING_UPDATE_FILE.exists():
                    old_data = json.loads(PENDING_UPDATE_FILE.read_text(encoding='utf-8'))
                    old_zip = old_data.get("zip_path", "")
                    # Only delete old ZIP if path differs from new (avoids deleting our fresh copy)
                    if old_zip and old_zip != str(persistent_zip) and Path(old_zip).exists():
                        Path(old_zip).unlink(missing_ok=True)
                    PENDING_UPDATE_FILE.unlink()
            except Exception:
                pass
            
            # Clean up original temp file
            try:
                os.unlink(zip_path)
                parent = os.path.dirname(zip_path)
                if parent and os.path.basename(parent).startswith("veo_update_"):
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass
            
            # ★ R16-4: Use explicit sha256 parameter (not self._latest_info which may be None)
            expected_sha = sha256
            
            # ★ R18-4: Use standard import instead of __import__ anti-pattern
            from datetime import datetime as _dt
            data = {
                "zip_path": str(persistent_zip),
                "update_type": "full",
                "version": version,
                "sha256": expected_sha,
                "saved_at": _dt.now().isoformat(),
            }
            PENDING_UPDATE_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            log.info(f"Pending update saved: v{version} → {persistent_zip}")
        except Exception as e:
            log.error(f"Failed to save pending update: {e}")
            # ★ R10-5: Notify UI so user doesn't think save succeeded
            self.download_error.emit(f"Failed to save pending update: {e}")
    
    @staticmethod
    def clear_pending_update():
        """Remove pending update marker AND persistent ZIP."""
        try:
            if PENDING_UPDATE_FILE.exists():
                # Also delete the stored ZIP file
                try:
                    data = json.loads(PENDING_UPDATE_FILE.read_text(encoding='utf-8'))
                    zip_path = data.get("zip_path", "")
                    if zip_path and Path(zip_path).exists():
                        Path(zip_path).unlink(missing_ok=True)
                except Exception:
                    pass
                PENDING_UPDATE_FILE.unlink()
        except Exception:
            pass
    
    @staticmethod
    def check_pending_update() -> Optional[dict]:
        """Check if a deferred update exists. Call on app startup.
        
        Returns:
            dict with zip_path and version if pending, None otherwise.
        """
        try:
            if not PENDING_UPDATE_FILE.exists():
                return None
            
            data = json.loads(PENDING_UPDATE_FILE.read_text(encoding='utf-8'))
            zip_path = data.get("zip_path", "")
            
            if zip_path and Path(zip_path).exists():
                log.info(f"Pending update found: v{data.get('version')} at {zip_path}")
                return data
            else:
                # ZIP was cleaned up → discard marker
                log.info("Pending update ZIP not found, discarding marker")
                PENDING_UPDATE_FILE.unlink(missing_ok=True)
                return None
                
        except Exception as e:
            log.debug(f"Pending update check error: {e}")
            try:
                PENDING_UPDATE_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            return None
    
    # ── Internal handlers ──
    
    def _on_check_result(self, info: UpdateInfo):
        """Determine update type by comparing both app and extension versions."""
        from config.constants import AppConstants
        
        current_app = AppConstants.APP_VERSION
        current_ext = get_local_extension_version()
        
        app_cmp = compare_versions(current_app, info.version)
        ext_cmp = compare_versions(current_ext, info.ext_version)
        
        # ★ min_version enforcement: block dangerously outdated versions
        below_min = compare_versions(current_app, info.min_version) < 0
        
        if below_min or app_cmp < 0:
            # ★ R10-1: App version changed (or below minimum) → must do full update
            info.update_type = "full"
            reason = f" [BELOW MIN v{info.min_version}]" if below_min else ""
            log.info(
                f"Full update available: app v{current_app}→v{info.version}, "
                f"ext v{current_ext}→v{info.ext_version}{reason}"
            )
            self._latest_info = info
            self.update_available.emit(info)
        elif info.force_update and app_cmp == 0 and ext_cmp < 0:
            # ★ R9-5+R11-1: force_update + same app + ext outdated → ext-only update
            if not info.ext_download_url:
                log.warning(
                    f"Extension v{info.ext_version} available but ext_download_url is empty — skipping"
                )
                self.up_to_date.emit()
                return
            info.update_type = "ext_only"
            log.info(f"Extension update available (force): v{current_ext}→v{info.ext_version}")
            self._latest_info = info
            self.update_available.emit(info)
        elif info.force_update and ext_cmp == 0:
            # ★ R15-1: force_update + app current/newer + ext ALSO current → nothing to do
            log.debug(
                f"force_update set but already up-to-date "
                f"(app=v{current_app}, ext=v{current_ext}) — skipping"
            )
            self.up_to_date.emit()
        elif ext_cmp < 0:
            # ★ R6-5: Skip ext_only if no download URL provided
            if not info.ext_download_url:
                log.warning(
                    f"Extension v{info.ext_version} available but ext_download_url is empty — skipping"
                )
                self.up_to_date.emit()
                return
            # Only extension changed → lightweight update
            info.update_type = "ext_only"
            log.info(f"Extension update available: v{current_ext}→v{info.ext_version}")
            self._latest_info = info
            self.update_available.emit(info)
        else:
            log.debug(f"Up to date (app=v{current_app}, ext=v{current_ext})")
            self.up_to_date.emit()
    
    def _on_check_error(self, error: str):
        """Log check errors and notify UI."""
        log.debug(f"Update check error: {error}")
        self.check_error.emit(error)
    
    def _on_download_complete(self, path: str):
        """Handle download completion."""
        log.info(f"Update downloaded: {path}")
        self.download_complete.emit(path)
    
    @staticmethod
    def _cleanup_zip(zip_path: str):
        """★ R10-4: Clean up ZIP file and its parent veo_update_* dir."""
        try:
            if os.path.exists(zip_path):
                parent = os.path.dirname(zip_path)
                if parent and os.path.basename(parent).startswith("veo_update_"):
                    shutil.rmtree(parent, ignore_errors=True)
                else:
                    os.unlink(zip_path)
        except Exception:
            pass
    
    @staticmethod
    def _get_app_dir() -> str:
        """Get the application root directory.
        
        ★ R8-P5: Uses resolve() to handle symlinks/junctions correctly.
        """
        if getattr(sys, "frozen", False):
            return str(Path(sys.executable).resolve().parent)
        else:
            return str(Path(__file__).resolve().parent.parent)


class _ExtUpdateWorker(QThread):
    """★ R6-1: QThread worker for extension hot-replace.
    
    Signals auto-marshal to the receiver's thread (main thread),
    unlike threading.Thread which does NOT integrate with Qt event loop.
    """
    ext_done = Signal()
    ext_error = Signal(str)
    
    def __init__(self, updater, zip_path: str):
        super().__init__(updater)  # parent = AutoUpdater
        self._zip_path = zip_path
        self._updater = updater
    
    def run(self):
        try:
            zip_path = self._zip_path
            app_dir = self._updater._get_app_dir()
            ext_dir = os.path.join(app_dir, "extension")
            
            # ★ R8-2: Validate ZIP integrity before extraction (same as full update)
            try:
                with zipfile.ZipFile(zip_path, "r") as zf_test:
                    bad = zf_test.testzip()
                    if bad is not None:
                        # ★ R10-4: Clean up invalid ZIP
                        AutoUpdater._cleanup_zip(zip_path)
                        self.ext_error.emit(
                            f"Extension ZIP corrupted: bad file {bad!r}\n"
                            f"Please re-download the update."
                        )
                        return
            except (zipfile.BadZipFile, Exception) as ze:
                AutoUpdater._cleanup_zip(zip_path)
                self.ext_error.emit(f"Extension ZIP invalid: {ze}")
                return
            
            extract_dir = tempfile.mkdtemp(prefix="veo_ext_update_")
            
            # Extract
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extractall(zf, extract_dir)
            
            # Source: extracted/extension/ or extracted/
            src_ext = os.path.join(extract_dir, "extension")
            if not os.path.isdir(src_ext):
                src_ext = extract_dir
            
            # Replace extension folder (retry for Chrome file locks)
            max_retries = 3
            _rmtree_ok = False
            for attempt in range(max_retries):
                try:
                    if os.path.isdir(ext_dir):
                        shutil.rmtree(ext_dir)
                    _rmtree_ok = True
                    break
                except PermissionError:
                    if attempt < max_retries - 1:
                        log.warning(f"Extension files locked (attempt {attempt+1}/{max_retries}), retrying in 2s...")
                        _time.sleep(2)
                    else:
                        log.warning("Extension files locked — force overwriting individual files")
                        # ★ R9-3: Ensure ext_dir exists (rmtree may have partially deleted)
                        os.makedirs(ext_dir, exist_ok=True)
                        for root, dirs, files in os.walk(src_ext):
                            rel = os.path.relpath(root, src_ext)
                            dst_root = os.path.join(ext_dir, rel)
                            os.makedirs(dst_root, exist_ok=True)
                            for f in files:
                                src_f = os.path.join(root, f)
                                dst_f = os.path.join(dst_root, f)
                                try:
                                    shutil.copy2(src_f, dst_f)
                                except Exception as e:
                                    log.warning(f"Cannot overwrite {f}: {e}")
                        # Clean stale files
                        new_files = set()
                        for root, dirs, files in os.walk(src_ext):
                            for f in files:
                                rel_path = os.path.relpath(os.path.join(root, f), src_ext)
                                new_files.add(rel_path)
                        for root, dirs, files in os.walk(ext_dir):
                            for f in files:
                                rel_path = os.path.relpath(os.path.join(root, f), ext_dir)
                                if rel_path not in new_files:
                                    try:
                                        os.unlink(os.path.join(root, f))
                                        log.debug(f"Removed stale extension file: {rel_path}")
                                    except Exception:
                                        pass
            
            if _rmtree_ok:
                # ★ FIX: dirs_exist_ok=True guards against race condition where
                # ext_dir is recreated between rmtree and copytree
                shutil.copytree(src_ext, ext_dir, dirs_exist_ok=True)
            
            # Cleanup
            shutil.rmtree(extract_dir, ignore_errors=True)
            try:
                os.unlink(zip_path)
                # ★ R7-5: Also remove parent veo_update_* dir (now empty)
                parent_dir = os.path.dirname(zip_path)
                if parent_dir and os.path.basename(parent_dir).startswith("veo_update_"):
                    shutil.rmtree(parent_dir, ignore_errors=True)
            except Exception:
                pass
            
            # ★ Fix: Clear stale %TEMP%\veo_extension cache
            # _get_safe_path() copies extension to this temp dir for folder picker.
            # After hot-update, old copy is stale → Chrome may load outdated version.
            _stale_temp = os.path.join(tempfile.gettempdir(), "veo_extension")
            if os.path.isdir(_stale_temp):
                shutil.rmtree(_stale_temp, ignore_errors=True)
                log.info(f"Cleared stale extension temp cache: {_stale_temp}")
            
            log.info("Extension hot-updated successfully (no restart needed)")
            self.ext_done.emit()
            
        except Exception as e:
            log.error(f"Extension update failed: {e}")
            # ★ R11-4: Clean up extract_dir if it was created
            if 'extract_dir' in locals():
                shutil.rmtree(extract_dir, ignore_errors=True)
            # ★ R13-3: Clean up downloaded ZIP on failure
            AutoUpdater._cleanup_zip(zip_path)
            self.ext_error.emit(f"Extension update failed: {e}")
