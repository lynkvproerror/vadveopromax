---
template_id: "treadmill_catwalk"
display_name: "Treadmill Fashion Catwalk"
group: "fashion"
keywords: [treadmill, catwalk, walking pad, đi bộ, thời trang, outfit, fashion, hard cut, silent]
visual_style: "Realistic"
structure: "conflict_tips"
scene_count_range: [6, 8]
output_files: [Bible, Prompts, SEO]
shared_rules: [01_Technical_Rules, 03_Quality_Checklist, 05_Prompts_Format, 07_SEO_Format]
advanced_rules: [01_Camera_Complete, 02_Negative_Prompts, 08_Character_Scale]
---

# 🚶‍♀️ Template: Treadmill Fashion Catwalk

> **Loại hình**: Cô gái đi bộ trên walking pad, outfit thay đổi qua hard cut  
> **Format**: Không voice — full outfit changes, continuous walking  
> **Phiên bản**: 1.0  
> **Tham khảo**: "Ông Chú MM" style

---

## 🔴 NGUYÊN TẮC CỐT LÕI

> [!CAUTION]
> 1. **TIẾNG ANH 100%** — Bible, Prompts đều viết English
> 2. **1 SETTING** — phòng khách với walking pad, KHÔNG đổi location
> 3. **GÓC MÁY CỐ ĐỊNH** — Wide shot full-body, **slightly low angle** (ngang eo), fixed tripod
> 4. **1 NHÂN VẬT** — Hot teen modern Asian beauty, KHÔNG đổi profile
> 5. **LUÔN ĐANG ĐI BỘ** — cô gái đi bộ liên tục trên treadmill, KHÔNG đứng yên
> 6. **HARD CUT** giữa bước chân — cắt trực tiếp, outfit mới ngay lập tức
> 7. **OUTFIT THAY ĐỔI TOÀN BỘ** — top + bottom + shoes + accessories đều đổi
> 8. **TÓC GIỮ NGUYÊN** — kiểu tóc cố định xuyên suốt (AI consistency)

---

## 📁 CẤU TRÚC FILE ĐẦU RA

```
[Project_Name]/
├── 01_Bible.md       ← Source of truth (English)
├── 02_Prompts.txt    ← 6-8 prompts hoàn chỉnh
└── 03_SEO.txt        ← Tiêu đề, hashtag, description
```

---

## 📐 CẤU TRÚC VIDEO (6-8 Outfits → ~18-24s)

```
OUTFIT-1  (3s) → Casual cute → friendly wave, đi nhẹ nhàng
OUTFIT-2  (3s) → Elegant chic → tự tin, tay hông
OUTFIT-3  (3s) → Coquette/feminine → duyên dáng, nhẹ nhàng
OUTFIT-4  (3s) → Streetwear cool → attitude, nonchalant
OUTFIT-5  (3s) → Romantic soft → dreamy, váy bay
OUTFIT-6  (3s) → Power boss → fierce, commanding
[OUTFIT-7] (3s) → (Tùy chọn thêm)
[OUTFIT-8] (3s) → (Tùy chọn thêm)
               = 18-24s
```

> **KHÔNG CÓ HOOK "confused"** — Bắt đầu NGAY outfit đầu tiên.
> Mỗi clip AI ~8s → cắt lấy **~3s** đẹp nhất.

---

## 📖 01_BIBLE.MD — CẤU TRÚC

### PHẦN 1: SETTING (Phòng khách + Walking Pad)

```markdown
## 1. SETTING

### Room
- Type: Modern warm-toned living room
- Walls: White cream with recessed warm LED ceiling lights
- Furniture: Wooden TV console with warm table lamp, dark leather sofa, tall wooden wardrobe
- Color palette: Warm — wood brown, cream, black, golden amber

### Walking Pad (BẮT BUỘC)
- Type: Flat walking pad treadmill (không tay vịn)
- Color: Black/dark grey
- Position: Center of room on floor
- Speed: Slow walking pace (~2-3 km/h)

### Lighting
- Ambient warm golden tone
- Ceiling LED + table lamp + natural window light
```

---

### PHẦN 2: GIRL PROFILE (Modern Asian Hot Teen — CỐ ĐỊNH)

> [!CAUTION]
> **TIÊU CHUẨN**: Hot teen modern Asian beauty.
> Profile + Hair COPY NGUYÊN VĂN vào MỌI prompt.

