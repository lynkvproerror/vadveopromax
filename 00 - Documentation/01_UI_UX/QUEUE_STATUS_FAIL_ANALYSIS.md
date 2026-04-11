# Queue Status `FAIL` - Phân tích trường hợp xuất hiện và cách xử lý

Ngày cập nhật: 2026-04-11

## 1. Kết luận ngắn

Trong Queue hiện tại, chữ `FAIL` trong cột `Status` không chỉ có một nghĩa duy nhất. Có 2 nhóm chính:

1. `Task FAILED` thật sự
   - Backend đã chuyển `task.state = failed`.
   - Đây là lỗi mức task, thường cần `Retry prompt`, `Force Retry`, hoặc xử lý nguyên nhân gốc rồi chạy lại.

2. `Partial fail` sau khi task đã chạy xong phần lớn pipeline
   - Task có thể đã đi tới `completed` hoặc `progress >= 100`, nhưng một hoặc vài `video_outputs` vẫn lỗi.
   - UI vẫn hiển thị `⚠️ FAIL` màu vàng để báo bộ output chưa hoàn chỉnh.
   - Trường hợp này thường nên `Retry failed video(s)`, `Re-upscale failed`, hoặc `Re-download 720p`, không nhất thiết phải chạy lại toàn bộ prompt.

Ảnh người dùng gửi khớp nhất với nhánh thứ 2: `⚠️ FAIL` màu vàng, tức là hàng Queue đã có output/thumbnails nhưng bộ kết quả chưa hoàn chỉnh.

## 2. App xác định `FAIL` như thế nào

### 2.1. Backend truyền trạng thái task sang UI

Nguồn chính nằm ở:

- `02 - CLIENT - VEO PRO MAX/core/app_controller.py`
- `02 - CLIENT - VEO PRO MAX/core/queue_dto.py`

Khi build dữ liệu cho Queue, app đẩy:

- `status = task.state.value`
- `error = task.error`
- `status_text = task.status_text`
- `video_outputs[].quality`
- `video_outputs[].upscale_status`
- `video_outputs[].upscale_error`

Điểm quan trọng:

- `status == failed` là lỗi mức task.
- Nhưng ngay cả khi `status == completed`, UI vẫn có thể đổi badge sang `⚠️ FAIL` nếu phát hiện output con bị lỗi.

### 2.2. Luật render của UI

Nguồn chính:

- `02 - CLIENT - VEO PRO MAX/ui/tabs/queue_components/group_renderer.py`

UI xử lý theo thứ tự ưu tiên:

1. Nếu đang retry video con: hiển thị `RETRYING`
2. Nếu đang upscale: hiển thị trạng thái upscale
3. Nếu có `has_failed_outputs`: hiển thị `⚠️ FAIL` hoặc `⚠️ N/TOTAL FAIL`
4. Nếu hoàn tất sạch: hiển thị `✅ COMPLETED`
5. Nếu `status == failed`: hiển thị `❌ FAILED`
6. Nếu `status == completed` nhưng output chưa settle đủ: hiển thị `⚠️ INCOMPLETE`

Do đó:

- `❌ FAILED` và `⚠️ FAIL` là 2 trạng thái nhìn gần giống nhau nhưng bản chất khác nhau.
- Ảnh màu vàng thường là `partial fail`.

## 3. Nhóm 1 - `Task FAILED` thật sự

### 3.1. Dấu hiệu nhận biết

