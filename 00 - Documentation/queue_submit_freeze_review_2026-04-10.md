# Review treo/giật khi submit task group sang Queue

Date: 2026-04-10

Phạm vi: `02 - CLIENT - VEO PRO MAX`

Yêu cầu: review hiện tượng task group được submit từ các generation tab sang Queue bị treo đơ, giật, đứng hình trong chốc lát; lập báo cáo chi tiết có vị trí code; không sửa source code.

## Tóm tắt kết luận

Hiện tượng đang giống nghẽn `GUI thread` hơn là deadlock thật sự.

Chuỗi gây khựng nhiều khả năng là:

1. Generation tab submit trực tiếp trên main/UI thread.
2. Controller build toàn bộ batch theo kiểu synchronous, gồm cả tiền xử lý từng prompt.
3. Dispatcher chèn toàn bộ task theo kiểu synchronous.
4. Queue update invalidate cache snapshot của Queue và tính lại queue status ngay lập tức.
5. Nếu Queue đang mở, hoặc người dùng mở Queue ngay sau đó, Queue tab lại rebuild DTO snapshot và cập nhật nhiều widget tiếp tục trên UI thread.

Chuỗi này giải thích được cả 3 biểu hiện:

- app khựng ngay sau khi bấm Add to Queue
- UI giật khi tab Queue đang visible
- khi chuyển sang Queue sau lúc submit, app đứng hình ngắn rồi mới render tiếp

## Cách audit

- Review tĩnh code path từ generation tabs sang dispatcher rồi đến Queue UI
- Soát thêm log mẫu trong `logs/`
- Không thay đổi source code
- Không gắn profiler/instrumentation trong đợt review này

## Flow submit -> Queue đã xác nhận

1. `ui/tabs/generation_tab_base.py:784-884`
   `_on_add_to_queue()` bắt đầu tại L784, gọi thẳng controller method tại L871-873, sau đó tiếp tục clear/toast/auto-start đến L884. Không có bước handoff sang worker thread trước khi submit.

2. Các entry point của từng tab đều đổ về common submit path:
   `core/app_controller.py:3873-3879`
   `core/app_controller.py:3981-3988`
   `core/app_controller.py:4026-4034`
   `core/app_controller.py:4132-4137`
   `core/app_controller.py:4161-4165`

3. Common submit path:
   `core/app_controller.py:3555-3852`

4. Dispatcher insert:
   `core/dispatcher.py:545-556`
   `core/dispatcher.py:474-519`

5. Queue update notification:
   `core/app_controller.py:4876-4897`

6. Queue refresh path:
   `ui/tabs/tab_queue.py:432-434`
   `ui/tabs/tab_queue.py:1620-1680`
   `core/app_controller.py:5377-5493`
   `ui/tabs/tab_queue.py:1725-1860`

## Finding 1 - [P1] Common submit path đang chặn UI thread

Vị trí code chính:

- `ui/tabs/generation_tab_base.py:871-873`
- `core/app_controller.py:3555-3852`
- `core/dispatcher.py:545-556`
- `core/dispatcher.py:474-519`

Điểm chính:

`_on_add_to_queue()` gọi controller trực tiếp từ tab. Sau đó common controller path làm một lượng việc đáng kể theo kiểu synchronous trước khi event loop được trả lại cho Qt.

Các đoạn nóng trong `submit_prompts(...)`:

- `core/app_controller.py:3630-3771`
  loop qua toàn bộ prompt và tạo `Task`
- `core/app_controller.py:3667-3682`
  kiểm tra từng image URI bằng `Path.exists()` để tách local path và remote URI
- `core/app_controller.py:3691-3712`
  regex-scan tag trong prompt rồi resolve qua `ImageLibrary`
- `core/app_controller.py:3715-3765`
  auto-switch workflow/model theo từng task
- `core/app_controller.py:3773-3788`
  ép continuation rule trên toàn batch
- `core/app_controller.py:3794-3807`
  ghi log chi tiết cho cả group và từng task
- `core/app_controller.py:3809-3845`
  build full JSON preview cho Dev Console
- `core/app_controller.py:3847-3850`
  submit toàn group và gọi queue update ngay lập tức

Phần Dispatcher cũng là synchronous:

- `core/dispatcher.py:545-556`
  `submit_task_group()` loop qua toàn bộ task trong group. Lưu ý: `self._lock` chỉ guard phần `_task_groups[group.id] = group` (L547-549), còn vòng `for task in group.tasks: self.submit_task(task)` (L553-554) chạy ngoài lock, tức là mỗi task được insert riêng lẻ mà không batch.
- `core/dispatcher.py:474-519`
  `submit_task()` chèn từng task vào dict/queue nội bộ

Vì sao khớp với triệu chứng:

Click submit đang chạy ngay trên thread chịu trách nhiệm paint UI. Batch càng lớn, càng nhiều image/tag, càng nhiều object/log/preview phải dựng thì khoảng đứng hình càng rõ.

