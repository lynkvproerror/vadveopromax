# 🔐 Account Session Management

**Location**: `03_Backend/ACCOUNT_SESSION_MANAGEMENT.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-07  
**Source**: Verified from HAR files (`F12 Dev/Old`, `F12 Dev/New`) + Research guides

---

## 1. Overview

Quản lý session, credentials, và auto-refresh cho các tài khoản VEO.

### 1.1 Thông tin cần quản lý

| Component | Lifetime | Auto-Refresh? | Source |
|-----------|----------|---------------|--------|
| **Auth Token** | ~1 hour | ✅ Yes | `__NEXT_DATA__` hoặc browser intercept |
| **reCAPTCHA Token** | ~90 sec | ✅ Yes | `grecaptcha.enterprise.execute()` |
| **Cookies** | ~30 days | ⚠️ On error | Browser profile |
| **Subscription (sku)** | Real-time | ✅ Per-request | API response |
| **Credits** | Real-time | ✅ Per-request | API response |
| **userPaygateTier** | Per-request | ✅ Automatic | Sent in clientContext |
| **Project ID** | Indefinite | ❌ On demand | API: `/v1/projects` |

---

## 2. ⚠️ CRITICAL: Subscription Detection (Verified)

### 2.1 Cách phát hiện loại tài khoản

**KHÔNG dựa vào tên user trong `__NEXT_DATA__`!**

Subscription được xác định qua **API response** từ `aisandbox-pa.googleapis.com`:

```json
// Actual response from HAR file (Ultra account)
{
  "credits": 43930,
  "userPaygateTier": "PAYGATE_TIER_TWO",
  "sku": "WS_ULTRA"
}
```

```json
// Actual response from HAR file (Free/Regular account)
{
  "credits": 50,
  "userPaygateTier": "PAYGATE_TIER_NOT_PAID",
  "sku": "WS_FREEMIUM"
}
```

### 2.2 Plan Matrix (Verified from HAR)

| Plan | SKU | userPaygateTier | Credits/Month | Features |
|------|-----|-----------------|---------------|----------|
| **🚀 Ultra** | `WS_ULTRA` | `PAYGATE_TIER_TWO` | ~45,000 | VEO 3.1, 4K, 16s |
| **💎 Pro** | `WS_PRO` | `PAYGATE_TIER_ONE` | ~1,000 | VEO 3.1, 1080p |
| **👤 Freemium** | `WS_FREEMIUM` | `PAYGATE_TIER_NOT_PAID` | ~50 | VEO 2, 720p |

### 2.3 Detection Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SUBSCRIPTION DETECTION FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ❌ WRONG: Check user name in __NEXT_DATA__                                 │
│     user.name = "Veo Ultra" → Does NOT mean Ultra subscription!            │
│                                                                              │
│  ✅ CORRECT: Check API response fields                                      │
│                                                                              │
│  Any API call to aisandbox-pa.googleapis.com                                 │
│      │                                                                       │
│      ▼                                                                       │
│  Response contains:                                                          │
│      {                                                                       │
│        "credits": 43930,                    ← Remaining credits             │
│        "userPaygateTier": "PAYGATE_TIER_TWO", ← Tier indicator              │
│        "sku": "WS_ULTRA"                    ← Plan name                     │
│      }                                                                       │
│      │                                                                       │
│      ▼                                                                       │
│  Detection Logic:                                                            │
│      if sku === "WS_ULTRA" || tier === "PAYGATE_TIER_TWO"                   │
│          → ULTRA                                                            │
│      else if sku === "WS_FREEMIUM" || tier === "PAYGATE_TIER_NOT_PAID"     │
│          → FREEMIUM                                                          │
│      else                                                                    │
│          → PRO                                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Session Data Structure

### 3.1 Data from __NEXT_DATA__ (session_dump.json)

```json
{
  "user": {
    "name": "Veo Ultra",
    "email": "ultra8574632@tk.solsticeenergyvn.com",
    "image": "https://lh3.googleusercontent.com/a/ACg8ocJXuEWPz6..."
  },
  "expires": "2026-02-01T17:19:40.000Z",
  "access_token": "ya29.a0AUMWg_KPc2U38_E33Zf2LZdTXtSB__mEBYf4oY_pUoLfHMt7GgAkxdiy..."
}
```

**⚠️ Note**: `user.name` is just display name, NOT subscription indicator!

### 3.2 Complete Session Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ACCOUNT SESSION ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     AccountSession (Data Class)                      │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │                                                                      │    │
│  │  From __NEXT_DATA__:                                                 │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │ email: "user@gmail.com"                                      │    │    │
│  │  │ display_name: "Veo Ultra"  ← Just display name!              │    │    │
│  │  │ avatar_url: "https://..."                                    │    │    │
│  │  │ access_token: "ya29.a0..."  ← OAuth token                    │    │    │
│  │  │ expires: "2026-02-01T17:19:40.000Z"                          │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  │  From API Response:                                                  │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │ sku: "WS_ULTRA" | "WS_PRO" | "WS_FREEMIUM"                   │    │    │
│  │  │ userPaygateTier: "PAYGATE_TIER_TWO" | "TIER_ONE" | "NOT_PAID"│    │    │
│  │  │ credits: 43930                                               │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  │  From Browser:                                                       │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │ recaptcha_token: "03AFY_..."  ← From grecaptcha.execute()    │    │    │
│  │  │ cookies: {...}                                               │    │    │
│  │  │ profile_path: "C:/profiles/acc1"                             │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. clientContext Structure (Verified from HAR)

Mọi request đều cần `clientContext`:

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "<~3000 char token>",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769822770783",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  }
}
```

