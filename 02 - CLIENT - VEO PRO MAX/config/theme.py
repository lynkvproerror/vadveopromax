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
    RADIUS_INPUT = 4        # Inputs, combos, spinboxes
    RADIUS_POPUP = 12       # Popups/modals
    RADIUS_NONE = 0         # Most containers - NO rounded corners
    
    # === INPUT WIDGETS (QComboBox, QLineEdit, QSpinBox) ===
    INPUT_PADDING_V = 4          # Vertical padding (px)
    INPUT_PADDING_H = 8          # Horizontal padding (px)
    INPUT_MIN_HEIGHT = 24        # Minimum height (px)
    INPUT_FONT_SIZE = 12         # Font size (px)
    
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
    SIDEBAR_WIDTH = 240          # Form sidebars (Video, Image, Project Builder)
    SIDEBAR_NAV_WIDTH = 180      # Navigation sidebars (Dev Console)
    SIDEBAR_PADDING = 8          # Contents margins (top, right, bottom, left)
    SIDEBAR_SPACING = 4          # Spacing between widgets
    
    # === WINDOW ===
    WINDOW_MIN_WIDTH = 900
    WINDOW_MIN_HEIGHT = 600
    WINDOW_DEFAULT_WIDTH = 1500
    WINDOW_DEFAULT_HEIGHT = 900
    
    # === TAB ICONS ===
    TAB_ICONS = {
        "PROJECT": "📋",
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
                "fg_color": cls.SURFACE2,
                "hover_color": cls.OVERLAY0,
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
    
    _arrow_paths = None

    @classmethod
    def _generate_arrows(cls):
        """Generate arrow PNG images for QSS (Qt needs image: url() for arrows)."""
        if cls._arrow_paths:
            return cls._arrow_paths

        import os, tempfile
        from PySide6.QtGui import QImage, QPainter, QColor, QPolygonF
        from PySide6.QtCore import QPointF, Qt

        d = os.path.join(tempfile.gettempdir(), 'veo_arrows')
        os.makedirs(d, exist_ok=True)

        color = QColor(cls.TEXT)
        dim_color = QColor(cls.OVERLAY0)
        arrows = {
            'up': ([QPointF(6, 2), QPointF(11, 10), QPointF(1, 10)], 12),
            'down': ([QPointF(1, 2), QPointF(11, 2), QPointF(6, 10)], 12),
            'combo_down': ([QPointF(1, 3), QPointF(13, 3), QPointF(7, 11)], 14),
            'up_dim': ([QPointF(6, 2), QPointF(11, 10), QPointF(1, 10)], 12),
            'down_dim': ([QPointF(1, 2), QPointF(11, 2), QPointF(6, 10)], 12),
        }
        paths = {}
        for name, (pts, sz) in arrows.items():
            img = QImage(sz, sz, QImage.Format.Format_ARGB32)
            img.fill(QColor(0, 0, 0, 0))
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dim_color if '_dim' in name else color)
            p.drawPolygon(QPolygonF(pts))
            p.end()
            fpath = os.path.join(d, f'{name}.png')
            img.save(fpath)
            paths[name] = fpath.replace('\\', '/')
        cls._arrow_paths = paths
        return paths

    @classmethod
    def get_qss_stylesheet(cls) -> str:
        """Get PySide6 QSS stylesheet.
        
        Reference: license_manager_gui.py DARK_STYLESHEET
        Returns complete stylesheet for QApplication.setStyleSheet()
        """
        arrows = cls._generate_arrows()
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
    background-color: {cls.SURFACE2};
    color: {cls.SUBTEXT0};
}}

/* -- Variants -- */
QPushButton[variant="secondary"] {{
    background-color: {cls.SURFACE2};
    color: {cls.TEXT};
}}
QPushButton[variant="secondary"]:hover {{
    background-color: {cls.OVERLAY0};
}}

QPushButton[variant="danger"] {{
    background-color: {cls.RED};
}}
QPushButton[variant="danger"]:hover {{
    background-color: #EBA0AC;
}}

QPushButton[variant="success"] {{
    background-color: {cls.GREEN};
    color: {cls.CRUST};
}}
QPushButton[variant="success"]:hover {{
    background-color: #A6E3A1;
}}
QPushButton[variant="success"]:checked {{
    background-color: {cls.GREEN};
    color: {cls.CRUST};
}}

QPushButton[variant="purple"] {{
    background-color: {cls.PURPLE};
}}
QPushButton[variant="purple"]:hover {{
    background-color: #C4A7E7;
}}

QPushButton[variant="warning"] {{
    background-color: {cls.PEACH};
}}
QPushButton[variant="warning"]:hover {{
    background-color: #FBCFB0;
}}

