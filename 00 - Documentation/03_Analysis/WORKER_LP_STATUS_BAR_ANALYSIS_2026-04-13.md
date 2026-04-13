# Worker / LP / Upscale Status Bar Analysis

Ngày: 2026-04-13  
Phạm vi: `02 - CLIENT - VEO PRO MAX`  
Trạng thái: Báo cáo phân tích code và hành vi UI, chưa áp dụng patch trong tài liệu này.

## 1. Mục tiêu

Báo cáo này làm rõ 4 câu hỏi:

1. Vì sao status bar đang hiển thị `8/12` trong khi nhìn từ queue có vẻ phải là `13`.
2. Cấu hình `worker` và `worker low priority (LP)` có đang bị bypass hay không.
3. Vì sao task `#10 T2V` có `output_count=4` nhưng không được hiểu là đang giữ đủ `4 worker` trong status bar.
4. Giải pháp nào là đúng để UI và backend cùng phản ánh đúng capacity thực tế.

---

## 2. Kết luận điều hành

Có 2 lớp vấn đề khác nhau:

- **Lớp 1: hiểu nhầm semantics của status bar**
  - `8/12` trong ảnh không phải là tổng worker đang chạy.
  - Nó là riêng **LP pool**.
  - `5/8` là riêng **upscale pool**.
  - Nên nếu cộng đúng theo UI hiện tại thì tổng held slots đang hiển thị là `0 + 8 + 5 = 13`.

- **Lớp 2: bug thật trong cách tính status bar**
  - Phần `⚡ Fast` đang tính sai.
  - UI đang lấy một biến vốn đã là **Fast-only**, sau đó lại trừ tiếp `LP`.
  - Kết quả là `⚡` có thể về `0` giả hoặc thấp hơn thực tế.

Tức là:

- **Không có bằng chứng LP cap đang bị bypass ở engine/session enforcement**.
- **Có bug ở tầng tổng hợp số liệu và trình bày status bar**.

---

## 3. Status Bar hiện đang hiển thị cái gì

Status bar bottom không hiển thị một con số “tổng worker đang chạy”.  
Nó hiển thị 3 pool riêng:

- `⚡ Fast ops`
- `🐢 LP ops`
- `⬆️ Upscale`

Điều này được render trực tiếp ở:

- `ui/app.py:833-844`

Logic:

```python
active_upscale = acc.get("active_upscale", 0)
max_upscale = acc.get("max_upscale", 8)
active_lp = acc.get("active_workers_lp", 0)
max_lp = acc.get("max_workers_lp", 20)
active_fast = max(0, active_workers - active_lp)

self._status_widgets["workers"].setText(
    f"⚡ {active_fast}/{total_capacity} "
    f"| 🐢 {active_lp}/{max_lp} "
    f"| ⬆️ {active_upscale}/{max_upscale} "
)
```

### Hệ quả

Nếu ảnh hiển thị kiểu:

- `⚡ 0/20`
- `🐢 8/12`
- `⬆️ 5/8`

thì UI đang nói:

- Fast pool đang được tính là `0`
- LP pool đang dùng `8` trên max `12`
- Upscale pool đang dùng `5` trên max `8`

Về mặt cộng pool, tổng số slot đang được UI biểu diễn là:

`0 + 8 + 5 = 13`

Nên phần “`8/12` thay vì `13`” là do **đọc nhầm `8/12` như tổng**, trong khi thực tế đó chỉ là LP pool.

---

## 4. Bug thật: `⚡ Fast` đang tính sai

### 4.1. Chỗ lấy dữ liệu

`AppController.get_account_summary()` trả về:

- `active_workers = self._multi_account.total_active`
- `active_workers_lp = self._multi_account.total_active_lp`
- `active_upscale = self._multi_account.total_active_upscale`

Tại:

- `core/app_controller.py:5481-5496`

### 4.2. `total_active` hiện không phải “tổng active”

`MultiAccount.total_active` hiện được tính như sau:

- `return sum(acc.active_slots for acc in self._accounts)`

Tại:

- `core/multi_account.py:71-73`

Nhưng:

- `AccountManager.active_slots` chỉ trả `self._session.active_slots`

Tại:

- `core/account_manager.py:173-175`

Và:

- `AccountSession.active_slots` là property deprecated, chỉ trả `self.active_workers`

