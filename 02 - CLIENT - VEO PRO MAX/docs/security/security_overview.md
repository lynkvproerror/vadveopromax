# 🔒 VEO Pro Max — Security Architecture Overview

> Tài liệu tổng hợp toàn bộ hệ thống bảo mật, chống crack, license management.

---

## I. Tổng quan kiến trúc bảo mật

```
┌───────────────────────────────────────────────────────────────┐
│                    VEO Pro Max Security                        │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│  License     │  Anti-Crack  │  Anti-Debug  │  Environment    │
│  System      │  Protection  │  Detection   │  Checker        │
├──────────────┼──────────────┼──────────────┼─────────────────┤
│ • Firebase   │ • SHA-256    │ • IsDebugger │ • VM Detection  │
│ • HMAC Key   │   Integrity  │   Present    │ • Sandbox Check │
│ • HWID Lock  │ • Encrypted  │ • Timing     │ • Tool Process  │
│ • Dual-DB    │   API Keys   │   Anomaly    │   Detection     │
│ • Trial      │ • AES-256    │ • Breakpoint │ • Registry Scan │
│   Protection │   Encryption │   Detection  │                 │
└──────────────┴──────────────┴──────────────┴─────────────────┘
```

---

## II. License System

### 2.1. License Tiers (Gói mua)

| Tier | Code | Giá | Thời hạn | Role |
|------|------|-----|----------|------|
| Trial | `trial` | Miễn phí | 7 ngày | TRIAL |
| 1 Tháng | `1M` | 300,000đ | 30 ngày | PREMIUM |
| 3 Tháng | `3M` | 500,000đ | 90 ngày | PREMIUM |
| 6 Tháng | `6M` | 800,000đ | 180 ngày | PREMIUM |
| 1 Năm | `1Y` | 1,200,000đ | 365 ngày | PREMIUM |
| Vĩnh viễn | `LIFE` | 3,000,000đ | ∞ | PREMIUM |
| Tester | — | Internal | ∞ | TESTER |

> Source: `config/constants.py` → `LicenseTier` enum

### 2.2. Role-Based Feature Gating

| Feature | TRIAL | PREMIUM | TESTER |
|---------|-------|---------|--------|
| T2V, I2V, R2V, T2I, I2I | ✅ | ✅ | ✅ |
| Queue Manager | ✅ | ✅ | ✅ |
| Auto Upscale | ✅ | ✅ | ✅ |
| Continuation | ❌ | ✅ | ✅ |
| Batch Processing | ❌ | ✅ | ✅ |
| Multi-Account | ❌ | ✅ | ✅ |
| Download 4K | ❌ | ✅ | ✅ |
| Image Library | ❌ | ✅ | ✅ |
| Custom Output | ❌ | ✅ | ✅ |
| Advanced Settings | ❌ | ✅ | ✅ |
| Dev Console | ❌ | ❌ | ✅ |
| Beta Features | ❌ | ❌ | ✅ |

| Limit | TRIAL | PREMIUM | TESTER |
|-------|-------|---------|--------|
| Max Accounts | 1 | ∞ | ∞ |
| Max Workers | 2 | ∞ | ∞ |
| Prompts/Batch | 10 | ∞ | ∞ |
| Output/Prompt | 2 | 4 | 4 |
| Daily Limit | 20 | ∞ | ∞ |

> Source: `services/permissions.py` → `PermissionsSystem.ROLE_LIMITS`

### 2.3. License Key Format & Validation

- **Format**: `XXXX-XXXX-XXXX-XXXX`
- **Verification**: HMAC-SHA256 checksum
- **Tier Detection**: Key prefix hoặc Firebase `_t` field
- **Machine Lock**: HWID (Hardware ID) binding — 1 key = 1 máy

> Source: `services/license_client.py` → `LicenseClient`

### 2.4. Firebase Backend

**Dual-Database Cross-Validation:**
- Primary Firebase project + Backup Firebase project
- Cross-validate kết quả giữa 2 DB → phát hiện tampering
- REST API (không dùng Admin SDK) → read-only access
- Collection: `_lic`

**Secure Configuration (4 layers):**
1. **Layer 1**: AES-256 encryption cho API keys (upgrade từ XOR)
2. **Layer 2**: Hardware-bound key — mã hoá gắn với HWID
3. **Layer 3**: Split & Scatter — config tách thành nhiều phần
4. **Layer 4**: Runtime configuration — decrypt lúc chạy

> Source: `security/firebase_rest_client.py` → `SecureFirebaseConfig`, `FirebaseRESTClient`

---

## III. Anti-Crack / Anti-Tampering

### 3.1. SHA-256 Integrity Check

```python
class IntegrityChecker:
    # Compute SHA-256 hash của executable
    # So sánh với expected hash
    # Phát hiện file bị patch/modify
```

- Hash toàn bộ file `.exe` hoặc `.py`
- So sánh với hash gốc lưu trên Firebase
- **Detect**: patch binary, hex edit, code injection

