# 🔐 License Security System v2.0 - Complete Guide

> **Version**: 2.0  
> **Updated**: 2026-02-02  
> **Status**: ✅ Fully Implemented

---

## 📋 Overview

This document provides a complete overview of the VEO Pro Max license security system after the v2.0 security updates.

---

## 🔒 Security Features Implemented

### 1. License Key Format v2.3
```
F208-72DF-9B1D-4BF6-661F-3FEB-E3C5-0DA9
```
- Pure obfuscated hex, no visible metadata
- SECRET_KEY from environment variable (not hardcoded)
- XOR obfuscation for all components
- SHA256 checksum with full machine ID

### 2. Trial System v2.0
- User runs app → "License key required" → Admin gives Trial key
- 3 hidden file markers
- 2 Windows Registry keys
- Firebase backup
- Clock manipulation detection

### 3. Local Storage Encryption
- AES-256 with machine-bound key (PBKDF2)

---

## 📁 File Structure

### 🔴 Admin Tools (`01 - ADMIN - License Security/`) — KHÔNG ship
```
01 - ADMIN - License Security/
├── license_manager_gui.py   # Admin GUI for key management
├── license_keygen.py        # v2.3 key generation (HMAC-SHA256)
├── license_admin.py         # Admin CLI
├── license_backend.py       # Firebase Admin SDK backend
├── firebase_config.py       # Firebase configuration
├── obfuscate_client.py      # PyArmor obfuscation script
├── cleanup_expired_keys.py  # Maintenance script
└── _legacy_pyside6/         # Legacy GUI backup
```

### ✅ Client Code (`02 - CLIENT - VEO PRO MAX/`) — ship cùng app
```
02 - CLIENT - VEO PRO MAX/
├── security/                    # Full source / specification
│   ├── license_client.py        # v2.2 - AES-256, HMAC, HW fingerprint (32KB)
│   ├── firebase_rest_client.py  # Firebase REST API + AES encryption (17KB)
│   ├── trial_protection.py      # Multi-layer trial protection (14KB)
│   ├── license_request.py       # License request submission to Firebase (14KB)
│   ├── permissions.py           # Role-based feature gating
│   ├── _encrypted_api_keys.py   # AES-256 encrypted Firebase API keys
│   └── _encrypted_keys.py       # Encrypted key storage
│
└── services/                    # Stripped-down app adapter layer
    ├── license_client.py        # Simplified license client (10KB)
    ├── firebase_rest_client.py  # Simplified Firebase client
    ├── permissions.py           # App-layer permissions
    └── image_library.py         # Image library service
```

> **Import pattern:** App code imports from `services/` (adapter layer).
> Full security logic lives in `security/` (source of truth).

### 📄 Documentation (`00 - Documentation/05_Security/docs/`)
```
05_Security/docs/
├── LICENSE_KEY_ALGORITHM.md
├── LICENSE_SECURITY_OVERVIEW.md   ← This file
├── TRIAL_TIME_PROTECTION.md
├── WORKFLOW_ANTI_CRACK_PROTECTION.md
├── WORKFLOW_LICENSE_ISSUANCE.md
├── WORKFLOW_LICENSE_SUPPORT.md
├── API_REFERENCE.md
├── FIREBASE_LICENSE_GUIDE.md
├── FIREBASE_CREDENTIALS_GUIDE.md
├── DEV_SETUP_GUIDE.md
└── CLIENT_INTEGRATION_GUIDE.md    ← NEW
```

---

## 🔑 Key Formats Supported

| Format | Example | Use Case |
|--------|---------|----------|
| v2.3 (obfuscated) | `F208-72DF-9B1D-4BF6-661F-3FEB-E3C5-0DA9` | Production |
| Trial | `TRIAL-ABCD-1234-5678` | Trial activation |
| Legacy | `VEOAUTO-XXXX-XXXX-XXXX-XXXX` | Backward compatibility |

---

## 🛡️ Anti-Crack Protections

### Layer 1: Trial Protection
- **File Markers**: 3 hidden locations
  - `%USERPROFILE%/.veoauto/.trial`
  - `%APPDATA%/VEO/.trial.dat`
  - `%LOCALAPPDATA%/VEO/trial.bin`
- **Registry Markers**: 2 locations
  - `HKCU\Software\VEO\Trial`
  - `HKCU\Software\Classes\.veo\Shell`
- **Firebase Backup**: `_trials/{machine_id_hash}`

### Layer 2: Clock Manipulation Detection
- HTTP headers time (Google/Cloudflare)
- Firebase server timestamp
- 5-minute drift tolerance
- Automatic correction

### Layer 3: Key Security
- SECRET_KEY in environment variable
- PBKDF2-derived AES key (machine-bound)
- Firebase validation required

### Layer 4: Binary Integrity (pending build)
- PyArmor obfuscation
- EXE hash verification
- Tampering detection

---

## 🔧 Setup Instructions

### 1. Generate Secret Key
```bash
python -c "import secrets; print(secrets.token_hex(16))"
# Output: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6
```

### 2. Set Environment Variable
```batch
:: Windows (permanent)
setx VEO_LICENSE_SECRET "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

:: Verify
echo %VEO_LICENSE_SECRET%
```

### 3. Install Dependencies
```bash
pip install cryptography firebase-admin
```

### 4. Test License System
```python
from license_client import LicenseClient

client = LicenseClient()
print(f"Machine ID: {client.get_display_machine_id()}")

info = client.validate()
print(f"Status: {'Valid' if info.valid else 'Invalid'}")
print(f"Error: {info.error}")
```

---

## 📊 Admin Commands

### Generate License Key
```python
from license_keygen import ObfuscatedKeyGenerator

# Generate license for 90 days (3 Tháng)
key, meta = ObfuscatedKeyGenerator.generate(
    machine_id="USER_MACHINE_ID_HERE",
    duration_days=90
)
print(f"Key: {key}")  # F208-72DF-9B1D-...
```

### Generate Trial Key
```python
import secrets
trial_key = f"TRIAL-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
print(f"Trial Key: {trial_key}")  # TRIAL-A1B2-C3D4-E5F6
```

### Activate Trial (User Side)
```python
from license_client import LicenseClient

client = LicenseClient()
result = client.activate_trial("TRIAL-A1B2-C3D4-E5F6")
print(f"Activated: {result.valid}")
```

---

## 🔐 Security Checklist

- [x] SECRET_KEY not hardcoded
- [x] Trial requires key from admin
- [x] Multi-layer trial markers
- [x] Clock manipulation detection
- [x] AES-256 for local storage
- [x] Machine ID binding
- [x] Firebase rate limiting
- [ ] Binary obfuscation (pending PyArmor build)
- [ ] Integrity hash verification (pending build)

---

## 📝 Change Log

### v2.0 (2026-02-02)
- Trial now requires TRIAL-XXXX key
- Added `trial_protection.py` with multi-layer protection
- AES-256 encryption for license storage
- Clock manipulation detection
- Key format v2.3 (no prefix)
- SECRET_KEY moved to environment variable