Tại:

- `core/session.py:184-186`

### 4.3. Nghĩa là gì

`active_workers` trong `AppController` đang mang tên như thể là:

- tổng active worker

nhưng thực tế source của nó chỉ là:

- **Fast active workers**

Sau đó UI lại tính:

```python
active_fast = max(0, active_workers - active_lp)
```

Tức là:

- đã Fast-only rồi
- lại trừ thêm LP một lần nữa

=> `⚡ Fast` bị thấp giả, thậm chí về `0` giả.

### 4.4. Kết luận bug

Đây là lỗi đặt tên + lỗi công thức.

Không phải engine chạy sai pool.  
Mà là:

- `active_workers` bị hiểu là “tổng ops”
- trong khi thực ra nó là “fast only”
- rồi UI trừ LP lần nữa

---

## 5. Vì sao `#10 T2V output_count=4` không đồng nghĩa status bar phải giữ `4 worker`

Đây là chỗ dễ nhầm nhất.

### 5.1. Hai-phase admission

Foreman ban đầu acquire:

- `1 worker` trước
- sau đó mới expand thêm theo `output_count`

Tại:

- `core/engine.py:4063-4074`
- `core/engine.py:4208-4235`

### 5.2. Sau submit, engine cố ý nhả bớt slot

Khi submit async thành công và server đã trả về `operation_names`, engine:

- giữ lại `1` slot pipeline
- release `output_count - 1`

Tại:

- `core/engine.py:5381-5423`

Logic comment trong code ghi rất rõ:

- submit xong thì task chỉ còn poll/download/upscale
- không cần giữ đủ toàn bộ slot submit ban đầu
- mục tiêu là tăng concurrency toàn hệ thống

### 5.3. Với task resume cũng tương tự

Ở nhánh resume từ checkpoint:

- task cũng chỉ giữ `1` slot pipeline
- release phần còn lại

Tại:

- `core/engine.py:4366-4378`

### 5.4. Kết luận

Một task `T2V output_count=4`:

- **được quyền cần 4 slot ở lúc admission/submit**
- **không được thiết kế để giữ 4 slot suốt toàn bộ vòng đời task**

Vì vậy nếu nhìn queue thấy `#10` đang `Processing` ở `45%` mà status bar không cộng đủ `4 Fast workers`, điều đó **không tự động là bug**.

Phần đúng theo kiến trúc hiện tại là:

- status bar không đếm “số video variants”
- status bar đếm “số slot hiện đang bị giữ bởi từng pool”

---

## 6. LP setup có đang bị bypass không

### 6.1. Kết luận ngắn

**Chưa thấy dấu hiệu bypass ở enforcement**.

LP vẫn đang bị chặn bởi:

- `effective_lp_capacity`
- `acquire_workers_lp()`
- `release_workers_lp()`

### 6.2. Nơi enforcement thật sự xảy ra

LP swap được thực hiện ở foreman:

- detect LP model qua `is_relaxed_model(task.model)`
- release Fast slot ban đầu
- acquire LP slot thay thế

Tại:

- `core/engine.py:4130-4160`

Capacity LP được enforce ở session:

- `effective_lp_capacity = min(max_workers_lp, total_remaining)`
- `acquire_workers_lp()` fail nếu vượt cap

Tại:

- `core/session.py:157-167`
- `core/session.py:241-255`

### 6.3. Điều đang sai là gì

Điều sai hiện tại là:

- UI/status bar diễn giải số liệu sai
- không phải LP cap thực thi bị bypass

Nói cách khác:

- **policy đúng**
- **telemetry sai**

### 6.4. LP cũng đang có vấn đề, nhưng không phải ở enforcement

Nếu hỏi:

- “không chỉ Fast mà LP cũng đang có vấn đề đúng không?”

thì câu trả lời chính xác là:

- **có**, nhưng vấn đề của LP hiện tại chủ yếu nằm ở **telemetry, aggregate semantics, và default fallback**, không phải ở `acquire_workers_lp()` hay `effective_lp_capacity()`.

Ba điểm LP cần làm rõ:

#### a. LP đang bị hiểu nhầm là “tổng worker”

Trong ảnh:

- `🐢 8/12`

đã là **tổng LP aggregate của các account/profile đang active**, không phải số LP của riêng một task group.

