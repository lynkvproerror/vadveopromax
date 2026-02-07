# 🔗 Client Integration Guide — Security vào VEO Pro Max

> **Version**: 1.0  
> **Updated**: 2026-02-07  
> **Purpose**: Hướng dẫn tích hợp security logic vào client app

---

## 📋 Tổng quan

Document này mô tả cách security code được tích hợp vào app client, bao gồm:
- Import pattern (`services/` vs `security/`)
- Startup flow (license check → feature unlock)
- Runtime enforcement
- Firebase interaction protocol

---

## 1. Architecture: `services/` vs `security/`

### Hai layer riêng biệt

```
┌──────────────────────────────────────────────────────────────────┐
│                        APP CODE                                   │
│   core/app_controller.py, core/settings_controller.py             │
│   ui/tabs/tab_*.py                                                │
│                                                                    │
│   ⬇️ import from services/ (ONLY)                                │
├──────────────────────────────────────────────────────────────────┤
│                    services/ (Adapter Layer)                       │
│   ┌─────────────┐  ┌──────────────────┐  ┌──────────────┐       │
│   │LicenseClient│  │FirebaseRESTClient│  │PermissionsSys│       │
│   │  (10KB)     │  │                  │  │              │       │
│   └─────────────┘  └──────────────────┘  └──────────────┘       │
│   Simplified API for app consumption                              │
├──────────────────────────────────────────────────────────────────┤
│                    security/ (Source of Truth)                     │
│   ┌─────────────┐  ┌──────────────────┐  ┌──────────────┐       │
│   │LicenseClient│  │FirebaseRESTClient│  │TrialMarker   │       │
│   │  v2.2 (32KB)│  │  AES-256 (17KB)  │  │Manager (14KB)│       │
│   └─────────────┘  └──────────────────┘  └──────────────┘       │
│   ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐      │
│   │LicenseRequest    │  │_encrypted    │  │permissions.py│      │
│   │  (14KB)          │  │_api_keys.py  │  │              │      │
│   └──────────────────┘  └──────────────┘  └──────────────┘      │
│   Full security logic + crypto + hardware fingerprint             │
└──────────────────────────────────────────────────────────────────┘
```

### Import rules

```python
# ✅ CORRECT — App code imports from services/
from services.license_client import LicenseClient, LicenseInfo
from services.permissions import PermissionsSystem, Role, Feature

# ❌ WRONG — App code should NOT import from security/ directly
from security.license_client import LicenseClient  # Don't do this
```

### Khi nào dùng cái nào?

| Layer | Dùng khi | Ví dụ |
|-------|---------|-------|
| `services/` | Build app, UI integration | `app_controller.py`, `tab_settings.py` |
| `security/` | Phát triển security logic, audit | Thay đổi crypto, thêm protection layer |

---

## 2. App Startup Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    APP STARTUP SEQUENCE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. main.py → AppController.__init__()                           │
│     │                                                            │
│     ▼                                                            │
│  2. from services.license_client import LicenseClient            │
│     license_client = LicenseClient(storage_dir=config_dir)       │
│     │                                                            │
│     ▼                                                            │
│  3. license_client.validate_license(saved_key)                   │
│     │                                                            │
│     ├─── Has saved key? ─── YES ──→ Validate locally + Firebase  │
│     │                                    │                       │
│     │                                    ├── Valid → LICENSED ✅  │
│     │                                    └── Invalid → TRIAL ⏳  │
│     │                                                            │
│     └─── No saved key? ── NO ──→ Check trial status              │
│                                    │                             │
│                                    ├── Trial valid → TRIAL ⏳    │
│                                    └── Trial expired → BLOCKED 🔒│
│     │                                                            │
│     ▼                                                            │
│  4. from services.permissions import PermissionsSystem            │
│     permissions = PermissionsSystem(role=detected_role)           │
│     │                                                            │
│     ▼                                                            │
│  5. UI loads → Features enabled/disabled based on role            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Actual import in code

```python
# core/app_controller.py
from services.license_client import LicenseClient
from services.permissions import PermissionsSystem, Role, Feature

class AppController:
    def __init__(self):
        self.license_client = LicenseClient()
        self._check_license()
    
    def _check_license(self):
        info = self.license_client.license_info
        if info.is_valid:
            role = Role.from_tier(info.tier)
        else:
            role = Role.TRIAL
        self.permissions = PermissionsSystem(role)
```

---

## 3. License Validation Flow (Firebase Protocol)

