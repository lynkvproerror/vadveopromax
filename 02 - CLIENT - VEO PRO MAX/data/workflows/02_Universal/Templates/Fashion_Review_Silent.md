---
template_id: "fashion_review_silent"
display_name: "Fashion Review Silent"
group: "fashion"
keywords: [thời trang, fashion, review, outfit, trang phục, quần áo, unboxing, try-on, glow up, silent, KOL]
visual_style: "Realistic"
structure: "conflict_tips"
scene_count_range: [8, 12]
output_files: [Bible, Master, Prompts, SEO]
shared_rules: [01_Technical_Rules, 03_Quality_Checklist, 05_Prompts_Format, 07_SEO_Format]
advanced_rules: [01_Camera_Complete, 02_Negative_Prompts, 08_Character_Scale]
---

# 🎬 Template Sản Xuất: Người Thật Review Trang Phục (Silent Fashion Review)

> **Loại hình**: KOL Daily Life → Unboxing → Try-on Glow Up  
> **Format**: Không voice — biểu cảm + thần thái + góc máy + pose  
> **Phiên bản**: 1.3 (English-Only Edition)

---

## 📁 CẤU TRÚC FILE ĐẦU RA

```
[Project_Name]/
├── 01_Bible.md          ← MÔ TẢ GỐC (Source of truth)
├── 02_Storyboard.txt    ← KỊCH BẢN HÌNH ẢNH (Shot-by-shot)
├── 03_Prompts.txt       ← PROMPT CHO AI (nếu dùng AI gen)
├── 04_SEO.txt           ← Tiêu đề, hashtag, description
└── 05_Checklist.md      ← QC trước khi publish
```

> [!CAUTION]
> **🔴 NGÔN NGỮ: TIẾNG ANH 100% — TẤT CẢ FILES.** Bible, Storyboard, Prompts đều PHẢI viết bằng tiếng Anh.
> Mô tả nhân vật, bối cảnh, trang phục trong Bible = English → copy thẳng sang Storyboard/Prompts.

> [!IMPORTANT]
> **01_Bible.md là SOURCE.** Mọi thay đổi về nhân vật, bối cảnh, trang phục đều sửa ở Bible TRƯỚC, rồi cập nhật sang Storyboard/Prompts.

---

## 📖 01_BIBLE.MD — CẤU TRÚC CHI TIẾT

Bible gồm **5 phần bắt buộc**, mỗi phần mô tả chi tiết **bằng tiếng Anh** để đảm bảo consistency và copy-paste trực tiếp.

---

### PHẦN 1: BỐI CẢNH (Setting) — 1 LOCATION DUY NHẤT

> [!IMPORTANT]
> **CHỈ 1 BỐI CẢNH.** Mọi hoạt động (daily life, unboxing, try-on) diễn ra tại CÙNG 1 location.
> KHÔNG tách 1A/1B/1C. Chỉ cần 1 mô tả setting dùng xuyên suốt.

```markdown
## 1. SETTING

### Location (Single setting for entire video)
- Type: [bedroom / living room / studio apartment / ...]
- Lighting: [natural morning from window / ring light / softbox / ...]
- Key details: [bed, mirror, desk, sofa, ...]
- Color palette: [warm beige / cool grey / pastel / ...]
- Props: [phone, glass of water, candle, plant, ...]
- Mirror: [full-length mirror type and frame — REQUIRED for try-on]
```

---

### PHẦN 2: MÔ TẢ CÔ GÁI TRƯỚC KHI REVIEW (Before — Raw Look)

> [!CAUTION]
> **TIÊU CHUẨN NHÂN VẬT**: Cô gái trẻ xinh đẹp hot teen, nét đẹp hiện đại châu Á.
> Modern Asian beauty standard: da sáng mịn, khuôn mặt V-line hoặc oval nhỏ, mắt to, mũi cao, môi đầy.
> Đây là CHARACTER PROFILE LOCK — PHẢI GIỐNG HOÀN TOÀN giữa Before & After.

