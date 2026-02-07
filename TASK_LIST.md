# VEO Pro Max - Task List
> **Created:** 2026-02-02
> **Updated:** 2026-02-02
> **Status:** ✅ PHASES 1-3 COMPLETE (Implementation Ready for Testing)

---

## ✅ DATA VERIFICATION STATUS

| Reference | Status | Location |
|-----------|--------|----------|
| API Endpoints | ✅ Verified | `Documentation/Research/reference/API_ENDPOINTS.md` |
| Security Matrix | ✅ Verified | `F12 Dev/final_verification_report.md` |
| Execution Flow (6 Workflows) | ✅ Complete | `API_ENDPOINTS.md` |
| Class Signatures | ✅ Synced | `Documentation/02_Architecture/PYTHON_CLASS_STRUCTURE.md` |
| HAR Samples | ✅ 46 files | `F12 Dev/` |


---

## 📋 PHASE 0: Documentation Completion (Pre-Implementation)

### Task 0.1: Create `PAYLOAD_SCHEMAS.md` ✅ COMPLETE
**Purpose:** Document exact JSON payloads for each workflow type
- [x] T2V Payload (Text-to-Video)
- [x] I2V Single Payload (Image Start Only)
- [x] F2V Payload (Frames: Start + End)
- [x] R2V Payload (Ingredients: 1-3 References)
- [x] T2I Payload (Text-to-Image)
- [x] Video Upscale Payload
- [x] Image Upscale Payload
- [x] Status Check Payload
- [x] Download Request Structure

### Task 0.2: Create `MODEL_MAPPING.md` ✅ COMPLETE
**Purpose:** Complete UI-to-API model key mapping
- [x] Text-to-Video models (`veo_3_1_t2v_*`)
- [x] Image-to-Video models (`veo_3_1_i2v_s_*`, `veo_3_1_i2v_s_fast_fl_*`)
- [x] Ingredients-to-Video models (`veo_3_1_r2v_*`)
- [x] Image Generation models
- [x] Upscale resolution enums (`VIDEO_RESOLUTION_1080P`, `VIDEO_RESOLUTION_4K`)
- [x] Aspect ratio enums

### Task 0.3: Create `BROWSER_HEADERS.md` ✅ COMPLETE
**Purpose:** Document required headers to mimic browser requests
- [x] Static headers (`x-browser-channel`, `x-browser-copyright`, `x-browser-year`)
- [x] Dynamic headers (`x-browser-validation` - how to harvest/replay)
- [x] `x-client-data` structure
- [x] Header placement per endpoint (which endpoints need which headers)

### Task 0.4: Update `CORE_MODULES_SPEC.md` ✅ COMPLETE
**Purpose:** Ensure code specs match verified API structure
- [x] Add `_build_standard_headers()` method spec
- [x] Add `_get_client_context()` method with reCAPTCHA
- [x] Ensure all 6 workflow methods have explicit payload structures
- [x] Add Download method with API Key query param

---

## 📋 PHASE 1: Core Engine (Single Account)

### Task 1.1: Implement `constants.py` ✅ COMPLETE
**Purpose:** Central location for all enums and mappings
- [x] `ModelKeys` enum/dict
- [x] `AspectRatio` enum
- [x] `Resolution` enum
- [x] `Endpoint` constants
- [x] `XBrowserHeaders` dict template

### Task 1.2: Implement `auth_manager.py` (~150 lines) ✅ COMPLETE
**Reference:** `CORE_MODULES_SPEC.md` + `BROWSER_HEADERS.md`
- [x] `TokenData` dataclass
- [x] `AuthManager.__init__()` with file load
- [x] `get_bearer_token()` → Return current valid token
- [x] `get_api_key()` → Return API Key for downloads
- [x] `get_recaptcha_token()` / `update_recaptcha_token()` → reCAPTCHA handling
- [x] `get_x_browser_headers()` → Return dict of x-browser-* headers
- [x] `set_credentials(token, project_id, api_key, x_browser_headers)` → Manual input
- [x] `harvest_from_har(har_path)` → Extract credentials from HAR file
- [x] `is_expired()` → Check validity
- [x] `_load_from_file()` / `_save_to_file()`

