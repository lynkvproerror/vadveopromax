"""
VEO Pro Max - Global Search & Replace Dialog

Notepad++ style Find/Replace popup dialog that works with any
QTextEdit / QPlainTextEdit widget.  Triggered by Ctrl+F / Ctrl+H
from MainWindow.
"""

from typing import Optional, List

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLineEdit, QTextEdit,
    QPushButton, QLabel, QWidget, QPlainTextEdit, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QTextCursor, QTextCharFormat, QColor, QBrush,
)

from config.theme import Theme


class SearchReplaceBar(QDialog):
    """Notepad++ style Find/Replace popup dialog."""

    closed = Signal()

    # Highlight colours
    _MATCH_BG = QColor("#514820")
    _MATCH_FG = QColor(Theme.YELLOW)
    _CURRENT_BG = QColor("#6B5B1E")
    _CURRENT_FG = QColor("#FFFFFF")

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Find & Replace")
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint
        )
        self.setMinimumWidth(480)
        self.setModal(False)  # Non-modal — can interact with editor behind

        self._target: Optional[QWidget] = None
        self._matches: List[tuple] = []
        self._current_idx = -1

        self._build_ui()
        self._apply_style()

    # ─────────────────── UI Construction ───────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Row 1: Search ──
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        search_label = QLabel("Find:")
        search_label.setFixedWidth(60)
        row1.addWidget(search_label)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search text…")
        self._search_input.textChanged.connect(self._on_search_changed)
        self._search_input.returnPressed.connect(self._next_match)
        row1.addWidget(self._search_input, stretch=1)

        root.addLayout(row1)

        # ── Row 2: Replace ──
        self._replace_label = QLabel("Replace:")
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self._replace_label.setFixedWidth(60)
        row2.addWidget(self._replace_label)

        self._replace_input = QTextEdit()
        self._replace_input.setPlaceholderText("Replace with… (multi-line supported)")
        self._replace_input.setAcceptRichText(False)
        self._replace_input.setFixedHeight(50)
        row2.addWidget(self._replace_input, stretch=1)

        root.addLayout(row2)

        # ── Row 3: Match info + Options ──
        info_row = QHBoxLayout()
        info_row.setSpacing(8)

        self._match_label = QLabel("No results")
        self._match_label.setMinimumWidth(80)
        info_row.addWidget(self._match_label)

        self._case_cb = QCheckBox("Match Case")
        self._case_cb.toggled.connect(lambda: self._on_search_changed(self._search_input.text()))
        info_row.addWidget(self._case_cb)

        info_row.addStretch()
        root.addLayout(info_row)

        # ── Row 4: Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._prev_btn = QPushButton("↑ Previous")
        self._prev_btn.clicked.connect(self._prev_match)
        btn_row.addWidget(self._prev_btn)

        self._next_btn = QPushButton("↓ Next")
        self._next_btn.clicked.connect(self._next_match)
        btn_row.addWidget(self._next_btn)

        btn_row.addSpacing(12)

        self._replace_btn = QPushButton("Replace")
        self._replace_btn.clicked.connect(self._replace_current)
        btn_row.addWidget(self._replace_btn)

        self._replace_all_btn = QPushButton("Replace All")
        self._replace_all_btn.clicked.connect(self._replace_all)
        btn_row.addWidget(self._replace_all_btn)

        btn_row.addStretch()

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.hide_bar)
        btn_row.addWidget(self._close_btn)

        root.addLayout(btn_row)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.SURFACE0};
                color: {Theme.TEXT};
            }}
            QLabel {{
                color: {Theme.TEXT};
                font-size: 13px;
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {Theme.BLUE};
            }}
            QTextEdit {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2};
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 13px;
            }}
            QTextEdit:focus {{
                border-color: {Theme.BLUE};
            }}
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {Theme.TEXT};
                border: none;
                border-radius: 4px;
                font-size: 12px;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.OVERLAY0};
            }}
            QCheckBox {{
                color: {Theme.SUBTEXT0};
                font-size: 12px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border-radius: 3px;
                border: 1px solid {Theme.SUBTEXT0};
                background-color: {Theme.SURFACE1};
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid {Theme.BLUE};
                background-color: {Theme.BLUE};
            }}
        """)

    # ─────────────────── Public API ───────────────────

    def attach(self, widget):
        """Bind to a QTextEdit or QPlainTextEdit."""
        self._clear_highlights()
        self._target = widget
        self._matches.clear()
        self._current_idx = -1
        self._update_counter()

    def show_bar(self, replace: bool = False):
        """Show the dialog, optionally hiding/showing replace row."""
        self._replace_label.setVisible(replace)
        self._replace_input.setVisible(replace)
        self._replace_btn.setVisible(replace)
        self._replace_all_btn.setVisible(replace)

        self.setWindowTitle("Find & Replace" if replace else "Find")
        self.show()
        self.raise_()
        self.activateWindow()
        self._search_input.setFocus()
        self._search_input.selectAll()

        if self._search_input.text():
            self._on_search_changed(self._search_input.text())

    def hide_bar(self):
        """Hide and clear highlights."""
        self._clear_highlights()
        self.hide()
        if self._target:
            self._target.setFocus()
        self.closed.emit()

    # ─────────────────── Search Logic ───────────────────

    def _on_search_changed(self, text: str):
        """Re-scan target for all matches."""
        self._matches.clear()
        self._current_idx = -1
        self._clear_highlights()

        if not text or not self._target:
            self._update_counter()
            return

        # Get full text
        if isinstance(self._target, (QPlainTextEdit, QTextEdit)):
            doc_text = self._target.toPlainText()
        else:
            self._update_counter()
            return

        # Case sensitivity
        case_sensitive = self._case_cb.isChecked()
        if case_sensitive:
            search_text = text
            compare_text = doc_text
        else:
            search_text = text.lower()
            compare_text = doc_text.lower()

        # Find all occurrences
        start = 0
        while True:
            idx = compare_text.find(search_text, start)
            if idx == -1:
                break
            self._matches.append((idx, idx + len(text)))
            start = idx + 1

        if self._matches:
            self._current_idx = 0
            self._highlight_all()
            self._go_to_current()
        self._update_counter()

    def _highlight_all(self):
        if not self._target or not self._matches:
            return

        selections = []
        for i, (start, end) in enumerate(self._matches):
            sel = self._make_selection(start, end, is_current=(i == self._current_idx))
            selections.append(sel)

        self._target.setExtraSelections(selections)

    def _make_selection(self, start: int, end: int, is_current: bool):
        if isinstance(self._target, QPlainTextEdit):
            sel = QPlainTextEdit.ExtraSelection()
        else:
            sel = QTextEdit.ExtraSelection()

        fmt = QTextCharFormat()
        if is_current:
            fmt.setBackground(QBrush(self._CURRENT_BG))
            fmt.setForeground(QBrush(self._CURRENT_FG))
        else:
            fmt.setBackground(QBrush(self._MATCH_BG))
            fmt.setForeground(QBrush(self._MATCH_FG))

        cursor = self._target.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        sel.cursor = cursor
        sel.format = fmt
        return sel

    def _go_to_current(self):
        if not self._target or self._current_idx < 0:
            return
        start, end = self._matches[self._current_idx]

        cursor = self._target.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self._target.setTextCursor(cursor)
        self._target.ensureCursorVisible()

        self._highlight_all()
        self._update_counter()

    def _clear_highlights(self):
        if self._target and hasattr(self._target, 'setExtraSelections'):
            self._target.setExtraSelections([])

    def _next_match(self):
        if not self._matches:
            return
        self._current_idx = (self._current_idx + 1) % len(self._matches)
        self._go_to_current()

    def _prev_match(self):
        if not self._matches:
            return
        self._current_idx = (self._current_idx - 1) % len(self._matches)
        self._go_to_current()

    # ─────────────────── Replace Logic ───────────────────

    def _replace_current(self):
        if not self._target or self._current_idx < 0 or not self._matches:
            return

        replacement = self._replace_input.toPlainText()
        start, end = self._matches[self._current_idx]

        cursor = self._target.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(replacement)

        self._on_search_changed(self._search_input.text())

        if self._matches and self._current_idx >= len(self._matches):
            self._current_idx = 0
            self._go_to_current()

    def _replace_all(self):
        if not self._target or not self._matches:
            return

        replacement = self._replace_input.toPlainText()
        cursor = self._target.textCursor()
        cursor.beginEditBlock()

        for start, end in reversed(self._matches):
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.insertText(replacement)

        cursor.endEditBlock()

        count = len(self._matches)
        self._on_search_changed(self._search_input.text())

        self._match_label.setText(f"✅ {count} replaced")
        QTimer.singleShot(2000, lambda: self._update_counter())

    # ─────────────────── UI Helpers ───────────────────

    def _update_counter(self):
        if not self._matches:
            self._match_label.setText("No results")
            self._match_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 12px;")
        else:
            self._match_label.setText(f"Match {self._current_idx + 1} of {len(self._matches)}")
            self._match_label.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 12px; font-weight: bold;")

    # ─────────────────── Overrides ───────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
            return
        if event.key() == Qt.Key_Return and event.modifiers() & Qt.ShiftModifier:
            self._prev_match()
            return
        # Enter in search field → next match (handled by returnPressed signal)
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """Handle window close button (✕)."""
        self._clear_highlights()
        self.closed.emit()
        super().closeEvent(event)
