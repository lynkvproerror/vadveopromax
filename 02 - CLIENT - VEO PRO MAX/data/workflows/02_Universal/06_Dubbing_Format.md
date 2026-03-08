# DUBBING.TXT TEMPLATE - VOICE SCRIPT
## Template chuẩn cho file `XX_Dubbing.txt`

**Phiên bản**: 1.0  
**Cập nhật**: 2026-01-29  
**Áp dụng**: Tất cả dự án - Dùng cho Voice Actor / TTS

---

## 📋 FORMAT CHUẨN ĐƠN GIẢN (2026)

```
[CLIP N]
[Character: Tên Nhân Vật] [Giọng: Vùng, Tuổi]
"Nội dung lời thoại."
```

> [!NOTE]
> **Giới tính**: Xác định trong Character Bible → Copy-paste cho toàn bộ kịch bản
> **Tone/Cảm xúc**: Mô tả trong prompt visual (VD: "villainous grin", "worried expression")

---

## ❌ FORMAT CŨ (KHÔNG DÙNG NỮA)

```
❌ SAI - Format cũ:
[CLIP 1 - PROBLEM]
[Character: Mẹ] [Region: Bắc (Hà Nội)] [Gender: Female] [Age: 40s] [Tone: Lo lắng]
"Lời thoại..."
```

---

## ✅ VÍ DỤ ĐẦY ĐỦ

```
[CLIP 1]
[Character: Mẹ Hương] [Giọng: Miền Bắc, 42 tuổi]
"Đồ ăn thừa từ hôm qua vẫn còn nguyên, liệu có ăn được không nhỉ."

[CLIP 2]
[Character: Vi Khuẩn Xanh] [Giọng: Miền Nam, 30 tuổi]
"Haha, chỉ sau 2 tiếng ở nhiệt độ phòng, bọn ta đã nhân lên gấp 4 lần rồi."

[CLIP 3]
[Character: Vi Khuẩn Vàng] [Giọng: Miền Nam, 35 tuổi]
"Bọn ta tiết ra độc tố mà dù nấu chín cũng không thể phá hủy được."

[CLIP 4]
[Character: Dạ Dày] [Giọng: Miền Tây, 45 tuổi]
"Ối trời ơi, bọn nó tràn vào đây hàng triệu con, tui xử lý không nổi rồi."

[CLIP 5]
[Character: Mẹ Hương] [Giọng: Miền Bắc, 42 tuổi]
"Đau bụng quá, chỉ vì tiếc 1 đĩa thức ăn mà giờ phải đi viện."

[CLIP 6]
[Character: Narrator] [Giọng: Miền Nam, 30 tuổi]
"Mỗi năm có hơn 600 triệu ca ngộ độc thực phẩm trên thế giới, 420 ngàn người tử vong."

[CLIP 7]
[Character: Bác sĩ Linh] [Giọng: Miền Nam, 35 tuổi]
"Quy tắc 2 tiếng, thức ăn để ngoài quá 2 tiếng phải bỏ ngay."

[CLIP 8]
[Character: Bác sĩ Linh] [Giọng: Miền Nam, 35 tuổi]
"Thức ăn còn nóng phải cho vào tủ lạnh trong vòng 1 tiếng, không cần đợi nguội."

[CLIP 9]
[Character: Mẹ Hương] [Giọng: Miền Bắc, 42 tuổi]
"Nhờ biết quy tắc này mà Tết năm nay cả nhà không ai bị đau bụng."
```

---

## 📝 BẢNG VÙNG GIỌNG (ĐƠN GIẢN)

| Vùng | Đặc điểm | Dùng cho |
|------|----------|----------|
| **Miền Bắc** | Chuẩn, rõ ràng, formal | Narrator, Expert, Hero |
| **Miền Nam** | Nhẹ nhàng, thân thiện | Expert, Villain, thường |
| **Miền Tây** | Ấm áp, chân chất | Victim (nội tạng), thường |
| **Miền Trung** | Đặc trưng, trầm | Nhân vật đặc biệt |

---

## 🎭 EXPRESSION REFERENCE (Mô tả trong Prompt Visual)

> [!TIP]
> Tone/cảm xúc KHÔNG ghi trong `[Giọng:]` nữa. Thay vào đó, mô tả trong phần visual của Master.txt

### Nhân vật TÍCH CỰC (Hero/Victim/Expert):
| Cảm xúc | Mô tả Visual Prompt |
|----------|---------------------|
| Lo lắng | "worried expression", "furrowed brow", "anxious eyes" |
| Đau đớn | "pained expression", "grimacing", "tearful eyes" |
| Chuyên nghiệp | "confident smile", "calm demeanor", "steady gaze" |
| Hướng dẫn | "warm encouraging smile", "pointing gesture" |
| Vui vẻ | "bright smile", "happy expression", "cheerful" |

