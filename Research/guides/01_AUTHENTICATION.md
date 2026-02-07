# VEO Authentication

Two authentication modes: **Authorization header** (fast, automation) vs **reCAPTCHA token** (slow, browser).

| Mode | Use Case | Speed | Complexity | 403 Risk |
|------|----------|-------|------------|----------|
| **Authorization Header** | API/Extension/Automation | Fast | Simple | Low |
| **reCAPTCHA Token** | Browser/Manual | Slow | Complex | High (if automated) |

---

## Mode 1: Authorization Header

**Request Structure**:
```http
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText
Authorization: Bearer ya29.a0AfB_byC... (~200 chars)
Content-Type: application/json

{
  "clientContext": {
    "sessionId": ";1738345600000",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_ONE"
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "seed": 5432,
    "textInput": {"prompt": "Your prompt"},
    "videoModelKey": "veo_3_1_t2v_fast_portrait",
    "metadata": {"sceneId": "uuid"}
  }]
}
```

**Token Extraction**:

*   **Option A: Manual (DevTools)**
    1. Login to `labs.google/fx/tools/flow`
    2. Open DevTools (F12) → Network tab
    3. Find request to `aisandbox-pa.googleapis.com`
    4. Copy `Authorization` header value

*   **Option B: Programmatic (Source Code)**
    1. Fetch `https://labs.google/fx/tools/flow`
    2. Parse HTML for `<script id="__NEXT_DATA__" type="application/json">`
    3. Extract JSON: `props.pageProps.session.access_token`
    4. **Note**: This token is generated server-side on page load.

Format: `Bearer ya29.a0AfB_byC...` (~200 characters)

**JavaScript Example**:
```javascript
async function generateVideo(token, projectId, prompt) {
  const response = await fetch(
    'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        clientContext: {
          sessionId: `;${Date.now()}`,
          projectId: projectId,
          tool: 'PINHOLE',
          userPaygateTier: 'PAYGATE_TIER_ONE'
        },
        requests: [{
          aspectRatio: 'VIDEO_ASPECT_RATIO_PORTRAIT',
          seed: Math.floor(Math.random() * 32768),
          textInput: {prompt: prompt},
          videoModelKey: 'veo_3_1_t2v_fast_portrait',
          metadata: {sceneId: crypto.randomUUID()}
        }]
      })
    }
  );
  return await response.json();
}
```

---

## Mode 2: reCAPTCHA Token

**Request Structure**:
```http
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartAndEndImage
Content-Type: text/plain;charset=UTF-8
x-browser-channel: stable
x-browser-validation: <hash>
x-browser-year: 2026

{
  "clientContext": {
    "recaptchaContext": {
      "token": "<~3000 char recaptcha v3 token>",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769858049289",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [...]
}
```

**Critical**: NO `Authorization` header. reCAPTCHA token in payload.

**Rate Limiting**: MUST use human-like delays (30-60s between requests) or risk 403.

**Implementation**:
```javascript
async function generateWithRecaptcha(prompt) {
  // Get reCAPTCHA token
  const token = await grecaptcha.execute('SITE_KEY', {action: 'generate_video'});
  
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'text/plain;charset=UTF-8',
      'x-browser-channel': 'stable',
      'x-browser-validation': generateHash()
    },
    body: JSON.stringify({
      clientContext: {
        recaptchaContext: {
          token: token,
          applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB'
        },
        sessionId: `;${Date.now()}`,
        projectId: projectId,
        tool: 'PINHOLE',
        userPaygateTier: 'PAYGATE_TIER_TWO'
      },
      requests: [...]
    })
  });
  
  // MUST WAIT before next request
  await new Promise(r => setTimeout(r, 30000 + Math.random() * 30000));
}
```

---

## Mode Comparison

| Requirement | Authorization | reCAPTCHA |
|-------------|---------------|-----------|
| Fast automation | ✅ | ❌ (403 risk) |
| Batch processing | ✅ | ❌ (too slow) |
| No token extraction | ❌ | ✅ |
| Production use | ✅ Recommended | ⚠️ Not recommended |

