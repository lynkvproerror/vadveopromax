# Build Rules — VEO Pro Max Client
# ==================================

## 🔑 Git & Repository Info

| Item | Value |
|------|-------|
| Git Token | `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` |
| Private Repo (source) | `https://github.com/lynkvproerror/veo-pro-max` |
| Public Repo (releases) | `https://github.com/lynkvproerror/vadveopromax` |
| Source folder | `02 - CLIENT - VEO PRO MAX` |
| Build output folder | `03 - Final App Client` |

### Quy trình Git khi release

```
1. Push source code → veo-pro-max (PRIVATE)
   git push https://ghp_...@github.com/lynkvproerror/veo-pro-max.git main

2. Chạy build_release.py → tạo exe + ZIP + tự push folder 03 → vadveopromax (PUBLIC)

3. Tạo GitHub Release + upload ZIP → vadveopromax (PUBLIC)
   GH_TOKEN=ghp_... gh release create v{VER} --repo lynkvproerror/vadveopromax ...
   GH_TOKEN=ghp_... gh release upload v{VER} --repo lynkvproerror/vadveopromax VEO_Pro_Max_v{VER}.zip
```

> ⚠️ **gh CLI cần `GH_TOKEN` env var** (hoặc `gh auth login`). Nếu gh CLI freeze, dùng `--repo` flag và tách create/upload thành 2 lệnh riêng.

---

## 📌 Rule #1: Changelog chỉ dành cho CLIENT

`CHANGELOG.txt` được hiển thị trực tiếp trong app client (phần Cập nhật).
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

## 📌 Rule #2: Versioning Convention

### 2a. Single Source of Truth

- `APP_VERSION` trong `02/config/constants.py` là NƠI DUY NHẤT khai báo version
- `version.json` trong folder 03 được TỰ SINH bởi `build_release.py` step [5.1]
- KHÔNG BAO GIỜ sửa tay `version.json` trong folder 03

### 2b. App Version ≠ Extension Version (ĐỘC LẬP)

| Component | Version Source | Khi nào bump |
|-----------|---------------|-------------|
| **App (exe)** | `constants.py` → `APP_VERSION` | Khi code Python thay đổi (core, UI, services...) |
| **Extension** | `manifest.json` → `version` | Khi code Extension thay đổi (background.js, content.js, offscreen.js...) |

> [!IMPORTANT]
> **Version KHÔNG tự đồng bộ.** Mỗi component bump RIÊNG khi có thay đổi.
> - Nếu CHỈ sửa app → chỉ bump `APP_VERSION`, giữ nguyên `manifest.json`
> - Nếu CHỈ sửa extension → chỉ bump `manifest.json`, giữ nguyên `APP_VERSION`
> - Nếu sửa CẢ HAI → bump CẢ HAI
> - Nếu KHÔNG thay đổi gì → KHÔNG bump
>
> Mechanism: `install_if_needed()` trong `extension_manager.py` so sánh installed vs local `manifest.json` version → tự reload/reinstall khi mismatch.

### 2c. Semantic Versioning (MAJOR.MINOR.PATCH) — áp dụng CHO CẢ App và Extension

| Digit | Khi nào bump | Ví dụ |
|-------|-------------|-------|
| **MAJOR** (X.y.z) | Breaking changes: license format, API protocol, data format incompatible | `2.0.0` → `3.0.0` |
| **MINOR** (x.Y.z) | Features mới: tab, AI model, workflow mới | `2.3.0` → `2.4.0` |
| **PATCH** (x.y.Z) | Bug fix, security, optimization | `2.3.1` → `2.3.2` |

### 2d. Ví dụ thực tế

| Tình huống | APP_VERSION | manifest.json |
|-----------|-------------|---------------|
| Fix offscreen loop trong background.js | Giữ nguyên | `2.3.0` → `2.3.1` |
| Fix anti-tamper trong Python code | `2.3.1` → `2.3.2` | Giữ nguyên |
| Thêm feature mới cần cả app + extension | `2.3.2` → `2.4.0` | `2.3.1` → `2.4.0` |
| Chỉ update BUILD_RULES, CHANGELOG | Giữ nguyên | Giữ nguyên |

### 2e. Granular Update Modes

