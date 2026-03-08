# PROMPT ADHERENCE - KHI VEO "LÀM NGƠ"

## Bộ Công Cụ Cấp Cứu Để Bắt Veo Nghe Lời

**Phiên bản**: 1.0  
**Cập nhật**: 2026-01-30  
**Mục tiêu**: Quy trình debug 10 phút để "bắt Veo nghe lời"

---

## 🎯 TRIẾT LÝ CỐT LÕI

> [!IMPORTANT]
> **"Veo làm ngơ" không phải lỗi của model — mà là cơ hội để bạn ra lệnh tốt hơn.**

Google và DeepMind đều ngầm hướng bạn về một điều:

> **Prompt có cấu trúc + Iteration (thử và sửa)**

---

## 📊 90% VẤN ĐỀ KHÔNG NẰM Ở AI

> Thực tế, **90% trường hợp Veo làm ngơ** xảy ra vì prompt của bạn rơi vào một trong các lỗi: **mơ hồ, quá tải, hoặc mâu thuẫn**.

| Lỗi | Hậu quả |
|-----|---------|
| **🔍 Mơ hồ** | AI không biết ưu tiên điều gì |
| **📦 Quá tải** | AI phải chọn bỏ bớt thông tin |
| **↔️ Mâu thuẫn** | AI tự chọn con đường dễ dàng nhất |

> [!TIP]
> **Google nói rõ**: Cách hiệu quả nhất là **bẻ ý tưởng thành các thành phần (key components)** để dẫn Veo về đúng outcome bạn muốn.

---

## 🎬 CHẨN ĐOÁN 3 TRIỆU CHỨNG PHỔ BIẾN NHẤT

| # | Triệu chứng | Mô tả |
|---|-------------|-------|
| 1 | **Camera đứng im** | Dù đã ra lệnh di chuyển |
| 2 | **Nhân vật làm sai hành động** | Hoặc chuỗi hành động bị "trật nhịp" |
| 3 | **Style & constraints bị "trôi"** | Màu sắc, mood, hoặc các yêu cầu cấm bị bỏ qua |

---

# PHẦN 1: CHẨN ĐOÁN - TẠI SAO VEO LÀM NGƠ?

---

## 🔍 3 VẤN ĐỀ CHÍNH

| Yếu tố | Vấn đề | Giải pháp |
|--------|--------|-----------|
| **CAMERA MOVE** | Mơ hồ, để cuối, mâu thuẫn | **Front-load**, cụ thể, đơn nhất |
| **ACTION & SEQUENCE** | Viết 'ý niệm', quá tải, chủ thể không rõ | **Viết như kịch bản**, 1 hành động chính |
| **STYLE & CONSTRAINTS** | Xung đột, không có cấu trúc | **Chọn style chủ đạo**, đóng gói constraints |

---

### ❌ Lỗi 1: CAMERA MOVE

| Vấn đề | Ví dụ sai |
|--------|-----------|
| **Mơ hồ** | "cinematic camera moves" |
| **Để cuối prompt** | "...and the camera slowly zooms in" |
| **Mâu thuẫn** | "tracking shot, dolly-in, pan left" (3 chuyển động cùng lúc) |

**✅ Giải pháp:**
- **Front-load**: Đặt camera movement ĐẦU TIÊN trong prompt
- **Cụ thể**: "slow dolly-in" thay vì "camera moves"
- **Đơn nhất**: Chỉ 1 camera movement chính

---

### ❌ Lỗi 2: ACTION & SEQUENCE

| Vấn đề | Ví dụ sai |
|--------|-----------|
| **Viết 'ý niệm'** | "feels anxious" (AI không thể render cảm giác) |
| **Quá tải** | "walks, talks, picks up coffee, looks at phone, sits down" |
| **Chủ thể không rõ** | "They are having a conversation" |

**✅ Giải pháp:**
- **Viết như kịch bản**: Mô tả hành động vật lý có thể quay được
- **1 hành động chính**: Giới hạn 1-2 hành động cho 8 giây
- **Rõ chủ thể**: "The woman speaks while the man listens"

---

### ❌ Lỗi 3: STYLE & CONSTRAINTS

| Vấn đề | Ví dụ sai |
|--------|-----------|
| **Xung đột** | "bright sunny day, dark moody lighting" |
| **Không có cấu trúc** | "cinematic, movie-like, professional, high quality" |
| **Quá nhiều style** | "anime, realistic, 3D, hand-drawn" |

