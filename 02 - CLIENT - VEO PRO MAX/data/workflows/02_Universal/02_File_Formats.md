# 📄 FILE FORMATS - 5 Output Files Chuẩn

**Áp dụng**: MỌI chủ đề, MỌI thể loại  
**Bắt buộc**: Tạo đủ 5 files theo format dưới đây

---

## 📋 TỔNG QUAN

| # | File | Format | Nội dung |
|---|------|--------|----------|
| 1 | `XX_Bible.md` | Markdown | Concept, characters, settings |
| 2 | `XX_Master.txt` | Text | Full script với visual + dialogue |
| 3 | `XX_Prompts.txt` | Text | Visual prompts only (no dialogue) |
| 4 | `XX_Dubbing.txt` | Text | Dialogue only (with voice metadata) |
| 5 | `XX_SEO.txt` | Text | Titles, hashtags, keywords |

---

## 1️⃣ BIBLE.MD FORMAT

```markdown
# [Tên Dự Án] - Bible

## 1. Concept
- Thể loại: [Action/Comedy/Drama/Educational/...]
- Target audience: [Mô tả]
- Tone: [Vui nhộn/Nghiêm túc/Hài hước/...]
- Duration: ~60 seconds

## 2. Characters
### [Tên nhân vật 1]
- Ngoại hình: [Mô tả chi tiết từ đầu đến chân]
- Tuổi: [XX years old]
- Tính cách: [Mô tả]
- Vai trò: [Hero/Villain/Sidekick/...]

### [Tên nhân vật 2]
...

## 3. Settings
### [Tên bối cảnh 1]
- Mô tả: [Chi tiết environment]
- Ánh sáng: [Lighting style]
- Màu sắc: [Color palette]

## 4. Visual Style
The 3D cute animation style, Pixar render, [thêm đặc điểm riêng]

## 5. Story Structure
- Opening: [Hook]
- Development: [Các sự kiện chính]
- Climax: [Cao trào]
- Ending: [Kết thúc]
```

---

## 2️⃣ MASTER.TXT FORMAT

```
[Scene type]. [Shot type]. [Visual Style]. [Setting]. [Character description + action]. Audio [sound]. (Voice metadata) "Dialogue"

Ví dụ:
Opening scene. Medium shot. The 3D cute animation style, Pixar render. City street. A young superhero, 25 years old, wearing red cape, landing heroically, dust rising. Audio of wind whoosh. (Giọng: Miền Bắc, 25 tuổi) "Ta đã đến để bảo vệ thành phố này."
```

### Checklist mỗi dòng:
- ✅ Scene type (Opening/Development/Climax/Ending)
- ✅ Shot type (Medium/Close-up/Wide/etc.)
- ✅ Visual style prefix
- ✅ Setting
- ✅ Character + action
- ✅ Audio/Sound
- ✅ Voice metadata: `(Giọng: Vùng, Tuổi)`
- ✅ Dialogue

---

## 3️⃣ PROMPTS.TXT FORMAT

```
(CLIP 1)
[Visual description only, no dialogue]
no text, no subtitles, no labels, no watermarks

(CLIP 2)
...
```

### Rules:
- ❌ KHÔNG có dialogue, quotes, text
- ❌ KHÔNG có số liệu trong visual
- ✅ KẾT THÚC: `no text, no subtitles, no labels, no watermarks`

---

## 4️⃣ DUBBING.TXT FORMAT

```
(CLIP 1)
(Character: Tên Nhân Vật) (Giọng: Vùng, Tuổi)
"Nội dung lời thoại."

(CLIP 2)
...
```

### Rules:
- ❌ KHÔNG dùng `?` (dấu hỏi)
- ❌ KHÔNG dùng `!` (dấu chấm than) → thay `.`
- ❌ KHÔNG dùng `-` trong từ (a-xít → a xít)
- ✅ Mỗi câu ≤ 20 từ tiếng Việt

---

## 5️⃣ SEO.TXT FORMAT

```
# [Tên Dự Án] - SEO

## Tiêu đề
A: [Tiêu đề option A]
B: [Tiêu đề option B]
C: [Tiêu đề option C]

## Description
[Mô tả video 100-150 từ]

## Hashtags
### TikTok
#hashtag1 #hashtag2 ...

### YouTube
#hashtag1 #hashtag2 ...

### Facebook
#hashtag1 #hashtag2 ...

## Keywords
- Primary: [keyword 1], [keyword 2]
- Secondary: [keyword 3], [keyword 4]
- Long-tail: [keyword phrase 1], [keyword phrase 2]
```

---

*File Formats v1.0 - 2026-02-05*
