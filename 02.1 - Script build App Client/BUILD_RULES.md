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

---

## 📌 Rule #6: Mã hóa dữ liệu Data (Fernet AES-256)

> **Status**: 🔜 Chưa triển khai — CHỈ xử lý khi bắt đầu build EXE

> [!CAUTION]
> **TUYỆT ĐỐI KHÔNG sửa folder gốc `02 - CLIENT - VEO PRO MAX`!**
> - Folder gốc LUÔN giữ nguyên `.md` plaintext để dev/nâng cấp bình thường
> - Encryption CHỈ chạy trên BẢN COPY trong quá trình build EXE
> - `data_source/` CHÍNH LÀ folder `data/` gốc từ 02 (không cần copy riêng)
> - Flow: `build_release.py` copy 02 → temp → encrypt data → compile exe → output 03

### Nguyên tắc cốt lõi
```
02 - CLIENT (gốc)     → KHÔNG BAO GIỜ bị thay đổi bởi encryption
                         Luôn giữ .md plaintext để dev tiếp

build_release.py       → Copy 02 → temp folder
                         Chạy encrypt_data.py trên temp/data/
                         Compile temp → EXE
                         Output → 03 - Final App Client

03 - Final App Client  → Chỉ chứa .enc (encrypted)
                         Ship cho khách
```

```
data_source/             ← 🔑 CHỈ DEV GIỮ (plaintext .md, KHÔNG ship)
├── workflows/
│   ├── 01_Research/
│   ├── 02_Universal/Templates/
│   ├── 03_Advanced/
│   └── content-video.md

data/                    ← 🔒 SHIP cho khách (encrypted .enc)
├── workflows/
│   ├── 01_Research/
│   ├── 02_Universal/Templates/
│   │   ├── Cooking_Tips.enc
│   │   ├── Health_PMCS.enc
│   │   └── ...
│   ├── 03_Advanced/
│   └── content-video.enc
```

### Quy trình cập nhật

```
1. Sửa/thêm file .md trong data_source/
2. Chạy: python encrypt_data.py
   → Tự encrypt tất cả .md → .enc trong data/
   → Tự xóa .enc orphan (nếu xóa .md source)
3. Chạy build_release.py như bình thường
4. Ship cho khách (data/ chỉ chứa .enc)
```

### Cần tạo khi triển khai

#### 1. `encrypt_data.py` (Build tool)
```python
# Chức năng:
# - Scan data_source/**/*.md
# - Encrypt mỗi file → data/**/*.enc (giữ cấu trúc thư mục)
# - Xóa .enc không còn .md source tương ứng
# - Report: X files encrypted, Y files removed
#
# Key: Fernet (from cryptography library)
# Key storage: Hardcode trong file hoặc derive từ APP_SECRET
# Dependency: pip install cryptography
```

#### 2. `core/data_loader.py` (Runtime module)
```python
# Chức năng:
# - Decrypt .enc files in memory (KHÔNG ghi ra disk)
# - Expose API: load_text(path) → str
# - Dev mode: đọc .md trực tiếp (cho dev)
#
# Config: DATA_MODE = "dev" | "encrypted"
# - dev: đọc từ data_source/*.md (plaintext)
# - encrypted: đọc từ data/*.enc (decrypt in memory)
```

#### 3. Sửa `core/workflow_scanner.py`
```python
# Thay đổi:
# - scan_sources() gọi data_loader.load_text() thay vì Path.read_text()
# - _parse_template() nhận content string thay vì Path
# - Fallback: nếu .enc không có, thử .md (backward compatible)
```

#### 4. Sửa `core/project_builder.py`
```python
# Thay đổi:
# - load_workflow_data() gọi data_loader thay vì đọc file trực tiếp
# - context_manager cũng dùng data_loader
```

### Lưu ý bảo mật

- **Key management**: Key nhúng trong Python code → dễ decompile
  → Giải pháp: kết hợp Nuitka compile Python → .exe (key ẩn trong binary)
- **Memory**: Decrypt in RAM, KHÔNG BAO GIỜ ghi plaintext ra disk
- **Dev mode**: CHỈ enable khi dev, disable trong production build
- **Dependency**: `cryptography` library (pip install cryptography)

### Checklist triển khai

- [ ] Tạo `data_source/` — copy toàn bộ từ `data/` hiện tại
- [ ] Viết `encrypt_data.py` — encrypt tool
- [ ] Viết `core/data_loader.py` — runtime decrypt
- [ ] Sửa `workflow_scanner.py` — dùng data_loader
- [ ] Sửa `project_builder.py` — dùng data_loader
- [ ] Thêm `DATA_MODE` config (dev/encrypted)
- [ ] Test: encrypt → run app → verify tất cả features OK
- [ ] Thêm `data_source/` vào `.gitignore` (nếu dùng git)
- [ ] Cập nhật `build_release.py` — auto chạy encrypt trước build


