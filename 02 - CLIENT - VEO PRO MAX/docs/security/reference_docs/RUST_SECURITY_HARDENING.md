# 🦀 Rust Security Hardening — Anti-Crack & Anti-Tamper

> **Version**: 1.0  
> **Created**: 2026-02-27  
> **Scope**: Compile critical security modules to Rust native binary  
> **Status**: Planning → Implementation

---

## I. Tại sao cần Rust?

### Python Security Limitations

| Vấn đề | Python | Rust |
|---------|--------|------|
| **Decompile** | `uncompyle6` → source code gốc | ❌ Không thể decompile |
| **Bytecode patch** | Sửa `.pyc` trực tiếp | ❌ Machine code, không patch được |
| **String extraction** | `strings binary.exe` → lộ keys | ✅ Obfuscate tại compile time |
| **Memory dump** | Plaintext trong RAM | ✅ Zero trên stack sau dùng |
| **Debug attach** | `pydevd`, `pdb` dễ inject | ✅ Anti-debug tại OS level |
| **PyArmor bypass** | Nhiều tool crack PyArmor | ✅ Native binary, không bypass |

### Kiến trúc mục tiêu

```
┌─────────────────────────────────────────────────────┐
│                   Python App (main.py)               │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │         veo_security (Rust → .pyd/.so)        │   │
│  │                                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │   │
│  │  │ License  │ │ Integrity│ │  Anti-Debug  │  │   │
│  │  │ Verify   │ │ Check    │ │  Anti-Tamper │  │   │
│  │  └──────────┘ └──────────┘ └──────────────┘  │   │
│  │                                                │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │   │
│  │  │ HWID     │ │ Crypto   │ │  Environment │  │   │
│  │  │ Binding  │ │ (AES/HMAC│ │  Sandbox Det │  │   │
│  │  └──────────┘ └──────────┘ └──────────────┘  │   │
│  └──────────────────────────────────────────────┘   │
│                     ↕ PyO3 FFI                       │
└─────────────────────────────────────────────────────┘
```

---

## II. Modules cần compile sang Rust

### Priority Matrix

| Module | File Python hiện tại | Mức độ | Lý do |
|--------|---------------------|--------|-------|
| **License Verify** | `security/license_client.py` | 🔴 P0 | Core — crack = bypass hoàn toàn |
| **Integrity Check** | `core/security.py` | 🔴 P0 | SHA-256 hash verify |
| **HWID Binding** | `security/firebase_rest_client.py` | 🟠 P1 | Hardware fingerprint |
| **Anti-Debug** | `core/security.py` | 🟠 P1 | IsDebuggerPresent, timing |
| **Crypto (AES/HMAC)** | `security/license_client.py` | 🟡 P2 | Key derivation, encryption |
| **Trial Protection** | `security/trial_protection.py` | 🟡 P2 | Multi-marker trial check |
| **Environment Check** | `core/security.py` | 🟢 P3 | VM/sandbox detection |

---

## III. Rust Anti-Tamper

### 3.1. Self-Integrity Check (Rust-native)

```rust
use sha2::{Sha256, Digest};
use std::fs;

/// Verify the .pyd/.so binary hasn't been modified
pub fn verify_self_integrity() -> bool {
    // 1. Read own binary
    let exe_path = std::env::current_exe().unwrap();
    let binary = fs::read(&exe_path).unwrap();
    
    // 2. Expected hash (embedded at build time)
    // Injected by build script → replaced in final binary
    let expected = include_str!("../.build_hash");
    
    // 3. Compute actual hash (exclude last 64 bytes = hash storage)
    let actual_data = &binary[..binary.len() - 64];
    let mut hasher = Sha256::new();
    hasher.update(actual_data);
    let actual = format!("{:x}", hasher.finalize());
    
    // 4. Constant-time compare (prevent timing attack)
    constant_time_eq(expected.as_bytes(), actual.as_bytes())
}
```

### 3.2. Code Section Hash (chống patch từng function)

```rust
/// Hash individual code sections to detect surgical patches
pub fn verify_code_sections() -> Vec<(&'static str, bool)> {
    let results = vec![
        ("license_verify", hash_section(license_verify as *const (), 512)),
        ("hwid_check",     hash_section(hwid_check as *const (), 256)),
        ("anti_debug",     hash_section(anti_debug as *const (), 128)),
    ];
    
    results.iter().map(|(name, hash)| {
        let expected = SECTION_HASHES.get(name).unwrap();
        (*name, constant_time_eq(hash, expected))
    }).collect()
}
```

