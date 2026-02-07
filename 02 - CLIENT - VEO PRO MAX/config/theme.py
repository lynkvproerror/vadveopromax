"""
VEO Pro Max - Unified SaaS Dark OLED Theme

Reference: CUSTOMTKINTER_STYLE_GUIDE.md, 00_DESIGN_SYSTEM.md
Color palette: Catppuccin Mocha (matching license_manager_gui.py)
"""


class Theme:
    """VEO Pro Max - Unified SaaS Dark OLED Theme
    
    This theme is designed for:
    - OLED displays (true black backgrounds)
    - Modern SaaS aesthetic
    - High contrast for readability
    - 8px grid system
    
    Color source: Catppuccin Mocha palette
    """
    
    # === BACKGROUNDS (Catppuccin Mocha) ===
    BASE = "#1E1E2E"        # Main window - Mocha Base
    MANTLE = "#181825"      # Darker than base
    CRUST = "#11111B"       # Darkest
    SURFACE0 = "#313244"    # Cards, Panels, Inputs
    SURFACE1 = "#45475A"    # Secondary bg
    SURFACE2 = "#585B70"    # Elevated, Dropdowns
    
    # === TEXT (High contrast) ===
    TEXT = "#CDD6F4"        # Primary text (Mocha Text)
    SUBTEXT0 = "#A6ADC8"    # Secondary text
    SUBTEXT1 = "#BAC2DE"    # Tertiary text
    OVERLAY0 = "#6C7086"    # Disabled/muted
    
    # === PRIMARY ACCENT (Blue) ===
    BLUE = "#89B4FA"        # Primary buttons (Mocha Blue)
    LAVENDER = "#B4BEFE"    # Hover state
    SAPPHIRE = "#74C7EC"    # Active/pressed state
    SKY = "#89DCFE"         # Info
    
    # === IMAGE ACCENT (Purple/Mauve) ===
    PURPLE = "#CBA6F7"      # Image generation tabs (Mocha Mauve)
    PURPLE_HOVER = "#DDB8FF"
    PURPLE_ACTIVE = "#B794F4"
    
    # === STATUS COLORS ===
    GREEN = "#A6E3A1"       # Success (Mocha Green)
    GREEN_BG = "#1E3A2F"    # Success background
    YELLOW = "#F9E2AF"      # Warning (Mocha Yellow)
    YELLOW_BG = "#3D3224"   # Warning background
    RED = "#F38BA8"         # Error (Mocha Red/Pink)
    RED_BG = "#3D2333"      # Error background
    PEACH = "#FAB387"       # Orange accent
    
    # === BORDERS (Visible) ===
    BORDER = "#45475A"      # Default border (Surface1 - visible!)
    BORDER_FOCUS = "#89B4FA"  # Focused input border (Blue)
    
    # === SPACING (8px Grid) ===
    SPACING_XS = 4
    SPACING_SM = 8
    SPACING_MD = 12
    SPACING_LG = 16
    SPACING_XL = 20
    SPACING_2XL = 24
    
    # === BORDER RADIUS ===
    RADIUS_BTN = 8          # ONLY buttons have rounded corners
    RADIUS_POPUP = 12       # Popups/modals
    RADIUS_NONE = 0         # Most containers - NO rounded corners
    
    # === TYPOGRAPHY ===
    # Font family names
    FONT_FAMILY_HEADING = "Segoe UI"  # Fallback to system fonts
    FONT_FAMILY_BODY = "Segoe UI"
    FONT_FAMILY_MONO = "Consolas"
    
    # Font tuples (family, size) - CTk format
    FONT_HEADING = ("Segoe UI", 16)
    FONT_SUBHEADING = ("Segoe UI", 14)
    FONT_BODY = ("Segoe UI", 13)
    FONT_SMALL = ("Segoe UI", 11)
    FONT_MONO = ("Consolas", 12)
    FONT_BUTTON = ("Segoe UI", 13)
    
    # === SIDEBAR ===
    SIDEBAR_WIDTH = 200
    
    # === WINDOW ===
    WINDOW_MIN_WIDTH = 900
    WINDOW_MIN_HEIGHT = 600
    WINDOW_DEFAULT_WIDTH = 1200
    WINDOW_DEFAULT_HEIGHT = 800
    
    # === TAB ICONS ===
    TAB_ICONS = {
        "T2V": "📹",
        "I2V": "🎬",
        "R2V": "✏️",
        "T2I": "🎯",
        "I2I": "✨",
        "Queue": "📋",
        "Settings": "⚙️",
        "License": "🔑",
        "About": "ℹ️",
        "DevConsole": "🛠️",
    }
    
    @classmethod
    def get_button_style(cls, variant: str = "primary") -> dict:
        """Get button style configuration.
        
        Args:
            variant: 'primary', 'secondary', 'danger', 'success'
        
        Returns:
            Dict with fg_color, hover_color, text_color
        """
        styles = {
            "primary": {
                "fg_color": cls.BLUE,
                "hover_color": cls.LAVENDER,
                "text_color": cls.CRUST,  # Dark text on light button
            },
            "secondary": {
                "fg_color": cls.SURFACE1,
                "hover_color": cls.SURFACE2,
                "text_color": cls.TEXT,
            },
            "danger": {
                "fg_color": cls.RED,
                "hover_color": "#EBA0AC",  # Lighter pink
                "text_color": cls.CRUST,
            },
            "success": {
                "fg_color": cls.GREEN,
                "hover_color": "#B8F0B2",
                "text_color": cls.CRUST,
            },
            "purple": {
                "fg_color": cls.PURPLE,
                "hover_color": cls.PURPLE_HOVER,
                "text_color": cls.CRUST,
            },
            "warning": {
                "fg_color": cls.YELLOW,
                "hover_color": "#FCE8C0",
                "text_color": cls.CRUST,
            },
        }
        return styles.get(variant, styles["primary"])
    
    @classmethod
    def get_input_style(cls) -> dict:
        """Get input field style configuration."""
        return {
            "fg_color": cls.SURFACE0,
            "border_color": cls.BORDER,
            "border_width": 1,
            "text_color": cls.TEXT,
            "placeholder_text_color": cls.OVERLAY0,
        }
    
    @classmethod
    def get_status_style(cls, status: str) -> dict:
        """Get status indicator style.
        
        Args:
            status: 'success', 'warning', 'error', 'info'
        """
        styles = {
            "success": {"fg_color": cls.GREEN, "bg_color": cls.GREEN_BG},
            "warning": {"fg_color": cls.YELLOW, "bg_color": cls.YELLOW_BG},
            "error": {"fg_color": cls.RED, "bg_color": cls.RED_BG},
            "info": {"fg_color": cls.BLUE, "bg_color": "#1E3A5F"},
        }
        return styles.get(status, styles["info"])
    
    @classmethod
    def get_qss_stylesheet(cls) -> str:
        """Get PySide6 QSS stylesheet.
        
        Reference: license_manager_gui.py DARK_STYLESHEET
        Returns complete stylesheet for QApplication.setStyleSheet()
        """
        return f"""
/* ============================================ */
/* VEO PRO MAX - Catppuccin Mocha Theme        */
/* ============================================ */

QMainWindow, QDialog {{
    background-color: {cls.BASE};
    color: {cls.TEXT};
}}

QWidget {{
    background-color: transparent;
    color: {cls.TEXT};
    font-family: "{cls.FONT_FAMILY_BODY}";
    font-size: 13px;
}}

QLabel {{
    color: {cls.TEXT};
    background: transparent;
}}

/* === BUTTONS === */
QPushButton {{
    background-color: {cls.BLUE};
    color: {cls.CRUST};
    border: none;
    border-radius: {cls.RADIUS_BTN}px;
    padding: 8px 16px;
    font-weight: bold;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: {cls.LAVENDER};
}}

QPushButton:pressed {{
    background-color: {cls.SAPPHIRE};
}}

QPushButton:disabled {{
    background-color: {cls.SURFACE1};
    color: {cls.OVERLAY0};
}}

QPushButton[variant="secondary"] {{
    background-color: {cls.SURFACE1};
    color: {cls.TEXT};
}}

QPushButton[variant="secondary"]:hover {{
    background-color: {cls.SURFACE2};
}}

QPushButton[variant="danger"] {{
    background-color: {cls.RED};
}}

QPushButton[variant="danger"]:hover {{
    background-color: #EBA0AC;
}}

QPushButton[variant="success"] {{
    background-color: {cls.GREEN};
}}

QPushButton[variant="purple"] {{
    background-color: {cls.PURPLE};
}}

/* === INPUT FIELDS === */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {cls.SURFACE0};
    color: {cls.TEXT};
    border: 1px solid {cls.BORDER};
    border-radius: 4px;
    padding: 8px;
    selection-background-color: {cls.BLUE};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {cls.BORDER_FOCUS};
}}

QLineEdit:disabled, QTextEdit:disabled {{
    background-color: {cls.SURFACE1};
    color: {cls.OVERLAY0};
}}

/* === COMBO BOX === */
QComboBox {{
    background-color: {cls.SURFACE0};
    color: {cls.TEXT};
    border: 1px solid {cls.BORDER};
    border-radius: 4px;
    padding: 8px;
    min-width: 100px;
}}

QComboBox:focus {{
    border-color: {cls.BORDER_FOCUS};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {cls.TEXT};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {cls.SURFACE0};
    color: {cls.TEXT};
    selection-background-color: {cls.SURFACE2};
    border: 1px solid {cls.BORDER};
}}

/* === SPIN BOX === */
QSpinBox, QDoubleSpinBox {{
    background-color: {cls.SURFACE0};
    color: {cls.TEXT};
    border: 1px solid {cls.BORDER};
    border-radius: 4px;
    padding: 8px;
}}

/* === CHECK BOX === */
QCheckBox {{
    color: {cls.TEXT};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {cls.BORDER};
    border-radius: 4px;
    background-color: {cls.SURFACE0};
}}

QCheckBox::indicator:checked {{
    background-color: {cls.BLUE};
    border-color: {cls.BLUE};
}}

QCheckBox::indicator:hover {{
    border-color: {cls.BORDER_FOCUS};
}}

/* === SLIDER === */
QSlider::groove:horizontal {{
    background: {cls.SURFACE1};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {cls.BLUE};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {cls.LAVENDER};
}}

/* === TABLE === */
QTableWidget, QTableView {{
    background-color: {cls.SURFACE0};
    color: {cls.TEXT};
    gridline-color: {cls.BORDER};
    selection-background-color: {cls.SURFACE2};
    border: 1px solid {cls.BORDER};
    border-radius: 4px;
}}

QTableWidget::item {{
    padding: 8px;
}}

QTableWidget::item:selected {{
    background-color: {cls.SURFACE2};
}}

QHeaderView::section {{
    background-color: {cls.SURFACE1};
    color: {cls.BLUE};
    padding: 8px;
    border: 1px solid {cls.BORDER};
    font-weight: bold;
}}

/* === GROUP BOX === */
QGroupBox {{
    border: 1px solid {cls.BORDER};
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 12px;
    color: {cls.BLUE};
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}}

/* === TAB WIDGET === */
QTabWidget::pane {{
    border: 1px solid {cls.BORDER};
    background-color: {cls.BASE};
}}

QTabBar::tab {{
    background-color: {cls.SURFACE0};
    color: {cls.SUBTEXT0};
    padding: 8px 16px;
    border: 1px solid {cls.BORDER};
    border-bottom: none;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {cls.BASE};
    color: {cls.BLUE};
    border-bottom: 2px solid {cls.BLUE};
}}

QTabBar::tab:hover:!selected {{
    background-color: {cls.SURFACE1};
}}

/* === SCROLL BAR === */
QScrollBar:vertical {{
    background-color: {cls.SURFACE0};
    width: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background-color: {cls.SURFACE1};
    border-radius: 6px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {cls.SURFACE2};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: {cls.SURFACE0};
    height: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {cls.SURFACE1};
    border-radius: 6px;
    min-width: 20px;
}}

/* === SCROLL AREA === */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* === SPLITTER === */
QSplitter::handle {{
    background-color: {cls.BORDER};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* === STATUS BAR === */
QStatusBar {{
    background-color: {cls.SURFACE0};
    color: {cls.SUBTEXT0};
}}

/* === MENU === */
QMenu {{
    background-color: {cls.SURFACE0};
    color: {cls.TEXT};
    border: 1px solid {cls.BORDER};
}}

QMenu::item:selected {{
    background-color: {cls.SURFACE2};
}}

/* === TOOL TIP === */
QToolTip {{
    background-color: {cls.SURFACE1};
    color: {cls.TEXT};
    border: 1px solid {cls.BORDER};
    padding: 4px 8px;
}}

/* === PROGRESS BAR === */
QProgressBar {{
    background-color: {cls.SURFACE0};
    border: 1px solid {cls.BORDER};
    border-radius: 4px;
    text-align: center;
    color: {cls.TEXT};
}}

QProgressBar::chunk {{
    background-color: {cls.BLUE};
    border-radius: 3px;
}}

/* === FRAME === */
QFrame[frameShape="4"] {{ /* HLine */
    background-color: {cls.BORDER};
    max-height: 1px;
}}

QFrame[frameShape="5"] {{ /* VLine */
    background-color: {cls.BORDER};
    max-width: 1px;
}}
"""


