# Build Rules — VEO Pro Max Client
# ==================================

## 📌 Rule #1: Changelog chỉ dành cho CLIENT

CHANGELOG.txt được hiển thị trực tiếp trong app client (phần Cập nhật).
KHÔNG BAO GIỜ đề cập thông tin về Admin app trong file này.

### ✅ NÊN ghi:
- Tính năng mới cho client (queue, download, generation...)
- Bug fix ảnh hưởng client
- Cải thiện hiệu năng, UI
- Thay đổi bảo mật (chung chung, không chi tiết)

### ❌ KHÔNG ghi:
- Thay đổi Admin app (phê duyệt, quản lý license, notification...)
- Chi tiết cơ chế bảo mật nội bộ (HMAC, integrity check...)
- Thay đổi chỉ ảnh hưởng server/admin
- Thông tin kỹ thuật build script

### Ví dụ đúng:
```
🔧 Fix: Extension hoạt động ổn định hơn
🚀 Cải thiện tốc độ tải video
🔒 Tăng cường bảo mật ứng dụng
```

### Ví dụ sai:
```
🔔 Admin: OS notification khi có request mới      ← Admin info
🔒 Admin: Close-to-tray + confirmation dialog      ← Admin info
🛡️ Fix: HMAC derived key (machine-bound)            ← Security detail
```

---

## 📌 Rule #2: Single Source of Truth cho Version

- `APP_VERSION` trong `02/config/constants.py` là NƠI DUY NHẤT khai báo version
- `version.json` trong folder 03 được TỰ SINH bởi `build_release.py`
- KHÔNG BAO GIỜ sửa tay `version.json` trong folder 03

---

## 📌 Rule #3: Quy trình Release

```
1. Sửa code trong folder 02
2. Bump APP_VERSION trong 02/config/constants.py
3. Cập nhật CHANGELOG.txt (chỉ client-facing changes!)
4. Chạy: python build_release.py
5. Push folder 03 lên GitHub
6. Chạy: python create_release.py (tạo GitHub Release + upload zip)
```

---

## 📌 Rule #4: Cấu trúc ZIP cho Auto-Update

ZIP phải có cấu trúc:
```
VEO_Pro_Max/
├── VEO_Pro_Max.exe
├── config/
├── assets/
├── extension/
└── [DLLs, .pyd files...]
```

KHÔNG dùng GitHub archive URL (cấu trúc sai, có thêm main.dist/ wrapper).
Luôn dùng GitHub Release asset URL.
