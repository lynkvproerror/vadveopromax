# VEO Web Client Protocol Analysis (Full Report)

## 1. Tóm tắt Tổng quan
Quá trình phân tích toàn diện từ **tất cả các file HAR** (HTTP Archive — định dạng chuẩn ghi lại mọi request/response của trình duyệt qua F12 DevTools) cho thấy VEO Web Client sử dụng kiến trúc phức tạp kết hợp nhiều giao thức và cơ chế xác thực khác nhau tùy theo domain và tính năng.

> **Thuật ngữ nền tảng dùng xuyên suốt tài liệu:**
>
> | Thuật ngữ | Giải thích | Tại sao quan trọng |
> |---|---|---|
> | **TRPC** | TypeScript Remote Procedure Call — framework gọi API qua HTTP với type-safety, URL dạng `/fx/api/trpc/{procedure}` | Google dùng cho quản lý project/settings/history trên `labs.google` |
> | **same-origin** | Request gửi đến **cùng domain** với trang đang mở (vd: trang `labs.google` gọi API `labs.google`) → browser **TỰ ĐỘNG gửi Cookies** | Lý do TRPC/AUTH chỉ cần Cookies |
> | **cross-site** | Request gửi đến **domain khác** (vd: trang `labs.google` gọi API `aisandbox-pa.googleapis.com`) → browser **KHÔNG gửi Cookies** (bảo mật) | Lý do REST/STORAGE phải dùng Custom Headers thay Cookies |
> | **protobuf** | Protocol Buffers — format binary serialization của Google, nhỏ hơn + nhanh hơn JSON | reCAPTCHA dùng protobuf cho request/response; `x-client-data` cũng là protobuf |
> | **T2V** | Text-to-Video — tạo video từ prompt text thuần, **KHÔNG** có ảnh đầu vào | Endpoint: `batchAsyncGenerateVideoText`, model key `t2v_*` |
> | **I2V** | Image-to-Video — 2 biến thể: **Start Only** (1 ảnh đầu) và **F2V** (ảnh đầu + ảnh cuối) | Start: `batchAsyncGenerateVideoStartImage`, F2V: `...StartAndEndImage` |
> | **F2V** | Frames-to-Video — biến thể I2V dùng 2 frame (start + end). Model key có `_fl_` | Cùng domain I2V, khác endpoint + model |
> | **R2V** | Reference-to-Video (Ingredients) — dùng 1-3 ảnh tham khảo | Endpoint: `batchAsyncGenerateVideoReferenceImages` |
> | **T2I** | Text-to-Image — tạo ảnh từ prompt (chưa có trong HAR, dùng cùng endpoint I2I) | Endpoint: `batchGenerateImages` (không có `imageInputs`) |
> | **I2I** | Image-to-Image — biến đổi ảnh có sẵn bằng prompt, dùng model **GEM_PIX_2** (Imagen) | Endpoint: `batchGenerateImages` + `imageInputs` |
> | **GEM_PIX_2** | Tên model Google Imagen dùng cho T2I/I2I. Khác hoàn toàn với VEO (VEO chỉ cho video) | Field `imageModelName: "GEM_PIX_2"` trong payload |
> | **PINHOLE** | Tên mã nội bộ Google cho **Flow** (VideoFX). Xuất hiện trong payload `tool: "PINHOLE"` | Phải gửi chính xác giá trị này trong `clientContext` |
> | **BACKBONE** | Tên mã nội bộ Google cho **Whisk**. Xuất hiện trong payload `tool: "BACKBONE"` | Phân biệt Flow vs Whisk trong cùng API backend |

### 1.1. Kiến trúc Tổng thể
```mermaid
graph LR
    Client[VEO Web Client]
    TRPC[labs.google/fx/api/trpc]
    REST[aisandbox-pa.googleapis.com]
    Storage[storage.googleapis.com]
    Recaptcha[google.com/recaptcha/enterprise]
    Auth[labs.google/fx/api/auth]

    Client -->|Cookies + JSON| TRPC
    Client -->|x-browser-* ± API Key| REST
    Client -->|Signed URL| Storage
    Client -->|Site Key + Protobuf| Recaptcha
    Client -->|Cookies| Auth
```

### 1.2. Bảng Phân loại Domain & Xác thực

| Domain | Vai trò | Xác thực | Content-Type |
|---|---|---|---|
| `labs.google` | TRPC Server (quản lý) | Cookies (ngầm định) | `application/json` |
| `aisandbox-pa.googleapis.com` | REST Server (generate) | `x-browser-*` bắt buộc, API Key chỉ GET + checkApp | `text/plain;charset=UTF-8` |
| `storage.googleapis.com` | Download | Signed URL (query params) | `video/mp4` |
| `www.google.com` | Recaptcha Enterprise | Site Key | `application/x-protobuffer` |

### 1.3. Phát hiện Quan trọng vs Mã nguồn
- **MÃ NGUỒN** (`api_client.py`): Dùng `Authorization: Bearer` + `x-goog-recaptcha-token` header → **SAI**
- **THỰC TẾ HAR**: Dùng Cookies (TRPC) hoặc API Key + `x-browser-*` (REST) → **ĐÚNG**
- **LỖI NGHIÊM TRỌNG**: `ProjectManager` gọi `create_project()` không tồn tại trong `VEOApiClient`

### 1.4. Bảng Tóm tắt Xác thực (5 Phương thức) — Đã xác minh 54 HAR / 3027+ requests

#### A. Danh sách 5 Phương thức Xác thực

| # | Phương thức | Mô tả | Ví dụ giá trị | Phạm vi áp dụng |
|---|---|---|---|---|
| 1 | **Browser Cookies** | Gửi ngầm định cho **same-origin** (`labs.google` → `labs.google` = cùng domain → cookies tự gửi). Chrome HAR không export Cookie header (hạn chế kỹ thuật) | `__Secure-next-auth.session-token=...` | Chỉ TRPC + AUTH |
| 2 | **API Key** | `?key=` trong URL query (GET) hoặc `x-goog-api-key` header (chỉ `checkAppAvailability`). **KHÔNG có ở REST POST gen** | `AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY` | Chỉ REST GET + checkApp |
| 3 | **Custom Headers** | 5 headers bắt buộc: `x-browser-channel`, `x-browser-copyright`, `x-browser-year`, `x-browser-validation`, `x-client-data` | `stable`, `Copyright 2026 Google LLC...`, `2026`, `WVxyJFF0uI...`, `CI+2yQE...` | REST + STORAGE + RECAPTCHA |
| 4 | **reCAPTCHA Token** | Nhúng trong **payload body** (`clientContext.recaptchaContext`), **KHÔNG phải header**. Gồm 2 fields: `token` + `applicationType: "RECAPTCHA_APPLICATION_TYPE_WEB"`. Token sinh bởi `grecaptcha.enterprise.execute(siteKey, {action: "VIDEO_GENERATION"})` | `0cAFcWeA71jcH...` (từ `recaptcha/enterprise/reload`) | Chỉ REST POST gen |
| 5 | **Signed URL** | Auth nằm trong URL query params, tự chứa đầy đủ, hết hạn ~24h | `?GoogleAccessId=...&Expires=1769845118&Signature=...` | Chỉ STORAGE |

#### B. Ma trận Kết hợp Phương thức Theo Loại Endpoint

> **Ghi chú**: `sec-fetch-site` là header browser tự thêm, cho biết request **cùng domain** (same-origin) hay **khác domain** (cross-site). Đây là cơ chế bảo mật trình duyệt — **KHÔNG thể thay đổi bằng code**. TRPC/AUTH = `same-origin` → cookies tự gửi. REST/STORAGE = `cross-site` → cookies **KHÔNG** gửi, phải dùng Custom Headers.

| Loại Endpoint | Target Domain | sec-fetch-site | Cookies | API Key | Custom Headers 5/5 | reCAPTCHA payload | Signed URL |
|---|---|---|:---:|:---:|:---:|:---:|:---:|
| **AUTH** | `labs.google` | same-origin | ✅ auto | ❌ | ❌ | ❌ | ❌ |
| **TRPC** | `labs.google` | same-origin | ✅ auto | ❌ | ❌ | ❌ | ❌ |
| **REST GET** | `aisandbox-pa` | cross-site | ❌ | ✅ URL query | ✅ | ❌ | ❌ |
| **REST POST gen** | `aisandbox-pa` | cross-site | ❌ | ❌ | ✅ | ✅ | ❌ |
| **REST POST poll** | `aisandbox-pa` | cross-site | ❌ | ❌ | ✅ | ❌ | ❌ |
| **REST POST check** | `aisandbox-pa` | cross-site | ❌ | ✅ header (chỉ checkApp) | ✅ | ❌ | ❌ |
| **REST POST GIF** | `aisandbox-pa` | cross-site | ❌ | ❌ | ✅ | ❌ | ❌ |
| **STORAGE** | `storage.googleapis` | cross-site | ❌ | ❌ | ✅ | ❌ | ✅ |
| **RECAPTCHA** | `www.google.com` | mixed | ❌ | ❌ | ✅ | ❌ | ❌ |

#### C. Cảnh báo Quan trọng

> ⚠️ **`access_token` (`ya29.*`) từ AUTH:session KHÔNG ĐƯỢC DÙNG trong bất kỳ API request nào.**
> Token này chỉ dùng nội bộ bởi Next.js SSR. Trong 50 HAR files (2968 requests), không có request nào chứa `Authorization` header.

> 🚫 **Code hiện tại (`api_client.py`) dùng `Authorization: Bearer` + `x-goog-recaptcha-token` header → HOÀN TOÀN SAI.**
> Cần thay bằng: Custom Headers (5/5) + reCAPTCHA token trong payload body.

> ✅ **Quy tắc kết hợp cho REST POST generate**: Phải có **ĐỦ 2** phương thức đồng thời:
> 1. Custom Headers (5 headers `x-browser-*` + `x-client-data`) — xác thực browser thật
> 2. reCAPTCHA token (trong `clientContext.recaptchaContext.token` của payload body, **KHÔNG phải header**)
>
> ⚠️ **API Key (`x-goog-api-key`) KHÔNG CÓ trong REST POST gen** (đã xác minh 0/58 requests). API Key chỉ dùng cho REST GET (URL query) và `checkAppAvailability` (header).
>
> Thiếu Custom Headers hoặc reCAPTCHA → request bị reject.

> 📊 **Hạn chế HAR**: Chrome DevTools export HAR **strip 100% Cookie headers** (bảo mật). Cookies được verify bằng `sec-fetch-site: same-origin` cho TRPC/AUTH endpoints.

#### D. Ánh xạ Chi tiết: Mỗi Hành động → Kết hợp Phương thức Xác thực

> 📌 **Flow vs Whisk — 2 công cụ khác nhau trong `labs.google`**
>
> | | **Flow** (VideoFX) | **Whisk** |
> |---|---|---|
> | **URL** | `labs.google/fx/tools/video-fx` | `labs.google/fx/tools/whisk` |
> | **Chức năng** | 6 chế độ: T2V, I2V (Start Only), F2V (Start+End), R2V (Ingredients), T2I, I2I | Remix/sáng tạo ảnh từ ảnh mẫu |
> | **Tên mã (tool)** | `PINHOLE` (trong mọi `clientContext.tool`) | `BACKBONE` (trong `clientContext.tool`) |
> | **Endpoints riêng** | `project.*`, `videoFx.*`, `media.*`, tất cả `batchAsync*` | `whisk:getVideoCreditStatus` |
> | **Endpoints chung** | `general.*`, `auth/session`, `credits`, `checkAppAvailability`, `fetchUserRecommendations` | ← Dùng chung |
> | **Init riêng** | `getFlowAppConfig` (chỉ reload), `listPreambles` | `fetchToolAvailability`, `fetchFeatureAvailability` |
>
> Cả hai dùng **cùng hạ tầng auth** (cookies, custom headers, reCAPTCHA) và **cùng REST API backend** (`aisandbox-pa.googleapis.com`). Bảng dưới đây ghi chú `[W]` cho endpoints chỉ xuất hiện trong Whisk sessions.

Bảng dưới đây sắp xếp theo **trình tự thực thi thực tế** quan sát từ 50 HAR files, nhóm theo **từng công việc cụ thể**.

**Ký hiệu**: 🍪 = Cookies (same-origin auto) | 🔑 = API Key | 🛡️ = Custom Headers 5/5 | 🤖 = reCAPTCHA Token (payload) | 🔗 = Signed URL | `[W]` = chỉ Whisk

##### Công việc 1: Mở trang Flow (Full Page Load) — 3 HAR files

> Xảy ra khi user mở/reload `labs.google/fx/tools/video-fx`. Tất cả gọi **đồng thời** (parallel).

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `GET /v1/credits?key=...` | REST | 🔑query + 🛡️ | Kiểm tra credits còn lại |
| 1 | `POST /v1:fetchUserRecommendations` | REST | 🛡️ | Gợi ý cho user |
| 1 | `POST /v1:checkAppAvailability` | REST | 🔑header + 🛡️ | Kiểm tra tool khả dụng |
| 1 | `project.getProject` | TRPC | 🍪 | Load project hiện tại |
| 1 | `videoFx.getFlowAppConfig` | TRPC | 🍪 | Feature flags |
| 1 | `project.searchProjectScenes` | TRPC | 🍪 | Load scenes |
| 1 | `general.fetchUserAcknowledgement` | TRPC | 🍪 | Kiểm tra ToS |
| 1 | `general.fetchUserLocale` | TRPC | 🍪 | Ngôn ngữ user |
| 1 | `general.submitBatchLog` | TRPC | 🍪 | Telemetry init |
| 2 | `videoFx.getUserSettings` | TRPC | 🍪 | Cài đặt user |
| 2 | `general.fetchUserPreferences` | TRPC | 🍪 | Preferences |
| 2 | `project.searchProjectWorkflows` | TRPC | 🍪 | Load workflows |
| 2 | `videoFx.getVideoModelConfig` | TRPC | 🍪 | Danh sách 30+ models |
| 2 | `videoFx.listPreambles` | TRPC | 🍪 | System prompts |
| 3 | `media.fetchUserHistoryDirectly` | TRPC | 🍪 | Lịch sử (phân trang) |
| 3 | `media.fetchFlowUserIngredients` | TRPC | 🍪 | Ảnh reference đã upload |
| 3 | `GET /fx/api/auth/session` | AUTH | 🍪 | Token nội bộ (`ya29.*`) |

##### Công việc 2: Tạo Project Mới — 1 HAR file

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `general.submitBatchLog` | TRPC | 🍪 | Log sự kiện tạo project |
| 2 | `project.createProject` | TRPC | 🍪 | Mutation → trả projectId |
| 3 | `project.getProject` | TRPC | 🍪 | Load project vừa tạo |
| 3 | `project.searchProjectScenes` | TRPC | 🍪 | Load scenes (trống) |
| 4 | `media.fetchUserHistoryDirectly` | TRPC | 🍪 | Load lịch sử |
| 4 | `videoFx.getUserSettings` | TRPC | 🍪 | Load settings |
| 4 | `videoFx.getVideoModelConfig` | TRPC | 🍪 | Load models |
| 4 | `general.fetchUserPreferences` | TRPC | 🍪 | Load preferences |
| 4 | `project.searchProjectWorkflows` | TRPC | 🍪 | Load workflows |
| 4 | `videoFx.listPreambles` | TRPC | 🍪 | Load preambles |

##### Công việc 3: Generate Video (T2V / I2V / F2V / R2V) — 17 HAR files

> Flow: Load → Upload ảnh → Chọn model → reCAPTCHA → Submit → Poll → Kết quả

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `project.searchProjectScenes` | TRPC | 🍪 | Refresh scenes |
| 2 | `media.fetchUserHistoryDirectly` | TRPC | 🍪 | Load lịch sử gần |
| 2 | `general.fetchUserAcknowledgement` | TRPC | 🍪 | Kiểm tra ToS |
| 3 | `GET /v1/media/{ID}?key=...` | REST | 🔑query + 🛡️ | Load ảnh reference hiện có |
| 4 | `POST /v1:uploadUserImage` | REST | 🛡️ | Upload ảnh mới (nếu cần) |
| 5 | `videoFx.setLastSelectedVideoModelKey` | TRPC | 🍪 | Chọn model (vd: `veo-3`) |
| 5 | `videoFx.setLastSelectedVideoAspectRatio` | TRPC | 🍪 | Chọn tỷ lệ (vd: `16:9`) |
| 6 | `general.submitBatchLog` | TRPC | 🍪 | Log trước khi submit |
| 7 | `recaptcha/enterprise/reload` | RECAPTCHA | 🛡️ | Lấy reCAPTCHA token |
| 8 | `POST batchAsync...ReferenceImages` | REST | 🛡️ + 🤖 | **Submit R2V** (hoặc variant khác) |
| 8 | ↳ `POST batchAsync...StartImage` | REST | 🛡️ + 🤖 | **Submit I2V-Start** |
| 8 | ↳ `POST batchAsync...StartAndEndImage` | REST | 🛡️ + 🤖 | **Submit I2V-StartEnd** |
| 8 | ↳ `POST batchAsyncGenerateVideoText` | REST | 🛡️ + 🤖 | **Submit T2V** |
| 9 | `recaptcha/enterprise/clr` | RECAPTCHA | 🛡️ | Log reCAPTCHA result |
| 10 | `POST batchCheckAsync...Status` | REST | 🛡️ | Poll mỗi ~6s cho đến khi SUCCESSFUL |
| 11 | `GET /v1/media/{ID}?key=...` | REST | 🔑query + 🛡️ | Lấy metadata kết quả |
| 11 | `general.submitBatchLog` | TRPC | 🍪 | Log completion |

##### Công việc 4: Generate Ảnh (T2I / I2I) — 5 HAR files

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `project.searchProjectScenes` | TRPC | 🍪 | Refresh scenes |
| 2 | `general.submitBatchLog` | TRPC | 🍪 | Log sự kiện |
| 2 | `media.fetchUserHistoryDirectly` | TRPC | 🍪 | Load lịch sử |
| 3 | `POST /v1:uploadUserImage` | REST | 🛡️ | Upload ảnh reference (nếu có) |
| 4 | `recaptcha/enterprise/reload` | RECAPTCHA | 🛡️ | Lấy reCAPTCHA token |
| 5 | `POST batchGenerateImages` | REST | 🛡️ + 🤖 | **Submit** — kết quả trả **sync** |
| 6 | `recaptcha/enterprise/clr` | RECAPTCHA | 🛡️ | Log reCAPTCHA result |

##### Công việc 5: Upscale Video (1080p / 4K) — 8 HAR files

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `project.searchProjectScenes` | TRPC | 🍪 | Refresh scenes |
| 2 | `general.submitBatchLog` | TRPC | 🍪 | Log sự kiện |
| 3 | `recaptcha/enterprise/reload` | RECAPTCHA | 🛡️ | Lấy reCAPTCHA token |
| 4 | `POST batchAsync...UpsampleVideo` | REST | 🛡️ + 🤖 | **Submit upscale** |
| 5 | `recaptcha/enterprise/clr` | RECAPTCHA | 🛡️ | Log reCAPTCHA result |
| 6 | `POST batchCheckAsync...Status` | REST | 🛡️ | Poll mỗi ~6s |
| 7 | `GET /v1/media/{ID}?key=...` | REST | 🔑query + 🛡️ | Lấy video upscale xong |

##### Công việc 6: Upscale Ảnh (2K / 4K) — 4 HAR files

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `project.searchProjectScenes` | TRPC | 🍪 | Refresh scenes |
| 2 | `general.submitBatchLog` | TRPC | 🍪 | Log sự kiện |
| 3 | `recaptcha/enterprise/reload` | RECAPTCHA | 🛡️ | Lấy reCAPTCHA token |
| 4 | `POST flow/upsampleImage` | REST | 🛡️ + 🤖 | **Submit** — kết quả trả **sync** |
| 5 | `recaptcha/enterprise/clr` | RECAPTCHA | 🛡️ | Log reCAPTCHA result |

##### Công việc 7: Download Video / GIF — 2 HAR files

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `project.searchProjectScenes` | TRPC | 🍪 | Refresh scenes |
| 2a | `GET /ai-sandbox-videofx/video/{UUID}` | STORAGE | 🛡️ + 🔗 | **Tải video MP4** (Signed URL) |
| 2b | `POST generatePinholeGif` | REST | 🛡️ | **Tải GIF** (chỉ cần Custom Headers) |
| 2b | `GET /v1/media/{ID}?key=...` | REST | 🔑query + 🛡️ | Load ảnh/metadata |
| 3 | `general.submitBatchLog` | TRPC | 🍪 | Log download event |

##### Công việc 8: Whisk Session `[W]` — 3 HAR files

> Whisk dùng endpoint riêng + một số endpoint chung với Flow.

| Bước | Endpoint | Giao thức | Auth | Ghi chú |
|:---:|---|---|---|---|
| 1 | `POST /v1:checkAppAvailability` | REST | 🔑header + 🛡️ | Kiểm tra Whisk khả dụng |
| 1 | `general.fetchToolAvailability` | TRPC | 🍪 | `[W]` Tool flags |
| 1 | `general.fetchUserAcknowledgement` | TRPC | 🍪 | Kiểm tra ToS |
| 1 | `general.fetchUserLocale` | TRPC | 🍪 | Ngôn ngữ |
| 1 | `general.submitBatchLog` | TRPC | 🍪 | Telemetry |
| 1 | `GET /fx/api/auth/session` | AUTH | 🍪 | Token nội bộ |
| 1 | `general.fetchFeatureAvailability` | TRPC | 🍪 | `[W]` Feature flags |
| 1 | `general.fetchUserPreferences` | TRPC | 🍪 | Preferences |
| 2 | `GET /v1/media/{ID}?key=...` | REST | 🔑query + 🛡️ | Load media items |
| 3 | `POST /v1/whisk:getVideoCreditStatus` | REST | 🛡️ | `[W]` Credit status |
| 4 | `GET /v1/credits?key=...` | REST | 🔑query + 🛡️ | Kiểm tra credits |
| 4 | `POST /v1:fetchUserRecommendations` | REST | 🛡️ | Gợi ý |
| 4 | `videoFx.getFlowAppConfig` | TRPC | 🍪 | App config |

##### Endpoints bổ sung (xuất hiện rải rác, không thuộc workflow cố định)

| Endpoint | Giao thức | Auth | Khi nào gọi |
|---|---|---|---|
| `general.submitUserAcknowledgement` | TRPC | 🍪 | User xác nhận ToS (1 lần/session) |
| `general.reportClientSideError` | TRPC | 🍪 | Khi có lỗi HTTP |
| `GET fifeUrl` (trong generate response) | STORAGE | 🔗 | URL trực tiếp từ response ảnh |
| `POST batchAsync...Reshoot` | REST | 🛡️ + 🤖 | Tạo lại video (chưa có HAR) |
| `POST batchAsync...ExtendVideo` | REST | 🛡️ + 🤖 | Kéo dài video (chưa có HAR) |

##### Tổng kết Quy tắc Auth theo Giao thức (Đã xác minh từ 2968 requests)

```
AUTH              → 🍪 (same-origin cookies)         [9 calls]
TRPC endpoints    → 🍪 (same-origin cookies)         [1649 calls]
REST GET          → 🔑query + 🛡️                     [358 calls]
REST POST (check) → 🔑header + 🛡️                    [chỉ checkAppAvailability]
REST POST (gen)   → 🛡️ + 🤖                          [58 calls]  ← KHÔNG CÓ API Key
REST POST (poll)  → 🛡️                               [721 calls] ← KHÔNG cần 🤖
REST POST (GIF)   → 🛡️                               [1 call]    ← KHÔNG cần 🤖
REST POST (other) → 🛡️                               [fetchRec, whiskCredit, etc.]
STORAGE           → 🛡️ + 🔗                          [4 calls]
RECAPTCHA         → 🛡️                               [123 calls]
```

