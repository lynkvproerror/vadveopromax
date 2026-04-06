"""
VEO Pro Max - Voice Library Popup

Browse, preview-play, filter, and select from 30 R2V voices.
Mirrors ImageManagerPopup pattern: non-modal, resizable, stays on top.
"""

from typing import Optional, Callable, List
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QScrollArea, QRadioButton,
    QButtonGroup, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QColor

from config.theme import Theme
from ui.popups import BasePopup


# ─── WAV Download Worker ─────────────────────────────────────────────

class _WavDownloadWorker(QThread):
    """Background thread that downloads a voice WAV file."""
    finished = Signal(str, str)  # (voice_id, local_path_or_empty)
    
    def __init__(self, voice_id: str, parent=None):
        super().__init__(parent)
        self._voice_id = voice_id
    
    def run(self):
        try:
            from services.voice_library import get_voice_library
            path = get_voice_library().download_wav_sync(self._voice_id)
            self.finished.emit(self._voice_id, str(path) if path else "")
        except Exception:
            self.finished.emit(self._voice_id, "")


# ─── Voice Card Widget ───────────────────────────────────────────────

class _VoiceCard(QFrame):
    """Single voice card in the grid (120×130px).
    
    Layout:
        🎤♀           ← gender-colored mic icon
        Aoede         ← display name (bold)
        soft · mid    ← tone/pitch subtitle
        [▶]   [✅]    ← play / select buttons
    """
    
    play_clicked = Signal(str)    # voice_id
    select_clicked = Signal(str)  # voice_id
    
    CARD_W = 120
    CARD_H = 130
    
    def __init__(self, voice, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self._voice = voice
        self._is_selected = is_selected
        
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style(is_selected)
        self._setup_ui()
    
    def _apply_style(self, selected: bool):
        border = f"2px solid {Theme.GREEN}" if selected else f"1px solid {Theme.SURFACE2}"
        self.setStyleSheet(f"""
            _VoiceCard {{
                background: {Theme.SURFACE1};
                border: {border};
                border-radius: 8px;
            }}
        """)
    
    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._apply_style(selected)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)
        
        v = self._voice
        
        # Gender icon (large, colored)
        icon_label = QLabel(f"🎤{v.gender_icon}")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"color: {v.gender_color}; font-size: 18px; border: none; background: transparent;"
        )
        layout.addWidget(icon_label)
        
        # Display name
        name_label = QLabel(v.display_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 11px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        layout.addWidget(name_label)
        
        # Subtitle (tone · pitch)
        sub = v.subtitle
        sub_label = QLabel(sub)
        sub_label.setAlignment(Qt.AlignCenter)
        sub_label.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 9px; border: none; background: transparent;"
        )
        sub_label.setToolTip(
            f"Voice: {v.display_name}\nGender: {v.gender.title()}\n"
            f"Tone: {v.tone or '—'}\nPitch: {v.pitch or '—'}"
        )
        layout.addWidget(sub_label)
        
        layout.addStretch()
        
        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setAlignment(Qt.AlignCenter)
        
        _btn_css = "border: none; border-radius: 3px; font-size: 12px; font-weight: bold; padding: 2px 6px;"
        
        # Play button
        play_btn = QPushButton("▶")
        play_btn.setFixedSize(32, 22)
        play_btn.setToolTip(f"Play {v.display_name} preview")
        play_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.BLUE}; color: {Theme.CRUST}; {_btn_css} }}"
            f"QPushButton:hover {{ background: #89B4FA; }}"
        )
        play_btn.clicked.connect(lambda: self.play_clicked.emit(v.id))
        btn_row.addWidget(play_btn)
        
        # Select button
        sel_btn = QPushButton("✅")
        sel_btn.setFixedSize(32, 22)
        sel_btn.setToolTip(f"Select {v.display_name}")
        sel_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.GREEN}; color: {Theme.CRUST}; {_btn_css} }}"
            f"QPushButton:hover {{ background: #B8F0B2; }}"
        )
        sel_btn.clicked.connect(lambda: self.select_clicked.emit(v.id))
        btn_row.addWidget(sel_btn)
        
        layout.addLayout(btn_row)


# ─── Main Popup ──────────────────────────────────────────────────────

