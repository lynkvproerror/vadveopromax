# VEO Web Client — Sơ đồ Hệ thống Quy trình

> **Nguồn dữ liệu**: [VEO_Web_Client_Protocol_Analysis.md](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/00%20-%20Documentation/VEO_Web_Client_Protocol_Analysis.md) — phân tích từ 53 HAR files thực tế.
> **Phong cách tham khảo**: [veo_master_execution_flow.png](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/00%20-%20Documentation/02_Architecture/diagrams/veo_master_execution_flow.png)

---

## Ký hiệu chung

| Ký hiệu | Ý nghĩa |
|:---:|---|
| 🍪 | **Cookie** — same-origin, browser tự gửi |
| 🔑 | **API Key** — query `?key=` hoặc header |
| 🛡️ | **Custom Headers** — 5 header `x-browser-*` + `x-client-data` |
| 🤖 | **reCAPTCHA Token** — trong payload `clientContext` |
| 🔗 | **Signed URL** — URL có chữ ký, tự xác thực |
| ⚡ | **Sync** — response trả kết quả ngay |
| ⏳ | **Async** — cần polling cho đến khi SUCCESSFUL |

---

## 1. TỔNG QUAN — Master Flow

```mermaid
flowchart TD
    START(("🔵 START"))

    subgraph PHASE1["🔐 PHASE 1: Đăng nhập & Khởi tạo"]
        A1["Mở labs.google/fx/tools/video-fx"]
        A2["Browser gửi Cookie 🍪 tự động"]
        A3["15+ API calls song song<br/>TRPC 🍪 + REST 🛡️ + AUTH 🍪"]
        A4(("✅ Session Ready"))
    end

    subgraph PHASE2["📁 PHASE 2: Tạo / Chọn Project"]
        B1["createProject hoặc getProject"]
        B2["Load scenes, settings, models"]
        B3(("✅ Project Ready"))
    end

    subgraph PHASE3["🎬 PHASE 3: Tạo Nội dung"]
        C0{"Loại nội dung?"}
        
        subgraph VIDEO["📹 VIDEO GENERATION"]
            direction TB
            C1{"Chế độ?"}
            C1T["T2V — Text Only"]
            C1I["I2V — Start Image"]
            C1F["F2V — Start+End"]
            C1R["R2V — 1-3 References"]
            C2["Upload ảnh nếu cần 🛡️"]
            C3["Get reCAPTCHA Token 🤖"]
            C4["Submit API 🛡️+🤖"]
            C5["Poll Status ⏳ ~6s/lần"]
            C6(("✅ Video 720p Ready"))
        end

        subgraph IMAGE["🖼️ IMAGE GENERATION"]
            direction TB
            D1{"Chế độ?"}
            D1T["T2I — Text Only"]
            D1I["I2I — Image Reference"]
            D2["Upload ảnh nếu I2I 🛡️"]
            D3["Get reCAPTCHA Token 🤖"]
            D4["batchGenerateImages ⚡<br/>Model: GEM_PIX_2"]
            D5(("✅ Image Ready"))
        end
    end

    subgraph PHASE4["⬆️ PHASE 4: Tính năng Hỗ trợ"]
        E0{"Cần nâng cấp?"}
        E1["Video Upscale ⏳<br/>720p → 1080p/4K"]
        E2["Image Upscale ⚡<br/>→ 2K/4K"]
        E3["Download ⬇️ 🔗"]
    end

    FINISH(("🔵 END"))

    START --> A1 --> A2 --> A3 --> A4
    A4 --> B1 --> B2 --> B3
    B3 --> C0
    C0 -->|Video| C1
    C0 -->|Ảnh| D1
    
    C1 --> C1T & C1I & C1F & C1R
    C1T & C1I & C1F & C1R --> C2 --> C3 --> C4 --> C5 --> C6
    
    D1 --> D1T & D1I
    D1T & D1I --> D2 --> D3 --> D4 --> D5
    
    C6 --> E0
    D5 --> E0
    E0 -->|Video Upscale| E1 --> E3
    E0 -->|Image Upscale| E2 --> E3
    E0 -->|Không| E3
    E3 --> FINISH

    style PHASE1 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style PHASE2 fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style PHASE3 fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style VIDEO fill:#e3f2fd,stroke:#1565c0
    style IMAGE fill:#e8f5e9,stroke:#2e7d32
    style PHASE4 fill:#fce4ec,stroke:#b71c1c,stroke-width:2px
```

