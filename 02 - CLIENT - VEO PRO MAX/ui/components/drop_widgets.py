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
    """QTextEdit that accepts .txt file drops to import content."""
    
    TEXT_EXTENSIONS = {'.txt', '.text', '.csv', '.md', '.log'}
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
    
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
