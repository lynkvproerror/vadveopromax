# PRODUCTION CHECKLIST - QUY TRÌNH SẢN XUẤT HOÀN CHỈNH
## Kiểm tra bắt buộc TRƯỚC và SAU khi tạo content
## ⚠️ PHẢI ĐỌC TEMPLATE VÀ INPUT FILES TRƯỚC KHI VIẾT!

---

## 📋 PHASE 0: CHỌN CHẾ ĐỘ (MODE SELECTION) - LÀM ĐẦU TIÊN

> [!IMPORTANT]
> Xác định loại nội dung TRƯỚC KHI bắt đầu bất kỳ công việc nào

### Chọn 1 trong 2:
- [ ] **MODE A: HEALTH EDUCATION** → Áp dụng cấu trúc **PMCS**, bắt buộc có **Chủ Thể** và **Chuyên gia**
- [ ] **MODE B: ENTERTAINMENT** → Áp dụng cấu trúc **3-Act**, xem `04_Entertainment_Template.md`

---

### 🤖 QUY TẮC TỰ ĐỘNG PHÁT HIỆN MODE (AI Auto-Detection)

**Nếu USER không chỉ định rõ Mode, AI tự xác định theo bảng sau:**

| Nếu yêu cầu chứa từ khóa... | → Mode | Lý do |
|-----------------------------|--------|-------|
| "sức khỏe", "y tế", "bệnh", "triệu chứng", "bác sĩ", "hại", "nguy hiểm" | **A** | Nội dung giáo dục sức khỏe |
| "cách làm", "hướng dẫn", "mẹo", "tips" + liên quan thực phẩm Tết | **A** | Nội dung hướng dẫn có tính giáo dục |
| Topic ID từ 01-100 trong `03_Project` | **A** | Danh sách topics Tết đều là Health |
| "hài", "comedy", "action", "drama", "phim", "giải trí", "animation" | **B** | Nội dung giải trí |
| "đại chiến", "battle", "cuộc chiến", "epic", "sử thi" | **B** | Nội dung action/drama |
| "thử nghiệm", "test", "sáng tạo tự do", "freestyle" | **B** | Nội dung thử nghiệm |
| Không rõ ràng | **HỎI LẠI USER** | Tránh làm sai |

**Ví dụ Auto-Detection:**
- "Làm video về tác hại của giò thập cẩm kém chất lượng" → **Mode A** (có "tác hại")
- "Làm video đại chiến giữa giò lụa và giò thập cẩm" → **Mode B** (có "đại chiến")
- "Làm Topic 55 Bánh Chưng" → **Mode A** (Topic ID trong danh sách)

---

### Nếu chọn Mode B, bỏ qua các phần sau:
- Phase 1.2: Scientific Research (E2) → Thay bằng Story Research
- Phase 2.4: CHỦ THỂ/VẬT CHỦ → Không bắt buộc
- Phase 2.5: Cấu trúc PMCS → Thay bằng 3-Act Structure
- Phase 8.2: Character Lineup Check → Không cần Expert

---




## 📥 INPUT FILES (Đọc trước khi bắt đầu)

### Bắt buộc:
| File | Đường dẫn | Mục đích |
|------|-----------|----------|
| **Content Plan** | `My Content/Tet_2026_Content_Plan.md` | Danh sách topics, tiêu đề gốc |
| **Topic Brief** | (Từ Content Plan hoặc yêu cầu user) | Chủ đề cụ thể cần triển khai |

### Tùy chọn (nếu có sẵn):
| File | Đường dẫn | Mục đích |
|------|-----------|----------|
| Trending Keywords | `01_Research/01_Trending_Keywords_2026.md` | Keywords trending đã research |
| Title Bank | `01_Research/02_Title_Bank_Tet_2026.md` | Tiêu đề viral đã chuẩn bị |
| SEO Bank | `01_Research/03_SEO_Bank_Tet_2026.md` | Hashtags, keywords sẵn có |

---

## 📚 REFERENCE FILES (Tham chiếu khi viết)

