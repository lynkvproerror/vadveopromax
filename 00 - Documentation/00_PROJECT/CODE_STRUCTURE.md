# 📁 VEO Pro Max - Code Structure

**Location**: `Documentation/00_PROJECT/CODE_STRUCTURE.md`  
**Last Updated**: 2026-02-07  
**Status**: COMPLETE

---

## 📊 Project Overview

```
#NEW VEO API/
├── 📁 Documentation/        ← Full project documentation (70+ files)
├── 📁 Research/             ← API research, HAR analysis
├── 📁 F12 Dev/              ← DevTools captures, analysis scripts
├── 📄 IMPLEMENTATION_ROADMAP.md
├── 📄 TASK_LIST.md
└── 📄 NEW_DATA_FINDINGS.md
```

---

## 📂 DOCUMENTATION (Main Knowledge Base)

```
Documentation/
│
├── 📁 00_PROJECT/                       ← Project & overview docs
│   ├── README.md                        ← Project introduction
│   ├── ARCHITECTURE_OVERVIEW.md         ← ⭐ System diagram
│   ├── GLOSSARY.md                      ← Terms & abbreviations
│   ├── CODE_STRUCTURE.md                ← THIS FILE
│   ├── CHANGELOG.md                     ← Version history
│   ├── TROUBLESHOOTING.md               ← Error solutions
│   └── DOCUMENTATION_AUDIT.md           ← Audit report
│
├── 📁 01_UI_UX/                         ← UI/UX Specifications (18 files)
│   ├── README.md                        ← UI overview
│   ├── 00_DESIGN_SYSTEM.md              ← Colors, fonts, spacing
│   ├── POPUP_LAYOUTS.md                 ← All popup designs
│   ├── IMAGE_LIBRARY_SYSTEM.md          ← Image library modal
│   ├── BUTTON_ACTION_MAPPING.md         ← Button → API mapping
│   ├── SOURCE_COLUMN_DISPLAY.md         ← Source column formats
│   │
│   ├── TAB_01_TEXT_TO_VIDEO.md          ← T2V tab spec
│   ├── TAB_02_IMAGE_TO_VIDEO.md         ← I2V/F2V tab spec
│   ├── TAB_03_INGREDIENTS.md            ← R2V tab spec
│   ├── TAB_04_TEXT_TO_IMAGE.md          ← T2I tab spec
│   ├── TAB_05_IMAGE_TO_IMAGE.md         ← I2I tab spec
│   ├── TAB_06_QUEUE_MANAGER.md          ← Queue manager spec
│   ├── TAB_07_SETTINGS.md               ← Settings & Profiles
│   ├── TAB_08_LICENSE.md                ← License tab spec
│   ├── TAB_09_ABOUT.md                  ← About tab spec
│   ├── TAB_10_DEV_CONSOLE.md            ← Dev console spec
│   └── ui_screenshot.png                ← Reference screenshot
│
├── 📁 02_Architecture/                  ← System architecture (4 active files)
│   ├── README.md                        ← Folder index
│   ├── API_MAPPING.md                   ← API endpoints overview
│   ├── UI_TO_API_PARAMETER_MAPPING.md   ← Complete UI → API mapping
│   ├── FRAME_CONTINUATION_WORKFLOW.md   ← Continuation logic
│   ├── WORKFLOW_ACTIVITY_DIAGRAMS.md    ← Activity diagrams
│   └── diagrams/
│       └── veo_master_execution_flow.png
│
├── 📁 03_Backend/                       ← Backend logic (14 files)
│   ├── ACCOUNT_SESSION_MANAGEMENT.md    ← ⭐ Session, tokens, subscription
│   ├── PROJECT_MANAGEMENT.md            ← ⭐ VEO Project handling
│   ├── MULTITHREADING_ARCHITECTURE.md   ← ⭐ ĐẠI CHỦ-CHỦ-THẦU-THỢ pattern
│   │
│   ├── BATCH_IMPORT_LOGIC.md            ← Bulk import processing
│   ├── BUILD_PIPELINE.md                ← PyInstaller build
│   ├── CORE_MODULES_SPEC.md             ← Core module specs
│   ├── DOWNLOAD_MANAGER.md              ← Download logic
│   ├── ERROR_HANDLING_STRATEGY.md       ← Error codes & recovery
│   ├── OUTPUT_NAMING_CONVENTION.md      ← File naming patterns
│   ├── RECAPTCHA_BROWSER_MANAGEMENT.md  ← reCAPTCHA handling
│   │
│   ├── TOKEN_SECURITY.md                ← Token encryption
│   └── FIREBASE_SECURITY_RULES.md       ← Firebase rules
│
├── 📁 04_Workflows/                     ← Workflow documentation
│   ├── VEO_WORKFLOWS.md                 ← Workflow overview
│   ├── VEO_PRODUCTION_WORKFLOWS.md      ← Full production flows
│   │
│   │── Tab Workflows:
│   ├── WORKFLOW_TAB_01_TEXT_TO_VIDEO.md
│   ├── WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md
│   ├── WORKFLOW_TAB_03_INGREDIENTS.md
│   ├── WORKFLOW_TAB_04_TEXT_TO_IMAGE.md
│   ├── WORKFLOW_TAB_05_IMAGE_TO_IMAGE.md
│   │
│   │── System Workflows:
│   ├── WORKFLOW_BATCH_OPERATIONS.md     ← Batch processing (moved from 05_Security)
│   ├── WORKFLOW_BROWSER_SESSION.md      ← Browser lifecycle
│   ├── WORKFLOW_SESSION_VALIDATION.md   ← Session validation
│   ├── WORKFLOW_MULTI_ACCOUNT_PARALLEL.md ← Multi-account parallel
│   ├── WORKFLOW_QUEUE_PERSISTENCE.md    ← Queue save/restore
│   ├── WORKFLOW_SETTINGS_SYNC.md        ← Settings sync
│   └── WORKFLOW_VIDEO_SCAN_DOWNLOAD.md  ← Download workflow
│
├── 📁 05_Security/                      ← License Security Documentation
│   ├── README.md                        ← Overview & quick start
│   ├── SECURITY_AUDIT_REPORT.md         ← Security audit findings
│   ├── docs/                            ← Security documentation (17 files)
│   │   ├── LICENSE_OVERVIEW.md
│   │   ├── LICENSE_SECURITY_OVERVIEW.md
│   │   ├── LICENSE_KEY_ALGORITHM.md
│   │   ├── TRIAL_TIME_PROTECTION.md
│   │   ├── WORKFLOW_ANTI_CRACK_PROTECTION.md
│   │   ├── WORKFLOW_LICENSE_ISSUANCE.md
│   │   ├── WORKFLOW_LICENSE_SUPPORT.md
│   │   └── ...
│
│   ⚠️ Admin code → 01 - ADMIN - License Security/ | Client code → 02 - CLIENT - VEO PRO MAX/security/
│
├── 📄 README.md                         ← Documentation index
├── 📄 QUICK_START.md                    ← Quick start guide
└── 📄 CHEATSHEET.md                     ← Quick reference
```

