# VEO Web Client — Complete API Protocol Analysis

> **Source**: Exhaustive analysis of **50 HAR files** from `F12 Dev\New`  
> **Script**: `full_har_analysis.py` → `full_har_analysis_output.txt` (15,527 lines)  
> **Date**: 2026-02-08

---

## Summary Statistics

| Metric | Value |
|---|---|
| HAR files processed | 50 |
| Unique API endpoints | 74 |
| Unique model keys | 72 |
| Project IDs observed | 4 |
| Session IDs observed | 11 |
| Total credit readings | 82 |
| Total polling requests | 721 |
| Files with polling | 21 |
| Error responses | 1 |
| Endpoint categories | AUTH (1), TRPC (21), REST (51), RECAPTCHA (2), STORAGE (1) |

---

## 1. API Domains & Headers

### 1.1 Domains

| Domain | Purpose | Content-Types |
|---|---|---|
| `aisandbox-pa.googleapis.com` | Primary REST API (video gen, image upload, credits, polling) | `text/plain;charset=UTF-8`, none |
| `labs.google` | TRPC API (project mgmt, media history, settings, logging) | `application/json` |
| `www.google.com` | reCAPTCHA Enterprise | `application/x-protobuffer`, none |
| `storage.googleapis.com` | Cloud Storage (video file downloads) | none |

### 1.2 Common Headers (All Domains)

All requests to `aisandbox-pa.googleapis.com` include:

```
:authority: aisandbox-pa.googleapis.com
content-type: text/plain;charset=UTF-8   (for POST)
origin: https://labs.google
referer: https://labs.google/
sec-fetch-mode: cors
sec-fetch-site: cross-site
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: <hashed_value>       ← Changes between sessions
x-browser-year: 2026
x-client-data: <base64_encoded>            ← Changes between sessions
```

> **CRITICAL**: No `Authorization: Bearer` header is used for REST API calls. Authentication is handled entirely via **cookies** and **reCAPTCHA tokens** embedded in payloads.

### 1.3 TRPC Headers

```
:authority: labs.google
content-type: application/json
```

TRPC calls have diverse `referer` values matching the current page:
- `https://labs.google/fx/tools/flow`
- `https://labs.google/fx/tools/flow/project/{projectId}`
- `https://labs.google/fx/tools/whisk`

---

## 2. Authentication

### 2.1 Session Endpoint

**`AUTH:/fx/api/auth/session`** — `GET` → HTTP 200

Response:
```json
{
    "user": {
        "name": "Veo Ultra",
        "email": "ultra8574632@tk.solsticeenergyvn.com",
        "image": "https://lh3.googleusercontent.com/a/ACg8ocJX..."
    },
    "expires": "2026-02-07T03:37:45.000Z",
    "access_token": "ya29.a0AUMWg_..."
}
```

> **NOTE**: The `access_token` in the session response is a Google OAuth token (ya29.*) but it is **NOT** sent as a Bearer header in REST API calls. It is used internally by the TRPC layer.

### 2.2 reCAPTCHA Enterprise

**Site Key**: `6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV`

Two endpoints:

| Endpoint | Occurrences | Purpose |
|---|---|---|
| `RECAPTCHA:/recaptcha/enterprise/reload` | 61 | Request new reCAPTCHA token |
| `RECAPTCHA:/recaptcha/enterprise/clr` | 62 | Client-side reCAPTCHA logging |

**Token flow**:
1. Client calls `/recaptcha/enterprise/reload` to get a token
2. Token is embedded in `clientContext.recaptchaContext.token` of REST API payloads
3. Token is ~1700-2500 chars long

**reCAPTCHA context in payloads**:
```json
{
    "clientContext": {
        "recaptchaContext": {
            "token": "0cAFcWeA5T6Org6Awo...(~1742 chars)",
            "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
        }
    }
}
```

---

## 3. Complete Endpoint Catalog

### 3.1 AUTH Endpoints (1)

| Endpoint | Method | Purpose |
|---|---|---|
| `/fx/api/auth/session` | GET | Fetch user session + access token |

### 3.2 TRPC Endpoints (21)

All TRPC calls go to `labs.google` with `application/json` content type.

| Endpoint | Method | Purpose |
|---|---|---|
| `general.fetchFeatureAvailability` | GET | Check feature flags (WHISK_R2I, etc.) |
| `general.fetchToolAvailability` | GET | Check tool availability state |
| `general.fetchUserAcknowledgement` | GET | Check if user acknowledged terms |
| `general.fetchUserLocale` | GET | Get user locale setting |
| `general.fetchUserPreferences` | GET | Get user preferences (enableHistory) |
| `general.reportClientSideError` | POST | Report client-side errors |
| `general.submitBatchLog` | POST | Submit analytics/telemetry events |
| `media.fetchFlowUserIngredients` | GET | Fetch user's uploaded ingredients (reference images) |
| `media.fetchUserHistoryDirectly` | GET | Fetch user's generation history (paginated) |
| `project.createProject` | POST | Create new Flow project |
| `project.getProject` | GET | Get project details |
| `project.searchProjectScenes` | GET | Search scenes within a project |
| `project.searchProjectWorkflows` | GET | Search workflows within a project |
| `videoFx.getFlowAppConfig` | GET | Get Flow app configuration |
| `videoFx.getUserSettings` | GET | Get user settings (model key, aspect ratio) |
| `videoFx.getVideoModelConfig` | GET | Get video model configuration (all model keys) |
| `videoFx.listPreambles` | GET | List available prompt preambles |
| `videoFx.setLastSelectedVideoAspectRatio` | POST | Save selected aspect ratio |
| `videoFx.setLastSelectedVideoModelKey` | POST | Save selected model key |
| `whisk.getRecentMedia` | GET | Get Whisk recent media |
| `whisk.getWhiskRecentMediaGroupIds` | GET | Get Whisk media group IDs |

**TRPC Response Structure** (all endpoints):
```json
{
    "result": {
        "data": {
            "json": {
                "result": { /* endpoint-specific data */ },
                "status": 200,
                "statusText": "OK"
            }
        }
    }
}
```

**submitBatchLog Event Types Observed**:
- `PAGE_VIEW`
- `PINHOLE_UPLOAD_IMAGE`
- `PINHOLE_UPLOAD_IMAGE_TO_CROP`
- `PINHOLE_RESIZE_IMAGE`
- `PINHOLE_CROP_IMAGE`
- `PINHOLE_GENERATE_IMAGE`
- `PINHOLE_GENERATE_VIDEO`
- `PINHOLE_GENERATE_VIDEO_ERROR`
- `PINHOLE_UPSCALE_IMAGE`
- `VIDEOFX_CREATE_VIDEO`
- `VIDEO_CREATION_TO_VIDEO_COMPLETION`
- `DOWNLOAD`

