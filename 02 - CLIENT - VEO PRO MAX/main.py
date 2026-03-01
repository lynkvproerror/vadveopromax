#!/usr/bin/env python3
"""
VEO Pro Max - Entry Point (PySide6)
Version: 2.0.0
"""

import sys
import logging
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


def main():
    """Main entry point for VEO Pro Max application."""
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
        app.setApplicationVersion("2.0.0")
        
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
            splash.set_status(f"License: {role}")
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


if __name__ == "__main__":
    main()
