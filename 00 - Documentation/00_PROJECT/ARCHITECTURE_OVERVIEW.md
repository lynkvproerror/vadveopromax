# 🏗️ Architecture Overview

**Location**: `Documentation/00_PROJECT/ARCHITECTURE_OVERVIEW.md`  
**Last Updated**: 2026-02-04

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VEO PRO MAX ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                           UI LAYER                                     │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │  │
│  │  │  T2V    │ │  I2V    │ │  R2V    │ │  T2I    │ │  I2I    │ ...     │  │
│  │  │ TAB_01  │ │ TAB_02  │ │ TAB_03  │ │ TAB_04  │ │ TAB_05  │         │  │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘         │  │
│  │       │           │           │           │           │               │  │
│  │       └───────────┴─────┬─────┴───────────┴───────────┘               │  │
│  │                         │                                              │  │
│  │  ┌────────────────────────────────────────────────────────────────┐   │  │
│  │  │              TAB_06: QUEUE MANAGER                              │   │  │
│  │  └────────────────────────┬───────────────────────────────────────┘   │  │
│  └───────────────────────────┼───────────────────────────────────────────┘  │
│                              │                                               │
│  ┌───────────────────────────┼───────────────────────────────────────────┐  │
│  │                    ORCHESTRATION LAYER                                 │  │
│  │                           │                                            │  │
│  │  ┌────────────────────────▼────────────────────────────────────────┐  │  │
│  │  │                    ĐẠI CHỦ (MultiAccountManager)                 │  │  │
│  │  │                    Manages N accounts, dispatches to CHỦ         │  │  │
│  │  └────────────────────────┬────────────────────────────────────────┘  │  │
│  │                           │                                            │  │
│  │           ┌───────────────┼───────────────┐                           │  │
│  │           │               │               │                           │  │
│  │  ┌────────▼───────┐ ┌─────▼──────┐ ┌──────▼─────┐                    │  │
│  │  │ CHỦ Account 1  │ │ CHỦ Acc 2  │ │ CHỦ Acc 3  │ ...                │  │
│  │  │ 4 slots        │ │ 4 slots    │ │ 4 slots    │                    │  │
│  │  │ + ProjectMgr   │ │ + ProjMgr  │ │ + ProjMgr  │                    │  │
│  │  └────────┬───────┘ └─────┬──────┘ └──────┬─────┘                    │  │
│  │           │               │               │                           │  │
│  │  ┌────────▼───────────────▼───────────────▼──────────────────────┐   │  │
│  │  │                    THẦU (WorkerDispatcher)                     │   │  │
│  │  │                    Dispatches tasks to available THỢ          │   │  │
│  │  └────────────────────────┬──────────────────────────────────────┘   │  │
│  │                           │                                           │  │
│  │       ┌───────────┬───────┼───────┬───────────┐                      │  │
│  │       │           │       │       │           │                      │  │
│  │  ┌────▼───┐ ┌─────▼──┐ ┌──▼───┐ ┌─▼────┐ ┌────▼───┐                 │  │
│  │  │ THỢ 1  │ │ THỢ 2  │ │ THỢ 3│ │ THỢ 4│ │ THỢ 5  │ ...             │  │
│  │  │ Task A │ │ Task B │ │ IDLE │ │ BUSY │ │ Upsc.  │                 │  │
│  │  └────────┘ └────────┘ └──────┘ └──────┘ └────────┘                 │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         API CLIENT LAYER                              │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                  │  │
│  │  │ VEOApiClient │ │ AuthManager  │ │ BrowserPool  │                  │  │
│  │  │ - T2V        │ │ - Tokens     │ │ - Playwright │                  │  │
│  │  │ - I2V        │ │ - reCAPTCHA  │ │ - Profiles   │                  │  │
│  │  │ - R2V        │ │ - Session    │ │ - Cookies    │                  │  │
│  │  │ - Upscale    │ │              │ │              │                  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         EXTERNAL SERVICES                             │  │
│  │                                                                       │  │
│  │  ┌─────────────────────┐    ┌─────────────────────┐                  │  │
│  │  │ Google VEO API      │    │ Google reCAPTCHA    │                  │  │
│  │  │ aisandbox-pa.       │    │ Enterprise v3       │                  │  │
│  │  │ googleapis.com      │    │                     │                  │  │
│  │  └─────────────────────┘    └─────────────────────┘                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA FLOW                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Action                                                                 │
│       │                                                                      │
│       ▼                                                                      │
│  [UI Tab] → Creates Task → [Queue Manager]                                   │
│                                  │                                           │
│                                  ▼                                           │
│                         [ĐẠI CHỦ] Gets available account                    │
│                                  │                                           │
│                                  ▼                                           │
│                         [CHỦ] Provides:                                      │
│                         - Session (tokens)                                   │
│                         - Project ID                                         │
│                         - Browser context                                    │
│                                  │                                           │
│                                  ▼                                           │
│                         [THẦU] Dispatches to THỢ                            │
│                                  │                                           │
│                                  ▼                                           │
│                         [THỢ] Executes:                                     │
│                         1. Get reCAPTCHA token                              │
│                         2. Upload images (if needed)                        │
│                         3. Call VEO API                                      │
│                         4. Poll status                                       │
│                         5. Download result                                   │
│                                  │                                           │
│                                  ▼                                           │
│                         [Queue Manager] Updates status                       │
│                                  │                                           │
│                                  ▼                                           │
│                         [UI] Shows completed result                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

| Component | Responsibility | Doc Reference |
|-----------|----------------|---------------|
| **ĐẠI CHỦ** | Multi-account coordination | [MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md) |
| **CHỦ** | Single account + project | [ACCOUNT_SESSION_MANAGEMENT.md](../03_Backend/ACCOUNT_SESSION_MANAGEMENT.md) |
| **THẦU** | Task dispatch | [MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md) |
| **THỢ** | Task execution | [MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md) |
| **ProjectManager** | VEO project handling | [PROJECT_MANAGEMENT.md](../03_Backend/PROJECT_MANAGEMENT.md) |
| **Queue Manager** | Task queue UI | [TAB_06_QUEUE_MANAGER.md](../01_UI_UX/TAB_06_QUEUE_MANAGER.md) |

---

## Key Design Patterns

### 1. Multi-Account Pool
```
N accounts × 4 slots = Total parallel capacity
```

### 2. On-Demand Token Refresh
```
No auto-sync → Refresh only when needed
```

### 3. Cross-Account Project Sharing
```
Frame from Account A → Use in Account B
(via local download → re-upload)
```

### 4. Task State Machine
```
PENDING → READY → RUNNING → WAITING_POLL → COMPLETED/FAILED
```

---

## Related Documents

- [MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md)
- [CORE_MODULES_SPEC.md](../03_Backend/CORE_MODULES_SPEC.md)
- [VEO_WORKFLOWS.md](../04_Workflows/VEO_WORKFLOWS.md)
