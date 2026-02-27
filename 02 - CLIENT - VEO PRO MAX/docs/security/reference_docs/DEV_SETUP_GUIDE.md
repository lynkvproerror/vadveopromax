# 🛠️ Development Environment Setup Guide

> **Version**: 1.0  
> **Updated**: 2026-02-02

---

## 📋 Mục lục

1. [Yêu cầu hệ thống](#1-yêu-cầu-hệ-thống)
2. [Cài đặt Python](#2-cài-đặt-python)
3. [Cài đặt Dependencies](#3-cài-đặt-dependencies)
4. [Thiết lập Firebase](#4-thiết-lập-firebase)
5. [Cấu hình IDE](#5-cấu-hình-ide)
6. [Chạy thử](#6-chạy-thử)
7. [Build Production](#7-build-production)

---

## 1. Yêu cầu hệ thống

| Item | Yêu cầu tối thiểu |
|------|-------------------|
| OS | Windows 10/11, macOS 10.15+, Ubuntu 20.04+ |
| Python | 3.10+ |
| RAM | 4GB+ |
| Disk | 500MB free |
| Network | Internet connection (for Firebase) |

---

## 2. Cài đặt Python

### Windows

```powershell
# Option 1: Microsoft Store
winget install Python.Python.3.12

# Option 2: Official installer
# Download từ https://www.python.org/downloads/

# Verify
python --version  # Python 3.12.x
pip --version     # pip 24.x
```

### macOS

```bash
# Homebrew
brew install python@3.12

# Verify
python3 --version
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

---

## 3. Cài đặt Dependencies

### 3.1 Tạo Virtual Environment (Khuyến khích)

```powershell
# Windows
cd "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\VEO Pro Max"
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3.2 Cài đặt packages

```bash
# Core packages
pip install customtkinter>=5.2.0
pip install firebase-admin>=6.0.0

# Optional (for full functionality)
pip install tkcalendar>=1.6.0
pip install CTkMessagebox>=2.0
pip install pyinstaller>=6.0.0
pip install pyarmor>=8.0.0
```

### 3.3 requirements.txt

Tạo file `requirements.txt`:

```txt
# GUI
customtkinter>=5.2.0
tkcalendar>=1.6.0

# Firebase
firebase-admin>=6.0.0

# Security
cryptography>=41.0.0

# Build (dev only)
pyinstaller>=6.0.0
pyarmor>=8.0.0
```

Cài đặt từ file:
```bash
pip install -r requirements.txt
```

---

## 4. Thiết lập Firebase

### 4.1 Tạo Firebase Project

1. Truy cập [console.firebase.google.com](https://console.firebase.google.com)
2. Click **"Add project"**
3. Đặt tên: `veoauto` (hoặc tên khác)
4. Tắt Google Analytics (không cần)
5. Click **"Create project"**

### 4.2 Bật Firestore Database

1. Trong Firebase Console → **Build** → **Firestore Database**
2. Click **"Create database"**
3. Chọn **"Start in production mode"**
4. Chọn location: `asia-southeast1` (Singapore)
5. Click **"Enable"**

### 4.3 Tạo Service Account Key

1. **Project Settings** (⚙️ icon) → **Service accounts**
2. Click **"Generate new private key"**
3. Download file JSON (e.g., `veoauto-firebase-adminsdk-xxxxx.json`)

### 4.4 Đặt Credentials File

Chọn 1 trong 3 cách:

**Cách 1: Folder 00_ADMIN (Dev)**
```
01 - ADMIN - License Security/
└── levanlinh.kma/
    └── firebase-credentials.json  ← Đặt ở đây
```

**Cách 2: User folder (Production)**
```
Windows: C:\Users\<username>\.veoauto\firebase-credentials.json
macOS:   ~/.veoauto/firebase-credentials.json
Linux:   ~/.veoauto/firebase-credentials.json
```

**Cách 3: Environment Variable**
```powershell
# Windows PowerShell
$env:VEO_LICENSE_CONFIG = "D:\path\to\firebase-credentials.json"

# Linux/macOS
export VEO_LICENSE_CONFIG="/path/to/firebase-credentials.json"
```

### 4.5 Thiết lập Firestore Security Rules

Trong Firestore → **Rules** tab:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // License keys - read only for clients
    match /_lic/{document=**} {
      allow read: if true;
      allow write: if false;  // Only server SDK can write
    }
    
    // License requests - clients can create
    match /_license_requests/{document=**} {
      allow read: if true;
      allow create: if true;
      allow update, delete: if false;  // Only server SDK
    }
  }
}
```

Click **"Publish"**

---

## 5. Cấu hình IDE

### 5.1 VS Code

**Extensions cần cài:**
- Python (Microsoft)
- Pylance
- Python Indent

**settings.json:**
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true
}
```

### 5.2 PyCharm

1. **File → Settings → Project → Python Interpreter**
2. Click ⚙️ → **Add** → **Existing Environment**
3. Chọn `.venv/Scripts/python.exe`

### 5.3 Cursor/Windsurf

Tương tự VS Code, sử dụng settings.json

---

## 6. Chạy thử

### 6.1 Chạy Admin GUI

```powershell
cd "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\01 - ADMIN - License Security"
python license_manager_gui.py
```

**Expected output:**
```
✅ Connected to Firebase
# GUI window opens
```

### 6.2 Chạy CLI

```powershell
cd "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\01 - ADMIN - License Security"
python -m admin.license_admin --help
```

### 6.3 Test License Client

```powershell
python -c "from client.license_client import LicenseClient; c = LicenseClient(); print(c.get_display_machine_id())"
```

**Expected output:**
```
3946C15B  # Your machine ID (8 chars)
```

---

## 7. Build Production

### 7.1 PyInstaller Build

```powershell
cd "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\VEO Pro Max"

# Build với client code only
pyinstaller --onefile --windowed ^
    --name "VEO Pro Max" ^
    --add-data "security;security" ^
    --exclude-module admin ^
    --exclude-module ctk_gui ^
    --exclude-module firebase_admin ^
    main.py
```

### 7.2 PyArmor Obfuscation (Optional)

```bash
# Obfuscate before building
pyarmor gen --enable-jit --private 05_Security/client/

# Then build with PyInstaller
pyinstaller ...
```

### 7.3 Build Checklist

```
□ Virtual environment đã activate
□ Tất cả tests pass
□ Firebase credentials KHÔNG có trong build
□ admin/ (01 - ADMIN - License Security/) KHÔNG có trong build
□ PyArmor đã obfuscate client code
□ Test trên clean machine
```

---

## 🔗 Quick Reference

| Task | Command |
|------|---------|
| Activate venv | `.\.venv\Scripts\Activate.ps1` |
| Install deps | `pip install -r requirements.txt` |
| Run GUI | `python ctk_gui/license_manager_gui.py` |
| Run CLI | `python -m admin.license_admin` |
| Build | `pyinstaller --onefile main.py` |

---

*Tài liệu này được tạo cho VEO License System. Cập nhật: 2026-02-02*
