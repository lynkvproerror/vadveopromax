﻿---
description: Sản xuất video content linh hoạt - MỌI chủ đề, đảm bảo 100% tuân thủ technical rules
---

## 🧠 DECISION LOGIC (Domain: CONTENT)

> **Tham chiếu:** [_rules-session.md](./_rules-session.md) - Per-Step Decision Logic

### EVALUATE Criteria (CONTENT-Specific):

- [ ] Length/format đạt yêu cầu?
- [ ] Tone/voice phù hợp target audience?
- [ ] Content accurate và không plagiarism?
- [ ] SEO keywords đủ density (nếu applicable)?
- [ ] Structure rõ ràng, engaging?

### DECIDE Logic:

| Result | Condition | Action |
|--------|-----------|--------|
| ✅ **PASS** | ALL quality criteria met | Continue to next step |
| ⚠️ **PARTIAL** | Structure OK but tone off → Adjust tone → Review | |
| ❌ **FAIL** | Content off-topic/inaccurate → Rewrite from scratch | |

### Per-Step Template:

```markdown
## Step X: [Name]

### Execute
- Action: [What was done]

### Evaluate  
- Expected: [What should happen]
- Actual: [What happened]
- Gap: [Difference if any]

### Decide
- Status: ✅/⚠️/❌
- Reason: [Why]
- Next: [Action]
```
---

# /content-video - Flexible Video Production

> **Phiên bản**: 9.8 (Anti-Decay Edition)  
> **Nguyên tắc**: UNIVERSAL rules + ADAPTIVE content + STRICT VERIFICATION  
> **Cập nhật**: Anti-Decay Character Profile Lock + v9.7 Multi-Segment + HEX→Text

---

## 🚨 SEVERITY MARKERS

| Marker | Meaning |
|--------|---------|
| 🔴 | **CRITICAL** - Không được bỏ qua, gây lỗi nghiêm trọng |
| ⚠️ | **WARNING** - Dễ quên, cần chú ý đặc biệt |
| ❌ | **FORBIDDEN** - Ví dụ sai, KHÔNG được làm |

---

## 🔴 CRITICAL: MASTER → PROMPTS RELATIONSHIP

> [!CAUTION]
> **Master.txt là SOURCE. Prompts.txt là OUTPUT (extracted from Master).**
> 
> Khi cần SỬA visual descriptions (character, expression, action):
> 1. **SỬA Master.txt TRƯỚC** ← Đây là file gốc
> 2. Sau đó extract lại Prompts.txt từ Master (bỏ dialogue, bỏ voice metadata)
> 
> **❌ KHÔNG BAO GIỜ** chỉ sửa Prompts.txt mà không sửa Master.txt!

```
Master.txt (SOURCE)           Prompts.txt (OUTPUT)
├── Visual descriptions  →    ├── Visual descriptions (COPY)
├── Character profiles   →    ├── Character profiles (COPY)
├── Audio cues          →    ├── Audio cues (COPY)
├── Voice metadata      ×    └── no text, no subtitles... (ADD)
└── Dialogue            ×
```

---

## 🎯 CÁCH SỬ DỤNG

```
/content-video [bất kỳ chủ đề nào]
```

---

## 🔄 WORKFLOW 9 PHASES (Chi tiết TỪNG STEP)

---

### PHASE 0: ANALYZE TOPIC 🔴 TEMPLATE-FIRST (v9.3 Automation)

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 0.1 | Phân tích topic | _(AI tự phân tích)_ | - |
| 0.2 | Xác định theme type | `02_Universal/Templates/_Hybrid_Guide.md` | Section "KHI NÀO CẦN HYBRID?" |
| 🔴 0.3 | **CHECK: Template tồn tại?** | `02_Universal/Templates/*.md` | List all templates |
| 🔴 0.4a | **(Nếu CÓ template)** → Ghi nhận template path | _(Note)_ | → Tiếp Phase 1 |
| 🔴 0.4b | **(Nếu KHÔNG CÓ template)** → **TẠO NGAY** | Load `_Template_Builder.md` | Tạo + Lưu vào Templates/ |
| 0.5 | Research trending | Web search hoặc `01_Research/01_Trending_Keywords_2026.md` | Toàn bộ |
| ⚠️ 0.5b | **(Nếu Anthropomorphic)** Research châm biếm | Web search: "câu nói viral TikTok châm biếm hài hước [năm]" | Ghi 5-10 câu hot |
| 🔴 0.6 | **CHỌN DIALOGUE TONE** | `Templates/Anthropomorphic_Tips.md` §TONE CLASSIFICATION | Xác định Thể loại (1-9) + Cấp độ (Low-Max) |
| ⚠️ 0.7 | **WEB SEARCH trending phrases** | Web search: "câu nói viral TikTok [tháng] [năm]" | Chọn 2-3 câu phù hợp tone → ghi vào Bible |

**🔴 TEMPLATE-FIRST AUTOMATION LOGIC:**
```
IF topic matches existing template:
   → Use existing template
   → Continue to Phase 1

ELSE (NEW topic type):
   → STOP at Phase 0
   → Create new template using _Template_Builder.md
   → Save to Templates/[NewTemplate].md
   → THEN continue to Phase 1
```

