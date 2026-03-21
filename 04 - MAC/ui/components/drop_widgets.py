"""
VEO Pro Max - Drop-enabled Widgets

Reusable widgets with drag & drop support:
- FolderDropLineEdit: Accept folder drops from Explorer → set path
- TextFileDropEdit: Accept .txt file drops → import content
"""

from pathlib import Path

from PySide6.QtWidgets import QLineEdit, QTextEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent


class FolderDropLineEdit(QLineEdit):
    """QLineEdit that accepts folder drops from file explorer."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_dir():
                        event.acceptProposedAction()
                        return
        # Also accept if it's a file — use its parent dir
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    # If folder, use directly; if file, use parent dir
                    folder = str(path) if path.is_dir() else str(path.parent)
                    self.setText(folder)
                    event.acceptProposedAction()
                    return
        event.ignore()


class TextFileDropEdit(QTextEdit):
    """QTextEdit that accepts .txt file drops to import content.
    
    Also sanitizes clipboard paste from Google Sheets (HTML <table> → plain text).
    """
    
    TEXT_EXTENSIONS = {'.txt', '.text', '.csv', '.md', '.log'}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
        self.setAcceptRichText(False)  # ★ Force plain-text paste (Google Sheets sends HTML <table>)
    
    def insertFromMimeData(self, source):
        """Override paste to sanitize Google Sheets / Excel clipboard content.
        
        Google Sheets copies data as HTML (<table><tr><td>...) AND as plain text.
        By forcing plain-text mode and sanitizing, we ensure proper line breaks.
        """
        if source.hasText():
            text = source.text()
            # Normalize line endings: \r\n → \n, \r → \n
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            # Strip BOM and zero-width chars that Google Sheets may inject
            text = text.lstrip('\ufeff').replace('\u200b', '').replace('\u00a0', ' ')
            # Insert as clean plain text
            from PySide6.QtCore import QMimeData
            clean = QMimeData()
            clean.setText(text)
            super().insertFromMimeData(clean)
        else:
            super().insertFromMimeData(source)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = Path(url.toLocalFile()).suffix.lower()
                    if ext in self.TEXT_EXTENSIONS:
                        event.acceptProposedAction()
                        return
        # Fall back to default (accept plain text drops)
        super().dragEnterEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    ext = path.suffix.lower()
                    if ext in self.TEXT_EXTENSIONS:
                        try:
                            content = path.read_text(encoding='utf-8')
                            self.setPlainText(content)
                            event.acceptProposedAction()
                            return
                        except Exception:
                            pass
        # Fall back to default
        super().dropEvent(event)
