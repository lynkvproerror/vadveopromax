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
from config.i18n import t

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
    """Custom toggle switch widget with clear on/off visual states."""
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
        from PySide6.QtGui import QPainter, QColor, QPen, QFont
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2
        thumb_margin = 3
        thumb_size = h - thumb_margin * 2

        if self._checked:
            # ON — bright green track
            track_color = QColor(Theme.GREEN)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(track_color)
            p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

            # White thumb (right side)
            thumb_x = w - thumb_size - thumb_margin
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QRectF(thumb_x, thumb_margin, thumb_size, thumb_size))

            # Checkmark inside thumb
            p.setPen(QPen(QColor(Theme.GREEN), 2.0))
            cx = thumb_x + thumb_size / 2
            cy = thumb_margin + thumb_size / 2
            p.drawLine(int(cx - 4), int(cy), int(cx - 1), int(cy + 3))
            p.drawLine(int(cx - 1), int(cy + 3), int(cx + 4), int(cy - 3))
        else:
            # OFF — dark track with visible border
            p.setPen(QPen(QColor("#555555"), 1.5))
            p.setBrush(QColor("#2a2a2a"))
            p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), radius, radius)

            # Gray thumb (left side)
            thumb_x = thumb_margin
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#888888"))
            p.drawEllipse(QRectF(thumb_x, thumb_margin, thumb_size, thumb_size))

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
      _on_toggle_browser_visibility, _on_reload_extension,
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
        
        # Premium-only sections (hidden for Trial tier)
        self._premium_sections: list = []

        self._setup_ui()
        
        # Apply audience visibility (User vs Tester)
        self._apply_audience_visibility()

        # Periodic refresh: ext status column every 5 s
        self._ext_timer = QTimer(self)
        self._ext_timer.timeout.connect(self._refresh_ext_column)
        self._ext_timer.start(5000)

    def retranslate_ui(self):
        """Hot-reload: rebuild entire Settings UI when language changes."""
        # Save current settings to disk before rebuilding
        try:
            self._on_save()
        except Exception:
            pass
        
        # Reset mixin state
        self.setting_combos = {}
        self.output_toggles = {}
        self._restore_sub_toggles = {}
        self._tester_sections = []
        self._premium_sections = []
        
        # Properly remove old layout — Qt won't allow a new layout if old one exists
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            # Transfer old layout to a temp widget → releases self for new layout
            QWidget().setLayout(old_layout)
        
        # Rebuild (reads from get_settings() → restores all values)
        self._setup_ui()
        self._apply_audience_visibility()

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
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
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

        # Build all sections via mixins — grouped by functional area
        
        # ── 1. ACCOUNT SETUP ──
        layout.addWidget(self._create_profiles_section())    # Chrome Profiles
        
        # ── 2. GENERATION CONFIG ──
        layout.addWidget(self._create_defaults_section())    # Default Settings (All)
        continuation_widget = self._create_continuation_section()
        layout.addWidget(continuation_widget)                # Smooth Continuation (self-guarded for Trial)
        
        # ── 3. AI & PRODUCTION ──
        layout.addWidget(self._create_gemini_ai_section())    # Gemini AI: Enhance & Fix + Project Builder AI
        # REMOVED: Project Builder section — bundled data/workflows/ auto-loads,
        # these settings were confusing (showing '0 folder(s)' when data exists).
        # layout.addWidget(self._create_project_builder_section())
        
        # REMOVED: Post-Queue Action — now exclusively in Queue tab
        
        # ── 5. BROWSER & SECURITY ──
        layout.addWidget(self._create_browser_visibility_section())  # Smart Hide (All)
        layout.addWidget(self._create_worker_section())              # Worker Settings + Anti-Detect (All)
        
        # ── 6. UX & APPEARANCE ──
        layout.addWidget(self._create_notification_section())# Notifications (All)
        layout.addWidget(self._create_ui_section())          # UI Theme (All)
        layout.addWidget(self._create_update_section())      # Auto-Update (All)
        
        # ── 6. SYSTEM / DEV (Tester only) ──
        tester_widgets = [
            self._create_session_section(),                  # Session & Data
            self._create_pipeline_section(),                 # Pipeline Optimization
            self._create_enhancer_section(),                 # Image Enhancer
        ]
        for w in tester_widgets:
            layout.addWidget(w)
            self._tester_sections.append(w)
        
        # (Action buttons moved to sticky bar below scroll area)

        # All sections built — allow auto-save signals now
        self._initializing = False

        layout.addStretch()
        scroll.setWidget(container)

        # ── Sticky action buttons bar (OUTSIDE scroll area) ──
        # This ensures Save/Reset/Export/Import/Reload are always visible
        sticky_bar = self._create_sticky_action_bar()
        main_layout.addWidget(sticky_bar)

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
        """Show/hide sections based on license tier.
        
        Trial mode: Profiles, Defaults, Output, Notification, Post-Queue, UI,
                    Browser Visibility, Worker (Anti Detect Spam)
                    Continuation visible but self-guarded with popup
        Premium mode: + Smooth Continuation (enabled)
        Tester mode: + Session, Pipeline, Enhancer
        """
        is_tester = False
        try:
            if self.controller and hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                is_tester = hasattr(lc, 'can_see_dev_console') and lc.can_see_dev_console()
        except Exception:
            pass
        
        # Tester sections: only for tester role
        for section in self._tester_sections:
            section.setVisible(is_tester)
    
    def refresh_role_state(self):
        """Re-evaluate audience visibility and trial guards after license change.
        
        Called when license_activated signal fires (upgrade from Trial → Premium).
        Re-enables toggles that were force-disabled at init for Trial users.
        """
        # Re-apply section visibility (show/hide tester sections)
        self._apply_audience_visibility()
        
        try:
            from services.permissions import PermissionsSystem, Role
            perm = PermissionsSystem.instance()
            if perm.role != Role.TRIAL:
                from config.settings import get_settings
                saved = get_settings()
                
                # Re-enable Anti-Detect Spam (was force-OFF for Trial)
                if hasattr(self, 'anti_detect_switch'):
                    self.anti_detect_switch.setToggled(
                        getattr(saved, 'anti_detect_enabled', True)
                    )
                
                # Re-enable Continuation toggle (was guarded by _is_trial_continuation)
                if hasattr(self, '_is_trial_continuation'):
                    self._is_trial_continuation = False
                if hasattr(self, 'cont_switch'):
                    self.cont_switch.setToggled(
                        getattr(saved, 'continuation_enabled', True)
                    )
        except Exception:
            pass

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

    # ── AI Settings Section ────────────────────────────────────

    def _create_gemini_ai_section(self) -> QFrame:
        """Create AI settings section with 2 panels: Queue + Project Builder."""
        from PySide6.QtWidgets import QTextEdit, QRadioButton, QButtonGroup, QLineEdit
        from config.settings import get_settings
        s = get_settings()

        section, layout = self._create_section("🤖 AI Prompt Processing")

        # ════════════════════════════════════════════════════════
        # PANEL 1: Queue — Enhance / Fix (per-profile account keys)
        # ════════════════════════════════════════════════════════
        q_header = QLabel(t("settings_ai.queue_header"))
        q_header.setStyleSheet(
            f"color: {Theme.BLUE}; font-size: 13px; font-weight: bold; "
            f"margin-top: 4px;"
        )
        layout.addWidget(q_header)

        q_desc = QLabel(
            "Sử dụng Gemini API key từ các profile đã thêm.\n"
            "Ưu tiên Pro (chất lượng cao) → tự động chuyển Flash nếu hết quota."
        )
        q_desc.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        q_desc.setWordWrap(True)
        layout.addWidget(q_desc)

        # Master toggle
        self.gemini_enable_switch = self._create_enable_row(
            "Bật tính năng",
            checked=getattr(s, 'prompt_enhance_enabled', False),
            bold=True
        )
        layout.addLayout(self.gemini_enable_switch._row_layout)

        # Auto-enhance toggle
        self.gemini_auto_enhance = self._create_enable_row(
            "Auto Enhance",
            checked=getattr(s, 'prompt_auto_enhance', False),
        )
        layout.addLayout(self.gemini_auto_enhance._row_layout)

        # Auto-fix toggle
        self.gemini_auto_fix = self._create_enable_row(
            "Auto Fix Policy",
            checked=getattr(s, 'prompt_auto_fix', False),
        )
        layout.addLayout(self.gemini_auto_fix._row_layout)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Theme.SURFACE2}; margin: 8px 0;")
        layout.addWidget(sep)

        # ════════════════════════════════════════════════════════
        # PANEL 2: Project Builder — model + API source selection
        # ════════════════════════════════════════════════════════
        pb_header = QLabel(t("settings_ai.pb_header"))
        pb_header.setStyleSheet(
            f"color: {Theme.PURPLE}; font-size: 13px; font-weight: bold;"
        )
        layout.addWidget(pb_header)

        pb_desc = QLabel(
            "Chọn nguồn API key và model cho tạo nội dung dự án (kịch bản, prompt, SEO...)."
        )
        pb_desc.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        pb_desc.setWordWrap(True)
        layout.addWidget(pb_desc)

        # API Source: Account keys vs Custom
        src_row = QHBoxLayout()
        src_label = QLabel(t("settings_ai.api_source"))
        src_label.setFixedWidth(150)
        src_label.setStyleSheet(f"color: {Theme.TEXT};")
        src_row.addWidget(src_label)

        self._pb_source_group = QButtonGroup(self)
        _radio_style = f"""
            QRadioButton {{
                color: {Theme.TEXT}; spacing: 6px; font-size: 12px;
            }}
            QRadioButton::indicator {{
                width: 16px; height: 16px; border-radius: 8px;
                border: 2px solid {Theme.SUBTEXT0};
                background-color: {Theme.SURFACE0};
            }}
            QRadioButton::indicator:checked {{
                border: 2px solid {Theme.BLUE};
                background-color: {Theme.BLUE};
            }}
            QRadioButton::indicator:hover {{
                border-color: {Theme.LAVENDER};
            }}
        """
        self._pb_src_account = QRadioButton("🔑 Dùng key từ Profile")
        self._pb_src_custom = QRadioButton("🔗 Custom API Keys")
        self._pb_src_account.setStyleSheet(_radio_style)
        self._pb_src_custom.setStyleSheet(_radio_style)
        self._pb_source_group.addButton(self._pb_src_account, 0)
        self._pb_source_group.addButton(self._pb_src_custom, 1)

        current_src = getattr(s, 'pb_ai_source', 'account')
        if current_src == 'custom':
            self._pb_src_custom.setChecked(True)
        else:
            self._pb_src_account.setChecked(True)

        src_row.addWidget(self._pb_src_account)
        src_row.addWidget(self._pb_src_custom)
        src_row.addStretch()
        layout.addLayout(src_row)

        self._pb_source_group.buttonClicked.connect(self._on_pb_source_changed)

        # Provider-Model registry (7 providers)
        self._PROVIDER_MODELS = {
            "Google": [
                "gemini-3.1-flash-lite-preview",
                "gemini-3-flash-preview",
                "gemini-3.1-pro-preview",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash-lite",
            ],
            "OpenAI": [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4.1",
                "gpt-4.1-mini",
                "gpt-4.1-nano",
                "o4-mini",
                "o3",
                "gpt-5",
                "gpt-5-mini",
            ],
            "Anthropic": [
                "claude-sonnet-4-20250514",
                "claude-opus-4-20250514",
                "claude-sonnet-4.5-20250929",
                "claude-haiku-4.5-20251015",
                "claude-opus-4.5-20251124",
                "claude-sonnet-4.6-20260217",
            ],
            "DeepSeek": [
                "deepseek-chat",
                "deepseek-reasoner",
            ],
            "xAI": [
                "grok-3",
                "grok-3-mini",
                "grok-4",
            ],
            "Mistral": [
                "mistral-large-latest",
                "mistral-small-latest",
                "mistral-medium-latest",
                "codestral-latest",
                "pixtral-large-latest",
            ],
            "OpenRouter": [],  # Aggregator — user types any model name
        }
        self._PROVIDER_ICONS = {
            "Google": "🟢", "OpenAI": "🟠", "Anthropic": "🟤",
            "DeepSeek": "🔵", "xAI": "⚫", "Mistral": "🟣", "OpenRouter": "🌐",
        }
        self._PROVIDER_KEY_HINTS = {
            "Google": "AIzaSy...",
            "OpenAI": "sk-proj-...",
            "Anthropic": "sk-ant-...",
            "DeepSeek": "sk-...",
            "xAI": "xai-...",
            "Mistral": "...",
            "OpenRouter": "sk-or-...",
        }
        self._PROVIDER_BASE_URLS = {
            "Google": "https://generativelanguage.googleapis.com/v1beta",
            "OpenAI": "https://api.openai.com/v1",
            "Anthropic": "https://api.anthropic.com/v1",
            "DeepSeek": "https://api.deepseek.com/v1",
            "xAI": "https://api.x.ai/v1",
            "Mistral": "https://api.mistral.ai/v1",
            "OpenRouter": "https://openrouter.ai/api/v1",
        }

        # ── Provider row (visible only in Custom mode) ──
        self._pb_provider_row_widget = QWidget()
        provider_row = QHBoxLayout(self._pb_provider_row_widget)
        provider_row.setContentsMargins(0, 0, 0, 0)
        provider_label = QLabel(t("settings_ai.provider"))
        provider_label.setFixedWidth(150)
        provider_label.setStyleSheet(f"color: {Theme.TEXT};")
        provider_row.addWidget(provider_label)

        _combo_style = f"""
            QComboBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: none; border-radius: 4px;
                padding: 4px 8px; font-size: 12px; font-weight: bold;
            }}
            QComboBox:focus {{ border: 1px solid {Theme.GREEN}; }}
            QComboBox::drop-down {{
                border: none; width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Theme.SURFACE0}; color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2};
                selection-background-color: {Theme.BLUE};
                selection-color: {Theme.CRUST};
            }}
        """

        self._pb_provider_combo = QComboBox()
        self._pb_provider_combo.setFixedWidth(280)
        self._pb_provider_combo.setStyleSheet(_combo_style)
        for name in self._PROVIDER_MODELS:
            icon = self._PROVIDER_ICONS.get(name, "")
            self._pb_provider_combo.addItem(f"{icon} {name}", name)

        # Set current provider
        current_provider = getattr(s, 'pb_ai_provider', 'Google')
        for i in range(self._pb_provider_combo.count()):
            if self._pb_provider_combo.itemData(i) == current_provider:
                self._pb_provider_combo.setCurrentIndex(i)
                break

        self._pb_provider_combo.currentIndexChanged.connect(self._on_pb_provider_changed)
        provider_row.addWidget(self._pb_provider_combo)
        provider_row.addStretch()
        layout.addWidget(self._pb_provider_row_widget)

        # ── Model row (always visible) ──
        self._pb_model_row_widget = QWidget()
        model_row = QHBoxLayout(self._pb_model_row_widget)
        model_row.setContentsMargins(0, 0, 0, 0)
        model_label = QLabel(t("settings_ai.model"))
        model_label.setFixedWidth(150)
        model_label.setStyleSheet(f"color: {Theme.TEXT};")
        model_row.addWidget(model_label)

        self._pb_model_combo = QComboBox()
        self._pb_model_combo.setFixedWidth(280)
        self._pb_model_combo.setStyleSheet(_combo_style)
        self._pb_model_combo.setEditable(True)  # Allow custom model names

        # Populate models based on source + provider
        if current_src == 'custom':
            models_list = self._PROVIDER_MODELS.get(current_provider, [])
        else:
            models_list = self._PROVIDER_MODELS["Google"]
        self._pb_model_combo.addItems(models_list)

        # Set current model
        current_model = getattr(s, 'pb_ai_model', 'gemini-2.0-flash')
        idx = self._pb_model_combo.findText(current_model)
        if idx >= 0:
            self._pb_model_combo.setCurrentIndex(idx)
        else:
            self._pb_model_combo.addItem(current_model)
            self._pb_model_combo.setCurrentText(current_model)

        model_row.addWidget(self._pb_model_combo)
        model_row.addStretch()
        layout.addWidget(self._pb_model_row_widget)

        # ── Base URL row (visible only in Custom mode) ──
        self._pb_baseurl_row_widget = QWidget()
        baseurl_row = QHBoxLayout(self._pb_baseurl_row_widget)
        baseurl_row.setContentsMargins(0, 0, 0, 0)
        baseurl_label = QLabel(t("settings_ai.base_url"))
        baseurl_label.setFixedWidth(150)
        baseurl_label.setStyleSheet(f"color: {Theme.TEXT};")
        baseurl_row.addWidget(baseurl_label)

        self._pb_baseurl_edit = QLineEdit()
        self._pb_baseurl_edit.setFixedWidth(380)
        self._pb_baseurl_edit.setStyleSheet(
            f"background-color: {Theme.SURFACE1}; color: {Theme.TEXT}; "
            f"border: none; border-radius: 4px; "
            f"font-family: Menlo, monospace; font-size: 12px; font-weight: bold; padding: 4px 8px;"
        )
        # Load saved or default base URL
        saved_url = getattr(s, 'pb_ai_base_url', '') or ''
        default_url = self._PROVIDER_BASE_URLS.get(current_provider, '')
        self._pb_baseurl_edit.setText(saved_url if saved_url else default_url)
        self._pb_baseurl_edit.setPlaceholderText(default_url)
        baseurl_row.addWidget(self._pb_baseurl_edit)
        baseurl_row.addStretch()
        layout.addWidget(self._pb_baseurl_row_widget)

        # ── API Keys frame (visible only in Custom mode) ──
        self._pb_keys_frame = QFrame()
        self._pb_keys_frame.setStyleSheet(
            f"background-color: {Theme.SURFACE0}; border-radius: 8px; "
            f"border: 1px solid {Theme.SURFACE2}; padding: 8px;"
        )
        keys_layout = QVBoxLayout(self._pb_keys_frame)
        keys_layout.setContentsMargins(8, 8, 8, 8)
        keys_layout.setSpacing(4)

        keys_header_row = QHBoxLayout()
        keys_title = QLabel(t("settings_ai.api_keys_title"))
        keys_title.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold;")
        keys_header_row.addWidget(keys_title)

        self._pb_keys_count = QLabel(t("settings_ai.keys_count").replace("{count}", "0"))
        self._pb_keys_count.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        keys_header_row.addStretch()
        keys_header_row.addWidget(self._pb_keys_count)
        keys_layout.addLayout(keys_header_row)

        self._pb_keys_edit = QTextEdit()
        self._pb_keys_edit.setFixedHeight(100)
        self._pb_keys_edit.setStyleSheet(
            f"background-color: {Theme.SURFACE1}; color: {Theme.TEXT}; "
            f"border: none; border-radius: 4px; "
            f"font-family: Menlo, monospace; font-size: 12px; font-weight: bold;"
        )
        # Set placeholder based on provider
        hint = self._PROVIDER_KEY_HINTS.get(current_provider, "API key...")
        self._pb_keys_edit.setPlaceholderText(f"{hint}\n{hint}")
        # Load saved keys
        saved_keys = getattr(s, 'pb_ai_custom_keys', [])
        self._pb_keys_edit.setPlainText("\n".join(saved_keys))
        self._pb_keys_edit.textChanged.connect(self._on_pb_keys_changed)
        keys_layout.addWidget(self._pb_keys_edit)

        # Initialize key count display (must be after textChanged connect)
        self._on_pb_keys_changed()

        layout.addWidget(self._pb_keys_frame)

        # Initial visibility (Custom mode only)
        is_custom_init = (current_src == 'custom')
        self._pb_provider_row_widget.setVisible(is_custom_init)
        self._pb_baseurl_row_widget.setVisible(False)  # Internal only, not shown to user
        self._pb_keys_frame.setVisible(is_custom_init)

        # ── Auto-save on change (R4 fix) ──
        self.gemini_enable_switch.toggled_signal.connect(self._save_gemini_ai_settings)
        self.gemini_auto_enhance.toggled_signal.connect(self._save_gemini_ai_settings)
        self.gemini_auto_fix.toggled_signal.connect(self._save_gemini_ai_settings)
        self._pb_source_group.buttonClicked.connect(self._save_gemini_ai_settings)
        self._pb_provider_combo.currentIndexChanged.connect(self._save_gemini_ai_settings)
        self._pb_model_combo.currentTextChanged.connect(self._save_gemini_ai_settings)
        self._pb_keys_edit.textChanged.connect(self._save_gemini_ai_settings)

        return section

    def _save_gemini_ai_settings(self, *args):
        """Persist Gemini AI + Project Builder AI settings to AppSettings.
        
        Hot-reload: Updates in-memory singleton immediately so pipeline
        picks up new keys on next Gemini call without restart.
        """
        if getattr(self, '_initializing', False):
            return
        try:
            from config.settings import get_settings, save_settings
            import logging
            _log = logging.getLogger('veo.settings')
            s = get_settings()
            # Queue toggles
            if hasattr(self, 'gemini_enable_switch'):
                s.prompt_enhance_enabled = self.gemini_enable_switch.isToggled()
            if hasattr(self, 'gemini_auto_enhance'):
                s.prompt_auto_enhance = self.gemini_auto_enhance.isToggled()
            if hasattr(self, 'gemini_auto_fix'):
                s.prompt_auto_fix = self.gemini_auto_fix.isToggled()
            # Project Builder source
            if hasattr(self, '_pb_src_custom'):
                s.pb_ai_source = 'custom' if self._pb_src_custom.isChecked() else 'account'
            if hasattr(self, '_pb_provider_combo'):
                s.pb_ai_provider = self._pb_provider_combo.currentData() or 'Google'
            if hasattr(self, '_pb_model_combo'):
                s.pb_ai_model = self._pb_model_combo.currentText().strip()
            if hasattr(self, '_pb_baseurl_edit'):
                s.pb_ai_base_url = self._pb_baseurl_edit.text().strip()
            if hasattr(self, '_pb_keys_edit'):
                text = self._pb_keys_edit.toPlainText().strip()
                old_keys = set(s.pb_ai_custom_keys)
                new_keys = [k.strip() for k in text.split('\n') if k.strip()]
                s.pb_ai_custom_keys = new_keys
                # Hot-reload: reset quota for newly added keys
                added = set(new_keys) - old_keys
                if added:
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        for k in added:
                            state = qm._get_state(k)
                            state.rpm_blocked_at = None
                            state.rpd_blocked_at = None
                        _log.info(
                            f"[Settings] 🔑 Hot-reload: {len(added)} new key(s) added, "
                            f"total {len(new_keys)} keys (quota reset for new keys)"
                        )
                    except Exception:
                        pass
                if len(new_keys) != len(old_keys):
                    _log.info(f"[Settings] 🔑 API keys updated: {len(old_keys)} → {len(new_keys)}")
            save_settings()
        except Exception as e:
            logging.getLogger('settings').error(f'Failed to save Gemini AI settings: {e}')

    def _on_pb_source_changed(self):
        """Toggle provider/keys/baseurl visibility and filter models by source."""
        is_custom = self._pb_src_custom.isChecked()
        self._pb_provider_row_widget.setVisible(is_custom)
        self._pb_keys_frame.setVisible(is_custom)

        # Update model combo
        if is_custom:
            # Custom: use selected provider
            self._on_pb_provider_changed()
        else:
            # Profile Key: Google-only
            current_model = self._pb_model_combo.currentText().strip()
            self._pb_model_combo.blockSignals(True)
            self._pb_model_combo.clear()
            self._pb_model_combo.addItems(self._PROVIDER_MODELS["Google"])
            idx = self._pb_model_combo.findText(current_model)
            if idx >= 0:
                self._pb_model_combo.setCurrentIndex(idx)
            else:
                self._pb_model_combo.setCurrentIndex(0)
            self._pb_model_combo.blockSignals(False)

    def _on_pb_provider_changed(self):
        """Filter model combo by selected provider, update base URL and key placeholder."""
        provider = self._pb_provider_combo.currentData() or "Google"
        models = self._PROVIDER_MODELS.get(provider, [])

        current_model = self._pb_model_combo.currentText().strip()
        self._pb_model_combo.blockSignals(True)
        self._pb_model_combo.clear()
        self._pb_model_combo.addItems(models)
        idx = self._pb_model_combo.findText(current_model)
        if idx >= 0:
            self._pb_model_combo.setCurrentIndex(idx)
        else:
            if self._pb_model_combo.count() > 0:
                self._pb_model_combo.setCurrentIndex(0)
        self._pb_model_combo.blockSignals(False)

        # Update base URL
        default_url = self._PROVIDER_BASE_URLS.get(provider, '')
        self._pb_baseurl_edit.setText(default_url)
        self._pb_baseurl_edit.setPlaceholderText(default_url)

        # Update key placeholder
        hint = self._PROVIDER_KEY_HINTS.get(provider, "API key...")
        self._pb_keys_edit.setPlaceholderText(f"{hint}\n{hint}")

    def _on_pb_keys_changed(self):
        """Update key count label when keys text changes."""
        text = self._pb_keys_edit.toPlainText().strip()
        keys = [k.strip() for k in text.split("\n") if k.strip()]
        self._pb_keys_count.setText(f"{len(keys)} key(s)")

    # ── Project Builder Section ──────────────────────────────

    def _create_project_builder_section(self) -> QFrame:
        """Create Project Builder settings section."""
        from PySide6.QtWidgets import QLineEdit, QSpinBox
        from config.settings import get_settings
        s = get_settings()

        section, layout = self._create_section("📋 Project Builder")

        # Workflow Sources
        ws_row = QHBoxLayout()
        ws_label = QLabel(t("settings_ai.workflow_sources"))
        ws_label.setFixedWidth(150)
        ws_label.setStyleSheet(f"color: {Theme.TEXT};")
        ws_row.addWidget(ws_label)

        sources = getattr(s, 'workflow_template_sources', [])
        ws_count = QLabel(f"{len(sources)} folder(s)")
        ws_count.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        ws_row.addWidget(ws_count)
        self._ws_count_label = ws_count

        ws_btn = QPushButton(t("settings_ai.manage"))
        ws_btn.setMinimumWidth(90)
        ws_btn.setProperty("variant", "secondary")
        ws_btn.setProperty("btnSize", "sm")
        ws_btn.clicked.connect(lambda: self._manage_source_dirs('workflow_template_sources'))
        ws_row.addWidget(ws_btn)
        ws_row.addStretch()
        layout.addLayout(ws_row)

        # Rules Sources
        rs_row = QHBoxLayout()
        rs_label = QLabel(t("settings_ai.rules_sources"))
        rs_label.setFixedWidth(150)
        rs_label.setStyleSheet(f"color: {Theme.TEXT};")
        rs_row.addWidget(rs_label)

        rules = getattr(s, 'workflow_rules_sources', [])
        rs_count = QLabel(f"{len(rules)} folder(s)")
        rs_count.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        rs_row.addWidget(rs_count)
        self._rs_count_label = rs_count

        rs_btn = QPushButton(t("settings_ai.manage"))
        rs_btn.setMinimumWidth(90)
        rs_btn.setProperty("variant", "secondary")
        rs_btn.setProperty("btnSize", "sm")
        rs_btn.clicked.connect(lambda: self._manage_source_dirs('workflow_rules_sources'))
        rs_row.addWidget(rs_btn)
        rs_row.addStretch()
        layout.addLayout(rs_row)

        # Default scenes
        scenes_row = QHBoxLayout()
        scenes_label = QLabel(t("settings_ai.default_scenes"))
        scenes_label.setFixedWidth(150)
        scenes_label.setStyleSheet(f"color: {Theme.TEXT};")
        scenes_row.addWidget(scenes_label)

        self._project_scenes_spin = QSpinBox()
        self._project_scenes_spin.setRange(1, 30)
        self._project_scenes_spin.setValue(getattr(s, 'project_default_scenes', 10))
        self._project_scenes_spin.setFixedWidth(80)
        scenes_row.addWidget(self._project_scenes_spin)
        scenes_row.addStretch()
        layout.addLayout(scenes_row)

        # Default output folder
        out_row = QHBoxLayout()
        out_label = QLabel(t("settings_ai.default_output"))
        out_label.setFixedWidth(150)
        out_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        out_row.addWidget(out_label)

        self._project_output_entry = QLineEdit()
        self._project_output_entry.setText(getattr(s, 'project_output_base', ''))
        self._project_output_entry.setPlaceholderText(t("tooltips.select_output"))
        self._project_output_entry.setMinimumHeight(32)
        self._project_output_entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: none; border-radius: 4px;
                padding: 4px 8px; font-weight: bold;
            }}
        """)
        out_row.addWidget(self._project_output_entry)

        browse_btn = QPushButton("📂")
        browse_btn.setMinimumWidth(40)
        browse_btn.setFixedHeight(32)
        browse_btn.setProperty("variant", "secondary")
        browse_btn.clicked.connect(self._browse_project_output)
        out_row.addWidget(browse_btn)
        layout.addLayout(out_row)

        return section

    def _manage_source_dirs(self, setting_key: str):
        """Open dialog to manage source directories."""
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Add Source Folder")
        if folder:
            from config.settings import get_settings, save_settings
            s = get_settings()
            current = getattr(s, setting_key, [])
            if folder not in current:
                current.append(folder)
                setattr(s, setting_key, current)
                save_settings()
                # Update count labels
                if setting_key == 'workflow_template_sources' and hasattr(self, '_ws_count_label'):
                    self._ws_count_label.setText(f"{len(current)} folder(s)")
                elif setting_key == 'workflow_rules_sources' and hasattr(self, '_rs_count_label'):
                    self._rs_count_label.setText(f"{len(current)} folder(s)")
                show_info(self, t("dialogs.added"), t("dialogs.folder_added").replace("{folder}", folder))
            else:
                show_info(self, t("dialogs.exists"), t("dialogs.folder_exists"))

    def _browse_project_output(self):
        """Browse for project output folder."""
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Project Output Folder")
        if folder:
            self._project_output_entry.setText(folder)

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
        save_btn = QPushButton(t("settings_buttons.save_all"))
        save_btn.setToolTip(t("tooltips.save_all_tooltip"))
        save_btn.setProperty("variant", "success")
        save_btn.setProperty("btnSize", "lg")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        # Reset Defaults button
        reset_btn = QPushButton(t("settings_buttons.reset_defaults"))
        reset_btn.setProperty("variant", "secondary")
        reset_btn.setProperty("btnSize", "lg")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        # Export Config button - blue
        export_btn = QPushButton(t("settings_buttons.export_config"))
        export_btn.setProperty("btnSize", "lg")
        export_btn.clicked.connect(self._on_export)
        layout.addWidget(export_btn)

        # Import Config button
        import_btn = QPushButton(t("settings_buttons.import_config"))
        import_btn.setProperty("variant", "secondary")
        import_btn.setProperty("btnSize", "lg")
        import_btn.clicked.connect(self._on_import)
        layout.addWidget(import_btn)

        # Reload App button — restart Python process
        reload_btn = QPushButton(t("settings_buttons.reload_app"))
        reload_btn.setToolTip(t("tooltips.reload_tooltip"))
        reload_btn.setProperty("variant", "warning")
        reload_btn.setProperty("btnSize", "lg")
        reload_btn.clicked.connect(self._on_reload_app)
        layout.addWidget(reload_btn)

        layout.addStretch()

        return frame

    def _create_sticky_action_bar(self) -> QWidget:
        """Create a sticky bar with ALL actions — always visible at bottom."""
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.MANTLE};
                border-top: 1px solid {Theme.BORDER};
            }}
        """)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 6, 16, 6)
        bar_layout.setSpacing(8)

        # Save All
        save_btn = QPushButton("💾 " + t('settings_buttons.save_all'))
        save_btn.setToolTip(t("tooltips.save_all_tooltip"))
        save_btn.setProperty("variant", "success")
        save_btn.setProperty("btnSize", "sm")
        save_btn.clicked.connect(self._on_save)
        bar_layout.addWidget(save_btn)

        # Reset Defaults
        reset_btn = QPushButton("🔄 " + t('settings_buttons.reset_defaults'))
        reset_btn.setProperty("variant", "secondary")
        reset_btn.setProperty("btnSize", "sm")
        reset_btn.clicked.connect(self._on_reset)
        bar_layout.addWidget(reset_btn)

        # Export Config
        export_btn = QPushButton("📤 " + t('settings_buttons.export_config'))
        export_btn.setProperty("btnSize", "sm")
        export_btn.clicked.connect(self._on_export)
        bar_layout.addWidget(export_btn)

        # Import Config
        import_btn = QPushButton("📥 " + t('settings_buttons.import_config'))
        import_btn.setProperty("variant", "secondary")
        import_btn.setProperty("btnSize", "sm")
        import_btn.clicked.connect(self._on_import)
        bar_layout.addWidget(import_btn)

        # Reload App
        reload_btn = QPushButton("⚡ " + t('settings_buttons.reload_app'))
        reload_btn.setToolTip(t("tooltips.reload_tooltip"))
        reload_btn.setProperty("variant", "warning")
        reload_btn.setProperty("btnSize", "sm")
        reload_btn.clicked.connect(self._on_reload_app)
        bar_layout.addWidget(reload_btn)

        bar_layout.addStretch()
        return bar

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
            # B1 fix: lookup output toggles by matching the actual dict keys
            for key, toggle in self.output_toggles.items():
                k_lower = key.lower()
                if "timestamp" in k_lower:
                    s.include_timestamp = toggle.isChecked()
                elif "quality" in k_lower:
                    s.include_quality = toggle.isChecked()
                elif "auto" in k_lower and "start" in k_lower:
                    s.auto_start_queue = toggle.isChecked()
                elif "pause" in k_lower:
                    s.pause_on_error = toggle.isChecked()

            # ── Continuation ──
            if hasattr(self, 'cont_switch'):
                s.continuation_enabled = self.cont_switch.isToggled()
            if hasattr(self, 'extract_menu'):
                s.extract_point_ms = self._parse_extract_point(self.extract_menu.currentText())

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

            # REMOVED: Post-Queue Action — now exclusively in Queue tab

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
            if hasattr(self, 'hide_all_switch'):
                s.hide_all_browsers = self.hide_all_switch.isToggled()
            
            # ── Gemini AI ──
            if hasattr(self, 'gemini_enable_switch'):
                s.prompt_enhance_enabled = self.gemini_enable_switch.isToggled()
            if hasattr(self, 'gemini_auto_enhance'):
                s.prompt_auto_enhance = self.gemini_auto_enhance.isToggled()
            if hasattr(self, 'gemini_auto_fix'):
                s.prompt_auto_fix = self.gemini_auto_fix.isToggled()
            
            # ── Project Builder AI (hot-reload keys) ──
            if hasattr(self, '_pb_src_custom'):
                s.pb_ai_source = "custom" if self._pb_src_custom.isChecked() else "account"
            if hasattr(self, '_pb_provider_combo'):
                s.pb_ai_provider = self._pb_provider_combo.currentData() or "Google"
            if hasattr(self, '_pb_model_combo'):
                s.pb_ai_model = self._pb_model_combo.currentText().strip()
            if hasattr(self, '_pb_baseurl_edit'):
                s.pb_ai_base_url = self._pb_baseurl_edit.text().strip()
            if hasattr(self, '_pb_keys_edit'):
                text = self._pb_keys_edit.toPlainText().strip()
                old_keys = set(s.pb_ai_custom_keys)
                new_keys = [k.strip() for k in text.split("\n") if k.strip()]
                s.pb_ai_custom_keys = new_keys
                # Hot-reload: reset quota for newly added keys
                added = set(new_keys) - old_keys
                if added:
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        for k in added:
                            state = qm._get_state(k)
                            state.rpm_blocked_at = None
                            state.rpd_blocked_at = None
                        log.info(
                            f"[Settings] 🔑 Hot-reload: {len(added)} new key(s), "
                            f"total {len(new_keys)} (quota reset)"
                        )
                    except Exception:
                        pass
                log.info(f"[Settings] 🔑 Saved {len(new_keys)} API key(s)")
            
            # REMOVED: Project Builder settings — section hidden from UI
            # if hasattr(self, '_project_scenes_spin'):
            #     s.project_default_scenes = self._project_scenes_spin.value()
            # if hasattr(self, '_project_output_entry'):
            #     s.project_output_base = self._project_output_entry.text()
            
            # Hide emails state
            if hasattr(self, '_emails_hidden'):
                s.hide_emails = self._emails_hidden

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

            if hasattr(self, 'auto_retry_dl_switch'):
                s.auto_retry_download = self.auto_retry_dl_switch.isToggled()
            if hasattr(self, 'dl_retry_max'):
                s.auto_retry_download_max = self.dl_retry_max.value()
            if hasattr(self, 'prewarm_switch'):
                s.prewarm_enabled = self.prewarm_switch.isToggled()
            if hasattr(self, 'prewarm_threshold'):
                s.prewarm_idle_threshold = self.prewarm_threshold.value()

            # ── Auto-Update ──
            if hasattr(self, 'auto_update_toggle'):
                s.auto_update_enabled = self.auto_update_toggle.isToggled()

            # ── UI (Language) ──
            if hasattr(self, 'lang_menu'):
                s.ui_language = self.lang_menu.currentText()

            # Persist to disk
            save_settings()
            log.info(f"Settings saved to {s._default_path()}")

            # Show confirmation
            show_info(self, t("dialogs.saved"), t("dialogs.all_saved"))

            # Also emit signal for live-update consumers
            settings_dict = self.get_settings()
            self.settings_changed.emit(settings_dict)
        except Exception as e:
            log.error(f"Failed to save settings: {e}")
            show_warning(self, t("dialogs.error"), t("dialogs.save_failed").replace("{error}", str(e)))

    def _on_reset(self):
        """Reset to default values and persist."""
        if not show_confirm(self, t("dialogs.reset_defaults"),
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
                self.setting_combos["Download Quality"].setCurrentText("720p")
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

            # ── Anti-Detect Spam ──
            if hasattr(self, 'anti_detect_switch'):
                self.anti_detect_switch.setToggled(True)
            if hasattr(self, 'anti_detect_delay_min'):
                self.anti_detect_delay_min.setValue(3.0)
            if hasattr(self, 'anti_detect_delay_max'):
                self.anti_detect_delay_max.setValue(8.0)

            # ── Enhancer Toggles ──
            if hasattr(self, '_enhance_context_toggle'):
                self._enhance_context_toggle.setToggled(True)
            if hasattr(self, '_enhance_library_toggle'):
                self._enhance_library_toggle.setToggled(True)
            if hasattr(self, '_enhance_auto_toggle'):
                self._enhance_auto_toggle.setToggled(False)

            # ── Session & Data ──
            if hasattr(self, 'restore_queue_switch'):
                self.restore_queue_switch.setToggled(False)
            if hasattr(self, 'restore_tabs_switch'):
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

            # REMOVED: Post-Queue Action — now exclusively in Queue tab

            # ── Browser Visibility ──
            if hasattr(self, 'smart_hide_switch'):
                self.smart_hide_switch.setToggled(False)
            if hasattr(self, 'hide_all_switch'):
                self.hide_all_switch.setToggled(True)

            # ── Gemini AI ──
            if hasattr(self, 'gemini_enable_switch'):
                self.gemini_enable_switch.setToggled(False)
            if hasattr(self, 'gemini_auto_enhance'):
                self.gemini_auto_enhance.setToggled(False)
            if hasattr(self, 'gemini_auto_fix'):
                self.gemini_auto_fix.setToggled(False)

            # ── Project Builder AI ──
            if hasattr(self, '_pb_src_account'):
                self._pb_src_account.setChecked(True)
            if hasattr(self, '_pb_provider_combo'):
                self._pb_provider_combo.setCurrentIndex(0)  # Google
            if hasattr(self, '_pb_model_combo'):
                self._pb_model_combo.setCurrentText('gemini-2.0-flash')
            if hasattr(self, '_pb_keys_edit'):
                self._pb_keys_edit.clear()
            if hasattr(self, '_pb_provider_row_widget'):
                self._pb_provider_row_widget.setVisible(False)
            if hasattr(self, '_pb_keys_frame'):
                self._pb_keys_frame.setVisible(False)

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

            if hasattr(self, 'auto_retry_dl_switch'):
                self.auto_retry_dl_switch.setToggled(True)
            if hasattr(self, 'dl_retry_max'):
                self.dl_retry_max.setValue(3)
            if hasattr(self, 'prewarm_switch'):
                self.prewarm_switch.setToggled(True)
            if hasattr(self, 'prewarm_threshold'):
                self.prewarm_threshold.setValue(10)

            # ── Auto-Update ──
            if hasattr(self, 'auto_update_toggle'):
                self.auto_update_toggle.setToggled(True)


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
        # B1 fix: match output toggles by substring (i18n-safe)
        _import_map = {
            "include_timestamp": "timestamp",
            "include_quality": "quality",
            "auto_start_queue": "auto",
            "pause_on_error": "pause",
        }
        for setting_key, substr in _import_map.items():
            if setting_key in settings:
                for tkey, toggle in self.output_toggles.items():
                    if substr in tkey.lower():
                        toggle.setChecked(bool(settings[setting_key]))
                        break
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
        if "retry_count" in settings and hasattr(self, 'retry_count'):
            self.retry_count.setValue(int(settings["retry_count"]))
        if "request_timeout" in settings and hasattr(self, 'request_timeout'):
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
        # REMOVED: Post-Queue Action — now exclusively in Queue tab
        # Browser Visibility
        if "smart_hide_enabled" in settings and hasattr(self, 'smart_hide_switch'):
            self.smart_hide_switch.setToggled(bool(settings["smart_hide_enabled"]))
        if "hide_all_browsers" in settings and hasattr(self, 'hide_all_switch'):
            self.hide_all_switch.setToggled(bool(settings["hide_all_browsers"]))
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

        # Language
        if "language" in settings and hasattr(self, 'lang_menu'):
            self.lang_menu.setCurrentText(settings["language"])
        # Auto-Update
        if "auto_update_enabled" in settings and hasattr(self, 'auto_update_toggle'):
            self.auto_update_toggle.setToggled(bool(settings["auto_update_enabled"]))
        # REMOVED: Post-Queue Sweep Rounds — now exclusively in Queue tab
        # Gemini AI
        if "prompt_enhance_enabled" in settings and hasattr(self, 'gemini_enable_switch'):
            self.gemini_enable_switch.setToggled(bool(settings["prompt_enhance_enabled"]))
        if "prompt_auto_enhance" in settings and hasattr(self, 'gemini_auto_enhance'):
            self.gemini_auto_enhance.setToggled(bool(settings["prompt_auto_enhance"]))
        if "prompt_auto_fix" in settings and hasattr(self, 'gemini_auto_fix'):
            self.gemini_auto_fix.setToggled(bool(settings["prompt_auto_fix"]))
        # Pipeline: Auto-Retry Download
        if "auto_retry_download" in settings and hasattr(self, 'auto_retry_dl_switch'):
            self.auto_retry_dl_switch.setToggled(bool(settings["auto_retry_download"]))
        if "auto_retry_download_max" in settings and hasattr(self, 'dl_retry_max'):
            self.dl_retry_max.setValue(int(settings["auto_retry_download_max"]))
        # Pipeline: Pre-warm
        if "prewarm_enabled" in settings and hasattr(self, 'prewarm_switch'):
            self.prewarm_switch.setToggled(bool(settings["prewarm_enabled"]))
        if "prewarm_idle_threshold" in settings and hasattr(self, 'prewarm_threshold'):
            self.prewarm_threshold.setValue(int(settings["prewarm_idle_threshold"]))

    # ── Helpers ──

    def _parse_extract_point(self, text: str) -> int:
        """Convert '750ms (recommended)' → 750."""
        import re
        match = re.search(r'(\d+)', text)
        return int(match.group(1)) if match else 750

    def get_settings(self) -> dict:
        """Get current settings — used for export and signal emission."""
        # B1 fix: lookup output toggles by substring matching (i18n-safe)
        _ot_ts = _ot_q = _ot_as = _ot_pe = False
        for key, toggle in self.output_toggles.items():
            k_lower = key.lower()
            if "timestamp" in k_lower:
                _ot_ts = toggle.isChecked()
            elif "quality" in k_lower:
                _ot_q = toggle.isChecked()
            elif "auto" in k_lower and "start" in k_lower:
                _ot_as = toggle.isChecked()
            elif "pause" in k_lower:
                _ot_pe = toggle.isChecked()
        result = {
            "aspect_ratio": self.setting_combos.get("Aspect Ratio").currentText() if "Aspect Ratio" in self.setting_combos else "",
            "download_quality": self.setting_combos.get("Download Quality").currentText() if "Download Quality" in self.setting_combos else "",
            "ai_model": self.setting_combos.get("AI Model").currentText() if "AI Model" in self.setting_combos else "",
            "outputs_per_prompt": self.setting_combos.get("Outputs per Prompt").currentText() if "Outputs per Prompt" in self.setting_combos else "",
            "image_ai_model": self.setting_combos.get("Image AI Model").currentText() if "Image AI Model" in self.setting_combos else "",
            "image_quality": self.setting_combos.get("Image Quality").currentText() if "Image Quality" in self.setting_combos else "",
            "output_folder": self.output_folder_entry.text(),
            "include_timestamp": _ot_ts,
            "include_quality": _ot_q,
            "auto_start_queue": _ot_as,
            "pause_on_error": _ot_pe,
            "continuation_enabled": self.cont_switch.isToggled(),
            "extract_point_ms": self._parse_extract_point(self.extract_menu.currentText()),
            # Enhancer Image (3-toggle system)
            "enhance_context_menu": self._enhance_context_toggle.isToggled() if hasattr(self, '_enhance_context_toggle') else True,
            "enhance_library": self._enhance_library_toggle.isToggled() if hasattr(self, '_enhance_library_toggle') else True,
            "enhance_auto_continuation": self._enhance_auto_toggle.isToggled() if hasattr(self, '_enhance_auto_toggle') else False,
            "language": self.lang_menu.currentText() if hasattr(self, 'lang_menu') else "English",
            # Worker Settings
            "anti_detect_enabled": self.anti_detect_switch.isToggled() if hasattr(self, 'anti_detect_switch') else True,
            "anti_detect_delay_min": self.anti_detect_delay_min.value() if hasattr(self, 'anti_detect_delay_min') else 3.0,
            "anti_detect_delay_max": self.anti_detect_delay_max.value() if hasattr(self, 'anti_detect_delay_max') else 8.0,
            # Session & Data
            "restore_queue_on_startup": self.restore_queue_switch.isToggled() if hasattr(self, 'restore_queue_switch') else False,
            "restore_tabs_on_startup": self.restore_tabs_switch.isToggled() if hasattr(self, 'restore_tabs_switch') else True,
            # Notifications
            "notify_toast_enabled": self.notify_toast_toggle.isToggled() if hasattr(self, 'notify_toast_toggle') else True,
            "notify_sound_enabled": self.notify_sound_toggle.isToggled() if hasattr(self, 'notify_sound_toggle') else True,
            "notify_sound_file": self._get_selected_sound() if hasattr(self, '_get_selected_sound') else "default",
            # REMOVED: Post-Queue Action — now exclusively in Queue tab
            # Browser Visibility
            "smart_hide_enabled": self.smart_hide_switch.isToggled() if hasattr(self, 'smart_hide_switch') else True,
            "hide_all_browsers": self.hide_all_switch.isToggled() if hasattr(self, 'hide_all_switch') else False,
            # Pipeline Optimization
            "adaptive_burst_enabled": self.burst_switch.isToggled() if hasattr(self, 'burst_switch') else True,
            "burst_min_delay": self.burst_min.value() if hasattr(self, 'burst_min') else 2.0,
            "burst_max_delay": self.burst_max.value() if hasattr(self, 'burst_max') else 15.0,
            "recaptcha_pool_enabled": self.pool_switch.isToggled() if hasattr(self, 'pool_switch') else True,
            "recaptcha_pool_size": self.pool_size.value() if hasattr(self, 'pool_size') else 2,
            "watchdog_timeout_min": self.watchdog_timeout.value() if hasattr(self, 'watchdog_timeout') else 10,
            "journal_save_interval_sec": self.journal_interval.value() if hasattr(self, 'journal_interval') else 30,

            "auto_retry_download": self.auto_retry_dl_switch.isToggled() if hasattr(self, 'auto_retry_dl_switch') else True,
            "auto_retry_download_max": self.dl_retry_max.value() if hasattr(self, 'dl_retry_max') else 3,
            "prewarm_enabled": self.prewarm_switch.isToggled() if hasattr(self, 'prewarm_switch') else True,
            "prewarm_idle_threshold": self.prewarm_threshold.value() if hasattr(self, 'prewarm_threshold') else 10,
            # Auto-Update
            "auto_update_enabled": self.auto_update_toggle.isToggled() if hasattr(self, 'auto_update_toggle') else True,
            # REMOVED: Post-Queue Sweep Rounds — now exclusively in Queue tab
            # Gemini AI
            "prompt_enhance_enabled": self.gemini_enable_switch.isToggled() if hasattr(self, 'gemini_enable_switch') else False,
            "prompt_auto_enhance": self.gemini_auto_enhance.isToggled() if hasattr(self, 'gemini_auto_enhance') else False,
            "prompt_auto_fix": self.gemini_auto_fix.isToggled() if hasattr(self, 'gemini_auto_fix') else False,
        }
        # Granular restore sub-toggles
        if hasattr(self, '_restore_sub_toggles'):
            for attr_name, toggle in self._restore_sub_toggles.items():
                result[attr_name] = toggle.isToggled()
        return result
