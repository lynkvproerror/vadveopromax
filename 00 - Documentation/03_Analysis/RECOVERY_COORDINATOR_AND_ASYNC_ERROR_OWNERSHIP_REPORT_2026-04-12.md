# Recovery Coordinator And Async Error Ownership Report

Ngày: 2026-04-12  
Phạm vi: `02 - CLIENT - VEO PRO MAX`  
Trạng thái: Báo cáo phân tích và đề xuất kiến trúc, chưa áp dụng patch trong tài liệu này.

## 1. Mục tiêu báo cáo

Báo cáo này tổng hợp các vấn đề đã quan sát được trong các log gần nhất và đưa ra một hướng xử lý kiến trúc rõ ràng để:

- chấm dứt tình trạng nhiều module cùng sửa state và cùng retry cho một task
- tránh việc reload/tab refresh/restart browser của một account làm nhiễu các task khác đang chạy chung browser
- tách rõ quyền sở hữu giữa `generation retry`, `upscale retry`, `browser recovery`, `watchdog`, và `UI`
- xác định kết quả cần đạt trước khi tiếp tục mở rộng phần UI semantics

## 2. Kết luận điều hành

Vấn đề cốt lõi hiện tại không phải vì `engine.py` quá dài, mà vì hệ thống đang có quá nhiều nơi cùng sở hữu quyền xử lý lỗi cho cùng một account và cùng một task.

Trong kiến trúc hiện tại, một task có thể lần lượt hoặc đồng thời bị đụng bởi:

- `engine.py`: worker, finalizer, replacement-task, supervisor gate
- `upscale_queue.py`: retry, durable retry, background completion
- `task_watchdog.py`: phát hiện timeout và tự requeue
- `app_controller.py`: OTF sweep, re-upscale, force retry, browser restart
- `remedy_registry.py`: reload/restart remedies
- `group_renderer.py`: diễn giải fail từ state/video_outputs/upscale_status

Với thực tế mỗi account chỉ có một browser/tab context dùng chung, mô hình này tạo ra xung đột ownership:

- một nơi vừa handoff task sang background owner
- nơi khác lại tưởng task bị kẹt và kéo task về `READY`
- một nơi đã có file `1080p`
- nơi khác vẫn giữ `upscale_status='failed'`
- UI nhìn state cục bộ và tiếp tục hiện `FAIL`

Kết luận kiến trúc:

- Có thể tách logic xử lý lỗi ra khỏi `engine.py`
- Nhưng không nên tạo một `error_manager` chung chung
- Nên tạo một `Account Recovery Coordinator` chuyên xử lý lỗi cấp browser/account
- Mỗi stage vẫn phải có đúng một retry owner cho task state

## 3. Log và evidence đã dùng

Các log chính:

- `logs/dev_logs_20260412_105232.txt`
- `logs/dev_logs_20260412_174342.txt`
- `logs/dev_logs_20260412_175845.txt`
- `logs/dev_logs_20260412_191033.txt`

Các file code đối chiếu:

- `core/engine.py`
- `core/upscale_queue.py`
- `core/task_watchdog.py`
- `core/app_controller.py`
- `core/dispatcher.py`
- `core/remedy_registry.py`
- `ui/tabs/queue_components/group_renderer.py`

## 4. Vấn đề hiện tại

### 4.1 Task upscale bị kéo về `READY`

Triệu chứng trên UI:

- row đang ở `Upscale 0/1`, `Resuming upscale`, hoặc đang có checkpoint `downloaded_720`
- sau đó quay lại `READY`
- tiếp theo worker lại pick lại task và resume từ checkpoint

Evidence:

- watchdog timeout rồi requeue tại `core/task_watchdog.py:239`
- `dispatcher.requeue_task()` ép `task.state = READY` tại `core/dispatcher.py:2172`
- finalizer trước đó đã handoff sang UpscaleQueue tại `core/engine.py:6223`
- log `dev_logs_20260412_191033.txt` cho thấy rõ chuỗi:
  - `task_54` defer sang UpscaleQueue ở dòng `6454`
  - watchdog requeue ở dòng `11279`
  - worker pick lại với trạng thái `running/downloaded_720` ở dòng `11436`
  - resume từ checkpoint ở dòng `11437`

Ý nghĩa:

- owner thực của task đã chuyển từ worker sang `UpscaleQueue`
- nhưng watchdog vẫn xử lý task đó như owner cũ chưa nhả quyền
- đây là xung đột ownership, không phải chỉ là vấn đề UI

### 4.2 Row vẫn hiện `FAIL` dù task đã `COMPLETED`

Triệu chứng:

- task có file `1080p`
- dispatcher đã `COMPLETED`
- nhưng row vẫn hiện `FAIL`

Evidence:

- UI coi `quality == 'failed'` hoặc `vo_upscale == 'failed'` là failed output tại `ui/tabs/queue_components/group_renderer.py:131`
- UI tiếp tục coi `upscale_status == 'failed'` là fail tổng tại `ui/tabs/queue_components/group_renderer.py:174`
- nhánh render `⚠️ FAIL` nằm tại `ui/tabs/queue_components/group_renderer.py:1103`
- log `dev_logs_20260412_191033.txt` cho thấy:
  - `task_55` đã `COMPLETED` ở dòng `12607`
  - nhưng state diagnostic lúc OTF quét lại cho thấy `quality='1080p', upscale_status='failed', file_upscaled=True` ở dòng `16094`
  - `task_56` có pattern tương tự ở dòng `16100`