### Templates (BẮT BUỘC đọc):
| File | Đường dẫn | Nội dung chính |
|------|-----------|----------------|
| **Core Principles** | `02_Universal/00_Core_Principles.md` | Rulebook cô đọng |
| **Technical Rules** | `02_Universal/01_Technical_Rules.md` | E0-E32 rules (LUÔN ÁP DỤNG) |

### Databases (CHECK khi viết):
| File | Đường dẫn | Khi nào dùng |
|------|-----------|--------------|
| **Sensitive Words** | `01_Research/Sensitive_Words.txt` | Check từ nhạy cảm (E11) |
| **Global Bible** | `03_Advanced/Global_Bible_Library.md` | Mẫu nhân vật/bối cảnh |

### Hướng dẫn chi tiết:
| File | Đường dẫn | Nội dung |
|------|-----------|----------|
| Quick Reference | `03_Advanced/Quick_Reference_Card.md` | Tra cứu nhanh |

---

## 📤 OUTPUT FILES (Bàn giao)

### Delivery Package (5 files/topic) - CHUẨN:
| # | File | Format | Nội dung |
|---|------|--------|----------|
| 1 | `XX_Bible.md` | Markdown | Nhân vật, Bối cảnh, PMCS, Số liệu |
| 2 | `XX_Master.txt` | Text | Kịch bản gốc (Golden Sample format) |
| 3 | `XX_Prompts.txt` | Text | Visual prompts (clean, no text) |
| 4 | `XX_Dubbing.txt` | Text | Lời thoại |
| 5 | `XX_SEO.txt` | Text | Tiêu đề, Hashtags, Keywords |

---

## 📋 PHASE 1: TRƯỚC KHI VIẾT - RESEARCH

### ☐ 1.1 Trending Research (E0)
- [ ] Search: `[chủ đề] + trending 2026 + TikTok/YouTube`
- [ ] Check Google Trends, TikTok Trending
- [ ] Xác định: Người ta đang nói gì về chủ đề này?
- [ ] Ghi lại hashtags trending với view count

### ☐ 1.2 Scientific Research (E)
- [ ] Search: `[chủ đề] + scientific study`
- [ ] Tìm số liệu từ WHO, CDC, Bộ Y tế VN
- [ ] Cross-check 2-3 nguồn uy tín
- [ ] Ghi chú nguồn (năm 2023-2026)
- [ ] Chuẩn bị 5-7 số liệu cho script (E2)

### ☐ 1.3 SEO Research (E14)
- [ ] Research hashtags TikTok
- [ ] Check hashtags YouTube (VidIQ)
- [ ] Tìm keywords Primary/Secondary/Long-tail
- [ ] Xem tags của video đối thủ top
- [ ] Ghi nguồn research

### ☐ 1.4 Consequence Planning (E15) - MỚI
- [ ] Xác định: Hậu quả NHÌN THẤY trên CON NGƯỜI là gì?
- [ ] Lập bảng: Nội tạng → Triệu chứng người xem thấy
- [ ] Dự kiến: Split Screen (cơ chế + hậu quả nhìn thấy)

---

## 📋 PHASE 2: VIẾT BIBLE.MD

### ☐ 2.1 Thông tin khoa học
- [ ] Có nguồn tham khảo (WHO, CDC, etc.)
- [ ] Có 5-7 số liệu chính
- [ ] Số liệu đã cross-check

### ☐ 2.2 Nhân vật (Character Bible)
- [ ] Mô tả ngoại hình đầy đủ (từ đầu đến chân)
- [ ] ĐỘ TUỔI có ghi rõ (XX years old) - MỚI
- [ ] TRANG PHỤC có mô tả (casual + festive nếu có) - MỚI
- [ ] PHỤ KIỆN cố định được liệt kê - MỚI
- [ ] Biểu cảm đơn giản (dot eyes, curved mouth) - E12
- [ ] Mỗi nhân vật = 1 kiến thức riêng (E3)

### ☐ 2.3 CHỦ THỂ/VẬT CHỦ (A2) - BẮT BUỘC khi nhân hóa nội tạng
- [ ] Mô tả cơ bản: ĐỘ TUỔI, giới tính, ngoại hình
- [ ] Trang phục: Quần áo, phụ kiện
- [ ] Trạng thái bình thường: Da hồng, mắt sáng, khỏe mạnh
- [ ] Trạng thái triệu chứng: Vàng da, phù mặt, mệt mỏi, etc.
- [ ] Kỹ thuật chuyển cảnh: Zoom Out / Split Screen / Match Cut (E20)

