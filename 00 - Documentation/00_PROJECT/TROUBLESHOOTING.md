# 🔧 Troubleshooting Guide

**Location**: `Documentation/00_PROJECT/TROUBLESHOOTING.md`  
**Last Updated**: 2026-02-04

---

## 🔴 Authentication Issues

### Error: `401 Unauthorized`

| Cause | Solution |
|-------|----------|
| Auth token expired | Click 🔄 Refresh on profile |
| Wrong account | Check active profile in Settings |
| Session cookie invalid | Click 🌐 to re-login |

**Steps:**
1. Go to Settings → Chrome Profiles
2. Find the affected profile
3. Click 🌐 Open Browser
4. Login to Google if needed
5. Visit `labs.google.com/fx`
6. Close browser
7. Click 🔄 Refresh

---

### Error: `403 Forbidden`

| Cause | Solution |
|-------|----------|
| reCAPTCHA token expired | Auto-refreshes on next request |
| `x-browser-*` headers missing | Check browser headers extraction |
| IP blocked | Use VPN or wait |

---

## 🟡 Generation Issues

### Error: `QUOTA_EXCEEDED`

**Meaning**: Account credits depleted.

| Plan | Credits/Month | Action |
|------|---------------|--------|
| Ultra | ~45,000 | Switch to another Ultra account |
| Pro | ~1,000 | Upgrade or use Free account |
| Free | ~50 | Wait for monthly reset |

**Steps:**
1. Check Credits column in Settings
2. If 0, switch to another profile
3. Or wait for monthly credit reset

---

### Error: `VIDEO_GENERATION_FAILED`

| Cause | Solution |
|-------|----------|
| Prompt too long | Shorten to <500 chars |
| Invalid aspect ratio | Use 16:9, 9:16, or 1:1 |
| Server overload | Retry in 5 minutes |
| Content policy | Modify prompt content |

---

### Status: `STUCK_AT_GENERATING`

**Symptoms**: Progress shows % but never completes.

**Solutions:**
1. Wait up to 5 minutes
2. Check network connection
3. Cancel and retry
4. Try different model (Veo 2 instead of 3.1)

---

## 🟠 Browser Issues

### Chrome Profile Not Working

| Issue | Solution |
|-------|----------|
| Profile folder deleted | Recreate profile |
| Profile corrupted | Delete and add new |
| Chrome version mismatch | Update Chrome |

**Steps:**
1. Delete the problematic profile
2. Click ➕ Add Profile
3. Login fresh

---

### reCAPTCHA Keeps Failing

| Cause | Solution |
|-------|----------|
| Browser fingerprint blocked | Clear profile cache |
| Too many requests | Wait 30 minutes |
| Headless detection | Use visible browser mode |

---

## 🔵 Project Issues

### Error: `PROJECT_NOT_FOUND`

**Meaning**: VEO Project ID invalid.

**Solutions:**
1. Click 🔄 Refresh on account
2. Check if project was deleted on VEO website
3. Create new project automatically

---

### Error: `UPLOAD_FAILED`

| Cause | Solution |
|-------|----------|
| Image too large | Resize to <10MB |
| Invalid format | Use PNG, JPG, WEBP |
| Network timeout | Retry with smaller file |

---

## 🟣 UI Issues

### Queue Not Updating

| Cause | Solution |
|-------|----------|
| UI freeze | Click Refresh button |
| Worker stopped | Check worker status in status bar |
| Database sync | Wait 5 seconds, check again |

---

### Settings Not Saving

| Cause | Solution |
|-------|----------|
| Permission denied | Run as admin |
| Config file locked | Close other instances |
| Disk full | Free up space |

---

## 📊 Diagnostic Commands

### Check Session Status

```python
# In Dev Console (TAB_10)
print(account_manager.get_active_sessions())
```

### Check Queue Status

```python
# In Dev Console
print(queue_manager.get_all_tasks())
```

### Check Worker Health

```python
# In Dev Console
print(worker_pool.get_status())
```

---

## 🆘 Still Need Help?

1. Check [Error Handling Strategy](../03_Backend/ERROR_HANDLING_STRATEGY.md)
2. Review [Architecture Overview](./ARCHITECTURE_OVERVIEW.md)
3. Open [Dev Console](../01_UI_UX/TAB_10_DEV_CONSOLE.md) for debugging

---

## 🔗 Related

- [ERROR_HANDLING_STRATEGY.md](../03_Backend/ERROR_HANDLING_STRATEGY.md)
- [API_MAPPING.md](../02_Architecture/API_MAPPING.md)

---

## 🔥 Firebase Connection Issues