Ý nghĩa:

- backend output đã terminal thành công
- nhưng status per-video bị stale
- UI phản ánh stale status, không phản ánh terminal artifact thực tế

### 4.3 OTF Phase 3 quét re-upscale lặp lại trên task đã terminal

Evidence:

- OTF phase 3 nằm tại `core/app_controller.py:4942`
- logic hiện tại vẫn coi `vo.upscale_status == 'failed'` là cần re-upscale, dù file upscaled có thể đã tồn tại
- `engine.re_upscale_task(..., failed_only=True)` lại lọc theo `not vo.file_upscaled` tại `core/engine.py:10045`
- kết quả là OTF gọi `re_upscale_task()`, nhưng `failed_indices=[]`, nên chỉ tạo no-op loop

Log minh họa:

- `task_55`:
  - OTF bắt đầu `ReUpscale` ở dòng `16092`
  - diagnostic state ở `16094`
  - `failed_indices=[]` ở `16095`
  - `no videos to upscale` ở `16096`

Ý nghĩa:

- OTF đang retry dựa trên semantic cũ
- `engine.re_upscale_task()` lại dùng semantic khác
- hai nơi nhìn cùng một state nhưng kết luận khác nhau

### 4.4 `watchdog` đang sở hữu cả recovery của stage không thuộc nó

Vai trò đáng ra của watchdog:

- phát hiện liveness issue
- phát tín hiệu recovery
- audit counter

Vai trò hiện tại:

- phát hiện timeout
- tự gọi `requeue_task(task)`
- đổi task về `READY`
- đánh thức foremen

Evidence:

- `core/task_watchdog.py:239` gọi `self._dispatcher.requeue_task(task)` trực tiếp
- `core/dispatcher.py:2219` nếu `notify=True` sẽ gọi `_on_task_ready`
- điều này dẫn tới wake-up và re-pick hàng loạt

Hệ quả:

- watchdog không chỉ quan sát
- watchdog đang mutate task lifecycle của stage upscale
- đây là nguyên nhân trực tiếp của các row “nhảy về READY”

### 4.5 Một account có một browser nhưng recovery đang bị xử lý như task-scoped

Evidence trong code:

- browser/account recovery nằm rải ở:
  - `core/account_manager.py:633` `restart_browser`
  - `core/app_controller.py:1188` `_on_tab_dead`
  - `core/app_controller.py:1935` `restart_browser_for`
  - `core/remedy_registry.py:252` restart browser remedy
  - `core/engine.py:8786` tới `core/engine.py:8909` reCAPTCHA recovery, reload, hard nav

Ý nghĩa:

- refresh/reload/restart là thao tác trên browser dùng chung của account
- khi một task gây ra reload browser, toàn bộ task khác gắn vào browser đó đều bị ảnh hưởng
- nên mọi quyết định loại này phải là account-scoped, không thể để từng stage/task tự quyết

### 4.6 `upscale_status` terminal semantics đang không thống nhất

Evidence:

- có nơi set `upscale_status = "completed"` tại `core/upscale_queue.py:1700`
- có nơi set `upscale_status = "success"` tại `core/upscale_queue.py:1937`, `1957`, `2049`, `2340`, `2961`
- UI hiện chủ yếu hiểu `failed`, `polling`, `submitting`, `success`; không có contract đầy đủ cho `completed`

Ý nghĩa:

- ngay cả khi flow kỹ thuật chạy xong, status vocabulary chưa thống nhất cũng tạo ra sai lệch hiển thị

### 4.7 Vẫn còn fail backend thật

Không phải mọi `FAILED` đều là UI mismatch.

Evidence:

- `task_61` fail thật nhiều lần với `PUBLIC_ERROR_VIDEO_GENERATION_TIMED_OUT`
- log tại:
  - `16317`
  - `16831`
  - `17813`
  trong `dev_logs_20260412_191033.txt`

Ý nghĩa:

- cần tách rõ:
  - fail thật do backend/server
  - fail giả do stale state / conflict owner / UI semantics

## 5. Nguyên nhân gốc

Nguyên nhân gốc không phải một bug đơn lẻ.

Nó là tổ hợp của bốn vấn đề kiến trúc:

### 5.1 Thiếu nguyên tắc `1 Stage = 1 Owner`

Hiện tại nhiều module cùng có quyền:

- retry
- requeue
- đổi `task.state`
- đổi `video_output.quality`
- đổi `video_output.upscale_status`
- reload browser
- restart browser

Khi các quyền này chồng nhau, async flow sẽ không ổn định.

### 5.2 Browser recovery và task recovery đang bị trộn vào nhau

Ví dụ:

- lỗi reCAPTCHA là lỗi browser/account
- nhưng worker, OTF, watchdog, AppController đều có thể tham gia recovery
- hậu quả là cùng một lỗi làm kích hoạt nhiều path remediation không đồng bộ

### 5.3 Background ownership chưa được biểu diễn rõ trong task model

Sau khi finalizer handoff sang `UpscaleQueue`, task vẫn là object cũ trong dispatcher/watchdog.

