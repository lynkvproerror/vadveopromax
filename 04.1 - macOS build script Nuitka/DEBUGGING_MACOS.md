# 🐞 Hướng Dẫn Debug An Toàn (Sau Khi Build Nuitka) - macOS
# ========================================================

Khi phần mềm đã được compile bằng Nuitka đóng gói thành `.app` bundle, việc debug sẽ khó khăn hơn môi trường Python raw (do code chuyển thành C, ẩn console, và có cơ chế chống crack).

Dưới đây là 4 phương pháp debug **AN TOÀN**, không làm trigger hệ thống `AntiDebug` và `AntiTamper` của VEO Pro Max.

---

## 1. Xem Stdout/Stderr trực tiếp từ Terminal (Recommended)

Mặc định khi click đúp vào file `.app`, macOS sẽ ẩn hoàn toàn giao diện console. Để xem được các luồng `print()`, `log.info()`, hoặc `Traceback` khi lỗi:

**Cách chạy:**
```bash
# Mở Terminal và trỏ thẳng vào file binary Core bên trong .app bundle
cd "04.2 - macOS final build/VEO_Pro_Max.app/Contents/MacOS"
./VEO_Pro_Max
```

✅ **Tại sao an toàn?**
- Việc chạy qua `./VEO_Pro_Max` không gắn trình gỡ lỗi (debugger), nên cờ `P_TRACED` trong `sysctl` của macOS vẫn là `0`.
- Hệ thống `AntiDebug.is_debugger_present()` sẽ **BỎ QUA** và cho phép app chạy bình thường.
- Mọi lỗi Python Crash sẽ được in thẳng ra màn hình Terminal này.

⛔ **TUYỆT ĐỐI KHÔNG:**
Không dùng `lldb ./VEO_Pro_Max` hoặc `gdb`. Việc này sẽ lật cờ `P_TRACED = 1`, app sẽ tự động văng (crash) ngay lập tức theo cơ chế bảo mật.

---

## 2. Theo dõi File Log Hệ Thống (App Logs)

VEO Pro Max giữ nguyên cơ chế ghi log qua file ổ cứng.
Bạn có thể đọc log theo thời gian thực (real-time) bằng lệnh `tail`.

**Thư mục lưu log:**
Nằm cùng cấp với file thực thi hoặc trong user directory (tuỳ cấu hình `constants.py`). Thường nằm ở:
`04.2 - macOS final build/VEO_Pro_Max.app/Contents/MacOS/logs/` 
hoặc `~/Library/Application Support/VEO Pro Max/logs/`

**Cách xem real-time:**
```bash
# Xem log hệ thống chung
tail -f "VEO_Pro_Max.app/Contents/MacOS/logs/dev_logs_*.txt"

# Xem log riêng của từng Account VEO đang chạy
tail -f "VEO_Pro_Max.app/Contents/MacOS/logs/accounts/*.log"
```

---

## 3. Phân tích macOS Crash Reports (Segfaults)

Nếu App biến mất đột ngột mà không in ra lỗi Python nào (Segment Fault ở tầng C/C++ do Nuitka):

1. Mở ứng dụng **Console.app** có sẵn trên máy Mac (nhấn Cmd + Space gõ Console).
2. Nhìn cột bên trái, chọn mục **Crash Reports**.
3. Tìm file có tên bắt đầu bằng `VEO_Pro_Max_...`.
4. Report này sẽ cho biết chính xác thư viện `.dylib` hoặc module nào gây ra crash (ví dụ: do PySide6 thiếu thư viện Qt, hoặc lỗi OpenGL).

---

## 4. Debug Extension (Chrome Bridge)

Extension của VEO Pro Max khi build ra `.app` đã bị chạy qua tool `obfuscate_extension.py` (xoá toàn bộ `console.log` và minify code để chống dịch ngược). Do đó, bạn không thể debug extension trên bản build Production.

**Cách Debug Extension an toàn:**

1. Sửa file `04.1 - macOS build script Nuitka/build_release_macos.py`:
2. Tìm dòng:
   `os.system(f"python obfuscate_extension.py ...")` 
   và **comment nó lại** (thêm dấu `#` ở đầu) để giữ nguyên code JS gốc.
3. Build lại app:
   `python build_release_macos.py --skip-sign`
4. Mở app, khi Chrome bật lên -> Truy cập `chrome://extensions` -> Bật **Developer mode** -> Nhấn vào **service worker** của Auto Accept Agent Pro -> Chuyển sang tab **Console** để xem log kết nối WebSocket.

---

### 🛡️ Tóm tắt Troubleshooting

| Hiện tượng | Cách Debug | Khả năng cao do |
|---|---|---|
| Click vào `.app` trỏ icon tưng tưng rồi tắt | Dùng cách 1 (Chạy binary qua terminal) | Lỗi import thư viện Python, sai đường dẫn thư mục |
| Đang chạy thì văng | Dùng cách 3 (Console.app) | Qt/C++ Segfault, tràn RAM |
| App treo, không kết nối được Chrome | Dùng cách 4 (Extension log) | Mất kết nối WebSocket port 8765 |
| API trả về lỗi | Dùng cách 2 (tail -f log accounts) | Sai license, hết quota, cloudflare chặn |
