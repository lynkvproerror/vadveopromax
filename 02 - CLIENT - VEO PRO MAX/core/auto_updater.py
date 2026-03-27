"""
VEO Pro Max - Auto Updater v2

Supports granular updates:
- Full ZIP: when app version changes (~67MB, requires restart)
- Installer EXE: for minimum-version jumps or fragile legacy updates
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
        # Installer
        self.installer_url: str = data.get("installer_url", "")
        self.installer_sha256: str = data.get("installer_sha256", "")
        self.installer_filename: str = data.get("installer_filename", "")
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
    """Background thread to download an update payload (ZIP or installer)."""
    
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
    download_complete = Signal(str)     # Path to downloaded payload
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
        elif info.update_type == "installer":
            url = info.installer_url
            sha = info.installer_sha256
            filename = info.installer_filename or f"VEO_Pro_Max_Setup_v{info.version}.exe"
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

    @staticmethod
    def _launch_detached_powershell(script_path: str):
        """Launch a PowerShell helper that must survive parent exit."""
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [
                "powershell", "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-File", script_path,
            ],
            creationflags=DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            close_fds=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _pre_shutdown_cleanup(self):
        """Kill managed browser/process trees before a destructive update."""
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
    
    def apply_update(self, zip_path: str):
        """Apply FULL update: extract ZIP, create updater script, restart.
        
        Strategy (CLEAN UPDATE):
        1. Validate ZIP integrity (★ R5-1)
        2. Extract ZIP to temp folder
        3. Write PowerShell script that waits for exit, replaces app, restarts
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
                        # ★ R10-4: Clean up invalid ZIP
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
            
            # ★ R8-P4: Validate source_dir contains expected exe
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
                        log.info(f"Source exe found in subdirectory: {source_dir}")
                        break
                if not found:
                    log.error(f"Extracted ZIP does not contain {exe_name}")
                    self.download_error.emit(
                        f"ZIP không chứa {exe_name}\n"
                        f"Vui lòng tải lại bản cập nhật."
                    )
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    return
            
            # ★ E1: Write paths to JSON sidecar to prevent PowerShell injection
            ps1_path = os.path.join(tempfile.gettempdir(), "veo_updater.ps1")
            json_path = os.path.join(tempfile.gettempdir(), "veo_updater_paths.json")
            # ★ R9-P7: exe_name already defined at R8-P4 validation block above
            exe_full = os.path.join(app_dir, exe_name)
            pid = os.getpid()
            log_path = os.path.join(tempfile.gettempdir(), "veo_update.log")
            
            # Write all paths to JSON (no PS injection possible)
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
            
            ps1_content = f"""
$ErrorActionPreference = 'Continue'

# ★ R6: Global error trap — catches silent PS1 crashes
trap {{
    $ts = Get-Date -Format 'HH:mm:ss'
    "$ts UNHANDLED ERROR: $_" | Out-File -Append -FilePath $cfg.logFile -Encoding utf8
    "$ts   At line: $($_.InvocationInfo.ScriptLineNumber)" | Out-File -Append -FilePath $cfg.logFile -Encoding utf8
    continue
}}

# ★ E1+R5-5: Read paths from JSON sidecar (injection-safe, here-string)
$jsonPath = @'
{json_path}
'@
$cfg = Get-Content -Path $jsonPath -Raw -Encoding utf8 | ConvertFrom-Json
$logFile  = $cfg.logFile

function Log($msg) {{
    $ts = Get-Date -Format 'HH:mm:ss'
    "$ts $msg" | Out-File -Append -FilePath $logFile -Encoding utf8
    Write-Host $msg
}}

Log '=== VEO Pro Max Clean Updater ==='

# ★ R7: Write start marker — proves PS1 launched
$markerFile = Join-Path $env:TEMP 'veo_update_marker.txt'
"started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath $markerFile -Encoding utf8
Log 'Marker: started'

Log 'Waiting for app to exit...'

# ★ R7: Improved WaitForExit — 60s timeout + process name fallback
try {{
    $proc = Get-Process -Id $cfg.pid -ErrorAction SilentlyContinue
    if ($proc) {{
        $exited = $proc.WaitForExit(60000)
        if ($exited) {{ Log 'App process exited (by PID).' }}
        else {{ Log 'WARNING: App did not exit within 60s — continuing anyway' }}
    }} else {{
        Log 'App process already exited (PID not found).'
    }}
}} catch {{
    Log "WaitForExit error: $_ — trying by name..."
}}

# ★ R7: Fallback — wait for any VEO_Pro_Max.exe to exit (covers PID reuse edge case)
$exeName = Split-Path $cfg.exePath -Leaf
$exeBaseName = [IO.Path]::GetFileNameWithoutExtension($exeName)
for ($w = 0; $w -lt 10; $w++) {{
    $still = Get-Process -Name $exeBaseName -ErrorAction SilentlyContinue
    if (-not $still) {{ break }}
    Log "App still running (by name '$exeBaseName'), waiting 2s... ($($w+1)/10)"
    Start-Sleep -Seconds 2
}}

# ★ R8-P1: Force-kill if STILL running after wait loop (prevents locked exe)
$still = Get-Process -Name $exeBaseName -ErrorAction SilentlyContinue
if ($still) {{
    Log "FORCE KILLING $exeBaseName (still running after 20s wait)"
    & taskkill /F /IM $exeName 2>&1 | Out-Null
    Start-Sleep -Seconds 3
    Log 'Force kill done.'
}} else {{
    # Extra safety wait for file handles to release
    Start-Sleep -Seconds 3
}}

# ★ FIX R5: Kill orphan Chrome processes using our browser profiles
# Chrome spawns ~10 child processes (renderer, GPU, utility, crashpad)
# taskkill /T /F kills entire process TREE — not just main PID
Log 'Killing orphan Chrome processes...'
$profilesDirs = @()
$profilesDir1 = Join-Path $env:USERPROFILE '.veoauto\browser_profiles'
$profilesDir2 = Join-Path $cfg.appDir 'config\browser_profiles'
if (Test-Path $profilesDir1) {{ $profilesDirs += $profilesDir1 }}
if (Test-Path $profilesDir2) {{ $profilesDirs += $profilesDir2 }}
$chromeKilled = 0
foreach ($profilesDir in $profilesDirs) {{
    Log "Scanning $profilesDir for Chrome PID files..."
    Get-ChildItem -Path $profilesDir -Filter '.chrome_pid.json' -Recurse -Force | ForEach-Object {{
        try {{
            $pidData = Get-Content $_.FullName -Raw -Encoding utf8 | ConvertFrom-Json
            $chromePid = $pidData.pid
            $chromeProc = Get-Process -Id $chromePid -ErrorAction SilentlyContinue
            if ($chromeProc -and $chromeProc.Name -match 'chrome') {{
                # taskkill /T = tree kill (parent + all children)
                & taskkill /T /F /PID $chromePid 2>&1 | Out-Null
                $chromeKilled++
                Log "Killed Chrome tree PID=$chromePid"
            }}
        }} catch {{
            Log "Chrome kill warning: $_"
        }}
    }}
}}

# ★ FIX R5: Nuclear fallback — kill ANY chrome.exe using our browser_profiles
# Catches Chrome processes not tracked by PID files (orphaned children, relaunched instances)
foreach ($profilesDir in $profilesDirs) {{
    Get-Process -Name 'chrome' -ErrorAction SilentlyContinue | Where-Object {{
        try {{
            $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
            $cmdLine -and ($cmdLine -match [regex]::Escape($profilesDir))
        }} catch {{ $false }}
    }} | ForEach-Object {{
        & taskkill /T /F /PID $_.Id 2>&1 | Out-Null
        $chromeKilled++
        Log "Nuclear: killed chrome.exe PID=$($_.Id)"
    }}
}}

# ★ FIX R5: Kill orphan node.exe from Playwright driver
# Playwright spawns node.exe that holds locks on playwright/ package directory
$appDir = $cfg.appDir
Get-Process -Name 'node' -ErrorAction SilentlyContinue | Where-Object {{
    try {{ $_.MainModule.FileName -like "$appDir*" }} catch {{ $false }}
}} | ForEach-Object {{
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    Log "Killed orphan node.exe PID=$($_.Id)"
}}

if ($profilesDirs.Count -eq 0) {{
    Log 'No browser_profiles dir found — skipping Chrome cleanup.'
}} else {{
    Start-Sleep -Seconds 2
    Log "Chrome cleanup done ($chromeKilled killed)."
}}

$appDir   = $cfg.appDir
$srcDir   = $cfg.srcDir
$exePath  = $cfg.exePath
$zipPath  = $cfg.zipPath
$extrDir  = $cfg.extrDir

# ★ R6: Validate source directory BEFORE any file operations
Log "Source dir: $srcDir"
Log "App dir:    $appDir"
Log "Exe path:   $exePath"
$srcCount = (Get-ChildItem $srcDir -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object).Count
Log "Source file count: $srcCount"
if ($srcCount -eq 0) {{
    Log 'FATAL: Source directory is EMPTY — aborting update!'
    exit 1
}}
$srcExe = Get-ChildItem -Path $srcDir -Filter '*.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
if ($srcExe) {{ Log "Source exe: $($srcExe.Name) ($([math]::Round($srcExe.Length / 1MB, 1)) MB)" }}
else {{ Log 'WARNING: No .exe found in source directory!' }}

# ★ R7: Rename-trick — Windows allows renaming a running exe!
# Rename old exe to .bak BEFORE robocopy → new exe writes without lock conflict
$exeFile = Join-Path $appDir (Split-Path $exePath -Leaf)
$exeBak = "$exeFile.old_bak"
if (Test-Path $exeFile) {{
    try {{
        # Remove old .bak if exists from previous failed update
        if (Test-Path $exeBak) {{ Remove-Item $exeBak -Force -ErrorAction SilentlyContinue }}
        Rename-Item -Path $exeFile -NewName (Split-Path $exeBak -Leaf) -Force -ErrorAction Stop
        Log "Exe renamed to .old_bak (rename-trick success)"
    }} catch {{
        Log "Exe rename failed: $_ — will try overwrite via robocopy"
        # Fallback: wait until exe is unlocked (max 15s)
        for ($i = 0; $i -lt 5; $i++) {{
            try {{
                [IO.File]::Open($exeFile, 'Open', 'ReadWrite', 'None').Close()
                Log 'Exe file is unlocked.'
                break
            }} catch {{
                Log "Exe still locked (attempt $($i+1)/5), waiting 3s..."
                Start-Sleep -Seconds 3
            }}
        }}
    }}
}} else {{
    Log 'Old exe not found — fresh install.'
}}

# CLEAN UPDATE: Delete old app → Copy new
Log 'Removing file protections...'
Get-ChildItem -Path $appDir -Recurse -Force -ErrorAction SilentlyContinue |
    ForEach-Object {{
        try {{ $_.Attributes = 'Normal' }} catch {{}}
    }}

# ★ Rule #11: Backup tools/ BEFORE delete (FFmpeg ~200MB, survives updates)
$toolsDir = Join-Path $appDir 'tools'
$toolsBackup = Join-Path $env:TEMP 'veo_tools_backup'
$toolsBackedUp = $false
if (Test-Path $toolsDir) {{
    Log 'Backing up tools/ directory...'
    if (Test-Path $toolsBackup) {{ Remove-Item $toolsBackup -Recurse -Force -ErrorAction SilentlyContinue }}
    try {{
        Copy-Item $toolsDir $toolsBackup -Recurse -Force -ErrorAction Stop
        $toolsBackedUp = $true
        $itemCount = (Get-ChildItem $toolsBackup -Recurse -File | Measure-Object).Count
        Log "Tools backed up ($itemCount files)"
    }} catch {{
        Log "Tools backup failed: $_ — will rely on auto-download"
    }}
}}

Log 'Deleting old app folder...'
$deleteOk = $false
try {{
    Remove-Item -Path $appDir -Recurse -Force -ErrorAction Stop
    $deleteOk = $true
    Log 'Old app folder deleted.'
}} catch {{
    Log "Delete failed: $_ — trying item-by-item..."
    # Delete files deepest-first, then directories
    Get-ChildItem -Path $appDir -Recurse -Force -ErrorAction SilentlyContinue |
        Sort-Object {{ $_.FullName.Length }} -Descending |
        ForEach-Object {{ try {{ Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }} catch {{}} }}
    try {{ Remove-Item -Path $appDir -Force -ErrorAction SilentlyContinue; $deleteOk = $true }} catch {{}}
    if (-not $deleteOk) {{
        Log 'WARNING: Could not fully delete old folder — will overwrite'
        # ★ R6: Log what files survived deletion
        $remaining = Get-ChildItem -Path $appDir -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object {{ -not $_.PSIsContainer }} | Select-Object -First 20
        foreach ($rem in $remaining) {{
            Log "  STILL EXISTS: $($rem.FullName) ($($rem.Length) bytes)"
        }}
    }}
}}

Log "Copying new files from $srcDir to $appDir ..."
New-Item -Path $appDir -ItemType Directory -Force | Out-Null
# ★ FIX R2: Use robocopy /MIR as PRIMARY — handles merge, overwrites, AND stale cleanup
# /MIR = mirror mode (/E + /PURGE) — deletes stale files in destination
# ★ R8-P3: Use full path for /XD to avoid excluding nested 'tools' dirs
# /R:2 /W:1 = retry locked files 2 times with 1s wait
$toolsExclude = Join-Path $appDir 'tools'
Log 'Using robocopy mirror...'
# ★ R6: Log robocopy output instead of suppressing (critical for diagnosis)
$roboLog = & robocopy $srcDir $appDir /MIR /IS /IT /R:2 /W:1 /XD $toolsExclude 2>&1
$roboLog | Out-File -Append -FilePath $logFile -Encoding utf8
$roboExit = $LASTEXITCODE
if ($roboExit -le 7) {{
    # ★ R9-P9: Exit codes 4-7 indicate partial mismatches — log as warning
    if ($roboExit -ge 4) {{
        Log "WARNING: Robocopy partial mismatch (exit=$roboExit) — some files may not have copied correctly"
    }} else {{
        Log "Robocopy completed (exit=$roboExit)."
    }}
    $deleteOk = $true
}} else {{
    Log "Robocopy had errors (exit=$roboExit) — falling back to Copy-Item..."
    try {{
        Copy-Item -Path (Join-Path $srcDir '*') -Destination $appDir -Recurse -Force -ErrorAction Stop
        Log 'Copy-Item fallback done.'
    }} catch {{
        Log "Copy-Item also failed: $_"
    }}
    # ★ R8-P2: Purge stale files not present in source (Copy-Item has no /PURGE)
    Log 'Purging stale files from destination...'
    $purgedCount = 0
    Get-ChildItem -Path $appDir -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {{
        $rel = $_.FullName.Substring($appDir.Length + 1)
        $srcPath = Join-Path $srcDir $rel
        if (-not (Test-Path $srcPath)) {{
            # Skip tools/ dir (managed separately)
            if (-not $rel.StartsWith('tools\')) {{
                Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
                $purgedCount++
            }}
        }}
    }}
    Log "Purged $purgedCount stale files."
}}

# ★ R6: Post-copy verification — compare file counts
$dstCount = (Get-ChildItem $appDir -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object).Count
Log "Destination file count after copy: $dstCount (source had: $srcCount)"
$dstExe = Join-Path $appDir (Split-Path $exePath -Leaf)
if (Test-Path $dstExe) {{
    $exeSize = [math]::Round((Get-Item $dstExe).Length / 1MB, 1)
    Log "Destination exe: $dstExe ($exeSize MB)"
}} else {{
    Log "CRITICAL: Exe NOT found in destination after copy: $dstExe"
}}

# ★ R7: Compare version.json — definitive proof update content is correct
$srcVer = Join-Path $srcDir 'version.json'
$dstVer = Join-Path $appDir 'version.json'
if ((Test-Path $srcVer) -and (Test-Path $dstVer)) {{
    $sv = (Get-Content $srcVer -Raw -Encoding utf8 | ConvertFrom-Json).version
    $dv = (Get-Content $dstVer -Raw -Encoding utf8 | ConvertFrom-Json).version
    if ($sv -eq $dv) {{ Log "Version match: $sv ✓" }}
    else {{ Log "VERSION MISMATCH! Source=$sv Dest=$dv — update may have failed" }}
}} elseif (Test-Path $srcVer) {{
    Log 'WARNING: version.json exists in source but NOT in destination'
}}

# ★ R7: Clean up .old_bak exe (safe now — process has exited)
if (Test-Path $exeBak) {{
    Remove-Item $exeBak -Force -ErrorAction SilentlyContinue
    Log 'Cleaned up .old_bak exe'
}}

# ★ Rule #11: Restore tools/ from backup (merge — keep new version if ZIP already bundles)
if ($toolsBackedUp) {{
    $newTools = Join-Path $appDir 'tools'
    if (-not (Test-Path (Join-Path $newTools 'ffmpeg' 'ffmpeg.exe'))) {{
        # New ZIP does NOT bundle FFmpeg → restore full backup
        Log 'Restoring tools/ from backup (new ZIP has no FFmpeg)...'
        if (Test-Path $newTools) {{ Remove-Item $newTools -Recurse -Force -ErrorAction SilentlyContinue }}
        try {{
            Copy-Item $toolsBackup $newTools -Recurse -Force -ErrorAction Stop
            Log 'Tools restored successfully.'
        }} catch {{
            Log "Tools restore failed: $_ — FFmpeg will auto-download on next launch"
        }}
    }} else {{
        Log 'New ZIP already bundles FFmpeg — using new version.'
    }}
    # Cleanup backup
    Remove-Item $toolsBackup -Recurse -Force -ErrorAction SilentlyContinue
}}

# Re-hide runtime files
Log 'Hiding runtime files...'
$hidePatterns = @('*.dll', '*.pyd')
$hideDirs = @('PySide6', 'certifi', 'aiohttp', 'playwright', 'charset_normalizer',
              'multidict', 'yarl', 'frozenlist', 'aiosignal', 'markupsafe')

foreach ($pat in $hidePatterns) {{
    Get-ChildItem -Path $appDir -Filter $pat -File -ErrorAction SilentlyContinue |
        ForEach-Object {{
            try {{ $_.Attributes = 'Hidden','System' }} catch {{}}
        }}
}}
foreach ($d in $hideDirs) {{
    $dp = Join-Path $appDir $d
    if (Test-Path $dp) {{
        try {{ (Get-Item $dp -Force).Attributes = 'Hidden','System' }} catch {{}}
    }}
}}

# ★ FIX: Verify new exe exists before restart
if (-not (Test-Path $exePath)) {{
    Log "FATAL: New exe not found at $exePath — update FAILED!"
    # Try to find exe in appDir
    $foundExe = Get-ChildItem -Path $appDir -Filter '*.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($foundExe) {{
        $exePath = $foundExe.FullName
        Log "Found alternate exe: $exePath"
    }} else {{
        Log 'No exe found — cannot restart. Manual intervention needed.'
        exit 1
    }}
}}

# Cleanup
Log 'Cleaning up temp files...'
Remove-Item -Path $extrDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue
# ★ R4-2: Remove JSON sidecar (contains full paths)
Remove-Item -Path $jsonPath -Force -ErrorAction SilentlyContinue

# ★ R7: Write completion marker — proves PS1 ran to the end
"completed $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath $markerFile -Encoding utf8
Log 'Marker: completed'

# Restart
Log "Starting: $exePath"
Start-Process -FilePath $exePath -WorkingDirectory $appDir
Log 'App restarted. Clean update complete!'

Start-Sleep -Seconds 2
Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
            
            with open(ps1_path, "w", encoding="utf-8") as f:
                f.write(ps1_content)
            
            # Launch updater PowerShell script and exit
            log.info(f"Launching updater: {ps1_path}")
            self._launch_detached_powershell(ps1_path)
            
            # ★ R8-P0: Clear pending marker AFTER Popen succeeds
            # Keep payload until helper script consumes it.
            self.clear_pending_update(keep_payload=True)
            
            self.update_applied.emit()
            
            # ★ FIX R3: Kill all Chrome processes BEFORE exit
            # os._exit() bypasses closeEvent() → Chrome kill in app.py never runs
            # Chrome holds locks on DLLs, .pyd, extension/ files → PS1 Remove-Item fails
            self._pre_shutdown_cleanup()
            
            # Exit the app (3s delay for Chrome kill + file handle release)
            QTimer.singleShot(3000, lambda: os._exit(0))
            
        except Exception as e:
            log.error(f"Failed to apply update: {e}")
            # ★ R13-4: Clean up extract_dir on failure
            if 'extract_dir' in locals():
                shutil.rmtree(extract_dir, ignore_errors=True)
            self.download_error.emit(f"Apply failed: {e}")

    def apply_installer_update(self, installer_path: str):
        """Apply a downloaded installer silently into the current app directory."""
        if getattr(self, '_applying_update', False):
            log.warning("apply_installer_update already in progress — ignoring duplicate call")
            return
        self._applying_update = True
        try:
            installer_file = Path(installer_path)
            if not installer_file.exists():
                self.download_error.emit(f"Installer not found: {installer_path}")
                self._applying_update = False
                return

            app_dir = self._get_app_dir()
            exe_path = os.path.join(app_dir, os.path.basename(sys.executable))
            ps1_path = os.path.join(tempfile.gettempdir(), "veo_installer_updater.ps1")
            json_path = os.path.join(tempfile.gettempdir(), "veo_installer_paths.json")
            log_path = os.path.join(tempfile.gettempdir(), "veo_installer_update.log")
            paths_data = {
                "appDir": app_dir,
                "exePath": exe_path,
                "installerPath": str(installer_file),
                "logFile": log_path,
                "pid": os.getpid(),
            }
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(paths_data, jf, ensure_ascii=False)

            ps1_content = f"""