### 3.3. Import Address Table (IAT) Protection

```rust
/// Detect IAT hooking (common in API monitors & debuggers)
pub fn check_iat_integrity() -> bool {
    #[cfg(target_os = "windows")]
    {
        use winapi::um::libloaderapi::GetModuleHandleA;
        use winapi::um::winnt::IMAGE_DOS_HEADER;
        
        unsafe {
            let base = GetModuleHandleA(std::ptr::null());
            let dos = base as *const IMAGE_DOS_HEADER;
            // Walk PE headers → verify IAT entries point to legitimate DLLs
            // Detect hooks: JMP instructions at function entry points
            verify_pe_imports(dos)
        }
    }
}
```

---

## IV. Rust Anti-Debug

### 4.1. Multi-Layer Debug Detection

```rust
#[cfg(target_os = "windows")]
pub fn is_debugger_attached() -> bool {
    use winapi::um::debugapi::{IsDebuggerPresent, CheckRemoteDebuggerPresent};
    use winapi::um::processthreadsapi::GetCurrentProcess;
    
    unsafe {
        // Layer 1: Standard API check
        if IsDebuggerPresent() != 0 {
            return true;
        }
        
        // Layer 2: Remote debugger (attached externally)
        let mut remote = 0i32;
        CheckRemoteDebuggerPresent(GetCurrentProcess(), &mut remote);
        if remote != 0 {
            return true;
        }
        
        // Layer 3: NtQueryInformationProcess (bypass API hooks)
        if nt_query_debug_port() {
            return true;
        }
        
        // Layer 4: Hardware breakpoint detection (DR0-DR7)
        if check_hardware_breakpoints() {
            return true;
        }
        
        // Layer 5: Timing check (RDTSC)
        if timing_check_suspicious() {
            return true;
        }
        
        false
    }
}

/// RDTSC timing — detect single-step debugging
fn timing_check_suspicious() -> bool {
    let start = unsafe { core::arch::x86_64::_rdtsc() };
    
    // Simple operation that should take < 1000 cycles
    let mut x: u64 = 0;
    for i in 0..100 { x = x.wrapping_add(i); }
    
    let elapsed = unsafe { core::arch::x86_64::_rdtsc() } - start;
    
    // > 50,000 cycles = breakpoint or single-stepping
    elapsed > 50_000
}

/// Check Debug Registers DR0-DR7 (hardware breakpoints)
fn check_hardware_breakpoints() -> bool {
    #[cfg(target_os = "windows")]
    unsafe {
        use winapi::um::processthreadsapi::GetCurrentThread;
        use winapi::um::winnt::CONTEXT;
        
        let mut ctx: CONTEXT = std::mem::zeroed();
        ctx.ContextFlags = 0x10; // CONTEXT_DEBUG_REGISTERS
        
        winapi::um::processthreadsapi::GetThreadContext(
            GetCurrentThread(), &mut ctx
        );
        
        // DR0-DR3: breakpoint addresses, DR7: control register
        ctx.Dr0 != 0 || ctx.Dr1 != 0 || ctx.Dr2 != 0 || ctx.Dr3 != 0
    }
}
```

---

## V. Rust Anti-Crack (License Protection)

### 5.1. License Verify in Rust (không thể decompile)

