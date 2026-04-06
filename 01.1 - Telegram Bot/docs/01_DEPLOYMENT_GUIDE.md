# 📦 Deployment Guide — VEO License Telegram Bot

## Prerequisites

| Item | Cách lấy | Ghi chú |
|------|----------|---------|
| Telegram Bot Token | [@BotFather](https://t.me/BotFather) → `/newbot` | Lưu vào Vercel env |
| Telegram Admin ID | [@userinfobot](https://t.me/userinfobot) | Whitelist admin |
| Vercel Account | [vercel.com](https://vercel.com) (login GitHub) | Free, không cần thẻ |
| Firebase Project | Đã có sẵn (veoauto + backup) | Spark plan (free) |
| Node.js 18+ | Cần cho Vercel CLI | Hoặc deploy qua GitHub |

---

## Step 1: Tạo Firebase Auth Account cho Bot

```bash
# Trên máy admin (có Admin SDK), chạy 1 lần:
python create_bot_account.py
```

Script sẽ:
1. Tạo Firebase Auth user: `veo-bot@system.local`
2. Set custom claims: `{"role": "bot", "level": 3}`
3. In ra UID → dùng cho Security Rules

> **Lưu email/password vào nơi an toàn — sẽ set làm Vercel env var.**

---

## Step 2: Cập nhật Firebase Security Rules

Thêm rules cho bot UID (xem `04_FIREBASE_RULES.md`).

---

## Step 3: Setup Vercel Project

```bash
# Clone project
cd "001 - Telegram Bot"

# Install Vercel CLI
npm i -g vercel

# Login
vercel login

# Deploy
vercel deploy
```

### Environment Variables (set trên Vercel Dashboard):

| Variable | Value | Mô tả |
|----------|-------|--------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | Token từ BotFather |
| `TELEGRAM_ADMIN_IDS` | `123456789,987654321` | Admin User IDs (comma-separated) |
| `WEBHOOK_SECRET` | `random_32_char_string` | Secret path cho webhook URL |
| `FIREBASE_BOT_EMAIL` | `veo-bot@system.local` | Bot account email |
| `FIREBASE_BOT_PASSWORD` | `strong_password_here` | Bot account password |
| `FIREBASE_PRIMARY_API_KEY` | `AIza...` | Primary project API key |
| `FIREBASE_BACKUP_API_KEY` | `AIza...` | Backup project API key |
| `FIREBASE_PRIMARY_PROJECT` | `veo-pro-max` | Primary project ID |
| `FIREBASE_BACKUP_PROJECT` | `veoauto-f54b5` | Backup project ID |
| `VEO_LICENSE_SECRET` | `32_char_hex` | Keygen secret |
| `CRON_SECRET` | `random_string` | Secret cho cron endpoint |

---

## Step 4: Set Telegram Webhook

```bash
# Sau khi deploy, set webhook:
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?\
url=https://<your-app>.vercel.app/api/webhook/<WEBHOOK_SECRET>&\
secret_token=<WEBHOOK_SECRET>"
```

Verify:
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

---

## Step 5: Setup Cron Jobs (cron-job.org)

> **⚠️ Vercel Hobby plan chỉ cho 1 cron/ngày** → dùng [cron-job.org](https://cron-job.org) (miễn phí, hỗ trợ 5 phút).

### Tại sao cần 2 cron jobs?

| Job | Mục đích | Nếu thiếu |
|-----|----------|-----------|
| **Health** | Giữ Vercel warm, không bị disable | Vercel cold start 5-10s, có thể bị disable nếu idle lâu |
| **Check Pending** | Kiểm tra request mới, gửi thông báo Telegram | Admin không biết có request pending |

### Job 1: Health Keep-Alive (tránh bị disable)

| Setting | Value |
|---------|-------|
| Title | `VEO Bot Health` |
| URL | `https://veo-license-bot.vercel.app/api/cron/health` |
| Method | `GET` |
| Schedule | Every **10 minutes** |
| Headers | *(không cần — endpoint public)* |
| Notify on failure | ✅ Bật |
| Save responses | ✅ Bật |

**Expected response:** `200 OK` → `{"ok": true, "service": "veo-license-bot", "status": "alive"}`

> **Endpoint này luôn trả 200** → cron-job.org sẽ **không bao giờ disable** nó → Vercel luôn warm.

### Job 2: Check Pending Requests

| Setting | Value |
|---------|-------|
| Title | `VEO Check Pending` |
| URL | `https://veo-license-bot.vercel.app/api/cron/check_pending` |
| Method | `GET` |
| Schedule | Every **5 minutes** |
| Notify on failure | ✅ Bật |
| Save responses | ✅ Bật |

**Header bắt buộc (kéo xuống mục Advanced):**

| Header Name | Header Value |
|-------------|--------------|
| `X-Cron-Secret` | *(giá trị CRON_SECRET trong `.env`)* |

**Expected response:**
- `200 OK` → `{"ok": true, "pending_total": N, "new_notified": N}`
- `403 Forbidden` → header secret sai hoặc thiếu

> **Lưu ý:** Nếu `X-Cron-Secret` header sai → trả 403 → cron-job.org có thể disable job sau nhiều lần fail liên tiếp.
> Giải pháp: vào cron-job.org bật lại + kiểm tra header.

### Cách set header trên cron-job.org:
1. Tạo job → Điền URL + Schedule
2. Kéo xuống **"Advanced"** → **"Headers"**
3. Thêm header: `X-Cron-Secret` = `<giá trị CRON_SECRET>`
4. Save

---

## Step 6: Verify

1. Mở Telegram → nhắn `/start` cho bot
2. Bot trả lời → ✅ Webhook OK
3. Gõ `/status` → xem tổng quan license
4. Gõ `/health` → kiểm tra kết nối Firebase
5. Check `https://veo-license-bot.vercel.app/api/cron/health` → trả `200 OK` → ✅

---

## Troubleshooting

| Vấn đề | Giải pháp |
|--------|-----------|
| Bot không phản hồi | Check Vercel logs: `vercel logs` |
| Firebase 403 | Check Security Rules + bot UID |
| Webhook timeout | Vercel free tier có 10s timeout — optimize queries |
| Cron không chạy | Check cron-job.org dashboard + header secret |
| Cron bị disable (403) | Kiểm tra `X-Cron-Secret` header khớp `CRON_SECRET` env var |
| Cron bị disable (404) | Kiểm tra URL chính xác: `/api/cron/check_pending` |
| Vercel cold start chậm | Health cron giữ warm — kiểm tra cron-job.org Job 1 |