> **QUY TẮC VÀNG**: Chỉ các hành động **tạo nội dung mới** (generate, upscale) mới cần reCAPTCHA token. Các hành động **đọc** (check, poll, download, load) không cần. Upload ảnh **không cần reCAPTCHA** (đã xác minh).

---

## 2. Hằng số & Khóa API (Constants)

### 2.1. API Keys
| Khóa | Giá trị | Nơi sử dụng |
|---|---|---|
| **Google API Key** | `AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY` | Header `x-goog-api-key` trên `aisandbox-pa`; Query param `key=` cho `/v1/credits` và `/v1/media/` |
| **Recaptcha Site Key** | `6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV` | Query param `k=` cho `/recaptcha/enterprise/reload` và `/clr` |

### 2.2. Custom Headers (x-browser-*)
Các header này BẮT BUỘC cho mọi request đến `aisandbox-pa`, `storage.googleapis.com`, và `google.com/recaptcha`:
```
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=  (hoặc m1p/flp8o...)
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEI...
```

### 2.3. Model Keys

Danh sách đầy đủ các model key quan sát được từ HAR:

#### Video Models (VEO)

| Model Key | Chế độ | Ghi chú |
|---|---|---|
| `veo_2_0_t2v` | T2V | Veo 2.0 Text-to-Video |
| `veo_2_1_fast_d_15_t2v` | T2V | Veo 2.1 Fast |
| `veo_3_0_t2v_fast_portrait_ultra` | T2V | Veo 3 Fast (từ `getVideoModelConfig`) |
| `veo_3_1_t2v_portrait` | T2V | Veo 3.1 Portrait |
| `veo_3_1_t2v_fast_portrait_ultra` | T2V | Veo 3.1 Fast Ultra |
| `veo_3_1_t2v_fast_portrait_ultra_relaxed` | T2V | Veo 3.1 Fast Ultra Relaxed (`relaxed` = hàng đợi ưu tiên thấp, không tốn credit) |
| `veo_3_1_i2v_s_fast_ultra_relaxed` | **I2V** | Start Image Only — **KHÔNG có `_fl_`** |
| `veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed` | **F2V** | Start+End Image — **CÓ `_fl_`** = First+Last |
| `veo_3_1_r2v_fast_portrait_ultra_relaxed` | **R2V** | Reference Images (Ingredients) |
| `veo_3_1_upsampler_1080p` | Upscale | Nâng cấp resolution video |

> **Cách phân biệt I2V vs F2V**: Cùng prefix `i2v_s_` nhưng F2V có suffix `_fl_` (First+Last). Endpoint cũng khác: I2V dùng `StartImage`, F2V dùng `StartAndEndImage`.

#### Image Model

| Model Name | Chế độ | Ghi chú |
|---|---|---|
| `GEM_PIX_2` | T2I / I2I | Google Imagen — **KHÔNG phải VEO**. Dùng cho tạo/biến đổi ảnh |

### 2.4. Aspect Ratios
- `VIDEO_ASPECT_RATIO_LANDSCAPE`
- `VIDEO_ASPECT_RATIO_PORTRAIT`

---

## 3. Endpoint Reference (Tham chiếu Đầy đủ)

### 3.1. Auth & Session

#### `GET /fx/api/auth/session` (labs.google)
Lấy thông tin session hiện tại. **QUAN TRỌNG**: Response chứa `access_token`.
```http
GET /fx/api/auth/session HTTP/1.1
Host: labs.google
Content-Type: application/json
Cookie: (ngầm định bởi trình duyệt)
```
**Response:**
```json
{
  "user": {
    "name": "Shop ultra",
    "email": "sss5540198@tnx.blue-orbita.com",
    "image": "https://lh3.googleusercontent.com/..."
  },
  "expires": "2026-02-06T19:42:31.000Z",
  "access_token": "ya29.a0AUMWg_IRQ_Ul_ZJKho9Bg..."
}
```
> **LƯU Ý**: `access_token` format `ya29.*` = Google OAuth2 token chuẩn (prefix `ya29.` là convention Google dùng để nhận dạng access token). Token này KHÔNG được dùng làm `Authorization: Bearer` header trong bất kỳ request nào quan sát được. Nó được dùng nội bộ bởi Next.js SSR (Server-Side Rendering — Next.js render trang phía server trước khi gửi HTML cho browser).

---

### 3.2. TRPC Endpoints (labs.google/fx/api/trpc)

> **TRPC** (TypeScript Remote Procedure Call) = framework cho phép client gọi server functions như gọi hàm local, tự động serialize/deserialize JSON. Google dùng TRPC cho các thao tác quản lý (project, settings, history) trên `labs.google` — domain **same-origin** với trang web, nên auth chỉ cần Cookies.

**Cơ chế chung**: Mọi TRPC endpoint đều:
- Xác thực bằng **Cookies** (ngầm định qua trình duyệt)
- Content-Type: `application/json`
- GET requests truyền `input` qua query params (URL-encoded JSON)
- POST requests truyền `json` trong body
- Response format: `{"result":{"data":{"json":{...}}}}`

#### 3.2.1. Project Management

| Endpoint | Method | Input | Response |
|---|---|---|---|
| `project.createProject` | POST | `{"projectTitle":"...","toolName":"PINHOLE"}` | `{"projectId":"uuid","projectInfo":{...}}` |
| `project.getProject` | GET | `{"projectId":"uuid","toolName":"PINHOLE"}` | `{"projectId":"...","projectInfo":{...}}` |
| `project.searchProjectScenes` | GET | `{"projectId":"uuid","toolName":"PINHOLE","pageSize":10}` | `{"result":{}}` |
| `project.searchProjectWorkflows` | GET | `{"pageSize":4,"projectId":"uuid","toolName":"PINHOLE",...}` | `{"result":{}}` |

**Mẫu thực tế - createProject:**
```http
POST /fx/api/trpc/project.createProject HTTP/1.1
Host: labs.google
Content-Type: application/json
Origin: https://labs.google
Referer: https://labs.google/fx/tools/flow

{"json":{"projectTitle":"Feb 01 - 02:49","toolName":"PINHOLE"}}
```
**Response:** `{"result":{"data":{"json":{"result":{"projectId":"daba1978-e588-4d76-a4fd-6c3126074187","projectInfo":{"projectTitle":"Feb 01 - 02:49"}},"status":200,"statusText":"OK"}}}}`

#### 3.2.2. Video Settings

| Endpoint | Method | Input | Response |
|---|---|---|---|
| `videoFx.setLastSelectedVideoModelKey` | POST | `{"modelKey":"veo_3_1_t2v_fast_portrait_ultra"}` | Full user settings object |
| `videoFx.setLastSelectedVideoAspectRatio` | POST | `{"videoAspectRatio":"VIDEO_ASPECT_RATIO_PORTRAIT"}` | Full user settings object |
| `videoFx.getUserSettings` | GET | `null` | `{"lastSelectedVideoModelKey":"...","lastSelectedVideoAspectRatio":"...","dismissedBannerIds":[...]}` |
| `videoFx.getVideoModelConfig` | GET | `null` | `{"videoModels":[{"key":"...","displayName":"...","capabilities":[...],...}]}` |
| `videoFx.getFlowAppConfig` | GET | `null` | `{"changeLogId":"...","siteContent":{"banners":[...]}}` |
| `videoFx.listPreambles` | GET | `null` | `{"result":{}}` |

#### 3.2.3. Media & History

| Endpoint | Method | Input | Response |
|---|---|---|---|
| `media.fetchUserHistoryDirectly` | GET | `{"type":"ASSET_MANAGER","pageSize":18,"responseScope":"..."}` | `{"userWorkflows":[...]}` |
| `media.fetchFlowUserIngredients` | GET | `{"type":"All","pageSize":18,"activityType":"ACTIVITY_TYPE_ADD_TO_FLOW_INGREDIENT_DRAWER"}` | `{"result":{}}` |

#### 3.2.4. General / System

| Endpoint | Method | Input | Response |
|---|---|---|---|
| `general.fetchUserPreferences` | GET | `null` | `{"enableHistory":true}` |
| `general.fetchUserLocale` | GET | `null` | `{"languageSetting":"en-GB"}` |
| `general.fetchUserAcknowledgement` | GET | `{"acknowledgementVersion":"FLOW_IMAGE_UPLOAD_TOS"}` | `{"hasAcknowledgement":true}` |
| `general.submitUserAcknowledgement` | POST | `{"acknowledgementVersion":"FLOW_IMAGE_UPLOAD_TOS","frontendCommitHash":"v-release-..."}` | `{"result":{}}` |
| `general.fetchToolAvailability` | GET | `{"tool":"BACKBONE"}` | `{"availabilityState":"AVAILABLE"}` |
| `general.fetchFeatureAvailability` | GET | `{"features":["WHISK_R2I","WHISK_R2I_PHOTOREALISTIC_REFERENCE"]}` | `{"featureAvailability":{"WHISK_R2I":"AVAILABLE",...}}` |
| `general.submitBatchLog` | POST | `{"appEvents":[{"event":"PINHOLE_CREATE_NEW_PROJECT",...}]}` | `{"result":{},"status":200}` |
| `general.reportClientSideError` | POST | `{"message":"..."}` | `null` |

---

### 3.3. REST Endpoints (aisandbox-pa.googleapis.com)

**Cơ chế chung**: Mọi REST endpoint đều:
- Content-Type: `text/plain;charset=UTF-8`
- Headers bắt buộc: `x-browser-channel`, `x-browser-copyright`, `x-browser-validation`, `x-browser-year`, `x-client-data`
- **KHÔNG** có `Authorization: Bearer` header
- **KHÔNG** có `Cookie` header
- Một số endpoint cần `recaptchaContext.token` trong payload
- API Key có thể ở header (`x-goog-api-key`) hoặc query param (`key=`)

#### 3.3.1. Account & Credits

**`GET /v1/credits`** — Kiểm tra credit còn lại
```http
GET /v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY HTTP/1.1
Host: aisandbox-pa.googleapis.com
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEI...
(Không Cookie, Không Authorization)
```
**Response:**
```json
{
  "credits": 45000,
  "userPaygateTier": "PAYGATE_TIER_TWO",
  "sku": "WS_ULTRA",
  "serviceTier": "SERVICE_TIER_ADVANCED"
}
```
> `userPaygateTier` = gói thanh toán của user (TIER_TWO = Ultra, TIER_ONE = Pro). `serviceTier` = cấp dịch vụ backend (ADVANCED = ưu tiên cao). `sku` = mã sản phẩm (WS_ULTRA = Workspace Ultra).

**`POST /v1:checkAppAvailability`** — Kiểm tra app khả dụng
```http
POST /v1:checkAppAvailability HTTP/1.1
Host: aisandbox-pa.googleapis.com
x-goog-api-key: AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY
x-browser-validation: ...

{"clientContext":{"tool":"PINHOLE"}}
```
**Response:** `{"availabilityState": "AVAILABLE"}`

**`POST /v1/whisk:getVideoCreditStatus`** — Credit status cho video
```http
POST /v1/whisk:getVideoCreditStatus HTTP/1.1
Host: aisandbox-pa.googleapis.com
x-browser-validation: ...

{}
```
**Response:**
```json
{
  "credits": 44890,
  "g1MembershipState": "AVAILABLE_CREDITS",
  "isUserAnimateCountryEnabled": true,
  "userPaygateTier": "PAYGATE_TIER_TWO",
  "isGemPix2CreditAvailable": false
}
```

**`POST /v1:fetchUserRecommendations`** — Gợi ý cho user
```http
POST /v1:fetchUserRecommendations HTTP/1.1
Host: aisandbox-pa.googleapis.com
x-browser-validation: ...

{"onramp":["WHISK_UPGRADE_BUTTON","WHISK_MANAGE_AI_CREDITS","WHISK_CREDIT_QUOTA_UPGRADE","WHISK_ANIMATE_TOAST"]}
```
> `onramp` = điểm vào (entry point) cho upsell — Google dùng để hiển thị các nút nâng cấp/mua credit tại các vị trí khác nhau trong UI.
**Response:** `{"recommendation":[{"onramp":"WHISK_UPGRADE_BUTTON","upsellMessage":"Add AI credits",...}]}`

#### 3.3.2. Image Upload & Generation

**`POST /v1:uploadUserImage`** — Upload ảnh (Ingredients)
```http
POST /v1:uploadUserImage HTTP/1.1
Host: aisandbox-pa.googleapis.com
Content-Type: text/plain;charset=UTF-8
x-browser-validation: ...  (Không Cookie, Không Authorization)

{
  "imageInput": {
    "rawImageBytes": "/9j/4AAQSkZ...",
    "mimeType": "image/jpeg",
    "isUserUploaded": true,
    "aspectRatio": "IMAGE_ASPECT_RATIO_..."
  },
  "clientContext": { ... }
}
```
**Response:**
```json
{
  "mediaGenerationId": {"mediaGenerationId": "CAMaJGM3..."},
  "width": 1920,
  "height": 1080
}
```

**`POST /v1/projects/{projectId}/flowMedia:batchGenerateImages`** — Tạo/Biến đổi ảnh (T2I / I2I)
- **Cần `recaptchaContext.token` trong payload**
- **Từ HAR**: Tất cả 10/10 calls đều là **I2I** (có `imageInputs`). **Không có T2I thuần** trong data.

> ⚠️ **Lưu ý HAR**: File `Text to image.har` tên gây hiểu lầm — thực tế bên trong là **I2I** (có `imageInputs` với `IMAGE_INPUT_TYPE_REFERENCE`), KHÔNG phải T2I thuần.

##### So sánh Payload: T2I vs I2I

| Trường | T2I (dự kiến) | I2I (xác minh 10/10 calls) |
|---|:---:|:---:|
| `prompt` | ✅ | ✅ |
| `imageModelName` | `GEM_PIX_2` | `GEM_PIX_2` |
| `imageAspectRatio` | ✅ | ✅ |
| `seed` | ✅ | ✅ |
| **`imageInputs[]`** | **❌ KHÔNG CÓ** | **✅ CÓ** |
| `clientContext.tool` | `PINHOLE` | `PINHOLE` |
| `clientContext.projectId` | ✅ | ✅ |
| `clientContext.userPaygateTier` | ❓ chưa có data | ❌ MISSING (10/10 calls) |
| `clientContext.recaptchaContext` | ✅ | ✅ |

> **Quy tắc nhận dạng**: Có `imageInputs[]` → I2I. Không có → T2I. Cùng endpoint, cùng model `GEM_PIX_2`, cùng response format.

**T2I Request** (dự kiến — chưa có trong HAR, suy từ cấu trúc I2I):
```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1770534060719",
    "projectId": "a89ea3a4-168c-4133-8fb0-7a852f11b33b",
    "tool": "PINHOLE"
  },
  "requests": [{
    "clientContext": { "recaptchaContext": { "token": "SAME_TOKEN" } },
    "seed": 123456,
    "imageModelName": "GEM_PIX_2",
    "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "prompt": "a beautiful sunset over mountains"
    // ⬆️ KHÔNG có imageInputs → T2I thuần
  }]
}
```

**I2I Request** (10 calls / 7 files):
```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA5w_xpJ...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769888782642",
    "projectId": "daba1978-e588-4d76-a4fd-6c3126074187",
    "tool": "PINHOLE"
  },
  "requests": [{
    "clientContext": { ... },
    "seed": 651946,
    "imageModelName": "GEM_PIX_2",
    "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "prompt": "thế giới hiện đại",
    "imageInputs": [{
      "name": "CAMaJDcxZDVl...",
      "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"
    }]
  }]
}
```
> **Nhận dạng I2I**: trường `imageInputs[]` chứa `name` (mediaId ảnh nguồn) + `imageInputType: "IMAGE_INPUT_TYPE_REFERENCE"`. Nếu không có `imageInputs` → T2I.

**I2I Response:**
```json
{
  "media": [{
    "name": "CAMSJGRh...",
    "workflowId": "ab3f1b1a-...",
    "image": {
      "generatedImage": {
        "seed": 651946,
        "mediaGenerationId": "...",
        "mediaVisibility": "PRIVATE",
        "prompt": "modern world",
        "modelNameType": "GEM_PIX_2",
        "fifeUrl": "https://storage.googleapis.com/ai-sandbox-videofx/image/...",
        "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
        "requestData": {
          "promptInputs": [{"textInput": "thế giới hiện đại"}],
          "imageGenerationRequestData": {
            "imageGenerationImageInputs": [{
              "mediaGenerationId": "CAMaJDcxZDVl...",
              "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"
            }]
          }
        }
      },
      "dimensions": {"width": 1376, "height": 768}
    }
  }]
}
```
> `fifeUrl` = FIFE (Fast Image Front End) — hệ thống serving ảnh nội bộ Google. URL signed, dùng để download ảnh kết quả.
> Response trả `prompt` bằng **tiếng Anh** (`"modern world"`) dù request gửi tiếng Việt → server **tự động dịch prompt**.

**`POST /v1/flow/upsampleImage`** — Upscale ảnh (2K/4K)
- **Cần `recaptchaContext.token` trong payload**
```json
{
  "mediaId": "CAMSJGY1...",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_2K",
  "clientContext": {
    "recaptchaContext": {"token": "0cAFcWeA5Clts...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"},
    "sessionId": ";1769880165773",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE"
  }
}
```
**Response:** `{"encodedImage": "/9j/4AAQSkZ..."}` (base64 image trả về trực tiếp)
> `targetResolution`: `UPSAMPLE_IMAGE_RESOLUTION_2K` hoặc `UPSAMPLE_IMAGE_RESOLUTION_4K`

#### 3.3.3. Video Generation — Cấu trúc gói tin đầy đủ theo chế độ

Tất cả các endpoint generate video đều:
- Cần `recaptchaContext.token` trong `clientContext`
- Trả về `operations[]` với `operationId` và `status: MEDIA_GENERATION_STATUS_PENDING`
- Dùng `batchCheckAsyncVideoGenerationStatus` để polling cho đến khi hoàn tất

> 📌 **Bảng so sánh `clientContext` theo chế độ** — các trường gửi khác nhau tùy mode:
>
> | Mode | `projectId` | `tool` | `userPaygateTier` | `recaptchaContext` |
> |---|:---:|:---:|:---:|:---:|
> | T2V | ✅ | `PINHOLE` | ✅ `PAYGATE_TIER_TWO` | ✅ |
> | I2V / F2V / R2V | ✅ | `PINHOLE` | ✅ `PAYGATE_TIER_TWO` | ✅ |
> | I2I | ✅ | `PINHOLE` | ❌ | ✅ |
> | Video Upscale | ❌ | ❌ | ❌ | ✅ (chỉ `sessionId`) |
> | Image Upscale | ✅ | `PINHOLE` | ❌ | ✅ |
> | Upload Image | ❌ | `ASSET_MANAGER` | ❌ | ❌ |

---

##### ① T2V — Text-to-Video (`batchAsyncGenerateVideoText`)

**2 calls / 2 files** — `Text to video 1.har`, `Text to video 2.har`

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA5AInSldiYtuksST3...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1770534060719",
    "projectId": "a89ea3a4-168c-4133-8fb0-7a852f11b33b",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "seed": 12546,
    "textInput": {
      "prompt": "Hook scene [2 SEG], underweight baby. Realistic Vietnamese family scene, cinemat..."
    },
    "videoModelKey": "veo_3_1_t2v_fast_portrait_ultra_relaxed",
    "metadata": {
      "sceneId": "2ab41e06-983f-47cc-b2f8-425c6fc9a6b9"
    }
  }]
}
```
> **Nhận dạng T2V**: chỉ có `textInput.prompt` — **KHÔNG** có `startImage`, `endImage`, hay `referenceImages`. Model key `t2v_*`.

**Response (PENDING → polling):**
```json
{
  "operations": [{
    "operation": {"name": "d3e32c4ec3465c7a39f6e7c002948677"},
    "sceneId": "2ab41e06-983f-47cc-b2f8-425c6fc9a6b9",
    "status": "MEDIA_GENERATION_STATUS_PENDING"
  }],
  "remainingCredits": 45000
}
```
> `remainingCredits: 45000` không đổi = `relaxed` mode **không tốn credit**.

**Response (SUCCESSFUL — sau 11+ lần polling):**
```json
{
  "operations": [{
    "operation": {
      "name": "d3e32c4ec3465c7a39f6e7c002948677",
      "metadata": {
        "@type": "type.googleapis.com/google.internal.labs.aisandbox.v1.Media",
        "name": "CAUSJGE4OWVhM2E0LTE2OGMtNDEzMy04ZmIwLTdhODUyZjExYjMzYho...",
        "video": {
          "seed": 12546,
          "mediaGenerationId": "CAUSJGE4OWVhM2E0...",
          "prompt": "Hook scene [2 SEG], underweight baby...",
          "fifeUrl": "https://storage.googleapis.com/ai-sandbox-videofx/video/010ad9bb-...",
          "mediaVisibility": "PRIVATE",
          "servingBaseUri": "https://storage.googleapis.com/ai-sandbox-videofx/image/010ad9bb-...",
          "model": "veo_3_1_t2v_fast_portrait_ultra_relaxed",
          "isLooped": false,
          "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT"
        }
      }
    },
    "sceneId": "2ab41e06-...",
    "mediaGenerationId": "CAUSJGE4OWVhM2E0...",
    "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL"
  }],
  "remainingCredits": 45000
}
```
> **Response phản hồi đầy đủ**: `fifeUrl` (download video), `servingBaseUri` (thumbnail), `model`, `isLooped`, `seed`.

---

##### ② I2V — Image-to-Video Start Only (`batchAsyncGenerateVideoStartImage`)

**1 call / 1 file** — `tao video vs anh first frame.har`

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA5T6Org6...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769822770783",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "seed": 15456,
    "textInput": {"prompt": "Tạo hiệu ứng intro"},
    "videoModelKey": "veo_3_1_i2v_s_fast_ultra_relaxed",
    "startImage": {"mediaId": "CAMaJDY2NGQ2Y2Vk..."},
    "metadata": {"sceneId": "0dc07a5e-16e5-46e4-a8c1-2a17107d536b"}
  }]
}
```
> **Nhận dạng I2V (Start Only)**: có `startImage.mediaId` + model key `i2v_s_*` **KHÔNG** chứa `_fl_`.

**Response:**
```json
{
  "operations": [{
    "operation": {"name": "0b4c004e3adb478c..."},
    "sceneId": "0dc07a5e-...",
    "status": "MEDIA_GENERATION_STATUS_PENDING"
  }],
  "remainingCredits": 44130
}
```

---

##### ③ F2V — Frames-to-Video Start+End (`batchAsyncGenerateVideoStartAndEndImage`)

**8 calls / 8 files** — phổ biến nhất trong HAR data!

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA6z7psF...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769969107327",
    "projectId": "4fd7fb72-790b-4c3e-8cc1-2bfc3b4245e3",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "seed": 16913,
    "textInput": {"prompt": "Đội quân đến từ tương lai"},
    "videoModelKey": "veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed",
    "startImage": {"mediaId": "CAMaJGM3ZTdk..."},
    "endImage": {"mediaId": "CAMaJDMzODBk..."},
    "metadata": {"sceneId": "a85c142f-561d-48ea-849b-8a3a32e1664b"}
  }]
}
```
> **Nhận dạng F2V**: có **CẢ** `startImage.mediaId` + `endImage.mediaId` + model key chứa `_fl_` (First+Last).
> **Khác I2V**: thêm `endImage`, model key thêm `_fl_`, endpoint khác (`StartAndEndImage` thay vì `StartImage`).

**Response** (giống I2V):
```json
{
  "operations": [{
    "operation": {"name": "cf0c9bf1a56e..."},
    "sceneId": "a85c142f-...",
    "status": "MEDIA_GENERATION_STATUS_PENDING"
  }],
  "remainingCredits": 44990
}
```

---

##### ④ R2V — Reference-to-Video / Ingredients (`batchAsyncGenerateVideoReferenceImages`)

**5 calls / 5 files** — dùng 1-3 ảnh tham khảo

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA57uAL6...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769888782642",
    "projectId": "daba1978-e588-4d76-a4fd-6c3126074187",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "seed": 7393,
    "textInput": {"prompt": "Kết hợp khung cảnh u buồn"},
    "videoModelKey": "veo_3_1_r2v_fast_portrait_ultra_relaxed",
    "referenceImages": [
      {"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": "CAMaJGM3ZTdk..."},
      {"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": "CAMaJDk4NTVm..."},
      {"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": "CAMaJDI0YzU0..."}
    ],
    "metadata": {"sceneId": "1088d16f-b395-44e0-8aa8-be1df603b0a9"}
  }]
}
```
> **Nhận dạng R2V**: trường `referenceImages[]` (1-3 items), mỗi item có `imageUsageType: "IMAGE_USAGE_TYPE_ASSET"` + `mediaId`.
> **Khác I2V/F2V**: KHÔNG có `startImage`/`endImage`, thay bằng `referenceImages[]`. Model key `r2v_*`.

