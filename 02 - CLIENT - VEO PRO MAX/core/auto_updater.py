"""
VEO Pro Max - Auto Updater

Checks GitHub for new versions, downloads updates, applies them,
and restarts the application.

GitHub Repo: https://github.com/lynkvproerror/vadveopromax
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal, QTimer, QThread

log = logging.getLogger(__name__)


# GitHub raw URL for version manifest
GITHUB_REPO = "lynkvproerror/vadveopromax"
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000  # 30 minutes


class UpdateInfo:
    """Parsed update information from version.json."""
    
    def __init__(self, data: dict):
        self.version: str = data.get("version", "0.0.0")
        self.release_date: str = data.get("release_date", "")
        self.changelog: str = data.get("changelog", "")
        self.download_url: str = data.get("download_url", "")
        self.sha256: str = data.get("sha256", "")
        self.min_version: str = data.get("min_version", "0.0.0")
        self.force_update: bool = data.get("force_update", False)
    
    def __repr__(self):
        return f"UpdateInfo(v{self.version}, force={self.force_update})"


def compare_versions(current: str, remote: str) -> int:
    """Compare semantic versions.
    
    Returns:
        -1 if current < remote (update available)
         0 if current == remote
         1 if current > remote
    """
    def parse(v: str):
        parts = v.replace("v", "").split(".")
        return tuple(int(p) for p in parts[:3])
    
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


class UpdateCheckWorker(QThread):
    """Background thread to check for updates (non-blocking)."""
    
    finished = Signal(object)  # UpdateInfo or None
    error = Signal(str)
    
    def run(self):
        try:
            import urllib.request
            import ssl
            
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                VERSION_URL,
                headers={"User-Agent": "VEO-Pro-Max-Updater/1.0"}
            )
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            info = UpdateInfo(data)
            self.finished.emit(info)
            
        except Exception as e:
            log.debug(f"Update check failed: {e}")
            self.error.emit(str(e))


class UpdateDownloadWorker(QThread):
    """Background thread to download update ZIP."""
    
    progress = Signal(int)      # 0-100 percentage
    finished = Signal(str)      # Path to downloaded file
    error = Signal(str)
    
    def __init__(self, url: str, sha256: str = ""):
        super().__init__()
        self.url = url
        self.expected_sha256 = sha256
    
    def run(self):
        try:
            import urllib.request
            import ssl
            import hashlib
            
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "VEO-Pro-Max-Updater/1.0"}
            )
            
            # Download to temp file
            tmp_dir = tempfile.mkdtemp(prefix="veo_update_")
            tmp_path = os.path.join(tmp_dir, "update.zip")
            
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                sha = hashlib.sha256()
                
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
                            self.progress.emit(min(pct, 99))
            
            # Verify SHA-256 if provided
            if self.expected_sha256:
                actual = sha.hexdigest()
                if actual.lower() != self.expected_sha256.lower():
                    self.error.emit(
                        f"SHA-256 mismatch!\n"
                        f"Expected: {self.expected_sha256[:16]}...\n"
                        f"Got: {actual[:16]}..."
                    )
                    return
            
            self.progress.emit(100)
            self.finished.emit(tmp_path)
            
        except Exception as e:
            log.error(f"Update download failed: {e}")
            self.error.emit(str(e))


class AutoUpdater(QObject):
    """Main auto-update controller.
    
    Usage:
        updater = AutoUpdater()
        updater.update_available.connect(on_update)
        updater.start_periodic_check()
    """
    
    # Signals
    update_available = Signal(object)   # UpdateInfo
    up_to_date = Signal()               # Already on latest version
    download_progress = Signal(int)     # 0-100
    download_complete = Signal(str)     # Path to ZIP
    download_error = Signal(str)
    update_applied = Signal()           # Ready to restart
    check_error = Signal(str)            # Version check error
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self.check_now)
        self._check_worker: Optional[UpdateCheckWorker] = None
        self._download_worker: Optional[UpdateDownloadWorker] = None
        self._latest_info: Optional[UpdateInfo] = None
    
    @property
    def latest_info(self) -> Optional[UpdateInfo]:
        return self._latest_info
    
    def start_periodic_check(self):
        """Start checking for updates every 30 minutes."""
        # Initial check after 10 seconds (let app fully load)
        QTimer.singleShot(10_000, self.check_now)
        self._check_timer.start(UPDATE_CHECK_INTERVAL_MS)
    
    def stop_periodic_check(self):
        self._check_timer.stop()
    
    def check_now(self):
        """Check for updates immediately (non-blocking)."""
        if self._check_worker and self._check_worker.isRunning():
            return  # Already checking
        
        self._check_worker = UpdateCheckWorker()
        self._check_worker.finished.connect(self._on_check_result)
        self._check_worker.error.connect(self._on_check_error)
        self._check_worker.start()
    
    def download_update(self, info: Optional[UpdateInfo] = None):
        """Download the update ZIP (non-blocking)."""
        info = info or self._latest_info
        if not info or not info.download_url:
            self.download_error.emit("No update URL available")
            return
        
        if self._download_worker and self._download_worker.isRunning():
            return  # Already downloading
        
        self._download_worker = UpdateDownloadWorker(
            url=info.download_url,
            sha256=info.sha256,
        )
        self._download_worker.progress.connect(self.download_progress.emit)
        self._download_worker.finished.connect(self._on_download_complete)
        self._download_worker.error.connect(self.download_error.emit)
        self._download_worker.start()
    
    def apply_update(self, zip_path: str):
        """Extract update ZIP and replace app files, then restart.
        
        Strategy:
        1. Extract ZIP to temp folder
        2. Write a small batch script that:
           a. Waits for this process to exit
           b. Copies new files over old ones
           c. Restarts the app
        3. Exit current app
        """
        try:
            app_dir = self._get_app_dir()
            extract_dir = tempfile.mkdtemp(prefix="veo_extract_")
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            
            # Find root of extracted content (might be nested in a folder)
            extracted_items = os.listdir(extract_dir)
            if len(extracted_items) == 1 and os.path.isdir(
                os.path.join(extract_dir, extracted_items[0])
            ):
                source_dir = os.path.join(extract_dir, extracted_items[0])
            else:
                source_dir = extract_dir
            
            # Create updater PowerShell script (handles special chars in paths)
            ps1_path = os.path.join(tempfile.gettempdir(), "veo_updater.ps1")
            exe_name = os.path.basename(sys.executable)
            exe_full = os.path.join(app_dir, exe_name)
            pid = os.getpid()
            log_path = os.path.join(tempfile.gettempdir(), "veo_update.log")
            
            # Use single-quoted strings in PS1 to avoid variable expansion issues
            # PowerShell single-quotes treat everything literally (no escaping needed)
            ps1_content = f"""
