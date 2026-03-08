# 📚 VEO 3 PRODUCTION - CORE PRINCIPLES

> **Cô đọng từ 29 files trong 00_System thành 1 hệ thống quy tắc thống nhất**  
> **Version**: 1.0  
> **Date**: 2026-02-05  
> **Total Rules**: 32+ E-Rules | 2 Modes | 5 Output Files

---

## 📋 MỤC LỤC

1. [Hai Mode Sản Xuất](#1-hai-mode-sản-xuất)
2. [32 Quy Tắc E-Rules](#2-32-quy-tắc-e-rules)
3. [5 Files Output](#3-5-files-output)
4. [Công Thức Viết Prompt](#4-công-thức-viết-prompt)
5. [Hệ Thống Camera](#5-hệ-thống-camera)
6. [Hệ Thống Nhân Vật](#6-hệ-thống-nhân-vật)
7. [Hệ Thống Voice](#7-hệ-thống-voice)
8. [Quality Checklist](#8-quality-checklist)

---

# 1. HAI MODE SẢN XUẤT

## Mode A: HEALTH (Giáo dục Sức khỏe)

| Đặc điểm | Giá trị |
|----------|---------|
| **Cấu trúc** | PMCS (Problem → Mechanism → Consequence → Solution) |
| **Visual Style** | 3D cute animation, Pixar render |
| **Nhân vật** | Anthropomorphic + Chủ thể người + Expert |
| **Mục đích** | Giáo dục, cảnh báo sức khỏe |
| **Template** | `02_Bible_Template.md` |

### Cấu trúc PMCS (9 Clips):

```
┌─────────────────────────────────────────────────────────┐
│  P (PROBLEM) - Clips 1-2                                │
│  Hook gây sốc, gợi tò mò                                │
│  Câu hỏi: "Điều gì đang xảy ra?"                        │
├─────────────────────────────────────────────────────────┤
│  M (MECHANISM) - Clips 3-5                              │
│  Cơ chế khoa học, số liệu                               │
│  Trả lời: "Tại sao nó nguy hiểm?"                       │
├─────────────────────────────────────────────────────────┤
│  C (CONSEQUENCE) - Clip 6                               │
│  Hậu quả HIỂN THỊ TRÊN CHỦ THỂ NGƯỜI                    │
│  ⚠️ BẮT BUỘC: Split screen hoặc visual trên người       │
├─────────────────────────────────────────────────────────┤
│  S (SOLUTION) - Clips 7-9                               │
│  Expert đưa giải pháp cụ thể                            │
│  Kết thúc tích cực, khán giả biết cách xử lý            │
└─────────────────────────────────────────────────────────┘
```

---

## Mode B: ENTERTAINMENT (Giải trí)

| Đặc điểm | Giá trị |
|----------|---------|
| **Cấu trúc** | 3-Act (Setup → Confrontation → Resolution) |
| **Visual Style** | Tùy genre (Cartoon, Realistic, Anime) |
| **Nhân vật** | Hero/Villain archetype |
| **Mục đích** | Giải trí, kể chuyện |
| **Template** | `04_Entertainment_Template.md` |

### Cấu trúc 3-Act:

```
┌─────────────────────────────────────────────────────────┐
│  ACT 1 - SETUP (25% thời lượng)                         │
│  • Opening Image (Đối lập Final Image)                  │
│  • Giới thiệu nhân vật, thế giới                        │
│  • Inciting Incident (Sự kiện kích hoạt)                │
├─────────────────────────────────────────────────────────┤
│  ACT 2 - CONFRONTATION (50% thời lượng)                 │
│  • Rising Complications                                  │
│  • Midpoint (Bước ngoặt giữa)                           │
│  • All Is Lost (Điểm đen tối nhất)                      │
├─────────────────────────────────────────────────────────┤
│  ACT 3 - RESOLUTION (25% thời lượng)                    │
│  • Climax (Cao trào)                                    │
│  • Resolution (Giải quyết xung đột)                     │
│  • Final Image (Đối lập Opening)                        │
└─────────────────────────────────────────────────────────┘
```

---

## Mode C: MẸ CHỒNG (Vietnamese Family Drama)

| Đặc điểm | Giá trị |
|----------|---------|
| **Cấu trúc** | Conflict → Tips → Success |
| **Visual Style** | Realistic Vietnamese |
| **Nhân vật** | Mẹ chồng (Authority) + Nàng dâu (Learner) |
| **Template** | `10_MeChong_NangDau_Template.md` |

---

# 2. 32 QUY TẮC E-RULES

## Nhóm A: NGÔN NGỮ & XƯNG HÔ

| Rule | Tên | Mô tả | ✅ Đúng | ❌ Sai |
|------|-----|-------|---------|--------|
| **E1** | No Invented Names | Không bịa tên nhân vật | "chị ơi", "bà chủ ơi" | "chị Lan ơi" |
| **E2** | Science-First | Mỗi clip ≥1 fact khoa học | Có số liệu | Không có fact |
| **E3** | Unique Knowledge | Mỗi NV đóng góp kiến thức riêng | NV có vai trò rõ | NV lặp lại thông tin |

## Nhóm B: CẤU TRÚC & LOGIC

| Rule | Tên | Mô tả | ✅ Đúng | ❌ Sai |
|------|-----|-------|---------|--------|
| **E4** | PMCS Structure | Tuân thủ P→M→C→S | Đủ 4 phase | Thiếu phase |
| **E5** | Logic Consistency | Thoại khớp hành động | "Đi bộ" + thoại về đi | "Đi bộ" + thoại về đứng yên |
| **E6** | Scene Transition | Mô tả chuyển cảnh | "Camera zooms out..." | Cắt đột ngột |

## Nhóm C: VISUAL PROMPT

| Rule | Tên | Mô tả | ✅ Đúng | ❌ Sai |
|------|-----|-------|---------|--------|
| **E7** | Zero Text | KHÔNG số/chữ trong visual | "needle in red zone" | "180mg/dL" |
| **E8** | Full Description | Mô tả đầy đủ TẤT CẢ NV | Tuổi, trang phục, biểu cảm | "Mom and Doctor" |
| **E9** | Visual Style Prefix | Style đầu mỗi prompt | "The 3D cute animation..." | Không có prefix |

## Nhóm D: SENSITIVE CONTENT

| Rule | Tên | Mô tả | ✅ Đúng | ❌ Sai |
|------|-----|-------|---------|--------|
| **E10** | Extreme Zoom | Không zoom cận khuyết điểm | Wide shot của người | Zoom cận mụn, mỡ |
| **E11** | Sensitive Words | Tra 05_Sensitive_Words | "tiêu diệt", "nguy kịch" | "giết", "chết" |

## Nhóm E: NHÂN VẬT

| Rule | Tên | Mô tả | ✅ Đúng | ❌ Sai |
|------|-----|-------|---------|--------|
| **E12** | Simple Face | Anthropomorphic đơn giản | "dot eyes, curved mouth" | Complex face |
| **E13** | Title Hook | Hook trong 3 từ đầu | "5 SAI LẦM..." | Tiêu đề dài dòng |
| **E14** | Visible Impact | Hậu quả nhìn thấy được | "stress cracks spreading" | "damage increases" |
| **E15** | Consequence on Human | Hậu quả trên CHỦ THỂ NGƯỜI | Split screen, triệu chứng | Chỉ nói không show |
| **E16** | Cross-Check | Đồng bộ giữa các files | Bible = Master = Dubbing | Mâu thuẫn giữa files |
| **E17** | Expert Standardized | Bác sĩ format chuẩn | Female, 35s, professional | Random expert |
| **E18** | Voice Consistency | Cùng NV = Cùng voice | Giữ nguyên voice | Thay đổi voice |

## Nhóm F: TTS & DIALOGUE

| Rule | Tên | Mô tả | ✅ Đúng | ❌ Sai |
|------|-----|-------|---------|--------|
| **E19** | Strict TTS | Không !, ?, - | "Lý do là vì..." | "Sao lại thế?" |
| **E20** | AI Labeling | Đánh dấu AI content | ✓ "AI-generated" | Không đánh dấu |
| **E21** | Medical Disclaimer | Miễn trừ y tế | Có disclaimer | Không có |
| **E22** | Personal Attributes | Không zoom khuyết điểm | Respectful framing | Zoom vào mụn |
| **E23** | Cinematic Keywords | Từ khóa điện ảnh | "slow dolly in" | "camera moves" |
| **E24** | Impact Dialogue | Không câu sáo rỗng | Số liệu cụ thể | "rất nguy hiểm" |
| **E25** | Pronoun Matching | Xưng hô đúng vai | Villain: "ta/bọn ta" | Villain: "tôi" |
| **E26** | Vague Language | Không mơ hồ | "44% nguy cơ" | "nguy hiểm lắm" |

## Nhóm G: RETENTION & VIRAL

| Rule | Tên | Mô tả | ✅ Đúng | ❌ Sai |
|------|-----|-------|---------|--------|
| **E27** | 8-Second Rule | Max 24 từ/clip | ≤24 từ | >30 từ |
| **E28** | Camera Keywords | Từ khóa camera | "tracking shot" | "camera follows" |
| **E29** | Retention Pacing | Đổi góc mỗi 3-5s | Varied shots | Static camera |
| **E30** | First Appearance | NV mới phải xưng tên | "Tôi là Gan đây!" | "Đau quá!" |
| **E31** | Seamless Stitching | Nối clip liền mạch | End-Start matching | Jump cut |
| **E32** | Viral Hook Quartet | 4 loại hook | Visual+Voice+Dialogue+SFX | Chỉ 1 loại |

---

# 3. 5 FILES OUTPUT

## 📁 Delivery Package

```
📁 XX_Topic_Name/
├── XX_Bible.md      ← Character + Setting design
├── XX_Master.txt    ← Golden Sample script
├── XX_Prompts.txt   ← Clean visual prompts
├── XX_Dubbing.txt   ← Voice script
└── XX_SEO.txt       ← Title, tags, description
```

## File Details

### 1. Bible.md

```markdown
# [TOPIC] - CHARACTER & SETTING BIBLE

## 1. Thông Tin Khoa Học
- Nguồn: [WHO/CDC/Bộ Y tế]
- Số liệu: [5-7 con số + nguồn]

## 2. Nhân Vật (COPY-PASTE vào Master)
### Nhân vật chính: [TÊN]
- Mô tả: [...]
- Voice: [Giọng: Vùng, Tuổi]

## 3. Bối Cảnh (COPY-PASTE vào Master)
[...]

## 4. Cấu Trúc PMCS
[...]
```

### 2. Master.txt

**Format mỗi dòng:**
```
[Scene type]. [Shot type]. [Visual Style prefix]. [Setting]. 
[Character description + action + expression]. 
Audio [sound]. [Giọng: Vùng, Tuổi] "Thoại."
```

### 3. Prompts.txt

```
The 3D cute animation style, Pixar render, [setting]. [Character description + action]. 
no text, no subtitles, no labels, no watermarks.
```

### 4. Dubbing.txt

```
[CLIP N]
[Character: Tên] [Giọng: Vùng, Tuổi]
"Nội dung thoại."
```

### 5. SEO.txt

```
## TITLE OPTIONS
A: [Số liệu + Kết quả sốc]
B: [Fear-based hook]
C: [Listicle format]

## DESCRIPTION
[...]

## HASHTAGS
#sứckhỏe #veo3 #animation
```

---

# 4. CÔNG THỨC VIẾT PROMPT

## 5 Trụ Cột (5 Pillars)

```
┌─────────────────────────────────────────────────────────┐
│  PROMPT = SUBJECT + CONTEXT + ACTION + CAMERA + STYLE   │
└─────────────────────────────────────────────────────────┘
```

| # | Pillar | Câu hỏi | Ví dụ |
|---|--------|---------|-------|
| 1 | **SUBJECT** | Ai/cái gì là trung tâm? | "A young woman", "An anthropomorphic liver" |
| 2 | **CONTEXT** | Ở đâu? Khi nào? | "Vietnamese kitchen, morning light" |
| 3 | **ACTION** | Đang làm gì? | "looking worried, holding stomach" |
| 4 | **CAMERA** | Camera thế nào? | "Close-up, slow dolly-in" |
| 5 | **STYLE** | Phong cách gì? | "3D cute animation, Pixar render" |

## Template Prompt Chuẩn

```
[Camera], [Style prefix]. [Context/Setting]. 
[Subject full description] [Action + Expression]. 
Audio of [sound]. 
no text, no subtitles, no labels, no watermarks.
```

## Negative Prompts (Luôn thêm)

```
no text, no subtitles, no labels, no watermarks, no UI elements,
no distorted face, no weird hands, no morphing, no flicker.
```

---

# 5. HỆ THỐNG CAMERA

## 6 Cỡ Cảnh (Shot Size)

| Shot | Khung hình | Tập trung | Khi dùng |
|------|------------|-----------|----------|
| **EWS** (Extreme Wide) | NV rất nhỏ | Bối cảnh | Opening, establishing |
| **WS** (Wide) | Toàn thân + bối cảnh | Hành động | Action, chase |
| **MS** (Medium) | Thắt lưng trở lên | Đối thoại | Conversation |
| **MCU** (Medium Close-up) | Vai trở lên | Emotion + context | Reaction |
| **CU** (Close-up) | Mặt | Cảm xúc mãnh liệt | Climax |
| **ECU** (Extreme Close-up) | Mắt/miệng | Chi tiết micro | Dramatic moment |

## 4 Góc Máy (Camera Angle)

| Góc | Hiệu ứng | Prompt |
|-----|----------|--------|
| **Eye-level** | Trung lập, gần gũi | `eye-level shot` |
| **Low angle** | Quyền lực, mạnh mẽ | `low angle, looking up at` |
| **High angle** | Yếu đuối, bị áp lực | `high angle, looking down at` |
| **Dutch angle** | Bất ổn, căng thẳng | `dutch angle, tilted frame` |

## 4 Camera Plays

| Play | Prompt | Hiệu ứng |
|------|--------|----------|
| **Push-in** | `slow push-in toward` | Tập trung cảm xúc |
| **Orbit** | `smooth 90-degree orbit around` | Epic, impressive |
| **Crane** | `crane up/down` | Reveal bối cảnh |
| **Handheld** | `subtle handheld shake 3-5%` | Chân thực, documentary |

---

# 6. HỆ THỐNG NHÂN VẬT

## Anthropomorphic Template

```
An anthropomorphic [màu] [hình dạng], [kích thước],
with simple dot eyes showing [biểu cảm], 
curved [kiểu] mouth, [chi tiết đặc trưng],
[hành động], [visual cue: mồ hôi/khói/ánh sáng]
```

## Human Character Template

```
A [tuổi] Asian [giới tính], [age]s, [body type],
wearing [trang phục chi tiết],
[biểu cảm] expression, [hành động]
```

## Xưng Hô Theo Vai Trò

| Vai | Xưng | Hô | Tone |
|-----|------|-----|------|
| **Hero** (Bác sĩ) | tôi, mình | anh/chị, bạn | Thân thiện, hướng dẫn |
| **Villain** (Vi khuẩn, Mỡ) | ta, bọn ta | mày, ngươi | Đắc thắng, đe dọa |
| **Victim** (Nội tạng) | tôi, tui | bà chủ, ông chủ | Mệt mỏi, cầu cứu |
| **Narrator** | - | - | Cảnh báo, giáo dục |

## 3-Layer Expression Method

| Layer | Tên | Mô tả | Ví dụ |
|-------|-----|-------|-------|
| **1** | Expression | Nhãn cảm xúc | "subtle sadness", "contained anger" |
| **2** | Micro-action | Chuyển động nhỏ | "lips tremble", "jaw tightens" |
| **3** | Eyes | Ánh mắt | "eyes dart left-right", "tears well up" |

---

# 7. HỆ THỐNG VOICE

## Format Voice Metadata (2026)

```
[Giọng: Vùng, Tuổi]
```

| Vùng | Đặc điểm | Dùng cho |
|------|----------|----------|
| **Miền Bắc** | Chuẩn, formal | Narrator, Expert |
| **Miền Nam** | Thân thiện, nhẹ nhàng | Villain, thường |
| **Miền Tây** | Ấm áp, chân chất | Victim, nội tạng |
| **Miền Trung** | Đặc trưng | Nhân vật đặc biệt |

## Expression trong Visual

> **Giới tính**: Xác định trong Bible → Copy-paste  
> **Tone/Cảm xúc**: Mô tả trong prompt visual

| Cảm xúc | Mô tả Visual |
|---------|--------------|
| Lo lắng | "worried expression, furrowed brow" |
| Đau đớn | "pained expression, grimacing" |
| Đắc thắng | "evil grin, triumphant expression" |
| Cười ác | "villainous grin, menacing smile" |
| Kiệt sức | "exhausted expression, drooping" |

## Quy Tắc 8 Giây

| Tone | Tốc độ | Max từ |
|------|--------|--------|
| Hào hứng | 4 từ/s | 32 từ |
| Bình thường | 3 từ/s | 24 từ |
| Nghiêm túc | 2.5 từ/s | 20 từ |

---

# 8. QUALITY CHECKLIST

## ✅ Phase 1: Research
- [ ] Có nguồn khoa học (WHO/CDC/Bộ Y tế)
- [ ] Có 5-7 số liệu chính
- [ ] Xác định Mode (A/B/C)

## ✅ Phase 2: Bible
- [ ] Nhân vật có mô tả COPY-PASTE
- [ ] Bối cảnh có mô tả COPY-PASTE
- [ ] Voice metadata format mới
- [ ] Cấu trúc PMCS/3-Act rõ ràng

## ✅ Phase 3: Master
- [ ] Mỗi dòng đủ: Scene + Shot + Style + Setting + Character + Audio + Voice + Dialogue
- [ ] Không có !, ?, - trong thoại
- [ ] ≤24 từ/thoại
- [ ] Logic nhất quán

## ✅ Phase 4: Prompts
- [ ] Có Style prefix
- [ ] Không có text/number
- [ ] Có negative suffix: `no text, no subtitles, no labels, no watermarks`
- [ ] Mô tả đầy đủ TẤT CẢ nhân vật

## ✅ Phase 5: Dubbing
- [ ] Format: [CLIP N] + [Character] + [Giọng] + "Thoại"
- [ ] Số clip = số scene trong Master
- [ ] Không từ nhạy cảm

## ✅ Phase 6: SEO
- [ ] 3 tiêu đề A/B/C
- [ ] Hook trong 3 từ đầu
- [ ] Không từ nhạy cảm

## ✅ Phase 7: Cross-Check
- [ ] Bible = Master = Dubbing = SEO
- [ ] Không mâu thuẫn giữa files
- [ ] Voice nhất quán cho cùng nhân vật

---

# 🔗 QUICK REFERENCE

## 7 Điều Cấm Kỵ

1. ❌ Số cụ thể trong visual: `"180mg/dL"`
2. ❌ Timer/Counter: `"30 minutes"`, `"+40%"`
3. ❌ Labels: `"DANGER ZONE 4-60°C"`
4. ❌ Tên bịa đặt: `"chị Lan"`
5. ❌ Dấu `?`, `!`, `-` trong thoại
6. ❌ Từ cam kết: `"Trị dứt điểm"`, `"Cam kết khỏi"`
7. ❌ Từ nhạy cảm: `"chết"`, `"giết"`, `"tử vong"`

## Viral Hook Quartet (3s Đầu)

| Loại | Kỹ thuật |
|------|----------|
| **VISUAL** | Breaking 4th wall, Reverse motion, Macro reveal |
| **VOICE** | Whisper, Glitch (vấp), Fast pacing |
| **DIALOGUE** | "Đừng bao giờ...", "Sự thật về...", "Đố bạn..." |
| **SFX** | Snap (búng tay), Silence cut, ASMR |

## Chuyển Cảnh

1. **Zoom Out → Pan**: Từ A → zoom out → thấy B
2. **Match Cut**: Hình dạng tương đồng
3. **Whip Pan**: Camera xoay nhanh
4. **Follow the Flow**: Theo dòng máu/dây dẫn

---

*Core Principles v1.0 - Consolidated from 00_System - 2026-02-05*