### ☐ 2.4 Bối cảnh (Setting Bible) - CẬP NHẬT
- [ ] Địa điểm được định nghĩa rõ
- [ ] Thời gian (sáng/trưa/tối) nhất quán
- [ ] Ánh sáng theo cảm xúc (E20 Lighting table)
- [ ] Palette màu được xác định
- [ ] Props cố định được liệt kê

### ☐ 2.5 Cấu trúc PMCS (E4)
- [ ] P (Problem): Hook gây sốc
- [ ] M (Mechanism): Cơ chế khoa học
- [ ] C (Consequence): Hậu quả (hiển thị trên CHỦ THỂ!)
- [ ] S (Solution): Giải pháp cụ thể

---

## 📋 PHASE 3: VIẾT MASTER.TXT (Golden Sample Format)

### ☐ 3.1 Format ĐÚNG - MỖI DÒNG PHẢI CÓ:
```
[Scene type]. [Shot type]. [Visual Style]. [Setting]. [Character full description + action]. Audio [sound]. [Giọng: Vùng, Tuổi] "Thoại."
```

### ☐ 3.2 Ví dụ ĐÚNG:
```
Opening scene, establishing the problem. Medium shot. The 3D cute animation style, Pixar render, Kitchen. A middle-aged Asian mother, 40 years old, wearing apron, opening fridge door, looking horrified. Audio of creaky door. [Giọng: Miền Bắc, 40 tuổi] "Tủ lạnh nhà mình sao có mùi lạ."
```

### ☐ 3.3 Format SAI (KHÔNG DÙNG):
```
CLIP 1:
[Visual:] ...
[Audio:] ...
```

### ☐ 3.4 Checklist mỗi dòng Master:
- [ ] Scene type: Opening/Mechanism 1/Consequence/Solution...
- [ ] Shot type: Medium shot/Close-up/Wide shot/Split screen
- [ ] Visual Style: `The 3D cute animation style, Pixar render`
- [ ] Setting: Kitchen/Inside body/etc.
- [ ] Character description ĐẦY ĐỦ (E8)
- [ ] Character action
- [ ] Audio/Sound effects
- [ ] Voice metadata: `[Giọng: Vùng, Tuổi]` (FORMAT 2026 — Giới tính từ Bible, Tone trong visual)

> [!WARNING]
> **FORMAT CŨ - KHÔNG DÙNG NỮA**: `[Region: X] [Gender: X] [Age: X] [Tone: X]`

### ☐ 3.5 Logic Check (E5)
- [ ] Nhân vật đang ĐI hay ĐỨNG? Thoại có khớp?
- [ ] Thời gian trong thoại khớp với bối cảnh?
- [ ] Hành động khớp với thoại?


### ☐ 3.6 Scene Transition (E6)
- [ ] Có mô tả chuyển cảnh giữa các clips?
- [ ] Dùng kỹ thuật: Zoom Out, Pan, Follow Flow

### ☐ 3.7 Linh hoạt 8-12 Scenes (E22) - BẮT BUỘC
- [ ] Video có **8-12** phân cảnh (linh hoạt theo chủ đề)?
- [ ] Mechanism có 2-3+ scenes riêng biệt?
- [ ] Solution có 1-2+ scenes riêng biệt?
- [ ] Không nhồi nhét nhiều cơ chế/giải pháp vào 1 scene?

### ☐ 3.8 Dialogue Length (E23) - BẮT BUỘC
- [ ] Mỗi thoại ≤ 20 từ tiếng Việt?
- [ ] Đếm: số + từ ghép = từ riêng
- [ ] Nếu >20 từ → đã chia thành scenes riêng?
- [ ] Đọc thử - không quá nhanh?

---

## 📋 PHASE 4: VIẾT PROMPTS.TXT

