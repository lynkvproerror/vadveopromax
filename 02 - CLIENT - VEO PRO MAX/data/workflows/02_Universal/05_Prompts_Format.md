# PROMPTS.TXT TEMPLATE - VEO 3 VISUAL PROMPTS
## Template chuẩn cho file `XX_Prompts.txt`

**Phiên bản**: 1.2  
**Cập nhật**: 2026-02-08  
**Áp dụng**: Tất cả dự án - Dùng cho AI Veo 3

---

## 📋 FORMAT CHUẨN MỖI PROMPT

```
[Scene type]. [Shot type + Camera movement]. [Visual Style prefix]. [Setting description]. [Character Name Tag] [Character full description + action]. [Audio/SFX cue], no text, no subtitles, no labels, no watermarks.
```

---

## 🏷️ CHARACTER NAME TAG (BẮT BUỘC)

### Quy tắc:
- **Mỗi nhân vật** phải có tag `[Tên nhân vật]` đặt **ngay trước** phần mô tả nhân vật đó
- Format: `[Tên gọi] Tên gọi, mô tả đầy đủ nhân vật...`
- Áp dụng cho **cả Master.txt và Prompts.txt**
- **Mọi lần** nhân vật xuất hiện trong prompt đều phải có tag

### Ví dụ:
```
...setting. [Cụ Chưng] Cụ Chưng, an anthropomorphic Vietnamese Tết sticky rice cake, oversized 35cm tall, square body... [Human] Human, a 25-year-old Vietnamese young man, 1.72m, light warm golden skin...
```

> [!IMPORTANT]
> Tag `[Name]` giúp AI identify và lock nhân vật nhất quán qua các scene.
> KHÔNG được bỏ tag. KHÔNG được viết sai tên trong tag.

---

## 🎨 CHARACTER REFERENCE IMAGE (BẮT BUỘC)

### Quy tắc:
- **Mỗi nhân vật CHÍNH** (anthropomorphic) cần 1 ảnh tham chiếu
- Đặt tên file: `[Tên gọi nhân vật].png` (ví dụ: `Cụ Chưng.png`)
- Lưu trong thư mục dự án
- Tạo **1 lần** cho mỗi nhân vật unique (nếu nhân vật dùng chung giữa các dự án, chỉ cần 1 ảnh)
- Ảnh phải khớp với Character Profile Lock trong Bible

### Quy trình:
1. Trong Bible (`_Bible.md`), section `## 🖼️ CHARACTER IMAGE PROMPT` chứa prompt tạo ảnh sẵn
2. Copy prompt đó vào bất kỳ AI image generator (Midjourney, DALL-E, Leonardo, Flux, etc.)
3. Lưu ảnh thành `[Tên nhân vật].png` trong thư mục dự án

### Checklist:
- [ ] Bible có section `CHARACTER IMAGE PROMPT` với prompt chi tiết cho MỌI nhân vật (chính + phụ)
- [ ] Ảnh đúng style (3D animated Pixar-inspired)
- [ ] Màu sắc khớp HEX code trong Bible
- [ ] Biểu cảm mặc định đúng personality
- [ ] Tên file = Tên gọi nhân vật

### Tổng hợp `_Total_Image_Prompts.md` (BẮT BUỘC):
- Sau khi TẤT CẢ Bible đã có CHARACTER IMAGE PROMPT, tạo file `_Total_Image_Prompts.md` tại **thư mục gốc** (cùng cấp với các folder dự án)
- Format mỗi dòng: `XX [Tên nhân vật]. Prompt...` (XX = số thứ tự dự án)
- **Mỗi prompt cách nhau 1 dòng trống** (2 lần enter)
- Sắp xếp lần lượt theo dự án: nhân vật chính trước, Human sau
- File này dùng để tạo ảnh hàng loạt — chỉ chứa prompt thuần, không markdown thừa

```
Ví dụ:
01 [Cụ Chưng]. Whimsical 3D Pixar-style character portrait...

01 [Human (Nam thanh niên 25t)]. Whimsical 3D Pixar-style...

02 [Lão Gừng]. Whimsical 3D Pixar-style character portrait...

02 [Human (Nhân viên VP 35t)]. Whimsical 3D Pixar-style...
```



## ✅ VÍ DỤ ĐÚNG

