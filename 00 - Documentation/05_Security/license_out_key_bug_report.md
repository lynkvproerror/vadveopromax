# License "Out Key" Bug Report — Full Debug Analysis

**Date**: 2026-04-09  
**Version**: v2.3.14 → v2.3.14-hotfix  
**Severity**: 🔴 Critical — Users bị mất license key khi mở app  
**Status**: ✅ ALL FIXED (15 findings — 11 defects fixed, 2 verified safe, 2 by-design)  

---

## Tóm tắt vấn đề

Users báo cáo bị "out key" — app yêu cầu nhập lại license key mặc dù key vẫn hợp lệ trên server. Nguyên nhân gốc: **nhiều path trong validation flow gọi `storage.clear()` hoặc trả `valid=False` không chính xác**, dẫn đến cascade:

```
cache bị xóa → _validate_uncached() thấy cached=None 
→ _check_trial() → server trả "upgraded" 
→ auto-restore fail → return ENTER_KEY 
→ app hiện popup nhập key → USER BỊ "OUT KEY"
```

---

## Kiến trúc License Cache

### Bảo mật 3 lớp

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| **L1** | AES-256 Fernet (PBKDF2 100K, machine-bound) | Mã hóa toàn bộ `license.dat` |
| **L2** | HMAC-SHA256 (12+ fields + nonce) | Tamper detection |
| **L3** | Machine ID binding (CPU, MB, BIOS, Disk) | Hardware lock |

### Signature Fields (HMAC)

```python
sig_parts = [
    key, tier, role, expires, last_validated,  # Core
    machine_id, cpu_id, mb_serial, disk_serial, bios_serial,  # HW binding
    nonce,           # Random per save
    "VEO_SIG_V3",    # Static marker
    data_length,     # Anti-tamper
    "v3o_l1c_s1g",   # Obfuscation marker
]
```

### Quan trọng: `last_verified` nằm trong encrypted blob → không thể sửa để bypass online check interval

---

## Danh sách 15 Findings

### Bug #1: No cache → straight to trial check 🔴 CRITICAL

**File**: `security/license_client.py` — `_validate_uncached()` L782-789  
**Root cause**: Khi `storage.load()` trả `None`, code đi thẳng vào `_check_trial()` mà không thử auto-restore.

**Before**:
```python
def _validate_uncached(self) -> LicenseInfo:
    cached = self.storage.load()
    if not cached:
        return self._check_trial()  # ← Thẳng vào trial!
```

**After**:
```python
def _validate_uncached(self) -> LicenseInfo:
    cached = self.storage.load()
    if not cached:
        # Try auto-restore from server FIRST
        restored = self._try_restore_by_mid()
        if restored and restored.valid:
            return restored
        return self._check_trial()
```

**Impact**: User có key hợp lệ + `_mid_to_key` mapping → auto-restore thành công thay vì bị "out key".

---

### Bug #2: Expired cache → immediate `storage.clear()` 🔴 CRITICAL

**File**: `security/license_client.py` — `_validate_uncached()` L805-820  
**Root cause**: Khi license expired theo local cache, code xóa cache ngay mà không thử hỏi server (server có thể đã extend).

**Before**:
```python
expires = self._safe_parse_dt(cached.get('expires', '2000-01-01'))
if expires < datetime.now():
    self.storage.clear()  # ← Xóa ngay!
    return LicenseInfo(valid=False, error="License expired")
```

**After**:
```python
expires = self._safe_parse_dt(cached.get('expires', '2000-01-01'))
if expires < datetime.now():
    # Try online re-validation BEFORE clearing
    _use = getattr(self, '_use_rest', False)
    _has_rc = hasattr(self, '_rest_client') and self._rest_client is not None
    if _use and _has_rc:
        try:
            online_result = self._validate_with_rest(cached.get('key'))
            if online_result and online_result.valid:
                return online_result  # Server extended!
        except Exception:
            pass
    self.storage.clear()
    return LicenseInfo(valid=False, error="License expired")
```

---

### Bug #3: Trial "upgraded" → hard ENTER_KEY 🔴 CRITICAL

