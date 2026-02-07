"""
VEO Pro Max - Tab 08: License - PySide6 Version

Reference: TAB_08_LICENSE.md
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QGridLayout
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class TabLicense(QWidget):
    """License tab (PySide6).
    
    Layout:
    - Pricing tiers display
    - License activation form
    - Usage statistics
    - Trial countdown
    """
    
    # Signals
    license_activated = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Trial banner
        banner = self._create_trial_banner()
        layout.addWidget(banner)
        
        # License activation
        activation = self._create_activation_section()
        layout.addWidget(activation)
        
        # Pricing tiers
        tiers = self._create_pricing_tiers()
        layout.addWidget(tiers)
        
        # Usage stats
        stats = self._create_usage_stats()
        layout.addWidget(stats)
        
        layout.addStretch()
    
    def _create_trial_banner(self) -> QWidget:
        """Create trial countdown banner - matches CTK lines 46-75."""
        section = QFrame()
        section.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        main_layout = QVBoxLayout(section)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Yellow header banner
        banner = QFrame()
        banner.setFixedHeight(40)
        banner.setStyleSheet(f"background-color: {Theme.YELLOW};")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(16, 0, 16, 0)
        
        text = QLabel("⏰ TRIAL MODE - 7 Days Remaining")
        text.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold; font-size: 14px;")
        banner_layout.addWidget(text)
        banner_layout.addStretch()
        
        main_layout.addWidget(banner)
        
        # Trial limits info
        info_frame = QFrame()
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(4)
        
        limits = [
            ("Cookies", "1 / 1"),
            ("Threads", "2 / 2"),
            ("Prompts Today", "5 / 10"),
        ]
        
        for label, value in limits:
            row = QHBoxLayout()
            label_widget = QLabel(f"{label}:")
            label_widget.setFixedWidth(150)
            label_widget.setStyleSheet(f"color: {Theme.SUBTEXT0};")
            row.addWidget(label_widget)
            
            value_widget = QLabel(value)
            value_widget.setStyleSheet(f"color: {Theme.TEXT};")
            row.addWidget(value_widget)
            row.addStretch()
            
            info_layout.addLayout(row)
        
        # Machine ID row
        machine_row = QHBoxLayout()
        machine_label = QLabel("Machine ID:")
        machine_label.setFixedWidth(150)
        machine_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        machine_row.addWidget(machine_label)
        
        self.machine_id_entry = QLineEdit("A1B2-C3D4-E5F6")
        self.machine_id_entry.setReadOnly(True)
        self.machine_id_entry.setFixedWidth(200)
        self.machine_id_entry.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        machine_row.addWidget(self.machine_id_entry)
        
        copy_btn = QPushButton("📋 Copy")
        copy_btn.setFixedSize(60, 24)
        copy_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; font-size: 11px;")
        machine_row.addWidget(copy_btn)
        machine_row.addStretch()
        
        info_layout.addLayout(machine_row)
        
        main_layout.addWidget(info_frame)
        
        return section
    
    def _create_activation_section(self) -> QWidget:
        """Create license activation section."""
        section = QFrame()
        section.setStyleSheet(f"background-color: {Theme.SURFACE0}; border-radius: 8px;")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        title = QLabel("🔑 Activate License")
        title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Key input
        input_layout = QHBoxLayout()
        
        self.key_entry = QLineEdit()
        self.key_entry.setPlaceholderText("Enter your license key (XXXX-XXXX-XXXX-XXXX)")
        self.key_entry.setMinimumHeight(36)
        input_layout.addWidget(self.key_entry)
        
        activate_btn = QPushButton("Activate")
        activate_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
        activate_btn.clicked.connect(self._on_activate)
        input_layout.addWidget(activate_btn)
        
        layout.addLayout(input_layout)
        
        return section
    
    def _create_pricing_tiers(self) -> QWidget:
        """Create pricing tiers display."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setSpacing(8)
        
        # Exact tiers from CTK tab_license.py lines 128-134
        tiers = [
            ("1 Tháng", "300,000đ", ["5 Cookies", "5 Threads", "100 prompts/day"], Theme.SURFACE2),
            ("3 Tháng", "500,000đ", ["-44%/tháng", "Unlimited Cookies", "10 Threads"], Theme.BLUE),
            ("6 Tháng", "800,000đ", ["-56%/tháng", "Unlimited prompts", "Priority Support"], Theme.GREEN),
            ("1 Năm", "1,200,000đ", ["-67%/tháng", "Everything in 6 Tháng", "Best Value"], Theme.PURPLE),
            ("Vĩnh viễn", "3,000,000đ", ["BEST DEAL", "Lifetime updates", "No expiry"], Theme.YELLOW),
        ]
        
        for name, price, features, color in tiers:
            card = self._create_tier_card(name, price, features, color)
            layout.addWidget(card)
        
        return container
    
    def _create_tier_card(self, name: str, price: str, features: list, color: str) -> QWidget:
        """Create a pricing tier card - matches CTK tab_license.py._create_tier_card."""
        card = QFrame()
        card.setFixedWidth(200)
        card.setStyleSheet(f"background-color: {Theme.SURFACE2}; border-radius: 8px;")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)
        
        # Header with color background
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"background-color: {color}; border-radius: 0px;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(8, 8, 8, 8)
        
        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold; font-size: 14px;")
        name_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(name_label)
        
        price_label = QLabel(price)
        price_label.setStyleSheet(f"color: {Theme.CRUST}; font-size: 12px;")
        price_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(price_label)
        
        layout.addWidget(header)
        
        # Features
        for feature in features:
            feat_label = QLabel(f"✓ {feature}")
            feat_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
            feat_label.setContentsMargins(8, 2, 8, 2)
            layout.addWidget(feat_label)
        
        layout.addStretch()
        
        # Select button with same color as header
        select_btn = QPushButton("Select")
        select_btn.setStyleSheet(f"background-color: {color}; color: {Theme.CRUST}; border-radius: 4px;")
        select_btn.setFixedHeight(28)
        select_btn.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(select_btn)
        
        return card
    
    def _create_usage_stats(self) -> QWidget:
        """Create usage statistics section."""
        section = QFrame()
        section.setStyleSheet(f"background-color: {Theme.SURFACE0}; border-radius: 8px;")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        title = QLabel("📊 Usage Statistics")
        title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        stats_layout = QGridLayout()
        stats = [
            ("Total Generations", "1,234"),
            ("This Month", "87 / 100"),
            ("API Calls", "456"),
            ("Storage Used", "2.3 GB"),
        ]
        
        for i, (label, value) in enumerate(stats):
            row = i // 2
            col = (i % 2) * 2
            
            label_widget = QLabel(label + ":")
            label_widget.setStyleSheet(f"color: {Theme.SUBTEXT0};")
            stats_layout.addWidget(label_widget, row, col)
            
            value_widget = QLabel(value)
            value_widget.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
            stats_layout.addWidget(value_widget, row, col + 1)
        
        layout.addLayout(stats_layout)
        
        return section
    
    def _on_activate(self):
        """Activate license key."""
        key = self.key_entry.text().strip()
        if key:
            self.license_activated.emit(key)
            if self.controller and hasattr(self.controller, 'activate_license'):
                self.controller.activate_license(key)
            else:
                # TODO: Implement activate_license in AppController
                print(f"[License] Key submitted: {key[:8]}...")
