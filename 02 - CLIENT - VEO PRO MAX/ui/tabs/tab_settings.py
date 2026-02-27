"""
TabSettings — Settings tab for application configuration.

Componentised via 4 mixins in settings_components/:
  • SettingsProfilesMixin    — Chrome profiles table
  • SettingsSectionsMixin    — Default/Output/Continuation/Worker/Session/Notification/UI
  • SettingsPipelineEnhancerMixin — Pipeline + Enhancer
  • SettingsBrowserControlsMixin  — Browser visibility, login, restart, ext, CRUD
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QScrollArea,
)
from ui.popups import show_info, show_warning, show_confirm
from PySide6.QtCore import Qt, Signal, Slot, QTimer

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme

# ── Mixin imports ──
from ui.tabs.settings_components import (
    SettingsProfilesMixin,
    SettingsSectionsMixin,
    SettingsPipelineEnhancerMixin,
    SettingsBrowserControlsMixin,
)


# ─────────────────────────────────────────────────────────────
# ToggleSwitch — compact on/off widget used throughout settings
# ─────────────────────────────────────────────────────────────
class ToggleSwitch(QWidget):
    """Custom toggle switch widget with on/off state and signal."""
    toggled_signal = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(48, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._row_layout = None  # Set by _create_enable_row

    def isToggled(self) -> bool:
        return self._checked

    def setToggled(self, state: bool):
        self._checked = state
        self.update()
        self.toggled_signal.emit(state)

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self.update()
        self.toggled_signal.emit(self._checked)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QPen
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Track
        track_color = QColor(Theme.GREEN) if self._checked else QColor(Theme.SURFACE2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(QRectF(0, 2, 48, 20), 10, 10)

        # Thumb
        thumb_x = 28 if self._checked else 2
        p.setBrush(QColor(Theme.TEXT))
        p.drawEllipse(QRectF(thumb_x, 4, 16, 16))
        p.end()


# ─────────────────────────────────────────────────────────────
# TabSettings — main class (inherits 4 mixins)
# ─────────────────────────────────────────────────────────────
class TabSettings(
    SettingsProfilesMixin,
    SettingsSectionsMixin,
    SettingsPipelineEnhancerMixin,
    SettingsBrowserControlsMixin,
    QWidget,
):
    """Settings tab — all UI sections are built by mixin methods.

    ⚠️ MRO Cross-dependencies between mixins:
    - SettingsProfilesMixin (UI builder) calls handlers from SettingsBrowserControlsMixin:
      _on_toggle_account, _on_slots_changed, _on_save_password, _on_refresh_session,
      _on_toggle_browser_visibility, _on_restart_browser, _on_reload_extension,
      _on_delete_profile, _on_add_profile_browser
    - All mixins call _create_section() and _create_enable_row() from TabSettings base.
    - All mixins reference self.controller and self.profiles_controller from __init__.
    """

    settings_changed = Signal(dict)

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller

        # ProfilesController — always needed, even without app controller
        from core.profiles_controller import get_profiles_controller
        self.profiles_controller = get_profiles_controller()

        # Shared widget state dictionaries (populated by mixin section builders)
        self.setting_combos = {}
        self.output_toggles = {}
        self._restore_sub_toggles = {}
        
        # Tester-only sections (hidden for regular users)
        self._tester_sections: list = []

        self._setup_ui()
        
        # Apply audience visibility (User vs Tester)
        self._apply_audience_visibility()

        # Periodic refresh: ext status column every 5 s
        self._ext_timer = QTimer(self)
        self._ext_timer.timeout.connect(self._refresh_ext_column)
        self._ext_timer.start(5000)

    # ── Layout ──────────────────────────────────────────────

    def _setup_ui(self):
        """Build the scrollable settings page — each section from a mixin."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)

        container = QWidget()
        # Global fix: prevent spinbox text from being clipped by up/down arrow buttons
        container.setStyleSheet(container.styleSheet() + f"""
            QSpinBox, QDoubleSpinBox {{
                padding-right: 20px;
                color: {Theme.TEXT};
                background-color: {Theme.SURFACE1};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{
                width: 18px;
            }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                width: 18px;
            }}
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Guard: prevent auto-save signals from writing to disk during init
        self._initializing = True

        # Build all sections via mixins
        # ── User sections (visible to everyone) ──
        layout.addWidget(self._create_profiles_section())   # SettingsProfilesMixin
        layout.addWidget(self._create_defaults_section())    # SettingsSectionsMixin
        layout.addWidget(self._create_output_section())      # SettingsSectionsMixin
        layout.addWidget(self._create_continuation_section())# SettingsSectionsMixin
        layout.addWidget(self._create_notification_section())# SettingsSectionsMixin
        layout.addWidget(self._create_post_queue_section())  # SettingsSectionsMixin
        layout.addWidget(self._create_ui_section())          # SettingsSectionsMixin
        
        # ── Tester sections (hidden for regular users) ──
        tester_widgets = [
            self._create_worker_section(),                    # SettingsSectionsMixin
            self._create_browser_visibility_section(),        # SettingsSectionsMixin
            self._create_session_section(),                   # SettingsSectionsMixin
            self._create_pipeline_section(),                  # SettingsPipelineEnhancerMixin
            self._create_enhancer_section(),                  # SettingsPipelineEnhancerMixin
        ]
        for w in tester_widgets:
            layout.addWidget(w)
            self._tester_sections.append(w)
        
        layout.addWidget(self._create_action_buttons())      # core

        # All sections built — allow auto-save signals now
        self._initializing = False

        layout.addStretch()
        scroll.setWidget(container)

    # ── Section helper (used by mixins) ─────────────────────

    def _create_section(self, title: str):
        """Create a collapsible-style section frame. Returns (section, layout)."""
        section = QFrame()
        section.setObjectName("settingsSection")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        header = QLabel(title)
        header.setStyleSheet(f"color: {Theme.TEXT}; font-size: 14px; font-weight: bold; border: none; padding: 0;")
        layout.addWidget(header)

        return section, layout
    
    def _apply_audience_visibility(self):
        """Show/hide tester-only sections based on license tier.
        
        User mode: Profiles, Defaults, Output, Continuation, Notification, Post-Queue, UI
        Tester mode: + Worker, Browser Visibility, Session, Pipeline, Enhancer
        """
        is_tester = False
        try:
            if self.controller and hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                is_tester = hasattr(lc, 'can_see_dev_console') and lc.can_see_dev_console()
        except Exception:
            pass
        
        for section in self._tester_sections:
            section.setVisible(is_tester)

    def _create_enable_row(self, label: str, checked: bool = True,
                           bold: bool = False, color: str = None,
                           badge: str = None) -> ToggleSwitch:
        """Create a label + ToggleSwitch row. The switch carries ._row_layout."""
        row = QHBoxLayout()

        lbl = QLabel(label)
        style = f"color: {color or Theme.TEXT};"
        if bold:
            style += " font-weight: bold;"
        lbl.setStyleSheet(style)
        lbl.setFixedWidth(150)
        row.addWidget(lbl)

        switch = ToggleSwitch(checked=checked)
        switch._row_layout = row
        row.addWidget(switch)

        if badge:
            badge_label = QLabel(badge)
            badge_label.setStyleSheet(
                f"color: {Theme.CRUST}; background-color: {Theme.YELLOW}; "
                f"font-size: 9px; font-weight: bold; padding: 1px 6px; border-radius: 4px;"
            )
            row.addWidget(badge_label)

        row.addStretch()
        return switch

    def _create_setting_row(self, parent_layout, label: str, options: list) -> QComboBox:
        """Create a label + QComboBox setting row."""
        row_layout = QHBoxLayout()

        label_widget = QLabel(f"{label}:")
        label_widget.setFixedWidth(150)
        label_widget.setStyleSheet(f"color: {Theme.TEXT};")
        row_layout.addWidget(label_widget)

        combo = QComboBox()
        combo.addItems(options)
        combo.setFixedWidth(200)
        row_layout.addWidget(combo)

        row_layout.addStretch()
        parent_layout.addLayout(row_layout)

        return combo

    # ── Action buttons (Save / Reset / Export / Import / Reload) ──

    def _create_action_buttons(self) -> QWidget:
        """Create action buttons - matches CTK lines 357-401."""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 16, 0, 0)

        # Save All button - explicitly force-saves all sections
        save_btn = QPushButton("💾 Save All")
        save_btn.setToolTip("Force-save ALL settings to disk (individual settings also auto-save on change)")
        save_btn.setStyleSheet(f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; height: 36px;")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        # Reset Defaults button
        reset_btn = QPushButton("🔄 Reset Defaults")
        reset_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; height: 36px;")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        # Export Config button - blue
        export_btn = QPushButton("📤 Export Config")
        export_btn.setStyleSheet(f"background-color: {Theme.BLUE}; height: 36px;")
        export_btn.clicked.connect(self._on_export)
        layout.addWidget(export_btn)

        # Import Config button
        import_btn = QPushButton("📥 Import Config")
        import_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; height: 36px;")
        import_btn.clicked.connect(self._on_import)
        layout.addWidget(import_btn)

        # Reload App button — restart Python process
        reload_btn = QPushButton("🔄 Reload App")
        reload_btn.setToolTip("Restart application (browsers keep running)")
        reload_btn.setStyleSheet(f"background-color: #FF6B00; color: {Theme.CRUST}; height: 36px; font-weight: bold;")
        reload_btn.clicked.connect(self._on_reload_app)
        layout.addWidget(reload_btn)

        layout.addStretch()

        return frame

    def _on_save(self):
        """Save ALL settings to AppSettings and persist to disk."""
        import logging
        log = logging.getLogger("settings")

        try:
            from config.settings import get_settings, save_settings
            s = get_settings()

            # ── Default Settings ──
            if "Aspect Ratio" in self.setting_combos:
                ar = self.setting_combos["Aspect Ratio"].currentText()
                s.default_aspect_ratio = "PORTRAIT" if "Portrait" in ar else "LANDSCAPE"
            if "Outputs per Prompt" in self.setting_combos:
                s.default_output_count = int(self.setting_combos["Outputs per Prompt"].currentText())
            if "AI Model" in self.setting_combos:
                s.default_model = self.setting_combos["AI Model"].currentText()
            if "Download Quality" in self.setting_combos:
                s.default_download_quality = self.setting_combos["Download Quality"].currentText()
            if "Image AI Model" in self.setting_combos:
                s.default_image_model = self.setting_combos["Image AI Model"].currentText()
            if "Image Quality" in self.setting_combos:
                s.default_image_quality = self.setting_combos["Image Quality"].currentText()

            # ── Output Settings ──
            s.output_folder = self.output_folder_entry.text()
            if "Include timestamp in filename" in self.output_toggles:
                s.include_timestamp = self.output_toggles["Include timestamp in filename"].isChecked()
            if "Include quality in filename" in self.output_toggles:
                s.include_quality = self.output_toggles["Include quality in filename"].isChecked()
            if "Auto-start queue when adding" in self.output_toggles:
                s.auto_start_queue = self.output_toggles["Auto-start queue when adding"].isChecked()
            if "Pause on error" in self.output_toggles:
                s.pause_on_error = self.output_toggles["Pause on error"].isChecked()

            # ── Continuation ──
            if hasattr(self, 'cont_switch'):
                s.continuation_enabled = self.cont_switch.isToggled()
            if hasattr(self, 'extract_menu'):
                s.extract_point_ms = self._parse_extract_point(self.extract_menu.currentText())

            # ── Worker Settings ──
            if hasattr(self, 'retry_count'):
                s.retry_count = self.retry_count.value()
            if hasattr(self, 'request_timeout'):
                s.request_timeout = self.request_timeout.value()

            # ── Anti-Detect Spam ──
            if hasattr(self, 'anti_detect_switch'):
                s.anti_detect_enabled = self.anti_detect_switch.isToggled()
            if hasattr(self, 'anti_detect_delay_min'):
                s.anti_detect_delay_min = self.anti_detect_delay_min.value()
            if hasattr(self, 'anti_detect_delay_max'):
                s.anti_detect_delay_max = self.anti_detect_delay_max.value()

            # ── Session & Data ──
            if hasattr(self, 'restore_queue_switch'):
                s.restore_queue_on_startup = self.restore_queue_switch.isToggled()
            if hasattr(self, 'restore_tabs_switch'):
                s.restore_tabs_on_startup = self.restore_tabs_switch.isToggled()
            if hasattr(self, '_restore_sub_toggles'):
                for attr_name, toggle in self._restore_sub_toggles.items():
                    setattr(s, attr_name, toggle.isToggled())

            # ── Notifications ──
            if hasattr(self, 'notify_toast_toggle'):
                s.notify_toast_enabled = self.notify_toast_toggle.isToggled()
            if hasattr(self, 'notify_sound_toggle'):
                s.notify_sound_enabled = self.notify_sound_toggle.isToggled()
            if hasattr(self, '_get_selected_sound'):
                s.notify_sound_file = self._get_selected_sound()

            # ── Post-Queue Action ──
            if hasattr(self, 'post_queue_switch'):
                s.post_queue_action_enabled = self.post_queue_switch.isToggled()
            if hasattr(self, 'post_queue_action_combo'):
                _reverse_map = {"🔌 Do Nothing": "nothing", "⚡ Shutdown": "shutdown", "💤 Sleep": "sleep"}
                s.post_queue_action = _reverse_map.get(
                    self.post_queue_action_combo.currentText(), "nothing"
                )

            # ── Enhancer Toggles ──
            if hasattr(self, '_enhance_context_toggle'):
                s.enhance_context_menu = self._enhance_context_toggle.isToggled()
            if hasattr(self, '_enhance_library_toggle'):
                s.enhance_library = self._enhance_library_toggle.isToggled()
            if hasattr(self, '_enhance_auto_toggle'):
                s.enhance_auto_continuation = self._enhance_auto_toggle.isToggled()

            # ── Browser Visibility ──
            if hasattr(self, 'smart_hide_switch'):
                s.smart_hide_enabled = self.smart_hide_switch.isToggled()

            # ── Pipeline Optimization ──
            if hasattr(self, 'burst_switch'):
                s.adaptive_burst_enabled = self.burst_switch.isToggled()
            if hasattr(self, 'burst_min'):
                s.burst_min_delay = self.burst_min.value()
            if hasattr(self, 'burst_max'):
                s.burst_max_delay = self.burst_max.value()
            if hasattr(self, 'pool_switch'):
                s.recaptcha_pool_enabled = self.pool_switch.isToggled()
            if hasattr(self, 'pool_size'):
                s.recaptcha_pool_size = self.pool_size.value()
            if hasattr(self, 'watchdog_timeout'):
                s.watchdog_timeout_min = self.watchdog_timeout.value()
            if hasattr(self, 'journal_interval'):
                s.journal_save_interval_sec = self.journal_interval.value()
            if hasattr(self, 'workload_priority') and hasattr(self, '_wp_map'):
                s.workload_priority = self._wp_map.get(
                    self.workload_priority.currentIndex(), '720p_priority'
                )

            # ── UI (Language) ──
            if hasattr(self, 'lang_menu'):
                s.ui_language = self.lang_menu.currentText()

            # Persist to disk
            save_settings()
            log.info(f"Settings saved to {s._default_path()}")

            # Show confirmation
            show_info(self, "Saved", "✅ All settings saved successfully.")

            # Also emit signal for live-update consumers
            settings_dict = self.get_settings()
            self.settings_changed.emit(settings_dict)
        except Exception as e:
            log.error(f"Failed to save settings: {e}")
            show_warning(self, "Error", f"Failed to save settings:\n{e}")

    def _on_reset(self):
        """Reset to default values and persist."""
        if not show_confirm(self, "Reset Defaults",
                "Reset all settings to factory defaults?\n\nThis cannot be undone.",
                danger=True):
            return

        # Guard: prevent cascade auto-saves while resetting widgets
        self._initializing = True

        try:
            # ── Default Settings ──
            if "Aspect Ratio" in self.setting_combos:
                self.setting_combos["Aspect Ratio"].setCurrentText("16:9 (Landscape)")
            if "Outputs per Prompt" in self.setting_combos:
                self.setting_combos["Outputs per Prompt"].setCurrentText("4")
            if "AI Model" in self.setting_combos:
                self.setting_combos["AI Model"].setCurrentText("Veo 3.1 - Fast")
            if "Download Quality" in self.setting_combos:
                self.setting_combos["Download Quality"].setCurrentText("1080p")
            if "Image AI Model" in self.setting_combos:
                self.setting_combos["Image AI Model"].setCurrentText("🔥 Nano Banana Pro")
            if "Image Quality" in self.setting_combos:
                self.setting_combos["Image Quality"].setCurrentText("1k")

            # ── Output Toggles ──
            if hasattr(self, 'output_toggles'):
                for key, toggle in self.output_toggles.items():
                    if "timestamp" in key.lower() or "quality" in key.lower() or "Pause" in key:
                        toggle.setChecked(True)
                    else:
                        toggle.setChecked(False)

            # ── Continuation ──
            if hasattr(self, 'cont_switch'):
                self.cont_switch.setToggled(True)
            if hasattr(self, 'extract_menu'):
                self.extract_menu.setCurrentText("750ms (recommended)")

            # ── Worker Settings ──
            self.retry_count.setValue(3)
            self.request_timeout.setValue(120)

            # ── Anti-Detect Spam ──
            self.anti_detect_switch.setToggled(True)
            self.anti_detect_delay_min.setValue(3.0)
            self.anti_detect_delay_max.setValue(8.0)

            # ── Enhancer Toggles ──
            if hasattr(self, '_enhance_context_toggle'):
                self._enhance_context_toggle.setToggled(True)
            if hasattr(self, '_enhance_library_toggle'):
                self._enhance_library_toggle.setToggled(True)
            if hasattr(self, '_enhance_auto_toggle'):
                self._enhance_auto_toggle.setToggled(False)

            # ── Session & Data ──
            self.restore_queue_switch.setToggled(False)
            self.restore_tabs_switch.setToggled(True)
            # Reset granular restore sub-toggles to ON
            if hasattr(self, '_restore_sub_toggles'):
                for attr_name, toggle in self._restore_sub_toggles.items():
                    toggle.setToggled(True)

            # ── Notifications ──
            if hasattr(self, 'notify_toast_toggle'):
                self.notify_toast_toggle.setToggled(True)
            if hasattr(self, 'notify_sound_toggle'):
                self.notify_sound_toggle.setToggled(True)
            if hasattr(self, 'sound_file_combo'):
                self.sound_file_combo.setCurrentIndex(0)  # default sound

            # ── Post-Queue Action ──
            if hasattr(self, 'post_queue_switch'):
                self.post_queue_switch.setToggled(False)
            if hasattr(self, 'post_queue_action_combo'):
                self.post_queue_action_combo.setCurrentText("🔌 Do Nothing")

            # ── Browser Visibility ──
            if hasattr(self, 'smart_hide_switch'):
                self.smart_hide_switch.setToggled(True)

            # ── Pipeline Optimization ──
            if hasattr(self, 'burst_switch'):
                self.burst_switch.setToggled(True)
            if hasattr(self, 'burst_min'):
                self.burst_min.setValue(2.0)
            if hasattr(self, 'burst_max'):
                self.burst_max.setValue(15.0)
            if hasattr(self, 'pool_switch'):
                self.pool_switch.setToggled(True)
            if hasattr(self, 'pool_size'):
                self.pool_size.setValue(2)
            if hasattr(self, 'watchdog_timeout'):
                self.watchdog_timeout.setValue(10)
            if hasattr(self, 'journal_interval'):
                self.journal_interval.setValue(30)
            if hasattr(self, 'workload_priority'):
                self.workload_priority.setCurrentIndex(0)  # 720p_priority

            # ── Language ──
            if hasattr(self, 'lang_menu'):
                self.lang_menu.setCurrentText("English")
        finally:
            # Allow auto-save signals again
            self._initializing = False

        # Persist all reset values to disk in one write
        self._on_save()

    def _on_export(self):
        """Export config to file."""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Config", "", "JSON Files (*.json)"
        )
        if file_path:
            import json
            settings = self.get_settings()
            with open(file_path, 'w') as f:
                json.dump(settings, f, indent=2)

    def _on_import(self):
        """Import config from file and persist."""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Config", "", "JSON Files (*.json)"
        )
        if file_path:
            import json
            with open(file_path, 'r') as f:
                settings = json.load(f)
            # Apply settings to widgets
            self._apply_imported_settings(settings)
            # Persist via Save button logic
            self._on_save()

    def _apply_imported_settings(self, settings: dict):
        """Apply imported settings to UI widgets — covers ALL sections."""
        # Default Settings
        if "aspect_ratio" in settings and "Aspect Ratio" in self.setting_combos:
            self.setting_combos["Aspect Ratio"].setCurrentText(settings["aspect_ratio"])
        if "download_quality" in settings and "Download Quality" in self.setting_combos:
            self.setting_combos["Download Quality"].setCurrentText(settings["download_quality"])
        if "ai_model" in settings and "AI Model" in self.setting_combos:
            self.setting_combos["AI Model"].setCurrentText(settings["ai_model"])
        if "image_ai_model" in settings and "Image AI Model" in self.setting_combos:
            self.setting_combos["Image AI Model"].setCurrentText(settings["image_ai_model"])
        if "image_quality" in settings and "Image Quality" in self.setting_combos:
            self.setting_combos["Image Quality"].setCurrentText(settings["image_quality"])
        if "outputs_per_prompt" in settings and "Outputs per Prompt" in self.setting_combos:
            self.setting_combos["Outputs per Prompt"].setCurrentText(str(settings["outputs_per_prompt"]))
        # Output Settings
        if "output_folder" in settings:
            self.output_folder_entry.setText(settings["output_folder"])
        for key, toggle_name in [
            ("include_timestamp", "Include timestamp in filename"),
            ("include_quality", "Include quality in filename"),
            ("auto_start_queue", "Auto-start queue when adding"),
            ("pause_on_error", "Pause on error"),
        ]:
            if key in settings and toggle_name in self.output_toggles:
                self.output_toggles[toggle_name].setChecked(bool(settings[key]))
        # Continuation
        if "continuation_enabled" in settings and hasattr(self, 'cont_switch'):
            self.cont_switch.setToggled(bool(settings["continuation_enabled"]))
        if "extract_point_ms" in settings and hasattr(self, 'extract_menu'):
            ms = int(settings["extract_point_ms"])
            for i in range(self.extract_menu.count()):
                if str(ms) in self.extract_menu.itemText(i):
                    self.extract_menu.setCurrentIndex(i)
                    break
        # Worker settings
        if "retry_count" in settings:
            self.retry_count.setValue(int(settings["retry_count"]))
        if "request_timeout" in settings:
            self.request_timeout.setValue(int(settings["request_timeout"]))
        # Anti-Detect Spam
        if "anti_detect_enabled" in settings:
            self.anti_detect_switch.setToggled(bool(settings["anti_detect_enabled"]))
        if "anti_detect_delay_min" in settings:
            self.anti_detect_delay_min.setValue(float(settings["anti_detect_delay_min"]))
        if "anti_detect_delay_max" in settings:
            self.anti_detect_delay_max.setValue(float(settings["anti_detect_delay_max"]))
        # Session & Data
        if "restore_queue_on_startup" in settings:
            self.restore_queue_switch.setToggled(bool(settings["restore_queue_on_startup"]))
        if "restore_tabs_on_startup" in settings:
            self.restore_tabs_switch.setToggled(bool(settings["restore_tabs_on_startup"]))
        # Granular restore sub-toggles
        if hasattr(self, '_restore_sub_toggles'):
            for attr_name, toggle in self._restore_sub_toggles.items():
                if attr_name in settings:
                    toggle.setToggled(bool(settings[attr_name]))
        # Notifications
        if "notify_toast_enabled" in settings and hasattr(self, 'notify_toast_toggle'):
            self.notify_toast_toggle.setToggled(bool(settings["notify_toast_enabled"]))
        if "notify_sound_enabled" in settings and hasattr(self, 'notify_sound_toggle'):
            self.notify_sound_toggle.setToggled(bool(settings["notify_sound_enabled"]))
        # Post-Queue Action
        if "post_queue_action_enabled" in settings and hasattr(self, 'post_queue_switch'):
            self.post_queue_switch.setToggled(bool(settings["post_queue_action_enabled"]))
        if "post_queue_action" in settings and hasattr(self, 'post_queue_action_combo'):
            _action_map = {"nothing": "🔌 Do Nothing", "shutdown": "⚡ Shutdown", "sleep": "💤 Sleep"}
            self.post_queue_action_combo.setCurrentText(
                _action_map.get(settings["post_queue_action"], "🔌 Do Nothing")
            )
        # Browser Visibility
        if "smart_hide_enabled" in settings and hasattr(self, 'smart_hide_switch'):
            self.smart_hide_switch.setToggled(bool(settings["smart_hide_enabled"]))
        # Enhancer
        if "enhance_context_menu" in settings and hasattr(self, '_enhance_context_toggle'):
            self._enhance_context_toggle.setToggled(bool(settings["enhance_context_menu"]))
        if "enhance_library" in settings and hasattr(self, '_enhance_library_toggle'):
            self._enhance_library_toggle.setToggled(bool(settings["enhance_library"]))
        if "enhance_auto_continuation" in settings and hasattr(self, '_enhance_auto_toggle'):
            self._enhance_auto_toggle.setToggled(bool(settings["enhance_auto_continuation"]))
        # Pipeline Optimization
        if "adaptive_burst_enabled" in settings and hasattr(self, 'burst_switch'):
            self.burst_switch.setToggled(bool(settings["adaptive_burst_enabled"]))
        if "burst_min_delay" in settings and hasattr(self, 'burst_min'):
            self.burst_min.setValue(float(settings["burst_min_delay"]))
        if "burst_max_delay" in settings and hasattr(self, 'burst_max'):
            self.burst_max.setValue(float(settings["burst_max_delay"]))
        if "recaptcha_pool_enabled" in settings and hasattr(self, 'pool_switch'):
            self.pool_switch.setToggled(bool(settings["recaptcha_pool_enabled"]))
        if "recaptcha_pool_size" in settings and hasattr(self, 'pool_size'):
            self.pool_size.setValue(int(settings["recaptcha_pool_size"]))
        if "watchdog_timeout_min" in settings and hasattr(self, 'watchdog_timeout'):
            self.watchdog_timeout.setValue(int(settings["watchdog_timeout_min"]))
        if "journal_save_interval_sec" in settings and hasattr(self, 'journal_interval'):
            self.journal_interval.setValue(int(settings["journal_save_interval_sec"]))
        if "workload_priority" in settings and hasattr(self, 'workload_priority') and hasattr(self, '_wp_map'):
            # Reverse-map value → index
            rev = {v: k for k, v in self._wp_map.items()}
            idx = rev.get(settings["workload_priority"], 1)
            self.workload_priority.setCurrentIndex(idx)
        # Language
        if "language" in settings and hasattr(self, 'lang_menu'):
            self.lang_menu.setCurrentText(settings["language"])

    # ── Helpers ──

    def _parse_extract_point(self, text: str) -> int:
        """Convert '750ms (recommended)' → 750."""
        import re
        match = re.search(r'(\d+)', text)
        return int(match.group(1)) if match else 750

    def get_settings(self) -> dict:
        """Get current settings — used for export and signal emission."""
        result = {
            "aspect_ratio": self.setting_combos.get("Aspect Ratio").currentText() if "Aspect Ratio" in self.setting_combos else "",
            "download_quality": self.setting_combos.get("Download Quality").currentText() if "Download Quality" in self.setting_combos else "",
            "ai_model": self.setting_combos.get("AI Model").currentText() if "AI Model" in self.setting_combos else "",
            "outputs_per_prompt": self.setting_combos.get("Outputs per Prompt").currentText() if "Outputs per Prompt" in self.setting_combos else "",
            "image_ai_model": self.setting_combos.get("Image AI Model").currentText() if "Image AI Model" in self.setting_combos else "",
            "image_quality": self.setting_combos.get("Image Quality").currentText() if "Image Quality" in self.setting_combos else "",
            "output_folder": self.output_folder_entry.text(),
            "include_timestamp": self.output_toggles.get("Include timestamp in filename").isChecked() if "Include timestamp in filename" in self.output_toggles else False,
            "include_quality": self.output_toggles.get("Include quality in filename").isChecked() if "Include quality in filename" in self.output_toggles else False,
            "auto_start_queue": self.output_toggles.get("Auto-start queue when adding").isChecked() if "Auto-start queue when adding" in self.output_toggles else False,
            "pause_on_error": self.output_toggles.get("Pause on error").isChecked() if "Pause on error" in self.output_toggles else False,
            "continuation_enabled": self.cont_switch.isToggled(),
            "extract_point_ms": self._parse_extract_point(self.extract_menu.currentText()),
            # Enhancer Image (3-toggle system)
            "enhance_context_menu": self._enhance_context_toggle.isToggled() if hasattr(self, '_enhance_context_toggle') else True,
            "enhance_library": self._enhance_library_toggle.isToggled() if hasattr(self, '_enhance_library_toggle') else True,
            "enhance_auto_continuation": self._enhance_auto_toggle.isToggled() if hasattr(self, '_enhance_auto_toggle') else False,
            "language": self.lang_menu.currentText(),
            # Worker Settings
            "retry_count": self.retry_count.value(),
            "request_timeout": self.request_timeout.value(),
            # Anti-Detect Spam
            "anti_detect_enabled": self.anti_detect_switch.isToggled(),
            "anti_detect_delay_min": self.anti_detect_delay_min.value(),
            "anti_detect_delay_max": self.anti_detect_delay_max.value(),
            # Session & Data
            "restore_queue_on_startup": self.restore_queue_switch.isToggled(),
            "restore_tabs_on_startup": self.restore_tabs_switch.isToggled(),
            # Notifications
            "notify_toast_enabled": self.notify_toast_toggle.isToggled() if hasattr(self, 'notify_toast_toggle') else True,
            "notify_sound_enabled": self.notify_sound_toggle.isToggled() if hasattr(self, 'notify_sound_toggle') else True,
            "notify_sound_file": self._get_selected_sound() if hasattr(self, '_get_selected_sound') else "default",
            # Post-Queue Action
            "post_queue_action_enabled": self.post_queue_switch.isToggled() if hasattr(self, 'post_queue_switch') else False,
            "post_queue_action": self.post_queue_action_combo.currentText() if hasattr(self, 'post_queue_action_combo') else "nothing",
            # Browser Visibility
            "smart_hide_enabled": self.smart_hide_switch.isToggled() if hasattr(self, 'smart_hide_switch') else True,
            # Pipeline Optimization
            "adaptive_burst_enabled": self.burst_switch.isToggled() if hasattr(self, 'burst_switch') else True,
            "burst_min_delay": self.burst_min.value() if hasattr(self, 'burst_min') else 2.0,
            "burst_max_delay": self.burst_max.value() if hasattr(self, 'burst_max') else 15.0,
            "recaptcha_pool_enabled": self.pool_switch.isToggled() if hasattr(self, 'pool_switch') else True,
            "recaptcha_pool_size": self.pool_size.value() if hasattr(self, 'pool_size') else 2,
            "watchdog_timeout_min": self.watchdog_timeout.value() if hasattr(self, 'watchdog_timeout') else 10,
            "journal_save_interval_sec": self.journal_interval.value() if hasattr(self, 'journal_interval') else 30,
            "workload_priority": self._wp_map.get(self.workload_priority.currentIndex(), '720p_priority') if hasattr(self, '_wp_map') and hasattr(self, 'workload_priority') else '720p_priority',
        }
        # Granular restore sub-toggles
        if hasattr(self, '_restore_sub_toggles'):
            for attr_name, toggle in self._restore_sub_toggles.items():
                result[attr_name] = toggle.isToggled()
        return result
