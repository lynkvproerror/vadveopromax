# 📋 VEO Pro Max - Implementation Task

**Generated**: 2026-02-05  
**Source**: Documentation/ folder analysis  
**Framework**: PySide6 (Qt6) + Catppuccin Mocha

---

## 📊 Documentation → Implementation Mapping

| Documentation Folder | Files | Implementation Target |
|---------------------|-------|----------------------|
| `01_UI_UX/` | 19 files | `client/ui/` (tabs, popups, widgets) |
| `02_Architecture/` | 6 files | `client/core/` (classes, state machines) |
| `03_Backend/` | 15 files | `client/backend/` (modules, managers) |
| `04_Workflows/` | 16 files | `client/workflows/` (automation logic) |
| `05_Security/` | 9+ files | `client/security/`, `admin/` |

---

## 🏗️ Implementation Structure (Target)

```
client/
├── main.py                          ← Entry point
├── config/
│   ├── __init__.py
│   ├── constants.py                 ← From 00_DESIGN_SYSTEM colors, spacing
│   └── settings.py                  ← From TAB_07_SETTINGS
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py               ← From 00_DESIGN_SYSTEM layout
│   ├── tabs/
│   │   ├── __init__.py
│   │   ├── base_tab.py              ← Sidebar + Workspace pattern
│   │   ├── t2v_tab.py               ← From TAB_01_TEXT_TO_VIDEO
│   │   ├── i2v_tab.py               ← From TAB_02_IMAGE_TO_VIDEO
│   │   ├── ingredients_tab.py       ← From TAB_03_INGREDIENTS
│   │   ├── t2i_tab.py               ← From TAB_04_TEXT_TO_IMAGE
│   │   ├── i2i_tab.py               ← From TAB_05_IMAGE_TO_IMAGE
│   │   ├── queue_tab.py             ← From TAB_06_QUEUE_MANAGER
│   │   ├── settings_tab.py          ← From TAB_07_SETTINGS
│   │   ├── license_tab.py           ← From TAB_08_LICENSE
│   │   ├── about_tab.py             ← From TAB_09_ABOUT
│   │   └── dev_console_tab.py       ← From TAB_10_DEV_CONSOLE
│   ├── popups/
│   │   ├── __init__.py
│   │   ├── edit_prompt_popup.py     ← From 01_POPUP_LAYOUTS #P01
│   │   ├── image_manager_popup.py   ← From 01_POPUP_LAYOUTS #P02
│   │   └── ...                      ← Other popups
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── styled_button.py         ← QSS styling from 00_DESIGN_SYSTEM
│   │   ├── styled_input.py
│   │   └── ...
│   └── theme.py                     ← Catppuccin Mocha colors
│
├── core/
│   ├── __init__.py
│   ├── worker.py                    ← From WORKER_STATE_MACHINE
│   ├── queue_manager.py             ← From PYTHON_CLASS_STRUCTURE
│   ├── session_manager.py           ← From ACCOUNT_SESSION_MANAGEMENT
│   └── project_manager.py           ← From PROJECT_MANAGEMENT
│
├── backend/
│   ├── __init__.py
│   ├── api_client.py                ← From API_MAPPING, UI_TO_API_PARAMETER_MAPPING
│   ├── browser_manager.py           ← From RECAPTCHA_BROWSER_MANAGEMENT
│   ├── download_manager.py          ← From DOWNLOAD_MANAGER
│   ├── image_library.py             ← From 02_IMAGE_LIBRARY_SYSTEM
│   └── batch_import.py              ← From BATCH_IMPORT_LOGIC
│
├── workflows/
│   ├── __init__.py
│   ├── t2v_workflow.py              ← From WORKFLOW_TAB_01
│   ├── i2v_workflow.py              ← From WORKFLOW_TAB_02
│   ├── ingredients_workflow.py      ← From WORKFLOW_TAB_03
│   ├── t2i_workflow.py              ← From WORKFLOW_TAB_04
│   ├── i2i_workflow.py              ← From WORKFLOW_TAB_05
│   ├── browser_session.py           ← From WORKFLOW_BROWSER_SESSION
│   └── multi_account.py             ← From WORKFLOW_MULTI_ACCOUNT_PARALLEL
│
└── security/
    ├── __init__.py
    ├── license_client.py            ← From 05_Security/client/
    ├── trial_protection.py          ← From TRIAL_TIME_PROTECTION
    └── token_security.py            ← From TOKEN_SECURITY
```