### 4.1 Field Requirements

| Field | Required | Source | Refresh Needed |
|-------|----------|--------|----------------|
| `recaptchaContext.token` | ✅ Generate/Upscale | Browser | Every 90 sec |
| `sessionId` | ✅ All | Client | None (timestamp) |
| `projectId` | ✅ All | API `/v1/projects` | On account change |
| `tool` | ✅ Most | Static | None |
| `userPaygateTier` | Optional | API response | On login |

---

## 5. Token Lifecycle

### 5.1 Token Lifetimes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TOKEN LIFECYCLE                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ACCESS TOKEN (OAuth):                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  Source: __NEXT_DATA__.props.pageProps.session.access_token         │    │
│  │  Format: Bearer ya29.a0AUMWg_... (~200-300 chars)                   │    │
│  │  Lifetime: ~60 minutes                                               │    │
│  │  Refresh: Reload page or intercept from browser                      │    │
│  │                                                                      │    │
│  │  0 min          50 min              60 min                           │    │
│  │  │───────────────│──────────────────│                               │    │
│  │  │    VALID      │  REFRESH ZONE    │  EXPIRED                      │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  reCAPTCHA TOKEN:                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  Source: grecaptcha.enterprise.execute()                            │    │
│  │  Site Key: 6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV                 │    │
│  │  Length: ~3000 characters                                            │    │
│  │  Lifetime: ~90-120 seconds                                           │    │
│  │                                                                      │    │
│  │  0 sec          80 sec      90 sec   120 sec                        │    │
│  │  │───────────────│───────────│────────│                             │    │
│  │  │    VALID      │ PRE-FETCH │ UNSAFE │ EXPIRED                     │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Auto-Refresh Flow