---

## 2. ĐĂNG NHẬP & KHỞI TẠO SESSION

> **Trigger**: User mở/reload `labs.google/fx/tools/video-fx`
> **Auth**: Tất cả same-origin → Cookie tự động. Cross-site → Custom Headers.
> **Dữ liệu**: 3 HAR files

```mermaid
flowchart TD
    START(("🔵 START<br/>User mở trang"))
    
    subgraph STEP1["⚡ Bước 1 — Song song (cùng lúc)"]
        direction LR
        subgraph TRPC1["TRPC 🍪 Cookie"]
            T1["getProject"]
            T2["getFlowAppConfig"]
            T3["searchProjectScenes"]
            T4["fetchUserAcknowledgement"]
            T5["fetchUserLocale"]
            T6["submitBatchLog"]
        end
        subgraph REST1["REST 🛡️ Headers"]
            R1["GET credits 🔑+🛡️"]
            R2["fetchUserRecommendations"]
            R3["checkAppAvailability 🔑+🛡️"]
        end
        subgraph AUTH1["AUTH 🍪"]
            A1["GET auth/session<br/>→ ya29.* token"]
        end
    end
    
    subgraph STEP2["⚡ Bước 2 — Song song"]
        T7["getUserSettings 🍪"]
        T8["fetchUserPreferences 🍪"]
        T9["searchProjectWorkflows 🍪"]
        T10["getVideoModelConfig 🍪<br/>→ 30+ model keys"]
        T11["listPreambles 🍪"]
    end
    
    subgraph STEP3["⚡ Bước 3 — Song song"]
        T12["fetchUserHistoryDirectly 🍪<br/>→ phân trang"]
        T13["fetchFlowUserIngredients 🍪<br/>→ ảnh reference đã upload"]
    end
    
    READY(("✅ SESSION READY<br/>Tất cả data đã load"))

    START --> STEP1 --> STEP2 --> STEP3 --> READY

    style STEP1 fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style STEP2 fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style STEP3 fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style TRPC1 fill:#bbdefb,stroke:#1565c0
    style REST1 fill:#c8e6c9,stroke:#2e7d32
    style AUTH1 fill:#ffe0b2,stroke:#e65100
```

> [!IMPORTANT]
> **15+ API calls** gửi **song song** trong 3 đợt. Tất cả TRPC dùng Cookie (same-origin), REST dùng Custom Headers (cross-site). `getVideoModelConfig` trả về **30+ model keys** quan trọng cho bước generate.

---

## 3. TẠO PROJECT

> **Trigger**: User nhấn "New Project"
> **Auth**: Toàn bộ TRPC → Cookie only
> **Dữ liệu**: 1 HAR file

```mermaid
flowchart TD
    START(("🔵 Tạo Project"))
    
    S1["submitBatchLog 🍪<br/>Log sự kiện tạo project"]
    S2["createProject 🍪<br/>→ trả projectId mới"]
    
    subgraph PARALLEL["⚡ Load song song sau khi tạo"]
        S3["getProject 🍪"]
        S4["searchProjectScenes 🍪<br/>→ trống"]
        S5["fetchUserHistoryDirectly 🍪"]
        S6["getUserSettings 🍪"]
        S7["getVideoModelConfig 🍪"]
        S8["fetchUserPreferences 🍪"]
        S9["searchProjectWorkflows 🍪"]
        S10["listPreambles 🍪"]
    end

    READY(("✅ PROJECT READY<br/>projectId sẵn sàng"))

    START --> S1 --> S2 --> PARALLEL --> READY

    style PARALLEL fill:#fff3e0,stroke:#e65100,stroke-width:2px
```

> [!NOTE]
> **projectId** (UUID format: `a89ea3a4-168c-4133-8fb0-7a852f11b33b`) được trả về từ `createProject` và dùng xuyên suốt cho mọi API call sau đó — đặc biệt trong `clientContext.projectId` của các request generate.

---

## 4. TẠO VIDEO — 4 Chế độ Chi tiết

> **4 chế độ**: T2V, I2V, F2V, R2V — khác endpoint, model key, và payload fields
> **Auth**: Upload 🛡️ → reCAPTCHA 🤖 → Generate 🛡️+🤖 → Poll 🛡️
> **Dữ liệu**: 17 HAR files (2 T2V + 1 I2V + 8 F2V + 5 R2V + 1 mixed)