**⚠️ TEMPLATE CHECK DECISION TREE:**
```
Topic = "Mẹ chồng dạy con dâu nấu ăn"
   → Match: Family_Drama.md ✅

Topic = "Chị dạy em trả lời hàng xóm"  
   → Match: NONE → 🔴 CREATE Social_Tips_Sister.md FIRST

Topic = "Bác sĩ giải thích bệnh tiểu đường"
   → Match: Health_PMCS.md ✅

Topic = "Cô gái review outfit mới nhận" / "KOL unbox quần áo"
   → Match: Fashion_Review_Silent.md ✅ 🔴 NEW v9.9
```

**Output**: Topic analysis + Template confirmed (existing or newly created)

---

### PHASE 1: RESEARCH

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 1.1 | Tìm trending keywords | `01_Research/01_Trending_Keywords_2026.md` | Toàn bộ |
| 1.2 | Ghi nhận title patterns | `01_Research/02_Title_Bank_Tet_2026.md` | Toàn bộ |
| 1.3 | Check SEO database | `01_Research/03_SEO_Bank_Tet_2026.md` | Toàn bộ |
| 1.4 | Note sensitive words | `01_Research/Sensitive_Words.txt` | Toàn bộ (memorize) |

**Output**: Research notes

---

### PHASE 2: LOAD RULES & TEMPLATES

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 2.1 | Hiểu core principles | `02_Universal/00_Core_Principles.md` | Toàn bộ |
| 2.2 | Đọc E-Rules liên quan | `02_Universal/01_Technical_Rules.md` | E0-E32 (focus E7, E8, E11, E19) |
| 2.3 | Hiểu file formats | `02_Universal/02_File_Formats.md` | Toàn bộ |
| 2.4a | (Nếu SINGLE Health) Load template | `02_Universal/Templates/Health_PMCS.md` | Toàn bộ |
| 2.4b | (Nếu SINGLE Entertain) Load template | `02_Universal/Templates/Entertainment_3Act.md` | Toàn bộ |
| 2.4c | (Nếu SINGLE Family) Load template | `02_Universal/Templates/Family_Drama.md` | Toàn bộ |
| 2.4d | (Nếu HYBRID) Load guide | `02_Universal/Templates/_Hybrid_Guide.md` | Toàn bộ |
| 🔴 2.4e | **(Nếu FASHION REVIEW người thật)** Load template | `02_Universal/Templates/Fashion_Review_Silent.md` | Toàn bộ — Bible 5 phần, Storyboard shot-by-shot 🔴 NEW v9.9 |

**Output**: Rules & template loaded

---

### PHASE 3: BIBLE CREATION ⚠️ HEX + TEXT REQUIRED

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 3.1 | Xác định Bible format | `02_Universal/02_File_Formats.md` | Section "1️⃣ BIBLE.MD FORMAT" |
| 🔴 3.2 | **Load CHARACTER PROFILE LOCK format** | `02_Universal/05_Prompts_Format.md` | §CHÌA KHÓA #1: CHARACTER PROFILE LOCK |
| 🔴 3.2b | **Load HEX Color Reference Table** | `02_Universal/05_Prompts_Format.md` | §BẢNG TRA CỨU HEX→TEXT |
| 3.3 | Định nghĩa characters **VỚI HEX + TEXT** | Template + Rule E8 | Height, Skin: `#D4A574 - warm golden tan`, Hair: `#1A1A1A - soft matte black` |
| 🔴 3.3b | **Tạo Text Description cho mọi màu** | `05_Prompts_Format.md` §BẢNG HEX→TEXT | Bible: `#XXXXXX - text description` song song |
| 3.4 | Định nghĩa settings | Template + Rule E9 | - |
| 3.5 | Xác định visual style | `02_Universal/00_Core_Principles.md` | Section Visual Style |
| 3.6 | Check voice format | Rule E23 | "[Giọng: Vùng, Tuổi]" |
| 3.7 | Xác định story structure | Template đã load | Section Story Structure |
| 🔴 3.8 | **Tạo CHARACTER IMAGE PROMPT** | `05_Prompts_Format.md` §CHARACTER REFERENCE IMAGE | Prompt tạo ảnh cho MỌI nhân vật (chính + phụ), lưu trong Bible |

**⚠️ CHARACTER PROFILE LOCK BẮT BUỘC (Bible format = HEX + Text):**
```
Character Profile Lock (BIBLE):
├── Gender + Height (Female, 1.58m)
├── Skin tone: #D4A574 - warm golden tan, sun-kissed
├── Face features (weathered but strong, round face)
├── Hair: #1A1A1A - soft matte black, gray-streaked in bun
├── Clothing: #3D2314 - deep dark chocolate brown áo bà ba
├── Pants: #1A1A1A - soft matte black loose pants
├── Footwear: #5D4037 - warm earthy brown slippers
├── Accessories: #FFD700 - rich metallic gold earrings, #00A86B - vivid jade green bracelet
└── Material/Style (realistic skin texture)
```

**🔴 CHARACTER IMAGE PROMPT BẮT BUỘC (v9.8):**
```
## 🖼️ CHARACTER IMAGE PROMPT

### Prompt tạo ảnh [Tên nhân vật]:
> Lưu ảnh thành: `Tên_nhân_vật.png`
[Prompt chi tiết style + body + HEX + expression + background]
```

