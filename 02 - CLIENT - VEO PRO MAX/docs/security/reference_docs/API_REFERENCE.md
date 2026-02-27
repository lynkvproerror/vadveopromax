# 📚 API Reference

> **Version**: 1.0  
> **Updated**: 2026-02-02

---

## 📋 Mục lục

1. [Client Module](#1-client-module)
   - [LicenseClient](#licenseclient)
   - [LicenseRequest](#licenserequest)
   - [TrialMarkerManager](#trialmarkermanager)
   - [HardwareFingerprint](#hardwarefingerprint)
2. [Admin Module](#2-admin-module)
   - [LicenseKeyGenerator](#licensekeygenerator)
   - [FirebaseManager](#firebasemanager)
   - [LicenseTier](#licensetier)
3. [GUI Module](#3-gui-module)
   - [LicenseManagerApp](#licensemanagerapp)
   - [Dialogs](#dialogs)

---

## 1. Client Module

> **Location:** `02 - CLIENT - VEO PRO MAX/security/`  
> **Import:** `from client import LicenseClient, TrialMarkerManager`

---

### LicenseClient

**File:** `client/license_client.py`

Class chính để validate license từ phía client.

```python
class LicenseClient:
    """
    Main license validation client for VEO applications.
    
    Handles:
    - Machine ID generation
    - License validation (local cache + Firebase)
    - Trial period management
    """
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__(config_path=None)` | `None` | Initialize client, optionally with custom config |
| `get_machine_id()` | `str` | Get full 64-char SHA256 machine ID |
| `get_display_machine_id()` | `str` | Get 8-char display version (e.g., "3946C15B") |
| `validate()` | `LicenseInfo` | Validate current license status |
| `validate_key(key: str)` | `LicenseInfo` | Validate specific license key |
| `activate(key: str)` | `ActivationResult` | Activate a new license key |
| `deactivate()` | `bool` | Remove current license |
| `get_cached_license()` | `dict|None` | Get cached license data |
| `check_online()` | `bool` | Check if online validation is possible |

#### Usage Examples

```python
from client import LicenseClient

# Initialize
client = LicenseClient()

# Get machine ID to send to admin
machine_id = client.get_display_machine_id()
print(f"Machine ID: {machine_id}")  # "3946C15B"

# Validate on app startup
info = client.validate()
if info.valid:
    print(f"License active: {info.tier.name}")
    print(f"Expires: {info.expires}")
else:
    print(f"Error: {info.message}")

# Activate new key (v2.3 format)
result = client.activate("F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B")
if result.success:
    print("Activation successful!")
```

#### LicenseInfo Class

```python
@dataclass
class LicenseInfo:
    valid: bool           # True if license is valid
    tier: LicenseTier     # TRIAL, ONE_MONTH, THREE_MONTHS, SIX_MONTHS, ONE_YEAR, LIFETIME
    expires: datetime     # Expiry date
    days_left: int        # Days until expiry
    message: str          # Status message
    
    @property
    def is_expired(self) -> bool:
        """Check if license is expired"""
        
    @property
    def is_trial(self) -> bool:
        """Check if using trial license"""
```

---

### LicenseRequest

**File:** `client/license_request.py`

Gửi yêu cầu cấp license lên Firebase.

```python
class LicenseRequest:
    """
    Submit license requests to Firebase for admin approval.
    
    Flow:
    1. Client submits request with machine_id, name, email
    2. Request saved to Firebase with status "pending"
    3. Admin approves/rejects via License Manager GUI
    4. Client checks request status
    """
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__()` | `None` | Initialize request client |
| `submit(name, email, duration=30)` | `dict` | Submit new request |
| `check_status(request_id)` | `dict` | Check request status |
| `get_approved_key(request_id)` | `str|None` | Get approved key if available |

#### Usage Examples

```python
from client import LicenseRequest

req = LicenseRequest()

# Submit request
result = req.submit(
    name="Nguyễn Văn A",
    email="client@example.com",
    duration=90  # 3 Tháng
)

if result['success']:
    request_id = result['request_id']
    print(f"Request submitted: {request_id}")
    
# Later: check status
status = req.check_status(request_id)
if status['status'] == 'approved':
    key = status['approved_key']
    print(f"Your key: {key}")
```

#### Response Format

```python
# submit() response
{
    "success": True,
    "request_id": "REQ_20260202_abc123",
    "message": "Request submitted successfully"
}

# check_status() response
{
    "status": "pending" | "approved" | "rejected",
    "approved_key": "F208-72DF-..." | None,
    "admin_note": "..." | None,
    "processed_at": datetime | None
}
```

---

### TrialMarkerManager

**File:** `client/trial_protection.py`

Quản lý trial period.

```python
class TrialMarkerManager:
    """
    Manage trial period with anti-tampering protection.
    
    Features:
    - Trial starts on first run
    - Data encrypted and stored in multiple locations
    - Detects time manipulation
    """
    
    TRIAL_DAYS = 7  # Default trial duration
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__(trial_days=7)` | `None` | Initialize with trial duration |
| `check_trial()` | `dict` | Check current trial status |
| `start_trial()` | `bool` | Start new trial (if not exists) |
| `get_remaining_days()` | `int` | Get remaining trial days |
| `is_trial_active()` | `bool` | Quick check if trial still active |
| `invalidate()` | `None` | Mark trial as used (for activation) |

#### Usage Examples

```python
from client.trial_protection import TrialMarkerManager

trial = TrialMarkerManager(trial_days=7)

# Check trial on startup
status = trial.check_trial()
if status['active']:
    print(f"Trial: {status['days_left']} days left")
else:
    print("Trial expired - please activate license")
    
# Check remaining days
days = trial.get_remaining_days()
if days <= 2:
    print("Trial ending soon!")
```

#### Trial Status Response

```python
{
    "active": True,           # Trial still valid
    "days_left": 5,           # Remaining days
    "started_at": datetime,   # When trial started
    "expires_at": datetime,   # When trial ends
    "used": False             # True if trial was already used
}
```

---

### HardwareFingerprint

**File:** `client/license_client.py`

Tạo machine ID từ hardware components.

```python
class HardwareFingerprint:
    """
    Generate unique machine fingerprint from stable hardware components.
    
    Components used (stable):
    - CPU ID
    - Motherboard Serial
    - Motherboard UUID
    - BIOS Serial
    - Disk Serial
    
    NOT used (unstable):
    - MAC Address
    - GPU
    - RAM
    """
```

#### Static Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_machine_id()` | `str` | Get full SHA256 hash (64 chars) |
| `get_display_id()` | `str` | Get short display ID (8 chars) |
| `get_all_components()` | `dict` | Get all hardware components |
| `verify_match(stored_hash)` | `bool` | Verify current matches stored |

#### Usage Examples

```python
from client.license_client import HardwareFingerprint

# Get machine ID
full_id = HardwareFingerprint.get_machine_id()
print(f"Full: {full_id}")  # 64 char hash

display_id = HardwareFingerprint.get_display_id()
print(f"Display: {display_id}")  # "3946C15B"

# Get components (for debugging)
components = HardwareFingerprint.get_all_components()
print(components)
# {
#     'cpu_id': 'BFEBFBFF000A0671',
#     'mb_serial': 'PF1234567',
#     'mb_uuid': '03000200-0400-0500-...',
#     'bios_serial': 'H1XYZ12345',
#     'disk_serial': 'WD-WCC123456'
# }
```

---

## 2. Admin Module

> **Location:** `01 - ADMIN - License Security/`  
> **Import:** `from admin import LicenseKeyGenerator, FirebaseManager`

---

### LicenseKeyGenerator

**File:** `admin/license_keygen.py`

Tạo license keys.

```python
class LicenseKeyGenerator:
    """
    Generate license keys with v2.3 obfuscated hex format.
    
    Key format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
    Example: F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B
    """
```

#### Static Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `generate(machine_id, duration)` | `tuple[str, dict]` | Generate key + metadata |
| `validate_format(key)` | `bool` | Check key format is valid |
| `calculate_checksum(data)` | `str` | Calculate checksum |

#### Usage Examples

```python
from admin.license_keygen import LicenseKeyGenerator

# Generate key (v2.3 format)
key, metadata = LicenseKeyGenerator.generate(
    machine_id="3946C15B...",
    duration=90  # 3 Tháng
)

print(f"Key: {key}")
# F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B

print(f"Metadata: {metadata}")
# {
#     'duration': 90,
#     'machine_id_hash': '...',
#     'expires': '2026-05-01T00:00:00',
#     'created': '2026-02-04T04:37:00'
# }

# Validate format
valid = LicenseKeyGenerator.validate_format("F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B")
print(valid)  # True
```

---

### LicenseTier

**File:** `admin/license_keygen.py`

Enum định nghĩa các tiers.

```python
class LicenseTier(Enum):
    """VND Pricing Model - License Tiers"""
    TRIAL = "TRIA"           # 7 ngày - Miễn phí
    ONE_MONTH = "1M"         # 30 ngày - 300,000đ
    THREE_MONTHS = "3M"      # 90 ngày - 500,000đ
    SIX_MONTHS = "6M"        # 180 ngày - 800,000đ
    ONE_YEAR = "1Y"          # 365 ngày - 1,200,000đ
    LIFETIME = "LT"          # Vĩnh viễn - 3,000,000đ
    
    
    @classmethod
    def from_name(cls, name: str) -> 'LicenseTier':
        """Get tier from name string"""
```

#### Usage

```python
from admin.license_keygen import LicenseTier

# From name
tier = LicenseTier.from_name("THREE_MONTHS")
print(tier.value)  # "3M"

# Get tier info
tier = LicenseTier.ONE_YEAR
print(tier.name)   # "ONE_YEAR"
print(tier.value)  # "1Y"

# All tiers
for tier in LicenseTier:
    print(f"{tier.name}: {tier.value}")
# TRIAL: TRIA
# ONE_MONTH: 1M
# THREE_MONTHS: 3M
# SIX_MONTHS: 6M
# ONE_YEAR: 1Y
# LIFETIME: LT
```

---

### FirebaseManager

**File:** `admin/license_backend.py` hoặc `ctk_gui/license_manager_gui.py`

Quản lý Firebase operations.

```python
class FirebaseManager:
    """
    Firebase Firestore operations for license management.
    
    Collections:
    - _lic: License keys
    - _license_requests: Pending requests
    """
    
    COLLECTION = "_lic"
    REQUEST_COLLECTION = "_license_requests"
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__()` | `None` | Initialize manager |
| `connect()` | `bool` | Connect to Firebase |
| `find_credentials()` | `Path|None` | Find credentials file |
| **License Operations** | | |
| `get_all_keys()` | `list[dict]` | Get all license keys |
| `create_key(machine_id, tier, days, email, note, client_name)` | `dict` | Create new key |
| `revoke_key(key_id, reason)` | `bool` | Revoke a key |
| `delete_key(key_id)` | `bool` | Delete a key |
| `update_key(key_id, updates)` | `bool` | Update key fields |
| `get_summary()` | `dict` | Get statistics |
| **Cleanup** | | |
| `delete_expired_keys(include_revoked)` | `tuple[int, str]` | Delete expired with backup |
| **Requests** | | |
| `get_pending_requests()` | `list[dict]` | Get pending requests |
| `approve_request(request_id, tier, days)` | `tuple[bool, str]` | Approve and generate key |
| `reject_request(request_id, reason)` | `bool` | Reject request |

#### Usage Examples

```python
from admin.license_backend import FirebaseManager
# or
from ctk_gui.license_manager_gui import FirebaseManager

fm = FirebaseManager()

# Connect
if fm.connect():
    print("Connected to Firebase")
    
# Get all keys
keys = fm.get_all_keys()
for key in keys:
    print(f"{key['key']}: {key['tier']} - {key['status']}")
    
# Create new key
result = fm.create_key(
    machine_id="3946C15B",
    tier="PRO",
    days=365,
    email="client@example.com",
    client_name="Nguyễn Văn A"
)
print(f"Created: {result['key']}")

# Revoke
fm.revoke_key("F208-72DF-9B1D-4BF6-...", reason="Refund")

# Cleanup expired
deleted, backup_path = fm.delete_expired_keys(include_revoked=True)
print(f"Deleted {deleted} keys, backup: {backup_path}")
```

---

## 3. GUI Module

> **Location:** `01 - ADMIN - License Security/`  
> **Import:** `from ctk_gui import LicenseManagerApp`

---

### LicenseManagerApp

**File:** `ctk_gui/license_manager_gui.py`

Main GUI application class.

```python
class LicenseManagerApp(ctk.CTk):
    """
    CustomTkinter-based license manager GUI.
    
    Features:
    - View/search license keys
    - Create/edit/revoke keys
    - Manage pending requests
    - Cleanup expired keys
    """
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__()` | `None` | Initialize and show GUI |
| `refresh_keys()` | `None` | Reload keys from Firebase |
| `show_create_dialog()` | `None` | Open create key dialog |
| `show_edit_dialog()` | `None` | Open edit key dialog |
| `show_requests_dialog()` | `None` | Open requests dialog |
| `show_cleanup_dialog()` | `None` | Open cleanup dialog |
| `revoke_selected()` | `None` | Revoke selected key |
| `delete_selected()` | `None` | Delete selected key |
| `copy_selected_key()` | `None` | Copy key to clipboard |

#### Run GUI

```python
from ctk_gui.license_manager_gui import LicenseManagerApp

app = LicenseManagerApp()
app.mainloop()
```

---

### Dialogs

#### CreateKeyDialog

```python
class CreateKeyDialog(ctk.CTkToplevel):
    """Dialog for creating new license key"""
    
    # Fields:
    # - machine_id (required)
    # - client_name
    # - tier (VND pricing: Trial, 1 Tháng, 3 Tháng, 6 Tháng, 1 Năm, Vĩnh viễn)
    # - days (auto-set based on tier)
    # - email
```

#### EditKeyDialog

```python
class EditKeyDialog(ctk.CTkToplevel):
    """Dialog for editing existing license key"""
    
    # Editable fields:
    # - status (Active/Suspended/Revoked)
    # - email
    # - client_name
    # - admin_note
```

#### RequestsDialog

```python
class RequestsDialog(ctk.CTkToplevel):
    """Dialog for managing pending license requests"""
    
    # Actions:
    # - View pending requests
    # - Approve → generates key
    # - Reject → requires reason
```

#### CleanupDialog

```python
class CleanupDialog(ctk.CTkToplevel):
    """Dialog for cleaning up expired keys"""
    
    # Options:
    # - Delete expired only
    # - Include revoked keys
    # - Creates backup before deletion
```

---

## 🔗 Quick Import Reference

```python
# Client-side (ship with app)
from client import LicenseClient, TrialMarkerManager
from client.license_client import HardwareFingerprint, LicenseInfo
from client.license_request import LicenseRequest

# Admin-side (do not ship)
from admin import LicenseKeyGenerator, LicenseTier
from admin.license_backend import FirebaseManager

# GUI (do not ship)
from ctk_gui import LicenseManagerApp
```

---

*API Reference for VEO License System. Last updated: 2026-02-02*