### 6.1 Refresh Schedule

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AUTO-REFRESH SCHEDULE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌── Every Request ────────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  API response contains:                                              │    │
│  │  {                                                                   │    │
│  │    "credits": 43930,                                                 │    │
│  │    "userPaygateTier": "PAYGATE_TIER_TWO",                           │    │
│  │    "sku": "WS_ULTRA"                                                 │    │
│  │  }                                                                   │    │
│  │                                                                      │    │
│  │  → Update session.credits, session.sku on every response            │    │
│  │                                                                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌── Every ~60 seconds ────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  Check reCAPTCHA token age:                                          │    │
│  │      If age > 80 sec → Pre-fetch new token                          │    │
│  │                                                                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌── Every ~50 minutes ────────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  Check auth token:                                                   │    │
│  │      If age > 50 min → Refresh from browser                         │    │
│  │                                                                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌── On Startup / On Error ────────────────────────────────────────────┐    │
│  │                                                                      │    │
│  │  Full refresh:                                                       │    │
│  │      1. Load browser profile                                         │    │
│  │      2. Navigate to labs.google                                      │    │
│  │      3. Extract __NEXT_DATA__ (access_token)                         │    │
│  │      4. Get reCAPTCHA token                                          │    │
│  │      5. Make any API call → Get sku, credits, tier                  │    │
│  │                                                                      │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Implementation

### 7.1 AccountSession Data Class

```python
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class SubscriptionType(Enum):
    """Based on 'sku' field from API response"""
    FREEMIUM = "WS_FREEMIUM"       # Free tier
    PRO = "WS_PRO"                  # Pro tier
    ULTRA = "WS_ULTRA"              # Ultra tier

class PaygateTier(Enum):
    """Based on 'userPaygateTier' field"""
    NOT_PAID = "PAYGATE_TIER_NOT_PAID"
    TIER_ONE = "PAYGATE_TIER_ONE"
    TIER_TWO = "PAYGATE_TIER_TWO"

@dataclass
class AccountSession:
    """Complete account session data."""
    
    # From __NEXT_DATA__
    email: str
    display_name: str = ""
    avatar_url: str = ""
    access_token: str = ""
    token_expires: Optional[datetime] = None
    
    # From API Response
    sku: SubscriptionType = SubscriptionType.FREEMIUM
    paygate_tier: PaygateTier = PaygateTier.NOT_PAID
    credits: int = 0
    
    # From Browser
    recaptcha_token: str = ""
    recaptcha_fetched_at: Optional[datetime] = None
    profile_path: str = ""
    
    # Runtime
    is_connected: bool = False
    last_activity: Optional[datetime] = None
    
    @property
    def is_ultra(self) -> bool:
        return self.sku == SubscriptionType.ULTRA
    
    @property
    def is_pro(self) -> bool:
        return self.sku == SubscriptionType.PRO
    
    @property
    def recaptcha_age_seconds(self) -> float:
        if not self.recaptcha_fetched_at:
            return float('inf')
        return (datetime.now() - self.recaptcha_fetched_at).total_seconds()
    
    @property
    def needs_recaptcha_refresh(self) -> bool:
        """Refresh if older than 80 seconds (10s buffer from 90s limit)"""
        return self.recaptcha_age_seconds > 80
    
    def update_from_api_response(self, response: dict):
        """Update subscription info from any API response."""
        if 'sku' in response:
            self.sku = SubscriptionType(response['sku'])
        if 'userPaygateTier' in response:
            self.paygate_tier = PaygateTier(response['userPaygateTier'])
        if 'credits' in response:
            self.credits = response['credits']
```

### 7.2 Token Extraction

```python
async def extract_session_from_browser(page) -> dict:
    """
    Extract session data from __NEXT_DATA__ in page HTML.
    
    Returns dict with: email, name, access_token, expires
    """
    # Navigate to VEO
    await page.goto("https://labs.google/fx/tools/flow")
    await page.wait_for_load_state('networkidle')
    
    # Extract __NEXT_DATA__
    session_data = await page.evaluate("""
        () => {
            const script = document.getElementById('__NEXT_DATA__');
            if (!script) return null;
            
            const data = JSON.parse(script.textContent);
            const session = data?.props?.pageProps?.session;
            
            if (!session) return null;
            
            return {
                email: session.user?.email || '',
                name: session.user?.name || '',
                image: session.user?.image || '',
                access_token: session.access_token || '',
                expires: session.expires || ''
            };
        }
    """)
    
    return session_data
```

### 7.3 Subscription Detection from API Response

