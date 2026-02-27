# 🔍 Cross-Audit: Image Generation Workflow — T2I Pipeline + Queue + Extension

> **Phân tích từ**: UPSCALE_403_ANALYSIS.md + FOREMAN_PIPELINE_API_FLOW.md + TAB_KEEPALIVE_ARCHITECTURE.md  
> **Version**: 1.0 • **Created**: 2026-02-25  
> **Scope**: Tab T2I (Tab 4), Tab I2I (Tab 5), Queue, Engine Foreman, Extension Bridge, background.js

---

## 1. Sơ đồ tổng quan — Full Pipeline từ UI → Google API

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  UI Layer (PySide6)                                                         │
│                                                                             │
│  Tab T2I (tab_t2i.py)         Tab I2I (tab_i2i.py)                         │
│  └─ add_t2i_batch() ──────── └─ add_i2i_batch() ──────────────────────┐    │
│           │                            │                               │    │
│           └──────── AppController.submit_prompts() ────────────────────┘    │
│                              │                                              │
│                              ▼                                              │
│                    Dispatcher.enqueue(Task)                                 │
│                              │                                              │
└──────────────────────────────┼──────────────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────────────┐
│  Engine Layer                │                                              │
│                              ▼                                              │
│  ┌──────────── Foreman (_account_foreman_loop) ──────────────────────┐      │
│  │  SEQUENTIAL per account                                           │      │
│  │                                                                   │      │
│  │  Step 1: acquire_workers(1) → wait if full                       │      │
│  │  Step 2: check cooldown → wait if on cooldown                    │      │
│  │  Step 3: get_next_task() → FIFO from Dispatcher                  │      │
│  │  Step 4: build_request_body() → api_client                       │      │
│  │  Step 5: ★ submit via Extension Bridge                           │      │
│  │          └─ ext_bridge.submit_prompt(endpoint="T2I", body=...)   │      │
│  │  Step 6: Parse response → WorkerResult                           │      │
│  │  Step 7: ★ Fire-and-forget: _run_t2i_pipeline_bg()              │      │
│  │  Step 8: Loop back to Step 1 (next task)                         │      │
│  └───────────────────────────┬───────────────────────────────────────┘      │
│                              │                                              │
│                     fire-and-forget                                         │
│                              │                                              │
│  ┌──────────── T2I Pipeline (_run_t2i_pipeline_bg) ──────────────────┐      │
│  │  CONCURRENT — nhiều pipeline chạy song song                       │      │
│  │                                                                   │      │
│  │  Stage 1: Download 1K images (FIFE URLs → local files)           │      │
│  │  Stage 2: Upscale to 4K/2K (per image, needs reCAPTCHA)         │      │
│  │  Stage 3: Complete task (dispatcher.complete_task)                │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                             │
│  ┌──────────── UpscaleQueue (video upscale) ─────────────────────────┐      │
│  │  Per-account background worker                                    │      │
│  │  Sequential submit → parallel poll (video upscale only)           │      │
│  │  Has full cooldown + circuit breaker + retry logic ✅              │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────────────┐
│  Extension Layer             │                                              │
│                              ▼                                              │
│  ExtensionBridge (Python)                                                   │
│  └─ submit_prompt() ──→ WebSocket ──→ background.js                        │
│                                              │                              │
│  background.js (Chrome Extension)            │                              │
│  ├─ Step 1: Find tab for email               │                              │
│  ├─ Step 2: chrome.scripting.executeScript    │                              │
│  │          (world: MAIN — ngay trên VEO page)                              │
│  │          ├─ Extract reCAPTCHA siteKey                                    │
│  │          ├─ ★ grecaptcha.enterprise.execute(action)                      │
│  │          ├─ Inject recaptchaContext vào body.clientContext                │
│  │          ├─ Get Authorization header                                     │
│  │          └─ fetch(endpointUrl, body) → Google API                        │
│  └─ Step 3: Return result via WebSocket                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                    Google VEO API ←→ Response
```

---

## 2. Audit kết quả — Kiểm tra từng layer

### 2.1 UI Layer → Engine (Tab 4, 5)

| # | Kiểm tra | Kết quả | Ghi chú |
|---|----------|---------|---------|
| 1 | TabT2I gọi đúng `add_t2i_batch()` | ✅ OK | `CONTROLLER_METHOD = "add_t2i_batch"` |
| 2 | TabT2I dùng ImageSidebar (không VideoSidebar) | ✅ OK | Override `_create_sidebar_widget()` |
| 3 | Task enqueueing vào Dispatcher | ✅ OK | FIFO + priority queue |
| 4 | Tab Queue hiển thị tiến trình | ✅ OK | `update_progress()` callbacks |

### 2.2 Engine Foreman → Submit

| # | Kiểm tra | Kết quả | Ghi chú |
|---|----------|---------|---------|
| 5 | Foreman kiểm tra cooldown TRƯỚC submit | ✅ OK | L1495: `is_account_on_cooldown()` |
| 6 | Foreman build T2I body đúng | ✅ OK | `api_client.build_request_body()` |
| 7 | Foreman gửi qua Extension Bridge | ✅ OK | `ext_bridge.submit_prompt(endpoint="T2I")` |
| 8 | T2I endpoint = dynamic URL | ✅ OK | `projects/{projectId}/flowMedia:batchGenerateImages` |
| 9 | T2I response parse correctly | ✅ OK | Extract `fifeUrl`, `mediaId` from `media[]` |
| 10 | Fire-and-forget pipeline | ✅ OK | `_run_t2i_pipeline_bg()` via `asyncio.create_task()` |
| 11 | Worker slots transfer | ✅ OK | `worker_count = 0` after fire-and-forget |

### 2.3 Extension Bridge → background.js → Google API

| # | Kiểm tra | Kết quả | Ghi chú |
|---|----------|---------|---------|
| 12 | Endpoint mapping đúng | ✅ OK | `UPSCALE_IMAGE → /v1/flow/upsampleImage` |
| 13 | reCAPTCHA token generation | ✅ OK | `grecaptcha.enterprise.execute()` on MAIN world |
| 14 | Token injection vào body | ✅ OK | `body.clientContext.recaptchaContext = rcCtx` |
| 15 | Token minimum validation | ✅ OK | `≥ 1000 chars` (was 500, fixed) |
| **16** | **reCAPTCHA action cho UPSCALE_IMAGE** | **⚠️ NGHI VẤN** | **Xem phân tích bên dưới** |
| 17 | Access token extraction | ✅ OK | `tabState[tabId].accessToken || __NEXT_DATA__` |
| 18 | Fetch timeout cho T2I | ✅ OK | 90s (sync endpoint, server renders images) |
| 19 | MV3 keepalive timer | ✅ OK | `getPlatformInfo()` mỗi 25s |

### 2.4 T2I Pipeline (Download + Upscale)

| # | Kiểm tra | Kết quả | Ghi chú |
|---|----------|---------|---------|
| 20 | Download 1K images | ✅ OK | `_download_outputs()` → 1K/ folder |
| 21 | Upscale decision logic | ✅ OK | Check `has_media_ids && download_quality in (4K,2K)` |
| **22** | **Cooldown check TRƯỚC upscale** | **🔴 BUG** | **Poll-based race condition** |
| **23** | **Upscale 403 → set_account_cooldown** | **🔴 BUG** | **KHÔNG GỌI** |
| **24** | **Upscale 403 → record_circuit_403** | **🔴 BUG** | **KHÔNG GỌI** |
| **25** | **Upscale retry logic** | **🔴 BUG** | **0 retries (fire-and-forget)** |
| **26** | **Log quality accuracy** | **🟡 BUG** | **Báo "4k" khi thực tế 1K** |

### 2.5 UpscaleQueue (Video Upscale — đối chiếu)

| # | Kiểm tra | Kết quả | Ghi chú |
|---|----------|---------|---------|
| 27 | Cooldown check trước submit | ✅ OK | `_wait_cooldown()` x3 (entry, retry, inside lock) |
| 28 | 403 → set_cooldown | ✅ OK | L886: `_set_cooldown(email, "upscale submit 403")` |
| 29 | 403 → record_circuit_403 | ✅ OK | L876-878: `_record_circuit_403(email)` |
| 30 | Retry logic | ✅ OK | `max_submit_retries` (default 3) |
| 31 | reCAPTCHA readiness check | ✅ OK | `_wait_recaptcha_fn(account, max_wait=20)` |
| 32 | Stable seed idempotency | ✅ OK | `sha256(task_id:media_id:attempt)` |
| 33 | Extension disconnect recovery | ✅ OK | Wait reconnection + re-init reCAPTCHA |
| 34 | Browser recovery phases | ✅ OK | Phase 1: gentle → Phase 2: hard restart |

### 2.6 Tab Keepalive — Engine Coordination

| # | Kiểm tra | Kết quả | Ghi chú |
|---|----------|---------|---------|
| 35 | Keepalive paused khi engine processing | ✅ OK | `_keepalive_yield.clear()` |
| 36 | Keepalive resumed khi engine stopped | ✅ OK | `_keepalive_yield.set()` |
| 37 | Engine cooldown keepalive | ✅ OK | `wait_for_cooldown()` ping mỗi 20s |
| 38 | No conflict giữa keepalive + submit | ✅ OK | Mutual exclusion via yield event |
| **39** | **Keepalive coverage cho T2I upscale** | **⚠️ GAP** | **Xem phân tích bên dưới** |

---

## 3. Phân tích chi tiết các BUG phát hiện

### 🔴 BUG 1: T2I Upscale — Race Condition trên Cooldown Check (L2550-2554)

**Code hiện tại:**
```python
# engine.py L2550-2554
_cd_waited = 0
while self.is_account_on_cooldown(account.email) and _cd_waited < 90:
    await asyncio.sleep(2)
    _cd_waited += 2
