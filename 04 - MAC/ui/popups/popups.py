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
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut

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
        
        # Window setup
        self.setWindowTitle(title)
        self.setFixedSize(width, height)
        self.setModal(True)
        
        # Remove native title bar for custom header
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        
        # Style
        self.setStyleSheet(f"background-color: {Theme.BASE};")
        
        # Layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
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
    
    def _center_on_parent(self):
        """Center dialog on parent window."""
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
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


# Convenience functions
def confirm(parent, title="⚠️ CONFIRM", message="Are you sure?", 
            confirm_text="Yes", cancel_text="No", danger=False) -> bool:
    """Show confirmation dialog."""
    dialog = ConfirmDialog(parent, title, message, confirm_text, cancel_text, danger)
    return dialog.wait_for_close() or False


def show_error(parent, title="❌ ERROR", message="An error occurred", 
               details: Optional[str] = None):
    """Show error dialog."""
    dialog = ErrorDialog(parent, title, message, details)
    dialog.wait_for_close()