```markdown
## 2. GIRL DESCRIPTION — BEFORE REVIEW (Before)

### Character Profile Lock (UNCHANGED between Before & After):
- Gender: Female
- Height: [1.60m-1.68m]
- Skin: [bright fair smooth / naturally glowing / porcelain / ...] — modern Asian beauty
- Face: [small V-line or oval face, high nose bridge, large expressive double-lidded eyes, full soft lips, defined jawline] — hot teen modern Asian features
- Body: [slim toned / slender / petite fit / ...] — youthful attractive
- Unique feature: [beauty mark / dimple / freckles / ...]

### Before State (Daily Life):
- Hair: [messy from sleep, tangled, loose clip / ...]
- Makeup: [completely bare face, no makeup]
- Expression: [sleepy, drowsy, rubbing eyes, yawning]
- Outfit: [old oversized t-shirt, shorts, pajama, barefoot]
- Accessories: [none / simple hair clip]
```

---

### PHẦN 3: MÔ TẢ GÓI HÀNG / ĐƠN HÀNG (Package)

```markdown
## 3. GÓI HÀNG / ĐƠN ĐẶT HÀNG

### Bao bì ngoài:
- Loại: [hộp carton / túi nilon / túi giấy thương hiệu]
- Kích thước: [nhỏ gọn / trung bình / lớn]
- Màu sắc & branding: [trắng minimalist / đen sang / có logo brand]
- Tình trạng: [mới nguyên, chưa mở, còn seal/băng keo]

### Bên trong:
- Cách đóng gói: [gấp gọn trong giấy lụa / bọc PP / túi zip riêng]
- Phụ kiện kèm: [thank you card / sticker / túi đựng giày / ...]
- Số lượng sản phẩm: [1 set / 2 items / ...]
- Sắp xếp: [theo thứ tự mở: phụ kiện trước → quần → áo]

### Cảm quan khi mở:
- Âm thanh: [tiếng xé băng keo, tiếng giấy xào xạc, tiếng zip]
- Mùi: [mùi vải mới, mùi giấy]
- First impression: [chất liệu mềm, màu sắc đúng hình ...]
```

---

### PHẦN 4: MÔ TẢ TỪNG THÀNH PHẦN TRANG PHỤC (Outfit Breakdown)

Mỗi item phải mô tả riêng, đặc biệt chi tiết về chất liệu và visual.

```markdown
## 4. MÔ TẢ CHI TIẾT TRANG PHỤC

### 4A. ÁO (Top)
- Loại: [áo sơ mi / blazer / áo thun / crop top / ...]
- Màu sắc: [trắng kem / đen tuyền / xanh navy ...]
- Chất liệu: [cotton mềm / lụa satin / len mỏng / polyester ...]
- Form dáng: [ôm body / oversize / regular fit / croptop ...]
- Chi tiết đặc biệt: [nút bọc vải / cổ V / tay phồng / ...]
- Kích thước đang mặc: [S / M / ...]

### 4B. QUẦN / VÁY (Bottom)
- Loại: [quần jeans / quần ống rộng / chân váy midi / ...]
- Màu sắc: [xanh wash / đen / be ...]
- Chất liệu: [denim / vải lanh / cotton ...]
- Form dáng: [ống suông / ống rộng / ôm / xòe ...]
- Chi tiết: [cạp cao / có túi / rách gối / xẻ tà ...]
- Kích thước: [S / M / ...]

### 4C. GIÀY / DÉP (Footwear)
- Loại: [sneaker / sandal / boot / cao gót / ...]
- Màu sắc: [trắng / đen / nâu ...]
- Chất liệu: [da thật / vải canvas / da lộn ...]
- Chiều cao gót: [flat / 3cm / 7cm ...]

### 4D. PHỤ KIỆN (Accessories)
- Túi: [loại, màu, chất liệu, kích thước]
- Trang sức: [dây chuyền, vòng tay, khuyên tai ...]
- Khác: [kính mát, mũ, belt, khăn ...]

### 4E. TỔNG THỂ OUTFIT (Styling Note)
- Phong cách: [Quiet Luxury / Streetwear / Coquette / ...]
- Tone màu chủ đạo: [monochrome / earth tone / contrast ...]
- Cảm giác tổng thể: [thanh lịch / năng động / nữ tính / cool ...]
```