```

**Vấn đề:**
- Poll-based (sleep 2s → check → sleep 2s) thay vì Event-based
- Race condition: nếu cooldown được set SAU khi check pass, upscale vẫn submit vào cooldown
- Không tôn trọng `_stop_event` → không cancel được trong shutdown

**So sánh UpscaleQueue:**
```python
# upscale_queue.py L548-552
if self._is_on_cooldown(job.account_email):
    await self._wait_cooldown(job.account_email)  # ← Event-based, blocks properly
```

**Impact:** Upscale submit trong cooldown → 403 → token lãng phí, request thất bại không cần thiết.

---

### 🔴 BUG 2: T2I Upscale — 403 Không Trigger Cooldown/Circuit (L2674-2686)

**Code hiện tại:**
```python
# engine.py L2674-2686
else:
    error = ext_result.get('error', 'unknown') if ext_result else 'no response'
    log.warning(f"[T2I-Upscale] {idx+1}/{total}: failed ({error}), keeping 1K")
    upscaled_paths.append(local_1k)
    # ❌ THIẾU: set_account_cooldown()
    # ❌ THIẾU: record_circuit_403()
    # ❌ THIẾU: _burst_controller.record_error()
```

**So sánh UpscaleQueue:**
```python
# upscale_queue.py L871-890
if "recaptcha" in error_lower or is_403:
    if is_403 and self._record_circuit_403:
        self._record_circuit_403(job.account_email)  # ✅
    if is_403:
        self._set_cooldown(job.account_email, "upscale submit 403")  # ✅
        await self._wait_cooldown(job.account_email)  # ✅