```
Opening scene, establishing the problem. Medium shot, slow dolly in. The 3D cute animation style, Pixar render, soft lighting, vibrant colors. Vietnamese family kitchen with traditional red Tet decorations, warm morning light streaming through window. A middle-aged Asian mother, 42 years old, wearing light blue cotton t-shirt and gray sweatpants, standing at the counter, looking worried at leftover food containers, hand on hip. Audio of refrigerator humming and morning ambiance, no text, no subtitles, no labels, no watermarks.

Mechanism scene 1, explaining bacterial growth. Extreme close-up, macro reveal. The 3D cute animation style, Pixar render, soft lighting, vibrant colors. Inside the leftover food container, microscopic view with organic textures. An anthropomorphic green bacteria with simple dot eyes showing excitement, curved wide grin, tiny arms raised in victory, multiplying rapidly with green glow effect, bubbles forming around. Audio of wet bubbling growth sounds, no text, no subtitles, no labels, no watermarks.

Consequence scene, split screen showing effect. Split screen composition, static shot. The 3D cute animation style, Pixar render, soft lighting, vibrant colors. Left side: Inside stomach environment with warm reddish lighting, bacteria celebrating. Right side: Living room with dim lighting, the same mother sitting on couch, pale yellowish skin, holding stomach in pain, sweating droplets visible on forehead, grimacing expression. Audio of stomach gurgling and distressed ambient, no text, no subtitles, no labels, no watermarks.

Solution scene, expert advice. Medium shot, orbit shot. The 3D cute animation style, Pixar render, soft lighting, vibrant colors. Clean bright hospital setting with soft blue-white lighting, medical equipment in background. A professional female doctor, 35 years old, wearing white lab coat over light blue scrubs, stethoscope around neck, glasses, confident warm expression, short neat black hair, holding up two fingers indicating rule. Audio of calm reassuring background music, no text, no subtitles, no labels, no watermarks.
```

> [!CAUTION]
> Lưu ý: Ví dụ trên có **blank line giữa mỗi prompt** — đây là BẮT BUỘC.
> KHÔNG được dồn liền các prompts. Mỗi prompt = 1 dòng, giữa 2 prompt = 1 blank line (enter 2 lần).
> Đây là v9.7 rule — áp dụng cho cả Master và Prompts.

---

## ❌ FORMAT SAI (KHÔNG DÙNG)

```
❌ SAI 1: Có text trong visual
Close-up of thermometer showing "38°C"...

❌ SAI 2: Có thoại trong prompt
...mother says "Tôi lo quá!"

❌ SAI 3: Có metadata voice
...[Region: Bắc] [Gender: Female]...

❌ SAI 4: Thiếu mandatory suffix
...mother looking worried. (THIẾU: no text, no subtitles...)

❌ SAI 5: Có labels/signs
...poster on wall reads "Danger Zone 4-60°C"...
```

---

## 🚫 E7 - ZERO TEXT POLICY (BẮT BUỘC)

### Danh sách từ khóa CẤM TUYỆT ĐỐI:

| Category | Trigger Words CẤM |
|----------|-------------------|
| **Numbers** | `shows "X"`, `displays X`, counter, timer, meter, clock |
| **Labels** | label, labeled, tag, caption, title, name |
| **Signs** | sign, poster, banner, billboard, notice |
| **Text Actions** | reads, says, shows text, displays text, writes |
| **UI Elements** | button, menu, interface, screen showing |
| **Charts** | chart, graph, diagram with text, infographic |

### Bảng chuyển đổi:

| ❌ SAI (Text-Trigger) | ✅ ĐÚNG (Visual Alternative) |
|----------------------|------------------------------|
| `clock shows "3:00 PM"` | `afternoon lighting, sun position` |
| `thermometer displays "38°C"` | `thermometer needle in red zone, glowing` |
| `sign reads "Danger"` | `red warning glow pulsing` |
| `counter shows "100"` | `container overflowing, liquid spilling` |
| `phone screen showing message` | `phone glowing with notification light` |
| `percentage bar at 80%` | `container nearly full, almost overflowing` |

---

## 🎥 E28 - CAMERA MOVEMENT KEYWORDS

### Bắt buộc có ít nhất 1 keyword mỗi prompt:

| Effect | Keyword | Dùng khi nào |
|--------|---------|--------------|
| **Kịch tính** | `Slow dolly in` | Hook, soi chi tiết |
| **Mở rộng** | `Slow pull out` | Reveal context |
| **Theo dõi** | `Tracking shot` | Character movement |
| **Giới thiệu** | `Orbit shot` | Hero/Villain entrance |
| **Bất an** | `Dutch angle` | Danger, warning |
| **Quyền lực** | `Low angle shot` | Villain dominant |
| **Yếu đuối** | `High angle shot` | Victim perspective |
| **Macro** | `Extreme close-up, macro reveal` | Bacteria, detail |

---

## 🧵 E31 - SEAMLESS STITCHING (Long-form)

### Kỹ thuật nối clip liền mạch:

| Kỹ thuật | Clip trước kết thúc | Clip sau bắt đầu |
|----------|---------------------|------------------|
| **End-Start** | `...character mid-gesture` | `Continuing from mid-gesture...` |
| **Motion blur** | `...whip pan right blur` | `Blur resolving to sharp...` |
| **Object pass** | `...blocked by character back` | `Reveal from behind character...` |
| **Match cut** | `...circular object filling frame` | `Similar circular shape...` |

---

## 🎞️ MULTI-SEGMENT PROMPTS (1-3 phân cảnh / prompt)

> [!IMPORTANT]
> Mỗi prompt (8s clip) có thể chứa **1-3 phân cảnh** (sub-scenes).
> Sub-scenes thay đổi **GÓC NHÌN / CAMERA**, không thay đổi lượng thoại.
> Dialogue: **15-20 từ TỔNG** cho cả prompt, bất kể số segments.