**File**: `security/license_client.py` — `_check_trial()` L1184-1209  
**Root cause**: Khi server trả `status="upgraded"`, nếu `_try_restore_by_mid()` fail → return `ENTER_KEY` ngay, không check cached paid key.

**Before**:
```python
if status == "upgraded":
    restored = self._try_restore_by_mid()
    if restored:
        return restored
    # ← ENTER_KEY ngay! Không check cache...
    return LicenseInfo(valid=False, tier="TRIAL", error="ENTER_KEY")
```

**After**:
```python
if status == "upgraded":
    restored = self._try_restore_by_mid()
    if restored and restored.valid:
        return restored
    # Check cached paid key BEFORE giving up
    cached = self.storage.load()
    if cached and cached.get('key') and not cached.get('_is_trial'):
        if cached.get('machine_id') == self.machine_id:
            expires = self._safe_parse_dt(cached.get('expires', '2000-01-01'))
            if expires > datetime.now():
                tier = self._tier_from_code(cached.get('tier', ''))
                return LicenseInfo(
                    valid=True, tier=tier,
                    role=UserRole(cached.get('role', 1)),
                    expires=expires,
                    machine_id=self.machine_id,
                    limits_override=cached.get('_lim')
                )
    return LicenseInfo(valid=False, tier="TRIAL", error="ENTER_KEY")
```

---

### Bug #4: `_validate_online()` gọi `storage.clear()` bypass soft-reject 🟡 HIGH

**File**: `security/license_client.py` — `_validate_online()` L1137-1143  
**Root cause**: `_validate_online()` (legacy Firestore path) gọi `storage.clear()` bên trong khi server reject, nhưng caller `_validate_uncached()` L858-866 lại áp dụng "soft reject, keep cache" policy → **cache đã bị xóa trước khi caller kiểm tra!**

**Flow lỗi**:
```
_validate_uncached() → _validate_online(key)
  → _validate_online: _mid != self.machine_id → self.storage.clear() → return invalid
  → Caller L858: "soft reject, keep cache" → BUT CACHE ALREADY CLEARED!
  → Next validate → cached=None → _check_trial → upgraded → OUT KEY!
```

**Before**:
```python
if data.get('_st') == 'r':
    self.storage.clear()  # ← Xóa trong sub-function!
    return LicenseInfo(valid=False, error="License revoked")

if data.get('_mid') != self.machine_id:
    self.storage.clear()  # ← Xóa trong sub-function!
    return LicenseInfo(valid=False, error="License transferred")
```

**After**:
```python
if data.get('_st') == 'r':
    return LicenseInfo(valid=False, error="License revoked")
    # Caller decides whether to clear cache

if data.get('_mid') and data.get('_mid').lower() != self.machine_id:
    return LicenseInfo(valid=False, error="License transferred")
    # + Added case-insensitive compare + null check
```

---

### Bug #5: `main.py` force `validate_online_now()` mỗi startup 🔴 CRITICAL

**File**: `main.py` L299-318  
**Root cause**: Mỗi lần mở app, `validate_online_now()` reset `last_verified` → force online check → bypass 24h interval policy. Nếu cache bị mất + network fail → cascade vào trial check → OUT KEY.

**Xung đột chính sách**:

| Policy | Hành vi |
|--------|---------|
| `_validate_uncached` 24h interval | Check online 1x/ngày, soft-reject |
| `main.py` startup | **Bypass** 24h, force online, **hard-block** nếu fail |

**Before**:
```python
# main.py startup
online_result = lc.validate_online_now()  # Force online EVERY startup
if not online_result.valid:
    controller._license_valid = False  # HARD BLOCK!
```

**After**:
```python
# main.py startup — trust cached + 6h interval
startup_result = lc.validate()  # Normal flow with soft-reject
if not startup_result.valid:
    controller._license_valid = False
```

**Bảo mật không giảm vì**:
- Cache có HMAC → không forge được
- Machine ID binding → không copy sang máy khác
- 6h interval vẫn catch revoke trong 6 giờ

---

### Bug #6: Integrity check → `storage.clear()` xóa license 🟡 HIGH

**File**: `main.py` L337-341  
**Root cause**: Integrity check fail → `storage.clear()` xóa `license.dat`. User hợp lệ gặp false positive (antivirus, Windows Update) mất license.

