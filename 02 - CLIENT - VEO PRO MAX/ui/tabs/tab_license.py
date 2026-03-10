"""
VEO Pro Max - Tab 08: License - PySide6 Version

Reference: TAB_08_LICENSE.md
Wired to security/license_client.py + services/permissions.py backend.
"""

from typing import Optional
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QGridLayout, QApplication
)
from PySide6.QtCore import Qt, Signal, QTimer

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from config.i18n import t


class TabLicense(QWidget):
    """License tab (PySide6).
    
    Layout:
    - Dynamic status banner (TRIAL/PREMIUM/TESTER/EXPIRED)
    - License activation form
    - Pricing tiers display
    - Real-time usage statistics
    """
    
    # Signals
    license_activated = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self._limit_labels = {}   # Track limit value labels for refresh
        self._stat_labels = {}    # Track stat value labels for refresh
        self._banner_text = None  # Banner text label for refresh
        self._banner_frame = None # Banner frame for color change
        
        try:
            self._setup_ui()
            self._bind_real_data()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"TabLicense init failed: {e}", exc_info=True)
            # Fallback: show error instead of black screen
            if not self.layout():
                from PySide6.QtWidgets import QVBoxLayout
                QVBoxLayout(self)
            err_label = QLabel(f"⚠️ License tab error: {e}")
            err_label.setStyleSheet(f"color: {Theme.RED}; font-size: 14px; padding: 20px;")
            self.layout().addWidget(err_label)
        
        # Auto-refresh every 60s (for stats/limits)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(60000)
        self._refresh_timer.timeout.connect(self._refresh_data)
        self._refresh_timer.start()
        
        # Countdown timer (1s interval for live d:h:m:s)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._update_countdown)
        self._expires_dt = None  # datetime of expiry
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Trial banner
        banner = self._create_trial_banner()
        layout.addWidget(banner)
        
        # License activation (hidden for Lifetime users)
        self._activation_widget = self._create_activation_section()
        layout.addWidget(self._activation_widget)
        
        # Pricing tiers (stored for rebuild after activation)
        self._pricing_tiers_widget = self._create_pricing_tiers()
        layout.addWidget(self._pricing_tiers_widget)
        
        # Usage stats
        stats = self._create_usage_stats()
        layout.addWidget(stats)
    
    def _create_trial_banner(self) -> QWidget:
        """Create dynamic status banner — shows TRIAL/PREMIUM/TESTER/EXPIRED."""
        section = QFrame()
        section.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        main_layout = QVBoxLayout(section)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Dynamic banner header
        self._banner_frame = QFrame()
        self._banner_frame.setFixedHeight(40)
        self._banner_frame.setStyleSheet(f"background-color: {Theme.YELLOW};")
        banner_layout = QHBoxLayout(self._banner_frame)
        banner_layout.setContentsMargins(16, 0, 16, 0)
        
        self._banner_text = QLabel(t("license.banner.trial"))
        self._banner_text.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold; font-size: 14px;")
        banner_layout.addWidget(self._banner_text)
        banner_layout.addStretch()
        
        main_layout.addWidget(self._banner_frame)
        
        # Limits info
        info_frame = QFrame()
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(4)
        
        limit_defs = [
            ("accounts", t("license.limits.accounts")),
            ("threads", t("license.limits.threads")),
            ("workers", "Max OpPP/Acc"),
            ("daily", t("license.limits.daily")),
            ("batch", t("license.limits.batch")),
        ]
        
        for key, label in limit_defs:
            row = QHBoxLayout()
            label_widget = QLabel(f"{label}:")
            label_widget.setFixedWidth(200)
            label_widget.setStyleSheet(f"color: {Theme.SUBTEXT0};")
            row.addWidget(label_widget)
            
            value_widget = QLabel("--")
            value_widget.setStyleSheet(f"color: {Theme.TEXT};")
            self._limit_labels[key] = value_widget
            row.addWidget(value_widget)
            row.addStretch()
            info_layout.addLayout(row)
        
        # Machine ID row
        machine_row = QHBoxLayout()
        machine_label = QLabel(t("license.machine_id"))
        machine_label.setFixedWidth(200)
        machine_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        machine_row.addWidget(machine_label)
        
        self.machine_id_entry = QLineEdit("--")
        self.machine_id_entry.setReadOnly(True)
        self.machine_id_entry.setMinimumWidth(420)
        self.machine_id_entry.setFixedHeight(32)
        self.machine_id_entry.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; font-family: monospace; font-size: 12px; padding: 4px 8px;"
        )
        machine_row.addWidget(self.machine_id_entry)
        
        copy_btn = QPushButton(t("license.copy"))
        copy_btn.setFixedSize(100, 32)
        copy_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; font-size: 12px; font-weight: bold;")
        copy_btn.clicked.connect(self._on_copy_machine_id)
        self._copy_btn = copy_btn
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
        
        title = QLabel(t("license.activate_title"))
        title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Key input
        input_layout = QHBoxLayout()
        
        self.key_entry = QLineEdit()
        self.key_entry.setPlaceholderText(t("license.activate_placeholder"))
        self.key_entry.setMinimumHeight(36)
        input_layout.addWidget(self.key_entry)
        
        self._activate_btn = QPushButton(t("license.activate"))
        self._activate_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
        self._activate_btn.clicked.connect(self._on_activate)
        input_layout.addWidget(self._activate_btn)
        
        layout.addLayout(input_layout)
        
        # Status label
        self._activation_status = QLabel("")
        self._activation_status.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        layout.addWidget(self._activation_status)
        
        return section
    
    def _create_pricing_tiers(self) -> QWidget:
        """Create pricing tiers display."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setSpacing(8)
        
        # Check first-buy eligibility (matches popup logic)
        self._is_first_buy = self._check_first_buy()
        
        # Get dynamic trial days from tier template
        _tdl = 3  # fallback
        try:
            from security._encrypted_api_keys import set_runtime_keys
            set_runtime_keys()
            from security.firebase_rest_client import FirebaseRESTClient
            _rest = FirebaseRESTClient()
            _defs = _rest.read_tier_defaults()
            _tdl = _defs.get('TRIAL', {}).get('days', 3) or 3
        except Exception:
            pass
        
        # Read TRIAL limits from permissions (server-synced values)
        _trial_accounts = 1
        _trial_threads = 2
        _trial_daily = 100
        try:
            from services.permissions import PermissionsSystem, Role
            trial_lim = PermissionsSystem.ROLE_LIMITS[Role.TRIAL]
            _trial_accounts = trial_lim.max_accounts
            _trial_threads = trial_lim.max_foremen
            _trial_daily = trial_lim.daily_generation_limit
        except Exception:
            pass
        
        # (tier_key, name, price, features, color)
        # Luồng = số tác vụ xử lý đồng thời (tránh dùng từ 'Workers' trên UI)
        tiers = [
            ("FREE", t("license.tiers.free"), t("license.free"), [
                t("license.features.trial_days").format(days=_tdl),
                t("license.features.one_account").format(count=_trial_accounts),
                t("license.features.two_threads").format(count=_trial_threads),
                t("license.features.gen_per_day").format(count=_trial_daily),
                t("license.features.upscale_720"),
                t("license.features.no_continuation"),
                t("license.features.no_ai_prompt"),
                t("license.features.no_priority"),
            ], Theme.SUBTEXT0),
            ("1M", t("license.tiers.1m"), "300,000đ", [
                t("license.features.unlimited_accounts"),
                t("license.features.unlimited_threads"),
                t("license.features.unlimited_gen"),
                t("license.features.continuation"),
                t("license.features.anti_detect"),
                t("license.features.smart_hide"),
                t("license.features.auto_upscale"),
                t("license.features.ai_prompt"),
            ], Theme.PEACH),
            ("3M", t("license.tiers.3m"), "500,000đ", [
                t("license.features.save_44"),
                t("license.features.unlimited_accounts"),
                t("license.features.unlimited_threads"),
                t("license.features.unlimited_gen"),
                t("license.features.continuation"),
                t("license.features.anti_detect_hide"),
                t("license.features.auto_upscale"),
                t("license.features.ai_prompt"),
            ], Theme.BLUE),
            ("6M", t("license.tiers.6m"), "800,000đ", [
                t("license.features.save_56"),
                t("license.features.unlimited_accounts"),
                t("license.features.unlimited_threads"),
                t("license.features.unlimited_gen"),
                t("license.features.continuation"),
                t("license.features.anti_detect_hide"),
                t("license.features.priority_support"),
                t("license.features.ai_prompt"),
            ], Theme.GREEN),
            ("1Y", t("license.tiers.1y"), "1,200,000đ", [
                t("license.features.save_67"),
                t("license.features.unlimited_accounts"),
                t("license.features.unlimited_threads"),
                t("license.features.unlimited_gen"),
                t("license.features.continuation"),
                t("license.features.full_security"),
                t("license.features.priority_support"),
                t("license.features.best_value"),
                t("license.features.ai_prompt"),
            ], Theme.PURPLE),
            ("LIFETIME", t("license.tiers.lifetime"), "3,000,000đ", [
                t("license.features.best_deal"),
                t("license.features.no_expiry"),
                t("license.features.lifetime_updates"),
                t("license.features.unlimited_everything"),
                t("license.features.continuation"),
                t("license.features.full_security"),
                t("license.features.priority_vip"),
                t("license.features.all_new_features"),
                t("license.features.ai_prompt"),
            ], Theme.YELLOW),
        ]
        
        # Get active tier for button labels
        active_tier = self._get_active_tier()
        
        for tier_key, name, price, features, color in tiers:
            card = self._create_tier_card(tier_key, name, price, features, color, active_tier)
            layout.addWidget(card)
        
        return container
    
    def _create_tier_card(self, tier_key: str, name: str, price: str, features: list, color: str, active_tier: str = "") -> QWidget:
        """Create a pricing tier card with dynamic button."""
        card = QFrame()
        card.setFixedWidth(200)
        card.setStyleSheet(f"background-color: {Theme.SURFACE2}; border-radius: 0px;")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"background-color: {color}; border-radius: 0px;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(8, 8, 8, 8)
        
        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold; font-size: 16px;")
        name_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(name_label)
        
        # First-buy pricing: show discounted price + strikethrough original
        from ui.popups.license_popup import TIER_FIRST_BUY
        if tier_key != "FREE" and self._is_first_buy and tier_key in TIER_FIRST_BUY:
            fb = TIER_FIRST_BUY[tier_key]
            discount_label = QLabel(fb["price"])
            discount_label.setStyleSheet(f"color: {Theme.CRUST}; font-size: 14px; font-weight: bold;")
            discount_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(discount_label)
            
            orig_label = QLabel(f"<s>{price}</s>  {t('license.first_buy_badge')}")
            orig_label.setStyleSheet(f"color: {Theme.CRUST}; font-size: 9px;")
            orig_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(orig_label)
        else:
            price_label = QLabel(price)
            price_label.setStyleSheet(f"color: {Theme.CRUST}; font-size: 13px; font-weight: bold;")
            price_label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(price_label)
        
        layout.addWidget(header)
        
        for feature in features:
            feat_label = QLabel(f"✓ {feature}")
            feat_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold;")
            feat_label.setContentsMargins(10, 2, 8, 2)
            layout.addWidget(feat_label)
        
        layout.addStretch()
        
        # Dynamic button based on active tier
        if tier_key == "FREE":
            # Show trial status button if currently on trial
            is_trial = False
            try:
                if self.controller and hasattr(self.controller, '_permissions'):
                    is_trial = self.controller._permissions.is_trial()
            except Exception:
                pass
            if is_trial:
                status_btn = QPushButton(t("license.using_trial"))
                status_btn.setStyleSheet(
                    f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                    f"border-radius: 0px; font-weight: bold; font-size: 14px;"
                )
                status_btn.setEnabled(False)
                status_btn.setFixedHeight(60)
                status_btn.setContentsMargins(8, 0, 8, 0)
                layout.addWidget(status_btn)
            elif active_tier == "LIFETIME":
                # Lifetime user: FREE tier is included
                status_btn = QPushButton(t("license_extra.included"))
                status_btn.setStyleSheet(
                    f"background-color: {Theme.SURFACE1}; color: {Theme.SUBTEXT0}; "
                    f"border-radius: 0px; font-weight: bold; font-size: 14px;"
                )
                status_btn.setEnabled(False)
                status_btn.setFixedHeight(60)
                status_btn.setContentsMargins(8, 0, 8, 0)
                layout.addWidget(status_btn)
        elif tier_key != "FREE":
            if active_tier == "LIFETIME":
                # Lifetime user: all tiers are included
                if tier_key == "LIFETIME":
                    select_btn = QPushButton("✅ " + t("license.current_plan"))
                    select_btn.setStyleSheet(
                        f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                        f"border-radius: 0px; font-weight: bold; font-size: 14px;"
                    )
                else:
                    select_btn = QPushButton(t("license_extra.included"))
                    select_btn.setStyleSheet(
                        f"background-color: {Theme.SURFACE1}; color: {Theme.SUBTEXT0}; "
                        f"border-radius: 0px; font-weight: bold; font-size: 14px;"
                    )
                select_btn.setEnabled(False)
            elif active_tier:
                # Has active license → can always buy more to stack time
                # Lifetime: "Nâng cấp" (one-time), others: "Mua thêm" (stackable)
                btn_text = t("license.upgrade") if tier_key == "LIFETIME" else t("license.buy_more")
                select_btn = QPushButton(btn_text)
                select_btn.setStyleSheet(f"background-color: {color}; color: {Theme.CRUST}; border-radius: 0px; font-weight: bold; font-size: 14px;")
                select_btn.clicked.connect(lambda checked, k=tier_key: self._on_select_tier(k))
            else:
                # No active license → normal select
                select_btn = QPushButton(t("license.select"))
                select_btn.setStyleSheet(f"background-color: {color}; color: {Theme.CRUST}; border-radius: 0px; font-weight: bold; font-size: 14px;")
                select_btn.clicked.connect(lambda checked, k=tier_key: self._on_select_tier(k))
            select_btn.setFixedHeight(60)
            select_btn.setContentsMargins(8, 0, 8, 0)
            layout.addWidget(select_btn)
        
        return card
    
    def _on_select_tier(self, tier_key: str):
        """Open purchase popup with the selected tier pre-highlighted."""
        from ui.popups.license_popup import LicenseRequiredDialog
        dlg = LicenseRequiredDialog(
            parent=self,
            controller=self.controller,
            selected_tier=tier_key,
            force_exit=False,
        )
        result = dlg.exec()
        if result == dlg.DialogCode.Accepted:
            self._refresh_data()
    
    def _get_active_tier(self) -> str:
        """Get current active license tier code (mapped to pricing card keys)."""
        if not self.controller:
            return ""
        try:
            lc = self.controller._license_client
            if lc and lc._license_data:
                raw_tier = lc._license_data.get("tier", "")
                # Map stored tier codes → pricing card tier_keys
                tier_map = {
                    "LT": "LIFETIME",
                    "1M": "1M",
                    "3M": "3M",
                    "6M": "6M",
                    "1Y": "1Y",
                }
                return tier_map.get(raw_tier, raw_tier)
        except Exception:
            pass
        return ""
    
    def _check_first_buy(self) -> bool:
        """Check if this machine has no previous purchases (first-buy eligible).
        
        Logic:
        1. If user already has active PREMIUM/TESTER license → NOT first buy
        2. Query Firebase _customers/{MID} for purchase_count
        3. Fallback: assume first buy only if role is TRIAL
        """
        # Quick check: if already has a paid license → definitely not first buy
        try:
            if self.controller and hasattr(self.controller, '_permissions'):
                from services.permissions import Role
                role = self.controller._permissions.role
                if role in (Role.PREMIUM, Role.TESTER):
                    return False  # Already purchased → not first buy
        except Exception:
            pass
        
        # Server check: query_customer for purchase_count
        try:
            rest_client = None
            if self.controller and hasattr(self.controller, '_license_client'):
                rest_client = getattr(self.controller._license_client, '_rest_client', None)
            if not rest_client:
                return True  # Can't check + TRIAL → assume first buy
            if hasattr(rest_client, 'query_customer'):
                from security.license_client import get_machine_id
                mid = get_machine_id()
                customer = rest_client.query_customer(mid)
                return int(customer.get('purchase_count', 0)) == 0
            return True
        except Exception:
            return True  # Error → assume first buy
    
    def _create_usage_stats(self) -> QWidget:
        """Create usage statistics section with real data bindings."""
        section = QFrame()
        section.setStyleSheet(f"background-color: {Theme.SURFACE0}; border-radius: 8px;")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        title = QLabel(t("license.usage_title"))
        title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        stats_layout = QGridLayout()
        stat_defs = [
            ("total_gen", t("license.total_gen")),
            ("today_gen", t("license.today_gen")),
            ("total_dl", t("license.total_downloads")),
            ("role", t("license.current_role")),
        ]
        
        for i, (key, label) in enumerate(stat_defs):
            row = i // 2
            col = (i % 2) * 2
            
            label_widget = QLabel(label + ":")
            label_widget.setStyleSheet(f"color: {Theme.SUBTEXT0};")
            stats_layout.addWidget(label_widget, row, col)
            
            value_widget = QLabel("--")
            value_widget.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
            stats_layout.addWidget(value_widget, row, col + 1)
            self._stat_labels[key] = value_widget
        
        layout.addLayout(stats_layout)
        
        return section
    
    def retranslate_ui(self):
        """Hot-reload: rebuild entire UI when language changes."""
        # Remove old layout — Qt won't allow a new layout if old one exists
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            # Transfer old layout to temp widget → releases self for new layout
            QWidget().setLayout(old_layout)
        
        # Reset tracked widgets
        self._limit_labels = {}
        self._stat_labels = {}
        self._banner_text = None
        self._banner_frame = None
        
        # Rebuild
        self._setup_ui()
        self._bind_real_data()
    
    # ── Data Binding ─────────────────────────────────────────────
    
    def _bind_real_data(self):
        """Bind real data from controller on first load."""
        if not self.controller:
            return
        try:
            # 3.6b: Machine ID
            if hasattr(self.controller, '_license_client'):
                mid = self.controller._license_client.machine_id
                self.machine_id_entry.setText(mid)
            
            # Refresh all dynamic data
            self._refresh_data()
        except Exception:
            pass
    
    def _refresh_data(self):
        """Refresh all dynamic data from controller."""
        if not self.controller:
            return
        
        # Hide activation section for Lifetime users
        active_tier = self._get_active_tier()
        try:
            if hasattr(self, '_activation_widget'):
                self._activation_widget.setVisible(active_tier != "LIFETIME")
        except Exception:
            pass
        
        # Rebuild pricing cards (updates first-buy status + active tier buttons)
        try:
            parent_layout = self._pricing_tiers_widget.parentWidget().layout()
            if parent_layout:
                idx = parent_layout.indexOf(self._pricing_tiers_widget)
                parent_layout.removeWidget(self._pricing_tiers_widget)
                self._pricing_tiers_widget.deleteLater()
                self._pricing_tiers_widget = self._create_pricing_tiers()
                parent_layout.insertWidget(idx, self._pricing_tiers_widget)
        except Exception:
            pass
        try:
            perm = getattr(self.controller, '_permissions', None)
            lc = getattr(self.controller, '_license_client', None)
            
            if perm:
                lim = perm.limits
                # 3.6d: Limits
                def fmt(v):
                    return "∞" if v < 0 else str(v)
                self._limit_labels.get("accounts", QLabel()).setText(fmt(lim.max_accounts))
                self._limit_labels.get("threads", QLabel()).setText(fmt(lim.max_foremen))
                self._limit_labels.get("workers", QLabel()).setText(fmt(lim.max_workers_per_account))
                self._limit_labels.get("daily", QLabel()).setText(fmt(lim.daily_generation_limit))
                self._limit_labels.get("batch", QLabel()).setText(fmt(lim.max_prompts_per_batch))
                
                # 3.6h: Dynamic banner with countdown
                role = perm.role
                from services.permissions import Role
                from datetime import datetime
                
                # Get license info from controller
                tier_name = ""
                expires_dt_str = None
                days = 0
                if hasattr(self.controller, 'get_license_status'):
                    ls = self.controller.get_license_status()
                    tier_name = ls.get('tier_name', '') or ''
                    days = ls.get('days_remaining', 0)
                    expires_dt_str = ls.get('expires_dt')
                
                # Parse expires datetime for countdown
                if expires_dt_str:
                    try:
                        self._expires_dt = datetime.fromisoformat(expires_dt_str)
                    except Exception:
                        self._expires_dt = None
                
                if role == Role.TESTER:
                    self._set_banner("🔑 ADMINISTRATOR", Theme.PURPLE)
                    self._countdown_timer.stop()
                elif role == Role.PREMIUM:
                    tier_code = ls.get('tier', '') if ls else ''
                    if tier_code == 'LT':
                        # Lifetime: no countdown
                        self._set_banner(f"♾️ {t('license.lifetime_banner')}", Theme.GREEN)
                        self._countdown_timer.stop()
                    else:
                        self._update_countdown()  # Initial update
                        self._countdown_timer.start()
                else:
                    if days > 0:
                        self._update_trial_countdown()  # Initial update
                        self._countdown_timer.start()
                    else:
                        self._set_banner(f"⏰ {t('license.trial_banner_limited')}", Theme.YELLOW)
            
            if lc:
                # 3.6c: Usage stats
                usage = lc.usage
                self._stat_labels.get("total_gen", QLabel()).setText(str(usage.total_generations))
                self._stat_labels.get("today_gen", QLabel()).setText(str(usage.today_generations))
                self._stat_labels.get("total_dl", QLabel()).setText(str(usage.total_downloads))
                
                # 3.6i: Role display
                if perm:
                    _role_display = "ADMINISTRATOR" if perm.role == Role.TESTER else perm.role.value.upper()
                    self._stat_labels.get("role", QLabel()).setText(_role_display)
                    
        except Exception:
            pass
    
    def _set_banner(self, text: str, color: str):
        """Update banner text and color."""
        if self._banner_text:
            self._banner_text.setText(text)
        if self._banner_frame:
            self._banner_frame.setStyleSheet(f"background-color: {color};")
    
    def _update_countdown(self):
        """Update banner with live countdown (called every 1s).
        
        Dispatches to trial or premium countdown based on current role.
        """
        from datetime import datetime
        
        # Detect role — dispatch to trial-specific countdown
        perm = getattr(self.controller, '_permissions', None) if self.controller else None
        if perm:
            from services.permissions import Role
            if perm.role == Role.TRIAL:
                self._update_trial_countdown()
                return
        
        if not self._expires_dt:
            return
        
        now = datetime.now()
        remaining = self._expires_dt - now
        total_secs = int(remaining.total_seconds())
        
        if total_secs <= 0:
            self._set_banner(f"❌ {t('license.expired_msg')}", Theme.RED)
            self._countdown_timer.stop()
            return
        
        days = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins = (total_secs % 3600) // 60
        secs = total_secs % 60
        
        # Get tier_name from controller
        tier_name = ""
        if self.controller and hasattr(self.controller, 'get_license_status'):
            ls = self.controller.get_license_status()
            tier_name = ls.get('tier_name', 'PREMIUM') or 'PREMIUM'
        
        exp_str = self._expires_dt.strftime('%Y-%m-%d %H:%M')
        self._set_banner(
            f"💎 {tier_name} — {t('license.remaining_time')}: {days}d {hours:02d}:{mins:02d}:{secs:02d} ({t('license.expires_on')}: {exp_str})",
            Theme.GREEN
        )
    
    def _update_trial_countdown(self):
        """Update trial banner with live countdown (called every 1s)."""
        from datetime import datetime
        if not self._expires_dt:
            return
        
        now = datetime.now()
        remaining = self._expires_dt - now
        total_secs = int(remaining.total_seconds())
        
        if total_secs <= 0:
            self._set_banner(f"❌ {t('license.trial_expired_banner')}", Theme.RED)
            self._countdown_timer.stop()
            return
        
        days = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins = (total_secs % 3600) // 60
        secs = total_secs % 60
        
        exp_str = self._expires_dt.strftime('%Y-%m-%d %H:%M')
        self._set_banner(
            f"⏰ Trial — {t('license.remaining_time')} {days}d {hours:02d}:{mins:02d}:{secs:02d} ({t('license.expires_on')}: {exp_str})",
            Theme.YELLOW
        )
    # ── Actions ──────────────────────────────────────────────────
    
    def _on_activate(self):
        """Activate license key — wired to controller.activate_license."""
        key = self.key_entry.text().strip()
        if not key:
            self._activation_status.setText(t("license_status.enter_key"))
            self._activation_status.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px;")
            return
        
        self._activation_status.setText(t("license_status.activating"))
        self._activation_status.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        
        if self.controller and hasattr(self.controller, 'activate_license'):
            result = self.controller.activate_license(key)
            if result:
                self._activation_status.setText(t("license_status.activated"))
                self._activation_status.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
                self.license_activated.emit(key)
                self.key_entry.clear()
                self._refresh_data()
            else:
                self._activation_status.setText(t("license_status.failed"))
                self._activation_status.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
        else:
            self._activation_status.setText(t("license_status.no_controller"))
    
    
    def _on_copy_machine_id(self):
        """Copy machine ID to clipboard."""
        mid = self.machine_id_entry.text()
        if mid and mid != "--":
            clipboard = QApplication.clipboard()
            clipboard.setText(mid)
            # Show feedback via main window toast if available
            main_win = self.window()
            if hasattr(main_win, 'show_toast'):
                main_win.show_toast(f"📋 Machine ID copied: {mid}", "success")