### 3.3 REST Endpoints (51)

All REST calls go to `aisandbox-pa.googleapis.com`.

#### Video Generation

| Endpoint | Method | Occurrences | Purpose |
|---|---|---|---|
| `/v1/video:batchAsyncGenerateVideo` | POST | 16 | Text-to-Video generation |
| `/v1/video:batchAsyncGenerateVideoStartImage` | POST | 1 | Image-to-Video (start frame) |
| `/v1/video:batchAsyncGenerateVideoStartAndEndImage` | POST | 8 | Image-to-Video (start + end frames) |
| `/v1/video:batchAsyncGenerateVideoReshoot` | POST | 5 | Reshoot video |
| `/v1/video:batchAsyncGenerateVideoExtendVideo` | POST | 2 | Extend video duration |
| `/v1/video:batchAsyncGenerateVideoReferenceImages` | POST | 5 | Reference-to-Video (R2V) generation |
| `/v1/video:batchAsyncGenerateVideoUpsampleVideo` | POST | 32 | Upscale video (1080p/4K) |
| `/v1/video:batchCheckAsyncVideoGenerationStatus` | POST | 721 | Poll generation status |

#### Image Generation

| Endpoint | Method | Occurrences | Purpose |
|---|---|---|---|
| `/v1/projects/{UUID}/flowMedia:batchGenerateImages` | POST | 2 | Generate images (within project) |
| `/v1:uploadUserImage` | POST | 23 | Upload user image |
| `/v1/flow/upsampleImage` | POST | 4 | Upscale image |

#### Media & Credits

| Endpoint | Method | Occurrences | Purpose |
|---|---|---|---|
| `/v1/media/{MEDIA_ID}` | GET | many | Fetch media data (images/videos) |
| `/v1/credits` | GET | 5 | Check remaining credits |
| `/v1/whisk:getVideoCreditStatus` | POST | 9 | Get Whisk credit status |
| `/v1:checkAppAvailability` | POST | 2 | Check if app is available |
| `/v1:fetchUserRecommendations` | POST | 2 | Fetch upgrade recommendations |

#### Whisk-Specific Media Endpoints

50+ individual media endpoints observed in Whisk HAR files (e.g., `/v1/media/03gr5ab4k0000`). These use **short alphanumeric IDs** instead of the Base64-encoded media IDs used by Flow.

---

## 4. Video Generation Payloads

### 4.1 Text-to-Video (`batchAsyncGenerateVideo`)

```json
{
    "clientContext": {
        "recaptchaContext": {
            "token": "...(~1742 chars)",
            "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
        },
        "sessionId": ";1769888782642",
        "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_TWO"
    },
    "requests": [
        {
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "seed": 15456,
            "textInput": {
                "prompt": "Your prompt text here"
            },
            "videoModelKey": "veo_3_1_t2v_fast_portrait_ultra_relaxed",
            "metadata": {
                "sceneId": "uuid-here"
            }
        }
        /* ... typically 4 requests per batch */
    ]
}
```

### 4.2 Image-to-Video with Start Frame (`batchAsyncGenerateVideoStartImage`)

```json
{
    "requests": [
        {
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "seed": 15456,
            "textInput": { "prompt": "..." },
            "videoModelKey": "veo_3_1_i2v_s_fast_ultra_relaxed",
            "startImage": {
                "mediaId": "CAMaJDY2NGQ2Y2VkLTll..."
            },
            "metadata": { "sceneId": "uuid-here" }
        }
    ]
}
```

### 4.3 Image-to-Video with Start+End Frames (`batchAsyncGenerateVideoStartAndEndImage`)

```json
{
    "requests": [
        {
            "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
            "seed": 11386,
            "textInput": { "prompt": "..." },
            "videoModelKey": "veo_3_1_i2v_s_fast_fl_ultra_relaxed",
            "startImage": { "mediaId": "CAMaJGM3ZTdkODY4..." },
            "endImage": { "mediaId": "CAMaJDMzODBkZTVj..." },
            "metadata": { "sceneId": "uuid-here" }
        }
    ]
}
```

### 4.4 Upscale Video (`batchAsyncGenerateVideoUpsampleVideo`)

```json
{
    "requests": [
        {
            "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
            "resolution": "VIDEO_RESOLUTION_1080P",
            "seed": 18779,
            "videoInput": {
                "mediaId": "CAUSJDRmZDdmYjcyLTc5MGIt..."
            },
            "videoModelKey": "veo_3_1_upsampler_1080p",
            "metadata": { "sceneId": "uuid-here" }
        }
    ],
    "clientContext": {
        "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
        "sessionId": ";1769969107327"
    }
}
```

> **NOTE**: Upscale `clientContext` does NOT include `projectId` or `tool` fields.

### 4.5 Generation Response

```json
{
    "operations": [
        {
            "operation": { "name": "hex32-operation-id" },
            "sceneId": "uuid-scene-id",
            "status": "MEDIA_GENERATION_STATUS_PENDING"
        }
    ],
    "remainingCredits": 44990
}
```

**Upscale Response** additionally includes:
```json
{
    "workflows": [
        {
            "metadata": {
                "createTime": "2026-02-01T23:23:14.782856Z",
                "primaryMediaId": "operation-id_upsampled",
                "batchId": "uuid"
            },
            "projectId": "uuid"
        }
    ],
    "media": [
        {
            "name": "operation-id_upsampled",
            "workflowStepId": "CAE",
            "mediaMetadata": {
                "mediaStatus": {
                    "mediaGenerationStatus": "MEDIA_GENERATION_STATUS_PENDING"
                }
            },
            "sceneId": "uuid"
        }
    ]
}
```

---

## 5. Image Operations

### 5.1 Upload Image (`/v1:uploadUserImage`)

```json
{
    "imageInput": {
        "rawImageBytes": "/9j/4AAQSkZ...(base64 JPEG)",
        "mimeType": "image/jpeg",
        "isUserUploaded": true,
        "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"
    },
    "clientContext": {
        "sessionId": ";1769888782642",
        "tool": "ASSET_MANAGER"
    }
}
```

Response:
```json
{
    "mediaGenerationId": {
        "mediaGenerationId": "CAMaJDY2NGQ2Y2VkL..."
    },
    "width": 1920,
    "height": 1080
}
```

### 5.2 Generate Images (`/v1/projects/{UUID}/flowMedia:batchGenerateImages`)

```json
{
    "clientContext": {
        "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
        "sessionId": ";1769814594643",
        "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
        "tool": "PINHOLE"
    }
}
```

### 5.3 Upscale Image (`/v1/flow/upsampleImage`)

```json
{
    "mediaId": "CAMSJGY1ZGIxMzQyLWM2NzYt...",
    "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_4K",
    "clientContext": {
        "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
        "sessionId": ";1769817646087"
    }
}
```

