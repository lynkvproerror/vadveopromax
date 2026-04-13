# Retry-Until-Done Hardening Report

Ngày: 2026-04-12

## Mục tiêu

Làm rõ vì sao hệ thống hiện tại vẫn xuất hiện `FAIL`, dù kỳ vọng là:

- không task nào bị đánh dấu fail khi lỗi còn recover được
- mọi lỗi transient phải tiếp tục retry cho đến khi hoàn thành
- trạng thái hiển thị phải phản ánh đúng tiến trình thực, không báo `FAIL` sớm
- không được làm mất stage/checkpoint đúng của công việc

Báo cáo này chỉ phân tích kiến trúc và hướng xử lý. Không có thay đổi code runtime trong tài liệu này.

## Kết luận ngắn

Hệ thống hiện tại chưa phải `retry until done`. Nó đang là `auto-retry hữu hạn` ở nhiều lớp khác nhau.

Có 4 nguyên nhân gốc:

1. Có nhiều vòng retry độc lập, mỗi vòng có quota riêng, nên task có thể hết retry ở một lớp dù lớp khác vẫn còn khả năng cứu.
2. Một số nhánh set `quality='failed'` hoặc `upscale_status='failed'` quá sớm, trong khi về mặt nghiệp vụ output đó vẫn còn recover được.
3. UI đang coi `video_output.quality == 'failed'` hoặc `upscale_status == 'failed'` là `FAIL`, kể cả khi `task.state` chưa phải `FAILED`.
4. Retry transient của video generation vẫn đi qua mô hình `replacement task`, làm phân mảnh lifecycle của một công việc duy nhất thành nhiều task con khác nhau.

Vì vậy:

- footer có thể vẫn là `Failed: 0`
- nhưng từng hàng trong queue vẫn hiện `FAIL`
- và sau một số vòng retry hữu hạn, hệ thống dừng auto-retry dù output chưa hoàn thành

## Bằng chứng từ log `dev_logs_20260412_100620.txt`

### 1. Video generation timeout chỉ retry hữu hạn

Trong log có nhiều lần:

- `Op FAILED: INTERNAL`
- ngay sau đó là `SERVER TIMEOUT -> auto-retry #1/2`
- hoặc `SERVER TIMEOUT -> auto-retry #2/2`

Điều này khớp với `core/engine.py:5497-5501`, nơi timeout retry chỉ được phép tối đa `2` lần.

Sau khi hết quota này, code rơi xuống:

- `core/engine.py:5544-5548` -> set `quality="failed"`

### 2. On-the-fly sweep cũng có trần cứng

Log ghi rõ:

- `Round 1/5`
- `Round 2/5`
- `Round 3/5`
- `Round 4/5`
- `Round 5/5`
- sau đó là `Max 5 rounds exhausted — no more auto-retry`

Điều này khớp với:

- `config/settings.py:146` -> `auto_sweep_max_rounds = 5`
- `core/app_controller.py:4881` -> dừng hẳn auto-retry sau khi hết số vòng

Nói cách khác: hệ thống hiện tại tự dừng cơ chế "vá lỗi nền" sau 5 vòng, nên không thể coi là retry đến khi xong.

### 3. Upscale queue vẫn có terminal failure

Video upscale hiện có:

- normal retry hữu hạn: `core/upscale_queue.py:1754-1777`
- durable retry hữu hạn: `core/upscale_queue.py:1779-1809`
- hết toàn bộ retry thì:
  - `core/upscale_queue.py:1811-1817` -> set `upscale_status="failed"`
  - `core/upscale_queue.py:1825` -> cập nhật progress kiểu `Upscale failed — 720p saved`

Điều này giải thích vì sao task tổng có thể không fail hoàn toàn, nhưng hàng vẫn hiện `FAIL`.

### 4. Một số hàng `FAIL` trong ảnh thực ra chỉ là trạng thái tạm thời giữa phiên

Ngay trong log session này:

- `task_40` về sau `COMPLETED`
- `task_41` về sau `COMPLETED`
- `task_42` về sau `COMPLETED`

Nghĩa là tại thời điểm chụp ảnh, UI đang hiển thị output-level failure tạm thời. Một phần trong số đó đã được cứu lại sau đó.