```rust
use hmac::{Hmac, Mac};
use sha2::Sha256;
use aes_gcm::{Aes256Gcm, KeyInit, aead::Aead};

type HmacSha256 = Hmac<Sha256>;

/// Core license verification — compiled to native, cannot be patched
pub fn verify_license(
    key_hex: &str, 
    hwid: &str, 
    secret: &[u8; 32]
) -> LicenseResult {
    // 1. Decode obfuscated key
    let key_bytes = deobfuscate_key(key_hex);
    
    // 2. Extract components
    let (tier, duration, timestamp, hwid_hash, checksum) = 
        parse_key_components(&key_bytes);
    
    // 3. Verify HMAC checksum
    let mut mac = HmacSha256::new_from_slice(secret).unwrap();
    mac.update(&key_bytes[..28]); // All except checksum
    if mac.verify_slice(&checksum).is_err() {
        return LicenseResult::Invalid("checksum_failed");
    }
    
    // 4. Verify HWID binding
    let expected_hwid = compute_hwid_hash(hwid, secret);
    if !constant_time_eq(&hwid_hash, &expected_hwid) {
        return LicenseResult::Invalid("hwid_mismatch");
    }
    
    // 5. Check expiration
    let now = get_trusted_time();
    let expires = timestamp + (duration as u64 * 86400);
    if now > expires {
        return LicenseResult::Expired(expires);
    }
    
    LicenseResult::Valid { tier, days_remaining: ((expires - now) / 86400) as u32 }
}

/// Deobfuscate with compile-time XOR key
fn deobfuscate_key(hex: &str) -> Vec<u8> {
    // XOR key embedded at compile time — different per build
    const XOR_KEY: [u8; 32] = *include_bytes!("../.xor_key");
    
    let bytes = hex::decode(hex.replace("-", "")).unwrap_or_default();
    bytes.iter().enumerate()
        .map(|(i, b)| b ^ XOR_KEY[i % XOR_KEY.len()])
        .collect()
}
```

### 5.2. HWID Fingerprint (Rust-native, không fake được)

```rust
#[cfg(target_os = "windows")]
pub fn get_hardware_id() -> String {
    use sha2::{Sha256, Digest};
    
    let mut hasher = Sha256::new();
    
    // 1. CPU ID (CPUID instruction — không thể fake bằng software)
    let cpuid = raw_cpuid();
    hasher.update(&cpuid);
    
    // 2. Disk serial (WMI query)
    let disk = wmi_query("Win32_DiskDrive", "SerialNumber");
    hasher.update(disk.as_bytes());
    
    // 3. BIOS serial
    let bios = wmi_query("Win32_BIOS", "SerialNumber");
    hasher.update(bios.as_bytes());
    
    // 4. MAC address (first physical adapter)
    let mac = get_physical_mac();
    hasher.update(mac.as_bytes());
    
    // 5. Machine GUID (registry)
    let guid = registry_read(
        r"SOFTWARE\Microsoft\Cryptography", "MachineGuid"
    );
    hasher.update(guid.as_bytes());
    
    format!("{:x}", hasher.finalize())
}

/// Direct CPUID instruction — bypasses any software hook
fn raw_cpuid() -> [u8; 48] {
    let mut result = [0u8; 48];
    unsafe {
        // EAX=0: Vendor string
        let r0 = core::arch::x86_64::__cpuid(0);
        result[0..4].copy_from_slice(&r0.ebx.to_le_bytes());
        result[4..8].copy_from_slice(&r0.ecx.to_le_bytes());
        result[8..12].copy_from_slice(&r0.edx.to_le_bytes());
        
        // EAX=1: Processor signature + features
        let r1 = core::arch::x86_64::__cpuid(1);
        result[12..16].copy_from_slice(&r1.eax.to_le_bytes());
        result[16..20].copy_from_slice(&r1.ebx.to_le_bytes());
        
        // EAX=3: Processor serial number (if supported)
        let r3 = core::arch::x86_64::__cpuid(3);
        result[20..24].copy_from_slice(&r3.ecx.to_le_bytes());
        result[24..28].copy_from_slice(&r3.edx.to_le_bytes());
    }
    result
}
```

---

## VI. Compile & Build Pipeline

### 6.1. Project Structure

```
veo_security/                    # Rust crate
├── Cargo.toml                   # Dependencies + PyO3 config
├── src/
│   ├── lib.rs                   # PyO3 module entry point
│   ├── license.rs               # License verification
│   ├── integrity.rs             # Self-integrity + code section hash
│   ├── anti_debug.rs            # Multi-layer debug detection
│   ├── hwid.rs                  # Hardware fingerprint
│   ├── crypto.rs                # AES-256-GCM, HMAC-SHA256
│   ├── anti_tamper.rs           # IAT check, hook detection
│   └── environment.rs           # VM/sandbox detection
├── build.rs                     # Build script (inject hashes)
└── .xor_key                     # Per-build XOR key (generated)
```

### 6.2. Cargo.toml