QPushButton[variant="link"] {{
    background-color: transparent;
    color: {cls.BLUE};
    border: none;
    padding: 0;
    font-weight: normal;
    text-align: left;
}}
QPushButton[variant="link"]:hover {{
    color: {cls.LAVENDER};
}}

/* -- Button Sizes -- */
QPushButton[btnSize="sm"] {{
    height: 26px;
    font-size: 11px;
    padding: 0 10px;
}}

QPushButton[btnSize="lg"] {{
    height: 36px;
    font-size: 14px;
    padding: 0 20px;
}}

/* === INPUT FIELDS === */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {cls.SURFACE1};
    color: {cls.TEXT};
    border: 1px solid {cls.BORDER};
    border-radius: {cls.RADIUS_INPUT}px;
    padding: {cls.INPUT_PADDING_V}px {cls.INPUT_PADDING_H}px;
    font-size: {cls.INPUT_FONT_SIZE}px;
    font-weight: bold;
    min-height: {cls.INPUT_MIN_HEIGHT}px;
    selection-background-color: {cls.BLUE};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {cls.GREEN};
}}

QLineEdit:disabled, QTextEdit:disabled {{
    background-color: {cls.SURFACE0};
    color: {cls.OVERLAY0};
    border-color: {cls.BORDER};
}}

/* === COMBO BOX === */
QComboBox {{
    background-color: {cls.SURFACE1};
    color: {cls.TEXT};
    border: none;
    border-radius: {cls.RADIUS_INPUT}px;
    padding: {cls.INPUT_PADDING_V}px {cls.INPUT_PADDING_H}px;
    font-size: {cls.INPUT_FONT_SIZE}px;
    font-weight: bold;
    min-height: {cls.INPUT_MIN_HEIGHT}px;
}}

QComboBox:focus {{
    border: 1px solid {cls.GREEN};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
    background-color: {cls.SURFACE1};
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
}}

QComboBox::drop-down:hover {{
    background-color: {cls.SURFACE2};
}}

QComboBox::down-arrow {{
    image: url({arrows['combo_down']});
    width: 14px;
    height: 14px;
}}

QComboBox QAbstractItemView {{
    background-color: {cls.SURFACE0};
    color: {cls.TEXT};
    selection-background-color: {cls.SURFACE2};
    border: 1px solid {cls.BORDER};
}}

/* === SPIN BOX === */
QSpinBox, QDoubleSpinBox {{
    background-color: {cls.SURFACE1};
    color: {cls.TEXT};
    border: 1px solid {cls.BORDER};
    border-radius: {cls.RADIUS_INPUT}px;
    padding: {cls.INPUT_PADDING_V}px {cls.INPUT_PADDING_H}px;
    padding-right: 28px;  /* Space for buttons on right (24px + 4px) */
    font-size: {cls.INPUT_FONT_SIZE}px;
    font-weight: bold;
    min-height: {cls.INPUT_MIN_HEIGHT}px;
    selection-background-color: {cls.BLUE};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {cls.GREEN};
}}

QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {cls.SURFACE0};
    color: {cls.OVERLAY0};
    border-color: {cls.BORDER};
}}

/* Up button — top right */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid {cls.BORDER};
    border-bottom: 1px solid {cls.BORDER};
    border-top-right-radius: 3px;
    background-color: {cls.SURFACE1};
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
    background-color: {cls.SURFACE2};
}}

QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed {{
    background-color: {cls.BLUE};
}}

/* Down button — bottom right */
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    border-left: 1px solid {cls.BORDER};
    border-top: 1px solid {cls.BORDER};
    border-bottom-right-radius: 3px;
    background-color: {cls.SURFACE1};
}}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {cls.SURFACE2};
}}

QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background-color: {cls.BLUE};
}}

/* Up arrow */
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({arrows['up']});
    width: 12px;
    height: 12px;
}}

QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off {{
    image: url({arrows['up_dim']});
    width: 12px;
    height: 12px;
}}

/* Down arrow */
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({arrows['down']});
    width: 12px;
    height: 12px;
}}

QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off {{
    image: url({arrows['down_dim']});
    width: 12px;
    height: 12px;
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
    font-size: 12px;
    font-weight: bold;
}}

QTabBar::tab:selected {{
    background-color: {cls.BASE};
    color: {cls.BLUE};
    border-bottom: 2px solid {cls.BLUE};
    font-weight: bold;
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
    font-size: 12px;
    font-weight: bold;
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

/* === SCROLL AREA === */
QScrollArea {{
    border: none;
}}

/* === SETTINGS SECTIONS === */
QFrame#settingsSection {{
    background-color: {cls.SURFACE0};
    border: 1px solid {cls.BORDER};
    border-radius: 8px;
    padding: 12px;
}}

/* === SIDEBAR CONTAINER === */
QWidget#sidebarPanel {{
    background-color: {cls.SURFACE0};
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

