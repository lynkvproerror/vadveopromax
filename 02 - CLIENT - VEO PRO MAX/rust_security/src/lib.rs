use pyo3::prelude::*;
use sha2::{Sha256, Digest};
use std::time::Instant;

// ============================================================
// MODULE 1: Anti-Debug
// ============================================================

/// Check if a debugger is attached (IsDebuggerPresent).
#[pyfunction]
fn is_debugger_attached() -> bool {
    #[cfg(target_os = "windows")]
    {
        use winapi::um::debugapi::IsDebuggerPresent;
        unsafe { IsDebuggerPresent() != 0 }
    }
    #[cfg(not(target_os = "windows"))]
    { false }
}

/// Timing-based debugger detection.
/// Normal execution of simple loop: <1ms. Under debugger: >50ms.
#[pyfunction]
fn timing_check() -> bool {
    let start = Instant::now();

    // Simple computation that should be fast
    let mut x: u64 = 0;
    for i in 0..10000u64 {
        x = x.wrapping_add(i).wrapping_mul(31);
    }

    let elapsed = start.elapsed().as_millis();
    // If this takes >50ms, likely being single-stepped in debugger
    elapsed > 50
}

/// Check Debug Registers (DR0-DR7) for hardware breakpoints.
#[pyfunction]
fn check_debug_registers() -> bool {
    #[cfg(target_os = "windows")]
    {
        use winapi::um::processthreadsapi::GetCurrentThread;
        use winapi::um::winnt::CONTEXT;
        use std::mem::zeroed;

        unsafe {
            let mut ctx: CONTEXT = zeroed();
            ctx.ContextFlags = 0x00100010; // CONTEXT_DEBUG_REGISTERS

            // GetThreadContext
            use winapi::um::processthreadsapi::GetThreadContext;
            let thread = GetCurrentThread();
            if GetThreadContext(thread, &mut ctx) != 0 {
                // DR0-DR3 contain hardware breakpoint addresses
                // Non-zero = hardware breakpoint set
                return ctx.Dr0 != 0 || ctx.Dr1 != 0 || ctx.Dr2 != 0 || ctx.Dr3 != 0;
            }
        }
        false
    }
    #[cfg(not(target_os = "windows"))]
    { false }
}

/// Combined anti-debug check (runs all methods).
#[pyfunction]
fn full_anti_debug_check() -> PyResult<(bool, Vec<String>)> {
    let mut flags: Vec<String> = Vec::new();

    if is_debugger_attached() {
        flags.push("debugger_attached".into());
    }
    if timing_check() {
        flags.push("timing_anomaly".into());
    }
    if check_debug_registers() {
        flags.push("debug_registers".into());
    }

    let detected = !flags.is_empty();
    Ok((detected, flags))
}

// ============================================================
// MODULE 2: Integrity Check
// ============================================================

/// Compute SHA-256 hash of a file.
#[pyfunction]
fn hash_file(path: &str) -> PyResult<String> {
    use std::fs::File;
    use std::io::Read;

    let mut file = File::open(path)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(format!("Cannot open {}: {}", path, e)))?;

    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];

    loop {
        let n = file.read(&mut buffer)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyIOError, _>(e.to_string()))?;
        if n == 0 { break; }
        hasher.update(&buffer[..n]);
    }

    let result = hasher.finalize();
    Ok(format!("{:x}", result))
}

/// Verify a file's hash against expected value.
#[pyfunction]
fn verify_file_hash(path: &str, expected: &str) -> PyResult<bool> {
    let actual = hash_file(path)?;
    Ok(actual == expected)
}

// ============================================================
// MODULE 3: Hardware Fingerprint (stable, native)
// ============================================================

/// Get CPU ID via CPUID instruction (native, cannot be spoofed easily).
#[pyfunction]
fn get_native_cpuid() -> String {
    #[cfg(target_arch = "x86_64")]
    {
        // CPUID leaf 1 returns processor info
        let cpuid_result = unsafe { std::arch::x86_64::__cpuid(1) };
        format!(
            "{:08X}{:08X}{:08X}{:08X}",
            cpuid_result.eax, cpuid_result.ebx, cpuid_result.ecx, cpuid_result.edx
        )
    }
    #[cfg(not(target_arch = "x86_64"))]
    {
        "unsupported_arch".to_string()
    }
}

/// Generate hardware fingerprint combining CPUID + WMI data.
#[pyfunction]
fn native_machine_id() -> String {
    let cpuid = get_native_cpuid();

    // Combine CPUID with additional entropy
    let mut hasher = Sha256::new();
    hasher.update(cpuid.as_bytes());
    hasher.update(b"|VEO_NATIVE|");

    // Add hostname as additional factor
    if let Ok(hostname) = std::env::var("COMPUTERNAME") {
        hasher.update(hostname.as_bytes());
    }

    let result = hasher.finalize();
    format!("{:x}", result)
}

// ============================================================
// MODULE 4: Frida Detection
// ============================================================