---

## 📂 RESEARCH (API Research & Analysis)

```
Research/
│
├── 📁 guides/                           ← Implementation guides (8 files)
│   ├── 01_AUTHENTICATION.md             ← Auth modes, tokens
│   ├── 02_TEXT_TO_VIDEO.md              ← T2V implementation
│   ├── 03_IMAGE_TO_VIDEO.md             ← I2V implementation
│   ├── 04_INGREDIENTS_TO_VIDEO.md       ← R2V implementation
│   ├── 05_VIDEO_UPSCALING.md            ← Video upscale
│   ├── 06_IMAGE_GENERATION.md           ← T2I/I2I implementation
│   ├── 07_IMAGE_UPSCALING.md            ← Image upscale
│   └── 08_ERROR_HANDLING.md             ← Error codes
│
├── 📁 reference/                        ← API reference (8 files)
│   ├── API_ENDPOINTS.md                 ← All endpoints
│   ├── BROWSER_HEADERS.md               ← Required headers
│   ├── MODEL_KEYS.md                    ← All model keys
│   ├── MODEL_MAPPING.md                 ← Model selection
│   ├── PAYLOAD_SCHEMAS.md               ← Request/response schemas
│   ├── SEED_GUIDE.md                    ← Seed handling
│   ├── STATUS_CODES.md                  ← Status codes
│   └── WORKFLOWS.md                     ← API workflows
│
├── 📁 _internal/                        ← Internal analysis (4 files)
│   ├── API_CAPTURE_GUIDE.md             ← How to capture API
│   ├── FINAL_STRUCTURE_VERIFICATION.md  ← Payload verification
│   ├── MODEL_COMPARISON_ANALYSIS.md     ← Model comparison
│   └── UPSCALE_VERIFICATION_REPORT.md   ← Upscale verification
│
├── 📁 _archive_2026-02-01/              ← Archived docs
└── 📁 assets_old/                       ← Old assets
```