> [!CAUTION]
> **BẮT BUỘC (v9.7)**: Ít nhất **3-5 prompts** trong mỗi project PHẢI dùng multi-segment `>>`.
> Hook, Teaching/Tips phức tạp, và Demo scenes NÊN ưu tiên 2-3 segments.
> KHÔNG được viết 100% prompts chỉ có 1 segment.

### Cú pháp: Dùng `>>` phân cách segments

**1 segment (mặc định):**
```
[Scene type]. [Shot]. [Style]. [Setting + Character + Action]. Audio... [suffix]
```

**2 segments:**
```
[Scene type]. [Style]. SEG1: [Shot]. [Setting + Character + Action].
>> SEG2: [Shot]. [Character + Reaction/New angle].
Audio... [suffix]
```

**3 segments:**
```
[Scene type]. [Style]. SEG1: [Shot]. [Description].
>> SEG2: [Shot]. [Description].
>> SEG3: [Shot]. [Description].
Audio... [suffix]
```

### 8 Quy tắc:

| # | Quy tắc | Chi tiết |
|---|---------|----------|
| 1 | **Max 3 segments** | Quá nhiều → VEO bị confused |
| 2 | **Mỗi seg ≈ 2-3 giây** | 3 seg = ~2.5s + 2.5s + 3s |
| 3 | **Dialogue 15-20 từ TỔNG** | Tổng cho cả prompt, không mỗi seg |
| 4 | **Character Lock giữ nguyên** | Chỉ thay action/expression, không đổi mô tả |
| 5 | **Camera logic** | wide→close, close→reveal — KHÔNG nhảy loạn |
| 6 | **Audio liền mạch** | 1 audio cue cho cả prompt |
| 7 | **Thoại linh hoạt** | Monologue / 2 chars tương tác / chia theo seg |
| 8 | **Segment ≠ nhiều thoại** | Thoại vẫn 15-20 từ dù 1 hay 3 seg |

### Phân bổ segments (8-12 prompts linh hoạt):

| Scene role | Seg gợi ý | 1 seg khi | 2-3 seg khi |
|------------|-----------|-----------|-------------|
| **Hook** | 2-3 | Project ngắn | Dynamic mở đầu |
| **Problem** | 1-2 | Vấn đề đơn | Show reaction |
| **Teaching** | 2-3 | 1 bước duy nhất | Demo nhiều bước |
| **Demo** | 2-3 | Hành động đơn | Quá trình liên tiếp |
| **Result** | 1-2 | Kết quả rõ | So sánh trước/sau |
| **Hook-end** | 1 | Kết gọn | - |

```
8 prompts:  tổng ≈ 14 segments (minimum - KHÔNG nên dùng trừ khi đơn giản)
10 prompts: tổng ≈ 19 segments (ưu tiên)
12 prompts: tổng ≈ 24 segments (phức tạp)
```

> [!WARNING]
> **KHÔNG mặc định 9 prompts** (Hook + Problem + 5 Tips + Result + Hook-end).
> Ưu tiên **10-12 prompts** bằng cách thêm Demo, Reaction, Warning, Practice, Comparison scenes.

### Ví dụ: 1-segment vs 3-segment

**1 segment (hiện tại):**
```
Hook scene. Medium shot. Whimsical animated style. Vietnamese kitchen 
with anthropomorphic carrot, vivid warm orange body, forest green top, 
excited expression, mouth open speaking. Audio of cheerful music, 
no text, no subtitles, no labels, no watermarks.
```

**3 segments (mới — cùng 8s, visual phong phú hơn):**
```
Hook scene (3 SEG). Whimsical animated style. 
SEG1: Wide shot, slow dolly in. Vietnamese kitchen, anthropomorphic carrot 
with vivid warm orange body, forest green leafy top, standing on cutting 
board arms crossed, confident pose.
>> SEG2: Close-up, quick zoom. Carrot face, mouth open speaking playfully, 
sassy expression, one arm pointing at camera, eyebrows raised.
>> SEG3: Wide shot, pull out. Revealing confused person in background, 
carrot turning to audience with knowing wink. 
Audio of cheerful music building, no text, no subtitles, no labels, 
no watermarks, no deformed limbs, no mutated faces, no extra fingers, 
no melting geometry, no color shifts, no texture distortion.
```

---

## 📐 CẤU TRÚC PROMPT ĐẦY ĐỦ

```
[1. Scene type]
    Opening scene / Mechanism scene 1 / Consequence scene / Solution scene

[2. Shot type + Camera movement]
    Medium shot, slow dolly in / Close-up, tracking shot / Wide shot, orbit

[3. Visual Style prefix] - COPY-PASTE Y NGUYÊN
    The 3D cute animation style, Pixar render, soft lighting, vibrant colors

[4. Setting description] - COPY TỪ BIBLE
    Vietnamese family kitchen with traditional Tet decorations, warm morning light

[5. Character full description] - COPY TỪ BIBLE
    A middle-aged Asian mother, 42 years old, wearing light blue cotton t-shirt...

[6. Character action]
    standing at the counter, looking worried at leftover food containers

[7. Audio/SFX cue]
    Audio of refrigerator humming and morning ambiance

[8. Mandatory suffix] - LUÔN LUÔN THÊM
    no text, no subtitles, no labels, no watermarks
```

