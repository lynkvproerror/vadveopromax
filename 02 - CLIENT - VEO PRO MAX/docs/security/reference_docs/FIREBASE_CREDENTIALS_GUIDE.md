# 🔥 Firebase Credentials Guide

> **Date**: 2026-02-04  
> **Scope**: Admin vs Client Firebase access

---

## 📂 Credential File Locations

### Admin Tool
```
admin/
├── levanlinh.kma/
│   └── veo-pro-max-firebase-adminsdk-...json    # 🔥 PRIMARY
└── lynkv.pro/
    └── veoauto-f54b5-firebase-adminsdk-...json  # 💾 BACKUP
```

### Client App
```
CLIENT SHOULD NOT HAVE ADMIN SDK CREDENTIALS!
```

---

## ❓ FAQ

### Q1: Có thể thay đổi credential files không?
**A**: Có, nhưng cần restart app để reload.

| Thay đổi | Admin Tool | Client App |
|----------|------------|------------|
| Thay file JSON | ✅ Restart required | N/A |
| Qua Settings dialog | ✅ Auto reload | N/A |
| Env variable | ✅ Override paths | N/A |

### Q2: Client có dùng credentials không?
**A**: **KHÔNG NÊN!**

| Approach | Security | Complexity |
|----------|----------|------------|
| ❌ Admin SDK in client | 🔴 Very bad | Simple |
| ✅ Firebase Web SDK | 🟢 Good | Medium |
| ✅ Your own API | 🟢 Best | Complex |

### Q3: Client validate license như thế nào?

**Option 1: Qua your own API (Recommended)**
```
Client ──► Your Backend API ──► Firebase Admin SDK
```

**Option 2: Firebase Web SDK (Direct)**
```
Client ──► Firebase (với Firestore Security Rules)
```

---

## 🔒 Security Rules for Client Access

Nếu dùng Firebase Web SDK, cần set Firestore rules:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // License collection - READ ONLY
    match /_lic/{keyId} {
      // Allow read if machine_id matches
      allow read: if request.auth != null 
                  && resource.data.machine_id == request.auth.token.machine_id;
      
      // Block all writes
      allow write: if false;
    }
  }
}
```

---

## 📐 Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        ADMIN SIDE                            │
│                                                              │
│   license_manager_gui.py                                     │
│          │                                                   │
│          ▼                                                   │
│   ┌───────────────┐      ┌───────────────┐                  │
│   │ PRIMARY       │ sync │ BACKUP        │                  │
│   │ Admin SDK     │─────►│ Admin SDK     │                  │
│   └───────────────┘      └───────────────┘                  │
│                                                              │
│   ⚠️ NEVER GIVE TO CLIENT!                                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ Firestore
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT SIDE                           │
│                                                              │
│   Option A: Firebase Web SDK (Anonymous Auth)                │
│   ┌───────────────────────────────────────────┐             │
│   │ Firebase App ID + API Key (safe to embed) │             │
│   │ → Validate via Firestore Security Rules   │             │
│   └───────────────────────────────────────────┘             │
│                                                              │
│   Option B: Your Own Validation API                          │
│   ┌───────────────────────────────────────────┐             │
│   │ Client → Your API → Firebase Admin SDK    │             │
│   └───────────────────────────────────────────┘             │
│                                                              │
│   Current: Admin SDK embedded (will obfuscate with PyArmor) │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Changing Credentials

### Method 1: Replace Files
1. Replace JSON file in `levanlinh.kma/` or `lynkv.pro/`
2. Restart Admin GUI

### Method 2: Settings Dialog
1. Open Admin GUI
2. Click ⚙️ Settings
3. Browse for new credential file
4. Save → Auto reload

### Method 3: Environment Variables
```bash
# Override primary
export VEO_PRIMARY_CRED="/path/to/new/primary.json"

# Override backup
export VEO_BACKUP_CRED="/path/to/new/backup.json"

# Or via .veoauto/config.json
# ~/.veoauto/config.json
{
  "primary_cred": "/path/to/primary.json",
  "backup_cred": "/path/to/backup.json",
  "auto_sync": true
}
```

---

## ⚠️ Important Notes

> [!CAUTION]
> Admin SDK credentials (`*-firebase-adminsdk-*.json`) have FULL access to Firestore.
> Never distribute to clients!

> [!TIP]
> For client apps, use Firebase Web SDK with Anonymous Auth + Security Rules.
> Or create your own validation API endpoint.
