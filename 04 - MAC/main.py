#!/usr/bin/env python3
"""
VEO Pro Max - Entry Point (PySide6)
Version: 2.3.4
"""

import sys
import logging
import logging.handlers
import os
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set root logger to DEBUG so ALL log levels are captured by DevConsole.
# Previously INFO → log.debug() calls were invisible until DevConsole opened.
# NOTE: Do NOT use logging.basicConfig() here! It adds a StreamHandler(sys.stderr)
# which crashes after _StreamToLogger replaces sys.stderr later. The QtLogHandler
# (installed by DevConsole) handles all output display.
#
# Terminal StreamHandler: Shows INFO+ in terminal for visibility.
# DevConsole QtLogHandler: Shows DEBUG+ (attached later when DevConsole opens).
logging.getLogger().setLevel(logging.DEBUG)

# Add a simple StreamHandler for terminal output at INFO level
# This ensures critical info is visible in terminal even before DevConsole opens.
# _StreamToLogger will replace sys.stdout later, but this handler writes
# directly to the original stdout before that happens.
_terminal_handler = logging.StreamHandler(sys.stdout)
_terminal_handler.setLevel(logging.INFO)
_terminal_handler.setFormatter(logging.Formatter(
    "[%(levelname)-5s] %(asctime)s - %(name)s - %(message)s",
    datefmt="%H:%M:%S",
))
logging.getLogger().addHandler(_terminal_handler)