- `task.state == failed`
- Nút `Retry` trên hàng sẽ hiện ra
- Tooltip của badge lấy từ `task.error`
- App tính task này vào nhóm failed trong thống kê Queue

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/dispatcher.py`
- `02 - CLIENT - VEO PRO MAX/ui/tabs/tab_queue.py`
- `02 - CLIENT - VEO PRO MAX/ui/tabs/queue_components/group_renderer.py`

### 3.2. Điểm chuyển sang `FAILED`

Nguồn gốc chính là:

- `02 - CLIENT - VEO PRO MAX/core/dispatcher.py` - `fail_task()`

Hàm này:

- set `task.state = FAILED`
- ghi `task.error`
- đóng task bằng `completed_at`
- phát callback/UI event
- nếu task là cha của continuation chain thì cascade-fail các child đang chờ

### 3.3. Các nhóm nguyên nhân làm task rơi vào `FAILED`

#### A. Lỗi license / quyền tính năng

Ví dụ trong mã:

- đạt giới hạn ngày: `Daily limit reached (...)`
- continuation nhưng license không đủ: `Continuation requires Premium license`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Hướng xử lý:

- kiểm tra license/gói hiện tại
- giảm số prompt trong ngày nếu bị daily limit
- nếu là continuation nhưng tài khoản trial/free thì phải đổi sang account đủ quyền hoặc bỏ continuation

#### B. Thiếu dữ liệu đầu vào bắt buộc

Ví dụ:

- `I2V/R2V/F2V has no images (upload failed or image_paths empty)`
- `Continuation frame re-upload failed`
- `Continuation frame extraction failed (FFmpeg unavailable or download error)`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`
- `02 - CLIENT - VEO PRO MAX/core/dispatcher.py`

Hướng xử lý:

- kiểm tra ảnh đầu vào có còn tồn tại, đọc được, và upload thành công không
- với continuation: kiểm tra video cha đã có file thật chưa
- kiểm tra `ffmpeg` có sẵn và hoạt động nếu child task cần extract frame
- nếu file nguồn đã đổi/di chuyển, nên queue lại từ đầu thay vì retry mù

#### C. Hết phiên đăng nhập / token hỏng

Ví dụ:

- `auth error — please re-login manually via Browser button`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Đây là nhóm lỗi app cố ý không auto-fix triệt để.

Hướng xử lý:

- mở Browser của đúng account
- đăng nhập lại Google/VEO
- đảm bảo extension reconnect và header/token refresh bình thường
- sau đó `Retry` task failed

#### D. Lỗi submit/generate sau khi đã thử retry nhưng vẫn hết cách

Ví dụ:

- `... (after N retries)`
- `Worker returned no result`
- `Unexpected error: ...`
- `Pipeline error: ...`
- `Worker errors: ...`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Đây là nhóm fail tổng quát khi:

- worker không trả kết quả
- có exception bất ngờ trong pipeline
- tất cả retry submit đã cạn
- lỗi không còn được xếp vào nhánh auto-recovery tiếp theo

Hướng xử lý:

- xem `task.error` hoặc log để biết lỗi gốc
- nếu là lỗi transient kiểu 403/reCAPTCHA/network thì retry lại sau khi account/browser ổn định
- nếu lặp lại nhiều lần trên cùng prompt thì kiểm tra prompt, model, aspect ratio, account health

#### E. Toàn bộ operation poll đều fail hoặc poll timeout

Ví dụ:

- `All video operations failed`
- `Transient error after X/Y retries: ...`
- `Polling timeout (...)`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Hướng xử lý:

- nếu lỗi nghiêng về reCAPTCHA / 403 / timeout / network: retry task
- nếu lỗi lặp lại trên nhiều account: khả năng API/server-side instability
- nếu là continuation chain: retry root chain thay vì chỉ retry child cuối

#### F. Download 720p thất bại và không thể tự cứu nữa

Ví dụ:

- `Download failed (...), auto re-generation disabled`
- `Download retry X/Y exhausted`
- `Resume failed: no valid output files in checkpoint`
- `No output files (...)`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Hướng xử lý:

- nếu do toggle auto-retry-download đang OFF: bật lại hoặc force retry task
- nếu URL/file đã lỗi nhưng operation còn hợp lệ: ưu tiên `Re-download 720p`
- nếu checkpoint bị rỗng/hỏng: retry task hoặc force retry full

#### G. Request invalid ở pipeline ảnh

Ví dụ:

- `Invalid request: ...`
- `Image download failed after ... attempts`
- `T2I pipeline error: ...`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Hướng xử lý:

- kiểm tra model, aspect ratio, input image, prompt
- nếu là 400 cố định thì retry sẽ không giúp nhiều, nên sửa input rồi submit lại

## 4. Nhóm 2 - `⚠️ FAIL` kiểu partial fail

### 4.1. Dấu hiệu nhận biết

Trường hợp này UI badge vào nhánh:

- `has_failed_outputs == True`

Điều kiện:

- có `video_outputs[].quality == failed`
- hoặc `video_outputs[].upscale_status == failed`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/ui/tabs/queue_components/group_renderer.py`
- `02 - CLIENT - VEO PRO MAX/core/dispatcher.py`

Biểu hiện thường gặp:

- hàng vẫn có thumbnail/video ở một số slot
- nhưng badge hiện `⚠️ FAIL` hoặc `⚠️ x/y FAIL`
- màu thường là vàng
- tooltip sẽ ghi video nào lỗi

### 4.2. Partial fail thường đến từ đâu

#### A. Một số variant generate thành công, một số variant fail

Ví dụ:

- submit 4 outputs, chỉ 2-3 op thành công
- app tạo `video_outputs` đầy đủ theo index
- slot fail sẽ có `quality = failed`

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Hướng xử lý:

- ưu tiên `Retry failed video(s)`
- chỉ `Force Retry full task` nếu nghi prompt/context đã hỏng toàn cục

#### B. Download một phần thành công, một phần fail

Ví dụ:

- poll xong nhưng download local chỉ lưu được một vài file
- app đánh dấu phần thiếu để re-generate/retry

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Hướng xử lý:

- nếu app đã sinh replacement task thì chờ retry slot
- nếu còn treo partial fail lâu: dùng `Retry failed video(s)` hoặc `Force Retry`
- nếu operation còn tốt nhưng file local mất: dùng `Re-download 720p`

#### C. Upscale fail nhưng 720p/1K gốc vẫn có

Ví dụ:

- generation thành công
- file base quality có rồi
- nhưng upscale 1080p/2K/4K bị lỗi

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/dispatcher.py`
- `02 - CLIENT - VEO PRO MAX/core/engine.py`
- `02 - CLIENT - VEO PRO MAX/ui/tabs/queue_components/group_renderer.py`

Hướng xử lý:

- không cần chạy lại cả prompt
- dùng `Re-Upscale Failed`
- nếu cần làm lại toàn bộ upscale cho task đó thì dùng `Re-Upscale All`

## 5. Cách xử lý đúng theo từng tình huống

### 5.1. Nếu badge là `❌ FAILED`

Ưu tiên xử lý:

1. Hover xem tooltip để đọc `task.error`
2. Mở log để xác định lỗi thuộc nhóm nào:
   - auth/session
   - license
   - input thiếu
   - poll timeout / 403 / recaptcha
   - download exhausted
   - invalid request
3. Xử lý nguyên nhân gốc
4. Sau đó bấm:
   - `Retry` nếu muốn resume/checkpoint-aware retry
   - `Force Retry` nếu muốn reset mạnh và chạy lại từ đầu

### 5.2. Nếu badge là `⚠️ FAIL` màu vàng

Ưu tiên xử lý:

1. Hover badge để biết slot nào fail
2. Nếu lỗi là generate fail trên một vài slot:
   - dùng `Retry Failed Videos`
   - hoặc chuột phải `Retry N Failed Video(s)`
3. Nếu lỗi là upscale fail:
   - dùng `Re-Upscale Failed`
4. Nếu lỗi là mất file local nhưng generation đã có:
   - dùng `Re-download 720p`
5. Chỉ dùng `Force Retry (re-generate all)` khi:
   - quá nhiều slot fail
   - prompt bị nghi sai
   - kết quả đang lẫn giữa nhiều lần retry và muốn làm sạch toàn bộ

## 6. Những gì UI hiện hỗ trợ để cứu task