---

## 📂 F12 DEV (DevTools Analysis)

```
F12 Dev/
│
├── 📁 New/                              ← Latest HAR captures (50 files)
│   ├── 0. Tao Project.har              ← Project creation
│   ├── 01.* ingredients*.har (6)       ← R2V workflows (9:16, 16:9)
│   ├── 916 frame to video*.har (6)     ← F2V + Upscale flows
│   ├── 916 ingre to video*.har (2)     ← R2V 916 aspect
│   ├── Check *.har (3)                 ← Account status (Ultra/Pro/Free)
│   ├── Download *.har (10)             ← Download 720p, 1080p, 4K, GIF
│   ├── chon firt va last*.har (7)      ← F2V start+end frame
│   ├── Full tạo ảnh.har               ← Complete T2I flow
│   ├── Tao hinh *.har (3)             ← T2I workflows
│   ├── Login dieu huong Flow.har       ← Login flow
│   ├── Model Video*.har (2)            ← Model selection
│   ├── upload/tao video*.har (2)       ← I2V upload + generate
│   ├── download image 4k.har           ← Image download
│   ├── labs.google.har                 ← Full session
│   └── whisk*.har (3)                  ← Whisk integration
│
├── 📁 Old/                              ← Previous HAR captures (65+ files)
│   ├── Check trạng thái tài khoản Ultra hay *.har   ← ⭐ Subscription detection
│   ├── chon firt va last *.har                      ← F2V captures
│   ├── Download *.har                               ← Download captures
│   ├── Tao hinh *.har                               ← Image creation
│   │
│   ├── *.py                             ← Analysis scripts
│   │   ├── find_ultra_v2.py
│   │   ├── analyze_ultra_context.py
│   │   ├── deep_analyze_v2.py
│   │   └── ...
│   │
│   └── *.json                           ← Extracted data
│       ├── session_dump.json            ← Session example
│       └── entry_1_regular.json
│
├── 📄 Analysis scripts:
│   ├── analyze_new_hars.py
│   ├── comprehensive_auth_audit.py
│   ├── final_verification.py
│   ├── header_extractor.py
│   ├── payload_extractor.py
│   └── security_matrix_audit.py
│
└── 📄 Results:
    ├── analysis_result.txt
    ├── payload_extraction_results.md
    ├── final_verification_report.md
    └── security_compliance_matrix.md
```

---

## 🏗️ Document Cross-References

### Core Architecture Documents

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DOCUMENT RELATIONSHIP                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TAB_07_SETTINGS.md (Chrome Profiles)                                        │
│       │                                                                      │
│       └──→ ACCOUNT_SESSION_MANAGEMENT.md (Session, Tokens, Subscription)    │
│                    │                                                         │
│                    └──→ PROJECT_MANAGEMENT.md (VEO Projects)                │
│                    │                                                         │
│                    └──→ MULTITHREADING_ARCHITECTURE.md (ĐẠI CHỦ-CHỦ-THẦU-THỢ)│
│                                 │                                            │
│                                 └──→ RECAPTCHA_BROWSER_MANAGEMENT.md        │
│                                 │                                            │
│                                 └──→ ERROR_HANDLING_STRATEGY.md             │
│                                                                              │
│  WORKFLOW_BROWSER_SESSION.md ←──→ ACCOUNT_SESSION_MANAGEMENT.md             │
│  WORKFLOW_MULTI_COOKIE_PARALLEL.md ←──→ MULTITHREADING_ARCHITECTURE.md      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab Documents → Workflow Documents

```
TAB_01_TEXT_TO_VIDEO.md     → WORKFLOW_TAB_01_TEXT_TO_VIDEO.md
TAB_02_IMAGE_TO_VIDEO.md    → WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md
TAB_03_INGREDIENTS.md       → WORKFLOW_TAB_03_INGREDIENTS.md
TAB_04_TEXT_TO_IMAGE.md     → WORKFLOW_TAB_04_TEXT_TO_IMAGE.md
TAB_05_IMAGE_TO_IMAGE.md    → WORKFLOW_TAB_05_IMAGE_TO_IMAGE.md
```

### UI Docs → Backend Docs