### ☐ 4.1 Zero Text Policy (E7) - NGHIÊM NGẶT
- [ ] ❌ Không có text trong dấu ngoặc kép `"..."` trong visual
- [ ] ❌ Không có từ: shows, displays, reads, says + text
- [ ] ❌ Không có labels, signs, posters, buttons, menus
- [ ] ❌ Không có charts/graphs với text labels
- [ ] ❌ Không có phone/computer screens showing text
- [ ] ❌ Không có timestamps, counters, timers
- [ ] ❌ Không có số liệu trong visual (dùng voice thay thế)
- [ ] ✅ Đã thêm suffix cuối mỗi prompt: `no text, no subtitles, no labels, no watermarks`

### ☐ 4.2 Thay thế bằng Visual Symbols:
| Thay vì | Dùng |
|---------|------|
| `clock shows "3:00"` | `afternoon lighting, sun position` |
| `sign reads "Danger"` | `red warning glow pulsing` |
| `counter shows "100"` | `container overflowing` |
| `label says "Toxic"` | `skull symbol, green fumes` |
| `phone screen text` | `phone glowing notification` |

### ☐ 4.3 Face Style (E12)
- [ ] Anthropomorphic faces đơn giản
- [ ] Dot eyes (không realistic eyes)
- [ ] Curved/wavy mouth (không lips)
- [ ] Không mô tả eyelashes, pupils, teeth

### ☐ 4.4 Sensitive Words (E11)
- [ ] Check 03_Sensitive_Words_Database.txt
- [ ] Không dùng: chết, giết, tử vong
- [ ] Thay bằng: hẹo, tiêu đời, game over

### ☐ 4.5 Special Characters in Dialogue (E24) - MỚI
- [ ] Không có `>` hoặc `<` trong thoại?
- [ ] Không có `=` (thay bằng "bằng")?
- [ ] Không có `-` (tất cả các dấu nối câu)?
- [ ] Không có `!` (thay bằng `.`) ở Master file?
- [ ] Số liệu đã viết đầy đủ dạng chữ?

**Bảng chuyển đổi nhanh (Master File):**
| Ký tự | Thay bằng |
|-------|-----------|
| `>` | "lớn hơn", "vượt" |
| `<` | "dưới", "nhỏ hơn" |
| `=` | "bằng" |
| `!` | "." (dấu chấm) |
| `?` | "." (dấu chấm) hoặc chuyển thành câu trần thuật |
| `-` | " " (khoảng trắng) hoặc loại bỏ |
| `60-80%` | "60 đến 80 phần trăm" |

### ☐ 4.5a Dialogue Quality (Context & Flow) - MỚI
- [ ] KHÔNG dùng câu cụt, câu quá ngắn (< 5 chữ) gây hụt hẫng?
- [ ] KHÔNG dùng câu hỏi tu từ (dễ gây lỗi đọc sai tone)?
- [ ] Ví dụ SAI: "Nếp thế này? Bánh cứng." (Cụt + Dấu ?)
- [ ] Ví dụ ĐÚNG: "Nếu chọn nếp cũ thế này thì bánh sẽ cứng như gạch."
- [ ] Luôn giải thích "Tại sao" hoặc "Cái gì" rõ ràng trong câu.

### ☐ 4.5b Thuật ngữ Y học (E24.4) - MỚI
- [ ] KHÔNG dùng dấu nối (hyphen) trong phiên âm (Ví dụ: A-phờ-la-tô-xin -> SAI)
- [ ] Chuyển về tiếng Việt hoặc phiên âm trơn (Ví dụ: Aflatoxin hoặc Chất độc gan)
- [ ] ACID → "a xít" (không gạch nối)
- [ ] Enzyme → "en zim" (không gạch nối)
- [ ] Aflatoxin → "Aflatoxin" hoặc "chất độc gan"
- [ ] Sodium bisulfite → "Sô đi um bi sun phít" (không gạch nối)

### ☐ 4.6 Villain Dialogue Style (E25) - MỚI
- [ ] Villain xưng "Ta/Bọn ta" (không "Tôi")?
- [ ] Có tone Đắc thắng/Cười ác/Đe dọa?
- [ ] Đe dọa có số liệu + hậu quả cụ thể?
- [ ] Villain có thái độ kiêu ngạo, coi thường?

