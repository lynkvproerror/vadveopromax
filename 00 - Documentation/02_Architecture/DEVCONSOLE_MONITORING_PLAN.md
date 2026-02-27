# 📊 DevConsole Monitoring Enhancement Plan

> **Version**: 1.0 • **Created**: 2026-02-25  
> **Scope**: Bổ sung 12 datapoints backend chưa hiển thị trên DevConsole.  
> **Status**: ✅ IMPLEMENTED — 2026-02-25  
> **Related**: [TAB_KEEPALIVE_ARCHITECTURE.md](./TAB_KEEPALIVE_ARCHITECTURE.md), [ENGINE_PIPELINE_ARCHITECTURE.md](./ENGINE_PIPELINE_ARCHITECTURE.md)

---

## 1. Tổng quan — Hiện trạng vs Mục tiêu

### 1.1 Hiện trạng DevConsole

DevConsole gồm 5 trang, hiển thị **phần lớn** dữ liệu cơ bản:

| Trang | Số metric hiện tại | Đánh giá |
|-------|:---:|---|
| 📊 Dashboard (4 cards) | 15 | ✅ Tốt — Throughput, Account Health, Subsystems, Bottlenecks |
| 📋 Queue & Performance | 10 | ✅ Đủ — Queue counts, system resources |
| 👥 Accounts | 9/account | ✅ Tốt — Token, reCAPTCHA, Extension, Cookies, Browser, Pre-warm |
| 📝 Logs | ∞ (streaming) | ✅ Tốt — Full Python logging stream |
| 🌐 Network | 5 | ✅ Đủ — WebSocket, registered tabs, API activity |
| **Tổng hiển thị** | **~39** | |

### 1.2 Thiếu sót

**12 datapoints backend** có sẵn dữ liệu nhưng **không hiển thị** trên UI:

| # | Datapoint | Nhóm | Ưu tiên |
|---|-----------|------|---------|
| 1 | Tab Keepalive state (ACTIVE/PAUSED/STOPPED) | 🛡️ Keepalive | 🔴 Cao |
| 2 | Keepalive ping count (tabs pinged mỗi cycle) | 🛡️ Keepalive | 🟡 TB |
| 3 | Keepalive ↔ Engine coordination (ai đang control) | 🛡️ Keepalive | 🔴 Cao |
| 4 | Circuit Breaker state per-account (CLOSED/OPEN/HALF_OPEN) | ⚡ Circuit | 🔴 Cao |
| 5 | Circuit Breaker open duration | ⚡ Circuit | 🟡 TB |
| 6 | Consecutive 403 count per-account | ⚡ Circuit | 🔴 Cao |
| 7 | Account Cooldown remaining time | ❄️ Cooldown | 🔴 Cao |
| 8 | Cooldown backoff level (30/60/120/180s) | ❄️ Cooldown | 🟡 TB |
| 9 | Workload Priority mode (720p_priority/upscale_priority) | 🔧 Config | 🟢 Thấp |
| 10 | Recent errors list (last 5) | 📊 StatusAgg | 🟡 TB |
| 11 | reCAPTCHA Pool per-account depth | 🔑 reCAPTCHA | 🟡 TB |
| 12 | Rate Lock contention (who holds/waits) | 🔒 Concurrency | 🟢 Thấp |

---

## 2. Phân nhóm và Design

### 2.1 Nhóm A: Tab Keepalive Status (Datapoints #1, #2, #3)

**Vị trí UI**: Dashboard → card "🔧 Subsystems" (thêm dòng mới)

**Data flow mới**:
```
Engine._keepalive_yield.is_set()  ─┐
Engine._keepalive_stop.is_set()   ─┤
Engine._keepalive_last_ping_count ─┼→ Engine.get_dashboard_stats()
Engine._keepalive_last_ping_time  ─┘     → dashboard["keepalive"]
                                              → DashboardPage._update_subsystems()
```