## Vì sao UI hiện `FAIL` dù `Failed: 0`

Đây không phải bug đếm số đơn thuần. Nó là khác biệt giữa `task-level state` và `output-level state`.

### Task-level

Footer `Failed` tăng khi `Dispatcher.fail_task()` được gọi:

- `core/dispatcher.py:1124`

### Output-level

Renderer lại coi task là fail nếu bất kỳ output nào có:

- `quality == 'failed'`
- hoặc `upscale_status == 'failed'`

Các điểm chính:

- `ui/tabs/queue_components/group_renderer.py:131-133`
- `ui/tabs/queue_components/group_renderer.py:174`
- `ui/tabs/queue_components/group_renderer.py:1114-1116`
- `core/queue_controller.py:97-108`

Hệ quả:

- task có thể vẫn là `COMPLETED`
- footer vẫn báo `Failed: 0`
- nhưng row vẫn bị tô `FAIL`

Điều này hiện tại là hành vi có chủ đích của UI.

## Các vòng lặp retry hiện tại và vấn đề của từng vòng

### Vòng 1: worker timeout retry bằng replacement task

Đường chính:

- `core/engine.py:5495-5534`
- `core/dispatcher.py:2213-2249`

Hành vi hiện tại:

- poll lỗi retryable -> tạo replacement task mới
- parent task giữ slot cũ
- replacement task chạy như một task độc lập

Vấn đề:

- mất continuity của một công việc duy nhất
- task cũ và task mới có lifecycle khác nhau
- UI dễ hiện `FAIL`, `RETRYING`, `COMPLETED` không đồng bộ
- phát sinh nhiều reserve/retry spam

### Vòng 2: finalizer transient retry

Đường chính:

- `core/engine.py:6033-6057`

Hành vi hiện tại:

- nếu tất cả ops failed và bị xem là transient
- sleep một khoảng thời gian
- reset task rồi requeue
- tối đa `3` lần

Vấn đề:

- vẫn là retry hữu hạn
- sleep inline giữ coroutine sống lâu
- nếu đã có replacement task ở vòng 1 thì vòng 2 chồng lên vòng 1

### Vòng 3: OTF sweep

Đường chính:

- `core/app_controller.py:4917-5031`

Hành vi hiện tại:

- quét theo vòng
- retry failed tasks
- retry failed video slots
- re-upscale failed upscales
- re-gen missing media

Vấn đề:

- không stage-aware thật sự
- là lớp "quét" ngoài, không phải lifecycle chính
- bị trần `5` vòng
- dễ tạo cảm giác "lúc retry, lúc bỏ"

### Vòng 4: Upscale queue retry

Đường chính:

- `core/upscale_queue.py:1754-1809`

Hành vi hiện tại:

- retry submit/poll/download theo job
- sau đó durable retry
- sau cùng set `upscale_status='failed'`

Vấn đề:

- vẫn hữu hạn
- còn ghi trạng thái fail terminal khá sớm theo góc nhìn UI

## Điều cần loại bỏ trước

Nếu mục tiêu là `recover until done`, cần loại bỏ vai trò "driver chính" của các vòng sau:

### 1. Loại bỏ OTF sweep khỏi vai trò auto-retry chính khi engine đang chạy

Không nhất thiết phải xóa code ngay, nhưng phải hạ nó xuống vai trò:

- watchdog repair
- maintenance sweep
- fallback cuối

Không dùng nó như cơ chế chính để cứu task/output.

Lý do:

- sweep không giữ đúng stage nội tại
- sweep bị quota cứng
- sweep gây lệch trạng thái hiển thị

### 2. Loại bỏ retry bằng replacement task cho lỗi transient generation

Không dùng `force_retry_video()` làm đường auto-retry mặc định cho timeout/internal transient.

Giữ lại replacement task chỉ cho:

- manual retry
- slot replacement có chủ đích
- repair những trường hợp parent-child chain thực sự cần tách task

Lý do:

- replacement task làm mất identity của công việc gốc
- gây phân mảnh state
- làm tăng duplicate reserve/requeue noise

### 3. Loại bỏ inline sleep trong retry path

Không để:

- worker sleep chờ retry
- finalizer sleep chờ retry
- queue worker sleep dài để giữ flow

Thay vào đó:

- dùng `retry_after`
- delayed requeue
- stage checkpoint giữ nguyên

Lý do:

- không block pipeline
- không giữ coroutine sống vô ích
- dễ resume, persist, watchdog và UI hơn

## Điều không nên làm nữa

### Không set `failed` khi lỗi còn recover được

Các trạng thái sau đang bị set quá sớm:

- `core/engine.py:5545` -> `quality="failed"`
- `core/engine.py:5577` -> `quality="failed"`
- `core/upscale_queue.py:1816` -> `upscale_status="failed"`

Nếu output vẫn còn retry budget nghiệp vụ, các trạng thái đúng phải là:

- `retrying`
- `recovering`
- `pending_retry`
- `waiting_download_retry`
- `waiting_upscale_retry`

Chỉ set `failed` khi đã xác nhận là terminal.

## Mô hình đúng hơn: Stage-Level Recovery

### Nguyên tắc

Một task giữ nguyên:

- `task.id`
- `video_index`
- `stage checkpoint`

Không sinh task mới cho lỗi transient.

### Mỗi output phải có stage recovery riêng

Ví dụ:

- `submit`
- `poll_generation`
- `download_720`
- `submit_upscale`
- `poll_upscale`
- `download_upscale`

Mỗi stage có metadata riêng:

- `stage_retry_count`
- `stage_retry_after`
- `last_error`
- `last_error_kind`
- `last_attempt_at`
- `terminal_reason`

### Trạng thái gợi ý

Không dùng `failed` cho retryable state.

Nên có:

- `recovering_submit`
- `recovering_poll`
- `recovering_download_720`
- `recovering_upscale_submit`
- `recovering_upscale_poll`
- `recovering_upscale_download`
- `terminal_policy`
- `terminal_manual_stop`
- `terminal_input_invalid`

## Quy tắc phân loại lỗi

### Retry vô hạn có kiểm soát

Áp cho:

- timeout
- `INTERNAL`
- disconnect
- reCAPTCHA cold/not ready
- bridge unavailable tạm thời
- download transient
- poll miss/transient backend error

### Không retry vô hạn

Áp cho:

- policy violation không sửa được
- input invalid thực sự
- missing local file không thể phục hồi
- user cancelled
- license/tier cứng không đạt

Các lỗi này mới là terminal thật.

## UI nên đổi gì

### 1. `FAIL` chỉ dành cho terminal fail

UI không nên tô `FAIL` chỉ vì `quality='failed'` hoặc `upscale_status='failed'` nếu output vẫn còn auto-recovery active hoặc còn retry budget nghiệp vụ.

### 2. Hiện trạng thái recovering rõ ràng

Ví dụ:

- `Recovering submit`
- `Retrying poll`
- `Retrying 720p download`
- `Retrying 1080p upscale`

### 3. Footer phải phân biệt

- `Failed`: terminal failed task
- `Recovering`: task/output đang auto-retry
- `Partial`: task completed nhưng còn output chưa terminal

## Hướng triển khai triệt để

### P1. Dừng set output-level fail sớm

Đổi mọi nhánh retryable đang set:

- `quality='failed'`
- `upscale_status='failed'`

thành trạng thái recovering/pending retry.

### P2. Thay replacement-task retry bằng stage requeue

Timeout/internal của video generation:

- không tạo task mới
- giữ nguyên task gốc
- giữ nguyên `video_index`
- chuyển slot về `recovering_submit` hoặc `recovering_poll`

### P3. Tắt OTF sweep như auto-driver trong lúc engine chạy

Cho phép giữ lại như:

- startup repair
- idle maintenance
- manual command

Không để nó quyết định lifecycle chính nữa.

### P4. Mọi retry dài phải dùng `retry_after`, không `sleep`

Điều này áp cho:

- engine worker retry
- finalizer transient retry
- upscale queue retry

### P5. UI chỉ hiển thị `FAIL` khi terminal

Đây là điều kiện bắt buộc nếu muốn người dùng không thấy fail giả.

## Tóm tắt các giới hạn cứng hiện tại cần bỏ hoặc đổi

- `worker timeout retry max = 2` tại `core/engine.py:5497-5501`
- `finalizer transient retry max = 3` tại `core/engine.py:6035-6038`
- `OTF sweep max rounds = 5` tại `config/settings.py:146`
- `upscale retry max + durable max` tại `core/upscale_queue.py:1754-1809`