# In compiled mode (Nuitka/frozen), console is disabled.
# Add rotating file handler to capture all logs for debugging.
# RotatingFileHandler: 10 MB max, 2 backups → max 30 MB on disk.
if getattr(sys, 'frozen', False) or '__compiled__' in dir():
    _log_dir = Path.home() / ".veoauto"
    _log_dir.mkdir(parents=True, exist_ok=True)
    
    # Per-session log file with timestamp
    from datetime import datetime as _dt
    _session_ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    _file_handler = logging.handlers.RotatingFileHandler(
        _log_dir / f"veo_session_{_session_ts}.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=2,
        encoding='utf-8',
    )
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(logging.Formatter(
        "[%(levelname)-5s] %(asctime)s - %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    ))
    logging.getLogger().addHandler(_file_handler)
    
    # Cleanup old session logs (older than log_retention_days)
    try:
        import time as _time
        _retention_days = 7  # Default; settings not loaded yet at this point
        _cutoff = _time.time() - (_retention_days * 86400)
        for _old_log in _log_dir.glob("veo_session_*.log*"):
            try:
                if _old_log.stat().st_mtime < _cutoff:
                    _old_log.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _hide_runtime_files():
    """Hide runtime files in Finder (compiled mode only — macOS).
    
    Uses chflags hidden to hide files/folders that the user
    doesn't need to see. Only keeps app bundle + user-facing folders visible.
    Safe: does NOT move files.
    """
    import os
    import subprocess as sp
    
    exe_dir = Path(os.path.dirname(sys.executable))
    
    KEEP_VISIBLE = {
        "VEO Pro Max.app",
        "VEO_Pro_Max",  # Unix executable name
        "config",
        "assets",
        "data",
        "extension",
        "tools",  # FFmpeg bundled (Rule #11)
    }
    
    hidden = 0
    for item in exe_dir.iterdir():
        if item.name in KEEP_VISIBLE:
            continue
        try:
            sp.run(["chflags", "hidden", str(item)],
                   capture_output=True, check=False, timeout=5)
            hidden += 1
        except Exception:
            pass
    
    if hidden > 0:
        logging.getLogger(__name__).debug(
            f"[Startup] Hidden {hidden} runtime files in Finder"
        )


def main():
    """Main entry point for VEO Pro Max application."""
    # ── Hide runtime files in compiled mode (clean Explorer view) ──
    if getattr(sys, 'frozen', False) or '__compiled__' in dir():
        try:
            _hide_runtime_files()
        except Exception:
            pass  # Non-critical — don't block startup
    
    # ── Single Instance Lock: block duplicate app windows ──
    from core.single_instance import SingleInstanceLock, show_already_running_dialog
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        show_already_running_dialog()
        sys.exit(0)
    
    try:
        # ── Pre-UI: ensure PySide6 is installed (no splash yet) ──
        from core.dependency_checker import ensure_critical_deps
        ensure_critical_deps()
        
        # PySide6 imports
        from PySide6.QtWidgets import QApplication, QDialog
        from PySide6.QtCore import Qt
        
        # App imports
        from config.settings import AppSettings
        from config.theme import ThemeManager
        from core.app_controller import AppController
        from core.event_manager import get_event_manager
        from ui.app import MainWindow
        from ui.splash_screen import SplashScreen
        
        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("VEO Pro Max")
        app.setApplicationVersion("2.1.0")
        
        # Apply theme
        theme_manager = ThemeManager()
        theme_manager.apply_to_app(app)
        
        # ── Show splash immediately ──
        splash = SplashScreen()
        splash.show()
        app.processEvents()
        
        # ── Check & install missing dependencies (with splash progress) ──
        from core.dependency_checker import check_all_dependencies
        
        def _dep_callback(pct: int, status: str):
            """Map dependency progress (0-100) into splash auto-advance range."""
            # Dependency check uses the splash status text only
            # Auto-advance handles the progress bar (0→80%)
            splash.set_status(status)
            app.processEvents()
        
        check_all_dependencies(_dep_callback)
        
        # Auto-advance mode: splash auto-animates 0→80% on its own
        # We only update the status text at each init step
        splash.set_status("Loading settings...")
        
        # Load settings
        settings = AppSettings.load()
        
        # Initialize controller
        splash.set_status("Initializing engine...")
        controller = AppController(settings)
        
        # Connect controller's auto-launch progress to splash
        controller.set_splash_callback(splash.set_progress)
        
        # Initialize event manager
        splash.set_status("Starting event manager...")
        event_manager = get_event_manager()
        event_manager.start_processor()
        
        # ── License validation BEFORE starting services ──
        splash.set_status("Checking license...")
        print("[LICENSE] Startup license validation...")
        try:
            # 🔒 Force IMMEDIATE online check at startup (bypass 5-min cache)
            if hasattr(controller, '_license_client') and controller._license_client:
                lc = controller._license_client
                if hasattr(lc, 'validate_online_now'):
                    splash.set_status("Verifying license online...")
                    app.processEvents()
                    print("[LICENSE] Calling validate_online_now()...")
                    online_result = lc.validate_online_now()
                    print(f"[LICENSE] Online result: valid={online_result.valid}, error={getattr(online_result, 'error', None)}")
                    
                    if not online_result.valid:
                        # Key deleted/revoked on server → force invalid
                        controller._license_valid = False
                        print(f"[LICENSE] ⛔ Server says INVALID → blocking app")
                    else:
                        print(f"[LICENSE] ✅ Server confirmed valid")
                else:
                    print("[LICENSE] ⚠️ validate_online_now not found")
            else:
                print("[LICENSE] ⚠️ _license_client not available")
            
            controller._update_permissions()
            role = controller._permissions.role.value.upper()
            role_display = "ADMINISTRATOR" if role == "TESTER" else role
            splash.set_status(f"License: {role_display}")
            print(f"[LICENSE] Role={role}, _license_valid={controller._license_valid}")
            
            if role == "TRIAL":
                splash.set_status("License: TRIAL — limited features")
        except Exception as e:
            print(f"[LICENSE] ❌ Exception: {e}")
            controller._license_valid = False
            splash.set_status("License: TRIAL (default)")
        
        # ── License popup gate: block if invalid BEFORE launching anything ──
        if not controller._license_valid:
            splash.close()
            
            from ui.popups.license_popup import LicenseRequiredDialog
            
            # Get the error message from the last validation
            _license_error = ""
            try:
                info = controller._license_client.validate()
                _license_error = getattr(info, 'error', '') or ''
            except Exception:
                pass
            
            # Loop: keep showing dialog until valid key or explicit exit
            while not controller._license_valid:
                dlg = LicenseRequiredDialog(
                    parent=None,
                    controller=controller,
                    force_exit=True,
                    license_error=_license_error,
                )
                dlg.exec()
                # Re-validate after dialog closes
                controller._update_permissions()
        
        # Start controller (launches browsers, services) — only after license OK
        splash.set_status("Starting services...")
        controller.start()
        
        # Create main window
        splash.set_status("Building interface...")
        window = MainWindow(controller=controller, settings=settings)
        
        # ── Splash done ──
        splash.finish(window)
        
        # Run event loop
        exit_code = app.exec()
        
        # Cleanup
        controller.stop()
        event_manager.stop_processor()
        
        sys.exit(exit_code)
        
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Run: pip install PySide6")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        instance_lock.release()


if __name__ == "__main__":
    main()
