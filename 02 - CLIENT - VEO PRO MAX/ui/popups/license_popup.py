"""
VEO Pro Max - License Required Popup

Modal dialog shown when:
1. Trial expired (0 days) - after splash, blocks app
2. User clicks "Select" on pricing tier - auto-selects that tier

Contains: Machine ID, serial input, pricing tiers, request button with anti-spam token.
"""

import sys
import hashlib
import requests as http_requests
from typing import Optional
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QApplication, QSizePolicy, QWidget
)
from PySide6.QtCore import Qt, QTimer

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from config.i18n import t


# ── Tier definitions (shared) ───────────────────────────────────
TIER_DEFS = [
    {"key": "FREE",     "name": "🆓 Free",     "price": "Miễn phí",     "desc": "3 ngày dùng thử"},
    {"key": "1M",       "name": "1 Tháng",      "price": "300,000đ",    "desc": "Tất cả tính năng"},
    {"key": "3M",       "name": "3 Tháng",      "price": "500,000đ",    "desc": "~167K/tháng, -44%"},
    {"key": "6M",       "name": "6 Tháng",      "price": "800,000đ",    "desc": "~133K/tháng, -56%"},
    {"key": "1Y",       "name": "1 Năm",        "price": "1,200,000đ",  "desc": "~100K/tháng, -67%"},
    {"key": "LIFETIME", "name": "Vĩnh viễn",    "price": "3,000,000đ",  "desc": "Lifetime, BEST DEAL"},
]

# First-buy discounted prices (display + amount)
TIER_FIRST_BUY = {
    "1M":       {"price": "200,000đ",   "amount": 200000, "desc": "🎁 Ưu đãi lần đầu!"},
    "3M":       {"price": "400,000đ",   "amount": 400000, "desc": "🎁 Ưu đãi lần đầu!"},
    "6M":       {"price": "600,000đ",   "amount": 600000, "desc": "🎁 Ưu đãi lần đầu!"},
    "1Y":       {"price": "1,000,000đ", "amount": 1000000, "desc": "🎁 Ưu đãi lần đầu!"},
    "LIFETIME": {"price": "3,000,000đ", "amount": 3000000, "desc": "Lifetime, BEST DEAL"},
}

# Normal prices (amount for payment tracking)
TIER_NORMAL_AMOUNT = {
    "1M": 300000, "3M": 500000, "6M": 800000,
    "1Y": 1200000, "LIFETIME": 3000000,
}

# Color map for tier cards
TIER_COLORS = {
    "FREE": Theme.SUBTEXT0,
    "1M": Theme.PEACH,
    "3M": Theme.BLUE,
    "6M": Theme.GREEN,
    "1Y": Theme.PURPLE,
    "LIFETIME": Theme.YELLOW,
}