## Finding 2 - [P1] Các image-based tab còn làm thêm preprocessing đồng bộ trước khi vào common submit path

Vị trí code chính:

- `core/app_controller.py:3881-3923`
- `core/app_controller.py:3937-3978`
- `core/app_controller.py:3990-4034`
- `core/app_controller.py:4146-4160`

Điểm chính:

I2V, R2V, I2I không chỉ bị chậm ở common submit path, mà còn trả thêm chi phí đồng bộ trước đó.

Phần việc đáng chú ý:

- `_resolve_tags_to_paths()` làm library lookup và path check
- `add_i2v_batch()` resolve tag theo từng prompt và kiểm tra local file path
- `add_r2v_batch()` build per-prompt image map và voice map
- `add_i2i_batch()` resolve và validate image theo kiểu synchronous

Vì sao khớp với triệu chứng:

Nếu người dùng thấy các tab có ảnh lag rõ hơn T2V thuần text thì đây là một nguyên nhân rất hợp lý. Nút submit đã mất thêm chi phí filesystem/tag-resolution trước khi vào luồng insert queue chung.

## Finding 3 - [P1] Mỗi lần submit đều invalidate Queue cache và tính lại trạng thái bằng cách scan toàn bộ task

Vị trí code chính:

- `core/app_controller.py:4876-4879`
- `core/app_controller.py:5117-5136`
- `core/dispatcher.py:1603-1616`
- `core/app_controller.py:5204-5207`

Điểm chính:

Sau khi submit, `_notify_queue_updated()` lập tức:

- invalidate cached Queue group snapshot
- gọi `get_queue_status()`
- broadcast callback update

`get_queue_status()` lại gọi `dispatcher.get_status_summary()`, còn `get_status_summary()` thì loop qua `self._all_tasks.values()` để đếm state.

Nghĩa là độ trễ sau submit không chỉ phụ thuộc số task mới thêm. Nó còn tăng theo tổng queue hiện có trong memory. `get_status_summary()` là O(total_tasks) — đây là contributing cost, còn bottleneck nặng hơn nằm ở callback chain và Queue DTO/widget rebuild phía sau.

Nuance quan trọng:

`get_queue_groups()` có TTL cache tại `core/app_controller.py:5377-5407`, nhưng `_notify_queue_updated()` xóa cache đó ngay ở `core/app_controller.py:5204-5207`. Vì vậy sau submit, lần refresh Queue kế tiếp có xu hướng bị buộc rebuild mới hoàn toàn thay vì tận dụng snapshot vừa cache.

Vì sao khớp với triệu chứng:

Nếu queue càng lớn thì submit càng khựng, đoạn code này giải thích trực tiếp điều đó. Mỗi lần submit đều kèm whole-queue status accounting và ép lần refresh kế tiếp build lại snapshot Queue.

## Finding 4 - [P1] Queue tab refresh đang rebuild DTO và widget state trên UI thread

Vị trí code chính:

- `ui/tabs/tab_queue.py:432-434`
- `ui/tabs/tab_queue.py:1629-1631`
- `ui/tabs/tab_queue.py:1674-1680`
- `ui/tabs/tab_queue.py:1691-1697`
- `core/app_controller.py:5409-5493`
- `ui/tabs/tab_queue.py:1725-1860`

Điểm chính:

Khi Queue nhận update, refresh path vẫn chạy trên GUI thread:

- `_on_queue_updated()` chỉ schedule throttled refresh
- `_refresh_queue_from_controller()` kéo `groups_data`
- `get_queue_groups()` rebuild hierarchical DTO tree nếu cache vừa bị invalidate
- `_refresh_groups()` sync project, index, stale group removal, QueueItem tracking và group widget

Các đoạn nặng:

- `core/app_controller.py:5409-5493` (`_build_queue_groups()`)
  duyệt toàn bộ group/task visible, sort lại, rồi build DTO dict cho từng task
- `ui/tabs/tab_queue.py:1756`
  clear `_item_widgets`
- `ui/tabs/tab_queue.py:1764-1766`
  chỉ bắt đầu lazy behavior khi queue vượt 50 task (`use_lazy = total_tasks > 50`)
- `ui/tabs/tab_queue.py:1788-1792`
  group có 100 task trở xuống vẫn rebuild child row ngay trên GUI thread (`if _group_size > 100: ... else: _rebuild_group_children`)

Vì sao khớp với triệu chứng:

Ngay cả group cỡ vừa vẫn bị rebuild synchronous. Vì thế UI có thể giật dù queue chưa phải "siêu lớn". Ngưỡng async hiện tại chỉ cứu khi group đã khá to.

## Finding 5 - [P1] Nếu Queue đang ẩn thì refresh bị dồn lại, rồi bắn ngay khi người dùng mở Queue

Vị trí code chính:

- `ui/tabs/tab_queue.py:1629-1631`
- `ui/tabs/tab_queue.py:1691-1697`

Điểm chính:

Nếu Queue không visible tại thời điểm submit, `_refresh_queue_from_controller()` không refresh ngay mà set `_refresh_hidden_pending = True`.

Khi tab Queue được mở, `showEvent()` sẽ schedule `_refresh_queue_from_controller()` ngay bằng `QTimer.singleShot(0, ...)`.

Vì sao khớp với triệu chứng:

Điều này tạo ra đúng kiểu trải nghiệm mà user mô tả:

- submit từ tab khác có vẻ vẫn chạy
- phần nặng của Queue bị dời lại
- lúc vừa mở Queue thì app khựng ngắn rồi mới hiện nội dung

Nói cách khác, hiện tượng "submit từ tab sang Queue bị treo đơ" hoàn toàn khớp với cơ chế defer rồi flush ngay này.

## Finding 6 - [P2] Dev Console làm tăng thêm chi phí trên hot path khi submit

Vị trí code chính:

- `core/app_controller.py:3809-3845`
- `ui/tabs/tab_devconsole.py:507-529`
- `ui/tabs/devconsole/page_logs.py:303-310`
- `ui/tabs/devconsole/page_queue.py:92-104`
- `ui/app.py:373-404`

Điểm chính:

Nếu role hiện tại có Dev Console, submit path sẽ build full preview payload chứa toàn bộ task mới rồi đẩy sang UI của Dev Console.

`page_logs.update_json_preview()` làm trực tiếp:

- `json.dumps(data, indent=2, ensure_ascii=False, default=str)`
- `setPlainText(formatted)`

Code tại `app_controller.py:3837-3838` check `QThread.currentThread() == self._dev_console.thread()` rồi gọi `update_json_preview(preview)` trực tiếp. Trong user-submit path đang review, submit flow chạy trên main/UI thread nên điều kiện này luôn `True`, nghĩa là `json.dumps` + `setPlainText` chạy synchronous trước khi dispatcher insert diễn ra (L3847). Điều này đúng cho user-submit path hiện đang review.

Vì sao khớp với triệu chứng:

Đây có thể không phải nguyên nhân duy nhất, nhưng nó làm freeze nặng hơn khi submit group lớn, đặc biệt ở session tester/dev-console.

## Những gì chưa thấy

- Chưa thấy dấu hiệu deadlock thuyết phục trong submit flow này.
- Chưa thấy chỗ `wait()` hoặc `join()` dài ở đường submit -> queue đã review.
- Triệu chứng phù hợp với việc dồn quá nhiều synchronous work lên Qt GUI thread hơn là lock contention.

## Bằng chứng runtime đã lấy được

Log mẫu xác nhận submit path:

- `logs/dev_logs_20260405_034252.txt:19854`
  `[ADD TO QUEUE] group_id=group_20260405_034044`

Giới hạn của log hiện có:

- Không thấy được line timing hữu ích kiểu `[QueueDTO]` hoặc `[QueueRefresh]` trong các file log mẫu đã soát.
- Trong code, các line timing đó đang là mức `debug` tại `core/app_controller.py:5488-5492`, nên nhiều khả năng chưa được bật ở các run đã capture.

Vì vậy báo cáo này có độ tin cậy cao ở phần code-path analysis, còn phần timing runtime hiện bị giới hạn bởi mức log đang có.

## Tiêu chí verify sau fix

Trước khi sửa, cần chốt 3 điểm đo để biết fix nào thực sự ăn tiền:

1. **Thời gian `submit_prompts()`**: đo từ entry đến return, bao gồm batch build + dev console preview + dispatcher insert + `_notify_queue_updated()`.
2. **Thời gian `_notify_queue_updated()` / `get_queue_status()`**: tách riêng cost của invalidate cache + `get_status_summary()` + callback broadcast.
3. **Thời gian `get_queue_groups()` / `_refresh_groups()`**: đo khi Queue visible vs hidden, để xác nhận defer-and-flush có đúng là bottleneck.

Test matrix:

- Queue tab hidden vs visible lúc submit
- Dev Console on vs off
- Batch size nhỏ (5 prompt) vs lớn (100+ prompt)
- Queue đang trống vs đang có 500+ task

Phần đo này không phải blocker để bắt đầu code fix, nhưng sẽ giúp xác nhận fix nào thực sự hiệu quả.

## Kết luận cuối

Giải thích hợp lý nhất là bottleneck hai tầng trên GUI thread:

1. tầng submit: build batch + notify queue theo kiểu synchronous
2. tầng queue: rebuild DTO + refresh widget theo kiểu synchronous

Vấn đề không nằm ở một line đơn lẻ. Nó là phần cộng dồn của nhiều đoạn synchronous work liên tiếp:

- generation tab submit
- controller batch preprocessing
- dispatcher insertion
- queue-status recomputation ngay sau submit
- ép rebuild Queue snapshot sau khi invalidate cache
- Queue widget refresh trên main thread

Root cause map đã đủ rõ để bắt đầu fix có mục tiêu.

Không có source file nào bị sửa trong đợt review này.
