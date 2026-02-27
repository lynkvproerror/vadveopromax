# VEO Pro Max — Tổng hợp tính năng & Bảng giá

## 🎬 I. Tính năng tạo Video & Ảnh AI

### Video Generation (VEO 3.1)

| Workflow | Mô tả | Input | Output |
|----------|--------|-------|--------|
| **Text → Video** (T2V) | Tạo video từ prompt text | Text | Video 720p/1080p/4K |
| **Image → Video** (I2V) | Tạo video từ 1 ảnh (Start frame) | 1 Image + Text | Video |
| **Frames → Video** (F2V) | Tạo video từ 2 ảnh (Start + End frame) | 2 Images + Text | Video |
| **References → Video** (R2V) | Tạo video từ 1-3 ảnh tham chiếu | 1-3 Images + Text | Video |

### Image Generation

| Workflow | Mô tả | Model |
|----------|--------|-------|
| **Text → Image** (T2I) | Tạo ảnh từ text | GEM PIX 2 (Nano Banana Pro), Imagen 4 |
| **Image → Image** (I2I) | Biến đổi ảnh có sẵn | GEM PIX 2, Imagen 4 |

### Video Options

| Tính năng | Chi tiết |
|-----------|----------|
| **Aspect Ratio** | Landscape (16:9), Portrait (9:16) |
| **Speed Mode** | Fast (priority), LP - Lower Priority (queue thấp hơn, ít bị reject) |
| **Output Count** | 1-4 video/prompt |
| **Auto Upscale** | 720p → 1080p hoặc 4K tự động |
| **Video Model** | VEO 3.1 (latest), VEO 3.0 (legacy) |

---

## ⚡ II. Tính năng xử lý hàng loạt (Batch Processing)

| Tính năng | Mô tả |
|-----------|--------|
| **Queue Manager** | Quản lý hàng đợi tối đa 1,000 prompt |
| **Batch Import** | Nhập hàng loạt prompt từ file |
| **Multi-Output** | 1 prompt → 1-4 video đồng thời |
| **Auto-Retry** | Tự động retry 11 lần khi fail (403, timeout...) |
| **Task Journal** | Lưu trạng thái, crash recovery tự động |
| **Continuation** | Tiếp tục video (video nối tiếp) |

---

## 🔧 III. Kiến trúc đa tài khoản (Multi-Account)

| Tính năng | Mô tả |
|-----------|--------|
| **Multi-Account** | Chạy nhiều Google account đồng thời (tối đa 10) |
| **Multi-Foreman** | N Foreman/account — mỗi Foreman 1 prompt pipeline |
| **Max Workers** | Tối đa 20+ video/account chạy song song |
| **Chrome Profile** | Mỗi account = 1 Chrome profile riêng biệt |
| **Auto Dispatch** | Phân bổ task thông minh giữa các account |
| **Account Affinity** | Task continuation chạy đúng account gốc |

---

## 🛡️ IV. Anti-Detect & Bảo vệ tài khoản

| Tính năng | Mô tả |
|-----------|--------|
| **reCAPTCHA Auto-Solve** | Tự động xử lý reCAPTCHA v3 qua Extension Bridge |
| **Token Pool** | Pre-fetch 2 token/account, tái sử dụng smart |
| **Rate Lock** | Serialize submit per-account (chống spam) |
| **Adaptive Burst** | Tự động điều chỉnh delay giữa các lần submit |
| **Cooldown Backoff** | 403 → 30s/60s/120s cooldown tự động (exponential) |
| **Tab Keepalive** | Chống Chrome freeze tab khi idle |
| **x-client-data** | Headers tự động cập nhật từ Chrome real-time |
| **Profile Reset** | Tự động reset profile khi bị ban |

---

## 🖥️ V. Giao diện & Tiện ích

| Tab | Mô tả |
|-----|--------|
| **T2V / I2V / R2V / T2I / I2I** | Giao diện riêng cho từng workflow |
| **Queue** | Quản lý hàng đợi: Start All, Pause, Stop, Export |
| **Account** | Quản lý Chrome profiles + session |
| **Settings** | Cấu hình output, browser, model, delay |
| **License** | Kích hoạt key + xem usage stats |
| **DevConsole** *(TESTER)* | Dashboard debug, structured log, performance metrics |

### Tính năng nâng cao khác

