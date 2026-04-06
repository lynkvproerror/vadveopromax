# 🏗️ Architecture — VEO License Telegram Bot

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    🔥 Firebase Cloud                         │
│  ┌──────────────┐              ┌──────────────┐             │
│  │ Primary DB   │              │ Backup DB    │             │
│  │ veo-pro-max  │              │ veoauto-f54b5│             │
│  │              │              │              │             │
│  │ _lic         │    sync      │ _lic         │             │
│  │ _upgrade_req │ ◄──────────► │ _upgrade_req │             │
│  │ _trials      │              │ _trials      │             │
│  │ _customers   │              │ _customers   │             │
│  │ _mid_to_key  │              │ _mid_to_key  │             │
│  └──────┬───────┘              └──────┬───────┘             │
│         │                             │                     │
│         │      🔑 Firebase Auth       │                     │
│         │      (bot@system.local)     │                     │
│         │             │               │                     │
└─────────┼─────────────┼───────────────┼─────────────────────┘
          │             │               │
    ┌─────┴──────┐ ┌────┴────┐   ┌─────┴──────┐
    │ Admin App  │ │Telegram │   │ Seller App │
    │ (PySide6)  │ │  Bot    │   │ (PySide6)  │
    │            │ │(Vercel) │   │            │
    │ Admin SDK  │ │REST API │   │ Admin SDK  │
    │ LOCAL only │ │+ Auth   │   │ LOCAL only │
    └────────────┘ └────┬────┘   └────────────┘
                        │
                   ┌────┴────┐
                   │📱Admin  │
                   │Telegram │
                   └─────────┘
```

---

## Data Flow

### Flow 1: Request mới → Alert

```
Client App → Firebase _upgrade_requests/{MID}
                          │
              ⏰ cron-job.org (5 min)
                          │
                          ▼
              Vercel /api/cron/check_pending
                          │
                  Query _upgrade_requests
                  where status = "pending"
                          │
                          ▼
              Telegram sendMessage → 📱 Admin
              [✅ Duyệt] [❌ Từ chối]
```

### Flow 2: Admin Approve từ Telegram

```
📱 Admin tap [✅ Duyệt]
         │
         ▼
Telegram callbackQuery → Vercel /api/webhook
         │
    1. Firebase Auth login (bot account)
    2. Atomic claim _upgrade_requests/{MID}
    3. Generate license key (license_keygen)
    4. Write _lic/{key} (Primary + Backup)
    5. Write _mid_to_key/{MID}
    6. Delete _upgrade_requests/{MID}
    7. Write _customers/{MID}
         │
         ▼
Telegram reply: "✅ Key created: A1B2-****-..."
```

### Flow 3: Concurrent Access (3 systems)

```
                    _upgrade_requests/{MID}
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         Admin App   Telegram Bot  Seller App
              │           │           │
              └─────┬─────┘           │
                    │                 │
            Atomic Claim ◄────────────┘
            (transaction)
                    │
              First wins ✅
              Others get "Already processed" ⚠️
```

---

## Module Structure

```
001 - Telegram Bot/
├── api/                        # Vercel serverless functions
│   ├── webhook/
│   │   └── [secret].py         # Telegram webhook handler
│   └── cron/
│       └── check_pending.py    # Scheduled alert check
│
├── bot/                        # Bot logic
│   ├── __init__.py
│   ├── handlers.py             # Command + callback handlers
│   ├── firebase_auth.py        # Firebase Auth REST login
│   ├── firebase_ops.py         # CRUD operations via REST API
│   ├── keygen.py               # License key generation
│   ├── formatters.py           # Message formatting
│   └── security.py             # Whitelist, rate limit, input validation
│
├── docs/                       # Documentation
│   ├── 01_DEPLOYMENT_GUIDE.md
│   ├── 02_SECURITY_ANALYSIS.md
│   ├── 03_ARCHITECTURE.md      # ← This file
│   ├── 04_FIREBASE_RULES.md
│   └── 05_COMMANDS_REFERENCE.md
│
├── scripts/
│   └── create_bot_account.py   # One-time setup script
│
├── vercel.json                 # Vercel config
├── requirements.txt            # Python dependencies
└── README.md
```

---

## Dependencies

```
python-telegram-bot==21.*       # Telegram Bot API (webhook mode)
requests>=2.31                  # Firebase REST API calls
```

> **Không cần**: `firebase-admin` (chạy trên Vercel), `PySide6` (headless)
