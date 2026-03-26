"""
VEO Pro Max - Base Popup Dialog (PySide6)

Reference: 01_POPUP_LAYOUTS.md
Common popup base with header, close button, and modal behavior.
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QWidget
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QKeySequence, QShortcut, QPainter, QColor, QPainterPath, QPen

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class BasePopup(QDialog):
    """Base class for all popup dialogs (PySide6).
    
    Features:
    - Modal behavior (blocks main window)
    - Header with title and close button
    - ESC key to close
    - Centered on parent window
    """
    
    # Signals
    closed = Signal()
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Popup",
        width: int = 400,
        height: int = 300,
    ):
        super().__init__(parent)
        
        self._result = None
        self._drag_pos = None          # ★ For drag-to-move
        
        # ── Popup visual constants ──
        self._popup_bg = QColor(Theme.MANTLE)      # #181825 — darkest, distinct
        self._popup_border = QColor(Theme.OVERLAY0) # #6C7086 — visible border
        self._popup_radius = Theme.RADIUS_POPUP     # 12px
        
        # Window setup
        self.setWindowTitle(title)
        self.setFixedSize(width, height)
        self.setModal(True)
        
        # Remove native title bar + enable true transparency for rounded corners
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Layout (2px margin for painted border)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(2, 2, 2, 2)
        self._main_layout.setSpacing(0)
        
        # Create layout
        self._create_header(title)
        self._create_content()
        self._create_footer()
        
        # ESC to close
        esc_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc_shortcut.activated.connect(self._on_close)
        
        # Center on parent
        self._center_on_parent()
    
    def paintEvent(self, event):
        """Draw rounded rectangle background with border — enables true corner clipping."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Rounded rect path
        path = QPainterPath()
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        path.addRoundedRect(rect, self._popup_radius, self._popup_radius)
        
        # Clip all painting to the rounded rect
        painter.setClipPath(path)
        
        # Fill background
        painter.fillPath(path, self._popup_bg)
        
        # Draw border
        painter.setPen(QPen(self._popup_border, 2))
        painter.drawPath(path)
        
        painter.end()
    
    # ── Drag-to-move (header acts as drag handle) ──────────────
    def mousePressEvent(self, event):
        """Start drag if mouse is on the header region."""
        if event.button() == Qt.LeftButton and event.position().y() <= (self.header.height() if hasattr(self, 'header') else 40):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Move dialog while dragging."""
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Stop drag."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)
    
    def _center_on_parent(self):
        """Center dialog on top-level parent window.
        
        Uses window().frameGeometry() to get the actual screen position
        of the main window, not the local geometry of the parent widget
        (which may be an embedded tab with local-only coordinates).
        """
        parent = self.parent()
        if parent:
            # Always center on the TOP-LEVEL window, not the passed widget
            top = parent.window() if parent.window() else parent
            geo = top.frameGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
    
    def _create_header(self, title: str):
        """Create header with title and close button."""
        self.header = QFrame()
        self.header.setFixedHeight(36)
        self.header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 4, 4, 4)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setMinimumSize(32, 28)
        self.close_btn.setProperty("variant", "link")
        self.close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(self.close_btn)
        
        self._main_layout.addWidget(self.header)
    
    def _create_content(self):
        """Create main content area. Override in subclass."""
        self.content = QWidget()
        self.content.setStyleSheet(f"background-color: {Theme.BASE};")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_footer(self):
        """Create footer with action buttons. Override in subclass."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        self._main_layout.addWidget(self.footer)
    
    def _on_close(self):
        """Handle close action."""
        self.closed.emit()
        self.reject()
    
    def get_result(self):
        """Get result after dialog closes."""
        return self._result
    
    def wait_for_close(self):
        """Wait for dialog to close and return result."""
        self.exec()
        return self._result