```mermaid
flowchart TD
    START(("🔵 Tạo Video"))
    
    MODE{"Chọn chế độ?"}
    
    subgraph T2V["🔤 T2V — Text-to-Video"]
        T2V_1["Nhập prompt text"]
        T2V_2["Endpoint: batchAsyncGenerateVideoText"]
        T2V_F["textInput.prompt ✅<br/>startImage ❌<br/>endImage ❌<br/>referenceImages ❌"]
    end
    
    subgraph I2V["🖼️ I2V — Image-to-Video Start"]
        I2V_1["Upload 1 ảnh → mediaId"]
        I2V_2["Nhập prompt"]
        I2V_3["Endpoint: ...StartImage"]
        I2V_F["textInput.prompt ✅<br/>startImage.mediaId ✅<br/>endImage ❌<br/>referenceImages ❌"]
    end
    
    subgraph F2V["🎞️ F2V — Frames Start+End"]
        F2V_1["Upload 2 ảnh → 2 mediaIds"]
        F2V_2["Nhập prompt"]
        F2V_3["Endpoint: ...StartAndEndImage"]
        F2V_F["textInput.prompt ✅<br/>startImage.mediaId ✅<br/>endImage.mediaId ✅<br/>referenceImages ❌"]
    end
    
    subgraph R2V["🎨 R2V — Reference Images"]
        R2V_1["Upload 1-3 ảnh<br/>→ 1-3 mediaIds"]
        R2V_2["Nhập prompt"]
        R2V_3["Endpoint: ...ReferenceImages"]
        R2V_F["textInput.prompt ✅<br/>startImage ❌<br/>endImage ❌<br/>referenceImages[1-3] ✅"]
    end
    
    RECAP["Get reCAPTCHA Token 🤖<br/>recaptcha/enterprise/reload"]
    
    SUBMIT["Submit Generate API<br/>🛡️ Custom Headers + 🤖 reCAPTCHA<br/>clientContext: projectId + PINHOLE + PAYGATE_TIER_TWO"]
    
    subgraph POLLING["⏳ Polling Loop"]
        POLL["batchCheckAsyncVideoGenerationStatus 🛡️<br/>Gửi mỗi ~6 giây"]
        STATUS{"Status?"}
        PENDING["PENDING"]
        ACTIVE["ACTIVE"]
        SUCCESS["SUCCESSFUL ✅<br/>→ fifeUrl, servingBaseUri,<br/>model, isLooped, seed"]
    end
    
    VIDEO_READY(("✅ Video 720p Ready"))

    START --> MODE
    MODE -->|"Text only"| T2V_1 --> T2V_2 --> T2V_F --> RECAP
    MODE -->|"1 ảnh đầu"| I2V_1 --> I2V_2 --> I2V_3 --> I2V_F --> RECAP
    MODE -->|"2 frames"| F2V_1 --> F2V_2 --> F2V_3 --> F2V_F --> RECAP
    MODE -->|"1-3 references"| R2V_1 --> R2V_2 --> R2V_3 --> R2V_F --> RECAP
    
    RECAP --> SUBMIT --> POLL
    POLL --> STATUS
    STATUS -->|PENDING| PENDING --> POLL
    STATUS -->|ACTIVE| ACTIVE --> POLL
    STATUS -->|SUCCESSFUL| SUCCESS --> VIDEO_READY

    style T2V fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style I2V fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style F2V fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style R2V fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style POLLING fill:#fce4ec,stroke:#b71c1c,stroke-width:2px
```

### Bảng phân biệt 4 chế độ Video

| | T2V | I2V | F2V | R2V |
|---|:---:|:---:|:---:|:---:|
| **Endpoint** | `...VideoText` | `...StartImage` | `...StartAndEndImage` | `...ReferenceImages` |
| **Model key** | `t2v_*` | `i2v_s_*` (no `_fl_`) | `i2v_s_*_fl_*` | `r2v_*` |
| **textInput.prompt** | ✅ | ✅ | ✅ | ✅ |
| **startImage** | ❌ | ✅ | ✅ | ❌ |
| **endImage** | ❌ | ❌ | ✅ | ❌ |
| **referenceImages** | ❌ | ❌ | ❌ | ✅ (1-3) |
| **Upload cần?** | ❌ | 1 ảnh | 2 ảnh | 1-3 ảnh |
| **Response type** | ⏳ Async | ⏳ Async | ⏳ Async | ⏳ Async |
| **HAR calls** | 2 | 1 | 8 | 5 |