> Source: `core/security.py` → `IntegrityChecker`

### 3.2. AES-256 Encrypted API Keys

```python
class _AES256Encryptor:
    # PBKDF2 key derivation
    # AES-256 encrypt/decrypt
    # Fallback XOR nếu không có PyCryptodome
```

- API keys mã hoá AES-256, KHÔNG lưu plaintext
- Key derive từ machine-specific password (HWID)
- Có 2 bộ keys: `_encrypted_api_keys.py`, `_encrypted_keys.py`

> Source: `security/firebase_rest_client.py` → `_AES256Encryptor`

### 3.3. Hardware-Bound Encryption

```python
class _HardwareBinder:
    # Generate machine-specific encryption key
    # Bind config to specific hardware
```

- Key dựa trên: CPU ID + Disk Serial + OS Install Date + MAC
- Config mã hoá bằng key này → không copy được sang máy khác
- Hỗ trợ static mode cho multi-machine deployment

> Source: `security/firebase_rest_client.py` → `_HardwareBinder`

---

## IV. Anti-Debug

### 4.1. Debugger Detection

```python
class AntiDebug:
    # IsDebuggerPresent (Windows API)
    # Timing check — detect breakpoints
```

- **IsDebuggerPresent**: Windows API `kernel32.IsDebuggerPresent()`
- **Timing check**: Đo thời gian thực thi, >100ms = có breakpoint
- Detect: Visual Studio, x64dbg, OllyDbg, IDA Pro

> Source: `core/security.py` → `AntiDebug`

### 4.2. Tool Process Detection

```python
SUSPICIOUS_PROCESSES = [
    "x64dbg", "ida", "ghidra",
    "ollydbg", "wireshark", "fiddler"
]
```

- Quét danh sách process đang chạy
- Phát hiện debugger, disassembler, network sniffer

> Source: `core/security.py` → `EnvironmentChecker`

---

## V. Anti-Time Tampering

### 5.1. Time Tamper Detector

```python
class TimeTamperDetector:
    NTP_SERVERS = ["time.google.com", "pool.ntp.org", ...]
```

- So sánh system time với NTP servers
- Monotonic clock consistency check
- Phát hiện user chỉnh đồng hồ để gia hạn trial

> Source: `core/security.py` → `TimeTamperDetector`

### 5.2. Multi-Source Time Verification

```python
class TimeVerifier:
    MAX_DRIFT_SECONDS = 300  # 5 phút
```

- HTTP header time (Google, Cloudflare)
- Firebase server time
- Cho phép drift tối đa 5 phút
- Cache offset để giảm network requests

> Source: `security/trial_protection.py` → `TimeVerifier`

---

## VI. Trial Protection

### 6.1. Multi-Layer Trial Markers

**Lưu trial start date ở 5 nơi đồng thời:**

| # | Location | Path |
|---|----------|------|
| 1 | File (hidden) | `%USERPROFILE%/.veoauto/.trial` |
| 2 | File (hidden) | `%APPDATA%/VEO/.trial.dat` |
| 3 | File (hidden) | `%LOCALAPPDATA%/VEO/trial.bin` |
| 4 | Windows Registry | `HKCU\SOFTWARE\VEOAutoTool` |
| 5 | Firebase Cloud | Remote database |

**Chống gian lận:**
- Timestamp mã hoá + obfuscation (không đọc plaintext)
- Machine ID hash binding
- Cross-validate giữa tất cả sources
- **Priority**: Firebase > Registry > Files
- Xoá 1 nơi → các nơi khác vẫn giữ → trial không reset

> Source: `security/trial_protection.py` → `TrialMarkerManager`

### 6.2. Trial Key Activation

- Trial key format: `TRIAL-XXXX-XXXX`
- Admin generate → user nhập → activate
- **KHÔNG auto-trial**: Phải có key mới dùng thử được
- 7 ngày từ ngày activate

> Source: `security/trial_protection.py` → `activate_trial_key()`

---

## VII. VM / Sandbox Detection

### 7.1. Environment Checker

```python
VM_INDICATORS = ["VBOX", "VMWARE", "QEMU", "XEN", "HYPERV"]
```

- **Registry scan**: Tìm VM indicators trong Windows Registry
- **System manufacturer**: Check WMI manufacturer string
- **Detect**: VirtualBox, VMware, QEMU, Xen, Hyper-V
- Cảnh báo nếu chạy trong VM (không block hoàn toàn)

> Source: `core/security.py` → `EnvironmentChecker`

---

## IX. 🦀 Rust Native Security Hardening (NEW)

> **Tài liệu chi tiết**: [`RUST_SECURITY_HARDENING.md`](./reference_docs/RUST_SECURITY_HARDENING.md)

### Mục tiêu
Compile critical security modules (License Verify, Integrity Check, Anti-Debug, HWID) sang **Rust native binary** (.pyd/.so) thông qua **PyO3** — chống decompile, chống patch, chống crack.

### So sánh

