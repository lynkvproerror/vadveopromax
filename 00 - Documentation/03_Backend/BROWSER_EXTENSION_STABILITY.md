# Browser-Extension Stability System

## Tổng quan

Hệ thống 3 tầng đảm bảo App–Extension–Browser luôn hoạt động đồng bộ, tự phát hiện và khắc phục sự cố mà không cần can thiệp thủ công.

## Layer A: Phòng ngừa

### Chrome Anti-Throttle Flags (`chrome_manager.py`)

Các flag ngăn Chrome tự throttle/discard tab:

| Flag | Mục đích |
|------|---------|
| `--disable-features=TabDiscarding` | Ngăn Chrome discard tab không active |
| `--disable-features=MemorySaver` | Tắt Memory Saver |
| `--disable-features=UseEcoQoSForBackgroundProcess` | Tắt EcoQoS cho background |
| `--disable-background-timer-throttling` | Timer/interval không bị chậm khi tab background |
| `--disable-backgrounding-occluded-windows` | Không throttle khi cửa sổ bị che |
| `--disable-renderer-backgrounding` | Renderer không bị throttle background |

### Windows Efficiency Mode Bypass (`chrome_manager.py`)

- **`_disable_efficiency_mode(pid)`** — Dùng Windows API `SetProcessInformation` để disable Efficiency Mode cho Chrome process
- Gọi ngay sau `subprocess.Popen()` khi launch Chrome
- Windows 11 tự đặt hidden/background process vào Efficiency Mode, throttle CPU → WebSocket heartbeat chậm → Extension không phản hồi

## Layer B: Phát hiện + Tự động sửa

### B1. Tab Discard Auto-Detect (`background.js`)

- **Trigger**: `chrome.tabs.onUpdated` với `changeInfo.discarded === true`
- **Hành động**: 
  1. Gửi `tab_discarded` về app qua WebSocket
  2. Auto-reload tab sau 1s
  3. Re-inject `content.js` khi tab restored

```
Tab bị discard → onUpdated fires → Extension gửi 'tab_discarded'
  → Extension tự reload tab → content.js inject lại → register → hoạt động tiếp
```

### B2. Efficiency Mode Watchdog (`account_manager.py`)

- **`_efficiency_mode_watchdog()`** — kiểm tra và re-disable Efficiency Mode mỗi 5 phút
- Windows có thể re-apply Efficiency Mode sau khi user mở Task Manager hoặc minimize ứng dụng

### B3. Server Heartbeat + Zombie Detection (`extension_bridge.py`)

- **`_heartbeat_loop()`** — gửi ping mỗi 15s
- Track `last_activity` mỗi message
- **Zombie detection**: nếu `last_activity > 90s` (3 missed pings) → cleanup connection + trigger `on_extension_disconnect`

### B4. Tab Health Check — On-demand (`extension_bridge.py` + `background.js`)

- **`check_tab_alive(email)`** — kiểm tra tab VEO còn sống trước khi gửi request quan trọng
- Gửi `executeScript(() => document.readyState)` — fail nếu tab bị discard

### B5. App Notification Handler (`extension_bridge.py`)

- Handle `tab_discarded` message từ Extension → log warning
- Handle `tab_alive` response → resolve pending future

## Layer C: Phục hồi (Active Recovery)

### Extension Wait (`extension_bridge.py`)

- **`wait_for_extension(email, timeout)`** — dùng `asyncio.Event`, zero CPU, instant wakeup
- Nhiều worker share cùng Event, tất cả wakeup đồng thời

### Active 4-Phase Recovery (`account_manager.py`)

`_active_extension_recovery()` — vòng lặp vô hạn (chỉ dừng khi mất mạng 120s):

| Phase | Kiểm tra | Hành động sửa |
|-------|----------|---------------|
| 1. Chrome alive | `_is_chrome_process_alive()` | Relaunch qua `open_browser_for_debug()` |
| 2. Extension loaded | `_is_extension_loaded()` via CDP | Poll 6×5s, kill+relaunch nếu stuck |
| 3. WebSocket connected | `wait_for_extension()` | asyncio.Event, 30s timeout |
| 4. Token refresh | `request_access_token()` | 3 attempts × 2s |

### File liên quan

| File | Thay đổi |
|------|---------|
| `core/chrome_manager.py` | Anti-throttle flags, `_disable_efficiency_mode()` |
| `core/extension_bridge.py` | `wait_for_extension()`, heartbeat, zombie detect, `check_tab_alive()`, `tab_discarded` handler |
| `core/account_manager.py` | `_active_extension_recovery()`, `_efficiency_mode_watchdog()` |
| `extension/background.js` | Tab discard auto-detect, `check_tab_alive` handler |
