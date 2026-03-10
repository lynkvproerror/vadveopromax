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

## 📌 Rule #6: Mã hóa dữ liệu Data (Fernet AES)

> **Status**: ✅ ĐÃ TRIỂN KHAI — Tự động chạy trong `build_release.py` Step 5.8

> [!CAUTION]
> **TUYỆT ĐỐI KHÔNG sửa folder gốc `02 - CLIENT - VEO PRO MAX/data/`!**
> - Folder gốc LUÔN giữ nguyên `.md` plaintext để dev/nâng cấp bình thường
> - Encryption CHỈ chạy trên output `main.dist/data/` SAU KHI Nuitka compile xong

### Kiến trúc

```
02 - CLIENT (source)         → .md plaintext — KHÔNG BAO GIỜ bị encrypt
    core/data_loader.py      → Runtime: decrypt .enc in-memory, fallback .md (dev)
    core/workflow_scanner.py  → Dùng data_loader.scan_data_files() + load_text()
    core/project_builder.py  → Dùng data_loader.load_text() (5 locations)

02.1 - Script build
    encrypt_data.py          → Build tool: Fernet AES, .md → .enc
    build_release.py         → Step 5.8: auto-encrypt main.dist/data/

03 - Final App Client
    main.dist/data/          → Chỉ chứa .enc (0 file .md plaintext)
```

### Flow tự động khi build

```
python build_release.py
  [4]   Nuitka compile (includes data_loader.py in binary)
  [5.8] encrypt_data.py encrypts main.dist/data/**/*.md → .enc, xóa .md
  → Ship: .enc files only, key ẩn trong compiled binary
```

### Key management

- Key derivation: PBKDF2-HMAC-SHA256 (200k iterations)
- Salt + passphrase hardcode trong `encrypt_data.py` và `core/data_loader.py`
- Nuitka compile cả 2 file thành native code → khó extract key
- Key PHẢI GIỐNG NHAU giữa `encrypt_data.py` và `data_loader.py`

### Lưu ý khi sửa code

- Khi thêm module mới đọc `data/workflows/*.md`:
  → **PHẢI** dùng `from core.data_loader import load_text, scan_data_files`
  → **KHÔNG** dùng `path.read_text()` trực tiếp
- Khi thêm file data mới (ngoài workflows):
  → Thêm vào `encrypt_data.py` nếu cần encrypt
  → Hoặc thêm `--include-data-files` vào `build_release.py`

---

## 📌 Rule #7: One-Command Build-to-Publish

> **Một lệnh duy nhất** xử lý toàn bộ từ compile → ZIP → git push → GitHub Release.

### Lệnh build đầy đủ

```bash
python build_release.py
```

### Pipeline tự động (9 bước)

```
[1] Check dependencies (nuitka, PySide6, C compiler)
[2] Generate SHA-256 hashes (security files)
[3] Save build_info.json
[4] Nuitka standalone compile → main.dist/
[5] Copy release files + generate version.json
[5.8] Encrypt workflow data (.md → .enc)
[5.5] Obfuscate extension JS
[6] Organize dist folder (hide DLLs)
[7] Create ZIP: VEO_Pro_Max_v{VERSION}.zip + SHA-256
[8] Git add/commit/push → remote
[9] GitHub Release (gh CLI) hoặc in manual instructions
```

### Flags tuỳ chỉnh

| Flag | Mô tả |
|---|---|
| `--skip-compile` | Bỏ qua Nuitka (dùng khi chỉ cần re-ZIP) |
| `--skip-publish` | Bỏ qua steps 7-9 (chỉ build, không publish) |
| `--skip-organize` | Bỏ qua sắp xếp folder |
| `--onefile` | Build single exe (chậm hơn khi startup) |

### Prerequisites

- `gh` CLI: `winget install GitHub.cli` + `gh auth login` (cho step 9)
- Git LFS: đã cấu hình cho `.exe` files
- `cryptography`: `pip install cryptography` (cho step 5.8)

### Khi nào chạy?

Mỗi khi có thay đổi code cần release:

```
1. Sửa code trong folder 02
2. Bump APP_VERSION trong 02/config/constants.py
3. Cập nhật CHANGELOG.txt (chỉ client-facing!)
4. Chạy: python build_release.py    ← MỘT LỆNH DUY NHẤT
5. Verify app chạy OK
```

---

## 📌 Rule #8: Dual-Repo Architecture

> **2 repo riêng biệt** — KHÔNG NHẦM LẪN!

| Repo | Chế độ | Nội dung | Git remote |
|---|---|---|---|
| `lynkvproerror/veo-pro-max` | **PRIVATE** | Source code (folder 02) | `origin` |
| `lynkvproerror/vadveopromax` | **PUBLIC** | Exe + ZIP releases | upload manual/gh CLI |

### GITHUB_REPO trong code = `vadveopromax` (public)

Files chứa `GITHUB_REPO` (PHẢI trỏ tới **PUBLIC** repo):

| File | Mục đích |
|---|---|
| `02/config/constants.py` | Client auto-update check URL |
| `02/core/auto_updater.py` | Download update ZIP URL |
| `02.1/build_release.py` | version.json download_url + gh release |

### Flow khi release

```
1. git push → veo-pro-max (PRIVATE) — source code
2. build_release.py tạo ZIP
3. Upload ZIP → vadveopromax (PUBLIC) releases
4. Client auto-update tải từ vadveopromax
```

> [!CAUTION]
> **GITHUB_REPO PHẢI là `vadveopromax`!**
> Nếu đổi thành `veo-pro-max` (private) → client không download được → HTTP 404!