```

**Impact:** Hệ thống cooldown và circuit breaker bị "mù" — không biết upscale vừa gặp 403. Upscale tiếp theo submit ngay vào account đang bị rate-limit.

---

### 🔴 BUG 3: T2I Upscale — Zero Retry (L2524-2706)

**Code hiện tại:** Mỗi image upscale chỉ thử 1 lần. Thất bại → giữ 1K ngay.

**So sánh:**

| Component | Retry Count | Recovery |
|-----------|:-----------:|---------|
| Foreman (main submit) | 11 attempts | 4-phase recovery state machine |
| UpscaleQueue (video) | 3 attempts | gentle → hard browser restart |
| **T2I Upscale (image)** | **0 retries** | **Không có** |

**Impact:** Một lần 403 (có thể transient) → mất luôn 4K. Không có cơ hội retry sau khi cooldown.

---

### ⚠️ BUG 4: reCAPTCHA Action cho Image Upscale — Possible Mismatch

**Code hiện tại (background.js L766):**
```javascript
const rcAction = (endpointKey === 'T2I') ? 'IMAGE_GENERATION' : 'VIDEO_GENERATION';
```

**Phân tích:**
- `T2I` (generate images) → `IMAGE_GENERATION` ✅
- `UPSCALE_IMAGE` → **falls through to `VIDEO_GENERATION`** ⚠️
- `UPSCALE_VIDEO` → `VIDEO_GENERATION` ✅ (video upscale đúng)

**Câu hỏi:** Google có phân biệt reCAPTCHA action giữa `IMAGE_GENERATION` và `VIDEO_GENERATION` cho image upscale không?

**HAR validation:** Token trong HAR cho image upscale có `response_status: 200`, nhưng:
- HAR không cho biết action name đã dùng (token opaque)
- Có thể Google chấp nhận cả hai action, HOẶC
- Có thể `VIDEO_GENERATION` là nguyên nhân 403 của image upscale mà chưa ai phát hiện

**Khuyến nghị:** Test thử đổi action cho `UPSCALE_IMAGE` sang `IMAGE_GENERATION`:
```javascript
const rcAction = (endpointKey === 'T2I' || endpointKey === 'UPSCALE_IMAGE') 
    ? 'IMAGE_GENERATION' 
    : 'VIDEO_GENERATION';
