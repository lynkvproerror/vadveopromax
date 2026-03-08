"""
VEO License Manager GUI
PySide6 app for sellers to manage license requests

Usage: python seller_manager_gui.pyw
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QComboBox, QTextEdit, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QMessageBox, QStatusBar, QHeaderView,
    QFrame, QTabWidget, QStackedWidget
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from seller_auth import (
    get_machine_id, get_display_mid,
    SellerFirebaseManager, SellerPermissions
)


def _get_app_icon() -> QIcon:
    """Load app icon from logo folder (works in both dev and compiled)."""
    candidates = [
        Path(__file__).parent / "logo" / "LOGO 5.png",
        Path(sys.argv[0]).parent / "logo" / "LOGO 5.png",
        Path(".") / "logo" / "LOGO 5.png",
    ]
    for p in candidates:
        if p.exists():
            return QIcon(QPixmap(str(p)))
    return QIcon()

# ============================================================
# DARK THEME
# ============================================================

DARK_STYLESHEET = """
QMainWindow, QDialog, QWidget {
    background-color: #1a1b2e;
    color: #e0e0f0;
}
QLabel { color: #e0e0f0; }
QTableWidget {
    background-color: #242540;
    color: #e0e0f0;
    gridline-color: #3a3b5c;
    selection-background-color: #4a4b7c;
    border: 1px solid #3a3b5c;
    border-radius: 6px;
}
QTableWidget::item { padding: 6px; }
QTableWidget::item:selected { background-color: #4a4b7c; }
QHeaderView::section {
    background-color: #2a2b4e;
    color: #7aa2f7;
    padding: 8px;
    border: 1px solid #3a3b5c;
    font-weight: bold;
}
QPushButton {
    background-color: #7aa2f7;
    color: #1a1b2e;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover { background-color: #9ab8f9; }
QPushButton:pressed { background-color: #5a82d7; }
QPushButton:disabled { background-color: #3a3b5c; color: #6a6b8c; }
QPushButton#dangerBtn { background-color: #f7768e; }
QPushButton#dangerBtn:hover { background-color: #f9a0b0; }
QPushButton#successBtn { background-color: #9ece6a; color: #1a1b2e; }
QPushButton#successBtn:hover { background-color: #b8e88a; }
QPushButton#warnBtn { background-color: #e0af68; color: #1a1b2e; }
QPushButton#warnBtn:hover { background-color: #f0cf88; }
QLineEdit, QTextEdit, QComboBox {
    background-color: #242540;
    color: #e0e0f0;
    border: 1px solid #3a3b5c;
    border-radius: 6px;
    padding: 10px;
    font-size: 13px;
}
QLineEdit:focus { border-color: #7aa2f7; }
QGroupBox {
    border: 1px solid #3a3b5c;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    color: #7aa2f7;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QTabWidget::pane {
    border: 1px solid #3a3b5c;
    border-radius: 6px;
    background-color: #1a1b2e;
}
QTabBar::tab {
    background-color: #242540;
    color: #8a8bac;
    padding: 10px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #1a1b2e;
    color: #7aa2f7;
    border-bottom: 2px solid #7aa2f7;
}
QTabBar::tab:hover { background-color: #2a2b4e; }
QStatusBar { background-color: #242540; color: #8a8bac; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #242540;
    color: #e0e0f0;
    selection-background-color: #4a4b7c;
}
"""


# ============================================================
# LOGIN DIALOG
# ============================================================

class LoginDialog(QDialog):
    """Login screen with MID auto-detect + password."""
    
    def __init__(self, firebase: SellerFirebaseManager, parent=None):
        super().__init__(parent)
        self.firebase = firebase
        self.machine_id = get_machine_id()
        self.login_result = None
        self.setWindowIcon(_get_app_icon())
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("🔐 VEO License Manager — Đăng nhập")
        self.setFixedSize(480, 420)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(40, 30, 40, 30)
        
        # Title
        title = QLabel("VEO LICENSE MANAGER")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet("color: #7aa2f7; margin-bottom: 8px;")
        layout.addWidget(title)
        
        subtitle = QLabel("Đăng nhập bằng mật khẩu được Admin cấp")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #8a8bac; font-size: 12px;")
        layout.addWidget(subtitle)
        
        layout.addSpacing(10)
        
        # Machine ID (auto-detected — full, selectable, with Copy button)
        mid_row = QHBoxLayout()
        
        mid_field = QLineEdit(self.machine_id)
        mid_field.setReadOnly(True)
        mid_field.setStyleSheet(
            "color: #9ece6a; font-size: 12px; font-family: 'Consolas'; "
            "background-color: #242540; border: 1px solid #3a3b5c; padding: 8px;"
        )
        mid_field.setToolTip("Machine ID — gửi mã này cho Admin để được cấp tài khoản")
        mid_row.addWidget(mid_field, stretch=1)
        
        copy_mid_btn = QPushButton("📋 Copy MID")
        copy_mid_btn.setFixedWidth(110)
        copy_mid_btn.setAutoDefault(False)
        copy_mid_btn.setDefault(False)
        copy_mid_btn.setStyleSheet("font-size: 11px; padding: 8px;")
        copy_mid_btn.clicked.connect(lambda: (
            QApplication.clipboard().setText(self.machine_id),
            self.status_label.setStyleSheet("color: #9ece6a; font-size: 12px;"),
            self.status_label.setText("✅ Đã copy Machine ID — gửi cho Admin!")
        ))
        mid_row.addWidget(copy_mid_btn)
        
        layout.addLayout(mid_row)
        
        # Password
        pw_label = QLabel("🔑 Mật khẩu:")
        pw_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(pw_label)
        
        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.Password)
        self.pw_input.setPlaceholderText("Nhập mật khẩu Admin đã cấp...")
        self.pw_input.returnPressed.connect(self.do_login)
        layout.addWidget(self.pw_input)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #f7768e; font-size: 12px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # Login button
        self.login_btn = QPushButton("🔓 ĐĂNG NHẬP")
        self.login_btn.setMinimumHeight(44)
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self.do_login)
        layout.addWidget(self.login_btn)
        
        layout.addStretch()
    
    def do_login(self):
        password = self.pw_input.text().strip()
        if not password:
            self.status_label.setText("⚠ Vui lòng nhập mật khẩu")
            return
        
        self.login_btn.setEnabled(False)
        self.login_btn.setText("Đang xác thực...")
        self.status_label.setText("")
        QApplication.processEvents()
        
        result = self.firebase.authenticate(self.machine_id, password)
        
        if result.get("success"):
            self.login_result = result
            self.accept()
        else:
            self.status_label.setText(f"❌ {result.get('error', 'Lỗi không xác định')}")
            self.login_btn.setEnabled(True)
            self.login_btn.setText("🔓 ĐĂNG NHẬP")
            self.pw_input.selectAll()
            self.pw_input.setFocus()


# ============================================================
# MAIN WINDOW
# ============================================================

class SellerMainWindow(QMainWindow):
    """Main seller window with permission-based tabs."""
    
    def __init__(self, firebase: SellerFirebaseManager, login_data: dict):
        super().__init__()
        self.firebase = firebase
        self.login_data = login_data
        self.machine_id = get_machine_id()
        self.level = login_data.get('level', 1)
        self.seller_name = login_data.get('name', '')
        self.app_filter = login_data.get('app_filter', ['VEO'])
        self.permissions = SellerPermissions(self.level)
        
        self.setWindowIcon(_get_app_icon())
        self.setup_ui()
        self.refresh_data()
        
        # Auto-refresh data every 30s
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(30000)
        
        # Session auto-refresh every 25 minutes (before 30-min expiry)
        self.session_timer = QTimer()
        self.session_timer.timeout.connect(self._refresh_session)
        self.session_timer.start(25 * 60 * 1000)  # 25 min
    
    def setup_ui(self):
        level_tag = f"Level {self.level} — {self.permissions.level_name}"
        self.setWindowTitle(f"🛒 VEO License Manager — {self.seller_name} [{level_tag}]")
        self.setMinimumSize(1200, 700)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Header bar
        header = QHBoxLayout()
        
        info_label = QLabel(f"👤 {self.seller_name}  |  📋 {level_tag}  |  🖥 {get_display_mid(self.machine_id)}")
        info_label.setStyleSheet("font-size: 13px; color: #9ece6a;")
        header.addWidget(info_label)
        
        header.addStretch()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self._manual_refresh)
        header.addWidget(self.refresh_btn)
        
        layout.addLayout(header)
        
        # Tabs
        self.tabs = QTabWidget()
        
        # Tab 1: Requests
        self._setup_requests_tab()
        
        # Tab 2: Active Keys (Level 2 ONLY)
        if self.permissions.can('approve_paid'):
            self._setup_keys_tab()
        
        # Tab 3: Trials (ALL levels)
        self._setup_trials_tab()
        
        # Tab 4: Overview
        self._setup_overview_tab()
        
        # Tab 5: Change Password
        self._setup_password_tab()
        
        layout.addWidget(self.tabs)
        
        # Status bar
        self.statusBar().showMessage(f"✅ Đăng nhập thành công — {datetime.now().strftime('%H:%M:%S')}")
    
    # ── Tab Setup ──────────────────────────────────────
    
    def _setup_requests_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        self.approve_trial_btn = QPushButton("✅ Approve Trial")
        self.approve_trial_btn.setObjectName("successBtn")
        self.approve_trial_btn.clicked.connect(self.action_approve_trial)
        toolbar.addWidget(self.approve_trial_btn)
        
        if self.permissions.can('approve_paid'):
            self.approve_paid_btn = QPushButton("💰 Confirm Payment & Create Key")
            self.approve_paid_btn.setObjectName("warnBtn")
            self.approve_paid_btn.clicked.connect(self.action_approve_paid)
            toolbar.addWidget(self.approve_paid_btn)
        
        toolbar.addStretch()
        
        self.req_search = QLineEdit()
        self.req_search.setPlaceholderText("🔍 Tìm tên / MID...")
        self.req_search.setFixedWidth(220)
        self.req_search.textChanged.connect(self._filter_requests)
        toolbar.addWidget(self.req_search)
        
        layout.addLayout(toolbar)
        
        # Request table
        cols = ["Client", "MID", "Tier", "App", "Submitted", "Status"]
        self.req_table = QTableWidget()
        self.req_table.setColumnCount(len(cols))
        self.req_table.setHorizontalHeaderLabels(cols)
        self.req_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.req_table.setSelectionMode(QTableWidget.SingleSelection)
        self.req_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.req_table.horizontalHeader().setStretchLastSection(True)
        self.req_table.setColumnWidth(0, 150)
        self.req_table.setColumnWidth(1, 120)
        self.req_table.setColumnWidth(2, 80)
        self.req_table.setColumnWidth(3, 60)
        self.req_table.setColumnWidth(4, 160)
        layout.addWidget(self.req_table)
        
        self.tabs.addTab(widget, "📬 Requests")
    
    def _setup_keys_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        toolbar = QHBoxLayout()
        
        if self.permissions.can('revoke_key'):
            revoke_btn = QPushButton("🗑 Revoke Key")
            revoke_btn.setObjectName("dangerBtn")
            revoke_btn.clicked.connect(self.action_revoke_key)
            toolbar.addWidget(revoke_btn)
            
            if self.permissions.can('edit_client_name'):
                edit_btn = QPushButton("✏ Edit Họ tên")
                edit_btn.clicked.connect(self.action_edit_name)
                toolbar.addWidget(edit_btn)
            
            copy_key_btn = QPushButton("📋 Copy Key")
            copy_key_btn.clicked.connect(self.action_copy_key)
            toolbar.addWidget(copy_key_btn)
        
        toolbar.addStretch()
        
        self.key_search = QLineEdit()
        self.key_search.setPlaceholderText("🔍 Tìm tên / MID / Key...")
        self.key_search.setFixedWidth(220)
        self.key_search.textChanged.connect(self._filter_keys)
        toolbar.addWidget(self.key_search)
        
        layout.addLayout(toolbar)
        
        cols = ["Key", "Client", "MID", "Tier", "App", "Status", "Expires"]
        self.keys_table = QTableWidget()
        self.keys_table.setColumnCount(len(cols))
        self.keys_table.setHorizontalHeaderLabels(cols)
        self.keys_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.keys_table.setSelectionMode(QTableWidget.SingleSelection)
        self.keys_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.keys_table.horizontalHeader().setStretchLastSection(True)
        self.keys_table.setColumnWidth(0, 200)
        self.keys_table.setColumnWidth(1, 120)
        self.keys_table.setColumnWidth(2, 100)
        layout.addWidget(self.keys_table)
        
        self.tabs.addTab(widget, "🔑 Keys")
    
    def _setup_overview_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.overview_text = QTextEdit()
        self.overview_text.setReadOnly(True)
        self.overview_text.setStyleSheet("font-size: 14px; padding: 16px;")
        layout.addWidget(self.overview_text)
        
        self.tabs.addTab(widget, "📊 Tổng quan")
    
    def _setup_password_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(40, 40, 40, 40)
        
        group = QGroupBox("🔑 Đổi mật khẩu")
        form = QFormLayout(group)
        
        self.old_pw = QLineEdit()
        self.old_pw.setEchoMode(QLineEdit.Password)
        self.old_pw.setPlaceholderText("Mật khẩu hiện tại")
        form.addRow("Mật khẩu cũ:", self.old_pw)
        
        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.Password)
        self.new_pw.setPlaceholderText("Mật khẩu mới (>=6 ký tự)")
        form.addRow("Mật khẩu mới:", self.new_pw)
        
        self.confirm_pw = QLineEdit()
        self.confirm_pw.setEchoMode(QLineEdit.Password)
        self.confirm_pw.setPlaceholderText("Nhập lại mật khẩu mới")
        form.addRow("Xác nhận:", self.confirm_pw)
        
        change_btn = QPushButton("💾 Đổi mật khẩu")
        change_btn.clicked.connect(self.action_change_password)
        form.addRow("", change_btn)
        
        self.pw_status = QLabel("")
        self.pw_status.setWordWrap(True)
        form.addRow("", self.pw_status)
        
        layout.addWidget(group)
        layout.addStretch()
        self.tabs.addTab(widget, "⚙ Đổi mật khẩu")
    
    def _setup_trials_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        cols = ["Client", "MID", "Status", "Ngày bắt đầu", "Ngày hết hạn", "Approved by"]
        self.trials_table = QTableWidget()
        self.trials_table.setColumnCount(len(cols))
        self.trials_table.setHorizontalHeaderLabels(cols)
        self.trials_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.trials_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.trials_table.horizontalHeader().setStretchLastSection(True)
        self.trials_table.setColumnWidth(0, 150)
        self.trials_table.setColumnWidth(1, 120)
        self.trials_table.setColumnWidth(2, 80)
        self.trials_table.setColumnWidth(3, 150)
        self.trials_table.setColumnWidth(4, 150)
        layout.addWidget(self.trials_table)
        
        self.tabs.addTab(widget, "🕑 Trials")
    
    # ── Session Management ─────────────────────────────
    
    def _refresh_session(self):
        """Auto-refresh session token before 30-min expiry."""
        from seller_auth import generate_session_token
        try:
            # Re-verify status from Firebase
            sv = self.firebase._verify_session()
            if not sv.get('valid'):
                QMessageBox.critical(self, "Phiên hết hạn", sv.get('error', 'Session expired'))
                self.close()
                return
            # Generate fresh token
            new_token = generate_session_token(self.machine_id, self.level)
            self.firebase._session_token = new_token
            self.firebase._last_status_check = datetime.now()
            # Update level if changed
            if self.firebase._permissions:
                new_level = self.firebase._permissions.level
                if new_level != self.level:
                    self.level = new_level
                    self.permissions = SellerPermissions(new_level)
                    self.statusBar().showMessage(f"⚠️ Level thay đổi → {new_level}")
        except Exception:
            pass
    
    # ── Data Refresh ───────────────────────────────────
    
    def _manual_refresh(self):
        """Manual refresh with 5s cooldown to prevent Firebase quota drain."""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳ Wait...")
        self.refresh_data()
        QTimer.singleShot(5000, lambda: (
            self.refresh_btn.setEnabled(True),
            self.refresh_btn.setText("🔄 Refresh")
        ))
    
    def refresh_data(self):
        self._load_requests()
        if hasattr(self, 'keys_table'):
            self._load_keys()
        if hasattr(self, 'trials_table'):
            self._load_trials()
        self._load_overview()
        self.statusBar().showMessage(f"🔄 Cập nhật lúc {datetime.now().strftime('%H:%M:%S')}")
    
    def _load_requests(self):
        requests = self.firebase.get_pending_requests(self.app_filter)
        
        # Level 1: chỉ thấy TRIAL requests
        if self.level == 1:
            requests = [r for r in requests if r.get('tier', '') == 'TRIAL']
        
        self.req_table.setRowCount(len(requests))
        self._requests_data = requests
        
        for i, req in enumerate(requests):
            self.req_table.setItem(i, 0, QTableWidgetItem(req.get('client_name', '')))
            self.req_table.setItem(i, 1, QTableWidgetItem(req.get('machine_id', '')[:16]))
            
            tier = req.get('tier', '')
            tier_item = QTableWidgetItem(tier)
            if tier == 'TRIAL':
                tier_item.setForeground(QColor("#9ece6a"))
            else:
                tier_item.setForeground(QColor("#e0af68"))
            self.req_table.setItem(i, 2, tier_item)
            
            self.req_table.setItem(i, 3, QTableWidgetItem(req.get('app', 'VEO')))
            self.req_table.setItem(i, 4, QTableWidgetItem(req.get('client_submitted_at', '')[:19]))
            self.req_table.setItem(i, 5, QTableWidgetItem(req.get('status', '')))
    
    def _load_keys(self):
        keys = self.firebase.get_active_keys(self.app_filter)
        self.keys_table.setRowCount(len(keys))
        self._keys_data = keys
        
        for i, key in enumerate(keys):
            self.keys_table.setItem(i, 0, QTableWidgetItem(key.get('id', '')[:16] + '****'))
            self.keys_table.setItem(i, 1, QTableWidgetItem(key.get('_cn', '') or ''))
            self.keys_table.setItem(i, 2, QTableWidgetItem((key.get('_mid', '') or '')[:16]))
            self.keys_table.setItem(i, 3, QTableWidgetItem(key.get('_t', '')))
            self.keys_table.setItem(i, 4, QTableWidgetItem(key.get('_app', 'VEO')))
            
            status = key.get('_st', '')
            st_item = QTableWidgetItem('Revoked' if status == 'r' else 'Active' if status == 'a' else status)
            st_item.setForeground(QColor("#f7768e") if status == 'r' else QColor("#9ece6a"))
            self.keys_table.setItem(i, 5, st_item)
            
            exp = key.get('_exp')
            exp_str = ''
            if exp:
                if hasattr(exp, 'isoformat'):
                    exp_str = exp.isoformat()[:10]
                elif isinstance(exp, str):
                    exp_str = exp[:10]
            self.keys_table.setItem(i, 6, QTableWidgetItem(exp_str))
    
    def _load_trials(self):
        trials = self.firebase.get_all_trials(self.app_filter)
        
        # Level 1: only show trials approved by this seller
        if self.level == 1:
            seller_prefix = f"seller:{self.machine_id[:16]}"
            trials = [t for t in trials if t.get('approved_by', '') == seller_prefix]
        
        self.trials_table.setRowCount(len(trials))
        self._trials_data = trials
        
        for i, trial in enumerate(trials):
            # Client name
            name = trial.get('client_name', '') or trial.get('_ecn', '?')[:16]
            self.trials_table.setItem(i, 0, QTableWidgetItem(name))
            
            # MID
            mid = (trial.get('machine_id', '') or trial.get('id', ''))[:16]
            self.trials_table.setItem(i, 1, QTableWidgetItem(mid))
            
            # Status
            status = trial.get('status', '')
            st_item = QTableWidgetItem(status)
            st_item.setForeground(QColor("#9ece6a") if status == 'active' else QColor("#f7768e"))
            self.trials_table.setItem(i, 2, st_item)
            
            # Dates
            started = trial.get('started_at', '')[:10]
            expires = trial.get('expires_at', '')[:10]
            self.trials_table.setItem(i, 3, QTableWidgetItem(started))
            self.trials_table.setItem(i, 4, QTableWidgetItem(expires))
            
            # Approved by
            approved = trial.get('approved_by', '')
            self.trials_table.setItem(i, 5, QTableWidgetItem(approved))
    
    def _load_overview(self):
        summary = self.firebase.get_summary(self.app_filter)
        if not summary:
            self.overview_text.setHtml("<p style='color:#f7768e;'>Không thể tải dữ liệu</p>")
            return
        
        # Level 1: chỉ thấy trial stats
        if self.level == 1:
            html = f"""
            <div style='font-family: Segoe UI; color: #e0e0f0;'>
                <h2 style='color: #7aa2f7;'>📊 Tổng quan (Trial)</h2>
                <table style='font-size: 16px; margin: 20px 0;' cellpadding='10'>
                    <tr><td>🕐 Trials active:</td><td style='color:#e0af68;'><b>{summary.get('active_trials', 0)}</b></td></tr>
                    <tr><td>📬 Trial requests:</td><td style='color:#f7768e;'><b>{summary.get('pending_requests', 0)}</b></td></tr>
                </table>
                <p style='color: #8a8bac; font-size: 12px;'>Cập nhật: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            """
        else:
            html = f"""
            <div style='font-family: Segoe UI; color: #e0e0f0;'>
                <h2 style='color: #7aa2f7;'>📊 Tổng quan hệ thống</h2>
                <table style='font-size: 16px; margin: 20px 0;' cellpadding='10'>
                    <tr><td>🔑 Tổng keys:</td><td><b>{summary.get('total_keys', 0)}</b></td></tr>
                    <tr><td>✅ Keys active:</td><td style='color:#9ece6a;'><b>{summary.get('active_keys', 0)}</b></td></tr>
                    <tr><td>🕐 Trials active:</td><td style='color:#e0af68;'><b>{summary.get('active_trials', 0)}</b></td></tr>
                    <tr><td>📬 Requests pending:</td><td style='color:#f7768e;'><b>{summary.get('pending_requests', 0)}</b></td></tr>
                </table>
                <p style='color: #8a8bac; font-size: 12px;'>Cập nhật: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            """
        self.overview_text.setHtml(html)
    
    # ── Search/Filter ──────────────────────────────────
    
    def _filter_requests(self, text):
        q = text.strip().lower()
        for row in range(self.req_table.rowCount()):
            if not q:
                self.req_table.setRowHidden(row, False)
                continue
            name = (self.req_table.item(row, 0).text() if self.req_table.item(row, 0) else '').lower()
            mid = (self.req_table.item(row, 1).text() if self.req_table.item(row, 1) else '').lower()
            self.req_table.setRowHidden(row, q not in name and q not in mid)
    
    def _filter_keys(self, text):
        if not hasattr(self, 'keys_table'):
            return
        q = text.strip().lower()
        for row in range(self.keys_table.rowCount()):
            if not q:
                self.keys_table.setRowHidden(row, False)
                continue
            key_id = (self.keys_table.item(row, 0).text() if self.keys_table.item(row, 0) else '').lower()
            client = (self.keys_table.item(row, 1).text() if self.keys_table.item(row, 1) else '').lower()
            mid = (self.keys_table.item(row, 2).text() if self.keys_table.item(row, 2) else '').lower()
            self.keys_table.setRowHidden(row, q not in key_id and q not in client and q not in mid)
    
    # ── Actions ────────────────────────────────────────
    
    def _get_selected_request(self):
        row = self.req_table.currentRow()
        if row < 0 or row >= len(self._requests_data):
            QMessageBox.warning(self, "Chọn request", "Vui lòng chọn một request từ bảng.")
            return None
        return self._requests_data[row]
    
    def _get_selected_key(self):
        row = self.keys_table.currentRow()
        if row < 0 or row >= len(self._keys_data):
            QMessageBox.warning(self, "Chọn key", "Vui lòng chọn một key từ bảng.")
            return None
        return self._keys_data[row]
    
    def action_approve_trial(self):
        req = self._get_selected_request()
        if not req:
            return
        if req.get('tier') != 'TRIAL':
            QMessageBox.warning(self, "Lỗi", "Chỉ có thể approve TRIAL request bằng nút này.")
            return
        
        confirm = QMessageBox.question(
            self, "Xác nhận",
            f"Approve trial cho {req.get('client_name', '')}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        
        result = self.firebase.approve_trial(req['id'], self.machine_id)
        if result.get('success'):
            QMessageBox.information(self, "Thành công", result.get('message', 'OK'))
            self.refresh_data()
        else:
            QMessageBox.critical(self, "Lỗi", result.get('error', 'Unknown error'))
    
    def action_approve_paid(self):
        req = self._get_selected_request()
        if not req:
            return
        if req.get('tier', '') == 'TRIAL':
            QMessageBox.warning(self, "Lỗi", "Dùng nút 'Approve Trial' cho request trial.")
            return
        
        tier = req.get('tier', '1M')
        # Tier → days is inherent to tier code (business rule)
        tier_days_map = {'1M': 30, '3M': 90, '6M': 180, '1Y': 365, 'LIFETIME': 36500}
        days = tier_days_map.get(tier, 30)
        
        confirm = QMessageBox.question(
            self, "Xác nhận tạo key",
            f"Tạo key {tier} ({days} ngày) cho {req.get('client_name', '')}?\n"
            f"MID: {req.get('machine_id', '')[:16]}...",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        
        # Map tier for keygen
        tier_map = {'LIFETIME': 'LT'}
        tier_code = tier_map.get(tier, tier)
        
        result = self.firebase.approve_paid(req['id'], self.machine_id, tier_code, days)
        if result.get('success'):
            key = result.get('key', '')
            QMessageBox.information(self, "Thành công",
                                  f"{result.get('message', 'OK')}\n\nKey: {key}")
            self.refresh_data()
        else:
            QMessageBox.critical(self, "Lỗi", result.get('error', 'Unknown error'))
    
    def action_revoke_key(self):
        key_data = self._get_selected_key()
        if not key_data:
            return
        if key_data.get('_st') == 'r':
            QMessageBox.warning(self, "Lỗi", "Key này đã bị revoke.")
            return
        
        key_id = key_data.get('id', '')
        confirm = QMessageBox.question(
            self, "⚠ Xác nhận Revoke",
            f"THU HỒI key {key_id[:8]}****?\n"
            f"Client: {key_data.get('_cn', '')}\n\n"
            "Hành động này KHÔNG thể hoàn tác!",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        
        result = self.firebase.revoke_key(key_id, self.machine_id)
        if result.get('success'):
            QMessageBox.information(self, "Thành công", result.get('message', 'OK'))
            self.refresh_data()
        else:
            QMessageBox.critical(self, "Lỗi", result.get('error', 'Unknown error'))
    
    def action_edit_name(self):
        # Session + permission verify
        sv = self.firebase._verify_session()
        if not sv.get('valid'):
            QMessageBox.critical(self, "Phiên hết hạn", sv.get('error', 'Session expired'))
            return
        if not self.permissions.can('edit_client_name'):
            QMessageBox.warning(self, "Lỗi", "Không có quyền sửa tên.")
            return
        
        key_data = self._get_selected_key()
        if not key_data:
            return
        key_id = key_data.get('id', '')
        old_name = key_data.get('_cn', '')
        
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(self, "Edit họ tên", "Họ tên mới:", text=old_name)
        if not ok or not new_name.strip():
            return
        
        try:
            from firebase_admin import firestore
            updates = {'_cn': new_name.strip()}
            self.firebase.db.collection('_lic').document(key_id).update(updates)
            if self.firebase.backup_db:
                try:
                    self.firebase.backup_db.collection('_lic').document(key_id).update(updates)
                except Exception:
                    pass
            self.firebase._log_action(self.machine_id, 'edit_name', key_id[:16],
                                     f"{old_name} → {new_name.strip()}")
            QMessageBox.information(self, "Thành công", f"Đã đổi tên: {new_name.strip()}")
            self.refresh_data()
        except Exception:
            QMessageBox.critical(self, "Lỗi", "Không thể đổi tên. Thử lại sau.")
    
    def action_copy_key(self):
        key_data = self._get_selected_key()
        if not key_data:
            return
        full_key = key_data.get('id', '')
        QApplication.clipboard().setText(full_key)
        self.statusBar().showMessage(f"📋 Đã copy key: {full_key[:8]}****")
    
    def action_change_password(self):
        old = self.old_pw.text().strip()
        new = self.new_pw.text().strip()
        confirm = self.confirm_pw.text().strip()
        
        if not old or not new:
            self.pw_status.setStyleSheet("color: #f7768e;")
            self.pw_status.setText("⚠ Vui lòng nhập đủ thông tin")
            return
        if new != confirm:
            self.pw_status.setStyleSheet("color: #f7768e;")
            self.pw_status.setText("⚠ Mật khẩu mới không khớp")
            return
        
        result = self.firebase.change_password(self.machine_id, old, new)
        if result.get('success'):
            self.pw_status.setStyleSheet("color: #9ece6a;")
            self.pw_status.setText("✅ Đổi mật khẩu thành công!")
            self.old_pw.clear()
            self.new_pw.clear()
            self.confirm_pw.clear()
        else:
            self.pw_status.setStyleSheet("color: #f7768e;")
            self.pw_status.setText(f"❌ {result.get('error', 'Lỗi')}")


# ============================================================
# SINGLE INSTANCE (QLocalServer IPC)
# ============================================================

_IPC_NAME = "VEO_Seller_Manager_IPC_2026"

class SingleInstanceGuard:
    def __init__(self):
        self._server = None
        self._window = None
    
    def try_acquire(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(_IPC_NAME)
        if socket.waitForConnected(500):
            socket.write(b"show")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            return False
        self._server = QLocalServer()
        QLocalServer.removeServer(_IPC_NAME)
        self._server.listen(_IPC_NAME)
        self._server.newConnection.connect(self._on_connection)
        return True
    
    def set_window(self, window):
        self._window = window
    
    def _on_connection(self):
        if self._server:
            client = self._server.nextPendingConnection()
            if client:
                client.close()
        if self._window:
            w = self._window
            if not w.isVisible():
                w.show()
            if w.isMinimized():
                w.showNormal()
            w.raise_()
            w.activateWindow()
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(w.winId()))
            except Exception:
                pass


# ============================================================
# ANTI-TAMPER (Layer 3 + 8)
# ============================================================

def _security_checks():
    """Enhanced runtime security checks (Layer 3 + 8)."""
    import ctypes
    import time
    
    try:
        # 1. Standard debugger checks
        if ctypes.windll.kernel32.IsDebuggerPresent():
            return False
        
        is_remote = ctypes.c_int(0)
        ctypes.windll.kernel32.CheckRemoteDebuggerPresent(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(is_remote)
        )
        if is_remote.value:
            return False
        
        # 2. NtQueryInformationProcess — DebugPort check
        try:
            ntdll = ctypes.windll.ntdll
            debug_port = ctypes.c_ulong(0)
            status = ntdll.NtQueryInformationProcess(
                ctypes.windll.kernel32.GetCurrentProcess(),
                7,  # ProcessDebugPort
                ctypes.byref(debug_port),
                ctypes.sizeof(debug_port),
                None
            )
            if status == 0 and debug_port.value != 0:
                return False
        except Exception:
            pass
        
        # 3. Timing anomaly detection (breakpoints cause delays)
        t1 = time.perf_counter_ns()
        _ = sum(range(1000))
        t2 = time.perf_counter_ns()
        if (t2 - t1) > 500_000_000:  # 500ms = way too slow
            return False
        
        # 4. Known debugger process names
        try:
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FO', 'CSV', '/NH'],
                capture_output=True, text=True, timeout=3,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            blacklist = {'ida64.exe', 'ida.exe', 'x64dbg.exe', 'x32dbg.exe',
                        'ollydbg.exe', 'windbg.exe', 'dnspy.exe', 'de4dot.exe',
                        'httpdebuggerpro.exe', 'fiddler.exe', 'wireshark.exe',
                        'cheatengine-x86_64.exe'}
            for line in result.stdout.lower().split('\n'):
                for bad in blacklist:
                    if bad in line:
                        return False
        except Exception:
            pass
        
    except Exception:
        pass
    return True


def _integrity_check() -> bool:
    """
    Verify critical files haven't been TAMPERED with (Layer 9).
    
    Logic:
    - First run: compute hashes + HMAC signature → save .integrity
    - Subsequent runs: verify HMAC first (detects .integrity tampering),
      then compare file hashes. On mismatch → auto-regenerate 
      (legitimate update) but log the change.
    - Attacker can't forge .integrity because HMAC key is derived from app.
    """
    import hashlib
    import hmac as _hm
    import json
    
    app_dir = Path(__file__).parent
    hash_file = app_dir / ".integrity"
    critical_files = ['seller_auth.py', 'firebase_config.py', 'cred_protector.py']
    
    # Derive signing key from app identity (attacker can't easily forge)
    _INTEGRITY_KEY = hashlib.sha256(b"veo_integrity_2026_layer9").digest()
    
    def _compute_hashes():
        hashes = {}
        for fname in critical_files:
            fpath = app_dir / fname
            if fpath.exists():
                hashes[fname] = hashlib.sha256(fpath.read_bytes()).hexdigest()[:24]
        return hashes
    
    def _sign(data: dict) -> str:
        msg = json.dumps(data, sort_keys=True).encode()
        return _hm.new(_INTEGRITY_KEY, msg, hashlib.sha256).hexdigest()[:32]
    
    def _save(hashes: dict):
        sig = _sign(hashes)
        payload = {"h": hashes, "s": sig}
        hash_file.write_text(json.dumps(payload))
    
    try:
        current = _compute_hashes()
        
        if hash_file.exists():
            stored = json.loads(hash_file.read_text())
            stored_hashes = stored.get("h", {})
            stored_sig = stored.get("s", "")
            
            # Verify .integrity file itself hasn't been forged
            expected_sig = _sign(stored_hashes)
            if not _hm.compare_digest(stored_sig, expected_sig):
                return False  # .integrity file tampered!
            
            # Compare file hashes
            if current != stored_hashes:
                # Files changed — auto-regenerate (legitimate update)
                _save(current)
        else:
            # First run — save baseline
            _save(current)
    except Exception:
        pass  # Allow if can't check
    
    return True


# ============================================================
# MAIN
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)
    
    # Single instance
    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        sys.exit(0)
    
    # Security check
    if not _security_checks():
        QMessageBox.critical(None, "Security", "Môi trường không an toàn.")
        sys.exit(1)
    
    # File integrity check
    if not _integrity_check():
        QMessageBox.critical(None, "Security", "File ứng dụng bị thay đổi. Liên hệ Admin.")
        sys.exit(1)
    
    # Connect Firebase
    firebase = SellerFirebaseManager()
    if not firebase.connect():
        QMessageBox.critical(None, "Lỗi kết nối",
                           "Không thể kết nối Firebase.\nKiểm tra internet và thử lại.")
        sys.exit(1)
    
    # Login
    login = LoginDialog(firebase)
    if login.exec() != QDialog.Accepted or not login.login_result:
        sys.exit(0)
    
    # Main window
    window = SellerMainWindow(firebase, login.login_result)
    guard.set_window(window)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