> [!IMPORTANT]
> Mỗi nhân vật (chính + phụ) PHẢI có 1 prompt tạo ảnh riêng trong Bible.
> Prompt dùng để tạo ảnh tham chiếu với bất kỳ AI image generator nào.
> KHÔNG cần tạo ảnh trực tiếp — chỉ cần prompt sẵn trong Bible.

**❌ FORBIDDEN (trong Bible):**
```
❌ "gray-streaked black hair" (Bible thiếu HEX, Master/Prompts thiếu text chi tiết)
❌ "dark maroon áo bà ba" (Bible thiếu HEX code, mô tả quá chung)
❌ "simple slippers" (thiếu cả HEX trong Bible lẫn text description chi tiết)
```

**Output**: `XX_Bible.md` với HEX + Text Description + CHARACTER IMAGE PROMPT

---

### PHASE 4: MASTER SCRIPT 🔴 ONE-LINE FORMAT + BLANK LINE + MULTI-SEGMENT

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 🔴 4.1 | **Xác định GOLDEN SAMPLE format** | `02_Universal/04_Master_Format.md` | §12-30 "VÍ DỤ ĐÚNG" |
| 4.2 | Viết theo scene structure | Rule E5 | - |
| 🔴 4.2b | **BẮT BUỘC phân bổ segments (1-3) cho từng prompt** | `05_Prompts_Format.md` §MULTI-SEGMENT | Hook=2-3, Teaching=2-3, End=1 |
| 🔴 4.3 | **COPY-PASTE TOÀN BỘ Character Profile Lock vào MỌI scene** | `XX_Bible.md` + `05_Prompts_Format.md` §CHÌA KHÓA #1 | ⚠️ KHÔNG dùng "same character" |
| 🔴 4.3b | **Dùng Text Description (KHÔNG HEX)** | `XX_Bible.md` | Copy phần text description, bỏ #XXXXXX |
| 🔴 4.3c | **ANTI-DECAY: Verify MỌI field ở MỌI scene** | `05_Prompts_Format.md` §ANTI-DECAY | ⚠️ KHÔNG bỏ field nào từ scene 2 trở đi 🔴 NEW v9.8 |
| 4.4 | Apply setting descriptions | `XX_Bible.md` | Section Settings → COPY nguyên văn |
| 4.5 | Add audio specifications | `04_Master_Format.md` | "Audio of [sound]" |
| 4.6 | Add voice metadata | Rule E23 | "[Giọng: Vùng, Tuổi]" |
| 🔴 4.6b | **Viết thoại SÁNG TẠO theo tone đã chọn** | Bible (Dialogue Tone) + Personality | 🔴 KHÔNG copy catchphrase nguyên văn, ≥70% sáng tạo |
| 🔴 4.7 | **Check scene count** | _(Self-check)_ | **10-12 prompts ưu tiên** (min 8, KHÔNG mặc định 9) |
| 🔴 4.7b | **Thêm scenes linh hoạt** | _(Self-check)_ | Thêm Demo, Reaction, Warning, Practice scenes ngoài tips 🔴 NEW v9.7 |
| 🔴 4.8 | **Verify ONE-LINE + BLANK LINE format** | _(Self-check)_ | 1 dòng/scene, **1 blank line giữa mỗi prompt** 🔴 NEW v9.7 |
| 🔴 4.8b | **Verify MULTI-SEGMENT presence** | _(Self-check)_ | Ít nhất 3-5 prompts phải có `>>` (Hook, Teaching, Demo) 🔴 NEW v9.7 |
| 🔴 4.9 | **[ANTHROPOMORPHIC] Verify VIOLENCE SAFETY** | `Sensitive_Words.txt` §13 | Nhân vật KHÔNG bị nấu/cắt/đốt, ĐỨNG BÊN CẠNH quan sát 🔴 NEW v9.6 |

**🔴 BLANK LINE BẮT BUỘC (v9.7):**

> [!CAUTION]
> Mỗi prompt = 1 dòng. Giữa 2 prompt = **1 dòng trống** (enter 2 lần).
> KHÔNG viết các prompt dồn liền nhau. File Master và Prompts đều phải có blank line.

```
✅ ĐÚNG:
Hook scene [2 SEG]. SEG1: Wide shot... >> SEG2: Close-up... Audio... [Giọng:...] "Thoại..."

Problem scene. Close-up... Audio... [Giọng:...] "Thoại..."

Tip 1 scene [2 SEG]. SEG1: Medium shot... >> SEG2: Close-up... Audio... [Giọng:...] "Thoại..."

❌ SAI (dồn liền):
Hook scene. Medium shot... Audio... "Thoại..."
Problem scene. Close-up... Audio... "Thoại..."
Tip 1 scene. Medium shot... Audio... "Thoại..."
```

**🔴 MULTI-SEGMENT BẮT BUỘC (v9.7):**

> [!IMPORTANT]
> KHÔNG được viết 100% prompts chỉ có 1 segment.
> Ít nhất **3-5 prompts** trong mỗi project PHẢI dùng multi-segment `>>`.
> Hook, Teaching/Tips phức tạp, và Demo scenes nên ưu tiên 2-3 segments.