Response:
```json
{
    "encodedImage": "/9j/4AAQSkZ...(base64, ~7.5MB for 4K)"
}
```

---

## 6. Polling Mechanism

### 6.1 Status Endpoint

**`/v1/video:batchCheckAsyncVideoGenerationStatus`** — POST

**Request**: Echo the operations from the generation response
```json
{
    "operations": [
        {
            "operation": { "name": "operation-id" },
            "sceneId": "scene-uuid",
            "status": "MEDIA_GENERATION_STATUS_PENDING"
        }
    ]
}
```

### 6.2 Status State Machine

```
PENDING → ACTIVE → SUCCESSFUL
                 → FAILED (not observed)
```

**State transitions observed**:
1. Initial submission returns `MEDIA_GENERATION_STATUS_PENDING`
2. First poll typically shows `MEDIA_GENERATION_STATUS_ACTIVE`
3. Individual operations complete at different times (partial completion is normal)
4. `remainingCredits` appears ONLY when ALL operations reach `SUCCESSFUL`

### 6.3 Successful Response (Complete)

When all operations succeed:
```json
{
    "operations": [
        {
            "operation": {
                "name": "operation-id",
                "metadata": {
                    "@type": "type.googleapis.com/google.internal.labs.aisandbox.v1.Media",
                    "name": "CAUS...(base64 media ID)",
                    "video": {
                        "seed": "...",
                        "mediaGenerationId": "...",
                        "prompt": "...",
                        "fifeUrl": "...",
                        "mediaVisibility": "...",
                        "servingBaseUri": "...",
                        "model": "...",
                        "isLooped": "...",
                        "aspectRatio": "..."
                    }
                }
            },
            "sceneId": "uuid",
            "mediaGenerationId": "CAUS...",
            "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL"
        }
    ],
    "remainingCredits": 43930
}
```

### 6.4 Polling Statistics

| File | Polls | Notes |
|---|---|---|
| Standard video gen (4 videos) | 4-16 | Completes relatively fast |
| 1080p upscale (1 video) | 33-47 | ~33 polls to first completion |
| 4K upscale (4 videos) | 253 | Longest observed, sequential completion |
| Incomplete captures | 1-10 | Still in ACTIVE at capture end |

**Key Pattern**: During upscale polling, responses show **interleaved completion**:
- Poll 33: ACTIVE → SUCCESSFUL (video 1 done, `remainingCredits` appears)
- Poll 34: SUCCESSFUL → ACTIVE (new upscale started)
- Poll 36: ACTIVE → SUCCESSFUL (video 2 done)
- Pattern repeats for each video

---

## 7. Credit System

### 7.1 Credit Endpoints

| Endpoint | Context | Response |
|---|---|---|
| `GET /v1/credits` | Flow app | `{"credits": 43930, "userPaygateTier": "PAYGATE_TIER_TWO", "sku": "WS_ULTRA"}` |
| `POST /v1/whisk:getVideoCreditStatus` | Whisk app | `{"credits": 44890, "g1MembershipState": "AVAILABLE_CREDITS", "isUserAnimateCountryEnabled": true, "userPaygateTier": "PAYGATE_TIER_TWO", "isGemPix2CreditAvailable": false}` |

### 7.2 Credit Values Observed (Chronological)

| Credits | Context |
|---|---|
| 45000 | Full Ultra account (Check Ultra.har) |
| 44990 | After video gen submission |
| 44940 | After upscale |
| 44890 | After multiple operations |
| 44130 | After downloads + upscales |
| 44080-43930 | Progressive 4K upscale costs |
| 50 | Nearly depleted account |

**Cost observations**:
- Video generation: ~10 credits per video
- 1080p upscale: ~50 credits per video
- 4K upscale: ~50 credits per video
- Image operations: appear to be free or very low cost

### 7.3 Tier Information

- `userPaygateTier`: `"PAYGATE_TIER_TWO"` (Ultra subscription)
- `sku`: `"WS_ULTRA"`
- `serviceTier`: `"SERVICE_TIER_ADVANCED"` (seen in whisk credit response)

---

## 8. Model Keys (72 Unique)

### 8.1 VEO 2.x Models

| Key | Type |
|---|---|
| `veo_2_0_t2v` | Text-to-Video |
| `veo_2_0_i2v` | Image-to-Video |
| `veo_2_0_object_insertion_landscape` | Object insertion |
| `veo_2_0_object_insertion_portrait` | Object insertion |
| `veo_2_0_object_removal_landscape` | Object removal |
| `veo_2_0_object_removal_portrait` | Object removal |
| `veo_2_1_fast_d_15_t2v` | Text-to-Video (fast) |
| `veo_2_1_fast_d_15_i2v` | Image-to-Video (fast) |
| `veo_2_1_fast_d_15_with_start_image_and_end_image_interpolation` | Interpolation |
| `veo_2_1_fast_d_15_with_video_extension` | Video extension |
| `veo_2_1080p_upsampler_8s` | 1080p upsampler |
| `veo_2_camera_control` | Camera control |
| `veo_2_r2v` | Reference-to-Video |
| `veo_2_r2v_fast` | Reference-to-Video (fast) |

### 8.2 VEO 3.0 Models

| Key | Type |
|---|---|
| `veo_3_0_t2v` | Text-to-Video |
| `veo_3_0_t2v_fast` | T2V fast |
| `veo_3_0_t2v_fast_portrait` | T2V fast portrait |
| `veo_3_0_t2v_fast_portrait_ultra` | T2V fast portrait ultra |
| `veo_3_0_t2v_fast_ultra` | T2V fast ultra |
| `veo_3_0_t2v_portrait` | T2V portrait |
| `veo_3_0_t2v_pro` | T2V pro |
| `veo_3_0_r2v_fast` | R2V fast |
| `veo_3_0_r2v_fast_ultra` | R2V fast ultra |
| `veo_3_0_r2v_fast_ultra_relaxed` | R2V fast ultra relaxed |
| `veo_3_0_reshoot_landscape` | Reshoot landscape |
| `veo_3_0_reshoot_portrait` | Reshoot portrait |

### 8.3 VEO 3.1 Models