| Mode | Trigger | Artifact | Restart? |
|------|---------|----------|----------|
| **Full ZIP** | `APP_VERSION` bumped | `VEO_Pro_Max_v{VER}.zip` (~67MB) | Yes (hoặc defer) |
| **Extension Only** | Chỉ `manifest.json version` bumped | `VEO_Extension_v{VER}.zip` (~50KB) | ❌ No |
| **No Update** | Cả hai giữ nguyên | Nothing | — |

> ⚠️ **Nếu extension fix CẦN code Python mới (bridge protocol change) → PHẢI bump APP_VERSION → Full ZIP**

### 2f. Release Artifacts

Mỗi GitHub Release v{VER} upload:
```
├── VEO_Pro_Max_v{VER}.zip         ← Full (luôn tạo)
├── VEO_Extension_v{EXT_VER}.zip   ← Extension only (~50KB)
└── version.json (trong repo)       ← Contains both versions
```

`version.json` v2 format:
```json
{
  "version": "2.3.2",
  "ext_version": "2.3.2",
  "download_url": "...VEO_Pro_Max_v2.3.2.zip",
  "ext_download_url": "...VEO_Extension_v2.3.2.zip",
  "sha256": "...",
  "ext_sha256": "..."
}
```

### 2g. Pending Update (Deferred)

- Full update → user chọn "Yes" (restart ngay) hoặc "No" (defer)
- Defer lưu `~/.veoauto/pending_update.json` với path ZIP
- Khi mở app lần sau → check file này → hỏi apply hoặc skip
- Kể cả tắt máy rồi bật lại vẫn hoạt động

---

## 📌 Rule #3: Quy trình Release

```
1. Sửa code trong folder 02
2. Bump APP_VERSION (nếu Python code thay đổi) và/hoặc manifest.json version (nếu extension thay đổi)
3. Cập nhật CHANGELOG.txt (chỉ client-facing changes!)
4. Push source → veo-pro-max (PRIVATE)
5. Chạy: python build_release.py    ← MỘT LỆNH DUY NHẤT
6. Tạo GitHub Release trên vadveopromax (PUBLIC) + upload cả 2 ZIPs
7. Verify: version.json + download URLs chính xác
```

### 3b. Post-Release Verify (BẮT BUỘC)

> [!CAUTION]
> **Bước này BẮT BUỘC sau EVERY release/rebuild.**
> v2.3.2 đã gặp SHA mismatch vì build 2 lần mà không verify:
> - Build #1 (16:42) → push version.json SHA `91f5d9ae...`
> - Build #2 (18:36) → upload ZIP mới SHA `4e311c74...` nhưng KHÔNG push lại version.json
> - Kết quả: client download ZIP mới → SHA mismatch → KHÔNG update được!

**4 bước verify (chạy sau khi push+upload xong):**

```powershell
# 1. Verify version.json trên GitHub CDN (chờ 1-5 phút sau push)
curl -s https://raw.githubusercontent.com/lynkvproerror/vadveopromax/main/version.json | python -m json.tool

# 2. So sánh SHA trong version.json vs SHA thực tế của ZIP trên Release
#    Download ZIP → tính SHA → so với version.json
curl -sL "https://github.com/lynkvproerror/vadveopromax/releases/download/v{VER}/VEO_Pro_Max_v{VER}.zip" -o temp_verify.zip
certutil -hashfile temp_verify.zip SHA256
#    → SHA PHẢI KHỚP với "sha256" trong version.json

# 3. Nếu có extension ZIP, verify ext_sha256 tương tự
curl -sL "https://github.com/lynkvproerror/vadveopromax/releases/download/v{VER}/VEO_Extension_v{EXT_VER}.zip" -o temp_ext_verify.zip
certutil -hashfile temp_ext_verify.zip SHA256
#    → SHA PHẢI KHỚP với "ext_sha256" trong version.json

# 4. Verify download URLs trả 200 (không 404)
curl -sI "https://github.com/lynkvproerror/vadveopromax/releases/download/v{VER}/VEO_Pro_Max_v{VER}.zip" | findstr "HTTP/"
#    → Phải trả "302 Found" (redirect to CDN)
```

**Checklist:**
- [ ] `sha256` trong version.json == SHA thực tế của ZIP trên Release
- [ ] `ext_sha256` trong version.json == SHA thực tế của extension ZIP (nếu có)
- [ ] `download_url` trả 302 (không 404)
- [ ] `ext_download_url` trả 302 (không 404, hoặc empty nếu không có)
- [ ] `version` và `ext_version` đúng