### ☐ 4.7 Impact Dialogue - No Vague (E26) - MỚI
- [ ] Mỗi câu có ít nhất 1: số liệu / hậu quả / so sánh?
- [ ] KHÔNG có các cụm từ sáo rỗng sau:
  - "rất nguy hiểm" → Thay bằng số liệu cụ thể
  - "không tốt" → Thay bằng "gây [bệnh cụ thể]"
  - "ảnh hưởng" → Thay bằng "[hậu quả cụ thể]"
  - "cần cẩn thận" → Thay bằng "[số + hậu quả]"

### ☐ 4.8 Specific Units for Numbers (E27) - MỚI
- [ ] Số liệu y học có đơn vị cụ thể?
- [ ] Đơn vị đã phiên âm tiếng Việt?

**Bảng đơn vị chuẩn:**
| Chỉ số | Đơn vị tiếng Việt |
|--------|-------------------|
| Đường huyết | "mi-li-gam trên đề-xi-lít" |
| Huyết áp | "mi-li-mét thủy ngân" |
| Nhiệt độ | "độ xê" |
| Cân nặng | "ki-lô-gam" |
| Năng lượng | "ca-lo" |

**Ví dụ:**
- ❌ "vọt lên 50 điểm" → Không rõ đơn vị gì
- ✅ "vọt lên 250 mi-li-gam trên đề-xi-lít"

### ☐ 4.9 Sensitive Words Check (E28) - BẮT BUỘC
- [ ] Không có từ "chết/chết người" → thay bằng "hẹo/tiêu đời/tiêu diệt/cực độc"?
- [ ] Không có từ "tử vong" → thay bằng "nguy kịch/mất mạng"?
- [ ] Không có từ "giết" → thay bằng "tiêu diệt/gây nguy hiểm"?
- [ ] Đã check với 03_Sensitive_Words_Database.txt?

**Bảng thay thế nhanh:**
| Từ vi phạm | Thay bằng |
|------------|-----------|
| `chết` | "hẹo", "tiêu đời", "tiêu diệt" |
| `chết người` | "cực độc", "gây ngộ độc nguy hiểm" |
| `tử vong` | "nguy kịch", "mất mạng" |
| `giết` | "tiêu diệt", "gây nguy hiểm" |

---

## 📋 PHASE 5: VIẾT DUBBING.TXT

### ☐ 5.1 Content
- [ ] Chỉ chứa lời thoại (không visual)
- [ ] Có số liệu cụ thể trong mỗi câu
- [ ] Logic với hành động trong Master

### ☐ 5.2 Dubbing Format (E29) - BẮT BUỘC
- [ ] Format: `[CLIP N]` + Metadata + Dialogue
- [ ] Metadata: `[Character: Tên] [Giọng: Vùng, Tuổi]`
- [ ] Không dùng format cũ `[Region: ...]`
- [ ] Không có từ nhạy cảm (E28)?
- [ ] Số clip = số scene trong Master?
- [ ] Dialogue sync với Master.txt?

**Format chuẩn:**
```
[CLIP 1]
[Character: Tên Nhân Vật] [Giọng: Vùng, Tuổi]
"Nội dung lời thoại."

[CLIP 2]
...
```

---

## 📋 PHASE 6: VIẾT SEO.TXT

### ☐ 6.1 Metadata bắt buộc
- [ ] Ngày research
- [ ] Nguồn research
- [ ] 3 Tiêu đề A/B/C

### ☐ 6.2 Hashtags
- [ ] Trending TikTok (có view count)
- [ ] YouTube hashtags
- [ ] Facebook hashtags

### ☐ 6.3 Keywords
- [ ] Primary keywords
- [ ] Secondary keywords
- [ ] Long-tail keywords
- [ ] Competitor tags

### ☐ 6.4 Title Check (E13)
- [ ] Hook trong 3 từ đầu
- [ ] Số trong listicle >= 4 (sai lầm), >= 5 (dấu hiệu)
- [ ] Không có từ nhạy cảm
- [ ] Độ dài < 60 ký tự
- [ ] Hook liên quan sức khỏe (không ẩn dụ công sở)

