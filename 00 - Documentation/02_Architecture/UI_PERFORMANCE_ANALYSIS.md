# UI Performance & Effects — Báo cáo phân tích toàn diện

## Phần A: Hiệu ứng hiện tại

### ✅ Hiệu ứng ĐỘNG đã có

| # | Component | Loại | Cơ chế | File |
|---|-----------|------|--------|------|
| 1 | Splash Screen | Smooth progress + glow pulse + fade-out | `QTimer` 30ms + `QPropertyAnimation` | [splash_screen.py](file:///d:/NEW%20VEO%20PRO%20MAX/veo-pro-max/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/splash_screen.py) |
| 2 | Toast notifications | Slide-in + auto-dismiss + slide-out | `QPropertyAnimation` trên `pos` | [toast.py](file:///d:/NEW%20VEO%20PRO%20MAX/veo-pro-max/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/components/toast.py) |
| 3 | Input thumb pulse | Border nhấp nháy khi uploading | `QTimer` 500ms toggle màu | [tab_queue.py](file:///d:/NEW%20VEO%20PRO%20MAX/veo-pro-max/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py#L1017-L1047) |

### ❌ Hiệu ứng TĨNH (thay đổi rời rạc)

| # | Component | Hiện trạng |
|---|-----------|-----------|
| 4 | Thumbnail progress slots | Gradient fill cập nhật rời rạc, nhảy % |
| 5 | Upscale overlay | Static dark overlay + emoji "⬆️"/"🔄" |
| 6 | Border color changes | Đổi tức thời gray→yellow→blue khi complete |
| 7 | Row status text | Text thay đổi không có transition |
| 8 | Tab switching | Tức thời, không có fade/slide |
| 9 | Button hover | CSS `:hover` tĩnh |
| 10 | Queue row appear/disappear | Tức thời add/remove widget |

---

## Phần B: Nguyên nhân gây "Not Responding" / Freeze / Crash

### 🔴 Vấn đề 1: Widget Churn — Full Rebuild trên mỗi lần refresh

**Mức độ**: Critical — Nguyên nhân chính gây freeze

```
_refresh_groups()
  └→ _rebuild_group_children()   ← GỌI MỖI LẦN REFRESH
       └→ while layout.count():
            child.widget().deleteLater()  ← XÓA TẤT CẢ  
       └→ for td in tasks:
            _create_queue_item_widget()   ← TẠO LẠI TẤT CẢ
```

**File**: [tab_queue.py L1569-1590](file:///d:/NEW%20VEO%20PRO%20MAX/veo-pro-max/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_queue.py#L1569-L1590)

**Tại sao gây freeze**:
- 100 prompts × 4 thumbnails = 400+ `QLabel` bị destroy + recreate mỗi refresh
- Mỗi `_create_queue_item_widget()` tạo ~15 widget (row, labels, buttons, thumbnails)
- Tổng: **6,000+ widget operations** trên main thread mỗi refresh
- `deleteLater()` queue lên, GC xử lý hàng loạt → spike CPU

**Fix đề xuất**:
```
Thay vì rebuild → diff-update:
1. So sánh existing widgets vs new data
2. Chỉ update text/pixmap trên widget đã có
3. Chỉ create widget cho task MỚI
4. Chỉ delete widget cho task ĐÃ XÓA
```

---

### 🔴 Vấn đề 2: File System I/O trên Main Thread

**Mức độ**: High — Gây micro-freeze khi queue lớn

```python
# Đọc file system cho MỖI thumbnail slot — trên main thread!
has_thumb = thumb_path and Path(thumb_path).exists()      # L1064
has_file  = path and Path(path).exists()                  # L900
if video_path and Path(video_path).exists():              # L1129, L1155
```

- 100 prompts × 4 videos × 3 `exists()` calls = **1,200 disk I/O** trên main thread mỗi refresh
- Network drive hoặc HDD chậm → `exists()` block 10-50ms × 1200 = **12-60 giây freeze**

**Fix đề xuất**:
```
1. Cache exists() kết quả (invalidate khi file mới tạo)
2. Hoặc: background thread check + callback update UI
```

---

### 🟡 Vấn đề 3: QPixmap trên Main Thread (không cache)

**Mức độ**: Medium — Gây jank khi scroll

```python
# L1092-1095: Load + scale pixmap trên main thread MỖI LẦN rebuild
pixmap = QPixmap(thumb_path)
scaled = pixmap.scaled(40, 40, KeepAspectRatio, SmoothTransformation)
```

- Disk read + decode + scale = 5-50ms per thumbnail
- 400 thumbnails × 20ms = **8 giây** cho full rebuild
- Không có pixmap cache → load lại **mỗi lần refresh** dù file không đổi

**Fix đề xuất**:
```
1. Pixmap cache: dict[path] → QPixmap (already scaled)
2. LRU eviction khi cache > 500 entries
3. Background decode thread cho large queues
```

---

### 🟡 Vấn đề 4: Progress Update Storm  

**Mức độ**: Medium — Gây refresh quá thường xuyên

- Engine gửi **25+ `update_progress()`** per task lifecycle
- Mỗi `update_progress` → `on_progress` callback → có thể trigger UI refresh
- Nhiều task chạy song song → **hàng chục updates/giây**
- Mỗi update có thể trigger `_rebuild_group_children()` → quay lại Vấn đề 1

**Fix đề xuất**:
```
1. Debounce/throttle: merge updates trong 200ms window
2. Hoặc: chỉ update progress text, KHÔNG rebuild widget
3. Differential update: chỉ update widget của task đang thay đổi
```

---

### 🟡 Vấn đề 5: Memory Leak từ `deleteLater()` backlog

**Mức độ**: Medium — Crash sau session dài

- `deleteLater()` không xóa ngay — queue vào Qt event loop
- Full rebuild mỗi refresh → objects tích tụ → RAM tăng dần
- PySide6 + Python GC double management → potential leak
- Session dài với queue lớn → crash OOM

**Fix đề xuất**:
```
1. Không dùng deleteLater cho mass cleanup → dùng setParent(None) + del
2. Reuse widgets thay vì destroy/create
3. QApplication.processEvents() giữa batches (cẩn thận re-entrant)
```

---

## Phần C: Đề xuất hiệu ứng động mới

| # | Effect | Mô tả | Kỹ thuật | Impact |
|---|--------|-------|----------|:------:|
| 1 | **Shimmer progress** | Wave effect trên thumbnail đang generate | `QTimer` update gradient offset | ⭐⭐⭐ |
| 2 | **Completion glow** | Pulse xanh/vàng 3x khi task complete | `QPropertyAnimation` border-color | ⭐⭐⭐ |
| 3 | **Smooth progress** | Interpolate giữa progress values | `QPropertyAnimation` custom property | ⭐⭐ |
| 4 | **Upscale spinner** | Rotating icon thay emoji tĩnh | `QTimer` rotate transform | ⭐⭐ |
| 5 | **Row fade-in** | Mới add → fade from 0 opacity | `QPropertyAnimation` opacity | ⭐ |
| 6 | **Status transition** | Text change có fade | `QGraphicsOpacityEffect` | ⭐ |

> [!WARNING]
> **Phải fix Vấn đề 1-3 TRƯỚC khi thêm hiệu ứng động.** Animation trên widget bị destroy/recreate mỗi 200ms sẽ flicker + crash. Differential update là prerequisite cho tất cả hiệu ứng động.

---

## Phần D: Roadmap đề xuất

### Phase 1: Performance Fix (Ưu tiên cao nhất)
1. `_rebuild_group_children()` → **differential update** (chỉ update data, không destroy widget)
2. **Pixmap LRU cache** — cache `QPixmap` scaled sẵn
3. **File existence cache** — batch check + cache kết quả
4. **Progress throttle** — debounce UI refresh 200ms

### Phase 2: Dynamic Effects (Sau khi Phase 1 ổn định)
5. Shimmer progress trên thumbnail slots
6. Completion glow pulse
7. Smooth progress interpolation

### Phase 3: Polish
8. Row fade-in animation
9. Upscale spinner
10. Tab transition effects