class ThemeManager:
    """Manages theme switching and customization.
    
    Supports both CustomTkinter and PySide6.
    Reference: CUSTOMTKINTER_STYLE_GUIDE.md
    """
    
    AVAILABLE_THEMES = ["dark", "light", "system"]
    
    def __init__(self):
        self._current_theme = "dark"
        self._app = None  # QApplication instance
    
    @property
    def current_theme(self) -> str:
        """Get current theme name."""
        return self._current_theme
    
    def set_theme(self, theme_name: str) -> bool:
        """Set application theme.
        
        Args:
            theme_name: 'dark', 'light', or 'system'
        
        Returns:
            True if theme was changed successfully.
        """
        if theme_name not in self.AVAILABLE_THEMES:
            return False
        
        self._current_theme = theme_name
        
        # Apply to PySide6 if app is set
        if self._app is not None:
            self._apply_pyside6_theme()
            return True
        
        # Fallback: Apply to customtkinter if available
        try:
            import customtkinter as ctk
            ctk.set_appearance_mode(theme_name)
        except ImportError:
            pass
        
        return True
    
    def apply_to_app(self, app) -> None:
        """Apply theme to a PySide6 QApplication.
        
        Args:
            app: QApplication instance
        """
        self._app = app
        self._apply_pyside6_theme()
    
    def _apply_pyside6_theme(self) -> None:
        """Apply QSS stylesheet to the stored QApplication."""
        if self._app is None:
            return
        
        # Currently only dark theme is fully styled
        if self._current_theme == "dark":
            self._app.setStyleSheet(Theme.get_qss_stylesheet())
        else:
            # Light/system themes - clear stylesheet for now
            self._app.setStyleSheet("")
    
    def get_available_themes(self) -> list:
        """Get list of available theme names."""
        return self.AVAILABLE_THEMES.copy()
    
    def get_theme_colors(self) -> dict:
        """Get current theme color palette."""
        return {
            "base": Theme.BASE,
            "mantle": Theme.MANTLE,
            "crust": Theme.CRUST,
            "surface0": Theme.SURFACE0,
            "surface1": Theme.SURFACE1,
            "surface2": Theme.SURFACE2,
            "text": Theme.TEXT,
            "subtext0": Theme.SUBTEXT0,
            "subtext1": Theme.SUBTEXT1,
            "overlay0": Theme.OVERLAY0,
            "blue": Theme.BLUE,
            "green": Theme.GREEN,
            "yellow": Theme.YELLOW,
            "red": Theme.RED,
            "purple": Theme.PURPLE,
        }