```toml
[package]
name = "veo_security"
version = "1.0.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]          # → .pyd (Windows) / .so (Linux)

[dependencies]
pyo3 = { version = "0.21", features = ["extension-module"] }
sha2 = "0.10"
hmac = "0.12"
aes-gcm = "0.10"
hex = "0.4"
winapi = { version = "0.3", features = [
    "debugapi", "processthreadsapi", "libloaderapi",
    "winnt", "handleapi", "tlhelp32"
]}
constant_time_eq = "0.3"

[profile.release]
opt-level = "z"                  # Size optimization
lto = true                       # Link-Time Optimization
strip = true                     # Strip debug symbols
panic = "abort"                  # No unwind = smaller binary
codegen-units = 1                # Better optimization
```

### 6.3. PyO3 Bridge (lib.rs)

```rust
use pyo3::prelude::*;

mod license;
mod integrity;
mod anti_debug;
mod hwid;
mod crypto;
mod anti_tamper;
mod environment;

/// Python module: `import veo_security`
#[pymodule]
fn veo_security(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // License
    m.add_function(wrap_pyfunction!(license::verify_license_py, m)?)?;
    m.add_function(wrap_pyfunction!(license::get_tier_py, m)?)?;
    
    // Integrity
    m.add_function(wrap_pyfunction!(integrity::check_integrity_py, m)?)?;
    
    // Anti-Debug  
    m.add_function(wrap_pyfunction!(anti_debug::is_debugger_py, m)?)?;
    
    // HWID
    m.add_function(wrap_pyfunction!(hwid::get_hwid_py, m)?)?;
    
    // Security check (all-in-one)
    m.add_function(wrap_pyfunction!(full_security_check, m)?)?;
    
    Ok(())
}

/// All-in-one security gate — call on startup
#[pyfunction]
fn full_security_check(license_key: &str) -> PyResult<(bool, String)> {
    // 1. Anti-debug
    if anti_debug::is_debugger_attached() {
        return Ok((false, "debug_detected".into()));
    }
    
    // 2. Integrity
    if !integrity::verify_self_integrity() {
        return Ok((false, "tampered".into()));
    }
    
    // 3. Environment
    if environment::is_sandbox() {
        return Ok((false, "sandbox_detected".into()));
    }
    
    // 4. License
    let hwid = hwid::get_hardware_id();
    match license::verify_license(license_key, &hwid, &get_secret()) {
        license::LicenseResult::Valid { .. } => Ok((true, "valid".into())),
        license::LicenseResult::Expired(_) => Ok((false, "expired".into())),
        license::LicenseResult::Invalid(r) => Ok((false, r.into())),
    }
}
```

### 6.4. Build Commands

```bash
# 1. Install maturin (Rust → Python package builder)
pip install maturin

# 2. Build release .pyd (Windows) 
cd veo_security/
maturin build --release --strip

# 3. Output: target/wheels/veo_security-1.0.0-cp312-*.whl
# Install into project:
pip install target/wheels/veo_security-1.0.0-*.whl

# 4. Verify import
python -c "import veo_security; print(veo_security.full_security_check('test'))"
```

---

## VII. Python Integration

### 7.1. Thay thế Python security modules

```python
# BEFORE (Python — dễ crack)
from security.license_client import LicenseClient
result = LicenseClient.verify(key)

# AFTER (Rust — không thể crack)
try:
    import veo_security
    ok, reason = veo_security.full_security_check(key)
except ImportError:
    # Fallback to Python (development only)
    from security.license_client import LicenseClient
    ok, reason = LicenseClient.verify(key), "python_fallback"
```

### 7.2. Periodic Background Check

```python
import asyncio
import veo_security

async def security_watchdog(interval=30):
    """Background task — re-check every 30s."""
    while True:
        await asyncio.sleep(interval)
        
        # Anti-debug check (detect runtime attach)
        if veo_security.is_debugger_py():
            log.critical("Debugger detected — shutting down")
            os._exit(1)
        
        # Integrity check (detect hot-patch)
        if not veo_security.check_integrity_py():
            log.critical("Binary tampered — shutting down")
            os._exit(1)
```

---

## VIII. Anti-Crack Measures (Rust-specific)

### 8.1. Compile-Time Obfuscation

