# 🔒 Security Analysis — Webhook + Free Cloud

## Architecture

```
📱 Telegram ──webhook──→ ☁️ Vercel (Serverless, FREE)
                              │
                         🔑 Firebase Auth REST API
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
             🔥 Primary DB       🔥 Backup DB
                    ↑                   ↑
              ⏰ cron-job.org (5 min polling)
```

---

## 7 Attack Vectors

### 🔴 Vector 1: Firebase Credentials Exposure

| | |
|---|---|
| **Risk** | Credentials bị lộ → toàn quyền đọc/ghi Firebase |
| **Severity** | 🔴 CRITICAL (nếu dùng Admin SDK) → 🟢 LOW (approach hiện tại) |
| **Mitigation** | ❌ KHÔNG dùng Admin SDK trên cloud. Bot dùng Firebase Auth (email/pass) + REST API. Security Rules vẫn enforce. Ngay cả khi lộ credentials, kẻ tấn công chỉ write được collection bot được phép. |

### 🔴 Vector 2: Telegram Bot Token Leak

| | |
|---|---|
| **Risk** | Token lộ → giả mạo admin gửi `/approve` |
| **Severity** | 🔴 CRITICAL (nếu không có whitelist) → 🟢 LOW (sau mitigation) |
| **Mitigation** | User ID whitelist — chỉ accept lệnh từ admin IDs cụ thể. Lệnh nguy hiểm yêu cầu confirm. Token lưu Vercel env (encrypted at rest). |

### 🟡 Vector 3: Webhook Hijacking

| | |
|---|---|
| **Risk** | Fake webhook calls → trigger actions |
| **Severity** | 🟡 MEDIUM → 🟢 LOW |
| **Mitigation** | `X-Telegram-Bot-Api-Secret-Token` header verification. Webhook URL chứa random path. User ID check trước mọi action. |

### 🟡 Vector 4: Command Injection

| | |
|---|---|
| **Risk** | Malicious input trong MID/key → query injection |
| **Severity** | 🟡 MEDIUM → 🟢 LOW |
| **Mitigation** | Input validation (regex `^[A-Fa-f0-9-]{8,50}$`). Firestore auto-escapes document IDs. |

### 🟡 Vector 5: Data Leakage in Messages

| | |
|---|---|
| **Risk** | Full license keys hiển thị trong Telegram chat history |
| **Severity** | 🟡 MEDIUM → 🟢 LOW |
| **Mitigation** | Mask key: `A1B2-****-****-...-CSUM`. Full key gửi auto-delete message (60s). |

### 🟢 Vector 6: Cron Endpoint Abuse

| | |
|---|---|
| **Risk** | Spam endpoint → Firebase quota exhaust |
| **Severity** | 🟢 LOW |
| **Mitigation** | Secret header `X-Cron-Secret`. Rate limit 1 call/3 phút. |

### 🟢 Vector 7: Vercel Logs Exposure

| | |
|---|---|
| **Risk** | Sensitive data trong logs |
| **Severity** | 🟢 LOW |
| **Mitigation** | Không log keys/credentials. 2FA trên Vercel. Free tier logs expire trong 1h. |

---

## Summary

| Vector | Before | After Mitigation |
|--------|--------|------------------|
| Firebase Credentials | 🔴 | 🟢 (REST API, no Admin SDK) |
| Bot Token | 🔴 | 🟢 (User ID whitelist) |
| Webhook Hijacking | 🟡 | 🟢 (Secret token) |
| Command Injection | 🟡 | 🟢 (Input validation) |
| Data Leakage | 🟡 | 🟢 (Key masking) |
| Cron Abuse | 🟢 | 🟢 (Secret header) |
| Log Exposure | 🟢 | 🟢 (No sensitive logging) |

## So sánh với các hệ thống khác

| System | Credentials Risk | Write Access |
|--------|-----------------|--------------|
| Admin App (local) | 🟢 Local only | Admin SDK (full) |
| Seller App (local) | 🟢 Local only | Admin SDK (full) |
| Client App (compiled) | 🟢 Embedded + obfuscated | REST API (limited by rules) |
| **Telegram Bot (Vercel)** | 🟡 Cloud env vars | **REST API + Auth (limited by rules)** |

> ✅ **Verdict**: Bot KHÔNG làm giảm bảo mật tổng thể. Security Rules là tuyến phòng thủ chính, và chúng vẫn hoạt động với REST API + Auth.