```
┌─────────────────────────────────────────────────────────────────┐
│                 LICENSE VALIDATION PROTOCOL                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  CLIENT                          FIREBASE (Firestore)            │
│  ──────                          ─────────────────────           │
│                                                                   │
│  1. User enters key                                              │
│     "F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B"                  │
│     │                                                            │
│     ▼                                                            │
│  2. GET _lic/{key}              →  Firestore lookup              │
│     (key = document ID)             Collection: _lic             │
│     │                                                            │
│     ▼                                                            │
│  3. Response:                                                    │
│     {                                                            │
│       "_t": "3M",               // Tier code                    │
│       "_st": "a",               // Status: a=active             │
│       "_mid": "sha256_hash...", // Machine ID hash              │
│       "_exp": "2027-01-01",     // Expiry                       │
│       "_dur": 90,               // Duration days                │
│       "_role": 1,               // 0=Trial, 1=Premium, 2=Tester │
│       "_app": "VEO"             // Application ID               │
│     }                                                            │
│     │                                                            │
│     ▼                                                            │
│  4. Client validates:                                            │
│     ✓ _st == "a" (active)                                       │
│     ✓ _mid == SHA256(local_machine_id)                          │
│     ✓ _exp > today                                              │
│     ✓ _app == "VEO"                                             │
│     │                                                            │
│     ▼                                                            │
│  5. If valid:                                                    │
│     → Save encrypted to local cache (.veo_license)              │
│     → Unlock features per tier                                   │
│     → Set role from _role field                                  │
│                                                                   │
│  6. If invalid:                                                  │
│     → Show error message                                         │
│     → Keep current state (trial or locked)                       │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Firebase Collections Used

| Collection | Purpose | Access |
|------------|---------|--------|
| `_lic` | License keys (document ID = key) | Client: READ only |
| `_license_requests` | Pending license requests | Client: CREATE only |
| `_trials` | Trial marker backup | Client: READ/WRITE own |

---

## 4. License Request Flow (`license_request.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│                  LICENSE REQUEST FLOW                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  CLIENT (New User)              FIREBASE          ADMIN          │
│  ─────────────────              ────────          ─────          │
│                                                                   │
│  1. User fills form:                                             │
│     - Name, Email, Phone                                         │
│     - Requested tier                                             │
│     - Machine ID (auto)                                          │
│     │                                                            │
│     ▼                                                            │
│  2. LicenseRequestClient                                         │
│     .submit_request(info)                                        │
│     │                                                            │
│     ├── Validate inputs (InputValidator)                         │
│     ├── Check duplicate (same machine_id)                        │
│     │                                                            │
│     ▼                                                            │
│  3. POST → _license_requests/{machine_id_hash}                   │
│     {                                    │                       │
│       "client_name": "Nguyễn Văn A",    │                       │
│       "email": "...",                    │                       │
│       "phone": "...",                    ▼                       │
│       "requested_tier": "3M",      Admin sees in GUI             │
│       "machine_id": "3946C15B",    │                             │
│       "status": "pending"          │                             │
│     }                              ▼                             │
│                                Admin approves                    │
│     │                          → Generates key                   │
│     │                          → Updates status                  │
│     ▼                              │                             │
│  4. Client polls:                  │                             │
│     poll_result()                  ▼                             │
│     │                          Document updated:                 │
│     │                          status="approved"                 │
│     │                          approved_key="F208-..."           │
│     ▼                                                            │
│  5. Client receives key                                          │
│     → Auto-activate                                              │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `LicenseRequestClient` | `security/license_request.py` | Submit + poll requests |
| `LicenseRequest` | `security/license_request.py` | Request data structure |
| `RequestResult` | `security/license_request.py` | Operation result |
| `InputValidator` | `security/license_request.py` | Sanitize user input |
| `RequestStatus` | `security/license_request.py` | `pending` / `approved` / `rejected` |

---

## 5. Feature Gating (Runtime Enforcement)

```python
# core/settings_controller.py
from services.permissions import PermissionsSystem, Role, Feature

class SettingsController:
    def __init__(self, license_info):
        role = Role.from_tier(license_info.tier)
        self.permissions = PermissionsSystem(role)
    
    def can_use_feature(self, feature: Feature) -> bool:
        return self.permissions.has_access(feature)
```

### Role → Feature Matrix

| Feature | TRIAL (0) | PREMIUM (1) | TESTER (2) |
|---------|:---------:|:-----------:|:----------:|
| Basic generation | ✅ | ✅ | ✅ |
| HD quality | ❌ | ✅ | ✅ |
| Batch processing | ❌ | ✅ | ✅ |
| Dev Console | ❌ | ❌ | ✅ |
| Beta features | ❌ | ❌ | ✅ |
| Advanced settings | ❌ | ✅ | ✅ |

### UI enforcement

```python
# ui/tabs/tab_*.py
if not controller.permissions.has_access(Feature.BATCH):
    batch_button.setEnabled(False)
    batch_button.setToolTip("🔒 Premium feature - Upgrade to unlock")
```

---

## 6. Local Cache & Encryption

License data được cache encrypted local để hoạt động offline:

```
02 - CLIENT - VEO PRO MAX/
└── config/
    ├── .veo_license          ← AES-256 encrypted license cache
    ├── .veo_trial             ← Trial marker (hidden)
    └── usage_stats.json       ← Generation/download counts
```

### Encryption layers

| Layer | Method | Key Source |
|-------|--------|-----------|
| License cache | AES-256 (Fernet) | PBKDF2 from machine ID |
| HMAC integrity | HMAC-SHA256 | Hardware components |
| API keys | AES-256-GCM | Hardware-bound derivation |
| Trial markers | XOR obfuscation | Machine ID hash |

---

## 7. Error Handling

| Scenario | Client Behavior |
|----------|----------------|
| Firebase offline | Use local cache (grace period) |
| Invalid key format | Show format error, don't send to Firebase |
| Machine ID mismatch | Log security event, reject key |
| Key revoked (`_st: "r"`) | Clear local cache, show revoked message |
| Key expired (`_st: "e"`) | Show renewal prompt |
| Trial expired | Show license required dialog |

---

## Cross-References

| Topic | Document |
|-------|----------|
| Key algorithm | [LICENSE_KEY_ALGORITHM.md](LICENSE_KEY_ALGORITHM.md) |
| Trial protection | [TRIAL_TIME_PROTECTION.md](TRIAL_TIME_PROTECTION.md) |
| API Reference | [API_REFERENCE.md](API_REFERENCE.md) |
| Firebase setup | [FIREBASE_LICENSE_GUIDE.md](FIREBASE_LICENSE_GUIDE.md) |
| Anti-crack | [WORKFLOW_ANTI_CRACK_PROTECTION.md](WORKFLOW_ANTI_CRACK_PROTECTION.md) |
| Tiers & pricing | [LICENSE_TIERS_FEATURES.md](LICENSE_TIERS_FEATURES.md) |
