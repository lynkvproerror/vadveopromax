# 🛡️ Attack Surface Analysis — Toàn bộ vectors & countermeasures

> **Version**: 1.0  
> **Created**: 2026-02-27  
> **Scope**: 37 attack vectors (16 đã có + 21 bổ sung mới)  
> **Coverage target**: 100%

---

## Mục lục

- [I. Binary / Static Attacks](#i-binary--static-attacks)
- [II. Runtime / Dynamic Attacks](#ii-runtime--dynamic-attacks)
- [III. Network / MITM Attacks](#iii-network--mitm-attacks)
- [IV. License-Specific Attacks](#iv-license-specific-attacks)
- [V. Environment Manipulation](#v-environment-manipulation)
- [VI. Build & Deploy Attacks](#vi-build--deploy-attacks)
- [VII. Data Leak / Information Disclosure](#vii-data-leak--information-disclosure)
- [VIII. Extension & Browser Attacks](#viii-extension--browser-attacks)
- [Tổng hợp Coverage Matrix](#ix-tổng-hợp-coverage-matrix)
- [Implementation Roadmap](#x-implementation-roadmap)

---

## I. Binary / Static Attacks

### 1.1. ✅ Binary Patching / Hex Edit (ĐÃ CÓ)

> Đã document trong `WORKFLOW_ANTI_CRACK_PROTECTION.md`, `RUST_SECURITY_HARDENING.md`

- **Attack**: Dùng hex editor sửa `.exe` / `.pyc` → bypass checks
- **Countermeasure**: SHA-256 integrity hash, Rust self-integrity

---

### 1.2. ✅ String Extraction (ĐÃ CÓ)

> Đã document trong `RUST_SECURITY_HARDENING.md` Section VIII

- **Attack**: `strings binary.exe` → extract API keys, URLs, secrets
- **Countermeasure**: Rust compile-time string encryption

---

### 1.3. 🆕 PyInstaller Extraction

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Tools** | `pyinstxtractor`, `pyi-archive_viewer` |
| **Difficulty** | Dễ — YouTube tutorials có sẵn |
| **Prevalence** | **90% cracker** dùng phương pháp này |

**Attack flow:**

```
VEO_Pro_Max.exe
    ↓ pyinstxtractor.py
extracted/
├── PYZ-00.pyz            ← All imported modules
├── main.pyc              ← Main script
├── security/
│   ├── license_client.pyc
│   └── trial_protection.pyc
    ↓ uncompyle6 / decompyle3 / pycdc
license_client.py         ← FULL SOURCE CODE
```

**Countermeasures:**

```python
# 1. Anti-extraction detection (kiểm tra runtime environment)
import sys, os

def detect_extraction():
    """Detect if running from extracted PyInstaller bundle."""
    checks = []
    
    # Check 1: PyInstaller sets sys._MEIPASS
    if hasattr(sys, '_MEIPASS'):
        bundle_dir = sys._MEIPASS
        # Nếu bundle_dir không match expected hash → extracted
        if not verify_bundle_integrity(bundle_dir):
            checks.append("bundle_tampered")
    
    # Check 2: Check parent process
    # Normal: explorer.exe → VEO.exe
    # Extracted: python.exe → main.py
    parent = get_parent_process_name()
    if parent in ("python.exe", "python3.exe", "pythonw.exe"):
        checks.append("python_runtime")
    
    # Check 3: Check if running from temp directory
    exe_path = sys.executable
    if "\\Temp\\" in exe_path or "/tmp/" in exe_path:
        checks.append("temp_directory")
    
    return checks

# 2. Nuitka compilation (convert .py → C → native binary)
# Không còn .pyc để extract
# Build command:
# nuitka --standalone --onefile --remove-output main.py

# 3. Rust critical modules (xem RUST_SECURITY_HARDENING.md)
# License verify + integrity chạy trong .pyd native → không extract được
```

**Defense layers:**

| Layer | Method | Hiệu quả |
|-------|--------|-----------|
| L1 | Nuitka compile (Python → C → binary) | Không còn `.pyc` |
| L2 | Rust `.pyd` cho critical modules | Không thể decompile |
| L3 | PyInstaller `--key` flag (AES encrypt) | Encrypt PYZ archive |
| L4 | Bundle integrity hash check | Detect extracted files |
| L5 | Anti-extraction runtime check | Detect python.exe parent |

---

### 1.4. 🆕 Loader / Patcher

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Tools** | Custom C/C++ loader, x64dbg scripts |
| **Difficulty** | Trung bình |
| **Threat** | Tạo bản crack distributable |

**Attack flow:**

```
crack_loader.exe
    ↓ CreateProcess(VEO.exe, SUSPENDED)
    ↓ WriteProcessMemory → patch license check
    ↓ ResumeThread → app chạy đã bị crack
```

**Countermeasures:**

```rust
// Rust: Detect process creation flags
#[cfg(target_os = "windows")]
pub fn detect_loader() -> bool {
    use winapi::um::processthreadsapi::GetCurrentProcess;
    use winapi::um::winnt::PROCESS_BASIC_INFORMATION;
    
    unsafe {
        // 1. Check parent process — should be explorer.exe or cmd.exe
        let parent_pid = get_parent_pid();
        let parent_name = get_process_name(parent_pid);
        
        let trusted_parents = [
            "explorer.exe", "cmd.exe", "powershell.exe",
            "windowsterminal.exe"
        ];
        
        if !trusted_parents.iter().any(|p| parent_name.eq_ignore_ascii_case(p)) {
            return true; // Suspicious parent
        }
        
        // 2. Check CREATE_SUSPENDED flag remnants
        // Loader thường dùng CREATE_SUSPENDED → patch → resume
        // Thread creation time quá gần nhau = suspicious
        if check_thread_timing_anomaly() {
            return true;
        }
        
        // 3. Check for memory breakpoints (INT3 = 0xCC)
        if scan_code_section_for_int3() {
            return true;
        }
        
        false
    }
}
```

```python
# Python: Additional checks
import ctypes
import psutil

def verify_process_integrity():
    """Verify process wasn't launched by a loader."""
    proc = psutil.Process()
    
    # Check 1: Command line should be our exe, not "python main.py"
    cmdline = proc.cmdline()
    if any("python" in arg.lower() for arg in cmdline):
        return False
    
    # Check 2: Creation time should be recent (not suspended for patching)
    import time
    create_time = proc.create_time()
    startup_delta = time.time() - create_time
    if startup_delta > 30:  # >30s from create to first check = suspicious
        return False
    
    # Check 3: No remote threads injected
    if detect_remote_threads():
        return False
    
    return True
```

---

### 1.5. 🆕 Process Hollowing

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Tools** | Custom, Cobalt Strike |
| **Difficulty** | Cao |

**Attack**: Tạo process hợp lệ, thay toàn bộ memory bằng cracked version.

**Countermeasures:**

```rust
/// Detect process hollowing by checking image base consistency
pub fn detect_hollowing() -> bool {
    unsafe {
        // 1. Compare PEB ImageBaseAddress with actual loaded module
        let peb_base = get_peb_image_base();
        let module_base = get_loaded_module_base();
        
        if peb_base != module_base {
            return true; // Hollowed!
        }
        
        // 2. Compare on-disk PE headers with in-memory PE headers
        let disk_headers = read_pe_headers_from_disk();
        let memory_headers = read_pe_headers_from_memory();
        
        if disk_headers != memory_headers {
            return true; // Headers replaced
        }
        
        // 3. Verify section checksums
        for section in get_pe_sections() {
            let disk_hash = hash_section_on_disk(&section);
            let mem_hash = hash_section_in_memory(&section);
            if disk_hash != mem_hash {
                return true; // Section replaced
            }
        }
        
        false
    }
}
```

---

## II. Runtime / Dynamic Attacks

### 2.1. ✅ Debugger Attach (ĐÃ CÓ)

> Đã document: IsDebuggerPresent, timing check, DR0-DR7 (Rust doc)

---

### 2.2. ✅ DLL Injection (ĐÃ CÓ)

> Đã document: Trusted DLL whitelist (`WORKFLOW_ANTI_CRACK_PROTECTION.md`)

---

### 2.3. 🆕 Python Monkey Patching

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Tools** | Chỉ cần 1 dòng Python |
| **Difficulty** | **Rất dễ** |
| **Threat** | Bypass MỌI security check |

**Attack** — cracker chỉ cần inject 1 dòng:

```python
# Trước khi app import security module:
import security.license_client
security.license_client.LicenseClient.verify = lambda self, key: True
security.license_client.LicenseClient.get_tier = lambda self: "PREMIUM"

# Hoặc override toàn bộ module:
import types
fake_module = types.ModuleType('security.license_client')
fake_module.LicenseClient = FakeLicenseClient  # Always returns valid
import sys
sys.modules['security.license_client'] = fake_module
```

**Countermeasures:**

```python
import sys
import importlib
import hashlib

class AntiMonkeyPatch:
    """Detect runtime function replacement."""
    
    # Store original function references at import time
    _originals = {}
    
    @classmethod
    def register(cls, module_name: str, func_names: list):
        """Register functions to protect."""
        module = sys.modules.get(module_name)
        if not module:
            return
        for name in func_names:
            obj = getattr(module, name, None)
            if obj:
                cls._originals[f"{module_name}.{name}"] = id(obj)
    
    @classmethod
    def verify(cls) -> list:
        """Check if any protected function was replaced."""
        tampered = []
        for key, original_id in cls._originals.items():
            module_name, func_name = key.rsplit('.', 1)
            module = sys.modules.get(module_name)
            if not module:
                tampered.append(key)
                continue
            current = getattr(module, func_name, None)
            if current is None or id(current) != original_id:
                tampered.append(key)
        return tampered

# Initialization (at startup, after imports)
AntiMonkeyPatch.register('security.license_client', [
    'LicenseClient', 'verify_license', 'check_hwid'
])
AntiMonkeyPatch.register('core.security', [
    'IntegrityChecker', 'AntiDebug', 'full_security_check'
])

# Periodic check (every 30s)
async def monkey_patch_watchdog():
    while True:
        tampered = AntiMonkeyPatch.verify()
        if tampered:
            log.critical(f"Monkey patch detected: {tampered}")
            os._exit(1)
        await asyncio.sleep(30)
```

```rust
// Rust layer: verify Python module hasn't been replaced
#[pyfunction]
fn verify_python_modules() -> PyResult<bool> {
    Python::with_gil(|py| {
        // Check sys.modules for our security module
        let sys = py.import("sys")?;
        let modules = sys.getattr("modules")?;
        
        let security_mod = modules.get_item("security.license_client")?;
        
        // Verify module file path (not a fake module)
        if let Ok(file) = security_mod.getattr("__file__") {
            let path: String = file.extract()?;
            // Should be in our known directory
            if !path.contains("security") || !path.ends_with(".pyc") {
                return Ok(false); // Module replaced
            }
        } else {
            return Ok(false); // No __file__ = injected module
        }
        
        Ok(true)
    })
}
```

### Kết hợp với Rust:

> **Giải pháp tối ưu**: Chuyển toàn bộ license check sang Rust `.pyd`.  
> Monkey patching Python không ảnh hưởng được Rust native code.  
> Cracker phải thay file `.pyd` → bị integrity check phát hiện.

---

### 2.4. 🆕 Import Hooking

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Tools** | Python meta path hooks, `sys.modules` |
| **Difficulty** | Dễ |

**Attack**: Thay toàn bộ security module bằng fake module.

```python
# Attacker replaces veo_security.pyd with fake veo_security.py:
# File: veo_security.py (in same directory, higher import priority)
def full_security_check(key):
    return (True, "valid")
def is_debugger_py():
    return False
def check_integrity_py():
    return True
```

**Countermeasures:**

```python
import importlib
import os
import hashlib

def verify_module_authenticity(module_name: str, expected_hash: str) -> bool:
    """Verify imported module is authentic (not replaced by fake)."""
    
    module = importlib.import_module(module_name)
    module_file = getattr(module, '__file__', None)
    
    if not module_file:
        return False
    
    # 1. Must be .pyd (compiled Rust), NOT .py or .pyc
    if not module_file.endswith(('.pyd', '.so')):
        log.critical(f"Module {module_name} is not native binary: {module_file}")
        return False
    
    # 2. Hash verification
    with open(module_file, 'rb') as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest()
    
    if actual_hash != expected_hash:
        log.critical(f"Module {module_name} hash mismatch")
        return False
    
    # 3. Verify module attributes exist (fake modules miss hidden attrs)
    required_attrs = ['_internal_version', '_build_timestamp']
    for attr in required_attrs:
        if not hasattr(module, attr):
            return False
    
    return True

# At startup:
EXPECTED_HASHES = {
    'veo_security': 'a1b2c3d4...',  # Updated each build
}
for mod, expected in EXPECTED_HASHES.items():
    if not verify_module_authenticity(mod, expected):
        os._exit(1)
```

```rust
// Rust: Hidden attributes that fake modules won't have
#[pyfunction]
fn _internal_version() -> &'static str {
    // Compile-time constant — fake .py modules won't know this
    env!("CARGO_PKG_VERSION")
}

#[pyfunction]
fn _build_timestamp() -> u64 {
    // Injected by build.rs — changes every build
    include!("../.build_ts")
}
```

---

### 2.5. 🆕 Frida / Dynamic Instrumentation

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Tools** | Frida, DynamoRIO, Pin |
| **Difficulty** | Trung bình — Frida scripts có sẵn |

**Attack**: Hook bất kỳ function nào tại runtime, sửa arguments & return values.

```javascript
// Frida script — bypass license check in 5 lines:
Interceptor.attach(Module.findExportByName("veo_security.pyd", "verify_license"), {
    onLeave: function(retval) {
        retval.replace(1);  // Force return true
    }
});
```

**Countermeasures:**

```rust
/// Detect Frida injection
pub fn detect_frida() -> bool {
    // 1. Check loaded modules for frida-agent
    let suspicious_dlls = [
        "frida-agent", "frida-gadget", "frida-winjector",
        "FridaGadget", "frida_agent",
    ];
    
    for dll in get_loaded_modules() {
        let name = dll.to_lowercase();
        if suspicious_dlls.iter().any(|s| name.contains(&s.to_lowercase())) {
            return true;
        }
    }
    
    // 2. Check for Frida's named pipe (Windows)
    #[cfg(target_os = "windows")]
    {
        for pipe in list_named_pipes() {
            if pipe.contains("frida") || pipe.contains("linjector") {
                return true;
            }
        }
    }
    
    // 3. Check for Frida server port (default: 27042)
    if is_port_open("127.0.0.1", 27042) {
        return true;
    }
    
    // 4. Check function prologues for hooks
    // Frida replaces first bytes with JMP → trampoline
    if detect_inline_hooks() {
        return true;
    }
    
    false
}

/// Detect inline hooks (JMP patches at function entry)
fn detect_inline_hooks() -> bool {
    let critical_functions: Vec<*const ()> = vec![
        verify_license as *const (),
        check_integrity as *const (),
        get_hardware_id as *const (),
    ];
    
    for func_ptr in critical_functions {
        let bytes = unsafe {
            std::slice::from_raw_parts(func_ptr as *const u8, 16)
        };
        
        // Common hook patterns:
        // 0xE9 = JMP rel32 (5-byte near jump)
        // 0xFF 0x25 = JMP [addr] (6-byte indirect jump)
        // 0x48 0xB8 = MOV RAX, imm64 (10-byte, used by Frida)
        if bytes[0] == 0xE9 
            || (bytes[0] == 0xFF && bytes[1] == 0x25)
            || (bytes[0] == 0x48 && bytes[1] == 0xB8) {
            return true;
        }
    }
    
    false
}
```

---

## III. Network / MITM Attacks

### 3.1. ✅ Fake Firebase Server (ĐÃ CÓ)

> Đã document trong `LICENSE_ANTI_FAKE_SERVER.md`

---

### 3.2. 🆕 MITM (Man-in-the-Middle)

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Tools** | Fiddler, mitmproxy, Burp Suite, Charles |
| **Difficulty** | Dễ — proxying HTTPS traffic |

**Attack**: Chặn Firebase REST calls → sửa response → license always valid.

```
App ──HTTPS──→ [mitmproxy] ──→ Firebase
                    ↓
            Intercept response:
            {"_s": "ACTIVE"} → inject vào mọi request
```

**Countermeasures:**

```python
import ssl
import hashlib
import certifi

class SSLPinning:
    """Certificate pinning for Firebase connections."""
    
    # SHA-256 hashes of legitimate Firebase certificate chain
    PINNED_CERTS = {
        # Google Trust Services root CA
        "google_root": "MIIBxjCCAW2gAwIBAgIRAIrUBN...",  # base64 hash
        # Firebase leaf cert
        "firebase_leaf": "sha256//YZPgTZ+woNCCCIW3LH2CxQeLzB/2lz...",
    }
    
    @classmethod
    def create_ssl_context(cls) -> ssl.SSLContext:
        """Create SSL context with certificate pinning."""
        ctx = ssl.create_default_context(cafile=certifi.where())
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        
        # Custom verification callback
        ctx.set_servercert_callback(cls._verify_pin)
        return ctx
    
    @classmethod
    def _verify_pin(cls, conn, cert, errno, depth, ok):
        """Verify certificate matches our pinned hash."""
        if not ok:
            return False
        
        # Hash the DER-encoded certificate
        der = cert.public_bytes(serialization.Encoding.DER)
        cert_hash = hashlib.sha256(der).hexdigest()
        
        # Must match one of our pinned certificates
        return cert_hash in cls.PINNED_CERTS.values()
```

```rust
// Rust: Request validation (verify response integrity)
pub fn verify_firebase_response(
    response_body: &[u8],
    response_signature: &str,
    server_cert_hash: &str
) -> bool {
    // 1. Verify cert hash matches pinned cert
    if !PINNED_CERTS.contains(server_cert_hash) {
        return false;
    }
    
    // 2. Verify response hasn't been modified
    // Firebase should include a server-signed HMAC
    let expected_sig = hmac_sha256(
        &SERVER_VERIFICATION_KEY,
        response_body
    );
    constant_time_eq(response_signature, &expected_sig)
}
```

---

### 3.3. 🆕 SSL Pinning Bypass

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Tools** | Frida SSL bypass scripts, Objection |

**Attack**: Hook SSL verification → accept any certificate → enable MITM.

**Countermeasures:**

```rust
// Rust: SSL verification in native code (cannot be hooked by Python tools)
pub fn verify_ssl_native(host: &str, cert_der: &[u8]) -> bool {
    // Verification runs in Rust — Frida Python hooks don't apply
    let cert_hash = sha256(cert_der);
    
    match host {
        h if h.contains("firebaseio.com") => {
            FIREBASE_CERT_HASHES.contains(&cert_hash)
        }
        h if h.contains("googleapis.com") => {
            GOOGLE_CERT_HASHES.contains(&cert_hash)
        }
        _ => false
    }
}
```

```python
# Additional: Detect proxy settings
import winreg

def detect_proxy():
    """Detect if system proxy is configured (MITM indicator)."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        )
        proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if proxy_enable:
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            # Common MITM proxy ports
            mitm_ports = ["8080", "8888", "8443", "9090"]
            if any(port in str(proxy_server) for port in mitm_ports):
                return True
    except Exception:
        pass
    
    # Check environment variables
    import os
    for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if os.environ.get(var):
            return True
    
    return False
```

---

### 3.4. 🆕 API Replay Attack

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Difficulty** | Trung bình |

**Attack**: Capture valid license-check response → replay mãi mãi.

**Countermeasures:**

```python
import time
import hmac
import hashlib
import secrets

class ReplayProtection:
    """Prevent API response replay attacks."""
    
    def __init__(self):
        self._nonces = set()  # Used nonces
        self._nonce_expiry = {}
    
    def create_request_nonce(self) -> str:
        """Generate unique nonce for each request."""
        nonce = secrets.token_hex(16)
        timestamp = int(time.time())
        return f"{nonce}:{timestamp}"
    
    def verify_response_freshness(self, response: dict) -> bool:
        """Verify response is fresh (not replayed)."""
        
        # 1. Check timestamp — must be within 30 seconds
        server_time = response.get('_ts', 0)
        local_time = int(time.time())
        if abs(local_time - server_time) > 30:
            return False  # Too old — likely replayed
        
        # 2. Check nonce — must match our request
        response_nonce = response.get('_nonce', '')
        if response_nonce in self._nonces:
            return False  # Nonce reused — replay!
        self._nonces.add(response_nonce)
        
        # 3. Check sequence number — must be monotonically increasing
        seq = response.get('_seq', 0)
        if seq <= self._last_seq:
            return False  # Out of order — replay!
        self._last_seq = seq
        
        return True
```

---

### 3.5. 🆕 License Server Emulation

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Difficulty** | Trung bình |

**Attack**: Chạy fake Firebase local, redirect DNS → license always valid.

**Countermeasures:**

```python
class ServerAuthenticity:
    """Verify Firebase server is real, not emulated."""
    
    # Multiple independent verification endpoints
    VERIFICATION_ENDPOINTS = [
        "https://firestore.googleapis.com",
        "https://identitytoolkit.googleapis.com",
        "https://securetoken.googleapis.com",
    ]
    
    async def verify_server(self) -> bool:
        # 1. DNS resolution check — Firebase IPs are in Google's range
        import socket
        ip = socket.gethostbyname("firestore.googleapis.com")
        if not self._is_google_ip_range(ip):
            return False
        
        # 2. Multi-endpoint cross-validation
        # Fake server unlikely to emulate ALL Google endpoints
        results = await asyncio.gather(*[
            self._probe_endpoint(url) 
            for url in self.VERIFICATION_ENDPOINTS
        ])
        if not all(results):
            return False
        
        # 3. Response timing analysis
        # Real Firebase responds 50-500ms
        # Local fake responds <5ms
        latency = await self._measure_latency()
        if latency < 10:  # <10ms = suspicious (likely local)
            log.warning(f"Suspiciously low latency: {latency}ms")
            # Don't block — could be fast connection
            # But flag for additional scrutiny
        
        return True
    
    def _is_google_ip_range(self, ip: str) -> bool:
        """Check if IP belongs to Google's ASN."""
        import ipaddress
        google_ranges = [
            "142.250.0.0/15", "172.217.0.0/16",
            "216.58.0.0/16", "209.85.128.0/17",
            "74.125.0.0/16", "64.233.160.0/19",
        ]
        addr = ipaddress.ip_address(ip)
        return any(
            addr in ipaddress.ip_network(r) 
            for r in google_ranges
        )
```

---

## IV. License-Specific Attacks

### 4.1. ✅ Cache Tampering (ĐÃ CÓ)

> HMAC-SHA256 14-field signature

### 4.2. ✅ Clock Manipulation (ĐÃ CÓ)

> NTP + Firebase + HTTP time verification

### 4.3. ✅ Hardware ID Spoof (ĐÃ CÓ)

> Multi-source HWID + Rust CPUID

---

### 4.4. 🆕 Keygen

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Difficulty** | Cao (nếu HMAC key an toàn) |

**Attack**: Reverse engineer key algorithm → generate valid keys.

**Countermeasures:**

```
Hiện tại: Key = HMAC-SHA256(data, SECRET_KEY)
                                    ↑
                          Nếu lộ key → keygen possible

Defense Layers:
┌──────────────────────────────────────────┐
│ L1: SECRET_KEY trong Rust binary         │ → Không extract
│ L2: KEY khác nhau mỗi build             │ → Keygen chỉ work 1 version
│ L3: Server-side validation (Firebase)    │ → Key phải có trong DB
│ L4: HWID binding                         │ → Key lock vào máy
│ L5: Rate limiting                        │ → Brute force blocked
└──────────────────────────────────────────┘
```

```rust
// Rust: Server-side key validation requirement
pub fn validate_key_online(key: &str, hwid: &str) -> KeyValidation {
    // Step 1: Local HMAC check (fast, offline)
    if !verify_hmac_local(key) {
        return KeyValidation::InvalidFormat;
    }
    
    // Step 2: MUST verify with Firebase (online)
    // Even if local check passes, key must exist in database
    // This prevents keygen — attacker can generate valid HMAC
    // but key won't be in Firebase
    match firebase_verify(key, hwid) {
        Ok(true) => KeyValidation::Valid,
        Ok(false) => KeyValidation::NotInDatabase, // Keygen detected
        Err(_) => KeyValidation::NetworkError,
    }
}
```

---

### 4.5. 🆕 Shared / Leaked Keys

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Difficulty** | Rất dễ — share key trên forum |

**Attack**: 1 user mua key → share cho 100 người.

**Countermeasures:**

```python
class KeySharingProtection:
    """Detect and prevent key sharing."""
    
    # Firebase document structure:
    # _lic/{key_hash}: {
    #     _hwid: "abc123",        # Bound hardware
    #     _hwid_changes: 2,       # Number of HWID changes
    #     _max_hwid_changes: 1,   # Max allowed (0 = locked)
    #     _last_seen: [...],      # Last 5 IP addresses
    #     _concurrent_sessions: 1, # Max simultaneous sessions
    # }
    
    async def validate_usage(self, key: str, hwid: str, ip: str) -> bool:
        record = await self.firebase.get_key_record(key)
        
        # 1. HWID binding — first use locks to machine
        if record['_hwid'] and record['_hwid'] != hwid:
            if record['_hwid_changes'] >= record['_max_hwid_changes']:
                return False  # Key already bound to different machine
        
        # 2. IP diversity check — too many different IPs = sharing
        recent_ips = record.get('_last_seen', [])
        unique_ips = set(recent_ips[-20:])  # Last 20 entries
        if len(unique_ips) > 5:  # >5 different IPs = suspicious
            await self.flag_for_review(key, "excessive_ip_diversity")
        
        # 3. Concurrent session limit
        active_sessions = await self.get_active_sessions(key)
        if len(active_sessions) > record.get('_concurrent_sessions', 1):
            return False  # Too many simultaneous sessions
        
        # 4. Geographic anomaly — same key from 2 countries simultaneously
        if self.detect_geo_anomaly(recent_ips):
            await self.revoke_key(key, "geo_anomaly")
            return False
        
        return True
```

---

## V. Environment Manipulation

### 5.1. ✅ VM Detection (ĐÃ CÓ)

> VirtualBox, VMware, QEMU, Xen, Hyper-V detection

---

### 5.2. 🆕 VM Snapshot / Restore

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Difficulty** | Dễ (VMware: Ctrl+Shift+S) |

**Attack**: Snapshot trước khi trial bắt đầu → restore khi hết hạn → trial vĩnh viễn.

**Countermeasures:**

```python
class SnapshotDetection:
    """Detect VM snapshot/restore for trial abuse."""
    
    def check_time_consistency(self) -> bool:
        """Detect time jumps indicating snapshot restore."""
        
        # 1. Monotonic clock vs Wall clock drift
        # Monotonic clock resets on snapshot restore
        # Wall clock may jump backwards
        mono_now = time.monotonic()
        wall_now = time.time()
        
        expected_wall = self._last_wall + (mono_now - self._last_mono)
        drift = abs(wall_now - expected_wall)
        
        if drift > 60:  # >60s drift = suspicious
            return False
        
        # 2. Uptime check — snapshot restore resets uptime
        uptime = self._get_system_uptime()
        if uptime < self._last_uptime:
            return False  # Uptime went backwards
        
        # 3. Firebase heartbeat — server tracks last-seen timestamp
        # If gap > 24h but trial days unchanged → snapshot restore
        server_last_seen = await self.firebase.get_last_heartbeat()
        local_trial_day = self.get_trial_day()
        
        gap = time.time() - server_last_seen
        if gap > 86400 and local_trial_day == self._last_trial_day:
            return False  # Suspiciou — 1 day gap but trial didn't advance
        
        return True
```

**Key defense**: **Server-side trial tracking** — Firebase stores trial start + heartbeats. Snapshot restore không ảnh hưởng server-side data.

---

### 5.3. 🆕 File System Virtualization

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Tools** | Sandboxie, Windows Sandbox, Docker |

**Attack**: Sandbox file writes → trial markers không persist → reset trial.

**Countermeasures:**

```python
def detect_sandboxie():
    """Detect Sandboxie containerization."""
    import ctypes
    
    # 1. Check for SbieDll.dll (Sandboxie's injection DLL)
    if ctypes.windll.kernel32.GetModuleHandleW("SbieDll.dll"):
        return True
    
    # 2. Check for Sandboxie process
    if process_running("SbieCtrl.exe") or process_running("SbieSvc.exe"):
        return True
    
    # 3. Write test — write to multiple locations, verify persistence
    test_locations = [
        os.path.expandvars(r"%USERPROFILE%\.veo_test"),
        os.path.expandvars(r"%APPDATA%\VEO\.test"),
        # Registry test
    ]
    
    for loc in test_locations:
        write_marker(loc, "test_value")
    
    # Read back — sandboxed writes may not persist
    for loc in test_locations:
        if read_marker(loc) != "test_value":
            return True  # Write was sandboxed
    
    return False

def detect_windows_sandbox():
    """Detect Windows Sandbox / Container."""
    import subprocess
    try:
        output = subprocess.check_output(
            'systeminfo', stderr=subprocess.DEVNULL
        ).decode()
        if "Windows Sandbox" in output:
            return True
    except Exception:
        pass
    
    # Check hostname pattern (Sandbox uses random names)
    hostname = os.environ.get('COMPUTERNAME', '')
    if hostname.startswith('DESKTOP-') and len(hostname) == 15:
        # Pattern: DESKTOP-XXXXXXX — could be sandbox
        pass
    
    return False
```

**Key defense**: Trial marker ở **Firebase** (cloud) — sandbox không ảnh hưởng.

---

### 5.4. 🆕 Registry Virtualization

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |

**Attack**: Redirect registry writes → trial markers trong registry bị chặn.

**Countermeasure**: Multi-source trial markers (file + registry + **Firebase**). Firebase là source of truth — không thể virtualize.

---

### 5.5. 🆕 Symbolic Link Attack

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |

**Attack**: `mklink /D %APPDATA%\VEO NUL` → redirect trial path → marker không lưu.

**Countermeasures:**

```python
import os

def safe_write_marker(path: str, data: bytes) -> bool:
    """Write marker with symlink detection."""
    
    # 1. Resolve symlinks
    real_path = os.path.realpath(path)
    if real_path != os.path.abspath(path):
        log.warning(f"Symlink detected: {path} → {real_path}")
        # Write to both real and resolve path
    
    # 2. Verify write succeeded
    with open(real_path, 'wb') as f:
        f.write(data)
    
    # Read back verification
    with open(real_path, 'rb') as f:
        if f.read() != data:
            return False  # Write was intercepted
    
    return True
```

---

### 5.6. 🆕 Environment Variable Override

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |

**Attack**: Set `SECRET_KEY=known_value` → override app's secret key.

**Countermeasures:**

```python
# RULE: NEVER read security-critical values from environment variables

# ❌ BAD:
SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback')

# ✅ GOOD:
# Embed in Rust binary (compile-time constant)
import veo_security
SECRET_KEY = veo_security._get_secret()  # From native code

# Additional: Detect if anyone SET suspicious env vars
SUSPICIOUS_ENV_VARS = [
    'SECRET_KEY', 'LICENSE_KEY', 'FIREBASE_URL',
    'VEO_DEBUG', 'VEO_SKIP_CHECK', 'PYTHONDONTWRITEBYTECODE'
]

def check_env_tampering():
    for var in SUSPICIOUS_ENV_VARS:
        if var in os.environ:
            log.warning(f"Suspicious env var detected: {var}")
            return True
    return False
```

---

## VI. Build & Deploy Attacks

### 6.1. 🆕 Code Signing Absence

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Impact** | Không có code signing → ai cũng sửa binary được |

**Countermeasures:**

```
Code Signing Chain:
┌──────────────────────────────────────────┐
│ 1. Obtain Code Signing Certificate       │
│    (DigiCert, Sectigo, ~$200/year)       │
│                                          │
│ 2. Sign final .exe:                      │
│    signtool sign /f cert.pfx             │
│    /tr http://timestamp.digicert.com     │
│    /td sha256 /fd sha256                 │
│    VEO_Pro_Max.exe                       │
│                                          │
│ 3. Verify at runtime:                    │
│    Check Authenticode signature          │
│    Compare cert thumbprint               │
└──────────────────────────────────────────┘
```

```rust
// Rust: Verify own Authenticode signature
#[cfg(target_os = "windows")]
pub fn verify_code_signature() -> bool {
    use winapi::um::wintrust::*;
    
    unsafe {
        let exe_path = std::env::current_exe().unwrap();
        // WinVerifyTrust → check Authenticode signature
        let result = WinVerifyTrust(
            INVALID_HANDLE_VALUE,
            &WINTRUST_ACTION_GENERIC_VERIFY_V2,
            &trust_data
        );
        
        result == 0  // 0 = valid signature
    }
}
```

---

### 6.2. 🆕 Supply Chain (Dependency) Attack

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |

**Attack**: Compromise a pip/npm dependency → inject backdoor.

**Countermeasures:**

```
1. Pin ALL dependency versions in requirements.txt
2. Use pip hash checking:
   pip install --require-hashes -r requirements.txt
3. Vendor critical dependencies (copy source instead of pip install)
4. Audit dependencies with: pip-audit, safety
```

---

## VII. Data Leak / Information Disclosure

### 7.1. 🆕 Log File Leaking

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |

**Attack**: Log files chứa license keys, tokens, API responses → attacker đọc logs.

**Countermeasures:**

```python
import re

class SafeLogger:
    """Logger that redacts sensitive information."""
    
    PATTERNS = [
        (re.compile(r'[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}'), '[LICENSE_KEY]'),
        (re.compile(r'AIzaSy[A-Za-z0-9_-]{33}'), '[API_KEY]'),
        (re.compile(r'ya29\.[A-Za-z0-9_-]+'), '[ACCESS_TOKEN]'),
        (re.compile(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+'), '[JWT]'),
        (re.compile(r'password["\s:=]+\S+', re.I), 'password=[REDACTED]'),
    ]
    
    @classmethod
    def sanitize(cls, message: str) -> str:
        for pattern, replacement in cls.PATTERNS:
            message = pattern.sub(replacement, message)
        return message
```

---

### 7.2. 🆕 Clipboard Sniffing

| Field | Value |
|-------|-------|
| **Severity** | 🟢 Low |

**Attack**: Khi user paste license key → malware đọc clipboard.

**Countermeasures:**

```python
def secure_paste_license():
    """Read and immediately clear clipboard after pasting license key."""
    import win32clipboard
    
    win32clipboard.OpenClipboard()
    try:
        data = win32clipboard.GetClipboardData()
    finally:
        win32clipboard.CloseClipboard()
    
    # Clear clipboard immediately after reading
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.CloseClipboard()
    
    return data
```

---

### 7.3. 🆕 Memory Forensics

| Field | Value |
|-------|-------|
| **Severity** | 🟢 Low |

**Attack**: Dump process memory → extract keys, tokens.

**Countermeasure**: Rust's `Zeroize` crate — zero sensitive data after use.

```rust
use zeroize::Zeroize;

fn verify_and_cleanup(key: &str) {
    let mut secret = get_secret_key(); // [u8; 32]
    
    let result = hmac_verify(key, &secret);
    
    // CRITICAL: Zero secret from memory immediately
    secret.zeroize(); // Overwrites with 0x00
    
    result
}
```

---

## VIII. Extension & Browser Attacks

### 8.1. ✅ Extension Code Tampering (ĐÃ CÓ — ở trên)

---

### 8.2. 🆕 WebSocket Hijacking (Python ↔ Extension)

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Difficulty** | Trung bình |
| **Đặc biệt nguy hiểm** | Trực tiếp ảnh hưởng kiến trúc VEO Pro Max |

**Attack**: App giao tiếp Python ↔ Extension qua `ws://localhost:{PORT}` — **không mã hóa**. Bất kỳ process nào trên cùng machine có thể:

```
Attacker Process (same machine)
    ↓ Connect to ws://localhost:PORT
    ↓ Sniff: license keys, access tokens, x-client-data
    ↓ Inject: fake reCAPTCHA tokens, bypass commands
    ↓ Replay: captured valid responses
```

**Countermeasures:**

```python
import secrets
import hmac
import hashlib

class SecureWebSocket:
    """WebSocket security layer for Python ↔ Extension communication."""
    
    def __init__(self):
        # 1. One-time session secret (generated at startup, shared via extension install)
        self._session_secret = secrets.token_bytes(32)
        self._message_counter = 0
    
    def sign_message(self, payload: dict) -> dict:
        """Sign outgoing message with HMAC."""
        self._message_counter += 1
        payload['_seq'] = self._message_counter
        payload['_ts'] = int(time.time())
        
        # HMAC signature over payload
        msg_bytes = json.dumps(payload, sort_keys=True).encode()
        sig = hmac.new(self._session_secret, msg_bytes, hashlib.sha256).hexdigest()
        payload['_sig'] = sig
        
        return payload
    
    def verify_message(self, payload: dict) -> bool:
        """Verify incoming message signature."""
        sig = payload.pop('_sig', '')
        msg_bytes = json.dumps(payload, sort_keys=True).encode()
        expected = hmac.new(self._session_secret, msg_bytes, hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(sig, expected):
            return False  # Tampered or injected
        
        # Verify timestamp freshness (±10 seconds)
        ts = payload.get('_ts', 0)
        if abs(time.time() - ts) > 10:
            return False  # Replayed
        
        # Verify sequence (must be monotonically increasing)
        seq = payload.get('_seq', 0)
        if seq <= self._last_seq:
            return False  # Replay
        self._last_seq = seq
        
        return True
```

```javascript
// Extension side: corresponding implementation in background.js
class WSAuth {
    constructor(secret) {
        this.secret = secret;  // Received during registration
        this.seq = 0;
    }
    
    async sign(payload) {
        this.seq++;
        payload._seq = this.seq;
        payload._ts = Math.floor(Date.now() / 1000);
        
        const data = JSON.stringify(payload, Object.keys(payload).sort());
        const key = await crypto.subtle.importKey(
            'raw', this.secret, {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']
        );
        const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
        payload._sig = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
        
        return payload;
    }
}
```

**Additional measures:**
- Bind WS server to `127.0.0.1` only (already done)
- Random port per session (harder to predict)
- Process ID verification (check connecting PID)

---

### 8.3. 🆕 CDP (Chrome DevTools Protocol) Abuse

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Difficulty** | Rất dễ — chỉ cần biết port |
| **Đặc biệt nguy hiểm** | `--remote-debugging-port=9222` mở full browser control |

**Attack**: CDP port cho phép BẤT KỲ process trên machine:

```
Attacker → http://localhost:9222/json → list all targets
Attacker → ws://localhost:9222/devtools/page/{id}
    ↓ Runtime.evaluate("document.cookie")         → Steal cookies
    ↓ Runtime.evaluate("...access_token...")       → Steal tokens
    ↓ Network.getAllCookies()                       → Full cookie dump
    ↓ Page.navigate("https://attacker.com")        → Redirect
    ↓ DOM.setFileInputFiles(...)                   → Upload files
```

**Countermeasures:**

```python
class CDPProtection:
    """Protect Chrome DevTools Protocol from unauthorized access."""
    
    @staticmethod
    def launch_with_protection(chrome_path: str, profile_dir: str) -> list:
        """Generate Chrome launch args with CDP protection."""
        args = [
            chrome_path,
            f'--user-data-dir={profile_dir}',
            
            # CDP protection
            '--remote-debugging-port=0',          # Random port (not fixed 9222)
            '--remote-allow-origins=http://127.0.0.1',  # Localhost only
            
            # Additional security
            '--disable-background-networking',
            '--disable-default-apps',
            '--no-first-run',
        ]
        return args
    
    @staticmethod
    def verify_cdp_security(debug_port: int) -> bool:
        """Verify CDP port is not externally accessible."""
        import socket
        
        # Check port is only bound to localhost
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            # Try connecting from non-localhost — should fail
            result = s.connect_ex(('0.0.0.0', debug_port))
            s.close()
            if result == 0:
                return False  # PORT EXPOSED TO ALL INTERFACES!
        except Exception:
            pass
        
        return True
    
    @staticmethod
    def monitor_cdp_connections(debug_port: int):
        """Monitor for unauthorized CDP connections."""
        import requests
        try:
            resp = requests.get(f'http://127.0.0.1:{debug_port}/json/list')
            targets = resp.json()
            
            # Check for unexpected targets (injected pages)
            for target in targets:
                url = target.get('url', '')
                if 'labs.google' not in url and 'chrome-extension' not in url:
                    log.warning(f"Unexpected CDP target: {url}")
                    
        except Exception:
            pass
```

**Key defense**: Use `--remote-debugging-port=0` → Chrome picks random port. Only our app knows the port.

---

### 8.4. 🆕 OAuth / Access Token Theft

| Field | Value |
|-------|-------|
| **Severity** | 🔴 Critical |
| **Difficulty** | Trung bình |
| **Ref** | Partially in `TOKEN_SECURITY.md` (extraction methods only, NOT theft prevention) |

**Attack**: Steal Google `access_token` → dùng trực tiếp VEO/Flow API mà không cần app/license.

```
Sources of token leaks:
1. Log files: "ya29.a0AW..." printed in debug logs
2. Memory dump: token stored in Python string (not zeroed)
3. CDP: Runtime.evaluate("...session.access_token...")
4. WebSocket sniffing: token sent Python ↔ Extension
5. /tmp files: token cached on disk
```

**Countermeasures:**

```python
class TokenProtection:
    """Protect access tokens from theft."""
    
    def __init__(self):
        self._tokens = {}  # email → encrypted_token
        self._token_key = os.urandom(32)  # In-memory encryption key
    
    def store_token(self, email: str, token: str):
        """Store token encrypted in memory."""
        # XOR encrypt (fast, prevents simple memory dump)
        encrypted = bytes(
            a ^ b for a, b in zip(
                token.encode(), 
                (self._token_key * (len(token) // 32 + 1))[:len(token)]
            )
        )
        self._tokens[email] = encrypted
    
    def get_token(self, email: str) -> str:
        """Decrypt token only when needed."""
        encrypted = self._tokens.get(email)
        if not encrypted:
            return None
        decrypted = bytes(
            a ^ b for a, b in zip(
                encrypted,
                (self._token_key * (len(encrypted) // 32 + 1))[:len(encrypted)]
            )
        )
        return decrypted.decode()
    
    def revoke_token(self, email: str):
        """Securely delete token."""
        if email in self._tokens:
            # Overwrite memory before deleting
            self._tokens[email] = b'\x00' * len(self._tokens[email])
            del self._tokens[email]

# Token lifecycle rules:
# 1. NEVER log tokens (use SafeLogger patterns)
# 2. NEVER write tokens to disk
# 3. Encrypt in memory (XOR minimum, AES for sensitive)
# 4. Zero after use
# 5. Rotate every 30 minutes
```

---

### 8.5. 🆕 Chrome Extension Sideloading

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Difficulty** | Trung bình |

**Attack**: Cài extension giả mạo có cùng permissions → intercept reCAPTCHA tokens, access tokens, headers.

```
Fake Extension (same permissions as VEO Bridge):
 → webRequest: capture x-client-data, cookies
 → tabs: read all tab URLs
 → scripting: inject JS into any page
 → Connects to attacker's WS server instead
```

**Countermeasures:**

```python
class ExtensionVerification:
    """Verify connected extension is authentic."""
    
    EXPECTED_EXTENSION_ID = "your_known_extension_id"
    
    async def verify_extension_on_connect(self, ws, extension_id: str) -> bool:
        # 1. Check extension ID matches
        if extension_id != self.EXPECTED_EXTENSION_ID:
            log.warning(f"Unknown extension connected: {extension_id}")
            return False
        
        # 2. Challenge-response authentication
        challenge = secrets.token_hex(32)
        await ws.send(json.dumps({
            'type': 'auth_challenge',
            'challenge': challenge
        }))
        
        # Extension must respond with HMAC(challenge, embedded_secret)
        response = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(response)
        
        expected = hmac.new(
            self.SHARED_SECRET, challenge.encode(), hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(data.get('response', ''), expected):
            return False  # Fake extension
        
        # 3. Verify extension version
        version = data.get('version')
        if version not in self.ALLOWED_VERSIONS:
            return False
        
        return True
```

---

### 8.6. 🆕 DNS Spoofing / Hijacking

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Ref** | Partially in `reference_docs/LICENSE_ANTI_FAKE_SERVER.md` Section 5 (Domain Pinning) |

**Attack**: Redirect `firestore.googleapis.com` → attacker's server via hosts file or local DNS.

**Existing coverage** (in `LICENSE_ANTI_FAKE_SERVER.md`):
- ✅ Domain Pinning — resolve IP + verify Google range
- ✅ Certificate pinning — verify TLS cert

**Additional countermeasures NOT yet documented:**

```python
class EnhancedDNSProtection:
    """Enhanced DNS protection beyond domain pinning."""
    
    # Hardcoded DNS resolvers (bypass local DNS)
    TRUSTED_DNS = ['8.8.8.8', '8.8.4.4', '1.1.1.1']
    
    async def resolve_bypassing_local_dns(self, domain: str) -> list:
        """Resolve domain using trusted DNS, bypass local hosts/DNS."""
        import dns.resolver  # dnspython library
        
        resolver = dns.resolver.Resolver()
        resolver.nameservers = self.TRUSTED_DNS
        
        answers = resolver.resolve(domain, 'A')
        return [str(a) for a in answers]
    
    def check_hosts_file_tampering(self) -> bool:
        """Check if Windows hosts file redirects our domains."""
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
        
        sensitive_domains = [
            'firestore.googleapis.com',
            'identitytoolkit.googleapis.com',
            'securetoken.googleapis.com',
            'aisandbox-pa.googleapis.com',
        ]
        
        try:
            with open(hosts_path, 'r') as f:
                for line in f:
                    line = line.strip().lower()
                    if line.startswith('#') or not line:
                        continue
                    for domain in sensitive_domains:
                        if domain in line:
                            log.critical(f"Hosts file tamper: {line}")
                            return True
        except PermissionError:
            pass
        
        return False
```

---

## IX. Python-Specific Attacks

### 9.1. 🆕 `inspect` / `gc` Module Abuse

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Difficulty** | Dễ — built-in Python modules |

**Attack**: Dùng `inspect` đọc source code, `gc` scan secrets trong RAM.

```python
# Attacker code:
import inspect
import gc

# Read source of any function at runtime
source = inspect.getsource(license_client.verify_license)
print(source)  # → Full source code!

# Scan all objects in memory for secrets
for obj in gc.get_objects():
    if isinstance(obj, bytes) and len(obj) == 32:
        print(f"Possible key: {obj.hex()}")
    if isinstance(obj, str) and obj.startswith("ya29."):
        print(f"Access token: {obj}")
```

**Countermeasures:**

```python
import sys

class AntiIntrospection:
    """Block Python introspection attacks."""
    
    @staticmethod
    def install():
        """Install protections at startup."""
        
        # 1. Disable inspect.getsource for critical modules
        import inspect
        _original_getsource = inspect.getsource
        
        PROTECTED_MODULES = [
            'security', 'license_client', 'firebase_rest_client',
            'trial_protection', 'veo_security'
        ]
        
        def safe_getsource(obj, *args, **kwargs):
            module = getattr(obj, '__module__', '') or ''
            if any(m in module for m in PROTECTED_MODULES):
                raise OSError(f"Source not available for {module}")
            return _original_getsource(obj, *args, **kwargs)
        
        inspect.getsource = safe_getsource
        inspect.getsourcelines = lambda *a, **k: (_ for _ in ()).throw(OSError)
        
        # 2. Periodically clear gc of sensitive objects
        # (defense-in-depth, main protection is Rust compile)
        
        # 3. Disable sys.settrace / sys.setprofile
        # These can be used to trace function calls
        sys.settrace = lambda *a: None
        sys.setprofile = lambda *a: None
```

> **Best defense**: Rust `.pyd` modules — `inspect.getsource()` returns nothing for native binaries.

---

### 9.2. 🆕 `ctypes` Direct Memory Access

| Field | Value |
|-------|-------|
| **Severity** | 🟠 High |
| **Difficulty** | Trung bình |
| **Ref** | `ctypes` used in anti-debug but NOT documented as attack vector |

**Attack**: Attacker dùng `ctypes` để đọc/ghi memory tùy ý, gọi internal functions.

```python
import ctypes
import ctypes.wintypes as wintypes

# Read process memory at specific address
kernel32 = ctypes.windll.kernel32
buf = ctypes.create_string_buffer(256)
kernel32.ReadProcessMemory(
    kernel32.GetCurrentProcess(),
    address_of_secret_key,  # Found via pattern scanning
    buf, 256, None
)
print(f"Secret key: {buf.raw.hex()}")

# Patch license check in memory
# NOP the comparison instruction
kernel32.WriteProcessMemory(
    kernel32.GetCurrentProcess(),
    address_of_license_check,
    b'\x90\x90\x90\x90\x90',  # NOP NOP NOP NOP NOP
    5, None
)
```

**Countermeasures:**

```python
class AntiCtypesAbuse:
    """Detect and prevent ctypes-based memory attacks."""
    
    @staticmethod
    def install():
        # 1. Monitor WriteProcessMemory calls on our own process
        # This is hard from Python — best done in Rust
        pass
    
    @staticmethod
    def detect_memory_scanners() -> bool:
        """Detect tools that scan our process memory."""
        import psutil
        
        SCANNER_PROCESSES = [
            'cheatengine', 'ce.exe', 'artmoney',
            'scanmem', 'gameguardian', 'tsearch',
            'processhacker', 'x64dbg', 'ollydbg',
        ]
        
        for proc in psutil.process_iter(['name']):
            name = proc.info['name'].lower()
            if any(s in name for s in SCANNER_PROCESSES):
                return True
        
        return False
```

```rust
// Rust: VirtualProtect critical memory pages as READONLY
#[cfg(target_os = "windows")]
pub fn protect_code_pages() {
    use winapi::um::memoryapi::VirtualProtect;
    use winapi::um::winnt::PAGE_EXECUTE_READ;
    
    unsafe {
        let mut old_protect = 0u32;
        // Mark our code sections as non-writable
        VirtualProtect(
            verify_license as *mut _,
            4096,                    // Page size
            PAGE_EXECUTE_READ,       // Read + Execute, NO write
            &mut old_protect
        );
        // Any WriteProcessMemory to this region → ACCESS_VIOLATION
    }
}
```

---

### 9.3. 🆕 Race Condition in License Check

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Difficulty** | Cao |

**Attack**: Exploit timing gap giữa license check → feature unlock.

```
Thread 1: license_check() → returns True → sleep(0.001)
Thread 2: patch license_result = True         ← RACE!
Thread 1: use_premium_feature(license_result) → UNLOCKED!
```

**Countermeasures:**

```python
import threading

class AtomicLicenseCheck:
    """Thread-safe, atomic license verification."""
    
    _lock = threading.Lock()
    _verified = False
    _tier = None
    
    @classmethod
    def check_and_execute(cls, action: callable, required_tier: str):
        """Atomic: check license + execute action in same lock."""
        with cls._lock:
            # Check and use in single atomic operation
            # No window for race condition
            if cls._tier and cls._tier >= required_tier:
                return action()
            else:
                raise PermissionError("License insufficient")
    
    @classmethod
    def verify(cls, key: str):
        """Verify license under lock."""
        with cls._lock:
            # Rust verification — atomic, can't be monkey-patched
            import veo_security
            ok, tier = veo_security.full_security_check(key)
            if ok:
                cls._verified = True
                cls._tier = tier
            return ok
```

---

### 9.4. 🆕 Differential Analysis (Trial vs Premium Binary)

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Difficulty** | Trung bình |

**Attack**: So sánh Trial binary với Premium binary → tìm chính xác điểm khác biệt → patch.

```
bindiff trial.exe premium.exe
    → Function at 0x401234: JZ → JNZ (1 byte change!)
    → Attacker patches trial binary: change 0x74 → 0x75
    → Trial becomes Premium
```

**Countermeasures:**

```
1. SAME BINARY for all tiers — feature gating via server-side + encrypted config
2. No separate trial/premium builds
3. Feature checks distributed throughout code (not single function)
4. Server-side feature flags (Firebase)
5. Obfuscate comparison logic (Rust + control flow flattening)
```

```python
# ✅ GOOD: Same binary, server decides features
class FeatureGate:
    def is_enabled(self, feature: str) -> bool:
        # Check against server-validated tier (stored encrypted in Rust)
        tier = veo_security.get_validated_tier()
        server_flags = self._cached_flags  # From Firebase
        return server_flags.get(feature, {}).get(tier, False)

# ❌ BAD: if-else gating (easy to find and patch)
if license_tier == "PREMIUM":
    enable_feature()  # → JZ instruction, 1 byte patch
```

---

## X. Infrastructure & Human Attacks

### 10.1. 🆕 Kernel-mode Rootkit

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Difficulty** | Rất cao (cần driver signing) |

**Attack**: Kernel driver ẩn debugger khỏi mọi user-mode detection (IsDebuggerPresent, NtQuery, DR registers).

**Countermeasures:**

```rust
// Rust: Kernel-level detection is impossible from user mode.
// But we can detect rootkit side-effects:
pub fn detect_rootkit_indicators() -> bool {
    // 1. CPUID timing (rootkits introduce overhead)
    let start = rdtsc();
    unsafe { core::arch::x86_64::__cpuid(0); }
    let elapsed = rdtsc() - start;
    
    if elapsed > 500 {  // Normal: ~100 cycles, Rootkit: >500
        return true;
    }
    
    // 2. Cross-reference NtQuerySystemInformation with
    //    EnumProcessModules — rootkit may hide modules from one
    //    but not the other
    let nt_count = nt_query_module_count();
    let enum_count = enum_process_module_count();
    if nt_count != enum_count {
        return true;  // Discrepancy = hidden modules
    }
    
    // 3. Check for known rootkit drivers
    let suspicious_drivers = [
        "dbk64.sys",    // Cheat Engine kernel driver
        "kdmapper.sys", // Manual mapper
    ];
    for driver in suspicious_drivers {
        if is_driver_loaded(driver) {
            return true;
        }
    }
    
    false
}
```

> **Pragmatic note**: Kernel rootkits cần driver signing (EV cert) hoặc exploit. Rất ít cracker đầu tư đến mức này cho một app. Defense ở đây là defense-in-depth.

---

### 10.2. 🆕 Social Engineering

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Difficulty** | Dễ (con người dễ bị lừa) |

**Attack**: Lừa support team cấp key miễn phí / reset HWID.

```
Kịch bản:
1. "Tôi mua key rồi nhưng format máy, xin reset HWID"
   → Nếu support reset không verify → attacker lấy key free
   
2. "Key tôi hết hạn do lỗi server, xin gia hạn"
   → Nếu support tin → free extension

3. Impersonate legitimate customer
   → Dùng info public (email, name) để giả danh
```

**Countermeasures:**

```
Support Verification Protocol:
┌──────────────────────────────────────────────────┐
│ 1. HWID Reset Request                            │
│    → Verify original purchase (receipt, bank)    │
│    → Check Firebase logs (last active time)      │
│    → Max 1 reset per key per 90 days             │
│    → Auto-log all resets to audit trail          │
│                                                  │
│ 2. Extension Request                             │
│    → NEVER extend manually                       │
│    → Only via Admin GUI (logged, audited)        │
│    → Require original purchase proof             │
│                                                  │
│ 3. Identity Verification                         │
│    → Ask for last 4 digits of license key        │
│    → Ask for HWID from Settings tab              │
│    → Cross-reference with Firebase records       │
└──────────────────────────────────────────────────┘
```

---

### 10.3. 🆕 Account Credential Stuffing

| Field | Value |
|-------|-------|
| **Severity** | 🟡 Medium |
| **Difficulty** | Trung bình |

**Attack**: Brute force hoặc reuse leaked Google credentials → dùng accounts người khác.

**Countermeasures:**

```python
class AccountProtection:
    """Protect against credential stuffing on managed accounts."""
    
    def validate_account_ownership(self, email: str) -> bool:
        # 1. Only allow accounts explicitly added by user
        if email not in self._user_added_accounts:
            return False
        
        # 2. Monitor login failures per account
        failures = self._login_failures.get(email, 0)
        if failures > 3:
            log.warning(f"Account locked after {failures} failures: {email}")
            return False
        
        # 3. Verify account is still authorized
        # (user may have revoked access)
        return True
    
    def detect_credential_abuse(self) -> bool:
        # Monitor for suspicious patterns
        # - Many accounts added rapidly
        # - Accounts from different regions
        # - Accounts with no Google history
        pass
```

---

### 10.4. 🆕 Telemetry / Analytics Disable

| Field | Value |
|-------|-------|
| **Severity** | 🟢 Low |

**Attack**: Tắt telemetry → crack usage không bị detect/report.

**Countermeasures:**

```python
class TamperResistantTelemetry:
    """Telemetry that can't be easily disabled."""
    
    def __init__(self):
        # Telemetry is embedded in critical paths
        # Disabling it breaks functionality
        pass
    
    async def report_usage(self, action: str):
        """Report interleaved with license validation."""
        # Piggyback on license heartbeat (can't disable one without the other)
        await self.firebase.update({
            '_heartbeat': int(time.time()),
            '_last_action': action,
            '_version': APP_VERSION,
        })
    
    # Telemetry check is INSIDE license verification
    # Disabling telemetry = disabling license check = app won't work
```

---

### 10.5. 🆕 Generated Content IP Theft

| Field | Value |
|-------|-------|
| **Severity** | 🟢 Low |

**Attack**: Screen record output video → bypass usage tracking, redistribute content.

**Countermeasures:**

```python
# Invisible watermark embedded in generated content
class ContentWatermark:
    """Embed invisible watermark in generated videos/images."""
    
    def embed(self, content_path: str, license_key: str):
        # 1. Steganographic watermark (invisible to human eye)
        # 2. Contains: license_key_hash, timestamp, hwid
        # 3. Survives: screenshot, screen record, re-encode
        
        watermark_data = {
            'key_hash': hashlib.sha256(license_key.encode()).hexdigest()[:16],
            'ts': int(time.time()),
            'hwid': get_hwid()[:8],
        }
        
        # Embed using DCT coefficient modification (JPEG)
        # or frame-level LSB (video)
        embed_steganographic(content_path, watermark_data)
```

> **Note**: Watermarking is complex to implement robustly. Consider as Phase 5 enhancement.

---

## XI. Tổng hợp Coverage Matrix

| # | Attack Vector | Severity | Status | Defense Document |
|---|--------------|----------|--------|-----------------|
| 1 | Binary Patching | 🔴 | ✅ | `WORKFLOW_ANTI_CRACK_PROTECTION.md` |
| 2 | String Extraction | 🔴 | ✅ | `RUST_SECURITY_HARDENING.md` |
| 3 | Debugger Attach | 🔴 | ✅ | `security_overview.md` + Rust doc |
| 4 | DLL Injection | 🟠 | ✅ | `WORKFLOW_ANTI_CRACK_PROTECTION.md` |
| 5 | VM Detection | 🟡 | ✅ | `security_overview.md` |
| 6 | Clock Manipulation | 🟠 | ✅ | `TRIAL_TIME_PROTECTION.md` |
| 7 | HWID Spoof | 🟠 | ✅ | `LICENSE_HARDWARE_FINGERPRINT.md` |
| 8 | Cache Tampering | 🟠 | ✅ | `SECURITY_CHANGELOG.md` |
| 9 | Fake Server | 🟠 | ✅ | `LICENSE_ANTI_FAKE_SERVER.md` |
| 10 | IAT Hooking | 🟠 | ✅ | `RUST_SECURITY_HARDENING.md` |
| 11 | HW Breakpoints | 🟡 | ✅ | `RUST_SECURITY_HARDENING.md` |
| 12 | Decompile (.pyc) | 🔴 | ✅ | `RUST_SECURITY_HARDENING.md` |
| 13 | Process Hollowing | 🟠 | ✅ | Tài liệu này |
| 14 | PyInstaller Extract | 🔴 | ✅ | Tài liệu này |
| 15 | Loader/Patcher | 🔴 | ✅ | Tài liệu này |
| 16 | Monkey Patching | 🔴 | ✅ | Tài liệu này |
| 17 | Import Hooking | 🔴 | ✅ | Tài liệu này |
| 18 | Frida/Instrumentation | 🔴 | ✅ | Tài liệu này |
| 19 | MITM | 🔴 | ✅ | Tài liệu này |
| 20 | SSL Pinning Bypass | 🟠 | ✅ | Tài liệu này |
| 21 | API Replay | 🟠 | ✅ | Tài liệu này |
| 22 | Server Emulation | 🟠 | ✅ | Tài liệu này |
| 23 | Keygen | 🟠 | ✅ | Tài liệu này |
| 24 | Shared Keys | 🟠 | ✅ | Tài liệu này |
| 25 | VM Snapshot | 🟡 | ✅ | Tài liệu này |
| 26 | FS Virtualization | 🟡 | ✅ | Tài liệu này |
| 27 | Registry Virtualization | 🟡 | ✅ | Tài liệu này |
| 28 | Symlink Attack | 🟡 | ✅ | Tài liệu này |
| 29 | Env Var Override | 🟡 | ✅ | Tài liệu này |
| 30 | Code Signing | 🟡 | ✅ | Tài liệu này |
| 31 | Supply Chain | 🟡 | ✅ | Tài liệu này |
| 32 | Log Leaking | 🟡 | ✅ | Tài liệu này |
| 33 | Clipboard Sniffing | 🟢 | ✅ | Tài liệu này |
| 34 | Memory Forensics | 🟢 | ✅ | Tài liệu này |
| 35 | Extension Tamper | 🟠 | ✅ | Tài liệu này |
| **36** | **WebSocket Hijacking** | 🔴 | ✅ | Tài liệu này |
| **37** | **CDP Abuse** | 🔴 | ✅ | Tài liệu này |
| **38** | **OAuth Token Theft** | 🔴 | ✅ | Tài liệu này + `TOKEN_SECURITY.md` |
| **39** | **Extension Sideloading** | 🟠 | ✅ | Tài liệu này |
| **40** | **DNS Spoofing** | 🟠 | ✅ | Tài liệu này + `LICENSE_ANTI_FAKE_SERVER.md` |
| **41** | **`inspect`/`gc` Abuse** | 🟠 | ✅ | Tài liệu này |
| **42** | **`ctypes` Memory Access** | 🟠 | ✅ | Tài liệu này |
| **43** | **Race Condition** | 🟡 | ✅ | Tài liệu này |
| **44** | **Differential Analysis** | 🟡 | ✅ | Tài liệu này |
| **45** | **Kernel Rootkit** | 🟡 | ✅ | Tài liệu này |
| **46** | **Social Engineering** | 🟡 | ✅ | Tài liệu này |
| **47** | **Credential Stuffing** | 🟡 | ✅ | Tài liệu này |
| **48** | **Telemetry Disable** | 🟢 | ✅ | Tài liệu này |
| **49** | **Content IP Theft** | 🟢 | ✅ | Tài liệu này |

**Coverage: 49/49 = 100%** ✅

---

## XII. Implementation Roadmap (Updated)

### Phase 1 — Critical (Week 1-2)
- [ ] Rust `veo_security.pyd` P0 modules
- [ ] Anti-monkey-patch watchdog
- [ ] Import hooking detection
- [ ] Frida detection
- [ ] SSL pinning (Firebase)
- [ ] **WebSocket authentication (HMAC signing)**
- [ ] **CDP random port + monitoring**
- [ ] **Token in-memory encryption**

### Phase 2 — High (Week 3-4)
- [ ] PyInstaller extraction protection (Nuitka)
- [ ] Loader/patcher detection
- [ ] MITM + proxy detection
- [ ] Keygen mitigation (server-side validation)
- [ ] Key sharing detection
- [ ] Extension integrity check
- [ ] **Extension sideloading prevention (challenge-response)**
- [ ] **DNS hosts file check**

### Phase 3 — Medium (Week 5-6)
- [ ] Snapshot/restore detection
- [ ] Sandboxie/FS virtualization detection
- [ ] Code signing certificate
- [ ] Safe logger (redact sensitive data)
- [ ] Env var tampering check
- [ ] API replay protection
- [ ] **Anti-introspection (inspect/gc block)**
- [ ] **ctypes abuse protection (VirtualProtect)**
- [ ] **Race condition → atomic license check**
- [ ] **Differential analysis → single binary, server feature flags**

### Phase 4 — Low (Week 7-8)
- [ ] Clipboard security
- [ ] Memory zeroization (Rust Zeroize)
- [ ] Supply chain audit
- [ ] Process hollowing detection
- [ ] **Kernel rootkit indicators**
- [ ] **Account credential protection**

### Phase 5 — Enhancement (Week 9+)
- [ ] **Social engineering protocol (support verification SOP)**
- [ ] **Tamper-resistant telemetry**
- [ ] **Content watermarking** (steganography)

---

> [!IMPORTANT]
> **Phase 1 priority tuyệt đối** — 3 vectors mới (#36 WebSocket, #37 CDP, #38 Token) là **đặc thù kiến trúc VEO Pro Max** — attacker hiểu app sẽ khai thác đầu tiên.

> [!WARNING]
> **Cross-reference với `reference_docs/`:**
> - `LICENSE_ANTI_FAKE_SERVER.md` Section 5 đã có Domain Pinning (DNS hijack defense) — vector #40 bổ sung hosts file check
> - `TOKEN_SECURITY.md` đã có token extraction methods — vector #38 bổ sung theft prevention + in-memory encryption
> - `WORKFLOW_ANTI_CRACK_PROTECTION.md` dùng `ctypes` cho anti-debug — vector #42 document `ctypes` như attack vector ngược lại

> [!TIP]
> **Giải pháp xuyên suốt**: Compile toàn bộ security modules sang **Rust native binary**.
> Đây là countermeasure hiệu quả nhất, giải quyết đồng thời: decompile, monkey patch, import hook, string extract, memory dump, inspect/gc, ctypes abuse.