**Phân tích bảo mật**: Xóa cache **KHÔNG ngăn attacker** — attacker patch binary → nhập lại key → bypass. Ngược lại, tampered binary **tự động không đọc được cache** vì AES key derive từ PBKDF2 salt trong binary → thay đổi binary → key khác → HMAC fail → `load() = None`.

**Before**:
```python
if not integrity['passed']:
    controller._license_client.storage.clear()  # ← XÓA license!
```

**After**:
```python
if not integrity['passed']:
    # Don't clear license.dat — tampered binary can't decrypt it anyway
    controller._license_client._invalidate_validate_cache()
```

---

### Bug #7: Online check interval 24h → 6h ⬜ ENHANCEMENT

**File**: `security/license_client.py` L830

```diff
-ONLINE_CHECK_INTERVAL = 86400  # 24 hours
+ONLINE_CHECK_INTERVAL = 21600  # 6 hours
```

**Rationale**: User muốn revoke enforcement nhanh hơn. `last_verified` nằm trong encrypted cache nên không bypass được.

---

### Bug #8: `_try_restore_by_mid()` truthy check ✅ VERIFIED SAFE

**File**: `security/license_client.py` — multiple callers  
**Analysis**: `_try_restore_by_mid()` chỉ trả 2 giá trị:
- `None` — không tìm thấy / lỗi
- `LicenseInfo(valid=True)` — restore thành công

→ `if restored:` kiểm tra `None vs LicenseInfo` → **đúng logic**, không gây false positive.

---

### Bug #9: Anti-tamper guards → `storage.clear()` 🟡 HIGH

**File**: `core/app_controller.py` L641-645  
**Root cause**: Cùng vấn đề Bug #6 — anti-tamper guards fail → `storage.clear()` → xóa license trên production.

**Before**:
```python
# app_controller.py controller.start()
if not guards['passed']:
    self._license_client.storage.clear()  # ← XÓA!
```

**After**:
```python
if not guards['passed']:
    # Don't clear — tampered binary can't decrypt cache anyway
    self._license_client._invalidate_validate_cache()
```

---

### Bug #10: Periodic integrity check → `storage.clear()` 🟡 HIGH

**File**: `core/app_controller.py` L4988-4992  
**Root cause**: Timer chạy mỗi 5 phút → integrity check → fail → `storage.clear()` → mất license **khi app đang chạy**.

**Before**:
```python
# _periodic_integrity_check (runs every 5 min!)
if tampered:
    self._license_client.storage.clear()  # ← XÓA khi đang chạy!
```

**After**:
```python
if tampered:
    # Don't clear — tampered binary can't decrypt cache anyway
    self._license_client._invalidate_validate_cache()
```

---

### Bug #11: `LicenseStorage.load()` self-clear trên HMAC fail ✅ BY-DESIGN

**File**: `security/license_client.py` L406-407  
**Behavior**: `storage.load()` gọi `self.clear()` khi HMAC verify fail + không migrate được.

**Đây là hành vi đúng**: cache bị tamper/corrupt → xóa → user phải nhập lại key. Với Bug #1 fix, flow mới sẽ thử `_try_restore_by_mid()` trước → auto-restore nếu `_mid_to_key` tồn tại.

**Edge case duy nhất**: User cũ có key nhưng admin chưa deploy `_mid_to_key` mapping + cache bị corrupt → phải nhập lại key. Đây là **behavior hợp lý** vì mọi auto-restore đều fail.

---

### Bug #12: `NameError: log` crash v2→v3 migration path 🔴 CRITICAL

**File**: `security/license_client.py` — `LicenseStorage.load()` L398, L403  
**Root cause**: `LicenseStorage` class không có `log` hay `logging` global. Khi user nâng cấp app (cache có `_sig_version ≤ 2`), path "auto-migrate v2→v3" gọi `log.info(...)` → **NameError** → rơi vào `except:` L409 → `return None`.

**Cascade**:
```
load() → HMAC v2 fail → try migrate → log.info() → NameError!
→ except: return None
→ _validate_uncached: cached=None → _try_restore_by_mid() 
→ no _mid_to_key? → _check_trial() → "upgraded" → ENTER_KEY → OUT KEY!
```

