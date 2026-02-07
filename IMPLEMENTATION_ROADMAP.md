# VEO Pro Max - Implementation Roadmap
> **Created:** 2026-02-02
> **Purpose:** Consolidated audit + fix preparation for API-first VEO tool

---

## 1. PROJECT STATUS SUMMARY

| Component | Status | Location |
|-----------|--------|----------|
| **Licensing System** | ✅ Complete | `VEO Pro Max/05_Security/` |
| **API Documentation** | ✅ Complete | `Documentation/` |
| **F12 HAR Data** | ✅ Available | `F12 Dev/` |
| **Core Engine Code** | 🔴 **NOT STARTED** | `VEO Pro Max/core/` (empty) |
| **Multi-Account System** | 🔴 **NOT STARTED** | - |

---

## 2. ARCHITECTURE (API-FIRST)

```
┌─────────────────────────────────────────────────────────────┐
│                     VEO Pro Max App                         │
├─────────────────────────────────────────────────────────────┤
│  UI Layer (CustomTkinter)                                   │
│  ├── Tabs: T2V, I2V, R2V, Image Gen, Queue, Settings       │
│  └── License validation UI                                  │
├─────────────────────────────────────────────────────────────┤
│  Core Layer (TO BE IMPLEMENTED)                             │
│  ├── VEOApiClient    → HTTP requests to VEO API            │
│  ├── AuthManager     → Token storage/refresh               │
│  ├── MediaHandler    → Image/video processing              │
│  ├── QueueManager    → Task queue                          │
│  ├── AccountManager  → Multi-account tokens (Phase 2)      │
│  └── WorkerPool      → Parallel execution (Phase 2)        │
├─────────────────────────────────────────────────────────────┤
│  Security Layer (COMPLETE)                                  │
│  ├── license_client.py  → Validate license                 │
│  ├── trial_protection.py → Anti-crack                      │
│  └── license_keygen.py  → Admin key generation             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. IMPLEMENTATION PHASES

### Phase 1: Core Engine (Single Account)
| Priority | File | Lines Est. | Reference Spec |
|----------|------|------------|----------------|
| 1 | `core/api_client.py` | ~300 | `03_Backend/CORE_MODULES_SPEC.md` |
| 2 | `core/auth_manager.py` | ~100 | `03_Backend/CORE_MODULES_SPEC.md` |
| 3 | `core/media_handler.py` | ~80 | `03_Backend/CORE_MODULES_SPEC.md` |
| 4 | `core/queue_manager.py` | ~100 | Existing spec |
| 5 | `main.py` | ~50 | Entry point |
| 6 | `ui/app.py` | ~300 | `01_UI_UX/` tab specs |

### Phase 2: Multi-Account Parallel
| Priority | File | Reference Spec |
|----------|------|----------------|
| 1 | `core/account_manager.py` | `04_Workflows/WORKFLOW_MULTI_COOKIE_PARALLEL.md` |
| 2 | `core/scheduler.py` | `04_Workflows/WORKFLOW_MULTI_COOKIE_PARALLEL.md` |
| 3 | `core/worker_pool.py` | `02_Architecture/WORKER_STATE_MACHINE.md` |

### Phase 3: Advanced Features
- Continuation/Concat video chaining
- Queue Full auto-retry
- Rate limiting per account

---

## 4. API ENDPOINTS TO IMPLEMENT

| Method | Endpoint | Mode |
|--------|----------|------|
| `upload_image()` | `/v1:uploadUserImage` | Sync |
| `generate_video_t2v()` | `/v1/video:batchAsyncGenerateVideoText` | Async |
| `generate_video_i2v_single()` | `/v1/video:batchAsyncGenerateVideoStartImage` | Async |
| `generate_video_i2v_dual()` | `/v1/video:batchAsyncGenerateVideoStartAndEndImage` | Async |
| `generate_video_r2v()` | `/v1/video:batchAsyncGenerateVideoReferenceImages` | Async |
| `generate_image()` | `/v1/projects/{id}/flowMedia:batchGenerateImages` | Sync |
| `upscale_video()` | `/v1/video:batchAsyncGenerateVideoUpsampleVideo` | Async |
| `upscale_image()` | `/v1/flow/upsampleImage` | Async |
| `check_status()` | `/v1/video:batchCheckAsyncVideoGenerationStatus` | Sync |
| `download_media()` | Direct signed URL | Sync |

---

## 5. REFERENCE FILES

| Purpose | File |
|---------|------|
| API Endpoints Detail | `Documentation/reference/API_ENDPOINTS.md` |
| Model Keys | `Documentation/reference/MODEL_KEYS.md` |
| Class Signatures | `VEO Pro Max/03_Backend/CORE_MODULES_SPEC.md` |
| Multi-Cookie Spec | `VEO Pro Max/04_Workflows/WORKFLOW_MULTI_COOKIE_PARALLEL.md` |
| UI Tab Specs | `VEO Pro Max/01_UI_UX/TAB_*.md` |
| HAR Examples | `F12 Dev/*.har` |

---

## 6. NEXT STEPS

1. [ ] **Create `core/` directory** in VEO Pro Max
2. [ ] **Implement `api_client.py`** following CORE_MODULES_SPEC.md
3. [ ] **Test T2V endpoint** with manual token from DevTools
4. [ ] **Build UI shell** with CustomTkinter
5. [ ] **Integrate licensing** from `05_Security/client/`