**Backend thay đổi** — `engine.py`:
```python
# Thêm vào __init__ hoặc set bởi _tab_keepalive_loop:
self._keepalive_last_ping_count: int = 0
self._keepalive_last_ping_time: float = 0

# Thêm vào get_dashboard_stats():
stats["keepalive"] = {
    "state": self._get_keepalive_state(),   # "ACTIVE" | "PAUSED" | "STOPPED" | "NOT_STARTED"
    "last_ping_count": self._keepalive_last_ping_count,
    "last_ping_time": self._keepalive_last_ping_time,  # timestamp
    "controller": "keepalive" if yield_set else "engine",
}

def _get_keepalive_state(self) -> str:
    stop = getattr(self, '_keepalive_stop', None)
    yield_ev = getattr(self, '_keepalive_yield', None)
    if not stop or not yield_ev:
        return "NOT_STARTED"
    if stop.is_set():
        return "STOPPED"
    return "ACTIVE" if yield_ev.is_set() else "PAUSED"
```

**Frontend thay đổi** — `page_dashboard.py`:
```python
# Trong _update_subsystems(), thêm sau phần Pre-warm:
ka = data.get("keepalive", {})
if ka:
    state = ka.get('state', 'NOT_STARTED')
    state_icons = {
        "ACTIVE": "🟢 ACTIVE",
        "PAUSED": "⏸️ PAUSED (Engine Processing)",
        "STOPPED": "🔴 STOPPED",
        "NOT_STARTED": "⚪ Not Started",
    }
    controller = ka.get('controller', '?')
    ping_count = ka.get('last_ping_count', 0)
    lines.append(f"• Tab Keepalive: {state_icons.get(state, state)}")
    lines.append(f"  └ Controller: {controller}  |  Last ping: {ping_count} tabs")
```

**Sửa trong `_tab_keepalive_loop()`** — cập nhật tracking vars mỗi cycle:
```python
# Sau khi ping xong tất cả accounts:
self._keepalive_last_ping_count = pinged
self._keepalive_last_ping_time = time.time()
```

**Files sửa**:
| File | Thay đổi |
|------|---------|
| `core/engine.py` | Thêm 2 tracking vars, method `_get_keepalive_state()`, cập nhật `get_dashboard_stats()`, cập nhật `_tab_keepalive_loop()` |
| `ui/tabs/devconsole/page_dashboard.py` | Thêm render keepalive trong `_update_subsystems()` |

**Ước tính**: ~30 dòng code

---

### 2.2 Nhóm B: Circuit Breaker Status (Datapoints #4, #5, #6)

**Vị trí UI**: 
- Dashboard → card "👥 Account Health" (thêm cột CB)
- Accounts → per-account card (thêm dòng Circuit Breaker)

**Data flow mới**:
```
Engine._circuit_state[email]           ─┐
Engine._circuit_open_since[email]      ─┤→ Engine.get_dashboard_stats()
Engine._circuit_consecutive_403[email] ─┘     → dashboard["circuit_breaker"]
                                                  → DashboardPage + AccountsPage
```

**Backend thay đổi** — `engine.py`:
```python
# Thêm vào get_dashboard_stats():
stats["circuit_breaker_status"] = {}
for email in self._circuit_state:
    state = self._circuit_state.get(email, "closed")
    open_since = self._circuit_open_since.get(email, 0)
    duration = round(time.time() - open_since) if open_since and state != "closed" else 0
    stats["circuit_breaker_status"][email] = {
        "state": state,                                    # "closed" | "open" | "half_open"
        "consecutive_403": self._circuit_consecutive_403.get(email, 0),
        "open_duration_sec": duration,
    }
```

**Frontend thay đổi — Dashboard** (`page_dashboard.py`):
```python
# Trong _update_accounts(), thêm cột CB:
# Header: Account | Slots | Score | Burst | CB   | Ext
# Data:            | 2/5   | 85    | 3.0s  | 🟢  | ✅
#                  |       |       |       | 🔴3 |
# CB icons: 🟢=CLOSED, 🟡=HALF_OPEN, 🔴=OPEN (+count)
```