---

## ✅ CHECKLIST TRƯỚC KHI SUBMIT

- [ ] Không có text trong dấu ngoặc kép `"..."` trong visual
- [ ] Không có từ: shows, displays, reads, says + text
- [ ] Không có labels, signs, posters, buttons, menus
- [ ] Không có số liệu cụ thể trong visual
- [ ] Không có thoại hoặc voice metadata
- [ ] Có Camera movement keyword (E28)
- [ ] Có Visual Style prefix đầy đủ
- [ ] Có Character description đầy đủ (tuổi, trang phục, biểu cảm)
- [ ] Có mandatory suffix ở cuối
- [ ] Nếu multi-character: MỌI nhân vật đều có mô tả đầy đủ
- [ ] 🔴 Blank line giữa mỗi prompt (enter 2 lần) — NEW v1.2
- [ ] 🔴 ≥3 prompts có multi-segment `>>` (Hook, Teaching, Demo) — NEW v1.2
- [ ] 🔴 Prompt count ≥ 10 (ưu tiên), không cố định 9 — NEW v1.2

---

## 🔒 CHARACTER LOCK SYSTEM (PLAYBOOK 5 LỚP KHÓA)

### Mục tiêu: Đạt độ nhất quán 95-99% cho nhân vật

> [!IMPORTANT]
> AI không có "trí nhớ" theo cách chúng ta nghĩ. Nó chỉ hiểu những gì được nhắc lại liên tục.
> Quên đi việc hy vọng AI sẽ "hiểu ý bạn" - sự nhất quán đến từ việc áp dụng một hệ thống đã được chứng minh.

### 3 "Cơn Ác Mộng" Của Creator AI:

| Vấn đề | Mô tả | Nguyên nhân |
|--------|-------|-------------|
| 🎨 **Đổi Màu Sắc** | Áo cam → Áo tím giữa video | Không khóa màu HEX |
| 😵 **Biến Dạng** | Mặt bị méo, thay đổi giữa scenes | Thiếu chi tiết cố định |
| 👥 **Mất Nhất Quán** | 2 người khác nhau trong cùng 1 nhân vật | Không lặp lại profile |

---

### 🔑 CHÌA KHÓA #1: XÂY DỰNG "CHARACTER PROFILE LOCK"

**Nguyên tắc:** Cảnh 1 quyết định sự ổn định của 15 cảnh tiếp theo. Một mô tả sơ sài sẽ dẫn đến kết quả ngẫu nhiên.

| ❌ TRƯỚC (Sơ sài) | ✅ SAU (Character Profile Lock) |
|-------------------|--------------------------------|
| `a man in a jacket` | `Character Profile Lock: Male, 1.8m, sharp jawline, rich dark black messy hair, bold bright orange jacket, soft matte black pants, matte lowpoly material.` |

**Các yếu tố BẮT BUỘC trong Character Profile Lock:**

```
TRONG BIBLE (HEX + Text Description):
├── Hair: #0F0F0F - rich dark black messy hair
├── Clothing: #FF6B00 - bold bright orange jacket
├── Pants: #1A1A1A - soft matte black pants
└── Accessories: #FFD700 - rich metallic gold earrings

TRONG MASTER + PROMPTS (CHỈ Text Description):
├── Gender + Height (Male/Female, 1.6m/1.8m)
├── Face features (sharp jawline, round face, prominent cheekbones)
├── Hair style + color description (rich dark black messy hair)
├── Clothing + color description (bold bright orange jacket)
├── Pants/Bottom + color description (soft matte black pants)
├── Accessories + color description (rich metallic gold earrings)
└── Material/Style (matte lowpoly material, realistic skin texture)
```

> [!WARNING]
> **Bible** chứa CẢ HEX + Text (VD: `#FF6B00 - bold bright orange`)
> **Master + Prompts** CHỈ chứa Text Description, KHÔNG có mã HEX.
> VEO không xử lý tốt raw HEX → dùng text description chi tiết thay thế.

---

### 🔑 CHÌA KHÓA #2: LẶP LẠI PROFILE Ở MỌI SCENE

> [!CAUTION]
> Sai lầm lớn nhất là viết "same character as previous scene". AI không có "trí nhớ"!
> Để đạt độ nhất quán 95-100%, bạn phải **LẶP LẠI ĐẦY ĐỦ** mô tả nhân vật ở mỗi cảnh, KHÔNG CÓ NGOẠI LỆ.

**❌ QUY TRÌNH SAI:**

```
Scene 1: Character Profile Lock: Male, 1.8m, sharp jawline, 
         rich dark black messy hair, bold bright orange jacket, 
         soft matte black pants, matte lowpoly material.

Scene 2: "same character" ❌

Scene 3: "he walks" ❌
```

