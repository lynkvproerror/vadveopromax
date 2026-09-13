# Changelog

## v3.2.4

### Video Enhancer (Bộ nâng cao chất lượng video 720p → 1080p)
- Tích hợp bộ công cụ Video Enhancer cục bộ cho video 720p base với 2 engine: Real-ESRGAN Vulkan NCNN siêu phân giải và FFmpeg Unsharp / CAS adaptive filter.
- Cơ chế bảo vệ khuôn mặt (Face Protection) tự động phát hiện vùng mặt bằng Haar Cascade / DNN và giữ độ mềm mại tự nhiên, tránh bị sắc nét quá đà.
- 5 preset tăng cường chất lượng tùy biến: Cinematic, Anime, Natural, Crisp, Vivid.
- Thiết lập bật/tắt (Toggle) và tùy chọn preset trực quan ngay trong tab Cài đặt (Settings).
- Nhận diện và hiển thị huy hiệu 1080p trên video sau khi nâng cấp chất lượng thành công.

### Grid-Mesh Micro-Stabilizer (Chống rung lắc video cục bộ)
- Nâng cấp bộ ổn định video Micro-Stabilizer với chế độ Grid-Mesh (lưới ma trận phân vùng thích ứng).
- Triệt tiêu hiện tượng rung lắc vi mô (micro-jitter) cục bộ ở các góc và vùng chi tiết mà bộ ổn định toàn cục (global phase correlation) không xử lý được.

### VPN Proxy Auto-Recovery & Chống văng IP
- Cơ chế tự động kết nối lại (Auto-Reconnect) với thuật toán Exponential Backoff khi đường hầm proxy bị gián đoạn.
- Tự động đổi IP và đưa IP bị gắn cờ vào danh sách đen khi phát hiện Unusual Activity (US Err / CAPTCHA 403 / 429).
- Cơ chế thác nước dự phòng quốc gia (Country Fallback Waterfall) tự động chuyển sang quốc gia/cụm máy chủ thay thế khi toàn bộ server của quốc gia hiện tại không phản hồi.
- Tích hợp hệ thống RPC điều khiển VPN Proxy hai chiều giữa Python Backend và Flow Extension.

### Chuẩn hóa & Cô lập Bộ đếm thời gian Hàng đợi (Queue Timing Isolation)
- Cô lập hoàn toàn đồng hồ đếm giây cho từng giai đoạn hậu kỳ (Generating, Downloading, Enhancing, Stabilizing, Cleaning watermark, Processing audio), reset về 0s độc lập giữa các stage.
- Khắc phục triệt để lỗi Enhancing kế thừa thời gian của công đoạn Download trước đó (>120s).
- Tách biệt rõ ràng giữa elapsed_seconds (thời gian của stage hiện tại) và total_elapsed_seconds (tổng thời gian xử lý toàn bộ task).
- Đồng bộ toàn diện phiên bản App và Extension v3.2.4.

## v3.2.3

### VPN Proxy & Định tuyến IP Đa quốc gia
- Tích hợp mạng lưới VPN Proxy với 84 quốc gia và hơn 262 máy chủ phân tán toàn cầu.
- Giao diện bộ chọn quốc gia (Country Picker) trực quan ngay trên Extension Side Panel: thẻ trạng thái kết nối, nhóm quốc gia phổ biến, thanh tìm kiếm thông minh và nút Đổi IP (IP Rotation) tức thì.
- Cơ chế tự động lấy token proxy xác thực qua đường hầm bảo mật, chu kỳ làm mới định kỳ 30 phút và cơ chế dự phòng về cụm máy chủ US tin cậy khi có sự cố.
- Chuẩn hóa toàn diện nhận diện "VPN Proxy" trên toàn bộ giao diện người dùng và extension.

### Quản lý Đa tài khoản & Điều phối Profile
- Nâng cấp cơ chế nhận diện Profile Chrome tự động chuẩn hóa qua giao thức Google ListAccounts và bản đồ phiên đăng nhập.
- Thuật toán điều phối hàng đợi Fair-Share Round-Robin đảm bảo tài nguyên tài khoản được phân bổ công bằng, tối ưu hóa tốc độ tạo video.
- Đồng bộ toàn diện phiên bản App và Extension v3.2.3.

## v3.2.2