> [!TIP]
> **Cách phân biệt I2V vs F2V bằng model key**: Cùng prefix `i2v_s_` nhưng F2V có thêm `_fl_` (First+Last). Ví dụ:
> - I2V: `veo_3_1_i2v_s_fast_ultra_relaxed`
> - F2V: `veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed`

### clientContext — Cấu trúc payload chung cho Video

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA5...",
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
    "textInput": { "prompt": "..." },
    "videoModelKey": "veo_3_1_t2v_fast_portrait_ultra_relaxed",
    "startImage": { "mediaId": "..." },
    "endImage": { "mediaId": "..." },
    "referenceImages": [{ "imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": "..." }],
    "metadata": { "sceneId": "..." }
  }]
}
```

> Mỗi chế độ chỉ gửi các trường tương ứng — xem bảng phân biệt ở trên.

---

## 5. TẠO ẢNH — T2I & I2I

> **2 chế độ**: T2I (text only), I2I (text + image reference)
> **Model**: `GEM_PIX_2` (Google Imagen) — **KHÔNG phải VEO**
> **Response**: ⚡ **Sync** — trả kết quả ngay, không cần polling
> **Dữ liệu**: 5 HAR files (8 I2I calls, 0 T2I calls)

```mermaid
flowchart TD
    START(("🔵 Tạo Ảnh"))
    
    MODE{"Chế độ?"}
    
    subgraph T2I["🔤 T2I — Text-to-Image"]
        T2I_1["Nhập prompt text"]
        T2I_N["Không có imageInputs<br/>Chưa có trong HAR data"]
    end
    
    subgraph I2I["🖼️ I2I — Image-to-Image"]
        I2I_1["Upload ảnh reference 🛡️<br/>→ nhận mediaId"]
        I2I_2["Nhập prompt"]
        I2I_3["imageInputs: name + type<br/>IMAGE_INPUT_TYPE_REFERENCE"]
    end

    RECAP["Get reCAPTCHA Token 🤖"]
    
    SUBMIT["batchGenerateImages ⚡<br/>🛡️ + 🤖<br/>Model: GEM_PIX_2<br/>clientContext: projectId + PINHOLE"]

    subgraph RESULT["📸 Kết quả (Sync)"]
        RES1["fifeUrl → download ảnh"]
        RES2["seed, dimensions"]
        RES3["prompt tiếng Anh<br/>→ server tự dịch!"]
    end

    READY(("✅ Image Ready"))

    START --> MODE
    MODE -->|"Text only"| T2I_1 --> T2I_N --> RECAP
    MODE -->|"Image ref"| I2I_1 --> I2I_2 --> I2I_3 --> RECAP
    RECAP --> SUBMIT --> RESULT --> READY

    style T2I fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style I2I fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style RESULT fill:#fff9c4,stroke:#f9a825,stroke-width:2px
