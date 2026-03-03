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
5. Push folder 03 lên GitHub (git add, commit, push — LFS tự upload exe)
6. Tạo ZIP từ main.dist/ (cấu trúc VEO_Pro_Max/ bên trong)
7. Tạo GitHub Release: gh release create v{VERSION}
8. Upload ZIP lên Release: gh release upload v{VERSION} VEO_Pro_Max_v{VERSION}.zip
```

> ⚠️ **QUAN TRỌNG**: Bước 6-8 BẮT BUỘC. Nếu thiếu ZIP trên Release,
> auto-update client sẽ gặp lỗi **HTTP 404 Not Found**.
> `version.json` trỏ đến URL: `releases/download/v{VERSION}/VEO_Pro_Max_v{VERSION}.zip`
> → URL này chỉ hoạt động khi ZIP đã được upload làm Release asset.

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

---

## 📌 Rule #5: ZIP tạo bằng Python (không dùng tay)

```python
import zipfile, os
from pathlib import Path

dist_dir = Path("03 - Final App Client/main.dist")
zip_path = Path(f"03 - Final App Client/VEO_Pro_Max_v{VERSION}.zip")

with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(str(dist_dir)):
        for f in files:
            fp = os.path.join(root, f)
            arcname = 'VEO_Pro_Max/' + os.path.relpath(fp, str(dist_dir))
            zf.write(fp, arcname)
```

Root folder trong ZIP PHẢI là `VEO_Pro_Max/` (không phải `main.dist/`).