```markdown
## 2. GIRL PROFILE (Character Lock)

- Gender: Female
- Height: [1.60-1.68m]
- Skin: Bright fair smooth porcelain skin — modern Asian beauty
- Face: Small V-line face, high nose bridge, large double-lidded dark brown eyes, full soft lips, defined jawline
- Body: Slim toned build, straight shoulders, narrow waist, long legs
- Hair: Long dark brown hair past shoulders, flowing naturally (GIỮ NGUYÊN mọi outfit)
- Unique: [beauty mark / dimple]
```

---

### PHẦN 3: OUTFIT COLLECTION (6-8 bộ hoàn chỉnh)

> [!IMPORTANT]
> Mỗi outfit = **full set mới**: Top + Bottom (hoặc Dress) + Shoes + Accessories.
> Variety qua: kiểu dáng, màu sắc, style, vibe.

```markdown
## 3. OUTFIT COLLECTION

### OUTFIT-1: [Style Name] (vd: Casual Cute)
- Top: [or Dress if one-piece]
- Bottom: [if separate]
- Shoes: [specific]
- Accessories: [glasses / sunglasses / bag / earrings]
- Vibe/Mood: [casual, cute, friendly]
- Walking pose: [wave hand / arms swing / smile]

### OUTFIT-2: [Style Name]
- ...

(Lặp lại cho 6-8 outfits)
```

**Bảng variety mẫu:**

| # | Style | Loại | Màu chủ đạo | Shoes | Accessories |
|---|-------|------|-------------|-------|-------------|
| 1 | Casual Cute | Dress liền | Đen hoa | Chân trần | Kính cận |
| 2 | Elegant Date | Dress liền | Trắng | Boots chunky | Sunglasses |
| 3 | Coquette | Áo + Váy | Đỏ + Trắng | Mary Jane | Kính cận |
| 4 | Streetwear | Áo + Quần | Đen + Jeans | Sneakers | Cap |
| 5 | Romantic | Áo + Váy | Lavender + Cream | Sandal | Pearl earrings |
| 6 | Power Chic | Blazer + Quần | Đen toàn bộ | Stiletto | Gold jewelry |

---

## 📋 02_PROMPTS.TXT — QUY TẮC TẠO PROMPT

### 🔴 BLOCKS BẮT BUỘC TRONG MỌI PROMPT:

| Block | Bắt buộc? | Nội dung |
|-------|-----------|----------|
| `**[Setting]**` | ✅ MỌI prompt | Phòng + walking pad — copy FULL |
| `**[Girl Profile]**` | ✅ MỌI prompt | Nhân vật — copy FULL |
| `**[Hair]**` | ✅ MỌI prompt | Tóc GIỮ NGUYÊN — copy FULL |
| `**[Makeup]**` | ✅ MỌI prompt | Mức makeup cho outfit này |
| `**[Top]**` hoặc `**[Top + Bottom]**` | ✅ | Áo (hoặc dress liền) |
| `**[Bottom]**` | ✅ nếu tách | Quần/váy |
| `**[Shoes]**` | ✅ MỌI prompt | Giày cụ thể |
| `**[Accessories]**` | ✅ MỌI prompt | Phụ kiện cụ thể |
| Walking action | ✅ MỌI prompt | Đi bộ + expression + tay |

### 🔴 FORMAT TỪNG PROMPT:

```
[OUTFIT-N]. Wide shot full-body, fixed tripod slightly low angle from waist height.
**[Setting] full room + treadmill description**.
**[Girl Profile] full description**.
**[Hair] long dark brown hair flowing, swaying with walk**.
**[Makeup] level for this outfit**.
**[Top / Top+Bottom] outfit top or dress**.
**[Bottom] if separate**.
**[Shoes] specific shoes**.
**[Accessories] specific accessories**.
Walking on treadmill at gentle pace, [arm action], [expression], [direction looking], [outfit movement]. Audio of upbeat music.
```

### 🔴 ĐẶC THÙ TREADMILL:

1. **Walking action phải chi tiết**: "walking slowly on treadmill at gentle pace"
2. **Outfit movement**: mô tả váy bay, tóc đung đưa, vải chuyển động
3. **Tay**: mỗi outfit tay làm gì khác nhau (vẫy / hông / vuốt tóc / pocket)
4. **Chân**: đi bộ liên tục, KHÔNG đứng yên, KHÔNG ngồi

### 🔴 TRANSITION:

Giữa mỗi prompt ghi note:
```
> Hard cut giữa bước chân. Thay đổi: [liệt kê]. Giữ: Setting + Girl + Hair + Walking.
```

---

## 🔑 QUY LUẬT VISUAL VARIETY