### Error: "Firebase credentials not found"

**Nguyên nhân:** Không tìm thấy file credentials JSON

**Vị trí tìm kiếm theo thứ tự:**
1. `$env:VEO_LICENSE_CONFIG`
2. `$env:GOOGLE_APPLICATION_CREDENTIALS`
3. `00_ADMIN/veoauto-*.json`
4. `00_ADMIN/firebase-credentials.json`
5. `~/.veoauto/firebase-credentials.json`

### Error: "Failed to initialize Firebase"

**Kiểm tra:**
1. File JSON có đúng format không?
2. Project ID có tồn tại trên Firebase Console?
3. Service account có quyền Firestore không?

### Error: "Permission denied" khi đọc/ghi Firestore

1. Vào Firebase Console → Firestore → Rules
2. Kiểm tra rules cho collection `_lic` và `_license_requests`
3. Xem [FIREBASE_SECURITY_RULES.md](../03_Backend/FIREBASE_SECURITY_RULES.md)

### Error: "Network unreachable" / Timeout

```powershell
# Test connection
Test-NetConnection -ComputerName "firestore.googleapis.com" -Port 443

# Bypass proxy (if needed)
$env:NO_PROXY = "*.googleapis.com,*.google.com"
```

---

## 🔑 License Validation Errors

| Error | Nguyên nhân | Giải pháp |
|-------|-------------|-----------|
| "Machine ID mismatch" | License từ máy khác | Kiểm tra MID: `client.get_display_machine_id()` |
| "License expired" | Key hết hạn | Admin gia hạn qua GUI hoặc CLI |
| "License revoked" | Key bị thu hồi | Contact admin để cấp key mới |
| "Key format invalid" | Sai format v2.3 | Format: `XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX` (8×4 hex) |

---

## 🖥️ Admin GUI Issues

| Issue | Giải pháp |
|-------|-----------|
| "No module named 'customtkinter'" | `pip install customtkinter>=5.2.0` |
| GUI không hiển thị / Crash | Check `python -c "import customtkinter; print(customtkinter.__version__)"` |
| Bảng trống / Không có dữ liệu | Check Firebase connection + collection `_lic` |
| Theme không đúng | `ctk.set_appearance_mode("dark")` |

---

## 📦 Build/Packaging Issues

| Error | Giải pháp |
|-------|-----------|
| PyInstaller "Failed to execute script" | Build với `--console` để xem lỗi |
| "ModuleNotFoundError" trong exe | Thêm `--hidden-import=firebase_admin` |
| File exe quá lớn (>100MB) | `--exclude-module matplotlib numpy pandas` |
| Anti-virus block exe | Sign exe hoặc submit false positive report |

---

## 🔍 Debug Mode

```python
# Bật debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Hoặc environment variable
import os
os.environ['VEO_DEBUG'] = '1'
```

**Log files:**
```
Windows: %USERPROFILE%\.veoauto\logs\
├── license.log      # License validation logs
├── firebase.log     # Firebase operations
└── error.log        # Uncaught exceptions
```

---

## Common Error Messages

| Error | Nguyên nhân | Giải pháp |
|-------|-------------|-----------|
| `CERTIFICATE_VERIFY_FAILED` | SSL certificate issue | `pip install --upgrade certifi` |
| `quota exceeded` | Firebase free tier limit | Upgrade plan hoặc optimize queries |
| `DEADLINE_EXCEEDED` | Network timeout | Check connection, retry |
| `ALREADY_EXISTS` | Key đã tồn tại | Dùng key khác hoặc delete cũ |
| `NOT_FOUND` | Document không tồn tại | Check key ID chính xác |
| `UNAUTHENTICATED` | Credentials expired | Regenerate service account key |

---

## 🆕 🚀 Deployment Setup Steps

> Migrated from archive: `OUTSTANDING_ISSUES_TASK.md`

### Quick Start (5 Steps)

1. **Set Environment Variables**
```powershell
setx VEO_LICENSE_SECRET "your-secret-key-here"
setx GOOGLE_APPLICATION_CREDENTIALS "path/to/firebase-credentials.json"
```

2. **Install Dependencies**
```bash
pip install -r requirements.txt
# Includes: firebase-admin, PySide6, playwright, httpx, cryptography
```

3. **Deploy Firebase Rules**
```bash
firebase deploy --only firestore:rules
# See: 03_Backend/FIREBASE_SECURITY_RULES.md
```

4. **Build EXE (Production)**
```bash
python build.py
# Output: dist/VEO_Pro_Max.exe
```

5. **Launch Admin GUI**
```bash
python 05_Security/admin/license_manager_gui.py
```