Các giới hạn này là lý do trực tiếp khiến hệ thống hiện tại không thể đạt mục tiêu `retry cho đến khi hoàn thành 100%`.

## Kết luận cuối

Muốn xử lý triệt để, cần đổi triết lý retry:

- từ `nhiều vòng auto-retry hữu hạn`
- sang `một lifecycle recovery duy nhất theo stage`

Trong mô hình mới:

- không tạo replacement task cho transient error
- không set `failed` khi còn recover được
- không dùng sweep theo vòng làm driver chính
- không sleep inline trong retry path
- UI chỉ hiển thị `FAIL` khi thật sự terminal

Đó là điều kiện cần để hệ thống tiến tới đúng mục tiêu:

- retry đến khi xong
- không block vô ích
- không sai trạng thái
- không mất checkpoint đúng của công việc

---

## Phụ lục: Trạng thái triển khai v5.2 (2026-04-12)

### Đã triển khai — 5 fix cụ thể

#### Fix 1: Watchdog không requeue task đang upscale (`task_watchdog.py`)

**Mapping:** Liên quan log `task_54 requeued at 925s` — watchdog timeout.

**Gốc rễ:** `TaskWatchdog._scan_loop` skip `UPSCALING`/`UPSCALED` stage, nhưng finalizer đặt `_counter_decremented=True` trước khi UpscaleQueue đổi stage. Cửa sổ race: task ở RUNNING + `_counter_decremented=True` → watchdog coi là stuck → requeue về READY.

**Fix:** Thêm guard `_counter_decremented` — bất kỳ task nào đã bàn giao cho UpscaleQueue đều exempt khỏi timeout.

**Kết quả:** Task upscale không bị kéo ngược về READY nữa.

#### Fix 2: Normalize `upscale_status` khi hoàn thành (`dispatcher.py`)

**Mapping:** Mục "Vì sao UI hiện FAIL dù Failed: 0" — stale `upscale_status='failed'`.

**Gốc rễ:** `complete_task()` set `COMPLETED` nhưng không kiểm tra `upscale_status`. Nếu retry upscale thành công (file_upscaled tồn tại) nhưng status cũ vẫn là `failed`, UI hiện FAIL.

**Fix:** Trong `complete_task()`, nếu `vo.file_upscaled` tồn tại mà `upscale_status='failed'`, tự động normalize sang `success`.

**Kết quả:** UI không hiện FAIL cho task đã có file upscale thành công.

**Giới hạn:** Chỉ fix tại thời điểm `complete_task()`. Nếu upscale fail SAU khi complete, vẫn cần sweep hoặc manual retry. Đây là tactical fix, chưa phải P5 triệt để (UI semantic overhaul).

#### Fix 3: OTF Phase 3 skip khi file đã tồn tại (`app_controller.py`)

**Mapping:** Mục P3 — OTF sweep re-upscale sai.

**Gốc rễ:** Phase 3 check `upscale_status='failed'` → trigger re-upscale, nhưng không check `file_upscaled`. Task đã có file 1080p nhưng status cũ → trigger vô ích → vòng lặp.

**Fix:** Skip re-upscale nếu `vo.file_upscaled` đã tồn tại.

**Kết quả:** OTF sweep không re-upscale task đã hoàn thành. Giảm noise trong log và giảm tải UpscaleQueue.

**Giới hạn:** OTF sweep vẫn giữ vai trò auto-driver (round limit=5). Chưa hạ vai trò xuống maintenance như P3 đề xuất.

#### Fix 4: UpscaleQueue drop job cho task đã COMPLETED (`upscale_queue.py`)

**Mapping:** Mục "upscale queue retry" — stale job re-enqueue.

**Gốc rễ:** OTF enqueue job cho task đã COMPLETED → UpscaleQueue process → ghi log lỗi → re-enqueue → duplicate cycle.

**Fix:** Early-exit guard: nếu `task.state == COMPLETED`, drop job ngay.

**Kết quả:** Không còn stale upscale job chạy cho task đã hoàn thành.

#### Fix 5: Remedy escalation tracker (`remedy_registry.py`)

