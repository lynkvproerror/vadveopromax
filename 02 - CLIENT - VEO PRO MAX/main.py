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

# Set root logger to INFO EARLY so all modules' log.info() calls are captured.
# Without this, Python defaults to WARNING and extension install logs are dropped.
# NOTE: Do NOT use logging.basicConfig() here! It adds a StreamHandler(sys.stderr)
# which crashes after _StreamToLogger replaces sys.stderr later. The QtLogHandler
# (installed by DevConsole) handles all output display.
logging.getLogger().setLevel(logging.INFO)


def main():
    """Main entry point for VEO Pro Max application."""
    try:
        # ── Pre-UI: ensure PySide6 is installed (no splash yet) ──
        from core.dependency_checker import ensure_critical_deps
        ensure_critical_deps()
        
        # PySide6 imports
        from PySide6.QtWidgets import QApplication
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
        
        # Start controller
        splash.set_status("Starting services...")
        controller.start()
        
        # Create main window (hidden for now, splash is visible)
        splash.set_status("Building interface...")
        window = MainWindow(controller=controller, settings=settings)
        
        # ── Splash done: close as soon as UI is built ──
        # Browsers will auto-launch in background via set_profiles_controller()
        # No need to wait for browser launch — user sees app immediately
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