Nhưng hiện không có một tín hiệu ownership cứng kiểu:

- `task.recovery_owner = UPSCALE_QUEUE`
- hoặc `task.background_owner = UPSCALE`
- hoặc `task.watchdog_exempt = True`

Nên watchdog vẫn coi task đó là task poll bình thường.

### 5.4 UI đang tự suy diễn terminal semantics thay vì đọc contract backend đã chuẩn hóa

Khi backend chưa normalize đầy đủ `upscale_status`, UI phải đoán.

Đoán nhiều nơi sẽ luôn dẫn tới lệch semantics.

## 6. Có nên tách module xử lý lỗi ra ngoài `engine.py` không

Có, nhưng chỉ nếu tách đúng scope.

### 6.1 Điều nên làm

Tạo một module mới, ví dụ:

- `core/account_recovery_coordinator.py`

Module này chỉ xử lý lỗi cấp account/browser.

Nó là nơi duy nhất được quyền:

- đóng/mở gate submit của account
- set/clear cooldown account
- gọi `reload_tab`
- gọi `reload_page`
- gọi `hard_navigation`
- gọi `restart_browser`
- pause/resume `UpscaleQueue` của account
- quyết định escalation từ soft recovery sang hard recovery

### 6.2 Điều không nên làm

Không tạo một `error_manager.py` tổng quát rồi dồn:

- browser recovery
- task retry
- per-video status mutation
- UI semantics

vào cùng một nơi.

Làm vậy chỉ chuyển chỗ rối từ `engine.py` sang file khác.

## 7. Mô hình kiến trúc đề xuất

## 7.1 Phân lớp trách nhiệm

### A. Signal producers

Các nơi được phép phát hiện và gửi tín hiệu:

- `engine.py`
- `upscale_queue.py`
- `task_watchdog.py`
- `extension_bridge`
- `account_manager`

Các nơi này chỉ được:

- detect
- classify sơ bộ
- gửi signal vào coordinator

Chúng không được tự reload/restart browser nữa.

### B. Account Recovery Coordinator

Coordinator nhận tín hiệu và quyết định:

- có cần recovery browser/account không
- recovery ở mức nào
- có cần block submit mới không
- có cần pause upscale queue không
- có cần restart browser không

Coordinator phải serialize theo account.

Một account chỉ có một recovery sequence hoạt động tại một thời điểm.

#### Drain-and-remedy sequence (bắt buộc)

Vì mỗi account chỉ có một browser/tab context, mọi recovery action (reload, hard_navigation, restart) đều phá ngang các RPC đang chạy trên context đó. Coordinator phải thực hiện theo trình tự cứng sau:

```
1. close submit gate         → ngăn foremen gửi request mới
2. pause UpscaleQueue         → ngăn upscale download trên browser đó
3. mark account RECOVERING    → state machine transition
4. freeze all leases          → extend owner_lease cho mọi task của account (chống false-expire)
5. wait/cancel in-flight ops  → drain các RPC đang chạy (timeout 10s)
6. execute remedy action      → reload_tab / hard_navigation / restart_browser
7. startup probe              → verify extension + reCAPTCHA + x-browser-validation
8. unfreeze leases            → resume heartbeat cho các task đang chạy
9. reopen submit gate         → cho phép foremen hoạt động lại
10. resume UpscaleQueue       → cho phép upscale tiếp tục
11. mark account HEALTHY      → state machine transition
```

Nếu thiếu bước drain (step 5), dù gom quyền về một nơi, reload vẫn có thể chém ngang các RPC đang chạy.

**Rule cứng:** Trong trạng thái `RECOVERING_*` hoặc `BROWSER_RESTARTING`, lease phải được freeze/extend vô hạn. `has_live_background_owner(task)` phải coi account đang recovery là owner còn sống, không phụ thuộc heartbeat. Nếu không, recovery kéo dài hơn lease sẽ khiến watchdog/OTF tưởng task orphan và reclaim sai.

### C. Stage owners

Task state mutation vẫn thuộc stage owner:

- generation stage:
  - owner là worker/finalizer/replacement-task
- upscale stage:
  - owner là `UpscaleQueue`
  - chỉ `UpscaleQueue` (hoặc helper do nó gọi) mới được normalize `upscale_status`
- continuation dependency:
  - owner là dispatcher

### D. Watchdog

Watchdog có hai chế độ:

- **Với task có owner sống** (`background_owner` with live lease):
  - chỉ emit signal + audit counters
  - không gọi `requeue_task()`
- **Với task orphan** (generation stage, không có `background_owner`, worker đã chết):
  - vẫn được gọi `requeue_task()` → đây là rescue path cuối cùng
  - đây là trường hợp duy nhất watchdog được mutate task state

Watchdog không bao giờ được kéo task của `UpscaleQueue` về `READY`.

### E. UI

UI chỉ render contract backend.

UI không nên trở thành nơi hợp nhất semantics.

## 7.2 State machine ở cấp account

Đề xuất các trạng thái:

- `HEALTHY`
- `COOLDOWN`
- `RECOVERING_SOFT`
- `RECOVERING_HARD`
- `BROWSER_RESTARTING`
- `PAUSED`

Transition ví dụ:

- `HEALTHY -> RECOVERING_SOFT`
  khi reCAPTCHA not ready hoặc tab reload needed
- `RECOVERING_SOFT -> RECOVERING_HARD`
  khi reload mềm thất bại
- `RECOVERING_HARD -> BROWSER_RESTARTING`
  khi tab dead/no response
- `BROWSER_RESTARTING -> HEALTHY`
  khi reconnect + startup probe pass

## 7.3 Contract signal đề xuất

Ví dụ signal object:

```python
RecoverySignal(
    account_email=email,
    source="watchdog",
    scope="account",
    stage="upscale",
    task_id=task.id,
    error_type="poll_timeout",
    severity="high",
    checkpoint_stage=str(task.stage),
    can_retry_locally=False,
)
```

Ý nghĩa:

- source có thể nhiều nơi
- decision chỉ coordinator

## 8. Quy tắc ownership sau refactor

### 8.1 Generation stage

Owner:

- worker/finalizer
- replacement-task nếu là `timeout_retry`

Không nơi nào khác được:

- set `quality='timeout_retry'`
- tạo replacement task
- promote từ replacement về original

### 8.2 Upscale stage

Owner:

- `UpscaleQueue`

Chỉ `UpscaleQueue` được:

- đổi `upscale_status`
- retry/durable retry upscale
- complete task sau khi background upscale terminal

`watchdog` và `OTF` không được tự cướp task lifecycle của stage này.

### 8.3 Watchdog

Nếu task đang ở:

- `DOWNLOADED_720`
- `UPSCALING`
- `UPSCALED`

và còn checkpoint/file hợp lệ,

thì watchdog chỉ được:

- emit signal
- ghi log
- không gọi `requeue_task()`

### 8.4 OTF sweep

OTF chỉ nên xử lý:

- abandoned terminal failures
- missing media IDs
- tasks thực sự không còn owner sống

OTF không nên:

- re-upscale task đã `COMPLETED` nếu `file_upscaled` đã tồn tại
- quét các task background owner vẫn còn active

## 9. Chi tiết xử lý cần làm và vì sao

## 9.1 Chặn watchdog requeue trên task đã handoff sang `UpscaleQueue`

Vì sao:

- hiện đây là nguồn trực tiếp làm task upscale nhảy về `READY`
- phá checkpoint ownership
- gây spam `READY -> RESERVED`

Cách xử lý:

- thêm guard trong `task_watchdog.py`
- nếu task đang ở stage upscale/downloaded checkpoint và task còn active job trong `UpscaleQueue`, watchdog không được gọi `requeue_task()`
- watchdog chỉ emit signal cho coordinator hoặc log heartbeat failure

Kết quả cần đạt:

- không còn row đang upscale bị kéo về `READY` chỉ vì timeout poll cũ

## 9.2 Chuẩn hóa `upscale_status` terminal

Vì sao:

- hiện có cả `completed` và `success`
- có case file `1080p` tồn tại nhưng status vẫn `failed`

Cách xử lý:

- chọn một terminal value duy nhất, ví dụ `success`
- trước `complete_task()`, normalize:
  - nếu `file_upscaled` tồn tại hoặc `best_file` là bản upscaled thì set `upscale_status='success'`
  - clear `upscale_error`

Kết quả cần đạt:

- task đã có file upscaled không còn bị OTF/UI tiếp tục xem là failed

## 9.3 Sửa OTF Phase 3 để không retry stale terminal outputs

Vì sao:

- OTF hiện còn quét các task `COMPLETED` nhưng per-video status stale
- gây vòng lặp `Re-upscale -> failed_indices=[] -> no-op`

Cách xử lý:

- khi `file_upscaled` tồn tại thì output đó là terminal
- `upscale_status='failed'` trong case này phải bị normalize hoặc bỏ qua khỏi Phase 3

Kết quả cần đạt:

- OTF chỉ retry các slot thực sự chưa có artifact terminal

## 9.4 Tách browser recovery khỏi `engine.py`

Vì sao:

- `engine.py` hiện vừa xử lý generation retry, vừa điều phối reCAPTCHA reload, vừa dính account cooldown
- với một browser chung cho account, quyết định reload/restart không nên nằm trong worker path

Cách xử lý:

- giữ detection ở `engine.py`
- chuyển remedy decision sang coordinator
- `engine.py` chỉ gọi kiểu:

```python
await self._recovery.report_signal(...)
```

Kết quả cần đạt:

- chỉ có một luồng recovery browser/account tại một thời điểm
- không còn reload storm do nhiều nơi cùng quyết định

## 9.5 Giữ `task retry` ở stage owner, không gom hết vào coordinator

Vì sao:

- coordinator nên xử lý account/browser shared resource
- generation retry và upscale retry là logic nghiệp vụ theo stage

Cách xử lý:

- generation retry logic vẫn ở `engine.py`
- upscale retry logic vẫn ở `upscale_queue.py`
- coordinator chỉ pause/resume gate và account state

Kết quả cần đạt:

- tách đúng mức
- tránh tạo “god object”

## 10. Kết quả cần đạt sau refactor

## 10.1 Kết quả kỹ thuật bắt buộc