**✅ QUY TRÌNH ĐÚNG:**

```
Scene 1: Character Profile Lock: Male, 1.8m, sharp jawline, 
         rich dark black messy hair, bold bright orange jacket, 
         soft matte black pants, matte lowpoly material.

Scene 2: Character Profile Lock: Male, 1.8m, sharp jawline, 
         rich dark black messy hair, bold bright orange jacket, 
         soft matte black pants, matte lowpoly material.

Scene 3: Character Profile Lock: Male, 1.8m, sharp jawline, 
         rich dark black messy hair, bold bright orange jacket, 
         soft matte black pants, matte lowpoly material.
```

---

### 📋 CHECKLIST CHARACTER LOCK

- [ ] Mỗi nhân vật có **Character Profile Lock** đầy đủ ở Scene 1
- [ ] HEX colors cho TẤT CẢ màu sắc (tóc, áo, quần, phụ kiện)
- [ ] **LẶP LẠI TOÀN BỘ** Character Profile Lock ở MỌI scene
- [ ] Không dùng "same character", "như scene trước", "he/she"
- [ ] Mô tả chi tiết: chiều cao, đặc điểm mặt, kiểu tóc, trang phục, phụ kiện
- [ ] 🔴 **ANTI-DECAY**: Scene 2+ có ĐẦY ĐỦ 8 fields giống hệt Scene 1 (v9.8)

---

### 🔴 ANTI-DECAY: CHỐNG SUY GIẢM PROFILE QUA CÁC SCENES (v9.8)

> [!CAUTION]
> **Vấn đề phổ biến**: Agent/người viết có xu hướng viết ĐẦY ĐỦ mô tả ở scene đầu tiên,
> rồi **"decay" (suy giảm) dần** — bỏ bớt face, skin modifiers, pants, accessories từ scene 2 trở đi.
> Hiện tượng này đặc biệt nghiêm trọng khi nhân vật ở **SEG2** hoặc **background**.
>
> **Hậu quả**: AI không có trí nhớ → thiếu field = AI render nhân vật KHÁC → mất nhất quán.

#### 8 MANDATORY FIELDS — Không được bỏ bất kỳ field nào

| # | Field | Ví dụ | Hay bị bỏ ở scene? |
|---|-------|-------|---------------------|
| 1 | **Age + Role** | `58-year-old Vietnamese mother-in-law` | Ít khi bỏ |
| 2 | **Height** | `1.58m` | Ít khi bỏ |
| 3 | **Skin + Modifier** | `warm caramel brown **naturally weathered** skin` | 🔴 HAY BỎ modifier |
| 4 | **Face features** | `round face smile lines prominent cheekbones` | 🔴 RẤT HAY BỎ |
| 5 | **Hair** | `deep charcoal black gray-streaked hair in bun` | Ít khi bỏ |
| 6 | **Clothing top** | `dark maroon áo bà ba` | Ít khi bỏ |
| 7 | **Clothing bottom** | `deep matte charcoal black loose pants` | 🔴 RẤT HAY BỎ |
| 8 | **Accessories** | `warm antique gold earrings, sea green jade bracelet` | 🔴 HAY BỎ khi ở SEG2 |

#### Quy tắc ANTI-DECAY

1. **Scene 1 (Hook) = BASELINE** — viết đầy đủ nhất, là chuẩn cho tất cả scenes sau
2. **MỌI scene sau = COPY 8 fields từ baseline** — chỉ thay đổi expression và action
3. **SEG2 / Background KHÔNG PHẢI lý do cắt bỏ** — nhân vật visible = phải đủ 8 fields
4. **Self-check bắt buộc**: Sau khi viết xong, so sánh từng scene vs scene 1

#### ❌ Decay Pattern điển hình

```
Scene 1: Bà Tư, 58-year-old..., 1.58m, warm caramel brown naturally weathered skin,
         round face smile lines prominent cheekbones, deep charcoal black gray-streaked
         hair in bun, dark maroon áo bà ba, deep matte charcoal black loose pants,
         warm antique gold small earrings, sea green jade bracelet, stern expression...

Scene 5: Bà Tư, 58-year-old..., 1.58m, warm caramel brown skin,     ← THIẾU "naturally weathered"
                                                                       ← THIẾU face features
         deep charcoal black gray-streaked hair in bun,
         dark maroon áo bà ba,                                       ← THIẾU pants
         warm antique gold small earrings, sea green jade bracelet...
```

#### ✅ Đúng — MỌI scene giống hệt baseline

```
Scene 5: Bà Tư, 58-year-old..., 1.58m, warm caramel brown naturally weathered skin,
         round face smile lines prominent cheekbones, deep charcoal black gray-streaked
         hair in bun, dark maroon áo bà ba, deep matte charcoal black loose pants,
         warm antique gold small earrings, sea green jade bracelet, solemn expression...
```