### Thay đổi mỗi outfit:
1. **Top + Bottom** (hoặc toàn bộ dress)
2. **Shoes** — khác hoàn toàn
3. **Accessories** — khác (kính/sunglasses/túi/jewelry/cap)
4. **Expression + Hand pose** — khác
5. **Makeup level** — từ nhẹ → đậm (optional)

### Giữ nguyên:
1. **Girl Profile** — face, body, skin
2. **Hair** — kiểu tóc cố định (AI consistency)
3. **Setting** — cùng phòng, cùng treadmill
4. **Camera** — wide shot, slightly low, fixed
5. **Walking** — luôn đang đi bộ

---

## 🔀 QUY TRÌNH TÁCH RIÊNG — 3 BƯỚC (Character + Outfit Swap)

> [!IMPORTANT]
> Ngoài cách tạo prompt trực tiếp (all-in-one), có thể dùng quy trình **tách riêng**
> để đảm bảo nhất quán nhân vật + tự do thay đổi outfit.

### STEP 1: Tạo BASE IMAGE (Nhân vật + Bối cảnh)
```
Prompt tạo BASE — cô gái trên treadmill mặc outfit trung tính:

Full body photo of [Girl Profile FULL]. She wears a simple plain white
fitted t-shirt and basic black shorts as neutral base outfit.
[Hair FULL]. Walking on [Setting FULL with treadmill].
[Expression]. Wide shot full body, slightly low angle, ultra-realistic.
```
> Kết quả: `base_character.png` — Giữ nguyên cho MỌI outfit swap.

### STEP 2: Tạo OUTFIT IMAGE (Flat lay riêng biệt)
```
Prompt tạo OUTFIT — trang phục trên nền trắng:

Product flat lay photo on pure white background.
[MÔ TẢ chi tiết: TOP + BOTTOM + SHOES + ACCESSORIES].
Clean white background, professional product photography,
fashion flat lay, no model, top-down view, sharp details.
```
> Kết quả: `outfit_N.png` — 1 ảnh cho mỗi bộ.

### STEP 3: COMBINE — Swap Outfit lên Nhân vật
```
Task: Replace the outfit in Image #1 with the outfit from Image #2.

STRICT REQUIREMENTS:
- Keep the person in Image #1 exactly the same.
- Preserve 100% of the original face, identity, hairstyle, body shape,
  pose, lighting, and background from Image #1.
- Do NOT change the camera angle or composition.
- Do NOT beautify or modify the face.
- Do NOT alter the hairstyle.

Outfit Replacement:
- Remove the original clothing from Image #1.
- Apply the outfit from Image #2 exactly as shown.
- Match fabric, color, fit, folds, and details precisely.
- The new outfit must fit the body naturally and realistically.

Editing Scope:
- ONLY the clothing is allowed to change.
- Everything else must remain identical to Image #1.

Style:
Ultra-realistic photo edit, seamless natural blending,
correct shadows and fabric physics, no artifacts, no distortion.
```

### Quy trình sản xuất:
```
base_character.png + outfit_1.png → [AI Swap] → result_1.png
base_character.png + outfit_2.png → [AI Swap] → result_2.png
...
base_character.png + outfit_6.png → [AI Swap] → result_6.png
→ 6 ảnh kết quả → ghép hard cut → video ~18s
```

### Cấu trúc folder resources:
```
[Project_Name]/
├── 01_Bible.md
├── 02_Prompts.txt
├── 03_Storyboard.txt
└── resources/
    ├── base_character.png    ← Image #1
    ├── outfit_1_casual.png   ← Image #2
    ├── outfit_2_elegant.png
    ├── outfit_3_coquette.png
    ├── outfit_4_street.png
    ├── outfit_5_romantic.png
    └── outfit_6_power.png
```

---

## ✅ QC CHECKLIST

- [ ] Tất cả prompts tiếng Anh 100%?
- [ ] Mỗi prompt có `**[Girl Profile]**` FULL?
- [ ] Mỗi prompt có `**[Setting]**` với walking pad?
- [ ] Mỗi prompt có: Hair + Makeup + Top + Bottom + Shoes + Accessories?
- [ ] Tóc GIỐNG trong mọi prompt?
- [ ] 6-8 outfits đều KHÁC NHAU hoàn toàn?
- [ ] Mỗi prompt có "walking on treadmill" action?
- [ ] Expression + hand pose có variety?
- [ ] Shoes có variety?
- [ ] Accessories có variety?
- [ ] Góc máy = "slightly low angle from waist height" trong mọi prompt?