- Không còn nhiều module cùng reload/restart browser cho cùng một account
- Không còn task đã handoff sang `UpscaleQueue` bị watchdog kéo về `READY`
- Không còn OTF re-upscale no-op trên task đã có file upscaled
- Không còn task `COMPLETED` nhưng per-video `upscale_status='failed'` khi artifact thực đã terminal
- Chỉ có một owner được quyền mutate state cho mỗi stage

## 10.2 Kết quả UI tối thiểu

Ngay cả khi chưa sửa UI semantics toàn bộ, sau backend refactor vẫn phải đạt:

- số row `FAIL` giảm rõ rệt
- `FAILED` đỏ chỉ còn cho fail backend thật
- không còn các row upscale chuyển `READY -> Resuming -> READY` một cách bất thường

## 10.3 Kết quả vận hành

- không còn reload storm hoặc browser restart storm cho một account
- khi browser chết, recovery được serialize và có escalation rõ ràng
- các task khác của cùng account không bị nhiễu state do nhiều nơi cùng chạm browser

## 11. Phạm vi nên làm theo hai tầng

### Tier 1: Backend ownership cleanup

Mục tiêu:

- watchdog không cướp owner của upscale
- normalize terminal upscale status
- OTF không retry stale terminal outputs
- thêm `Account Recovery Coordinator`

### Tier 2: UI semantics alignment

Mục tiêu:

- thống nhất cách hiển thị `failed/completed/incomplete/recovering`
- loại bỏ hoàn toàn fail flash giả
- làm gọn contract `TaskDTO`

Lý do tách tầng:

- backend ownership là blocker thực cho async correctness
- UI semantics là lớp hiển thị, nên sửa sau khi backend contract ổn định

## 12. Chỉ dấu thành công để nghiệm thu

Sau khi làm đúng kiến trúc, cần thấy trong log:

- không còn `POLL timeout -> requeue_task -> READY` cho task đang thuộc `UpscaleQueue`
- không còn `Re-upscale ... failed_indices = []` lặp vô hạn trên task đã complete
- không còn task complete nhưng lại bị enqueue upscale tiếp chỉ vì stale `upscale_status`
- recovery browser/account có log serialized theo account, không chồng nhau

Và trên UI:

- `READY` chỉ xuất hiện khi task thực sự quay lại hàng đợi
- `Resuming upscale` không bị xen `READY` giả
- row đã complete với file `1080p` không còn bị gắn `FAIL` chỉ vì stale per-video status

## 13. Khuyến nghị chốt

Khuyến nghị triển khai:

1. Không tiếp tục vá lẻ từng bug trong `engine.py`, `watchdog`, `OTF`, `UI` nếu chưa khóa ownership.
2. Ưu tiên refactor nhỏ nhưng đúng hướng: thêm `Account Recovery Coordinator`.
3. Đặt luật cứng:
   - browser/account recovery chỉ coordinator được quyết định
   - generation retry chỉ generation owner
   - upscale retry chỉ `UpscaleQueue`
   - watchdog không mutate task của stage có owner sống
4. Sau khi Tier 1 ổn định mới làm tiếp Tier 2 UI semantics.

## 14. Tóm tắt một câu

Muốn hệ thống chạy bất đồng bộ ổn định với một browser dùng chung cho mỗi account, phải tách riêng recovery cấp account/browser ra khỏi `engine.py` và áp nguyên tắc cứng: nhiều nơi được báo lỗi, nhưng mỗi stage và mỗi account chỉ có một owner được quyền sửa state và ra quyết định recovery.

---

## 15. Trạng thái triển khai (v5.2 — 2026-04-12)

### 15.1 Các patch đã áp dụng

5 fix đã triển khai trong v5.2:

| # | File | Nội dung | Mapping report |
|---|------|----------|----------------|
| 1 | `task_watchdog.py` | Skip task có `_counter_decremented=True` | §9.1 |
| 2 | `dispatcher.py` | Normalize `upscale_status='failed'` → `success` khi `file_upscaled` tồn tại tại `complete_task()` | §9.2 |
| 3 | `app_controller.py` | OTF Phase 3 skip re-upscale khi `file_upscaled` đã tồn tại | §9.3 |
| 4 | `upscale_queue.py` | Drop job nếu `task.state == COMPLETED` | §4.1 stale job |
| 5 | `remedy_registry.py` | Escalation tracker: nếu cùng error_type xảy ra lại trong 180s, bắt đầu từ remedy tiếp theo thay vì reset về remedy #1 | §5.2 browser recovery trộn lẫn |

### 15.2 Đánh giá: fix đúng triệu chứng, chưa giải quyết gốc kiến trúc

| Fix | Triệu chứng giải quyết | Giới hạn kiến trúc |
|-----|------------------------|---------------------|
| Fix 1 | Task upscale không bị kéo về READY | Dùng proxy attribute `_counter_decremented` thay vì ownership contract. Watchdog vẫn giữ quyền gọi `requeue_task()` cho mọi stage khác. Nếu attribute bị clear/reset, bug quay lại. |
| Fix 2 | Task có file 1080p không còn bị UI hiện FAIL | `dispatcher.complete_task()` đang sửa status — vi phạm ownership (§8.2: chỉ `UpscaleQueue` được đổi `upscale_status`). |
| Fix 3 | OTF không re-upscale task đã hoàn thành | OTF vẫn giữ vai trò auto-driver (round limit=5). Chưa hạ xuống "abandoned only" (§8.4). |
| Fix 4 | Stale job cycle bị chặn | Hợp lý, đúng ownership. Không có giới hạn kiến trúc. |
| Fix 5 | Vòng lặp soft_recovery bị phá vỡ | Vẫn để 5+ file cùng quyết định reload/restart browser. Escalation tracker chỉ cải thiện remedy_registry, không giải quyết vấn đề nhiều nơi cùng quyền recovery (§9.4). |