> [!WARNING]
> Rule này áp dụng cho **TẤT CẢ project types** — Family Drama, Health, Entertainment, Anthropomorphic.
> Bất kỳ nhân vật nào xuất hiện visible trong bất kỳ scene nào đều phải có đủ 8 fields.

---

### 🔑 CHÌA KHÓA #2B: SPEAKER EXPRESSION SYSTEM (BẮT BUỘC)

> [!CRITICAL]
> Mỗi scene có NGƯỜI NÓI và NGƯỜI NGHE. Prompt PHẢI mô tả rõ ràng:
> - **Ai đang nói?** → Có speaking indicator
> - **Biểu cảm khi nói?** → Facial expression khớp với cảm xúc thoại
> - **Ai đang nghe?** → Có listening expression tương ứng

#### ❌ SAI (Thiếu Speaking Indicator):

```
Bà Tư... stern critical expression, pursed lips, shaking head...
Hương... anxious expression, hands clasped...
```

**Vấn đề:** Không rõ AI đang nói - chỉ có expression tĩnh, không có trạng thái ĐANG NÓI.

#### ✅ ĐÚNG (Có Speaking + Listening States):

```
Bà Tư... stern critical expression, mouth open speaking firmly, 
scolding tone visible in posture, pointing finger forcefully...
Hương... anxious listening expression, slightly bowed head, 
eyes downcast receiving criticism, hands clasped nervously...
```

---

#### 📋 BẢNG SPEAKING INDICATORS (Thêm vào mô tả NGƯỜI NÓI)

| Cảm xúc thoại | Speaking Indicator cần thêm |
|---------------|----------------------------|
| Chửi/la mắng | `mouth open speaking firmly, scolding tone visible, angry speaking gesture` |
| Dạy dỗ/hướng dẫn | `speaking instructively, explaining with open mouth, teaching gesture` |
| Xin lỗi/ân hận | `speaking softly, lips moving apologetically, humble speaking posture` |
| Khen ngợi | `speaking admiringly, open mouth praise, enthusiastic speaking gesture` |
| Hài lòng/đồng ý | `speaking approvingly, slight smile while talking, nodding as speaking` |
| Tò mò/hỏi | `asking curiously, mouth forming question, inquisitive speaking expression` |
| Trấn an | `speaking reassuringly, calm open mouth, comforting speaking tone visible` |
| Vui vẻ/đùa | `speaking playfully, wide smile while talking, animated speaking gesture` |
| Than vãn | `complaining vocally, mouth pursed while speaking, exasperated speaking` |
| Ngạc nhiên | `exclaiming with surprise, mouth wide, startled speaking expression` |

---

#### 📋 BẢNG LISTENING EXPRESSIONS (Thêm vào mô tả NGƯỜI NGHE)

| Người nói đang... | Listening Expression cho người nghe |
|-------------------|-------------------------------------|
| Chửi/la mắng | `receiving criticism, eyes downcast, shrinking posture, attentive listening` |
| Dạy dỗ | `attentive listening expression, nodding, absorbing information, focused eyes` |
| Khen ngợi | `receiving praise, brightening expression, grateful listening posture` |
| Hỏi | `considering response, thoughtful listening, processing question` |
| Than vãn | `sympathetic listening, concerned expression, attentive to complaint` |

---

#### 🔍 VÍ DỤ ĐẦY ĐỦ MỘT SCENE

**Thoại:** Bà Tư nói (chửi): "Hai giờ sáng còn lướt điện thoại, mày định thức tới sáng cho tao lo à."

**Prompt ĐÚNG (CHỈ text description, KHÔNG HEX):**
```
Bà Tư, a 58-year-old Vietnamese mother-in-law, 1.58m, warm golden tan sun-kissed skin, 
gray-streaked soft matte black hair in traditional bun, wearing deep dark chocolate brown áo bà ba, 
stern critical expression, mouth open speaking firmly, scolding tone visible, 
raised eyebrows showing disapproval, pointing finger accusingly, shaking head while speaking.

Hương, a 28-year-old daughter-in-law, 1.62m, soft warm ivory light peach skin, 
long deep jet black hair in messy ponytail, wearing soft baby pink delicate blush pajamas, 
startled anxious expression receiving scolding, eyes widened in surprise, 
caught in the act posture, phone in hand frozen, shrinking back slightly.
```

---

#### 📋 CHECKLIST SPEAKER EXPRESSION (Thêm vào QC)

- [ ] 🔴 Mỗi scene xác định rõ AI ĐANG NÓI (từ Dubbing)
- [ ] 🔴 Người NÓI có speaking indicator (mouth open, speaking + emotion)
- [ ] 🔴 Người NGHE có listening expression tương ứng
- [ ] 🔴 Biểu cảm khớp với cảm xúc của thoại (chửi → stern, khen → warm)
- [ ] ⚠️ Không chỉ dùng expression tĩnh (stern expression) mà thiếu trạng thái nói

---

### 🔑 CHÌA KHÓA #3: MÔ TẢ MÀU SẮC BẰNG VĂN BẢN CHI TIẾT

