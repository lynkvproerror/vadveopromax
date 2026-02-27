# 🔐 License Protection System - Overview

> Split from LICENSE_PROTECTION_SYSTEM.md

**Version**: 2.3 (Updated Key Format)  
**Updated**: 2026-02-04

---

## 📋 Quick Navigation

| Document | Content |
|----------|---------|
| **This file** | Overview, licensing flow, admin commands |
| [LICENSE_TIERS_FEATURES.md](./LICENSE_TIERS_FEATURES.md) | Tier matrix, pricing, feature limits |
| [LICENSE_HARDWARE_FINGERPRINT.md](./LICENSE_HARDWARE_FINGERPRINT.md) | Machine ID, clone detection |
| [LICENSE_ANTI_CRACK.md](./LICENSE_ANTI_CRACK.md) | Code obfuscation, DLL injection protection |
| [LICENSE_ANTI_FAKE_SERVER.md](./LICENSE_ANTI_FAKE_SERVER.md) | Certificate pinning, RSA verification |
| [LICENSE_KEY_ALGORITHM.md](./LICENSE_KEY_ALGORITHM.md) | v2.3 key format specification |

---

## 🔑 Key Format v2.3

> [!IMPORTANT]
> **Format**: Pure obfuscated hex, no prefix, no visible metadata.

```
XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX

Ví dụ: F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B
```

| Component | Description |
|-----------|-------------|
| Format | 8 nhóm 4 ký tự hex |
| Machine ID | SHA256 hash (hidden) |
| Duration | Stored in Firebase only |
| Signature | HMAC-SHA256 |

---

## 📁 Implementation Files

| File | Purpose | 
|------|---------|
| `security/license_client.py` | Client-side: machine ID, activation, validation |
| `admin/license_admin.py` | Admin: generate keys, push to Firebase, revoke |
| `admin/license_keygen.py` | v2.3 key format and HMAC |
| `admin/license_backend.py` | Firebase connection |

> **Admin files** → `01 - ADMIN - License Security/`  
> **Client files** → `02 - CLIENT - VEO PRO MAX/security/`

---

## 🔄 Quy trình cấp phép (4 bước)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   CLIENT    │     │   ADMIN     │     │  FIREBASE   │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ 1. Gửi Machine ID │                   │
       │ ─────────────────>│                   │
       │                   │ 2. Tạo key từ:    │
       │                   │    MID + Tier     │
       │                   │    + Salt + HMAC  │
       │                   │ 3. Upload key     │
       │                   │ ─────────────────>│
       │ 4. Nhận key       │                   │
       │ <─────────────────│                   │
       │ 5. Nhập key → OK! │                   │
       └───────────────────────────────────────┘
```

---

## 🛠️ Admin Commands

```bash
# Tạo key cho client (v2.3 format)
python admin/license_admin.py create \\
    --machine-id 3946C15B \\
    --duration 90

# Output:
# ✅ Key: F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B
# ✅ Uploaded to Firebase
# ✅ Bound to machine: 3946C15B

# Xem thông tin key
python admin/license_admin.py check F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B

# Thu hồi key
python admin/license_admin.py revoke F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B \
    --reason "refund"
```

---

## 🔐 Client Integration

```python
from client import LicenseClient

class VEOApp:
    def __init__(self):
        self.license = LicenseClient()
    
    def on_startup(self):
        machine_id = self.license.get_display_machine_id()  # "3946C15B"
        info = self.license.validate()
        
        if info.valid:
            self.enable_features(info.tier)
        else:
            self.show_license_input()
    
    def on_activate(self, key: str):
        # Key format: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
        result = self.license.validate_key(key)
        if result.valid:
            self.show_success(f"Activated: {result.tier.name}")
```

---

## 🔥 Firebase Configuration

| Item | Value |
|------|-------|
| **Project ID** | `YOUR_FIREBASE_PROJECT_ID` |
| **Database** | Firestore |
| **Location** | `asia-southeast1` |
| **Plan** | Spark (Free) |

### Free Tier Limits

| Service | Limit | Est. Usage |
|---------|-------|------------|
| Reads | 50K/day | ~1K/day ✅ |
| Writes | 20K/day | ~100/day ✅ |
| Storage | 1 GB | ~10 MB ✅ |