| Tính năng | Mô tả |
|-----------|--------|
| **Custom Output** | Chọn thư mục output, naming pattern |
| **Image Library** | Quản lý ảnh tham chiếu (I2V, R2V) |
| **Image Enhancer** | Upscale ảnh bằng RealESRGAN (GPU) trước khi dùng |
| **Manifest Manager** | Auto-track project metadata |
| **Per-Account Logs** | Log file riêng cho từng account (debug dễ dàng) |
| **Session Monitor** | Giám sát session health real-time |
| **Crash Recovery** | TaskJournal auto-save, resume khi restart |

---

## 💰 VI. Bảng giá

### Gói dùng thử

| | **Trial** |
|---|---|
| **Giá** | **MIỄN PHÍ** (7 ngày) |
| Accounts | 1 |
| Workers | 2 |
| Prompts/ngày | 10 |
| Output/prompt | 1-2 |
| Workflows | T2V, I2V, R2V, T2I, I2I |
| Auto Upscale | ✅ |
| Queue Manager | ✅ |
| Batch Processing | ❌ |
| Multi-Account | ❌ |
| Download 4K | ❌ |
| Custom Output | ❌ |

### Gói Premium

| | **1 Tháng** | **3 Tháng** | **6 Tháng** | **1 Năm** | **Vĩnh viễn** |
|---|---|---|---|---|---|
| **Giá** | **300,000đ** | **500,000đ** | **800,000đ** | **1,200,000đ** | **3,000,000đ** |
| **Giá/tháng** | 300K | 167K (-44%) | 133K (-56%) | 100K (-67%) | ∞ |
| Accounts | 5 | Unlimited | Unlimited | Unlimited | Unlimited |
| Workers | 5 | 10 | Unlimited | Unlimited | Unlimited |
| Prompts/ngày | 100 | Unlimited | Unlimited | Unlimited | Unlimited |
| Output/prompt | 1-4 | 1-4 | 1-4 | 1-4 | 1-4 |
| All Workflows | ✅ | ✅ | ✅ | ✅ | ✅ |
| Batch Processing | ✅ | ✅ | ✅ | ✅ | ✅ |
| Multi-Account | ✅ | ✅ | ✅ | ✅ | ✅ |
| Auto Upscale | ✅ | ✅ | ✅ | ✅ | ✅ |
| Download 4K | ✅ | ✅ | ✅ | ✅ | ✅ |
| Custom Output | ✅ | ✅ | ✅ | ✅ | ✅ |
| Advanced Settings | ✅ | ✅ | ✅ | ✅ | ✅ |
| Image Library | ✅ | ✅ | ✅ | ✅ | ✅ |
| Continuation | ✅ | ✅ | ✅ | ✅ | ✅ |
| Priority Support | ❌ | ❌ | ✅ | ✅ | ✅ |
| Lifetime Updates | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Tiết kiệm** | — | **400K** | **1M** | **2.4M** | **♾️** |

---

## 🏗️ VII. Kiến trúc kỹ thuật (Điểm nhấn quảng cáo)

```
┌─────────────────────────────────────────────┐
│                 VEO Pro Max                  │
├─────────────────────┬───────────────────────┤
│   🖥️ PySide6 UI     │   ⚙️ Core Engine      │
│  • 8 Tab chuyên biệt│  • Multi-Foreman      │
│  • Real-time Queue  │  • Adaptive Burst     │
│  • Dark Theme       │  • Crash Recovery     │
├─────────────────────┼───────────────────────┤
│  🌐 Extension Bridge│  🔒 Security          │
│  • Chrome Extension │  • HWID Lock          │
│  • WebSocket Live   │  • Firebase License   │
│  • Auto reCAPTCHA   │  • HMAC Verification  │
└─────────────────────┴───────────────────────┘
```

### Điểm nổi bật kỹ thuật

- **VEO 3.1 API** — Model mới nhất của Google (2025)
- **Async Engine** — Xử lý bất đồng bộ, không block UI
- **Auto-Upscale Pipeline** — 720p → 1080p/4K tự động
- **Smart Retry** — 11 lần retry + exponential backoff
- **Multi-Foreman** — N pipeline song song/account
- **Extension Bridge** — WebSocket real-time với Chrome Extension
- **Per-Account Logging** — Debug riêng từng account, tagged by activity