| Key | Type |
|---|---|
| `veo_3_1_t2v` | T2V |
| `veo_3_1_t2v_fast` | T2V fast |
| `veo_3_1_t2v_fast_portrait` | T2V fast portrait |
| `veo_3_1_t2v_fast_portrait_ultra` | T2V fast portrait ultra ★ |
| `veo_3_1_t2v_fast_portrait_ultra_relaxed` | T2V fast portrait ultra relaxed ★★ |
| `veo_3_1_t2v_fast_ultra` | T2V fast ultra |
| `veo_3_1_t2v_fast_ultra_relaxed` | T2V fast ultra relaxed |
| `veo_3_1_t2v_portrait` | T2V portrait |
| `veo_3_1_i2v_s` | I2V start |
| `veo_3_1_i2v_s_fast` | I2V start fast |
| `veo_3_1_i2v_s_fast_fl` | I2V start fast (first+last) |
| `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | I2V start fast FL ultra relaxed ★ |
| `veo_3_1_i2v_s_fast_portrait` | I2V start fast portrait |
| `veo_3_1_i2v_s_fast_portrait_fl` | I2V start fast portrait FL |
| `veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed` | I2V start fast portrait FL ultra relaxed |
| `veo_3_1_i2v_s_fast_portrait_ultra` | I2V start fast portrait ultra |
| `veo_3_1_i2v_s_fast_portrait_ultra_fl` | I2V start fast portrait ultra FL |
| `veo_3_1_i2v_s_fast_portrait_ultra_relaxed` | I2V start fast portrait ultra relaxed |
| `veo_3_1_i2v_s_fast_ultra` | I2V start fast ultra |
| `veo_3_1_i2v_s_fast_ultra_fl` | I2V start fast ultra FL |
| `veo_3_1_i2v_s_fast_ultra_relaxed` | I2V start fast ultra relaxed ★ |
| `veo_3_1_i2v_s_fl` | I2V start FL |
| `veo_3_1_i2v_s_portrait` | I2V start portrait |
| `veo_3_1_i2v_s_portrait_fl` | I2V start portrait FL |
| `veo_3_1_r2v_fast_landscape` | R2V fast landscape |
| `veo_3_1_r2v_fast_landscape_ultra` | R2V fast landscape ultra ★ |
| `veo_3_1_r2v_fast_landscape_ultra_relaxed` | R2V fast landscape ultra relaxed |
| `veo_3_1_r2v_fast_portrait` | R2V fast portrait |
| `veo_3_1_r2v_fast_portrait_ultra` | R2V fast portrait ultra |
| `veo_3_1_r2v_fast_portrait_ultra_relaxed` | R2V fast portrait ultra relaxed ★ |
| `veo_3_1_extend_fast_landscape` | Extend fast landscape |
| `veo_3_1_extend_fast_landscape_ultra` | Extend fast landscape ultra |
| `veo_3_1_extend_fast_landscape_ultra_relaxed` | Extend fast landscape ultra relaxed |
| `veo_3_1_extend_fast_portrait` | Extend fast portrait |
| `veo_3_1_extend_fast_portrait_ultra` | Extend fast portrait ultra |
| `veo_3_1_extend_fast_portrait_ultra_relaxed` | Extend fast portrait ultra relaxed |
| `veo_3_1_extend_landscape` | Extend landscape |
| `veo_3_1_extend_portrait` | Extend portrait |
| `veo_3_1_upsampler_1080p` | 1080p upsampler ★ |
| `veo_3_1_upsampler_4k` | 4K upsampler ★ |

### 8.4 VEO 3 I2V (Legacy)

| Key | Type |
|---|---|
| `veo_3_i2v_s` | I2V start |
| `veo_3_i2v_s_fast` | I2V start fast |
| `veo_3_i2v_s_fast_portrait` | I2V start fast portrait |
| `veo_3_i2v_s_fast_portrait_ultra` | I2V start fast portrait ultra |
| `veo_3_i2v_s_fast_ultra` | I2V start fast ultra |
| `veo_3_i2v_s_portrait` | I2V start portrait |

> ★ = Observed in actual generation payloads across HAR files  
> ★★ = Most frequently used model key (11 HAR files)

### 8.5 Model Key Naming Pattern

```
veo_{major}_{minor}_{type}_{speed}_{orientation}_{tier}_{relaxed}
```

| Component | Values |
|---|---|
| major.minor | `2_0`, `2_1`, `3_0`, `3_1` |
| type | `t2v`, `i2v_s`, `r2v`, `extend`, `reshoot`, `upsampler`, `camera_control`, `object_insertion`, `object_removal` |
| speed | (none), `fast`, `pro` |
| orientation | (none=landscape), `portrait` |
| tier | (none), `ultra` |
| relaxed | (none), `relaxed` |
| fl | `fl` = first+last frame support |

---

## 9. Media IDs

### 9.1 ID Prefixes

| Prefix | Count | Context |
|---|---|---|
| `CAMa` | 10+ unique | Uploaded images |
| `CAMS` | 1+ unique | Generated images (from project) |
| `CAUS` | 2+ unique | Generated videos |

### 9.2 ID Structure

Media IDs are **Base64-encoded** strings containing:
- Workflow ID
- Step ID  
- Media key (UUID)

Example: `CAMaJDY2NGQ2Y2VkLTllMmUtNDUyOS04ZGM4LTcwMjhjZTM2OWRiZCIDQ0FFKiRlYzBkMTBlOC05ZTRhLTQ5ZWUtOGVlOC1kMWQ0MjJjNTQ3YTQ`

### 9.3 Whisk Media IDs

Whisk uses **short alphanumeric IDs**: `03gr5ab4k0000`, `075e6tu3i0000`, etc. These are used directly in URL paths: `/v1/media/03gr5ab4k0000`

---

## 10. Project & Session Management

### 10.1 Project IDs

| Project ID | Files |
|---|---|
| `daba1978-e588-4d76-a4fd-6c3126074187` | 6 files (project creation + generation) |
| `f5db1342-c676-437b-b763-d97ae2d7cd16` | 21 files (main working project) |
| `4fd7fb72-790b-4c3e-8cc1-2bfc3b4245e3` | 6 files (upscale + frame-to-video) |
| `909d317a-c45b-4033-b02a-03385848b986` | 1 file (ingredient-to-video) |

### 10.2 Session IDs

Session IDs have format `;{timestamp_ms}` (e.g., `;1769822770783`). 11 unique sessions observed.

### 10.3 Project Creation Flow

From `0. Tao Project.har`:
1. `POST project.createProject` — `{"json": {"projectTitle": "...", "toolName": "..."}}`
2. `GET project.getProject`
3. `GET project.searchProjectScenes`
4. `GET media.fetchUserHistoryDirectly`
5. `GET videoFx.getUserSettings`
6. `GET videoFx.getVideoModelConfig`
7. `GET general.fetchUserPreferences`
8. `GET project.searchProjectWorkflows`
9. `GET videoFx.listPreambles`

---

## 11. Aspect Ratios & Resolutions

### 11.1 Video Aspect Ratios

| Value | Description |
|---|---|
| `VIDEO_ASPECT_RATIO_LANDSCAPE` | 16:9 landscape |
| `VIDEO_ASPECT_RATIO_PORTRAIT` | 9:16 portrait |

### 11.2 Image Aspect Ratios

| Value | Description |
|---|---|
| `IMAGE_ASPECT_RATIO_LANDSCAPE` | Landscape |
| `IMAGE_ASPECT_RATIO_PORTRAIT` | Portrait |

### 11.3 Video Resolutions

| Value | Used With |
|---|---|
| `VIDEO_RESOLUTION_1080P` | `veo_3_1_upsampler_1080p` |
| (4K implied) | `veo_3_1_upsampler_4k` |

### 11.4 Image Resolutions

| Value | Used With |
|---|---|
| `UPSAMPLE_IMAGE_RESOLUTION_4K` | `/v1/flow/upsampleImage` |

---

## 12. Error Handling

### 12.1 Observed Error

Only 1 error response observed across all 50 HAR files:

**403 reCAPTCHA failure** on `batchAsyncGenerateVideoStartAndEndImage`:
```json
{
    "error": {
        "code": 403,
        "message": "reCAPTCHA evaluation failed",
        "status": "PERMISSION_DENIED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                "reason": "PUBLIC_ERROR_SOMETHING_WENT_WRONG"
            }
        ]
    }
}
```

**Client-side error reporting** after failure:
```json
// TRPC: general.reportClientSideError
{
    "json": {
        "message": "{\"json\":\"React Query\"} | {\"json\":{}}"
    }
}
```

Followed by:
```json
// TRPC: general.submitBatchLog  
{
    "json": {
        "appEvents": [{
            "event": "PINHOLE_GENERATE_VIDEO_ERROR",
            "eventProperties": [/* error details */]
        }]
    }
}
```

---

## 13. Complete Workflow Sequences

### 13.1 Full Video Generation Flow (Image-to-Video)

1. **Session Check** — `GET AUTH:/fx/api/auth/session`
2. **Load Project** — `GET TRPC:project.searchProjectScenes`
3. **Load History** — `GET TRPC:media.fetchUserHistoryDirectly` (multiple pages)
4. **Check Acknowledgement** — `GET TRPC:general.fetchUserAcknowledgement`
5. **Load Uploaded Images** — `GET REST:/v1/media/{MEDIA_ID}` (per image)
6. **Upload New Image** — `POST REST:/v1:uploadUserImage` (base64 JPEG)
7. **Log Upload Events** — `POST TRPC:general.submitBatchLog` (PINHOLE_UPLOAD_IMAGE, PINHOLE_RESIZE_IMAGE, PINHOLE_CROP_IMAGE)
8. **Set Aspect Ratio** — `POST TRPC:videoFx.setLastSelectedVideoAspectRatio`
9. **Get reCAPTCHA Token** — `POST RECAPTCHA:/recaptcha/enterprise/reload`
10. **Submit Generation** — `POST REST:/v1/video:batchAsyncGenerateVideo*`
11. **Log Generation** — `POST TRPC:general.submitBatchLog` (VIDEOFX_CREATE_VIDEO, PINHOLE_GENERATE_VIDEO)
12. **reCAPTCHA Logging** — `POST RECAPTCHA:/recaptcha/enterprise/clr`
13. **Poll Status** — `POST REST:/v1/video:batchCheckAsyncVideoGenerationStatus` (repeat ~every 5-10s)
14. **Generation Complete** — Response includes `remainingCredits` + `metadata` with media URLs

### 13.2 Upscale Flow

1. **Get reCAPTCHA Token** — `/recaptcha/enterprise/reload`
2. **Submit Upscale** — `POST /v1/video:batchAsyncGenerateVideoUpsampleVideo`
3. **Poll Status** — `POST /v1/video:batchCheckAsyncVideoGenerationStatus` (33-253 polls)
4. **Download** — `GET /ai-sandbox-videofx/video/{UUID}?GoogleAccessId=...&Expires=...&Signature=...`

### 13.3 Whisk App Flow

1. **Check Availability** — `POST /v1:checkAppAvailability` (tool: "PINHOLE")
2. **Load Features** — `GET TRPC:general.fetchFeatureAvailability`
3. **Session** — `GET AUTH:/fx/api/auth/session`
4. **Load Media Gallery** — `GET /v1/media/{short_id}` (many individual media items with encoded images/videos)
5. **Credit Check** — `POST /v1/whisk:getVideoCreditStatus`
6. **Recommendations** — `POST /v1:fetchUserRecommendations`
7. **App Config** — `GET TRPC:videoFx.getFlowAppConfig`

---

## 14. Video Download

### 14.1 Storage API

**`STORAGE:/ai-sandbox-videofx/video/{UUID}`** — GET

URL includes signed access:
```
/ai-sandbox-videofx/video/37776fce-83fc-4370-b67d-5e69f5a755df
?GoogleAccessId=labs-ai-sandbox-videoserver-prod@system.gserviceaccount.com
&Expires=1769...
&Signature=...
```

Response: Raw binary video data with C2PA content credentials (watermarking).

---

## 15. Key Differences: Flow vs Whisk

| Feature | Flow (PINHOLE) | Whisk |
|---|---|---|
| Tool name | `PINHOLE` | Not specified / implicit |
| Media IDs | Long Base64 (`CAMa...`, `CAUS...`) | Short alpha (`03gr5ab4k0000`) |
| Credit check | `GET /v1/credits` | `POST /v1/whisk:getVideoCreditStatus` |
| Project context | Uses `projectId` in payloads | No project context |
| History | `TRPC:media.fetchUserHistoryDirectly` | Direct media endpoint loads |
| Credit response | `{credits, userPaygateTier, sku}` | `{credits, g1MembershipState, isUserAnimateCountryEnabled, userPaygateTier, isGemPix2CreditAvailable}` |
| App config | `TRPC:videoFx.getUserSettings` | `TRPC:videoFx.getFlowAppConfig` |

---

## 16. clientContext Variations

| Field | Presence | Values |
|---|---|---|
| `recaptchaContext.token` | All generation endpoints | ~1700-2500 char token |
| `recaptchaContext.applicationType` | All generation endpoints | `"RECAPTCHA_APPLICATION_TYPE_WEB"` |
| `sessionId` | All endpoints with clientContext | `;{timestamp_ms}` |
| `projectId` | Video gen, image gen (NOT upscale) | UUID |
| `tool` | Video gen, image gen (NOT upscale) | `"PINHOLE"`, `"ASSET_MANAGER"` |
| `userPaygateTier` | Video gen (NOT upscale) | `"PAYGATE_TIER_TWO"` |

---

## 17. Endpoint Dependency Chains & Relationships

### 17.1 Master Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BROWSER SESSION (Cookie-based Auth)              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    access_token     ┌───────────────────────┐    │
│  │ AUTH:session  │ ─────────────────→  │ TRPC Layer (labs.google)│   │
│  │ (ya29.* token)│                     │ Uses token internally   │   │
│  └──────────────┘                     └───────────────────────┘    │
│         │                                      │                    │
│         │ cookies only                         │ TRPC calls         │
│         ▼                                      ▼                    │
│  ┌──────────────────┐              ┌──────────────────────────┐    │
│  │  REST API Layer   │              │  project.createProject    │    │
│  │  (aisandbox-pa)   │              │  project.getProject       │    │
│  │  NO Bearer token  │              │  project.searchScenes     │    │
│  │  NO access_token  │              │  videoFx.getUserSettings  │    │
│  │  Uses: cookies +  │              │  videoFx.getModelConfig   │    │
│  │  reCAPTCHA token  │              │  media.fetchHistory       │    │
│  └──────────────────┘              │  general.submitBatchLog   │    │
│                                     └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 17.2 Pre-Generation Dependency Chain

Every generation request requires these **prerequisite** calls:

```
project.searchProjectScenes ──→ Validates project exists, loads scenes
        │
        ├──→ media.fetchUserHistoryDirectly ──→ Loads user history (paginated, 2-11 pages)
        │            │
        │            └──→ /v1/media/{ID} ──→ Loads each uploaded image (parallel batch)
        │                     │
        │                     └──→ Returns: mediaGenerationId, fifeUrl, aspectRatio
        │
        ├──→ general.fetchUserAcknowledgement ──→ Terms check
        │
        └──→ (Optional) videoFx.setLastSelectedVideoModelKey
             videoFx.setLastSelectedVideoAspectRatio