```

---

### ⚠️ BUG 5: Keepalive Coverage Gap khi T2I Upscale đang chạy

**Timeline gap:**
```
Foreman submit T2I → pipeline fire-and-forget
│
├── Foreman picks NEXT task → submit
│   └── reCAPTCHA token consumed ✅
│
└── T2I Pipeline (background):
    ├── Download 1K (5-10s) — ổn, nhanh
    └── ★ Upscale loop (10-60s PER IMAGE):
        ├── May be waiting cooldown (90s poll loop)
        ├── Rate lock wait (burst delay 5-8s)
        └── submit → fetch (up to 120s timeout)
```

**Vấn đề:**
- Keepalive service PAUSED (vì engine đang processing)
- Engine cooldown keepalive chỉ ping trong `wait_for_cooldown()` — nhưng T2I upscale dùng poll-based cooldown (L2552), KHÔNG gọi `wait_for_cooldown()` → **KHÔNG có tab keepalive trong cooldown wait**
- Nếu upscale đợi cooldown 90s → tab có thể bị frozen → reCAPTCHA die → upscale thất bại

**So sánh:** UpscaleQueue gọi `self._wait_cooldown()` = `engine.wait_for_cooldown()` → có tab keepalive ✅

---

### 🟡 BUG 6: Log Quality Misleading (L2733-2737)

```python
log.info(
    f"[T2I-Pipeline] Task {task.id}: ✅ DONE "
    f"({len(task.output_uris)} files, "
    f"quality={upscale_quality})"  # ← Luôn hiển thị quality từ setting
)
```

**Vấn đề:** `upscale_quality` là DESIRED quality (từ settings), không phải ACTUAL quality. Khi upscale 403 → file thực tế là 1K, nhưng log nói "quality=4k".

---

### 🟡 BUG 7: T2I Upscale sử dụng `submit_prompt()` thay vì `submit_upscale()`

**Engine T2I upscale (L2606):**
```python
ext_bridge.submit_prompt(
    endpoint="UPSCALE_IMAGE",  # ← Generic submit_prompt, serialized by reCAPTCHA lock
)
```

**UpscaleQueue video upscale (L808):**
```python
ext_bridge.submit_upscale(
    email=account.email, body=upscale_body  # ← Dedicated method, no global lock
)
```

**Khác biệt quan trọng:**
- `submit_prompt()` (L548): **dùng `_recaptcha_locks[email]`** → serialize TẤT CẢ submissions cho account (bao gồm task mới) → upscale phải CHỜI main task submit xong
- `submit_upscale()` (L609): **KHÔNG dùng lock** → independent, nhưng có thể conflict với `submit_prompt` nếu chạy đồng thời

**Impact:** T2I upscale bị bottleneck bởi main task submission lock. Nếu Foreman đang submit task mới, upscale phải chờ. Nhưng `submit_upscale()` CŨNG có vấn đề — không serialize → có thể chạy concurrent với submit_prompt. Cần xem xét nên dùng cái nào.

---

### 🟢 BUG 8: submit_upscale() bypass reCAPTCHA pre-warm

**`submit_upscale()` (L609-672):**
- Không gọi `simulate_activity()` trước khi submit (unlike `submit_prompt()` L534-542)
- Không check tab idle time
- Nếu tab idle > 60s → grecaptcha có thể đã frozen → 538-char token

**`submit_prompt()` (L534-542):**
```python
# Pre-warm: simulate activity if tab idle > 60s
if last_hb and (time.time() - last_hb) > 60:
    await self.simulate_activity(email, timeout=3.0)
    await asyncio.sleep(0.5)