### Nhân vật PHẢN DIỆN (Villain):
| Cảm xúc | Mô tả Visual Prompt |
|----------|---------------------|
| Đắc thắng | "evil grin", "triumphant expression", "smug look" |
| Cười ác | "villainous grin", "menacing smile", "cruel laugh" |
| Đe dọa | "threatening expression", "glaring", "intimidating" |
| Kiêu ngạo | "arrogant smirk", "looking down", "dismissive" |
| Dụ dỗ | "sly smile", "sweet but deceptive expression" |

### Nhân vật TRUNG LẬP (Narrator/Organ):
| Cảm xúc | Mô tả Visual Prompt |
|----------|---------------------|
| Kiệt sức | "exhausted expression", "drooping", "tired eyes" |
| Mệt mỏi | "weary face", "sluggish", "overwhelmed" |
| Cầu cứu | "pleading eyes", "desperate expression" |
| Cảnh báo | "serious face", "stern expression" |
| Giáo dục | "neutral but attentive", "explanatory gesture" |

---

## 🚫 QUY TẮC THOẠI (E19, E24-E29)

### KHÔNG ĐƯỢC CÓ:

| Ký tự/Pattern | Vấn đề | Thay bằng |
|---------------|--------|-----------|
| `?` | VEO 3.1 đọc sai tone | `.` hoặc câu trần thuật |
| `!` | Quá kích động | `.` |
| `-` trong từ | TTS không đọc được | Khoảng trắng hoặc bỏ |
| Câu < 5 chữ | Quá cụt, hụt hẫng | Viết đầy đủ hơn |
| `>`, `<`, `=` | Ký tự toán học | "lớn hơn", "bằng" |

### VÍ DỤ SỬA:

| ❌ SAI | ✅ ĐÚNG |
|--------|---------|
| `"Sao lại thế?"` | `"Lý do là vì điều này."` |
| `"Nguy hiểm quá!"` | `"Đây là điều nguy hiểm."` |
| `"A-xít"` | `"A xít"` |
| `"Hỏng."` | `"Bánh sẽ bị hỏng hoàn toàn."` |
| `"60-80%"` | `"60 đến 80 phần trăm"` |
| `">5 tiếng"` | `"hơn 5 tiếng"` |

---

## 🎙️ XƯNG HÔ THEO VAI TRÒ (E10)

| Vai | Xưng | Hô |
|-----|------|-----|
| **Tích cực** (Bác sĩ, Mẹ) | tôi, mình, em | bạn, anh chị, con |
| **Phản diện** (Vi khuẩn, Mỡ) | ta, bọn ta, tao | mày, bà, ông |
| **Trung lập** (Gan, Thận) | tôi, tui | bà chủ, ông chủ |
| **Thân mật cùng phe** | mày-tao (vui) | mày-tao (vui) |

---

## ⚠️ TỪ NHẠY CẢM (E11, E28)

### Bắt buộc thay thế:

| Từ CẤM | Thay bằng |
|--------|-----------|
| `chết` | hẹo, tiêu đời, tiêu diệt |
| `chết người` | cực độc, gây ngộ độc nguy hiểm |
| `tử vong` | nguy kịch, mất mạng |
| `giết` | tiêu diệt, gây nguy hiểm |

### Ví dụ:
- ❌ "Có thể gây chết người" → ✅ "Có thể gây ngộ độc cực độc"
- ❌ "Giết chết tế bào gan" → ✅ "Tiêu diệt tế bào gan"

---

## ✅ CHECKLIST TRƯỚC KHI SUBMIT

- [ ] Format đúng: `[CLIP N]` + Metadata + Thoại
- [ ] Metadata dùng format ĐƠN GIẢN: `[Giọng: Vùng, Tuổi]`
- [ ] Giới tính nhân vật đã xác định trong Bible
- [ ] Không có `?`, `!`, `-` trong thoại
- [ ] Không có câu cụt < 5 chữ
- [ ] Số liệu viết đầy đủ dạng chữ
- [ ] Xưng hô đúng vai trò
- [ ] Đã check Sensitive Words Database
- [ ] Số clip = số scene trong Master.txt
- [ ] Thoại sync với Master.txt

---

## 🔗 LIÊN KẾT VỚI CÁC FILE KHÁC

| File | Cách lấy nội dung |
|------|-------------------|
| `_Master.txt` | TÁCH phần Dialogue + Voice Metadata (không lấy tone) |
| `_Bible.md` | Lấy tên nhân vật, giới tính, voice style |

---

*Dubbing Template v1.0 - 2026-01-29*