```

> **KEY FINDING**: `media.fetchUserHistoryDirectly` is called **2-11 times per file** (paginated). Files that revisit a project with many uploaded images load **25-30 individual media items** via `/v1/media/{ID}` before any generation can begin.

### 17.3 Generation-to-Completion Chain

```
recaptcha/enterprise/reload ──→ Gets fresh token (REQUIRED)
        │
        ├──→ /v1/video:batchAsync... ──→ Submit generation with token
        │            │
        │            ├──→ Returns: operations[] with operation.name + sceneId
        │            ├──→ Returns: remainingCredits (immediate deduction)
        │            └──→ (Upscale only) Returns: workflows[] + media[]
        │
        ├──→ recaptcha/enterprise/clr ──→ Log reCAPTCHA result (ALWAYS after submit)
        │
        ├──→ general.submitBatchLog ──→ VIDEOFX_CREATE_VIDEO event
        │    general.submitBatchLog ──→ PINHOLE_GENERATE_VIDEO event
        │    (3-6 batch log calls per generation)
        │
        └──→ /v1/video:batchCheckAsync... ──→ Poll loop (4-253 times)
                     │
                     ├──→ PENDING → ACTIVE → SUCCESSFUL
                     ├──→ When SUCCESSFUL: metadata contains video URLs
                     └──→ remainingCredits appears when ALL ops complete