### 15.3 Các gap chưa giải quyết

#### GAP-1: Thiếu nguyên tắc "1 Stage = 1 Owner" (§5.1)

Nhiều module cùng có quyền mutate `task.state`, `video_output.quality`, `upscale_status`, và gọi browser recovery. Cần define ownership cứng cho mỗi stage.

#### GAP-2: Thiếu Account Recovery Coordinator (§6.1, §7, §9.4)

Browser recovery rải ở:
- `engine.py` — CircuitBreaker, reCAPTCHA monitor
- `remedy_registry.py` — soft_recovery, hard_restart
- `app_controller.py` — `_on_tab_dead`, `restart_browser_for`
- `account_manager.py` — `restart_browser`, `soft_recover_browser`
- `extension_bridge.py` — `trigger_hard_navigation`

Cùng 1 account có thể bị reload/restart bởi nhiều path đồng thời → reload storm.

#### GAP-3: Background ownership chưa biểu diễn rõ (§5.3)

Sau handoff sang `UpscaleQueue`, task vẫn dùng `_counter_decremented` là proxy ngầm. Cần ownership contract cứng với liveness guarantee:

- `task.background_owner: Optional[str]` — tên owner (vd: `"upscale_queue"`)
- `task.owner_heartbeat_ts: float` — timestamp heartbeat gần nhất từ owner
- `task.owner_lease_duration: float` — thời hạn lease (vd: 120s)
- Helper: `has_live_background_owner(task)` → True nếu `background_owner is not None` AND `now - owner_heartbeat_ts < owner_lease_duration`

Nếu chỉ dùng raw string flag, owner crash hoặc app restart sẽ khiến OTF/watchdog skip task mãi mãi.

**Yêu cầu bắt buộc:**
- Startup reconcile: khi app khởi động, quét mọi task có `background_owner` set. Nếu owner tương ứng chưa có job cho task đó → clear `background_owner`. Persist `background_owner` + `owner_heartbeat_ts` vào session JSON.
- Lease freeze during recovery: `has_live_background_owner(task)` có thêm check: nếu account của task đang ở trạng thái `RECOVERING_*` / `BROWSER_RESTARTING` (theo coordinator state machine) → return True vô điều kiện, không phụ thuộc heartbeat. Điều này ngăn watchdog/OTF reclaim task sai trong khi coordinator đang drain + recovery.

#### GAP-4: `upscale_status` terminal vocabulary không thống nhất (§4.6)

- `upscale_queue.py:1700` set `"completed"`
- `upscale_queue.py:1937,1957,2049,2340,2961` set `"success"`
- UI hiểu: `failed`, `polling`, `submitting`, `success` — không có contract cho `completed`

#### GAP-7: Terminal upscale normalization nằm sai ownership

Fix v5.2 đặt normalize `upscale_status` trong `dispatcher.complete_task()` — vi phạm nguyên tắc ownership (§8.2). Logic này phải nằm ở `UpscaleQueue` hoặc helper do `UpscaleQueue` gọi trước khi gọi `complete_task()`.

#### GAP-8: `_mark_account_sick()` bypass ownership cho background-owned tasks

`engine.py:1989-1993` — khi circuit breaker trip nhiều lần, `_mark_account_sick()` requeue mọi task RUNNING/WAITING_POLL của account mà không check `background_owner`. Task đang ở handoff window sang `UpscaleQueue` (state=RUNNING, đã `_counter_decremented`) sẽ bị requeue sai.

Ngoài ra, `engine.py:2002-2018` tự gọi `acc.close_browser()` + `bridge.set_browser_cooldown()` — vi phạm single owner cho browser recovery.

Hướng xử lý:
- Phần requeue: mọi chỗ gọi `requeue_task()` phải dùng `has_live_background_owner(task)` — ghi vào T0-3 scope.
- Phần browser close: chuyển về coordinator — ghi vào T1-7 call inventory.
- Không nên patch edge case 1 (đơn độc skip requeue) nếu chưa có recovery path cho account sick. Nếu không, task upscale có thể không bị requeue sai nhưng sẽ bị treo luôn. Tốt nhất triển khai cùng T1-1/T1-5 để có coordinator nhận signal.

---

### Backlog song song (không block Recovery Coordinator scope)

#### BACKLOG-1: Dispatcher reserve race

`task_12` bị `READY → RESERVED` lặp lại >15 lần trong vài giây. `reserve_task()` check `task.state == READY` nhưng không atomic transition. Cần lock hoặc CAS pattern. Không liên quan đến coordinator — triển khai độc lập.

#### BACKLOG-2: CreditWindow cold-start drain