| Scene type | Segment yêu cầu | Lý do |
|------------|-----------------|--------|
| Hook | 🔴 2-3 seg BẮT BUỘC | Dynamic mở đầu, visual phong phú |
| Problem | 1-2 seg | Tùy mức phức tạp |
| Teaching/Tips | 🔴 2-3 seg khi demo nhiều bước | Cho thấy hành động rõ ràng |
| Demo/Practice | 🔴 2-3 seg | Quá trình liên tiếp |
| Result | 1-2 seg | Kết quả rõ |
| Hook-end | 1 seg | Kết gọn |

**🔴 PROMPT COUNT LINH HOẠT (v9.7):**

> [!WARNING]
> KHÔNG mặc định 9 prompts (Hook + Problem + 5 Tips + Result + Hook-end).
> Phải linh hoạt **10-12 prompts** bằng cách thêm các loại scene sau:

| Scene type bổ sung | Mô tả | Khi nào thêm |
|-------------------|-------|-------------|
| **Demo scene** | Thực hành, minh họa trực tiếp | Sau tips phức tạp |
| **Reaction scene** | Phản ứng cảm xúc nhân vật phụ | Giữa tips, tạo drama |
| **Warning scene** | Cảnh báo hậu quả, so sánh | Trước/sau solution |
| **Practice scene** | Con dâu thực hành theo hướng dẫn | Sau nhóm tips |
| **Comparison scene** | So sánh trước/sau, đúng/sai | Tăng visual variety |

**✅ GOLDEN SAMPLE FORMAT (v9.7):**

**1 segment (cho scenes đơn giản):**
```
Problem scene. Close-up, dolly in. Realistic Vietnamese family scene, cinematic lighting, warm color grading. Vietnamese kitchen. Hương, 28-year-old... apologetic expression, speaking softly. Audio of ambient. [Giọng: Miền Nam, 28 tuổi] "Thoại..."
```

**Multi-segment (cho Hook, Teaching, Demo — BẮT BUỘC dùng >>):**
```
Hook scene [2 SEG]. Realistic Vietnamese family scene, cinematic lighting, warm color grading. SEG1: Wide shot, dolly in. Vietnamese kitchen, Bà Tư, 58-year-old... stern expression, standing arms crossed. >> SEG2: Close-up, quick zoom. Bà Tư face, mouth open speaking firmly, pointing accusingly. Audio of dramatic ambient. [Giọng: Miền Bắc, 58 tuổi] "Thoại..."
```

> [!TIP]
> Multi-segment prompts vẫn là **1 dòng** trong Master. Dùng `>>` phân cách, KHÔNG xuống dòng.

**❌ FORBIDDEN FORMAT:**
```
❌ ---
❌ [CLIP 1] HOOK - Phát hiện
❌ Medium shot...
❌ ---
❌ Prompts dồn liền không blank line
❌ 100% prompts chỉ 1 segment
❌ Luôn cố định 9 prompts
❌ Scene 2+ thiếu face/pants/accessories so với scene 1
```

**🔴 ANTI-DECAY: TOÀN BỘ FIELDS Ở MỌI SCENE (v9.8):**

> [!CAUTION]
> Agent có xu hướng viết ĐẦY ĐỦ ở scene 1 (Hook), rồi **"decay" dần** — bỏ face, skin modifier,
> pants, accessories từ scene 2 trở đi. ĐẶC BIỆT nghiêm trọng khi nhân vật ở SEG2 hoặc background.
> Đây là vi phạm nghiêm trọng rule 4.3 — AI KHÔNG CÓ TRÍ NHỚ, thiếu field = nhân vật khác.

**MANDATORY FIELDS cho MỌI nhân vật ở MỌI scene (kể cả SEG2/background):**

```
┌─────────────────────────────────────────────────────────────┐
│ 8 FIELDS BẮT BUỘC — KHÔNG ĐƯỢC BỎ BẤT KỲ FIELD NÀO       │
├─────────────────────────────────────────────────────────────┤
│ 1. Age + Role     │ "58-year-old Vietnamese mother-in-law" │
│ 2. Height         │ "1.58m"                                │
│ 3. Skin + Detail  │ "warm caramel brown naturally           │
│                   │  weathered skin"                       │
│ 4. Face           │ "round face smile lines prominent      │
│                   │  cheekbones"                           │
│ 5. Hair           │ "deep charcoal black gray-streaked      │
│                   │  hair in bun"                          │
│ 6. Clothing top   │ "dark maroon áo bà ba"                 │
│ 7. Clothing bottom│ "deep matte charcoal black loose pants" │
│ 8. Accessories    │ "warm antique gold small earrings,      │
│                   │  sea green jade bracelet"               │
└─────────────────────────────────────────────────────────────┘
```

**SELF-CHECK: So sánh scene N vs scene 1 (Hook):**
```
 FOR EACH scene (2 → cuối):
   FOR EACH character xuất hiện:
     CHECK: age+role? ✅/❌
     CHECK: height?   ✅/❌
     CHECK: skin + modifier ("naturally weathered")?  ✅/❌
     CHECK: face features? ✅/❌
     CHECK: hair?     ✅/❌
     CHECK: clothing top? ✅/❌
     CHECK: pants/bottom? ✅/❌
     CHECK: accessories?  ✅/❌
     IF ANY ❌ → THÊM LẠI field đó, copy từ scene 1
```