```

### 17.4 Critical Endpoint Pairs (Always Co-occur)

These endpoints are **always called together** — never independently:

| Primary Endpoint | Always Paired With | Relationship |
|---|---|---|
| `recaptcha/enterprise/reload` | Any `batchAsync*` generation | Token obtained → embedded in payload |
| Any `batchAsync*` generation | `recaptcha/enterprise/clr` | Always called immediately after submission |
| Any `batchAsync*` generation | `batchCheckAsyncVideoGenerationStatus` | Polling always follows generation |
| `STORAGE:/ai-sandbox-videofx/video/{UUID}` | `general.submitBatchLog` (DOWNLOAD) | Download event always logged |
| `reportClientSideError` | `submitBatchLog` (ERROR event) | Error always reported + logged |
| `uploadUserImage` | `submitBatchLog` (UPLOAD events) | 3 events: UPLOAD, RESIZE, CROP |

### 17.5 Endpoint Isolation (Never Co-occur)

| Endpoint A | Endpoint B | Reason |
|---|---|---|
| `whisk.getRecentMedia` | `project.searchProjectScenes` | Different apps (Whisk vs Flow) |
| `/v1/whisk:getVideoCreditStatus` | `/v1/credits` | Different credit check per app |
| `general.fetchFeatureAvailability` | `videoFx.getUserSettings` | Feature flags = Whisk, User settings = Flow |

---

## 18. Cross-Component Data Flow

### 18.1 Media ID Lifecycle

```
┌─────────────────┐     uploadUserImage      ┌────────────────────┐
│ User Image File  │ ──────────────────────→ │ mediaGenerationId   │
│ (Base64 JPEG)    │                          │ "CAMaJDY2NGQ2Y2..." │
└─────────────────┘                          └────────────────────┘
        │                                              │
        │ Upload returns mediaId                       │ Used as:
        ▼                                              ▼
┌─────────────────────────────────────────────────────────────┐
│ startImage.mediaId   │ endImage.mediaId  │ referenceImages   │
│ (in I2V payload)     │ (in S+E payload)  │ (in R2V payload)  │
└─────────────────────────────────────────────────────────────┘
        │
        │ Generation response returns:
        ▼
┌─────────────────────────────────────────────────────────────┐
│ operation.name (hex32)    │ → Used in polling request       │
│ sceneId (UUID)            │ → Links video to scene          │
│ remainingCredits          │ → Credit tracking               │
└─────────────────────────────────────────────────────────────┘
        │
        │ Poll SUCCESSFUL returns:
        ▼
┌─────────────────────────────────────────────────────────────┐
│ operation.metadata.name = "CAUS..." │ → New video mediaId   │
│ video.fifeUrl                       │ → Preview URL         │
│ video.servingBaseUri                │ → Download base       │
│ mediaGenerationId = "CAUS..."       │ → Used for upscale    │
└─────────────────────────────────────────────────────────────┘
        │
        │ Upscale uses videoInput.mediaId:
        ▼
┌──────────────────────────────────────────────┐
│ videoInput.mediaId = "CAUS..."               │
│ → Upscale returns: primaryMediaId + "_upsampled" │
│ → workflowStepId = "CAE"                     │
└──────────────────────────────────────────────┘
```

### 18.2 Media ID Prefix → Type Mapping

| Prefix | Decoded Meaning | Created By | Used In |
|---|---|---|---|
| `CAMa` | Uploaded image (workflow=user, step=upload) | `uploadUserImage` | `startImage.mediaId`, `endImage.mediaId` |
| `CAMS` | Generated image (workflow=project, step=gen) | `batchGenerateImages` | `upsampleImage.mediaId` |
| `CAUS` | Generated video (workflow=auto, step=gen) | `batchCheckAsync...` (on SUCCESS) | `videoInput.mediaId` in upscale |

### 18.3 Session ID → Endpoint Mapping

Session IDs (`;{timestamp}`) appear in ALL `clientContext` objects. A single session spans:

- All generation requests within one browser tab session
- All uploads within that session
- All image upscales within that session
- Upscale `clientContext` carries sessionId but **drops** projectId + tool

### 18.4 Project ID Flow

```
project.createProject ──→ Returns projectId
        │
        ├──→ project.getProject (projectId in URL query)
        ├──→ project.searchProjectScenes (projectId in URL query)
        ├──→ project.searchProjectWorkflows (projectId in URL query)
        ├──→ /v1/projects/{projectId}/flowMedia:batchGenerateImages
        ├──→ clientContext.projectId in generation payloads
        └──→ workflows[].projectId in upscale responses