```python
def detect_subscription(api_response: dict) -> tuple:
    """
    Detect subscription from API response.
    
    Returns: (sku, paygate_tier, credits)
    
    Example response:
    {
        "credits": 43930,
        "userPaygateTier": "PAYGATE_TIER_TWO",
        "sku": "WS_ULTRA"
    }
    """
    sku = api_response.get('sku', 'WS_FREEMIUM')
    tier = api_response.get('userPaygateTier', 'PAYGATE_TIER_NOT_PAID')
    credits = api_response.get('credits', 0)
    
    return sku, tier, credits

# Usage: Intercept any API response
async def on_api_response(response):
    if 'aisandbox-pa.googleapis.com' in response.url:
        try:
            data = await response.json()
            if 'sku' in data:
                sku, tier, credits = detect_subscription(data)
                session.update_from_api_response(data)
                print(f"Subscription: {sku}, Credits: {credits}")
        except:
            pass
```

### 7.4 reCAPTCHA Token

```python
RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

async def get_recaptcha_token(page) -> str:
    """
    Get fresh reCAPTCHA Enterprise token.
    
    Must be called from a page on labs.google domain.
    """
    token = await page.evaluate(f"""
        async () => {{
            if (typeof grecaptcha === 'undefined') {{
                throw new Error('reCAPTCHA not loaded');
            }}
            
            return await grecaptcha.enterprise.execute(
                '{RECAPTCHA_SITE_KEY}',
                {{ action: 'GENERAL' }}
            );
        }}
    """)
    
    return token
```

---

## 8. userPaygateTier in Requests

**Important**: `userPaygateTier` phải được gửi trong `clientContext` của mọi request!

```python
def build_client_context(session: AccountSession, project_id: str) -> dict:
    """Build clientContext for API request."""
    return {
        "recaptchaContext": {
            "token": session.recaptcha_token,
            "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
        },
        "sessionId": f";{int(time.time() * 1000)}",
        "projectId": project_id,
        "tool": "PINHOLE",
        "userPaygateTier": session.paygate_tier.value
    }
```

---

## 9. UI Integration