**Frontend thay đổi — Accounts** (`page_accounts.py`):
```python
# Trong _render_all(), thêm dòng per-account:
cb = self._circuit_data.get(email, {})
if cb:
    cb_state = cb.get("state", "closed")
    cb_403 = cb.get("consecutive_403", 0)
    cb_icons = {"closed": "🟢 OK", "open": f"🔴 OPEN ({cb.get('open_duration_sec', 0)}s)", 
                "half_open": "🟡 PROBING"}
    lines.append(f"Circuit: {cb_icons.get(cb_state, cb_state)}  |  403s: {cb_403}")
```

**Files sửa**:
| File | Thay đổi |
|------|---------|
| `core/engine.py` | Thêm `circuit_breaker_status` vào `get_dashboard_stats()` |
| `ui/tabs/devconsole/page_dashboard.py` | Thêm cột CB trong `_update_accounts()` |
| `ui/tabs/devconsole/page_accounts.py` | Thêm `_circuit_data` storage + render circuit row |
| `ui/tabs/tab_devconsole.py` | Forward `circuit_breaker_status` từ dashboard data đến accounts page |

**Ước tính**: ~50 dòng code

---

### 2.3 Nhóm C: Account Cooldown Status (Datapoints #7, #8)

**Vị trí UI**:
- Dashboard → card "👥 Account Health" (thêm cột CD)
- Accounts → per-account card (thêm dòng Cooldown)

**Data flow mới**:
```
Engine._account_cooldowns[email]       ─┐→ Engine.get_dashboard_stats()
Engine._account_cooldown_backoff[email]─┘     → dashboard["cooldowns"]
                                                  → DashboardPage + AccountsPage
```

**Backend thay đổi** — `engine.py`:
```python
# Thêm vào get_dashboard_stats():
stats["cooldowns"] = {}
now = datetime.now()
for email, until in self._account_cooldowns.items():
    remaining = max(0, (until - now).total_seconds())
    if remaining > 0:
        stats["cooldowns"][email] = {
            "remaining_sec": round(remaining),
            "backoff_level": self._account_cooldown_backoff.get(email, 0),
            "until": until.isoformat(),
        }
```

**Frontend thay đổi — Dashboard** (`page_dashboard.py`):
```python
# Trong _update_accounts(), thêm cột CD (cooldown):
# Hiển thị: ❄️60s (đang cooldown 60s remaining)
# Hiển thị: ✅ (không cooldown)
```

**Frontend thay đổi — Accounts** (`page_accounts.py`):
```python
# Thêm dòng per-account:
cd = self._cooldown_data.get(email, {})
if cd:
    remaining = cd.get("remaining_sec", 0)
    level = cd.get("backoff_level", 0)
    lines.append(f"Cooldown: ❄️ {remaining}s remaining  |  Level: {level} (30→60→120→180s)")
else:
    # Không thêm dòng nếu không có cooldown — tránh noise
    pass
```

**Files sửa**:
| File | Thay đổi |
|------|---------|
| `core/engine.py` | Thêm `cooldowns` vào `get_dashboard_stats()` |
| `ui/tabs/devconsole/page_dashboard.py` | Thêm cột CD trong `_update_accounts()` |
| `ui/tabs/devconsole/page_accounts.py` | Thêm `_cooldown_data` storage + render cooldown row |
| `ui/tabs/tab_devconsole.py` | Forward `cooldowns` từ dashboard data đến accounts page |

**Ước tính**: ~40 dòng code

---

### 2.4 Nhóm D: Recent Errors + reCAPTCHA Pool Detail (Datapoints #10, #11)

**Vị trí UI**:
- Dashboard → card "⚠️ Bottlenecks" — thêm recent errors
- Dashboard → card "🔧 Subsystems" — thêm per-account pool depth

**Data flow**: Data ĐÃ CÓ SẴN trong `get_engine_dashboard()` return dict — chỉ cần **render** trong frontend.

**Không cần sửa backend** — data đã có:
- `StatusAggregator.get_dashboard()["recent_errors"]` — list of last 5 errors
- `RecaptchaPool.get_stats()["pool_sizes"]` — dict `{email: pool_depth}`

**Frontend thay đổi — Dashboard** (`page_dashboard.py`):