**❌ SAI — Decay Pattern điển hình:**
```
Scene 1: Bà Tư, 58-year-old..., 1.58m, warm caramel brown naturally weathered skin,
         round face smile lines prominent cheekbones, deep charcoal black gray-streaked
         hair in bun, dark maroon áo bà ba, deep matte charcoal black loose pants,
         warm antique gold small earrings, sea green jade bracelet...

Scene 5: Bà Tư, 58-year-old..., 1.58m, warm caramel brown skin,     ← THIẾU "naturally weathered"
         deep charcoal black gray-streaked hair in bun,               ← THIẾU face
         dark maroon áo bà ba,                                       ← THIẾU pants
         warm antique gold small earrings, sea green jade bracelet...
```

**✅ ĐÚNG — Scene 5 PHẢI giống hệt scene 1:**
```
Scene 5: Bà Tư, 58-year-old..., 1.58m, warm caramel brown naturally weathered skin,
         round face smile lines prominent cheekbones, deep charcoal black gray-streaked
         hair in bun, dark maroon áo bà ba, deep matte charcoal black loose pants,
         warm antique gold small earrings, sea green jade bracelet...
```

> [!WARNING]
> **BACKGROUND/SEG2 KHÔNG PHẢI LÝ DO ĐỂ CẮT BỎ FIELDS.**
> Nhân vật ở SEG2, background, hoặc visible in corner vẫn PHẢI có đầy đủ 8 fields.
> AI render MỌI nhân vật visible trong frame — thiếu field = render sai.

**Output**: `XX_Master.txt` (1 line per scene, blank line between scenes, multi-segment với `>>`, anti-decay enforced)

---

### PHASE 5: PROMPTS EXTRACTION 🔴 NEGATIVE PROMPTS + SPEAKER EXPRESSION + BLANK LINE

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 5.1a | Đọc format cơ bản | `02_Universal/05_Prompts_Format.md` | §CẤU TRÚC PROMPT ĐẦY ĐỦ + §MULTI-SEGMENT |
| 🔴 5.1b | **Đọc CHARACTER LOCK SYSTEM** | `02_Universal/05_Prompts_Format.md` | §CHÌA KHÓA #1: CHARACTER PROFILE LOCK ⚠️ CRITICAL |
| 🔴 5.1c | **Đọc SPEAKER EXPRESSION SYSTEM** | `02_Universal/05_Prompts_Format.md` | §CHÌA KHÓA #2B: SPEAKER EXPRESSION 🔴 NEW v9.1 |
| 5.1d | Đọc HEX + Negative + Style | `02_Universal/05_Prompts_Format.md` | §CHÌA KHÓA #3 + §BẢNG TRA CỨU HEX→TEXT |
| 5.2 | Extract visual từ Master | `XX_Master.txt` | Lấy phần visual, bỏ dialogue |
| 🔴 5.2b | **Verify KHÔNG CÓ HEX trong Prompts** | _(Self-check)_ | Scan #XXXXXX → phải = 0, chỉ text description |
| 🔴 5.2c | **Verify Multi-Segment format** | _(Self-check)_ | `>>` đúng cú pháp, camera logic, max 3 seg, ≥3 prompts có `>>` 🔴 v9.7 |
| 🔴 5.2d | **Verify BLANK LINE giữa mỗi prompt** | _(Self-check)_ | 1 blank line giữa 2 prompts, KHÔNG dồn liền 🔴 NEW v9.7 |
| 5.3 | Check zero text policy | Rule E7 | - |
| 🔴 5.3b | **SCAN Text-Trigger Words** | `05_Prompts_Format.md` §E7 ZERO TEXT POLICY | ⚠️ Check: shows, displays, clock, timer, labeled |
| 5.4 | Add basic suffix | _(Self-add)_ | `no text, no subtitles, no labels, no watermarks` |
| 5.5 | Check prompt structure | Rule E28 | - |
| 5.6 | Camera enhance | `03_Advanced/01_Camera_Complete.md` | (Khuyến khích) |
| 🔴 5.7 | **[BẮT BUỘC] Add Negative Prompts** | `05_Prompts_Format.md` §NEGATIVE PROMPTS BẮT BUỘC | 6 items bắt buộc |
| 🔴 5.8 | **[BẮT BUỘC] Add SPEAKER INDICATORS** | `05_Prompts_Format.md` §BẢNG SPEAKING INDICATORS | Người NÓI + Người NGHE |
| 🔴 5.9 | **Verify Speaker = Dubbing match** | `XX_Dubbing.txt` vs Prompts | Ai nói → có speaking indicator |
| 🔴 5.10 | **Verify prompt count ≥ 10** | _(Self-check)_ | Nếu < 10 → thêm Demo/Reaction/Warning scenes 🔴 NEW v9.7 |

**🔴 BLANK LINE BẮT BUỘC trong Prompts (v9.7):**
```
✅ ĐÚNG:
Hook scene [2 SEG]. SEG1: Wide shot... >> SEG2: Close-up... Audio..., no text, no subtitles...

Problem scene. Close-up... Audio..., no text, no subtitles...

Tip 1 scene [2 SEG]. SEG1: Medium shot... >> SEG2: Close-up... Audio..., no text...

❌ SAI:
Hook scene. Medium shot... no text...
Problem scene. Close-up... no text...
Tip 1 scene. Medium shot... no text...
```

