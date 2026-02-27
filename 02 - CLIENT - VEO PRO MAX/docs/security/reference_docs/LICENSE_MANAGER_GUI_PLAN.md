# License Manager GUI - Implementation Plan

> **Version**: 2.3 (Updated Key Format)  
> **Updated**: 2026-02-04

## Mục tiêu

Tạo công cụ GUI bằng CustomTkinter để quản lý license keys trên Firebase:
- Tạo key mới (v2.3 format - pure hex)
- Xem danh sách tất cả keys
- Xem chi tiết từng key
- Cập nhật thông tin key (gia hạn, đổi tier)
- Thu hồi/Xoá key

---

## UI Layout dự kiến

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ 🔐 VEO License Manager (v2.3)                                   [─] [□] [X]   │
├────────────────────────────────────────────────────────────────────────────────┤
│ [🔄 Refresh]  [➕ Create Key]  [🗑️ Revoke]  [📊 Summary]                        │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│ ┌──────────────────────────────────────────────────────────────────────────┐  │
│ │ KEY (v2.3 Pure Hex)           │ MID      │ TIER │ STATUS │ EXPIRES      │  │
│ ├───────────────────────────────┼──────────┼──────┼────────┼──────────────┤  │
│ │ F208-72DF-9B1D-4BF6-****-**** │ ****C15B │ PRO  │ ✅     │ 2027-01-20   │  │
│ │ A1B2-C3D4-E5F6-7890-****-**** │ ****CD34 │ BASI │ ✅     │ 2026-06-15   │  │
│ │ 1234-5678-90AB-CDEF-****-**** │ ****7ZAB │ TRIA │ ❌     │ 2026-03-01   │  │
│ └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│ ┌─────────────── Key Details ───────────────┐                                 │
│ │ Key: F208-72DF-9B1D-4BF6-661F-10F4...  │                                 │
│ │ Format: v2.3 (Pure Hex)                │                                 │
│ │ Machine ID: ****C15B (hash stored)     │                                 │
│ │ Tier: PRO                              │                                 │
│ │ Status: Active                         │                                 │
│ │ Created: 2026-01-20                    │                                 │
│ │ Expires: 2027-01-20                    │                                 │
│ │ Email: customer@example.com            │                                 │
│ │                                        │                                 │
│ │ [📋 Copy Key]  [✏️ Edit]  [🗑️ Revoke]  │                                 │
│ └────────────────────────────────────────┘                                 │
│                                                                                │
├────────────────────────────────────────────────────────────────────────────────┤
│ ✅ Connected to Firebase  │  Total: 3 keys  │  Active: 2  │  Expired: 1       │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
09_Security/
├── license_manager_gui.py       # Main GUI application (NEW)
├── license_manager_gui.spec     # PyInstaller spec (optional, for .exe)
├── license_keygen.py            # Key generation logic (existing)
├── license_admin.py             # Admin CLI tool (existing)
├── cleanup_expired_keys.py      # Cleanup script (existing)
└── 00_ADMIN/
    └── firebase-credentials.json
```

---

## Dependencies

```python
# requirements.txt
customtkinter>=5.2.0
firebase-admin>=6.0.0
```

---

## Core Components

### 1. Main Window (`LicenseManagerWindow`)

```python
class LicenseManagerWindow(CTk):
    """Main application window"""
    
    def __init__(self):
        # Setup UI
        # Connect to Firebase
        # Load initial data
    
    # Actions
    def refresh_keys(self)
    def create_key_dialog(self)
    def revoke_selected_key(self)
    def show_summary(self)
    
    # Table
    def load_keys_to_table(self)
    def on_key_selected(self)
    
    # Details panel
    def show_key_details(self, key_id)
    def copy_key_to_clipboard(self)
    def edit_key_dialog(self)
```

### 2. Create Key Dialog (`CreateKeyDialog`)

```python
class CreateKeyDialog(CTkToplevel):
    """Dialog for creating new license key"""
    
    # Inputs:
    # - Machine ID (required, text input)
    # - Tier (dropdown: TRIAL, BASIC, PRO, ENTERPRISE)
    # - Duration (spinbox: 7-365 days)
    # - Email (optional, text input)
    # - Note (optional, text area)
    
    def validate_inputs(self) -> bool
    def create_key(self) -> str
```

### 3. Edit Key Dialog (`EditKeyDialog`)

```python
class EditKeyDialog(CTkToplevel):
    """Dialog for editing existing key"""
    
    # Editable fields:
    # - Extends expiry date (date picker)
    # - Change tier (dropdown)
    # - Update note (text area)
    # - Change status (dropdown: active/suspended)
    
    def save_changes(self)
```

### 4. Firebase Manager (`FirebaseManager`)

```python
class FirebaseManager:
    """Handles all Firebase operations"""
    
    def connect(self) -> bool
    def get_all_keys(self) -> list
    def get_key_by_id(self, key_id) -> dict
    def create_key(self, machine_id, tier, days, email, note) -> str
    def update_key(self, key_id, updates: dict)
    def revoke_key(self, key_id, reason: str)
    def delete_key(self, key_id)
    def get_summary(self) -> dict
```

---

## Styling (Dark Theme)

```python
DARK_STYLESHEET = """
CTk {
    background-color: #1e1e2e;
}
CTkScrollableFrame (with CTkFrame rows) {
    background-color: #2d2d3d;
    color: #cdd6f4;
    gridline-color: #45475a;
    selection-background-color: #6c7086;
}
CTkButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-radius: 4px;
    padding: 8px 16px;
}
CTkButton:hover {
    background-color: #b4befe;
}
CTkEntry, CTkTextbox, CTkOptionMenu, CTkEntry (with validation) {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px;
}
"""
```

---

## Features Checklist

- [ ] Firebase connection with auto-reconnect
- [ ] Table view with sorting and filtering
- [ ] Create key with validation
- [ ] View key details
- [ ] Copy key to clipboard
- [ ] Edit key (extend, change tier)
- [ ] Revoke key with confirmation
- [ ] Delete key (permanent) with confirmation
- [ ] Status summary (active/revoked/expired counts)
- [ ] Dark theme UI
- [ ] Status bar with connection status
- [ ] Keyboard shortcuts (Ctrl+N new, Delete revoke, F5 refresh)

---

## Implementation Priority

1. **Phase 1**: Basic UI + Firebase connection + List keys
2. **Phase 2**: Create key dialog + Revoke
3. **Phase 3**: Key details + Edit dialog
4. **Phase 4**: Polish (themes, shortcuts, status bar)
