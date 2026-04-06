# Deploy Rules — VEO License Telegram Bot
# =============================================

## 🔑 Project Info

| Item | Value |
|------|-------|
| Vercel Project | `veo-license-bot` |
| Vercel Dashboard | `https://vercel.com/lynkvproerrors-projects/veo-license-bot` |
| Cron Service | `https://console.cron-job.org/` |
| Source Folder | `01 - ADMIN - License Security/001 - Telegram Bot` |
| Bot Username | `@VadacceptAdminBot` |
| Runtime | Python 3.13 (Vercel Serverless Functions) |

### Cấu trúc API Endpoints

```
api/
├── webhook/
│   └── handler.py      → POST /api/webhook/{WEBHOOK_SECRET}
├── cron/
│   ├── health.py       → GET  /api/cron/health (public, no auth)
│   └── check_pending.py→ GET  /api/cron/check_pending (X-Cron-Secret)
└── notify/
    └── new_request.py  → POST /api/notify/new_request (X-Notify-Key)
```

---

## 📌 Rule #1: Deploy quy trình (Push → Vercel → Verify)

### 1a. Deploy code lên Vercel

```powershell
# Cách 1: Push qua GitHub (auto-deploy)
cd "01 - ADMIN - License Security/001 - Telegram Bot"
git add .
git commit -m "Bot: <mô tả thay đổi>"
git push origin main
# → Vercel tự build & deploy khi detect commit trên main branch

# Cách 2: Vercel CLI (manual deploy)
cd "01 - ADMIN - License Security/001 - Telegram Bot"
vercel deploy --prod
```

> ⚠️ **LUÔN deploy `--prod`!** `vercel deploy` (không có `--prod`) chỉ tạo preview URL — bot webhook sẽ không nhận được.

### 1b. Post-Deploy Verify (BẮT BUỘC)

> [!CAUTION]
> **Bước này BẮT BUỘC sau EVERY deploy.** Bot có thể crash ngầm nếu import lỗi — Vercel KHÔNG báo nếu endpoint chưa được gọi.

**4 bước verify:**

```powershell
# 1. Health check — phải trả 200
curl -s "https://veo-license-bot.vercel.app/api/cron/health"
# Expected: {"ok":true,"service":"veo-license-bot","status":"alive"}

# 2. Webhook health — phải trả 200
curl -s "https://veo-license-bot.vercel.app/api/webhook/<WEBHOOK_SECRET>"
# Expected: {"status":"ok","service":"veo-license-bot"}

# 3. Telegram webhook info — phải có pending_update_count
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
# Expected: url trỏ đúng, no last_error

# 4. Test bot — nhắn /start trên Telegram
# Expected: Bot trả lời menu chính
```

**Checklist:**
- [ ] Health endpoint trả `200 OK`
- [ ] Webhook GET trả `200 OK`
- [ ] `getWebhookInfo` → `url` đúng, `last_error_message` rỗng
- [ ] Bot phản hồi `/start` trên Telegram
- [ ] `/health` trả Firebase status (Primary ✅, Backup ✅)

---

## 📌 Rule #2: Environment Variables (Vercel Dashboard)

> **Sửa env var:** Vercel Dashboard → Settings → Environment Variables

| Variable | Value | Bắt buộc |
|----------|-------|----------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC-xyz...` | ✅ |
| `TELEGRAM_ADMIN_IDS` | `123456789,987654321` | ✅ |
| `WEBHOOK_SECRET` | `random_32_char_string` | ✅ |
| `FIREBASE_BOT_EMAIL` | `veo-bot@system.local` | ✅ |
| `FIREBASE_BOT_PASSWORD` | `<strong_password>` | ✅ |
| `FIREBASE_PRIMARY_API_KEY` | `AIza...` | ✅ |
| `FIREBASE_BACKUP_API_KEY` | `AIza...` | ✅ |
| `FIREBASE_PRIMARY_PROJECT` | `veo-pro-max` | ✅ |
| `FIREBASE_BACKUP_PROJECT` | `veoauto-f54b5` | ✅ |
| `VEO_LICENSE_SECRET` | `<32_char_hex>` | ✅ |
| `CRON_SECRET` | `<random_string>` | ✅ |
| `NOTIFY_SECRET` | `<random_string>` (fallback: API key) | Optional |

> [!IMPORTANT]
> **Sau khi sửa env var → PHẢI Redeploy!**
> Vercel KHÔNG auto-redeploy khi chỉ thay đổi env var.
> Redeploy: Dashboard → Deployments → 3-dot menu → Redeploy.

---

## 📌 Rule #3: Cron Jobs (cron-job.org)

> **Dashboard:** https://console.cron-job.org/
> **Tại sao dùng external cron?** Vercel Hobby plan chỉ cho 1 cron/ngày → dùng cron-job.org (miễn phí, interval tối thiểu 1 phút).

### Job 1: Health Keep-Alive

| Setting | Value |
|---------|-------|
| Title | `VEO Bot Health` |
| URL | `https://veo-license-bot.vercel.app/api/cron/health` |
| Method | `GET` |
| Schedule | Every **10 minutes** |
| Headers | *(không cần — endpoint public)* |
| Notify on failure | ✅ Bật |
| Save responses | ✅ Bật |

