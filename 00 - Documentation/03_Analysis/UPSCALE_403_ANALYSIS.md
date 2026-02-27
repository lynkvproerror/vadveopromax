# 🔍 Phân tích Upscale Failure + 403 Recovery Logic

> **Phân tích từ logs session**: 2026-02-25, 10:38-10:41  
> **Version**: 1.0 • **Created**: 2026-02-25

---

## 1. Timeline — Trình tự sự kiện

```
10:38:15  Task 0 picked (T2I, prompt_idx=0)
10:38:22  Task 0 submitted → Extension
10:38:45  Task 0 ✅ HTTP 200 (2 images, 2 mediaIds)
10:38:45  Task 1 picked (T2I, prompt_idx=1) — delay 5.5s
10:38:48  Task 0 pipeline: downloaded 2 images → 1K/
10:38:48  Task 0 upscale 1/2 STARTED ← tại đây bắt đầu song song
          ↓ CONCURRENT ↓
10:38:51  Task 1 submit attempt 1 → ❌ 403 reCAPTCHA
          → Cooldown 30s (consecutive #1)
          → Recovery Phase 0, fail #1: wait readiness
          → Burst backoff: 5.5s → 8.0s
          ↓ CONCURRENT ↓  
10:38:57  Cooldown waiting 25s (tab keepalive)
10:38:59  Upscale 1/2 submit → ❌ 403 reCAPTCHA
          "keeping 1K" — NGAY LẬP TỨC GIỮ LẠI 1K
10:39:00  Upscale 2/2 STARTED
          → wait cooldown (vì cooldown từ task 1)
10:39:22  Upscale 2/2: "waited 22s for cooldown" ← đã đợi
10:39:28  Upscale 2/2 submit → ❌ 403 reCAPTCHA
          "keeping 1K"
          ↓ ↓ ↓
10:39:28  Task 0: ✅ DONE (2 files, quality=4k) ← SAI! cả 2 đều 1K
          ↓ ↓ ↓
10:39:36  Task 1 attempt 2 → ❌ 403 (consecutive #2)
          → Cooldown 60s, reload tabs
10:40:48  Task 1 attempt 3 → ❌ 403 (consecutive #3)
          → Cooldown 120s, Phase 0 exhausted → Phase 1
```

---

## 2. Vấn đề #1: Upscale chạy SONG SONG với Task tiếp theo

### Root Cause

Khi Task 0 tải xong 2 ảnh 1K, engine đồng thời:
1. Bắt đầu upscale 1/2 cho Task 0 (async pipeline)
2. Bắt đầu Task 1 (Foreman picks next task)

Cả hai **dùng chung 1 reCAPTCHA context** trên cùng 1 account. Khi Task 1 gặp 403:
- Cooldown 30s được set cho account
- Upscale 1/2 at 10:38:59 **KHÔNG kiểm tra cooldown trước khi submit**
  - Nó kiểm tra cooldown tại L2552 (`while self.is_account_on_cooldown...`)
  - Nhưng lúc 10:38:48 khi upscale bắt đầu, cooldown CHƯA ĐƯỢC SET (cooldown set lúc 10:38:51)
  - Upscale 1/2 đi vào rate lock, chờ burst delay 5.8s, rồi submit lúc 10:38:59
  - Lúc này cooldown ĐÃ set, nhưng **cooldown check đã pass trước đó** → race condition

### Sequence Diagram

```
Time     Task 1 Worker              Upscale Pipeline
─────    ────────────────           ───────────────────
10:38:48                            upscale 1/2: check cooldown? NO ✅
10:38:48                            upscale 1/2: enter rate lock
10:38:48                            upscale 1/2: burst wait 5.8s...
10:38:51 submit → 403! RECAPTCHA    
10:38:51 set_cooldown(30s)          
10:38:51 burst backoff 5.5→8.0s    (still in burst wait...)
10:38:57 cooldown waiting 25s...   
10:38:59                            upscale 1/2: submit → 403! ❌
                                    → NO cooldown set (upscale doesn't call set_cooldown)
                                    → NO circuit 403 recorded
                                    → just "keeping 1K"
10:39:00                            upscale 2/2: check cooldown? YES (from task 1)
10:39:00                            upscale 2/2: polling cooldown...
10:39:22                            upscale 2/2: cooldown expired, waited 22s
10:39:28                            upscale 2/2: submit → 403! ❌
                                    → "keeping 1K"
```

