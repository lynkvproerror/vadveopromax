# 🤖 VEO License Telegram Bot

> Quản lý license system 24/7 từ Telegram — Miễn phí, không cần VPS, không cần thẻ.

## Architecture

```
📱 Telegram ──webhook──→ ☁️ Vercel (free)
                              │
                         🔑 Firebase Auth (bot account)
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
             🔥 Primary DB       🔥 Backup DB
```

## Chạy song song với:
- ✅ Admin App (PySide6 GUI — Admin SDK local)
- ✅ Seller App (Admin SDK local)
- ✅ Client App (VEO PRO MAX — REST API)

## Tài liệu

| File | Mô tả |
|------|--------|
| [01_DEPLOYMENT_GUIDE.md](docs/01_DEPLOYMENT_GUIDE.md) | Hướng dẫn triển khai từ A-Z |
| [02_SECURITY_ANALYSIS.md](docs/02_SECURITY_ANALYSIS.md) | Phân tích bảo mật 7 attack vectors |
| [03_ARCHITECTURE.md](docs/03_ARCHITECTURE.md) | Kiến trúc hệ thống + data flow |
| [04_FIREBASE_RULES.md](docs/04_FIREBASE_RULES.md) | Security Rules cho bot account |
| [05_COMMANDS_REFERENCE.md](docs/05_COMMANDS_REFERENCE.md) | Danh sách lệnh bot |

## Quick Start

```bash
# 1. Tạo bot trên Telegram
# → Nhắn @BotFather → /newbot → lấy TOKEN

# 2. Lấy Telegram User ID
# → Nhắn @userinfobot → lấy ID

# 3. Deploy lên Vercel
vercel deploy

# 4. Set webhook
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<app>.vercel.app/api/webhook/<secret>"
```
