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
    QScrollArea, QFileDialog, QLineEdit,
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
    ("pmcs",          "PMCS"),
    ("3act",          "3-Act"),
    ("conflict_tips", "Tips"),
    ("silent_review", "Silent"),
    ("pov_styling",   "POV"),
    ("narrative",     "Narrative"),
    ("custom",        "Custom"),
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
]

CHARACTER_TYPES = [
    ("anthropomorphic", "Nhân hóa"),
    ("human",           "Người"),
    ("animal",          "Động vật"),
    ("toy",             "Đồ chơi"),
    ("mixed",           "Mix"),
]

AUDIENCES = [
    ("kids",   "Kids"),
    ("teens",  "Teens"),
    ("adults", "Adults"),
    ("family", "Family"),
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
    ("fun",       "Vui"),
    ("serious",   "Nghiêm"),
    ("dramatic",  "Drama"),
    ("warm",      "Ấm"),
    ("villain",   "Villain"),
    ("inspiring", "Truyền cảm"),
    ("nostalgic", "Hoài niệm"),
]

VOICE_REGIONS = [
    ("mien_bac",   "Bắc"),
    ("mien_nam",   "Nam"),
    ("mien_tay",   "Tây"),
    ("mien_trung", "Trung"),
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
        self.lineEdit().setPlaceholderText("Select...")
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
        self.setCurrentText(", ".join(labels) if labels else "Select...")
        self.setEditText(", ".join(labels) if labels else "Select...")
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

    def __init__(self, parent=None):
        super().__init__(parent)
        # Match SidebarBase: fixed width, same background
        self.setFixedWidth(260)
        self.setStyleSheet(f"background-color: {Theme.SURFACE0};")

        # Main layout (no scroll — matches SidebarBase)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Color header bar (matches GenerationTabBase._create_sidebar) ──
        mode_header = QFrame()
        mode_header.setFixedHeight(32)
        mode_header.setStyleSheet(f"background-color: {Theme.GREEN};")
        mode_layout = QHBoxLayout(mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        mode_title = QLabel("🎯 PROJECT BUILDER")
        mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        mode_layout.addStretch()
        outer.addWidget(mode_header)

        # ── Scrollable body ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)

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
            else:
                combo = QComboBox()
                for oid, olabel in options:
                    combo.addItem(olabel, oid)

            combo.setMinimumHeight(32)
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

        # All 8 dimensions — stacked label/combo, full width
        self.d1_category  = _dim_combo("Category", CATEGORIES,
                                       self._on_category_changed, multi=True, max_select=3)
        self.d2_structure = _dim_combo("Structure", STRUCTURES)
        self.d3_style     = _dim_combo("Visual Style", VISUAL_STYLES)
        self.d4_character = _dim_combo("Character", CHARACTER_TYPES)
        self.d5_audience  = _dim_combo("Audience", AUDIENCES, self._on_audience_changed)
        self.d6_persona   = _dim_combo("Persona", PERSONAS, self._on_persona_changed)
        self.d7_tone      = _dim_combo("Tone", TONES)
        self.d8_voice     = _dim_combo("Voice Region", VOICE_REGIONS,
                                       multi=True, max_select=4)

    # ── Production Section ────────────────────────────────────

    def _create_production_section(self):
        self._separator()

        # Collapsible production header
        prod_header = QPushButton("── ⚙️ PRODUCTION ── ▼")
        prod_header.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold; "
            f"background: transparent; border: none; text-align: left; "
            f"padding: 6px 0 2px 0; cursor: pointer;"
        )
        prod_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layout.addWidget(prod_header)

        # Container for all production content
        self._prod_container = QWidget()
        prod_layout = QVBoxLayout(self._prod_container)
        prod_layout.setContentsMargins(0, 0, 0, 0)
        prod_layout.setSpacing(4)
        self._layout.addWidget(self._prod_container)

        def _toggle_production():
            vis = self._prod_container.isVisible()
            self._prod_container.setVisible(not vis)
            prod_header.setText("── ⚙️ PRODUCTION ── ▶" if vis else "── ⚙️ PRODUCTION ── ▼")

        prod_header.clicked.connect(_toggle_production)

        # Style helpers (match SidebarBase)
        def _section_lbl(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding-top: 8px; padding-bottom: 2px;")
            prod_layout.addWidget(lbl)

        # ── Output Folder ──
        _section_lbl("📂 Output Folder")
        self.output_folder = QLineEdit()
        self.output_folder.setPlaceholderText("D:/Projects/VEO (or drag folder)")
        self.output_folder.setMinimumHeight(32)
        prod_layout.addWidget(self.output_folder)

        browse_btn = QPushButton("📁 Browse")
        browse_btn.setMinimumHeight(28)
        browse_btn.setProperty("variant", "secondary")
        browse_btn.clicked.connect(self._browse_output)
        prod_layout.addWidget(browse_btn)

        # Auto-populate from settings
        try:
            from config.settings import get_settings
            s = get_settings()
            if s and s.output_folder:
                self.output_folder.setText(s.output_folder)
        except Exception:
            pass

        # ── Image Settings ──
        _section_lbl("🖼️ Image Model")
        self.image_model = QComboBox()
        for display, api_key in IMAGE_MODELS:
            self.image_model.addItem(display, api_key)
        self.image_model.setMinimumHeight(32)
        prod_layout.addWidget(self.image_model)

        _section_lbl("Image Aspect Ratio")
        self.image_aspect = QComboBox()
        self.image_aspect.addItems(["16:9 (Landscape)", "9:16 (Portrait)"])
        self.image_aspect.setMinimumHeight(32)
        prod_layout.addWidget(self.image_aspect)

        _section_lbl("Image Count")
        self.image_count = QSpinBox()
        self.image_count.setRange(1, 50)
        self.image_count.setValue(10)
        self.image_count.setMinimumHeight(32)
        prod_layout.addWidget(self.image_count)

        _section_lbl("Image Quality")
        self.image_quality = QComboBox()
        self.image_quality.addItems(["1k", "2k", "4k"])
        self.image_quality.setCurrentText("2k")
        self.image_quality.setMinimumHeight(32)
        prod_layout.addWidget(self.image_quality)

        _section_lbl("Outputs/Request")
        self.image_outputs = QSpinBox()
        self.image_outputs.setRange(1, 4)
        self.image_outputs.setValue(4)
        self.image_outputs.setMinimumHeight(32)
        prod_layout.addWidget(self.image_outputs)

        # ── Video Settings ──
        _section_lbl("🎬 Video Model")
        self.video_model = QComboBox()
        self.video_model.addItems(VIDEO_MODELS)
        self.video_model.setMinimumHeight(32)
        prod_layout.addWidget(self.video_model)

        _section_lbl("Video Quality")
        self.video_quality = QComboBox()
        self.video_quality.addItems(["720p", "1080p", "4K"])
        self.video_quality.setCurrentText("1080p")
        self.video_quality.setMinimumHeight(32)
        prod_layout.addWidget(self.video_quality)

        _section_lbl("Video Aspect Ratio")
        self.video_aspect = QComboBox()
        self.video_aspect.addItems(["16:9", "9:16"])
        self.video_aspect.setMinimumHeight(32)
        prod_layout.addWidget(self.video_aspect)

        _section_lbl("Video Count")
        self.video_count = QSpinBox()
        self.video_count.setRange(1, 50)
        self.video_count.setValue(8)
        self.video_count.setMinimumHeight(32)
        prod_layout.addWidget(self.video_count)

        _section_lbl("Video Outputs/Prompt")
        self.video_outputs = QSpinBox()
        self.video_outputs.setRange(1, 4)
        self.video_outputs.setValue(4)
        self.video_outputs.setMinimumHeight(32)
        prod_layout.addWidget(self.video_outputs)



    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)

    # ── Inter-dimension Logic ─────────────────────────────────

    def _auto_select_combo(self, combo: QComboBox, data_value: str):
        """Auto-select a QComboBox item by its data value."""
        idx = combo.findData(data_value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

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
        self.config_changed.emit(self.get_config())

    # ── Public API ─────────────────────────────────────────────

    def get_config(self) -> dict:
        """Get full matrix configuration."""
        img_aspect = "LANDSCAPE" if "Landscape" in self.image_aspect.currentText() else "PORTRAIT"
        vid_aspect = "LANDSCAPE" if "16:9" in self.video_aspect.currentText() else "PORTRAIT"

        return {
            # Content dimensions
            "category":  self.d1_category.get_selected(),        # list (multi)
            "structure": [self.d2_structure.currentData()] if self.d2_structure.currentData() else [],
            "style":     [self.d3_style.currentData()] if self.d3_style.currentData() else [],
            "character": [self.d4_character.currentData()] if self.d4_character.currentData() else [],
            "audience":  [self.d5_audience.currentData()] if self.d5_audience.currentData() else [],
            "persona":   self.d6_persona.currentData(),
            "tone":      [self.d7_tone.currentData()] if self.d7_tone.currentData() else [],
            "voice":     self.d8_voice.get_selected(),           # list (multi)
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