$ErrorActionPreference = 'Stop'
$jsonPath = @'
{json_path}
'@
$cfg = Get-Content -Path $jsonPath -Raw -Encoding utf8 | ConvertFrom-Json
$logFile = $cfg.logFile

function Log($msg) {{
    $ts = Get-Date -Format 'HH:mm:ss'
    "$ts $msg" | Out-File -Append -FilePath $logFile -Encoding utf8
}}

Log '=== VEO Pro Max Installer Updater ==='

try {{
    $proc = Get-Process -Id $cfg.pid -ErrorAction SilentlyContinue
    if ($proc) {{
        $null = $proc.WaitForExit(60000)
    }}
}} catch {{
    Log "WaitForExit warning: $_"
}}

$exeName = Split-Path $cfg.exePath -Leaf
try {{
    & taskkill /F /IM $exeName /T 2>&1 | Out-Null
}} catch {{}}
Start-Sleep -Seconds 2

$setupLog = Join-Path $env:TEMP 'veo_setup_silent.log'
$args = @(
    '/SP-',
    '/VERYSILENT',
    '/SUPPRESSMSGBOXES',
    '/NORESTART',
    "/DIR=$($cfg.appDir)",
    "/LOG=$setupLog"
)

Log "Launching installer: $($cfg.installerPath)"
$setup = Start-Process -FilePath $cfg.installerPath -ArgumentList $args -PassThru -Wait
Log "Installer exit code: $($setup.ExitCode)"
if ($setup.ExitCode -ne 0) {{
    exit $setup.ExitCode
}}