**R2V Response** — phong phú hơn I2V, thêm `workflows[]` và `media[]`:
```json
{
  "operations": [{
    "operation": {"name": "92cea5b7-..."},
    "sceneId": "1088d16f-...",
    "status": "MEDIA_GENERATION_STATUS_PENDING"
  }],
  "remainingCredits": 43930,
  "workflows": [{
    "name": "d9c37290-...",
    "metadata": {
      "createTime": "2026-01-31T20:11:09.517358Z",
      "primaryMediaId": "92cea5b7-...",
      "batchId": "95450273-..."
    },
    "projectId": "daba1978-..."
  }],
  "media": [{
    "name": "92cea5b7-...",
    "workflowId": "d9c37290-...",
    "workflowStepId": "CAE",
    "mediaMetadata": {"mediaStatus": {"mediaGenerationStatus": "MEDIA_GENERATION_STATUS_PENDING"}},
    "sceneId": "1088d16f-..."
  }]
}
```

---

##### Tính năng hỗ trợ: Video Upscale (`batchAsyncGenerateVideoUpsampleVideo`)

> Đây là **tính năng hỗ trợ**, không phải chế độ tạo nội dung. Video tạo ra mặc định 720p — muốn download 1080p/4K phải upscale trước, server mới trả về.

**32 calls / 8 files** — nhiều calls nhất

```json
{
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "resolution": "VIDEO_RESOLUTION_1080P",
    "seed": 18779,
    "videoInput": {"mediaId": "CAUSJDR..."},
    "videoModelKey": "veo_3_1_upsampler_1080p",
    "metadata": {"sceneId": "09f1cc82-..."}
  }],
  "clientContext": {
    "recaptchaContext": {"token": "0cAFcWeA71...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"},
    "sessionId": ";1769969107327"
  }
}
```
> **Nhận dạng**: có `videoInput.mediaId` + `resolution` field. `clientContext` **thu gọn** — chỉ có `sessionId` + reCAPTCHA, **KHÔNG** có `projectId`, `tool`, `userPaygateTier`.

**Response:**
```json
{
  "operations": [{"operation": {"name": "7a014236-..._upsampled"}, "status": "MEDIA_GENERATION_STATUS_PENDING"}],
  "remainingCredits": 44990
}
```

---

##### Bảng tổng hợp — Phân biệt các chế độ tạo nội dung theo trường payload

**Chế độ tạo VIDEO:**

| Trường | T2V | I2V | F2V | R2V |
|---|:---:|:---:|:---:|:---:|
| `textInput.prompt` | ✅ | ✅ | ✅ | ✅ |
| `startImage.mediaId` | ❌ | ✅ | ✅ | ❌ |
| `endImage.mediaId` | ❌ | ❌ | ✅ | ❌ |
| `referenceImages[]` | ❌ | ❌ | ❌ | ✅ |
| Model key prefix | `t2v_` | `i2v_s_` | `i2v_s_*_fl_` | `r2v_` |
| `userPaygateTier` | ✅ | ✅ | ✅ | ✅ |
| HAR calls | 2 | 1 | 8 | 5 |

**Chế độ tạo ẢNH:**

| Trường | T2I | I2I |
|---|:---:|:---:|
| `prompt` | ✅ | ✅ |
| `imageInputs[]` | ❌ | ✅ |
| `imageModelName` | `GEM_PIX_2` | `GEM_PIX_2` |
| `userPaygateTier` | ❓ (chưa có data) | ❌ (MISSING — xác minh 10/10 calls) |
| HAR calls | 0 | 10 |

> ⚠️ **`userPaygateTier` Scope** (verified từ 54 HAR files):
> - **CÓ** trong `clientContext` của: T2V, I2V, F2V, R2V (tất cả video generate endpoints)
> - **KHÔNG CÓ** trong: `batchGenerateImages` (image gen), `batchAsyncGenerateVideoUpsampleVideo` (video upscale), `upsampleImage` (image upscale), `uploadUserImage` (upload)
> - Giá trị: `"PAYGATE_TIER_TWO"` (Ultra), `"PAYGATE_TIER_ONE"` (Pro). Free users có thể là `"PAYGATE_TIER_UNSPECIFIED"` hoặc field absent.
> - **Ý nghĩa**: Server dùng để quyết định model availability và tốc độ xử lý. Python client cần lấy giá trị này từ `GET /v1/credits` response trước khi generate.

**Tính năng hỗ trợ** (không phải chế độ tạo nội dung):

| Tính năng | Endpoint | Mô tả | HAR calls |
|---|---|---|:---:|
| Video Upscale | `batchAsyncGenerateVideoUpsampleVideo` | Nâng cấp video từ 720p → 1080p/4K | 32 |
| Image Upscale | `upsampleImage` | Nâng cấp ảnh lên 2K/4K | 4 |
| Upload Image | `uploadUserImage` | Tải ảnh lên server, nhận `mediaId` để dùng cho I2V/F2V/R2V/I2I | 23 |
| GIF Preview | `generatePinholeGif` | Tạo GIF xem trước từ video | 1 |

**`POST /v1/video:generatePinholeGif`** — Tạo GIF từ video
- **KHÔNG cần `recaptchaContext`**
```http
POST /v1/video:generatePinholeGif HTTP/1.1
Host: aisandbox-pa.googleapis.com
x-browser-validation: ...

{"mediaGenerationId": "CAUSJGY1ZGIx..."}
```
**Response:** `{"encodedGif": "R0lGODlh..."}`

#### 3.3.4. Polling

**`POST /v1/video:batchCheckAsyncVideoGenerationStatus`** — Kiểm tra trạng thái
```http
POST /v1/video:batchCheckAsyncVideoGenerationStatus HTTP/1.1
Host: aisandbox-pa.googleapis.com
x-browser-validation: ...

{
  "operations": [
    {"operation": {"name": "92cea5b7-..."}, "sceneId": "1088d16f-...", "status": "MEDIA_GENERATION_STATUS_PENDING"}
  ]
}
```
**Các trạng thái:** `MEDIA_GENERATION_STATUS_PENDING` → `MEDIA_GENERATION_STATUS_ACTIVE` → `MEDIA_GENERATION_STATUS_SUCCESSFUL`

#### 3.3.5. Media Fetch

**`GET /v1/media/{mediaId}?key=...&clientContext.tool=PINHOLE`** — Lấy media
- API Key trong query params
- Trả về binary hoặc JSON metadata tùy mediaId format

---

### 3.4. Recaptcha Enterprise

> **⚠️ VERIFIED (2026-02-10)** — Các thông tin dưới đây đã được xác minh trực tiếp từ VEO website bằng phương pháp monkey-patching `grecaptcha.enterprise.execute()` trên F12 Console.

#### 3.4.1. Client-side: Lấy Token

VEO sử dụng **reCAPTCHA Enterprise** (KHÔNG phải standard v2/v3). Token được sinh bởi JavaScript trong browser:

```javascript
// Verified exact call — dùng cho TẤT CẢ thao tác VEO (T2V, I2V, R2V, Upscale)
const token = await grecaptcha.enterprise.execute(
    "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV",  // Site Key
    { action: "VIDEO_GENERATION" }                   // Action name — CÙNG cho mọi thao tác
);
```

| Thông số | Giá trị | Ghi chú |
|---|---|---|
| **API** | `grecaptcha.enterprise.execute()` | KHÔNG phải `grecaptcha.execute()` |
| **Site Key** | `6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV` | Hằng số, dùng chung |
| **Action** | `VIDEO_GENERATION` | Cùng cho T2V, I2V, R2V, Upscale 1080p/4K |
| **Script URL** | `https://www.google.com/recaptcha/enterprise.js?render={siteKey}` | Enterprise script |

> 📌 **Action name `VIDEO_GENERATION`** được encode BÊN TRONG token (không gửi riêng trong request body). Server-side verify bằng cách decode token và kiểm tra action có khớp. Sai action → score thấp → 403.

#### 3.4.2. recaptchaContext trong API Request Body

Token được nhúng vào `clientContext.recaptchaContext` với **đúng 2 fields**:

```json
{
    "clientContext": {
        "recaptchaContext": {
            "token": "0cAFcWeA57uAL6OvX4ROdTu2oBZKnkRD8Y54oALk...",
            "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
        }
    }
}
```

> ⚠️ **`applicationType`** là **BẮT BUỘC** — đã xác nhận 100% nhất quán trên 37+ API requests trong 60 HAR files. Thiếu field này có thể gây reject.

#### 3.4.3. Network: `POST /recaptcha/enterprise/reload`
```http
POST /recaptcha/enterprise/reload?k=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV HTTP/1.1
Host: www.google.com
Content-Type: application/x-protobuffer
x-browser-validation: ...

(Binary protobuf payload — opaque blob sinh bởi grecaptcha.enterprise.execute)
```
**Response:** `)]}\'\n["rresp","0cAFcWeA57uAL6..."]`
- Prefix `)]}\'\n` là anti-XSSI prefix
- Phần tử thứ 2 trong mảng JSON là token cần trích xuất
- Token hết hạn sau ~120 giây, chỉ dùng 1 lần

#### 3.4.4. Network: `POST /recaptcha/enterprise/clr` — Clear/Collect (phụ trợ)
- Cùng Site Key, cùng protobuf payload
- Được gọi NGAY SAU mỗi `batchAsync...` submission
- Chức năng: log kết quả reCAPTCHA (telemetry), KHÔNG ảnh hưởng flow chính

#### 3.4.5. Phương pháp Xác minh

Action name được xác minh bằng **monkey-patching** trên F12 Console:

```javascript
// Paste VÀO F12 Console TRƯỚC khi bấm Generate
const _origExecute = grecaptcha.enterprise.execute;
grecaptcha.enterprise.execute = function(...args) {
    console.log('🎯 reCAPTCHA execute called with:', JSON.stringify(args));
    return _origExecute.apply(this, args);
};
```

Kết quả xác minh:
- **Text to Video**: `{action: "VIDEO_GENERATION"}` ✅
- **Upscale 1080p**: `{action: "VIDEO_GENERATION"}` ✅
- **Image to Video**: `{action: "VIDEO_GENERATION"}` ✅ (expected)

> 💡 **Tại sao HAR không tiết lộ action name**: Action name được encode bên trong protobuf binary payload của `enterprise/reload`. HAR chỉ capture binary blob, không thể đọc trực tiếp. JS bundle của VEO cũng bị minified/obfuscated nặng và thường được serve từ browser cache (không capture trong HAR).

---

### 3.5. Download (Signed URL)

**`GET /download/storage/v1/b/{bucket}/o/{object}?...`** — Tải file
```http
GET /download/storage/v1/b/labs-fx-prod-.../o/...
  ?GoogleAccessId=...
  &Expires=1769...
  &Signature=...
Host: storage.googleapis.com
x-browser-validation: ...
(Không Cookie, Không Authorization)
```
- Response: `video/mp4` binary stream
- Auth hoàn toàn qua query params

---

### 3.6. Next.js Data Routes (labs.google)

> Website VEO dùng Next.js — trước khi render trang, browser tải data từ `_next/data/{buildId}/...json`. Những route này **KHÔNG dùng cho Python client** (không chứa data API) nhưng cần biết để phân biệt với API calls trong HAR.

| Route | Query Params | Mục đích |
|---|---|---|
| `/_next/data/{buildId}/en/tools/flow.json` | — | Page data cho Flow tool |
| `/_next/data/{buildId}/en/tools/flow/project/{uuid}.json` | `?projectId=...` | Page data cho project cụ thể |
| `/_next/data/{buildId}/en/library.json` | `?type=...` | Library page data |
| `/_next/data/{buildId}/en/tools/whisk/library.json` | `?catchAll=...` | Whisk library page data |

⚠️ **`{buildId}`** thay đổi mỗi lần Google deploy website mới (ví dụ: `0QTD5IT7rAmrobzxOA4bS`, `9TO92rV5wvlcVlz1O9A9i`). Python client **KHÔNG cần** gọi các route này.

**Headers đặc biệt** (chỉ cho Next.js routes, KHÔNG cho API calls):

| Header | Giá trị | Mục đích |
|---|---|---|
| `x-nextjs-data` | `1` | Đánh dấu request là Next.js data fetch |
| `x-middleware-prefetch` | `1` | Next.js middleware prefetch indicator |

> 💡 2 headers này chỉ xuất hiện cho `_next/data/*.json` routes. Python client **KHÔNG cần** gửi chúng.

---

## 4. Mô hình Giao tiếp (Communication Models)

### 4.1. Mô hình 1: TRPC Thuần túy
**Áp dụng:** Project CRUD, Settings, History, Preferences, System checks
```mermaid
sequenceDiagram
    participant Client
    participant TRPC as labs.google/fx/api/trpc

    Note over Client: 0. Auth Session
    Client->>TRPC: GET /fx/api/auth/session
    TRPC-->>Client: {user, access_token}

    Note over Client, TRPC: 1. App Init
    Client->>TRPC: GET videoFx.getFlowAppConfig
    Client->>TRPC: GET videoFx.getVideoModelConfig
    Client->>TRPC: GET videoFx.getUserSettings
    Client->>TRPC: GET general.fetchUserPreferences
    Client->>TRPC: GET general.fetchUserLocale
    Client->>TRPC: GET general.fetchToolAvailability

    Note over Client, TRPC: 2. Project Management
    Client->>TRPC: POST project.createProject
    TRPC-->>Client: {projectId}
    Client->>TRPC: GET project.getProject
    Client->>TRPC: GET project.searchProjectScenes
    Client->>TRPC: GET project.searchProjectWorkflows

    Note over Client, TRPC: 3. Set Parameters
    Client->>TRPC: POST videoFx.setLastSelectedVideoModelKey
    Client->>TRPC: POST videoFx.setLastSelectedVideoAspectRatio

    Note over Client, TRPC: 4. History
    Client->>TRPC: GET media.fetchUserHistoryDirectly
    Client->>TRPC: GET media.fetchFlowUserIngredients
```

### 4.2. Mô hình 2: Hybrid REST + Recaptcha
**Áp dụng:** Tất cả các thao tác Generate (Video, Ảnh, Upsample)
```mermaid
sequenceDiagram
    participant Client
    participant TRPC as TRPC Server
    participant Recaptcha as Recaptcha Enterprise
    participant REST as aisandbox-pa

    Note over Client: 1. Check Credits & Availability
    Client->>REST: GET /v1/credits?key=...
    REST-->>Client: {credits: 45000, sku: "WS_ULTRA"}
    Client->>REST: POST /v1:checkAppAvailability
    REST-->>Client: {availabilityState: "AVAILABLE"}

    Note over Client: 2. Setup via TRPC
    Client->>TRPC: POST videoFx.setLastSelectedVideoModelKey
    Client->>TRPC: POST videoFx.setLastSelectedVideoAspectRatio

    Note over Client: 3. Upload (nếu có ảnh)
    Client->>REST: POST /v1:uploadUserImage
    REST-->>Client: {mediaGenerationId: "CAM..."}

    Note over Client, Recaptcha: 4. Lấy Recaptcha Token
    Client->>Recaptcha: POST /recaptcha/enterprise/reload?k=6LdsFiUs...
    Note right of Client: Content-Type: application/x-protobuffer
    Note right of Client: Payload: opaque blob từ grecaptcha.enterprise.execute
    Recaptcha-->>Client: ["rresp","0cAFcWeA..."]
    Note right of Client: Trích xuất phần tử thứ 2 làm token

    Note over Client, REST: 5. Generate
    Client->>REST: POST /v1/video:batchAsyncGenerate[Variant]
    Note right of Client: Payload chứa recaptchaContext.token
    REST-->>Client: {operations: [{name: "uuid", status: "PENDING"}]}

    Note over Client, REST: 6. Polling
    loop Every few seconds
        Client->>REST: POST /v1/video:batchCheckAsyncVideoGenerationStatus
        REST-->>Client: {operations: [{status: "ACTIVE|SUCCESSFUL"}]}
    end

    Note over Client, REST: 7. Fetch Result
    Client->>REST: GET /v1/media/{mediaId}?key=...
```

**Các biến thể Generate:**
| Variant | Endpoint | Đặc điểm |
|---|---|---|
| Text-to-Video (T2V) | `batchAsyncGenerateVideoText` | Prompt text only, không ảnh |
| Ingredients (Reference Images) | `batchAsyncGenerateVideoReferenceImages` | Upload ảnh + prompt |
| First Frame | `batchAsyncGenerateVideoStartImage` | Dùng first frame |
| First + Last Frame | `batchAsyncGenerateVideoStartAndEndImage` | Dùng cả 2 frame |
| Upsample Video (1080p/4K) | `batchAsyncGenerateVideoUpsampleVideo` | Nâng cấp resolution, trả `remainingCredits` |
| Image Generation | `/projects/{id}/flowMedia:batchGenerateImages` | Tạo ảnh trong project |
| Image Upsample | `/flow/upsampleImage` | Upscale ảnh 2K, trả `encodedImage` trực tiếp |
| GIF | `generatePinholeGif` | **KHÔNG cần recaptcha**, trả `encodedGif` trực tiếp |

### 4.3. Mô hình 3: Signed URL (Tải xuống)
**Áp dụng:** Tải xuống file Video/Ảnh kết quả
```mermaid
sequenceDiagram
    participant Client
    participant Storage as Google Storage

    Note over Client: 1. Nhận URL từ API trước đó

    Note over Client, Storage: 2. Request Download
    Client->>Storage: GET /download/storage/v1/b/...?GoogleAccessId=...&Signature=...
    Note right of Client: Auth: Query Params
    Storage-->>Client: 200 OK (Binary Stream — video/mp4)
```

---

## 5. Phân tích Mã nguồn (`core/`)

### 5.1. Triển khai (`api_client.py`)
Lớp `VEOApiClient` nhắm mục tiêu `https://aisandbox-pa.googleapis.com` nhưng sử dụng giao thức **khác hoàn toàn** với HAR:
- **Header SAI**: `Authorization: Bearer {access_token}` (không tồn tại trong HAR)
- **Header SAI**: `x-goog-recaptcha-token` (HAR dùng payload `recaptchaContext.token`)
- **THIẾU**: Không xử lý TRPC endpoints
- **THIẾU**: Không có logic lấy Recaptcha token từ SDK

### 5.2. Lỗi Nghiêm trọng trong `ProjectManager`
- **Tệp tin:** `core/project_manager.py`
- **Vấn đề:** Dòng 76 gọi `api_client.create_project(access_token)` — hàm không tồn tại
- **Sửa:** Nên gọi TRPC endpoint `project.createProject`

---

## 6. Bản đồ Quan hệ & So sánh — PHÂN TÍCH SÂU TỪNG THÀNH PHẦN

> **Nguồn dữ liệu**: Toàn bộ file HAR trong `F12 Dev\New\` — 27 thành phần, 721 polls, 72 model keys.

### 6.0. Bảng Tổng quan Trạng thái

| # | Thành phần | Code | HAR | Trạng thái | Deep Analysis |
|---|:---|:---|:---|:---|:---|
| 1 | Giao thức API | REST `/v1/` | TRPC + REST Hybrid | **KHÔNG KHỚP** | §6.1 |
| 2 | Auth Header | `Bearer <token>` | Cookies / API Key | **KHÔNG KHỚP** | §6.2 |
| 3 | Recaptcha Token | `x-goog-recaptcha-token` | `recaptchaContext.token` | **KHÔNG KHỚP** | §6.3 |
| 4 | Recaptcha Site Key | ✗ | `6LdsFiUs...` | **THIẾU** | §6.3 |
| 5 | Recaptcha SDK Payload | ✗ | protobuf blob | **THIẾU** | §6.3 |
| 6 | Recaptcha Response | ✗ | `["rresp","token"]` | **THIẾU** | §6.3 |
| 7 | Recaptcha `clr` | ✗ | `POST /enterprise/clr` | **THIẾU** | §6.3 |
| 8 | Google API Key | ✗ | `AIzaSyBtrm0o5...` | **THIẾU** | §6.4 |
| 9 | x-browser-* Headers | 1/4 | 4/4 suite | **THIẾU 3/4** | §6.5 |
| 10 | `x-client-data` | ✗ | Bắt buộc | **THIẾU** | §6.5 |
| 11 | Auth Session | ✗ | `auth/session` | **THIẾU** | §6.6 |
| 12 | Credits Check | ✗ | `GET /v1/credits` | **THIẾU** | §6.7 |
| 13 | App Availability | ✗ | `checkAppAvailability` | **THIẾU** | §6.8 |
| 14 | Video Upsample | ✗ | `UpsampleVideo` | **THIẾU** | §6.9 |
| 15 | Image Generation | ✗ | `batchGenerateImages` | **THIẾU** | §6.10 |
| 16 | Image Upsample | ✗ | `upsampleImage` | **THIẾU** | §6.11 |
| 17 | GIF Generation | ✗ | `generatePinholeGif` | **THIẾU** | §6.12 |
| 18 | Start Frame Video | ✗ | `StartImage` | **THIẾU** | §6.13 |
| 19 | Start+End Frame Video | ✗ | `StartAndEndImage` | **THIẾU** | §6.14 |
| 20 | User Recommendations | ✗ | `fetchUserRecommendations` | **THIẾU** | §6.15 |
| 21 | Video Credit Status | ✗ | `getVideoCreditStatus` | **THIẾU** | §6.16 |
| 22 | Model Config | ✗ | `getVideoModelConfig` | **THIẾU** | §6.17 |
| 23 | User Settings | ✗ | `getUserSettings` | **THIẾU** | §6.18 |
| 24 | Flow App Config | ✗ | `getFlowAppConfig` | **THIẾU** | §6.19 |
| 25 | Polling State Machine | ✗ | 721 polls 3 trạng thái | **THIẾU** | §6.20 |
| 26 | Browser Validation | `x-browser-validation` | `x-browser-validation` | **KHỚP** | §6.5 |
| 27 | Download | ✗ | Signed URL | **THIẾU** | §6.21 |

---

### 6.1. Giao thức API — KHÔNG KHỚP

**Code hiện tại**: Chỉ dùng REST endpoints trực tiếp đến `aisandbox-pa.googleapis.com`
**HAR thực tế**: Kiến trúc Hybrid — TRPC (quản lý) + REST (generate) + Auth riêng

```mermaid
graph TD
    A[Client] -->|Cookies + JSON| B[TRPC: labs.google/fx/api/trpc]
    A -->|x-browser-* ± API Key| C[REST: aisandbox-pa.googleapis.com]
    A -->|Cookies| D[Auth: labs.google/fx/api/auth/session]
    A -->|Signed URL| E[Download: storage.googleapis.com]
    A -->|Site Key + Protobuf| F[Recaptcha: google.com/recaptcha/enterprise]
    
    B -->|Project, Settings, History| B1[16 endpoints]
    C -->|Generate, Upload, Poll| C1[13 endpoints]
    F -->|Token| C