**🔴 SPEAKER EXPRESSION BẮT BUỘC (mỗi scene):**
```
✅ Người NÓI: "mouth open speaking firmly" / "speaking instructively" / "speaking softly"
✅ Người NGHE: "attentive listening expression" / "receiving criticism" / "nodding while listening"
```

**❌ THIẾU SPEAKER STATE:**
```
❌ "stern expression, pointing finger" → Chỉ có expression TĨNH, không có ĐANG NÓI
❌ "anxious expression, hands clasped" → Không rõ đang NGHE hay NÓI
```

**🔴 NEGATIVE PROMPTS BẮT BUỘC (thêm vào cuối MỌI prompt):**
```
, no deformed limbs, no mutated faces, no extra fingers, no melting geometry, no color shifts, no texture distortion
```

**⚠️ TEXT-TRIGGER BLACKLIST (KHÔNG được có trong prompt):**
```
❌ shows "X", displays X, clock showing, timer, counter
❌ label, labeled, tag, caption, sign reads
❌ poster, banner, button, menu, screen showing
```

**Output**: `XX_Prompts.txt` với Negative Prompts + Speaker Expression + Blank Lines

---

### PHASE 6: DUBBING EXTRACTION ⚠️ CÂU HỎI ẨN

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 6.1 | Xác định Dubbing format | `02_Universal/06_Dubbing_Format.md` | Toàn bộ |
| 6.2 | Extract dialogue từ Master | `XX_Master.txt` | Lấy phần trong dấu "" |
| 6.3 | Format voice metadata | Rule E23 | "[Giọng: Vùng, Tuổi]" |
| 🔴 6.4 | **Remove ký tự cấm + CÂU HỎI ẨN** | Rule E19 | Bỏ `? ! -` + "hả", "sao", "gì" cuối câu |
| 6.5 | Check độ dài câu | _(Self-check)_ | ≤20 từ/câu |
| 6.6 | Replace sensitive words | `Sensitive_Words.txt` | Thay thế theo bảng |

**⚠️ CÂU HỎI ẨN PATTERNS (CẤM):**
```
❌ "...bao giờ nữa hả."  → Từ "hả" = câu hỏi
❌ "...biết trả lời sao." → Từ "sao" = câu hỏi
❌ "...làm gì được."     → Từ "gì" = câu hỏi
```

**✅ FIX:**
```
✅ "...cứ như vậy thì ngày nào cũng mệt."
✅ "...con không biết phải làm thế nào."
```

**Output**: `XX_Dubbing.txt` không có câu hỏi ẩn

---

### PHASE 7: SEO CREATION ⚠️ ĐẦY ĐỦ SECTIONS

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 7.1 | Xác định SEO format | `02_Universal/07_SEO_Format.md` | Toàn bộ |
| ⚠️ 7.1b | **Add THÔNG TIN RESEARCH** | _(Self-write)_ | Ngày, Nguồn, Chủ đề chính |
| 7.2 | Research keywords | `01_Research/01_Trending_Keywords_2026.md` | - |
| 7.3 | Tạo 3 title variants | `02_Title_Bank_Tet_2026.md` | - |
| 7.4 | Check title rules | _(Self-check)_ | < 60 ký tự, hook 3 từ đầu |
| 7.5 | Check sensitive trong title | `Sensitive_Words.txt` | Không có từ cấm |
| 7.6 | Generate hashtags với view count | `03_SEO_Bank_Tet_2026.md` | TikTok (có XXM views) |
| 7.7 | Write description | _(Self-write)_ | 100-150 từ |
| ⚠️ 7.8 | **Add Disclaimer** | _(Self-add)_ | "⚠️ Disclaimer: Thông tin không thay thế tư vấn y khoa..." |
| ⚠️ 7.9 | **Add YouTube Tags** | _(Self-write)_ | < 500 ký tự |
| ⚠️ 7.10 | **Add Thumbnail Text** | _(Self-write)_ | 3-4 từ shock |

**Output**: `XX_SEO.txt` đầy đủ sections

---

### PHASE 8: QC (Quality Check) 🔴 EXPANDED CHECKLIST