---

## 📋 PHASE 7: CROSS-CHECK ĐỒNG BỘ (E16) - MỚI

### ☐ 7.1 Character Sync
- [ ] Mô tả nhân vật BIBLE = MASTER = PROMPTS?
- [ ] Đã copy-paste chính xác (không paraphrase)?
- [ ] Biểu cảm (dot eyes, curved mouth) nhất quán?

### ☐ 7.2 Setting Sync
- [ ] Mô tả bối cảnh BIBLE = MASTER = PROMPTS?
- [ ] Ánh sáng, màu sắc nhất quán?

### ☐ 7.3 Host/Subject Sync
- [ ] Mô tả Chủ Thể nhất quán khi xuất hiện?
- [ ] Trạng thái triệu chứng giống nhau?

### ☐ 7.4 Visual Style Sync
- [ ] Visual style nhất quán trong MỌI prompt (Pixar / Realistic / Whimsical / etc.)?
- [ ] Không thiếu prefix nào?

### Giọng Nói (Voice Metadata) - FORMAT ĐƠN GIẢN 2026:
**Cú pháp**: `[Giọng: Vùng, Tuổi]`

| Vùng | Ví dụ Tuổi |
|------|------------|
| Miền Bắc | 20 tuổi, 35 tuổi, 60 tuổi |
| Miền Nam | Teen, 30 tuổi, 50 tuổi |
| Miền Tây | 25 tuổi, 45 tuổi |
| Miền Trung | 35 tuổi, 55 tuổi |

**Ví dụ:**
```
[Giọng: Miền Nam, 35 tuổi]
[Giọng: Miền Bắc, 60 tuổi]
[Giọng: Miền Tây, 40 tuổi]
```

> [!IMPORTANT]
> **Giới tính**: Xác định trong Character Bible → Copy-paste như visual description
> **Tone/Cảm xúc**: Mô tả trong prompt visual (VD: "speaking with worried expression", "villainous grin while taunting")

### Cách mô tả Tone trong Prompt Visual:
| Loại nhân vật | Mô tả trong Prompt |
|---------------|--------------------|
| **Villain** | "evil grin", "taunting expression", "menacing voice" |
| **Hero** | "confident smile", "warm caring expression" |
| **Victim** | "exhausted face", "pained expression", "crying" |
| **Narrator** | "neutral expression", "serious face" |

---

## 📋 VISUAL STYLE (Copy-paste)

```
The 3D cute animation style, Pixar render, soft lighting, vibrant colors
```

---

## 📋 PHASE 8: FINAL REVIEW (Trước khi bàn giao)

### ☐ 8.1 File Completion Check
- [ ] 5 files đầy đủ: Bible, Master, Prompts, Dubbing, SEO?
- [ ] Naming convention đúng: XX_Bible.md, XX_Master.txt...?

### ☐ 8.2 Character Lineup Check (E17)
- [ ] Có CHỦ THỂ (Human Subject) ở Opening + Consequence?
- [ ] Có NHÂN VẬT NHÂN HÓA ở Mechanism?
- [ ] Có CHUYÊN GIA ở Solution scene?
- [ ] Consequence dùng Split Screen (organ + person)?

### ☐ 8.3 Voice Consistency Check (E18)
- [ ] Cùng nhân vật = Cùng Region/Gender/Age?
- [ ] Expert dùng voice chuẩn: Nữ 35s Chuyên nghiệp?
- [ ] Nhân vật phụ có voice khác biệt?

### ☐ 8.4 Timing Check
- [ ] Mỗi dòng Master ≈ 8 giây (E9)?
- [ ] Tổng video ≤ 60 giây (Shorts)?

### ☐ 8.5 Flow Check
- [ ] Logic PMCS đầy đủ?
- [ ] Có Solution rõ ràng?
- [ ] Có Call-to-action cuối video?

---

## 📋 PHASE 9: QUY TRÌNH VÒNG LẶP (WORKFLOW LOOP) - BẮT BUỘC

> [!IMPORTANT]
> **Quy trình này áp dụng cho cả sản xuất TỪNG DỰ ÁN và sản xuất NHIỀU DỰ ÁN liên tục**