> **Chi tiết UI xem tại:** [TAB_07_SETTINGS.md](../01_UI_UX/TAB_07_SETTINGS.md#chrome-profiles-auto-login)

### Tích hợp với Chrome Profiles

Thông tin session được hiển thị trực tiếp trong bảng Chrome Profiles:

| Column | Source | Auto-Update |
|--------|--------|-------------|
| **Account** | `__NEXT_DATA__` email | On sync |
| **Plan** | API `sku` | On any request |
| **Credits** | API `credits` | On any request |
| **Cookie** | Profile check | On sync |

### Mapping SKU → Plan Badge

```python
PLAN_BADGES = {
    "WS_ULTRA": "🚀 Ultra",
    "WS_PRO": "💎 Pro",
    "WS_FREEMIUM": "👤 Free"
}
```

---

## 10. Configuration

| Setting | Values | Default | Description |
|---------|--------|---------|-------------|
| `recaptcha_refresh_buffer` | 5-30 sec | 10 sec | Buffer before reCAPTCHA expires |
| `auth_refresh_buffer` | 5-15 min | 10 min | Buffer before auth expires |
| `auto_detect_subscription` | On/Off | On | Auto-update from API responses |

---

## 11. Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `401 Unauthorized` | Auth token expired | Refresh token from browser |
| `403 Forbidden` | reCAPTCHA expired/invalid | Get new reCAPTCHA token |
| `Invalid projectId` | Wrong project | Fetch projects, use valid one |
| `Quota exceeded` | credits = 0 | Switch account or wait reset |
---

## 12. Dual Login System (NEW - 2026-02-06)

VEO Pro Max hỗ trợ 2 phương thức đăng nhập với ưu/nhược điểm khác nhau:

### 12.1 Login Methods Comparison

| Feature | 🔑 OAuth Login | 🌐 Browser Login |
|---------|---------------|-----------------|
| **Tốc độ** | ⚡ Nhanh (popup) | 🐢 Chậm hơn (browser) |
| **Plan/Credits** | ⏳ Wait → Update sau video đầu tiên | ✅ Hiện ngay |
| **Token Refresh** | ✅ Tự động | ❌ N/A |
| **Browser Profile** | ❌ Không cần | ✅ Lưu trong app |
| **Session API** | ❌ Limited scopes | ✅ Full access |

### 12.2 ChromeProfile Model Fields

```python
@dataclass
class ChromeProfile:
    email: str
    display_name: str = ""
    profile_path: str = ""
    
    # Subscription fields
    sku: str = "WS_FREEMIUM"
    paygate_tier: str = "PAYGATE_TIER_NOT_PAID"
    credits: int = 0
    
    # Dual login fields (NEW)
    login_method: str = "oauth"        # "oauth" | "browser"
    browser_profile_path: str = ""     # Path to Chromium profile
    subscription_fetched: bool = False # True after successful fetch
    
    is_ready: bool = False
    last_used: str = ""
```

### 12.3 Display Properties

```python
@property
def tier_display(self) -> str:
    # OAuth without fetch → "⏳ Wait"
    if self.login_method == "oauth" and not self.subscription_fetched:
        return "⏳ Wait"
    
    tier_map = {
        "WS_ULTRA": "🚀 Ultra",
        "WS_PRO": "💎 Pro",
        "WS_FREEMIUM": "👤 Free",
    }
    return tier_map.get(self.sku, "👤 Free")

@property
def credits_display(self) -> str:
    if self.login_method == "oauth" and not self.subscription_fetched:
        return "N/A"
    return f"{self.credits:,}"
```

### 12.4 Login Flow Chart

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DUAL LOGIN SYSTEM                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User clicks:                                                               │
│   ┌──────────────┐    ┌──────────────┐                                       │
│   │ 🔑 OAuth     │    │ 🌐 Browser   │                                       │
│   └───────┬──────┘    └───────┬──────┘                                       │
│           │                   │                                              │
│           ▼                   ▼                                              │
│   Google OAuth Popup    Chromium opens                                       │
│   (consent page)        (labs.google/fx)                                     │
│           │                   │                                              │
│           ▼                   ▼                                              │
│   Exchange code →       User logs in                                         │
│   Get tokens            manually                                             │
│           │                   │                                              │
│           ▼                   ▼                                              │
│   Profile created       Session API                                          │
│   login_method="oauth"  detects email                                        │
│           │                   │                                              │
│           ▼                   ▼                                              │
│   subscription_fetched  Profile created                                      │
│   = False               login_method="browser"                               │
│           │                   │                                              │
│           ▼                   ▼                                              │
│   Plan = "⏳ Wait"     Fetch subscription()                                  │
│   Credits = "N/A"       → Real-time data                                     │
│           │                   │                                              │
│           ▼                   ▼                                              │
│   After 1st video:      subscription_fetched                                 │
│   update_subscription   = True                                               │
│   _from_response()            │                                              │
│           │                   │                                              │
│           ▼                   ▼                                              │
│   ┌─────────────────────────────────────────┐                                │
│   │         PROFILE READY                   │                                │
│   │  Plan: 🚀 Ultra | 💎 Pro | 👤 Free      │                                │
│   │  Credits: 43,930                        │                                │
│   └─────────────────────────────────────────┘                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 12.5 OAuth → Browser Upgrade

Khi user đã có profile OAuth và sau đó login cùng email bằng Browser:

```python
# In add_profile_via_browser_login():
existing = self.get_profile(email)
if existing:
    # Upgrade OAuth → Browser
    existing.login_method = "browser"
    existing.browser_profile_path = str(profile_path)
    existing.is_ready = True
    self.save_profiles()
    
    # Fetch subscription real-time
    self._fetch_subscription_via_browser(existing)
```

### 12.6 Refresh Button Logic

| Type | Refresh Action | Browser Mode |
|------|----------------|--------------|
| 🔑 OAuth | `refresh_session()` → Refresh token → Placeholder | N/A |
| 🌐 Browser | `_fetch_subscription_via_browser()` → Real-time | Headless ✅ |

### 12.7 Browser Profile Storage

Browser profiles được lưu trong app folder để đảm bảo portability:

```
02 - CLIENT - VEO PRO MAX/
├── config/
│   ├── profiles.json
│   └── browser_profiles/        ← Chrome profiles
│       ├── browser_session_a1b2c3d4/
│       └── browser_session_e5f6g7h8/
```

### 12.8 Chrome vs Chromium (Updated 2026-02-07)

VEO Pro Max sử dụng **Chrome thật** thay vì Chromium để đảm bảo session Google ổn định:

```python
# profiles_controller.py, browser_manager.py, token_extractor.py, cookie_validator.py
context = p.chromium.launch_persistent_context(
    user_data_dir=profile_path,
    channel="chrome",  # ← Sử dụng Chrome thật
    headless=True,     # ← Chạy ẩn cho refresh
    ...
)
```

| Aspect | Chromium (cũ) | Chrome (mới) |
|--------|---------------|--------------|
| Google Session | ⚠️ Hay bị hết hạn | ✅ Ổn định |
| Re-login | ⚠️ Thường xuyên | ✅ Hiếm khi |
| Cookie Format | Riêng biệt | Native Google |
| Automation Detection | Dễ bị detect | Khó detect hơn |

**Yêu cầu:** User phải có Google Chrome cài sẵn trên máy.

### 12.9 Auto-Login Flow (NEW)

Hỗ trợ auto-fill email/password để login tự động:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AUTO-LOGIN FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User inputs:                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Email: ultra8574632@tk.solsticeenergyvn.com                          │   │
│  │ Password: ********                                                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           ▼                                                                  │
│  CredentialsManager.save() → Encrypt with Fernet                            │
│           │                                                                  │
│           ▼                                                                  │
│  Launch Chrome (visible) → Navigate to accounts.google.com                  │
│           │                                                                  │
│           ▼                                                                  │
│  Auto-fill email → Click Next → Wait for password field                     │
│           │                                                                  │
│           ▼                                                                  │
│  Auto-fill password → Click Next                                            │
│           │                                                                  │
│           ▼                                                                  │
│  Wait for redirect to myaccount.google.com (max 120s for CAPTCHA/2FA)       │
│           │                                                                  │
│           ▼                                                                  │
│  Navigate to labs.google/fx → Fetch session API                             │
│           │                                                                  │
│           ▼                                                                  │
│  Save profile (login_method="browser") → Fetch subscription                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 12.10 Headless Mode Configuration

| Operation | Headless | Lý do |
|-----------|----------|-------|
| **Browser Login** | ❌ False | User cần thao tác CAPTCHA/2FA |
| **Auto-Login** | ❌ False | User có thể cần xử lý CAPTCHA/2FA |
| **Refresh Session** | ✅ True | Không cần interaction |
| **Cookie Validation** | ✅ True | Chỉ verify, không interact |
| **Token Extraction** | ✅ True | Background task |

### 12.11 UI Type Column Display

Cột Type trong bảng profiles hiển thị login method:

| Login Method | Emoji | Tooltip |
|--------------|-------|---------|
| OAuth | 🔑 | OAuth Login - Token based |
| Browser | 🌐 | Browser Login - Full session |

```python
# tab_settings.py
type_emoji = "🌐" if login_method == "browser" else "🔑"
type_tooltip = "Browser Login - Full session" if login_method == "browser" else "OAuth Login - Token based"
```

---

## Cross-References

- [TOKEN_SECURITY.md](./TOKEN_SECURITY.md) - Full auth guide
- [MULTITHREADING_ARCHITECTURE.md](./MULTITHREADING_ARCHITECTURE.md) - Role hierarchy
- [PROJECT_MANAGEMENT.md](./PROJECT_MANAGEMENT.md) - Project handling
- [API_MAPPING.md](../02_Architecture/API_MAPPING.md) - Request formats