```
01_UI_UX/                   → 03_Backend/
├── TAB_07_SETTINGS.md      → ├── ACCOUNT_SESSION_MANAGEMENT.md
├── TAB_06_QUEUE_MANAGER.md → ├── MULTITHREADING_ARCHITECTURE.md
├── TAB_08_LICENSE.md        → ├── LICENSE_KEY_ALGORITHM.md
└── BUTTON_ACTION_MAPPING.md → └── UI_TO_API_PARAMETER_MAPPING.md
```

---

## 📋 Document Statistics

### By Category

| Category | Count | Description |
|----------|-------|-------------|
| **01_UI_UX** | 18 | UI specifications, tab docs |
| **02_Architecture** | 4 | System architecture |
| **03_Backend** | 14 | Backend logic |
| **04_Workflows** | 16 | Workflow documentation |
| **00_Overview** | — | *(merged into 00_PROJECT)* |
| **05_Security** | 9+ | Security & protection |
| **Research/guides** | 8 | Implementation guides |
| **Research/reference** | 8 | API reference |
| **Total** | **80+** | Full documentation |

### Key Documents (⭐ Priority Reading)

| Document | Purpose |
|----------|---------|
| **ACCOUNT_SESSION_MANAGEMENT.md** | Subscription detection, token management |
| **MULTITHREADING_ARCHITECTURE.md** | ĐẠI CHỦ-CHỦ-THẦU-THỢ pattern |
| **PROJECT_MANAGEMENT.md** | VEO project handling |
| **TAB_06_QUEUE_MANAGER.md** | Queue UI & logic |
| **TAB_07_SETTINGS.md** | Chrome Profiles management |
| **UI_TO_API_PARAMETER_MAPPING.md** | Complete UI → API mapping |
| **VEO_PRODUCTION_WORKFLOWS.md** | Full production workflows |

---

## 📊 API Reference Quick Links

### Endpoints (Research/reference/API_ENDPOINTS.md)

| Endpoint | Doc |
|----------|-----|
| `POST /v1/video:batchAsyncGenerateVideoText` | 02_TEXT_TO_VIDEO.md |
| `POST /v1/video:batchAsyncGenerateVideoStartImage` | 03_IMAGE_TO_VIDEO.md |
| `POST /v1/video:batchAsyncGenerateVideoStartAndEndImage` | 03_IMAGE_TO_VIDEO.md |
| `POST /v1/video:batchAsyncGenerateVideoReferenceImages` | 04_INGREDIENTS_TO_VIDEO.md |
| `POST /v1/video:batchAsyncGenerateVideoUpsampleVideo` | 05_VIDEO_UPSCALING.md |
| `POST /v1/projects/{id}/flowMedia:batchGenerateImages` | 06_IMAGE_GENERATION.md |
| `POST /v1/flow/upsampleImage` | 07_IMAGE_UPSCALING.md |

### Models (Research/reference/MODEL_KEYS.md)

| Type | Model Key Format |
|------|------------------|
| T2V | `veo_3_1_t2v_fast_{aspect}_ultra` |
| I2V | `veo_3_1_i2v_s_fast_{aspect}_ultra_relaxed` |
| F2V | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` |
| R2V | `veo_3_1_r2v_fast_{aspect}_ultra` |

---

## 🔄 Update Tracking

| Date | Changed Files | Description |
|------|---------------|-------------|
| 2026-02-04 | TAB_07_SETTINGS.md, ACCOUNT_SESSION_MANAGEMENT.md | Chrome Profiles update, remove Auto-Sync |
| 2026-02-03 | MULTITHREADING_ARCHITECTURE.md, PROJECT_MANAGEMENT.md | ĐẠI CHỦ-CHỦ-THẦU-THỢ pattern |
| 2026-02-02 | All TAB_*.md files | UI/UX audit fixes |

---

## 📌 Navigation Index

### Quick Access

- **UI Specs**: [01_UI_UX/README.md](../01_UI_UX/README.md)
- **Architecture**: [02_Architecture/MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md)
- **Backend**: [03_Backend/CORE_MODULES_SPEC.md](../03_Backend/CORE_MODULES_SPEC.md)
- **Workflows**: [04_Workflows/VEO_WORKFLOWS.md](../04_Workflows/VEO_WORKFLOWS.md)
- **API Reference**: [Research/reference/](../../Research/reference/)
- **Quick Start**: [QUICK_START.md](../QUICK_START.md)
- **Cheatsheet**: [CHEATSHEET.md](../CHEATSHEET.md)