> ⚠️ **Nếu build NHIỀU LẦN**: PHẢI push lại version.json SAU LẦN BUILD CUỐI.
> SHA trong version.json phải khớp với ZIP CUỐI CÙNG được upload lên Release.

> ⚠️ **QUAN TRỌNG**: Bước 6 BẮT BUỘC nếu gh CLI không tự chạy được.
> `version.json` trỏ đến 2 URLs:
> - Full: `releases/download/v{VERSION}/VEO_Pro_Max_v{VERSION}.zip`
> - Extension: `releases/download/v{VERSION}/VEO_Extension_v{EXT_VERSION}.zip`

---

## 📌 Rule #4: Cấu trúc ZIP cho Auto-Update

ZIP phải có cấu trúc root folder `VEO_Pro_Max/` (KHÔNG phải `main.dist/`):
```
VEO_Pro_Max/
├── VEO_Pro_Max.exe
├── config/
├── assets/
├── data/          (chỉ chứa .enc, 0 file .md)
├── extension/     (obfuscated JS)
├── ui/
└── [DLLs, .pyd files - hidden attribute]
```

- Build script tự tạo ZIP đúng cấu trúc tại step [7]
- KHÔNG dùng GitHub archive URL (cấu trúc sai, có `main.dist/` wrapper)
- LUÔN dùng GitHub Release asset URL

---

## 📌 Rule #5: Mã hóa dữ liệu Data (Fernet AES)

> **Status**: ✅ ĐÃ TRIỂN KHAI — Tự động chạy trong `build_release.py` Step [5.8]

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
    build_release.py         → Step [5.8]: auto-encrypt main.dist/data/

03 - Final App Client
    main.dist/data/          → Chỉ chứa .enc (0 file .md plaintext)
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

## 📌 Rule #6: One-Command Build Pipeline

> **`python build_release.py`** — xử lý toàn bộ từ compile → ZIP → git push → GitHub Release.

### Pipeline tự động (9 bước)

```
[1]   Check dependencies (python, nuitka, PySide6, C compiler)
[2]   Generate SHA-256 hashes (8 security files)
[3]   Save build_info.json → folder 03
[4]   Nuitka standalone compile → main.dist/
[5]   Copy release files (CHANGELOG.md, README.md)
[5.1] Generate version.json (from APP_VERSION + CHANGELOG.txt)
[5.8] Encrypt workflow data (.md → .enc) trong main.dist/data/
[5.5] Obfuscate extension JS trong main.dist/extension/
[6]   Organize dist folder (attrib +H +S hide DLLs)
[7]   Create ZIP: VEO_Pro_Max_v{VERSION}.zip + SHA-256 cập nhật vào version.json
[8]   Git add/commit/push folder 03 → vadveopromax remote
[9]   GitHub Release (gh CLI) — tạo tag + upload ZIP, hoặc in manual instructions
```

### Flags tuỳ chỉnh

| Flag | Mô tả |
|---|---|
| `--skip-compile` | Bỏ qua Nuitka (dùng khi chỉ cần re-ZIP/re-publish) |
| `--skip-publish` | Bỏ qua steps 7-9 (chỉ build, không publish) |
| `--skip-organize` | Bỏ qua step 6 (không ẩn DLLs) |
| `--onefile` | Build single exe (chậm hơn khi startup) |
| `--check` | Chỉ kiểm tra dependencies rồi exit |
| `--hash-only` | Chỉ generate hashes (step 1-3) rồi exit |

### Prerequisites

- **Python 3.13+** với `pip install nuitka ordered-set zstandard cryptography`
- **Git LFS**: đã cấu hình cho `.exe` files trong folder 03
- **gh CLI** (optional): `winget install GitHub.cli`
  - Auth: `gh auth login` hoặc set `GH_TOKEN` env var
  - Nếu không có gh CLI → script in manual instructions (step 9 fallback)

### ⚠️ Lưu ý khi gh CLI không hoạt động

Build script sẽ in manual instructions nếu:
- `gh` CLI không tìm thấy trong PATH
- `gh release create` bị lỗi (timeout, auth, MinTTY freeze)