```python
# 1. Trong _update_bottlenecks(), thêm recent errors:
def _update_bottlenecks(self, bottlenecks: list, recent_errors: list = None):
    lines = []
    if bottlenecks:
        lines.extend([f"• {bn}" for bn in bottlenecks])
    else:
        lines.append("✅ No bottlenecks detected")
    
    # Recent errors (already in aggregator.get_dashboard()["recent_errors"])
    if recent_errors:
        lines.append("")
        lines.append("── Recent Errors ──")
        for err in recent_errors[-5:]:
            t = err.get("time", "")
            reason = err.get("reason", "?")[:60]
            lines.append(f"  {t} | {reason}")
    
    self._bottlenecks_card.setPlainText("\n".join(lines))

# 2. Trong _update_subsystems(), mở rộng reCAPTCHA pool:
pool = data.get("recaptcha_pool", {})
if pool:
    lines.append(
        f"• reCAPTCHA Pool: hits={pool.get('hits', 0)}, "
        f"misses={pool.get('misses', 0)}, "
        f"rate={pool.get('hit_rate', 0):.1f}%"
    )
    # Per-account pool depth (NEW)
    pool_sizes = pool.get("pool_sizes", {})
    if pool_sizes:
        for email, depth in pool_sizes.items():
            short = email.split('@')[0][:12]
            lines.append(f"  └ {short}: {depth} tokens ready")
```

**Caller sửa** — `page_dashboard.py`:
```python
# update_dashboard() cần truyền recent_errors:
def update_dashboard(self, data: dict):
    agg = data.get("aggregator", {})
    self._update_throughput(agg)
    self._update_accounts(...)
    self._update_subsystems(data)
    self._update_bottlenecks(
        data.get("bottlenecks", []),
        recent_errors=agg.get("recent_errors", []),  # NEW
    )
```

**Files sửa**:
| File | Thay đổi |
|------|---------|
| `ui/tabs/devconsole/page_dashboard.py` | Mở rộng `_update_bottlenecks()` + `_update_subsystems()` |

**Ước tính**: ~25 dòng code

---

### 2.5 Nhóm E: Config + Minor Info (Datapoints #9, #12)

**Ưu tiên thấp** — thông tin phụ trợ, ít ảnh hưởng debugging.

#### #9. Workload Priority Mode

**Vị trí**: Dashboard → "🔧 Subsystems"

```python
# engine.py — get_dashboard_stats():
stats["workload_priority"] = self._workload_priority

# page_dashboard.py — _update_subsystems():
wp = data.get("workload_priority", "720p_priority")
wp_display = {"720p_priority": "720p First", "upscale_priority": "Upscale First"}
lines.append(f"• Workload: {wp_display.get(wp, wp)}")
```

#### #12. Rate Lock Contention

**Phức tạp hơn** — `asyncio.Lock` không expose waiter count. Cần wrapper:

```python
# Option A (đơn giản): Chỉ hiển thị lock.locked() — đang bị hold hay không
stats["rate_locks"] = {
    email: {"locked": lock.locked()}
    for email, lock in self._account_rate_locks.items()
}

# Option B (chi tiết): Custom lock wrapper track wait count — PHỨC TẠP, SKIP
```

**Quyết định**: Implement Option A (1 dòng per account: 🔒 Locked / 🔓 Free). Skip waiter count.

**Files sửa**:
| File | Thay đổi |
|------|---------|
| `core/engine.py` | Thêm 2 keys vào `get_dashboard_stats()` |
| `ui/tabs/devconsole/page_dashboard.py` | Thêm 2 dòng render |

**Ước tính**: ~15 dòng code

---

## 3. Bảng tổng hợp — Tất cả thay đổi theo file

### 3.1 Backend (`core/`)

| File | Nhóm | Thay đổi | Dòng ước tính |
|------|------|---------|:---:|
| `core/engine.py` | A | Thêm `_keepalive_last_ping_count`, `_keepalive_last_ping_time`, method `_get_keepalive_state()` | 15 |
| `core/engine.py` | A | Cập nhật `_tab_keepalive_loop()` — ghi tracking vars mỗi cycle | 3 |
| `core/engine.py` | A+B+C+E | Mở rộng `get_dashboard_stats()` — thêm `keepalive`, `circuit_breaker_status`, `cooldowns`, `workload_priority`, `rate_locks` | 35 |
| | | **Subtotal engine.py** | **~53** |