### Impact

- **Cả 2 upscale đều thất bại** — ảnh giữ lại 1K
- **Log nói "quality=4k" nhưng thức tế là 1K** — misleading
- **Upscale 403 không trigger cooldown** → không bảo vệ các request sau
- **Upscale 403 không ghi vào circuit breaker** → counter bị undercount

---

## 3. Vấn đề #2: Upscale không có retry logic

### So sánh Code

| Feature | Main Task Worker (L1860-2200) | Upscale Pipeline (L2550-2700) |
|---------|------------------------------|-------------------------------|
| Retry loop | ✅ 11 attempts | ❌ 0 retries |
| Cooldown check trước submit | ✅ `wait_for_cooldown()` | ⚠️ Poll-based (L2552), nhưng race condition |
| 403 → set_account_cooldown | ✅ L2045 | ❌ Không gọi |
| 403 → record_circuit_403 | ✅ L2040 | ❌ Không gọi |
| 403 → burst backoff | ✅ L2037 | ❌ Không gọi |
| Recovery phases | ✅ 4 phases | ❌ Không có |
| reCAPTCHA refresh | ✅ L2088+ | ❌ Dùng token cũ/pool |

### Root Cause

Upscale pipeline được thiết kế "fire-and-forget" — thất bại thì giữ 1K. Đây là thiết kế ban đầu khi upscale chưa dùng reCAPTCHA. Sau khi VEO thêm reCAPTCHA cho upscale, code chưa được update.

---

## 4. Vấn đề #3: Log "quality=4k" sai khi upscale thất bại

### Evidence

```
10:39:28 [T2I-Pipeline] Task group_20260225_100706_task_0: ✅ DONE (2 files, quality=4k)
```

Nhưng cả 2 upscale đều 403 → file thực tế là 1K. Log sai vì code tại L2710+ không kiểm tra upscaled_paths có thực sự là 4K hay không.

---

## 5. So sánh HAR — Body upscale thực tế vs Code

### HAR (Browser thật, HTTP 200 ✅)

```json
{
  "mediaId": "CAMS...",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_4K",
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA4Sh...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769880165773",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE"
  }
}
```

**HAR structure**: 
- Top-level keys: `mediaId`, `targetResolution`, `clientContext`
- `clientContext` chứa: `recaptchaContext`, `sessionId`, `projectId`, `tool`
- **KHÔNG có `userPaygateTier`** ✅ (code đã verify đúng)

### Code — `build_upscale_image_body()`

```python
return {
    "mediaId": media_id,
    "targetResolution": target_resolution,
    "clientContext": self._build_client_context(
        recaptcha_token="",
        project_id=project_id,     # ← có projectId ✅
        paygate_tier="",           # ← không có paygateTier ✅
        include_recaptcha=False,   # ← Extension sẽ thêm
    ),
}
```

**Code structure đúng** ✅ — Extension thêm `recaptchaContext` vào `clientContext` sau khi tạo body.

### Kết luận format: Body format ĐÚNG ✗ — Problems lies elsewhere

Upscale body format khớp HAR 100%. Vấn đề 403 KHÔNG phải do body sai, mà **do timing**:
1. Token chưa kịp refresh sau 403 trước đó
2. Cooldown chưa đủ lâu
3. reCAPTCHA context trên page bị "tainted" sau 403 liên tiếp

---

## 6. Phân tích Logic 403 Recovery

### Flow hiện tại (from logs)

```
403 #1 (Task 1, 10:38:51):
  → burst backoff 5.5→8.0s
  → set_cooldown(30s)
  → record_circuit_403 (#1)
  → Recovery Phase 0, fail #1:
    → wait_for_recaptcha_ready (0.2s)
    → priority prefetch 2 tokens
    → retry after 3s backoff
    
403 #2 (Task 1, 10:39:36):
  → burst backoff 8.0→8.0s (already at max)
  → set_cooldown(60s)  ← escalation!
  → record_circuit_403 (#2)
  → Recovery Phase 0, fail #2:
    → refresh_headers (1 tab reloaded)
    → wait 15s + wait_for_recaptcha_ready
    → priority prefetch 2 tokens
    → retry after 5s backoff

403 #3 (Task 1, 10:40:48):
  → set_cooldown(120s)  ← escalation!
  → record_circuit_403 (#3)
  → Phase 0 exhausted → escalate to Phase 1
  → retry after 8s backoff
  → Cooldown 112s remaining...
```