**Mục đích:** Giữ Vercel warm → tránh cold start 5-10s khi admin gửi lệnh.

**Expected response:** `200` → `{"ok": true, "status": "alive"}`

> ⚠️ **KHÔNG bao giờ xóa job này!** Nếu Vercel idle > 1 giờ → function bị disable tạm → bot không phản hồi.

### Job 2: Check Pending Requests

| Setting | Value |
|---------|-------|
| Title | `VEO Check Pending` |
| URL | `https://veo-license-bot.vercel.app/api/cron/check_pending` |
| Method | `GET` |
| Schedule | Every **5 minutes** |
| Notify on failure | ✅ Bật |
| Save responses | ✅ Bật |

**Header BẮT BUỘC** (Settings → Advanced → Headers):

| Header Name | Header Value |
|-------------|--------------|
| `X-Cron-Secret` | *(giá trị `CRON_SECRET` trong Vercel env)* |

**Expected response:**
- `200` → `{"ok": true, "pending_total": N, "new_notified": N}`
- `403` → Header secret sai → **FIX NGAY**

**Cách tạo/sửa header:**
1. Mở job → **Edit**
2. Kéo xuống **"Advanced"**
3. Mục **"Custom Headers"** → Add: `X-Cron-Secret` = `<CRON_SECRET value>`
4. Save

---

## 📌 Rule #4: Webhook Management

### 4a. Set/Reset Webhook

```powershell
# Set webhook (chạy 1 lần, hoặc khi đổi domain/secret)
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://veo-license-bot.vercel.app/api/webhook/<WEBHOOK_SECRET>&secret_token=<WEBHOOK_SECRET>"

# Verify
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

### 4b. Delete Webhook (debug)

```powershell
# Tạm xóa webhook (bot ngừng nhận message)
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# Kiểm tra message thủ công (polling mode)
curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
```

> [!WARNING]
> **Sau khi debug xong → PHẢI set lại webhook!** Nếu quên → bot ngừng hoạt động vĩnh viễn.

### 4c. Khi nào cần reset webhook

| Tình huống | Hành động |
|-----------|-----------|
| Đổi `WEBHOOK_SECRET` | Set lại webhook với secret mới |
| Đổi Vercel domain | Set lại webhook với URL mới |
| Bot không phản hồi | Check `getWebhookInfo` → `last_error_message` |
| Deploy project mới | Set webhook cho project mới |

---

## 📌 Rule #5: Notify Endpoint (Real-time Alerts)

Client app gọi endpoint này khi có request mới → bot alert admin **ngay lập tức** (không cần chờ cron 5 phút).

### API Contract

```
POST https://veo-license-bot.vercel.app/api/notify/new_request
Header: X-Notify-Key: <NOTIFY_SECRET hoặc FIREBASE_PRIMARY_API_KEY>
Body: {
  "mid": "3946C15B...",
  "client_name": "Nguyễn Văn A",
  "tier_requested": "3M",
  "request_id": "req_xxx"
}
```

**Response:**
- `200` → `{"ok": true, "alerted": 2}` (2 admins đã nhận)
- `403` → `X-Notify-Key` sai

> [!TIP]
> `NOTIFY_SECRET` env var là optional — nếu không set, endpoint dùng `FIREBASE_PRIMARY_API_KEY` làm auth key.

---

## 📌 Rule #6: Troubleshooting

### 6a. Vercel Logs

```powershell
# Xem logs realtime
vercel logs veo-license-bot --follow