### 3.2 Frontend (`ui/tabs/devconsole/`)

| File | Nhóm | Thay đổi | Dòng ước tính |
|------|------|---------|:---:|
| `page_dashboard.py` | A | Render keepalive status trong `_update_subsystems()` | 8 |
| `page_dashboard.py` | B+C | Thêm cột CB + CD trong `_update_accounts()` | 15 |
| `page_dashboard.py` | D | Mở rộng `_update_bottlenecks()` — thêm recent errors | 10 |
| `page_dashboard.py` | D | Mở rộng `_update_subsystems()` — per-account reCAPTCHA pool | 5 |
| `page_dashboard.py` | E | Thêm workload priority + rate lock lines | 5 |
| `page_dashboard.py` | D | Sửa `update_dashboard()` — truyền `recent_errors` | 3 |
| | | **Subtotal page_dashboard.py** | **~46** |
| `page_accounts.py` | B+C | Thêm `_circuit_data`, `_cooldown_data`, 2 method `update_*`, render 2 rows | 25 |
| `tab_devconsole.py` | B+C | Forward circuit + cooldown data từ dashboard → accounts page | 6 |
| | | **Subtotal accounts + tab** | **~31** |

### 3.3 Tổng kết

| Metric | Giá trị |
|--------|---------|
| **Files sửa** | 4 files |
| **Dòng code mới** | ~130 dòng |
| **Dòng code sửa** | ~20 dòng |
| **Tổng thay đổi** | ~150 dòng |
| **Files mới** | 0 |
| **Risk level** | 🟢 Thấp — chỉ đọc data + render, không thay đổi logic |

---

## 4. Thứ tự triển khai

### Phase 1: Backend Data Collection (engine.py)

Tất cả backend changes trong 1 commit — mở rộng `get_dashboard_stats()`.

**Bước 1.1**: Thêm tracking vars cho keepalive
```
engine.py __init__:
  + self._keepalive_last_ping_count = 0
  + self._keepalive_last_ping_time = 0.0
```

**Bước 1.2**: Cập nhật `_tab_keepalive_loop()` ghi tracking
```
engine.py _tab_keepalive_loop():
  # Sau khi ping xong:
  + self._keepalive_last_ping_count = pinged
  + self._keepalive_last_ping_time = time.time()
```

**Bước 1.3**: Thêm method `_get_keepalive_state()`
```
engine.py:
  + def _get_keepalive_state(self) -> str:
  +     # Return "ACTIVE"|"PAUSED"|"STOPPED"|"NOT_STARTED"
```

**Bước 1.4**: Mở rộng `get_dashboard_stats()` — thêm 5 keys mới
```
engine.py get_dashboard_stats():
  + stats["keepalive"] = { state, last_ping_count, last_ping_time, controller }
  + stats["circuit_breaker_status"] = { email: { state, consecutive_403, open_duration_sec } }
  + stats["cooldowns"] = { email: { remaining_sec, backoff_level, until } }
  + stats["workload_priority"] = self._workload_priority
  + stats["rate_locks"] = { email: { locked: bool } }
```

**Verify**: Chạy `python -c "import ast; ast.parse(open('core/engine.py', encoding='utf-8-sig').read()); print('OK')"` 

---

### Phase 2: Dashboard Page Rendering (page_dashboard.py)

**Bước 2.1**: Mở rộng `_update_subsystems()` — thêm Keepalive, Pool depth, Workload Priority
```
page_dashboard.py _update_subsystems():
  + Render keepalive state với icon
  + Render per-account reCAPTCHA pool depth
  + Render workload priority mode
```

**Bước 2.2**: Mở rộng `_update_accounts()` — thêm cột CB + CD
```
page_dashboard.py _update_accounts():
  + Header: thêm CB, CD columns
  + Data row: circuit state icon + cooldown remaining
```