### Nhận xét

| Aspect | Đánh giá | Chi tiết |
|--------|----------|---------|
| **Cooldown escalation** | ✅ ĐÚNG | 30s → 60s → 120s đúng formula `30 * 2^(n-1)` |
| **Tab keepalive during cooldown** | ✅ ĐÚNG | Ping mỗi 20s, log "ping OK" xác nhận |
| **Recovery phases** | ✅ ĐÚNG | Phase 0 → 1 escalation sau 3 fails |
| **reCAPTCHA readiness check** | ✅ ĐÚNG | `check_recaptcha_ready` trước mỗi retry |
| **Priority prefetch** | ✅ ĐÚNG | 2 tokens prefetched mỗi retry |
| **Token length** | ✅ ĐÚNG | 2126-2233 chars (not 538 short tokens) |

### Vấn đề phát hiện trong Recovery

1. **Upscale 403 không tham gia recovery** — gây thêm 2 requests thất bại không cần thiết
2. **Upscale chạy MID-cooldown** — Upscale 1/2 submit tại 10:38:59, TRONG KHI Task 1 đang cooldown
3. **Token length OK nhưng vẫn 403** → Vấn đề có thể là Google rate-limit TOÀN BỘ ACCOUNT, không phải per-token

---

## 7. Root Cause Summary

| # | Vấn đề | Severity | Root Cause |
|---|--------|----------|------------|
| 1 | Upscale submit TRONG cooldown | 🔴 Critical | Race condition: cooldown check pass trước khi cooldown set |
| 2 | Upscale 403 không trigger cooldown | 🔴 Critical | Code thiếu `set_account_cooldown()` trong upscale error path |
| 3 | Upscale 403 không ghi circuit | 🟡 Medium | Code thiếu `record_circuit_403()` trong upscale error path |
| 4 | Upscale không retry | 🟡 Medium | Design "fire-and-forget" — nên thêm 1-2 retries |
| 5 | Log "quality=4k" sai | 🟢 Low | Không kiểm tra upscale_status trước khi log |
| 6 | Upscale concurrent với task mới | 🟡 Medium | Pipeline async không serialize với next task |

---

## 8. Kế hoạch sửa (Recommendations)

### Fix 1: Upscale 403 → trigger cooldown + circuit (CRITICAL)

```python
# engine.py L2674-2686, trong upscale error path:
else:
    error = ext_result.get('error', 'unknown') if ext_result else 'no response'
    
    # ★ FIX: Upscale 403 must participate in cooldown system
    if '403' in str(error) or 'recaptcha' in str(error).lower():
        self._burst_controller.record_error(account.email, 403)
        self.record_circuit_403(account.email)
        self.set_account_cooldown(
            account.email, f"403/upscale: {error}"
        )
    
    log.warning(
        f"[T2I-Upscale] {idx+1}/{total}: "
        f"failed ({error}), keeping 1K"
    )
```

### Fix 2: Upscale cooldown check — use Event-based wait (CRITICAL)

```python
# engine.py L2550-2560, thay poll-based cooldown bằng Event-based:
# OLD: poll while loop (race condition)
# NEW: await event, giống main worker
await self.wait_for_cooldown(account.email)
```

### Fix 3: Upscale retry 1-2 lần (MEDIUM)

```python
# Wrap upscale submit trong retry loop (max 2 attempts):
for upscale_attempt in range(2):
    await self.wait_for_cooldown(account.email)
    # ... submit ...
    if ext_result and ext_result.get('success'):
        break
    elif upscale_attempt < 1:
        # Wait then retry
        await asyncio.sleep(5)
```

### Fix 4: Log quality chính xác (LOW)

```python
# engine.py L2710+, check actual upscale status:
actual_quality = upscale_quality
for vo in task.video_outputs:
    if getattr(vo, 'upscale_status', '') != 'success':
        actual_quality = '1k'
        break
```