**✅ Giải pháp:**
- **Chọn style chủ đạo**: 1 visual style rõ ràng
- **Đóng gói constraints**: Nhóm các yếu tố liên quan với nhau
- **Loại bỏ mâu thuẫn**: Kiểm tra từng yếu tố có xung đột không

---

# PHẦN 1B: TRIỆU CHỨNG & TOA THUỐC CHI TIẾT

---

## 🏥 TRIỆU CHỨNG #1: CAMERA

### Camera không bám hoặc chuyển động sai

**Biểu hiện thường gặp:**
- Bạn viết "dolly-in" nhưng camera static
- Bạn muốn "tracking shot" nhưng camera lại pan
- Camera chuyển động ngẫu nhiên, không theo ý

**Vì sao Veo làm ngơ?**
1. **Camera để cuối prompt**: AI đọc từ trên xuống, camera cuối = ưu tiên thấp
2. **Nhiều chuyển động xung đột**: "orbit + dolly + handheld" = model bối rối
3. **Mơ hồ**: "cinematic camera movement" không có nghĩa cụ thể

---

## 💊 TOA THUỐC #1: CAMERA

### Ra lệnh cho camera bằng ngôn ngữ điện ảnh chính xác

---

#### FIX 1: Front-load camera

> Đưa lệnh camera và shot size lên **ngay câu đầu** của prompt.

**Ví dụ:**
```
"Medium shot, slow dolly-in..." rồi mới tới chủ thể và hành động.
```

---

#### FIX 2: Mỗi clip chỉ 1 camera move chính

> Tránh kết hợp "orbit" + "dolly" + "handheld" trong một clip ngắn.

| ❌ Sai | ✅ Đúng |
|--------|---------|
| "Orbit, dolly-in, handheld shake" | "Slow orbit around..." |
| "Pan left, track right, zoom in" | "Tracking shot following..." |

---

#### FIX 3: Nói rõ shot size + move + mục đích

> Đưa lệnh chia orpromptist. Sự tập trung mang lại kết quả tốt hơn.

| ❌ Sai | ✅ Đúng |
|--------|---------|
| "A girl in a rainy street, cinematic camera movement." | "Medium shot, slow tracking shot following a girl walking under neon signs, gentle handheld (3%)..." |

---

## 🏥 TRIỆU CHỨNG #2: ACTION

### Nhân vật không làm đúng hành động bạn mô tả

**Biểu hiện thường gặp:**
- Bạn viết 'nhặt đồ / quay đầu / mở cửa' → nhân vật chỉ đứng nhìn
- Bạn muốn sequence 'setup → turn → payoff' → Veo chỉ render 1 trạng thái duy nhất
- Bạn viết nhiều hành động liên tiếp → clip bị 'lẫn', AI chỉ làm 1-2 hành động

**Vì sao Veo làm ngơ?**
1. **Action là 'ý niệm'**: 'cô ấy cảm thấy tổn thương' là tâm lý, không phải hành động hữu hình. AI không biết cách 'quay' cảm xúc này.
2. **Nhồi quá nhiều hành động**: Một clip 8 giây không thể chứa 5 hành động lớn. Model sẽ phải hy sinh bớt.
3. **Subject mơ hồ**: Nếu có 2 nhân vật và không ghi rõ 'ai làm gì', Veo sẽ tự phân vai hoặc bỏ qua hành động.

---

## 💊 TOA THUỐC #2: ACTION

### Viết hành động như một kịch bản ngắn gọn

---

#### FIX 1: 1 clip = 1 hành động chính (+ 1 phản ứng phụ)

> Tập trung vào một hành động cốt lõi để đảm bảo nó được thực thi.

**Ví dụ:**
```
"cô ấy vươn tay chạm tay nắm cửa" (hành động chính) + "ánh sáng rò ra" (phản ứng phụ)
```

---

#### FIX 2: Viết action theo công thức

```
[Động từ] + [Mục tiêu] + [Phản ứng môi trường]
```

| Thành phần | Ví dụ |
|------------|-------|
| **Động từ** | reach / grab / turn / open |
| **Mục tiêu** | doorknob / letter / phone |
| **Phản ứng môi trường** | dust falls / light leaks / wind blows |

**Ví dụ hoàn chỉnh:**
```
She reaches for the dusty book (action). As she pulls it from the shelf, 
particles drift through the sunbeam (reaction).
```

---

#### FIX 3: Nếu cần sequence, hãy viết theo nhịp

> Mô tả clip như một mini-kịch bản với 3 hồi: **setup → turn → payoff**.

| Phần | Mô tả | Ví dụ |
|------|-------|-------|
| **Setup** | Trạng thái ban đầu | "A man sits at his desk, staring at a blank screen" |
| **Turn** | Hành động chính | "He suddenly stands up" |
| **Payoff** | Kết quả | "knocking over his coffee cup" |