```

**Quan hệ**: TRPC quản lý session/project → REST thực thi generate → Recaptcha bảo vệ REST → Storage phục vụ download.

---

### 6.2. Auth Header — KHÔNG KHỚP

**Code**: `Authorization: Bearer {access_token}`
**HAR**: Không bao giờ xuất hiện `Authorization` header

| Domain | Auth Method | Header có | Header không có |
|---|---|---|---|
| `labs.google` (TRPC) | Cookies ngầm định | `content-type: application/json` | `Authorization`, `x-goog-api-key` |
| `aisandbox-pa` (REST) | x-browser-* bắt buộc ± API Key (chỉ GET + checkApp) | `x-browser-*` × 4, `x-client-data`; `x-goog-api-key` chỉ GET/checkApp | `Authorization`, `Cookie` |
| `storage.googleapis.com` | Signed URL params | `x-browser-*` × 4, `x-client-data` | `Authorization`, `Cookie` |

**Mẫu thực tế TRPC headers** (từ `videoFx.getUserSettings`):
```
:authority: labs.google
:method: GET
content-type: application/json
sec-fetch-site: same-origin
(Cookie tự động gửi bởi browser — không xuất hiện trong HAR headers)
```

**Mẫu thực tế REST headers** (từ `uploadUserImage`):
```
:authority: aisandbox-pa.googleapis.com
content-type: text/plain;charset=UTF-8
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE=
```

---

### 6.3. Recaptcha Enterprise — KHÔNG KHỚP + THIẾU 4 thành phần

**Code**: Dùng `x-goog-recaptcha-token` header (SAI)
**HAR**: Token nằm trong payload `recaptchaContext.token`

#### 6.3.1. Flow Recaptcha hoàn chỉnh

```mermaid
sequenceDiagram
    participant JS as grecaptcha SDK
    participant Reload as /enterprise/reload
    participant CLR as /enterprise/clr
    participant REST as aisandbox-pa

    Note over JS: 1. SDK gọi grecaptcha.enterprise.execute
    JS->>JS: Tạo protobuf blob (opaque)
    
    Note over JS, Reload: 2. Gửi protobuf để lấy token
    JS->>Reload: POST /reload?k=6LdsFiUsAAAAAI...
    Note right of JS: Content-Type: application/x-protobuffer
    Note right of JS: Gồm x-browser-* headers
    Reload-->>JS: )]}'\n["rresp","0cAFcWeA57uAL6..."]
    Note over JS: 3. Parse: loại bỏ )]}'\ prefix, JSON.parse, lấy [1]
    
    Note over JS, CLR: 4. Telemetry (phụ trợ, song song)
    JS->>CLR: POST /clr?k=6LdsFiUsAAAAAI...
    Note right of JS: Content-Type: (không có)
    Note right of JS: sec-fetch-mode: no-cors
    CLR-->>JS: 200 OK (application/binary)
    
    Note over JS, REST: 5. Dùng token trong payload
    JS->>REST: POST /v1/video:batchAsync...
    Note right of JS: {"clientContext":{"recaptchaContext":{"token":"0cAFcWeA57u...","applicationType":"RECAPTCHA_APPLICATION_TYPE_WEB"}}}
```

#### 6.3.2. Recaptcha `reload` — Full Request/Response

**Request** (từ `01. ingedients to video hoan thanh 4 video prompt 3 anh.har`):
```
POST /recaptcha/enterprise/reload?k=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV
Host: www.google.com
Content-Type: application/x-protobuffer
Origin: https://www.google.com
Referer: https://www.google.com/recaptcha/enterprise/anchor?ar=1&k=6LdsFiUs...
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE=

Payload: Binary protobuf (bắt đầu bằng \x18N67nZn4AqZkNcb...)
```

**Response** (HTTP 200, `application/json`):
```
)]}'
["rresp","0cAFcWeA57uAL6OvX4ROdTu2oBZK...(~1500 chars)...",null,120,null,null,null,
["bgdata","","LyogQW50aS1zcGFtLi..."]]
```

**Trích xuất token**: `response.split("\n")[1]` → `JSON.parse(...)` → `result[1]` = `"0cAFcWeA57uAL6..."`

#### 6.3.3. Recaptcha `clr` — Full Request

```
POST /recaptcha/enterprise/clr?k=6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV
Host: www.google.com
Origin: https://labs.google
Referer: https://labs.google/
sec-fetch-mode: no-cors   ← Khác với reload (cors)
sec-fetch-site: cross-site

Payload: Binary protobuf (bắt đầu bằng \x28 + site key)
Response: 200 OK, application/binary (rỗng)
```

**Khác biệt `reload` vs `clr`**:
| Thuộc tính | `reload` | `clr` |
|---|---|---|
| Origin | `https://www.google.com` | `https://labs.google` |
| Referer | `/recaptcha/enterprise/anchor?...` | `https://labs.google/` |
| sec-fetch-mode | `cors` | `no-cors` |
| Response | JSON `["rresp","token"]` | Binary rỗng |
| Mục đích | Lấy token | Telemetry/Clear |

#### 6.3.4. Cách dùng token trong payload

Token được đóng gói trong `clientContext.recaptchaContext`:
```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA57uAL6OvX4ROdTu2oBZKnkRD8Y54o...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769888782642",
    "projectId": "daba1978-e588-4d76-a4fd-6c3126074187",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  }
}
```

#### 6.3.5. Phân bổ reCAPTCHA Token theo Endpoint — Dữ liệu định lượng (54 HAR files)

**Tổng quan**: 66 lần `reload` (lấy token) → 62 lần dùng token trong payload = tỷ lệ gần **1:1** (thừa 4 reload = browser preload/retry)

##### Endpoints CẦN reCAPTCHA token (7 endpoints / 62 calls)

| # | Endpoint | Loại | Calls | % |
|---|---|---|:---:|:---:|
| 1 | `batchAsyncGenerateVideoUpsampleVideo` | Video Upscale | 32 | 51.6% |
| 2 | `batchGenerateImages` | Image Gen (I2I/T2I) | 10 | 16.1% |
| 3 | `batchAsyncGenerateVideoStartAndEndImage` | F2V | 8 | 12.9% |
| 4 | `batchAsyncGenerateVideoReferenceImages` | R2V | 5 | 8.1% |
| 5 | `upsampleImage` | Image Upscale | 4 | 6.5% |
| 6 | `batchAsyncGenerateVideoText` | T2V | 2 | 3.2% |
| 7 | `batchAsyncGenerateVideoStartImage` | I2V | 1 | 1.6% |

##### Endpoints KHÔNG CẦN reCAPTCHA token

| Endpoint | Loại | Lý do |
|---|---|---|
| `batchCheckAsyncVideoGenerationStatus` | Polling | Chỉ kiểm tra trạng thái, không tạo nội dung |
| `uploadUserImage` | Upload | Upload ảnh nguồn, chưa generate |
| `generatePinholeGif` | GIF Preview | Utility — chuyển đổi format, không tạo mới |
| `fetchUserRecommendations` | Recommendations | Đọc dữ liệu, không tạo nội dung |
| `getVideoCreditStatus` | Credit check | Đọc trạng thái credit |
| `checkAppAvailability` | App check | Kiểm tra khả dụng |
| `GET /v1/credits` | Credit check | Đọc credit (REST GET) |
| `GET /v1/media/{id}` | Media fetch | Đọc metadata |

> 📌 **QUY TẮC VÀNG**: Chỉ các hành động **tạo/biến đổi nội dung** (generate video, generate ảnh, upscale) mới cần reCAPTCHA. Mọi hành động **đọc** (check, poll, download, fetch) đều **KHÔNG cần**.
>
> 📌 **MỖI lần generate = 1 token MỚI**: Token là **vé vào cửa 1 lần dùng** — lấy từ `/reload`, nhúng vào payload, server xác thực, xong thì bỏ. Không tái sử dụng.

```mermaid
graph LR
    SDK[grecaptcha SDK] --> Reload[POST /reload]
    Reload --> Token[reCAPTCHA Token]
    Token --> Gen{Generate Endpoint}
    Gen --> VidGen[Video: T2V/I2V/F2V/R2V]
    Gen --> ImgGen[Image: T2I/I2I]
    Gen --> Upscale[Upscale: Video/Image]
    
    style Token fill:#ff9,stroke:#f90
    style Gen fill:#9cf,stroke:#39f
```

**Endpoints cần Recaptcha**: Tất cả generate/upscale endpoints NGOẠI TRỪ `generatePinholeGif`, `uploadUserImage`, polling, và các REST GET.

#### 6.3.6. Sơ đồ End-to-End: WebClient ↔ reCAPTCHA ↔ VEO API Server

> Sơ đồ tổng hợp toàn bộ luồng từ lúc user nhấn Generate đến lúc nhận kết quả, tách rõ 3 bên tham gia:

```mermaid
sequenceDiagram
    participant WC as 🖥️ WebClient
    participant RC as 🛡️ reCAPTCHA Server<br/>(www.google.com)
    participant API as ⚡ VEO API Server<br/>(aisandbox-pa)
    participant ST as 📦 Storage<br/>(storage.googleapis)

    Note over WC: User nhấn Generate

    rect rgb(255, 245, 230)
    Note over WC, RC: PHASE 1 — Lấy reCAPTCHA Token
    WC->>WC: grecaptcha.enterprise.execute()<br/>→ tạo protobuf blob (opaque)
    WC->>RC: POST /enterprise/reload?k=6LdsFiUs...<br/>Content-Type: application/x-protobuffer<br/>+ x-browser-* headers
    RC-->>WC: )]}'\n["rresp","0cAFcWeA..."]<br/>(anti-XSSI prefix + JSON)
    WC->>WC: Parse: bỏ prefix → JSON.parse → [1]<br/>→ token = "0cAFcWeA..."
    WC->>RC: POST /enterprise/clr?k=6LdsFiUs...<br/>(telemetry, song song, no-cors)
    RC-->>WC: 200 OK (binary rỗng)
    end

    rect rgb(230, 245, 255)
    Note over WC, API: PHASE 2 — Submit Generate Request
    WC->>API: POST /v1/video:batchAsync[Variant]<br/>Headers: x-browser-* (5 headers)<br/>Body: {clientContext: {recaptchaContext: {token}, sessionId, projectId, tool}, requests: [...]}
    Note right of WC: Token nhúng trong payload body<br/>KHÔNG phải header
    API-->>WC: {operations: [{name: "opId", status: "PENDING"}],<br/>remainingCredits: 44990}
    end

    rect rgb(230, 255, 230)
    Note over WC, API: PHASE 3 — Polling (KHÔNG cần reCAPTCHA)
    loop Mỗi ~6 giây
        WC->>API: POST /v1/video:batchCheckAsyncVideoGenerationStatus<br/>Headers: x-browser-* (5 headers)<br/>Body: {operations: [{name: "opId", status: "PENDING"}]}
        API-->>WC: {operations: [{status: "ACTIVE"}]}
    end
    API-->>WC: {operations: [{status: "SUCCESSFUL",<br/>metadata: {video: {fifeUrl, servingBaseUri, model, isLooped}}}],<br/>remainingCredits: 44990}
    end

    rect rgb(245, 230, 255)
    Note over WC, ST: PHASE 4 — Download Kết quả
    WC->>ST: GET /download/storage/v1/b/.../o/...?<br/>GoogleAccessId=...&Signature=...<br/>Headers: x-browser-* (5 headers)
    ST-->>WC: 200 OK (video/mp4 binary stream)
    end

    Note over WC: ✅ Hoàn tất — Video/Ảnh sẵn sàng
```

> **Lưu ý theo loại nội dung**:
> - **Video** (T2V/I2V/F2V/R2V/Upscale): Async — Phase 1 → 2 → 3 (polling) → 4 (download)
> - **Ảnh** (T2I/I2I): Sync — Phase 1 → 2 → kết quả trả **ngay** trong response (có `fifeUrl`) → 4
> - **Image Upscale**: Sync — Phase 1 → 2 → trả `encodedImage` base64 ngay, **không cần Phase 3-4**

---

### 6.4. Google API Key — THIẾU

**Giá trị**: `AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY`

**2 cách sử dụng**:
| Cách | Endpoint mẫu | Vị trí |
|---|---|---|
| **Header** | `checkAppAvailability` | `x-goog-api-key: AIzaSyBtrm0o5...` |
| **Query Param** | `/v1/credits`, `/v1/media/{id}` | `?key=AIzaSyBtrm0o5...` |

**Lưu ý**: Không phải mọi REST endpoint đều cần API Key. Ví dụ `uploadUserImage`, `batchAsyncGenerate*` KHÔNG có `x-goog-api-key`.

---

### 6.5. Custom Headers — Phân tích Cấu trúc & Hoạt động (1310+ requests / 54 HAR files)

**Full header suite** bắt buộc cho mọi request đến `aisandbox-pa`, `storage`, `recaptcha` — **KHÔNG BAO GIỜ** gửi cho `labs.google` (TRPC):

```
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE=
```

#### A. Phân loại 5 headers theo tính chất

##### 3 Headers TĨNH (hardcoded trong Chrome binary)

| Header | Giá trị | Đổi khi | Xác minh |
|---|---|---|---|
| `x-browser-channel` | `stable` | Dùng Chrome beta/canary | 1310/1310 giống nhau |
| `x-browser-copyright` | `Copyright 2026 Google LLC. All Rights reserved.` | Chrome update year | 1310/1310 giống nhau |
| `x-browser-year` | `2026` | Chrome update year | 1310/1310 giống nhau |

> Nhúng trong Chrome binary lúc build, **KHÔNG compute at runtime**. Có thể hardcode an toàn cho cùng phiên bản Chrome.

##### 2 Headers ĐỘNG (sinh mỗi browser session)

**`x-browser-validation`** — Browser fingerprint hash:

| Giá trị | Decoded | Requests | Files | Thời gian |
|---|---|---|---|---|
| `WVxyJFF0uIgXSTejJocZmmZTO+I=` | 20 bytes (SHA1?) `595c7224...` | 720 | 27 | Jan 31 PM → Feb 6 |
| `m1p/flp8o0rsqq649T7rsY5vgtE=` | 20 bytes (SHA1?) `9b5a7f7e...` | 590 | 19 | Jan 30 → Jan 31 AM |

- **Cấu trúc**: Base64 encode của 20 bytes = khớp kích thước SHA1 output
- **Session binding**: **KHÔNG ĐỔI** trong cùng 1 HAR file (50/50 files ✅ CONSTANT)
- **Đổi khi**: Khởi động lại Chrome (giá trị B → A sau browser restart)
- **Nguồn gốc (suy luận)**: SHA1 hash từ tổ hợp browser fingerprint data (version, platform, extensions, etc.)

**`x-client-data`** — Chrome Variations protobuf:

| Giá trị | Decoded | Requests | Files |
|---|---|---|---|
| `CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE=` | 35 bytes `...96a1cb...d9aacf01` | 628 | 23 |
| `CI+2yQEIo7bJAQipncoBCM7aygEIkqHLAQiFoM0BCNmqzwE=` | 35 bytes `...92a1cb...d9aacf01` | 590 | 19 |
| `CI+2yQEIo7bJAQipncoBCM7aygEIkqHLAQiFoM0B` | 30 bytes `...92a1cb...a0cd01` | 92 | 4 |

