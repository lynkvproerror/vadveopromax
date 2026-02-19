# 🔧 Tab: Dev Console (Developer Mode)

> **Framework**: PySide6 (Qt6)  
> **Reference**: [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md)  
> **Version**: 4.0 — Sidebar Navigation Redesign

---

## 🗂️ Tab Menu

| Tab | Display Name | Key |
|-----|--------------|-----|
| 01-09 | [Previous tabs...] | |
| **→ 10** | **Dev Console** | `dev` (hidden by default) |

---

## 🔓 Activation Methods

**Method 1**: Settings → Enable Developer Mode  
**Method 2**: License → Show dev banner when license expired  
**Method 3**: Keyboard shortcut `Ctrl+Shift+D`

When enabled:
- Tab 10 becomes visible
- JSON preview before queue submission
- Verbose logging enabled
- Performance metrics shown

---

## 🎨 Layout (Sidebar + Content Workspace)

```
┌──────────────────────────────────────────────────────────────────┐
│ 🛠️ DEVELOPER CONSOLE                                  42 logs  │
├────────────┬─────────────────────────────────────────────────────┤
│            │                                                     │
│ 📊 Dashboard│  ┌──────────────────┐ ┌──────────────────┐        │
│            │  │ 🏭 Throughput    │ │ 👥 Account Health│        │
│ 📋 Queue   │  │ Tasks/hr: 15    │ │ Email  Score Ext │        │
│            │  │ ✅ Done: 42     │ │ acc1@  98%   ✅  │        │
│ 👥 Accounts│  │ ❌ Fail: 2      │ │ acc2@  95%   ✅  │        │
│            │  └──────────────────┘ └──────────────────┘        │
│ 📝 Logs    │  ┌──────────────────┐ ┌──────────────────┐        │
│            │  │ 🔧 Subsystems   │ │ ⚠️ Bottlenecks   │        │
│ 🌐 Network │  │ • reCAPTCHA: OK │ │ ✅ No bottlenecks│        │
│            │  │ • Upscale: 3/0  │ │                  │        │
│            │  └──────────────────┘ └──────────────────┘        │
│            │                                                     │
├────────────┴─────────────────────────────────────────────────────┤
│ Engine: 🟢 Active | 3 running | 42/50 done              21:05  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📑 Sidebar Sections

### 📊 Dashboard (Page 0 — Default)

Engine metrics in a 2×2 card grid.

| Card | Content | Data Source |
|------|---------|-------------|
| 🏭 Throughput | Tasks/hr, active, completed, failed, success rate, avg time | `aggregator` |
| 👥 Account Health | Per-account table: email, slots, score, burst delay, extension | `health_scores` + `burst_controller` |
| 🔧 Subsystems | reCAPTCHA pool hits/misses/rate, Upscale Queue stats, Adaptive Burst | `recaptcha_pool`, `upscale_queue`, `burst_controller` |
| ⚠️ Bottlenecks | Live warning list or "✅ No bottlenecks" | `bottlenecks` |

**API**: `update_engine_dashboard(data)` → `DashboardPage.update_dashboard(data)`

---

### 📋 Queue & Performance (Page 1)

Vertical split: queue state (top) + system performance (bottom).

| Section | Fields |
|---------|--------|
| 📊 Queue State | Total, Pending, Processing, Completed, Failed, Status |
| ⚡ Performance | Uptime, CPU%, RAM MB, Threads, API Calls, Downloads, Errors |

**API**: `update_queue_state(state)`, `update_performance(data)` → `QueuePerfPage`

---

### 👥 Accounts (Page 2)

Per-account scrollable cards consolidating **3 data sources**:

| Data | Source |
|------|--------|
| Plan, Credits, Slots, Session, Token, Expiry, reCAPTCHA | `update_session_data(accounts)` |
| Browser state, Enabled status | `update_browser_status(accounts)` |
| Extension connection, Headers | `update_extension_status(status)` |

**Card layout per account:**
```
┌─ account@gmail.com ──────────────────────────┐
│ Plan: 3M  |  Credits: 50,000  |  Slots: 3/5  │
│ Session: ✅ Valid                              │
│ Token  : abc1234...xyz789                     │
│ Expiry : 14:30                                │
│ reCAPTCHA: ✅ Valid (len=1203)                 │
│ Extension: 🟢 Connected → 5 headers           │
│ Cookies: 45 (google.com: 30, labs: 15)        │
│ Browser: 🟢 Visible  |  Enabled: ✅           │
└───────────────────────────────────────────────┘
```

---

### 📝 Logs (Page 3)

Full-height workspace: live logs (~70%) + JSON preview (~30%).

| Widget | Type | Description |
|--------|------|-------------|
| `_log_text` | `QPlainTextEdit` (read-only) | Live log output (auto-trim 1500 lines) |
| `_json_text` | `QPlainTextEdit` (read-only) | Last submitted task JSON |
| `_search_input` | `QLineEdit` | Text filter (case-insensitive) |
| `_level_combo` | `QComboBox` | Min level: DEBUG/INFO/WARNING/ERROR |
| `_api_btn` | `QPushButton` (toggle) | 📡 API Debug ON/OFF |
| `_scroll_btn` | `QPushButton` (toggle) | 📌 Auto-scroll ON/OFF |
| Clear / Export | `QPushButton` | 🗑️ Clear all / 📤 Export to file |

**Toolbar** is embedded in the Logs page header — only visible when Logs is active.

**API**: `append_log(msg, level)`, `update_json_preview(data)` → `LogsPage`

---

### 🌐 Network (Page 4)

Extension Bridge status + API activity log.

| Section | Content |
|---------|---------|
| 🧩 Extension Bridge | WebSocket status, port, connections, registered tabs, cached headers per email |
| 📡 API Activity | Filtered API/HTTP log entries (last 200 lines, auto-scroll) |

**API**: `update_extension_status(status)` → `NetworkPage`

---

## 🧩 Architecture

```
tab_devconsole.py
├── Logging infra (QtLogHandler, _StreamToLogger — unchanged)
├── TabDevConsole (QWidget)
│   ├── Toolbar (QFrame, 40px)
│   ├── QSplitter (horizontal)
│   │   ├── Sidebar (QListWidget, 180px, Mantle bg)
│   │   └── QStackedWidget
│   │       ├── [0] DashboardPage  ← page_dashboard.py
│   │       ├── [1] QueuePerfPage  ← page_queue.py
│   │       ├── [2] AccountsPage   ← page_accounts.py
│   │       ├── [3] LogsPage       ← page_logs.py
│   │       └── [4] NetworkPage    ← page_network.py
│   └── Status Bar (QFrame, 28px)
└── Public API methods (route to pages)
```

### File Structure

```
ui/tabs/
├── tab_devconsole.py           # Main tab: sidebar + logging infra
└── devconsole/                 # Page widgets
    ├── __init__.py
    ├── page_dashboard.py       # 📊 Engine metrics cards
    ├── page_queue.py           # 📋 Queue + Performance
    ├── page_accounts.py        # 👥 Session + Browser + Extension
    ├── page_logs.py            # 📝 Live logs + JSON
    └── page_network.py         # 🌐 Extension bridge + API
```

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system |
| [ENGINE_PIPELINE_ARCHITECTURE.md](../02_Architecture/ENGINE_PIPELINE_ARCHITECTURE.md) | Engine pipeline |

---

**Status**: ✅ v4.0 — Sidebar Navigation Redesign (2026-02-18)