class LicenseRequiredDialog(QDialog):
    """Modal license popup.
    
    Args:
        controller: AppController instance (for machine ID + activate)
        selected_tier: Pre-select a tier (e.g. "3M" when clicking Select on 3-month card)
        force_exit: If True, closing dialog exits app (used at startup)
    """
    
    def __init__(
        self,
        parent=None,
        controller=None,
        selected_tier: str = "",
        force_exit: bool = False,
        license_error: str = "",
    ):
        super().__init__(parent)
        self.controller = controller
        self._force_exit = force_exit
        self._selected_tier = selected_tier
        self._license_error = license_error
        self._tier_buttons = {}  # key → QPushButton
        self._active_tier = self._get_active_tier()  # Current active tier code
        self._is_first_buy = self._check_first_buy()  # Check purchase history
        
        # Dynamic trial days from tier template
        self._trial_days = 3  # fallback
        try:
            rest = self._get_rest_client()
            if rest and hasattr(rest, 'read_tier_defaults'):
                defaults = rest.read_tier_defaults()
                trial_tmpl = defaults.get('TRIAL', {})
                if trial_tmpl.get('days', 0) > 0:
                    self._trial_days = trial_tmpl['days']
        except Exception:
            pass
        # Override FREE card desc with actual trial days
        for td in TIER_DEFS:
            if td['key'] == 'FREE':
                td['desc'] = f"{self._trial_days} ngày dùng thử"
                break
        
        self.setWindowTitle("VEO Pro Max — License")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setMinimumSize(700, 580)
        self.setModal(True)
        self.setStyleSheet(f"background-color: {Theme.BASE}; color: {Theme.TEXT};")
        
        self._setup_ui()
        
        # IP detection + rate limit tracking
        self._client_ip = self._detect_ip()
        self._send_times = []  # Track upgrade request timestamps
        
        # Pre-select tier if provided
        if selected_tier:
            self._select_tier(selected_tier)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ── Header banner — context-aware ──
        header = QFrame()
        header.setFixedHeight(44)
        
        # Determine header text and color based on error
        err = self._license_error.lower() if self._license_error else ""
        if "revoked" in err or "thu hồi" in err:
            header_text = "⛔ LICENSE ĐÃ BỊ THU HỒI"
            header_color = Theme.RED
            warn_text = "🚫 License của bạn đã bị admin thu hồi. Liên hệ admin để được hỗ trợ."
        elif "deleted" in err or "not found" in err or "xoá" in err:
            header_text = "❌ LICENSE KHÔNG TỒN TẠI"
            header_color = Theme.RED
            warn_text = t("license_popup.not_found")
        elif "expired" in err or "hết hạn" in err:
            header_text = "⏰ LICENSE ĐÃ HẾT HẠN"
            header_color = Theme.PEACH
            warn_text = "⚠️ License đã hết hạn. Gia hạn hoặc nhập key mới để tiếp tục."
        elif "machine" in err:
            header_text = "🔒 SAI MÁY"
            header_color = Theme.PURPLE
            warn_text = "⚠️ License này được kích hoạt trên máy khác. Liên hệ admin."
        elif "stale" in err or "backup" in err:
            header_text = "❌ LICENSE ĐÃ BỊ XOÁ"
            header_color = Theme.RED
            warn_text = "🚫 License đã bị xoá trên server. Nhập key mới để tiếp tục."
        elif "trial" in err or "required" in err:
            header_text = "📋 CẦN LICENSE"
            header_color = Theme.YELLOW
            warn_text = "⚠️ Bản dùng thử đã kết thúc. Nâng cấp để sử dụng đầy đủ tính năng."
        else:
            header_text = "❌ LICENSE HẾT HẠN"
            header_color = Theme.RED
            warn_text = t("license_popup.enter_serial")
        
        header.setStyleSheet(f"background-color: {header_color};")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        htxt = QLabel(header_text)
        htxt.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold; font-size: 15px;")
        hlayout.addWidget(htxt)
        hlayout.addStretch()
        layout.addWidget(header)
        
        # ── Content area ──
        content = QFrame()
        content.setStyleSheet(f"background-color: {Theme.BASE};")
        clayout = QVBoxLayout(content)
        clayout.setContentsMargins(24, 16, 24, 16)
        clayout.setSpacing(12)
        
        # Warning text — context-aware
        warn = QLabel(warn_text)
        warn.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 13px; font-weight: bold;")
        warn.setWordWrap(True)
        clayout.addWidget(warn)
        
        # ── Machine ID + Serial section ──
        id_frame = QFrame()
        id_frame.setStyleSheet(f"background-color: {Theme.SURFACE0}; border-radius: 8px;")
        id_layout = QVBoxLayout(id_frame)
        id_layout.setContentsMargins(16, 12, 16, 12)
        id_layout.setSpacing(8)
        
        # Machine ID row
        mid_row = QHBoxLayout()
        mid_label = QLabel("🆔 Machine ID:")
        mid_label.setFixedWidth(120)
        mid_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        mid_row.addWidget(mid_label)
        
        self._mid_entry = QLineEdit(self._get_machine_id())
        self._mid_entry.setReadOnly(True)
        self._mid_entry.setMinimumWidth(420)
        self._mid_entry.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"font-family: monospace; font-size: 10px; padding: 4px 8px;"
        )
        mid_row.addWidget(self._mid_entry)
        
        copy_btn = QPushButton("📋 Copy")
        copy_btn.setFixedSize(85, 28)
        copy_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; font-size: 11px;")
        copy_btn.clicked.connect(self._on_copy_mid)
        self._copy_btn = copy_btn  # Store reference for feedback
        mid_row.addWidget(copy_btn)
        mid_row.addStretch()
        id_layout.addLayout(mid_row)
        
        # Serial input row  
        serial_row = QHBoxLayout()
        serial_label = QLabel("🔑 Serial:")
        serial_label.setFixedWidth(120)
        serial_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        serial_row.addWidget(serial_label)
        
        self._serial_entry = QLineEdit()
        self._serial_entry.setPlaceholderText("XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
        self._serial_entry.setMinimumHeight(32)
        self._serial_entry.returnPressed.connect(self._on_activate)  # Enter = Activate
        serial_row.addWidget(self._serial_entry)
        
        activate_btn = QPushButton("✅ Kích hoạt")
        activate_btn.setFixedHeight(32)
        activate_btn.setStyleSheet(
            f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
            f"font-weight: bold; padding: 0 16px; border-radius: 4px;"
        )
        activate_btn.clicked.connect(self._on_activate)
        activate_btn.setDefault(True)       # Capture Enter key
        activate_btn.setAutoDefault(False)  # Don't auto-trigger accept()
        serial_row.addWidget(activate_btn)
        id_layout.addLayout(serial_row)
        
        # Status label (for serial activation only)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        self._status_label.setVisible(False)
        id_layout.addWidget(self._status_label)
        
        clayout.addWidget(id_frame)
        
        # ── Pricing tiers ──
        tier_header = QLabel("💰 BẢNG GIÁ NÂNG CẤP")
        tier_header.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 13px;")
        clayout.addWidget(tier_header)
        
        tier_container = QFrame()
        tier_layout = QHBoxLayout(tier_container)
        tier_layout.setContentsMargins(0, 0, 0, 0)
        tier_layout.setSpacing(6)
        
        for td in TIER_DEFS:
            card = self._create_tier_card(td)
            tier_layout.addWidget(card)
        
        clayout.addWidget(tier_container)
        
        # ── Customer info + Request section ──
        req_frame = QFrame()
        req_frame.setStyleSheet(f"background-color: {Theme.SURFACE0}; border-radius: 8px;")
        req_layout = QVBoxLayout(req_frame)
        req_layout.setContentsMargins(16, 12, 16, 12)
        req_layout.setSpacing(6)
        
        req_title = QLabel("📲 GỬI YÊU CẦU NÂNG CẤP")
        req_title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 12px;")
        req_layout.addWidget(req_title)
        
        # Row 1: Name (bắt buộc)
        name_row = QHBoxLayout()
        name_lbl = QLabel("👤 Họ tên: *")
        name_lbl.setFixedWidth(90)
        name_lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        name_row.addWidget(name_lbl)
        self._name_entry = QLineEdit()
        self._name_entry.setPlaceholderText("Nguyễn Văn A")
        self._name_entry.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px 8px;")
        self._name_locked = False
        # Auto-fill and LOCK if name already registered
        try:
            cn = None
            # Priority: get name from license client (same as header "Chào mừng X")
            # Already in memory — no Firebase call needed
            if self.controller and hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                if hasattr(lc, 'get_client_name'):
                    cn = (lc.get_client_name() or '').strip()
                    if cn == '***':
                        cn = ''
            # Fallback: try Firebase sources
            if not cn:
                rest_client = self._get_rest_client()
                mid = self._get_machine_id()
                if rest_client and mid:
                    # Try _upgrade_requests first (has name from previous requests)
                    req = rest_client.read_upgrade_request(mid)
                    cn = (req.get('client_name', '') if req else '').strip()
                    if cn == '***':
                        cn = ''
                    # Fallback 1: try _trials
                    if not cn:
                        trial_doc = rest_client._read_doc('_trials', mid, mid)
                        cn = ((trial_doc or {}).get('client_name', '')).strip()
                        if cn == '***':
                            cn = ''
                    # Fallback 2: try _keys (_cn from admin)
                    if not cn:
                        key_doc = rest_client._read_doc('_keys', mid, mid)
                        cn = ((key_doc or {}).get('_cn', '')).strip()
                        if cn == '***':
                            cn = ''
            if cn:
                self._name_entry.setText(cn)
                self._name_entry.setReadOnly(True)
                self._name_locked = True
                self._name_entry.setStyleSheet(
                    f"background-color: {Theme.SURFACE1}; padding: 4px 8px; "
                    f"color: {Theme.SUBTEXT0};"
                )
                self._name_entry.setToolTip("🔒 Tên đã gắn với Machine ID. Liên hệ admin để thay đổi.")
                name_lbl.setText("🔒 Họ tên:")
        except Exception:
            pass
        name_row.addWidget(self._name_entry)
        req_layout.addLayout(name_row)
        
        # Warning for first-time name entry
        if not self._name_locked:
            name_warn = QLabel("⚠️ Lưu ý: Tên chỉ nhập 1 lần. Nếu sai, liên hệ admin để đổi tên!")
            name_warn.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 10px; padding-left: 90px;")
            name_warn.setWordWrap(True)
            req_layout.addWidget(name_warn)
        
        # Row 2: Tier combo
        tier_row = QHBoxLayout()
        tier_lbl = QLabel("📦 Gói:")
        tier_lbl.setFixedWidth(90)
        tier_lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        tier_row.addWidget(tier_lbl)
        self._tier_combo = QComboBox()
        for td in TIER_DEFS:
            # Show first-buy price if eligible (paid tiers only)
            if td["key"] != "FREE" and self._is_first_buy and td["key"] in TIER_FIRST_BUY:
                display_price = TIER_FIRST_BUY[td["key"]]["price"]
            else:
                display_price = td["price"]
            self._tier_combo.addItem(f"{td['name']} — {display_price}", td["key"])
        self._tier_combo.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        tier_row.addWidget(self._tier_combo)
        req_layout.addLayout(tier_row)
        
        # Pre-select combo if tier provided
        if self._selected_tier:
            for i in range(self._tier_combo.count()):
                if self._tier_combo.itemData(i) == self._selected_tier:
                    self._tier_combo.setCurrentIndex(i)
                    break
        
        # Row 3: Email (không bắt buộc)
        email_row = QHBoxLayout()
        email_lbl = QLabel("📧 Email:")
        email_lbl.setFixedWidth(90)
        email_lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        email_row.addWidget(email_lbl)
        self._email_entry = QLineEdit()
        self._email_entry.setPlaceholderText("Không bắt buộc")
        self._email_entry.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px 8px;")
        email_row.addWidget(self._email_entry)
        req_layout.addLayout(email_row)
        
        # Send button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        send_btn = QPushButton("📤 Gửi yêu cầu")
        send_btn.setFixedHeight(34)
        send_btn.setFixedWidth(220)
        send_btn.setStyleSheet(
            f"background-color: {Theme.BLUE}; color: {Theme.CRUST}; "
            f"font-weight: bold; padding: 0 16px; border-radius: 4px; font-size: 12px;"
        )
        send_btn.clicked.connect(self._on_send_request)
        send_btn.setAutoDefault(False)
        btn_row.addWidget(send_btn)
        btn_row.addStretch()
        req_layout.addLayout(btn_row)
        
        # Send status label (below send button)
        self._send_status = QLabel("")
        self._send_status.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        self._send_status.setAlignment(Qt.AlignCenter)
        req_layout.addWidget(self._send_status)
        
        clayout.addWidget(req_frame)
        
        # ── Contact info (from secure provider) ──
        from config.contact_provider import get_contact_info
        _ci = get_contact_info()
        contact = QLabel(f"📞 Liên hệ mua license: Zalo {_ci.get('zalo', 'N/A')} hoặc {_ci.get('phone', 'N/A')}")
        contact.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        contact.setAlignment(Qt.AlignCenter)
        clayout.addWidget(contact)
        
        # ── Exit button ──
        clayout.addStretch()
        
        exit_row = QHBoxLayout()
        exit_row.addStretch()
        exit_btn = QPushButton("❌ Thoát ứng dụng" if self._force_exit else "Đóng")
        exit_btn.setFixedSize(180, 36)
        exit_btn.setStyleSheet(
            f"background-color: {Theme.RED}; color: {Theme.CRUST}; "
            f"font-weight: bold; border-radius: 4px;"
        )
        exit_btn.clicked.connect(self._on_exit)
        exit_btn.setAutoDefault(False)
        exit_row.addWidget(exit_btn)
        exit_row.addStretch()
        clayout.addLayout(exit_row)
        
        layout.addWidget(content)
    
    # ── Tier card ───────────────────────────────────────────────
    
    def _create_tier_card(self, td: dict) -> QWidget:
        """Create a single pricing tier card."""
        key = td["key"]
        color = TIER_COLORS.get(key, Theme.SURFACE2)
        
        card = QFrame()
        card.setStyleSheet(f"background-color: {Theme.SURFACE2}; border-radius: 6px;")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setFixedHeight(155)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(2)
        
        # Colored header
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(f"background-color: {color};")
        hlayout = QVBoxLayout(header)
        hlayout.setContentsMargins(4, 2, 4, 2)
        
        name_lbl = QLabel(td["name"])
        name_lbl.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold; font-size: 13px;")
        name_lbl.setAlignment(Qt.AlignCenter)
        hlayout.addWidget(name_lbl)
        
        layout.addWidget(header)
        
        # Price — dynamic based on first-buy status
        if key != "FREE" and self._is_first_buy and key in TIER_FIRST_BUY:
            fb = TIER_FIRST_BUY[key]
            # Show discounted price + original strikethrough
            price_lbl = QLabel(f"{fb['price']}")
            price_lbl.setStyleSheet(f"color: {Theme.GREEN}; font-weight: bold; font-size: 12px;")
            price_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(price_lbl)
            
            # Original price strikethrough
            orig_lbl = QLabel(f"<s>{td['price']}</s>")
            orig_lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px;")
            orig_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(orig_lbl)
            
            # Desc
            desc_lbl = QLabel(fb["desc"])
            desc_lbl.setStyleSheet(f"color: {Theme.GREEN}; font-size: 10px; font-weight: bold;")
            desc_lbl.setAlignment(Qt.AlignCenter)
            desc_lbl.setWordWrap(True)
            layout.addWidget(desc_lbl)
        else:
            price_lbl = QLabel(td["price"])
            price_lbl.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 12px;")
            price_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(price_lbl)
            
            # Desc
            desc_lbl = QLabel(td["desc"])
            desc_lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px;")
            desc_lbl.setAlignment(Qt.AlignCenter)
            desc_lbl.setWordWrap(True)
            layout.addWidget(desc_lbl)
        
        layout.addStretch()
        
        # Select / Buy more button
        if key == "FREE":
            # ── Trial card: status display + select button ──
            trial_state = self._get_trial_state()
            
            if trial_state == "approved":
                status_lbl = QLabel("✅ Đã được phê duyệt!")
                status_lbl.setStyleSheet(f"color: {Theme.GREEN}; font-size: 10px; font-weight: bold;")
                status_lbl.setAlignment(Qt.AlignCenter)
                layout.addWidget(status_lbl)
                
                sel_btn = QPushButton("🔓 Active Now")
                sel_btn.setFixedHeight(30)
                sel_btn.setStyleSheet(
                    f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                    f"font-size: 11px; font-weight: bold; border-radius: 5px;"
                )
                sel_btn.clicked.connect(self._on_activate_trial)
                
            elif trial_state == "pending":
                status_lbl = QLabel("⏳ Đang chờ admin duyệt...")
                status_lbl.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 10px;")
                status_lbl.setAlignment(Qt.AlignCenter)
                layout.addWidget(status_lbl)
                self._trial_status_label = status_lbl
                
                sel_btn = QPushButton("📩 Đã gửi yêu cầu")
                sel_btn.setFixedHeight(30)
                sel_btn.setStyleSheet(
                    f"background-color: {Theme.SURFACE1}; color: {Theme.SUBTEXT0}; "
                    f"font-size: 11px; border-radius: 5px;"
                )
                sel_btn.setEnabled(False)
                self._start_trial_polling()
                
            elif trial_state in ("active", "expired", "revoked"):
                state_msgs = {
                    "active": ("✅ Đang dùng thử", Theme.GREEN),
                    "expired": ("❌ Đã hết hạn", Theme.RED),
                    "revoked": ("❌ Đã bị thu hồi", Theme.RED),
                }
                msg, clr = state_msgs.get(trial_state, ("❌ Đã hết hạn", Theme.RED))
                sel_btn = QPushButton(msg)
                sel_btn.setFixedHeight(30)
                sel_btn.setStyleSheet(
                    f"background-color: {Theme.SURFACE1}; color: {clr}; "
                    f"font-size: 11px; border-radius: 5px;"
                )
                sel_btn.setEnabled(False)
                
            else:
                # Available → "Chọn" button selects Free in combo
                sel_btn = QPushButton("Chọn")
                sel_btn.setFixedHeight(30)
                sel_btn.setStyleSheet(
                    f"background-color: {color}; color: {Theme.CRUST}; "
                    f"font-size: 11px; font-weight: bold; border-radius: 5px;"
                )
                sel_btn.clicked.connect(lambda checked, k="FREE": self._select_tier(k))
            
            layout.addWidget(sel_btn)
        elif key != "FREE":
            if self._active_tier == "LIFETIME" and key == "LIFETIME":
                # Already Lifetime → nothing more to buy
                sel_btn = QPushButton("✅ Đang dùng")
                sel_btn.setFixedHeight(30)
                sel_btn.setStyleSheet(
                    f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                    f"font-size: 11px; font-weight: bold; border-radius: 5px;"
                )
                sel_btn.setEnabled(False)
            elif self._active_tier:
                # Has active license → can buy more to stack time
                # Lifetime: "Nâng cấp" (one-time), others: "Mua thêm" (stackable)
                btn_text = "🔥 Nâng cấp" if key == "LIFETIME" else "🛒 Mua thêm"
                sel_btn = QPushButton(btn_text)
                sel_btn.setFixedHeight(30)
                sel_btn.setStyleSheet(
                    f"background-color: {color}; color: {Theme.CRUST}; "
                    f"font-size: 11px; font-weight: bold; border-radius: 5px;"
                )
                sel_btn.clicked.connect(lambda checked, k=key: self._select_tier(k))
            else:
                # No active license → normal select
                sel_btn = QPushButton("Chọn")
                sel_btn.setFixedHeight(30)
                sel_btn.setStyleSheet(
                    f"background-color: {color}; color: {Theme.CRUST}; "
                    f"font-size: 11px; font-weight: bold; border-radius: 5px;"
                )
                sel_btn.clicked.connect(lambda checked, k=key: self._select_tier(k))
            layout.addWidget(sel_btn)
            self._tier_buttons[key] = sel_btn
        
        return card
    
    def _check_first_buy(self) -> bool:
        """Check if this machine has no previous purchases (first-buy eligible)."""
        # Quick check: if already has a paid license → definitely not first buy
        try:
            if self.controller and hasattr(self.controller, '_permissions'):
                from services.permissions import Role
                role = self.controller._permissions.role
                if role in (Role.PREMIUM, Role.TESTER):
                    return False
        except Exception:
            pass
        
        try:
            rest_client = None
            if self.controller and hasattr(self.controller, '_license_client'):
                rest_client = getattr(self.controller._license_client, '_rest_client', None)
            
            if not rest_client:
                try:
                    import sys
                    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "security"))
                    from _encrypted_api_keys import set_runtime_keys
                    set_runtime_keys()
                    from firebase_rest_client import FirebaseRESTClient
                    rest_client = FirebaseRESTClient()
                except Exception:
                    return True  # Can't check → assume first buy
            
            if rest_client and hasattr(rest_client, 'query_customer'):
                mid = self._get_machine_id()
                customer = rest_client.query_customer(mid)
                purchase_count = int(customer.get('purchase_count', 0))
                return purchase_count == 0
            return True  # No method → assume first buy
        except Exception:
            return True  # Error → assume first buy (be generous)
    
    def _get_rest_client(self):
        """Get REST client from controller or create new one."""
        rest_client = None
        if self.controller and hasattr(self.controller, '_license_client'):
            rest_client = getattr(self.controller._license_client, '_rest_client', None)
        if not rest_client:
            try:
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "security"))
                from _encrypted_api_keys import set_runtime_keys
                set_runtime_keys()
                from firebase_rest_client import FirebaseRESTClient
                rest_client = FirebaseRESTClient()
            except Exception:
                pass
        return rest_client
    
    def _get_trial_state(self) -> str:
        """
        Get trial state from server + local flag.
        Returns: "available" | "pending" | "approved" | "active" | "expired" | "revoked"
        
        Logic:
        - _trials/{MID} exists → server state (approved/active/expired/revoked)
        - _trials/{MID} not exists + local flag → "pending" (waiting admin)
        - Nothing → "available"
        """
        try:
            rest_client = self._get_rest_client()
            if not rest_client:
                return "available"
            
            mid = self._get_machine_id()
            
            # Check _trials/{MID} for admin-created trial record
            if hasattr(rest_client, 'check_trial_status'):
                trial = rest_client.check_trial_status(mid)
                if trial.get("exists"):
                    status = trial.get("status", "unknown")
                    if status == "active":
                        expires = trial.get("expires_at", "")
                        if expires:
                            try:
                                from datetime import datetime as dt
                                if dt.now() > dt.fromisoformat(expires):
                                    return "expired"
                            except Exception:
                                pass
                        # Check if already activated locally
                        # → show "✅ Đang dùng thử" instead of "Active Now"
                        if self.controller and getattr(self.controller, '_license_valid', False):
                            return "active"
                        return "approved"
                    elif status == "revoked":
                        return "revoked"
                    elif status in ("expired", "upgraded"):
                        return "expired"
            
            # No server record → check local pending flag
            if self._has_trial_requested_flag():
                return "pending"
            
            return "available"
        except Exception:
            return "available"
    
    def _has_trial_requested_flag(self) -> bool:
        """Check if local trial-request flag exists."""
        try:
            flag_path = Path(__file__).parent.parent.parent / "data" / ".trial_requested"
            return flag_path.exists()
        except Exception:
            return False
    
    def _set_trial_requested_flag(self):
        """Set local trial-request flag."""
        try:
            flag_dir = Path(__file__).parent.parent.parent / "data"
            flag_dir.mkdir(parents=True, exist_ok=True)
            flag_path = flag_dir / ".trial_requested"
            flag_path.write_text(datetime.now().isoformat(), encoding="utf-8")
        except Exception:
            pass
    
    def _on_submit_trial_request(self):
        """Submit trial request with full name → sends to _upgrade_requests.
        
        Uses the shared _name_entry from the upgrade request form.
        """
        name = getattr(self, '_name_entry', None)
        name_text = name.text().strip() if name else ''
        if not name_text or name_text == '***':
            self._status_label.setVisible(True)
            self._status_label.setText(t("license_popup.enter_name"))
            self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
            # Highlight the name field
            if name:
                if name_text == '***':
                    name.clear()
                    name.setReadOnly(False)
                name.setFocus()
                name.setStyleSheet(
                    f"background-color: {Theme.SURFACE2}; padding: 4px 8px; "
                    f"border: 2px solid {Theme.RED};"
                )
            return
        
        full_name = name.text().strip()
        if len(full_name) < 3:
            self._status_label.setVisible(True)
            self._status_label.setText("❌ Họ tên phải ít nhất 3 ký tự")
            self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
            return
        
        self._status_label.setVisible(True)
        self._status_label.setText("⏳ Đang gửi yêu cầu...")
        self._status_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        QApplication.processEvents()
        
        try:
            rest_client = self._get_rest_client()
            if not rest_client:
                self._status_label.setText("❌ Không thể kết nối server")
                self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                return
            
            mid = self._get_machine_id()
            
            success = rest_client.write_upgrade_request(
                machine_id=mid,
                tier="TRIAL",
                st_token="trial_request",
                send_count=1,
                client_name=full_name,
                email="",
                client_ip=getattr(self, '_client_ip', 'unknown'),
                is_first_buy=False,
            )
            
            if success:
                self._set_trial_requested_flag()
                self._status_label.setText(t("license_popup.sent_waiting"))
                self._status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
                
                if hasattr(self, '_name_entry'):
                    self._name_entry.setReadOnly(True)
                    self._name_entry.setStyleSheet(
                        f"background-color: {Theme.SURFACE1}; padding: 4px 8px; "
                        f"color: {Theme.SUBTEXT0};"
                    )
                
                self._start_trial_polling()
            else:
                self._status_label.setText("❌ Gửi yêu cầu thất bại. Thử lại sau.")
                self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                
        except Exception as e:
            self._status_label.setText(f"❌ Lỗi: {str(e)[:50]}")
            self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
    
    def _start_trial_polling(self):
        """Poll server to check if admin approved trial. Interval from server config."""
        if hasattr(self, '_trial_poll_timer') and self._trial_poll_timer:
            return  # Already polling
        
        # Get interval from server config (admin-controlled)
        rest_client = self._get_rest_client()
        if rest_client and hasattr(rest_client, 'get_config_value'):
            self._poll_interval = int(rest_client.get_config_value("trial_poll_interval_ms", 300000))
            self._poll_max = int(rest_client.get_config_value("trial_poll_max", 6))
        else:
            self._poll_interval = 300000  # 5 min default
            self._poll_max = 6
        
        self._trial_poll_count = 0
        self._trial_poll_timer = QTimer(self)
        self._trial_poll_timer.timeout.connect(self._poll_trial_approval)
        self._trial_poll_timer.start(self._poll_interval)
    
    def _poll_trial_approval(self):
        """Check if admin approved trial request."""
        self._trial_poll_count = getattr(self, '_trial_poll_count', 0) + 1
        poll_max = getattr(self, '_poll_max', 6)
        
        if self._trial_poll_count > poll_max:
            if hasattr(self, '_trial_poll_timer') and self._trial_poll_timer:
                self._trial_poll_timer.stop()
            if hasattr(self, '_trial_status_label') and self._trial_status_label:
                self._trial_status_label.setText("⏰ Hết thời gian chờ. Liên hệ admin.")
            return
        
        try:
            state = self._get_trial_state()
            
            if state == "approved":
                # Admin approved! Stop polling & update UI
                if hasattr(self, '_trial_poll_timer') and self._trial_poll_timer:
                    self._trial_poll_timer.stop()
                
                if hasattr(self, '_trial_status_label') and self._trial_status_label:
                    self._trial_status_label.setText("✅ Đã được phê duyệt! Bấm Active Now.")
                    self._trial_status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 10px; font-weight: bold;")
                
                self._status_label.setVisible(True)
                self._status_label.setText("✅ Admin đã duyệt! Bấm Active Now bên dưới.")
                self._status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
                
        except Exception:
            pass  # Silent fail — will retry next poll
    
    def _on_activate_trial(self):
        """Activate trial AFTER admin has approved (server record exists)."""
        self._status_label.setVisible(True)
        self._status_label.setText("⏳ Đang kích hoạt...")
        self._status_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        QApplication.processEvents()
        
        try:
            rest_client = self._get_rest_client()
            mid = self._get_machine_id()
            
            # Verify server approval exists
            if rest_client and hasattr(rest_client, 'check_trial_status'):
                trial = rest_client.check_trial_status(mid)
                if not trial.get("exists") or trial.get("status") != "active":
                    self._status_label.setText(t("license_popup.not_approved"))
                    self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                    return
                
                expires = trial.get("expires_at", "")
            else:
                self._status_label.setText("❌ Không thể kết nối server")
                self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                return
            
            # Create local cache from server data
            if self.controller and hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                trial_data = {
                    'key': f'TRIAL-{mid[:16]}',
                    'tier': 'TRIA',
                    'role': 0,
                    'expires': expires,
                    'machine_id': mid,
                    'last_verified': datetime.now().isoformat(),
                    '_lim': trial.get('_lim'),  # Dynamic limits from server
                }
                lc.storage.save(trial_data)
                if hasattr(lc, '_invalidate_validate_cache'):
                    lc._invalidate_validate_cache()
                self.controller._update_permissions()
                self.controller._license_valid = True
                
                # Apply trial dynamic limits
                trial_lim = trial.get('_lim')
                if trial_lim and hasattr(self.controller, '_permissions'):
                    self.controller._permissions.apply_server_limits(trial_lim)
            
            self._status_label.setText("✅ Đã kích hoạt 3 ngày dùng thử!")
            self._status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
            QTimer.singleShot(1500, self.accept)
            
        except Exception as e:
            self._status_label.setText(f"❌ Lỗi: {str(e)[:50]}")
            self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
    
    def _select_tier(self, key: str):
        """Select a tier in the combo box."""
        for i in range(self._tier_combo.count()):
            if self._tier_combo.itemData(i) == key:
                self._tier_combo.setCurrentIndex(i)
                break
        self._selected_tier = key
        self._status_label.setText(f"✅ Đã chọn gói: {key}")
        self._status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
    
    # ── Actions ─────────────────────────────────────────────────
    
    def _get_active_tier(self) -> str:
        """Get current active license tier code (e.g. '1M', '3M', 'LT')."""
        if self.controller and hasattr(self.controller, 'get_license_status'):
            try:
                ls = self.controller.get_license_status()
                if ls.get('is_licensed') and ls.get('tier'):
                    return ls['tier']
            except Exception:
                pass
        return ""  # No active license
    
    def _get_machine_id(self) -> str:
        """Get FULL machine ID (64-char SHA256 hash)."""
        if self.controller and hasattr(self.controller, '_license_client'):
            try:
                return self.controller._license_client.get_machine_id()
            except Exception:
                pass
        try:
            from security.license_client import LicenseClient
            return LicenseClient().get_machine_id()
        except Exception:
            return "N/A"
    
    def _detect_ip(self) -> str:
        """Auto-detect client public IP via ipify.org (no user input)."""
        try:
            return http_requests.get("https://api.ipify.org", timeout=3).text.strip()
        except Exception:
            return "unknown"
    
    def _generate_st(self) -> str:
        """Generate anti-spam token: SHA256(mid + hour + salt)[:8]."""
        mid = self._mid_entry.text()
        hour = datetime.now().strftime("%Y%m%d%H")
        raw = f"{mid}:{hour}:veo_pro_max_st"
        return hashlib.sha256(raw.encode()).hexdigest()[:8].upper()
    
    def _on_copy_mid(self):
        """Copy Machine ID to clipboard with visual feedback."""
        mid = self._mid_entry.text()
        if mid and mid != "N/A":
            QApplication.clipboard().setText(mid)
            # Visual feedback
            if hasattr(self, '_copy_btn'):
                self._copy_btn.setText("✅ Copied!")
                self._copy_btn.setStyleSheet(
                    f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; font-size: 11px; font-weight: bold;"
                )
                QTimer.singleShot(1500, lambda: (
                    self._copy_btn.setText("📋 Copy"),
                    self._copy_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; font-size: 11px;")
                ))
    
    def _on_activate(self):
        """Activate serial key."""
        try:
            key = self._serial_entry.text().strip()
            if not key:
                self._status_label.setVisible(True)
                self._status_label.setText(t("license_popup.enter_key"))
                self._status_label.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px;")
                return
            
            # ── Local format validation (instant feedback) ──
            parts = key.upper().replace(" ", "").split("-")
            
            # Check segment count
            if len(parts) not in (8, 9, 4, 5):
                self._status_label.setVisible(True)
                expected = "9 nhóm (XXXX-XXXX-...-XXXX)"
                self._status_label.setText(f"❌ Sai format — cần {expected}, bạn nhập {len(parts)} nhóm")
                self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                return
            
            # Check each segment is 4-char hex (for 8/9-segment keys)
            if len(parts) in (8, 9):
                for i, p in enumerate(parts):
                    if len(p) != 4:
                        self._status_label.setVisible(True)
                        self._status_label.setText(f"❌ Nhóm {i+1} phải là 4 ký tự (bạn nhập {len(p)})")
                        self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                        return
                    if not all(c in '0123456789ABCDEF' for c in p):
                        self._status_label.setVisible(True)
                        self._status_label.setText(f"❌ Nhóm {i+1} chỉ chấp nhận ký tự HEX (0-9, A-F)")
                        self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                        return
            
            # ── Persistent rate limit (5/hour, HMAC-signed, tamper-proof) ──
            rate_file = Path.home() / ".veoauto" / ".rate_limit"
            now = datetime.now()
            attempts = []
            # V7: Derive HMAC key from machine_id (not hardcoded)
            _mid = self._get_machine_id()
            _rl_hmac_key = hashlib.sha256((_mid + "||rl_hmac").encode()).digest()
            
            def _rl_sign(data_str: str) -> str:
                """HMAC-SHA256 signature for rate limit data."""
                import hmac as _hmac
                return _hmac.new(_rl_hmac_key, data_str.encode(), hashlib.sha256).hexdigest()
            
            try:
                if rate_file.exists():
                    raw_text = rate_file.read_text(encoding='utf-8')
                    parts = raw_text.rsplit('|', 1)
                    if len(parts) == 2:
                        data_str, stored_sig = parts
                        expected_sig = _rl_sign(data_str)
                        if stored_sig == expected_sig:
                            # Signature valid → parse
                            raw = json.loads(data_str)
                            attempts = [datetime.fromisoformat(t) for t in raw
                                        if (now - datetime.fromisoformat(t)).total_seconds() < 3600]
                        else:
                            # TAMPERED! Treat as max attempts (punish tampering)
                            self._status_label.setVisible(True)
                            self._status_label.setText(t("license_popup.tamper_detected"))
                            self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                            return
                    else:
                        # Invalid format → treat as tampered
                        self._status_label.setVisible(True)
                        self._status_label.setText(t("license_popup.rate_limit_invalid"))
                        self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                        return
            except json.JSONDecodeError:
                # Tampered JSON → block
                self._status_label.setVisible(True)
                self._status_label.setText(t("license_popup.tamper_detected"))
                self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
                return
            except Exception:
                attempts = []
            
            if len(attempts) >= 5:
                oldest = attempts[0]
                remaining_secs = int(3600 - (now - oldest).total_seconds())
                mins = remaining_secs // 60
                secs = remaining_secs % 60
                self._status_label.setVisible(True)
                self._status_label.setText(t("license_popup.too_many_attempts").replace("{mins}", str(mins)).replace("{secs}", f"{secs:02d}"))
                self._status_label.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px;")
                return
            
            # ── Rate limit OK → call server ──
            self._status_label.setVisible(True)
            self._status_label.setText("⏳ Đang kích hoạt...")
            self._status_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
            QApplication.processEvents()
            
            if self.controller and hasattr(self.controller, 'activate_license'):
                result = self.controller.activate_license(key)
                success = result.get('success') if isinstance(result, dict) else bool(result)
                if success:
                    self._status_label.setText("✅ Kích hoạt thành công!")
                    self._status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
                    self._activated = True
                    # Clear rate limit on success
                    try:
                        rate_file.unlink(missing_ok=True)
                    except Exception:
                        pass
                    # ── Trial cleanup: remove local trial flag ──
                    # NOTE: Server-side trial update (status → "upgraded") is handled
                    # by admin's approve_request() via Admin SDK. Client REST API cannot
                    # write to _trials (Firebase rules: allow write: if false).
                    try:
                        flag_path = Path(__file__).parent.parent.parent / "data" / ".trial_requested"
                        flag_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self.accept()
                    return
                else:
                    # ── Record failed attempt (both local + server) ──
                    err_msg = result.get('message', 'Serial không hợp lệ') if isinstance(result, dict) else "Serial không hợp lệ hoặc đã hết hạn"
                    attempts.append(now)
                    try:
                        data_str = json.dumps([t.isoformat() for t in attempts])
                        sig = _rl_sign(data_str)
                        rate_file.parent.mkdir(parents=True, exist_ok=True)
                        rate_file.write_text(f"{data_str}|{sig}", encoding='utf-8')
                    except Exception:
                        pass
                    
                    # Server-side tracking (anti-DDoS)
                    try:
                        full_mid = self._get_machine_id()
                        if full_mid != "N/A":
                            rest_client = None
                            if self.controller and hasattr(self.controller, '_license_client'):
                                rest_client = getattr(self.controller._license_client, '_rest_client', None)
                            if rest_client and hasattr(rest_client, 'record_activation_attempt'):
                                rest_client.record_activation_attempt(full_mid)
                    except Exception:
                        pass
                    
                    self._status_label.setText(f"❌ {err_msg}")
                    self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
            else:
                self._status_label.setText("⚠️ Không thể kích hoạt — controller unavailable")
                self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
        except Exception as e:
            self._status_label.setVisible(True)
            self._status_label.setText(f"❌ Lỗi: {str(e)[:50]}")
            self._status_label.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
    
    def _on_send_request(self):
        """Send request to Firebase — handles both FREE (trial) and paid tiers."""
        mid = self._mid_entry.text()
        tier_key = self._tier_combo.currentData() or "1M"
        name = self._name_entry.text().strip()
        email = self._email_entry.text().strip()  # optional
        st = self._generate_st()
        
        # ── Guard 0: Require name only ──
        if not name or name == '***':
            self._send_status.setText(t("license_popup.enter_real_name"))
            self._send_status.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px;")
            self._name_entry.setFocus()
            if name == '***':
                self._name_entry.clear()  # Clear masked placeholder
                self._name_entry.setReadOnly(False)
            return
        
        # ── FREE tier → delegate to trial request logic ──
        if tier_key == "FREE":
            self._on_submit_trial_request()
            return
        
        # ── Guard 1: Validate MID from hardware ──
        real_mid = self._get_machine_id()
        if mid != real_mid or mid == "N/A":
            self._send_status.setText("❌ Machine ID không hợp lệ")
            self._send_status.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
            return
        
        # Get full 64-char MID for Firebase storage
        full_mid = self._get_machine_id()
        if full_mid == "N/A":
            self._send_status.setText("❌ Không lấy được Machine ID đầy đủ")
            self._send_status.setStyleSheet(f"color: {Theme.RED}; font-size: 11px;")
            return
        
        # ── Guard 2: Client-side rate limit (5 sends/hour) ──
        now = datetime.now()
        # Remove sends older than 1 hour
        self._send_times = [t for t in self._send_times if (now - t).total_seconds() < 3600]
        if len(self._send_times) >= 5:
            oldest = self._send_times[0]
            remaining = int((3600 - (now - oldest).total_seconds()) / 60)
            self._send_status.setText(f"⏳ Đã gửi 5/5 lần. Chờ {remaining} phút")
            self._send_status.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px;")
            return
        
        self._send_status.setText("⏳ Đang gửi yêu cầu...")
        self._send_status.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        QApplication.processEvents()
        
        # ── Send to Firebase (PATCH: 1 doc per machine) ──
        sent = False
        error_msg = ""
        try:
            # Try getting REST client from controller
            rest_client = None
            if self.controller and hasattr(self.controller, '_license_client'):
                rest_client = getattr(self.controller._license_client, '_rest_client', None)
            
            # Fallback: create REST client directly if controller's is missing
            if not rest_client:
                try:
                    import sys
                    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "security"))
                    from _encrypted_api_keys import set_runtime_keys
                    set_runtime_keys()
                    from firebase_rest_client import FirebaseRESTClient
                    rest_client = FirebaseRESTClient()
                except Exception as e:
                    error_msg = f"Firebase init: {str(e)[:40]}"
            
            if rest_client and hasattr(rest_client, 'write_upgrade_request'):
                # Send FULL 64-char MID to Firebase (not truncated display ID)
                sent = rest_client.write_upgrade_request(
                    full_mid, tier_key, st, len(self._send_times) + 1,
                    client_name=name, email=email,
                    client_ip=self._client_ip,
                    is_first_buy=self._is_first_buy
                )
                if not sent:
                    error_msg = "Server rejected request"
            elif not error_msg:
                error_msg = "REST client not available"
        except Exception as e:
            error_msg = str(e)[:50]
        
        # Calculate price for clipboard
        if self._is_first_buy and tier_key in TIER_FIRST_BUY:
            price_display = TIER_FIRST_BUY[tier_key]["price"]
            price_amount = TIER_FIRST_BUY[tier_key]["amount"]
            buy_label = "Lần đầu"
        else:
            price_amount = TIER_NORMAL_AMOUNT.get(tier_key, 0)
            price_display = next((t["price"] for t in TIER_DEFS if t["key"] == tier_key), "N/A")
            buy_label = "Mua thêm"
        
        # Also copy to clipboard (always)
        submit_time = datetime.now().strftime("%d/%m/%Y %H:%M")
        text = (
            f"VEO Pro Max — Yêu cầu nâng cấp\n"
            f"Machine ID: {mid}\n"
            f"Họ tên: {name}\n"
            f"Gói: {tier_key} ({buy_label})\n"
            f"Thành tiền: {price_display} ({price_amount:,}đ)\n"
            + (f"Email: {email}\n" if email else "")
            + f"Thời gian gửi: {submit_time}\n"
            f"ST: {st}\n"
            f"Nội dung CK: VEO {mid} {tier_key}"
        )
        QApplication.clipboard().setText(text)
        
        if sent:
            self._send_times.append(datetime.now())
            remaining = 5 - len(self._send_times)
            self._send_status.setText(f"✅ Đã gửi thành công! (còn {remaining} lần/h)")
            self._send_status.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
        else:
            detail = f" [{error_msg}]" if error_msg else ""
            self._send_status.setText(f"📋 Đã copy (server thất bại{detail})")
            self._send_status.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px;")
    
    def _on_exit(self):
        """Exit or close dialog."""
        if self._force_exit:
            sys.exit(0)
        else:
            self.reject()
    
    def reject(self):
        """Override reject to prevent accidental dialog close.
        
        In Qt, various internal events can trigger reject() on a QDialog
        (Enter key, autoDefault buttons, etc.). Block all of these when
        force_exit=True and activation hasn't succeeded.
        """
        if self._force_exit and not getattr(self, '_activated', False):
            return  # Block — only _on_exit (sys.exit) or accept() can close
        super().reject()
    
    def keyPressEvent(self, event):
        """Block Escape key when force_exit — prevent license bypass."""
        if self._force_exit and event.key() == Qt.Key_Escape:
            return  # Ignore Escape
        super().keyPressEvent(event)
    

    def closeEvent(self, event):
        """Handle window close (X button)."""
        if self._force_exit:
            sys.exit(0)
        super().closeEvent(event)