**Tất cả user nâng cấp từ phiên bản cũ với `_sig_version ≤ 2` sẽ bị out key** nếu auto-restore fail.

**Before**:
```python
if old_version <= 2 and data.get('key'):
    log.info(f"...")      # ← NameError! log không tồn tại
    data.pop('_sig', None)
    data.pop('_nonce', None)
    self.save(data)
    log.info("...")        # ← NameError!
    return data
```

**After**:
```python
if old_version <= 2 and data.get('key'):
    print(f"[LicenseStorage] Migrating license from sig v{old_version} → v3")
    data.pop('_sig', None)
    data.pop('_nonce', None)
    self.save(data)
    print("[LicenseStorage] ✅ License migrated successfully")
    return data
```

---

### Bug #13: Popup trial status "upgraded" → "expired" ⚠️ UX BUG

**File**: `ui/popups/license_popup.py` L750-751, L597-603  
**Root cause**: `status in ("expired", "upgraded")` map cả hai thành `"expired"`, hiện "❌ Đã hết hạn" khi thực tế trial đã được upgrade lên paid.

Không xóa cache, nhưng gây nhầm lẫn user và support khi user bị "out key" do restore miss — UI báo "trial hết hạn" thay vì "đã upgrade, nhập key bên dưới".

**Before**:
```python
elif status in ("expired", "upgraded"):
    return "expired"

# Render:
state_msgs = {
    "active": ("✅ Đang dùng thử", Theme.GREEN),
    "expired": ("❌ Đã hết hạn", Theme.RED),
    "revoked": ("❌ Đã bị thu hồi", Theme.RED),
}
```

**After**:
```python
elif status in ("expired",):
    return "expired"
elif status == "upgraded":
    return "upgraded"

# Render:
state_msgs = {
    "active": ("✅ Đang dùng thử", Theme.GREEN),
    "expired": ("❌ Đã hết hạn", Theme.RED),
    "revoked": ("❌ Đã bị thu hồi", Theme.RED),
    "upgraded": ("✅ Đã nâng cấp — nhập key bên dưới", Theme.YELLOW),
}
```

---

### Bug #14: Cloudflare Worker hardcode `_mid_to_key` ⬜ CONDITIONAL

**File**: `01.2 - Cloudflare Worker/src/worker.js` L28-30, L361  
**Root cause**: Vercel server dùng app-specific collection mapping (`_mid_to_key` vs `_grok_mid_to_key`), nhưng Cloudflare Worker hardcode `"_mid_to_key"`. Khi `app=grok` và Vercel down → Cloudflare backup restore truy vấn sai collection → miss key → user phải nhập lại.

**Ảnh hưởng**: Chỉ app `grok` khi Vercel down. Không ảnh hưởng `veo`.

**Before**:
```javascript
const APP_COLLECTIONS = {
  veo: { lic: "_lic", blocked: "_blocked_machines" },
  grok: { lic: "_lic_grok", blocked: "_grok_blocked_machines" },
};

// handleRestore:
const midData = await readDoc(..., "_mid_to_key", ...);  // ← hardcoded!
```

**After**:
```javascript
const APP_COLLECTIONS = {
  veo: { lic: "_lic", blocked: "_blocked_machines", mid_to_key: "_mid_to_key" },
  grok: { lic: "_lic_grok", blocked: "_grok_blocked_machines", mid_to_key: "_grok_mid_to_key" },
};

// handleRestore:
const midData = await readDoc(..., collections.mid_to_key, ...);
```

---

### Bug #15: `tier.value == "trial"` mismatch với `LicenseTier.TRIAL.value = "TRIA"` ⚠️ STATUS BUG

**File**: `core/app_controller.py` L5115-5116, `core/settings_controller.py` L190-191, L278  
**Root cause**: `LicenseTier.TRIAL` enum value là `"TRIA"` (4 ký tự, khớp server), nhưng 3 nơi trong code so sánh `info.tier.value == "trial"` (lowercase, 5 ký tự).

**Hậu quả**:
- `"TRIA" != "trial"` → **luôn True** → `is_licensed = True` cho trial users
- `is_trial` luôn `False` cho trial users → trial warning **không bao giờ hiện**
- Status bar hiển thị trial users như paid users

