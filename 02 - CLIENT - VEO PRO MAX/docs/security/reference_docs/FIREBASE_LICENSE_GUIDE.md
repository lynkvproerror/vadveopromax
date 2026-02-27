# 🔥 Firebase License Management - Hướng dẫn chi tiết

**Version**: 1.0  
**Updated**: 2026-01-20  
**Purpose**: Setup Firebase và quản lý license keys

---

## 📋 Mục lục

1. [Setup Firebase Console](#1-setup-firebase-console)
2. [Cấu hình Credentials](#2-cấu-hình-credentials)
3. [Cấu trúc dữ liệu Firestore](#3-cấu-trúc-dữ-liệu-firestore)
4. [Admin Commands](#4-admin-commands)
5. [Quản lý Key hết hạn](#5-quản-lý-key-hết-hạn)
6. [Firebase Console UI](#6-firebase-console-ui)

---

## 1. Setup Firebase Console

### Bước 1.1: Tạo Project

1. Truy cập: https://console.firebase.google.com
2. Click "Add project"
3. Đặt tên: `veoauto` (hoặc tên bạn muốn)
4. Disable Google Analytics (không cần cho license)
5. Click "Create project"

### Bước 1.2: Enable Firestore Database

1. Trong Firebase Console → Build → Firestore Database
2. Click "Create database"
3. Chọn location gần nhất (ví dụ: `asia-southeast1` cho VN)
4. Start in **production mode** (bạn sẽ set rules sau)

### Bước 1.3: Tạo Service Account

1. Project Settings (⚙️) → Service accounts
2. Click "Generate new private key"
3. Download file JSON → **Lưu an toàn!**
4. Đổi tên file thành: `firebase-credentials.json`

---

## 2. Cấu hình Credentials

### Đặt file credentials

Đặt file `firebase-credentials.json` vào **một trong các vị trí** sau:

```
# Option 1: Trong folder admin (khuyến nghị)
01 - ADMIN - License Security/
├── levanlinh.kma/
│   └── firebase-credentials.json  ← Đặt ở đây
├── license_admin.py
├── license_keygen.py
└── ...

# Option 2: Trong HOME directory
~/.veoauto/
└── firebase-credentials.json

# Option 3: Dùng environment variable
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/firebase-credentials.json"
# hoặc
export VEO_LICENSE_CONFIG="/path/to/firebase-credentials.json"
```

### Kiểm tra kết nối

```bash
python license_admin.py list

# Kết quả mong đợi:
# ✅ Connected to Firebase
# 
# KEY (v2.3)                                    MID      STATUS   EXPIRES
# --------------------------------------------------------------------------------
# F208-72DF-9B1D-4BF6-****-****                 ****C15B ✅       2026-05-01
# --------------------------------------------------------------------------------
# Total: 1 keys
```

---

## 3. Cấu trúc dữ liệu Firestore

### Collection: `_lic`

Mỗi document trong collection `_lic` có cấu trúc:

```
Document ID: F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B  (đây chính là key v2.3)

Fields:
┌──────────────┬─────────────────────────────┬────────────────────────────┐
│ Field        │ Type                        │ Mô tả                      │
├──────────────┼─────────────────────────────┼────────────────────────────┤
│ _dur         │ number                      │ Số ngày (30/90/180/365)   │
│ _st          │ string                      │ Status: a=active, r=revoked│
│ _mid         │ string                      │ Machine ID (SHA256 hash)   │
│ _exp         │ timestamp                   │ Ngày hết hạn               │
│ _cr          │ timestamp                   │ Ngày tạo key               │
│ _em          │ string (nullable)           │ Email khách hàng           │
│ _nt          │ string (nullable)           │ Ghi chú của admin          │
│ _rv_at       │ timestamp (nullable)        │ Thời điểm thu hồi          │
│ _rv_reason   │ string (nullable)           │ Lý do thu hồi              │
└──────────────┴─────────────────────────────┴────────────────────────────┘
```

### Xem trong Firebase Console

1. Firebase Console → Firestore Database
2. Click collection `_lic`
3. Bạn sẽ thấy danh sách documents (mỗi cái là 1 key)

```
_lic/
├── F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B
│   ├── _dur: 90
│   ├── _st: "a"
│   ├── _mid: "3946c15b..."
│   ├── _exp: May 1, 2026 at 3:27:25 AM UTC+7
│   ├── _cr: February 4, 2026 at 3:27:25 AM UTC+7
│   └── _em: "customer@example.com"
│
├── A1B2-C3D4-E5F6-7890-... (document khác)
└── ...
```

---

## 4. Admin Commands

### 4.1 Tạo key mới

```bash
# Tạo key 3 Tháng cho machine ID 3946C15B
python license_admin.py create \
    --machine-id 3946C15B \
    --duration 90 \
    --email customer@example.com

# Output (v2.3 format - pure hex):
# ✅ Connected to Firebase
# 🔑 Generated: F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B
#    Machine ID: 3946C15B
#    Duration: 90 ngày (3 Tháng)
#    Expires: 2026-05-01
# ✅ Uploaded to Firebase
```

**Duration options:**
- `7` = Trial (7 ngày miễn phí)
- `30` = 1 Tháng (300,000đ)
- `90` = 3 Tháng (500,000đ)
- `180` = 6 Tháng (800,000đ)  
- `365` = 1 Năm (1,200,000đ)
- `36500` = Vĩnh viễn (3,000,000đ)

### 4.2 Liệt kê tất cả keys

```bash
python license_admin.py list

# Output:
# KEY (v2.3)                                    MID      STATUS   EXPIRES
# --------------------------------------------------------------------------------
# F208-72DF-9B1D-4BF6-****-****                 ****C15B ✅       2026-05-01
# A1B2-C3D4-E5F6-7890-****-****                 ****CD34 ✅       2026-06-15
# 1234-5678-90AB-CDEF-****-****                 ****7ZAB ❌       2026-03-01
# --------------------------------------------------------------------------------
# Total: 3 keys
```

### 4.3 Kiểm tra key cụ thể

```bash
python license_admin.py check F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B

# Output:
# 🔍 Key: F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B
#    Machine ID: ****C15B (hash stored)
#    Duration: 90 ngày (3 Tháng)
#    Status: Active
#    Expires: 2026-05-01
#    Email: customer@example.com
```

### 4.4 Thu hồi key

```bash
# Thu hồi với lý do
python license_admin.py revoke F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B \
    --reason "Customer requested refund"

# Output:
# ✅ Revoked: F208-72DF-9B1D-4BF6-661F-10F4-A3C2-8E7B
#    Reason: Customer requested refund
```

---

## 5. Quản lý Key hết hạn

### 5.1 Xem keys hết hạn trong Firebase Console

1. Firestore Database → `_lic` collection
2. Click "Add filter" (icon filter)
3. Field: `_exp`, Operator: `<`, Value: `<today's date>`
4. Bạn sẽ thấy tất cả keys đã hết hạn

### 5.2 Script tự động thu hồi keys hết hạn

Tạo file `cleanup_expired_keys.py`:

```python
"""
Cleanup expired license keys
Run daily via cron/scheduler
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from pathlib import Path

def cleanup_expired_keys():
    # Init Firebase
    cred_path = Path(__file__).parent / "levanlinh.kma" / "firebase-credentials.json"
    if not firebase_admin._apps:
        cred = credentials.Certificate(str(cred_path))
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    now = datetime.now()
    
    # Query expired keys that are still active
    expired_docs = db.collection("_lic") \
        .where("_st", "==", "a") \
        .where("_exp", "<", now) \
        .stream()
    
    count = 0
    for doc in expired_docs:
        doc.reference.update({
            "_st": "e",  # expired
            "_expired_at": firestore.SERVER_TIMESTAMP
        })
        print(f"⏰ Expired: {doc.id}")
        count += 1
    
    print(f"\n✅ Total cleaned: {count} keys")

if __name__ == "__main__":
    cleanup_expired_keys()
```

### 5.3 Chạy tự động hàng ngày

**Windows (Task Scheduler):**
1. Mở Task Scheduler
2. Create Basic Task → Name: "VEO License Cleanup"
3. Trigger: Daily at 00:00
4. Action: Start a program
5. Program: `python`
6. Arguments: `cleanup_expired_keys.py`
7. Start in: `D:\...\09_Security`

**Linux/Mac (Cron):**
```bash
# Mở crontab editor
crontab -e

# Thêm dòng (chạy lúc 00:00 mỗi ngày)
0 0 * * * cd /path/to/09_Security && python cleanup_expired_keys.py >> /var/log/veo_cleanup.log 2>&1
```

---

## 6. Firebase Console UI

### 6.1 Xem trực tiếp trong Firebase

1. Truy cập: https://console.firebase.google.com
2. Chọn project của bạn
3. Build → Firestore Database
4. Click collection `_lic`

### 6.2 Tìm kiếm key theo email

1. Trong Firestore Database
2. Add filter: `_em` == `customer@example.com`
3. Xem tất cả keys của customer này

### 6.3 Chỉnh sửa key trực tiếp

1. Click vào document (key)
2. Click vào field muốn sửa
3. Thay đổi giá trị
4. Tự động lưu!

**Các trường hay sửa:**
- `_st`: Đổi từ `a` → `r` để thu hồi
- `_exp`: Gia hạn thêm thời gian
- `_nt`: Thêm ghi chú

### 6.4 Backup dữ liệu

```bash
# Export tất cả licenses
gcloud firestore export gs://your-bucket-name/backups/$(date +%Y%m%d)

# Hoặc dùng Firebase Console:
# Project Settings → Usage and billing → Export data
```

---

## 📊 Status Codes

| Code | Tên | Mô tả |
|------|-----|-------|
| `a` | Active | Key đang hoạt động |
| `r` | Revoked | Admin đã thu hồi |
| `e` | Expired | Quá hạn sử dụng |
| `s` | Suspended | Tạm ngưng (điều tra) |

---

## ⚠️ Lưu ý bảo mật

1. **KHÔNG commit file credentials vào Git!**
   ```
   # .gitignore
    # Credentials folder (e.g. levanlinh.kma/)
   *-credentials.json
   *-adminsdk*.json
   ```

2. **Firestore Security Rules** (nếu cần client đọc):
   ```javascript
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       match /_lic/{licenseId} {
         // Chỉ cho phép đọc, không cho phép ghi từ client
         allow read: if request.auth != null;
         allow write: if false;  // Chỉ admin SDK mới ghi được
       }
     }
   }
   ```

3. **Rotate credentials định kỳ** (mỗi 3-6 tháng)

---

## 🔧 Troubleshooting

### "Firebase credentials not found"
```bash
# Kiểm tra file có tồn tại
ls -la levanlinh.kma/

# Hoặc set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="./levanlinh.kma/firebase-credentials.json"
```

### "Permission denied"
- Kiểm tra Service Account có quyền `Cloud Datastore User`
- IAM & Admin → Service Accounts → Edit → Add role

### "Collection not found"
- Collection `_lic` tự động tạo khi bạn tạo key đầu tiên
- Nếu chưa có, chạy: `python license_admin.py create --machine-id TEST123 --duration 7`