# Xem logs 1 endpoint cụ thể
vercel logs veo-license-bot --follow --path="/api/webhook/*"
```

Hoặc: Vercel Dashboard → Project → **Logs** tab → filter by function name.

### 6b. Common Issues

| Vấn đề | Nguyên nhân | Giải pháp |
|--------|-------------|-----------|
| Bot không phản hồi | Webhook sai/thiếu | `getWebhookInfo` → check URL + error |
| `/health` trả Firebase ❌ | Bot account bị disable/password sai | Check `FIREBASE_BOT_EMAIL` + `FIREBASE_BOT_PASSWORD` |
| Cron trả 403 | `X-Cron-Secret` header không khớp `CRON_SECRET` env | Sửa header trên cron-job.org |
| Cron bị disable tự động | Quá nhiều lần fail (403/500) | Fix lỗi → vào cron-job.org bật lại |
| Import error (500) | Missing dependency hoặc syntax error | Check Vercel logs → fix → redeploy |
| Timeout (504/408) | Firebase query chậm (> 10s) | Optimize query hoặc reduce page_size |
| Rate limited | > 30 lệnh/phút từ 1 user | Chờ 60s rồi thử lại |
| Seller vào bot → "Không có quyền" | Chưa link Telegram ID | Admin gõ `/linkseller <tg_id> <seller_mid>` |

### 6c. Emergency: Bot hoàn toàn chết

```powershell
# 1. Check Vercel deployment status
vercel ls veo-license-bot

# 2. Force redeploy
vercel deploy --prod --force

# 3. Re-set webhook
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://veo-license-bot.vercel.app/api/webhook/<SECRET>&secret_token=<SECRET>"

# 4. Verify
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
curl "https://veo-license-bot.vercel.app/api/cron/health"
```

---

## 📌 Rule #7: Khi nào cần Redeploy

| Thay đổi | Cần Redeploy? | Cần Reset Webhook? | Cần Update Cron? |
|----------|:---:|:---:|:---:|
| Sửa code Python (handlers, formatters...) | ✅ | ❌ | ❌ |
| Sửa `vercel.json` (routes, builds) | ✅ | ❌ | ❌ |
| Thêm endpoint mới (api/*) | ✅ | ❌ | ✅ (nếu cron mới) |
| Đổi `WEBHOOK_SECRET` | ✅ | ✅ | ❌ |
| Đổi `CRON_SECRET` | ✅ | ❌ | ✅ (update header) |
| Đổi `TELEGRAM_BOT_TOKEN` | ✅ | ✅ | ❌ |
| Đổi Firebase env vars | ✅ | ❌ | ❌ |
| Chỉ sửa docs (*.md) | ❌ | ❌ | ❌ |

> [!CAUTION]
> **`vercel deploy` (không `--prod`) → KHÔNG update production!**
> Phải dùng `vercel deploy --prod` hoặc push qua GitHub (auto-deploy).

---

## 📌 Rule #8: Dual-Database Sync

Bot ghi dữ liệu vào **CẢ 2 Firebase projects** (Primary + Backup) cho mỗi write operation.

| Operation | Primary | Backup | Fallback |
|-----------|:---:|:---:|----------|
| Read | ✅ (ưu tiên) | ✅ (fallback) | Nếu Primary 404/error → đọc Backup |
| Write/Update | ✅ | ✅ | Ghi cả 2, log warning nếu 1 fail |
| Delete | ✅ | ✅ | Xóa cả 2 |
| List | ✅+✅ | — | Merge + deduplicate bằng doc_id |

> [!WARNING]
> **Nếu chỉ 1 DB fail:** Bot vẫn hoạt động bình thường (đọc/ghi DB còn lại).
> **Nếu CẢ 2 fail:** `/health` sẽ hiện ❌❌ → check Firebase Console + bot account.

---

## 📌 Rule #9: Adding New Cron Jobs

Khi cần thêm cron endpoint mới (ví dụ: `/api/cron/cleanup`, `/api/cron/sync`):

### Bước 1: Tạo Python file

```python
# api/cron/new_job.py
from http.server import BaseHTTPRequestHandler
from bot.security import verify_cron_secret

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not verify_cron_secret(dict(self.headers)):
            self.send_response(403)
            self.end_headers()
            return
        # ... logic ...
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
```

### Bước 2: Deploy

```powershell
git add api/cron/new_job.py
git commit -m "Bot: add new_job cron endpoint"
git push  # → Vercel auto-deploy
```

`vercel.json` route `"/api/cron/(.*)"` → tự map `/api/cron/new_job` → `api/cron/new_job.py`.

### Bước 3: Tạo cron job trên cron-job.org

| Setting | Value |
|---------|-------|
| URL | `https://veo-license-bot.vercel.app/api/cron/new_job` |
| Method | `GET` |
| Schedule | Tuỳ mục đích |
| Header | `X-Cron-Secret: <CRON_SECRET>` |

### Bước 4: Verify

```powershell
# Test thủ công
curl -H "X-Cron-Secret: <SECRET>" "https://veo-license-bot.vercel.app/api/cron/new_job"
```