### Task 1.3: Implement `api_client.py` (~400 lines) ✅ COMPLETE
**Reference:** `CORE_MODULES_SPEC.md` + `PAYLOAD_SCHEMAS.md`
- [x] `VEOApiClient.__init__(project_id, auth_manager)`
- [x] `_build_headers()` → Combine Bearer + x-browser-* headers
- [x] `_get_client_context(recaptcha_token, tool="PINHOLE")` → Build clientContext
- [x] **Upload**: `upload_image(image_bytes, aspect_ratio)` → `/v1:uploadUserImage`
- [x] **T2V**: `generate_video_t2v(prompt, model, aspect_ratio, count, seeds, recaptcha_token)`
- [x] **I2V Single**: `generate_video_i2v_single(media_id, prompt, model, count, recaptcha_token)`
- [x] **F2V Dual**: `generate_video_i2v_dual(start_id, end_id, prompt, model, count, recaptcha_token)`
- [x] **R2V**: `generate_video_r2v(media_ids, prompt, model, count, recaptcha_token)`
- [x] **T2I**: `generate_image(prompt, model, aspect_ratio, count, recaptcha_token)`
- [x] **Video Upscale**: `upscale_video(media_id, resolution, recaptcha_token)`
- [x] **Image Upscale**: `upscale_image(media_id, resolution, recaptcha_token)`
- [x] **Status**: `check_status(operation_id, scene_id)` → No reCAPTCHA
- [x] **Poll**: `wait_for_completion(operation_id, scene_id, max_attempts, interval)`
- [x] **Download**: `download_media(media_id, output_path)` → Uses API Key
- [x] Error classes: `VEOApiError`, `AuthenticationError`, `RateLimitError`, `ContentPolicyError`

### Task 1.4: Implement `media_handler.py` (~80 lines) ✅ COMPLETE
**Reference:** `CORE_MODULES_SPEC.md`
- [x] `image_to_base64(image_path)` → JPEG Base64
- [x] `detect_aspect_ratio(image_path)` → VEO enum
- [x] `download_file(url, output_path, headers)`
- [x] `save_base64_image(base64_data, output_path)`

### Task 1.5: Implement `queue_manager.py` (~100 lines) ✅ COMPLETE
**Reference:** Reuse from original
- [x] `TaskStatus` enum
- [x] `Task` dataclass
- [x] `QueueManager` class with thread-safe operations

### Task 1.6: Create `main.py` Entry Point ✅ COMPLETE
- [x] Import core modules
- [x] Initialize AuthManager + VEOApiClient
- [x] Basic CLI for testing all 6 workflows

---

## 📋 PHASE 2: Multi-Account Parallel ✅ COMPLETE

### Task 2.1: Implement `account_manager.py` ✅ COMPLETE
- [x] `Account` dataclass (token, project_id, api_key, x_browser_headers, status, capacity)
- [x] `AccountManager.load_accounts()`
- [x] `AccountManager.get_available_account()`
- [x] `AccountManager.update_account_status()`

### Task 2.2: Implement `scheduler.py` ✅ COMPLETE
- [x] `CookieScheduler.allocate(tasks, accounts)`
- [x] Parallel vs Continuation logic
- [x] Queue Full handling

### Task 2.3: Implement `worker_pool.py` ✅ COMPLETE
- [x] `WorkerThread` class
- [x] State machine (IDLE, BUSY, QUEUE_FULL)
- [x] Parallel execution management

---

## 📋 PHASE 3: UI + Integration ✅ COMPLETE

### Task 3.1: Build CustomTkinter UI ✅ COMPLETE
**Reference:** `VEO Pro Max/01_UI_UX/TAB_*.md`
- [x] Main window shell
- [x] Tab 1: Text-to-Video
- [x] Tab 2: Image-to-Video (Single Frame)
- [x] Tab 3: Frames-to-Video (Start + End)
- [x] Tab 4: Ingredients-to-Video (R2V)
- [x] Tab 5: Image Generation
- [x] Tab 6: Queue Manager (with Upscale/Download/Play buttons)
- [x] Tab 7: Settings (Token, Headers, API Key)
- [x] Tab 8: License (Activation + Pricing Plans)

---

## ⚠️ REQUIRED USER INPUT

| Item | Question |
|------|----------|
| **Test Token** | Cần Bearer token từ DevTools để test API calls |
| **API Key** | Cần API Key (AIza...) từ DevTools query params |
| **x-browser-validation** | Cần giá trị header này từ DevTools |
| **Project ID** | Cần Project UUID từ VEO Studio |
| **reCAPTCHA Token** | Cần token test từ DevTools payload |
| **Test Images** | Cần 1-3 ảnh mẫu để test I2V/R2V workflows |

---

## 📊 PRIORITY ORDER

1. **Phase 0** → Complete documentation (PAYLOAD_SCHEMAS, MODEL_MAPPING, BROWSER_HEADERS)
2. **constants.py** → Central mapping
3. **auth_manager.py** → Token + Header handling
4. **api_client.py** → Core functionality
5. **Test T2V endpoint** → Validate implementation
6. **media_handler.py** → Image processing
7. **queue_manager.py** → Task management
8. **main.py** → CLI testing all 6 workflows
9. UI development (Phase 3)