### 9.1 VÒNG LẶP TẠO FILE TRONG 1 DỰ ÁN (Sequential File Creation)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW LOOP - 1 DỰ ÁN                          │
│                                                                     │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐                    │
│  │ 1. LOAD  │ ──▶ │ 2. TẠO   │ ──▶ │ 3. LƯU   │                    │
│  │ Template │     │   File   │     │  Output  │                    │
│  └──────────┘     └──────────┘     └──────────┘                    │
│       ▲                                  │                          │
│       │                                  │                          │
│       └──────────────────────────────────┘                          │
│              REPEAT cho file tiếp theo                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Thứ tự tạo file BẮT BUỘC:

| Bước | Load Template | + Input từ | → Tạo Output | Lưu vào |
|------|---------------|------------|--------------|---------|
| 1 | `02_Bible_Template.md` | Chủ đề User | `XX_Bible.md` | Project folder |
| 2 | `06_Master_Template.md` | **XX_Bible.md** | `XX_Master.txt` | Project folder |
| 3 | `07_Prompts_Template.md` | **XX_Master.txt** | `XX_Prompts.txt` | Project folder |
| 4 | `08_Dubbing_Template.md` | **XX_Master.txt** | `XX_Dubbing.txt` | Project folder |
| 5 | `09_SEO_Template.md` | **XX_Bible.md** + Chủ đề | `XX_SEO.txt` | Project folder |

### Checklist mỗi bước:
- [ ] **LOAD**: Đọc lại template tương ứng từ `00_System`
- [ ] **INPUT**: Sử dụng file vừa tạo ở bước trước làm nguồn dữ liệu
- [ ] **COPY-PASTE**: Character/Setting descriptions COPY từ Bible, không paraphrase
- [ ] **CHECK**: Áp dụng rules từ `03_Veo3_Technical_Template.md`
- [ ] **SAVE**: Lưu file với đúng naming convention `XX_[Type].[ext]`

---

### 9.2 VÒNG LẶP NHIỀU DỰ ÁN (Multi-Project Batch Production)