```

---

## 4. Ma trận so sánh: T2I Pipeline vs UpscaleQueue vs Foreman

| Feature | Foreman (Submit) | UpscaleQueue (Video) | T2I Pipeline (Image) |
|---------|:-:|:-:|:-:|
| **Cooldown check** | ✅ Event-based | ✅ `_wait_cooldown()` x3 | ❌ Poll + race condition |
| **403 → set_cooldown** | ✅ L2045 | ✅ L886 | ❌ Missing |
| **403 → circuit_403** | ✅ L2040 | ✅ L876 | ❌ Missing |
| **403 → burst_backoff** | ✅ L2037 | ✅ adaptive | ❌ Missing |
| **Retry count** | 11 | 3 | **0** |
| **Recovery phases** | 4 phases | 2 phases | **None** |
| **reCAPTCHA readiness** | ✅ pre-warm gate | ✅ `_wait_recaptcha_fn` | ❌ None |
| **Tab keepalive in cooldown** | ✅ `wait_for_cooldown()` | ✅ `_wait_cooldown()` | ❌ Poll-based, no keepalive |
| **Pre-warm activity** | ✅ `simulate_activity()` | ❌ (uses `submit_upscale`) | ✅ (uses `submit_prompt`) |
| **Extension method** | `submit_prompt()` | `submit_upscale()` | `submit_prompt()` |
| **reCAPTCHA action** | Correct per endpoint | `VIDEO_GENERATION` | Possibly wrong |
| **Idempotent seed** | ❌ Not needed | ✅ `sha256(task:media:attempt)` | ❌ Not needed |

---

## 5. Root Cause Hierarchy

```
WHY: Tại sao T2I Upscale luôn thất bại khi có 403?
│
├── CAUSE 1: T2I upscale KHÔNG tham gia hệ thống cooldown/recovery
│   ├── Không gọi set_account_cooldown() → requests sau không biết account bị rate-limited
│   ├── Không gọi record_circuit_403() → circuit breaker counter sai
│   └── Không retry → 1 lần 403 = mất 4K permanently
│
├── CAUSE 2: Race condition trên cooldown check
│   ├── Poll-based (sleep 2s loop) → window 2s mà cooldown có thể set
│   ├── Foreman submit 403 → set_cooldown → nhưng upscale đã pass check → submit → 403 lần nữa
│   └── Không dùng Event-based wait → không blocking properly
│
├── CAUSE 3: Keepalive gap trong cooldown wait
│   ├── T2I upscale poll cooldown (L2552-2554) → sleep 2s → KHÔNG ping tab
│   ├── Tab có thể freeze trong 90s poll loop → reCAPTCHA die
│   └── Khi submit sau cooldown → 538-char token → 403 → vòng lặp
│
└── POSSIBLE CAUSE 4: reCAPTCHA action sai cho UPSCALE_IMAGE
    ├── IMAGE_GENERATION chỉ match T2I endpoint
    ├── UPSCALE_IMAGE → VIDEO_GENERATION (có thể sai)
    └── Cần HAR verify: browser thật dùng action nào cho image upscale?
```

---

## 6. Kết luận

### ✅ Những gì ĐÚNG:

1. **Foreman pipeline architecture** — submit tuần tự, pipeline song song → đúng design
2. **Extension Bridge communication** — WebSocket → chrome.scripting.executeScript → fetch → đầy đủ
3. **Endpoint mapping** — tất cả 8 endpoints map đúng URL
4. **Body format** — HAR khớp 100% (đã verify ở UPSCALE_403_ANALYSIS)
5. **Tab Keepalive** — mutual exclusion, coverage 100% (trừ T2I upscale gap)
6. **UpscaleQueue** — video upscale có đầy đủ cooldown + circuit + retry + recovery
7. **reCAPTCHA token generation** — site key extraction + action mapping + validation ≥1000 chars

### ❌ Những gì SAI — T2I Image Upscale là "weak link":

T2I image upscale pipeline (`_run_t2i_pipeline_bg`, L2524-2706) được code như một "afterthought" — fire-and-forget, zero retry, nhưng:
1. **Nó gọi API CẦN reCAPTCHA** (HAR confirmed)
2. **Nó chạy CONCURRENT với Foreman** (có thể conflict trên cùng account)
3. **Nó KHÔNG tham gia hệ thống cooldown/circuit** (UpscaleQueue thì có)

→ **T2I image upscale cần được nâng cấp lên cùng level protection với UpscaleQueue.**

### 📋 Priority fix order:

| Priority | Fix | Effort | Impact |
|:--------:|-----|:------:|:------:|
| **P0** | T2I upscale 403 → trigger cooldown + circuit | Small | Stops cascade failures |
| **P0** | T2I upscale cooldown → Event-based wait | Small | Fixes race condition |
| **P1** | T2I upscale retry (1-2 lần) | Medium | Recovers from transient 403 |
| **P1** | reCAPTCHA action audit cho UPSCALE_IMAGE | Small | May fix root cause of 403 |
| **P2** | Log quality accuracy | Small | UX improvement |
| **P2** | submit_upscale() pre-warm activity | Small | Defence-in-depth |