| Step | Action | File cần đọc | Criteria |
|------|--------|-------------|----------|
| 8.1 | Load QC checklist | `02_Universal/03_Quality_Checklist.md` | Toàn bộ |
| 8.2 | Check files completeness | _(Self-verify)_ | 5 files exist |
| 8.3 | Verify voice format | `XX_Dubbing.txt` | "[Giọng: Vùng, Tuổi]" |
| 8.4 | Verify zero text suffix | `XX_Prompts.txt` | Có suffix "no text..." |
| 8.5 | Verify dialogue rules | `XX_Dubbing.txt` | Không `? ! -` |
| 8.6 | Verify sensitive words | All files | Không có từ cấm |
| 8.7 | Cross-file consistency | Bible vs Master vs Prompts | Characters, settings khớp |
| 🔴 8.8 | **Verify HEX colors** | Bible | Mọi màu có `#XXXXXX - text description` |
| 🔴 8.9 | **Verify Profile Lock completeness** | Prompts | Height, skin text, accessories đầy đủ MỌI scene |
| 🔴 8.9b | **ANTI-DECAY: So sánh scene 2+ vs scene 1** | Master + Prompts | 8 fields (age, height, skin+modifier, face, hair, top, bottom, accessories) PHẢI giống hệt scene 1 cho MỌI nhân vật ở MỌI scene kể cả SEG2/background 🔴 NEW v9.8 |
| 🔴 8.10 | **Verify Negative Prompts** | Prompts | 6 items: deformed, mutated, extra fingers, melting, color shifts, texture |
| 🔴 8.11 | **Verify Text-Triggers** | Prompts | No: shows, displays, clock, timer, labeled |
| 🔴 8.12 | **Verify câu hỏi ẩn** | Dubbing | No: hả, sao, gì cuối câu |
| 🔴 8.13 | **Verify Master format** | Master | 1 line/scene, no [CLIP], no --- |
| 🔴 8.13b | **Verify BLANK LINE** | Master + Prompts | 1 blank line giữa mỗi prompt, KHÔNG dồn liền 🔴 NEW v9.7 |
| 🔴 8.14 | **Verify SPEAKER indicators** | Prompts | Người NÓI có: speaking, mouth open, talking 🔴 NEW v9.1 |
| 🔴 8.15 | **Verify LISTENER expressions** | Prompts | Người NGHE có: listening, receiving, attentive 🔴 NEW v9.1 |
| 🔴 8.16 | **Verify Dialogue Tone** | Bible + Master + Dubbing | Tone nhất quán với thể loại đã chọn 🔴 NEW v9.4 |
| 🔴 8.17 | **Verify Dialogue Originality** | Master + Dubbing | ≥70% sáng tạo, ≤3 catchphrase, đã biến tấu 🔴 NEW v9.4 |
| 🔴 8.18 | **Verify Character Voice** | Master + Dubbing | Object có personality riêng, không generic 🔴 NEW v9.4 |
| 🔴 8.19 | **Verify NO HEX in Master/Prompts** | Master + Prompts | Không còn #XXXXXX, chỉ text description 🔴 NEW v9.4 |
| 🔴 8.20 | **Verify Multi-Segment ≥3 prompts** | Master + Prompts | `>>` có ≥3 prompts, max 3 seg, dialogue ≤20 từ/prompt 🔴 v9.7 |
| 🔴 8.20b | **Verify Prompt Count ≥ 10** | Master + Prompts | Không cố định 9, ưu tiên 10-12, có Demo/Reaction/Warning 🔴 NEW v9.7 |
| 🔴 8.21 | **[ANTHROPOMORPHIC] Verify VIOLENCE SAFETY** | Master + Prompts (VISUAL only) | Visual: nhân vật KHÔNG bị nấu/cắt/đốt, KHÔNG pained/tears/flailing. Dialogue OK 🔴 NEW v9.6 |

**🔴 ANTHROPOMORPHIC VIOLENCE SAFETY (v9.6):**

> [!CAUTION]
> Nhân vật nhân hóa (có mắt, miệng, cánh tay) = **SINH VẬT SỐNG**.
> Mô tả chúng bị nấu/cắt/đốt = **TRA TẤN** trong mắt AI platforms (Gemini, Veo, YouTube).

**SCAN cho từ khóa CẤM (CHỈ trong VISUAL — Master + Prompts):**
```
❌ Visual: pained grimace, tears forming, flailing helplessly, melting unevenly
❌ Visual: writhing, screaming, burning, dissolving, crumbling, being cooked
```

> ⚠️ Lời thoại (dialogue) KHÔNG bị hạn chế bởi rule này.

**✅ CÁCH LÀM ĐÚNG (Visual):**
```
✅ Nhân vật ĐỨNG BÊN CẠNH và QUAN SÁT hành vi sai
✅ Expression: annoyed frown, sigh bubble, arms crossed, head shake
```

**Output**: QC passed (ALL 21 items) / Issues list

---

### PHASE 9: FINALIZE & LEARNING

| Step | Action | File cần đọc | Section/Line |
|------|--------|-------------|--------------|
| 9.1 | Package deliverables | _(Self-package)_ | 5-6 files |
| 9.2 | Present to CHỦ | _(Notify)_ | Summary |
| 9.3 | Đánh giá template đã dùng | _(Self-evaluate)_ | Structure hiệu quả? |
| ~~9.4~~ | ~~Template creation~~ | _(ĐÃ LÀM Ở PHASE 0)_ | 🔴 MOVED TO PHASE 0 v9.3 |

**⚠️ NOTE v9.3**: Template creation đã di chuyển lên Phase 0 để hỗ trợ batch automation.

**Output**: Delivered (Template đã có từ Phase 0)

---

## 📁 OUTPUT STRUCTURE

```
[Project]/
├── XX_Bible.md        (với HEX colors)
├── XX_Master.txt      (1 line per scene)
├── XX_Prompts.txt     (với Negative Prompts)
├── XX_Prompts_Ref.txt (optional)
├── XX_Dubbing.txt     (không câu hỏi ẩn)
└── XX_SEO.txt         (đầy đủ sections)
```

---

## 📋 MASTER FILE REFERENCE