```

### Khác biệt so với Video Generation

| Đặc điểm | Video (VEO) | Ảnh (Imagen) |
|---|---|---|
| **Model** | `veo_3_1_*` | `GEM_PIX_2` |
| **Engine** | VEO | Google Imagen |
| **Response** | ⏳ Async (polling) | ⚡ Sync (ngay lập tức) |
| **userPaygateTier** | ✅ Gửi | ❌ Không gửi |
| **Download URL** | `fifeUrl` → video MP4 | `fifeUrl` → ảnh |
| **Prompt translation** | Chưa xác nhận | ✅ Server tự dịch sang EN |

### I2I Request payload

```json
{
  "clientContext": {
    "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
    "sessionId": ";...",
    "projectId": "daba1978-...",
    "tool": "PINHOLE"
  },
  "requests": [{
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

> [!WARNING]
> **Không có `userPaygateTier`** trong clientContext ảnh — khác với video! Upload ảnh dùng `tool: "ASSET_MANAGER"`, còn generate dùng `tool: "PINHOLE"`.

---

## 6. TÍNH NĂNG HỖ TRỢ

> **Không phải chế độ tạo nội dung** — là các utility hỗ trợ sau khi tạo xong.

```mermaid
flowchart TD
    subgraph UPVID["⬆️ Video Upscale (720p → 1080p/4K)"]
        direction TB
        UV1["Video 720p đã tạo"]
        UV2["Get reCAPTCHA Token 🤖"]
        UV3["batchAsyncGenerateVideoUpsampleVideo ⏳<br/>🛡️ + 🤖<br/>Model: veo_3_1_upsampler_1080p"]
        UV4["Poll Status ~6s"]
        UV5["Video 1080p/4K Ready ✅"]
        UV1 --> UV2 --> UV3 --> UV4 --> UV5
    end

    subgraph UPIMG["⬆️ Image Upscale (→ 2K/4K)"]
        direction TB
        UI1["Ảnh đã tạo"]
        UI2["Get reCAPTCHA Token 🤖"]
        UI3["upsampleImage ⚡<br/>🛡️ + 🤖<br/>targetResolution: 2K or 4K"]
        UI4["encodedImage base64 ✅"]
        UI1 --> UI2 --> UI3 --> UI4
    end

    subgraph UPLOAD["📤 Upload Image"]
        direction TB
        UL1["User chọn ảnh"]
        UL2["uploadUserImage 🛡️<br/>tool: ASSET_MANAGER"]
        UL3["→ mediaId<br/>Dùng cho I2V/F2V/R2V/I2I"]
        UL1 --> UL2 --> UL3
    end

    subgraph DOWNLOAD["⬇️ Download"]
        direction TB
        DL0{"Loại?"}
        DL1["Video MP4<br/>GET Signed URL 🔗+🛡️<br/>storage.googleapis.com"]
        DL2["GIF Preview<br/>generatePinholeGif 🛡️<br/>Không cần reCAPTCHA"]
        DL3["Ảnh<br/>GET fifeUrl 🔗"]
        DL0 -->|Video| DL1
        DL0 -->|GIF| DL2
        DL0 -->|Ảnh| DL3
    end
    
    style UPVID fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style UPIMG fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style UPLOAD fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style DOWNLOAD fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
```

### Bảng clientContext theo tính năng

> clientContext khác nhau tùy tính năng — cần gửi đúng fields!

| Trường | Video Gen | Image Gen | Video Upscale | Image Upscale | Upload |
|---|:---:|:---:|:---:|:---:|:---:|
| `projectId` | ✅ | ✅ | ❌ | ✅ | ❌ |
| `tool` | `PINHOLE` | `PINHOLE` | ❌ | `PINHOLE` | `ASSET_MANAGER` |
| `userPaygateTier` | ✅ `TIER_TWO` | ❌ | ❌ | ❌ | ❌ |
| `recaptchaContext` | ✅ | ✅ | ✅ | ✅ | ❌ |
| `sessionId` | ✅ | ✅ | ✅ | ✅ | ✅ |

> [!CAUTION]
> **Video Upscale** có `clientContext` **thu gọn nhất** — chỉ `sessionId` + reCAPTCHA. Không có `projectId`, `tool`, hay `userPaygateTier`. Gửi sai sẽ bị reject.

---

## Tổng hợp Endpoints

| Quy trình | Endpoint | Protocol | Auth | Response |
|---|---|---|---|---|
| **Session Init** | TRPC calls, REST calls | TRPC + REST | 🍪 + 🛡️ | ⚡ Sync |
| **Create Project** | `createProject` | TRPC | 🍪 | ⚡ Sync |
| **T2V** | `batchAsyncGenerateVideoText` | REST | 🛡️+🤖 | ⏳ Async |
| **I2V** | `batchAsyncGenerateVideoStartImage` | REST | 🛡️+🤖 | ⏳ Async |
| **F2V** | `batchAsyncGenerateVideoStartAndEndImage` | REST | 🛡️+🤖 | ⏳ Async |
| **R2V** | `batchAsyncGenerateVideoReferenceImages` | REST | 🛡️+🤖 | ⏳ Async |
| **T2I / I2I** | `batchGenerateImages` | REST | 🛡️+🤖 | ⚡ Sync |
| **Video Upscale** | `batchAsyncGenerateVideoUpsampleVideo` | REST | 🛡️+🤖 | ⏳ Async |
| **Image Upscale** | `upsampleImage` | REST | 🛡️+🤖 | ⚡ Sync |
| **Upload** | `uploadUserImage` | REST | 🛡️ | ⚡ Sync |
| **Poll Status** | `batchCheckAsyncVideoGenerationStatus` | REST | 🛡️ | ⚡ Sync |
| **Download Video** | `GET storage.googleapis.com/...` | STORAGE | 🛡️+🔗 | ⚡ Sync |
| **GIF Preview** | `generatePinholeGif` | REST | 🛡️ | ⚡ Sync |

---

> **Cập nhật**: 2026-02-08 | **Nguồn**: 53 HAR files (51 ban đầu + 2 T2V mới)
