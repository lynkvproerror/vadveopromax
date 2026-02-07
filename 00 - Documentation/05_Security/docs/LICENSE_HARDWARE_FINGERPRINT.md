# 🔧 Hardware Fingerprint & Clone Detection

> Split from LICENSE_PROTECTION_SYSTEM.md

---

## Machine ID Components

| Component | Used | Reason |
|-----------|------|--------|
| CPU ID | ✅ | Unique per CPU |
| Motherboard Serial | ✅ | Stable |
| Motherboard UUID | ✅ | Unique per board |
| BIOS Serial | ✅ | Embedded in hardware |
| Disk Serial | ✅ | Detects HDD transfer |
| MAC Address | ❌ | Too unstable (USB WiFi changes it) |
| GPU | ❌ | Users upgrade GPUs |
| RAM | ❌ | Users upgrade RAM |

---

## Implementation

```python
class HardwareFingerprint:
    @staticmethod
    def get_machine_id() -> str:
        """Generate unique machine fingerprint hash"""
        components = HardwareFingerprint.get_all_components()
        
        # Combine STABLE components only
        combined = '|'.join([
            components.get('cpu_id', ''),
            components.get('mb_serial', ''),
            components.get('mb_uuid', ''),
            components.get('bios_serial', ''),
            components.get('disk_serial', ''),
        ])
        
        return hashlib.sha256(combined.encode()).hexdigest()
    
    @staticmethod
    def get_display_id() -> str:
        """Short 8-char ID for display"""
        return HardwareFingerprint.get_machine_id()[:8].upper()
```

---

## Clone Detection

```python
class CloneDetector:
    @staticmethod
    def detect_vm() -> bool:
        """Detect virtual machine environment"""
        vm_indicators = ['vmware', 'virtualbox', 'qemu', 'hyper-v']
        
        bios = subprocess.check_output(
            'wmic bios get manufacturer,version', shell=True
        ).decode().lower()
        
        return any(ind in bios for ind in vm_indicators)
    
    @staticmethod
    def verify_hardware_match(stored: dict) -> dict:
        """Compare stored vs current hardware"""
        current = HardwareFingerprint.get_all_components()
        
        critical = ['mb_uuid', 'bios_serial', 'cpu_id']
        mismatches = [k for k in critical if stored.get(k) != current.get(k)]
        
        return {
            "valid": len(mismatches) == 0,
            "mismatches": mismatches,
            "is_vm": CloneDetector.detect_vm()
        }
```

---

## What Changes Invalidate License?

| Change | License Impact |
|--------|----------------|
| Replace CPU | ❌ Invalid |
| Replace Motherboard | ❌ Invalid |
| Clone HDD to new PC | ❌ Invalid |
| Replace HDD (same PC) | ⚠️ Re-activation needed |
| Add/remove RAM | ✅ Still valid |
| Add GPU | ✅ Still valid |
| Reinstall Windows | ✅ Still valid |
| Move to VM | ❌ Invalid |
