# 🔍 Chrome Bug Fixes — Compliance Audit vs Concurrency Analysis

> **Audit date**: 2026-02-21 · **Scope**: Tab limiter + Stale headers recovery fixes

---

## Fixes Audited

| Fix | Files Modified |
|-----|---------------|
| **Tab Limiter (Python)** | `chrome_manager.py`, `profiles_controller.py` |
| **Tab Limiter (Extension)** | `background.js` |
| **Stale Headers Recovery** | `extension_bridge.py`, `refresh_manager.py`, `background.js` |

---

## ✅ Tuân Thủ

### 1. Token Storage vẫn tập trung (§15.2 ✅)

Các fix **không thêm credential storage mới**. `extension_bridge.py` chỉ thêm state tracking (`_frozen_tab_counts`, `_stale_log_times`) — đây là operational state, không phải credential. Token/headers vẫn nằm hoàn toàn trong `AccountSession` + `ExtensionBridge`.

### 2. Không thêm Law of Demeter violations (Fragmentation #1 ✅)

Không có code mới nào truy cập `_engine._account_manager._accounts`. Các fix chỉ gọi public APIs: `get_cached_headers()`, `refresh_headers()`, `refresh_headers_lightweight()`, `is_connected()`.

### 3. Heartbeat monitor dùng đúng encapsulated API (§15.2 ✅)

`_heartbeat_loop` mới gọi `self.refresh_headers_lightweight()` — method public của chính `ExtensionBridge`, không bypass qua internal state.

---

## ⚠️ Vi Phạm

### 1. Refresh trigger thêm rời rạc (§15.3 Gap #2) — MEDIUM

Concurrency Analysis §15.2 đã cảnh báo: **"Refresh triggers scattered — 3 module quyết định KHI NÀO gọi refresh"**.

Sau fix, **refresh triggers bây giờ ở 4 nơi** (thêm 1):

| Module | Trigger | Trước fix | Sau fix |
|--------|---------|-----------|---------|
| `refresh_manager.py` | `check_sessions_need_refresh()` | ✅ Có | ✅ Có (+ 60s cooldown) |
| `extension_bridge.py` `_heartbeat_loop` | Missing heartbeat >120s | ❌ Không | ⚠️ **MỚI** |
| `extension_bridge.py` `tab_frozen` handler | Frozen tab recovery | ❌ Không (chỉ log) | ⚠️ **MỚI** |
| `background.js` `checkHeartbeats` | Tab frozen → reload | ✅ Có | ✅ Có (capped) |

> [!WARNING]
> Thêm 2 refresh trigger mới trong `extension_bridge.py` làm **tăng fragmentation**, dù có cooldown/rate-limit. Lý tưởng, tất cả refresh triggers nên đi qua 1 `RefreshCoordinator` duy nhất.

**Remediation**: Tạo method `_trigger_refresh(email, reason)` trong `ExtensionBridge` wrap tất cả refresh logic (lightweight → full → escalate), dùng chung cho cả heartbeat loop và tab_frozen handler. Sau đó `refresh_manager.py` nên gọi method này thay vì gọi trực tiếp `refresh_headers()`.

### 2. `setattr` dùng trong heartbeat loop (Code smell)

```python
# extension_bridge.py — heartbeat loop
recovery_key = f"_hb_recovery_{email}"
last_attempt = getattr(self, recovery_key, 0)
setattr(self, recovery_key, time.time())
```

Đây là dynamic attribute creation — should be a proper dict `self._hb_recovery_times: Dict[str, float]` thay vì `setattr`.

**Remediation**: Thay `getattr/setattr` bằng `self._hb_recovery_times` dict (khai báo trong `__init__`).

---

## Kết Luận

| Aspect | Status |
|--------|--------|
| Token storage centralization | ✅ Tuân thủ |
| Law of Demeter | ✅ Tuân thủ |
| Refresh trigger centralization | ⚠️ Tăng fragmentation (2 trigger mới) |
| Code quality | ⚠️ 1 code smell (setattr) |

**Tổng**: Fix đạt yêu cầu functional (break infinite loop thành công), nhưng tăng nhẹ fragmentation ở refresh triggers. Recommend fix code smell (`setattr` → dict) ngay, và plan consolidation refresh triggers vào `RefreshCoordinator` trong sprint sau.
