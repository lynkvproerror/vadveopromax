"""
Settings Sections mixin — default, output, continuation, worker, session,
notification, and UI section builders with their save handlers.

Extracted from tab_settings.py.  All methods operate on shared `self`
attributes initialised by TabSettings.__init__.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QLineEdit, QCheckBox,
    QSpinBox, QDoubleSpinBox, QFileDialog,
)
from ui.popups import show_info, show_warning, show_confirm
from PySide6.QtCore import Qt, QTimer

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme
from config.i18n import t


class SettingsSectionsMixin:
    """Default, output, continuation, worker, session, notification, UI sections."""

    def _create_defaults_section(self) -> QWidget:
        """Create Default Settings section — split into Video + Image sub-sections."""
        section, layout = self._create_section(t("settings.sections.defaults"))

        # Load saved values from AppSettings
        try:
            from config.settings import get_settings as _gs
            _s = _gs()
        except Exception:
            _s = None

        self.setting_combos = {}

        # --- Shared: Aspect Ratio ---
        ar_options = ["16:9 (Landscape)", "9:16 (Portrait)"]
        combo = self._create_setting_row(layout, t("settings.defaults_sub.aspect_ratio"), ar_options)
        if _s:
            _ar = getattr(_s, 'default_aspect_ratio', 'LANDSCAPE')
            combo.setCurrentText("9:16 (Portrait)" if "PORTRAIT" in _ar.upper() else "16:9 (Landscape)")
        self.setting_combos["Aspect Ratio"] = combo

        # --- Shared: Outputs per Prompt ---
        out_options = ["1", "2", "3", "4"]
        combo = self._create_setting_row(layout, t("settings.defaults_sub.outputs_per_prompt"), out_options)
        if _s:
            _cnt = str(getattr(_s, 'default_output_count', 4))
            if _cnt in out_options:
                combo.setCurrentText(_cnt)
        self.setting_combos["Outputs per Prompt"] = combo

        # ─── 🎬 Video Defaults ───
        vid_label = QLabel(t("settings.defaults_sub.video"))
        vid_label.setStyleSheet(f"color: {Theme.BLUE}; font-weight: bold; padding-top: 8px;")
        layout.addWidget(vid_label)

        # Video: AI Model
        model_options = [
            "Veo 3.1 - Fast",
            "Veo 3.1 - Fast [LP]",
            "Veo 3.1 - Quality",
            "Veo 2 - Fast",
            "Veo 2 - Quality",
        ]
        combo = self._create_setting_row(layout, t("settings.defaults_sub.ai_model"), model_options)
        if _s:
            _m = getattr(_s, 'default_model', 'Veo 3.1 - Fast')
            idx = combo.findText(_m)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.setting_combos["AI Model"] = combo

        # Video: Download Quality
        vq_options = ["720p", "1080p", "4K"]
        combo = self._create_setting_row(layout, t("settings.defaults_sub.download_quality"), vq_options)
        if _s:
            _vq = getattr(_s, 'default_download_quality', '1080p')
            if _vq in vq_options:
                combo.setCurrentText(_vq)
        self.setting_combos["Download Quality"] = combo

        # ─── 🖼️ Image Defaults ───
        img_label = QLabel(t("settings.defaults_sub.image"))
        img_label.setStyleSheet(f"color: {Theme.PURPLE}; font-weight: bold; padding-top: 8px;")
        layout.addWidget(img_label)

        # Image: AI Model
        img_model_options = [
            "🔥 Nano Banana Pro",
            "🔥 Nano Banana",
            "Imagen 4",
        ]
        combo = self._create_setting_row(layout, t("settings.defaults_sub.image_model"), img_model_options)
        if _s:
            _im = getattr(_s, 'default_image_model', '🔥 Nano Banana Pro')
            idx = combo.findText(_im)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.setting_combos["Image AI Model"] = combo

        # Image: Download Quality
        iq_options = ["1k", "2k", "4k"]
        combo = self._create_setting_row(layout, t("settings.defaults_sub.image_quality"), iq_options)
        if _s:
            _iq = getattr(_s, 'default_image_quality', '1k')
            if _iq in iq_options:
                combo.setCurrentText(_iq)
        self.setting_combos["Image Quality"] = combo

        # Wire save-on-change for all combos
        for key, cb in self.setting_combos.items():
            cb.currentTextChanged.connect(self._save_default_settings)

        return section

    def _save_default_settings(self, *args):
        """Persist default settings to AppSettings."""
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings as _gs
            import logging
            settings = _gs()
            # Aspect Ratio
            ar_text = self.setting_combos["Aspect Ratio"].currentText()
            settings.default_aspect_ratio = "PORTRAIT" if "Portrait" in ar_text else "LANDSCAPE"
            # Outputs per Prompt
            settings.default_output_count = int(self.setting_combos["Outputs per Prompt"].currentText())
            # Video: AI Model
            settings.default_model = self.setting_combos["AI Model"].currentText()
            # Video: Download Quality
            settings.default_download_quality = self.setting_combos["Download Quality"].currentText()
            # Image: AI Model
            if "Image AI Model" in self.setting_combos:
                settings.default_image_model = self.setting_combos["Image AI Model"].currentText()
            # Image: Quality
            settings.default_image_quality = self.setting_combos["Image Quality"].currentText()
            settings.save()
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save default settings: {e}')

    def _create_output_section(self) -> QWidget:
        """Create Output Settings section — folder + filename toggles."""
        section, layout = self._create_section(t("settings.sections.output"))

        # Load saved values
        try:
            from config.settings import get_settings as _gs
            _s = _gs()
        except Exception:
            _s = None

        # Default output folder
        folder_layout = QHBoxLayout()

        folder_label = QLabel("Thư mục lưu:")
        folder_label.setFixedWidth(120)
        folder_label.setStyleSheet(f"color: {Theme.TEXT};")
        folder_layout.addWidget(folder_label)

        self.output_folder_entry = QLineEdit()
        self.output_folder_entry.setPlaceholderText("D:/Projects/VEO")
        self.output_folder_entry.setMinimumWidth(200)
        if _s and getattr(_s, 'output_folder', ''):
            self.output_folder_entry.setText(_s.output_folder)
        folder_layout.addWidget(self.output_folder_entry)

        browse_btn = QPushButton("📁 Chọn")
        browse_btn.setFixedSize(90, 35)
        browse_btn.setToolTip("Chọn thư mục lưu video")
        browse_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; font-weight: bold; font-size: 12px; border-radius: 4px;")
        browse_btn.clicked.connect(self._browse_output_folder)
        folder_layout.addWidget(browse_btn)

        layout.addLayout(folder_layout)

        # Toggles with saved state
        _ts = getattr(_s, 'include_timestamp', True) if _s else True
        _qs = getattr(_s, 'include_quality', True) if _s else True
        _as = getattr(_s, 'auto_start_queue', False) if _s else False
        _ps = getattr(_s, 'pause_on_error', True) if _s else True

        toggles = [
            (t("settings.output_toggles.include_timestamp"), _ts),
            (t("settings.output_toggles.include_quality"), _qs),
            (t("settings.output_toggles.auto_start_queue"), _as),
            (t("settings.output_toggles.pause_on_error"), _ps),
        ]

        # Filename & behavior options — grouped under sub-label
        opts_label = QLabel(t("settings.output_toggles.filename_options"))
        opts_label.setStyleSheet(f"color: {Theme.BLUE}; font-weight: bold; padding-top: 6px;")
        layout.addWidget(opts_label)

        self.output_toggles = {}
        for label, default in toggles:
            checkbox = QCheckBox(label)
            checkbox.setChecked(default)
            checkbox.setStyleSheet(f"color: {Theme.TEXT}; margin-left: 12px;")
            checkbox.setToolTip("Auto-saved — changes take effect immediately")
            checkbox.toggled.connect(self._save_output_settings)
            layout.addWidget(checkbox)
            self.output_toggles[label] = checkbox

        # Wire folder save
        self.output_folder_entry.textChanged.connect(self._save_output_settings)

        return section

    def _browse_output_folder(self):
        """Open folder picker for default output folder."""
        folder = QFileDialog.getExistingDirectory(self, "Select Default Output Folder")
        if folder:
            self.output_folder_entry.setText(folder)

    def _save_output_settings(self, *args):
        """Persist output settings to AppSettings."""
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings as _gs
            import logging
            settings = _gs()
            settings.output_folder = self.output_folder_entry.text()
            settings.include_timestamp = self.output_toggles.get("Include timestamp in filename").isChecked() if "Include timestamp in filename" in self.output_toggles else True
            settings.include_quality = self.output_toggles.get("Include quality in filename").isChecked() if "Include quality in filename" in self.output_toggles else True
            settings.auto_start_queue = self.output_toggles.get("Auto-start queue when adding").isChecked() if "Auto-start queue when adding" in self.output_toggles else False
            settings.pause_on_error = self.output_toggles.get("Pause on error").isChecked() if "Pause on error" in self.output_toggles else True
            settings.save()
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save output settings: {e}')

    # _create_browser_section — REMOVED (headless/persistent profile managed elsewhere)

    def _create_continuation_section(self) -> QWidget:
        """Create Smooth Continuation section — toggle only, no sub-options."""
        section, layout = self._create_section(t("settings.sections.continuation"))

        # Load saved values from AppSettings
        from config.settings import get_settings as _gs
        _s = _gs()
        saved_enabled = getattr(_s, 'continuation_enabled', True)
        saved_ms = getattr(_s, 'extract_point_ms', 750)

        # Check if Trial user — force OFF
        is_trial = False
        try:
            if hasattr(self, 'controller') and self.controller and hasattr(self.controller, '_permissions'):
                from services.permissions import Role
                role = self.controller._permissions.role
                is_trial = (role == Role.TRIAL)
        except Exception:
            pass

        initial_checked = False if is_trial else saved_enabled

        # Enable toggle — loaded from saved (forced OFF for Trial)
        self.cont_switch = self._create_enable_row("Smooth Continuation:", checked=initial_checked)
        layout.addLayout(self.cont_switch._row_layout)

        # Description
        desc = QLabel(
            "ON = Cắt cảnh mượt hơn.\n"
            "OFF = Mặc định."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; margin-left: 16px;")
        layout.addWidget(desc)

        # Trial badge
        if is_trial:
            trial_badge = QLabel("🔒 Premium Only — Nâng cấp để sử dụng")
            trial_badge.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px; margin-left: 16px;")
            layout.addWidget(trial_badge)

        # Hidden extract_menu — still needed for save/get_settings but not shown
        self.extract_menu = QComboBox()
        self.extract_menu.addItems(["500ms", "750ms (recommended)", "1000ms", "Custom"])
        _ms_map = {500: "500ms", 750: "750ms (recommended)", 1000: "1000ms"}
        self.extract_menu.setCurrentText(_ms_map.get(saved_ms, "750ms (recommended)"))
        self.extract_menu.setVisible(False)

        # Auto-save on change (with Trial guard)
        self._is_trial_continuation = is_trial
        self.cont_switch.toggled_signal.connect(self._on_continuation_toggled)

        return section

    def _on_continuation_toggled(self, checked: bool):
        """Handle continuation toggle — block for Trial users."""
        if getattr(self, '_is_trial_continuation', False) and checked:
            # Revert toggle to OFF
            self.cont_switch.blockSignals(True)
            self.cont_switch.setToggled(False)
            self.cont_switch.blockSignals(False)
            from ui.popups import show_warning
            show_warning(
                self, "🔒 Trial Limit",
                "Smooth Continuation chỉ dành cho gói Premium.\n\n"
                "Nâng cấp để sử dụng tính năng cắt cảnh mượt."
            )
            return
        self._save_continuation_settings(checked)

    def _save_continuation_settings(self, *args):
        """Persist continuation settings to AppSettings."""
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings, save_settings
            import logging
            settings = get_settings()
            settings.continuation_enabled = self.cont_switch.isToggled()
            settings.extract_point_ms = self._parse_extract_point(self.extract_menu.currentText())
            save_settings()
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save continuation settings: {e}')

    def _create_worker_section(self) -> QWidget:
        """Create Worker Settings section per TAB_07_SETTINGS.md spec."""
        section, layout = self._create_section(t("settings.sections.worker"))

        # Load saved values from AppSettings (not controller — may be None)
        from config.settings import get_settings as _gs
        _s = _gs()
        saved = {
            'retry_count': getattr(_s, 'retry_count', 3),
            'request_timeout': getattr(_s, 'request_timeout', 120),
            'anti_detect_enabled': getattr(_s, 'anti_detect_enabled', True),
            'anti_detect_delay_min': getattr(_s, 'anti_detect_delay_min', 3.0),
            'anti_detect_delay_max': getattr(_s, 'anti_detect_delay_max', 8.0),
        }

        # Note: Max Concurrent Workers removed — now per-account via Chrome Profiles

        # Retry on Error (default for new accounts)
        retry_row = QHBoxLayout()
        retry_label = QLabel(t("settings.retry_on_error"))
        retry_label.setFixedWidth(150)
        retry_label.setStyleSheet(f"color: {Theme.TEXT};")
        retry_row.addWidget(retry_label)

        self.retry_count = QSpinBox()
        self.retry_count.setRange(0, 5)
        self.retry_count.setValue(saved.get('retry_count', 3))
        self.retry_count.setFixedWidth(100)
        retry_row.addWidget(self.retry_count)
        retry_row.addStretch()
        layout.addLayout(retry_row)

        # Request Timeout
        timeout_row = QHBoxLayout()
        timeout_label = QLabel(t("settings.request_timeout"))
        timeout_label.setFixedWidth(150)
        timeout_label.setStyleSheet(f"color: {Theme.TEXT};")
        timeout_row.addWidget(timeout_label)

        self.request_timeout = QSpinBox()
        self.request_timeout.setRange(30, 300)
        self.request_timeout.setValue(saved.get('request_timeout', 120))
        self.request_timeout.setFixedWidth(100)
        self.request_timeout.setSuffix("s")
        timeout_row.addWidget(self.request_timeout)
        timeout_row.addStretch()
        layout.addLayout(timeout_row)

        # === Anti-Detect Spam — bold + emoji ===
        self.anti_detect_switch = self._create_enable_row(
            "🛡️ Anti-Detect Spam:", checked=saved.get('anti_detect_enabled', True),
            bold=True, color=Theme.YELLOW
        )
        layout.addLayout(self.anti_detect_switch._row_layout)

        # Hidden delay spinboxes — still needed for save/get_settings but not shown
        self.anti_detect_delay_min = QDoubleSpinBox()
        self.anti_detect_delay_min.setRange(0.5, 10.0)
        self.anti_detect_delay_min.setValue(saved.get('anti_detect_delay_min', 3.0))
        self.anti_detect_delay_min.setVisible(False)

        self.anti_detect_delay_max = QDoubleSpinBox()
        self.anti_detect_delay_max.setRange(1.0, 30.0)
        self.anti_detect_delay_max.setValue(saved.get('anti_detect_delay_max', 8.0))
        self.anti_detect_delay_max.setVisible(False)

        # Auto-save on change (C1 fix)
        self.retry_count.valueChanged.connect(self._save_worker_settings)
        self.request_timeout.valueChanged.connect(self._save_worker_settings)
        self.anti_detect_switch.toggled_signal.connect(self._on_anti_detect_toggled)
        self.anti_detect_delay_min.valueChanged.connect(self._save_worker_settings)
        self.anti_detect_delay_max.valueChanged.connect(self._save_worker_settings)
        # Cross-validation: min ≤ max (M2 fix)
        self.anti_detect_delay_min.valueChanged.connect(self._clamp_anti_detect_delays)
        self.anti_detect_delay_max.valueChanged.connect(self._clamp_anti_detect_delays)

        # Trial guard: force OFF
        try:
            from services.permissions import PermissionsSystem, Role
            perm = PermissionsSystem.instance()
            if perm.role == Role.TRIAL:
                self.anti_detect_switch.setToggled(False)
        except Exception:
            pass

        return section

    def _on_anti_detect_toggled(self, checked: bool):
        """Handle Anti-Detect toggle — Trial users get popup + revert."""
        if checked:
            try:
                from services.permissions import PermissionsSystem, Role
                perm = PermissionsSystem.instance()
                if perm.role == Role.TRIAL:
                    from ui.popups import show_warning
                    show_warning(
                        self,
                        "🛡️ Tính năng Premium",
                        "Anti-Detect Spam chỉ khả dụng cho gói Premium trở lên.\n\n"
                        "Nâng cấp để bảo vệ tài khoản khỏi bị phát hiện spam!"
                    )
                    self.anti_detect_switch.setToggled(False)
                    return
            except Exception:
                pass
        self._save_worker_settings()

    def _clamp_anti_detect_delays(self, *args):
        """Ensure min_delay ≤ max_delay by auto-clamping."""
        if getattr(self, '_initializing', False):
            return
        mn = self.anti_detect_delay_min.value()
        mx = self.anti_detect_delay_max.value()
        if mn > mx:
            self.anti_detect_delay_max.blockSignals(True)
            self.anti_detect_delay_max.setValue(mn)
            self.anti_detect_delay_max.blockSignals(False)

    def _save_worker_settings(self, *args):
        """Persist worker + anti-detect settings to AppSettings."""
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings, save_settings
            import logging
            settings = get_settings()
            settings.retry_count = self.retry_count.value()
            settings.request_timeout = self.request_timeout.value()
            settings.anti_detect_enabled = self.anti_detect_switch.isToggled()
            settings.anti_detect_delay_min = self.anti_detect_delay_min.value()
            settings.anti_detect_delay_max = self.anti_detect_delay_max.value()
            save_settings()
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save worker settings: {e}')

    def _create_session_section(self) -> QWidget:
        """Create Session & Data Management section."""
        section, layout = self._create_section(t("settings.sections.session"))

        # Load saved values from AppSettings (not controller — may be None)
        from config.settings import get_settings as _gs
        s = _gs()
        saved_restore_queue = getattr(s, 'restore_queue_on_startup', False)
        saved_restore_tabs = getattr(s, 'restore_tabs_on_startup', True)

        # Toggle: Restore Queue
        self.restore_queue_switch = self._create_enable_row(
            "Restore Queue:", checked=saved_restore_queue
        )
        layout.addLayout(self.restore_queue_switch._row_layout)

        # Description for restore queue
        queue_desc = QLabel("⚠️ When ON, tasks from previous session are reloaded. Turn OFF to prevent stale/broken tasks.")
        queue_desc.setWordWrap(True)
        queue_desc.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; margin-left: 16px; margin-bottom: 4px;")
        layout.addWidget(queue_desc)

        # Toggle: Restore Tabs
        self.restore_tabs_switch = self._create_enable_row(
            "Restore Tabs:", checked=saved_restore_tabs
        )
        layout.addLayout(self.restore_tabs_switch._row_layout)

        # Auto-save: persist session toggles immediately on change
        self.restore_queue_switch.toggled_signal.connect(self._save_session_settings)
        self.restore_tabs_switch.toggled_signal.connect(self._save_session_settings)

        # === Granular Restore Sub-toggles (grouped columns) ===
        self._restore_sub_container = QFrame()
        self._restore_sub_container.setStyleSheet(f"margin-left: 16px; padding: 4px 0;")
        sub_outer = QVBoxLayout(self._restore_sub_container)
        sub_outer.setContentsMargins(0, 4, 0, 4)
        sub_outer.setSpacing(4)

        sub_label = QLabel("Choose what to restore:")
        sub_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-style: italic;")
        sub_outer.addWidget(sub_label)

        # Load saved granular values
        _g = lambda attr, default=True: getattr(s, attr, default)

        # Define groups with their options
        restore_groups = [
            ("📁 Project", [
                ("Project Name",    "restore_project_name",       _g('restore_project_name')),
                ("Output Folder",   "restore_output_folder",      _g('restore_output_folder')),
            ]),
            ("⚙️ Generation", [
                ("Aspect Ratio",      "restore_aspect_ratio",       _g('restore_aspect_ratio')),
                ("Outputs/Prompt",    "restore_outputs_per_prompt", _g('restore_outputs_per_prompt')),
                ("AI Model",          "restore_ai_model",           _g('restore_ai_model')),
                ("Download Quality",  "restore_download_quality",   _g('restore_download_quality')),
                ("Frame Mode (I2V)",  "restore_frame_mode",         _g('restore_frame_mode')),
            ]),
            ("✍️ Content", [
                ("Prompt Input",    "restore_prompt_input",       _g('restore_prompt_input')),
                ("Parsed Prompts",  "restore_parsed_prompts",     _g('restore_parsed_prompts')),
                ("Prompt Images",   "restore_prompt_images",      _g('restore_prompt_images')),
            ]),
        ]

        # Create columns layout
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(12)
        columns_layout.setContentsMargins(0, 0, 0, 0)

        self._restore_sub_toggles = {}  # attr_name -> toggle widget

        for group_title, options in restore_groups:
            group_frame = QFrame()
            group_frame.setObjectName("restoreGroup")
            group_frame.setStyleSheet(f"""
                QFrame#restoreGroup {{
                    background-color: {Theme.SURFACE1};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 6px;
                    padding: 4px;
                }}
                QFrame#restoreGroup > * {{
                    border: none;
                }}
            """)
            group_layout = QVBoxLayout(group_frame)
            group_layout.setContentsMargins(8, 6, 8, 6)
            group_layout.setSpacing(2)

            # Group header
            header = QLabel(group_title)
            header.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px; font-weight: bold; border: none; padding: 0; margin-bottom: 2px;")
            group_layout.addWidget(header)

            for label_text, attr_name, checked in options:
                toggle = self._create_enable_row(label_text, checked=checked)
                group_layout.addLayout(toggle._row_layout)
                toggle.toggled_signal.connect(self._save_session_settings)
                self._restore_sub_toggles[attr_name] = toggle

            group_layout.addStretch()
            columns_layout.addWidget(group_frame)

        sub_outer.addLayout(columns_layout)

        layout.addWidget(self._restore_sub_container)

        # Show/hide sub-toggles based on Restore Tabs state
        self._restore_sub_container.setVisible(saved_restore_tabs)
        self.restore_tabs_switch.toggled_signal.connect(
            lambda checked: self._restore_sub_container.setVisible(checked)
        )

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {Theme.BORDER}; max-height: 1px; margin: 8px 0;")
        layout.addWidget(sep)

        # Cache stats label
        cache_stats = self._get_cache_stats_text()
        self.cache_stats_label = QLabel(cache_stats)
        self.cache_stats_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        layout.addWidget(self.cache_stats_label)

        # Action buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        # Clear Cache button (YELLOW)
        clear_cache_btn = QPushButton("🧹 Clear Cache")
        clear_cache_btn.setFixedHeight(32)
        clear_cache_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.YELLOW};
                color: {Theme.CRUST};
                border-radius: 6px;
                padding: 0 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #FCE8C0;
            }}
        """)
        clear_cache_btn.setToolTip("Delete cached files (downloaded videos, temp data)")
        clear_cache_btn.clicked.connect(self._on_clear_cache)
        btn_layout.addWidget(clear_cache_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return section

    def _get_cache_stats_text(self) -> str:
        """Get cache statistics as display text."""
        try:
            if self.controller and hasattr(self.controller, 'get_cache_stats'):
                stats = self.controller.get_cache_stats()
                size_mb = stats.get("size_mb", 0)
                file_count = stats.get("file_count", 0)
                return f"📊 Cache: {size_mb:.1f} MB ({file_count} files)"
        except Exception:
            pass
        return "📊 Cache: N/A"

    def _on_clear_cache(self):
        """Clear cache files with confirmation."""
        if show_confirm(self, "Clear Cache",
                "🧹 This will delete ALL cached files.\n\n"
                "Are you sure?", danger=True):
            if self.controller and hasattr(self.controller, 'clear_cache'):
                result = self.controller.clear_cache()
                deleted = result.get("deleted_count", 0)
                freed = result.get("freed_mb", 0)
                show_info(
                    self, "Cache Cleared",
                    f"✅ {deleted} files removed ({freed:.1f} MB freed)."
                )
                # Refresh cache stats
                self.cache_stats_label.setText(self._get_cache_stats_text())

    def _create_notification_section(self) -> QWidget:
        """Create Notifications section — toast + sound settings."""
        section, layout = self._create_section(t("settings.sections.notification"))

        from config.settings import get_settings
        settings = get_settings()

        # Row 1: In-App Toast toggle
        toast_row = QHBoxLayout()

        toast_label = QLabel(t("settings.notification_sub.in_app_toast"))
        toast_label.setFixedWidth(150)
        toast_label.setStyleSheet(f"color: {Theme.TEXT};")
        toast_row.addWidget(toast_label)

        from ui.tabs.tab_settings import ToggleSwitch
        self.notify_toast_toggle = ToggleSwitch(checked=settings.notify_toast_enabled)
        toast_row.addWidget(self.notify_toast_toggle)
        toast_row.addStretch()
        layout.addLayout(toast_row)

        # Row 2: Sound Notification toggle + sound selector + preview
        sound_row = QHBoxLayout()

        sound_label = QLabel(t("settings.notification_sub.sound_notification"))
        sound_label.setFixedWidth(150)
        sound_label.setStyleSheet(f"color: {Theme.TEXT};")
        sound_row.addWidget(sound_label)

        self.notify_sound_toggle = ToggleSwitch(checked=settings.notify_sound_enabled)
        sound_row.addWidget(self.notify_sound_toggle)

        # Separator
        sep = QFrame()
        sep.setFixedSize(1, 24)
        sep.setStyleSheet(f"background-color: {Theme.BORDER};")
        sound_row.addWidget(sep)

        # Sound selector dropdown
        sound_select_label = QLabel(t("settings.notification_sub.sound"))
        sound_select_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        sound_row.addWidget(sound_select_label)

        self.sound_file_combo = QComboBox()
        from core.notification_manager import BUILTIN_SOUNDS
        self._builtin_sound_names = list(BUILTIN_SOUNDS.keys())
        self.sound_file_combo.addItems(self._builtin_sound_names + ["Custom..."])
        self.sound_file_combo.setFixedWidth(140)
        self.sound_file_combo.setFixedHeight(30)

        # Set current selection from settings
        current_sound = settings.notify_sound_file
        if current_sound in self._builtin_sound_names:
            self.sound_file_combo.setCurrentText(current_sound)
        elif current_sound:
            # Custom file — show filename
            from pathlib import Path
            custom_name = Path(current_sound).name
            idx = self.sound_file_combo.count() - 1  # Before "Custom..."
            self.sound_file_combo.insertItem(idx, f"📁 {custom_name}")
            self.sound_file_combo.setCurrentIndex(idx)
            self.sound_file_combo.setItemData(idx, current_sound, Qt.UserRole)

        self.sound_file_combo.currentIndexChanged.connect(self._on_sound_selection_changed)
        sound_row.addWidget(self.sound_file_combo)

        # Preview button
        preview_btn = QPushButton(t("settings.notification_sub.preview"))
        preview_btn.setFixedSize(120, 30)
        preview_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE2};
            }}
        """)
        preview_btn.clicked.connect(self._on_preview_sound)
        sound_row.addWidget(preview_btn)

        sound_row.addStretch()
        layout.addLayout(sound_row)

        # Auto-save: connect toggles + dropdown to persist immediately
        self.notify_toast_toggle.toggled_signal.connect(self._save_notification_settings)
        self.notify_sound_toggle.toggled_signal.connect(self._save_notification_settings)
        self.sound_file_combo.currentIndexChanged.connect(
            lambda: self._save_notification_settings()
        )

        return section

    def _save_notification_settings(self, *args):
        """Persist notification settings to AppSettings singleton."""
        if getattr(self, '_initializing', False):
            return
        from config.settings import get_settings, save_settings
        settings = get_settings()
        settings.notify_toast_enabled = self.notify_toast_toggle.isToggled()
        settings.notify_sound_enabled = self.notify_sound_toggle.isToggled()
        settings.notify_sound_file = self._get_selected_sound()
        save_settings()

    def _save_session_settings(self, *args):
        """Persist session toggles (Restore Queue/Tabs + granular options) to AppSettings immediately."""
        if getattr(self, '_initializing', False):
            return
        from config.settings import get_settings, save_settings
        settings = get_settings()
        settings.restore_queue_on_startup = self.restore_queue_switch.isToggled()
        settings.restore_tabs_on_startup = self.restore_tabs_switch.isToggled()
        # Save granular sub-toggles
        for attr_name, toggle in self._restore_sub_toggles.items():
            setattr(settings, attr_name, toggle.isToggled())
        save_settings()

    def _on_sound_selection_changed(self, index: int):
        """Handle sound dropdown selection change."""
        text = self.sound_file_combo.currentText()
        if text == "Custom...":
            from PySide6.QtWidgets import QFileDialog
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Select Sound File", "",
                "Sound Files (*.wav *.mp3);;All Files (*)"
            )
            if filepath:
                from pathlib import Path
                custom_name = Path(filepath).name
                # Insert custom file before "Custom..." item
                insert_idx = self.sound_file_combo.count() - 1
                self.sound_file_combo.blockSignals(True)
                self.sound_file_combo.insertItem(insert_idx, f"📁 {custom_name}")
                self.sound_file_combo.setItemData(insert_idx, filepath, Qt.UserRole)
                self.sound_file_combo.setCurrentIndex(insert_idx)
                self.sound_file_combo.blockSignals(False)
                # M1 fix: explicitly save after blockSignals
                self._save_notification_settings()
            else:
                # User cancelled — revert to "default"
                self.sound_file_combo.blockSignals(True)
                self.sound_file_combo.setCurrentIndex(0)
                self.sound_file_combo.blockSignals(False)

    def _on_preview_sound(self):
        """Preview the currently selected notification sound."""
        sound = self._get_selected_sound()
        try:
            from core.notification_manager import NotificationManager
            if not hasattr(self, '_preview_player'):
                self._preview_player = NotificationManager()
            self._preview_player.play(sound, duration_ms=4000)
        except Exception as e:
            from ui.popups import show_warning as _sw
            _sw(self, "Sound Error", f"Cannot play sound: {e}")

    def _get_selected_sound(self) -> str:
        """Get the sound file name/path from the current dropdown selection."""
        text = self.sound_file_combo.currentText()
        if text in self._builtin_sound_names:
            return text
        # Custom file — get path from UserRole data
        custom_path = self.sound_file_combo.itemData(
            self.sound_file_combo.currentIndex(), Qt.UserRole
        )
        return custom_path if custom_path else "default"

    def _create_ui_section(self) -> QWidget:
        """Create UI section — Language selector."""
        section, layout = self._create_section(t("settings.sections.ui"))

        # Load saved language
        from config.settings import get_settings as _gs
        _s = _gs()
        saved_lang = getattr(_s, 'ui_language', 'English')

        row_layout = QHBoxLayout()

        # Language
        lang_label = QLabel(t("settings.language"))
        lang_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        row_layout.addWidget(lang_label)

        self.lang_menu = QComboBox()
        self.lang_menu.addItems(["English", "Tiếng Việt"])
        self.lang_menu.setCurrentText(saved_lang)
        self.lang_menu.setFixedWidth(140)
        self.lang_menu.currentTextChanged.connect(self._save_ui_settings)
        row_layout.addWidget(self.lang_menu)

        row_layout.addStretch()
        layout.addLayout(row_layout)

        return section

    def _save_ui_settings(self, *args):
        """Persist UI settings (language) to AppSettings + hot-reload."""
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings, save_settings
            from config.i18n import set_language
            import logging
            settings = get_settings()
            lang_display = self.lang_menu.currentText()
            settings.ui_language = lang_display
            save_settings()
            # Hot-reload: switch language immediately (emits language_changed signal)
            set_language(lang_display)
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save UI settings: {e}')

    # ── Auto-Update Section ────────────────────────────────────────

    def _create_update_section(self) -> QWidget:
        """Create Auto-Update section — version check + download + apply."""
        section, layout = self._create_section(t("settings.sections.update"))

        from config.settings import get_settings
        from config.constants import AppConstants
        settings = get_settings()

        # Row 1: Auto-update toggle
        toggle_row = QHBoxLayout()
        toggle_label = QLabel(t("settings.update_sub.auto_check"))
        toggle_label.setFixedWidth(200)
        toggle_label.setStyleSheet(f"color: {Theme.TEXT};")
        toggle_row.addWidget(toggle_label)

        from ui.tabs.tab_settings import ToggleSwitch
        self.auto_update_toggle = ToggleSwitch(
            checked=getattr(settings, 'auto_update_enabled', True)
        )
        toggle_row.addWidget(self.auto_update_toggle)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # Row 2: Current version + status
        version_row = QHBoxLayout()

        version_label = QLabel(
            f"{t('settings.update_sub.current_version')}: v{AppConstants.APP_VERSION}"
        )
        version_label.setStyleSheet(
            f"color: {Theme.TEXT}; font-weight: bold; font-size: 13px;"
        )
        version_row.addWidget(version_label)

        self._update_status_label = QLabel(t("settings.update_sub.up_to_date"))
        self._update_status_label.setStyleSheet(
            f"color: {Theme.GREEN}; font-size: 12px; margin-left: 12px;"
        )
        version_row.addWidget(self._update_status_label)
        version_row.addStretch()
        layout.addLayout(version_row)

        # Row 3: Check Now + Update Now buttons
        btn_row = QHBoxLayout()

        self._check_update_btn = QPushButton(t("settings.update_sub.check_now"))
        self._check_update_btn.setFixedSize(160, 34)
        self._check_update_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE2};
            }}
        """)
        self._check_update_btn.clicked.connect(self._on_check_update)
        btn_row.addWidget(self._check_update_btn)

        self._update_now_btn = QPushButton(t("settings.update_sub.update_now"))
        self._update_now_btn.setFixedSize(260, 34)
        self._update_now_btn.setVisible(False)  # Hidden until update found
        self._update_now_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BLUE};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 4px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.LAVENDER};
            }}
        """)
        self._update_now_btn.clicked.connect(self._on_update_now)
        btn_row.addWidget(self._update_now_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Changelog area (hidden until update found)
        self._changelog_label = QLabel("")
        self._changelog_label.setWordWrap(True)
        self._changelog_label.setVisible(False)
        self._changelog_label.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px; "
            f"margin: 4px 0 0 4px; padding: 6px; "
            f"background: {Theme.SURFACE0}; border-radius: 4px;"
        )
        layout.addWidget(self._changelog_label)

        # Auto-save toggle
        self.auto_update_toggle.toggled_signal.connect(self._save_update_settings)

        # Store updater reference (initialized lazily)
        self._updater = None

        return section

    def _get_updater(self):
        """Get or create AutoUpdater instance."""
        if self._updater is None:
            from core.auto_updater import AutoUpdater
            self._updater = AutoUpdater(self)
            self._updater.update_available.connect(self._on_update_available)
            self._updater.download_progress.connect(self._on_download_progress)
            self._updater.download_complete.connect(self._on_download_complete)
            self._updater.download_error.connect(self._on_download_error)
            self._updater.update_applied.connect(self._on_update_applied)
        return self._updater

    def _save_update_settings(self, *args):
        """Persist auto-update toggle."""
        if getattr(self, '_initializing', False):
            return
        from config.settings import get_settings, save_settings
        settings = get_settings()
        settings.auto_update_enabled = self.auto_update_toggle.isToggled()
        save_settings()

    def _on_check_update(self):
        """Manual check for updates."""
        self._check_update_btn.setEnabled(False)
        self._check_update_btn.setText(t("settings.update_sub.checking"))
        self._update_status_label.setText("⏳ " + t("settings.update_sub.checking"))
        self._update_status_label.setStyleSheet(
            f"color: {Theme.YELLOW}; font-size: 12px; margin-left: 12px;"
        )
        updater = self._get_updater()
        updater.check_now()

        # Reset button after 10s timeout
        from PySide6.QtCore import QTimer
        QTimer.singleShot(10_000, self._reset_check_btn)

    def _reset_check_btn(self):
        """Reset check button state."""
        self._check_update_btn.setEnabled(True)
        self._check_update_btn.setText(t("settings.update_sub.check_now"))

    def _on_update_available(self, info):
        """Handle update available signal."""
        self._reset_check_btn()
        self._update_status_label.setText(
            f"🆕 v{info.version} {t('settings.update_sub.available')}"
        )
        self._update_status_label.setStyleSheet(
            f"color: {Theme.PEACH}; font-size: 12px; font-weight: bold; margin-left: 12px;"
        )
        self._update_now_btn.setVisible(True)
        self._update_now_btn.setText(
            f"⬇️ {t('settings.update_sub.update_now')} (v{info.version})"
        )

        # Show changelog
        if info.changelog:
            self._changelog_label.setText(f"📝 {info.changelog}")
            self._changelog_label.setVisible(True)

        # Also show toast on main window
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, 'show_toast'):
                main_win.show_toast(
                    f"🆕 {t('settings.update_sub.new_version')}: v{info.version}",
                    "info", duration=8000
                )
        except Exception:
            pass

    def _on_update_now(self):
        """Start downloading the update."""
        self._update_now_btn.setEnabled(False)
        self._update_now_btn.setText("⬇️ 0%...")
        updater = self._get_updater()
        updater.download_update()

    def _on_download_progress(self, pct: int):
        """Update download progress on button."""
        self._update_now_btn.setText(f"⬇️ {pct}%...")

    def _on_download_complete(self, zip_path: str):
        """Download finished — apply update."""
        self._update_now_btn.setText(f"📦 {t('settings.update_sub.installing')}")
        self._update_status_label.setText(
            f"📦 {t('settings.update_sub.installing')}"
        )

        # Show toast before restart
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, 'show_toast'):
                main_win.show_toast(
                    f"📦 {t('settings.update_sub.restarting')}",
                    "success", duration=3000
                )
        except Exception:
            pass

        # Apply update (will restart app)
        updater = self._get_updater()
        updater.apply_update(zip_path)

    def _on_download_error(self, error: str):
        """Handle download error."""
        self._update_now_btn.setEnabled(True)
        self._update_now_btn.setText(t("settings.update_sub.update_now"))
        self._update_status_label.setText(f"❌ {error[:50]}")
        self._update_status_label.setStyleSheet(
            f"color: {Theme.RED}; font-size: 12px; margin-left: 12px;"
        )

    def _on_update_applied(self):
        """Update applied — app will restart."""
        self._update_status_label.setText(
            f"🔄 {t('settings.update_sub.restarting')}"
        )

    # ── Post-Queue Action Section ──────────────────────────────────

    def _create_post_queue_section(self) -> QWidget:
        """Create Post-Queue Action section — auto shutdown/sleep after queue completes."""
        section, layout = self._create_section(t("settings.sections.post_queue"))

        from config.settings import get_settings
        settings = get_settings()

        saved_enabled = getattr(settings, 'post_queue_action_enabled', False)
        saved_action = getattr(settings, 'post_queue_action', 'nothing')

        # Row 1: Master toggle
        self.post_queue_switch = self._create_enable_row(
            "Auto action after queue completes:", checked=saved_enabled
        )
        layout.addLayout(self.post_queue_switch._row_layout)

        # Row 2: Action selector (visible only when toggle ON)
        self._post_queue_action_container = QWidget()
        action_layout = QHBoxLayout(self._post_queue_action_container)
        action_layout.setContentsMargins(0, 0, 0, 0)

        action_label = QLabel("Action:")
        action_label.setFixedWidth(150)
        action_label.setStyleSheet(f"color: {Theme.TEXT};")
        action_layout.addWidget(action_label)

        self.post_queue_action_combo = QComboBox()
        self.post_queue_action_combo.addItems(["🔌 Do Nothing", "⚡ Shutdown", "💤 Sleep"])
        # Map saved value to display text
        _action_map = {"nothing": "🔌 Do Nothing", "shutdown": "⚡ Shutdown", "sleep": "💤 Sleep"}
        self.post_queue_action_combo.setCurrentText(_action_map.get(saved_action, "🔌 Do Nothing"))
        self.post_queue_action_combo.setFixedWidth(160)
        action_layout.addWidget(self.post_queue_action_combo)

        action_layout.addStretch()
        layout.addWidget(self._post_queue_action_container)

        # Show/hide action selector based on toggle
        self._post_queue_action_container.setVisible(saved_enabled)
        self.post_queue_switch.toggled_signal.connect(
            lambda checked: self._post_queue_action_container.setVisible(checked)
        )

        # Description
        desc = QLabel("⚠️ When enabled, the selected action runs automatically after all tasks complete (failed tasks are ignored).")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; margin-left: 16px;")
        layout.addWidget(desc)

        # Auto-save
        self.post_queue_switch.toggled_signal.connect(self._save_post_queue_settings)
        self.post_queue_action_combo.currentIndexChanged.connect(
            lambda: self._save_post_queue_settings()
        )

        return section

    def _save_post_queue_settings(self, *args):
        """Persist post-queue action settings to AppSettings."""
        if getattr(self, '_initializing', False):
            return
        from config.settings import get_settings, save_settings
        settings = get_settings()
        settings.post_queue_action_enabled = self.post_queue_switch.isToggled()
        # Map display text to stored value
        _reverse_map = {"🔌 Do Nothing": "nothing", "⚡ Shutdown": "shutdown", "💤 Sleep": "sleep"}
        settings.post_queue_action = _reverse_map.get(
            self.post_queue_action_combo.currentText(), "nothing"
        )
        save_settings()

    # ── Browser Visibility Section ─────────────────────────────────

    def _create_browser_visibility_section(self) -> QWidget:
        """Create Browser Visibility section — Smart-Hide + Hide All toggles.

        Smart-Hide: Hide browsers after launch & successful submit.
                    Show errored account's browser on 403 Phase 2 hard restart.
                    Re-hide after 3 consecutive successful prompts.
        Hide All:   Hide ALL browsers after startup. Only show when
                    adding account or clicking show button in Actions.
                    Mutually exclusive with Smart-Hide.
        """
        section, layout = self._create_section(t("settings.sections.browser"))

        # Load saved values
        from config.settings import get_settings
        s = get_settings()
        saved_smart_hide = getattr(s, 'smart_hide_enabled', True)
        saved_hide_all = getattr(s, 'hide_all_browsers', False)

        # Smart-Hide toggle
        self.smart_hide_switch = self._create_enable_row(
            t("settings.browser_sub.smart_hide"), checked=saved_smart_hide
        )
        layout.addLayout(self.smart_hide_switch._row_layout)

        # Hide All Browsers toggle
        self.hide_all_switch = self._create_enable_row(
            t("settings.browser_sub.hide_all"), checked=saved_hide_all
        )
        layout.addLayout(self.hide_all_switch._row_layout)

        # Auto-save on toggle change — with mutual exclusion
        self.smart_hide_switch.toggled_signal.connect(self._save_browser_visibility_settings)
        self.hide_all_switch.toggled_signal.connect(self._save_browser_visibility_settings)

        return section

    def _save_browser_visibility_settings(self, *args):
        """Persist browser visibility toggles with mutual exclusion.
        
        - Hide All ON → Smart-Hide OFF
        - Smart-Hide ON → Hide All OFF
        Hot-apply: immediately hide/show all running browsers.
        """
        if getattr(self, '_initializing', False):
            return
        from config.settings import get_settings, save_settings
        settings = get_settings()
        
        new_smart_hide = self.smart_hide_switch.isToggled()
        new_hide_all = self.hide_all_switch.isToggled()
        
        old_smart_hide = settings.smart_hide_enabled
        old_hide_all = getattr(settings, 'hide_all_browsers', False)
        
        # Mutual exclusion: if Hide All just turned ON, turn off Smart-Hide
        if new_hide_all and not old_hide_all:
            new_smart_hide = False
            self.smart_hide_switch.blockSignals(True)
            self.smart_hide_switch.setToggled(False)
            self.smart_hide_switch.blockSignals(False)
        # If Smart-Hide just turned ON, turn off Hide All
        elif new_smart_hide and not old_smart_hide:
            new_hide_all = False
            self.hide_all_switch.blockSignals(True)
            self.hide_all_switch.setToggled(False)
            self.hide_all_switch.blockSignals(False)
        
        settings.smart_hide_enabled = new_smart_hide
        settings.hide_all_browsers = new_hide_all
        save_settings()
        
        # Hot-apply: hide or show all running debug browsers
        if self.controller:
            pc = getattr(self.controller, '_profiles_controller', None)
            if pc and hasattr(pc, '_debug_browsers'):
                for email in list(pc._debug_browsers.keys()):
                    try:
                        if new_hide_all or new_smart_hide:
                            pc.hide_debug_browser(email)
                        elif not old_smart_hide and not new_smart_hide and not new_hide_all:
                            # Both off → show all
                            pc.show_debug_browser(email)
                    except Exception:
                        pass


