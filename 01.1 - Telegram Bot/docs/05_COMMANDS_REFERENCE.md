# 📖 Commands Reference — VEO License Telegram Bot

## 📊 Monitoring

| Command | Mô tả | Output |
|---------|--------|--------|
| `/start` | Khởi động bot | Welcome message + danh sách lệnh |
| `/status` | Tổng quan license system | Active/Expired/Revoked counts |
| `/health` | Kiểm tra kết nối | Firebase Primary ✅, Backup ✅ |
| `/pending` | Danh sách requests chờ duyệt | List + inline buttons |

---

## 🔍 Tra cứu

| Command | Mô tả | Ví dụ |
|---------|--------|-------|
| `/lookup <MID>` | Tra cứu theo Machine ID | `/lookup 3946C15B` |
| `/key <key>` | Tra cứu theo license key | `/key A1B2-C3D4-E5F6-...` |

### Output `/lookup`:
```
📋 License Info
🖥️ MID: 3946C15B
👤 Tên: Nguyễn Văn A
🔑 Key: A1B2-****-****-...-CSUM
📦 Gói: 3M | Role: PREMIUM
📅 Tạo: 2026-03-06
⏰ Hết hạn: 2026-06-04
🟢 Status: Active
🔄 Sync: ✅ Primary + Backup
```

---

## ✅ Quản lý Requests

| Command | Mô tả | Ví dụ |
|---------|--------|-------|
| `/approve <MID>` | Duyệt request | `/approve 3946C15B` |
| `/reject <MID> [lý do]` | Từ chối request | `/reject 3946C15B hết slot` |

### Flow `/approve`:
```
Admin: /approve 3946C15B

Bot:   📋 Request Info
       👤 Nguyễn Văn A
       📦 Yêu cầu: 3M (90 ngày)
       
       Chọn gói duyệt:
       [1M] [3M] [6M] [1Y] [LT]
       
Admin: tap [3M]

Bot:   ✅ Xác nhận duyệt 3M cho 3946C15B?
       [✅ Xác nhận] [❌ Hủy]

Admin: tap [✅]

Bot:   ✅ Đã tạo key!
       🔑 A1B2-C3D4-E5F6-G7H8-I9J0-K1L2-M3N4-O5P6-CSUM
       📦 3M (90 ngày)
       ⏰ Hết hạn: 2026-06-04
       (🗑️ Tin nhắn này tự xóa sau 60s)
```

---

## 🔧 Quản lý Keys

| Command | Mô tả | Ví dụ |
|---------|--------|-------|
| `/create` | Tạo key mới (interactive) | Bot hỏi MID → Tier → Days |
| `/extend <MID> <days>` | Gia hạn key | `/extend 3946C15B 30` |
| `/revoke <key>` | Thu hồi key | `/revoke A1B2-C3D4-...` |
| `/delete <key>` | Xóa key vĩnh viễn | `/delete A1B2-C3D4-...` |

---

## 🔄 Maintenance

| Command | Mô tả |
|---------|--------|
| `/sync` | Force sync Primary → Backup |
| `/cleanup` | Dọn keys hết hạn |
| `/orphans` | Scan _mid_to_key orphaned entries |

---

## 🔐 Security Commands

| Command | Mô tả |
|---------|--------|
| `/audit [n]` | Xem n actions gần nhất (default: 10) |
| `/whoami` | Hiện admin info + permissions |

---

## Inline Button Actions

Khi bot gửi alert request mới, có inline buttons:

| Button | Action |
|--------|--------|
| ✅ Duyệt | → Approve flow (chọn tier) |
| 📦 Đổi gói | → Thay đổi tier trước khi duyệt |
| ❌ Từ chối | → Reject + optional reason |
| 🔍 Xem chi tiết | → Lookup MID |

---

## Alert Messages

| Alert | Format |
|-------|--------|
| 🆕 Request mới | `🆕 Yêu cầu mới!\n👤 {name}\n🖥️ {mid}\n📦 {tier}` |
| ✅ Key activated | `✅ Key kích hoạt: {name} ({tier})` |
| ⚠️ Keys hết hạn | `⚠️ {n} key hết hạn hôm nay` |
| 🔴 Sync error | `🔴 Backup sync failed: {error}` |
| 🟢 Daily summary | `📊 Tổng kết ngày: {active}/{expired}/{revoked}` |
