# Deterministic Extension Binding via CDP Identity Injection — v2

> [!NOTE]
> **Scope Assumption**: `1 Account = 1 Browser Profile = 1 Extension Instance`.
> Race condition xảy ra ở mức cross-profile khi mở song song, không phải do trộn account trong 1 profile.

## 1. Vấn Đề (2 Layer)

| Layer | Mô tả | Root Cause |
|-------|--------|------------|
| **A** | Connection ↔ Profile Binding | `assign_email()` chọn `unregistered[0]` — sai khi timing đổi |
| **B** | Profile/Email ↔ VEO Tab Readiness | `register(tabId:null)` → app trigger warmup trước khi tab sẵn sàng |

## 2. Giải Pháp: 3 Tầng Bảo Vệ

### Tầng 1 — Primary Injection (launch_chrome)
Ngay sau `install_if_needed()`, inject `__veo_identity: email` vào `chrome.storage.local` qua CDP.
Extension đọc identity lúc `onWsConnected()` → register đúng email.

### Tầng 2 — Fallback (assign_email)
Nếu primary injection fail, `assign_email()` hoạt động như cũ.
Handler `assign_email` trong `background.js` persist identity vào storage cho lần restart sau.

### Tầng 3 — Corrective (ensure_all_extensions + check_identity)
`ensure_all_extensions()` **LUÔN inject identity** (kể cả khi bridge đã connected).
Sau inject → gửi WS message `{action: 'check_identity'}` → extension re-read storage → re-register.
`_claim_email_on_connection()` supersede binding cũ nếu sai.

> [!IMPORTANT]
> Tầng 3 là cơ chế **self-correcting**: dù tầng 1 fail và tầng 2 bind sai, tầng 3 sửa lại 100%.

## 3. Layer B Gate

Register với `tabId=null` (source=cdp_identity) → app ghi nhận identity nhưng **KHÔNG** fire `on_extension_connect`.
Chỉ khi `register(tabId=123)` từ `pushTabSnapshotToApp()` → fire callback → warmup bắt đầu.

## 4. Files Thay Đổi

### 4.1. `extension_manager.py` — inject function
```python
def inject_extension_identity(port: int, email: str) -> bool:
    """Inject __veo_identity vào chrome.storage.local via CDP service worker."""
```

### 4.2. `background.js` — 3 thay đổi
- `onWsConnected()`: đọc `__veo_identity` → register(src=cdp_identity)
- `assign_email` handler: persist `chrome.storage.local.set({__veo_identity: email})`
- **MỚI** `check_identity` handler: re-read storage → re-register

### 4.3. `extension_bridge.py` — 2 thay đổi
- Register handler: log `source`, Layer B gate (tabId=null → no callback)
- **MỚI** `send_check_identity()`: gửi WS message tới tất cả connection

### 4.4. `chrome_manager.py` — Primary injection
Sau `install_if_needed()` trong `launch_chrome()`.

### 4.5. `app_controller.py` — Secondary + Corrective
- `ensure_all_extensions()`: **LUÔN inject + check_identity** (không skip khi connected)
- `_on_unregistered_extension()`: inject trước assign_email, gửi check_identity

## 5. Mismatch Resolution
`__veo_identity` là Ground Truth. Nếu content.js detect email khác → dùng identity.

## 6. Backward Compatibility
- Injection fail → code cũ (`assign_email`) hoạt động bình thường
- Extension không có `__veo_identity` → register bằng content.js như cũ
- `check_identity` handler trong extension cũ không tồn tại → message bị ignore (safe)

## 7. Verification Plan

| Test | Kỳ vọng |
|------|---------|
| Launch 2 profile đồng thời | `src=cdp_identity` cho cả 2, không `binding may be wrong` |
| Kill SW trước injection | Primary fail → assign_email fallback → ensure_all corrective fix |
| Version mismatch reinstall | Storage bị wipe → secondary inject set lại → check_identity trigger |
| Tab chưa load | `tabId=null` → no warmup → `tabId=123` → warmup starts |