Nguồn aggregate:

- `core/multi_account.py:93-98`

```python
return sum(
    getattr(acc.session, 'max_workers_lp', 20)
    for acc in self._accounts
)
```

Tức là:

- nếu có nhiều account/profile
- status bar đang cộng LP cap của tất cả account lại

#### b. LP có fallback mặc định dễ làm cap bị “nở” hơn user nghĩ

Khi load session từ dữ liệu cũ hoặc profile không có `max_workers_lp`, hệ thống dùng:

- `session.max_workers_lp = data.get("max_workers_lp", session.max_workers)`

Tại:

- `core/session.py:430`

Điều này có nghĩa:

- profile mới chuẩn: LP cap riêng, ví dụ `8`
- nhưng profile cũ / thiếu field: LP cap sẽ fallback thành toàn bộ `max_workers`

=> không phải bypass runtime, nhưng là **fallback có thể làm LP cap lớn hơn user kỳ vọng**.

#### c. LP đang được tổng hợp đúng về mặt enforcement nhưng chưa rõ về mặt UI contract

Profile model mặc định đang khai báo:

- `max_workers = 20`
- `max_workers_lp = 8`

Tại:

- `core/profiles_controller.py:189-190`

Nhưng status bar chỉ hiển thị aggregate cuối cùng, không chỉ ra:

- mỗi profile đang set bao nhiêu
- profile nào đóng góp bao nhiêu vào `12`

=> với LP, bug hiện không phải “pool mở sai”, mà là:

- **aggregate hiển thị đúng kiểu máy tính, nhưng không đúng kiểu người dùng kỳ vọng**

---

## 7. Vì sao ảnh trông như “worker count bị bypass”

Có 3 nguyên nhân gây ảo giác:

### 7.1. UI tách 3 pool nhưng người xem đang cộng theo task

Người dùng đang suy luận:

- `#10 T2V` dùng 4 worker
- `Test Voice` có 7 prompt
- vậy tổng phải là 11 hoặc 13 tùy cách cộng

Nhưng UI không hiển thị theo “số prompt đang active”.
UI hiển thị theo:

- Fast slots đang giữ
- LP slots đang giữ
- Upscale slots đang giữ

### 7.2. `⚡ Fast` hiện đang bị under-report

Do bug:

- `active_workers` lấy từ `active_slots`
- `active_slots` chỉ là `active_workers`
- UI lại trừ tiếp LP

=> làm `⚡` nhỏ giả

### 7.3. Task 4-output nhả bớt slot sau submit

Task nhiều output không nhất thiết giữ đủ số slot bằng `output_count` sau khi đã submit xong.

Nên việc “nhìn thấy task còn đang chạy” không đồng nghĩa “status bar phải còn giữ đủ N worker”.

---

## 8. Vấn đề thiết kế telemetry hiện tại

Telemetry đang bị lẫn giữa 3 khái niệm:

### 8.1. `running_tasks`

Đây là số task còn ở:

- `RUNNING`
- `WAITING_POLL`

Nguồn:

- `dispatcher.running_count`
- `core/app_controller.py:5485-5488`

### 8.2. `held worker slots`

Đây là số slot capacity thực sự đang bị giữ bởi pool:

- Fast
- LP
- Upscale

### 8.3. `visible active prompts`

Đây là số prompt trong queue đang hiện:

- Gate check
- Submitting
- Processing
- Waiting in queue
- Upscaling

Ba thứ này không bằng nhau.

Status bar hiện đang trộn tên gọi không rõ ràng, dẫn tới:

- user tưởng nó là “số task đang chạy”
- trong khi thực chất là “slot counters của các pool”

### 8.4. Luồng điều khiển số lượng: Settings tab -> Profile -> Runtime -> Dispatcher -> Status bar

Đây là phần trước đó báo cáo chưa làm rõ đủ.

#### Bước 1: Profile model lưu cấu hình per-account

Profile schema hiện có:

- `max_workers`
- `max_workers_lp`

Tại:

- `core/profiles_controller.py:189-190`

Khi serialize profile ra list/dict:

- `max_workers`
- `max_workers_lp`

được export ở:

- `core/profiles_controller.py:379-380`

#### Bước 2: Runtime session nạp cấu hình từ profile

Khi account được sync vào runtime:

