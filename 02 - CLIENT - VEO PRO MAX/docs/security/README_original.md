# 🔐 VEO Pro Max Security System v2.4

> **Last Updated**: 2026-02-04  
> **Security Level**: 9.5/10 (Enterprise-grade)

---

## 📂 Folder Structure

```
05_Security/
├── README.md                    # This file
├── SECURITY_AUDIT_REPORT.md     # Security audit findings
│
├── docs/                        # Technical documentation (18 files)
│   ├── LICENSE_OVERVIEW.md
│   ├── LICENSE_SECURITY_OVERVIEW.md
│   ├── LICENSE_KEY_ALGORITHM.md
│   ├── CLIENT_INTEGRATION_GUIDE.md  # 🆕 Integration flow
│   ├── TRIAL_TIME_PROTECTION.md
│   └── ...
```

> [!IMPORTANT]
> **Code placement**:
> - `01 - ADMIN - License Security/` — 🔴 Admin tools (license_manager_gui, license_keygen, firebase_config, obfuscate_client...) — **ngoài app, không ship**
> - `02 - CLIENT - VEO PRO MAX/security/` — ✅ Client validation (license_client, firebase_rest_client, permissions, trial_protection...) — **trong app, xử lý bảo mật phía client**

---

## 🏗️ Architecture Overview (v2.4)

```
┌──────────────────────────────────────────────────────────────┐
│                        ADMIN TOOL v2.4                        │
│                                                               │
│   firebase_config.py                                          │
│   ├── 🆕 Auto-Discovery: Scans all *.json files              │
│   ├── 🆕 No hardcoded folder names                           │
│   └── 🆕 No hardcoded project IDs                            │
│                                                               │
│   ┌─────────────────┐      ┌─────────────────┐               │
│   │ 🔥 PRIMARY      │ sync │ 💾 BACKUP       │               │
│   │ (auto-detected) │─────►│ (auto-detected) │               │
│   └─────────────────┘      └─────────────────┘               │
└──────────────────────────────────────────────────────────────┘
                              │
                              │ Firestore
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                        CLIENT APP v2.4                        │
│                                                               │
│   ┌─────────────────────────────────────────┐                │
│   │ firebase_rest_client.py                 │                │
│   │ • 🆕 AES-256 encryption (PBKDF2)        │                │
│   │ • Hardware-bound decryption             │                │
│   │ • Cross-validation (Primary vs Backup)  │                │
│   │ • No Admin SDK                          │                │
│   └─────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔐 Security Layers (v2.4)

| # | Layer | Status | Description |
|---|-------|--------|-------------|
| 1 | **AES-256 Encryption** | ✅ v2.4 | PBKDF2 key derivation (100k iterations) |
| 2 | **No Admin SDK** | ✅ Done | REST API only (read-only) |
| 3 | **Cross-validation** | ✅ Done | Primary vs Backup check |
| 4 | **Hardware Binding** | ✅ Done | Keys bound to machine |
| 5 | **Auto-Discovery** | ✅ v2.4 | No hardcoded paths |
| 6 | HMAC-SHA256 cache | ✅ v2.2 | 14-field signature |
| 7 | Clock tampering | ✅ v2.2 | Detects time rollback |
| 8 | Grace period | ✅ v2.2 | 3 days (reduced from 7) |
| 9 | PyArmor | ⏳ Ready | Before distribution |
| 10 | **Memory Protection** | 🆕 Spec | Anti-runtime-patch (bytecode hashing) |
| 11 | **DLL Injection Detection** | 🆕 Spec | Module enumeration + whitelist/blacklist |
| 12 | **API Hook Detection** | 🆕 Spec | JMP/CALL signature scan on Windows APIs |
| 13 | **Environment Detection** | 🆕 Spec | Docker/Wine/WSL/Sandbox detection |
| 14 | **HeartbeatService** | 🆕 Spec | Periodic online license revalidation |
| 15 | **Domain Pinning** | 🆕 Spec | Anti-DNS hijack for API server |
| 16 | **Session Control** | 🆕 Spec | Concurrent device limiting (max 2) |
| 17 | **Anomaly Detection** | 🆕 Spec | Key sharing / bot / geo anomaly detection |

---

## 🆕 What's New in v2.4

### 1. Auto-Discovery (Admin)
```python
# OLD: Hardcoded paths
Path("levanlinh.kma/...")  # ❌ Required specific folder name

# NEW: Auto-scan all JSON files
for json_file in admin_dir.rglob("*.json"):
    if is_firebase_credential(json_file):  # ✅ Any folder!
        credentials.append(json_file)
```

### 2. AES-256 Encryption (Client)
```python
# OLD: Simple XOR
result = data ^ key  # ❌ Weak

# NEW: AES-256 with PBKDF2
kdf = PBKDF2HMAC(
    algorithm=SHA256(),
    iterations=100000,
    salt=SALT
)  # ✅ Strong
```

---

## 🔄 Cross-validation Flow

```
┌───────────────┐     ┌───────────────┐
│   PRIMARY     │     │    BACKUP     │
│ (auto-found)  │     │ (auto-found)  │
└───────┬───────┘     └───────┬───────┘
        │                     │
        ▼                     ▼
   ┌─────────┐           ┌─────────┐
   │ Result A │           │ Result B │
   └────┬─────┘           └────┬─────┘
        │                      │
        └──────────┬───────────┘
                   ▼
            ┌─────────────┐
            │ A == B ?    │
            └──────┬──────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
    ✅ VALID            🚨 TAMPERING
   (cross-validated)     DETECTED!
```

---

## 👥 Role-Based Access Control

| Role | Code | Features | Dev Console | Limits |
|------|------|----------|-------------|--------|
| TRIAL | `0` | Basic | ❌ | 1 cookie, 2 threads, 10 prompts |
| PREMIUM | `1` | Full | ❌ | Unlimited |
| TESTER | `2` | Full + Beta | ✅ | Unlimited |

---

## 📋 Files Reference

| File | Version | Purpose | Location | Distribute? |
|------|---------|---------|----------|-------------|
| `firebase_config.py` | v2.4 | Auto-discovery | `01 - ADMIN/` | 🔴 NO |
| `license_manager_gui.py` | v2.3 | Admin GUI | `01 - ADMIN/` | 🔴 NO |
| `api_key_encryptor.py` | v2.3 | Key encryption | `01 - ADMIN/` | 🔴 NO |
| `license_client.py` | v2.2 | Client validation | `security/` + `services/` | ✅ YES |
| `firebase_rest_client.py` | v2.4 | AES-256 REST | `security/` + `services/` | ✅ YES |
| `trial_protection.py` | v2.0 | Multi-layer trial | `security/` | ✅ YES |
| `license_request.py` | v1.0 | License request flow | `security/` | ✅ YES |
| `permissions.py` | v2.2 | Role system | `security/` + `services/` | ✅ YES |

> **Note:** `services/` contains simplified adapters imported by app code.
> `security/` contains full source implementations. See [CLIENT_INTEGRATION_GUIDE.md](docs/CLIENT_INTEGRATION_GUIDE.md).

---

## ⚠️ Security Notes

> [!CAUTION]
> **NEVER distribute admin/ folder to clients!**

> [!IMPORTANT]
> v2.4 uses AES-256 with PBKDF2 (100,000 iterations).
> Even if extracted, brute-forcing would take years.

> [!TIP]
> Credential folders can have ANY name now.
> Just drop `.json` files in `admin/` - auto-detected!