**Bước 2.3**: Mở rộng `_update_bottlenecks()` — thêm recent errors
```
page_dashboard.py _update_bottlenecks():
  + Accept recent_errors parameter
  + Render last 5 errors with timestamp + reason
```

**Bước 2.4**: Sửa `update_dashboard()` — truyền data mới
```
page_dashboard.py update_dashboard():
  + Pass circuit_breaker_status, cooldowns, rate_locks to _update_accounts()
  + Pass recent_errors to _update_bottlenecks()
```

---

### Phase 3: Accounts Page Enhancement (page_accounts.py + tab_devconsole.py)

**Bước 3.1**: Thêm data storage + update methods
```
page_accounts.py:
  + self._circuit_data: dict = {}
  + self._cooldown_data: dict = {}
  + def update_circuit_data(self, data: dict)
  + def update_cooldown_data(self, data: dict)
```

**Bước 3.2**: Mở rộng `_render_all()` — thêm 2 row per-account
```
page_accounts.py _render_all():
  + Render Circuit Breaker row (after Extension row)
  + Render Cooldown row (after Circuit row, chỉ khi đang cooldown)
```

**Bước 3.3**: Forward data trong TabDevConsole
```
tab_devconsole.py update_engine_dashboard():
  + Forward circuit_breaker_status → accounts page
  + Forward cooldowns → accounts page
```

---

### Phase 4: Verify

**Bước 4.1**: Syntax check tất cả files đã sửa
```powershell
python -c "import ast; [ast.parse(open(f, encoding='utf-8-sig').read()) or print(f'{f}: OK') for f in ['core/engine.py', 'ui/tabs/devconsole/page_dashboard.py', 'ui/tabs/devconsole/page_accounts.py', 'ui/tabs/tab_devconsole.py']]"
```

**Bước 4.2**: Verify dashboard data shape
```python
# Trong engine, log output để verify:
import json
log.debug(f"[Dashboard] Stats: {json.dumps(stats, default=str)[:500]}")
```

---

## 5. UI Mockup — Dashboard sau khi hoàn thành

```
┌─────────────────────────────────────────────────────────────────┐
│ 📊 Engine Dashboard                                             │
├─────────────────────────┬───────────────────────────────────────┤
│ 🏭 Throughput           │ 👥 Account Health                     │
│                         │                                       │
│ Tasks/hr : 12  |  2     │ Account         Slots Score Burst CB   CD   Ext│
│ ✅ Done  : 45           │ ─────────────── ───── ───── ───── ──── ──── ───│
│ ❌ Failed: 3            │ user1@gm..     2/5    85   3.0s  🟢   ✅   ✅│
│ 📈 Rate  : 93.8%        │ user2@gm..     0/5    60   5.0s  🔴3  ❄️45s ✅│
│ ⏱ Avg   : 4m 32s       │ user3@gm..     3/5    90   2.0s  🟡   ✅   ✅│
│ Recent err: 6%          │                                       │
├─────────────────────────┼───────────────────────────────────────┤
│ 🔧 Subsystems           │ ⚠️ Bottlenecks                        │
│                         │                                       │
│ • reCAPTCHA Pool:       │ • stuck_task: task_abc (18min, POLL)  │
│   hits=120, miss=8,     │                                       │
│   rate=93.8%            │ ── Recent Errors ──                   │
│   └ user1: 2 tokens     │   10:23:45 | HTTP 403 reCAPTCHA...   │
│   └ user2: 0 tokens     │   10:25:12 | Download timeout...     │
│ • Upscale Queue: p=3,   │   10:30:01 | Extension disconnect... │
│   done=40, fail=1       │                                       │
│ • Adaptive Burst:       │                                       │
│   avg delay=3.5s        │                                       │
│ • Tab Keepalive:        │                                       │
│   🟢 ACTIVE             │                                       │
│   └ Controller: keepalive│                                      │
│   └ Last ping: 3 tabs   │                                       │
│ • Pre-warm: ✅ ON       │                                       │
│   (threshold: 10m)      │                                       │
│ • Workload: 720p First  │                                       │
└─────────────────────────┴───────────────────────────────────────┘
```

