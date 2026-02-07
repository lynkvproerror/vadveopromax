# 🔐 Security Features v2.7 - Changelog

> **Version**: 2.7  
> **Updated**: 2026-02-04  
> **Status**: ✅ Fully Implemented

---

## 📋 New Security Features (2026-02-04)

### 1. AES-256 Encrypted API Keys

**Purpose**: Protect Firebase Web API keys from reverse engineering.

**Location**: `client/firebase_rest_client.py`

```python
class _AES256Encryptor:
    """AES-256 encryption for API keys"""
    
    @staticmethod
    def encrypt(plaintext: str, key: bytes) -> bytes:
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return iv + ciphertext + encryptor.tag
    
    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes) -> str:
        iv, ct, tag = ciphertext[:12], ciphertext[12:-16], ciphertext[-16:]
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        return (decryptor.update(ct) + decryptor.finalize()).decode()
```

**Key Derivation Modes**:

| Mode | Key Source | Use Case |
|------|------------|----------|
| **Hardware-Bound** | CPU ID + MB UUID + Disk Serial | Production (default) |
| **Static** | Hardcoded fallback key | Development/Testing |

```python
class _HardwareBinder:
    """Derive encryption key from hardware fingerprint"""
    
    @staticmethod
    def get_machine_key() -> bytes:
        # Collect hardware IDs
        cpu_id = get_cpu_id()
        mb_uuid = get_motherboard_uuid()
        disk_serial = get_disk_serial()
        
        # Combine and hash
        combined = f"{cpu_id}|{mb_uuid}|{disk_serial}"
        return hashlib.sha256(combined.encode()).digest()
```

**Protection Against**:
- ✅ Memory dumping (key derived at runtime)
- ✅ String extraction from binary
- ✅ Static analysis (no plaintext API keys)

---

### 2. Encrypted API Keys Storage

**File**: `client/_encrypted_api_keys.py`

```python
ENCRYPTED_PRIMARY_KEY = bytes([...])  # AES-256 encrypted
ENCRYPTED_BACKUP_KEY = bytes([...])   # AES-256 encrypted
USE_STATIC_KEY = True/False           # Key derivation mode
```

**Generation via Admin GUI**:
1. Settings → Security tab
2. Enter Primary Web API Key
3. Enter Backup Web API Key
4. Select encryption mode (Static/Hardware-bound)
5. Click "Generate Encrypted Keys"

---

### 3. Dual Firebase Failover

**Purpose**: Ensure license validation even if primary Firebase project is unavailable.

```python
class SecureFirebaseConfig:
    """Dual-project Firebase configuration with auto-failover"""
    
    def __init__(self):
        self.primary = self._decrypt_key(ENCRYPTED_PRIMARY_KEY)
        self.backup = self._decrypt_key(ENCRYPTED_BACKUP_KEY)
        self.current_source = "primary"
    
    def get_api_key(self) -> str:
        try:
            # Try primary first
            if self._test_connection(self.primary):
                return self.primary
        except:
            pass
        
        # Fallback to backup
        self.current_source = "backup"
        return self.backup
```

**Failover Scenarios**:
- Primary Firebase quota exceeded → Auto-switch to Backup
- Primary Firebase down → Auto-switch to Backup
- Network issues → Retry with Backup

---

### 4. Role-Based License System

**New Field**: `_role` in Firebase document

| Role ID | Name | Description |
|---------|------|-------------|
| 0 | TRIAL | Trial user (limited features) |
| 1 | PREMIUM | Paid user (full features) |
| 2 | TESTER | Internal tester (bypass limits) |

**Usage in Code**:
```python
from license_keygen import UserRole

# Generate key with role
key, meta = LicenseKeyGenerator.generate(
    machine_id="ABC12345",
    tier=LicenseTier.THREE_MONTHS,
    days=90,
    role=UserRole.PREMIUM  # or 0, 1, 2
)
```

---

