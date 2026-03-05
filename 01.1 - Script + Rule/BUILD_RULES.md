# VEO Seller App — Build & Deploy Rules
> Tuân thủ nghiêm ngặt khi build/deploy app seller

---

## 1. Pre-Build Checklist (Tự Động)

Chạy trước MỌI lần build:
```powershell
cd "01.1 - Script + Rule"
python build_seller.py check
```

**8 checks bắt buộc PASS:**
1. ✅ Critical files tồn tại
2. ✅ Không có `.json` credentials plaintext
3. ✅ Không có `print()` lộ thông tin
4. ✅ Không có hardcoded secrets
5. ✅ `VEO_LICENSE_SECRET` env var đã set
6. ✅ `.veo.enc` encrypted credentials tồn tại
7. ✅ Syntax check pass (py_compile)
8. ✅ Không có plaintext password comparison

---

## 2. Build Rules

### Environment
```powershell
# Cần cài 1 lần:
pip install nuitka pyside6 firebase-admin

# Set env var (User scope — persistent):
[System.Environment]::SetEnvironmentVariable("VEO_LICENSE_SECRET", "<hex>", "User")
```

### Build Command
```powershell
python build_seller.py all    # Check → Build → Deploy → Verify
```

### Nuitka Settings Quan Trọng

| Setting | Giá trị | Lý do |
|---|---|---|
| `--standalone` | Required | Bundle tất cả dependencies |
| `--onefile` | Required | Gom thành 1 file .exe |
| `--enable-plugin=pyside6` | Required | GUI framework support |
| `--windows-console-mode=disable` | Required | Ẩn console window |
| `--include-module=firebase_admin` | Required | Dynamic import |
| `--include-module=google.cloud.firestore_v1` | Required | Firestore SDK |
| `--include-data-dir=primary=primary` | Required | Encrypted credentials |

---

## 3. Deploy Rules

### ❌ KHÔNG BAO GIỜ gửi cho seller:
- File `.json` credentials
- File `.py` source code (nếu đã build exe)
- File `.integrity` (tạo lại tự động)
- File `__pycache__/`
- File `PLAN.md`, `README.md`
- File `build_seller.py`
- Folder `01.1 - Script + Rule`

### ✅ Output folder (`01.2 - Seller Management Final Tool`):
```
01.2 - Seller Management Final Tool/
├── SellerManager.exe     ← Compiled binary
└── version.json          ← Build info
```

### Nếu deploy Python files (không build exe):
```
01.0 - Seller Management/
├── primary/cred.veo.enc
├── backup/cred.veo.enc
├── seller_auth.py
├── seller_manager_gui.py
├── firebase_config.py
├── cred_protector.py
└── license_keygen.py
```

---

## 4. Sau Khi Sửa Code

```
Sửa code → Xóa .integrity → Xóa __pycache__ → Test → Build lại
```

```powershell
# Quick cleanup
Remove-Item "01.0 - Seller Management\.integrity" -Force -ErrorAction SilentlyContinue
Remove-Item "01.0 - Seller Management\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
```

---

## 5. Khi Thêm Seller Mới

1. Admin app → tạo seller (MID + password)
2. Gửi `SellerManager.exe` (hoặc folder Python)
3. Cung cấp `VEO_LICENSE_SECRET` value cho seller
4. Seller chạy app → đăng nhập bằng password

---

## 6. Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| "File ứng dụng bị thay đổi" | `.integrity` HMAC bị forge | Xóa `.integrity` (auto-regenerate) |
| "VEO_LICENSE_SECRET not set" | Env var chưa set | `set VEO_LICENSE_SECRET=<hex>` |
| "Môi trường không an toàn" | Anti-debug phát hiện debugger | Đóng Wireshark/Fiddler/IDE debugger |
| "Phiên hết hạn" | Token 30 phút | Restart app |
| Nuitka build lỗi module | Dynamic import thiếu | Thêm `--include-module=<name>` |
