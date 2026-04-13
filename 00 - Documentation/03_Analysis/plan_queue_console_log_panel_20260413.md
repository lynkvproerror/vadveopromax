# Kế Hoạch Bổ Sung Khung Console Log Ở Tab Queue

## Mục tiêu

Tài liệu này mô tả kế hoạch bổ sung một khung `Console Log` trong tab `Queue` để người dùng phổ thông có thể:

- xem nhanh trạng thái đang diễn ra của hàng đợi;
- biết app đang kết nối với trình duyệt và extension ra sao;
- hiểu rõ việc gửi `prompt` / `upscale` thành công hay thất bại;
- đọc lỗi theo ngôn ngữ đơn giản, không cần hiểu thuật ngữ kỹ thuật;
- mở rộng / thu gọn khung log khi cần, tránh làm rối giao diện chính.

Phạm vi tài liệu này chỉ là **kế hoạch triển khai**.  
**Không sửa code trong tài liệu này.**

---

## Hiện trạng code liên quan

### 1. Tab Queue đã có luồng callback thời gian thực

File: [tab_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:216)

Các điểm đã có sẵn:

- `set_queue_updated_callback(...)` ở [tab_queue.py:219](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:219)
- `set_progress_callback(...)` ở [tab_queue.py:220](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:220)
- bridge từ worker thread sang UI qua `_progress_signal` ở [tab_queue.py:223](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:223)
- xử lý progress tập trung ở `_on_progress_update(...)` tại [tab_queue.py:233](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:233)

Ý nghĩa:

- tab `Queue` hiện đã nhận được phần lớn các cập nhật cần thiết theo thời gian thực;
- có thể tận dụng luồng callback hiện tại để bơm dữ liệu vào một khung `Console Log` riêng, không cần phát minh lại luồng dữ liệu từ đầu.

### 2. Tab Queue hiện chỉ cập nhật trạng thái ngắn trên từng task

File: [tab_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:346)

Đoạn [tab_queue.py:346-370](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:346) cho thấy UI hiện đang ưu tiên cập nhật `status_text` cho từng hàng task.

Điểm hạn chế:

- người dùng chỉ thấy trạng thái ngắn gắn vào từng task;
- không có một vùng log tập trung để đọc diễn biến hệ thống;
- nhiều message hiện tại còn mang tính kỹ thuật hoặc dùng icon / wording nội bộ.

### 3. Dự án đã có mẫu vùng text log/card đơn giản

File: [page_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/devconsole/page_queue.py:33)

Các đoạn tham chiếu hữu ích:

- layout card + splitter ở [page_queue.py:33-58](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/devconsole/page_queue.py:33)
- `QPlainTextEdit` read-only ở [page_queue.py:60-88](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/devconsole/page_queue.py:60)

Ý nghĩa:

- có thể tái sử dụng pattern `QFrame + QPlainTextEdit` cho log console;
- phù hợp để tạo một khung log đơn giản, dễ bảo trì, không cần một hệ thống widget quá phức tạp.

### 4. AppController đã có callback trạng thái cấp app

File: [app_controller.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py:6374)

Các điểm có thể tận dụng:

- `set_progress_callback(...)` ở [app_controller.py:6374](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py:6374)
- `set_status_callback(...)` ở [app_controller.py:6385](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py:6385)

Ý nghĩa:

- ngoài trạng thái gắn theo task, hệ thống cũng đã có chỗ để phát đi trạng thái tổng quát;
- đây là điểm phù hợp để bổ sung message cấp app như kết nối browser / extension.

### 5. Nguồn message kỹ thuật hiện phân tán ở nhiều nơi

Nguồn quan trọng:

- `extension_bridge` cho app ↔ extension ↔ browser:
  - [extension_bridge.py:2240-2338](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py:2240)
- `upscale_queue` cho upscale submit / pause / resume / progress:
  - [upscale_queue.py:549-603](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py:549)
  - [upscale_queue.py:2562-2565](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py:2562)
- `extension_bridge` cũng đang chứa readiness / cache / reCAPTCHA state:
  - [extension_bridge.py:644-687](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py:644)
  - [extension_bridge.py:2317-2338](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py:2317)

Điểm hạn chế hiện tại:

- message đang thiên về debug nội bộ;
- nhiều từ quá kỹ thuật;
- người dùng phổ thông khó hiểu trạng thái thực tế là “ổn”, “chưa sẵn sàng”, hay “lỗi”.

---

## Vấn đề UX hiện tại