> [!WARNING]
> **VEO không xử lý tốt mã HEX raw trong prompt** — dễ gây lỗi render.
> - **Bible**: Giữ CẢ HEX + Text description cạnh nhau (source of truth)
> - **Master + Prompts**: CHỈ dùng text description chi tiết, KHÔNG CÓ mã HEX
> - Mô tả phải đủ chi tiết để VEO render chính xác màu mong muốn

| ❌ MƠ HỒ | ✅ BIBLE (HEX + Text) | ✅ MASTER/PROMPTS (Text only) |
|----------|----------------------|-------------------------------|
| `blue jacket` | `#0093E1 - bright cerulean blue jacket` | `bright cerulean blue jacket` |
| `dark pants` | `#1A1A1A - soft matte black pants` | `soft matte black pants` |
| `black hair` | `#0B0B0B - deep jet black hair` | `deep jet black hair` |

### 🔄 BẢNG TRA CỨU HEX → TEXT (Công cụ chuyển đổi — KHÔNG phải palette cố định)

> [!CAUTION]
> Bảng dưới đây là **CÔNG CỤ TRA CỨU** để chuyển HEX → text description.
> Đây **KHÔNG PHẢI** bảng màu mặc định cho mọi project.
> Mỗi project PHẢI tự chọn HEX codes RIÊNG → sau đó tra bảng để lấy text description.

| HEX Code | Tên ngắn | Text Description (dùng trong Master/Prompts) |
|----------|----------|----------------------------------------------|
| `#0B0B0B` | Đen tóc | `deep jet black` |
| `#0F0F0F` | Đen đậm | `rich dark black` |
| `#1A1A1A` | Đen quần | `soft matte black` |
| `#3D2314` | Nâu sẫm | `deep dark chocolate brown` |
| `#5D4037` | Nâu trung | `warm earthy brown, like worn leather` |
| `#8B4513` | Nâu gỗ | `rich saddle brown, like polished wood` |
| `#D4A574` | Da nâu ấm | `warm golden tan, sun-kissed` |
| `#E8C4A0` | Da sáng | `soft warm ivory, light peach` |
| `#F5DEB3` | Da sáng nhạt | `warm wheat-toned fair` |
| `#FADADD` | Hồng nhạt | `soft baby pink, delicate blush` |
| `#FF6B6B` | Hồng cam | `vivid warm coral-pink, salmon tone` |
| `#FF6B00` | Cam | `bold bright orange, tangerine` |
| `#FFC125` | Vàng nghệ | `warm golden amber, turmeric` |
| `#FFD700` | Vàng gold | `rich metallic gold, gleaming golden` |
| `#00A86B` | Xanh ngọc | `vivid jade green, emerald tone` |
| `#2D4739` | Xanh lá đậm | `deep forest green, dark moss` |
| `#0093E1` | Xanh dương | `bright cerulean blue, clear sky blue` |
| `#1E3A5F` | Navy | `deep navy blue, midnight blue` |
| `#4A2040` | Tím mận | `deep muted plum, dark aubergine` |
| `#FFFFFF` | Trắng | `pure clean white` |
| `#000000` | Đen tuyệt đối | `absolute pure black` |

### 🎨 QUY TẮC PALETTE MÀU THEO DỰ ÁN:

> [!IMPORTANT]
> - **Trong 1 dự án**: Palette CỐ ĐỊNH → mọi scene dùng đúng bộ màu đã chọn
> - **Giữa các dự án**: Palette PHẢI KHÁC → không dùng lại bộ HEX của project trước
> - Mỗi dự án TỰ CHỌN HEX phù hợp chủ đề + nhân vật → tra bảng lấy text description

**Ví dụ — 2 project PHẢI có palette KHÁC:**
```
DỰ ÁN A (Tôm luộc):
├── Body: #FF6B6B - vivid warm coral-pink
├── Eyes: #000000 - absolute pure black
├── Kitchen: #FFC125 - warm golden amber accents
└── Pot:  #C0C0C0 - polished silver metallic

DỰ ÁN B (Dao rửa):
├── Blade: #B8B8B8 - gleaming light steel gray
├── Handle: #2F1B14 - deep espresso brown
├── Kitchen: #F0EDE5 - soft warm cream, eggshell
└── Sink:  #E8E8E8 - matte cool light gray
```

❌ **SAI**: Dự án B dùng lại `#FF6B6B`, `#FFC125` giống Dự án A
✅ **ĐÚNG**: Mỗi dự án chọn bộ HEX mới phù hợp object + setting riêng

### Nếu HEX không có trong bảng tra cứu:
1. Tra Google: "HEX #XXXXXX color name"
2. Viết theo pattern: `[intensity] [hue modifier] [base color]`
   - **Intensity**: soft, bright, vivid, deep, muted, rich
   - **Hue modifier**: warm, cool, golden, dusty, pastel
   - **Base color**: red, blue, green, brown, pink, purple, orange, yellow