---

### PHẦN 5: MÔ TẢ CÔ GÁI SAU KHI MẶC ĐỒ REVIEW (After — Glow Up)

> [!CAUTION]
> **CRITICAL**: Phần này và Phần 2 phải GIỐNG HOÀN TOÀN về **chiều cao, màu da, khuôn mặt, vóc dáng, đặc điểm riêng**. Chỉ khác ở: tóc (đã làm), makeup (có), biểu cảm (tự tin), trang phục (outfit review).

```markdown
## 5. MÔ TẢ CÔ GÁI — SAU REVIEW (After — Glow Up)

### Character Profile Lock (COPY TỪ PHẦN 2 — KHÔNG THAY ĐỔI):
- Giới tính: Nữ                          ← GIỐNG Phần 2
- Chiều cao: [1.60m]                      ← GIỐNG Phần 2
- Màu da: [sáng trắng tự nhiên]          ← GIỐNG Phần 2
- Khuôn mặt: [oval nhỏ, mũi cao, mắt to tròn, môi đầy] ← GIỐNG Phần 2
- Vóc dáng: [thon gọn]                   ← GIỐNG Phần 2
- Đặc điểm riêng: [nốt ruồi dưới mắt trái] ← GIỐNG Phần 2

### Trạng thái After (Glow Up):
- Tóc: [đã chải mượt, buộc đuôi ngựa cao / xõa sóng nhẹ / ...]
- Makeup: [nhẹ nhàng tự nhiên — kem lót, cushion, mascara, son nude]
- Biểu cảm: [TỰ TIN, mắt sáng, cười nhẹ, cằm ngẩng]
- Trang phục: [COPY TỪ PHẦN 4 — full outfit đã mặc lên người]
- Phụ kiện: [COPY TỪ PHẦN 4D — đã đeo/cầm đầy đủ]

### So sánh Before vs After:
| Yếu tố | Before (Phần 2) | After (Phần 5) |
|---------|-----------------|-----------------|
| Tóc | Bù xù, rối | Chải mượt, tạo kiểu |
| Makeup | Mặt mộc | Makeup nhẹ/đầy đủ |
| Biểu cảm | Ngái ngủ, uể oải | Tự tin, rạng rỡ |
| Trang phục | Đồ ngủ/đồ nhà | Full outfit review |
| Thần thái | Lazy, casual | Confident, glowing |
| ⚠️ Chiều cao | GIỐNG | GIỐNG |
| ⚠️ Màu da | GIỐNG | GIỐNG |
| ⚠️ Khuôn mặt | GIỐNG | GIỐNG |
| ⚠️ Vóc dáng | GIỐNG | GIỐNG |
```

---

## 📋 02_STORYBOARD.TXT — CẤU TRÚC

> [!CAUTION]
> **🔴 NGÔN NGỮ: TIẾNG ANH 100%.** Storyboard/Prompts PHẢI viết bằng tiếng Anh.

> [!CAUTION]
> **🔴 COPY-PASTE ĐẦY ĐỦ.** Mỗi yếu tố (người, bối cảnh, trang phục) PHẢI dùng format
> `**[Name] FULL description copy-paste từ Bible**` — KHÔNG viết tắt, KHÔNG bỏ field.

### 🎬 CÁCH MỞ ĐẦU — POV HOOK + MULTI-OUTFIT FORMAT