Credits giảm 10→5 trong 2 phút cold-start reCAPTCHA. `ERROR_CREDIT_COST[RECAPTCHA_TIMEOUT]` = 2, quá cao cho cold-start transient. Giảm cost hoặc miễn trừ trong cold-start window. Không liên quan đến coordinator — triển khai độc lập.

## 16. Kế hoạch triển khai theo tier

### Tier 0: Quick fixes (rủi ro thấp, không phụ thuộc refactor kiến trúc)

| # | Task | File(s) | GAP | Mô tả |
|---|------|---------|-----|-------|
| T0-1 | Chuẩn hóa `upscale_status` vocabulary | `upscale_queue.py` | GAP-4 | Grep `"completed"` → `"success"` cho upscale terminal. |
| T0-2 | Thêm `task.background_owner` + lease contract | `dispatcher.py`, `engine.py`, `upscale_queue.py` | GAP-3 | Thêm `background_owner`, `owner_heartbeat_ts`, `owner_lease_duration`. UpscaleQueue set khi handoff, update heartbeat mỗi cycle, clear khi hoàn thành. Helper `has_live_background_owner(task)` dùng chung. Persist vào session JSON + startup reconcile bắt buộc. |
| T0-3 | Watchdog + mọi rescue path: refactor guard sang `has_live_background_owner()` | `task_watchdog.py`, `engine.py` | GAP-1/3/8 | Task có owner sống → skip. Task orphan generation → vẫn giữ `requeue_task()`. Áp dụng cho cả `_mark_account_sick()` requeue loop (`engine.py:1989`). Lưu ý: không patch skip requeue đơn độc nếu chưa có coordinator nhận signal — nên triển khai cùng T1-5. |
| T0-4 | Chuyển terminal upscale normalization về UpscaleQueue | `upscale_queue.py`, `dispatcher.py` | GAP-7 | Xóa normalize logic khỏi `dispatcher.complete_task()`. `UpscaleQueue` (hoặc helper) normalize `file_upscaled → upscale_status='success'` trước khi gọi `complete_task()`. |

### Tier 1: Backend ownership cleanup (blocker cho async correctness)

| # | Task | Scope | GAP | Dependency | Mô tả |
|---|------|-------|-----|------------|-------|
| T1-1 | Tạo `core/account_recovery_coordinator.py` | New file | GAP-2 | — | Class nhận RecoverySignal, serialize recovery per account, state machine (HEALTHY → RECOVERING_SOFT → RECOVERING_HARD → BROWSER_RESTARTING), drain-and-remedy sequence (§7.1B). |
| T1-2 | Di chuyển CircuitBreaker reCAPTCHA monitor ra coordinator | `engine.py` → coordinator | GAP-2 | T1-1 | Extract logic L2180-2240. Engine chỉ gọi `coordinator.report_signal()`. |
| T1-3 | Di chuyển remedy decision ra coordinator | `remedy_registry.py` → coordinator | GAP-2 | T1-1 | Coordinator gọi remedy chain nội bộ. Các module khác không trực tiếp gọi remedy. |
| T1-4 | Centralize browser restart calls — `account_manager.py`, `app_controller.py` | GAP-2 | T1-1 | Gọi browser recovery chỉ qua coordinator. Xem call inventory bên dưới. |
| T1-5 | Watchdog: bỏ `requeue_task()` cho task có owner sống | `task_watchdog.py` | GAP-1 | T1-1 | Emit signal cho coordinator thay vì tự requeue. Giữ orphan-rescue cho generation stage (task không có `background_owner` và worker đã chết). |
| T1-6 | OTF sweep: chỉ quét abandoned tasks | `app_controller.py` | GAP-1 | T0-2 | Kiểm tra `has_live_background_owner(task)`: nếu owner sống → skip. Chỉ xử lý task thật sự orphaned. |
| T1-7 | Remove direct recovery calls từ engine.py + upscale_queue.py | `engine.py`, `upscale_queue.py` | GAP-2 | T1-1 | Thay mọi call trực tiếp bằng `coordinator.report_signal()`. Xem call inventory bên dưới. |

#### Call inventory: direct browser recovery calls cần chuyển qua coordinator