**Mapping:** Vòng lặp refresh trình duyệt liên tục — gốc rễ của bug reCAPTCHA cold-start.

**Gốc rễ (chi tiết):**

```
Submit → reCAPTCHA evaluation failed
→ classify → recaptcha_timeout
→ RECAPTCHA_TIMEOUT chain starts at remedy 1/5: soft_recovery
→ soft_recovery: navigate away → back → widget ready
→ health check (skip_probe=True): only checks extension + recaptcha_ready
→ recaptcha_ready passes (widget loaded, trial token OK)
→ health reports HEALTHY → recovery returns success=True
→ remedy index RESETS
→ next submit fails with same error
→ chain starts at remedy 1/5 again → INFINITE LOOP
```

`soft_recovery` nằm trong `_skip_probe_remedies` nên health check không validate token thực sự. Widget report ready nhưng server vẫn reject token.

**Fix:** Thêm `_remedy_escalation` tracker:
- Lưu `{email: {error_type, remedy_idx, ts}}`
- Nếu cùng error_type xảy ra lại cho cùng email trong 180s, bắt đầu từ `remedy_idx + 1`
- Escalation flow mới:

```
Fail #1 → remedy 1 (soft_recovery) → "healthy" → resume
Fail #2 → escalate → remedy 2 (simulate_activity) → check
Fail #3 → escalate → remedy 3 (reload_tab) → check
Fail #4 → escalate → remedy 4 (soft_recovery 15s) → check
Fail #5 → escalate → remedy 5 (hard_restart) → Chrome killed + relaunch
```

**Kết quả:** Không còn vòng lặp `soft_recovery` vô hạn. Hệ thống escalate tự động đến `hard_restart` sau ~4 vòng fail liên tục.

---

### Trạng thái kế hoạch P1–P5 sau v5.2

| Hạng mục | Trạng thái | Ghi chú |
|----------|-----------|--------|
| P1: Dừng set output-level fail sớm | ⚠️ Tactical fix | Fix 2 normalize `upscale_status` tại `complete_task()`. Chưa đổi các nhánh gốc (`quality='failed'` tại engine.py:5545, 5577). Cần refactor sang `recovering` state. |
| P2: Thay replacement-task retry | ❌ Chưa bắt đầu | Vẫn dùng `force_retry_video()` cho transient timeout. Đây là redesign lớn nhất. |
| P3: Hạ vai trò OTF sweep | ⚠️ Giảm thiểu | Fix 3 loại bỏ false positive re-upscale. OTF vẫn là auto-driver (round limit=5). |
| P4: Retry dùng `retry_after`, không `sleep` | ❌ Chưa bắt đầu | Finalizer vẫn `sleep` inline. |
| P5: UI chỉ hiện FAIL khi terminal | ⚠️ Tactical fix | Fix 2 normalize status. Chưa đổi renderer logic (`group_renderer.py`). |

### Vấn đề mới phát hiện (không có trong kế hoạch gốc)

#### Dispatcher reserve race: `task_12` reserved nhiều lần

Trong log 19:30, `task_12` bị `READY → RESERVED` lặp lại >15 lần trong vài giây. Nhiều foremen đồng thời reserve cùng task → dispatcher không mutual-exclude đúng.

**Nguyên nhân giả thuyết:** `reserve_task()` check `task.state == READY` nhưng không atomic transition. Nhiều coroutine qua gate cùng lúc.

**Ảnh hưởng:** Log noise, running_count không chính xác (luôn hiện =13 dù không tăng thật).

**Khuyến nghị:** Investigate `dispatcher.reserve_task()` — có thể cần lock hoặc CAS pattern.

#### CreditWindow giảm credits quá nhanh trong cold-start

Trong 2 phút đầu: credits giảm từ 10→5 (cost=2 mỗi lần) dù đây chỉ là cold-start reCAPTCHA trust issue, không phải lỗi account thực sự.

**Ảnh hưởng:** Nếu có thêm vài fail nữa, account bị suspend → tất cả task migrate → downtime không cần thiết.

**Khuyến nghị:** reCAPTCHA cold-start failures nên có credit cost=0 hoặc =1 (hiện tại cost=2 theo `ERROR_CREDIT_COST[RECAPTCHA_TIMEOUT]`).