> [!IMPORTANT]
> **Format chuẩn dựa trên KOL trending** (trangmeow222 style):
> 1. **HOOK**: Cô gái đứng 1 góc phòng đơn giản, outfit basic/bình thường, biểu cảm confused/suy nghĩ — ĐẶT VẤN ĐỀ
> 2. **OUTFIT 1→N**: Cùng cô gái, CÙNG VỊ TRÍ, CÙNG GÓC MÁY, thay đổi phối đồ — mỗi outfit = 1 prompt
> 3. **SETTING KHÔNG ĐỔI** — cùng 1 góc phòng xuyên suốt video
> 4. **CÔ GÁI KHÔNG ĐỔI** — chỉ thay trang phục + biểu cảm (từ confused → tự tin)

### 🔄 CẤU TRÚC VIDEO (Theo thứ tự):

```
HOOK          → Cô gái mặc basic outfit, biểu cảm suy nghĩ/confused, đặt vấn đề
OUTFIT-1      → Phối đồ thứ 1 (vd: Thứ 2), biểu cảm tự tin, pose
OUTFIT-2      → Phối đồ thứ 2 (vd: Thứ 3), biểu cảm tự tin, pose khác
OUTFIT-3      → Phối đồ thứ 3 (vd: Thứ 4), biểu cảm tự tin, pose khác
OUTFIT-4      → Phối đồ thứ 4 (vd: Thứ 5), biểu cảm tự tin, pose khác
[OUTFIT-5...] → (Tùy số lượng phối đồ)
```

### 🏷️ HỆ THỐNG BLOCK COPY-PASTE

Mỗi Bible section → 1 block `**[Name] ...**` dùng xuyên suốt Storyboard:

| Block Name | Nguồn Bible | Nội dung PHẢI có |
|------------|-------------|------------------|
| `**[Setting] ...**` | Phần 1 | Location duy nhất: loại phòng, ánh sáng, chi tiết, màu, gương |
| `**[Girl Profile] ...**` | Phần 2 Lock | Chiều cao, da, mặt (modern Asian beauty), dáng, đặc điểm riêng |
| `**[Girl Before] ...**` | Phần 2 State | Tóc, makeup, biểu cảm, trang phục basic/before |
| `**[Girl After] ...**` | Phần 5 State | Tóc, makeup, biểu cảm, trang phục styled |
| `**[Top 4A] ...**` | Phần 4A | Loại áo, màu, chất liệu, form, chi tiết |
| `**[Bottom 4B] ...**` | Phần 4B | Loại quần/váy, màu, chất liệu, form |
| `**[Shoes 4C] ...**` | Phần 4C | Loại giày, màu, chất liệu, gót |
| `**[Accessories 4D] ...**` | Phần 4D | Trang sức, túi, mũ... |
| `**[Outfit 4E] ...**` | Phần 4E | Phong cách, tone màu tổng thể |

### 🔴 QUY TẮC BẮT BUỘC:

1. **MỌI prompt viết tiếng Anh** — không mix tiếng Việt
2. **MỌI prompt có người → PHẢI có `**[Girl Profile] ...**`** copy-paste ĐẦY ĐỦ
3. **KHÔNG viết tắt** — không "same girl", "she", "the girl from before"
4. **MỌI prompt có bối cảnh → PHẢI có `**[Setting] ...**`** copy-paste
5. **MỌI prompt có trang phục → PHẢI có `**[Top/Bottom/Shoes] ...**`** copy-paste
6. **1 prompt = 1 dòng**, blank line giữa mỗi prompt
7. **CÙNG GÓC MÁY cố định** cho tất cả outfits (wide shot hoặc full-body)

### FORMAT MỖI DÒNG:

```
[Phase]. [Shot size], [camera]. **[Setting] ...**. **[Girl Profile] ...**. **[Girl Before/After] ...**, [expression], [pose]. Audio of [sound].
```

### VÍ DỤ STORYBOARD (POV HOOK + MULTI-OUTFIT):