### 6.1. Với task failed/cancelled

Nguồn:

- `02 - CLIENT - VEO PRO MAX/ui/tabs/tab_queue.py`

Hỗ trợ:

- nút `Retry` ngay trên dòng
- nút `Retry Failed` ở toolbar
- context menu `Force Retry`

### 6.2. Với partial fail trong completed task

Nguồn:

- `02 - CLIENT - VEO PRO MAX/ui/tabs/queue_components/context_menu.py`
- `02 - CLIENT - VEO PRO MAX/ui/tabs/tab_queue.py`

Hỗ trợ:

- `Retry Failed Videos`
- `Retry N Failed Video(s)`
- `Re-Upscale Failed`
- `Re-Upscale All`
- `Re-download All 720p`

### 6.3. Auto-sweep

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/queue_controller.py`
- `02 - CLIENT - VEO PRO MAX/ui/tabs/tab_queue.py`

Auto-sweep quét lại:

- task `FAILED` để retry
- completed task có `quality=failed` để retry slot lỗi
- completed task có `upscale_status=failed` hoặc output thiếu để tiếp tục cứu

Điểm cần hiểu đúng:

- Auto-sweep là cơ chế hỗ trợ, không thay thế việc xử lý nguyên nhân gốc
- auth expired, thiếu input, license gate, invalid request vẫn sẽ fail lại nếu không sửa nguyên nhân

## 7. Phân biệt các trạng thái dễ nhầm

### `❌ FAILED`

- Task chết ở mức backend state machine
- `task.state == failed`
- Retry button xuất hiện

### `⚠️ FAIL`

- Task đã có output một phần nhưng bộ output chưa hoàn chỉnh
- Thường do một vài video fail hoặc upscale fail
- Nên ưu tiên cứu từng slot thay vì re-run cả task

### `⚠️ INCOMPLETE`

- Task `completed` nhưng output set chưa settle đủ
- Chưa chắc là fail hẳn
- Có thể do file chưa materialize đủ, upscale còn dang dở, hoặc metadata chưa hoàn chỉnh

### `⛔ POLICY VIOLATION`

- Đây là nhánh riêng
- Không nên retry mù
- Cần sửa prompt/nội dung

## 8. Quy trình vận hành khuyến nghị

### Trường hợp 1 - Chỉ 1-2 video lỗi, các video khác đã ra

Nên làm:

1. Chuột phải task
2. `Retry N Failed Video(s)`
3. Nếu lỗi nằm ở upscale thôi thì `Re-Upscale Failed`

Không nên:

- `Force Retry full task` ngay từ đầu, vì sẽ tốn thời gian và có thể tốn credit không cần thiết

### Trường hợp 2 - Cả task fail đỏ

Nên làm:

1. Đọc tooltip / log
2. Phân loại:
   - auth -> login lại
   - license -> đổi account/gói
   - input thiếu -> sửa input
   - timeout/403/network -> retry sau khi browser/account ổn
3. Bấm `Retry`
4. Chỉ dùng `Force Retry` nếu retry thường không đủ

### Trường hợp 3 - Upscale fail nhưng 720p vẫn có

Nên làm:

1. Không re-generate cả prompt
2. Dùng `Re-Upscale Failed`
3. Nếu media_id không còn hợp lệ hoặc account gốc không còn sẵn, kiểm tra lại account đã chạy task ban đầu

### Trường hợp 4 - Download/local file hỏng

Nên làm:

1. `Re-download 720p`
2. Nếu không cứu được và task đã rối nhiều lần retry, chuyển sang `Force Retry`

## 9. Kết luận cuối

Nếu nhìn đúng theo code hiện tại thì:

- `FAIL` trong Queue không đồng nghĩa 100% với "prompt chết hoàn toàn"
- phần lớn trường hợp badge vàng là "có output nhưng còn slot lỗi"
- badge đỏ `FAILED` mới là fail cứng ở mức task state

Vì vậy cách xử lý hiệu quả nhất là:

- fail đỏ: xử lý nguyên nhân gốc rồi retry task
- fail vàng: ưu tiên cứu theo slot (`Retry failed videos`, `Re-upscale failed`, `Re-download 720p`)

Nếu cần chẩn đoán nhanh một hàng Queue cụ thể, nên đọc theo thứ tự:

1. màu badge
2. tooltip của badge
3. `task.error` / `upscale_error`
4. log runtime gần thời điểm task đó fail

## 10. Giải pháp tự động: Auto-Retry Failed + On-the-fly Sweep

Ngày cập nhật: 2026-04-11

### 10.1. Vấn đề cần giải quyết

Hiện tại auto-sweep CHỈ chạy khi:

1. Queue hết task + post_queue_action = shutdown/sleep
2. Bấm Start All mà không còn task READY

Khi post_queue_action = "Do Nothing" (mặc định), partial fail nằm im cho đến khi user thủ công bấm retry. Điều này gây mất thời gian và bỏ sót video lỗi.

### 10.2. Giải pháp

Kết hợp 2 cơ chế:

#### A. Setting "Auto-Retry Failed" (ON/OFF)

Nguồn:

- `02 - CLIENT - VEO PRO MAX/config/settings.py`
- `02 - CLIENT - VEO PRO MAX/ui/tabs/settings_components/pipeline_enhancer.py`

Thêm toggle `auto_retry_failed: bool = True` trong Pipeline Optimization:

- Mặc định BẬT — app tự động xử lý mọi partial fail
- User tắt được nếu muốn kiểm soát thủ công
- Hiển thị ngay dưới Auto-Retry Download trong Settings

#### B. On-the-fly Auto-Sweep

Nguồn:

- `02 - CLIENT - VEO PRO MAX/core/app_controller.py`
- `02 - CLIENT - VEO PRO MAX/ui/tabs/tab_queue.py`

Auto-sweep chạy ngay trong khi engine đang xử lý (không đợi hết queue):

1. Hook vào `_check_auto_stop()` — trước khi engine quyết định dừng
2. Nếu `auto_retry_failed` = True và phát hiện incomplete work:
   - Phase 1: Retry tất cả FAILED tasks
   - Phase 2: Retry video slots có `quality=failed`
   - Phase 3: Re-upscale video có `upscale_status=failed`
   - Phase 4: Re-generate task thiếu `media_id`
3. Sau khi sweep inject new work → engine KHÔNG auto-stop mà tiếp tục xử lý
4. Throttle bằng `auto_sweep_max_rounds` (mặc định 5) để tránh loop vô hạn

### 10.3. Post-queue action tích hợp

Khi engine dừng, `_check_post_queue_action` cũng sweep nếu `auto_retry_failed` = True:

- Bất kể post_queue_action là "Do Nothing", "Sleep" hay "Shutdown"
- Đảm bảo không bỏ sót partial fail khi queue hoàn tất

### 10.4. Flow tự động

Kịch bản: 4 video submit, 2 thành công, 2 fail

1. Engine hoàn tất task → `_check_auto_stop()` phát hiện incomplete
2. On-the-fly sweep gọi `force_retry_all_failed_videos()` → tạo 2 replacement task
3. Engine nhận 2 task mới → tiếp tục xử lý thay vì dừng
4. Nếu 2 task mới lại fail → sweep round 2 retry tiếp
5. Tối đa 5 rounds → nếu vẫn fail thì dừng (tránh lãng phí credits/thời gian)

### 10.5. Các trường hợp KHÔNG tự retry

Auto-retry tôn trọng nguyên nhân gốc. Các trường hợp retry sẽ không có tác dụng:

- auth expired — cần user login lại
- license gate — cần đổi account/gói
- invalid request (400) — cần sửa prompt/input
- policy violation — cần sửa nội dung

Trong những trường hợp này, auto-retry sẽ fail lại và dừng sau max rounds. Log ghi lại đầy đủ lý do.

