# Gemma/Gemini API Full Audit

- Date: `2026-04-09`
- Scope: `Project Builder` / `Prompt Enhancer` / Google `Gemini API` integration
- Status: Audit only, no code or settings changed

## Executive Summary

- Endpoint hiện tại `generateContent` là đúng; đây không phải nguyên nhân gốc của lỗi.
- Request body nền tảng (`contents`, `generationConfig`, API key qua `?key=`) đang hoạt động vì `gemini-3.1-flash-lite-preview` đã trả `200 OK` trong runtime.
- Vấn đề tương thích lớn nhất với Gemma là app luôn gửi `systemInstruction`, trong khi nhiều Gemma instruction-tuned models không hỗ trợ `system` role theo cách hiện tại.
- Registry model trong app đang chứa ít nhất 2 model ID sai hoặc stale: `gemma-3-2b-it` và `gemma-4-26b-it`.
- Lỗi `403 Your project has been denied access` là lỗi quyền truy cập ở lớp `project/key access`; không phải lỗi endpoint.
- Luồng hiện tại đã có key rotation khi gặp `403`, nên app không còn fail cứng ngay ở key đầu tiên.
- Trong flow hiện tại, `gemini-3.1-flash-lite-preview` là fallback đã được xác nhận chạy ổn.
- Muốn dùng Gemma ổn định trong flow này cần xử lý đồng thời 3 việc: dọn model registry, tách request-shape cho Gemma, và loại các key/project bị deny.

## Môi Trường Và Nguồn Bằng Chứng

Audit này tổng hợp từ 4 nguồn:

1. Code trong repo.
2. Runtime logs do người dùng cung cấp trong phiên phân tích ngày `2026-04-09`.
3. Local settings/runtime state quan sát trong môi trường chạy.
4. Tài liệu chính thức của Google AI Developers và Google AI Developers Forum.

Ba file code trọng tâm đã được đối chiếu:

- [gemini_client.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/services/gemini_client.py)
- [production_pipeline.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/production_pipeline.py)
- [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py)

## Bảng 1: Full Issue Inventory