```

> **CRITICAL**: `projectId` is **NOT** included in upscale `clientContext`, but the server **returns** the `projectId` in the upscale response's `workflows[].projectId`. The server tracks this link internally.

---

## 19. Per-File Operation Type Matrix

### 19.1 All 50 HAR Files Categorized

| Category | Files | Endpoints Used | Unique Pattern |
|---|---|---|---|
| **Project Creation** | `0. Tao Project.har` (×2) | createProject, getProject, searchScenes, getUserSettings, getModelConfig, fetchPreferences, searchWorkflows, listPreambles | Full initialization sequence |
| **Page Load/Check** | `Check Ultra.har`, `Check trang thai...` (×2) | credits, fetchUserRecommendations, checkAppAvailability, getProject, getFlowAppConfig, fetchUserLocale, fetchFlowUserIngredients | Account status + app config |
| **Text-to-Video** | `Prompt 1-5.har` (×16) | batchAsyncGenerateVideo, batchCheckAsync, setModelKey, setAspectRatio | submitBatchLog ×3 per gen |
| **Image-to-Video (S+E)** | `916 frame to video.har` (×5) | uploadUserImage, batchAsync...StartAndEndImage, batchCheckAsync, fetchUserHistoryDirectly ×3, media/{ID} ×25+ | Mass media reload |
| **Reference-to-Video** | `01.x 169 ingredients.har` (×6) | batchAsync...ReferenceImages, setModelKey, setAspectRatio | referenceImages[] in payload |
| **Upscale** | `916 frame to video...Upscale*.har` (×4) | batchAsync...UpsampleVideo (×4 sequential), batchCheckAsync (×33-253) | Sequential upscale + poll |
| **Reshoot** | Various `.har` | batchAsync...Reshoot | Re-generation of specific video |
| **Extend** | Various `.har` | batchAsync...ExtendVideo | Video extension generation |
| **Download (720p)** | `Download 720 4 vid.har` | STORAGE ×4, submitBatchLog ×4 | Paired: download + log |
| **Download Image** | `Download anh 1k.har` | /v1/media/{ID} (image response) | encodedImage in response |
| **Image Upscale** | `Download anh 2k.har`, `Download anh 4k*.har` (×3) | flow/upsampleImage, recaptcha | Returns encodedImage (base64) |
| **Whisk** | `Whisk*.har` (×5) | whisk.getRecentMedia, whisk.getWhiskRecentMediaGroupIds, whisk:getVideoCreditStatus, fetchFeatureAvailability, checkAppAvailability, fetchUserRecommendations | Short media IDs, different credit check |

### 19.2 Cross-File Relationships (Shared Project IDs)

```
Project f5db1342 (21 files) ─── Main working project
  │
  ├── 0. Tao Project.har ────── Created here
  ├── Prompt 1.har ──────────── First T2V generation
  ├── Prompt 2.har ──────────── Second T2V generation
  ├── ...
  ├── Prompt 5.har ──────────── Fifth T2V generation
  ├── Download 720.har ──────── Download results
  ├── Download anh 1k.har ───── Download generated image
  ├── Download anh 2k.har ───── Upscale image to 2K
  └── Download anh 4k*.har ──── Upscale image to 4K

Project 4fd7fb72 (6 files) ─── Frame-to-Video project
  │
  ├── 916 frame to video...start.har ──── Submit 4 video I2V
  ├── 916 frame to video...done.har ───── Generation complete
  ├── 916 frame to video...Upscale start ── Submit 4 upscales
  ├── 916 frame to video...1080 done.har ── 1080p upscales done
  └── 916 frame to video...all done.har ─── All upscales complete

Project 909d317a (1 file) ─── Ingredients project
  │
  └── 916 ingre to video.har

Project daba1978 (6 files) ─── Reference-image project
  │
  ├── 01.2 169 ingredients...submit.har (×3)
  └── 01.3 169 ingredients...done.har (×3)
```

---

## 20. Reference-to-Video (R2V) — Previously Missing

### 20.1 Endpoint: `batchAsyncGenerateVideoReferenceImages`

**Occurrences**: 5 (in files: `01.x 169 ingredients...`)

**Payload structure** (distinct from T2V and I2V):
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
            "referenceImages": [ /* array of reference image objects */ ],
            "seed": 12345,
            "textInput": { "prompt": "..." }
        }
    ]
}
```

**Key difference from I2V**: Uses `referenceImages[]` array instead of `startImage`/`endImage`. No `videoModelKey` visible in payload keys (may be server-defaulted).

**Response structure** (richer than T2V/I2V):
```json
{
    "operations": [{ "operation": { "name": "..." }, "sceneId": "...", "status": "PENDING" }],
    "remainingCredits": 44990,
    "workflows": [{ "name": "...", "metadata": { "createTime": "...", "primaryMediaId": "...", "batchId": "..." }, "projectId": "..." }],
    "media": [{ "name": "..." }]
}
```

> R2V responses include `workflows` + `media` fields (like upscale), while standard T2V responses do NOT.

### 20.2 R2V Flow Pattern

The R2V files show a distinctive multi-step flow:

1. `searchProjectScenes` → Load project
2. `setLastSelectedVideoModelKey` → Change model (R2V model)
3. `setLastSelectedVideoAspectRatio` → May change twice (user adjusting)
4. `submitBatchLog` ×3 → Pre-generation logging
5. `recaptcha/enterprise/reload` → Get token
6. `batchAsync...ReferenceImages` → Submit R2V generation
7. `recaptcha/enterprise/clr` → Log reCAPTCHA
8. `batchCheckAsync...` → Poll (4-6 polls observed)

---

## 21. Telemetry & Logging Relationships

### 21.1 submitBatchLog Event → Trigger Mapping