---

## 🏥 TRIỆU CHỨNG #3: STYLE & CONSTRAINTS

### Style, mood, và các giới hạn bị 'trôi' hoặc bỏ qua

**Biểu hiện thường gặp:**
- Bạn muốn 'low-poly' nhưng ra nửa realistic nửa cartoon
- Bạn muốn 'no text overlay' nhưng vẫn xuất hiện chữ lạ
- Bạn muốn ambience 'quiet' nhưng âm thanh lại quá dày
- Bạn cấm 'extra people' nhưng vẫn có người lạ xuất hiện

**Vì sao Veo làm ngơ?**
1. **Style xung đột**: 'realistic, anime, disney, noir' trong cùng một prompt khiến model bối rối.
2. **Constraints không được 'đóng gói'**: Negative prompt nằm rải rác hoặc không rõ ràng sẽ bị ưu tiên thấp.
3. **Kỳ vọng tắt tính năng hệ thống**: Bạn không thể dùng prompt để tắt watermark kỹ thuật như SynthID.
4. **Audio prompt không khớp cảnh**: Quá nhiều lớp âm thanh không liên quan khiến AI phải chọn bỏ bớt.

---

## 💊 TOA THUỐC #3: STYLE & CONSTRAINTS

### Áp đặt style và giới hạn một cách có cấu trúc

---

#### FIX 1: Chỉ chọn 1 style chủ đạo + 1-2 thuộc tính phụ

| ❌ Tránh | ✅ Nên |
|----------|--------|
| "lowpoly + disney + anime + realistic" | "stylized 3D low-poly diorama, matte textures, soft global illumination" |

---

#### FIX 2: Đưa constraints thành một block rõ ràng

> Dùng cấu trúc để tăng độ bám dính:

```
Must-have: [list 1-3 items]
Must-not-have (Negative list): [list items]
```

**Ví dụ:**
```
Must-have: soft shadows, warm color palette, shallow depth of field
Must-not-have: text overlays, extra people, modern elements
```

---

#### FIX 3: Viết audio theo thứ tự ưu tiên

> Giữ âm thanh đúng với bối cảnh và tuân theo cấu trúc:

| Thứ tự | Lớp | Mô tả |
|--------|-----|-------|
| 1 | **Ambience** (nền) | Âm thanh môi trường xung quanh |
| 2 | **SFX** (tiếng động chính) | Hiệu ứng âm thanh liên quan đến action |
| 3 | **Dialogue** (nếu có) | Lời thoại nhân vật |

**Ví dụ:**
```
Audio: Quiet forest ambience with distant birds (ambience), 
soft footsteps on fallen leaves (SFX), 
character whispers "I found it" (dialogue).
```

---

# PHẦN 2: QUY TRÌNH DEBUG 4 BƯỚC

---

## 🛠️ BƯỚC 1 & 2: QUAY VỀ CẤU TRÚC VÀ CÔ LẬP VẤN ĐỀ

---

### STEP 1: CẮT PROMPT VỀ SKELETON 5 PHẦN

> Luôn bắt đầu với công thức nền tảng của Google:

```
[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]
```

| Phần | Nội dung | Ví dụ |
|------|----------|-------|
| **[Cinematography]** | Camera + Shot size | "Close-up, slow dolly-in" |
| **[Subject]** | Nhân vật chính | "on a tired man" |
| **[Action]** | Hành động vật lý | "rubbing his temples" |
| **[Context]** | Bối cảnh | "Dim late-night office" |
| **[Style & Ambiance]** | Phong cách, ánh sáng | "1980s film look, tense atmosphere" |

---

### STEP 2: CHỈ TEST 1 BIẾN MỖI LẦN

> Hãy là một **nhà khoa học** với prompt của bạn.

#### Test Case A: Nếu camera không bám

```
[CAMERA] → [subject] → [action]
```

- ❌ Bỏ hết style rườm rà
- ✅ Chỉ test camera

**Ví dụ Test Case A:**
```
Slow dolly-in on a man sitting at a desk. He looks up.
```

#### Test Case B: Nếu action không đúng

```
[camera] → [SUBJECT] → [ACTION]
```

- ❌ Bỏ camera phức tạp
- ✅ Chỉ test action với static camera

---

## 🛠️ BƯỚC 3 & 4: GIẢM XUNG ĐỘT VÀ HOÀN THIỆN

---

### STEP 3: GIẢM XUNG ĐỘT NỘI TẠI