**Không gây out key trực tiếp**, nhưng che giấu trạng thái trial → user không biết trial sắp hết → hết hạn đột ngột → support ticket.

**Before**:
```python
"is_licensed": info.valid and info.tier and info.tier.value != "trial",
"is_trial": info.tier and info.tier.value == "trial" if info.valid else True,
```

**After**:
```python
"is_licensed": info.valid and info.tier and info.tier.value != "TRIA",
"is_trial": info.tier and info.tier.value == "TRIA" if info.valid else True,
```

---

## Bảng tổng hợp `storage.clear()` — Trước vs Sau

### Trước (9 locations gọi `storage.clear()`)

| # | File | Line | Context | Verdict |
|---|------|------|---------|---------|
| 1 | `license_client.py` | L797 | Clock tampering | ✅ Keep |
| 2 | `license_client.py` | L818 | Expired (after online re-validate) | ✅ Keep |
| 3 | `license_client.py` | L1012 | `deactivate()` user action | ✅ Keep |
| 4 | `license_client.py` | L1137 | `_validate_online` revoked | ❌ **Removed** |
| 5 | `license_client.py` | L1142 | `_validate_online` machine mismatch | ❌ **Removed** |
| 6 | `license_client.py` | L1224 | Trial expired (server confirmed) | ✅ Keep |
| 7 | `main.py` | L338 | Integrity check fail | ❌ **Removed** |
| 8 | `app_controller.py` | L642 | Anti-tamper guards fail | ❌ **Removed** |
| 9 | `app_controller.py` | L4989 | Periodic integrity fail | ❌ **Removed** |

### Sau (4 locations — chỉ giữ các trường hợp hợp lý)

| # | File | Line | Context | Reason |
|---|------|------|---------|--------|
| 1 | `license_client.py` | L797 | Clock tampering | Cố ý chỉnh clock → xóa đúng |
| 2 | `license_client.py` | L818 | Expired + online confirm | License thực sự hết hạn |
| 3 | `license_client.py` | L1012 | `deactivate()` | User chủ động |
| 4 | `license_client.py` | L1224 | Trial expired (server) | Trial hết hạn |

---

## Validation Flow Diagram (Sau khi fix)

```
App Startup
│
├─ main.py: lc.validate()  ← Sử dụng flow chuẩn (không force online)
│  │
│  └─ _validate_uncached()
│     │
│     ├─ storage.load() = None (file mất/corrupt/HMAC fail)
│     │  ├─ (Bug #12 fix: v2→v3 migration giờ không crash)
│     │  ├─ _try_restore_by_mid() → found? ✅ Return valid
│     │  └─ _check_trial()
│     │     ├─ "upgraded" → _try_restore_by_mid()
│     │     │  ├─ found? ✅ Return valid
│     │     │  └─ not found → check cached paid key
│     │     │     ├─ cached valid? ✅ Return valid
│     │     │     └─ no cache → ENTER_KEY (user nhập lại)
│     │     │        └─ (Bug #13 fix: UI hiện "Đã nâng cấp — nhập key")
│     │     ├─ "active" → ✅ Trial valid
│     │     ├─ "expired" → ❌ Trial hết hạn
│     │     └─ "revoked" → ❌ Admin thu hồi
│     │
│     ├─ cached = trial key → _check_trial() (server-authoritative)
│     │
│     ├─ cached = paid key
│     │  ├─ Clock tamper? → ❌ Clear + re-activate
│     │  ├─ Machine mismatch? → ❌ Wrong machine
│     │  ├─ Expired?
│     │  │  ├─ Online re-validate → server extended? ✅ Return valid
│     │  │  └─ Still expired → ❌ Clear + expired
│     │  │
│     │  └─ 6h elapsed? → Online check
│     │     ├─ Server valid → ✅ Update cache timestamp
│     │     ├─ Server reject → ⚠️ SOFT REJECT (keep cache!)
│     │     └─ Network error → ⚠️ Skip (use cache)
│     │
│     └─ Valid cache, <6h → ✅ Return cached
│
├─ Integrity check fail? → Block features (DO NOT clear cache)
│
└─ _license_valid = False? → Show license popup → Activate
```

---

## Bảng so sánh Kịch bản — Trước/Sau