class VoiceLibraryPopup(BasePopup):
    """Voice Library Manager popup.
    
    Features:
    - 30 voices in scrollable grid (4 columns)
    - Filter sidebar: Gender / Tone / Pitch (AND logic)
    - Search by name
    - Play WAV preview via QMediaPlayer
    - Select voice → callback to R2V tab
    - Non-modal, resizable, stays on top
    """
    
    GRID_COLS = 4
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_select_all: Optional[Callable[[str], None]] = None,
        on_select_empty: Optional[Callable[[str], None]] = None,
        current_voice: str = "",
    ):
        self._cb_select_all = on_select_all
        self._cb_select_empty = on_select_empty
        self._current_voice = current_voice
        self._playing_voice = ""
        self._voice_cards: dict = {}  # voice_id → _VoiceCard
        
        # Audio player (lazy init)
        self._player = None
        self._audio_output = None
        self._download_worker = None
        
        # Filter state
        self._filter_gender = "All"
        self._filter_tone = "All"
        self._filter_pitch = "All"
        self._search_query = ""
        
        super().__init__(parent, title="🎙️ Voice Library", width=780, height=550)
        
        # Non-modal
        self.setModal(False)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.header.hide()
        self.footer.hide()
        self.setMinimumSize(600, 400)
        self.setMaximumSize(1100, 750)
        
        # Populate
        self._reload_grid()
    
    # ─── Layout Creation ─────────────────────────────────────────
    
    def _create_content(self):
        """Split layout: filter sidebar + voice grid."""
        self.content = QWidget()
        content_layout = QHBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Filter sidebar
        sidebar = self._create_filter_sidebar()
        content_layout.addWidget(sidebar)
        
        # Grid area (search + grid + player bar)
        grid_area = self._create_grid_area()
        content_layout.addWidget(grid_area, stretch=1)
        
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_filter_sidebar(self) -> QWidget:
        """Filter sidebar with Gender / Tone / Pitch radio groups."""
        sidebar = QFrame()
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background: {Theme.SURFACE0}; border: none;")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        from services.voice_library import get_voice_library
        lib = get_voice_library()
        
        # === Gender filter ===
        layout.addWidget(self._section_label("🔘 Gender"))
        self._gender_group = QButtonGroup(self)
        for i, name in enumerate(lib.GENDER_FILTERS):
            radio = QRadioButton(name)
            radio.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px;")
            if name == self._filter_gender:
                radio.setChecked(True)
            self._gender_group.addButton(radio, i)
            layout.addWidget(radio)
        self._gender_group.buttonClicked.connect(self._on_filter_changed)
        
        layout.addSpacing(8)
        
        # === Tone filter ===
        layout.addWidget(self._section_label("🎵 Tone"))
        self._tone_group = QButtonGroup(self)
        for i, name in enumerate(lib.TONE_FILTERS):
            radio = QRadioButton(name)
            radio.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px;")
            if name == self._filter_tone:
                radio.setChecked(True)
            self._tone_group.addButton(radio, i)
            layout.addWidget(radio)
        self._tone_group.buttonClicked.connect(self._on_filter_changed)
        
        layout.addSpacing(8)
        
        # === Pitch filter ===
        layout.addWidget(self._section_label("🎚️ Pitch"))
        self._pitch_group = QButtonGroup(self)
        for i, name in enumerate(lib.PITCH_FILTERS):
            radio = QRadioButton(name)
            radio.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px;")
            if name == self._filter_pitch:
                radio.setChecked(True)
            self._pitch_group.addButton(radio, i)
            layout.addWidget(radio)
        self._pitch_group.buttonClicked.connect(self._on_filter_changed)
        
        layout.addStretch()
        
        # Reset button
        reset_btn = QPushButton("🔄 Reset Filters")
        reset_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"border: none; border-radius: 4px; padding: 6px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {Theme.OVERLAY0}; }}"
        )
        reset_btn.clicked.connect(self._reset_filters)
        layout.addWidget(reset_btn)
        
        scroll.setWidget(container)
        
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(scroll)
        
        return sidebar
    
    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {Theme.TEXT}; font-weight: bold; font-size: 12px; "
            f"border: none; background: transparent;"
        )
        return label
    
    def _create_grid_area(self) -> QWidget:
        """Grid area: toolbar + scrollable grid + player bar."""
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # Toolbar: search + count
        toolbar = QHBoxLayout()
        
        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText("🔍 Search by voice name...")
        self._search_entry.setFixedWidth(220)
        self._search_entry.setMinimumHeight(30)
        self._search_entry.setStyleSheet(
            f"background: {Theme.SURFACE1}; color: {Theme.TEXT}; "
            f"border: 1px solid {Theme.SURFACE2}; border-radius: 4px; padding: 4px 8px;"
        )
        self._search_entry.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search_entry)
        
        toolbar.addStretch()
        
        self._voice_count = QLabel("30 voices")
        self._voice_count.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        toolbar.addWidget(self._voice_count)
        
        layout.addLayout(toolbar)
        
        # Scrollable grid
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setStyleSheet(f"background: {Theme.SURFACE0}; border-radius: 6px;")
        self._grid_scroll.setWidgetResizable(True)
        
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(8)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_scroll.setWidget(self._grid_widget)
        
        layout.addWidget(self._grid_scroll, stretch=1)
        
        # Player bar (bottom)
        self._player_bar = self._create_player_bar()
        layout.addWidget(self._player_bar)
        
        # Action buttons bar
        action_bar = self._create_action_bar()
        layout.addWidget(action_bar)
        
        return area
    
    def _create_player_bar(self) -> QFrame:
        """Now-playing bar at bottom of grid."""
        bar = QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"background: {Theme.SURFACE1}; border-radius: 6px; "
            f"border: 1px solid {Theme.SURFACE2};"
        )
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)
        
        self._play_indicator = QLabel("🔇 No voice playing")
        self._play_indicator.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none; background: transparent;"
        )
        layout.addWidget(self._play_indicator, stretch=1)
        
        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setFixedHeight(26)
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.RED}; color: {Theme.CRUST}; "
            f"border: none; border-radius: 4px; padding: 2px 10px; "
            f"font-size: 11px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #EBA0AC; }}"
        )
        self._stop_btn.clicked.connect(self._stop_playback)
        self._stop_btn.hide()
        layout.addWidget(self._stop_btn)
        
        return bar
    
    def _create_action_bar(self) -> QFrame:
        """Bottom action buttons: Select for All / Select for Empty."""
        bar = QFrame()
        bar.setFixedHeight(40)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        
        self._selected_display = QLabel("Selected: —")
        self._selected_display.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(self._selected_display)
        
        layout.addStretch()
        
        _btn_css = (
            f"border: none; border-radius: 4px; padding: 6px 14px; "
            f"font-weight: bold; font-size: 12px;"
        )
        
        # Select for empty prompts only
        sel_empty_btn = QPushButton("✅ Select for Empty")
        sel_empty_btn.setToolTip("Apply voice to prompts that don't have a voice yet")
        sel_empty_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.LAVENDER}; color: {Theme.CRUST}; {_btn_css} }}"
            f"QPushButton:hover {{ background: #B4BEFE; }}"
        )
        sel_empty_btn.clicked.connect(self._on_select_empty)
        layout.addWidget(sel_empty_btn)
        
        # Select for ALL prompts
        sel_all_btn = QPushButton("✅ Select for ALL")
        sel_all_btn.setToolTip("Apply voice to ALL parsed prompts (overwrite existing)")
        sel_all_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.GREEN}; color: {Theme.CRUST}; {_btn_css} }}"
            f"QPushButton:hover {{ background: #B8F0B2; }}"
        )
        sel_all_btn.clicked.connect(self._on_select_all)
        layout.addWidget(sel_all_btn)
        
        # Update display
        self._update_selected_display()
        
        return bar
    
    def _create_footer(self):
        """Minimal footer (hidden)."""
        self.footer = QFrame()
        self.footer.setFixedHeight(0)
        self._main_layout.addWidget(self.footer)
    
    # ─── Grid Rendering ──────────────────────────────────────────
    
    def _reload_grid(self):
        """Rebuild voice card grid with current filters."""
        # Clear grid
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._voice_cards.clear()
        
        from services.voice_library import get_voice_library
        lib = get_voice_library()
        
        voices = lib.get_voices(self._filter_gender, self._filter_tone, self._filter_pitch)
        
        # Apply search
        if self._search_query:
            q = self._search_query.lower()
            voices = [v for v in voices if q in v.display_name.lower() or q in v.id]
        
        self._voice_count.setText(f"{len(voices)} voices")
        
        if not voices:
            empty = QLabel("No voices match the current filters.")
            empty.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 12px;")
            empty.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(empty, 0, 0, 1, self.GRID_COLS)
            return
        
        for i, voice in enumerate(voices):
            row = i // self.GRID_COLS
            col = i % self.GRID_COLS
            
            card = _VoiceCard(voice, is_selected=(voice.id == self._current_voice))
            card.play_clicked.connect(self._play_voice)
            card.select_clicked.connect(self._select_voice)
            
            self._voice_cards[voice.id] = card
            self._grid_layout.addWidget(card, row, col, alignment=Qt.AlignTop)
    
    # ─── Filter Handlers ─────────────────────────────────────────
    
    def _on_filter_changed(self):
        """Handle radio button change."""
        checked_gender = self._gender_group.checkedButton()
        checked_tone = self._tone_group.checkedButton()
        checked_pitch = self._pitch_group.checkedButton()
        
        self._filter_gender = checked_gender.text() if checked_gender else "All"
        self._filter_tone = checked_tone.text() if checked_tone else "All"
        self._filter_pitch = checked_pitch.text() if checked_pitch else "All"
        
        self._reload_grid()
    
    def _on_search(self, text: str):
        self._search_query = text.strip()
        self._reload_grid()
    
    def _reset_filters(self):
        """Reset all filters to 'All'."""
        # Check first button in each group (All)
        for group in (self._gender_group, self._tone_group, self._pitch_group):
            btn = group.button(0)
            if btn:
                btn.setChecked(True)
        self._filter_gender = "All"
        self._filter_tone = "All"
        self._filter_pitch = "All"
        self._search_query = ""
        self._search_entry.clear()
        self._reload_grid()
    
    # ─── Voice Selection ─────────────────────────────────────────
    
    def _select_voice(self, voice_id: str):
        """Handle voice card select click."""
        # Deselect old
        if self._current_voice and self._current_voice in self._voice_cards:
            self._voice_cards[self._current_voice].set_selected(False)
        
        self._current_voice = voice_id
        
        # Highlight new
        if voice_id in self._voice_cards:
            self._voice_cards[voice_id].set_selected(True)
        
        self._update_selected_display()
    
    def _on_select_all(self):
        """Apply current voice to ALL prompts."""
        if self._current_voice and self._cb_select_all:
            self._cb_select_all(self._current_voice)
            # Toast feedback
            main_win = self.window()
            if hasattr(main_win, 'show_toast'):
                from services.voice_library import get_voice_library
                v = get_voice_library().get_voice(self._current_voice)
                name = v.display_name if v else self._current_voice
                main_win.show_toast(f"🎤 {name} applied to ALL prompts", "success")
    
    def _on_select_empty(self):
        """Apply current voice to prompts without voice."""
        if self._current_voice and self._cb_select_empty:
            self._cb_select_empty(self._current_voice)
            main_win = self.window()
            if hasattr(main_win, 'show_toast'):
                from services.voice_library import get_voice_library
                v = get_voice_library().get_voice(self._current_voice)
                name = v.display_name if v else self._current_voice
                main_win.show_toast(f"🎤 {name} applied to empty prompts", "success")
    
    def _update_selected_display(self):
        """Update the 'Selected: ...' label."""
        if self._current_voice:
            from services.voice_library import get_voice_library
            v = get_voice_library().get_voice(self._current_voice)
            if v:
                self._selected_display.setText(
                    f"Selected: {v.gender_icon} {v.display_name}"
                )
                self._selected_display.setStyleSheet(
                    f"color: {v.gender_color}; font-size: 11px; font-weight: bold;"
                )
                return
        self._selected_display.setText("Selected: —")
        self._selected_display.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold;"
        )
    
    # ─── Audio Playback ──────────────────────────────────────────
    
    def _play_voice(self, voice_id: str):
        """Play voice preview WAV."""
        from services.voice_library import get_voice_library
        lib = get_voice_library()
        voice = lib.get_voice(voice_id)
        if not voice:
            return
        
        # Stop current playback
        self._stop_playback()
        
        # Check cache
        cached = lib.get_cached_wav(voice_id)
        if cached and cached.exists():
            self._play_local(cached, voice)
        else:
            # Download in background
            self._play_indicator.setText(f"⏳ Downloading {voice.display_name}...")
            self._download_worker = _WavDownloadWorker(voice_id, self)
            self._download_worker.finished.connect(self._on_wav_downloaded)
            self._download_worker.start()
    
    def _on_wav_downloaded(self, voice_id: str, local_path: str):
        """Handle WAV download completion."""
        if not local_path:
            self._play_indicator.setText(f"❌ Download failed")
            return
        
        from services.voice_library import get_voice_library
        voice = get_voice_library().get_voice(voice_id)
        if voice:
            self._play_local(Path(local_path), voice)
    
    def _play_local(self, path: Path, voice):
        """Play a local WAV file."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        except ImportError:
            self._play_indicator.setText("❌ QtMultimedia not available")
            return
        
        if not self._player:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            self._player.mediaStatusChanged.connect(self._on_media_status)
        
        self._playing_voice = voice.id
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        
        self._play_indicator.setText(
            f"🔊 Playing: {voice.gender_icon} {voice.display_name}"
        )
        self._play_indicator.setStyleSheet(
            f"color: {voice.gender_color}; font-size: 11px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        self._stop_btn.show()
    
    def _stop_playback(self):
        """Stop current audio playback."""
        if self._player:
            self._player.stop()
        self._playing_voice = ""
        self._play_indicator.setText("🔇 No voice playing")
        self._play_indicator.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none; background: transparent;"
        )
        self._stop_btn.hide()
    
    def _on_media_status(self, status):
        """Handle QMediaPlayer status changes."""
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                self._stop_playback()
        except Exception:
            pass
    
    def closeEvent(self, event):
        """Cleanup on close."""
        self._stop_playback()
        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.quit()
        super().closeEvent(event)