/// Detect Frida dynamic instrumentation framework.
#[pyfunction]
fn detect_frida() -> PyResult<(bool, Vec<String>)> {
    let mut flags: Vec<String> = Vec::new();

    #[cfg(target_os = "windows")]
    {
        use winapi::um::libloaderapi::GetModuleHandleA;
        use std::ffi::CString;

        // Check for Frida DLLs
        let suspicious_dlls = [
            "frida-agent",
            "frida-gadget",
            "frida-winjector-helper-32",
            "frida-winjector-helper-64",
        ];

        for dll_name in &suspicious_dlls {
            if let Ok(cname) = CString::new(*dll_name) {
                unsafe {
                    let handle = GetModuleHandleA(cname.as_ptr());
                    if !handle.is_null() {
                        flags.push(format!("frida_dll_{}", dll_name));
                    }
                }
            }
        }

        // Check for Frida's default port (27042)
        use std::net::TcpStream;
        use std::time::Duration;
        if TcpStream::connect_timeout(
            &"127.0.0.1:27042".parse().unwrap(),
            Duration::from_millis(100),
        ).is_ok() {
            flags.push("frida_port_27042".into());
        }
    }

    let detected = !flags.is_empty();
    Ok((detected, flags))
}

// ============================================================
// MODULE 5: DLL Injection Detection
// ============================================================

/// Check loaded DLLs against blacklist.
#[pyfunction]
fn detect_injected_dlls() -> PyResult<(bool, Vec<String>)> {
    let mut flags: Vec<String> = Vec::new();

    #[cfg(target_os = "windows")]
    {
        use winapi::um::tlhelp32::*;
        use winapi::um::processthreadsapi::GetCurrentProcessId;
        use winapi::um::handleapi::CloseHandle;
        use std::ffi::OsString;
        use std::os::windows::ffi::OsStringExt;

        let blacklist = [
            "cheatengine", "x64dbg", "ollydbg", "immunity",
            "hookshark", "apimonitor", "winspy", "processhacker",
        ];

        unsafe {
            let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
            if snapshot as isize != -1 {
                let mut entry: MODULEENTRY32W = std::mem::zeroed();
                entry.dwSize = std::mem::size_of::<MODULEENTRY32W>() as u32;

                if Module32FirstW(snapshot, &mut entry) != 0 {
                    loop {
                        let module_name = OsString::from_wide(
                            &entry.szModule[..entry.szModule.iter().position(|&c| c == 0).unwrap_or(entry.szModule.len())]
                        ).to_string_lossy().to_lowercase();

                        for bl in &blacklist {
                            if module_name.contains(bl) {
                                flags.push(format!("injected_dll_{}", module_name));
                            }
                        }

                        if Module32NextW(snapshot, &mut entry) == 0 {
                            break;
                        }
                    }
                }
                CloseHandle(snapshot);
            }
        }
    }

    let detected = !flags.is_empty();
    Ok((detected, flags))
}

// ============================================================
// BUILD INFO
// ============================================================

/// Internal version — fake modules won't have this.
#[pyfunction]
fn _internal_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Build timestamp — changes every build.
#[pyfunction]
fn _build_timestamp() -> String {
    // Populated by build.rs at compile time
    include_str!(concat!(env!("OUT_DIR"), "/build_ts.txt")).to_string()
}

// ============================================================
// COMBINED CHECK
// ============================================================

/// Run all native security checks. Returns (all_passed, details_dict).
#[pyfunction]
fn full_security_check() -> PyResult<(bool, Vec<(String, bool, Vec<String>)>)> {
    let mut results: Vec<(String, bool, Vec<String>)> = Vec::new();
    let mut all_passed = true;

    // Anti-Debug
    let (debug_detected, debug_flags) = full_anti_debug_check()?;
    if debug_detected { all_passed = false; }
    results.push(("anti_debug".into(), !debug_detected, debug_flags));

    // Frida
    let (frida_detected, frida_flags) = detect_frida()?;
    if frida_detected { all_passed = false; }
    results.push(("frida_detection".into(), !frida_detected, frida_flags));

    // DLL Injection
    let (dll_detected, dll_flags) = detect_injected_dlls()?;
    if dll_detected { all_passed = false; }
    results.push(("dll_injection".into(), !dll_detected, dll_flags));

    Ok((all_passed, results))
}

// ============================================================
// PYTHON MODULE
// ============================================================

/// VEO Pro Max Native Security Module
#[pymodule]
fn veo_security(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Anti-Debug
    m.add_function(wrap_pyfunction!(is_debugger_attached, m)?)?;
    m.add_function(wrap_pyfunction!(timing_check, m)?)?;
    m.add_function(wrap_pyfunction!(check_debug_registers, m)?)?;
    m.add_function(wrap_pyfunction!(full_anti_debug_check, m)?)?;

    // Integrity
    m.add_function(wrap_pyfunction!(hash_file, m)?)?;
    m.add_function(wrap_pyfunction!(verify_file_hash, m)?)?;

    // HWID
    m.add_function(wrap_pyfunction!(get_native_cpuid, m)?)?;
    m.add_function(wrap_pyfunction!(native_machine_id, m)?)?;

    // Frida Detection
    m.add_function(wrap_pyfunction!(detect_frida, m)?)?;

    // DLL Injection
    m.add_function(wrap_pyfunction!(detect_injected_dlls, m)?)?;

    // Build Info
    m.add_function(wrap_pyfunction!(_internal_version, m)?)?;
    m.add_function(wrap_pyfunction!(_build_timestamp, m)?)?;

    // Combined
    m.add_function(wrap_pyfunction!(full_security_check, m)?)?;

    Ok(())
}
