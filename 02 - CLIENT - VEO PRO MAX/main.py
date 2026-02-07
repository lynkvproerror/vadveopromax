#!/usr/bin/env python3
"""
VEO Pro Max - Entry Point (PySide6)
Version: 2.0.0
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    """Main entry point for VEO Pro Max application."""
    try:
        # PySide6 imports
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        
        # App imports
        from config.settings import AppSettings
        from config.theme import ThemeManager
        from core.app_controller import AppController
        from core.event_manager import get_event_manager
        from ui.app import MainWindow
        
        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("VEO Pro Max")
        app.setApplicationVersion("2.0.0")
        
        # Apply theme
        theme_manager = ThemeManager()
        theme_manager.apply_to_app(app)
        
        # Load settings
        settings = AppSettings.load()
        
        # Initialize controller
        controller = AppController(settings)
        
        # Initialize event manager
        event_manager = get_event_manager()
        event_manager.start_processor()
        
        # Start controller
        controller.start()
        
        # Create main window
        window = MainWindow(controller=controller, settings=settings)
        window.show()
        
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