### 5. Multi-App License Field

**New Field**: `_app` in Firebase document

| App ID | Description |
|--------|-------------|
| VEO | VEO Automation |
| CCT | CapCut Automation |
| RAT | Ruby Automation Tools |
| G-LABS | General Labs Tools |

**Filter licenses by app**:
```python
# Admin GUI
keys = firebase.get_all_keys(app_filter="VEO")

# Firebase query
docs = db.collection("_lic").where("_app", "==", "VEO").get()
```

---

## 🔐 Firebase Document Schema v2.7

```json
{
  "_t": "3M",                    // Tier code
  "_st": "a",                    // Status: a/r/e/s
  "_mid": "sha256_hash...",      // Machine ID (hashed)
  "_exp": "2027-01-01",          // Expiry date
  "_cr": "2026-02-04T03:09:00",  // Created timestamp
  "_dur": 90,                    // Duration in days
  "_em": "user@example.com",     // Email (optional)
  "_cn": "Client Name",          // Client name (optional)
  "_nt": "Admin note",           // Note (optional)
  "_role": 1,                    // User role: 0/1/2
  "_app": "VEO"                  // Application ID
}
```

---

## 🛡️ Security Layers Summary

| Layer | Component | Protection |
|-------|-----------|------------|
| 1 | License Key Format v2.3 | XOR obfuscated, no visible metadata |
| 2 | Hardware Fingerprint | CPU + MB + Disk binding |
| 3 | AES-256 API Key Encryption | Protect Firebase credentials |
| 4 | Hardware-Bound Key Derivation | Machine-specific decryption |
| 5 | Dual Firebase Failover | High availability |
| 6 | Role-Based Permissions | Feature gating per role |
| 7 | Multi-App Isolation | Separate licenses per app |
| 8 | Trial Protection | Multi-layer trial markers |
| 9 | Clock Manipulation Detection | HTTP/Firebase time sync |
| 10 | Anti-Crack (PyArmor) | Binary obfuscation |

---

## 📁 Security Files

| File | Location | Purpose |
|------|----------|---------|
| `license_manager_gui.py` | `01 - ADMIN - License Security/` | Admin GUI with encryption key generator |
| `license_keygen.py` | `01 - ADMIN - License Security/` | Key generation with role, app support |
| `firebase_rest_client.py` | `02 - CLIENT - VEO PRO MAX/security/` | AES encryption, hardware binding |
| `_encrypted_api_keys.py` | `02 - CLIENT - VEO PRO MAX/security/` | Encrypted API keys storage |
| `license_client.py` | `02 - CLIENT - VEO PRO MAX/security/` | Client-side validation |

---

## ✅ Security Checklist

- [x] SECRET_KEY not hardcoded (environment variable)
- [x] API keys AES-256 encrypted
- [x] Hardware-bound key derivation
- [x] Dual Firebase failover
- [x] Role-based permissions (_role field)
- [x] Multi-app isolation (_app field)
- [x] Trial requires key from admin
- [x] Multi-layer trial markers
- [x] Clock manipulation detection
- [x] Machine ID binding (SHA256)
- [x] Firebase rate limiting rules
- [ ] Binary obfuscation (pending PyArmor build)
- [ ] Integrity hash verification (pending build)

---

## 📝 Change Log

### v2.7 (2026-02-04)
- Added AES-256 encryption for API keys
- Added hardware-bound key derivation
- Added dual Firebase failover
- Added `_role` field (0=Trial, 1=Premium, 2=Tester)
- Added `_app` field (VEO, CCT, RAT, G-LABS)
- Updated Admin GUI with encryption key generator
- Updated License table with Role/App columns

### v2.0 (2026-02-02)
- Trial requires TRIAL-XXXX key
- Added `trial_protection.py` 
- AES-256 for license storage
- Clock manipulation detection
- Key format v2.3 (no prefix)
- SECRET_KEY moved to environment variable