---

## 6. UI Mockup — Per-Account Card sau khi hoàn thành

```
┌─ 📧 user2@gmail.com ──────────────────────────────────────────┐
│ Plan: free  |  Credits: 1,200  |  Workers: 2/5                │
│ Session: ✅ Active                                             │
│ Token  : eyJhbGci...w5Nk2SQ                                  │
│ Expiry : 2026-02-25 11:30:00                                  │
│ reCAPTCHA: ✅ Ready                                            │
│ Extension: 🟢 Connected → 3 headers (client-data, goog, sapisi)│
│ Circuit: 🔴 OPEN (45s)  |  403s: 6                   ← MỚI   │
│ Cooldown: ❄️ 45s remaining  |  Level: 2 (60s)         ← MỚI   │
│ Cookies: 142 (google.com: 85, youtube.com: 57)                │
│ Browser: 🟡 Hidden  |  Enabled: ✅                             │
│ Pre-warm: idle=2m30s  |  Warms: 3                             │
└───────────────────────────────────────────────────────────────┘
```

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|:-:|:-:|---|
| Dashboard refresh quá chậm do nhiều data hơn | 🟢 Thấp | 🟢 Thấp | `get_dashboard_stats()` chỉ đọc dict values — O(N accounts), N < 100 |
| asyncio.Event `.is_set()` gọi từ non-async thread | 🟡 TB | 🔴 Cao | `asyncio.Event.is_set()` thread-safe cho read-only — OK |
| Account Health table quá rộng (thêm 2 cột) | 🟡 TB | 🟢 Thấp | Dùng abbreviation (CB, CD), rút gọn data |
| `_account_cooldowns` access race condition | 🟢 Thấp | 🟡 TB | `get_dashboard_stats()` gọi từ main thread qua QTimer, dict read thread-safe |
| `datetime.now()` comparison cho cooldown | 🟢 Thấp | 🟢 Thấp | Worst case: tính sai ±1s — acceptable |

**Overall Risk**: 🟢 **Thấp** — Tất cả thay đổi đều read-only, không sửa logic.

---

## 8. Acceptance Criteria

Sau khi hoàn thành, DevConsole cần hiển thị:

| # | Datapoint | Kiểm tra |
|---|-----------|---------|
| ✅ 1 | Keepalive state | Dashboard Subsystems hiển thị 🟢 ACTIVE hoặc ⏸️ PAUSED |
| ✅ 2 | Keepalive ping count | Dashboard hiển thị "Last ping: N tabs" |
| ✅ 3 | Keepalive controller | Dashboard hiển thị "Controller: keepalive" hoặc "engine" |
| ✅ 4 | Circuit Breaker state | Account Health table cột CB: 🟢/🟡/🔴 |
| ✅ 5 | Circuit open duration | Account card: "OPEN (45s)" |
| ✅ 6 | Consecutive 403 | Account Health table: 🔴3 (3 consecutive) |
| ✅ 7 | Cooldown remaining | Account Health table cột CD: ❄️45s |
| ✅ 8 | Cooldown backoff | Account card: "Level: 2 (60s)" |
| ✅ 9 | Workload Priority | Dashboard Subsystems: "Workload: 720p First" |
| ✅ 10 | Recent errors | Bottlenecks card: last 5 errors with timestamp |
| ✅ 11 | reCAPTCHA pool depth | Subsystems: per-account "2 tokens ready" |
| ✅ 12 | Rate Lock status | (Optional) Account card: 🔒 Locked / 🔓 Free |

**Test scenario**: 
1. Start app → Keepalive: 🟢 ACTIVE, Controller: keepalive
2. Start All → Keepalive: ⏸️ PAUSED, Controller: engine
3. Gây 403 → Circuit: 🔴 OPEN, Cooldown: ❄️ 60s
4. Pause → Keepalive: 🟢 ACTIVE
5. Resume → Keepalive: ⏸️ PAUSED
6. Stop → Keepalive: 🟢 ACTIVE, Circuit: 🟢 CLOSED
