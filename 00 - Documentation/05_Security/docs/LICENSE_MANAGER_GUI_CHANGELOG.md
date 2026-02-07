# License Manager GUI - UI Fixes Changelog

> **Version**: 2.7  
> **Updated**: 2026-02-04

---

## Overview

Document này ghi lại tất cả các UI fixes và enhancements cho `license_manager_gui.py` (PySide6 Admin GUI).

---

## 🆕 Changes (2026-02-04)

### 1. Multi-App Support in Create Key Dialog

**File**: `license_manager_gui.py` - `CreateKeyDialog`

| Field | Before | After |
|-------|--------|-------|
| App | ❌ Missing | ✅ Dropdown: VEO, CCT, RAT, G-LABS |

**Code location**: Line 665-675

```python
# App (multi-app support)
self.app_combo = QComboBox()
apps = ["VEO", "CCT", "RAT", "G-LABS"]
self.app_combo.addItems(apps)
form.addRow("App:", self.app_combo)
```

---

### 2. Multi-App + Role in Request Approval UI

**File**: `license_manager_gui.py` - `RequestsDialog`

| Field | Before | After |
|-------|--------|-------|
| App | ❌ Missing | ✅ Dropdown after Role |
| days_spin max | 3650 | 36500 (100 years for LIFETIME) |
| on_tier_changed | ❌ Not implemented | ✅ Full sync logic |

**on_tier_changed() Logic**:
```python
def on_tier_changed(self, tier_text: str):
    # Duration mapping for each tier
    TIER_DURATION = {
        "TRIAL": 7, "ONE_MONTH": 30, "THREE_MONTHS": 90,
        "SIX_MONTHS": 180, "ONE_YEAR": 365, "LIFETIME": 36500
    }
    
    # Auto-set duration
    self.days_spin.setValue(TIER_DURATION[tier_text])
    
    # Lock duration for TRIAL/LIFETIME
    self.days_spin.setEnabled(tier_text not in ["TRIAL", "LIFETIME"])
    
    # Adjust role options
    if tier_text == "TRIAL":
        self.role_combo.addItems(["TRIAL (0)", "TESTER (2)"])
    else:
        self.role_combo.addItems(["PREMIUM (1)", "TESTER (2)"])
```

---

### 3. approve_request() Updated

**Before**:
```python
firebase.approve_request(req.get('id'), tier, days)
```

**After**:
```python
role_code = int(role_text.split("(")[1].rstrip(")"))
app = self.app_combo.currentText()
firebase.approve_request(req.get('id'), tier, days, role=role_code, app_id=app)
```

---

### 4. firebase.approve_request() Signature Updated

**Before**:
```python
def approve_request(self, request_id, tier, days, admin_email="admin")
```

**After**:
```python
def approve_request(self, request_id, tier, days, admin_email="admin", role=1, app_id="VEO")
```

**lic_data changes**:
```python
lic_data = {
    "_t": metadata['tier'],
    "_st": "a",
    "_role": role,     # 🆕 User role
    "_app": app_id,    # 🆕 Application
    ...
}
```

---

### 5. License Table Expanded to 8 Columns

**Before** (6 columns):
```
| Client | Key | Machine ID | Tier | Status | Expires |
```

**After** (8 columns):
```
| Client | Key | MID | Tier | Role | App | Status | Expires |
```

**Column Resizing**:
```python
header = self.table.horizontalHeader()
header.setSectionsMovable(True)                       # Drag to reorder
header.setSectionResizeMode(QHeaderView.Interactive)  # Drag to resize
header.setStretchLastSection(True)                    # Expires fills space
```

---

### 6. Details Panel Updated

**New fields added**:
- `self.detail_role` - Shows role: Trial/Premium/Tester
- `self.detail_app` - Shows app: VEO/CCT/RAT/G-LABS

**on_key_selected() update**:
```python
role_map = {0: "Trial", 1: "Premium", 2: "Tester"}
self.detail_role.setText(role_map.get(data.get('_role', 1)))
self.detail_app.setText(data.get('_app', 'VEO'))
```

---

### 7. EditKeyDialog Updated

**New editable fields**:
| Field | Type | Options |
|-------|------|---------|
| Role | QComboBox | TRIAL (0), PREMIUM (1), TESTER (2) |
| App | QComboBox | VEO, CCT, RAT, G-LABS |

**save_changes() now includes**:
```python
updates = {
    '_st': new_status,
    '_exp': new_expiry,
    '_nt': new_note,
    '_em': new_email,
    '_cn': new_client_name,
    '_role': new_role,  # 🆕
    '_app': new_app,    # 🆕
}
```

---

## 📋 Button Logic Status

All buttons connected to Firebase:

| Button | Method | Firebase API |
|--------|--------|--------------|
| 🔄 Refresh | `refresh_keys()` | `get_all_keys()` |
| ➕ Create Key | `create_key_dialog()` | `create_key()` |
| 🗑️ Revoke | `revoke_selected_key()` | `revoke_key()` |
| ❌ Delete | `delete_selected_key()` | `delete_key()` |
| 🧹 Cleanup | `cleanup_expired_dialog()` | `cleanup_expired()` |
| 📬 Requests | `show_requests_dialog()` | `get_pending_requests()` |
| 📊 Summary | `show_summary()` | `get_summary()` |
| ✅ APPROVE | `approve_request()` | `approve_request()` |
| ❌ REJECT | `reject_request()` | `reject_request()` |
| ✏️ Edit | `edit_key_dialog()` | `update_key()` |
| ⚡ Sync | `sync_databases()` | Batch sync |
| ✏️ Edit App | `edit_app()` | `migrate_app_name()` |

---

## 🗃️ Firebase Document Structure

```json
{
  "_t": "3M",           // Tier code
  "_st": "a",           // Status: a=active, r=revoked, e=expired, s=suspended
  "_mid": "3946...",    // Machine ID (hashed)
  "_exp": "2027-01-01", // Expiry date
  "_cr": "...",         // Created timestamp
  "_dur": 90,           // Duration in days
  "_em": "user@...",    // Email (optional)
  "_cn": "Client Name", // Client name (optional)
  "_nt": "Admin note",  // Note (optional)
  "_role": 1,           // User role: 0=Trial, 1=Premium, 2=Tester
  "_app": "VEO"         // Application: VEO, CCT, RAT, G-LABS
}
```

---

## ✅ Summary

| Feature | Status |
|---------|--------|
| App field in CreateKeyDialog | ✅ Implemented |
| App field in RequestsDialog | ✅ Implemented |
| Role/Duration sync in RequestsDialog | ✅ Implemented |
| Days spin max 36500 | ✅ Fixed |
| Role/App columns in table | ✅ Added |
| Role/App in Details Panel | ✅ Added |
| Role/App in EditKeyDialog | ✅ Added |
| Interactive column resize | ✅ Enabled |
| All buttons connected to Firebase | ✅ Verified |