**Workaround**: Tách thành 2 lệnh riêng với `GH_TOKEN` env var:
```powershell
$env:GH_TOKEN = "ghp_..."
gh release create v{VER} --repo lynkvproerror/vadveopromax --title "VEO Pro Max v{VER}" --notes "..."
gh release upload v{VER} --repo lynkvproerror/vadveopromax "path/to/VEO_Pro_Max_v{VER}.zip"
```

> **Tip**: Nếu path có ký tự đặc biệt (#, space), copy ZIP ra `C:\Users\Linh\` trước khi upload.

---

## 📌 Rule #7: Dual-Repo Architecture

> **2 repo riêng biệt** — KHÔNG NHẦM LẪN!

| Repo | Chế độ | Nội dung | Folder |
|---|---|---|---|
| `lynkvproerror/veo-pro-max` | **PRIVATE** | Source code Python | 02 - CLIENT |
| `lynkvproerror/vadveopromax` | **PUBLIC** | Exe + ZIP releases | 03 - Final App Client |

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
2. build_release.py step [8]: git push folder 03 → vadveopromax (PUBLIC)
3. build_release.py step [9]: gh release create + upload ZIP → vadveopromax (PUBLIC)
4. Client auto-update: check version.json → tải ZIP từ vadveopromax releases
```

> [!CAUTION]
> **`GITHUB_REPO` PHẢI là `lynkvproerror/vadveopromax`!**
> Nếu đổi thành `veo-pro-max` (private) → client không download được → HTTP 404!

### Git push flow chi tiết (step 8)

Build script push từ **BASE_DIR** (`#NEW VEO API`), KHÔNG phải từ folder 03:
```python
# build_release.py line 575-576
git add "03 - Final App Client"
git commit -m "Release v{VERSION}"
git push   # → vadveopromax remote
```

→ Remote `origin` của folder `#NEW VEO API` phải trỏ tới `vadveopromax` (PUBLIC).
→ Nếu push lỗi, dùng explicit URL:
```powershell
git push https://ghp_...@github.com/lynkvproerror/vadveopromax.git main
```

---

## 📌 Rule #8: Clean Root Structure (Runtime File Hiding)

Exe tự động ẩn runtime files (.dll, .pyd, Python packages) khi khởi động.

### Tại sao?

Nuitka standalone yêu cầu DLLs ở **cùng thư mục** với exe → KHÔNG thể dời vào subfolder.
Giải pháp: `main.py` → `_hide_runtime_files()` chạy `attrib +H +S` mỗi lần khởi động.

### Thư mục gốc user thấy (Explorer):

| Item | Loại | Mục đích |
|------|------|----------|
| `VEO_Pro_Max.exe` | File | Ứng dụng chính |
| `assets/` | Folder | Icons, themes, images |
| `config/` | Folder | Cấu hình người dùng + locales |
| `data/` | Folder | Workflow data (encrypted .enc) |
| `extension/` | Folder | Chrome extension (obfuscated) |

### File ẩn (vẫn ở cùng thư mục, loadable bởi exe):

- `.dll` (python313.dll, qt6core.dll, libcrypto-3.dll...)
- `.pyd` (unicodedata.pyd, _ssl.pyd, _sqlite3.pyd...)
- Package folders (PySide6/, aiohttp/, cryptography/...)

### Hai lớp bảo vệ:

1. **Build time**: `build_release.py` step [6] → `organize_dist_folder()` ẩn trên máy build
2. **Runtime**: `main.py` → `_hide_runtime_files()` ẩn trên máy user (chạy mỗi lần khởi động)

### `KEEP_VISIBLE` phải khớp

```python
# build_release.py line 296-302 (organize_dist_folder)
KEEP_VISIBLE = {"VEO_Pro_Max.exe", "config", "assets", "data", "extension"}

# main.py (_hide_runtime_files)
# Phải giữ CHÍNH XÁC danh sách này
```

> ⚠️ Khi giải nén ZIP trên máy mới, file chưa ẩn → exe sẽ tự ẩn lần chạy đầu tiên.

---

## 📌 Rule #9: Rebuild cùng Version (Hotfix)

Khi cần fix bug và rebuild **cùng version** (không bump):

```powershell
# 1. Sửa code trong folder 02
# 2. Push source
git push https://ghp_...@github.com/lynkvproerror/veo-pro-max.git main

# 3. Xóa release cũ (BẮT BUỘC — nếu không, ZIP cũ vẫn live)
$env:GH_TOKEN = "ghp_..."
gh release delete v{VER} --repo lynkvproerror/vadveopromax --yes
git push https://ghp_...@github.com/lynkvproerror/vadveopromax.git :refs/tags/v{VER}

# 4. Build lại
python build_release.py

# 5. Push build output (version.json chứa SHA MỚI)
git push https://ghp_...@github.com/lynkvproerror/vadveopromax.git main

# 6. Tạo release mới + upload ZIP
gh release create v{VER} --repo lynkvproerror/vadveopromax --title "VEO Pro Max v{VER}" --notes "..."
gh release upload v{VER} --repo lynkvproerror/vadveopromax "path/to/VEO_Pro_Max_v{VER}.zip"

# 7. ⚠️ VERIFY (Rule #3b) — BẮT BUỘC! Chờ CDN cache clear (~5 phút) rồi verify SHA
```

> ⚠️ Client sẽ KHÔNG nhận thông báo update mới (vì version number không đổi).
> Chỉ ai tải lại ZIP mới sẽ có bản fix.

---

## 📌 Rule #10: Update Safety — Các trường hợp dễ gây lỗi

### 10a. Pipeline Ordering Gap (Step 8 → Step 9)

> [!WARNING]
> Build script push `version.json` (step 8) **TRƯỚC KHI** upload ZIP (step 9).
> → Có cửa sổ ~30 giây client check → thấy version mới → download → **404** vì ZIP chưa upload!

**Giải pháp hiện tại**: Chấp nhận rủi ro nhỏ (window < 1 phút). Client retry sau 30 phút.

**Nếu cần zero-downtime**: Upload ZIP trước, push version.json sau:
```powershell
# Manual override nếu cần:
# 1. Build (skip publish)
python build_release.py --skip-publish
# 2. Upload ZIP TRƯỚC
gh release create v{VER} ... && gh release upload v{VER} ./VEO_Pro_Max_v{VER}.zip
# 3. Push version.json SAU
git push
```

### 10b. GitHub CDN Cache (raw.githubusercontent.com)

| Hành vi | Thời gian |
|---------|-----------|
| Cache `raw.githubusercontent.com` | ~5 phút |
| Cache GitHub Releases CDN | ~2 phút |
| Client check interval | 30 phút |

→ **KHÔNG** announce update cho user ngay sau push. Chờ ít nhất **5 phút** rồi verify (Rule #3b).

### 10c. Build NHIỀU LẦN = Bug SHA mismatch

> [!CAUTION]
> **Mỗi lần build tạo ZIP MỚI → SHA KHÁC.**
> Nếu build N lần, chỉ zip cuối cùng + version.json cuối cùng mới khớp.
> PHẢI đảm bảo version.json trên GitHub chứa SHA của ZIP CÓ TRÊN RELEASE.

**Nguyên tắc**: Build lần cuối → push version.json → upload ZIP → verify.
Nếu upload ZIP manual (không qua script) → PHẢI tính SHA thủ công và update version.json.

### 10d. `force_update` trong version.json

| Giá trị | Hành vi |
|---------|---------|
| `false` (default) | Client check version → update nếu app version < remote |
| `true` | **Bắt buộc update** — bỏ qua version compare, luôn show "Full Update" |

**Khi nào dùng `force_update: true`**:
- Breaking change buộc ALL clients phải update (data format change, API protocol change)
- Security vulnerability critical cần patch gấp
- Kết hợp với `min_version` để block client quá cũ

**Cách set**: Sửa `version.json` thủ công hoặc qua `generate_version_json()` trong `build_release.py`.

### 10e. Extension-Only Release

Khi chỉ sửa extension (không sửa Python code):

```
1. Sửa code trong extension/ (background.js, content.js...)
2. Bump manifest.json version (ví dụ: 2.3.1 → 2.3.2)
3. KHÔNG bump APP_VERSION (giữ nguyên)
4. Chạy build_release.py → tự tạo extension ZIP + update version.json
5. Push + upload → client nhận "Extension Update" (~50KB, không restart)
```

> ⚠️ Extension hot-replace chỉ update FILE trên ổ đĩa. Chrome giữ extension CŨ trong memory
> cho đến khi Chrome restart hoặc `install_if_needed()` cycle tiếp theo reload.