```
HOOK. Wide shot, fixed tripod eye-level. **[Setting] A simple clean room corner with white cream walls, brown wooden door visible on left, bright natural light from window, minimal clean background**. **[Girl Profile] A 1.63m tall young woman with bright fair smooth porcelain skin, small V-line face, high straight nose bridge, large expressive double-lidded dark brown eyes, full soft pink lips, defined jawline, slim toned build with narrow waist and long legs, small beauty mark on left cheek — modern Asian hot teen beauty**. **[Girl Before] Black hair loosely falling past shoulders slightly messy, bare face minimal no makeup, white oversized button-up shirt untucked, patterned casual shorts, barefoot**, confused thinking expression with hand on chin furrowed brow looking slightly to the side. Audio of ambient room tone.

OUTFIT-1. Wide shot, fixed tripod eye-level. **[Setting] A simple clean room corner with white cream walls, brown wooden door visible on left, bright natural light**. **[Girl Profile] A 1.63m tall young woman with bright fair smooth porcelain skin, small V-line face, high straight nose bridge, large expressive double-lidded dark brown eyes, full soft pink lips, defined jawline, slim toned build with narrow waist and long legs, small beauty mark on left cheek**. **[Girl After] Black hair styled in high ponytail, light natural makeup with cushion foundation mascara and soft pink lipstick, bright confident smile**. **[Top 4A] White cotton button-up shirt regular fit tucked in, classic collar, long sleeves**. **[Bottom 4B] Black fitted mini skirt high waist above knee**. **[Accessories 4D] Black leather structured shoulder bag with gold hardware**. Confident bright smile, one hand holding bag strap, weight on one leg. Audio of upbeat music.

OUTFIT-2. Wide shot, fixed tripod eye-level. **[Setting] A simple clean room corner with white cream walls, brown wooden door visible on left, bright natural light**. **[Girl Profile] A 1.63m tall young woman with bright fair smooth porcelain skin, small V-line face, high straight nose bridge, large double-lidded dark brown eyes, full soft pink lips, defined jawline, slim toned build, small beauty mark on left cheek**. **[Girl After] Black hair in messy high bun, light natural makeup, confident elegant smile**. **[Top 4A] White cotton button-up shirt regular fit tucked in, classic collar**. **[Bottom 4B] White cream wide-leg high-waist trousers full length**. **[Accessories 4D] Black leather thin belt at waist**. Confident elegant expression, one hand on hip, one hand touching collar. Audio of upbeat music.

OUTFIT-3. Wide shot, fixed tripod eye-level. **[Setting] A simple clean room corner with white cream walls, brown wooden door visible on left, bright natural light**. **[Girl Profile] A 1.63m tall young woman with bright fair smooth porcelain skin, small V-line face, high straight nose bridge, large double-lidded dark brown eyes, full soft pink lips, defined jawline, slim toned build, small beauty mark on left cheek**. **[Girl After] Black hair in neat ponytail, light natural makeup, sweet soft smile**. **[Top 4A] White cotton button-up shirt regular fit tucked in**. **[Bottom 4B] Black wide-leg tailored trousers high waist full length**. **[Accessories 4D] Black leather crossbody small bag**. Sweet smile, one hand touching hair, relaxed confident pose. Audio of upbeat music.

OUTFIT-4. Wide shot, fixed tripod eye-level. **[Setting] A simple clean room corner with white cream walls, brown wooden door visible on left, bright natural light from window**. **[Girl Profile] A 1.63m tall young woman with bright fair smooth porcelain skin, small V-line face, high straight nose bridge, large expressive double-lidded dark brown eyes, full soft pink lips, defined jawline, slim toned build with narrow waist and long legs, small beauty mark on left cheek**. **[Girl After] Black hair in messy high bun, light natural makeup, bright beaming smile**. **[Top 4A] White cotton button-up shirt regular fit tucked in, classic collar**. **[Bottom 4B] Light wash wide-leg high-waist jeans full length**. **[Accessories 4D] Brown leather mini handbag held in one hand**. Bright beaming confident smile, one hand on hip one hand holding bag, weight shifted. Audio of upbeat music.
```

> [!IMPORTANT]
> **ANTI-DECAY**: MỌI prompt có người PHẢI copy-paste `**[Girl Profile] ...**` ĐẦY ĐỦ.
> KHÔNG viết "same girl", "she appears again", "the model". Copy nguyên văn mỗi lần.