### Ví dụ chuyển đổi đầy đủ:
```
BIBLE (source of truth — palette RIÊNG cho dự án này):
Skin: #D4A574 - warm golden tan, sun-kissed
Hair: #1A1A1A - soft matte black
Clothing: #3D2314 - deep dark chocolate brown
Earrings: #FFD700 - rich metallic gold, gleaming golden

MASTER/PROMPTS (text only — KHÔNG có HEX):
warm golden tan sun-kissed skin, soft matte black hair in bun,
deep dark chocolate brown áo bà ba, rich metallic gold gleaming earrings
```

---

### 🔑 CHÌA KHÓA #4: DỰNG "ÁO GIÁP" BẰNG NEGATIVE PROMPT

Các lỗi biến dạng như méo mặt, thừa ngón tay, hay chảy hình là lỗi phổ biến của AI. **Đừng chờ sửa lỗi, hãy ngăn chặn chúng.** Negative prompt chính là "áo giáp" bảo vệ sự toàn vẹn cho nhân vật của bạn trong mọi cảnh.

**Danh sách Negative Prompt BẮT BUỘC:**

```
no deformed limbs, no mutated faces, no extra fingers, 
no melting geometry, no color shifts, no texture distortion
```

**Bảng lỗi phổ biến và Negative Prompt tương ứng:**

| Lỗi AI (Tiếng Việt) | Lỗi AI (English) | Negative Prompt |
|---------------------|------------------|-----------------|
| Méo mặt | Distorted face | `no mutated faces` |
| Mắt lệch | Misaligned eyes | `no deformed limbs` |
| Thêm ngón tay | Extra fingers | `no extra fingers` |
| Cằm chảy | Melting chin | `no melting geometry` |
| Đổi màu | Color shift | `no color shifts` |
| Texture bị lỗi | Texture distortion | `no texture distortion` |

---

### 🔑 CHÌA KHÓA #5: GIỮ VỮNG MỘT PHONG CÁCH DUY NHẤT

> [!CAUTION]
> Việc trộn lẫn "Disney + anime + realism + lowpoly" sẽ khiến AI bị "overload", dẫn đến việc nhân vật bị thay đổi tỉ lệ và cấu trúc.
> Hãy chọn **MỘT** phong cách duy nhất và mô tả nó thật rõ ràng. Sự nhất quán về phong cách sẽ tạo ra sự ổn định cho nhân vật.

**❌ SAI:** `"Disney + anime + realism + lowpoly"`

**✅ ĐÚNG - Chọn MỘT trong các phong cách sau:**

| Phong cách | Mô tả chi tiết |
|------------|----------------|
| **Anime Cinematic** | `anime cinematic style, expressive eyes, dynamic poses` |
| **Lowpoly Geometric** | `clean polygons, matte texture, sharp edges` |
| **Plastic Toys** | `plastic toy figurine style, smooth glossy surface` |
| **Realistic Vietnamese** | `realistic Vietnamese family scene, cinematic lighting, warm color grading, shallow depth of field, natural expressions` |
| **3D Pixar** | `The 3D cute animation style, Pixar render, soft lighting, vibrant colors` |

---

## 📚 TÓM TẮT: PLAYBOOK 5 LỚP KHÓA CHO NHÂN VẬT BẤT BIẾN

> [!TIP]
> **Từ May Rủi Đến Chuyên Nghiệp**: Nhân vật AI không bị biến dạng hay đổi màu không phải do may mắn. 
> **Đó là kết quả của kỹ thuật và sự chuẩn bị.** Làm đúng 5 điều này, continuity đạt 95-99% không còn là mục tiêu xa vời — đó là tiêu chuẩn mới của bạn.

| # | Tên Khóa | Mô tả | Hành động |
|---|----------|-------|-----------|
| 1 | **Bản Thiết Kế Gốc** | Mô tả nhân vật chi tiết và đầy đủ ngay từ Scene 1 | Tạo Character Profile Lock hoàn chỉnh |
| 2 | **Thuật Lặp Lại** | Copy và paste toàn bộ profile nhân vật cho mọi scene | KHÔNG dùng "same character" |
| 3 | **Mô Tả Màu Chi Tiết** | Bible: HEX + Text. Master/Prompts: CHỈ text description | Tra bảng HEX→Text, không dùng raw #XXXXXX trong prompt |
| 4 | **Mã Hóa Màu Sắc (Negative)** | Luôn sử dụng Negative Prompt để chặn các lỗi biến dạng phổ biến | Thêm `no deformed limbs...` |
| 5 | **Dấu Ấn Phong Cách** | Chọn và giữ vững một phong cách nghệ thuật duy nhất | Không mix styles |

---

## 🔗 LIÊN KẾT VỚI CÁC FILE KHÁC

| File | Cách lấy nội dung |
|------|-------------------|
| `_Bible.md` | COPY Character + Setting description |
| `_Master.txt` | TÁCH phần Visual (bỏ thoại, bỏ metadata voice) |

---

*Prompts Template v1.2 - 2026-02-08 - Updated with Blank Line + Multi-Segment Enforcement + Flexible Count*

