# 🛡️ Security Knowledge Base — Toàn Bộ Attack Vectors & Countermeasures

> **Mục đích**: Encyclopedia tất cả kỹ thuật hacking/cracking/patching có thể xảy ra  
> **Scope**: Python desktop app + Chrome Extension + Firebase backend  
> **Total vectors**: 200+

---

## Mục Lục

| # | Category | Vectors | Severity Focus |
|---|----------|---------|----------------|
| I | [Binary / Static Attacks](#i-binary--static-attacks) | 12 | 🔴 Critical |
| II | [Runtime / Dynamic Attacks](#ii-runtime--dynamic-attacks) | 10 | 🔴 Critical |
| III | [Python-Specific Attacks](#iii-python-specific-attacks) | 15 | 🔴 Critical |
| IV | [Windows-Specific Attacks](#iv-windows-specific-attacks) | 14 | 🟠 High |
| V | [Network / Protocol Attacks](#v-network--protocol-attacks) | 12 | 🔴 Critical |
| VI | [License-Specific Attacks](#vi-license-specific-attacks) | 8 | 🟠 High |
| VII | [Browser / Extension Attacks](#vii-browser--extension-attacks) | 14 | 🔴 Critical |
| VIII | [Environment Manipulation](#viii-environment-manipulation) | 10 | 🟡 Medium |
| IX | [Build / Supply Chain](#ix-build--supply-chain-attacks) | 6 | 🟠 High |
| X | [Data Leak / Information Disclosure](#x-data-leak--information-disclosure) | 8 | 🟠 High |
| XI | [Side-Channel Attacks](#xi-side-channel-attacks) | 5 | 🟡 Medium |
| XII | [Social Engineering](#xii-social-engineering) | 6 | 🟠 High |
| XIII | [Physical / Hardware](#xiii-physical--hardware-attacks) | 4 | 🟡 Medium |
| XIV | [Advanced Persistence](#xiv-advanced-persistence) | 5 | 🟠 High |
| XV | [Reverse Engineering Techniques](#xv-reverse-engineering-techniques) | 8 | 🔴 Critical |
| **XVI** | [**OAuth / Google Session Attacks**](#xvi-oauth--google-session-attacks) | **8** | 🔴 **Critical** |
| **XVII** | [**Cryptographic Attacks**](#xvii-cryptographic-attacks) | **8** | 🟠 **High** |
| **XVIII** | [**Firebase / Cloud-Specific Attacks**](#xviii-firebase--cloud-specific-attacks) | **7** | 🔴 **Critical** |
| **XIX** | [**Race Condition / Concurrency Attacks**](#xix-race-condition--concurrency-attacks) | **6** | 🟠 **High** |
| **XX** | [**GUI / UI Attacks**](#xx-gui--ui-attacks) | **6** | 🟡 **Medium** |
| **XXI** | [**File Format / Input Attacks**](#xxi-file-format--input-attacks) | **6** | 🟠 **High** |
| **XXII** | [**AI / Automation-Specific Attacks**](#xxii-ai--automation-specific-attacks) | **8** | 🔴 **Critical** |
| **XXIII** | [**Anti-Forensics / Evasion**](#xxiii-anti-forensics--evasion) | **6** | 🟡 **Medium** |
| **XXIV** | [**DoS / Availability Attacks**](#xxiv-dos--availability-attacks) | **7** | 🟠 **High** |
| **XXV** | [**Backup / Recovery Exploitation**](#xxv-backup--recovery-exploitation) | **5** | 🟡 **Medium** |
| **XXVI** | [**Multi-Account Isolation**](#xxvi-multi-account-isolation-attacks) | **5** | 🔴 **Critical** |
| **XXVII** | [**Obfuscation Bypass**](#xxvii-obfuscation-bypass) | **6** | 🔴 **Critical** |
| **XXVIII** | [**WebDriver / Browser Fingerprint**](#xxviii-webdriver--browser-fingerprint) | **6** | 🔴 **Critical** |

---

## I. Binary / Static Attacks

### 1. Binary Patching (Hex Edit)
- **Attack**: Sửa bytes trong `.exe`/`.pyc` → `JNZ` thành `JZ` → bypass license check
- **Tools**: x64dbg, HxD, 010 Editor, Ghidra
- **Difficulty**: Trung bình
- **Countermeasure**: SHA-256 self-integrity check, code section hash verification, `.text` section CRC at runtime

### 2. String Extraction
- **Attack**: `strings binary.exe` → extract URLs, API keys, error messages → hiểu logic
- **Tools**: `strings`, FLOSS (FireEye), BinText
- **Difficulty**: Dễ
- **Countermeasure**: Compile-time string encryption (Rust `obfstr`), XOR encoding, stack strings

### 3. PyInstaller / cx_Freeze Extraction
- **Attack**: Extract `.pyc` from bundled exe → decompile → full source code
- **Tools**: `pyinstxtractor`, `pyi-archive_viewer`, `uncompyle6`, `decompyle3`, `pycdc`
- **Difficulty**: **Rất dễ** — YouTube tutorials sẵn
- **Countermeasure**:
  - Nuitka compile (Python→C→binary)
  - PyInstaller `--key` flag (AES encrypt PYZ)
  - Rust `.pyd` cho critical modules
  - Anti-extraction runtime check (detect `sys._MEIPASS` tampering)

### 4. Loader / Patcher
- **Attack**: `CreateProcess(SUSPENDED)` → `WriteProcessMemory` patch → `ResumeThread`
- **Tools**: Custom C/C++ loader, x64dbg scripts
- **Difficulty**: Trung bình
- **Countermeasure**: Check parent process, thread timing anomaly, `CREATE_SUSPENDED` detection

### 5. Process Hollowing
- **Attack**: Create legit process → unmapViewOfSection → write cracked image → resume
- **Tools**: Cobalt Strike, custom tools
- **Difficulty**: Cao
- **Countermeasure**: PEB ImageBaseAddress vs loaded module comparison, section checksum verify

### 6. PE Header Manipulation
- **Attack**: Modify PE headers → change entry point, disable ASLR/DEP
- **Tools**: CFF Explorer, PE-bear, LordPE
- **Difficulty**: Trung bình
- **Countermeasure**: PE header checksum verification, ASLR/DEP forced via linker flags

### 7. Resource Section Patching
- **Attack**: Modify embedded resources (icons, manifests, version info) → social engineering
- **Tools**: Resource Hacker, PE Explorer
- **Difficulty**: Dễ
- **Countermeasure**: Resource section hash in integrity check

### 8. Import Table (IAT) Modification
- **Attack**: Thay import address → redirect API calls to cracker's DLL
- **Tools**: CFF Explorer, custom tools
- **Difficulty**: Trung bình
- **Countermeasure**: IAT hash verification at runtime, direct syscalls for critical APIs

### 9. Code Cave Injection
- **Attack**: Find unused space in PE → inject code → redirect execution
- **Tools**: x64dbg, CFF Explorer
- **Difficulty**: Trung bình-Cao
- **Countermeasure**: Code section size verification, page permission monitoring

### 10. Relocation Table Abuse
- **Attack**: Sửa relocation entries → code chạy sai address → bypass checks
- **Tools**: PE tools
- **Difficulty**: Cao
- **Countermeasure**: Relocation table integrity check

### 11. Debug Directory Removal
- **Attack**: Xóa debug info từ PE → khó trace, nhưng app vẫn chạy
- **Tools**: PE editors
- **Difficulty**: Dễ
- **Countermeasure**: Not critical — chỉ ảnh hưởng debugging capability

### 12. Digital Signature Stripping
- **Attack**: Remove authenticode signature → patch binary → resign hoặc không sign
- **Tools**: `signtool`, `delcert`
- **Difficulty**: Dễ
- **Countermeasure**: Self-verify signature at runtime, timestamp checking

---

## II. Runtime / Dynamic Attacks

### 1. Debugger Attach
- **Attack**: Attach debugger → set breakpoint tại license check → modify return value
- **Tools**: x64dbg, WinDbg, OllyDbg, IDA Pro
- **Difficulty**: Trung bình
- **Countermeasure**:
  - `IsDebuggerPresent()` + `CheckRemoteDebuggerPresent()`
  - `NtQueryInformationProcess(ProcessDebugPort)`
  - DR0-DR7 hardware breakpoint detection
  - RDTSC timing check
  - Self-debugging (occupy debug slot)

### 2. DLL Injection
- **Attack**: Inject malicious DLL → hook critical functions
- **Tools**: Process Hacker, custom injector, `CreateRemoteThread`
- **Difficulty**: Trung bình
- **Countermeasure**: Loaded module whitelist, DLL signature verification, `SetDllDirectory("")`

### 3. API Hooking (Inline/IAT/EAT)
- **Attack**: Patch first bytes of WinAPI → JMP to hook function
- **Tools**: Detours, MinHook, EasyHook
- **Difficulty**: Trung bình
- **Countermeasure**: Verify function prologues (check for `0xE9 JMP`), syscall stubs, read kernel32 from disk

### 4. Thread Hijacking
- **Attack**: `SuspendThread` → modify context (`RIP/EIP`) → `ResumeThread`
- **Tools**: Custom tools
- **Difficulty**: Cao
- **Countermeasure**: Thread integrity monitoring, TLS callback verification

### 5. Memory Patching (Runtime)
- **Attack**: `WriteProcessMemory` → patch license check at runtime (giữ file clean)
- **Tools**: Cheat Engine, custom scripts
- **Difficulty**: Trung bình
- **Countermeasure**: Periodic code section hash verification, VirtualProtect monitoring

### 6. APC Injection
- **Attack**: Queue APC to target thread → execute malicious code in process context
- **Tools**: Custom C code
- **Difficulty**: Cao
- **Countermeasure**: APC queue monitoring, thread alertable wait detection

### 7. Exception Handler Hijacking
- **Attack**: Register custom SEH/VEH → intercept anti-debug exceptions → hide debugger
- **Tools**: x64dbg plugins
- **Difficulty**: Trung bình
- **Countermeasure**: SEH chain validation, VEH registration monitoring

### 8. Callback Overwrite
- **Attack**: Overwrite TLS callbacks, CRT init functions → code chạy trước `main()`
- **Tools**: PE tools
- **Difficulty**: Cao
- **Countermeasure**: TLS callback integrity check

### 9. Return-Oriented Programming (ROP)
- **Attack**: Chain existing code gadgets → execute arbitrary logic without injecting code
- **Tools**: ROPgadget, ropper
- **Difficulty**: Rất cao
- **Countermeasure**: CFI (Control Flow Integrity), shadow stack

### 10. Heap Spraying
- **Attack**: Fill heap with NOP sleds + shellcode → exploit use-after-free
- **Tools**: Custom scripts
- **Difficulty**: Cao
- **Countermeasure**: Heap isolation, ASLR, DEP/NX bit

---

## III. Python-Specific Attacks

> ⚠️ **ĐẶC BIỆT NGUY HIỂM** — Python là interpreted language, rất dễ manipulate

### 1. Monkey Patching
- **Attack**: `module.function = lambda: True` → bypass MỌI check
- **Difficulty**: **Cực dễ — 1 dòng code**
- **Countermeasure**: Function `id()` tracking, periodic verify, Rust native modules

### 2. `sys.modules` Injection
- **Attack**: `sys.modules['security'] = FakeModule()` → replace entire module
- **Difficulty**: Dễ
- **Countermeasure**: Module hash verification, `__file__` path check, Rust `.pyd` can't be faked

### 3. Import Hook (`sys.meta_path`)
- **Attack**: Custom importer intercepts ALL imports → redirect security modules
- **Difficulty**: Dễ
- **Countermeasure**: Freeze `sys.meta_path` at startup, detect additions

### 4. `.pth` File Injection
- **Attack**: Drop `.pth` file in `site-packages` → auto-execute arbitrary code at Python startup
- **Difficulty**: Dễ (cần write access)
- **Countermeasure**: Monitor `site-packages` for unexpected `.pth` files, `-S` flag

### 5. `sitecustomize.py` / `usercustomize.py`
- **Attack**: Create these files → Python auto-imports before app code
- **Difficulty**: Dễ
- **Countermeasure**: Verify non-existence at startup, use `-S` flag

### 6. `PYTHONPATH` / `PYTHONSTARTUP` Manipulation
- **Attack**: Set env var → Python loads attacker's modules first
- **Difficulty**: Dễ
- **Countermeasure**: `-E` flag (ignore env vars), or verify these vars at startup

### 7. `inspect` Module Abuse
- **Attack**: `inspect.getsource(func)` → read source; `inspect.getmembers()` → enumerate secrets
- **Difficulty**: Dễ
- **Countermeasure**: Block `inspect` import, Rust modules can't be inspected

### 8. `gc.get_objects()` — Garbage Collector Leak
- **Attack**: Enumerate ALL Python objects in memory → find license keys, tokens, passwords
- **Difficulty**: Dễ
- **Countermeasure**: `gc.disable()` for critical sections, Rust handles secrets (not in Python heap)

### 9. `ctypes` Direct Memory Access
- **Attack**: `ctypes.windll.kernel32.VirtualProtect()` → change memory protection → patch code
- **Difficulty**: Trung bình
- **Countermeasure**: Monitor ctypes usage, Rust modules immune to Python ctypes

### 10. `eval()` / `exec()` Injection
- **Attack**: Nếu app dùng eval/exec với user input → arbitrary code execution
- **Difficulty**: Dễ (nếu vulnerability exists)
- **Countermeasure**: **NEVER** use eval/exec with untrusted input

### 11. `pickle` Deserialization
- **Attack**: Craft malicious pickle → `__reduce__` executes arbitrary code khi load
- **Difficulty**: Trung bình
- **Countermeasure**: Không dùng `pickle` cho untrusted data, dùng `json` thay thế

### 12. Bytecode (`.pyc`) Patching
- **Attack**: Sửa `.pyc` bytecode trực tiếp — thay `LOAD_TRUE` thành `LOAD_FALSE`
- **Tools**: `dis`, `marshal`, custom tools
- **Difficulty**: Trung bình
- **Countermeasure**: `.pyc` hash verification, Nuitka compile

### 13. Code Object Manipulation
- **Attack**: `func.__code__ = modified_code_object` → change function behavior
- **Difficulty**: Trung bình
- **Countermeasure**: Code object hash tracking, `__code__` attribute monitoring

### 14. `sys.settrace()` — Transparent Debug
- **Attack**: Set trace function → intercept EVERY function call → log/modify silently
- **Difficulty**: Dễ
- **Countermeasure**: Detect `sys.gettrace() is not None`, Rust modules invisible to trace

### 15. `__del__` / Destructor Abuse
- **Attack**: Override `__del__` on security objects → prevent cleanup → extend trial
- **Difficulty**: Trung bình
- **Countermeasure**: Use context managers, explicit cleanup, Rust Drop trait

---

## IV. Windows-Specific Attacks

### 1. AppInit_DLLs Registry
- **Attack**: Set `HKLM\...\AppInit_DLLs` → DLL loaded into EVERY process
- **Difficulty**: Dễ (admin required)
- **Countermeasure**: Check registry key at startup, warn if set

### 2. Image File Execution Options (IFEO)
- **Attack**: `HKLM\...\IFEO\VEO.exe\Debugger = crack_loader.exe` → redirect execution
- **Difficulty**: Dễ (admin required)
- **Countermeasure**: Check IFEO registry for own exe name, self-path verification

### 3. DLL Search Order Hijacking
- **Attack**: Drop malicious DLL in app directory → loaded before system DLL
- **Tools**: Procmon (find missing DLLs)
- **Difficulty**: Dễ
- **Countermeasure**: `SetDllDirectory("")`, explicit DLL paths, SafeDllSearchMode

### 4. COM Hijacking
- **Attack**: Register fake COM object → app loads attacker's code via COM
- **Difficulty**: Trung bình
- **Countermeasure**: COM CLSID verification, avoid COM for security-critical functions

### 5. WMI Event Subscription
- **Attack**: WMI event→action → execute code when app starts/stops
- **Difficulty**: Trung bình
- **Countermeasure**: WMI subscription monitoring

### 6. Named Pipe Impersonation
- **Attack**: Create named pipe with expected name → intercept IPC
- **Difficulty**: Trung bình
- **Countermeasure**: Unique pipe names with process PID, ACLs on pipes

### 7. Token Impersonation / Privilege Escalation
- **Attack**: Steal process token → run as different user → access protected resources
- **Tools**: mimikatz, incognito
- **Difficulty**: Cao
- **Countermeasure**: Minimal privileges, token integrity level checks

### 8. ETW (Event Tracing) Monitoring
- **Attack**: Subscribe to ETW events → monitor ALL network calls, file I/O, registry
- **Tools**: PerfView, xperf, custom ETW consumer
- **Difficulty**: Trung bình
- **Countermeasure**: Detect ETW providers for own process, obfuscate event names

### 9. Windows Hooks (`SetWindowsHookEx`)
- **Attack**: Global keyboard/message hook → capture license keys, intercept UI
- **Tools**: Custom code
- **Difficulty**: Trung bình
- **Countermeasure**: Detect global hooks, use SecureDesktop for sensitive input

### 10. Job Object Restrictions
- **Attack**: Create Job Object → assign to app process → limit network/file access
- **Difficulty**: Trung bình
- **Countermeasure**: Detect Job Object assignment, verify unrestricted access

### 11. Minifilter Driver (File System)
- **Attack**: Kernel driver intercepts file I/O → show fake license file → app reads "valid"
- **Difficulty**: Rất cao
- **Countermeasure**: Multiple verification sources (file + registry + network), kernel integrity

### 12. Registry Virtualization
- **Attack**: Windows redirects registry writes → app thinks it wrote but didn't persist
- **Difficulty**: Dễ
- **Countermeasure**: Verify registry reads match writes, use multiple storage locations

### 13. Transactional NTFS (TxF)
- **Attack**: Bắt đầu FS transaction → modify files → rollback → file changes disappear
- **Difficulty**: Cao
- **Countermeasure**: Verify file state after write, use non-NTFS verification (network)

### 14. Windows Sandbox / App Container
- **Attack**: Run app in AppContainer → intercept tất cả I/O
- **Difficulty**: Trung bình
- **Countermeasure**: Detect AppContainer token, check integrity level

---

## V. Network / Protocol Attacks

### 1. Man-in-the-Middle (MITM)
- **Attack**: Proxy HTTPS → intercept/modify Firebase responses
- **Tools**: mitmproxy, Fiddler, Charles, Burp Suite
- **Difficulty**: Dễ
- **Countermeasure**: Certificate pinning, response signature verification

### 2. SSL/TLS Stripping
- **Attack**: Downgrade HTTPS to HTTP → read plaintext
- **Tools**: sslstrip, bettercap
- **Difficulty**: Trung bình
- **Countermeasure**: HSTS enforcement, refuse HTTP connections

### 3. Certificate Pinning Bypass
- **Attack**: Hook SSL verify function → accept any cert → enable MITM
- **Tools**: Frida SSL scripts, Objection
- **Difficulty**: Trung bình
- **Countermeasure**: Pin verification in Rust native code (unreachable by Frida Python hooks)

### 4. API Replay Attack
- **Attack**: Capture valid license response → replay indefinitely
- **Difficulty**: Trung bình
- **Countermeasure**: Nonce per request, timestamp validation (<30s), sequence numbers

### 5. Server Emulation (Fake Firebase)
- **Attack**: Redirect DNS → local fake server → always return "valid"
- **Difficulty**: Trung bình
- **Countermeasure**: Server certificate verify, response HMAC, Google IP range check

### 6. DNS Spoofing / Hosts File
- **Attack**: Edit `C:\Windows\System32\drivers\etc\hosts` → redirect Firebase → local server
- **Difficulty**: Dễ (admin)
- **Countermeasure**: Check hosts file for Firebase domains, use IP-based verification

### 7. DNS Rebinding
- **Attack**: Attacker's DNS alternates between real IP and 127.0.0.1 → bypass same-origin
- **Difficulty**: Cao
- **Countermeasure**: Verify resolved IP is in expected range, refuse private IPs

### 8. WebSocket Frame Injection
- **Attack**: Nếu WebSocket không authenticated → inject commands → control extension
- **Difficulty**: Trung bình (nếu `0.0.0.0` binding hoặc no auth)
- **Countermeasure**: HMAC signed messages, session tokens, `127.0.0.1` binding only

### 9. WebSocket Hijacking (Cross-Site)
- **Attack**: Malicious webpage connects to local WS server → send commands
- **Difficulty**: Trung bình
- **Countermeasure**: Origin validation, unique per-session tokens, auth handshake

### 10. gRPC / API Reflection
- **Attack**: If gRPC used → reflection API reveals all methods and message types
- **Difficulty**: Dễ
- **Countermeasure**: Disable reflection in production, TLS mutual auth

### 11. Certificate Transparency Monitoring
- **Attack**: Monitor CT logs → discover Firebase project subdomains → target attack
- **Difficulty**: Dễ
- **Countermeasure**: Not preventable — assume Firebase project ID is public

### 12. HTTP Request Smuggling
- **Attack**: Malformed HTTP headers → bypass WAF/proxy → direct server access
- **Difficulty**: Cao
- **Countermeasure**: Strict HTTP parsing, modern frameworks handle this

---

## VI. License-Specific Attacks

### 1. Keygen (Key Generator)
- **Attack**: Reverse-engineer key algorithm → generate unlimited valid keys
- **Difficulty**: Cao (with HMAC-SHA256)
- **Countermeasure**: Server-side validation, HMAC secret in env var, per-build secrets

### 2. Key Sharing (Same Key, Multiple Machines)
- **Attack**: Share key file → bypass HWID check bằng HWID spoofer
- **Difficulty**: Dễ
- **Countermeasure**: HWID binding (Firebase), max device count, concurrent use detection

### 3. License File Copying
- **Attack**: Copy cache file `license_cache.json` to another machine
- **Difficulty**: Dễ
- **Countermeasure**: HMAC signature includes HWID, machine-bound AES key (PBKDF2)

### 4. Grace Period Exploitation
- **Attack**: Disconnect network → app runs in grace period indefinitely
- **Difficulty**: Dễ
- **Countermeasure**: Short grace period (3 days), monotonic clock tracking, resume requires online

### 5. Trial Reset
- **Attack**: Delete trial markers → reinstall → unlimited trial
- **Difficulty**: Dễ
- **Countermeasure**: 5+ marker locations (file, registry, Firebase), cross-validate all

### 6. Clock Rollback
- **Attack**: Set system date back → trial never expires
- **Difficulty**: Dễ
- **Countermeasure**: NTP verification, Firebase server time, monotonic clock, HTTP header time

### 7. HWID Spoofing
- **Attack**: Fake hardware identifiers → bypass machine binding
- **Tools**: HWID Changer, custom WMI hooks
- **Difficulty**: Trung bình
- **Countermeasure**: Multi-source HWID (CPUID + disk serial + MAC + MachineGuid + BIOS UUID), direct hardware queries via Rust

### 8. License Downgrade/Upgrade Manipulation
- **Attack**: Modify cached tier from TRIAL→PREMIUM in memory or file
- **Difficulty**: Trung bình
- **Countermeasure**: Server-authoritative tier, HMAC-signed cache, periodic server revalidation

---

## VII. Browser / Extension Attacks

> ⚠️ **ĐẶC THÙ VEO** — Chrome extension + CDP là attack surface lớn nhất

### 1. Extension Source Code Theft
- **Attack**: Copy extension folder → đọc `background.js`, `content.js` → hiểu toàn bộ logic
- **Difficulty**: **Cực dễ** — extension files là plaintext
- **Countermeasure**: Obfuscate JS (webpack + terser), code splitting, don't embed secrets

### 2. Extension Tamper / Modified Extension
- **Attack**: Sửa `background.js` → luôn return `{success: true}` → bypass reCAPTCHA
- **Difficulty**: Dễ
- **Countermeasure**: Extension integrity hash check (mỗi khi connect WS), content hash in manifest

### 3. Rogue Extension Sideloading
- **Attack**: Load extension giả với cùng logic → kết nối WS → nhận commands
- **Difficulty**: Trung bình
- **Countermeasure**: Challenge-response auth khi WS handshake, extension ID verification

### 4. Chrome DevTools Protocol (CDP) Abuse
- **Attack**: Connect CDP port → `Runtime.evaluate` → chạy bất kỳ code nào trên page
- **Tools**: Chrome DevTools, Playwright, Puppeteer, `curl`
- **Difficulty**: **Dễ** nếu biết port
- **Countermeasure**: Random CDP port, monitor CDP connections, `--remote-debugging-address=127.0.0.1`

### 5. CDP Page.navigate Abuse
- **Attack**: Navigate tab tới attacker's page → steal cookies, tokens
- **Difficulty**: Dễ (nếu CDP exposed)
- **Countermeasure**: Domain whitelist for navigation, monitor tab URLs

### 6. WebSocket Hijacking
- **Attack**: Connect to extension WS server → send commands → steal tokens
- **Difficulty**: Trung bình
- **Countermeasure**: HMAC message signing, per-session nonce, origin checking

### 7. OAuth Token Theft
- **Attack**: Extract access_token from Chrome cookies/storage → use directly
- **Tools**: CDP `Network.getCookies`, `Storage.getItems`
- **Difficulty**: Trung bình
- **Countermeasure**: Token encryption in memory, short-lived tokens, token binding

### 8. reCAPTCHA Token Bypass
- **Attack**: Generate fake reCAPTCHA tokens → submit directly to API
- **Difficulty**: Rất cao (Google's security)
- **Countermeasure**: reCAPTCHA Enterprise score validation server-side

### 9. Service Worker Manipulation
- **Attack**: Register malicious service worker → intercept ALL network requests
- **Difficulty**: Trung bình
- **Countermeasure**: Monitor SW registrations, CSP headers

### 10. Content Security Policy Bypass
- **Attack**: If CSP is weak → inject scripts → steal data
- **Difficulty**: Depends on CSP strength
- **Countermeasure**: Strict CSP, no `unsafe-inline`, nonce-based scripts

### 11. Cross-Extension Messaging
- **Attack**: Malicious extension sends messages to VEO extension → trigger actions
- **Difficulty**: Dễ (if externally_connectable is permissive)
- **Countermeasure**: Restrict `externally_connectable` in manifest, validate sender

### 12. Chrome Profile Cloning
- **Attack**: Copy entire Chrome profile → paste on other machine → steal cookies/tokens
- **Difficulty**: Dễ
- **Countermeasure**: Token binding to HWID, session invalidation on device change

### 13. Background Page Debugging
- **Attack**: `chrome://extensions` → Inspect background page → DevTools → breakpoints
- **Difficulty**: Dễ
- **Countermeasure**: Obfuscate JS, don't store secrets in JS variables, minimal logging

### 14. Manifest V3 Limitations Exploitation
- **Attack**: MV3 service workers have limited lifetime → exploit restart gaps
- **Difficulty**: Trung bình
- **Countermeasure**: Robust reconnection logic, state persistence via `chrome.storage`

---

## VIII. Environment Manipulation

### 1. VM Snapshot & Restore
- **Attack**: Create VM snapshot → activate trial → restore snapshot → repeat
- **Difficulty**: Dễ
- **Countermeasure**: VM detection, Firebase-side trial tracking, timestamp anomaly detection

### 2. Sandboxie / FS Virtualization
- **Attack**: Run in Sandboxie → all file writes go to sandbox → always shows trial
- **Tools**: Sandboxie, Turbo Studio
- **Difficulty**: Dễ
- **Countermeasure**: Detect SbieDll.dll, check `GetModuleHandle("SbieDll.dll")`

### 3. Registry Virtualization
- **Attack**: Virtualize registry → app writes to real reg but reads from virtual
- **Difficulty**: Trung bình
- **Countermeasure**: Double-write verification, network-based state

### 4. Symlink/Junction Attack
- **Attack**: Create symlink from license file → `/dev/null` or fake file
- **Difficulty**: Dễ
- **Countermeasure**: Resolve symlinks before reading, verify file attributes

### 5. Environment Variable Override
- **Attack**: Set `VEO_LICENSE_SECRET=known_value` → forge licenses
- **Difficulty**: Dễ
- **Countermeasure**: `-E` Python flag, verify env var integrity, derive from hardware

### 6. Docker / WSL / Wine
- **Attack**: Run in Linux environment → bypass Windows-specific security checks
- **Difficulty**: Trung bình
- **Countermeasure**: Detect Wine, WSL (`/proc/version`), Docker (`/.dockerenv`)

### 7. Time Zone Manipulation
- **Attack**: Change TZ → confuse license expiry calculation
- **Difficulty**: Dễ
- **Countermeasure**: Always use UTC internally, NTP verification

### 8. Locale / Code Page Attack
- **Attack**: Change system locale → break string parsing → bypass validation
- **Difficulty**: Trung bình
- **Countermeasure**: Explicitly set encoding, use `utf-8` everywhere

### 9. Disk Encryption Rollback
- **Attack**: BitLocker/VeraCrypt snapshot → rollback all file changes
- **Difficulty**: Trung bình
- **Countermeasure**: Server-side state as source of truth

### 10. System Restore Point
- **Attack**: Windows System Restore → rollback trial markers, registry
- **Difficulty**: Dễ
- **Countermeasure**: Firebase-based markers survive system restore

---

## IX. Build / Supply Chain Attacks

### 1. Dependency Poisoning
- **Attack**: Publish malicious version of popular pip package → typosquatting
- **Difficulty**: Trung bình
- **Countermeasure**: Pin exact versions in `requirements.txt`, hash verification, private PyPI

### 2. Build Pipeline Compromise
- **Attack**: Modify CI/CD → inject backdoor during build
- **Difficulty**: Cao
- **Countermeasure**: Signed commits, build reproducibility, artifact hash verification

### 3. Code Signing Bypass
- **Attack**: Strip authenticode → patch → không resign (hoặc self-sign)
- **Difficulty**: Dễ
- **Countermeasure**: Self-verify signature at runtime, refuse unsigned

### 4. Update Channel Hijacking
- **Attack**: MITM update server → deliver cracked version as "update"
- **Difficulty**: Trung bình
- **Countermeasure**: Code-signed updates, hash verification, pinned update server cert

### 5. Malicious PR / Insider Threat
- **Attack**: Contributor submits code with subtle backdoor
- **Difficulty**: Trung bình
- **Countermeasure**: Code review, automated security scanning, least privilege

### 6. Open Source Intelligence (OSINT)
- **Attack**: Analyze public repos, docs, issues → understand architecture → targeted attack
- **Difficulty**: Dễ
- **Countermeasure**: Separate public/private docs, no internal paths in public repos

---

## X. Data Leak / Information Disclosure

### 1. Log File Leaking
- **Attack**: Read log files → extract tokens, API keys, internal state
- **Difficulty**: Dễ
- **Countermeasure**: Redact sensitive data in logs, auto-rotate, restrictive file permissions

### 2. Clipboard Sniffing
- **Attack**: Monitor clipboard → capture license keys khi user copy-paste
- **Tools**: Clipboard history tools, keyloggers
- **Difficulty**: Dễ
- **Countermeasure**: Auto-clear clipboard after paste, don't log clipboard content

### 3. Memory Forensics
- **Attack**: Memory dump → search for tokens, keys, passwords in plaintext
- **Tools**: `procdump`, Volatility, WinDbg `!heap`
- **Difficulty**: Trung bình
- **Countermeasure**: Zeroize secrets after use (Rust `Zeroize` trait), encrypted memory, `VirtualLock()`

### 4. Crash Dump Analysis
- **Attack**: Post-crash minidump chứa toàn bộ memory → extract secrets
- **Difficulty**: Trung bình
- **Countermeasure**: Disable minidumps for production, clear secrets before crash handler

### 5. Screen Capture / Recording
- **Attack**: Capture license key từ UI khi displayed
- **Difficulty**: Dễ
- **Countermeasure**: Mask sensitive fields, DRM flag on window (`SetWindowDisplayAffinity`)

### 6. Network Traffic Analysis
- **Attack**: Even with HTTPS → traffic patterns (timing, size) reveal behavior
- **Difficulty**: Trung bình
- **Countermeasure**: Padding, decoy traffic, consistent request timing

### 7. Error Message Intelligence
- **Attack**: Error messages/stack traces tiết lộ internal structure, file paths
- **Difficulty**: Dễ
- **Countermeasure**: Generic error messages for users, detailed only in logs

### 8. Temporary File Exposure
- **Attack**: `%TEMP%` files chứa intermediate data → tokens, configs
- **Difficulty**: Dễ
- **Countermeasure**: Encrypt temp files, delete after use, use `tempfile.mkstemp()` with permissions

---

## XI. Side-Channel Attacks

### 1. Timing Attack
- **Attack**: Measure license validation time → shorter = invalid, longer = valid
- **Difficulty**: Trung bình
- **Countermeasure**: Constant-time comparison (`hmac.compare_digest`), add random delay

### 2. Power Analysis
- **Attack**: Measure power consumption → correlate with crypto operations
- **Difficulty**: Rất cao (cần hardware)
- **Countermeasure**: Constant-time crypto implementations (Rust)

### 3. Cache Timing Attack
- **Attack**: Measure CPU cache hit/miss → infer memory access patterns
- **Difficulty**: Rất cao
- **Countermeasure**: Cache-oblivious algorithms, Rust constant-time operations

### 4. Network Timing
- **Attack**: Measure Firebase response time → determine if key exists (faster) vs not (slower)
- **Difficulty**: Trung bình
- **Countermeasure**: Add random delay to all responses, consistent response time

### 5. UI Timing
- **Attack**: Observe UI response time → determine license check result before displayed
- **Difficulty**: Dễ
- **Countermeasure**: Fixed delay before showing result, always show loading spinner

---

## XII. Social Engineering

### 1. Phishing for License Keys
- **Attack**: Fake support page → "enter your key for upgrade" → steal valid keys
- **Difficulty**: Dễ
- **Countermeasure**: Educate users, official verification channel, key revocation

### 2. Fake Support Channel
- **Attack**: Impersonate support → "give me your key for debugging" → steal
- **Difficulty**: Dễ
- **Countermeasure**: Official support verification SOP, never ask for full key

### 3. Credential Harvesting
- **Attack**: Fake login page → steal Google account credentials → access VEO
- **Difficulty**: Trung bình
- **Countermeasure**: 2FA enforcement, OAuth only (never handle passwords)

### 4. Insider Threat
- **Attack**: Disgruntled employee/admin leaks keys or secret
- **Difficulty**: N/A
- **Countermeasure**: Least privilege, audit logs, key rotation capability

### 5. Social Engineering Admin
- **Attack**: Pretend to be customer → "I lost my key, machine changed" → get free key
- **Difficulty**: Dễ
- **Countermeasure**: Verification SOP (payment proof, HWID verification)

### 6. Warez / Crack Distribution
- **Attack**: Distribute cracked version → users run malware disguised as crack
- **Difficulty**: Dễ (for attacker)
- **Countermeasure**: Version fingerprinting, telemetry for unusual patterns

---

## XIII. Physical / Hardware Attacks

### 1. Cold Boot Attack
- **Attack**: Freeze RAM → reboot → dump memory → extract encryption keys
- **Difficulty**: Rất cao
- **Countermeasure**: Memory encryption, quick key zeroization

### 2. JTAG / Hardware Debug
- **Attack**: Hardware debugger attached to motherboard → bypass software protections
- **Difficulty**: Rất cao
- **Countermeasure**: Not practically defensible for software

### 3. USB Keylogger
- **Attack**: Hardware keylogger captures license key input
- **Difficulty**: Dễ (cần physical access)
- **Countermeasure**: Clipboard-based key entry, virtual keyboard option

### 4. Evil Maid Attack
- **Attack**: Physical access → install rootkit → monitor app
- **Difficulty**: Trung bình (cần physical access)
- **Countermeasure**: BitLocker, Secure Boot, TPM

---

## XIV. Advanced Persistence

### 1. Registry Run Keys
- **Attack**: `HKCU\...\Run` → load crack loader at every startup
- **Difficulty**: Dễ
- **Countermeasure**: Check for unexpected run entries, clean environment verification

### 2. Scheduled Task
- **Attack**: Task Scheduler → patch files before app starts
- **Difficulty**: Dễ
- **Countermeasure**: Verify file integrity at startup (AFTER scheduled tasks run)

### 3. WMI Persistence
- **Attack**: WMI event subscription → execute on app start → patch runtime
- **Difficulty**: Trung bình
- **Countermeasure**: WMI subscription audit

### 4. DLL Proxying (Persistent)
- **Attack**: Replace system DLL with proxy → forwards calls + injects code
- **Difficulty**: Trung bình
- **Countermeasure**: DLL hash verification, SFC integration

### 5. Boot-Level Persistence
- **Attack**: Bootkit/UEFI rootkit → runs before OS → can bypass EVERYTHING
- **Difficulty**: Rất cao
- **Countermeasure**: Secure Boot, UEFI measured boot, TPM attestation

---

## XV. Reverse Engineering Techniques

### 1. Static Analysis (IDA Pro / Ghidra)
- **Attack**: Disassemble binary → understand all code paths → find vulnerable spots
- **Tools**: IDA Pro, Ghidra, Binary Ninja, Cutter
- **Difficulty**: Cao
- **Countermeasure**: Control flow obfuscation, dead code insertion, opaque predicates

### 2. Dynamic Analysis (Tracing)
- **Attack**: Run under tracer → log ALL API calls → understand behavior
- **Tools**: API Monitor, Procmon, x64dbg trace
- **Difficulty**: Trung bình
- **Countermeasure**: Anti-debug, timing checks, detect tracing tools

### 3. Symbolic Execution
- **Attack**: Solve constraints → find inputs that bypass checks
- **Tools**: angr, Manticore, KLEE
- **Difficulty**: Cao
- **Countermeasure**: Complex path conditions, hash-based validation (hard to solve)

### 4. Differential Analysis
- **Attack**: Compare TRIAL vs PREMIUM binary → find exact bytes that differ
- **Tools**: BinDiff, Diaphora, `diff`
- **Difficulty**: Trung bình
- **Countermeasure**: Single binary for all tiers, server-controlled features

### 5. Protocol Analysis
- **Attack**: Analyze Firebase API traffic → understand request/response format → emulate
- **Tools**: Wireshark, Fiddler, mitmproxy
- **Difficulty**: Trung bình
- **Countermeasure**: Encrypted payloads beyond HTTPS, signed requests

### 6. Emulation
- **Attack**: Emulate binary in sandbox → analyze without risk
- **Tools**: QEMU, Unicorn, Qiling
- **Difficulty**: Cao
- **Countermeasure**: Anti-emulation checks (CPUID, timing, hardware features)

### 7. Fuzzing
- **Attack**: Feed random inputs → find crashes → exploit vulnerabilities
- **Tools**: AFL, libFuzzer, Boofuzz
- **Difficulty**: Trung bình
- **Countermeasure**: Input validation, safe parsing, memory-safe languages (Rust)

### 8. Firmware / Driver Analysis
- **Attack**: Nếu app dùng kernel driver → reverse driver → bypass kernel-level protection
- **Tools**: IDA Pro, WinDbg kernel mode
- **Difficulty**: Rất cao
- **Countermeasure**: Driver code signing (EV cert), kernel code integrity

---

---

## XVI. OAuth / Google Session Attacks

> ⚠️ **ĐẶC THÙ VEO** — App dùng Google OAuth tokens để gọi VEO API

### 1. OAuth Token Interception
- **Attack**: Intercept OAuth authorization code during redirect → exchange for access token
- **Tools**: Burp Suite, proxy tools
- **Difficulty**: Trung bình
- **Countermeasure**: PKCE (Proof Key for Code Exchange), state parameter validation

### 2. Refresh Token Theft
- **Attack**: Steal refresh token từ file/memory → generate unlimited access tokens
- **Tools**: File browser, memory dump, CDP
- **Difficulty**: Trung bình
- **Countermeasure**: Encrypt refresh tokens at rest (machine-bound key), token rotation

### 3. Google Cookie Hijacking (SID/HSID/SSID)
- **Attack**: Extract Google authentication cookies → hijack entire Google session
- **Tools**: CDP `Network.getCookies`, Chrome profile copy, cookie editors
- **Difficulty**: Dễ (nếu có access vào Chrome profile)
- **Countermeasure**: Encrypt Chrome profile directory, HWID-bound session tokens, detect multiple active sessions

### 4. OAuth Consent Screen Phishing
- **Attack**: Fake OAuth consent screen → user grants permission to attacker's app
- **Difficulty**: Trung bình
- **Countermeasure**: Verify OAuth client_id matches expected, educate users about official consent

### 5. Token Scope Escalation
- **Attack**: Request broader OAuth scopes than needed → access more Google services
- **Difficulty**: Trung bình
- **Countermeasure**: Minimum required scopes only, server validates scope on each request

### 6. Session Fixation
- **Attack**: Pre-set session ID → trick user into authenticating → attacker hijacks session
- **Difficulty**: Trung bình
- **Countermeasure**: Regenerate session after auth, validate session origin

### 7. Cross-Account Token Reuse
- **Attack**: Use access token from Account A to generate video on Account B
- **Difficulty**: Dễ (nếu tokens không bound)
- **Countermeasure**: Token-account binding, validate account in every API call

### 8. `x-client-data` / `x-browser-validation` Header Forgery
- **Attack**: Forge Chrome-specific headers → bypass bot detection
- **Tools**: Header sniffing + replay
- **Difficulty**: Trung bình
- **Countermeasure**: Header freshness validation, per-session x-client-data, detect inconsistent Chrome version vs header

---

## XVII. Cryptographic Attacks

### 1. Brute Force on Short Keys
- **Attack**: Nếu key space nhỏ → enumerate tất cả combinations
- **Difficulty**: Depends on key length
- **Countermeasure**: Minimum 128-bit keys, rate limiting, account lockout after N failures

### 2. Padding Oracle Attack
- **Attack**: Manipulate ciphertext → observe error responses → decrypt byte-by-byte
- **Difficulty**: Cao
- **Countermeasure**: Use authenticated encryption (AES-GCM), constant-time error handling

### 3. Length Extension Attack
- **Attack**: If using `SHA256(secret || message)` → extend message without knowing secret
- **Difficulty**: Trung bình (nếu vulnerable construction)
- **Countermeasure**: Use HMAC (not raw hash), HMAC-SHA256 immune to length extension

### 4. Birthday Attack on Hash
- **Attack**: Find two inputs with same hash → forge valid license with different data
- **Difficulty**: Cao (SHA-256 = 2^128 collision resistance)
- **Countermeasure**: SHA-256/512 có đủ collision resistance

### 5. Known Plaintext Attack
- **Attack**: Know plaintext (e.g., format of license response) → derive key information
- **Difficulty**: Cao
- **Countermeasure**: Random IV/nonce per encryption, AES-GCM với unique nonces

### 6. Key Derivation Weakness
- **Attack**: Nếu PBKDF2 iterations thấp → brute force password → derive AES key
- **Difficulty**: Trung bình
- **Countermeasure**: PBKDF2 ≥ 600,000 iterations (OWASP 2025), or Argon2id

### 7. Nonce/IV Reuse
- **Attack**: Reuse nonce in AES-GCM → XOR two ciphertexts → recover plaintext
- **Difficulty**: Trung bình (nếu nonce deterministic)
- **Countermeasure**: Random nonce per encryption, nonce counter (never reuse)

### 8. Weak Random Number Generator
- **Attack**: Predict `random.random()` → predict license keys, session tokens
- **Difficulty**: Trung bình
- **Countermeasure**: Use `secrets` module (CSPRNG), never `random` for security

---

## XVIII. Firebase / Cloud-Specific Attacks

### 1. Firestore Rules Bypass
- **Attack**: Craft request that bypasses security rules → read/write unauthorized data
- **Tools**: Firebase REST API, Postman
- **Difficulty**: Trung bình
- **Countermeasure**: Comprehensive Firestore rules testing, Firebase Emulator Suite

### 2. Firebase Project ID Enumeration
- **Attack**: Discover Firebase project ID → access public data, attempt unauthorized access
- **Difficulty**: Dễ (project ID often in config)
- **Countermeasure**: Assume project ID is public, rely on Firestore rules + App Check

### 3. Firebase App Check Bypass
- **Attack**: Generate fake app attestation → bypass App Check protection
- **Difficulty**: Cao
- **Countermeasure**: Enforce App Check on all Cloud Functions, use Play Integrity / reCAPTCHA Enterprise

### 4. Cloud Functions Direct Invocation
- **Attack**: Call Cloud Functions directly (bypass client app) → abuse API
- **Tools**: `curl`, Postman
- **Difficulty**: Dễ (nếu endpoint known)
- **Countermeasure**: Validate App Check token + user auth token in every Cloud Function

### 5. Firestore Data Exfiltration
- **Attack**: If rules too permissive → enumerate/download all license documents
- **Difficulty**: Dễ (nếu rules weak)
- **Countermeasure**: Strict collection-level rules, no list permission on `_lic`, validate key format

### 6. Firebase Admin SDK Key Leak
- **Attack**: Admin SDK service account JSON leaked → full database admin access
- **Difficulty**: Dễ (nếu key committed to git)
- **Countermeasure**: NEVER commit service account key, use env vars, IAM roles

### 7. Realtime Database / Firestore Injection
- **Attack**: Inject special characters in document paths → access unintended documents
- **Difficulty**: Trung bình
- **Countermeasure**: Sanitize all document IDs, validate format before query

---

## XIX. Race Condition / Concurrency Attacks

### 1. TOCTOU (Time of Check / Time of Use)
- **Attack**: License valid at check time → switch license file before use → pirated content
- **Difficulty**: Trung bình
- **Countermeasure**: Atomic check-and-use, re-validate at use time, lock file during check

### 2. License Double-Activation
- **Attack**: Send two activation requests simultaneously → activate on two machines
- **Difficulty**: Trung bình
- **Countermeasure**: Firebase transactions (atomic read-write), distributed locking

### 3. Credit Double-Spend
- **Attack**: Submit two video generation requests simultaneously → spend 1 credit for 2 videos
- **Difficulty**: Trung bình (timing critical)
- **Countermeasure**: Server-side credit deduction with transactions, idempotency keys

### 4. Thread Safety in Security Checks
- **Attack**: Trigger security check in one thread → patch while check runs in another
- **Difficulty**: Cao
- **Countermeasure**: Atomic security checks, immutable security state, mutex/lock

### 5. WebSocket Message Ordering
- **Attack**: Send out-of-order WS messages → confuse state machine → bypass auth
- **Difficulty**: Trung bình
- **Countermeasure**: Sequence numbers, state machine validation, reject out-of-order

### 6. Parallel Account Abuse
- **Attack**: Run multiple VEO instances with different accounts → multiply output
- **Difficulty**: Dễ
- **Countermeasure**: Named mutex (single instance), HWID-based rate limiting across accounts

---

## XX. GUI / UI Attacks

### 1. Clickjacking (UI Redressing)
- **Attack**: Embed app window/webview in invisible iframe → trick user into clicking
- **Difficulty**: Trung bình
- **Countermeasure**: X-Frame-Options: DENY, CSP frame-ancestors

### 2. Fake Dialog Injection
- **Attack**: Create fake system dialog → "License expired, enter key here" → phish
- **Tools**: Custom overlay window
- **Difficulty**: Dễ
- **Countermeasure**: Unique app-specific dialog design, anti-overlay detection

### 3. Window Message Injection
- **Attack**: `SendMessage(WM_SETTEXT)` → change text in license dialog → show "VALID"
- **Tools**: Spy++, AutoIt, custom code
- **Difficulty**: Dễ
- **Countermeasure**: Don't rely on UI state for security, server-authoritative

### 4. Accessibility API Abuse
- **Attack**: Use Windows Accessibility API → read/modify UI elements programmatically
- **Tools**: UI Automation, MSAA
- **Difficulty**: Trung bình
- **Countermeasure**: Disable accessibility for sensitive fields, or mark as not-automatable

### 5. Screenshot Prevention Bypass
- **Attack**: Use kernel-level screen capture → bypass `SetWindowDisplayAffinity`
- **Difficulty**: Cao
- **Countermeasure**: Multiple capture prevention layers, minimize sensitive data display time

### 6. DPI/Resolution Attack
- **Attack**: Extreme DPI settings → UI elements overlap → expose hidden fields
- **Difficulty**: Dễ
- **Countermeasure**: DPI-aware UI, responsive layouts, test at extreme DPI

---

## XXI. File Format / Input Attacks

### 1. Path Traversal
- **Attack**: `../../etc/passwd` hoặc `..\..\Windows\System32` → read/write arbitrary files
- **Difficulty**: Dễ
- **Countermeasure**: Canonicalize paths, whitelist allowed directories, `pathlib.resolve()`

### 2. Zip Slip
- **Attack**: Malicious zip with `../../path` entries → extract to arbitrary location
- **Difficulty**: Trung bình
- **Countermeasure**: Validate all zip entry paths before extraction

### 3. Config File Injection
- **Attack**: Sửa `config.json` → change API endpoints, disable security features
- **Difficulty**: Dễ
- **Countermeasure**: Config file integrity hash, signed configs, ignore unauthorized changes

### 4. Prompt Injection (via Task Files)
- **Attack**: Inject special characters in prompt text → exploit API parsing vulnerabilities
- **Difficulty**: Trung bình
- **Countermeasure**: Sanitize prompt text, length limits, character whitelist

### 5. Large File DoS
- **Attack**: Submit extremely large prompt file → exhaust memory/disk
- **Difficulty**: Dễ
- **Countermeasure**: File size limits, streaming parsing, memory limits

### 6. Unicode/Encoding Attack
- **Attack**: Use homoglyph characters (Cyrillic 'а' looks like Latin 'a') → bypass filters
- **Difficulty**: Trung bình
- **Countermeasure**: Normalize Unicode (NFC), ASCII-only for critical fields

---

## XXII. AI / Automation-Specific Attacks

> ⚠️ **ĐẶC THÙ VEO** — Video generation automation có attack surface riêng

### 1. reCAPTCHA Score Poisoning
- **Attack**: Deliberately lower reCAPTCHA score → trigger bot detection → blame tool → force fix that weakens security
- **Difficulty**: Trung bình
- **Countermeasure**: Score threshold monitoring, anomaly detection, multi-factor verification

### 2. API Rate Limit Circumvention
- **Attack**: Rotate accounts/IPs → bypass per-account rate limits → abuse quota
- **Difficulty**: Dễ
- **Countermeasure**: HWID-based global rate limiting, suspicious pattern detection

### 3. Google Account Credential Theft
- **Attack**: VEO uses real Google accounts → if compromised, attacker has full Google access
- **Difficulty**: Trung bình
- **Countermeasure**: Dedicated Google accounts (not personal), 2FA, monitor account activity

### 4. Video Output Theft / IP Piracy
- **Attack**: Steal generated videos → redistribute without credits
- **Difficulty**: Dễ (files on disk)
- **Countermeasure**: Invisible watermarking (steganography), metadata embedding

### 5. Prompt Replay Attack
- **Attack**: Capture successful prompt → replay to generate same video without credits
- **Difficulty**: Dễ
- **Countermeasure**: Unique generation ID per request, server-side dedup, credit tracking

### 6. Account Pool Exploitation
- **Attack**: Create mass Google accounts → use free tier → unlimited generation
- **Difficulty**: Trung bình
- **Countermeasure**: Phone verification, account age check, IP reputation

### 7. Extension Command Injection
- **Attack**: Inject commands via WebSocket → make extension perform unauthorized actions
- **Difficulty**: Trung bình
- **Countermeasure**: Command whitelist, input validation, HMAC signing

### 8. Headless Browser Detection Evasion
- **Attack**: Google detects headless/automated browser → blocks access → tool fails
- **Difficulty**: Ongoing arms race
- **Countermeasure**: Real Chrome profiles, human-like behavior patterns, extension-based approach (current)

---

## XXIII. Anti-Forensics / Evasion

> Kỹ thuật mà **attacker dùng để che dấu** việc đã crack/patch

### 1. Log Tampering
- **Attack**: Modify/delete log files → hide evidence of cracking activity
- **Difficulty**: Dễ
- **Countermeasure**: Remote logging (Firebase), log integrity hash chain, append-only logs

### 2. Timestamp Falsification
- **Attack**: Change file timestamps → hide when files were modified
- **Tools**: `touch`, `timestomp`
- **Difficulty**: Dễ
- **Countermeasure**: Use NTFS $MFT timestamps (harder to fake), compare with server records

### 3. Anti-VM in Crack
- **Attack**: Crack tự detect analysis environment → không activate → tránh bị bắt
- **Difficulty**: Trung bình
- **Countermeasure**: Analyze in bare-metal environment, use hardware-based analysis

### 4. Packed/Encrypted Crack Loader
- **Attack**: Pack crack loader với UPX/Themida → tránh signature detection
- **Difficulty**: Trung bình
- **Countermeasure**: Behavior-based detection (not signature), monitor for suspicious process activity

### 5. Memory-Only Patching
- **Attack**: Patch only in memory, never touch disk file → integrity check passes (checks disk)
- **Difficulty**: Trung bình
- **Countermeasure**: Check code section hash at runtime (in-memory), not just disk file hash

### 6. Rootkit-Level Hiding
- **Attack**: Kernel rootkit hides crack files, processes, registry keys from app
- **Difficulty**: Rất cao
- **Countermeasure**: Secure Boot, driver signing enforcement, cloud-side verification as primary

---

## XXIV. DoS / Availability Attacks

> Attacker không cần crack — chỉ cần phá hoại làm tool không hoạt động

### 1. Task Queue Poisoning
- **Attack**: Fill task queue với garbage prompts → legitimate tasks can't process
- **Difficulty**: Dễ
- **Countermeasure**: Queue size limits, prompt validation, priority queuing for legitimate tasks

### 2. Disk Space Exhaustion
- **Attack**: Trigger mass video generation → fill disk → app crashes
- **Difficulty**: Dễ
- **Countermeasure**: Disk space monitoring, auto-cleanup, output directory size limits

### 3. Memory Exhaustion (OOM)
- **Attack**: Submit massive prompts/configs → allocate unbounded memory → OOM kill
- **Difficulty**: Dễ
- **Countermeasure**: Input size limits, memory monitoring, graceful degradation

### 4. Process Fork Bomb
- **Attack**: Exploit multi-process architecture → spawn infinite Chrome processes
- **Difficulty**: Trung bình
- **Countermeasure**: Max process count limit, process tree monitoring

### 5. WebSocket Connection Flooding
- **Attack**: Open thousands of WS connections → exhaust server resources
- **Difficulty**: Dễ
- **Countermeasure**: Max connection limit, IP-based rate limiting, connection timeout

### 6. Deadlock Injection
- **Attack**: Send specific message sequence → cause async deadlock → app hangs forever
- **Difficulty**: Cao
- **Countermeasure**: Deadlock detection (watchdog timer), async timeout on all operations

### 7. Google Account Lockout
- **Attack**: Deliberately trigger 403/429 → Google locks account → tool can't use account
- **Difficulty**: Dễ
- **Countermeasure**: Account cooldown rotation, rate limit awareness, backup accounts

---

## XXV. Backup / Recovery Exploitation

> Windows có nhiều backup mechanisms → attacker dùng để rollback security state

### 1. Volume Shadow Copy (VSS)
- **Attack**: `vssadmin list shadows` → access old versions of license/trial files
- **Tools**: `vssadmin`, Shadow Explorer
- **Difficulty**: Dễ
- **Countermeasure**: Delete shadow copies of sensitive dirs, Firebase as source of truth

### 2. Windows File History
- **Attack**: Restore old trial markers from File History → reset trial
- **Difficulty**: Dễ
- **Countermeasure**: Exclude security directories from File History, server-side validation

### 3. System Image Backup
- **Attack**: Full system image → restore → trial reset, license rollback
- **Difficulty**: Trung bình
- **Countermeasure**: Firebase-side monotonic timestamp (can't go back)

### 4. Third-Party Backup Tools
- **Attack**: Acronis/Macrium → bare metal restore → complete state rollback
- **Difficulty**: Trung bình
- **Countermeasure**: Server-side state > local state, HWID change detection

### 5. Recycle Bin Recovery
- **Attack**: Recover deleted license files from Recycle Bin → restore old valid license
- **Difficulty**: Dễ
- **Countermeasure**: Secure delete (overwrite before delete), `shutil.rmtree` + overwrite

---

## XXVI. Multi-Account Isolation Attacks

> ⚠️ **ĐẶC THÙ VEO** — VEO chạy nhiều Google accounts trên 1 máy

### 1. Cross-Account Session Leakage
- **Attack**: Token/cookie từ Account A leak sang Account B → unauthorized access
- **Difficulty**: Trung bình (nếu isolation yếu)
- **Countermeasure**: Strict per-account Chrome profile isolation, separate process per account

### 2. Shared Chrome Profile Exploitation
- **Attack**: Nếu nhiều accounts dùng chung profile → cookies mix → session confusion
- **Difficulty**: Dễ (nếu misconfigured)
- **Countermeasure**: One Chrome profile per Google account, verify profile isolation

### 3. Account Credential Crossover
- **Attack**: Extract credentials từ 1 account config → access other accounts
- **Difficulty**: Dễ (nếu stored in same directory)
- **Countermeasure**: Per-account encryption keys, ACLs on profile directories

### 4. Multi-Account Rate Limit Evasion
- **Attack**: Spread load across accounts → bypass per-account limits → abuse total capacity
- **Difficulty**: Dễ (tool supports this natively)
- **Countermeasure**: HWID-based global rate limit (across all accounts), Firebase tracking

### 5. Account Synchronization Attack
- **Attack**: Desync account states → confuse dispatcher → tasks assigned to wrong account
- **Difficulty**: Trung bình
- **Countermeasure**: Account-task binding verification, session ID matching

---

## XXVII. Obfuscation Bypass

> Cracker chuyên bypass obfuscation — cần hiểu họ dùng tools gì

### 1. JavaScript De-obfuscation
- **Attack**: Beautify + rename variables → read extension code easily
- **Tools**: `de4js`, `js-beautify`, Chrome DevTools Formatter, `synchrony`
- **Difficulty**: Dễ
- **Countermeasure**: Control-flow flattening (Babel plugin), webpack dynamic imports, no secrets in JS

### 2. Python Decompilation
- **Attack**: `.pyc` → readable Python source bằng decompiler
- **Tools**: `uncompyle6`, `decompyle3`, `pycdc`, `Bytecode Viewer`
- **Difficulty**: Dễ
- **Countermeasure**: Nuitka (Python→C→binary), Cython compilation, Rust for critical modules

### 3. PyArmor/PyInstaller Key Recovery
- **Attack**: Extract AES key từ PyInstaller `--key` → decrypt PYZ archive → access all modules
- **Tools**: `pyimod00_crypto_key` extraction, custom scripts
- **Difficulty**: Trung bình
- **Countermeasure**: Don't rely solely on PyInstaller `--key`, use Nuitka + Rust layers

### 4. Control Flow Analysis
- **Attack**: Analyze program control flow graph (CFG) → understand logic despite obfuscation
- **Tools**: IDA Pro CFG, Ghidra decompiler, angr
- **Difficulty**: Cao
- **Countermeasure**: Opaque predicates, dead code injection, fake branches, random scheduling

### 5. String Cross-Reference (XREF)
- **Attack**: Find strings ("License", "expired") → XREF to find all code using them → understand logic
- **Tools**: IDA XREF, Ghidra references, `strings` + `grep`
- **Difficulty**: Dễ
- **Countermeasure**: Encrypt ALL user-facing strings, no literal error messages in security code

### 6. Pattern Matching Against Known Protectors
- **Attack**: Recognize PyArmor/Nuitka/Themida patterns → apply known bypass scripts
- **Tools**: Detect-It-Easy (DIE), Exeinfo PE, PEiD
- **Difficulty**: Trung bình
- **Countermeasure**: Custom obfuscation layers on top of standard tools, multi-layer protection

---

## XXVIII. WebDriver / Browser Fingerprint

> ⚠️ **SỐNG CÒN CHO VEO** — Google phát hiện automation = block tất cả

### 1. `navigator.webdriver` Detection
- **Attack**: Google checks `navigator.webdriver === true` → detect automation → block
- **Difficulty**: Dễ (Google-side)
- **Countermeasure**: Extension-based approach (not Selenium/Playwright), CDP `Page.addScriptToEvaluateOnNewDocument` to override

### 2. Chrome DevTools Protocol Fingerprint
- **Attack**: Pages detect CDP connection via `Runtime.enable` side effects
- **Difficulty**: Trung bình
- **Countermeasure**: Minimize CDP usage, use extension APIs instead of CDP when possible

### 3. Canvas / WebGL Fingerprinting
- **Attack**: Google creates unique browser fingerprint → detect reused/automated browsers
- **Difficulty**: Trung bình (Google-side)
- **Countermeasure**: Real Chrome profiles with history, consistent fingerprint per account

### 4. Behavioral Analysis (Mouse/Keyboard Patterns)
- **Attack**: reCAPTCHA v3 analyzes mouse movement, keystroke timing → detect bot behavior → low score
- **Difficulty**: Trung bình (Google-side)
- **Countermeasure**: Human-like interaction timing (random delays), real user engagement on pages

### 5. TLS Fingerprinting (JA3/JA4)
- **Attack**: Server identifies TLS client fingerprint → detect non-browser clients
- **Tools**: JA3/JA4 fingerprint database
- **Difficulty**: Trung bình (server-side)
- **Countermeasure**: Use real Chrome (not custom HTTP client), Chrome TLS stack matches JA3 database

### 6. HTTP/2 Fingerprinting (Akamai)
- **Attack**: HTTP/2 settings, header order, priority frames differ between real browsers and automation
- **Difficulty**: Cao (server-side)
- **Countermeasure**: Use real Chrome browser (extension-based), avoid direct HTTP from Python for Google APIs

---

## Tổng Kết: Priority Matrix (Updated)

```
             Difficulty
             Easy       Medium      Hard       Very Hard
           ┌──────────┬───────────┬──────────┬───────────┐
Critical   │ III.1    │ V.1      │ XV.1     │ XV.3      │
   🔴      │ III.2    │ VII.4    │ VI.1     │           │
           │ I.3      │ II.1     │ XVIII.3  │           │
           │ VII.1    │ XVI.3    │          │           │
           │ XXII.2   │ XVI.1    │          │           │
           │ XXII.5   │ XVIII.1  │          │           │
           │          │ XXII.1   │          │           │
           ├──────────┼───────────┼──────────┼───────────┤
High       │ X.1      │ IV.3     │ II.9     │ IV.11     │
   🟠      │ VIII.1   │ V.8      │ I.5      │ XIV.5     │
           │ VI.5     │ VII.6    │ XVII.2   │           │
           │ XII.1    │ IX.4     │ XIX.4    │           │
           │ XXI.1    │ XVII.6   │          │           │
           │ XXI.3    │ XIX.1    │          │           │
           │ XXII.4   │ XIX.2    │          │           │
           ├──────────┼───────────┼──────────┼───────────┤
Medium     │ VIII.7   │ XI.1     │ V.7      │ XI.2      │
   🟡      │ X.7      │ IV.5     │ VIII.3   │ XI.3      │
           │ XX.3     │ XV.4     │ XX.5     │           │
           │ XX.6     │ XX.1     │          │           │
           │ XXIII.1  │ XXIII.5  │          │           │
           ├──────────┼───────────┼──────────┼───────────┤
Low        │ X.8      │ XIV.3    │          │ XIII.1    │
   🟢      │ I.11     │ XXIII.3  │          │ XXIII.6   │
           └──────────┴───────────┴──────────┴───────────┘

🎯 Ưu tiên phòng chống: Easy+Critical → Easy+High → Medium+Critical
```

### Top 10 Rủi Ro Cao Nhất (dễ khai thác + impact lớn)

| # | Vector | Category | Lý do |
|---|--------|----------|-------|
| 1 | **Monkey Patching** (III.1) | Python | 1 dòng code bypass MỌI check |
| 2 | **PyInstaller Extract** (I.3) | Binary | YouTube tutorials, 90% cracker dùng |
| 3 | **Extension Source Code** (VII.1) | Browser | Plaintext JS, copy là đọc được |
| 4 | **Google Cookie Hijack** (XVI.3) | OAuth | Chrome profile copy = full access |
| 5 | **Config File Injection** (XXI.3) | File | Sửa JSON = đổi behavior |
| 6 | **Account Pool Exploit** (XXII.6) | AI/Auto | Mass Google accounts = unlimited |
| 7 | **Log Leaking** (X.1) | Data Leak | Tokens in logs = no hack needed |
| 8 | **Trial Reset** (VI.5) | License | Delete markers = fresh trial |
| 9 | **WebSocket Hijack** (V.8) | Network | No auth = full control |
| 10 | **API Rate Limit Bypass** (XXII.2) | AI/Auto | Rotate accounts = unlimited quota |

> **Nguyên tắc xuyên suốt**: 
> 1. **Rust native** cho security-critical modules → giải quyết III.1-15 đồng thời
> 2. **Server-authoritative** cho license/credits → giải quyết VI + XIX
> 3. **HMAC signing** cho tất cả IPC → giải quyết V.8-9 + VII.6 + XXII.7
> 4. **Encrypt at rest** cho secrets → giải quyết X + XVI + XXI
> 5. **Browser fingerprint evasion** → giải quyết XXVIII (sống còn cho automation tool)

