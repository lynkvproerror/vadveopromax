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
import zipfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer, QThread

log = logging.getLogger(__name__)


def _create_ssl_context():
    """Create SSL context with certifi fallback for Nuitka-compiled apps."""
    import ssl
    try:
        ctx = ssl.create_default_context()
        if ctx.get_ca_certs():
            return ctx
    except Exception:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    log.warning("SSL: Using unverified context (certifi not available)")
    return ctx


# GitHub raw URL for version manifest
GITHUB_REPO = "lynkvproerror/vadveopromax"
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.json"
UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000  # 30 minutes
PENDING_UPDATE_FILE = Path.home() / ".veoauto" / "pending_update.json"


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


def get_local_extension_version() -> str:
    """Read extension version from bundled extension/manifest.json."""
    try:
        if getattr(sys, "frozen", False):
            ext_manifest = Path(os.path.dirname(sys.executable)) / "extension" / "manifest.json"
        else:
            ext_manifest = Path(__file__).parent.parent / "extension" / "manifest.json"
        
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
        try:
            import urllib.request
            
            ctx = _create_ssl_context()
            req = urllib.request.Request(
                VERSION_URL,
                headers={"User-Agent": "VEO-Pro-Max-Updater/2.0"}
            )
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            info = UpdateInfo(data)
            self.finished.emit(info)
            
        except Exception as e:
            log.debug(f"Update check failed: {e}")
            self.error.emit(str(e))


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
            
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
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
        
        # Disconnect old worker signals to prevent accumulation
        if self._check_worker is not None:
            try:
                self._check_worker.finished.disconnect()
                self._check_worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass
        
        self._check_worker = UpdateCheckWorker()
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
        
        # Disconnect old worker signals
        if self._download_worker is not None:
            try:
                self._download_worker.progress.disconnect()
                self._download_worker.finished.disconnect()
                self._download_worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass
        
        self._download_worker = UpdateDownloadWorker(
            url=url, sha256=sha, filename=filename
        )
        self._download_worker.progress.connect(self.download_progress.emit)
        self._download_worker.finished.connect(self._on_download_complete)
        self._download_worker.error.connect(self.download_error.emit)
        self._download_worker.start()
    
    def apply_update(self, zip_path: str):
        """Apply FULL update: extract ZIP, create updater script, restart.
        
        Strategy (CLEAN UPDATE):
        1. Extract ZIP to temp folder
        2. Write PowerShell script that waits for exit, replaces app, restarts
        3. Exit current app
        """
        try:
            app_dir = self._get_app_dir()
            extract_dir = tempfile.mkdtemp(prefix="veo_extract_")
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            
            # Find root of extracted content
            extracted_items = os.listdir(extract_dir)
            if len(extracted_items) == 1 and os.path.isdir(
                os.path.join(extract_dir, extracted_items[0])
            ):
                source_dir = os.path.join(extract_dir, extracted_items[0])
            else:
                source_dir = extract_dir
            
            # Create updater PowerShell script
            ps1_path = os.path.join(tempfile.gettempdir(), "veo_updater.ps1")
            exe_name = os.path.basename(sys.executable)
            exe_full = os.path.join(app_dir, exe_name)
            pid = os.getpid()
            log_path = os.path.join(tempfile.gettempdir(), "veo_update.log")
            
            ps1_content = f"""
$ErrorActionPreference = 'Continue'
$logFile = '{log_path.replace(chr(39), chr(39)+chr(39))}'

function Log($msg) {{
    $ts = Get-Date -Format 'HH:mm:ss'
    "$ts $msg" | Out-File -Append -FilePath $logFile -Encoding utf8
    Write-Host $msg
}}

Log '=== VEO Pro Max Clean Updater ==='
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

# CLEAN UPDATE: Delete old app → Copy new
Log 'Removing file protections...'
Get-ChildItem -Path $appDir -Recurse -Force -ErrorAction SilentlyContinue |
    ForEach-Object {{
        try {{ $_.Attributes = 'Normal' }} catch {{}}
    }}

Log 'Deleting old app folder...'
try {{
    Remove-Item -Path $appDir -Recurse -Force -ErrorAction Stop
    Log 'Old app folder deleted.'
}} catch {{
    Log "Delete failed: $_ — trying item-by-item..."
    Get-ChildItem -Path $appDir -Recurse -Force -ErrorAction SilentlyContinue |
        Sort-Object {{ $_.FullName.Length }} -Descending |
        ForEach-Object {{ try {{ Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }} catch {{}} }}
    try {{ Remove-Item -Path $appDir -Force -ErrorAction SilentlyContinue }} catch {{}}
}}

Log "Copying new files from $srcDir to $appDir ..."
New-Item -Path $appDir -ItemType Directory -Force | Out-Null
try {{
    Copy-Item -Path (Join-Path $srcDir '*') -Destination $appDir -Recurse -Force -ErrorAction Stop
    Log 'Copy completed successfully.'
}} catch {{
    Log "Copy-Item failed: $_"
    Log 'Trying robocopy fallback...'
    & robocopy $srcDir $appDir /E /IS /IT /NFL /NDL /NJH /NJS 2>&1 | Out-Null
    Log 'Robocopy fallback done.'
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

# Cleanup
Log 'Cleaning up temp files...'
Remove-Item -Path $extrDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue

# Restart
Log "Starting: $exePath"
Start-Process -FilePath $exePath -WorkingDirectory $appDir
Log 'App restarted. Clean update complete!'

Start-Sleep -Seconds 2
Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
            
            with open(ps1_path, "w", encoding="utf-8") as f:
                f.write(ps1_content)
            
            # Clear any pending update marker
            self.clear_pending_update()
            
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
            
            # Exit the app
            QTimer.singleShot(500, lambda: os._exit(0))
            
        except Exception as e:
            log.error(f"Failed to apply update: {e}")
            self.download_error.emit(f"Apply failed: {e}")
    
    def apply_extension_update(self, zip_path: str):
        """Hot-replace extension/ folder only. NO restart needed.
        
        Handles Chrome file locks with retry logic.
        """
        try:
            app_dir = self._get_app_dir()
            ext_dir = os.path.join(app_dir, "extension")
            extract_dir = tempfile.mkdtemp(prefix="veo_ext_update_")
            
            # Extract
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            
            # Source: extracted/extension/ or extracted/ 
            src_ext = os.path.join(extract_dir, "extension")
            if not os.path.isdir(src_ext):
                src_ext = extract_dir
            
            # Replace extension folder (retry for Chrome file locks)
            import time
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if os.path.isdir(ext_dir):
                        shutil.rmtree(ext_dir)  # NO ignore_errors — catch the exception
                    break
                except PermissionError:
                    if attempt < max_retries - 1:
                        log.warning(f"Extension files locked (attempt {attempt+1}/{max_retries}), retrying in 2s...")
                        time.sleep(2)
                    else:
                        log.warning("Extension files locked — force overwriting individual files")
                        # Fallback: overwrite files individually
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
            else:
                # All retries used the fallback path, skip copytree
                pass
            
            # Only copytree if rmtree succeeded (ext_dir doesn't exist)
            if not os.path.isdir(ext_dir):
                shutil.copytree(src_ext, ext_dir)
            
            # Cleanup
            shutil.rmtree(extract_dir, ignore_errors=True)
            try:
                os.unlink(zip_path)
            except Exception:
                pass
            
            log.info("Extension hot-updated successfully (no restart needed)")
            self.ext_update_applied.emit()
            
        except Exception as e:
            log.error(f"Extension update failed: {e}")
            self.download_error.emit(f"Extension update failed: {e}")
    
    # ── Pending Update (defer full update to next startup) ──
    
    def save_pending_update(self, zip_path: str, version: str):
        """Save pending update marker for deferred full update.
        
        Copies ZIP to ~/.veoauto/updates/ (persistent across reboots).
        Cleans up any existing pending update before saving new one.
        """
        try:
            # Clean up any previously pending update first (prevent orphaned ZIPs)
            self.clear_pending_update()
            
            # Copy ZIP to persistent location (temp may be cleaned)
            updates_dir = PENDING_UPDATE_FILE.parent / "updates"
            updates_dir.mkdir(parents=True, exist_ok=True)
            
            persistent_zip = updates_dir / Path(zip_path).name
            shutil.copy2(zip_path, str(persistent_zip))
            log.info(f"Copied update ZIP to persistent location: {persistent_zip}")
            
            # Clean up original temp file
            try:
                os.unlink(zip_path)
                parent = os.path.dirname(zip_path)
                if parent and os.path.basename(parent).startswith("veo_update_"):
                    shutil.rmtree(parent, ignore_errors=True)
            except Exception:
                pass
            
            data = {
                "zip_path": str(persistent_zip),
                "update_type": "full",
                "version": version,
                "saved_at": __import__('datetime').datetime.now().isoformat(),
            }
            PENDING_UPDATE_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            log.info(f"Pending update saved: v{version} → {persistent_zip}")
        except Exception as e:
            log.error(f"Failed to save pending update: {e}")
    
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
        
        if app_cmp < 0 or info.force_update:
            # App version changed (or server forced) → must do full update
            info.update_type = "full"
            log.info(
                f"Full update available: app v{current_app}→v{info.version}, "
                f"ext v{current_ext}→v{info.ext_version}"
                f"{' [FORCED]' if info.force_update else ''}"
            )
            self._latest_info = info
            self.update_available.emit(info)
        elif ext_cmp < 0:
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
    def _get_app_dir() -> str:
        """Get the application root directory."""
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        else:
            return str(Path(__file__).parent.parent)