```
┌─────────────────────────────────────────────────────────────────────┐
│                WORKFLOW LOOP - NHIỀU DỰ ÁN                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            DANH SÁCH CHỦ ĐỀ TỪ USER                         │   │
│  │  Topic 1, Topic 2, Topic 3, ... Topic N                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    FOR EACH TOPIC:                          │   │
│  │                                                             │   │
│  │   ┌───────────────────────────────────────────────────┐    │   │
│  │   │ BƯỚC 0: RELOAD TẤT CẢ TEMPLATES                   │    │   │
│  │   │ • Load 02_Bible_Template.md                       │    │   │
│  │   │ • Load 06_Master_Template.md                      │    │   │
│  │   │ • Load 07_Prompts_Template.md                     │    │   │
│  │   │ • Load 08_Dubbing_Template.md                     │    │   │
│  │   │ • Load 09_SEO_Template.md                         │    │   │
│  │   │ • Load 03_Veo3_Technical_Template.md (Rules)      │    │   │
│  │   └───────────────────────────────────────────────────┘    │   │
│  │                          │                                  │   │
│  │                          ▼                                  │   │
│  │   ┌───────────────────────────────────────────────────┐    │   │
│  │   │ BƯỚC 1-5: TẠO 5 FILES THEO THỨ TỰ                 │    │   │
│  │   │ Bible → Master → Prompts → Dubbing → SEO          │    │   │
│  │   └───────────────────────────────────────────────────┘    │   │
│  │                          │                                  │   │
│  │                          ▼                                  │   │
│  │   ┌───────────────────────────────────────────────────┐    │   │
│  │   │ BƯỚC 6: QUALITY CHECK (Phase 7-8)                 │    │   │
│  │   └───────────────────────────────────────────────────┘    │   │
│  │                          │                                  │   │
│  │                          ▼                                  │   │
│  │   ┌───────────────────────────────────────────────────┐    │   │
│  │   │ BƯỚC 7: LƯU VÀO PROJECT FOLDER                    │    │   │
│  │   │ → XX_[Topic_Name]/                                │    │   │
│  │   └───────────────────────────────────────────────────┘    │   │
│  │                          │                                  │   │
│  └──────────────────────────┼──────────────────────────────────┘   │
│                             │                                      │
│                             ▼                                      │
│              ┌──────────────────────────┐                          │
│              │  NEXT TOPIC (nếu còn)    │                          │
│              │  LOOP BACK to BƯỚC 0     │                          │
│              └──────────────────────────┘                          │
│                             │                                      │
│                             ▼                                      │
│              ┌──────────────────────────┐                          │
│              │  ✅ HOÀN THÀNH TẤT CẢ   │                          │
│              │  Báo cáo cho User        │                          │
│              └──────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Quy tắc RELOAD Templates:

> [!CAUTION]
> **BẮT BUỘC**: Trước mỗi dự án MỚI, PHẢI reload lại TẤT CẢ templates từ `00_System` để:
> 1. Đảm bảo dùng phiên bản mới nhất
> 2. Reset context, tránh nhầm lẫn giữa các dự án
> 3. Áp dụng đúng rules cho từng dự án

### Checklist Multi-Project:
- [ ] **TRƯỚC KHI BẮT ĐẦU**: Liệt kê tất cả topics cần làm
- [ ] **MỖI TOPIC**: Reload templates → Tạo 5 files → Quality check → Lưu
- [ ] **SAU MỖI TOPIC**: Xác nhận hoàn thành, chuyển sang topic tiếp theo
- [ ] **KẾT THÚC**: Báo cáo tổng số files đã tạo

---

### 9.3 SƠ ĐỒ DEPENDENCY (File nào phụ thuộc file nào)

```
                    ┌─────────────┐
                    │   USER      │
                    │  Chủ đề     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   BIBLE     │ ◀── 02_Bible_Template.md
                    │  (.md)      │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
     ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
     │   MASTER    │ │     SEO     │ │  (Prompts   │
     │  (.txt)     │ │   (.txt)    │ │   _Ref)     │
     └──────┬──────┘ └─────────────┘ └─────────────┘
            │          ◀── 09_SEO_Template.md
            │
     ┌──────┴──────┐
     │             │
     ▼             ▼
┌─────────────┐ ┌─────────────┐
│   PROMPTS   │ │   DUBBING   │
│  (.txt)     │ │   (.txt)    │
└─────────────┘ └─────────────┘
 ◀── 07_       ◀── 08_
```

### Dependency Rules:
| File | Phụ thuộc vào | KHÔNG THỂ tạo nếu thiếu |
|------|---------------|-------------------------|
| Bible | Chủ đề User | - |
| Master | **Bible** | Character, Setting descriptions |
| Prompts | **Master** | Visual scenes |
| Dubbing | **Master** | Dialogue, Voice metadata |
| SEO | **Bible** + Chủ đề | Số liệu, Keywords |

---

### 9.4 LỖI THƯỜNG GẶP & CÁCH TRÁNH

| Lỗi | Hậu quả | Cách tránh |
|-----|---------|------------|
| Tạo Master trước Bible | Mô tả nhân vật không nhất quán | Luôn tạo Bible TRƯỚC |
| Không reload template | Dùng format cũ, sai rules | Reload ĐẦU mỗi dự án |
| Paraphrase thay vì copy | Veo render khác nhau | COPY-PASTE từ Bible |
| Bỏ qua Quality Check | Lỗi format, từ nhạy cảm | Check SAU mỗi file |
| Không reset giữa các topics | Nhầm lẫn nội dung | Reload templates giữa các topics |

---

## 📋 DELIVERY PACKAGE (5 FILES)

| # | File | Nội dung |
|---|------|----------|
| 1 | `_Bible.md` | Nhân vật, Bối cảnh, PMCS, Số liệu |
| 2 | `_Master.txt` | Kịch bản gốc (Golden Sample format) |
| 3 | `_Prompts.txt` | Visual prompts (clean, no text) |
| 4 | `_Dubbing.txt` | Lời thoại |
| 5 | `_SEO.txt` | Tiêu đề, Hashtags, Keywords |

---

*Production Checklist v2.0 - Cập nhật: 2026-01-05*