class ConfirmDialog(BasePopup):
    """Confirm Dialog with Yes/No buttons (PySide6)."""
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "⚠️ CONFIRM",
        message: str = "Are you sure?",
        confirm_text: str = "Yes",
        cancel_text: str = "No",
        danger: bool = False,
    ):
        self.message = message
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.danger = danger
        
        super().__init__(parent, title=title, width=350, height=180)
    
    def _create_content(self):
        """Create message content."""
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(24, 16, 24, 16)
        
        self.message_label = QLabel(self.message)
        self.message_label.setStyleSheet(f"color: {Theme.TEXT};")
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.message_label)
        
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_footer(self):
        """Create footer with No and Yes buttons."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        _btn_base = (
            f"border: none; border-radius: {Theme.RADIUS_BTN}px; "
            f"padding: 8px 16px; font-weight: bold; font-size: 13px;"
        )
        # Cancel button
        self.cancel_btn = QPushButton(self.cancel_text)
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; {_btn_base} }}"
            f"QPushButton:hover {{ background-color: {Theme.OVERLAY0}; }}"
        )
        self.cancel_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(self.cancel_btn)
        
        # Confirm button
        if self.danger:
            bg, hover = Theme.RED, "#EBA0AC"
        else:
            bg, hover = Theme.BLUE, Theme.LAVENDER
        self.confirm_btn = QPushButton(self.confirm_text)
        self.confirm_btn.setMinimumWidth(80)
        self.confirm_btn.setStyleSheet(
            f"QPushButton {{ background-color: {bg}; color: {Theme.CRUST}; {_btn_base} }}"
            f"QPushButton:hover {{ background-color: {hover}; }}"
        )
        self.confirm_btn.clicked.connect(self._on_confirm)
        self.footer_layout.addWidget(self.confirm_btn)
        
        self._main_layout.addWidget(self.footer)
    
    def accept(self):
        """Override: Enter key triggers Qt's accept() — set result before closing."""
        self._result = True
        super().accept()
    
    def _on_confirm(self):
        """Handle confirm action."""
        self.accept()
    
    def _on_close(self):
        """Handle close/cancel action."""
        self._result = False
        self.reject()


