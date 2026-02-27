# Log Analysis — 27/02/2026

> Session hôm nay bắt đầu 08:01. Phân tích cả 2 tài khoản.

---

## 1. Tổng quan

| Metric | Giá trị |
|---|---|
| **Log files** | `abc14_at_z-98_com.log` (1886 lines) · `levanlinh_kma_at_gmail_com.log` (6094 lines) |
| **Session hôm nay** | 1/account, bắt đầu 08:01 |
| **Task groups** | `group_20260226_182828` (11 tasks) + `group_20260226_182841` (5 tasks) |
| **Dev log** | `dev_logs_20260227_081843.txt` — rỗng (chỉ header, chưa export) |

---

## 2. 🟢 levanlinh.kma@gmail.com — Hoạt động tốt

### Session 08:01 → 08:21+

- **Startup**: Extension v2.2 connected, reCAPTCHA pre-warmed ✅
- **Submit**: Tất cả T2V → **HTTP 200** ✅
- **Pipeline**: PENDING → ACTIVE → Downloaded 720p → Upscale HTTP 200 ✅
- **AdaptiveBurst**: base delay giảm đến **3.0s** (ổn định)
- **Throughput**: ~7 tasks song song, avg 5.5

### Vấn đề hôm qua (Feb 26, 3 sessions)

| Session | Vấn đề | Kết quả |
|---|---|---|
| 18:57 | Tab frozen 3 lần / 300s | Circuit Breaker OPEN |
| 20:16 | reCAPTCHA 403 ngay submit đầu | Browser disconnect |
| 20:49 | Token quá ngắn (538 chars) | Auth token expired, task fail |

---

## 3. 🔴 abc14@z-98.com — Blocked bởi reCAPTCHA 403

### Session 08:01 → đang chạy

- **Startup**: Extension connected, reCAPTCHA pre-warmed ✅
- ❌ **Mọi submit đều 403**: `reCAPTCHA evaluation failed`
- Escalation: 08:01:54 Fail#1 (30s) → 08:02:32 Fail#2 (60s) → 08:03:40 Fail#3 → **Phase 0→1** (120s)
- **Token valid** (2100+ chars) nhưng Google **reject score** → account bị flag

### Vấn đề hôm qua (Feb 26, 3 sessions)

| Session | 403 liên tiếp | Recovery cao nhất | Kết quả |
|---|---|---|---|
| 18:58 | 7 lần | Phase 2 (HARD restart) | Vẫn fail |
| 20:16 | 2 lần | Phase 0 | Browser disconnect |
| 20:49 | 4+ lần | Phase 1 → Circuit Breaker OPEN | Auto-restart |

---

## 4. Root Cause Analysis

### 4.1 `x-client-data` stuck 8 chars

Cả 2 account gặp warning:
```
⚠️ Readiness timeout (30s) — x-client-data still 8 chars. First submit may 403.
```

Header cần >100 chars để Google accept. Khi 8 chars → guaranteed 403.

### 4.2 Tại sao levanlinh.kma OK mà abc14 fail?

| Factor | levanlinh.kma | abc14 |
|---|---|---|
| reCAPTCHA token | Valid + **accepted** | Valid + **rejected** |
| Google trust score | Cao | Bị flag/throttled |
| Submit result | HTTP 200 | HTTP 403 liên tục |

### 4.3 Task không chuyển sang account khác (BUG)

Khi `abc14` fail → task requeue về READY (`assigned_account=None`) nhưng **luôn quay lại abc14**:

1. **PA3 Fair-Share Gate**: `levanlinh.kma` running=7 > avg+1=5 → `yielding turn` → không lấy task
2. **Race condition**: Foremen abc14 thức dậy cùng lúc sau cooldown → chiếm hết queue
3. **Không có `excluded_accounts`**: task bị fail bởi abc14 hoàn toàn có thể bị abc14 lấy lại

---

## 5. Hệ thống Recovery hiện tại — Đánh giá

| Cái CÓ | Đánh giá |
|---|---|
| Phase 0-3 escalation | ⚠️ Chỉ restart browser, không fix root cause |
| Cooldown 30-180s | ⚠️ Quá ngắn cho account bị flag (cần hàng giờ) |
| Tab keepalive during cooldown | ✅ Giữ session alive |
| CircuitBreaker OPEN/HALF-OPEN | ⚠️ Probe đúng nhưng không chuyển task sang account khác |

| Cái THIẾU | Tác động |
|---|---|
| Cross-account failover | Task stuck trên account lỗi |
| Error classification | Tất cả lỗi xử lý giống nhau |
| Account health monitoring | Không biết account nào healthy |
| Verify trước resume | Retry ngay → fail tiếp |
| Graduated suspension | Cooldown quá ngắn → loop vô tận |

---

## 6. Khuyến nghị

1. **Implement Credit Window + Diagnose-Remedy** → xem `SMART_RECOVERY_ARCHITECTURE.md`
2. **abc14**: Tạm dừng 24-48h hoặc đổi Chrome profile
3. **levanlinh.kma**: Đang healthy, assign thêm tasks từ abc14
4. **Dev log**: Verify export logic — file rỗng