> [!TIP]
> **GÓC MÁY CỐ ĐỊNH**: Tất cả outfit prompts dùng CÙNG shot size, CÙNG camera angle.
> Wide shot, fixed tripod, eye-level — giống y hệt reference (KOL luôn đứng cùng 1 vị trí).
> Chỉ thay: trang phục + biểu cảm + pose + kiểu tóc.

---

## 📋 QC CHECKLIST — TRƯỚC KHI DÙNG

### Character Consistency (Phần 2 vs Phần 5)
- [ ] Chiều cao GIỐNG
- [ ] Màu da GIỐNG (từ ngữ mô tả y hệt)
- [ ] Khuôn mặt GIỐNG (mọi đặc điểm)
- [ ] Vóc dáng GIỐNG
- [ ] Đặc điểm riêng GIỐNG
- [ ] Chỉ khác: tóc, makeup, biểu cảm, trang phục

### Bible Completeness
- [ ] Phần 1: Có đủ 3 bối cảnh (phòng ngủ, unbox, reveal)
- [ ] Phần 2: Character Profile Lock đầy đủ + trạng thái Before
- [ ] Phần 3: Mô tả bao bì + bên trong + cảm quan mở hộp
- [ ] Phần 4: Mô tả ĐỦ items (áo + quần/váy + giày + phụ kiện + tổng thể)
- [ ] Phần 5: Character Profile Lock COPY từ Phần 2 + trạng thái After

### 🏷️ Tag Verification (Storyboard)
- [ ] 🔴 Mọi shot Daily Life có `{BỐI_CẢNH:1A}` + `{NGƯỜI:BEFORE}`
- [ ] 🔴 Mọi shot Unboxing có `{BỐI_CẢNH:1B}` + `{GÓI_HÀNG}`
- [ ] 🔴 Shot mở hộp có tag TỪNG item: `{ÁO:4A}`, `{QUẦN:4B}`, `{GIÀY:4C}`...
- [ ] 🔴 Mọi shot Try-on có `{BỐI_CẢNH:1C}` + `{NGƯỜI:AFTER}`
- [ ] 🔴 Shot reveal/showcase có ĐỦ tag outfit: `{ÁO:4A}` + `{QUẦN:4B}` + `{GIÀY:4C}` + `{PHỤ_KIỆN:4D}`
- [ ] 🔴 MỌI shot có người → có `{NGƯỜI:PROFILE}` (anti-decay)
- [ ] 🔴 KHÔNG shot nào thiếu tag (mọi bối cảnh, người, đồ phải tagged)

### Storyboard Consistency
- [ ] Mỗi shot có cỡ cảnh rõ (TOÀN/TRUNG/CẬN/SIÊU CẬN)
- [ ] Mỗi shot có góc máy rõ (eye-level, high angle, low angle, 3/4...)
- [ ] Mỗi shot có biểu cảm cụ thể
- [ ] Trang phục After khớp 100% với Phần 4
- [ ] Có đủ 4 cỡ cảnh ít nhất 1 lần trong video
- [ ] Có blank line giữa mỗi shot

---

## 🔄 WORKFLOW TẠO CONTENT

```
Bước 1: Điền 01_Bible.md (5 phần)
   ↓
Bước 2: QC Bible — kiểm tra Phần 2 vs Phần 5 consistency
   ↓
Bước 3: Viết 02_Storyboard.txt (shot-by-shot từ Bible)
   ↓
Bước 4: (Tùy chọn) Tạo 03_Prompts.txt (nếu dùng AI image/video)
   ↓
Bước 5: Tạo 04_SEO.txt (tiêu đề, hashtag, description)
   ↓
Bước 6: QC toàn bộ bằng 05_Checklist.md
   ↓
Bước 7: Quay / Generate → Edit → Publish
```

---

> *Template v1.1 (Tag Reference Edition) — Fashion Review Silent Content Production*
