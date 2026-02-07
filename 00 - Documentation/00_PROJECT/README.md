# VEO Pro Max - Project Overview

**Version**: 1.1.0 (Architecture Sync & Documentation Cleanup)  
**Created**: 2026-02-01  
**Updated**: 2026-02-07  
**Type**: Pure API Client with PySide6 UI

---

## 🎯 Project Goal

Build a **pure API-based VEO client** that replaces Playwright/JavaScript approach with direct HTTP requests following the VEO API documentation.

---

## 📚 Documentation Sources

| Source | Purpose |
|--------|---------|
| `D:\...\VEO Tool\Documentation` | API endpoints, workflows, models |
| `D:\...\VEO PRO MAX` | PySide6 UI application source |

---

## 🔧 Key Design Decisions

### Token Management

**Dual Approach** (A + B):
- **A) Manual Input**: User pastes Bearer token from DevTools
- **B) Auto-Extract**: Playwright minimal browser for token extraction

### Architecture

| Component | Technology |
|-----------|------------|
| UI Framework | PySide6 |
| HTTP Client | requests + aiohttp |
| Token Auto-Extract | Playwright |
| Config | JSON persistence |

---

## 📂 Implementation Status

### Code Structure
```
02 - CLIENT - VEO PRO MAX/
├── core/              # Core modules
│   └── api_client, auth_manager, queue_manager, engine, etc.
│
├── ui/                # PySide6 UI modules
│   └── 10 tabs: T2V, I2V, R2V, T2I, I2I, Queue, Settings, License, About, DevConsole
│
└── Entry points: main.py, run.py, build.py
```

---

## 🚀 Development Priority

| Priority | Area | Status |
|----------|------|--------|
| **1** | Phase 1: Core Engine | ✅ **Complete** |
| **2** | Phase 2: Multi-Account | ✅ **Complete** |
| **3** | Phase 3: UI + 8 Tabs | ✅ **Complete** |
| 4 | Phase 4A: Utils (Logger, Settings) | ⏳ Pending |
| 5 | Phase 4B: UI (I2I, About, DevConsole) | ⏳ Pending |
| 6 | Phase 4C: Advanced Features | ⏳ Pending |

---

## 🔗 Related Documentation

- [API Endpoints](../Research/reference/API_ENDPOINTS.md)
- [Task List](../../TASK_LIST.md)
- [New Data Findings](../../NEW_DATA_FINDINGS.md)

---

**Last Updated**: 2026-02-07

