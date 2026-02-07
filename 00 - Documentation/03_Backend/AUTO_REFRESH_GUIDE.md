# 🔄 Auto-Refresh & Token Lifecycle Guide

**Location**: `03_Backend/AUTO_REFRESH_GUIDE.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-07  

---

## 1. Token Types & Lifetimes

| Token | Lifetime | Auto-Refresh | Source |
|-------|----------|--------------|--------|
| **Access Token** | ~60 phút | ❌ Cần browser | `__NEXT_DATA__` |
| **reCAPTCHA Token** | ~90 giây | ✅ Tự động | `grecaptcha.execute()` |

---

## 2. Buffer Time (Thời Gian Đệm)

**Buffer time** = Khoảng thời gian trước khi token hết hạn để bắt đầu refresh.

```
Access Token: 60 phút
Buffer: 5 phút

│──────────────────────────────────│──────│─────│
0 min                             55 min  60 min
│        TOKEN VALID              │BUFFER│EXPIRED
                                   ▲
                          Bắt đầu refresh ở đây
```

### Constants (trong code):

```python
# refresh_manager.py
REFRESH_CHECK_INTERVAL = 30 * 60   # Check mỗi 30 phút
TOKEN_REFRESH_BUFFER = 5 * 60      # Refresh trước 5 phút

# session.py
RECAPTCHA_REFRESH = 80             # Refresh reCAPTCHA ở 80 giây
```

---

## 3. So Sánh OAuth vs Browser Refresh

### 3.1 OAuth (🔑) - Cần User

```
Token hết hạn
     │
     ▼
Code detect: is_token_expired == True
     │
     ▼
⚠️ KHÔNG THỂ auto-refresh!
   - VEO dùng OAuth implicit flow
   - Không có refresh_token
   - Token lấy từ browser session
     │
     ▼
App cần hiện thông báo: "Session expired. Please login again"
     │
     ▼
User phải: Mở browser → Login Google → App lấy token mới
```

### 3.2 Browser (🌐) - Có Thể Tự Động

```
Token hết hạn
     │
     ▼
Code detect: is_token_expired == True
     │
     ▼
App mở browser HEADLESS với profile đã lưu
     │
     ▼
Navigate labs.google/fx → Lấy token từ __NEXT_DATA__
     │
     ▼
✅ Token mới (nếu Google session còn valid)
   hoặc
⚠️ Cần user login lại (nếu Google session hết hạn)
```

---

## 4. reCAPTCHA Auto-Refresh

reCAPTCHA v3 **hoàn toàn tự động**, không cần user:

```python
# token_extractor.py
async def _extract_recaptcha_token(page):
    # Wait for grecaptcha to load
    await page.wait_for_function("typeof grecaptcha !== 'undefined'")
    
    # Execute and get token
    token = await page.evaluate('''
        async () => await grecaptcha.execute(siteKey, {action: 'generate'})
    ''')
    return token  # ~3000 chars, valid 90s
```

### Timeline trong 1 OAuth session:

```
OAuth Token: 60 phút
│─────────────────────────────────────────────────────────────────│
│                                                                  │
│   reCAPTCHA auto-refresh (mỗi 80 giây):                         │
│   │──80s──│──80s──│──80s──│ ... (~45 lần refresh)              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Tính toán: 3600s / 80s = ~45 lần reCAPTCHA refresh trong 1 OAuth session
```

---

## 5. Refresh Manager Implementation

```python
# refresh_manager.py

class CookieRefreshManager:
    """Quản lý auto-refresh."""
    
    def check_sessions_need_refresh(self) -> List[str]:
        """Check sessions cần refresh."""
        for email, session in self._sessions.items():
            # 1. Check access token
            if time_until_expiry < TOKEN_REFRESH_BUFFER:
                self.request_refresh(email, "Token expiring soon")
            
            # 2. Check reCAPTCHA
            if session.needs_recaptcha_refresh:
                self.request_refresh(email, "reCAPTCHA expired")
    
    def start_auto_check(self, interval=30*60):
        """Start background check thread."""
        Thread(target=self._auto_check_loop, daemon=True).start()
```

---

## 6. Trạng Thái Thông Báo (UI)

### Hiện tại: ⚠️ CHƯA CÓ UI NOTIFICATION

Code có emit events nhưng chưa có UI handler:

```python
# recaptcha_handler.py - có emit event
emit_event(EventType.UI_NOTIFICATION, {
    "type": "recaptcha",
    "email": email,
    "message": "reCAPTCHA detected - user action required",
})
```

### Đề xuất UI Settings:

```
┌─────────────────────────────────────────────────────────────────┐
│ 🔄 AUTO-REFRESH SETTINGS                                        │
├─────────────────────────────────────────────────────────────────┤
│ ☑️ Enable auto-refresh monitoring                                │
│                                                                  │
│ Check interval:      [30 ▾] minutes   (how often to check)      │
│ Token buffer:        [5  ▾] minutes   (refresh before expiry)   │
│ reCAPTCHA threshold: [80 ▾] seconds   (when to refresh)         │
│                                                                  │
│ ℹ️ Note: Access token refresh requires browser login.            │
│    reCAPTCHA refreshes automatically in background.              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Summary Table

| Aspect | Access Token | reCAPTCHA Token |
|--------|--------------|-----------------|
| **Lifetime** | 60 phút | 90 giây |
| **Buffer/Threshold** | 5 phút | 80 giây |
| **Auto-refresh** | ❌ (OAuth) / ⚠️ (Browser) | ✅ Fully automatic |
| **User action** | Login required | None |
| **Code location** | `auth_manager.py` | `token_extractor.py` |
| **Refresh trong 1 session** | 1 lần / giờ | ~45 lần / giờ |

---

## Cross-References

- [ACCOUNT_SESSION_MANAGEMENT.md](./ACCOUNT_SESSION_MANAGEMENT.md) - Session structure
- [TOKEN_SECURITY.md](./TOKEN_SECURITY.md) - Token extraction methods
- [CORE_MODULES_SPEC.md](./CORE_MODULES_SPEC.md) - AuthManager specification

---

**Status**: ✅ Documentation Complete