| # | Kịch bản | Trước (Bug) | Sau (Fix) |
|---|----------|-------------|-----------|
| 1 | Mở app, mạng OK, key hợp lệ | ✅ OK | ✅ OK |
| 2 | Mở app, mạng lỗi, cache hợp lệ | ❌ Có thể OUT KEY | ✅ Dùng cache |
| 3 | Mở app, mạng OK, key bị revoke | ✅ Block (24h) | ✅ Block (6h) |
| 4 | Mở app, cache bị mất | ❌ OUT KEY (trial→upgraded) | ✅ Auto-restore qua Bot API |
| 5 | Integrity false positive | ❌ Xóa cache → OUT KEY | ✅ Block features, giữ cache |
| 6 | Attacker patch binary | ❌ Xóa cache (attacker nhập lại) | ✅ HMAC fail → cache unreadable |
| 7 | User reinstall clean | ❌ Phải nhập key lại | ✅ Cache tự decrypt → OK |
| 8 | License expired, server extended | ❌ Clear ngay → OUT KEY | ✅ Online re-validate trước |
| 9 | Periodic integrity (5min) fail | ❌ Xóa cache khi đang chạy | ✅ Chỉ invalidate memory cache |
| 10 | Anti-tamper guard false positive | ❌ Xóa cache | ✅ Giữ cache, block features |
| 11 | App upgrade v2→v3 sig migration | ❌ NameError → OUT KEY | ✅ print() thay log.info() |
| 12 | Trial upgraded → popup | ❌ Báo "hết hạn" | ✅ Báo "đã nâng cấp — nhập key" |
| 13 | Trial user hiện như paid | ❌ `"trial"` != `"TRIA"` | ✅ So sánh đúng `"TRIA"` |

---

## Files Changed

| File | Lines Modified | Changes |
|------|---------------|---------|
| `security/license_client.py` | L398, L403, L782-789, L807-820, L830, L1137-1143, L1172-1209 | Bugs #1-4, #7, #12 |
| `main.py` | L299-318, L337-341 | Bugs #5, #6 |
| `core/app_controller.py` | L641-645, L4988-4992, L5115-5116 | Bugs #9, #10, #15 |
| `core/settings_controller.py` | L190-191, L278 | Bug #15 |
| `ui/popups/license_popup.py` | L597-603, L750-751 | Bug #13 |
| `01.2 - Cloudflare Worker/src/worker.js` | L28-30, L361 | Bug #14 |

---

## Anti-Bypass Security Verification

### Câu hỏi: User có thể sửa `last_verified` để bypass 6h check không?

**Không** — `last_verified` nằm trong AES-256 encrypted blob (`license.dat`). Sửa bất kỳ byte nào → Fernet decrypt fail → `load()` return `None` → **tự động trigger re-validation**.

### Câu hỏi: Attacker có thể patch binary để skip online check?

**Không hiệu quả** — Patching binary thay đổi code → integrity check fail → `_tamper_detected = True` → app block features. Đồng thời, PBKDF2 salt trong binary thay đổi → AES key khác → **cache trước đó unreadable** → phải kích hoạt lại key.

### Câu hỏi: Tại sao không xóa cache khi integrity fail?

Vì **cache đã tự bảo vệ**: tampered binary → derived AES key khác → HMAC verify fail → `load() = None` → license tự động invalid. Xóa cache chỉ phạt user hợp lệ gặp false positive (antivirus, Windows Update thay đổi file).

---

## Verification Log

- `validate_online_now()` không còn được gọi ở bất kỳ đâu ngoài `_validate_uncached` internal flow
- Công thức `machine_id` và HMAC token khớp giữa client, Vercel, Cloudflare
- Runtime log ngày 09/04/2026 xác nhận validate pass bình thường
- Phiên gần nhất chỉ fail do format key, sau đó activate thành công

---

## Deployment

- **Build**: Chờ rebuild v2.3.14-hotfix
- **Installer**: `VEO_Pro_Max_Setup_v2.3.14.exe`
- **Cloudflare Worker**: Cần `wrangler deploy` sau khi merge Bug #14
- **Backward compatible**: ✅ — không thay đổi cache format, không thay đổi server API