| File | Line | Call | Context |
|------|------|------|---------|
| `engine.py` | 2125 | `account.soft_recover_browser()` | CircuitBreaker 403 recovery |
| `engine.py` | 2210 | `bridge.trigger_hard_navigation()` | CircuitBreaker reCAPTCHA unhealthy 60s |
| `engine.py` | 2877 | `account.soft_recover_browser()` | PreWarm recovery |
| `engine.py` | 3689 | `account.soft_recover_browser()` | Worker `_do_browser_recovery` soft tier |
| `engine.py` | 3692 | `account.restart_browser()` | Worker `_do_browser_recovery` hard tier |
| `engine.py` | 8799 | `bridge._trigger_refresh()` | Foreman reCAPTCHA not ready |
| `engine.py` | 8862 | `bridge.trigger_hard_navigation()` | Foreman escalation hard nav |
| `engine.py` | 9714 | `account.soft_recover_browser()` | Upscale submit reCAPTCHA fail attempt 1 |
| `engine.py` | 9725 | `send_and_wait('reload_tab')` | Upscale submit extension tab reload |
| `engine.py` | 9744 | `account.soft_recover_browser()` | Upscale submit reCAPTCHA fail attempt 2+ |
| `upscale_queue.py` | 1462 | `account.soft_recover_browser()` | M3 Phase 1 gentle recovery |
| `upscale_queue.py` | 1472 | `account.soft_recover_browser()` | M3 Phase 2 extended recovery |
| `upscale_queue.py` | 1496 | `profiles_ctrl.reset_profile(account)` | M3 Phase 3 profile reset |
| `upscale_queue.py` | 1503 | `account.soft_recover_browser()` | M3 Phase 3 fallback |
| `engine.py` | 2008 | `bridge.set_browser_cooldown()` | `_mark_account_sick` — cooldown (GAP-8) |
| `engine.py` | 2013 | `acc.close_browser()` | `_mark_account_sick` — auto-close browser (GAP-8) |
| `remedy_registry.py` | 241 | `account.soft_recover_browser()` | Remedy action (giữ lại — coordinator gọi trực tiếp) |
| `remedy_registry.py` | 252 | `account.restart_browser()` | Remedy action (giữ lại — coordinator gọi trực tiếp) |
| `account_manager.py` | 609 | `bridge.trigger_hard_navigation()` | `soft_recover_browser()` impl (giữ lại — impl method) |
| `app_controller.py` | 1241 | `_force_restart_browser()` | `_on_tab_dead` handler |
| `app_controller.py` | 1935 | `restart_browser_for()` | Public API |
| `app_controller.py` | 2092 | `restart_browser_for()` | Internal call |
| `app_controller.py` | 2325 | `restart_browser_for()` | Cooldown expired recovery |

Tổng: **16 call sites cần chuyển** (12 trong engine.py + 4 trong upscale_queue.py). 4 call trong remedy_registry.py và account_manager.py là implementation methods, giữ lại nhưng chỉ coordinator được invoke. 4 call trong app_controller.py chuyển qua coordinator (T1-4).

### Tier 2: UI semantics alignment (sau khi backend contract ổn định)

| # | Task | File(s) | Mô tả |
|---|------|---------|-------|
| T2-1 | Thêm `recovering` state cho video_output | `dispatcher.py`, model | Không set `quality='failed'` cho retryable error. Dùng `recovering_poll`, `recovering_submit`, etc. |
| T2-2 | Renderer: chỉ hiện FAIL khi terminal | `group_renderer.py` | Kiểm tra `terminal=True` thay vì `quality == 'failed'`. |
| T2-3 | Footer phân biệt: Failed / Recovering / Partial | UI footer | UX rõ ràng hơn. |

## 17. Thứ tự thực hiện

```
Tier 0 (T0-1..T0-4)       Backlog (song song, không block)
  → triển khai ngay         → BACKLOG-1: reserve race
  → không phụ thuộc gì      → BACKLOG-2: credit drain
          |
          v
Tier 1 (T1-1..T1-7)
  T1-1: Coordinator skeleton ─────────────────┐
          |                                     |
          ├─→ T1-2: Extract CircuitBreaker      |
          ├─→ T1-3: Extract remedy decision     |
          ├─→ T1-4: Centralize browser restart  |
          ├─→ T1-5: Watchdog emit signal        |
          └─→ T1-7: Remove direct calls ────────┘
  T1-6: OTF owner check (phụ thuộc T0-2 lease contract)
          |
          v
Tier 2 (T2-1..T2-3)
  → chỉ làm SAU KHI Tier 1 ổn định
  → phụ thuộc backend contract mới
```

Dependency cứng:
- `T1-1` (coordinator) PHẢI đi trước `T1-2`, `T1-3`, `T1-4`, `T1-5`, `T1-7`
- `T1-5` (watchdog emit signal) KHÔNG chạy nếu chưa có coordinator nhận signal
- `T1-7` (remove direct calls) nên chạy song song với `T1-4` (cùng scope: gom recovery calls)
- `T0-2` (lease contract) đi trước `T1-6` (OTF owner check)
- `T0-4` (normalize ownership) đi trước Tier 2

## 18. Quyết định thiết kế (đã chốt)

### D1: Account Recovery Coordinator — file riêng

Quyết định: tạo `core/account_recovery_coordinator.py`.

Lý do: coordinator cần state machine riêng + lock per account + signal queue + drain-and-remedy sequence. Không nên tiếp tục phình `app_controller.py`.

### D2: `background_owner` phải có lease/liveness — bắt buộc persist

Quyết định:
- Persist `background_owner` + `owner_heartbeat_ts` vào session JSON — bắt buộc.
- Startup reconcile — bắt buộc: quét mọi task có `background_owner` set, nếu owner tương ứng chưa có job → clear owner.
- Không dùng raw string flag. Phải có `owner_lease_duration` và helper `has_live_background_owner(task)`.

Lý do: nếu không persist + reconcile, app restart sẽ khiến watchdog/OTF skip task mãi mãi.

### Q3: OTF sweep — giảm rounds hay tắt khi engine chạy?

Option A: Giảm `auto_sweep_max_rounds` từ 5 → 2.
Option B: Tắt OTF khi engine đang chạy, chỉ chạy khi idle/startup.
Option C: Giữ rounds nhưng thêm owner check (T1-6).

Khuyến nghị: Option C trước (Tier 1), sau đó Option B khi coordinator ổn định.
