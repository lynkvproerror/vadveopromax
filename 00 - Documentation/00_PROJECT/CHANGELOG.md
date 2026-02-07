# 📋 CHANGELOG

**Location**: `Documentation/00_PROJECT/CHANGELOG.md`  
**Purpose**: Version history and breaking changes

---

## v1.1.0 (2026-02-07) - Architecture Sync & Documentation Cleanup

### 🔧 Technical
- **asyncio Migration**: Refactored core modules from `threading` → `asyncio` primitives
- **New modules**: `engine.py` (pipeline orchestrator), `project_manager.py` (project ID management)
- **PaygateTier enum**: Updated to match F12 API response keys
- **WAITING_POLL state**: Added to task state machine

### ⛔ Deprecated
- `PYTHON_CLASS_STRUCTURE.md` → see `MULTITHREADING_ARCHITECTURE.md`
- `WORKER_STATE_MACHINE.md` → see `MULTITHREADING_ARCHITECTURE.md`

### 📄 Documentation
- Consolidated duplicate docs (LICENSE_SYSTEM, TROUBLESHOOTING, FIREBASE_SECURITY_RULES)
- Archived legacy style guides (CustomTkinter, PySide6 admin)
- Archived completed issue trackers (OUTSTANDING_ISSUES_TASK, PROJECT_AUDIT_REPORT)
- Archived 87KB LICENSE_PROTECTION_SYSTEM monolith (content split into 17 docs)
- Renamed `01_`-`04_` files in UI_UX to avoid TAB numbering confusion
- Fixed all cross-document references to deprecated files

### 🗑️ Removed
- Duplicate `WorkerState`, `SubscriptionType` enums from `constants.py`
- `threading` imports from refactored core modules
- `__pycache__/`, `dist/` from Documentation directory

---

## v1.0.0 (2026-02-04) - Initial Release

### 🎉 Features
- **Multi-Account Management**: ĐẠI CHỦ-CHỦ-THẦU-THỢ pattern
- **Chrome Profiles**: Isolated browser profiles per account
- **VEO Project Management**: Auto-create, cache, share
- **Queue Manager**: 10 tabs × multi-account parallel processing

### 📄 Documentation
- Complete UI/UX specs (TAB_01-10)
- Backend architecture (14 docs)
- Workflow documentation (16 workflows)
- Research guides (8 guides) + Reference (8 refs)

### 🔧 Technical
- Session management with on-demand token refresh
- Subscription detection from API response (`sku`, `userPaygateTier`)
- reCAPTCHA v3 handling

---

## v0.9.0 (2026-02-01) - Documentation Complete

### 📄 Added
- `ACCOUNT_SESSION_MANAGEMENT.md`
- `MULTITHREADING_ARCHITECTURE.md`
- `PROJECT_MANAGEMENT.md`
- All TAB workflow docs

### 🔄 Changed
- Removed Auto-Sync from Settings (now on-demand)
- Updated Chrome Profiles with Credits column

---

## v0.8.0 (2026-01-28) - Research Phase

### 📄 Added
- HAR file analysis
- API endpoint documentation
- Model key mappings

---

## Format Guide

```markdown
## v{MAJOR}.{MINOR}.{PATCH} (YYYY-MM-DD) - Title

### 🎉 Features (New features)
### 🔧 Technical (Backend changes)
### 🐛 Bug Fixes
### 📄 Documentation
### 🔄 Changed
### ⚠️ Breaking Changes
### ⛔ Deprecated
### 🗑️ Removed
```