$ErrorActionPreference = 'Continue'
$logFile = '{log_path.replace(chr(39), chr(39)+chr(39))}'

function Log($msg) {{
    $ts = Get-Date -Format 'HH:mm:ss'
    "$ts $msg" | Out-File -Append -FilePath $logFile -Encoding utf8
    Write-Host $msg
}}

Log '=== VEO Pro Max Updater ==='
Log 'Waiting for app to exit...'

# Wait for the running app process to exit (by PID, max 30s)
try {{
    $proc = Get-Process -Id {pid} -ErrorAction SilentlyContinue
    if ($proc) {{
        $proc.WaitForExit(30000) | Out-Null
    }}
}} catch {{}}

# Extra safety wait
Start-Sleep -Seconds 2

$appDir   = '{app_dir.replace(chr(39), chr(39)+chr(39))}'
$srcDir   = '{source_dir.replace(chr(39), chr(39)+chr(39))}'
$exePath  = '{exe_full.replace(chr(39), chr(39)+chr(39))}'
$zipPath  = '{zip_path.replace(chr(39), chr(39)+chr(39))}'
$extrDir  = '{extract_dir.replace(chr(39), chr(39)+chr(39))}'

# Remove Hidden+System attributes so we can overwrite
Log 'Removing file protections...'
Get-ChildItem -Path $appDir -Recurse -Force -ErrorAction SilentlyContinue |
    ForEach-Object {{
        try {{ $_.Attributes = 'Normal' }} catch {{}}
    }}

# Copy new files over old ones
Log "Copying files from $srcDir to $appDir ..."
try {{
    Copy-Item -Path (Join-Path $srcDir '*') -Destination $appDir -Recurse -Force -ErrorAction Stop
    Log 'Copy completed successfully.'
}} catch {{
    Log "Copy-Item failed: $_"
    # Fallback: robocopy
    Log 'Trying robocopy fallback...'
    & robocopy $srcDir $appDir /E /IS /IT /NFL /NDL /NJH /NJS 2>&1 | Out-Null
    Log 'Robocopy fallback done.'
}}

# Re-hide runtime files (keep Explorer clean)
Log 'Restoring file protections...'
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

# Cleanup temp files
Log 'Cleaning up temp files...'
Remove-Item -Path $extrDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue

# Restart the app
Log "Starting: $exePath"
Start-Process -FilePath $exePath -WorkingDirectory $appDir
Log 'App restarted. Update complete!'

# Self-delete
Start-Sleep -Seconds 2
Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
            
            with open(ps1_path, "w", encoding="utf-8") as f:
                f.write(ps1_content)
            
            # Launch updater PowerShell script and exit
            log.info(f"Launching updater: {ps1_path}")
            subprocess.Popen(
                [
                    "powershell", "-ExecutionPolicy", "Bypass",
                    "-WindowStyle", "Hidden",
                    "-File", ps1_path,
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
            
            self.update_applied.emit()
            
            # Exit the app (main window should handle cleanup)
            QTimer.singleShot(500, lambda: os._exit(0))
            
        except Exception as e:
            log.error(f"Failed to apply update: {e}")
            self.download_error.emit(f"Apply failed: {e}")
    
    def _on_check_result(self, info: UpdateInfo):
        """Handle update check result."""
        from config.constants import AppConstants
        
        current = AppConstants.APP_VERSION
        cmp = compare_versions(current, info.version)
        
        if cmp < 0:
            # New version available
            log.info(f"Update available: v{current} → v{info.version}")
            self._latest_info = info
            self.update_available.emit(info)
        else:
            log.debug(f"App is up to date (v{current})")
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
    def _get_app_dir() -> str:
        """Get the application root directory."""
        if getattr(sys, "frozen", False):
            # PyInstaller/Nuitka bundled
            return os.path.dirname(sys.executable)
        else:
            # Running from source
            return str(Path(__file__).parent.parent)