| Nhóm vấn đề | Evidence trong repo/runtime | Xác nhận Internet | Ảnh hưởng | Kết luận |
|---|---|---|---|---|
| Endpoint `generateContent` | `BASE = "https://generativelanguage.googleapis.com/v1beta"` và URL `.../{model_path}:generateContent` tại [gemini_client.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/services/gemini_client.py) dòng `56`, `171` | [Gemini API reference](https://ai.google.dev/api), [Run Gemma with the Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api) | Không gây lỗi gốc | Endpoint hiện tại là đúng |
| Request body nền tảng | App gửi `contents`, `systemInstruction`, `generationConfig`, `safetySettings` tại [gemini_client.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/services/gemini_client.py) dòng `173-184` | [Gemini API reference](https://ai.google.dev/api) | Không chặn Gemini models đang chạy | Body nền tảng hợp lệ với Gemini |
| `systemInstruction` cho Gemma | App luôn gửi `systemInstruction` tại [gemini_client.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/services/gemini_client.py) dòng `174`; runtime log có `Developer instruction is not enabled` | [Prompt structure for Gemma](https://ai.google.dev/gemma/docs/core/prompt-structure), [Forum thread](https://discuss.ai.google.dev/t/gemma-3-missing-features-despite-announcement/71692/22) | Chặn nhiều Gemma models dù endpoint đúng | Đây là lỗi request-shape lớn nhất cho Gemma |
| `gemma-3-2b-it` | Có trong UI registry tại [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `497`; runtime log trả `404 model not found` | [Gemma releases](https://ai.google.dev/gemma/docs/releases), [Gemma overview](https://ai.google.dev/gemma/docs/core) | Retry vô ích, gây nhiễu | Model ID sai |
| `gemma-4-26b-it` | Có trong UI registry tại [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `501`; runtime log trả `404` | [Run Gemma with the Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api), [Gemma releases](https://ai.google.dev/gemma/docs/releases) | Retry vô ích | Model ID stale hoặc sai; docs hiện dùng `gemma-4-26b-a4b-it` |
| `403 denied access` | `401/403` bị map thành `InvalidKeyError` tại [gemini_client.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/services/gemini_client.py) dòng `210`; runtime log báo `Your project has been denied access` | [Gemini API troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting), [AI Studio troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshoot-ai-studio) | Chặn model ở lớp access trước khi model xử lý prompt | Đây là lỗi project/key access, không phải endpoint |
| Key rotation khi gặp `403` | Pipeline có `except InvalidKeyError`, mark denied, đổi key tại [production_pipeline.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/production_pipeline.py) dòng `3105-3127` | Không cần nguồn ngoài | Giảm fail cứng khi pool key lẫn key xấu | Cơ chế rotation `403` hiện đã có |
| `400 Developer instruction is not enabled` | Runtime log với `gemma-3-4b-it`, `gemma-3-1b-it`, và có lúc `gemma-3-12b-it` | [Prompt structure for Gemma](https://ai.google.dev/gemma/docs/core/prompt-structure), [Forum thread](https://discuss.ai.google.dev/t/gemma-3-missing-features-despite-announcement/71692/22) | Gemma không dùng được ổn định trong flow hiện tại | Không phải lỗi key; đây là incompatibility của request hiện tại |
| Gemini fallback thành công | Runtime log nhiều lần ghi `Gemini OK (gemini-3.1-flash-lite-preview)` | Gemini docs hỗ trợ system instructions bình thường: [System instructions](https://ai.google.dev/gemini-api/docs/system-instructions) | Pipeline vẫn có đường chạy ổn | `gemini-3.1-flash-lite-preview` là known-good fallback hiện tại |
| Extension/access token logs | Runtime log có `x-browser-validation`, `Startup access token set`, `Headers updated` | Không liên quan Gemini request schema | Có thể gây nhiễu khi đọc log | Không phải nguyên nhân gốc của `bible_gen` |

## Bảng 2: Model-by-Model Status Matrix

| Model | Có trong app hiện tại | Tình trạng chính thức | Kết quả runtime đã quan sát | Phân loại lỗi gần nhất | Dùng ngay trong flow hiện tại |
|---|---|---|---|---|---|
| `gemini-3.1-flash-lite-preview` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) | Hợp lệ | `OK` nhiều lần | Không có lỗi tương thích đã thấy | Có |
| `gemma-3-27b-it` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `494` | Hợp lệ theo docs | `403 denied access` | Project/key access | Chưa |
| `gemma-3-12b-it` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `495` | Hợp lệ theo family Gemma 3 | Có cả `403` và `400` | Vừa access issue vừa request incompatibility | Chưa |
| `gemma-3-4b-it` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `496` | Hợp lệ theo family Gemma 3 | `400 Developer instruction is not enabled` | Request-shape incompatibility | Chưa |
| `gemma-3-2b-it` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `497` | Không có trong docs Gemma 3 | `404 model not found` | Model ID sai | Không |
| `gemma-3-1b-it` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `498` | Hợp lệ theo family Gemma 3 | `400 Developer instruction is not enabled` | Request-shape incompatibility | Chưa |
| `gemma-4-31b-it` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `500` | Hợp lệ theo docs | Có attempt nhưng chưa có bằng chứng success rõ trong log đã phân tích | Chưa đủ dữ kiện runtime | Chưa nên kết luận |
| `gemma-4-26b-it` | Có, [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py) dòng `501` | Sai theo docs hiện tại | `404 model not found` | Model ID sai hoặc stale | Không |

## Bảng 3: Request-Field Compatibility Matrix

| Thành phần request | App hiện tại | Gemini | Gemma | Đánh giá |
|---|---|---|---|---|
| Endpoint `/models/{model}:generateContent` | Có | Đúng | Đúng | Không phải vấn đề |
| `contents` | Có | Đúng | Đúng | Không phải vấn đề |
| `generationConfig.maxOutputTokens` | Có | Đúng | Có thể dùng | Chưa thấy gây lỗi |
| `generationConfig.temperature` | Có | Đúng | Có thể dùng | Chưa thấy gây lỗi |
| `safetySettings` | Có | Đúng | Chưa có bằng chứng gây lỗi trong log này | Chưa kết luận là vấn đề |
| API key qua `?key=` | Có | Đúng | Đúng | Không phải vấn đề |
| `systemInstruction` | Luôn gửi | Đúng | Nhiều Gemma models không chấp nhận theo kiểu này | Đây là vấn đề request-shape chính |
| Model registry trong UI | Có | Không ảnh hưởng Gemini đang chạy | Gây `404` cho Gemma nếu chứa ID sai | Registry cần dọn |

## Bảng 4: Error-Code Interpretation

| HTTP code | Thông điệp điển hình | Ý nghĩa kỹ thuật trong ngữ cảnh này | Ví dụ từ audit | Hướng xử lý đúng |
|---|---|---|---|---|
| `400` | `Developer instruction is not enabled` | Request hợp lệ ở mức endpoint nhưng không tương thích với model do có `systemInstruction` hoặc instruction mode không được hỗ trợ | `gemma-3-4b-it`, `gemma-3-1b-it` | Sửa request-shape cho Gemma |
| `403` | `Your project has been denied access` | Key/project bị chặn hoặc không đủ quyền trên Google side | `gemma-3-27b-it`, có lúc `gemma-3-12b-it` | Loại key/project bị deny, kiểm tra access/billing/region/policy |
| `404` | `model ... is not found ... or is not supported for generateContent` | Model ID sai, stale, hoặc không hỗ trợ method này | `gemma-3-2b-it`, `gemma-4-26b-it` | Xóa hoặc thay bằng model ID đúng |
| `429` | Rate limit / quota exceeded | RPM hoặc RPD bị chạm | Không phải trọng tâm của audit này | Giữ rotation/quota strategy |

## Bảng 5: Operational Recommendations

| Nhóm | Việc cần làm | Mục tiêu | Ghi chú |
|---|---|---|---|
| `settings-only` | Đặt model mặc định về `gemini-3.1-flash-lite-preview` | Ổn định pipeline ngay | Không cần sửa code |
| `settings-only` | Không chọn `gemma-3-2b-it` và `gemma-4-26b-it` | Tránh `404` chắc chắn | Hai model ID này hiện sai |
| `settings-only` | Tách pool key thử nghiệm: chỉ 1 key sạch cho mỗi lần test Gemma | Cô lập lỗi `403` | Giúp phân biệt model lỗi với project/key lỗi |
| `settings-only` | Khi test Gemma, ghi riêng kết quả theo từng key và từng model | Làm sạch chẩn đoán | Tránh kết luận lẫn giữa `400` và `403` |
| `requires code` | Tách request path cho Gemma: không gửi `systemInstruction` theo kiểu hiện tại | Mở đường dùng Gemma thật sự | Đây là thay đổi quan trọng nhất |
| `requires code` | Dọn model registry khỏi `gemma-3-2b-it` và `gemma-4-26b-it` | Giảm retry vô ích | Đồng thời cập nhật danh sách model chính thức |
| `requires code` | Xem xét strategy prompt cho Gemma bằng cách ghép instruction vào `contents` user prompt đầu tiên | Phù hợp docs Gemma hơn | Cần test riêng từng model |
| `requires code` | Thêm phân loại lỗi rõ hơn giữa `403 key/project denied` và `403 model-specific denial` nếu cần | Debug nhanh hơn | Hiện đang gộp chung vào `InvalidKeyError` |
| `Google-side` | Kiểm tra project/key nào đang bị `denied access` | Loại bỏ key bẩn khỏi pool | Không thể sửa bằng đổi endpoint |
| `Google-side` | Kiểm tra billing, policy, region/IP, account state | Xác minh nguyên nhân `403` | Theo docs troubleshooting của Google |

## Recommended Actions

### Ưu tiên 1: Ổn định vận hành ngay

1. Dùng `gemini-3.1-flash-lite-preview` cho `Project Builder` và `Prompt Enhancer`.
2. Bỏ khỏi luồng thử nghiệm mọi lần chọn `gemma-3-2b-it` và `gemma-4-26b-it`.
3. Test Gemma chỉ với từng key riêng lẻ, không test cả pool cùng lúc.

### Ưu tiên 2: Làm sạch chẩn đoán

1. Tách rõ hai nhóm lỗi:
   - `400 Developer instruction is not enabled`
   - `403 Your project has been denied access`
2. Xem `403` là lỗi Google-side trước, không xem là lỗi endpoint.
3. Xem `400` ở Gemma là lỗi request-shape trước, không xem là lỗi key.

### Ưu tiên 3: Nếu muốn hỗ trợ Gemma thật sự

1. Cập nhật registry model theo docs chính thức.
2. Thay cách truyền instruction cho Gemma để không dùng `systemInstruction` như hiện tại.
3. Chỉ sau khi hai bước trên xong mới đánh giá lại từng model Gemma theo runtime thật.

## Phân Biệt Rõ 4 Lớp Vấn Đề

### 1. Endpoint correctness

- Endpoint hiện tại là đúng.
- Không có bằng chứng nào cho thấy cần đổi khỏi `generateContent`.

### 2. Request-shape incompatibility

- App hiện gửi `systemInstruction` cho mọi model.
- Đây là phù hợp với Gemini.
- Đây là không phù hợp ổn định với nhiều Gemma models trong runtime hiện tại.

### 3. Invalid model IDs

- `gemma-3-2b-it` là invalid đối với Gemma 3 family chính thức.
- `gemma-4-26b-it` không khớp tên model chính thức hiện tại của docs.

### 4. Google project/key denial

- `403 denied access` thuộc lớp quyền truy cập.
- Không thể giải quyết chỉ bằng việc đổi endpoint hoặc đổi field JSON.

## Runtime Observations Tóm Tắt

- `gemini-3.1-flash-lite-preview` đã trả `OK` nhiều lần trong cùng flow, chứng minh endpoint và body nền tảng đang hoạt động.
- `gemma-3-2b-it` và `gemma-4-26b-it` cho `404`, phù hợp với chẩn đoán model ID sai.
- `gemma-3-4b-it` và `gemma-3-1b-it` cho `400 Developer instruction is not enabled`, phù hợp với chẩn đoán `systemInstruction` không tương thích.
- `gemma-3-27b-it` và đôi lúc `gemma-3-12b-it` cho `403 denied access`, phù hợp với chẩn đoán access issue ở lớp key/project.
- Pipeline hiện đã có cơ chế đổi key khi gặp `403`, nên lỗi access không còn chặn mọi retry ngay ở key đầu tiên.

## Appendix A: Official Sources

- [Gemini API reference](https://ai.google.dev/api)
- [System instructions](https://ai.google.dev/gemini-api/docs/system-instructions)
- [Gemini API troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)
- [Google AI Studio troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshoot-ai-studio)
- [Available regions](https://ai.google.dev/gemini-api/docs/available-regions)
- [Billing](https://ai.google.dev/gemini-api/docs/billing/)
- [Run Gemma with the Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)
- [Prompt structure for Gemma](https://ai.google.dev/gemma/docs/core/prompt-structure)
- [Gemma releases](https://ai.google.dev/gemma/docs/releases)
- [Gemma overview](https://ai.google.dev/gemma/docs/core)
- [Forum: Gemma 3 missing features despite announcement](https://discuss.ai.google.dev/t/gemma-3-missing-features-despite-announcement/71692/22)

## Appendix B: Repo References

- [gemini_client.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/services/gemini_client.py)
  - Endpoint base: dòng `56`
  - Default model: dòng `57`
  - `generateContent` URL: dòng `171`
  - `systemInstruction`: dòng `174`
  - `401/403` mapping: dòng `210`
- [production_pipeline.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/production_pipeline.py)
  - `403` handling entrypoint: dòng `3105`
  - Key rotation log on `403`: dòng `3121`
  - Continue after `403`: dòng `3125-3129`
  - `400` handling: dòng `3133-3135`
  - Other client error fallback: dòng `3141`
- [tab_settings.py](../02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/tabs/tab_settings.py)
  - `gemma-3-27b-it`: dòng `494`
  - `gemma-3-12b-it`: dòng `495`
  - `gemma-3-4b-it`: dòng `496`
  - `gemma-3-2b-it`: dòng `497`
  - `gemma-3-1b-it`: dòng `498`
  - `gemma-4-31b-it`: dòng `500`
  - `gemma-4-26b-it`: dòng `501`
  - Current default lookup: dòng `638`

## Final Diagnosis

- `generateContent` endpoint: correct.
- Request compatibility with Gemini: correct enough and verified by successful runtime calls.
- Request compatibility with Gemma: incomplete because of `systemInstruction`.
- Model registry: not clean; contains at least 2 wrong/stale IDs.
- `403 denied access`: Google-side access problem at the key/project layer.
- Best current operational choice: keep production flow on `gemini-3.1-flash-lite-preview` until Gemma-specific request handling is implemented and key pool is cleaned.