| Attack | Python (hiện tại) | Rust (new) |
|--------|-------------------|------------|
| Decompile | ⚠️ `uncompyle6` | ❌ Impossible |
| Strings extract | ⚠️ Plaintext | ❌ Encrypted |
| Bytecode patch | ⚠️ Easy | ❌ No bytecode |
| Debug attach | ⚠️ `pydevd` | ❌ 5-layer anti-debug |
| Memory dump | ⚠️ Plaintext RAM | ✅ Zeroed after use |

### Priority
- **P0**: License Verify, Integrity Check
- **P1**: HWID Binding, Anti-Debug
- **P2**: Crypto (AES/HMAC), Trial Protection
- **P3**: Environment Check (VM/Sandbox)

---

## IX.B. 🛡️ Attack Surface Analysis (NEW)

> **Tài liệu chi tiết**: [`ATTACK_SURFACE_ANALYSIS.md`](./reference_docs/ATTACK_SURFACE_ANALYSIS.md)

**49 attack vectors** được phân tích toàn diện, bao gồm:
- 8 Binary/Static attacks (PyInstaller extract, loader, process hollowing...)
- 6 Runtime/Dynamic attacks (monkey patch, import hook, Frida...)
- 6 Network/MITM attacks (SSL pinning, replay, server emulation, DNS spoof...)
- 5 License attacks (keygen, shared keys...)
- 6 Environment manipulation (VM snapshot, FS virtualization...)
- 3 Build/Deploy attacks (code signing, supply chain...)
- 3 Data leak attacks (log leak, clipboard, memory forensics)
- 6 Extension/Browser attacks (WebSocket hijack, CDP abuse, token theft, sideload...)
- 4 Python-specific attacks (inspect/gc, ctypes, race condition, differential analysis)
- 5 Infrastructure/Human attacks (rootkit, social engineering, credential stuffing...)

**Coverage: 49/49 = 100%** ✅

---

## X. File Map — Toàn bộ files liên quan

### Documentation (`00 - Documentation/`)

| File | Nội dung |
|------|----------|
| `05_Security/README.md` | Security module overview |
| `05_Security/SECURITY_AUDIT_REPORT.md` | Audit report |
| `05_Security/docs/LICENSE_OVERVIEW.md` | License system overview |
| `05_Security/docs/LICENSE_SECURITY_OVERVIEW.md` | Security mechanisms |
| `05_Security/docs/LICENSE_TIERS_FEATURES.md` | Tier comparison table |
| `05_Security/docs/LICENSE_KEY_ALGORITHM.md` | HMAC key algorithm |
| `05_Security/docs/LICENSE_ANTI_FAKE_SERVER.md` | Anti-fake server protection |
| `05_Security/docs/LICENSE_HARDWARE_FINGERPRINT.md` | HWID fingerprinting |
| `05_Security/docs/FIREBASE_LICENSE_GUIDE.md` | Firebase setup guide |
| `05_Security/docs/WORKFLOW_LICENSE_ISSUANCE.md` | Key issuance workflow |
| `05_Security/docs/WORKFLOW_LICENSE_SUPPORT.md` | Support workflow |
| `05_Security/docs/LICENSE_MANAGER_GUI_PLAN.md` | Admin GUI plan |
| `05_Security/docs/LICENSE_MANAGER_GUI_CHANGELOG.md` | Admin GUI changelog |
| `05_Security/docs/SECURITY_CHANGELOG.md` | Security changelog |
| `05_Security/docs/RUST_SECURITY_HARDENING.md` | 🦀 Rust native binary security — anti-crack, anti-tamper |
| `05_Security/docs/ATTACK_SURFACE_ANALYSIS.md` | 🛡️ 35 attack vectors — full coverage analysis |
| `03_Backend/FIREBASE_SECURITY_RULES.md` | Firestore security rules |
| `03_Backend/TOKEN_SECURITY.md` | Token security |
| `01_UI_UX/TAB_08_LICENSE.md` | License tab UI spec |

### Code (`02 - CLIENT - VEO PRO MAX/`)

| File | Nội dung |
|------|----------|
| `core/security.py` | IntegrityChecker, AntiDebug, TimeTamper, TrialProtection, EnvironmentChecker |
| `security/__init__.py` | Package init |
| `security/firebase_rest_client.py` | AES-256 + HardwareBinder + Dual-DB Firebase client |
| `security/license_client.py` | License validation, HMAC, HWID |
| `security/license_request.py` | License request handling |
| `security/permissions.py` | Permission checks (deprecated, use services/) |
| `security/trial_protection.py` | Multi-layer trial markers + TimeVerifier |
| `security/_encrypted_api_keys.py` | Encrypted Firebase API keys |
| `security/_encrypted_keys.py` | Encrypted config keys |
| `services/license_client.py` | License client (service layer) |
| `services/permissions.py` | Role-based feature gating (canonical) |
| `config/constants.py` | LicenseTier enum, AppConstants |
| `ui/tabs/tab_license.py` | License UI tab |
| `veo_security/` | 🦀 Rust crate — native security modules (planned) |
