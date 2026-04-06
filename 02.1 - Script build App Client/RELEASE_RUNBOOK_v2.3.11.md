# Release Runbook v2.3.11

Status date: 2026-03-31

> Đây là tài liệu vận hành DUY NHẤT cho release `v2.3.11`.
> Tài liệu này bao trọn:
> - ZIP app + extension trong thư mục `03 - Final App Client`
> - Installer `.exe` trong thư mục `03.1-Installer`
>
> `BUILD_RULES.md` chỉ còn là tài liệu policy/rule nền, không dùng như checklist thao tác.

## 1. Mục tiêu release

- App target version: `2.3.11`
- Extension target version: `2.3.11`
- Extension payload mode cho release/debug window này: `plaintext` bằng cờ `--plain-extension`
- Chưa compile/build/publish cho đến khi có xác nhận cuối

## 2. Output chuẩn cần tạo

### 2.1. Output tại `03 - Final App Client`

Thư mục này là đầu ra cho app release và metadata update:

```text
03 - Final App Client/
├── main.dist/                     ← dist app sau compile
├── VEO_Pro_Max_v2.3.11.zip        ← full ZIP app
├── VEO_Extension_v2.3.11.zip      ← extension-only ZIP
├── version.json                   ← metadata update
├── build_info.json                ← build metadata
├── README.md
└── CHANGELOG.md
```

### 2.2. Output tại `03.1-Installer`

Thư mục này là đầu ra cho installer Windows:

```text
03.1-Installer/
├── VEO_Pro_Max_Setup_v2.3.11.iss
├── VEO_Pro_Max_Setup_v2.3.11.exe
└── installer_build_info.json
```

## 3. Một lệnh sinh cả `03` và `03.1`

Khi đã xác nhận build thật:

```powershell
python build_release.py --plain-extension
```

Hoặc dùng wrapper:

```powershell
build_app.bat
```

> `build_app.bat` KHÔNG tự viết lệnh `gh release` riêng.
> Nó chỉ gọi `build_release.py --plain-extension`, và chính `build_release.py`
> mới là nơi thực hiện:
> - tạo ZIP app
> - tạo ZIP extension
> - tạo installer `.exe`
> - upload asset lên GitHub Release
> - push `version.json` ra public repo
>
> Wrapper này hiện:
> - chạy `preflight` trước
> - bật Python unbuffered để log hiện ra ngay
> - hỏi xác nhận trước khi vào full build
> - cảnh báo trước việc build đầu có thể chậm do Nuitka tải MinGW64 trên Windows
> - khi vào full build sẽ in heartbeat định kỳ từ `build_app.bat`
> - heartbeat hiển thị tiến trình `python/cl/link`, kích thước log và 5 dòng log cuối
> - log live được ghi vào `02.1 - Script build App Client/build_app_live.log`

Kết quả mong đợi của MỘT lệnh này:

- Compile app vào `03 - Final App Client/main.dist`
- Tạo `VEO_Pro_Max_v2.3.11.zip` trong `03 - Final App Client`
- Tạo `VEO_Extension_v2.3.11.zip` trong `03 - Final App Client`
- Tạo `version.json` và `build_info.json` trong `03 - Final App Client`
- Render `.iss` và build `VEO_Pro_Max_Setup_v2.3.11.exe` trong `03.1-Installer`
- Nếu không dùng `--skip-publish`, script sẽ tiếp tục push/release theo flow hiện tại

## 4. Lệnh theo từng giai đoạn

### 4.1. Giai đoạn debug, chưa build

```powershell
python build_release.py --preflight --plain-extension
python build_release.py --archive-assets --preflight --plain-extension
```

Mục tiêu:

- Check version app/extension
- Check changelog
- Check `dist/data` không còn `.md`
- Check output cũ còn sót hay không
- Archive ZIP/setup top-level cũ để tránh publish nhầm

### 4.2. Giai đoạn package trên `main.dist` có sẵn, chưa publish

```powershell
python build_release.py --plain-extension --package-only --skip-compile
```

Lệnh này dùng khi:

- Đã có `main.dist` sẵn
- Muốn tạo lại ZIP ở `03`
- Muốn tạo lại installer ở `03.1`
- Chưa muốn push git/GitHub Release

Kết quả:

- Có ZIP app + extension ở `03`
- Có installer `.exe` ở `03.1`
- Có SHA local cập nhật vào `version.json`
- Không push git
- Không tạo GitHub Release
- Không publish `version.json` ra public repo

### 4.3. Giai đoạn build riêng installer từ `main.dist` có sẵn

```powershell
python build_release.py --installer-only
```

Lệnh này chỉ xử lý `03.1-Installer`:

- Giữ nguyên build metadata trong `03`
- Không compile lại app
- Không tạo lại ZIP
- Không publish
- Dùng khi chỉ muốn re-build installer từ `main.dist` hiện có

### 4.4. Giai đoạn full release sau khi xác nhận

```powershell
python build_release.py --plain-extension
```

Lệnh này là full flow:

- Compile
- Mã hóa `data/`
- Deploy `extension/` dạng plaintext
- Tạo ZIP ở `03`
- Tạo installer ở `03.1`
- Push/release nếu không tắt publish

## 5. Rule khóa cho release window này

- `APP_VERSION` và `manifest.json version` đang chủ động đồng bộ ở `2.3.11`
- `data/` encryption vẫn bắt buộc
- `extension/` được phép ship plaintext JS cho release/debug cycle này
- Không sửa tay `03 - Final App Client/version.json`
- Không build khi chưa xác nhận cuối

## 6. Trạng thái hiện tại

- `APP_VERSION = 2.3.11`
- `manifest.json version = 2.3.11`
- `CHANGELOG.txt` đã cập nhật nháp `v2.3.11`
- Script đã hỗ trợ:
  - `--plain-extension`
  - `--preflight`
  - `--archive-assets`
  - `--package-only`
- Asset top-level cũ đã được archive khỏi `03` và `03.1`

## 7. Checklist trước khi xác nhận build

- Debug xong phần app
- Debug xong phần extension
- Không đổi thêm version nếu chưa có scope mới
- Chốt lại changelog client-facing
- Chạy lại:

```powershell
python build_release.py --preflight --plain-extension
```

## 8. Checklist sau khi xác nhận build

### 8.1. Verify output `03`

- Có `VEO_Pro_Max_v2.3.11.zip`
- Có `VEO_Extension_v2.3.11.zip`
- `version.json` có `version = 2.3.11`
- `version.json` có `ext_version = 2.3.11`
- `sha256` và `ext_sha256` đã được điền

### 8.2. Verify output `03.1`

- Có `VEO_Pro_Max_Setup_v2.3.11.iss`
- Có `VEO_Pro_Max_Setup_v2.3.11.exe`
- Có `installer_build_info.json`

### 8.3. Verify payload nội bộ

- `main.dist/data` chỉ còn `.enc`
- `main.dist/extension` là plaintext JS khi dùng `--plain-extension`
- Installer lấy đúng payload từ `main.dist`

## 9. Ghi nhớ nhanh

- Muốn ra cả ZIP ở `03` và installer ở `03.1`: dùng cùng một flow `build_release.py`
- Muốn chỉ ra installer ở `03.1`: dùng `--installer-only`
- Muốn đóng gói lại nhưng chưa publish: dùng `--package-only --skip-compile`