| Technique | Mô tả | Hiệu quả |
|-----------|--------|-----------|
| **LTO** | Link-Time Optimization — inline + merge functions | Khó trace call graph |
| **Strip symbols** | Xóa function names, debug info | Không thể đọc tên function |
| **`panic = abort`** | Không có unwind info | Giảm metadata lộ |
| **`codegen-units = 1`** | Toàn bộ crate 1 compilation unit | Tối ưu + khó tách module |
| **`opt-level = "z"`** | Size opt — merge duplicate code | Khó pattern match |

### 8.2. Runtime Anti-Crack

| Technique | Mô tả |
|-----------|--------|
| **Control flow flattening** | Flatten if/else thành switch table |
| **Opaque predicates** | Điều kiện luôn true/false nhưng khó phân tích static |
| **Dead code injection** | Thêm code giả, confuse decompiler |
| **String encryption** | Encrypt strings tại compile time, decrypt runtime |
| **Stack string** | Build strings từng byte trên stack (chống `strings` scan) |

### 8.3. String Encryption Example

```rust
/// Macro: encrypt string at compile time, decrypt at runtime
macro_rules! enc_str {
    ($s:literal) => {{
        const ENCRYPTED: &[u8] = &encrypt_const($s.as_bytes());
        decrypt_runtime(ENCRYPTED)
    }};
}

// Usage — no plaintext in binary
let api_key = enc_str!("AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY");
let endpoint = enc_str!("https://aisandbox-pa.googleapis.com");
```

---

## IX. Deployment Checklist

### Build Pipeline

```mermaid
graph LR
    A[Rust Source] --> B[cargo build --release]
    B --> C[.pyd binary]
    C --> D[build.rs: inject hashes]
    D --> E[maturin build]
    E --> F[.whl package]
    F --> G[Bundle with Python app]
    G --> H[PyInstaller/Nuitka]
    H --> I[Final .exe]
```

### Pre-Distribution Checklist

- [ ] `strip = true` — no debug symbols
- [ ] `lto = true` — link-time optimization
- [ ] Verify no plaintext strings: `strings veo_security.pyd | grep -i key`
- [ ] Self-integrity hash injected by `build.rs`
- [ ] XOR key regenerated per build
- [ ] Test on clean VM (no dev tools)
- [ ] Anti-debug triggers correctly
- [ ] License verify works with valid key
- [ ] HWID binding matches target machine

---

## X. So sánh trước/sau Rust Hardening

| Attack Vector | Trước (Python) | Sau (Rust) |
|---------------|----------------|------------|
| `uncompyle6` decompile | ⚠️ Full source | ❌ Binary, impossible |
| `strings` extract keys | ⚠️ Plaintext | ❌ Encrypted at compile |
| Patch `.pyc` bytecode | ⚠️ Easy | ❌ No bytecode |
| `pydevd` debug attach | ⚠️ Works | ❌ Anti-debug kills |
| PyArmor strip | ⚠️ Known bypasses | ❌ Native binary |
| DLL inject + hook | ⚠️ Python level | ❌ IAT protection |
| Memory dump keys | ⚠️ Plaintext RAM | ✅ Zeroed after use |
| Hex edit binary | ⚠️ Pattern match | ❌ Integrity hash |
| Keygen / key forge | ⚠️ Algorithm visible | ❌ HMAC secret in binary |
| Time manipulation | ⚠️ Python check | ✅ RDTSC + NTP + Firebase |

---

## XI. References

| Resource | URL |
|----------|-----|
| PyO3 (Rust → Python) | https://pyo3.rs |
| Maturin (build tool) | https://maturin.rs |
| `sha2` crate | https://docs.rs/sha2 |
| `aes-gcm` crate | https://docs.rs/aes-gcm |
| `winapi` crate | https://docs.rs/winapi |
| Rust anti-debug patterns | https://anti-debug.checkpoint.com |
| PE format reference | https://docs.microsoft.com/en-us/windows/win32/debug/pe-format |

---

> [!IMPORTANT]
> Tài liệu này là **planning document**. Cần implement từng module theo Priority Matrix (Section II).
> P0 modules (License Verify, Integrity Check) nên implement trước.

> [!CAUTION]
> **KHÔNG distribute source Rust** cho client. Chỉ distribute compiled `.pyd`/`.so` binary.
> XOR key và build hash phải **regenerate mỗi build**.