| File Path | Dùng trong Phase |
|-----------|------------------|
| `01_Research/01_Trending_Keywords_2026.md` | 0, 1, 7 |
| `01_Research/02_Title_Bank_Tet_2026.md` | 1, 7 |
| `01_Research/03_SEO_Bank_Tet_2026.md` | 1, 7 |
| `01_Research/Sensitive_Words.txt` | 1, 6, 7, 8 |
| `02_Universal/00_Core_Principles.md` | 2, 3 |
| `02_Universal/01_Technical_Rules.md` | 2, 3, 4, 5, 6, 8 |
| `02_Universal/02_File_Formats.md` | 2, 3 |
| `02_Universal/03_Quality_Checklist.md` | 8 |
| `02_Universal/04_Master_Format.md` | 4 🔴 |
| `02_Universal/05_Prompts_Format.md` | 3 🔴, 5 🔴 |
| `02_Universal/06_Dubbing_Format.md` | 6 |
| `02_Universal/07_SEO_Format.md` | 7 |
| `02_Universal/Templates/*.md` | 0, 2, 3 |
| `02_Universal/Templates/Fashion_Review_Silent.md` | 0, 2, 3 🔴 (Fashion Review) |
| `03_Advanced/01_Camera_Complete.md` | 5 |
| `03_Advanced/02_Negative_Prompts.md` | 5 🔴 (BẮT BUỘC) |

---

## ✅ QUICK COMPLIANCE CHECKLIST

Trước khi submit, verify:

- [ ] 🔴 Bible có HEX + Text description song song (`#XXXXXX - text`)
- [ ] 🔴 Master + Prompts KHÔNG có raw HEX — chỉ text description
- [ ] 🔴 Palette màu KHÁC project trước
- [ ] 🔴 Character Profile Lock đầy đủ ở MỌI scene (không "same character")
- [ ] 🔴 Master format: 1 dòng/scene, KHÔNG có [CLIP X], KHÔNG có ---
- [ ] 🔴 **BLANK LINE** giữa mỗi prompt (enter 2 lần) — Master + Prompts 🔴 NEW v9.7
- [ ] 🔴 **10-12 prompts ưu tiên** (KHÔNG mặc định 9), thêm Demo/Reaction/Warning scenes 🔴 NEW v9.7
- [ ] 🔴 **≥3 prompts có multi-segment `>>`** (Hook, Teaching, Demo BẮT BUỘC) 🔴 NEW v9.7
- [ ] 🔴 Dialogue ≤20 từ/prompt (bất kể số segments)
- [ ] 🔴 Prompts có Negative Prompts 6 items
- [ ] 🔴 Prompts không có Text-Triggers (shows, clock, labeled...)
- [ ] 🔴 Dubbing không có câu hỏi ẩn (hả, sao, gì)
- [ ] 🔴 **[ANTHROPOMORPHIC] Visual: nhân vật KHÔNG bị nấu/cắt/đốt** (v9.6)
- [ ] 🔴 **Visual: KHÔNG có** pained/tears/flailing/melting/burning (dialogue OK)
- [ ] ⚠️ SEO có đủ: Research Info, Disclaimer, Thumbnail Text

---

## 🔴 FASHION REVIEW SILENT — QUY TẮC RIÊNG (v9.9)

> [!IMPORTANT]
> Áp dụng KHI topic là **người thật review quần áo/trang phục** (KOL Daily Life → Unboxing → Try-on).
> Format: **Không voice**, tập trung biểu cảm khuôn mặt, thần thái, góc máy, pose.

### Đặc điểm khác biệt so với content thông thường:

| Yếu tố | Content thông thường | Fashion Review Silent |
|---------|--------------------|-----------------------|
| Voice/Dialogue | Có thoại, có dubbing | ❌ KHÔNG có voice |
| Dubbing file | Bắt buộc | ❌ KHÔNG cần |
| Bible structure | Character + Setting | **5 phần**: Bối cảnh, Before, Package, Outfit, After |
| Character Lock | 8 fields mọi scene | Before vs After: cùng profile, khác trạng thái |
| Output files | Bible, Master, Prompts, Dubbing, SEO | **Bible, Storyboard, Prompts, SEO, Checklist** |
| Cỡ cảnh | Wide/Medium/Close-up | **4 cấp**: Toàn/Trung/Cận/Siêu cận |
| Storyboard format | 1 line per scene | `[Phase] [Cỡ cảnh]. [Góc máy]. [Mô tả]. Audio.` |

### 🔴 QC BỔ SUNG cho Fashion Review:
- [ ] 🔴 Bible Phần 2 (Before) vs Phần 5 (After): chiều cao, da, mặt, dáng GIỐNG
- [ ] 🔴 Bible Phần 4: Mô tả ĐỦ items (áo + quần/váy + giày + phụ kiện)
- [ ] 🔴 Bible Phần 3: Có mô tả bao bì + cảm quan mở hộp
- [ ] 🔴 Storyboard có ĐỦ 4 cỡ cảnh (Toàn/Trung/Cận/Siêu cận)
- [ ] 🔴 Mỗi shot lặp lại Character Profile Lock (KHÔNG viết "same girl")
- [ ] 🔴 KHÔNG có Dubbing file (format silent, no voice)
- [ ] 🔴 Có contrast rõ Before (daily life, bù xù) vs After (glow up, tự tin)
- [ ] ⚠️ ASMR audio cues: tiếng xé bao, vải, zip (trong Storyboard)

### Template: `02_Universal/Templates/Fashion_Review_Silent.md`

---

*Workflow v9.9 (Fashion Review Silent + Daily Life Format Edition) - 2026-03-03*