Nếu dùng trực tiếp log kỹ thuật hiện tại trong tab `Queue`, người dùng sẽ gặp các vấn đề:

- quá nhiều chữ chuyên môn như `x-client-data`, `x-browser-validation`, `probe`, `polling`, `pending request`, `inflight`, `warmth`;
- khó biết điều gì là quan trọng nhất;
- cùng một ý nghĩa nhưng lại xuất hiện bằng nhiều kiểu câu khác nhau;
- không rõ message nào là thông báo bình thường, message nào là lỗi;
- không có vùng riêng để xem lịch sử diễn biến theo thời gian.

Vì vậy cần một lớp **rút gọn và dịch lại thông điệp** cho người dùng thường.

---

## Đề xuất UI/UX

### 1. Thêm khung `Console Log` trong tab Queue

Đề xuất bổ sung một khung mới nằm trong tab `Queue`, có thể:

- `Thu gọn` mặc định để giao diện không bị nặng;
- `Mở rộng` khi người dùng cần xem chi tiết;
- hiển thị các dòng log mới nhất theo thời gian;
- tự cuộn xuống dòng mới nhất;
- giới hạn số dòng để tránh nặng UI.

### 2. Cách bố trí đề xuất

Phương án khuyến nghị:

- đặt `Console Log` ở phần dưới của tab `Queue`;
- bên trên vẫn là danh sách task/group như hiện tại;
- bên dưới là một `QFrame` riêng chứa:
  - tiêu đề `Console Log`;
  - nút `Mở rộng / Thu gọn`;
  - nút `Xóa log`;
  - vùng `QPlainTextEdit` chỉ đọc.

Lý do:

- ít ảnh hưởng đến cấu trúc task list hiện tại;
- dễ dùng với người mới;
- không làm thay đổi mạnh flow làm việc hiện có.

### 3. Hành vi mở rộng / thu gọn

Khuyến nghị:

- mặc định ở trạng thái `Thu gọn`;
- khi thu gọn: chỉ hiện một header mỏng với 1 dòng trạng thái gần nhất;
- khi mở rộng: hiện toàn bộ vùng log;
- lưu lại trạng thái mở / đóng trong session UI nếu cần.

---

## Luồng dữ liệu đề xuất

### Phương án nên dùng

Tạo một lớp dữ liệu log đơn giản cho Queue UI, ví dụ logic theo hướng:

1. Nguồn kỹ thuật phát ra event / progress như hiện tại.
2. Một lớp chuyển đổi message sẽ:
   - nhận message kỹ thuật;
   - phân loại nhóm message;
   - rút gọn câu;
   - đưa ra bản thân thiện với người dùng.
3. Tab `Queue` nhận bản log đã rút gọn và append vào `Console Log`.

### Không nên làm

Không nên đổ thẳng raw log kỹ thuật từ logger vào `QPlainTextEdit`, vì:

- quá ồn;
- khó lọc;
- khó kiểm soát wording;
- dễ làm UI thành “bản sao debug console”, không phải console cho người dùng.

### Cấu trúc log đề xuất

Mỗi dòng nên có dạng:

```text
[11:33:21] [Browser] Đã kết nối
[11:33:25] [XCD] Đã sẵn sàng
[11:33:27] [reCAPTCHA] Chưa đủ điều kiện
[11:33:39] [Submit Prompt] Thành công
[11:34:10] [Upscale] Đang xử lý 2/4
[11:34:50] [Lỗi] Không thể gửi upscale, vui lòng thử lại
```

### Nhóm log cần hỗ trợ

1. `Kết nối`
2. `XCD`
3. `Token`
4. `reCAPTCHA`
5. `Submit Prompt`
6. `Upscale`
7. `Tải xuống`
8. `Lỗi`

---

## Quy tắc đơn giản hoá thông điệp

### 1. Quy tắc đặt tên ngắn

Không hiển thị nguyên văn tên kỹ thuật dài nếu không cần thiết.

Khuyến nghị:

- `x-client-data` → `XCD`
- `access token` → `Token`
- `grecaptcha` / `recaptcha` → `reCAPTCHA`
- `extension bridge` → `Extension`
- `browser headers` → `Trình duyệt`

### 2. Quy tắc trạng thái dễ hiểu

Chỉ dùng từ ngắn, rõ:

- `Đã kết nối`
- `Mất kết nối`
- `Đang chờ`
- `Đang xử lý`
- `Đã sẵn sàng`
- `Chưa sẵn sàng`
- `Thành công`
- `Thất bại`
- `Tạm dừng`
- `Đang khôi phục`