if (Test-Path $cfg.installerPath) {{
    Remove-Item -Path $cfg.installerPath -Force -ErrorAction SilentlyContinue
}}
Remove-Item -Path $jsonPath -Force -ErrorAction SilentlyContinue

if (-not (Test-Path $cfg.exePath)) {{
    Log "ERROR: Installed exe not found at $($cfg.exePath)"
    exit 1
}}

Log "Restarting app: $($cfg.exePath)"
Start-Process -FilePath $cfg.exePath -WorkingDirectory $cfg.appDir
Start-Sleep -Seconds 2
Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
            with open(ps1_path, "w", encoding="utf-8") as f:
                f.write(ps1_content)

            log.info(f"Launching installer updater: {ps1_path}")
            self._launch_detached_powershell(ps1_path)
            self.clear_pending_update(keep_payload=True)
            self.update_applied.emit()
            self._pre_shutdown_cleanup()
            QTimer.singleShot(1500, lambda: os._exit(0))

        except Exception as e:
            log.error(f"Failed to apply installer update: {e}")
            self._applying_update = False
            self.download_error.emit(f"Installer apply failed: {e}")
    
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
    
    def save_pending_update(
        self,
        zip_path: str,
        version: str,
        sha256: str = "",
        update_type: str = "full",
    ):
        """Save a pending update payload for deferred install on next startup.
        
        Copies the payload to ~/.veoauto/updates/ (persistent across reboots).
        Cleans up any existing pending update before saving new one.
        """
        try:
            # Copy payload to persistent location (temp may be cleaned)
            updates_dir = PENDING_UPDATE_FILE.parent / "updates"
            updates_dir.mkdir(parents=True, exist_ok=True)
            
            persistent_zip = updates_dir / Path(zip_path).name
            shutil.copy2(zip_path, str(persistent_zip))
            log.info(f"Copied update payload to persistent location: {persistent_zip}")
            
            # ★ R17-4+R12-1: Clear old pending AFTER copy succeeds, but skip
            # deleting old ZIP if it's the same path (same-version re-defer)
            try:
                if PENDING_UPDATE_FILE.exists():
                    old_data = json.loads(PENDING_UPDATE_FILE.read_text(encoding='utf-8'))
                    old_zip = old_data.get("package_path") or old_data.get("zip_path", "")
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
                "package_path": str(persistent_zip),
                "zip_path": str(persistent_zip),
                "update_type": update_type,
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
    def clear_pending_update(keep_payload: bool = False):
        """Remove pending update marker and optionally its stored payload."""
        try:
            if PENDING_UPDATE_FILE.exists():
                if not keep_payload:
                    # Also delete the stored payload file
                    try:
                        data = json.loads(PENDING_UPDATE_FILE.read_text(encoding='utf-8'))
                        zip_path = data.get("package_path") or data.get("zip_path", "")
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
            zip_path = data.get("package_path") or data.get("zip_path", "")
            
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
            # ★ R10-1: App version changed (or below minimum) → full ZIP or installer
            if below_min and info.installer_url:
                info.update_type = "installer"
            else:
                info.update_type = "full"
            reason = f" [BELOW MIN v{info.min_version}]" if below_min else ""
            log.info(
                f"{info.update_type.title()} update available: app v{current_app}→v{info.version}, "
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