- `session.max_workers = getattr(profile_obj, 'max_workers', 20)`
- `session.max_workers_lp = getattr(profile_obj, 'max_workers_lp', session.max_workers)`

Tại:

- `core/app_controller.py:3522-3523`

Điểm quan trọng:

- `max_workers_lp` có thể fallback sang `session.max_workers`
- đây là nguồn của hiện tượng “LP cap nhìn như rộng hơn mong đợi” trên profile cũ/thiếu field

#### Bước 3: Settings UI đổi spinner sẽ chỉnh runtime account

Các entrypoint runtime hiện tại:

- `core/app_controller.py:2800-2823`
- `core/app_controller.py:3645-3669`

Chúng cập nhật:

- `acc.set_max_workers(value)`
- `acc.session.max_workers_lp = value`

Điểm cần lưu ý:

- đây là **runtime mutation**
- nếu nghi ngờ “đổi spinner xong restart app bị mất”, cần audit thêm đường persistence từ UI về `ProfilesController`
- báo cáo này hiện xác nhận rõ runtime path, nhưng chưa khẳng định toàn bộ save path của UI đã được audit end-to-end

#### Bước 4: Dispatcher chỉ hard-cap theo `max_workers`

Dispatcher đang có callback:

- `fn(email) -> max_workers`

và dùng nó để chặn `_per_account_running` vượt trần:

- `core/dispatcher.py:465-471`
- `core/dispatcher.py:650-656`
- wiring ở `core/engine.py:3261-3266`

Điều này có nghĩa:

- `max_workers` là hard cap cho task concurrency/account
- còn LP cap được enforce ở session acquire path, không phải dispatcher

#### Bước 5: Status bar cộng aggregate toàn multi-account

Status bar đang hiển thị:

- `total_capacity = sum(acc.max_workers)`
- `max_workers_lp = sum(acc.session.max_workers_lp)`

Nguồn:

- `core/multi_account.py:61-63`
- `core/multi_account.py:93-98`
- render ở `ui/app.py:833-844`

Nghĩa là:

- con số trong status bar là **tổng nhiều profile/account**
- không phải số của riêng task group đang nhìn thấy

#### Bước 6: License cũng có thể là một lớp cap khác

Role limits hiện còn có:

- `max_workers_per_account`

Tại:

- `services/permissions.py:61`
- `services/permissions.py:82`

Điểm này quan trọng vì về kiến trúc:

- Settings/Profile là cap cấu hình
- Session/Dispatcher là cap runtime
- License có thể là cap chính sách

Nếu sau này muốn báo cáo đầy đủ hơn, status bar nên phân biệt:

- configured cap
- effective cap after license
- currently held slots

### 8.5. Kết luận về “điều khiển số lượng trong từng profile, tổng profile trong Settings tab”

Sau khi kiểm tra code hiện tại, có thể kết luận:

- **Per-profile control có tồn tại** qua `max_workers` và `max_workers_lp`
- **Runtime control có tồn tại** qua `AccountSession` và `AccountManager`
- **Dispatcher hard-cap có tồn tại** nhưng chỉ cho `max_workers`
- **Status bar hiện đang hiển thị aggregate nhiều profile/account**
- **Báo cáo cũ chưa giải thích đầy đủ luồng này; mục này bổ sung để chốt semantics**

### 8.6. Vấn đề bổ sung khi dùng nhiều tài khoản

Khi chạy nhiều account/profile cùng lúc, status bar hiện tại có thêm một lớp sai lệch semantics ngoài bug `⚡ Fast`.

#### a. Denominator đang cộng theo toàn bộ account đã đăng ký trong runtime

Hiện tại:

- `total_capacity = sum(acc.max_workers for acc in self._accounts)`
- `total_capacity_lp = sum(acc.session.max_workers_lp for acc in self._accounts)`
- `total_max_upscale = account_count * display_max_upscale`

Tại:

- `core/multi_account.py:61-63`
- `core/multi_account.py:93-98`
- `core/multi_account.py:101-103`

Các property này:

- **không filter theo `enabled`**
- **không filter theo `ready`**
- **không filter theo account thực sự đang tham gia xử lý**

Trong khi `ready_accounts` lại có filter:

- `return [acc for acc in self._accounts if acc.is_ready]`

Tại:

- `core/multi_account.py:111-113`

=> status bar hiện đang trộn:

- `ready count` theo account usable
- `capacity denominator` theo account registered

Đây là nguồn gây lệch lớn khi dùng nhiều account.

#### b. Account disable / not-ready vẫn có thể làm phình capacity hiển thị

`account_count` hiện chỉ là:

- `len(self._accounts)`

Tại:

- `core/multi_account.py:106-108`

Nên nếu runtime vẫn giữ account trong pool nhưng account đó:

- đã disable
- chưa ready
- đang reconnect
- đang quarantine/recovery

thì denominator của:

- `⚡`
- `🐢`
- `⬆️`

vẫn có thể bị cộng cả account đó.

Tức là ở multi-account mode, status bar đang nghiêng về:

- **registered runtime capacity**

chứ không phải:

- **effective usable capacity**

#### c. LP aggregate trong multi-account đặc biệt dễ gây hiểu nhầm

Với LP:

- status bar chỉ hiển thị một aggregate `🐢 active/max`
- không cho biết account nào đang chiếm LP
- không cho biết account nào đóng góp bao nhiêu vào `12`
- không cho biết account nào đang fallback `max_workers_lp -> max_workers`

Nên `🐢 8/12` trong multi-account mode có thể tương ứng với rất nhiều phân bố khác nhau:

- `4 + 4`
- `8 + 0`
- `2 + 6`
- hoặc có account disabled vẫn còn nằm trong mẫu số

#### d. Upscale aggregate cũng bị cùng vấn đề

`total_active_upscale` đang cộng:

- `active_upscale_workers`
- `active_bg_upscale`

trên toàn bộ account

Tại:

- `core/multi_account.py:76-82`

Nên nếu:

- account A đang background upscale
- account B đang chạy Fast/LP

thì status bar chỉ hiện một con số fleet-level aggregate, rất khó map ngược về từng task group đang nhìn trên queue.

#### e. Load balancer và status bar đang nhìn hệ thống theo hai góc khác nhau

Load balancer chọn account theo:

- `available_workers`
- `active_workers`
- `403 health`
- extension connected

Tại:

- `core/multi_account.py:161-190`
- `core/multi_account.py:243-268`

Trong khi status bar render theo aggregate fleet.

Kết quả:

- task group đang nhìn thấy có thể chủ yếu chạy trên account A
- nhưng denominator status bar lại bị kéo bởi account B/C

=> user rất dễ nghĩ “worker count bị bypass”, trong khi thực tế chỉ là:

- scheduler đang nhìn theo account-level health/capacity
- UI đang nhìn theo fleet-level aggregate

#### f. Kết luận multi-account

Khi dùng nhiều tài khoản, hiện có thêm 3 vấn đề semantics:

1. **aggregate capacity** đang cộng theo registered runtime accounts
2. **effective usable capacity** chưa được tách khỏi configured/registered capacity
3. **per-account contribution** không được hiển thị nên người dùng map nhầm từ task group sang fleet telemetry

Nói ngắn:

- status bar hiện tại **không phù hợp để suy luận trực tiếp số worker của một task group cụ thể trong multi-account mode**
- nó chỉ phù hợp như một fleet-level telemetry thô

---

## 9. Giải pháp đề xuất

## 9.1. P0 — Sửa bug tính `⚡ Fast`

Không dùng:

```python
active_fast = active_workers - active_lp
```

vì `active_workers` hiện đã là Fast-only theo source chain hiện tại.

Có 2 hướng an toàn:

### Hướng A — sửa ở UI, nhanh nhất

Đổi `ui/app.py`:

- dùng trực tiếp `active_fast = acc.get("active_workers", 0)`
- không trừ `active_lp` nữa

Ưu điểm:

- patch nhỏ
- ít ảnh hưởng

Nhược điểm:

- tên field `active_workers` vẫn gây hiểu nhầm

### Hướng B — sửa contract telemetry cho rõ nghĩa

Đổi `AppController.get_account_summary()` để trả rõ:

- `active_workers_fast`
- `active_workers_lp`
- `active_workers_upscale`
- `active_workers_total_held`
- `registered_capacity_fast`
- `effective_capacity_fast`
- `registered_capacity_lp`
- `effective_capacity_lp`

