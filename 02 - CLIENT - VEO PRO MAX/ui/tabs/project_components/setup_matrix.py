"""
VEO Pro Max — Setup Matrix Panel for Project Builder

Replaces the old sidebar with 8 content dimensions (toggle buttons)
+ production settings (Image/Video/Output).

Inter-dimension logic:
  R1: D1=health   → D2=pmcs, D4=mixed
  R2: D1=entertainment → D2=3act
  R3: D1=family   → D2=conflict_tips, D3=realistic
  R4: D1=fashion  → D2=silent_review
  R5: D6 selected → D3=matching visual style
  R6: D5=kids     → D7=fun
  R7: D1 (2 selected) → Hybrid mode
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSpinBox, QPushButton, QFrame,
    QScrollArea, QFileDialog, QLineEdit, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme
from config.i18n import t

import logging
log = logging.getLogger("veo.setup_matrix")


# ═══════════════════════════════════════════════════════════════════
# Data: Dimension options
# ═══════════════════════════════════════════════════════════════════

# ── Project Type (new) ──
PROJECT_TYPES = [
    ("video_voice",    "🎬 Video + Voice"),
    ("video_silent",   "🎞️ Video (No Voice)"),
    ("animation",      "🎭 Phim Hoạt hình"),
    ("action",         "💥 Phim Hành động"),
    ("documentary",    "📹 Phim Tài liệu"),
    ("philosophy",     "🧘 Triết lý / Tâm linh"),
    ("slideshow",      "🖼️ Slideshow Ảnh"),
    ("storytelling",   "📖 Kể chuyện"),
    ("comedy",         "😂 Hài / Giải trí"),
    ("music_video",    "🎵 Music Video"),
    ("tutorial",       "📚 Hướng dẫn / How-to"),
    ("product_review", "📦 Review Sản phẩm"),
    ("custom",         "✏️ Custom"),
]

# ── Clip durations (seconds) — VEO supports 8s only ──
CLIP_DURATIONS = [8]

CATEGORIES = [
    ("health",          "🏥 Health"),
    ("entertainment",   "🎬 Entertainment"),
    ("family",          "👨‍👩‍👧 Family"),
    ("fashion",         "👗 Fashion"),
    ("tips",            "💡 Tips"),
    ("anthropomorphic", "🦊 Nhân hóa"),
    ("history",         "📜 Lịch sử"),
    ("science",         "🔬 Khoa học"),
    ("diy",             "🏗️ DIY"),
    ("gaming",          "🎮 Gaming"),
    ("animal",          "🐱 Animal"),
    ("cooking",         "🍳 Nấu ăn"),
    ("finance",         "💰 Tài chính"),
    ("religion",        "🙏 Tôn giáo"),
    ("social",          "🤝 Xã hội"),
    ("life",            "🌿 Đời sống"),
    ("education",       "📚 Giáo dục"),
    ("spiritual",       "🧘 Tâm linh"),
    ("experience",      "🌟 Kinh nghiệm"),
    ("psychology",      "🧠 Tâm lý"),
    ("custom",          "✏️ Custom"),
]

STRUCTURES = [
    ("pmcs",           "PMCS"),
    ("3act",           "3-Act"),
    ("conflict_tips",  "Tips"),
    ("silent_review",  "Silent"),
    ("pov_styling",    "POV"),
    ("narrative",      "Narrative"),
    ("montage",        "Montage"),
    ("parallel",       "Song song"),
    ("loop_cycle",     "Vòng lặp"),
    ("minimal",        "Tối giản"),
    ("before_after",   "Trước/Sau"),
    ("countdown",      "Countdown"),
    ("interview",      "Phỏng vấn"),
    ("custom",         "Custom"),
]

VISUAL_STYLES = [
    ("3d_pixar",       "3D Pixar"),
    ("realistic",      "Realistic"),
    ("anime",          "Anime"),
    ("disney_3d",      "Disney"),
    ("sketch",         "Sketch"),
    ("documentary",    "Documen"),
    ("minecraft",      "Minecraft"),
    ("photorealistic", "PhotoReal"),
    ("miniature",      "Miniature"),
    ("scientific",     "Science"),
    ("stickfigure",    "Người que"),
    ("watercolor",     "Watercolor"),
    ("claymation",     "Claymation"),
    ("retro_pixel",    "Retro/Pixel"),
    ("oil_painting",   "Oil Paint"),
    ("noir",           "Film Noir"),
    ("neon_cyber",     "Neon/Cyber"),
    ("pastel",         "Pastel"),
]

CHARACTER_TYPES = [
    ("anthropomorphic", "Nhân hóa"),
    ("human",           "Người"),
    ("animal",          "Động vật"),
    ("toy",             "Đồ chơi"),
    ("mixed",           "Mix"),
]

AUDIENCES = [
    ("kids",     "Kids"),
    ("teens",    "Teens"),
    ("adults",   "Adults"),
    ("family",   "Family"),
    ("seniors",  "Người cao tuổi"),
    ("all_ages", "Mọi lứa tuổi"),
]

PERSONAS = [
    ("mythos",             "Mythos Chronicle"),
    ("chronicle",          "Chronicle Weaver"),
    ("microset",           "Microset Construction"),
    ("bioanimator",        "BioAnimator 3D"),
    ("survival_sketch",    "Survival Sketch Lab"),
    ("anthropomorphic_st", "Anthropomorphic Storyteller"),
    ("toy_soldier",        "Toy Soldier War"),
    ("anime_ai",           "Anime AI"),
    ("disney",             "Disney Dreamweaver"),
    ("blocky",             "Blocky-Verse"),
    ("paleodoc",           "Paleodoc 3D"),
    ("cat_story",          "Realistic Cat"),
    ("none",               "No Persona"),
]

TONES = [
    ("fun",         "Vui"),
    ("serious",     "Nghiêm"),
    ("dramatic",    "Drama"),
    ("warm",        "Ấm"),
    ("villain",     "Villain"),
    ("inspiring",   "Truyền cảm"),
    ("nostalgic",   "Hoài niệm"),
    ("mysterious",  "Bí ẩn"),
    ("epic",        "Hoành tráng"),
    ("sarcastic",   "Mỉa mai"),
    ("calm",        "Bình yên"),
    ("intense",     "Gay cấn"),
]

VOICE_REGIONS = [
    ("mien_bac",   "Bắc"),
    ("mien_nam",   "Nam"),
    ("mien_tay",   "Tây"),
    ("mien_trung", "Trung"),
]

# D9: Camera Techniques (based on VEO 3.0 Reshoot Motion Types)
CAMERA_TECHNIQUES = [
    ("forward",             "🎥 Tiến tới (Forward)"),
    ("backward",            "🔙 Lùi lại (Backward)"),
    ("left_to_right",       "➡️ Trái → Phải"),
    ("right_to_left",       "⬅️ Phải → Trái"),
    ("up",                  "⬆️ Đi lên (Up)"),
    ("down",                "⬇️ Đi xuống (Down)"),
    ("dolly_zoom_out",      "🌀 Dolly In + Zoom Out (Vertigo)"),
    ("dolly_zoom_in",       "🔄 Dolly Out + Zoom In"),
    ("stationary",          "📌 Cố định (Stationary)"),
    ("pan_left",            "↩️ Cố định + Pan Trái"),
    ("pan_right",           "↪️ Cố định + Pan Phải"),
    ("tilt_up",             "🔼 Cố định + Tilt Lên"),
    ("tilt_down",           "🔽 Cố định + Tilt Xuống"),
    ("push_forward",        "📍 Cố định + Push Forward"),
    ("pull_backward",       "📍 Cố định + Pull Backward"),
]

# D6 → D3 auto-mapping
PERSONA_TO_STYLE = {
    "mythos":             "documentary",
    "chronicle":          "realistic",
    "microset":           "miniature",
    "bioanimator":        "scientific",
    "survival_sketch":    "sketch",
    "anthropomorphic_st": "3d_pixar",
    "toy_soldier":        "miniature",
    "anime_ai":           "anime",
    "disney":             "disney_3d",
    "blocky":             "minecraft",
    "paleodoc":           "photorealistic",
    "cat_story":          "photorealistic",
}

# D1 → D2 auto-mapping
CATEGORY_TO_STRUCTURE = {
    "health":        "pmcs",
    "entertainment": "3act",
    "family":        "conflict_tips",
    "tips":          "conflict_tips",
    "fashion":       "silent_review",
}

# D1 → D4 auto-mapping
CATEGORY_TO_CHARACTER = {
    "health":          "mixed",
    "entertainment":   "human",
    "family":          "human",
    "anthropomorphic": "anthropomorphic",
    "animal":          "animal",
    "diy":             "toy",
}

# D1 → D3 auto-mapping (R3b: family→realistic)
CATEGORY_TO_STYLE = {
    "family": "realistic",
}

# D5 → D7 auto-mapping
AUDIENCE_TO_TONE = {
    "kids":   "fun",
    "teens":  "fun",
    "adults": "serious",
    "family": "warm",
}

# D0 → D9 auto-mapping: Project Type → Suggested camera techniques
PROJECT_TYPE_TO_CAMERA = {
    "animation":      ["forward", "pan_left", "pan_right"],
    "action":         ["forward", "backward", "dolly_zoom_out"],
    "documentary":    ["stationary", "pan_left", "pan_right"],
    "philosophy":     ["stationary", "tilt_up"],
    "slideshow":      ["left_to_right", "stationary"],
    "storytelling":   ["forward", "pan_left", "stationary"],
    "comedy":         ["dolly_zoom_out", "forward"],
    "music_video":    ["dolly_zoom_out", "dolly_zoom_in", "left_to_right"],
    "tutorial":       ["stationary", "tilt_down"],
    "product_review": ["forward", "stationary", "dolly_zoom_out"],
}

# Video model display names
VIDEO_MODELS = [
    "Veo 3.1 - Fast",
    "Veo 3.1 - Fast [LP]",
    "Veo 3.1 - Quality",
    "Veo 2 - Fast",
    "Veo 2 - Quality",
]

# Image model display → API
IMAGE_MODELS = [
    ("🔥 Nano Banana Pro", "GEM_PIX_2"),
    ("🔥 Nano Banana 2",   "NARWHAL"),
    ("Imagen 4",            "IMAGEN_3_5"),
]


# ═══════════════════════════════════════════════════════════════════
# CheckableComboBox: Multi-select dropdown with checkboxes
# ═══════════════════════════════════════════════════════════════════

from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import QEvent


class CheckableComboBox(QComboBox):
    """QComboBox with checkboxes for multi-select."""

    selection_changed = Signal(list)  # [selected data values]

    def __init__(self, max_select: int = 3, parent=None):
        super().__init__(parent)
        self._max_select = max_select
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setText("---")
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._model.itemChanged.connect(self._on_item_changed)
        self.view().pressed.connect(self._handle_press)
        # Prevent dropdown from closing on click
        self.view().viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            return True  # Swallow release to keep dropdown open
        return super().eventFilter(obj, event)

    def addCheckItem(self, text: str, data=None):
        item = QStandardItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        item.setData(data, Qt.ItemDataRole.UserRole)
        self._model.appendRow(item)

    def _handle_press(self, index):
        item = self._model.itemFromIndex(index)
        if not item:
            return
        checked = item.checkState() == Qt.CheckState.Checked
        if checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            # Check max limit
            if len(self.get_selected()) >= self._max_select:
                return  # Silently ignore
            item.setCheckState(Qt.CheckState.Checked)

    def _on_item_changed(self, item):
        selected = self.get_selected()
        # Update display text
        labels = []
        for i in range(self._model.rowCount()):
            it = self._model.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                labels.append(it.text())
        self.setCurrentText(", ".join(labels) if labels else "---")
        self.setEditText(", ".join(labels) if labels else "---")
        self.selection_changed.emit(selected)

    def get_selected(self) -> list:
        """Return list of selected data values."""
        result = []
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def set_selected_by_data(self, data_values: list):
        """Programmatically check items by data value."""
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            val = item.data(Qt.ItemDataRole.UserRole)
            item.setCheckState(
                Qt.CheckState.Checked if val in data_values
                else Qt.CheckState.Unchecked
            )


# ═══════════════════════════════════════════════════════════════════
# SetupMatrixPanel: Main panel
# ═══════════════════════════════════════════════════════════════════

class SetupMatrixPanel(QFrame):
    """Setup Matrix panel replacing the old sidebar.

    Contains:
      - 🎯 CONTENT: 8 dimension rows (D1-D8)
      - ⚙️ PRODUCTION: Image/Video/Output settings

    Emits: config_changed(dict) when any setting changes.
    """

    config_changed = Signal(dict)
    pipeline_mode_changed = Signal(str)  # "text_only" or "full_production"
    image_library_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(Theme.SIDEBAR_WIDTH)
        self.setObjectName("sidebarPanel")

        # Main layout (no scroll — matches SidebarBase)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Color header bar (matches GenerationTabBase._create_sidebar) ──
        self._mode_header = QFrame()
        self._mode_header.setFixedHeight(32)
        self._mode_header.setStyleSheet(f"background-color: {Theme.GREEN};")
        mode_layout = QHBoxLayout(self._mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        self._mode_title = QLabel(t("project_builder.title"))
        self._mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        mode_layout.addWidget(self._mode_title)
        mode_layout.addStretch()
        outer.addWidget(self._mode_header)

        # ── Scrollable body ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Thin overlay-style scrollbar so it doesn't cover the right border
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 4px;
                margin: 2px 4px 2px 0px;
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Theme.SURFACE2};
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {Theme.OVERLAY0};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(
            Theme.SIDEBAR_PADDING, Theme.SIDEBAR_PADDING,
            Theme.SIDEBAR_PADDING, Theme.SIDEBAR_PADDING
        )
        self._layout.setSpacing(Theme.SIDEBAR_SPACING)

        self._create_content_section()
        self._create_production_section()
        self._layout.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ── Content Section ──────────────────────────────────────

    def _create_section_label(self, text: str) -> QLabel:
        """Create a section label (matches SidebarBase._create_section_label)."""
        label = QLabel(text)
        label.setStyleSheet(f"""
            color: {Theme.SUBTEXT0};
            font-size: 11px;
            padding-top: 8px;
            padding-bottom: 2px;
        """)
        self._layout.addWidget(label)
        return label

    def _separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {Theme.BORDER};")
        sep.setMaximumHeight(1)
        self._layout.addWidget(sep)

    def _create_content_section(self):

        def _dim_combo(label_text, options, on_change=None, multi=False, max_select=3):
            """Create stacked label + full-width combo (SidebarBase pattern)."""
            self._create_section_label(label_text)

            if multi:
                combo = CheckableComboBox(max_select=max_select)
                for oid, olabel in options:
                    combo.addCheckItem(olabel, oid)
                # QComboBox auto-selects index 0 when items are added — reset
                combo.setCurrentIndex(-1)
                combo.lineEdit().setText("---")
            else:
                combo = QComboBox()
                combo.addItem("---", None)  # Placeholder — no pre-selection
                for oid, olabel in options:
                    combo.addItem(olabel, oid)

            self._layout.addWidget(combo)

            if on_change:
                if multi:
                    combo.selection_changed.connect(on_change)
                else:
                    combo.currentIndexChanged.connect(on_change)
            else:
                if multi:
                    combo.selection_changed.connect(lambda sel: self._emit_config())
                else:
                    combo.currentIndexChanged.connect(lambda: self._emit_config())

            return combo

        # ═══ Pipeline Mode (master toggle) ═══
        self._create_section_label("⚙️ Pipeline Mode")
        self._pipeline_mode = QComboBox()
        self._pipeline_mode.addItem("📝 Prompt Text Only", "text_only")
        self._pipeline_mode.addItem("🎬 Full Production", "full_production")
        self._pipeline_mode.setMinimumHeight(34)
        self._pipeline_mode.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 4px;
                padding: 4px 8px; font-size: 12px; font-weight: bold;
            }}
        """)
        self._pipeline_mode.currentIndexChanged.connect(self._on_pipeline_mode_changed)
        self._layout.addWidget(self._pipeline_mode)

        # ── Shared styles ──
        section_style = f"""
            color: {Theme.SUBTEXT0};
            font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
            padding: 8px 0 2px 0; border: none;
        """
        cb_style = f"""
            QCheckBox {{ color: {Theme.TEXT}; font-size: 11px; }}
            QRadioButton {{ color: {Theme.TEXT}; font-size: 11px; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 3px;
                border: 1px solid {Theme.BORDER};
                background-color: {Theme.SURFACE0};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.GREEN};
                border-color: {Theme.GREEN};
            }}
            QRadioButton::indicator {{
                width: 16px; height: 16px; border-radius: 8px;
                border: 1px solid {Theme.BORDER};
                background-color: {Theme.SURFACE0};
            }}
            QRadioButton::indicator:checked {{
                background-color: {Theme.GREEN};
                border-color: {Theme.GREEN};
            }}
        """

        # ═══════════════════════════════════════
        # GROUP 1: 📦 DỰ ÁN
        # ═══════════════════════════════════════
        self._separator()
        grp1_label = QLabel("📦 DỰ ÁN")
        grp1_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold; border: none; padding: 2px 0;")
        self._layout.addWidget(grp1_label)

        # Project Type
        self.d0_project_type = _dim_combo("🎬 Project Type", PROJECT_TYPES,
                                          self._on_project_type_changed)

        # Shared spinbox style
        spin_style = f"""
            QSpinBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 4px;
                padding: 4px 8px; font-weight: bold;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                border: none; width: 16px;
            }}
            QSpinBox:disabled {{
                color: {Theme.SURFACE2};
            }}
        """

        # ── Mutually exclusive radios: Đơn / Đa kịch bản / Chia tập ──
        from PySide6.QtWidgets import QButtonGroup, QRadioButton

        # Hidden default radio for "neither" state
        self._single_radio = QRadioButton("📝 Đơn")
        self._single_radio.setChecked(True)
        self._single_radio.setStyleSheet(cb_style)
        self._single_radio.setToolTip("1 kịch bản duy nhất, không chia tập")
        self._single_radio.toggled.connect(self._on_structure_radio_changed)
        self._layout.addWidget(self._single_radio)

        # Row 1: Đa kịch bản + video count
        multi_row = QHBoxLayout()
        multi_row.setSpacing(6)

        self._multi_idea = QRadioButton("🎲 Đa kịch bản")
        self._multi_idea.setChecked(False)
        self._multi_idea.setStyleSheet(cb_style)
        self._multi_idea.setToolTip(
            "AI tạo N kịch bản/ý tưởng KHÁC NHAU từ cùng 1 chủ đề"
        )
        self._multi_idea.toggled.connect(self._on_structure_radio_changed)
        multi_row.addWidget(self._multi_idea)

        self._video_count = QSpinBox()
        self._video_count.setRange(1, 100)
        self._video_count.setValue(1)
        self._video_count.setSuffix(" video")
        self._video_count.setEnabled(False)
        self._video_count.setMinimumHeight(34)
        self._video_count.setStyleSheet(spin_style)
        self._video_count.setToolTip("Số kịch bản khác nhau cần tạo")
        self._video_count.valueChanged.connect(lambda: self._emit_config())
        multi_row.addWidget(self._video_count)

        self._layout.addLayout(multi_row)

        # Row 2: Chia tập + episode count
        ep_row = QHBoxLayout()
        ep_row.setSpacing(6)

        self._episode_enabled = QRadioButton("📺 Chia tập")
        self._episode_enabled.setChecked(False)
        self._episode_enabled.setStyleSheet(cb_style)
        self._episode_enabled.setToolTip(
            "AI chia 1 kịch bản dài thành N tập riêng biệt\n"
            "Nhân vật được dùng chung giữa các tập (chỉ tạo 1 lần)"
        )
        self._episode_enabled.toggled.connect(self._on_structure_radio_changed)
        ep_row.addWidget(self._episode_enabled)

        self._episode_count = QSpinBox()
        self._episode_count.setRange(2, 20)
        self._episode_count.setValue(3)
        self._episode_count.setSuffix(" tập")
        self._episode_count.setEnabled(False)
        self._episode_count.setMinimumHeight(34)
        self._episode_count.setStyleSheet(spin_style)
        self._episode_count.setToolTip("Số tập cần chia")
        self._episode_count.valueChanged.connect(lambda: self._emit_config())
        ep_row.addWidget(self._episode_count)

        self._layout.addLayout(ep_row)

        # QButtonGroup ensures mutual exclusion automatically
        self._structure_group = QButtonGroup(self)
        self._structure_group.addButton(self._single_radio, 0)
        self._structure_group.addButton(self._multi_idea, 1)
        self._structure_group.addButton(self._episode_enabled, 2)

        # ── Row 3: Có lời thoại ──
        self._voice_enabled = QCheckBox("🗣️ Có lời thoại")
        self._voice_enabled.setChecked(True)
        self._voice_enabled.setStyleSheet(cb_style)
        self._voice_enabled.setToolTip(
            "Bật: Video có lời thoại, thuyết minh, hoặc voice-over\n"
            "Tắt: Video chỉ có hình ảnh/âm nhạc, không có giọng nói"
        )
        self._voice_enabled.stateChanged.connect(lambda: self._emit_config())
        self._layout.addWidget(self._voice_enabled)

        # ── Row 4: Auto Confirm ──
        self._auto_confirm = QCheckBox("⚡ Auto Confirm")
        self._auto_confirm.setChecked(False)
        self._auto_confirm.setStyleSheet(cb_style)
        self._auto_confirm.setToolTip(
            "Bật: Tự động Confirm & Next qua mỗi stage (không cần bấm thủ công)\n"
            "Tắt: Dừng lại để user review trước khi Confirm"
        )
        self._auto_confirm.stateChanged.connect(lambda: self._emit_config())
        self._layout.addWidget(self._auto_confirm)

        # ═══════════════════════════════════════
        # GROUP 2: ⏱️ THỜI LƯỢNG
        # ═══════════════════════════════════════
        self._separator()
        grp2_label = QLabel("⏱️ THỜI LƯỢNG")
        grp2_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold; border: none; padding: 2px 0;")
        self._layout.addWidget(grp2_label)

        # Total video duration (main input)
        self._target_duration = QLineEdit()
        self._target_duration.setPlaceholderText("Tổng: 1:30 / 90s / 1:00:00")
        self._target_duration.setMinimumHeight(34)
        self._target_duration.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 4px;
                padding: 0 8px; font-size: 13px; font-weight: bold;
            }}
            QLineEdit:focus {{ border: 1px solid {Theme.GREEN}; }}
        """)
        self._target_duration.setToolTip(
            "Tổng độ dài video mong muốn:\n"
            "• HH:MM:SS (1:00:00 = 1 giờ)\n"
            "• MM:SS (1:30 = 1 phút 30 giây)\n"
            "• Số giây (90s hoặc 90)"
        )
        self._target_duration.textChanged.connect(self._on_target_duration_changed)
        self._layout.addWidget(self._target_duration)

        # Clip duration
        clip_row = QHBoxLayout()
        clip_row.setSpacing(6)
        clip_lbl = QLabel("Mỗi clip:")
        clip_lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
        clip_row.addWidget(clip_lbl)

        self._clip_duration = QComboBox()
        for d in CLIP_DURATIONS:
            self._clip_duration.addItem(f"{d}s", d)
        self._clip_duration.setCurrentIndex(1)  # 8s default
        self._clip_duration.setMinimumHeight(34)
        self._clip_duration.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 4px;
                padding: 4px 8px; font-weight: bold;
            }}
        """)
        self._clip_duration.currentIndexChanged.connect(self._update_duration_estimate)
        clip_row.addWidget(self._clip_duration)
        self._layout.addLayout(clip_row)

        # Hidden spinbox for scene count value
        self._scene_count = QSpinBox()
        self._scene_count.setRange(1, 999)
        self._scene_count.setValue(8)
        self._scene_count.setVisible(False)
        self._layout.addWidget(self._scene_count)

        # Auto-calculated result
        self._duration_label = QLabel()
        self._duration_label.setStyleSheet(f"""
            color: {Theme.GREEN}; font-size: 12px; font-weight: bold;
            padding: 4px 8px; border: 1px solid {Theme.BORDER}; border-radius: 4px;
            background-color: {Theme.SURFACE1};
        """)
        self._layout.addWidget(self._duration_label)
        self._update_duration_estimate()

        # Placeholder for _full_prod_sidebar (compat)
        self._full_prod_sidebar = QWidget()
        self._full_prod_sidebar.setVisible(False)
        self._layout.addWidget(self._full_prod_sidebar)

        # ═══ Detail Mode: Auto / Manual ═══
        detail_header = QHBoxLayout()
        detail_header.setSpacing(6)
        detail_label = QLabel("📋 CHI TIẾT NỘI DUNG")
        detail_label.setStyleSheet(f"""
            color: {Theme.SUBTEXT0};
            font-size: 11px; text-transform: uppercase;
            padding: 2px 0; border: none;
        """)
        detail_header.addWidget(detail_label)
        detail_header.addStretch()

        self._detail_mode = QComboBox()
        self._detail_mode.addItem("🤖 Auto", "auto")
        self._detail_mode.addItem("✋ Thủ công", "manual")
        self._detail_mode.setFixedHeight(26)
        self._detail_mode.setMinimumWidth(90)
        self._detail_mode.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 4px;
                padding: 2px 6px; font-size: 12px; font-weight: bold;
            }}
        """)
        self._detail_mode.currentIndexChanged.connect(self._on_detail_mode_changed)
        detail_header.addWidget(self._detail_mode)
        self._layout.addLayout(detail_header)

        # All 8 dimensions — stacked label/combo, full width
        self.d1_category  = _dim_combo(t("project_builder.sidebar.category"), CATEGORIES,
                                       self._on_category_changed, multi=True, max_select=3)
        self.d2_structure = _dim_combo(t("project_builder.sidebar.structure"), STRUCTURES)
        self.d3_style     = _dim_combo(t("project_builder.sidebar.visual_style"), VISUAL_STYLES)
        self.d4_character = _dim_combo(t("project_builder.sidebar.character"), CHARACTER_TYPES)
        self.d5_audience  = _dim_combo(t("project_builder.sidebar.audience"), AUDIENCES, self._on_audience_changed)
        self.d6_persona   = _dim_combo(t("project_builder.sidebar.persona"), PERSONAS, self._on_persona_changed)
        self.d7_tone      = _dim_combo(t("project_builder.sidebar.tone"), TONES)
        self.d8_voice     = _dim_combo(t("project_builder.sidebar.voice_region"), VOICE_REGIONS,
                                       multi=True, max_select=4)
        self.d9_camera    = _dim_combo("🎬 Camera Technique", CAMERA_TECHNIQUES,
                                       multi=True, max_select=4)

        # Wrap D1-D9 in a container for Auto/Manual toggle
        # Each _dim_combo adds 2 widgets (label + combo) = 18 widgets total (9 dims)
        self._dims_container = QWidget()
        dims_layout = QVBoxLayout(self._dims_container)
        dims_layout.setContentsMargins(0, 0, 0, 0)
        dims_layout.setSpacing(0)
        # Move last 18 widgets from self._layout → dims_layout
        widgets_to_move = []
        for _ in range(18):  # 9 combos × 2 (label + combo)
            item = self._layout.takeAt(self._layout.count() - 1)
            if item and item.widget():
                widgets_to_move.append(item.widget())
        for w in reversed(widgets_to_move):
            dims_layout.addWidget(w)

        # Default: Auto → hide dimensions
        self._dims_container.setVisible(False)
        self._layout.addWidget(self._dims_container)

    # ── Production Section ────────────────────────────────────

    def _create_production_section(self):
        self._separator()

        # Collapsible production header
        prod_header = QPushButton(f"{t('project_builder.production.header')} ▼")
        prod_header.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold; "
            f"background: transparent; border: none; text-align: left; "
            f"padding: 6px 0 2px 0;"
        )
        prod_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layout.addWidget(prod_header)

        # Container for production content
        self._prod_container = QWidget()
        prod_layout = QVBoxLayout(self._prod_container)
        prod_layout.setContentsMargins(0, 0, 0, 0)
        prod_layout.setSpacing(4)
        self._layout.addWidget(self._prod_container)

        def _toggle_production():
            vis = self._prod_container.isVisible()
            self._prod_container.setVisible(not vis)
            prod_header.setText(f"{t('project_builder.production.header')} ▶" if vis else f"{t('project_builder.production.header')} ▼")

        prod_header.clicked.connect(_toggle_production)

        lbl_style = f"color: {Theme.SUBTEXT0}; font-size: 11px; padding-top: 6px; padding-bottom: 1px;"
        combo_style = f"""
            QComboBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 4px;
                padding: 4px 8px; font-size: 12px; font-weight: bold;
            }}
        """
        input_style = f"""
            QLineEdit {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 4px;
                padding: 4px 8px; font-size: 12px; font-weight: bold;
            }}
            QLineEdit:focus {{ border: 1px solid {Theme.GREEN}; }}
        """

        # ── Output Folder ──
        lbl = QLabel(t("project_builder.production.output_folder"))
        lbl.setStyleSheet(lbl_style)
        prod_layout.addWidget(lbl)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(4)
        self.output_folder = QLineEdit()
        self.output_folder.setPlaceholderText(t("project_sidebar.output_placeholder"))
        self.output_folder.setMinimumHeight(34)
        self.output_folder.setStyleSheet(input_style)
        folder_row.addWidget(self.output_folder)

        browse_btn = QPushButton("📂 Chọn")
        browse_btn.setFixedHeight(34)
        browse_btn.setMinimumWidth(60)
        browse_btn.setProperty("variant", "secondary")
        browse_btn.setToolTip(t("project_builder.production.browse"))
        browse_btn.clicked.connect(self._browse_output)
        folder_row.addWidget(browse_btn)
        prod_layout.addLayout(folder_row)

        # ── 📐 Tỷ lệ khung hình ──
        lbl = QLabel("📐 Tỷ lệ khung hình")
        lbl.setStyleSheet(lbl_style)
        prod_layout.addWidget(lbl)
        self.video_aspect = QComboBox()
        self.video_aspect.addItems(["16:9 (Ngang)", "9:16 (Dọc)"])
        self.video_aspect.setMinimumHeight(34)
        self.video_aspect.setStyleSheet(combo_style)
        prod_layout.addWidget(self.video_aspect)

        # Hidden image_aspect synced from video_aspect
        self.image_aspect = QComboBox()
        self.image_aspect.addItems([t("project_sidebar.landscape"), t("project_sidebar.portrait")])
        self.image_aspect.setVisible(False)
        prod_layout.addWidget(self.image_aspect)
        self.video_aspect.currentIndexChanged.connect(
            lambda idx: self.image_aspect.setCurrentIndex(idx)
        )

        # ── 🖼️ Image Model / Quality ──
        lbl = QLabel("🖼️ Ảnh — Model / Chất lượng")
        lbl.setStyleSheet(lbl_style)
        prod_layout.addWidget(lbl)
        self.image_model = QComboBox()
        for display, api_key in IMAGE_MODELS:
            self.image_model.addItem(display, api_key)
        self.image_model.setMinimumHeight(34)
        self.image_model.setStyleSheet(combo_style)
        prod_layout.addWidget(self.image_model)
        self.image_quality = QComboBox()
        self.image_quality.addItems(["1k", "2k", "4k"])
        self.image_quality.setCurrentText("2k")
        self.image_quality.setMinimumHeight(34)
        self.image_quality.setStyleSheet(combo_style)
        prod_layout.addWidget(self.image_quality)

        # ── 🎬 Video Model / Quality ──
        lbl = QLabel("🎬 Video — Model / Chất lượng")
        lbl.setStyleSheet(lbl_style)
        prod_layout.addWidget(lbl)
        self.video_model = QComboBox()
        self.video_model.addItems(VIDEO_MODELS)
        self.video_model.setMinimumHeight(34)
        self.video_model.setStyleSheet(combo_style)
        prod_layout.addWidget(self.video_model)
        self.video_quality = QComboBox()
        self.video_quality.addItems(["720p", "1080p", "4K"])
        self.video_quality.setCurrentText("720p")
        self.video_quality.setMinimumHeight(34)
        self.video_quality.setStyleSheet(combo_style)
        prod_layout.addWidget(self.video_quality)

        # ── 📂 Image Library ──
        self.image_library_btn = QPushButton(t("sidebar.image_library"))
        self.image_library_btn.setFixedHeight(34)
        self.image_library_btn.setProperty("variant", "secondary")
        self.image_library_btn.clicked.connect(lambda: self.image_library_clicked.emit())
        prod_layout.addWidget(self.image_library_btn)

        # Hidden compat fields
        self.image_outputs = QSpinBox()
        self.image_outputs.setRange(1, 4)
        self.image_outputs.setValue(4)
        self.image_outputs.setVisible(False)
        prod_layout.addWidget(self.image_outputs)

        self.image_count = QSpinBox()
        self.image_count.setRange(1, 50)
        self.image_count.setValue(10)
        self.image_count.setVisible(False)
        prod_layout.addWidget(self.image_count)

        self.video_count = QSpinBox()
        self.video_count.setRange(1, 50)
        self.video_count.setValue(8)
        self.video_count.setVisible(False)
        prod_layout.addWidget(self.video_count)

        self.video_outputs = QSpinBox()
        self.video_outputs.setRange(1, 4)
        self.video_outputs.setValue(4)
        self.video_outputs.setVisible(False)
        prod_layout.addWidget(self.video_outputs)

        # ── Load defaults from AppSettings ──
        try:
            from config.settings import get_settings
            s = get_settings()
            if s:
                _vm = getattr(s, 'default_model', '')
                idx = self.video_model.findText(_vm)
                if idx >= 0:
                    self.video_model.setCurrentIndex(idx)
                _vq = getattr(s, 'default_download_quality', '720p')
                idx = self.video_quality.findText(_vq)
                if idx >= 0:
                    self.video_quality.setCurrentIndex(idx)
                _ar = getattr(s, 'default_aspect_ratio', 'LANDSCAPE')
                self.video_aspect.setCurrentText("9:16" if "PORTRAIT" in _ar.upper() else "16:9")
                self.image_aspect.setCurrentText(
                    t("project_sidebar.portrait") if "PORTRAIT" in _ar.upper()
                    else t("project_sidebar.landscape")
                )
                _oc = getattr(s, 'default_output_count', 4)
                self.image_outputs.setValue(min(max(_oc, 1), 4))
                self.video_outputs.setValue(min(max(_oc, 1), 4))
                _im = getattr(s, 'default_image_model', '')
                idx = self.image_model.findText(_im)
                if idx >= 0:
                    self.image_model.setCurrentIndex(idx)
                _iq = getattr(s, 'default_image_quality', '1k')
                idx = self.image_quality.findText(_iq)
                if idx >= 0:
                    self.image_quality.setCurrentIndex(idx)
                if s.output_folder:
                    self.output_folder.setText(s.output_folder)
        except Exception:
            pass


    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, t("project_builder.production.select_folder"))
        if folder:
            self.output_folder.setText(folder)

    # ── Inter-dimension Logic ─────────────────────────────────

    def _auto_select_combo(self, combo: QComboBox, data_value: str):
        """Auto-select a QComboBox item by its data value."""
        idx = combo.findData(data_value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _on_pipeline_mode_changed(self, index: int):
        """Toggle visibility of Full Production controls."""
        mode = self._pipeline_mode.currentData() or "text_only"
        is_full = mode == "full_production"
        # Show/hide Full Production-specific sidebar controls
        self._full_prod_sidebar.setVisible(is_full)
        # Sync header color with workspace mode
        header_color = Theme.BLUE if is_full else Theme.GREEN
        self._mode_header.setStyleSheet(f"background-color: {header_color};")
        self.pipeline_mode_changed.emit(mode)
        self._emit_config()

    def _on_detail_mode_changed(self, index: int):
        """Toggle visibility of 8 dimension combos (Auto=hidden, Manual=shown)."""
        mode = self._detail_mode.currentData() or "auto"
        self._dims_container.setVisible(mode == "manual")
        self._emit_config()

    def _on_structure_radio_changed(self, checked: bool):
        """Handle radio group change: Đơn / Đa kịch bản / Chia tập.
        
        QButtonGroup handles mutual exclusion automatically.
        We just update spinner enable states.
        """
        self._video_count.setEnabled(self._multi_idea.isChecked())
        self._episode_count.setEnabled(self._episode_enabled.isChecked())
        self._emit_config()

    def _on_project_type_changed(self, index: int):
        """Auto-set voice, structure, style, tone based on project type."""
        pt = self.d0_project_type.currentData()
        if not pt:
            return
        # Voice toggle based on project type
        NO_VOICE_TYPES = {"video_silent", "slideshow", "music_video"}
        self._voice_enabled.setChecked(pt not in NO_VOICE_TYPES)
        # Auto-suggest structure
        TYPE_TO_STRUCTURE = {
            "animation":    "3act",
            "action":       "3act",
            "documentary":  "narrative",
            "philosophy":   "minimal",
            "slideshow":    "montage",
            "storytelling": "narrative",
            "comedy":       "3act",
            "music_video":  "montage",
            "tutorial":     "pmcs",
            "product_review": "before_after",
        }
        if pt in TYPE_TO_STRUCTURE:
            self._auto_select_combo(self.d2_structure, TYPE_TO_STRUCTURE[pt])
        # Auto-suggest tone
        TYPE_TO_TONE = {
            "philosophy":   "calm",
            "action":       "intense",
            "comedy":       "fun",
            "documentary":  "serious",
            "storytelling": "warm",
        }
        if pt in TYPE_TO_TONE:
            self._auto_select_combo(self.d7_tone, TYPE_TO_TONE[pt])
        # D0 → D9: auto-suggest camera technique
        if pt in PROJECT_TYPE_TO_CAMERA:
            self.d9_camera.set_selected_by_data(PROJECT_TYPE_TO_CAMERA[pt])
        self._emit_config()

    def _on_target_duration_changed(self, *args):
        """Parse target duration and auto-calculate scene count (live).
        
        Accepts: HH:MM:SS, MM:SS, Ns (e.g. 90s), or raw number (seconds).
        Scene count = ceil(total_duration / clip_duration)
        """
        if getattr(self, '_updating_duration', False):
            return
        self._updating_duration = True
        try:
            import math
            text = self._target_duration.text().strip()
            if not text:
                self._scene_count.setValue(1)
                self._do_update_label()
                return

            total_s = 0
            text_clean = text.lower().replace("s", "").strip()
            if ":" in text_clean:
                parts = text_clean.split(":")
                if len(parts) == 3:  # HH:MM:SS
                    total_s = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                elif len(parts) == 2:  # MM:SS
                    total_s = int(parts[0]) * 60 + int(parts[1])
            else:
                total_s = int(float(text_clean))

            if total_s <= 0:
                return
            clip_s = self._clip_duration.currentData() or 8
            needed = math.ceil(total_s / clip_s)
            needed = max(1, min(needed, 999))
            self._scene_count.setValue(needed)
            self._do_update_label()
        except (ValueError, IndexError):
            pass
        finally:
            self._updating_duration = False

    def _update_duration_estimate(self, *args):
        """Recalculate when clip duration changes."""
        if getattr(self, '_updating_duration', False):
            return
        # If target text exists, recalculate scene count from it
        if hasattr(self, '_target_duration') and self._target_duration.text().strip():
            self._on_target_duration_changed()
        else:
            self._do_update_label()

    def _do_update_label(self):
        """Display auto-calculated scene count and actual duration."""
        clip_s = self._clip_duration.currentData() or 8
        scenes = self._scene_count.value()
        actual_s = clip_s * scenes

        hours = actual_s // 3600
        mins = (actual_s % 3600) // 60
        secs = actual_s % 60
        if hours > 0:
            time_str = f"{hours}:{mins:02d}:{secs:02d}"
        else:
            time_str = f"{mins:02d}:{secs:02d}"

        text = f"📊 {scenes} phân cảnh × {clip_s}s = {time_str}"
        self._duration_label.setText(text)
        self._emit_config()

    def _on_category_changed(self, selected: list):
        """R1-R4, R7: Category → Structure + Character + Style + Hybrid."""
        if selected:
            primary = selected[0]
            # R1-R4: auto-suggest structure
            if primary in CATEGORY_TO_STRUCTURE:
                self._auto_select_combo(self.d2_structure, CATEGORY_TO_STRUCTURE[primary])
            # D1 → D4: auto-suggest character
            if primary in CATEGORY_TO_CHARACTER:
                self._auto_select_combo(self.d4_character, CATEGORY_TO_CHARACTER[primary])
            # R3b: D1 → D3: auto-suggest style (e.g. family→realistic)
            if primary in CATEGORY_TO_STYLE:
                self._auto_select_combo(self.d3_style, CATEGORY_TO_STYLE[primary])
        self._emit_config()

    def _on_persona_changed(self, index: int):
        """R5: Persona → Visual Style."""
        persona_id = self.d6_persona.currentData()
        if persona_id and persona_id in PERSONA_TO_STYLE:
            self._auto_select_combo(self.d3_style, PERSONA_TO_STYLE[persona_id])
        self._emit_config()

    def _on_audience_changed(self, index: int):
        """R6: Audience → Tone."""
        audience_id = self.d5_audience.currentData()
        if audience_id and audience_id in AUDIENCE_TO_TONE:
            self._auto_select_combo(self.d7_tone, AUDIENCE_TO_TONE[audience_id])
        self._emit_config()

    def _emit_config(self, *args):
        if not hasattr(self, 'image_aspect'):
            return  # Still initializing — production section not built yet
        self.config_changed.emit(self.get_config())

    # ── Public API ─────────────────────────────────────────────

    def get_config(self) -> dict:
        """Get full matrix configuration."""
        vid_aspect = "LANDSCAPE" if "16:9" in self.video_aspect.currentText() else "PORTRAIT"
        img_aspect = vid_aspect  # Synced — both use same sidebar control

        return {
            # Pipeline mode
            "pipeline_mode":     self._pipeline_mode.currentData() or "text_only",
            "detail_mode":       self._detail_mode.currentData() or "auto",
            # Project type & duration
            "project_type":      self.d0_project_type.currentData(),
            "voice_enabled":     self._voice_enabled.isChecked(),
            "auto_confirm":      self._auto_confirm.isChecked(),
            "multi_idea":        self._multi_idea.isChecked(),
            "episode_enabled":   self._episode_enabled.isChecked(),
            "episode_count":     self._episode_count.value() if self._episode_enabled.isChecked() else 1,
            "clip_duration":     self._clip_duration.currentData() or 8,
            "scene_count":       self._scene_count.value(),
            "video_count":       self._video_count.value(),
            "target_duration":   self._target_duration.text().strip(),
            "estimated_duration": (self._clip_duration.currentData() or 8) * self._scene_count.value(),
            # Content dimensions
            "category":  self.d1_category.get_selected(),        # list (multi)
            "structure": [self.d2_structure.currentData()] if self.d2_structure.currentData() else [],
            "style":     [self.d3_style.currentData()] if self.d3_style.currentData() else [],
            "character": [self.d4_character.currentData()] if self.d4_character.currentData() else [],
            "audience":  [self.d5_audience.currentData()] if self.d5_audience.currentData() else [],
            "persona":   self.d6_persona.currentData(),
            "tone":      [self.d7_tone.currentData()] if self.d7_tone.currentData() else [],
            "voice":     self.d8_voice.get_selected(),           # list (multi)
            "camera_technique": self.d9_camera.get_selected(),    # list (multi)
            # Production
            "output_folder":     self.output_folder.text(),
            "image_model":       self.image_model.currentData(),
            "image_aspect":      img_aspect,
            "image_count":       self.image_count.value(),
            "image_quality":     self.image_quality.currentText(),
            "image_outputs":     self.image_outputs.value(),
            "video_model":       self.video_model.currentText(),
            "video_quality":     self.video_quality.currentText(),
            "video_aspect":      vid_aspect,
            "video_count":       self.video_count.value(),
            "video_outputs":     self.video_outputs.value(),
        }

    def set_from_tab_columns(self, columns: list) -> int:
        """Auto-update sidebar dropdowns from tab-separated column values.
        
        Smart detection: each column is matched against ALL dimension keyword
        tables. The unmatched column (longest text) = topic name.
        
        Returns:
            Index of the topic column (0-based), or 0 if no tab data.
        """
        if len(columns) < 2:
            return 0

        # ── Keyword → (dimension, data_id) mappings ──
        KEYWORD_MAP = {
            # ═══ Visual Style (d3) ═══
            "hoạt hình": ("style", "3d_pixar"),
            "3d": ("style", "3d_pixar"),
            "pixar": ("style", "3d_pixar"),
            "thực tế": ("style", "realistic"),
            "người thật": ("style", "realistic"),
            "realistic": ("style", "realistic"),
            "anime": ("style", "anime"),
            "disney": ("style", "disney_3d"),
            "sketch": ("style", "sketch"),
            "vẽ tay": ("style", "sketch"),
            "phim tài liệu": ("style", "documentary"),
            "minecraft": ("style", "minecraft"),
            "photo": ("style", "photorealistic"),
            "miniature": ("style", "miniature"),
            "mô hình": ("style", "miniature"),
            "người que": ("style", "stickfigure"),
            "stick figure": ("style", "stickfigure"),
            "người gỗ": ("style", "stickfigure"),
            "watercolor": ("style", "watercolor"),
            "màu nước": ("style", "watercolor"),
            # ═══ Category (d1) ═══
            # Health
            "sức khỏe": ("category", "health"),
            "health": ("category", "health"),
            "thực phẩm": ("category", "health"),
            "thuốc": ("category", "health"),
            "y tế": ("category", "health"),
            "bệnh": ("category", "health"),
            # Entertainment
            "giải trí": ("category", "entertainment"),
            "entertainment": ("category", "entertainment"),
            "hài hước": ("category", "entertainment"),
            # Family
            "gia đình": ("category", "family"),
            "family": ("category", "family"),
            # Fashion
            "thời trang": ("category", "fashion"),
            "fashion": ("category", "fashion"),
            "làm đẹp": ("category", "fashion"),
            # Tips
            "mẹo vặt": ("category", "tips"),
            # Others
            "nhân hóa": ("category", "anthropomorphic"),
            "lịch sử": ("category", "history"),
            "diy": ("category", "diy"),
            "tự làm": ("category", "diy"),
            "gaming": ("category", "gaming"),
            "động vật": ("category", "animal"),
            # NEW categories
            "nấu ăn": ("category", "cooking"),
            "cooking": ("category", "cooking"),
            "ẩm thực": ("category", "cooking"),
            "bếp": ("category", "cooking"),
            "tài chính": ("category", "finance"),
            "finance": ("category", "finance"),
            "tiền": ("category", "finance"),
            "đầu tư": ("category", "finance"),
            "tiết kiệm": ("category", "finance"),
            "phật giáo": ("category", "religion"),
            "phật": ("category", "religion"),
            "tôn giáo": ("category", "religion"),
            "chùa": ("category", "religion"),
            "thiền": ("category", "religion"),
            "kinh phật": ("category", "religion"),
            "nhà chùa": ("category", "religion"),
            "xã hội": ("category", "social"),
            "social": ("category", "social"),
            "cộng đồng": ("category", "social"),
            "đời sống": ("category", "life"),
            "cuộc sống": ("category", "life"),
            "life": ("category", "life"),
            "sống": ("category", "life"),
            "giáo dục": ("category", "education"),
            "education": ("category", "education"),
            "học tập": ("category", "education"),
            "dạy học": ("category", "education"),
            "tâm linh": ("category", "spiritual"),
            "phong thủy": ("category", "spiritual"),
            "tử vi": ("category", "spiritual"),
            "kinh nghiệm": ("category", "experience"),
            "experience": ("category", "experience"),
            "bí quyết": ("category", "experience"),
            "chia sẻ": ("category", "experience"),
            "tâm lý": ("category", "psychology"),
            "psychology": ("category", "psychology"),
            "cảm xúc": ("category", "psychology"),
            "khoa học": ("category", "science"),
            # ═══ Tone (d7) ═══
            "vui": ("tone", "fun"),
            "hài": ("tone", "fun"),
            "nghiêm": ("tone", "serious"),
            "chỉ dạy": ("tone", "serious"),
            "dạy bảo": ("tone", "serious"),
            "tôn trọng": ("tone", "warm"),
            "tranh cải": ("tone", "dramatic"),
            "tranh cãi": ("tone", "dramatic"),
            "drama": ("tone", "dramatic"),
            "kịch tính": ("tone", "dramatic"),
            "ấm áp": ("tone", "warm"),
            "tình cảm": ("tone", "warm"),
            "villain": ("tone", "villain"),
            "phản diện": ("tone", "villain"),
            "truyền cảm hứng": ("tone", "inspiring"),
            "truyền cảm": ("tone", "inspiring"),
            "inspiring": ("tone", "inspiring"),
            "hoài niệm": ("tone", "nostalgic"),
            "nostalgic": ("tone", "nostalgic"),
            "nhớ": ("tone", "nostalgic"),
            "xưa": ("tone", "nostalgic"),
            # ═══ Character type (d4) ═══
            "con người": ("character", "human"),
            "người": ("character", "human"),
            "thú": ("character", "animal"),
            "đồ chơi": ("character", "toy"),
            "mix": ("character", "mixed"),
            "hỗn hợp": ("character", "mixed"),
            # ═══ Audience (d5) ═══
            "cháu": ("audience", "kids"),
            "trẻ em": ("audience", "kids"),
            "trẻ nhỏ": ("audience", "kids"),
            "nàng dâu": ("audience", "adults"),
            "con dâu": ("audience", "adults"),
            "con trai": ("audience", "adults"),
            "thiếu niên": ("audience", "teens"),
            "người lớn": ("audience", "adults"),
            "mọi lứa tuổi": ("audience", "family"),
            "vợ chồng": ("audience", "adults"),
            "học sinh": ("audience", "teens"),
            "phật tử": ("audience", "adults"),
            "chị em": ("audience", "adults"),
            # ═══ Character / Persona roles (→ category) ═══
            "mẹ chồng": ("category", "family"),
            "bố chồng": ("category", "family"),
            "mẹ vợ": ("category", "family"),
            "bố vợ": ("category", "family"),
            "bà": ("category", "family"),
            "ông": ("category", "family"),
            "ông bà": ("category", "family"),
            "sư thầy": ("category", "religion"),
            "thầy chùa": ("category", "religion"),
            "hòa thượng": ("category", "religion"),
            # ═══ Camera Technique (d9) ═══
            "tiến tới": ("camera_technique", "forward"),
            "forward": ("camera_technique", "forward"),
            "lùi lại": ("camera_technique", "backward"),
            "backward": ("camera_technique", "backward"),
            "cố định": ("camera_technique", "stationary"),
            "stationary": ("camera_technique", "stationary"),
            "pan": ("camera_technique", "pan_left"),
            "tilt": ("camera_technique", "tilt_up"),
            "dolly": ("camera_technique", "dolly_zoom_out"),
            "vertigo": ("camera_technique", "dolly_zoom_out"),
            "zoom": ("camera_technique", "dolly_zoom_in"),
        }

        def _match(text):
            """Match text against keyword map."""
            t = text.strip().lower()
            if t in KEYWORD_MAP:
                return KEYWORD_MAP[t]
            for kw, result in KEYWORD_MAP.items():
                if kw in t or t in kw:
                    return result
            return None

        # ── Phase 1: Detect which column is the topic ──
        col_matches = []
        for i, col in enumerate(columns):
            match = _match(col)
            col_matches.append((i, match))
            log.debug(f"[SetupMatrix] Col {i}: '{col.strip()}' → {match}")

        unmatched = [(i, columns[i]) for i, m in col_matches if m is None]

        if len(unmatched) == 1:
            topic_idx = unmatched[0][0]
        elif len(unmatched) > 1:
            # Multiple unmatched → longest text is the topic
            topic_idx = max(unmatched, key=lambda x: len(x[1].strip()))[0]
        else:
            topic_idx = 0

        # ── Phase 2: Apply matched dimensions to sidebar ──
        applied = set()
        for i, match in col_matches:
            if i == topic_idx or match is None:
                continue
            dim, data_id = match
            if dim in applied:
                continue
            applied.add(dim)
            if dim == "style":
                self._auto_select_combo(self.d3_style, data_id)
            elif dim == "category":
                self.d1_category.set_selected_by_data([data_id])
                self._on_category_changed([data_id])
            elif dim == "tone":
                self._auto_select_combo(self.d7_tone, data_id)
            elif dim == "camera_technique":
                self.d9_camera.set_selected_by_data([data_id])
            elif dim == "character":
                self._auto_select_combo(self.d4_character, data_id)
            elif dim == "audience":
                self._auto_select_combo(self.d5_audience, data_id)

        log.info(
            f"[SetupMatrix] Applied {len(applied)} dimensions: "
            f"{applied}, topic_idx={topic_idx}"
        )

        if applied:
            self._emit_config()

        return topic_idx