> Giữ cho mỗi yêu cầu cốt lõi được **đơn giản và duy nhất**.

#### Checklist giảm xung đột:

| # | Yêu cầu | Kiểm tra |
|---|---------|----------|
| ✓ | **1 shot size chính** | Không mix "close-up and wide shot" |
| ✓ | **1 camera move chính** | Không mix "dolly-in and orbit" |
| ✓ | **1 action chính** | Không quá 2 hành động trong 8 giây |

---

### STEP 4: KHI ĐÃ ỔN, MỚI THÊM AUDIO/NEGATIVE

> Xây dựng prompt theo từng lớp.

**Quy trình:**
1. ✅ Hoàn thiện phần **hình ảnh** trước
2. ✅ Đảm bảo **nhịp điệu** đúng
3. ✅ Video gốc đã **đúng ý**
4. ➡️ **MỚI** thêm các lớp âm thanh và negative prompt

---

> [!TIP]
> **Pro-Tip**: Dùng một LLM như Gemini để giúp bạn 'dịch' ý tưởng ban đầu thành một prompt có cấu trúc hoàn chỉnh.

---

# PHẦN 3: CASE STUDY - SỨC MẠNH CỦA PROMPT CÓ CẤU TRÚC

---

## ❌ PROMPT SAI

```
"A man feels anxious in a room, cinematic, intense mood, camera moves."
```

**🔍 Phân tích lỗi:**
- Mơ hồ, dùng 'ý niệm' (feels anxious)
- Camera chung chung
- Không có cấu trúc rõ ràng

---

## ✅ PROMPT ĐÚNG

```
Close-up, slow dolly-in on a tired man rubbing his temples. 
He exhales and glances toward a flickering desk lamp. 
Dim late-night office, harsh fluorescent overhead light plus green monitor glow. 
1980s film look, subtle grain, tense atmosphere.
```

**✅ Phân tích cấu trúc:**

| Phần | Nội dung trong prompt |
|------|----------------------|
| **[Cinematography]** | Close-up, slow dolly-in |
| **[Subject]** | on a tired man |
| **[Action]** | rubbing his temples. He exhales and glances toward a flickering desk lamp |
| **[Context]** | Dim late-night office, harsh fluorescent overhead light plus green monitor glow |
| **[Style & Ambiance]** | 1980s film look, subtle grain, tense atmosphere |

---

# PHẦN 4: MASTER CHECKLIST - PROMPT ADHERENCE

---

## ✅ TRƯỚC KHI SUBMIT

### Cấu trúc
- [ ] Prompt theo skeleton 5 phần?
- [ ] Camera movement đặt ĐẦU TIÊN?
- [ ] Mỗi phần chỉ có 1 yếu tố chủ đạo?

### Xung đột
- [ ] Không có 2 camera movements cùng lúc?
- [ ] Không có styles mâu thuẫn?
- [ ] Action có thể quay được (không phải 'ý niệm')?

### Test
- [ ] Đã test từng biến riêng lẻ?
- [ ] Đã giữ prompt đơn giản trước khi thêm chi tiết?
- [ ] Đã thử iteration (sửa dần dần)?

---

## 🔧 KHI VEO VẪN "LÀM NGƠ"

| Triệu chứng | Giải pháp |
|-------------|-----------|
| Camera không bám | Bỏ hết style, test camera đơn thuần |
| Action sai | Dùng static camera, test action đơn thuần |
| Style lệch | Giảm về 1 style keyword duy nhất |
| Nhân vật sai | Tăng chi tiết Subject, giảm Context |

---

## 🔗 LIÊN KẾT VỚI CÁC TEMPLATE KHÁC

| Template | File | Sử dụng khi |
|----------|------|-------------|
| **Veo Master Guide** | [15_Veo_Master_Guide_Template.md](file:///D:/Music/Ruby/Produce%20for%20Customer/Research/My%20Content/00_System/15_Veo_Master_Guide_Template.md) | Cấu trúc prompt chuẩn |
| **Director Toolkit** | [14_Director_Toolkit_Template.md](file:///D:/Music/Ruby/Produce%20for%20Customer/Research/My%20Content/00_System/14_Director_Toolkit_Template.md) | Shot size, camera move |
| **Negative Prompt** | [11_Negative_Prompt_Template.md](file:///D:/Music/Ruby/Produce%20for%20Customer/Research/My%20Content/00_System/11_Negative_Prompt_Template.md) | Loại bỏ yếu tố không mong muốn |

---

*Prompt Adherence Template v1.0 - 2026-01-30 - Quy trình Debug 4 Bước*