và UI chỉ render từ các field rõ nghĩa đó.

Ưu điểm:

- hết nhập nhằng dài hạn
- dễ debug hơn

Nhược điểm:

- scope lớn hơn chút

---

## 9.2. P1 — Thêm số tổng `Σ held`

Để tránh user phải tự cộng:

- thêm một số tổng slot đang giữ:
  - `Σ = fast + lp + upscale`

Ví dụ hiển thị:

```text
⚡ 0/20 | 🐢 8/12 | ⬆️ 5/8 | Σ 13
```

hoặc:

```text
⚡ 4/20 | 🐢 8/12 | ⬆️ 5/8 | Σ 17
```

tùy cách định nghĩa final sau khi sửa bug `⚡`.

---

## 9.3. P1 — Tách rõ “running tasks” khỏi “held slots”

Status bar nên hiển thị riêng:

- `running_tasks`
- `held_slots`

Ví dụ:

```text
🏃 17 tasks | ⚡ 4/20 | 🐢 8/12 | ⬆️ 5/8
```

Như vậy người xem sẽ không còn dùng số pool để suy ra số prompt đang chạy.

---

## 9.4. P2 — Đổi wording UI

Hiện label `workers` khiến user hiểu là:

- tổng worker toàn hệ thống

Nhưng thực tế nó là:

- pool occupancy

Nên đổi tooltip/help text thành:

- `⚡ Fast slots held`
- `🐢 LP slots held`
- `⬆️ Upscale slots held`

## 9.5. P2 — Tách `registered capacity` khỏi `effective capacity` trong multi-account mode

Đây là việc rất nên làm nếu dùng nhiều tài khoản.

Nên có đồng thời:

- `registered_accounts`
- `enabled_accounts`
- `ready_accounts`
- `registered_capacity`
- `effective_capacity`

Ví dụ:

```text
👤 2/3 ready | Fleet eff: ⚡ 4/28 | 🐢 8/12 | ⬆️ 5/8
```

hoặc nếu cần debug sâu:

```text
Fleet reg: ⚡ 4/40 | 🐢 8/16 | ⬆️ 5/16
Fleet eff: ⚡ 4/28 | 🐢 8/12 | ⬆️ 5/8
```

---

## 10. Khuyến nghị patch tối thiểu

Nếu muốn sửa nhanh và an toàn:

1. Trong `ui/app.py`, bỏ phép trừ `active_lp` khỏi `active_workers`.
2. Giữ nguyên `active_upscale` và `active_lp`.
3. Thêm tooltip giải thích 3 pool là 3 chỉ số tách biệt.
4. Thêm tooltip hoặc popup help cho biết:
   - `⚡` = Fast held slots
   - `🐢` = LP held slots
   - `⬆️` = Upscale held slots
   - các mẫu số là aggregate của nhiều profile/account
5. Nếu phát hiện profile cũ thiếu `max_workers_lp`, log rõ fallback:
   - `max_workers_lp missing -> fallback to max_workers`
6. Với multi-account, tooltip cần nói rõ:
   - `registered capacity, not per-group capacity`

Patch này chưa hoàn hảo về naming, nhưng đủ để:

- không còn `⚡ 0` giả
- không còn cảm giác “LP bypass”
- giảm hiểu nhầm khi nhìn status bar
- giảm hiểu nhầm nghiêm trọng khi chạy nhiều tài khoản

---

## 11. Khuyến nghị patch đúng kiến trúc

Nếu muốn sửa tận gốc:

1. Đổi contract trong `AppController.get_account_summary()`
   - `active_workers_fast`
   - `active_workers_lp`
   - `active_workers_upscale`
   - `active_slots_total`
   - `running_tasks`

2. Đổi `ui/app.py` để render từ các field này, không tự suy luận nữa.

3. Thêm tooltip/status help:
   - `slots held != visible prompts`
   - `output_count != slots held for full task lifetime`
   - `aggregate status bar != per-profile value`

4. Nếu cần, thêm một dòng debug trong DevConsole:
   - `fast=`
   - `lp=`
   - `upscale=`
   - `running_tasks=`
   - `queue_visible_processing=`
   - `profile_caps=`
   - `effective_caps=`
   - `registered_accounts=`
   - `enabled_accounts=`
   - `ready_accounts=`

---

