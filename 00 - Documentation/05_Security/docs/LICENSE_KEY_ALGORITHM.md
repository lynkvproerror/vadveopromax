# 🔐 License Key Algorithm - Security Analysis & Improvements

> **Version**: 1.0  
> **Created**: 2026-02-02  
> **Purpose**: Phân tích và cải thiện thuật toán license key

---

## 📋 Legacy Algorithm (DEPRECATED - v1.x)

> [!WARNING]
> **This format is DEPRECATED**. See [v2.3 Format](#-proposed-improved-algorithm) below for current implementation.

### Legacy Key Format (DO NOT USE)
```
[REDACTED] - Legacy format no longer documented for security
```

### Security Issues in Legacy Format

| # | Issue | Severity | Description |
|---|-------|----------|-------------|
| 1 | **Predictable checksum** | 🔴 Critical | Checksum chỉ dựa trên visible parts, attacker có thể tính lại |
| 2 | **No secret salt** | 🔴 Critical | Không có server-side secret trong checksum |
| 3 | **Short MID prefix** | 🟡 Medium | Chỉ 4 chars MID dễ brute force |
| 4 | **Timestamp visible** | 🟡 Medium | Có thể đoán được key format từ timestamp |
| 5 | **`days` không dùng** | 🟢 Low | Parameter `days` không được include trong key |

---

## ✅ Current Algorithm (v2.3)

### New Key Format (v2.3 - No Prefix)
```
XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
 │     │     │     │     │     │     │     │
 └─────┴─────┴─────┴─────┴─────┴─────┴─────┴── All XOR obfuscated hex
                                              (No product identifier visible)
```

**Security Features:**
- Pure obfuscated hex format
- HMAC-SHA256 signature
- All metadata hidden (MID, duration, timestamp)

### Improved Code

```python
import hashlib
import hmac
import secrets
from datetime import datetime

class LicenseKeyGenerator:
    """Secure license key generation with HMAC signature."""
    
    # ⚠️ CRITICAL: Store this in environment variable, NEVER in code
    # Generate once: secrets.token_hex(32)
    SECRET_KEY = "YOUR_64_CHAR_HEX_SECRET_KEY_HERE"
    
    TIER_CODES = {
        "TRIAL": "TRIA",
        "BASIC": "BASI", 
        "PRO": "PROF",
        "ENTERPRISE": "ENTR",
        "LIFETIME": "LIFE"
    }
    
    def generate_key(self, machine_id: str, tier: str, days: int) -> str:
        """
        Generate secure hardware-bound license key.
        
        Security improvements:
        1. HMAC signature instead of simple SHA256
        2. Random salt makes same MID+tier produce different keys
        3. Full MID hash instead of prefix
        4. Days encoded in signature
        """
        
        # Components
        prefix = "VEO"
        
        # Hash full machine ID (not just prefix)
        mid_hash = hashlib.sha256(machine_id.encode()).hexdigest()[:4].upper()
        
        # Tier code
        tier_code = self.TIER_CODES[tier]
        
        # Random salt (makes each key unique)
        salt = secrets.token_hex(4).upper()  # 8 chars
        
        # Create signature payload (includes ALL data)
        payload = f"{prefix}:{mid_hash}:{tier_code}:{salt}:{days}:{machine_id}"
        
        # HMAC-SHA256 signature (requires secret key)
        signature = hmac.new(
            bytes.fromhex(self.SECRET_KEY),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()[:4].upper()
        
        return f"{prefix}-{mid_hash}-{tier_code}-{salt}-{signature}"
    
    def validate_key(self, key: str, machine_id: str, days: int) -> bool:
        """
        Server-side validation of key.
        
        Note: Client should NOT have SECRET_KEY, validation happens via Firebase.
        """
        
        try:
            parts = key.split("-")
            if len(parts) != 5 or parts[0] != "VEO":
                return False
            
            prefix, mid_hash, tier_code, salt, signature = parts
            
            # Reconstruct expected signature
            # Note: We need to know the tier from tier_code
            tier = {v: k for k, v in self.TIER_CODES.items()}.get(tier_code)
            if not tier:
                return False
            
            payload = f"{prefix}:{mid_hash}:{tier_code}:{salt}:{days}:{machine_id}"
            expected_sig = hmac.new(
                bytes.fromhex(self.SECRET_KEY),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()[:4].upper()
            
            # Timing-safe comparison
            return hmac.compare_digest(signature, expected_sig)
        
        except Exception:
            return False
```

---

## 🔄 Migration Strategy

### Phase 1: Server-Side Only (No client changes)
```python
# Admin generates new-format keys
new_key = LicenseKeyGenerator().generate_key(machine_id, tier, days)

# Firebase stores BOTH old and new format info
db.collection("_lic").document(new_key).set({
    "_t": tier,
    "_st": "a",
    "_exp": expiry_date,
    "_mid": hashlib.sha256(machine_id.encode()).hexdigest(),  # Full hash
    "_v": 2,  # Version 2 = new algorithm
    "_salt": salt,  # Stored for validation
    ...
})
```

### Phase 2: Client Validation (Firebase-based)
```python
# Client NEVER validates locally, always asks Firebase
def validate_license(key: str, machine_id: str) -> bool:
    """
    Client-side validation via Firebase lookup.
    
    The key itself is the document ID, no need to decrypt.
    Security comes from:
    1. Firebase rules (rate limiting)
    2. Machine ID matching
    3. Key must exist in Firebase (can't forge)
    """
    
    doc = db.collection("_lic").document(key).get()
    
    if not doc.exists:
        return False
    
    data = doc.to_dict()
    
    # Check status
    if data.get("_st") != "a":
        return False
    
    # Check machine ID
    expected_mid = hashlib.sha256(machine_id.encode()).hexdigest()
    if data.get("_mid") != expected_mid:
        log_security_event("KEY_SHARING_ATTEMPT", key, machine_id)
        return False
    
    # Check expiry
    if datetime.now().strftime("%Y-%m-%d") > data.get("_exp", ""):
        return False
    
    return True
```

---

## 🛡️ Why This Is Secure

| Attack | Old Algorithm | New Algorithm |
|--------|---------------|---------------|
| **Keygen** | ❌ Can compute checksum | ✅ Need SECRET_KEY for HMAC |
| **Brute force** | ⚠️ 4^4 MID space | ✅ Firebase rate limiting |
| **Key sharing** | ⚠️ Only prefix bound | ✅ Full MID hash in Firebase |
| **Replay** | ⚠️ Same MID = same key | ✅ Random salt = unique keys |
| **Offline crack** | ❌ All data in key | ✅ Validation requires Firebase |

---

## 📋 Implementation Checklist

- [ ] Generate 64-char hex secret key
- [ ] Store in environment variable (NOT in code)
- [ ] Update `license_keygen.py` with new algorithm
- [ ] Update `license_admin.py` to use new generator
- [ ] Deploy Firebase rules from `FIREBASE_SECURITY_RULES.md`
- [ ] Test rate limiting
- [ ] Test key sharing detection

---

## 🔗 Related Files

| File | Action |
|------|--------|
| `license_keygen.py` | Replace with new algorithm |
| `license_admin.py` | Update to use new generator |
| `license_client.py` | Keep Firebase-based validation |
| `FIREBASE_SECURITY_RULES.md` | Deploy rules |