### 3. Không dùng thuật ngữ nội bộ

Không nên hiện trực tiếp các từ sau cho người dùng thường:

- `probe`
- `polling`
- `pending`
- `inflight`
- `warmth`
- `headers captured`
- `startup probe`
- `retry escalation`
- `stale cache`

Các từ này nên được quy đổi sang ý nghĩa dễ hiểu hơn.

### 4. Mỗi log chỉ nên nói 1 ý

Không gộp nhiều ý kỹ thuật vào cùng một câu dài.

Ví dụ:

- Không nên: `Extension connected, startup headers refreshed, x-browser-validation captured`
- Nên tách:
  - `Extension đã kết nối`
  - `Trình duyệt đã sẵn sàng`
  - `XCD đã sẵn sàng`

---

## Bảng mapping thông điệp kỹ thuật sang thông điệp người dùng

### 1. Kết nối app ↔ browser

| Kỹ thuật | Hiển thị cho người dùng |
|----------|--------------------------|
| Browser launched | `Trình duyệt đã mở` |
| Browser connected | `Trình duyệt đã kết nối` |
| Browser disconnected | `Trình duyệt bị ngắt kết nối` |
| Tab reloading | `Trình duyệt đang tải lại` |
| Browser recovered | `Trình duyệt đã khôi phục` |

### 2. Kết nối app ↔ extension

| Kỹ thuật | Hiển thị cho người dùng |
|----------|--------------------------|
| Extension connected | `Extension đã kết nối` |
| Extension registered | `Extension đã sẵn sàng` |
| Extension disconnected | `Extension bị ngắt kết nối` |
| Bridge connected | `App đã kết nối với extension` |
| No extension bridge | `Chưa kết nối được extension` |

### 3. XCD / token / reCAPTCHA

| Kỹ thuật | Hiển thị cho người dùng |
|----------|--------------------------|
| x-client-data ready | `XCD = Đã sẵn sàng` |
| x-client-data short / missing | `XCD = Chưa sẵn sàng` |
| access token ready | `Token = Đã sẵn sàng` |
| token short / invalid | `Token = Chưa đủ điều kiện` |
| reCAPTCHA ready | `reCAPTCHA = Đã sẵn sàng` |
| reCAPTCHA not ready | `reCAPTCHA = Chưa sẵn sàng` |
| short token | `reCAPTCHA = Chưa đủ điều kiện` |

### 4. Submit prompt / submit upscale

| Kỹ thuật | Hiển thị cho người dùng |
|----------|--------------------------|
| submit_prompt success | `Submit Prompt = Thành công` |
| submit_prompt fail | `Submit Prompt = Thất bại` |
| submit_upscale success | `Submit Upscale = Thành công` |
| submit_upscale fail | `Submit Upscale = Thất bại` |
| request queued | `Yêu cầu đã vào hàng đợi` |
| waiting before submit | `Đang chờ để gửi yêu cầu` |

### 5. Upscale progress

| Kỹ thuật | Hiển thị cho người dùng |
|----------|--------------------------|
| upscaling 1080p | `Upscale = Đang xử lý` |
| upscaling 2/4 | `Upscale = Đang xử lý 2/4` |
| download upscaled videos | `Đang tải video đã upscale` |
| upscale paused recovery | `Upscale = Tạm dừng để khôi phục` |
| upscale success | `Upscale = Hoàn tất` |

### 6. Lỗi đơn giản hoá

| Lỗi kỹ thuật | Hiển thị cho người dùng |
|-------------|--------------------------|
| 403 / unauthorized | `Không thể gửi yêu cầu, vui lòng thử lại` |
| missing header | `Trình duyệt chưa sẵn sàng` |
| no extension | `Chưa kết nối được extension` |
| recaptcha unhealthy | `reCAPTCHA chưa sẵn sàng` |
| account paused recovery | `Tài khoản đang được khôi phục` |
| task not found | `Không tìm thấy tác vụ` |

---

## Đề xuất phạm vi hiển thị log

### Nên hiển thị

- thay đổi trạng thái kết nối quan trọng;
- trạng thái XCD / Token / reCAPTCHA;
- submit prompt / submit upscale thành công hoặc thất bại;
- lỗi đơn giản dễ hiểu;
- trạng thái khôi phục khi queue bị tạm dừng;
- mốc tiến trình quan trọng như:
  - đã gửi yêu cầu;
  - đang upscale;
  - đang tải về;
  - đã hoàn tất.

### Không nên hiển thị