## 12. Kết quả cần đạt sau khi sửa

Sau khi sửa đúng, hệ thống cần đạt:

- `⚡ Fast` không còn bị under-report do trừ LP hai lần.
- User không còn hiểu nhầm `8/12` là tổng worker.
- User hiểu rõ `12` là tổng LP cap của nhiều profile/account, không phải riêng task group đang nhìn.
- Queue UI và status bar không còn mâu thuẫn giả do khác semantics.
- Việc một task `output_count=4` chỉ giữ `1` slot pipeline sau submit được xem là hành vi đúng, không bị chẩn đoán nhầm là bypass.
- LP cap vẫn được giữ nguyên ở enforcement layer, chỉ telemetry được làm rõ.
- Profile cũ thiếu `max_workers_lp` không còn silently fallback mà không có dấu vết debug/telemetry.
- Khi dùng nhiều account, denominator không còn bị phình bởi account disabled/unready nếu UI đang hiển thị `effective capacity`.
- User phân biệt được:
  - per-profile cap
  - fleet registered cap
  - fleet effective cap
  - actual held slots

---

## 13. Kết luận cuối

Hiện tại:

- **không có bằng chứng số lượng LP/worker đang bị bypass ở engine/session**
- **có bug thật trong cách tính `⚡ Fast` của status bar**
- **LP cũng có vấn đề ở aggregate semantics và fallback mặc định**
- **có hiểu nhầm UI vì status bar đang hiển thị pool occupancy, không phải tổng prompt đang active**
- **khi dùng nhiều tài khoản, aggregate denominator còn có thể bị phình bởi registered runtime accounts thay vì effective ready/enabled accounts**

Vì vậy, vấn đề đúng nhất cần sửa là:

- **telemetry + status bar semantics + làm rõ luồng Settings/Profile -> Runtime -> Aggregate**

chứ không phải mở rộng thêm retry/recovery hay thay đổi worker admission logic.

---

## 14. Trường hợp `x/0` trên status bar

Sau khi đổi `effective capacity` sang nghĩa chặt hơn:

- `effective_* = READY accounts only`
- `ready = enabled + session healthy`

thì status bar **có thể** hiển thị các trạng thái như:

- `⚡ 5/0`
- `🐢 7/0`
- `⬆️ 5/0`

Đây là một hiện tượng cần giải thích riêng vì rất dễ bị hiểu nhầm là:

- worker pool đang vượt giới hạn
- hoặc scheduler đã bypass cấu hình

### 14.1. Vì sao `x/0` xuất hiện

Hiện tại hai vế của status bar được lấy từ **hai tập account khác nhau**:

#### a. Tử số `x`

Tử số là **slot đang được giữ thực tế** bởi các session/account tại thời điểm poll UI.

Ví dụ:

- `active_workers_fast`
- `active_workers_lp`
- `active_upscale`

được cộng trực tiếp từ session runtime của tất cả account.

Nguồn:

- `core/app_controller.py`

#### b. Mẫu số `0`

Mẫu số là **effective usable capacity**, hiện chỉ tính từ account:

- `is_ready == True`

Trong đó:

- `is_ready = enabled AND session.is_ready`

Nguồn:

- `core/account_manager.py`
- `core/multi_account.py`

### 14.2. Tình huống điển hình tạo ra `x/0`

Trạng thái `x/0` xuất hiện khi:

1. Trước đó account đang chạy bình thường và đã acquire slot.
2. Sau đó account bị rơi khỏi trạng thái `ready`.
3. Nhưng slot cũ chưa được release xong.

Ví dụ thực tế:

- browser vừa restart
- extension reconnect
- coordinator đang recovery hoặc quarantine
- session tạm thời mất healthy
- upscale/background worker đang drain dở
- task đang teardown hoặc decrement counter chưa chạy xong

Khi đó:

- **không còn account nào đủ điều kiện nhận việc mới** → denominator = `0`
- nhưng **vẫn còn slot cũ đang bị giữ** → numerator > `0`

### 14.3. `x/0` có phải là bypass giới hạn không

**Không mặc định là bypass.**

Trong đa số trường hợp, `x/0` chỉ có nghĩa là:

- `admission capacity = 0`
- nhưng `held slots > 0`

Tức là:

- hệ thống **không cho nhận task mới**
- nhưng các task cũ vẫn đang drain / recover / teardown

