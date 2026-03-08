# ✅ QUALITY CHECKLIST - Kiểm Tra Chất Lượng

**Áp dụng**: MỌI dự án trước khi bàn giao  
**Bắt buộc**: Pass ALL items

---

## 📋 FILES COMPLETENESS

- [ ] `XX_Bible.md` tồn tại và đầy đủ sections
- [ ] `XX_Master.txt` có **8-12** scenes (linh hoạt theo chủ đề)
- [ ] `XX_Prompts.txt` số clip = số scene trong Master
- [ ] `XX_Dubbing.txt` số clip = số scene trong Master
- [ ] `XX_SEO.txt` có đủ 3 tiêu đề + hashtags

---

## 🔒 TECHNICAL RULES (Universal)

### Voice Format
- [ ] Format: `[Giọng: Vùng, Tuổi]`
- [ ] Vùng: Miền Bắc / Miền Nam / Miền Trung / Miền Tây
- [ ] Tuổi: XX tuổi (số cụ thể)
- [ ] KHÔNG dùng format cũ `[Region: ...] [Gender: ...]`

### Zero Text Policy (E7)
- [ ] Mọi prompt kết thúc: `no text, no subtitles, no labels, no watermarks`
- [ ] KHÔNG có text trong dấu ngoặc kép trong visual
- [ ] KHÔNG có labels, signs, posters trong visual
- [ ] KHÔNG có số liệu trong visual (chỉ trong dialogue)

### Dialogue Rules (E19)
- [ ] KHÔNG dùng `?` (dấu hỏi)
- [ ] KHÔNG dùng `!` (thay bằng `.`)
- [ ] KHÔNG dùng `-` trong từ (a-xít → a xít)
- [ ] Mỗi câu ≤ 20 từ tiếng Việt
- [ ] KHÔNG câu cụt < 5 chữ

### Sensitive Words (E11, E28)
- [ ] Check với `01_Research/Sensitive_Words.txt`
- [ ] KHÔNG: chết, tử vong, giết
- [ ] THAY: hẹo, tiêu đời, tiêu diệt

### Visual Style
- [ ] Visual style nhất quán trong MỌI prompt (Pixar / Realistic / Whimsical / etc.)
- [ ] Consistent across ALL prompts

---

## 🔄 CROSS-FILE CONSISTENCY

### Characters
- [ ] Mô tả nhân vật BIBLE = MASTER = PROMPTS
- [ ] Copy-paste chính xác, KHÔNG paraphrase
- [ ] Tuổi nhất quán

### Settings
- [ ] Mô tả bối cảnh nhất quán
- [ ] Ánh sáng, màu sắc consistent

### Dialogue
- [ ] Master dialogue = Dubbing dialogue
- [ ] Voice metadata khớp với character

### Dialogue Originality & Tone
- [ ] Tone đã được chọn trong Bible (Thể loại + Cấp độ)
- [ ] Dialogue nhất quán với tone đã chọn
- [ ] Nhân vật có personality/cách nói RIÊNG (không generic)
- [ ] ≤ 2-3 catchphrase từ ngân hàng, đã biến tấu
- [ ] ≥70% câu thoại sáng tạo theo ngữ cảnh
- [ ] KHÔNG cùng sentence pattern ở cùng vị trí clip với project khác

### Color Description
- [ ] Bible có HEX + Text description cạnh nhau (`#XXXXXX - text`)
- [ ] Master KHÔNG có raw HEX — chỉ text description
- [ ] Prompts KHÔNG có raw HEX — chỉ text description
- [ ] Text description đủ chi tiết (intensity + hue + base color)
- [ ] Palette màu KHÁC với project trước (không dùng lại bộ HEX cũ)

---

## 📊 SCENE COUNT

- [ ] Tổng **8-12** prompts (linh hoạt theo chủ đề)
- [ ] Opening: 1-2 scenes
- [ ] Development: 4-7 scenes
- [ ] Climax: 2-3 scenes
- [ ] Ending: 1-2 scenes

### Multi-Segment
- [ ] Mỗi prompt max 3 segments (dùng `>>` phân cách)
- [ ] Dialogue ≤20 từ per prompt (bất kể số segments)
- [ ] Camera logic giữa segments (wide→close hoặc close→reveal)
- [ ] Character Lock nhất quán giữa segments
- [ ] Segments phân bổ hợp lý (hook=2-3, result=1-2)

---

## 🎯 SEO CHECK

- [ ] 3 tiêu đề A/B/C (hook trong 3 từ đầu)
- [ ] Tiêu đề < 60 ký tự
- [ ] Hashtags TikTok (có view count nếu research được)
- [ ] Hashtags YouTube
- [ ] Keywords Primary/Secondary/Long-tail
- [ ] KHÔNG từ nhạy cảm trong tiêu đề

---

## 🔴 ANTHROPOMORPHIC VIOLENCE SAFETY

> [!CAUTION]
> Nhân vật nhân hóa (có mắt, miệng, cánh tay) = SINH VẬT SỐNG.
> Mô tả chúng bị nấu/cắt/đốt = TRA TẤN trong mắt AI platforms.

- [ ] 🔴 Visual: Nhân vật nhân hóa KHÔNG BỊ mô tả bỏ vào lò/microwave/nước sôi
- [ ] 🔴 Visual: KHÔNG có `pained grimace`, `tears`, `flailing helplessly`, `melting`
- [ ] 🔴 Visual: KHÔNG có `writhing`, `screaming`, `burning`, `dissolving`
- [ ] 🔴 Visual: Nhân vật ĐỨNG BÊN CẠNH quan sát, KHÔNG bị xử lý nhiệt/vật lý
- [ ] 🔴 Visual: Dùng expression AN TOÀN: `annoyed frown`, `sigh`, `arms crossed`, `head shake`
- [ ] ⚠️ Lời thoại (dialogue) KHÔNG bị hạn chế bởi rule này

---

## ✅ FINAL SIGN-OFF

- [ ] Tất cả items trên đã PASS
- [ ] Ready to deliver

---

*Quality Checklist v1.1 - 2026-02-07*