| Event | Triggered By | Always Before/After |
|---|---|---|
| `PAGE_VIEW` | Page navigation | First event in Whisk files |
| `PINHOLE_UPLOAD_IMAGE` | `uploadUserImage` success | After upload response |
| `PINHOLE_UPLOAD_IMAGE_TO_CROP` | User imports image to crop | Before CROP event |
| `PINHOLE_RESIZE_IMAGE` | Image auto-resize | After upload, before gen |
| `PINHOLE_CROP_IMAGE` | User crops image | After resize |
| `PINHOLE_GENERATE_IMAGE` | `batchGenerateImages` submit | After generation submit |
| `PINHOLE_GENERATE_VIDEO` | Any video generation submit | After gen submit |
| `PINHOLE_GENERATE_VIDEO_ERROR` | Generation HTTP 403 | After error + reportError |
| `PINHOLE_UPSCALE_IMAGE` | `upsampleImage` submit | After upscale submit |
| `VIDEOFX_CREATE_VIDEO` | Any video generation submit | Same batch as GENERATE_VIDEO |
| `VIDEO_CREATION_TO_VIDEO_COMPLETION` | Polling reaches SUCCESSFUL | After completion |
| `DOWNLOAD` | STORAGE download complete | After each video download |

### 21.2 submitBatchLog Call Count Per Action

| Action | submitBatchLog Calls | Notes |
|---|---|---|
| Page load (Flow) | 2 | PAGE_VIEW + initialization |
| Image upload | 3 | UPLOAD + RESIZE + CROP |
| Video gen submit | 3 | CREATE_VIDEO + GENERATE_VIDEO + timing |
| Video upscale submit | 5-6 | Per upscale: CREATE + GENERATE + timing ×2 |
| Video download | 1 | DOWNLOAD event per file |
| Error | 2 | reportClientSideError + ERROR event |

### 21.3 Event Sequence Numbering Pattern

In per-file flows, request indices show **gaps** (e.g., [0], [1], [3], [6]) because:
- Non-API requests (CSS, JS, images) occupy indices [2], [4], [5]
- The HAR analysis script only extracts API calls, creating visible gaps
- Gap size indicates how many non-API requests occurred between API calls

---

## 22. Micro-Findings & Edge Cases

### 22.1 Rare/Low-Count Endpoints

| Endpoint | Count | Only In | Significance |
|---|---|---|---|
| `batchAsyncGenerateVideoStartImage` | 1 | Single HAR | Start-only I2V is rare |
| `general.fetchToolAvailability` | 1-2 | Whisk files | Only Whisk checks tool state |
| `general.fetchFeatureAvailability` | 2 | Whisk files | Feature flags for Whisk only |
| `general.fetchUserLocale` | 2 | Check status files | Locale checked on page load |
| `media.fetchFlowUserIngredients` | 2 | Check status files | Ingredients loaded on project open |
| `project.createProject` | 2 | `0. Tao Project.har` ×2 | Project creation is one-time |
| `general.reportClientSideError` | 1 | Error file | Only 1 error in 50 files |
| `whisk.getWhiskRecentMediaGroupIds` | 1 | Whisk HAR | Group IDs endpoint |

### 22.2 fetchUserRecommendations Response Variations

| Context | Response Fields |
|---|---|
| Ultra account (`Check Ultra.har`) | `{onramp, upsellMessage, recommendationUri}` |
| Status check files | `{onramp, upsellMessage, recommendationUri, description, imageUri}` |

> **INSIGHT**: The `description` and `imageUri` fields appear when the account is on a lower tier and Google is recommending an upgrade. Ultra accounts get minimal recommendation data.

### 22.3 /v1/credits Response Variations

| Context | Response Fields |
|---|---|
| `Check Ultra.har` | `{credits, userPaygateTier, sku, serviceTier}` |
| Other check files | `{credits, userPaygateTier, sku}` |

> `serviceTier` field (`SERVICE_TIER_ADVANCED`) only appears in some responses — possibly A/B tested or version-dependent.

### 22.4 Media Response Type Variations

`/v1/media/{ID}` returns different structures based on media type:

**Uploaded Image**:
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

**Generated Image**:
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

> **KEY DIFFERENCE**: Uploaded images use `userUploadedImage.image` wrapper; generated images use `image.encodedImage` wrapper. Generated images include `projectId` in `mediaGenerationId`; uploaded images do not.

### 22.5 Sequential Upscale Pattern (4 Videos)

The HAR data shows upscaling 4 videos requires **sequential submission** (NOT batch):

```
[Step 9]  recaptcha/reload → Get token A
[Step 10] batchAsync...Upsample(video1, tokenA) → Submit video 1
[Step 11] recaptcha/clr
[Step 15-19] submitBatchLog ×5
[Step 21] batchCheckAsync [POLL] → Check video 1
[Step 22] recaptcha/reload → Get token B (!)
[Step 23] batchAsync...Upsample(video2, tokenB) → Submit video 2
[Step 24] recaptcha/clr
[Step 27-31] submitBatchLog ×5
[Step 33] recaptcha/reload → Get token C (!)
[Step 34] batchAsync...Upsample(video3, tokenC) → Submit video 3
... (continues for video 4)
```

> **CRITICAL**: Each upscale requires a **fresh reCAPTCHA token**. Tokens are NOT reused across submissions. The client submits upscales **one at a time**, waits for reCAPTCHA, then submits the next — but polling for all continues simultaneously.

### 22.6 Download Flow Detail

Each video download follows this exact pattern:

```
[Step N]   GET STORAGE:/ai-sandbox-videofx/video/{UUID} → Binary video data
[Step N+1] POST TRPC:general.submitBatchLog → {event: "DOWNLOAD"}
```

For 4 videos:
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

### 22.7 Page Initialization Sequence (Full Load)

When opening a project page for the first time (`Check trang thai...` files), the client executes this initialization:

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
[20] GET project.searchProjectScenes (second call)
[21] GET videoFx.listPreambles
[22] GET media.fetchUserHistoryDirectly
[23] GET media.fetchFlowUserIngredients
```

> This is the most complete initialization sequence observed (23 API calls). It loads: credits, recommendations, project data, user settings, model configs, workflows, preambles, history, and ingredients.

### 22.8 Whisk vs Flow Initialization Comparison

| Step | Flow Init | Whisk Init |
|---|---|---|
| 1 | `/v1/credits` | `checkAppAvailability` |
| 2 | `fetchUserRecommendations` | `fetchFeatureAvailability` + `fetchToolAvailability` |
| 3 | `checkAppAvailability` | `AUTH:session` |
| 4 | `project.getProject` | `/v1/media/{shortId}` ×40+ |
| 5 | `getFlowAppConfig` | `whisk:getVideoCreditStatus` |
| 6+ | `searchScenes`, `getUserSettings`, etc. | `fetchUserRecommendations`, `getFlowAppConfig` |

---

> **Document generated from exhaustive analysis of 50 HAR files (15,527 lines of output data)**  
> **Enhanced with relationship analysis, dependency chains, data flow mapping, and micro-findings**