### Queue & Metrics
- Sửa lỗi Metric Queue Footer: Tính toán chính xác số lượng Done, Failed, số Credits tiêu thụ (bao gồm Omni 360p vs 720p theo thời lượng) và số video tạo hôm nay.
- Cơ chế Realtime Timing Ticker: Đồng bộ bộ đếm thời gian thực 1 giây trên main thread UI, loại bỏ hoàn toàn độ trễ 5s trên task row, group header stopwatch và tổng thời gian hàng đợi.
### Giao diện & Đóng gói (UI & Release)
- Nâng cấp Giao diện Màn hình khởi động (Splash Screen): Áp dụng thiết kế điện ảnh chuẩn 16:9 (888x500), thanh tiến trình capsule quang phổ Google Flow trên sàn phản chiếu studio, viền acrylic gradient tinh tế.
- Nhận diện Google Flow Extension: Bộ icon vector Google Flow quang phổ AI Prism mới (16x16, 32x32, 48x48, 128x128, 256x256) trên nền dark squircle hiện đại.
- Tối ưu Script Build Đa luồng: Tận dụng toàn bộ số luồng CPU (16 logical cores), mã hóa song song 40 files dữ liệu, tích hợp engine nén 64-bit Inno Setup (LZMA2 8 threads) loại bỏ hoàn toàn lỗi Out-of-Memory.
- Đồng bộ toàn diện phiên bản App và Extension v3.2.2.

## v3.1.5

### Tạo video & Omni Flash
- Bổ sung Omni 1.1 Flash T2V native 360p/720p cho 4s, 6s, 8s và 10s; chuẩn hóa Omni I2V/R2V theo capability thực tế.

### Queue & Output
- Xóa queue theo force detach để không bị giữ lại bởi callback hoặc output phản hồi muộn.
- Tách thư mục output theo từng run và tách cache media upload theo account/project, tránh lẫn media ID giữa các project.
- Cải thiện telemetry extension, cooldown CAPTCHA và trạng thái download để worker ổn định hơn.

### Giao diện
- Prompt table hiển thị trọn nội dung text/JSON, còn giới hạn hàng chứa nhiều hình ảnh để bảo toàn hiệu năng.

## v3.1.4

### Bảo mật ứng dụng (Security & Anti-Tamper)
- Tăng cường cơ chế xác thực bản quyền đa tầng và kiểm tra tính toàn vẹn ứng dụng tự động.
- Nâng cấp mã hóa dữ liệu nội bộ và bảo vệ chống can thiệp (anti-tamper) trên runtime.
- Làm sạch và bảo vệ an toàn các thông tin nhạy cảm, token xác thực khi đóng gói phát hành.

### Backend & Tạo Video (Generation & Flow API)
- Cập nhật backend FlowKit runtime mới nhất: tối ưu tương thích với Google Flow API mới.
- Cải thiện cơ chế xử lý CAPTCHA và khắc phục triệt để lỗi Unusual Activity/Unusual Traffic.
- Khắc phục lỗi kẹt tiến trình tạo video ở mức 55% hoặc bị nhảy lùi 22% do lệch nhịp polling.
- Tự động khôi phục dữ liệu các workflow request đã sinh thành công trên server khi gặp sự cố timeout mạng.
- Tối ưu quản lý hàng đợi (Queue): sửa lỗi xoá task/group triệt để, giải phóng tài nguyên sạch sẽ.

### Tải về (Download) & Nâng cấp chất lượng (Upscale 1080p/4K)
- Chuẩn hóa luồng download 720p/1080p theo HAR thực tế từ Flow, đảm bảo file MP4 tải về nguyên vẹn 100%.
- Khắc phục triệt để hiện tượng kẹt ở 95% (Downloading) hoặc gây Not Responding khi ghi file media.
- Sửa lỗi lặp vòng gửi request upscale không cần thiết (80% ↔ 92%), phân định rõ ràng vòng đời giữa Generate và Upscale.
- Tối ưu hóa hệ thống thư mục: chỉ tự động tạo thư mục output khi có file tải thực tế, loại bỏ việc tạo folder rỗng thừa.

## v2.4.3

- Bổ sung lựa chọn thời gian 4s, 6s, 8s cho T2V và I2V.
- Bổ sung Runtime Provider và Native Browser runtime độc lập extension.
- Cải thiện parser/backend cho tag voice/media trong prompt thường và JSON.
- Cải thiện Queue performance, progress thật và guard upscale cho video 4s/6s.
- Siết account recovery, session readiness và submit gate để giảm vòng lặp lỗi.