class ErrorDialog(BasePopup):
    """Error Dialog with details expandable (PySide6)."""
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "❌ ERROR",
        message: str = "An error occurred",
        details: Optional[str] = None,
    ):
        self.message = message
        self.details = details
        
        height = 200 if details else 160
        super().__init__(parent, title=title, width=400, height=height)
    
    def _create_content(self):
        """Create error content."""
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        
        # Message with icon
        msg_layout = QHBoxLayout()
        
        icon = QLabel("❌")
        icon.setStyleSheet(f"color: {Theme.RED}; font-size: 24px;")
        msg_layout.addWidget(icon)
        
        self.message_label = QLabel(self.message)
        self.message_label.setStyleSheet(f"color: {Theme.TEXT};")
        self.message_label.setWordWrap(True)
        msg_layout.addWidget(self.message_label, stretch=1)
        
        self.content_layout.addLayout(msg_layout)
        
        # Details (not implemented for simplicity)
        if self.details:
            details_label = QLabel(f"Details: {self.details[:100]}...")
            details_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
            details_label.setWordWrap(True)
            self.content_layout.addWidget(details_label)
        
        self.content_layout.addStretch()
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_footer(self):
        """Create footer with OK button."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setMinimumWidth(80)
        self.ok_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(self.ok_btn)
        
        self._main_layout.addWidget(self.footer)


class RenameDialog(BasePopup):
    """Simple rename/input dialog (PySide6)."""
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Rename",
        initial_value: str = "",
        placeholder: str = "Enter new name...",
    ):
        self._initial_value = initial_value
        self._placeholder = placeholder
        
        super().__init__(parent, title=title, width=400, height=160)
        
        # Enter to confirm
        from PySide6.QtWidgets import QLineEdit
        self.name_entry.returnPressed.connect(self._on_confirm)
        self.name_entry.setFocus()
    
    def _create_content(self):
        """Create the input field."""
        from PySide6.QtWidgets import QLineEdit
        
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        
        label = QLabel("Name:")
        label.setStyleSheet(f"color: {Theme.TEXT};")
        self.content_layout.addWidget(label)
        
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText(self._placeholder)
        self.name_entry.setMinimumHeight(36)
        self.name_entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BLUE};
            }}
        """)
        if self._initial_value:
            self.name_entry.setText(self._initial_value)
            self.name_entry.selectAll()
        self.content_layout.addWidget(self.name_entry)
        
        self.content_layout.addStretch()
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_footer(self):
        """Create footer with Cancel and OK buttons."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        _btn_base = (
            f"border: none; border-radius: {Theme.RADIUS_BTN}px; "
            f"padding: 8px 16px; font-weight: bold; font-size: 13px;"
        )
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; {_btn_base} }}"
            f"QPushButton:hover {{ background-color: {Theme.OVERLAY0}; }}"
        )
        cancel_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("OK")
        ok_btn.setMinimumWidth(80)
        ok_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Theme.BLUE}; color: {Theme.CRUST}; {_btn_base} }}"
            f"QPushButton:hover {{ background-color: {Theme.LAVENDER}; }}"
        )
        ok_btn.clicked.connect(self._on_confirm)
        self.footer_layout.addWidget(ok_btn)
        
        self._main_layout.addWidget(self.footer)
    
    def _on_confirm(self):
        """Handle confirm action."""
        value = self.name_entry.text().strip()
        if value:
            self._result = value
            self.accept()
        else:
            self._on_close()


class CreditWarningDialog(BasePopup):
    """Visually prominent credit cost warning dialog.
    
    Features:
    - Orange warning header bar
    - Large credit amount badge with cost breakdown
    - Color-coded buttons: Green (safe LP) vs Red (danger Fast)
    """
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        model_name: str = "",
        n_prompts: int = 0,
        n_outputs: int = 4,
        total_credits: int = 0,
        cost_per_video: int = 10,
        has_upscale: bool = False,
        confirm_text: str = "Yes, use Fast",
        cancel_text: str = "No → Fast [LP]",
    ):
        self._model_name = model_name
        self._n_prompts = n_prompts
        self._n_outputs = n_outputs
        self._total_credits = total_credits
        self._cost_per_video = cost_per_video
        self._has_upscale = has_upscale
        self._confirm_text = confirm_text
        self._cancel_text = cancel_text
        
        super().__init__(parent, title="⚠️ CREDIT WARNING", width=460, height=330)
    
    def _create_header(self, title: str):
        """Orange warning header bar."""
        self.header = QFrame()
        self.header.setFixedHeight(40)
        self.header.setStyleSheet(
            f"background-color: {Theme.PEACH}; "
            f"border-top-left-radius: {Theme.RADIUS_POPUP}px; "
            f"border-top-right-radius: {Theme.RADIUS_POPUP}px;"
        )
        
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(16, 4, 4, 4)
        
        self.title_label = QLabel("⚠️  CREDIT WARNING")
        self.title_label.setStyleSheet(
            f"color: {Theme.CRUST}; font-weight: bold; font-size: 15px;"
        )
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setMinimumSize(32, 28)
        self.close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Theme.CRUST}; "
            f"font-size: 16px; font-weight: bold; border: none; }}"
            f"QPushButton:hover {{ background: rgba(0,0,0,0.15); border-radius: 4px; }}"
        )
        self.close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(self.close_btn)
        
        self._main_layout.addWidget(self.header)
    
    def _create_content(self):
        """Create rich warning content with credit badge."""
        self.content = QWidget()
        self.content.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(24, 12, 24, 6)
        self.content_layout.setSpacing(8)
        
        # Model name
        model_lbl = QLabel(f"Model:  {self._model_name}")
        model_lbl.setStyleSheet(
            f"color: {Theme.PEACH}; font-size: 14px; font-weight: bold;"
        )
        model_lbl.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(model_lbl)
        
        # Credit badge — large, highlighted
        badge = QFrame()
        badge.setStyleSheet(
            f"background-color: {Theme.YELLOW_BG}; "
            f"border: 2px solid {Theme.YELLOW}; "
            f"border-radius: 8px; "
            f"padding: 8px;"
        )
        badge_layout = QVBoxLayout(badge)
        badge_layout.setContentsMargins(12, 6, 12, 6)
        badge_layout.setSpacing(4)
        
        # Per-video cost breakdown
        if self._has_upscale:
            if self._cost_per_video >= 60:
                detail_text = "10 (generation) + 50 (4K upscale) = 60 / video"
            else:
                detail_text = "50 (4K upscale) / video"
            cost_detail = QLabel(detail_text)
            cost_detail.setStyleSheet(
                f"color: {Theme.PEACH}; font-size: 11px; font-weight: bold;"
            )
            cost_detail.setAlignment(Qt.AlignCenter)
            badge_layout.addWidget(cost_detail)
        
        # Formula
        formula_lbl = QLabel(
            f"{self._n_prompts} prompt  ×  {self._n_outputs} video  ×  {self._cost_per_video}"
        )
        formula_lbl.setStyleSheet(
            f"color: {Theme.SUBTEXT1}; font-size: 12px;"
        )
        formula_lbl.setAlignment(Qt.AlignCenter)
        badge_layout.addWidget(formula_lbl)
        
        total_lbl = QLabel(f"💰  {self._total_credits} credits")
        total_lbl.setStyleSheet(
            f"color: {Theme.YELLOW}; font-size: 22px; font-weight: bold;"
        )
        total_lbl.setAlignment(Qt.AlignCenter)
        badge_layout.addWidget(total_lbl)
        
        self.content_layout.addWidget(badge)
        
        # Hint text
        hint_lbl = QLabel(
            f"Chọn '{self._cancel_text}' để tiết kiệm credit"
        )
        hint_lbl.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px; font-style: italic;"
        )
        hint_lbl.setAlignment(Qt.AlignCenter)
        hint_lbl.setWordWrap(True)
        self.content_layout.addWidget(hint_lbl)
        
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_footer(self):
        """Color-coded buttons: Green (LP safe) vs Red (Fast danger)."""
        self.footer = QFrame()
        self.footer.setFixedHeight(56)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(16, 8, 16, 8)
        
        self.footer_layout.addStretch()
        
        _btn_base = (
            f"border: none; border-radius: {Theme.RADIUS_BTN}px; "
            f"padding: 10px 20px; font-weight: bold; font-size: 13px;"
        )
        
        # Safe button (LP) — GREEN
        self.cancel_btn = QPushButton(self._cancel_text)
        self.cancel_btn.setMinimumWidth(140)
        self.cancel_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Theme.GREEN}; color: {Theme.CRUST}; {_btn_base} }}"
            f"QPushButton:hover {{ background-color: #B8F0B2; }}"
        )
        self.cancel_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(self.cancel_btn)
        
        self.footer_layout.addSpacing(8)
        
        # Danger button (Fast) — RED
        self.confirm_btn = QPushButton(self._confirm_text)
        self.confirm_btn.setMinimumWidth(140)
        self.confirm_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Theme.RED}; color: {Theme.CRUST}; {_btn_base} }}"
            f"QPushButton:hover {{ background-color: #EBA0AC; }}"
        )
        self.confirm_btn.clicked.connect(self._on_confirm)
        self.footer_layout.addWidget(self.confirm_btn)
        
        self._main_layout.addWidget(self.footer)
    
    def accept(self):
        self._result = True
        super().accept()
    
    def _on_confirm(self):
        self.accept()
    
    def _on_close(self):
        self._result = False
        self.reject()


# Convenience functions
def confirm(parent, title="⚠️ CONFIRM", message="Are you sure?", 
            confirm_text="Yes", cancel_text="No", danger=False) -> bool:
    """Show confirmation dialog."""
    dialog = ConfirmDialog(parent, title, message, confirm_text, cancel_text, danger)
    return dialog.wait_for_close() or False


def show_credit_warning(parent, model_name, n_prompts, n_outputs, total_credits,
                        cost_per_video=10, has_upscale=False,
                        confirm_text="Yes, use Fast", cancel_text="No → Fast [LP]") -> bool:
    """Show credit warning dialog. Returns True if user confirms Fast model."""
    dialog = CreditWarningDialog(
        parent, model_name, n_prompts, n_outputs, total_credits,
        cost_per_video, has_upscale, confirm_text, cancel_text
    )
    return dialog.wait_for_close() or False


def show_error(parent, title="❌ ERROR", message="An error occurred", 
               details: Optional[str] = None):
    """Show error dialog."""
    dialog = ErrorDialog(parent, title, message, details)
    dialog.wait_for_close()