Đây là một mismatch về **telemetry semantics**, không phải tự động là lỗi enforcement.

### 14.4. Khi nào `x/0` là bình thường

`x/0` được xem là bình thường nếu:

- chỉ xuất hiện ngắn hạn
- giảm dần về `0/0`
- hoặc capacity quay lại > `0` sau reconnect/recovery

Ví dụ:

- account vừa restart browser
- session vừa mất `ready` trong lúc worker đang release slot
- coordinator đang block submit nhưng upscale/background job cũ vẫn đang hoàn tất

### 14.5. Khi nào `x/0` là bug thật

`x/0` nên được xem là bug nếu:

- giữ lâu không giảm
- queue đã rỗng nhưng held slots vẫn > `0`
- account đã recover xong nhưng counters không về đúng trạng thái
- AutoStop/Watchdog bị giữ bởi slot ma hoặc owner stale

Khi đó các nhóm lỗi cần audit là:

- thiếu decrement counter
- stale `background_owner`
- stuck UQ ownership / refcount
- session state đã `not-ready` nhưng worker teardown chưa clear
- coordinator recovery hoàn tất nhưng account/session counters chưa đồng bộ

### 14.6. Ảnh hưởng vận hành

Nếu để `x/0` hiển thị nguyên trạng, user rất dễ kết luận sai rằng:

- pool đang vượt cap
- worker bị bypass
- scheduler không tôn trọng config trong Settings

Hệ quả là:

- debug sai hướng
- tưởng cần sửa admission logic
- trong khi gốc thực tế là telemetry semantics hoặc stale drain state

### 14.7. Giải pháp UI/telemetry nên áp dụng

Giải pháp đúng nhất không phải là ép denominator về số khác cho "đẹp", mà là tách rõ ý nghĩa:

#### a. Giữ nguyên telemetry backend

Tiếp tục phân biệt:

- `held_*`
- `effective_*`
- `registered_*`
- `ready`

vì đây là các khái niệm cần thiết để debug đúng.

#### b. Đổi cách render khi `ready == 0 && total_held > 0`

Thay vì hiện:

- `⚡ 5/0`

nên render theo trạng thái rõ nghĩa hơn, ví dụ:

- `⚡ 5/draining`
- `🐢 7/draining`
- `⬆️ 5/draining`

hoặc:

- `⚡ 5/paused`
- `🐢 7/paused`
- `⬆️ 5/paused`

Điểm quan trọng là:

- phải cho user thấy đây là **slot cũ đang được giữ**
- không phải capacity mới đang được cấp phép

#### c. Tooltip phải giải thích rõ

Tooltip nên ghi rõ:

- `Ready = 0`
- `Held slots belong to non-ready accounts and are draining`
- `No new work can be admitted until an account becomes ready again`

#### d. Có thể thêm breakdown để debug

Nếu muốn hỗ trợ debug tốt hơn, DevConsole hoặc tooltip có thể thêm:

- `registered accounts`
- `enabled accounts`
- `ready accounts`
- `held by ready accounts`
- `held by non-ready accounts`

Như vậy user sẽ thấy ngay:

- account nào còn giữ slot
- nhưng không còn nằm trong `effective capacity`

### 14.8. Giải pháp backend nếu muốn triệt để hơn

Nếu muốn telemetry chặt hơn nữa, có thể bổ sung thêm contract:

- `held_fast_ready`
- `held_fast_non_ready`
- `held_lp_ready`
- `held_lp_non_ready`
- `held_upscale_ready`
- `held_upscale_non_ready`

Nhờ đó UI có thể render:

- `effective ready capacity`
- `draining from non-ready accounts`

mà không phải suy luận lại ở tầng UI.

### 14.9. Kết luận cho case `x/0`

Trạng thái `x/0`:

- **có thể xuất hiện hợp lệ**
- **không mặc định là bypass cap**
- **là dấu hiệu của việc numerator và denominator đang biểu diễn hai tập account khác nhau**

Điều đúng cần làm là:

- giải thích semantics rõ hơn trong UI
- hiển thị `draining/paused` thay vì `x/0` trần trụi khi `ready == 0`
- chỉ coi đó là bug backend khi slot không giảm, queue đã rỗng, hoặc owner/counter bị stale