**Decision Tree**:
- Can extract token from browser? → Use Mode 1 (Authorization)
- Automation needed? → Mode 1 required
- Manual/browser only → Mode 2 acceptable

---

## 403 Prevention

| Cause | Mode 1 | Mode 2 | Solution |
|-------|--------|--------|----------|
| Token expired | ❌ | N/A | Refresh from browser |
| Invalid projectId | ❌ | ❌ | Verify matches user account |
| Too fast | ✅ OK | ❌ | Add 30-60s delays (Mode 2) |
| Bot detected | ✅ OK | ❌ | Use Authorization instead |
| No credits | ❌ | ❌ | Check `remainingCredits` |

**Token Management**:
```javascript
let cachedToken = null;
let tokenExpiry = 0;

async function getValidToken() {
  if (Date.now() < tokenExpiry && cachedToken) {
    return cachedToken;
  }
  cachedToken = await extractTokenFromBrowser();
  tokenExpiry = Date.now() + 3600000; // 1 hour
  return cachedToken;
}
```

---

## Account Status Detection

Trạng thái tài khoản được xác định qua **API response** từ `aisandbox-pa.googleapis.com`, KHÔNG phải từ tên user trong `__NEXT_DATA__`.

### API Endpoint
Request đầu tiên khi vào tool (ví dụ: `:uploadUserImage`, `:checkAppAvailability`) sẽ trả về:

```json
{
  "credits": 50,
  "userPaygateTier": "PAYGATE_TIER_NOT_PAID",
  "sku": "WS_FREEMIUM"
}
```

### Plan Matrix

| Plan | SKU | Paygate Tier | Credits/Mo |
|------|-----|--------------|------------|
| **🚀 Ultra** | `WS_ULTRA` | `PAYGATE_TIER_TWO` | ~45,000 |
| **👤 Freemium** | `WS_FREEMIUM` | `PAYGATE_TIER_NOT_PAID` | ~50 |
| **💎 Pro** | `WS_PRO` | `PAYGATE_TIER_ONE` | ~1,000 |

### Detection Logic

```javascript
// Intercept API response or call dedicated endpoint
async function detectAccountTier(apiResponse) {
  const { sku, userPaygateTier, credits } = apiResponse;
  
  // Priority: Ultra → Freemium → Pro (fallback)
  if (sku === "WS_ULTRA" || userPaygateTier === "PAYGATE_TIER_TWO") {
    return { tier: "ULTRA", credits };
  } else if (sku === "WS_FREEMIUM" || userPaygateTier === "PAYGATE_TIER_NOT_PAID") {
    return { tier: "FREEMIUM", credits };
  } else {
    return { tier: "PRO", credits }; // Fallback for WS_PRO / PAYGATE_TIER_ONE
  }
}
```

### UI Display
Frontend hiển thị badge "ULTRA" / "PRO" dựa trên giá trị `sku` này.

---

## Field Reference

### Client Context

| Field | Type | Mode 1 | Mode 2 | Example |
|-------|------|--------|--------|---------|
| `recaptchaContext` | Object | ❌ | ✅ Required | See Mode 2 |
| `sessionId` | String | ✅ | ✅ | `;1738345600000` |
| `projectId` | UUID | ✅ | ✅ | `f5db1342-c676-...` |
| `tool` | Enum | ✅ | ✅ | `PINHOLE` |
| `userPaygateTier` | Enum | ✅ | ✅ | `PAYGATE_TIER_ONE` |

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `aspectRatio` | Enum | ✅ | `VIDEO_ASPECT_RATIO_PORTRAIT` or `LANDSCAPE` |
| `seed` | Integer | ✅ | 0-32767 |
| `textInput.prompt` | String | ✅ | Video description |
| `videoModelKey` | String | ✅ | Model identifier |
| `metadata.sceneId` | UUID | ✅ | Client-generated UUID |

---

**Last Updated**: 2026-02-01  
**Source**: HAR files + working extension
