# 🔧 Troubleshooting — Error Log Analysis & Fixes

**Location**: `03_Backend/TROUBLESHOOTING_ERROR_LOG.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-18  
**Related**: [ERROR_HANDLING_STRATEGY.md](./ERROR_HANDLING_STRATEGY.md)

---

## 1. Stale `.pyc` Cache Issue

### Triệu chứng
Sau khi sửa code, lỗi cũ vẫn xuất hiện khi chạy. Traceback trỏ đến line number không khớp với code hiện tại.

### Nguyên nhân
Python cache bytecode thành `.pyc` trong `__pycache__/`. Nếu file `.py` bị sửa nhưng `.pyc` chưa được regenerate (timestamp thay đổi nhanh hơn polling interval), Python chạy code cũ.

### Fix
```powershell
# Xóa tất cả __pycache__ trước khi chạy
Get-ChildItem -Path "02 - CLIENT - VEO PRO MAX" -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
```

> [!TIP]
> Thêm vào workflow mỗi lần deploy/test code mới. Hoặc chạy Python với `-B` flag để disable bytecode cache: `python -B main.py`

---

## 2. RecaptchaPool — `RuntimeError: no running event loop`

### Traceback
```
File "app_controller.py", in start_processing
    self._engine._recaptcha_pool.start()
RuntimeError: no running event loop
```

### Nguyên nhân
`RecaptchaPool.start()` gọi `asyncio.create_task()` — yêu cầu running event loop. Nhưng `start_processing()` chạy trên **GUI thread** (Qt main thread) — không có async loop.

### Fix đã áp dụng
**File:** `core/app_controller.py` (line 2047–2063)

```python
# BEFORE (crash):
self._engine._recaptcha_pool.start()

# AFTER (fixed):
# Wrap trong async coroutine, chạy qua run_coroutine_threadsafe
self._run_async(self._start_recaptcha_pool())

async def _start_recaptcha_pool(self):
    """Runs inside async loop context where create_task() works."""
    self._engine._recaptcha_pool.start()
```

### Hệ quả nếu không fix
- `RecaptchaPool` không start → token không được pre-fetch → mỗi worker phải direct-fetch reCAPTCHA → delay 3-5s mỗi request
- RuntimeWarning: `coroutine 'RecaptchaPool._refill_loop' was never awaited`

---

## 3. DevConsole — `AttributeError: get_queue_state`

### Traceback
```
File "tab_devconsole.py", line 419, in update_queue_state_safe
    state = self.controller.get_queue_state()
AttributeError: 'AppController' has no attribute 'get_queue_state'
```

### Nguyên nhân
Method `get_queue_state()` đã được rename thành `get_queue_status()` trong `AppController`, nhưng caller trong `TabDevConsole` chưa được cập nhật.

### Fix đã áp dụng
**File:** `ui/tabs/tab_devconsole.py` (line 419)

```python
# BEFORE:
state = self.controller.get_queue_state()

# AFTER:
state = self.controller.get_queue_status()
```

### Hệ quả nếu không fix
- DevConsole Queue State panel không cập nhật realtime
- Error lặp mỗi giây (từ QTimer) → spam log

---

## 4. reCAPTCHA Token Failure — Cascade Chain Fail

### Triệu chứng
reCAPTCHA token trả về "too short (330 chars)" hoặc timeout 25s, retry 4 lần rồi PERMANENTLY FAIL. Nếu task là root của continuation chain → **tất cả child tasks bị cascade-fail**.

### Nguyên nhân (Runtime)
Không phải code bug. Có thể do:
1. Browser page chưa navigate đến `labs.google` (TRPC log: `origin = None`)
2. Extension không thực thi reCAPTCHA v3 thành công trong browser context
3. Network delay hoặc browser hang

### Khắc phục
1. **Restart browser** cho account bị lỗi (Settings → Restart Browser)
2. **Kiểm tra Extension** đang chạy đúng version
3. **Manual reload** labs.google page trong debug browser
4. Nếu vẫn fail → **check internet/proxy** connection

### Cải thiện khuyến nghị
- Tăng timeout từ 25s → 40s cho reCAPTCHA fetch
- Thêm mechanism bypass: nếu reCAPTCHA fail, thử submit không có token (một số endpoint cho phép)

---

## 5. I2V Image Pipeline — Flow Reference

### 5.1 Continuation Frame (từ chain)

```
Parent video 720p downloaded
  → FFmpeg extract last frame (engine._extract_continuation_frame)
  → MediaHandler.image_to_base64()
  → api_client.upload_image() → mediaId
  → dispatcher.activate_children_early(mediaId) [★ từ 2026-02-18]
  → Child task.image_uris = [mediaId]
  → Worker: I2V → generate_video_i2v_single(image_media_id=mediaId)
```

> [!IMPORTANT]
> **Change 2026-02-18**: Children được activate ngay sau download 720p + extract frame,
> KHÔNG chờ upscale nữa. Xem `dispatcher.activate_children_early()`.

### 5.2 I2V Tab (standalone, từ user upload)

```
User chọn ảnh trong I2V tab (image_tags)
  → add_i2v_batch() resolve tags → local paths
  → submit_prompts() split: local → image_paths, remote → image_uris
  → Engine: _resolve_image_paths() upload local → mediaId
  → Worker: I2V → generate_video_i2v_single(image_media_id=mediaId)
```

### 5.3 Auto-Switch Logic

| Condition | Result | Code |
|-----------|--------|------|
| I2V prompt, no image, no continuation | → T2V | `app_controller.py:1616` |
| I2V prompt, no image, IS continuation | → keep I2V (frame injected at runtime) | `app_controller.py:1631` |
| T2V prompt, has `[tag]` image | → I2V (auto-detect) | `app_controller.py:1602` |
| T2V prompt, IS continuation | → I2V (continuation upgrade) | `app_controller.py:1632` |

### 5.4 Upload không dùng reCAPTCHA

Upload image endpoint **KHÔNG** yêu cầu reCAPTCHA (HAR verified):
```python
upload_resp = await self._api_client.upload_image(
    access_token=access_token,
    recaptcha_token="",  # HAR: upload does NOT send recaptcha
    ...
)
```

> [!WARNING]
> **KHÔNG** gọi `refresh_recaptcha()` trước upload — sẽ tiêu tốn token single-use cần cho generate API call tiếp theo.

---

## 6. TODO — Future Frame Enhancement Pipeline

> Planned feature: enhance continuation frame trước khi inject vào child task.

```
extract_frame(720p) → enhance_frame(AI upscale/denoise) → activate_children()
```

**Khi implement:**
1. Thêm `FrameEnhancer` class (Real-ESRGAN hoặc server-side API)
2. Thay đổi `activate_children_early()` để nhận enhanced frame URI
3. Fallback: nếu enhance fail → dùng frame gốc 720p
4. Xem `dispatcher.py:activate_children_early()` TODO comment

---

## Cross-References

- [ERROR_HANDLING_STRATEGY.md](./ERROR_HANDLING_STRATEGY.md) — General error classification
- [MULTITHREADING_ARCHITECTURE.md](./MULTITHREADING_ARCHITECTURE.md) — Worker retry logic
- [RECAPTCHA_BROWSER_MANAGEMENT.md](./RECAPTCHA_BROWSER_MANAGEMENT.md) — reCAPTCHA flow
- [WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md](../04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md) — I2V tab workflow