- **Cấu trúc**: Base64 encode của protobuf binary — Chrome Variations experiment flags
- **3 variants** khác nhau ở byte thứ 20-21 (field 6: `96a1cb` vs `92a1cb`) và có/không field 7 (`d9aacf01`)
- **Ý nghĩa**: Google Chrome A/B test flags — **KHÔNG liên quan đến xác thực**, nhưng server nhận và ghi log
- **Session binding**: KHÔNG ĐỔI trong cùng 1 HAR file (50/50 files ✅ CONSTANT)
- **Tài liệu**: Google public spec — [Chrome Variations](https://chromium.googlesource.com/chromium/src/+/HEAD/components/variations/)

#### B. Luồng Client → Server

```
┌─────────────────────────────────────────┐         ┌──────────────────────────────┐
│            CHROME BROWSER                │         │     aisandbox-pa /           │
│                                          │         │     storage / recaptcha      │
│  ┌──────────────────────────────────┐    │         │                              │
│  │ Chrome binary (build-time):      │    │  HTTP   │                              │
│  │   channel = "stable"             │────┼────────→│  Server nhận 5 headers       │
│  │   copyright = "Copyright 2026…"  │    │  cross- │                              │
│  │   year = "2026"                  │    │  site   │  Validate? (xem mục C)       │
│  ├──────────────────────────────────┤    │         │                              │
│  │ Session init (browser start):    │    │         │  sec-fetch-site: cross-site   │
│  │   validation = SHA1?(fingerprint)│────┼────────→│  → Cookies KHÔNG gửi         │
│  │   client_data = Variations proto │    │         │  → Auth chỉ qua headers +    │
│  └──────────────────────────────────┘    │         │    API Key (nếu có) +         │
│                                          │         │    reCAPTCHA (nếu gen)        │
│  ⚠️ TRPC (labs.google) = same-origin    │         │                              │
│     → KHÔNG gửi x-browser-*             │         │  Response: 200 OK            │
│     → Dùng Cookies thay thế             │         │  (chưa quan sát được reject) │
└─────────────────────────────────────────┘         └──────────────────────────────┘
```

**Phân bố theo domain** (1310 requests):

| Domain | Requests | % | Headers | Ghi chú |
|---|---|---|---|---|
| REST (`aisandbox-pa`) | 1183 | 90.3% | 5/5 luôn đầy đủ | Bulk traffic: poll, gen, upload |
| RECAPTCHA (`google.com`) | 123 | 9.4% | 5/5 luôn đầy đủ | reload + clr |
| STORAGE (`storage.googleapis.com`) | 4 | 0.3% | 5/5 luôn đầy đủ | Video download |
| TRPC (`labs.google`) | 0 | 0% | 0/5 — KHÔNG BAO GIỜ | Same-origin = dùng Cookies |

#### C. Điểm chưa rõ (hạn chế phương pháp HAR)

| Câu hỏi | Tình trạng | Chi tiết |
|---|---|---|
| Server reject thế nào nếu thiếu header? | ❌ Chưa biết | 50 files × 1310 requests = tất cả hợp lệ, chưa thấy reject |
| `x-browser-validation` sinh chính xác từ đâu? | ⚠️ Suy luận | 20 bytes = SHA1. Không đổi trong session → hash từ static browser data |
| Có thể fake `validation` bằng giá trị cũ? | ⚠️ Chưa thực nghiệm | Giá trị A dùng liên tục 6 ngày (Jan 31 → Feb 6) → có thể tái sử dụng |
| `x-client-data` ảnh hưởng kết quả không? | ⚠️ Không chắc | Là experiment flags — có thể ảnh hưởng A/B test server-side |
| Headers có hết hạn không? | ⚠️ Chưa rõ | `validation` A dùng 6 ngày liên tục → ít nhất không hết hạn nhanh |

> **Khuyến nghị implementation**: Hardcode 3 headers tĩnh + capture 2 headers động từ browser session thực. `x-browser-validation` tồn tại ít nhất 6 ngày, nên capture 1 lần rồi tái sử dụng cho nhiều requests.

**Code chỉ có** `x-browser-validation` → cần bổ sung 3 header tĩnh + `x-client-data`.

#### D. Headers khác (Next.js — KHÔNG dành cho API calls)

| Header | Giá trị | Chỉ xuất hiện ở | Python client |
|---|---|---|---|
| `x-nextjs-data` | `1` | `_next/data/*.json` routes | ❌ KHÔNG CẦN |
| `x-middleware-prefetch` | `1` | `_next/data/*.json` routes | ❌ KHÔNG CẦN |

> 💡 2 headers này do Next.js framework tự thêm khi prefetch page data. Chúng **KHÔNG BAO GIỜ** xuất hiện trong API calls đến `aisandbox-pa`, `storage`, hay `recaptcha`. Python client bỏ qua hoàn toàn.

---

### 6.6. Auth Session — THIẾU

**Full Request** (từ `Check Ultra.har`):
```
GET /fx/api/auth/session HTTP/1.1
Host: labs.google
Content-Type: application/json
Referer: https://labs.google/fx/tools/flow/project/368870ec-...
sec-fetch-site: same-origin
(Cookie tự động — NOT cross-site)
```

**Full Response**:
```json
{
  "user": {
    "name": "Shop ultra",
    "email": "sss5540198@tnx.blue-orbita.com",
    "image": "https://lh3.googleusercontent.com/a/ACg8ocLrkVVTrR6SxDIHFBzjxO6XrRMohYEslFT9zr1yOFi5eITNIA=s96-c"
  },
  "expires": "2026-02-06T19:42:31.000Z",
  "access_token": "ya29.a0AUMWg_IRQ_Ul_ZJKho9BgrfRRX9VFP6dpBX7DiPHW7hBVhZgzI16inTueug9MkSFKwtEFnv55p1arxO0kZn3_MAigTaS4Mrx7PnmPpBPfSSsEU1vvl6Lngb8VBvOjoKnKfIctCZaRF-RbcKe0d7AYmu-bTQx5NmXca_Gi9bKWVFjrGC3hMR9PuOo622iKysoKeccUEXDV0zDGktMtfyHUeVjtfaGQ1H-RL_2c3xm_xxB3avGWVh9e1IdkTkmDxJ9iqrHtGIUMg2nISeI-HNMgM2C2OWWAN9EGGfugjyzLqJ9qeFA-gmB9XCxjVQIF_ajDYe39Kv1F2TNT3KoeTdNEDwMKKiR70ms1N1Iol1sfAaCgYKAcgSARcSFQHGX2MiwmKtSl4ngqTJC70opGHRMQ0369"
}
```

**Quan hệ**: `access_token` format `ya29.` = Google OAuth2 token. Tuy nhiên trong HAR, token này KHÔNG được dùng trong bất kỳ `Authorization` header nào. Nó được dùng nội bộ bởi Next.js SSR.

**`expires`**: Token hết hạn sau ~1 ngày. Client cần refresh session định kỳ.

#### 6.6.1. access_token Lifecycle — Từ đâu ra, tại sao không dùng

```mermaid
sequenceDiagram
    participant User as 👤 User
    participant Browser as 🖥️ Chrome Browser
    participant Google as 🔐 Google OAuth
    participant Labs as 🌐 labs.google (Next.js)
    participant API as ⚡ aisandbox-pa

    Note over User, Google: PHASE A — Đăng nhập Google (1 lần)
    User->>Browser: Truy cập labs.google, đăng nhập Google
    Browser->>Google: OAuth2 Authorization Flow
    Google-->>Browser: Set cookies: __Secure-next-auth.session-token=...
    Note over Browser: Cookies lưu trong browser, tự gửi cho labs.google

    Note over Browser, Labs: PHASE B — Lấy access_token (mỗi session)
    Browser->>Labs: GET /fx/api/auth/session (+ cookies auto)
    Labs-->>Browser: {user, expires, access_token: "ya29.*"}
    Note over Labs: Next.js SSR dùng access_token NỘI BỘ
    Note over Labs: để gọi Google APIs phía server

    Note over Browser, API: PHASE C — Gọi API (KHÔNG dùng access_token)
    Browser->>Labs: TRPC calls (cookies auto, same-origin)
    Browser->>API: REST calls (x-browser-* headers, cross-site)
    Note over Browser, API: ⚠️ KHÔNG BAO GIỜ gửi Authorization: Bearer ya29.*
```

> **Tại sao `access_token` có nhưng KHÔNG DÙNG?**
>
> | Câu hỏi | Trả lời |
> |---|---|
> | Token từ đâu? | Google OAuth2 login → cookies → `auth/session` endpoint trả về |
> | Ai dùng? | **Next.js SSR** (server-side rendering) dùng nội bộ để fetch data phía server |
> | Client có dùng? | ❌ **KHÔNG** — 0/3027+ requests có `Authorization` header |
> | Tại sao client không cần? | same-origin (TRPC) = cookies đủ rồi; cross-site (REST) = Custom Headers + reCAPTCHA thay thế |
> | Token hết hạn? | ~24h (`expires` field), browser tự refresh qua cookies |
> | Nếu code dùng Bearer? | **SAI** — server sẽ reject vì không đúng auth flow |

#### 6.6.2. Sơ đồ Quan hệ Tổng thể — 5 Phương thức Xác thực

> Sơ đồ thể hiện nguồn gốc, mối liên kết, và phạm vi áp dụng của tất cả phương thức xác thực:

```mermaid
graph TB
    subgraph ORIGIN["🔐 NGUỒN GỐC"]
        Login["Google OAuth Login"]
        Chrome["Chrome Browser Binary"]
        GSDK["grecaptcha SDK"]
        GServer["Google API Server"]
    end

    subgraph AUTH_METHODS["🛡️ 5 PHƯƠNG THỨC XÁC THỰC"]
        Cookies["1️⃣ Browser Cookies<br/>__Secure-next-auth.session-token"]
        APIKey["2️⃣ API Key<br/>AIzaSyBtrm0o5ab1c..."]
        Headers["3️⃣ Custom Headers (5)<br/>x-browser-channel, copyright,<br/>year, validation, x-client-data"]
        Token["4️⃣ reCAPTCHA Token<br/>0cAFcWeA... (1 lần dùng)"]
        SignedURL["5️⃣ Signed URL<br/>?GoogleAccessId=...&Signature=..."]
    end

    subgraph ENDPOINTS["📡 ENDPOINT TYPES"]
        TRPC["TRPC<br/>(labs.google)<br/>same-origin"]
        RESTGET["REST GET<br/>(aisandbox-pa)<br/>cross-site"]
        RESTGEN["REST POST gen<br/>(aisandbox-pa)<br/>cross-site"]
        RESTPOLL["REST POST poll<br/>(aisandbox-pa)<br/>cross-site"]
        STORAGE["STORAGE<br/>(storage.googleapis)<br/>cross-site"]
    end

    Login --> Cookies
    Chrome --> Headers
    GSDK --> Token
    GServer --> SignedURL
    GServer --> APIKey

    Cookies -->|"auto (same-origin)"| TRPC
    Headers -->|"bắt buộc"| RESTGET
    Headers -->|"bắt buộc"| RESTGEN
    Headers -->|"bắt buộc"| RESTPOLL
    Headers -->|"bắt buộc"| STORAGE
    APIKey -->|"URL query ?key="| RESTGET
    Token -->|"payload body"| RESTGEN
    SignedURL -->|"URL params"| STORAGE

    style Cookies fill:#4CAF50,color:#fff
    style Headers fill:#2196F3,color:#fff
    style Token fill:#FF9800,color:#fff
    style APIKey fill:#9C27B0,color:#fff
    style SignedURL fill:#607D8B,color:#fff
    style TRPC fill:#E8F5E9
    style RESTGEN fill:#FFF3E0
```

> **Đọc sơ đồ**:
> - **Hàng trên** = nguồn gốc (đâu sinh ra phương thức)
> - **Hàng giữa** = 5 phương thức xác thực
> - **Hàng dưới** = endpoint types
> - **Mũi tên** = phương thức nào dùng cho endpoint nào
> - TRPC chỉ cần Cookies (xanh lá). REST gen cần Headers (xanh dương) + reCAPTCHA (cam). REST GET cần Headers + API Key (tím).

#### 6.6.3. HTTP Request Templates — Cấu trúc Gửi Chính xác cho Mỗi Loại

> Mẫu request HOÀN CHỈNH (headers + body) client gửi đến server cho mỗi loại endpoint:

##### ① TRPC (same-origin → Cookies only)

```http
POST /fx/api/trpc/project.createProject HTTP/1.1
Host: labs.google
Content-Type: application/json
Origin: https://labs.google
Referer: https://labs.google/fx/tools/flow
sec-fetch-site: same-origin
sec-fetch-mode: cors
Cookie: __Secure-next-auth.session-token=... (TỰ ĐỘNG, không thấy trong HAR)

{"json":{"projectTitle":"Feb 08","toolName":"PINHOLE"}}
```
> **Auth**: Chỉ Cookies (browser tự gửi). **Không có** x-browser-*, API Key, hay reCAPTCHA.

##### ② REST GET (cross-site → Custom Headers + API Key)

```http
GET /v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY HTTP/1.1
Host: aisandbox-pa.googleapis.com
sec-fetch-site: cross-site
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEI...
(KHÔNG Cookie, KHÔNG Authorization)
```
> **Auth**: Custom Headers (5) + API Key trong URL query. **Không có** Cookie, Authorization, reCAPTCHA.

##### ③ REST POST Generate (cross-site → Custom Headers + reCAPTCHA payload)

```http
POST /v1/video:batchAsyncGenerateVideoText HTTP/1.1
Host: aisandbox-pa.googleapis.com
Content-Type: text/plain;charset=UTF-8
sec-fetch-site: cross-site
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEI...
(KHÔNG Cookie, KHÔNG Authorization, KHÔNG x-goog-api-key)

{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA4mxC9Bkr...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1770534060719",
    "projectId": "a89ea3a4-...",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [{ ... }]
}
```
> **Auth**: Custom Headers (5) + reCAPTCHA token **trong body** (không phải header). **Không có** Cookie, Authorization, hay API Key.

##### ④ REST POST Polling (cross-site → Custom Headers only)

```http
POST /v1/video:batchCheckAsyncVideoGenerationStatus HTTP/1.1
Host: aisandbox-pa.googleapis.com
Content-Type: text/plain;charset=UTF-8
sec-fetch-site: cross-site
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEI...
(KHÔNG Cookie, KHÔNG Authorization, KHÔNG API Key, KHÔNG reCAPTCHA)

{
  "operations": [{
    "operation": {"name": "d3e32c4ec346..."},
    "sceneId": "2ab41e06-...",
    "status": "MEDIA_GENERATION_STATUS_PENDING"
  }]
}
```
> **Auth**: Chỉ Custom Headers (5). **Không cần** reCAPTCHA, API Key, hay Cookie.

##### ⑤ REST POST checkApp (cross-site → Custom Headers + API Key header)

```http
POST /v1:checkAppAvailability HTTP/1.1
Host: aisandbox-pa.googleapis.com
Content-Type: text/plain;charset=UTF-8
x-goog-api-key: AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEI...

{"clientContext":{"tool":"PINHOLE"}}
```
> **Auth**: Custom Headers (5) + API Key **trong header** (`x-goog-api-key`). Endpoint **duy nhất** dùng API Key ở header.

##### ⑥ STORAGE Download (cross-site → Custom Headers + Signed URL)

```http
GET /download/storage/v1/b/labs-fx-prod-.../o/...
  ?GoogleAccessId=labs-fx-prod@...iam.gserviceaccount.com
  &Expires=1769845118
  &Signature=kLJ9qX2... HTTP/1.1
Host: storage.googleapis.com
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEI...
(KHÔNG Cookie, KHÔNG Authorization)
```
> **Auth**: Custom Headers (5) + Signed URL params (GoogleAccessId, Expires, Signature). URL tự chứa auth, hết hạn ~24h.

##### Bảng tóm tắt — Auth per Template

| # | Template | Cookies | API Key | Custom Headers | reCAPTCHA | Signed URL |
|---|---|:---:|:---:|:---:|:---:|:---:|
| ① | TRPC | ✅ auto | ❌ | ❌ | ❌ | ❌ |
| ② | REST GET | ❌ | ✅ query | ✅ 5/5 | ❌ | ❌ |
| ③ | REST POST gen | ❌ | ❌ | ✅ 5/5 | ✅ payload | ❌ |
| ④ | REST POST poll | ❌ | ❌ | ✅ 5/5 | ❌ | ❌ |
| ⑤ | REST POST check | ❌ | ✅ header | ✅ 5/5 | ❌ | ❌ |
| ⑥ | STORAGE | ❌ | ❌ | ✅ 5/5 | ❌ | ✅ |

---

### 6.7. Credits Check — THIẾU

**Full Request** (từ `Check Ultra.har`):
```
GET /v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY HTTP/1.1
Host: aisandbox-pa.googleapis.com
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEIkqHLAQiFoM0B
(Không Cookie, Không Authorization, Không x-goog-api-key header)
```

**Full Response**:
```json
{
  "credits": 45000,
  "userPaygateTier": "PAYGATE_TIER_TWO",
  "sku": "WS_ULTRA",
  "serviceTier": "SERVICE_TIER_ADVANCED"
}
```

**Quan hệ với các thành phần khác**:
- `credits` giảm sau mỗi generate thành công (ví dụ: 45000 → 44990 → 44930 → ...)
- `userPaygateTier` = `PAYGATE_TIER_TWO` cho Ultra subscribers, ảnh hưởng đến model access
- `sku` = `WS_ULTRA` xác định gói subscription
- Endpoint `getVideoCreditStatus` (§6.16) cung cấp thông tin tương tự nhưng thêm `g1MembershipState`

**Đặc biệt**: Auth chỉ qua query param `key=`, không cần header `x-goog-api-key`.

---

### 6.8. App Availability — THIẾU

**Full Request** (từ `Check trạng thái tài khoản.har`):
```
POST /v1:checkAppAvailability HTTP/1.1
Host: aisandbox-pa.googleapis.com
Content-Type: text/plain;charset=UTF-8
x-goog-api-key: AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY  ← API Key ở HEADER
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: WVxyJFF0uIgXSTejJocZmmZTO+I=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE=

{"clientContext":{"tool":"PINHOLE"}}
```

**Full Response**: `{"availabilityState": "AVAILABLE"}`

**Quan hệ**: Được gọi trước mọi generate flow. Nếu `AVAILABLE` → tiếp tục. Nếu khác → block UI.

---

### 6.9. Video Upsample — THIẾU

**Full Request** (từ `916 frame to video Upscale 1080.har`):
```json
{
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "resolution": "VIDEO_RESOLUTION_1080P",
    "seed": 18779,
    "videoInput": {
      "mediaId": "CAUSJDRmZDdmYjcyLTc5MGItNGMzZS04Y2MxLTJiZmMzYjQyNDVlMxokNWFiNzk4YzEtNTA4MS00MWVkLWJlMGEtZjNhNDYxNzRkNWFlIgNDQUUqJDdhMDE0MjM2LWQ0YmEtNDQ4Yi04ZDVlLTMxNWRiMGZhZDQwNw"
    },
    "videoModelKey": "veo_3_1_upsampler_1080p",
    "metadata": {"sceneId": "09f1cc82-6925-41fd-860f-4e264abcc886"}
  }],
  "clientContext": {
    "recaptchaContext": {"token": "0cAFcWeA71jcH...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"},
    "sessionId": ";1769969107327"
  }
}
```

**Full Response**:
```json
{
  "operations": [{
    "operation": {"name": "7a014236-d4ba-448b-8d5e-315db0fad407_upsampled"},
    "sceneId": "09f1cc82-6925-41fd-860f-4e264abcc886",
    "status": "MEDIA_GENERATION_STATUS_PENDING"
  }],
  "remainingCredits": 44990,
  "workflows": [{"metadata": {"createTime": "2026-02-01T23:23:14.782856Z", "primaryMediaId": "7a014236..._upsampled"}}],
  "media": [{"name": "7a014236..._upsampled", "workflowStepId": "CAE", "mediaMetadata": {"mediaStatus": {"mediaGenerationStatus": "MEDIA_GENERATION_STATUS_PENDING"}}}]
}
```

**Đặc biệt**:
- Operation ID gốc + `_upsampled` suffix
- `videoModelKey` = `veo_3_1_upsampler_1080p` (model riêng cho upscale)
- `resolution` field chỉ có trong Upsample, không có trong generate bình thường
- `clientContext` KHÔNG chứa `projectId` hay `tool` (khác với các generate khác)
- Có `workflows` và `media` trong response (metadata đầy đủ hơn generate thường)

---

### 6.10. Image Generation — THIẾU

**Full Request** (từ `Full tạo ảnh.har`):

URL: `POST /v1/projects/{projectId}/flowMedia:batchGenerateImages`
- ProjectId nằm trong **URL path**, không phải payload

**Payload quan trọng**: `clientContext` xuất hiện 2 lần — cả ở root level VÀ trong mỗi request item:
```json
{
  "clientContext": {
    "recaptchaContext": {"token": "0cAFcWeA5w_xpJ...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"},
    "sessionId": ";1769888782642",
    "projectId": "daba1978-e588-4d76-a4fd-6c3126074187",
    "tool": "PINHOLE"
  },
  "requests": [{
    "clientContext": { "recaptchaContext": {"token": "SAME_TOKEN"} },
    ...
  }]
}
```

**Response** — trả kết quả ngay (KHÔNG async):
```json
{
  "media": [{
    "name": "CAMSJGRh...",
    "workflowId": "ab3f1b1a-...",
    "image": {
      "generatedImage": {
        "seed": 651946,
        "mediaVisibility": "PRIVATE",
        "prompt": "modern world",
        "modelNameType": "GEM_PIX_2",
        "fifeUrl": "https://storage.googleapis.com/ai-sandbox-videofx/image/...?GoogleAccessId=...&Signature=...",
        "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
        "requestData": {
          "promptInputs": [{"textInput": "thế giới hiện đại"}],
          "imageGenerationRequestData": {
            "imageGenerationImageInputs": [{"mediaGenerationId": "CAMaJDcx...", "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"}]
          }
        }
      },
      "dimensions": {"width": 1376, "height": 768}
    }
  }]
}
```

**Đặc biệt**: `modelNameType: "GEM_PIX_2"` — dùng model ảnh Gemini Pix 2, KHÁC với video models.

---

### 6.11. Image Upsample — THIẾU

**Full Payload** (từ `Download anh 2k.har`):
```json
{
  "mediaId": "CAMSJGY1ZGIxMzQy...",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_2K",
  "clientContext": {
    "recaptchaContext": {"token": "0cAFcWeA5CltsPcE...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"}
  }
}
```

**Response**: `{"encodedImage": "[base64 ~4.3MB]"}` — Trả ảnh trực tiếp (KHÔNG async).

**Quan hệ**: `mediaId` prefix `CAMS` = ảnh đã generate. Prefix `CAUS` = video. Prefix `CAM` = uploaded.

---

### 6.12. GIF Generation — THIẾU

**Full Payload** (từ `Download gif 4 vid.har`):
```json
{"mediaGenerationId": "CAUSJGY1ZGIxMzQy..."}
```

**Response**: `{"encodedGif": "[base64 ~11MB]"}` — Trả GIF trực tiếp.

**Đặc biệt quan trọng**:
- **KHÔNG CẦN recaptchaContext** — endpoint duy nhất không cần Recaptcha
- **KHÔNG CẦN projectId, sessionId, tool**
- Payload cực kỳ đơn giản, chỉ cần `mediaGenerationId`
- `mediaGenerationId` prefix `CAUS` = video source

---

### 6.13. Start Frame Video — THIẾU

**Full Payload** (từ `tao video vs anh first frame.har`):
```json
{
  "clientContext": {
    "recaptchaContext": {"token": "0cAFcWeA5T6Org6...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"},
    "sessionId": ";1769822770783",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "seed": 15456,
    "textInput": {"prompt": "Tạo hiệu ứng intro"},
    "videoModelKey": "veo_3_1_i2v_s_fast_ultra_relaxed",
    "startImage": {"mediaId": "CAMaJDY2NGQ2Y2Vk..."},
    "metadata": {"sceneId": "0dc07a5e-..."}
  }]
}
```

**Response**: `{"operations": [...], "remainingCredits": 44130}`

**Model key pattern**: `veo_3_1_i2v_s_fast_ultra_relaxed` — `i2v_s` = Image to Video Start frame.

---

### 6.14. Start+End Frame Video — THIẾU

**Full Payload** (từ `916 frame to video submit - done.har`):
```json
{
  "clientContext": {
    "recaptchaContext": {"token": "0cAFcWeA6z7psF_...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"},
    "sessionId": ";1769969107327",
    "projectId": "4fd7fb72-790b-4c3e-8cc1-2bfc3b4245e3",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "seed": 16913,
    "textInput": {"prompt": "Đội quân đến từ tương lai"},
    "videoModelKey": "veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed",
    "startImage": {"mediaId": "CAMaJGM3ZTdkODY4..."},
    "endImage": {"mediaId": "CAMaJDMzODBkZTVj..."},
    "metadata": {"sceneId": "a85c142f-..."}
  }]
}
```

**Response**: Tương tự §6.13: `{"operations": [...], "remainingCredits": 44990}`

**Model key pattern**: `veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed` — `fl` = First+Last, khác với `i2v_s` (chỉ Start).

---

### 6.15. User Recommendations — THIẾU

**Full Payload** (từ `Check Ultra.har`):
```json
{"onramp": ["WHISK_UPGRADE_BUTTON", "WHISK_MANAGE_AI_CREDITS", "WHISK_CREDIT_QUOTA_UPGRADE", "WHISK_ANIMATE_TOAST"]}
```

**Full Response**:
```json
{
  "recommendation": [
    {"onramp": "WHISK_UPGRADE_BUTTON", "upsellMessage": "Add AI credits", "recommendationUri": "https://support.google.com/a/users?p=gws_ai_ultra_credits&ms=pt:1061;s:966;vp:9"},
    {"onramp": "WHISK_MANAGE_AI_CREDITS", "recommendationUri": "https://support.google.com/a/users?p=gws_ai_ultra_credits&ms=pt:1061;s:965;vp:9"},
    {"onramp": "WHISK_CREDIT_QUOTA_UPGRADE", "upsellMessage": "Manage subscription", "recommendationUri": "...", "description": "Your monthly quota will automatically refresh at the end of the month."},
    {"onramp": "WHISK_ANIMATE_TOAST", "upsellMessage": "Add AI credits", "description": "Add AI credits for higher Animate limits"}
  ]
}
```

**Quan hệ**: Endpoint marketing — hiển thị upsell buttons dựa trên subscription tier.

---

### 6.16. Video Credit Status — THIẾU

**Payload**: `{}`  (rỗng)

**Full Response** (từ `whisk 2.har`):
```json
{
  "credits": 44890,
  "g1MembershipState": "AVAILABLE_CREDITS",
  "isUserAnimateCountryEnabled": true,
  "userPaygateTier": "PAYGATE_TIER_TWO",
  "isGemPix2CreditAvailable": false
}
```

**So sánh với `/v1/credits`**:
| Field | `/v1/credits` | `getVideoCreditStatus` |
|---|---|---|
| credits | ✓ | ✓ |
| userPaygateTier | ✓ | ✓ |
| sku | ✓ (`WS_ULTRA`) | ✗ |
| serviceTier | ✓ (`SERVICE_TIER_ADVANCED`) | ✗ |
| g1MembershipState | ✗ | ✓ (`AVAILABLE_CREDITS`) |
| isUserAnimateCountryEnabled | ✗ | ✓ |
| isGemPix2CreditAvailable | ✗ | ✓ |

---

### 6.17. Model Config — THIẾU (30+ models)

**Full Response** (từ `0. Tao Project.har`, 467 dòng):

Danh sách **đầy đủ** tất cả model keys từ `videoFx.getVideoModelConfig`:

| # | Model Key | Display Name | Capabilities | Aspect | Cost | Status |
|---|---|---|---|---|---|---|
| 1 | `veo_3_0_t2v_fast_portrait_ultra` | Veo 3 - Fast | TEXT, AUDIO | Portrait | — | **DEPRECATED** |
| 2 | `veo_3_1_t2v_fast_portrait_ultra` | Veo 3.1 - Fast | TEXT, AUDIO | Portrait | 10 | Active |
| 3 | `veo_3_1_t2v_fast_portrait_ultra_relaxed` | Veo 3.1 - Fast [Lower Priority] | TEXT, AUDIO | Portrait | — | Active |
| 4 | `veo_3_0_t2v_fast_ultra` | Veo 3 - Fast | TEXT, AUDIO | Landscape | — | **DEPRECATED** |
| 5 | `veo_3_1_t2v_fast` | Veo 3.1 - Fast | TEXT, AUDIO | Landscape | 10 | **DEPRECATED** |
| 6 | `veo_3_1_t2v_fast_ultra` | Veo 3.1 - Fast | TEXT, AUDIO | Landscape | 10 | Active |
| 7 | `veo_3_1_t2v_fast_ultra_relaxed` | Veo 3.1 - Fast [Lower Priority] | TEXT, AUDIO | Landscape | — | Active |
| 8 | `veo_3_0_t2v_fast` | Veo 3 - Fast | TEXT, AUDIO | Landscape | 20 | **DEPRECATED** |
| 9 | `veo_3_1_r2v_fast_landscape_ultra` | Veo 3.1 - Fast | MULTI_REF_NO_STYLE, AUDIO | Landscape | 10 | Active |
| 10 | `veo_3_1_r2v_fast_landscape_ultra_relaxed` | Veo 3.1 - Fast [Lower Priority] | MULTI_REF_NO_STYLE, AUDIO | Landscape | — | Active |
| 11 | `veo_3_1_r2v_fast_portrait_ultra` | Veo 3.1 - Fast | MULTI_REF_NO_STYLE, AUDIO | Portrait | 10 | Active |
| 12 | `veo_3_1_r2v_fast_portrait_ultra_relaxed` | Veo 3.1 - Fast [Lower Priority] | MULTI_REF_NO_STYLE, AUDIO | Portrait | — | Active |
| 13 | `veo_3_1_i2v_s_fast_portrait_ultra` | Veo 3.1 - Fast | START_IMAGE, AUDIO | Portrait | 10 | Active |
| 14 | `veo_3_1_i2v_s_fast_portrait_ultra_relaxed` | Veo 3.1 - Fast [Lower Priority] | START_IMAGE, AUDIO | Portrait | — | Active |
| 15 | `veo_3_i2v_s_fast_portrait_ultra` | Veo 3 - Fast | START_IMAGE, AUDIO | Portrait | — | **DEPRECATED** |
| 16 | `veo_3_1_i2v_s_fast_ultra` | Veo 3.1 - Fast | START_IMAGE, AUDIO | Landscape | 10 | Active |
| 17 | `veo_3_1_i2v_s_fast_ultra_relaxed` | Veo 3.1 - Fast [Lower Priority] | START_IMAGE, AUDIO | Landscape | — | Active |

**Model Key Naming Convention**:
```
veo_{version}_{type}_{speed}_{aspect?}_{quality?}_{priority?}
  │       │        │         │          │            │
  │       │        │         │          │            └── relaxed = lower priority queue
  │       │        │         │          └── ultra = highest quality
  │       │        │         └── portrait/landscape (hoặc không)
  │       │        └── fast = nhanh, (không) = chậm hơn chất lượng cao
  │       └── t2v = Text to Video
  │           r2v = Reference (Ingredients) to Video  
  │           i2v_s = Image (Start) to Video
  │           i2v_s_..._fl = Image (Start+Last/First+Last) to Video
  │           upsampler_1080p / upsampler_4k
  └── 3_0 / 3_1 / 2_0 / 2_1
```

**Capability mapping**:
| Capability | Mô tả | Model types |
|---|---|---|
| `VIDEO_MODEL_CAPABILITY_TEXT` | Nhận text prompt | t2v models |
| `VIDEO_MODEL_CAPABILITY_AUDIO` | Tạo audio kèm video | Tất cả Veo 3.x |
| `VIDEO_MODEL_CAPABILITY_MULTI_REFERENCE_NO_STYLE` | Nhận nhiều ảnh reference | r2v models |
| `VIDEO_MODEL_CAPABILITY_START_IMAGE` | Nhận ảnh first frame | i2v_s models |

**Metadata thêm cho r2v models**:
```json
{
  "beyondModelName": "models/veo-3.1-creative-generate-002;backend_beyond",
  "maxImageInputs": 3
}
```

---

### 6.18. User Settings — THIẾU

**Full Response** (từ `0. Tao Project.har`):
```json
{
  "result": {
    "lastSelectedVideoModelKey": "veo_2_0_t2v",
    "lastAcknowledgedChangeLogId": "2025-12-18-v0-e2054626-1ac3-4d64-81ec-3134a94549a4",
    "dismissedBannerIds": [
      "e40fc7a7-aea8-4ec7-8250-89c5d266c177",
      "8dbcafbe-bd31-4de1-b9f8-b64d06015b2c",
      "d7011273-f85f-4da5-829a-8feadef78fa7",
      "94d90f50-4ec6-4e73-8c42-d3e709105da7",
      "cd266941-aba8-484c-b74f-64f8f39a49f6",
      "165ea8a4-91d4-4011-b46a-f522b1fd310c"
    ],
    "lastSelectedVideoAspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE"
  }
}
```

**Quan hệ**: `lastSelectedVideoModelKey` và `lastSelectedVideoAspectRatio` được update bởi `videoFx.setLastSelected*` trước mỗi generate.

---

### 6.19. Flow App Config — THIẾU

**Full Response** (từ `Check trạng thái tài khoản.har`):
```json
{
  "result": {
    "changeLogId": "2025-12-18-v0-e2054626-1ac3-4d64-81ec-3134a94549a4",
    "siteContent": {
      "banners": [
        {"id": "e40fc7a7-...", "headline": "Nano Banana Pro Has Arrived!", "ctaClickBehavior": "CTA_CLICK_BEHAVIOR_OPEN_URL"},
        {"id": "8dbcafbe-...", "headline": "Explore projects from Flow experts", "ctaClickBehavior": "CTA_CLICK_BEHAVIOR_SETUP_STARTER_PROJECTS"},
        {"id": "d7011273-...", "headline": "Veo 3.1 + New Controls"},
        {"id": "94d90f50-...", "headline": "Find your inspiration on Flow TV", "ctaUri": "https://labs.google/flow/tv"}
      ]
    },
    "isFreeTierEnabled": true,
    "isFlowImageEnabled": true,
    "isGemPixProEnabled": true,
    "isObjectRemovalEnabled": true,
    "imageUpsamplerMinTimeSeconds": "1765560600",
    "isFlowUpsamplingEnabled": true
  }
}
```

**Feature Flags quan trọng**: `isFreeTierEnabled`, `isFlowImageEnabled`, `isFlowUpsamplingEnabled` — ảnh hưởng đến khả năng sử dụng feature.

---

### 6.20. Polling State Machine — THIẾU (721 polls phân tích)

**Máy trạng thái hoàn chỉnh** (từ 721 polls qua tất cả HAR files):

```mermaid
stateDiagram-v2
    [*] --> PENDING: Generate Response
    PENDING --> ACTIVE: Poll 1 (ngay lập tức)
    ACTIVE --> ACTIVE: Polls tiếp theo (~5s mỗi poll)
    ACTIVE --> SUCCESSFUL: Hoàn thành 1 operation
    SUCCESSFUL --> SUCCESSFUL: Tất cả operations xong
    SUCCESSFUL --> [*]: remainingCredits xuất hiện

    note right of PENDING: Trạng thái từ generate response
    note right of ACTIVE: Đang xử lý trên server
    note right of SUCCESSFUL: Có signed URL trong response
```

**3 trạng thái**:
| Trạng thái | Mô tả | Response keys |
|---|---|---|
| `MEDIA_GENERATION_STATUS_PENDING` | Chỉ trong generate response, KHÔNG BAO GIỜ trong poll | `operations` |
| `MEDIA_GENERATION_STATUS_ACTIVE` | Đang xử lý | `operations` chỉ |
| `MEDIA_GENERATION_STATUS_SUCCESSFUL` | Hoàn thành | `operations` + `remainingCredits` khi TẤT CẢ xong |

**Quy tắc chuyển trạng thái** (từ 721 polls thực tế):
1. Poll đầu tiên: `PENDING` → `ACTIVE` (ngay lập tức)
2. Trong quá trình xử lý: Mix `ACTIVE` + `SUCCESSFUL` (từng operation xong dần)
3. Poll cuối: Tất cả `SUCCESSFUL` → response thêm `remainingCredits`

**Thống kê thực tế**:
| Scenario | Số polls trung bình | Thời gian ước tính |
|---|---|---|
| Video generate (4 videos) | ~10-12 polls | ~50-60 giây |
| Video upscale 1080p | ~35 polls | ~175 giây |
| Video upscale 4K | ~250+ polls | ~20+ phút |
| Frame to Video (Start+End) | ~10-15 polls | ~50-75 giây |

**Payload polling REQUEST** — gửi lại toàn bộ operations array:
```json
{
  "operations": [
    {"operation": {"name": "92cea5b7-..."}, "sceneId": "1088d16f-...", "status": "MEDIA_GENERATION_STATUS_PENDING"},
    {"operation": {"name": "d9607a25-..."}, "sceneId": "5a9dc801-...", "status": "MEDIA_GENERATION_STATUS_PENDING"}
  ]
}
```

**Polling RESPONSE — 3 dạng** (verified từ HAR):

Dạng 1: **ACTIVE** (đang xử lý)
```json
{
  "operations": [
    {"operation": {"name": "d3e32c4e..."}, "sceneId": "2ab41e06-...", "status": "MEDIA_GENERATION_STATUS_ACTIVE"}
  ]
}
```

Dạng 2: **Mix ACTIVE + SUCCESSFUL** (từng video xong dần)
```json
{
  "operations": [
    {"operation": {"name": "d3e32c4e..."}, "sceneId": "2ab41e06-...", "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
     "servingBaseUri": "https://storage.googleapis.com/ai-sandbox-videofx/video/{uuid}?GoogleAccessId=...&Expires=...&Signature=...",
     "mediaGenerationId": "CAUSJGFy..."},
    {"operation": {"name": "a1b2c3d4..."}, "sceneId": "5a9dc801-...", "status": "MEDIA_GENERATION_STATUS_ACTIVE"}
  ]
}
```
> ⚠️ `servingBaseUri` = **Signed URL** cho download. Chỉ xuất hiện khi operation `SUCCESSFUL`.
> `mediaGenerationId` = ID để fetch metadata qua `GET /v1/media/{id}`.

Dạng 3: **TẤT CẢ SUCCESSFUL** (poll cuối cùng)
```json
{
  "operations": [
    {"operation": {"name": "d3e32c4e..."}, "sceneId": "2ab41e06-...", "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
     "servingBaseUri": "https://storage.googleapis.com/...", "mediaGenerationId": "CAUSJGFy..."},
    {"operation": {"name": "a1b2c3d4..."}, "sceneId": "5a9dc801-...", "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
     "servingBaseUri": "https://storage.googleapis.com/...", "mediaGenerationId": "CAUSJDRm..."}
  ],
  "remainingCredits": 44890
}
```
> 💡 `remainingCredits` chỉ xuất hiện khi **TẤT CẢ** operations đều `SUCCESSFUL`. Python client dùng field này để cập nhật credit counter.

---

### 6.21. Download — THIẾU

**2 loại download**:

#### Video Download (Signed URL):
```
GET /ai-sandbox-videofx/video/{uuid}
  ?GoogleAccessId=labs-ai-sandbox-videoserver-prod@system.gserviceaccount.com
  &Expires=1769845118
  &Signature=stveZ3u3QZ5i4OTN...
Host: storage.googleapis.com
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: m1p/flp8o0rsqq649T7rsY5vgtE=
x-browser-year: 2026
x-client-data: CI+2yQEIo7bJAQipncoBCM7aygEIkqHLAQiFoM0BCNmqzwE=
Origin: https://labs.google
Referer: https://labs.google/
```
**Response**: `200 OK`, `Content-Type: video/mp4`, binary stream

#### Image Download (fifeUrl trong generate response):
URL format: `https://storage.googleapis.com/ai-sandbox-videofx/image/{uuid}?GoogleAccessId=...&Signature=...`
- Nhận trực tiếp từ `flowMedia:batchGenerateImages` response (`fifeUrl` field)

**Signed URL Components**:
| Parameter | Mô tả | Mẫu |
|---|---|---|
| `GoogleAccessId` | Service Account | `labs-ai-sandbox-videoserver-prod@system.gserviceaccount.com` |
| `Expires` | Unix timestamp | `1769845118` (~24h từ lúc tạo) |
| `Signature` | HMAC signature | URL-encoded base64 |

---

### 6.22. Phân tích Hệ thống Chống Spam — 3 Lớp Bảo vệ

> Website VEO (labs.google) sử dụng **3 lớp chống spam song song** để ngăn chặn bot và lạm dụng API:

#### 6.22.1. Lớp 1: reCAPTCHA Enterprise v3 (Chính)

| Thuộc tính | Giá trị |
|---|---|
| **Loại** | reCAPTCHA Enterprise **v3** — score-based, **invisible** (vô hình) |
| **Site Key** | `6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV` |
| **Cơ chế** | Google SDK chạy nền, phân tích hành vi user (chuột, keyboard, thời gian) → cho điểm 0.0-1.0 |
| **Token** | Gửi trong `clientContext.recaptchaContext.token` (payload body, KHÔNG phải header) |
| **Phạm vi** | 7 endpoints tạo/biến đổi nội dung (generate + upscale) |
| **Quy tắc** | 1 token = 1 lần dùng. Mỗi generate cần token mới |
| **Thống kê** | 66 reload / 62 gen calls = tỷ lệ 1:1 (thừa 4 = preload/retry) |

> ⚠️ reCAPTCHA v3 **KHÔNG BAO GIỜ** hiện challenge (hình ảnh, checkbox) cho user. Hoàn toàn invisible — chạy ngầm và cho điểm. Nếu điểm thấp (nghi bot), server **reject request** thay vì hiện challenge.

#### 6.22.2. Lớp 2: Browser Fingerprint Headers (Phụ trợ)

| Header | Vai trò | Tính chất |
|---|---|---|
| `x-browser-channel` | Kênh Chrome (`stable`) | Tĩnh (build-time) |
| `x-browser-copyright` | Copyright string | Tĩnh (build-time) |
| `x-browser-year` | Năm (`2026`) | Tĩnh (build-time) |
| `x-browser-validation` | **SHA1 fingerprint** từ browser | Động — đổi mỗi lần restart Chrome |
| `x-client-data` | Chrome Variations protobuf | Động — A/B test flags |

- **Mục đích**: Chứng minh request đến từ **Chrome thật**, chặn bot dùng `curl`/`requests`
- **Phạm vi**: MỌI request cross-site (REST, Storage, reCAPTCHA) — 1310+ requests xác minh
- **Binding**: `x-browser-validation` CỐ ĐỊNH trong cùng session (50/50 HAR files ✅ CONSTANT)

#### 6.22.3. Lớp 3: Credit System (Rate Limiting Kinh tế)

| Thuộc tính | Giá trị |
|---|---|
| **Cơ chế** | `remainingCredits` giảm sau mỗi generate (trả về trong response) |
| **Tiers** | `PAYGATE_TIER_TWO` (paid, 45000 credits) vs free |
| **Tracking** | Server theo dõi balance, reject khi hết credit |
| **Endpoint** | `GET /v1/credits` kiểm tra số dư |

#### 6.22.4. Bảng So sánh 3 Lớp

| Lớp | Cơ chế | Chặn gì | Bypass khó? | Thiếu → hậu quả |
|---|---|---|:---:|---|
| **reCAPTCHA v3** | Score-based token | Bot, script tự động | ⭐⭐⭐ Rất khó | Request bị **reject** ngay |
| **Browser Headers** | Chrome fingerprint | Non-Chrome clients | ⭐⭐ Trung bình | Request bị **reject** |
| **Credits** | Quota kinh tế | Spam volume | ⭐ Dễ (mua credits) | Hết credits → **block generate** |

```mermaid
graph TD
    Request["📤 Client Request"] --> L1{"🛡️ Lớp 1: Browser Headers"}
    L1 -->|"Có 5 headers hợp lệ"| L2{"🤖 Lớp 2: reCAPTCHA v3"}
    L1 -->|"Thiếu/sai headers"| Reject1["❌ REJECT"]
    L2 -->|"Token hợp lệ, score cao"| L3{"💰 Lớp 3: Credits"}
    L2 -->|"Token thiếu/hết hạn/score thấp"| Reject2["❌ REJECT"]
    L3 -->|"Còn credits"| Success["✅ GENERATE"]
    L3 -->|"Hết credits"| Reject3["❌ REJECT"]

    style L1 fill:#2196F3,color:#fff
    style L2 fill:#FF9800,color:#fff
    style L3 fill:#4CAF50,color:#fff
    style Success fill:#8BC34A,color:#fff
    style Reject1 fill:#f44336,color:#fff
    style Reject2 fill:#f44336,color:#fff
    style Reject3 fill:#f44336,color:#fff
```

---

### 6.23. Chiến lược Bypass cho Python Client — Kiến trúc kỹ thuật

> **Nguyên tắc**: KHÔNG THỂ bypass bằng `requests` library thuần. **PHẢI** dùng browser automation (Playwright) để lấy auth data, rồi gửi requests.

#### 6.23.1. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────┐
│              PYTHON CLIENT ARCHITECTURE                  │
│                                                          │
│  ┌──────────────────────┐    ┌───────────────────────┐  │
│  │  Playwright Browser  │    │   Python httpx/       │  │
│  │  (Chrome thật)       │    │   requests            │  │
│  │                      │    │                       │  │
│  │  1. Login Google     │    │  4. Gửi REST requests │  │
│  │  2. Capture headers  │───>│     + captured headers│  │
│  │  3. Get reCAPTCHA    │───>│     + fresh token     │  │
│  │     token mỗi lần    │    │  5. Polling           │  │
│  └──────────────────────┘    │  6. Download          │  │
│         Browser giữ mở       └───────────────────────┘  │
│         suốt session                                     │
└─────────────────────────────────────────────────────────┘
```

> ⚠️ **Browser Playwright PHẢI giữ mở** suốt session — vì nó là nguồn duy nhất để lấy reCAPTCHA token mới. Không thể đóng browser rồi gửi request bằng Python thuần.

#### 6.23.2. Bypass Lớp 1: Cookies — Persistent Chrome Profile

```python
from playwright.async_api import async_playwright

async def init_browser():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch_persistent_context(
        user_data_dir="./chrome_profile",  # Lưu cookies vĩnh viễn
        headless=False  # Lần đầu cần headed để login
    )
    page = await browser.new_page()
    await page.goto("https://labs.google/fx/tools/video-fx")
    # Login Google 1 lần → cookies tự lưu trong profile
    # Lần sau launch lại → tự động login
    return browser, page
```

> **Lưu ý**: Login chỉ cần 1 lần. Persistent profile lưu cookies giữa các session. Headless mode dùng được SAU khi đã login lần đầu.

#### 6.23.3. Bypass Lớp 2: Browser Headers — Intercept từ Chrome

```python
captured_headers = {}

async def capture_browser_headers(page):
    """Capture x-browser-* headers từ 1 request cross-site bất kỳ."""
    async def on_request(request):
        if "aisandbox-pa.googleapis.com" in request.url:
            h = request.headers
            captured_headers.update({
                "x-browser-channel": h.get("x-browser-channel"),        # "stable"
                "x-browser-copyright": h.get("x-browser-copyright"),    # "Copyright 2026..."
                "x-browser-year": h.get("x-browser-year"),              # "2026"
                "x-browser-validation": h.get("x-browser-validation"),  # SHA1 fingerprint
                "x-client-data": h.get("x-client-data"),                # Chrome variations
            })
    
    page.on("request", on_request)
    # Trigger 1 request: ví dụ check credits
    await page.evaluate("fetch('https://aisandbox-pa.googleapis.com/v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY')")
    # Headers captured → CỐ ĐỊNH trong session → capture 1 lần, dùng nhiều lần
```

> **Lưu ý**: `x-browser-validation` KHÔNG ĐỔI trong cùng session Chrome. Capture 1 lần, dùng cho tất cả requests trong session đó.

#### 6.23.4. Bypass Lớp 3: reCAPTCHA Token — Execute trong Real Browser

```python
async def get_recaptcha_token(page):
    """Lấy reCAPTCHA token mới bằng cách chạy SDK trong browser."""
    token = await page.evaluate("""
        () => {
            return new Promise((resolve, reject) => {
                grecaptcha.enterprise.ready(() => {
                    grecaptcha.enterprise.execute(
                        '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV',
                        {action: 'generate'}
                    ).then(token => resolve(token))
                      .catch(err => reject(err.message));
                });
            });
        }
    """)
    return token  # "0cAFcWeA4mxC9Bkr..." — dùng 1 lần duy nhất
```

> **Lưu ý quan trọng**:
> - **Mỗi lần generate PHẢI gọi lại** `get_recaptcha_token()` — token dùng 1 lần
> - SDK cần page đã load `labs.google` (có nhúng grecaptcha script)
> - Token có thời hạn ngắn (~2 phút), lấy xong phải dùng ngay

#### 6.23.5. Ghép lại: Gửi Request Hoàn chỉnh

```python
import httpx
import time

async def generate_video(page, prompt, project_id):
    """Generate video T2V qua Python, dùng auth data từ browser."""
    
    # 1. Lấy reCAPTCHA token MỚI (bắt buộc mỗi lần)
    token = await get_recaptcha_token(page)
    
    # 2. Build request với headers đã capture + token mới
    response = httpx.post(
        "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText",
        headers={
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            # Browser headers (captured 1 lần/session)
            **captured_headers,
            # KHÔNG có: Authorization, Cookie, x-goog-api-key
        },
        json={
            "clientContext": {
                "recaptchaContext": {
                    "token": token,  # Token mới mỗi lần
                    "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
                },
                "sessionId": f";{int(time.time()*1000)}",
                "projectId": project_id,
                "tool": "PINHOLE",
                "userPaygateTier": "PAYGATE_TIER_TWO"
            },
            "requests": [{
                "textInput": {"prompt": prompt},
                "generationSpecs": [{
                    "videoSpec": {
                        "duration": "VIDEO_DURATION_5_SECONDS",
                        "resolution": "VIDEO_RESOLUTION_720P"
                    }
                }],
                "videoModelKey": "t2v_veo3_relaxed_release",
                "metadata": {"sceneId": "uuid-here"}
            }]
        }
    )
    return response.json()
    # → {"operations": [{"name": "opId", "status": "PENDING"}], "remainingCredits": 44990}


async def poll_status(operation_name, scene_id):
    """Polling trạng thái — KHÔNG cần reCAPTCHA token."""
    while True:
        response = httpx.post(
            "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus",
            headers={
                "Content-Type": "text/plain;charset=UTF-8",
                "Origin": "https://labs.google",
                "Referer": "https://labs.google/",
                **captured_headers,
                # KHÔNG cần reCAPTCHA token cho polling
            },
            json={
                "operations": [{
                    "operation": {"name": operation_name},
                    "sceneId": scene_id,
                    "status": "MEDIA_GENERATION_STATUS_PENDING"
                }]
            }
        )
        result = response.json()
        status = result["operations"][0]["status"]
        
        if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
            return result  # Có fifeUrl, servingBaseUri
        elif status in ["MEDIA_GENERATION_STATUS_FAILED", "MEDIA_GENERATION_STATUS_CANCELLED"]:
            raise Exception(f"Generation failed: {status}")
        
        await asyncio.sleep(6)  # Poll mỗi ~6 giây
```

#### 6.23.6. Bảng Tóm tắt Bypass Strategy

| Lớp | Giải pháp | Capture | Tần suất | Cần browser? |
|---|---|---|---|:---:|
| **Cookies** | Persistent Chrome profile | Tự động | 1 lần login, dùng mãi | ✅ Lần đầu |
| **Headers** | Intercept từ browser request | 1 lần/session | Cố định trong session | ✅ 1 lần |
| **reCAPTCHA** | `page.evaluate(grecaptcha.enterprise.execute)` | Mỗi lần generate | **Bắt buộc mỗi lần** | ✅ Luôn luôn |
| **Credits** | Không bypass được — phụ thuộc account | — | — | ❌ |

> 📌 **KẾT LUẬN**: Python client **BẮT BUỘC** cần một Playwright browser instance chạy song song suốt session. Browser đóng vai trò:
> 1. **Cookie store** = duy trì Google login session
> 2. **Header source** = cung cấp browser fingerprint headers
> 3. **Token generator** = chạy reCAPTCHA SDK để lấy token mới mỗi lần generate
>
> Không có browser → không bypass được → không gửi request thành công.

---

### 6.24. Phân loại Biến Xác thực — Hằng số / Biến động / Vòng đời

> Bảng tổng hợp TẤT CẢ thành phần xác thực, phân loại theo phạm vi (scope), tính chất tĩnh/động, cách lấy, lưu trữ, refresh, và thời hạn:

#### 6.24.1. Bảng Phân loại Master

| # | Thành phần | Phạm vi | Tĩnh/Động | Giá trị mẫu |
|---|---|---|:---:|---|
| 1 | **Site Key** (reCAPTCHA) | 🌐 Website | 🟢 TĨNH | `6LdsFiUsAAAAAI...` |
| 2 | **API Key** | 🌐 Website | 🟢 TĨNH | `AIzaSyBtrm0o5ab1c...` |
| 3 | `x-browser-channel` | 💻 Chrome Build | 🟡 BÁN ĐỘNG | `stable` |
| 4 | `x-browser-copyright` | 💻 Chrome Build | 🟡 BÁN ĐỘNG | `Copyright 2026 Google LLC...` |
| 5 | `x-browser-year` | 💻 Chrome Build | 🟡 BÁN ĐỘNG | `2026` (đổi theo năm Chrome) |
| 6 | `x-browser-validation` | 💻 Máy+Session | 🟡 BÁN ĐỘNG | `WVxyJFF0uIgXSTej...` |
| 7 | `x-client-data` | 💻 Máy+Session | 🟡 BÁN ĐỘNG | `CI+2yQEIo7bJAQ...` |
| 8 | **Cookies** (session) | 👤 Account | 🔴 ĐỘNG | `__Secure-next-auth.session-token=...` |
| 9 | **access_token** (`ya29.*`) | 👤 Account | 🔴 ĐỘNG | `ya29.a0AUMWg_IRQ...` (⚠️ KHÔNG DÙNG) |
| 10 | **projectId** | 👤 Account | 🔴 ĐỘNG | `a89ea3a4-168c-4133-...` |
| 11 | **sessionId** | ⚡ Hành động | 🔴 ĐỘNG | `;1770534060719` |
| 12 | **reCAPTCHA Token** | ⚡ Hành động | 🔴 ĐỘNG | `0cAFcWeA4mxC9Bkr...` |
| 13 | **Signed URL** | ⚡ Hành động | 🔴 ĐỘNG | `?GoogleAccessId=...&Signature=...` |

> ⚠️ **Tại sao `x-browser-channel/copyright/year` là BÁN ĐỘNG thay vì TĨNH?**
> - `x-browser-year` = `"2026"` → sẽ thành `"2027"` khi Chrome update sang năm mới
> - `x-browser-copyright` = `"Copyright 2026 Google LLC..."` → cũng đổi theo năm
> - `x-browser-channel` = `"stable"` → có thể khác nếu dùng Chrome Beta/Canary
> - **Kết luận**: KHÔNG hardcode → capture TẤT CẢ 5 headers từ browser để app Python tự động đúng mọi lúc.

#### 6.24.2. Vòng đời Chi tiết — Cách lấy / Lưu trữ / Refresh / Thời hạn

##### 🟢 HẰNG SỐ (Tĩnh — hardcode, không cần refresh)

| Thành phần | Cách lấy | Lưu trữ | Refresh | Thời hạn |
|---|---|---|---|---|
| **Site Key** | Hardcode trong HTML `<script src="...?render=KEY">` | Hardcode trong code Python | ❌ Không cần | ♾️ Vĩnh viễn (cho đến khi Google đổi) |
| **API Key** | Hardcode trong JS bundle | Hardcode trong code Python | ❌ Không cần | ♾️ Vĩnh viễn |

> 💡 **Hằng số = chỉ Site Key và API Key.** Hardcode 1 lần, dùng mọi nơi.

##### 🟡 BÁN ĐỘNG (Thay đổi theo Chrome version/session, cố định trong session)

| Thành phần | Cách lấy | Lưu trữ | Refresh khi | Thời hạn |
|---|---|---|---|---|
| **x-browser-channel** | Intercept từ Chrome request | Biến Python (in-memory) | Chrome đổi kênh (stable→beta) | ♾️ trong session |
| **x-browser-copyright** | Intercept từ Chrome request | Biến Python (in-memory) | Chrome update sang năm mới | ♾️ trong session |
| **x-browser-year** | Intercept từ Chrome request | Biến Python (in-memory) | Chrome update sang năm mới | ♾️ trong session |
| **x-browser-validation** | Intercept từ Chrome request | Biến Python (in-memory) | Restart Chrome | ♾️ trong session |
| **x-client-data** | Intercept từ Chrome request | Biến Python (in-memory) | Chrome update A/B flags | ♾️ trong session |

> 💡 **TẤT CẢ 5 headers = capture 1 lần khi khởi tạo session** bằng `page.on("request")`. Dùng cho TẤT CẢ requests trong session đó. Chrome restart/update → capture lại. **KHÔNG BAO GIỜ hardcode giá trị cụ thể** (ví dụ `"2026"`) trong code.

##### 🔴 ĐỘNG (Thay đổi theo account/hành động, CẦN refresh)

| Thành phần | Cách lấy | Lưu trữ | Refresh | Thời hạn |
|---|---|---|---|---|
| **Cookies** | Google Login → browser tự lưu | Persistent Chrome profile (`user_data_dir`) | Tự động qua browser | ~30 ngày (Google session) |
| **access_token** | `GET /fx/api/auth/session` (cookies auto) | ❌ **KHÔNG CẦN LƯU** — không dùng | — | ~24h nhưng KHÔNG DÙNG |
| **projectId** | `TRPC project.createProject` hoặc `project.getProject` | Biến Python / DB | Khi tạo project mới | ♾️ (UUID vĩnh viễn) |
| **sessionId** | Tự tạo: `f";{int(time.time()*1000)}"` | Biến Python | Mỗi browser session | ♾️ trong session |
| **reCAPTCHA Token** | `page.evaluate(grecaptcha.enterprise.execute(...))` | ❌ **KHÔNG LƯU** — dùng ngay | **MỖI API call** | ⏱️ **~2 phút** (dùng 1 lần) |
| **Signed URL** | Server trả trong response (`servingBaseUri`) | Biến tạm để download | ❌ Server tạo mới mỗi lần | ⏱️ **~24h** |

> 💡 **Động = cần quản lý lifecycle. reCAPTCHA Token quan trọng nhất — hết hạn nhanh, dùng 1 lần, phải lấy mới MỖI API CALL.**
>
> ⚠️ **QUAN TRỌNG (verified từ 54 HAR files)**: Token là **1 per API call**, KHÔNG PHẢI 1 per output:
>
> | Endpoint | Gom batch? | Tokens / 4 outputs |
> |---|---|---|
> | `flowMedia:batchGenerateImages` | ✅ 4 ảnh = 1 POST | **1 token** |
> | `video:batchAsyncGenerateVideoText` | ✅ 4 video = 1 POST | **1 token** |
> | `video:batchAsyncGenerateVideo*` (tất cả mode) | ✅ 4 video = 1 POST | **1 token** |
> | `video:batchAsyncGenerateVideoUpsampleVideo` | ❌ 4 video = **4 POST riêng** | **4 tokens riêng** |
> | `flow/upsampleImage` | ❌ 1 ảnh = 1 POST | **1 token/ảnh** |

#### 6.24.3. Sơ đồ Vòng đời theo Thời gian

```mermaid
gantt
    title Vòng đời Auth Variables
    dateFormat X
    axisFormat %s

    section 🟢 Hằng số
    Site Key, API Key : done, const, 0, 100

    section 🟡 Bán động (capture từ browser)
    x-browser-channel/copyright/year : active, semi0, 0, 100
    x-browser-validation (capture 1 lần) : active, semi, 0, 100
    x-client-data (capture 1 lần) : active, semi2, 0, 100

    section 🔴 Động (Account)
    Cookies (30 ngày) : crit, cookie, 0, 90
    projectId (vĩnh viễn sau khi tạo) : done, proj, 5, 100

    section 🔴 Động (Hành động — per API call)
    Token Batch#1: generate 4 vid (~2 phút) : crit, tok1, 20, 22
    Token Batch#2: generate 4 vid (~2 phút) : crit, tok2, 40, 42
    Token Upscale#1-4: 4 vid riêng (~2 phút) : crit, tok3, 60, 64
    Signed URL #1 (~24h) : active, url1, 22, 80
    Signed URL #2 (~24h) : active, url2, 42, 100
```

#### 6.24.4. Checklist Khởi tạo Python Client

```python
# ============================================================
# KHỞI TẠO SESSION — THỨ TỰ BẮT BUỘC
# ============================================================

# BƯỚC 0: Hằng số — Hardcode (CHỈ 2 giá trị)
SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"  # 🟢 Vĩnh viễn
API_KEY  = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"   # 🟢 Vĩnh viễn
# ⚠️ KHÔNG hardcode x-browser-channel/copyright/year!
# Giá trị "2026" sẽ sai khi Chrome update sang 2027.

# BƯỚC 1: Launch browser + Login (1 lần)
browser, page = await init_browser()          # 🔴 Cookies = persistent profile

# BƯỚC 2: Capture TẤT CẢ 5 browser headers (1 lần/session)
await capture_browser_headers(page)           # 🟡 capture ALL 5: channel, copyright, year,
                                              #    validation, client-data từ Chrome thật
                                              #    → tự động đúng dù Chrome update năm nào

# BƯỚC 3: Lấy/tạo project (1 lần/project)
project_id = await create_or_get_project()    # 🔴 UUID vĩnh viễn

# BƯỚC 4: Tạo session ID (1 lần/session)
session_id = f";{int(time.time()*1000)}"      # 🔴 Tự tạo

# ============================================================
# MỖI LẦN GENERATE — LẶP LẠI BƯỚC NÀY
# ============================================================

# BƯỚC 5: Lấy reCAPTCHA token MỚI (BẮT BUỘC mỗi API call)
# Action = "VIDEO_GENERATION" cho TẤT CẢ thao tác (T2V, I2V, R2V, Upscale)
token = await page.evaluate('''
    grecaptcha.enterprise.execute("6LdsFiUs...", {action: "VIDEO_GENERATION"})
''')                                          # 🔴 ~2 phút, 1 lần dùng

# BƯỚC 6: Gửi request
# → headers = STATIC_HEADERS + captured_headers (bước 2)
# → payload = token (bước 5) + project_id (bước 3) + session_id (bước 4)
#
# ⚠️ TOKEN PER API CALL (verified từ HAR):
#   - Batch generate (image/video): 1 token → gom 4 outputs trong 1 POST
#     → Token copy vào cả root VÀ requests[0..3].clientContext.recaptchaContext
#   - Upscale video: 4 POST riêng biệt → CẦN 4 TOKENS RIÊNG
#     for video in videos_to_upscale:
#         token_i = await get_recaptcha_token(page)  # Token mới cho mỗi upscale
#         await upscale_video(video, token_i)

# BƯỚC 7: Polling (KHÔNG cần token mới)
# BƯỚC 8: Download (Signed URL từ response, ~24h)
```

> 📌 **QUY TẮC NHỚ**:
> - 🟢 **Hằng số**: Hardcode → quên đi
> - 🟡 **Bán động**: Capture TẤT CẢ 5 headers từ browser, 1 lần khi start → dùng cả session
> - 🔴 **Động (account)**: Login 1 lần → dùng mãi (cookies tự refresh)
> - 🔴 **Động (hành động)**: reCAPTCHA Token = **PHẢI LẤY MỚI MỖI API CALL** (1 token/batch cho generate, 4 token riêng cho 4 upscale)

#### 6.24.5. Phân công Nhiều Tài khoản / Nhiều Máy — Cách ly Biến

> Khi chạy Python client trên **nhiều tài khoản** và/hoặc **nhiều máy tính**, cần hiểu rõ biến nào **dùng chung** và biến nào **phải riêng biệt** cho mỗi worker:

##### A. Bảng Phân vùng Biến theo Scope

| Biến | Dùng chung TOÀN BỘ | Dùng chung CÙNG MÁY | RIÊNG mỗi Account | RIÊNG mỗi Hành động |
|---|:---:|:---:|:---:|:---:|
| **Site Key** | ✅ | ✅ | ✅ | ✅ |
| **API Key** | ✅ | ✅ | ✅ | ✅ |
| **x-browser-channel** | ❌ | ✅ cùng Chrome | ❌ | ❌ |
| **x-browser-copyright** | ❌ | ✅ cùng Chrome | ❌ | ❌ |
| **x-browser-year** | ❌ | ✅ cùng Chrome | ❌ | ❌ |
| **x-browser-validation** | ❌ | ❌ (khác profile) | ❌ | ❌ |
| **x-client-data** | ❌ | ✅ cùng Chrome | ❌ | ❌ |
| **Cookies** | ❌ | ❌ | 🔒 RIÊNG | ❌ |
| **projectId** | ❌ | ❌ | 🔒 RIÊNG | ❌ |
| **Credits** | ❌ | ❌ | 🔒 RIÊNG | ❌ |
| **sessionId** | ❌ | ❌ | 🔒 RIÊNG | ❌ |
| **reCAPTCHA Token** | ❌ | ❌ | ❌ | 🔒 RIÊNG |
| **Signed URL** | ❌ | ❌ | ❌ | 🔒 RIÊNG |

> ⚠️ **`x-browser-validation`** là ngoại lệ: dù cùng máy, nếu mỗi account chạy **Playwright profile riêng** thì mỗi profile có fingerprint khác nhau. Chỉ dùng chung khi cùng 1 Chrome instance.

##### B. Kiến trúc Multi-Account trên 1 Máy

```
┌──────────────────────────────────────────────────────────────┐
│                       MÁY A (1 máy tính)                      │
│                                                                │
│  Hằng số DÙNG CHUNG: Site Key, API Key                       │
│                                                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │ Worker 1          │  │ Worker 2          │  │ Worker 3   │  │
│  │ Account: user1@   │  │ Account: user2@   │  │ user3@     │  │
│  │                    │  │                    │  │            │  │
│  │ 📁 Profile riêng  │  │ 📁 Profile riêng  │  │ 📁 Riêng   │  │
│  │  ./profiles/user1  │  │  ./profiles/user2  │  │ ./p/user3  │  │
│  │                    │  │                    │  │            │  │
│  │ 🍪 Cookies riêng  │  │ 🍪 Cookies riêng  │  │ 🍪 Riêng   │  │
│  │ 🔑 Headers riêng  │  │ 🔑 Headers riêng  │  │ 🔑 Riêng   │  │
│  │ 📋 Project riêng  │  │ 📋 Project riêng  │  │ 📋 Riêng   │  │
│  │ 💰 Credits riêng  │  │ 💰 Credits riêng  │  │ 💰 Riêng   │  │
│  │ 🤖 Token riêng    │  │ 🤖 Token riêng    │  │ 🤖 Riêng   │  │
│  └──────────────────┘  └──────────────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

##### C. Kiến trúc Multi-Account trên Nhiều Máy

```mermaid
graph TB
    subgraph SHARED["🟢 DÙNG CHUNG (hardcode)"]
        SK["Site Key: 6LdsFiUs..."]
        AK["API Key: AIzaSyBt..."]
    end

    subgraph MACHINE_A["💻 MÁY A"]
        subgraph W1["Worker 1 — user1@gmail.com"]
            P1["📁 Profile: ./profiles/user1"]
            C1["🍪 Cookies: riêng"]
            H1["🔑 Headers: capture riêng"]
            CR1["💰 Credits: 45000"]
            PJ1["📋 projectId: uuid-1"]
        end
        subgraph W2["Worker 2 — user2@gmail.com"]
            P2["📁 Profile: ./profiles/user2"]
            C2["🍪 Cookies: riêng"]
            H2["🔑 Headers: capture riêng"]
            CR2["💰 Credits: 30000"]
            PJ2["📋 projectId: uuid-2"]
        end
    end

    subgraph MACHINE_B["💻 MÁY B"]
        subgraph W3["Worker 3 — user3@gmail.com"]
            P3["📁 Profile: ./profiles/user3"]
            C3["🍪 Cookies: riêng"]
            H3["🔑 Headers: capture riêng"]
            CR3["💰 Credits: 45000"]
            PJ3["📋 projectId: uuid-3"]
        end
    end

    SK --> W1
    SK --> W2
    SK --> W3
    AK --> W1
    AK --> W2
    AK --> W3

    style SHARED fill:#E8F5E9
    style W1 fill:#E3F2FD
    style W2 fill:#FFF3E0
    style W3 fill:#F3E5F5
```

##### D. Cấu trúc Dữ liệu cho Multi-Account Python Client

```python
# ============================================================
# MULTI-ACCOUNT: Mỗi account = 1 "worker" riêng biệt
# ============================================================

# 🟢 HẰNG SỐ — dùng chung cho TẤT CẢ workers
SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
API_KEY  = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"

# 🔴 MỖI ACCOUNT = 1 Worker instance
class AccountWorker:
    def __init__(self, account_email: str, profile_dir: str):
        self.email = account_email
        self.profile_dir = profile_dir       # 📁 Chrome profile RIÊNG
        
        # Sẽ populate sau khi init
        self.browser = None                  # 🖥️ Browser instance RIÊNG
        self.page = None                     # 📄 Page RIÊNG
        self.cookies = None                  # 🍪 Cookies RIÊNG (auto trong profile)
        self.browser_headers = {}            # 🔑 5 headers RIÊNG (capture từ browser)
        self.project_id = None               # 📋 Project RIÊNG
        self.session_id = None               # ⏱️ Session RIÊNG
        self.credits_remaining = 0           # 💰 Credits RIÊNG
    
    async def init(self):
        """Khởi tạo worker — browser + headers + project."""
        # Mỗi worker có browser profile RIÊNG → cookies RIÊNG
        pw = await async_playwright().start()
        self.browser = await pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,  # RIÊNG cho mỗi account
            headless=False
        )
        self.page = await self.browser.new_page()
        await self.page.goto("https://labs.google/fx/tools/video-fx")
        
        # Capture 5 headers từ browser CỦA WORKER NÀY
        await self._capture_headers()
        
        # Tạo session ID cho worker này
        self.session_id = f";{int(time.time()*1000)}"
    
    async def generate(self, prompt: str):
        """Generate — mỗi lần cần token MỚI từ browser CỦA WORKER NÀY."""
        token = await self._get_recaptcha_token()  # Token RIÊNG
        # Gửi request với headers RIÊNG + token RIÊNG
        ...

# ============================================================
# PHÂN CÔNG CÔNG VIỆC — N accounts × M tasks
# ============================================================

workers = [
    AccountWorker("user1@gmail.com", "./profiles/user1"),
    AccountWorker("user2@gmail.com", "./profiles/user2"),
    AccountWorker("user3@gmail.com", "./profiles/user3"),
]

# Init tất cả workers
for w in workers:
    await w.init()

# Phân công: round-robin hoặc theo credits còn lại
tasks = ["prompt_A", "prompt_B", "prompt_C", "prompt_D", ...]
for i, task in enumerate(tasks):
    worker = workers[i % len(workers)]    # Round-robin
    await worker.generate(task)
```

##### E. Quy tắc Cô lập (Isolation Rules)

| Quy tắc | Mô tả | Vi phạm → hậu quả |
|---|---|---|
| **1 profile = 1 account** | Mỗi `user_data_dir` chỉ login 1 Google account | Login account khác → mất cookies cũ |
| **1 browser = 1 bộ headers** | Mỗi Playwright instance có `x-browser-validation` riêng | Dùng chung → Google phát hiện bất thường |
| **1 token = 1 generate** | reCAPTCHA token không chia sẻ giữa workers | Dùng lại → server reject |
| **Credits độc lập** | Mỗi account có credits riêng, theo dõi riêng | Không track → generate fail khi hết credits |
| **Session ID riêng** | Mỗi worker tạo sessionId riêng | Dùng chung → server confuse tracking |

> 📌 **TÓM LẠI cho Multi-Account**:
> - **Dùng chung**: Chỉ 2 hằng số (Site Key, API Key)
> - **Mọi thứ khác**: RIÊNG cho mỗi account (browser profile, cookies, headers, projectId, credits, tokens)
> - **Mỗi worker = 1 Playwright browser riêng** với `user_data_dir` riêng
> - **Máy khác nhau**: Copy code + tạo profile mới trên máy đó, login account riêng

##### F. Ánh xạ Biến ↔ Vai trò Phân công (Cross-ref: MULTITHREADING_ARCHITECTURE.md)

> Tài liệu kiến trúc phân công chi tiết nằm tại:
> 📄 [`MULTITHREADING_ARCHITECTURE.md`](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/00%20-%20Documentation/03_Backend/MULTITHREADING_ARCHITECTURE.md)
>
> Dưới đây là ánh xạ biến xác thực → vai trò quản lý trong hệ thống ĐẠI CHỦ-CHỦ-THẦU-THỢ:

| Vai trò | Class | Quản lý biến nào | Chia sẻ? |
|---|---|---|---|
| **ĐẠI CHỦ** | `MultiAccountManager` | Site Key, API Key (hằng số, 1 bản) | ✅ Dùng chung N accounts |
| **CHỦ** | `AccountManager` | Cookies, browser headers (5 cái), projectId, sessionId, credits | 🔒 RIÊNG mỗi account |
| **CHỦ** | `ProjectManager` | projectId (UUID), project cache | 🔒 RIÊNG mỗi account |
| **THẦU** | `Dispatcher` | Không giữ biến auth — chỉ routing task | — |
| **THỢ** | Worker task | reCAPTCHA Token (nhận từ CHỦ), Signed URL (nhận từ server) | 🔒 RIÊNG mỗi hành động |

**Ràng buộc từ Architecture doc**:

| Ràng buộc | Giá trị | Ảnh hưởng đến biến |
|---|---|---|
| **Concurrent slots / account** | **4** | Mỗi CHỦ có semaphore(4), tối đa 4 THỢ cùng lúc. Token: 1/batch (generate), 4/batch (upscale) |
| **Total capacity** | N × 4 | 3 accounts = 12 slots đồng thời |
| **Cross-account continuation** | ✅ Hỗ trợ | Frame local → upload bằng account B → **dùng auth của account B**, không phải A |
| **Project isolation** | Mỗi CHỦ 1 project | Task chạy trên account nào → dùng projectId của account đó |

**Ví dụ cụ thể — 3 accounts, 12 prompts**:

```
ĐẠI CHỦ: 3 accounts × 4 slots = 12 slots
│
├─ CHỦ 1 (user1@gmail.com)
│  ├─ 🍪 Cookies: session-token-user1
│  ├─ 🔑 Headers: {validation: "abc...", client-data: "CI+..."}
│  ├─ 📋 projectId: uuid-1111
│  ├─ 💰 Credits: 45000
│  └─ THỢ 1,2,3,4 → Prompt 1,2,3,4    (4 đồng thời)
│     Generate: 1 batch = 1 token cho 4 outputs
│     Upscale: 4 POST riêng = 4 token RIÊNG
│
├─ CHỦ 2 (user2@gmail.com)
│  ├─ 🍪 Cookies: session-token-user2
│  ├─ 🔑 Headers: {validation: "xyz...", client-data: "CJ+..."}
│  ├─ 📋 projectId: uuid-2222
│  ├─ 💰 Credits: 30000
│  └─ THỢ 5,6,7,8 → Prompt 5,6,7,8    (4 đồng thời)
│
└─ CHỦ 3 (user3@gmail.com)
   ├─ 🍪 Cookies: session-token-user3
   ├─ 🔑 Headers: {validation: "def...", client-data: "CK+..."}
   ├─ 📋 projectId: uuid-3333
   ├─ 💰 Credits: 45000
   └─ THỢ 9,10,11,12 → Prompt 9,10,11,12 (4 đồng thời)
```

> ⚠️ **LƯU Ý QUAN TRỌNG** (verified từ 54 HAR files):
> - **Generate** (image/video): Website gom 4 outputs vào **1 batch POST** → chỉ cần **1 reCAPTCHA token**. Token được copy vào `clientContext.recaptchaContext` ở cả root body VÀ mỗi `requests[i]`
> - **Upscale** (video): Website gửi **4 POST riêng biệt** → mỗi POST cần **1 token RIÊNG** (4 token unique cho 4 video)
> - **Upscale** (image): 1 POST per ảnh → 1 token per ảnh
> - Tổng kết: Generate 4 + Upscale 4 = cần **1 + 4 = 5 tokens** cho full flow
> - Credits giảm theo MỖI ACCOUNT riêng biệt — khi 1 account hết credits, ĐẠI CHỦ redistribute tasks sang account khác
> - Chi tiết phân công, dependency chains, và state machine: xem [`MULTITHREADING_ARCHITECTURE.md`](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/00%20-%20Documentation/03_Backend/MULTITHREADING_ARCHITECTURE.md)

---

## 7. Chuỗi Phụ thuộc Endpoint & Quan hệ

### 7.1. Sơ đồ Luồng Dữ liệu Tổng thể

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BROWSER SESSION (Cookie-based Auth)              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    access_token     ┌───────────────────────┐    │
│  │ AUTH:session  │ ─────────────────→  │ TRPC Layer (labs.google)│   │
│  │ (ya29.* token)│                     │ Dùng token nội bộ      │   │
│  └──────────────┘                     └───────────────────────┘    │
│         │                                      │                    │
│         │ chỉ cookies                          │ TRPC calls         │
│         ▼                                      ▼                    │
│  ┌──────────────────┐              ┌──────────────────────────┐    │
│  │  REST API Layer   │              │  project.createProject    │    │
│  │  (aisandbox-pa)   │              │  project.getProject       │    │
│  │  KHÔNG Bearer     │              │  project.searchScenes     │    │
│  │  KHÔNG access_tok │              │  videoFx.getUserSettings  │    │
│  │  KHÔNG cookies    │              │  videoFx.getModelConfig   │    │
│  │  Dùng: x-browser-*│              │  media.fetchHistory       │    │
│  │  + reCAPTCHA (gen)│              │  general.submitBatchLog   │    │
│                                     └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2. Chuỗi Phụ thuộc Trước Khi Generate

Mọi request generate đều yêu cầu các **prerequisite** calls sau:

```
project.searchProjectScenes ──→ Xác nhận project tồn tại, load scenes
        │
        ├──→ media.fetchUserHistoryDirectly ──→ Load lịch sử (phân trang, 2-11 pages)
        │            │
        │            └──→ /v1/media/{ID} ──→ Load từng ảnh đã upload (song song)
        │                     │
        │                     └──→ Trả về: mediaGenerationId, fifeUrl, aspectRatio
        │
        ├──→ general.fetchUserAcknowledgement ──→ Kiểm tra đã chấp nhận điều khoản
        │
        └──→ (Tùy chọn) videoFx.setLastSelectedVideoModelKey
             videoFx.setLastSelectedVideoAspectRatio
```

> **PHÁT HIỆN QUAN TRỌNG**: `media.fetchUserHistoryDirectly` được gọi **2-11 lần mỗi file** (phân trang). Các file revisit project với nhiều ảnh upload phải load **25-30 media items** riêng lẻ qua `/v1/media/{ID}` trước khi có thể bắt đầu generate.

### 7.3. Chuỗi Generate-đến-Hoàn thành

```
recaptcha/enterprise/reload ──→ Lấy token mới (BẮT BUỘC)
        │
        ├──→ /v1/video:batchAsync... ──→ Submit generation với token
        │            │
        │            ├──→ Trả về: operations[] gồm operation.name + sceneId
        │            ├──→ Trả về: remainingCredits (trừ credit ngay)
        │            └──→ (Chỉ Upscale) Trả về: workflows[] + media[]
        │
        ├──→ recaptcha/enterprise/clr ──→ Log kết quả reCAPTCHA (LUÔN sau submit)
        │
        ├──→ general.submitBatchLog ──→ VIDEOFX_CREATE_VIDEO event
        │    general.submitBatchLog ──→ PINHOLE_GENERATE_VIDEO event
        │    (3-6 batch log calls mỗi lần generate)
        │
        └──→ /v1/video:batchCheckAsync... ──→ Vòng lặp polling (4-253 lần)
                     │
                     ├──→ PENDING → ACTIVE → SUCCESSFUL
                     ├──→ Khi SUCCESSFUL: metadata chứa video URLs
                     └──→ remainingCredits xuất hiện khi TẤT CẢ ops hoàn thành
```

### 7.4. Các Cặp Endpoint Luôn Đi Cùng (Co-occur)

Các endpoint này **luôn được gọi cùng nhau** — không bao giờ độc lập:

| Endpoint Chính | Luôn Đi Cùng Với | Quan hệ |
|---|---|---|
| `recaptcha/enterprise/reload` | Bất kỳ `batchAsync*` generation | Token lấy → nhúng vào payload |
| Bất kỳ `batchAsync*` generation | `recaptcha/enterprise/clr` | Luôn gọi ngay sau submission |
| Bất kỳ `batchAsync*` generation | `batchCheckAsyncVideoGenerationStatus` | Polling luôn theo sau generation |
| `STORAGE:/ai-sandbox-videofx/video/{UUID}` | `general.submitBatchLog` (DOWNLOAD) | Sự kiện download luôn được log |
| `reportClientSideError` | `submitBatchLog` (ERROR event) | Lỗi luôn report + log |
| `uploadUserImage` | `submitBatchLog` (UPLOAD events) | 3 events: UPLOAD, RESIZE, CROP |

### 7.5. Các Endpoint Tách biệt (Không Bao giờ Đi Cùng)

| Endpoint A | Endpoint B | Lý do |
|---|---|---|
| `whisk.getRecentMedia` | `project.searchProjectScenes` | Khác app (Whisk vs Flow) |
| `/v1/whisk:getVideoCreditStatus` | `/v1/credits` | ~~Credit check khác nhau theo app~~ **Đã sửa**: Whisk dùng **CẢ HAI** (bước 3 + 4 trong Công việc 8) |
| `general.fetchFeatureAvailability` | `videoFx.getUserSettings` | Feature flags = Whisk, User settings = Flow |

---

## 8. Luồng Dữ liệu Xuyên Thành phần

### 8.1. Vòng đời Media ID

```
┌─────────────────┐     uploadUserImage      ┌────────────────────┐
│ Ảnh User         │ ──────────────────────→ │ mediaGenerationId   │
│ (Base64 JPEG)    │                          │ "CAMaJDY2NGQ2Y2..." │
└─────────────────┘                          └────────────────────┘
        │                                              │
        │ Upload trả về mediaId                       │ Được dùng làm:
        ▼                                              ▼
┌─────────────────────────────────────────────────────────────┐
│ startImage.mediaId   │ endImage.mediaId  │ referenceImages   │
│ (trong I2V payload)  │ (trong S+E payload)│ (trong R2V payload)│
└─────────────────────────────────────────────────────────────┘
        │
        │ Generation response trả về:
        ▼
┌─────────────────────────────────────────────────────────────┐
│ operation.name (hex32)    │ → Dùng trong polling request    │
│ sceneId (UUID)            │ → Liên kết video với scene      │
│ remainingCredits          │ → Theo dõi credit               │
└─────────────────────────────────────────────────────────────┘
        │
        │ Poll SUCCESSFUL trả về:
        ▼
┌─────────────────────────────────────────────────────────────┐
│ operation.metadata.name = "CAUS..." │ → mediaId video mới   │
│ video.fifeUrl                       │ → URL xem trước       │
│ video.servingBaseUri                │ → Base URL tải xuống   │
│ mediaGenerationId = "CAUS..."       │ → Dùng cho upscale    │
└─────────────────────────────────────────────────────────────┘
        │
        │ Upscale dùng videoInput.mediaId:
        ▼
┌──────────────────────────────────────────────────┐
│ videoInput.mediaId = "CAUS..."                   │
│ → Upscale trả về: primaryMediaId + "_upsampled"  │
│ → workflowStepId = "CAE"                         │
└──────────────────────────────────────────────────┘
```

### 8.2. Ánh xạ Prefix Media ID → Loại

| Prefix | Ý nghĩa | Tạo bởi | Dùng trong |
|---|---|---|---|
| `CAMa` | Ảnh upload (workflow=user, step=upload) | `uploadUserImage` | `startImage.mediaId`, `endImage.mediaId` |
| `CAMS` | Ảnh generated (workflow=project, step=gen) | `batchGenerateImages` | `upsampleImage.mediaId` |
| `CAUS` | Video generated (workflow=auto, step=gen) | `batchCheckAsync...` (khi SUCCESS) | `videoInput.mediaId` trong upscale |

### 8.3. Session ID → Ánh xạ Endpoint

Session IDs (`;{timestamp}`) xuất hiện trong MỌI `clientContext`. Một session bao gồm:

- Tất cả generation requests trong một tab browser
- Tất cả uploads trong session đó
- Tất cả image upscales trong session đó
- Upscale `clientContext` mang sessionId nhưng **BỎ** projectId + tool

### 8.4. Luồng Project ID

```
project.createProject ──→ Trả về projectId
        │
        ├──→ project.getProject (projectId trong URL query)
        ├──→ project.searchProjectScenes (projectId trong URL query)
        ├──→ project.searchProjectWorkflows (projectId trong URL query)
        ├──→ /v1/projects/{projectId}/flowMedia:batchGenerateImages
        ├──→ clientContext.projectId trong generation payloads
        └──→ workflows[].projectId trong upscale responses
```

> **QUAN TRỌNG**: `projectId` **KHÔNG** có trong upscale `clientContext`, nhưng server **TRẢ VỀ** `projectId` trong `workflows[].projectId` của upscale response. Server tự theo dõi liên kết này nội bộ.

---

## 9. Ma trận Loại Thao tác Theo File

### 9.1. Phân loại Toàn bộ 50 HAR Files

| Loại | Files | Endpoints Chính | Pattern Đặc biệt |
|---|---|---|---|
| **Tạo Project** | `0. Tao Project.har` (×2) | createProject, getProject, searchScenes, getUserSettings, getModelConfig, fetchPreferences, searchWorkflows, listPreambles | Chuỗi khởi tạo đầy đủ |
| **Kiểm tra** | `Check Ultra.har`, `Check trang thai...` (×2) | credits, fetchUserRecommendations, checkAppAvailability, getProject, getFlowAppConfig, fetchUserLocale, fetchFlowUserIngredients | Trạng thái tài khoản + cấu hình |
| **Text-to-Video** | `Prompt 1-5.har` (×16) | batchAsyncGenerateVideo, batchCheckAsync, setModelKey, setAspectRatio | submitBatchLog ×3 mỗi lần gen |
| **Image-to-Video (S+E)** | `916 frame to video.har` (×5) | uploadUserImage, batchAsync...StartAndEndImage, batchCheckAsync, fetchUserHistoryDirectly ×3, media/{ID} ×25+ | Load media hàng loạt |
| **Reference-to-Video** | `01.x 169 ingredients.har` (×6) | batchAsync...ReferenceImages, setModelKey, setAspectRatio | referenceImages[] trong payload |
| **Upscale** | `916 frame to video...Upscale*.har` (×4) | batchAsync...UpsampleVideo (×4 tuần tự), batchCheckAsync (×33-253) | Upscale tuần tự + poll |
| **Reshoot** | Nhiều `.har` | batchAsync...Reshoot | Tạo lại video cụ thể |
| **Extend** | Nhiều `.har` | batchAsync...ExtendVideo | Kéo dài video |
| **Download (720p)** | `Download 720 4 vid.har` | STORAGE ×4, submitBatchLog ×4 | Ghép cặp: download + log |
| **Download Ảnh** | `Download anh 1k.har` | /v1/media/{ID} (trả ảnh) | encodedImage trong response |
| **Upscale Ảnh** | `Download anh 2k.har`, `Download anh 4k*.har` (×3) | flow/upsampleImage, recaptcha | Trả encodedImage (base64) |
| **Whisk** | `Whisk*.har` (×5) | whisk.getRecentMedia, whisk.getWhiskRecentMediaGroupIds, whisk:getVideoCreditStatus, fetchFeatureAvailability, checkAppAvailability, fetchUserRecommendations | Media ID ngắn, credit check khác |

### 9.2. Quan hệ Xuyên File (Chia sẻ Project ID)

```
Project f5db1342 (21 files) ─── Project làm việc chính
  │
  ├── 0. Tao Project.har ────── Tạo ở đây
  ├── Prompt 1.har ──────────── T2V lần 1
  ├── Prompt 2.har ──────────── T2V lần 2
  ├── ...
  ├── Prompt 5.har ──────────── T2V lần 5
  ├── Download 720.har ──────── Tải kết quả
  ├── Download anh 1k.har ───── Tải ảnh generated
  ├── Download anh 2k.har ───── Upscale ảnh lên 2K
  └── Download anh 4k*.har ──── Upscale ảnh lên 4K

Project 4fd7fb72 (6 files) ─── Project Frame-to-Video
  │
  ├── 916 frame to video...start.har ──── Submit 4 video I2V
  ├── 916 frame to video...done.har ───── Generation hoàn thành
  ├── 916 frame to video...Upscale start ── Submit 4 upscales
  ├── 916 frame to video...1080 done.har ── 1080p upscales xong
  └── 916 frame to video...all done.har ─── Tất cả upscales xong

Project 909d317a (1 file) ─── Project Ingredients
  │
  └── 916 ingre to video.har

Project daba1978 (6 files) ─── Project Reference-image
  │
  ├── 01.2 169 ingredients...submit.har (×3)
  └── 01.3 169 ingredients...done.har (×3)
```

---

## 10. Reference-to-Video (R2V) — Phân tích Chi tiết

### 10.1. Endpoint: `batchAsyncGenerateVideoReferenceImages`

**Số lần xuất hiện**: 5 (trong files: `01.x 169 ingredients...`)

**Cấu trúc Payload** (khác biệt so với T2V và I2V):
```json
{
    "clientContext": {
        "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
        "sessionId": ";...",
        "projectId": "909d317a-c45b-4033-b02a-03385848b986",
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_TWO"
    },
    "requests": [
        {
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "metadata": { "sceneId": "uuid" },
            "referenceImages": [ /* mảng các reference image objects */ ],
            "seed": 12345,
            "textInput": { "prompt": "..." }
        }
    ]
}
```

**Khác biệt chính so với I2V**: Dùng mảng `referenceImages[]` thay vì `startImage`/`endImage`. Không thấy `videoModelKey` trong payload keys (có thể server tự mặc định).

**Cấu trúc Response** (phong phú hơn T2V/I2V):
```json
{
    "operations": [{ "operation": { "name": "..." }, "sceneId": "...", "status": "PENDING" }],
    "remainingCredits": 44990,
    "workflows": [{ "name": "...", "metadata": { "createTime": "...", "primaryMediaId": "...", "batchId": "..." }, "projectId": "..." }],
    "media": [{ "name": "..." }]
}
```

> R2V response bao gồm `workflows` + `media` (giống upscale), trong khi T2V response tiêu chuẩn KHÔNG có.

### 10.2. Flow Pattern R2V

Các file R2V cho thấy luồng nhiều bước đặc trưng:

1. `searchProjectScenes` → Load project
2. `setLastSelectedVideoModelKey` → Đổi model (R2V model)
3. `setLastSelectedVideoAspectRatio` → Có thể đổi 2 lần (user điều chỉnh)
4. `submitBatchLog` ×3 → Logging trước generation
5. `recaptcha/enterprise/reload` → Lấy token
6. `batchAsync...ReferenceImages` → Submit R2V generation
7. `recaptcha/enterprise/clr` → Log reCAPTCHA
8. `batchCheckAsync...` → Poll (4-6 polls quan sát được)

---

## 11. Quan hệ Telemetry & Logging

### 11.1. Ánh xạ Event submitBatchLog → Trigger

| Event | Được kích hoạt bởi | Luôn Trước/Sau |
|---|---|---|
| `PAGE_VIEW` | Điều hướng trang | Event đầu tiên trong Whisk files |
| `PINHOLE_UPLOAD_IMAGE` | `uploadUserImage` thành công | Sau upload response |
| `PINHOLE_UPLOAD_IMAGE_TO_CROP` | User import ảnh để crop | Trước event CROP |
| `PINHOLE_RESIZE_IMAGE` | Ảnh tự động resize | Sau upload, trước gen |
| `PINHOLE_CROP_IMAGE` | User crop ảnh | Sau resize |
| `PINHOLE_GENERATE_IMAGE` | `batchGenerateImages` submit | Sau generation submit |
| `PINHOLE_GENERATE_VIDEO` | Bất kỳ video generation submit | Sau gen submit |
| `PINHOLE_GENERATE_VIDEO_ERROR` | Generation HTTP 403 | Sau error + reportError |
| `PINHOLE_UPSCALE_IMAGE` | `upsampleImage` submit | Sau upscale submit |
| `VIDEOFX_CREATE_VIDEO` | Bất kỳ video generation submit | Cùng batch với GENERATE_VIDEO |
| `VIDEO_CREATION_TO_VIDEO_COMPLETION` | Polling đạt SUCCESSFUL | Sau completion |
| `DOWNLOAD` | STORAGE download hoàn thành | Sau mỗi video download |

### 11.2. Số lần gọi submitBatchLog Theo Hành động

| Hành động | Số lần submitBatchLog | Ghi chú |
|---|---|---|
| Page load (Flow) | 2 | PAGE_VIEW + khởi tạo |
| Upload ảnh | 3 | UPLOAD + RESIZE + CROP |
| Submit video gen | 3 | CREATE_VIDEO + GENERATE_VIDEO + timing |
| Submit video upscale | 5-6 | Mỗi upscale: CREATE + GENERATE + timing ×2 |
| Download video | 1 | DOWNLOAD event mỗi file |
| Lỗi | 2 | reportClientSideError + ERROR event |

### 11.3. Pattern Đánh số Sequence trong Event

Trong luồng mỗi file, request indices có **khoảng trống** (vd: [0], [1], [3], [6]) vì:
- Request non-API (CSS, JS, images) chiếm indices [2], [4], [5]
- Script phân tích HAR chỉ trích xuất API calls, tạo ra gaps trong chỉ số
- Kích thước gap cho biết bao nhiêu request non-API xảy ra giữa các API calls

---

## 12. Phát hiện Chi tiết & Edge Cases

### 12.1. Endpoints Hiếm / Ít lần gọi

| Endpoint | Số lần | Chỉ trong | Ý nghĩa |
|---|---|---|---|
| `batchAsyncGenerateVideoStartImage` | 1 | 1 HAR file | I2V chỉ start frame hiếm gặp |
| `general.fetchToolAvailability` | 1-2 | Whisk files | Chỉ Whisk kiểm tra tool state |
| `general.fetchFeatureAvailability` | 2 | Whisk files | Feature flags chỉ cho Whisk |
| `general.fetchUserLocale` | 2 | Check status files | Locale kiểm tra khi load trang |
| `media.fetchFlowUserIngredients` | 2 | Check status files | Ingredients load khi mở project |
| `project.createProject` | 2 | `0. Tao Project.har` ×2 | Tạo project chỉ 1 lần |
| `general.reportClientSideError` | 1 | Error file | Chỉ 1 lỗi trong 50 files |
| `whisk.getWhiskRecentMediaGroupIds` | 1 | Whisk HAR | Endpoint group IDs |

### 12.2. Biến thể Response fetchUserRecommendations

| Ngữ cảnh | Các trường Response |
|---|---|
| Tài khoản Ultra (`Check Ultra.har`) | `{onramp, upsellMessage, recommendationUri}` |
| Files kiểm tra trạng thái | `{onramp, upsellMessage, recommendationUri, description, imageUri}` |

> **INSIGHT**: Trường `description` và `imageUri` xuất hiện khi tài khoản ở tier thấp hơn và Google đang đề xuất nâng cấp. Tài khoản Ultra nhận dữ liệu recommendation tối thiểu.

### 12.3. Biến thể Response /v1/credits

| Ngữ cảnh | Các trường Response |
|---|---|
| `Check Ultra.har` | `{credits, userPaygateTier, sku, serviceTier}` |
| Các files check khác | `{credits, userPaygateTier, sku}` |

> `serviceTier` (`SERVICE_TIER_ADVANCED`) chỉ xuất hiện trong một số response — có thể A/B test hoặc phụ thuộc version.

### 12.4. Biến thể Response Theo Loại Media

`/v1/media/{ID}` trả về cấu trúc khác nhau tùy loại media:

**Ảnh Upload**:
```json
{
    "name": "CAMa...",
    "userUploadedImage": {
        "image": "(base64)",
        "mediaGenerationId": "...",
        "fifeUrl": "...",
        "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"
    },
    "mediaGenerationId": { "mediaType": "...", "workflowId": "...", "workflowStepId": "...", "mediaKey": "..." }
}
```

**Ảnh Generated**:
```json
{
    "name": "CAMS...",
    "image": {
        "encodedImage": "(base64)",
        "seed": "...",
        "mediaGenerationId": "...",
        "prompt": "...",
        "modelNameType": "...",
        "fifeUrl": "...",
        "aspectRatio": "..."
    },
    "mediaGenerationId": { "mediaType": "...", "projectId": "...", "workflowId": "...", "workflowStepId": "...", "mediaKey": "..." }
}
```

> **KHÁC BIỆT CHÍNH**: Ảnh upload dùng wrapper `userUploadedImage.image`; ảnh generated dùng wrapper `image.encodedImage`. Ảnh generated có `projectId` trong `mediaGenerationId`; ảnh upload thì không.

### 12.5. Pattern Upscale Tuần tự (4 Videos)

Dữ liệu HAR cho thấy upscale 4 videos yêu cầu **submit tuần tự** (KHÔNG phải batch):

```
[Step 9]  recaptcha/reload → Lấy token A
[Step 10] batchAsync...Upsample(video1, tokenA) → Submit video 1
[Step 11] recaptcha/clr
[Step 15-19] submitBatchLog ×5
[Step 21] batchCheckAsync [POLL] → Check video 1
[Step 22] recaptcha/reload → Lấy token B (!)
[Step 23] batchAsync...Upsample(video2, tokenB) → Submit video 2
[Step 24] recaptcha/clr
[Step 27-31] submitBatchLog ×5
[Step 33] recaptcha/reload → Lấy token C (!)
[Step 34] batchAsync...Upsample(video3, tokenC) → Submit video 3
... (tiếp tục cho video 4)
```

> **QUAN TRỌNG**: Mỗi upscale yêu cầu **token reCAPTCHA MỚI**. Token KHÔNG được tái sử dụng giữa các lần submit. Client submit upscale **từng cái một**, đợi reCAPTCHA, rồi submit tiếp — nhưng polling cho tất cả tiếp tục đồng thời.

### 12.6. Chi tiết Luồng Download

Mỗi video download tuân theo pattern chính xác:

```
[Step N]   GET STORAGE:/ai-sandbox-videofx/video/{UUID} → Dữ liệu video binary
[Step N+1] POST TRPC:general.submitBatchLog → {event: "DOWNLOAD"}
```

Cho 4 videos:
```
[0] searchProjectScenes
[1] STORAGE download video 1
[2] submitBatchLog (DOWNLOAD)
[3] STORAGE download video 2
[4] submitBatchLog (DOWNLOAD)
[5] STORAGE download video 3
[6] submitBatchLog (DOWNLOAD)
[8] STORAGE download video 4  (gap: index 7 = non-API request)
[9] submitBatchLog (DOWNLOAD)
```

### 12.7. Chuỗi Khởi tạo Trang Đầy đủ (Full Page Load)

Khi mở trang project lần đầu (`Check trang thai...` files), client thực thi chuỗi khởi tạo:

```
[1] GET /v1/credits
[2] POST /v1:fetchUserRecommendations
[3] POST /v1:checkAppAvailability ({tool: "PINHOLE"})
[4] GET project.getProject
[5] GET videoFx.getFlowAppConfig
[6] GET project.searchProjectScenes
[7] GET general.fetchUserAcknowledgement (×2)
[9] GET general.fetchUserLocale
[10,15] submitBatchLog (PAGE_VIEW ×2)
[16] GET videoFx.getUserSettings
[17] GET general.fetchUserPreferences
[18] GET project.searchProjectWorkflows
[19] GET videoFx.getVideoModelConfig
[20] GET project.searchProjectScenes (lần 2)
[21] GET videoFx.listPreambles
[22] GET media.fetchUserHistoryDirectly
[23] GET media.fetchFlowUserIngredients
```

> Đây là chuỗi khởi tạo đầy đủ nhất được quan sát (23 API calls). Load: credits, recommendations, project data, user settings, model configs, workflows, preambles, history, và ingredients.

### 12.8. So sánh Khởi tạo Whisk vs Flow

| Bước | Flow Init | Whisk Init |
|---|---|---|
| 1 | `/v1/credits` | `checkAppAvailability` |
| 2 | `fetchUserRecommendations` | `fetchFeatureAvailability` + `fetchToolAvailability` |
| 3 | `checkAppAvailability` | `AUTH:session` |
| 4 | `project.getProject` | `/v1/media/{shortId}` ×40+ |
| 5 | `getFlowAppConfig` | `whisk:getVideoCreditStatus` |
| 6+ | `searchScenes`, `getUserSettings`, etc. | `fetchUserRecommendations`, `getFlowAppConfig` |

---

## 13. Kết luận & Khuyến nghị

### 13.1. Trạng thái Phân tích: **ĐẦY ĐỦ 100%**
- 27 thành phần deep-analyzed với full payload/response
- 721 polling requests phân tích state machine
- 72 model keys categorized (30+ active)
- 76 unique endpoints documented (AUTH 1, TRPC 21, REST 51, RECAPTCHA 2, STORAGE 1)
- Tất cả header sets documented
- Mọi inter-component relationship mapped
- 6 chuỗi phụ thuộc (dependency chains) đầy đủ
- 50 HAR files phân loại theo operation type
- 4 project ID cross-file relationships mapped
- 12 telemetry events ánh xạ trigger

### 13.2. Tổng hợp Sai lệch Code vs HAR

| Loại | Số lượng | Chi tiết |
|---|---|---|
| **KHÔNG KHỚP** | 3 | Giao thức, Auth, Recaptcha token placement |
| **THIẾU hoàn toàn** | 21 | API Key, headers, endpoints, state machine, configs |
| **KHỚP** | 1 | `x-browser-validation` header |
| **Tổng sai lệch** | **24/25** | **96% code cần viết lại** |

### 13.3. Khuyến nghị Cập nhật Code

1. **Sửa `ProjectManager`**: Thay `create_project()` bằng TRPC call đến `project.createProject`
2. **Viết lại `api_client.py` - Hỗ trợ Đa Chế độ**:
    - **TRPC Client**: Cookies + JSON cho project/settings/history endpoints
    - **REST Client**: `x-browser-*` + `x-client-data` cho mọi REST; API Key chỉ cho GET + checkApp; reCAPTCHA payload cho generate/upscale
    - **Recaptcha Client**: Browser automation để lấy token từ `reload` → parse `["rresp","token"]`
3. **Bổ sung endpoints**: Credits, Availability, Upsample (Video+Image), GIF, StartImage, StartAndEndImage, **ReferenceImages (R2V)**
4. **Implement Polling State Machine**: PENDING→ACTIVE→SUCCESSFUL, check `remainingCredits` để biết hoàn thành
5. **Loại bỏ hoàn toàn**: `Authorization: Bearer` header và `x-goog-recaptcha-token` header
6. **Implement Sequential Upscale**: Mỗi video upscale cần token reCAPTCHA mới, submit tuần tự
7. **Implement Download Flow**: STORAGE download + submitBatchLog(DOWNLOAD) ghép cặp

---

> **Tài liệu này được tạo từ phân tích toàn diện 50 HAR files (15,527 dòng dữ liệu output)**
> **Bổ sung phân tích quan hệ, chuỗi phụ thuộc, ánh xạ luồng dữ liệu, và các phát hiện chi tiết**