- message spam theo từng poll ngắn;
- chi tiết cache nội bộ;
- các log lặp lại liên tục cùng một nội dung;
- debug verbose như `requestId`, `inflight`, `headers_updated_at`, `cache invalidated`, `probe attempt`, nếu không có giá trị trực tiếp với người dùng.

---

## Thiết kế xử lý log đề xuất

### 1. Tạo một lớp chuẩn hoá thông điệp

Khuyến nghị thêm một lớp hoặc helper chuyên cho Queue log, ví dụ theo vai trò:

- nhận message từ `AppController`, `ExtensionBridge`, `UpscaleQueue`, `Dispatcher`;
- phân loại message thành loại đơn giản;
- map sang câu hiển thị cho người dùng;
- đẩy bản đã chuẩn hoá vào Queue UI.

Lý do:

- giữ cho `tab_queue.py` không bị ôm quá nhiều logic parse chuỗi kỹ thuật;
- dễ thêm / sửa từ điển mapping sau này;
- dễ test.

### 2. Dữ liệu log nên có cấu trúc

Khuyến nghị một bản ghi log gồm:

- `timestamp`
- `category`
- `level`
- `task_id` hoặc `group_id` nếu có
- `raw_message`
- `user_message`

Nhờ đó:

- UI có thể hiển thị câu rút gọn;
- vẫn giữ được raw message nội bộ nếu sau này cần debug nâng cao.

### 3. Chống spam log

Nên có 3 cơ chế:

- giới hạn số dòng, ví dụ giữ 300–500 dòng mới nhất;
- chống lặp message giống nhau trong một khoảng ngắn;
- gộp progress quá dày thành các mốc có ý nghĩa.

Ví dụ:

- giữ `Upscale = Đang xử lý 1/4`, `2/4`, `3/4`, `Hoàn tất`
- bỏ qua hàng chục message poll trung gian không đổi ý nghĩa.

---

## Vị trí code nên can thiệp khi triển khai

### 1. UI của Queue tab

File chính: [tab_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:66)

Vai trò:

- thêm `Console Log` frame vào layout của Queue tab;
- xử lý nút mở rộng / thu gọn;
- append dòng log vào vùng text;
- giới hạn số dòng;
- auto-scroll.

Điểm cần móc:

- callback registration ở [tab_queue.py:216-227](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:216)
- xử lý progress ở [tab_queue.py:233-304](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py:233)

### 2. Mẫu text console/card

File tham chiếu: [page_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/devconsole/page_queue.py:60)

Vai trò:

- tái sử dụng pattern `QFrame + QPlainTextEdit`;
- giúp giữ thiết kế nhất quán với phần DevConsole hiện có.

### 3. Nguồn event cấp app

File: [app_controller.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py:6374)

Vai trò:

- phát các status tổng quát;
- bổ sung message cấp app như:
  - app đã kết nối browser;
  - app đã kết nối extension;
  - queue đã bắt đầu;
  - queue đã dừng;
  - submit thành công / thất bại.

### 4. Nguồn event app ↔ extension ↔ browser

File: [extension_bridge.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py:2240)

Vai trò:

- cung cấp các mốc:
  - extension kết nối;
  - extension mất kết nối;
  - tab reloading;
  - reCAPTCHA readiness;
  - XCD / token readiness.

### 5. Nguồn event upscale

File: [upscale_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py:549)

Vai trò:

- phát các mốc:
  - account bị pause / unpause;
  - submit upscale;
  - đang upscale;
  - đang tải về;
  - hoàn tất / thất bại.

---

## Kế hoạch triển khai theo giai đoạn

### Giai đoạn 1: Bổ sung UI khung log

Mục tiêu:

- tạo khung `Console Log`;
- hỗ trợ mở rộng / thu gọn;
- hỗ trợ vùng text log read-only;
- có nút `Xóa log`.

Kết quả mong muốn:

- người dùng nhìn thấy một vùng log tập trung trong tab Queue;
- giao diện vẫn gọn khi log bị thu gọn.

### Giai đoạn 2: Tạo lớp chuẩn hoá message

Mục tiêu:

- xây một nơi duy nhất để map từ message kỹ thuật sang message người dùng;
- chuẩn hoá category và wording;
- chặn log quá kỹ thuật lọt ra UI.

Kết quả mong muốn:

- cùng một trạng thái chỉ có một cách diễn đạt;
- dễ chỉnh sửa wording cho toàn bộ app.

### Giai đoạn 3: Gắn các nguồn sự kiện chính

Mục tiêu:

- nối `AppController`, `ExtensionBridge`, `UpscaleQueue` vào lớp chuẩn hoá;
- đưa các mốc quan trọng vào Queue log.

Kết quả mong muốn:

- người dùng thấy đủ những gì cần biết mà không bị quá tải.

### Giai đoạn 4: Chống spam và làm gọn

Mục tiêu:

- chống trùng log;
- gom các cập nhật quá dày;
- chỉ giữ lại message có giá trị với người dùng.

Kết quả mong muốn:

- log dễ đọc, không biến thành debug stream.

---

## Bộ thông điệp tối thiểu khuyến nghị

Đây là tập message nên có ngay ở bản đầu:

### Kết nối

- `Trình duyệt đã mở`
- `Trình duyệt đã kết nối`
- `Trình duyệt đang tải lại`
- `Extension đã kết nối`
- `Extension bị ngắt kết nối`

### Trạng thái sẵn sàng

- `XCD = Đã sẵn sàng`
- `XCD = Chưa sẵn sàng`
- `Token = Đã sẵn sàng`
- `Token = Chưa đủ điều kiện`
- `reCAPTCHA = Đã sẵn sàng`
- `reCAPTCHA = Chưa sẵn sàng`

### Prompt / Upscale

- `Submit Prompt = Thành công`
- `Submit Prompt = Thất bại`
- `Submit Upscale = Thành công`
- `Submit Upscale = Thất bại`
- `Upscale = Đang xử lý`
- `Upscale = Hoàn tất`

### Lỗi đơn giản

- `Không thể gửi yêu cầu, vui lòng thử lại`
- `Trình duyệt chưa sẵn sàng`
- `Extension chưa sẵn sàng`
- `Tài khoản đang được khôi phục`

---

## Điều cần tránh khi triển khai

- không dùng raw log kỹ thuật làm log người dùng;
- không đưa toàn bộ message từ logger vào UI;
- không để wording thay đổi lung tung giữa các module;
- không dùng câu dài khó đọc;
- không để log tăng vô hạn làm nặng tab Queue.

---

## Kế hoạch test

### 1. Test giao diện

- mở tab `Queue`, kiểm tra khung `Console Log` hiển thị đúng;
- thử thu gọn / mở rộng nhiều lần;
- kiểm tra auto-scroll;
- kiểm tra nút xóa log.

### 2. Test luồng kết nối

- mở app;
- kết nối browser;
- kết nối extension;
- kiểm tra log hiển thị đúng các mốc:
  - trình duyệt đã mở;
  - trình duyệt đã kết nối;
  - extension đã kết nối.

### 3. Test luồng readiness

- kiểm tra log cho:
  - `XCD = Đã sẵn sàng`
  - `XCD = Chưa sẵn sàng`
  - `reCAPTCHA = Đã sẵn sàng`
  - `reCAPTCHA = Chưa sẵn sàng`

### 4. Test submit prompt / upscale

- gửi prompt thành công;
- gửi prompt thất bại;
- gửi upscale thành công;
- gửi upscale thất bại;
- kiểm tra wording có ngắn, rõ và nhất quán không.

### 5. Test lỗi và recovery

- mô phỏng mất kết nối extension;
- mô phỏng tab browser reload;
- mô phỏng trạng thái account recovery;
- xác nhận log chỉ hiện câu dễ hiểu, không lộ thuật ngữ nội bộ.

### 6. Test hiệu năng

- chạy queue dài;
- xác nhận log không lag;
- xác nhận số dòng bị giới hạn;
- xác nhận log không spam khi poll liên tục.

---

## Kết luận

Giải pháp phù hợp nhất là:

1. thêm một khung `Console Log` có thể mở rộng / thu gọn trong tab `Queue`;
2. dùng `QPlainTextEdit` kiểu card đơn giản như mẫu `DevConsole`;
3. không đổ raw log vào UI;
4. tạo một lớp chuẩn hoá thông điệp riêng cho người dùng;
5. gom sự kiện từ `AppController`, `ExtensionBridge`, `UpscaleQueue`;
6. chuẩn hoá toàn bộ cách hiển thị sang ngôn ngữ ngắn, dễ hiểu.

Nếu triển khai đúng hướng này, tab `Queue` sẽ có một vùng log vừa đủ đơn giản cho người dùng thường, nhưng vẫn đủ hữu ích để theo dõi:

- kết nối app ↔ browser,
- kết nối app ↔ extension,
- trạng thái XCD / token / reCAPTCHA,
- submit prompt / upscale,
- lỗi và khôi phục.