---

## ✅ Implementation Phases

### Phase 1: Foundation (Priority 1)
- [ ] `config/constants.py` - Colors, spacing from 00_DESIGN_SYSTEM
- [ ] `ui/theme.py` - Catppuccin Mocha QSS
- [ ] `main.py` - Entry point
- [ ] `ui/main_window.py` - Main window with QTabWidget

### Phase 2: UI Tabs (Priority 2)
- [ ] `ui/tabs/base_tab.py` - Sidebar + Workspace pattern
- [ ] `ui/tabs/t2v_tab.py` - TAB_01 implementation
- [ ] `ui/tabs/i2v_tab.py` - TAB_02 implementation
- [ ] `ui/tabs/ingredients_tab.py` - TAB_03 implementation
- [ ] `ui/tabs/t2i_tab.py` - TAB_04 implementation
- [ ] `ui/tabs/i2i_tab.py` - TAB_05 implementation
- [ ] `ui/tabs/queue_tab.py` - TAB_06 implementation
- [ ] `ui/tabs/settings_tab.py` - TAB_07 implementation
- [ ] `ui/tabs/license_tab.py` - TAB_08 implementation
- [ ] `ui/tabs/about_tab.py` - TAB_09 implementation
- [ ] `ui/tabs/dev_console_tab.py` - TAB_10 implementation

### Phase 3: Popups & Widgets (Priority 3)
- [ ] `ui/popups/` - All 11 popups from 01_POPUP_LAYOUTS
- [ ] `ui/widgets/` - Reusable styled widgets

### Phase 4: Core Logic (Priority 4)
- [ ] `core/worker.py` - Worker state machine
- [ ] `core/queue_manager.py` - Queue management
- [ ] `core/session_manager.py` - Account sessions
- [ ] `core/project_manager.py` - VEO projects

### Phase 5: Backend (Priority 5)
- [ ] `backend/api_client.py` - API calls
- [ ] `backend/browser_manager.py` - Playwright browser
- [ ] `backend/download_manager.py` - Video downloads
- [ ] `backend/image_library.py` - Image library

### Phase 6: Workflows (Priority 6)
- [ ] `workflows/t2v_workflow.py` - T2V automation
- [ ] `workflows/i2v_workflow.py` - I2V automation
- [ ] `workflows/ingredients_workflow.py` - R2V automation
- [ ] `workflows/browser_session.py` - Browser lifecycle

### Phase 7: Security (Priority 7)
- [ ] `security/license_client.py` - License validation
- [ ] `security/trial_protection.py` - Trial limits
- [ ] `security/token_security.py` - Token encryption

---

## 📐 Documentation → Code Traceability

| Documentation File | Target Code File | Key Elements |
|--------------------|------------------|--------------|
| `00_DESIGN_SYSTEM.md` | `config/constants.py`, `ui/theme.py` | Colors, spacing, QSS |
| `TAB_01_TEXT_TO_VIDEO.md` | `ui/tabs/t2v_tab.py` | QLineEdit, QComboBox, QTextEdit |
| `TAB_02_IMAGE_TO_VIDEO.md` | `ui/tabs/i2v_tab.py` | QRadioButton, frame modes |
| `TAB_03_INGREDIENTS.md` | `ui/tabs/ingredients_tab.py` | QTreeWidget, 3 image slots |
| `TAB_06_QUEUE_MANAGER.md` | `ui/tabs/queue_tab.py` | QTreeWidget hierarchy |
| `TAB_07_SETTINGS.md` | `ui/tabs/settings_tab.py` | Chrome Profiles table |
| `01_POPUP_LAYOUTS.md` | `ui/popups/*.py` | 11 popup dialogs |
| `PYTHON_CLASS_STRUCTURE.md` | `core/*.py` | Class hierarchy |
| `ACCOUNT_SESSION_MANAGEMENT.md` | `core/session_manager.py` | Token, subscription |
| `WORKER_STATE_MACHINE.md` | `core/worker.py` | State transitions |
| `WORKFLOW_TAB_*.md` | `workflows/*.py` | Automation steps |

---

## 🔗 Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PySide6 | 6.6.x | UI framework |
| playwright | 1.40.x | Browser automation |
| httpx | 0.25.x | HTTP client |
| cryptography | 41.x | Token encryption |
| firebase-admin | 6.x | License backend |

---

**Status**: 📋 Ready for Implementation
