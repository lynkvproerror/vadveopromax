# QUICK REFERENCE CARD - VEO 3 SCRIPT PRODUCTION
## Thẻ Tham Khảo Nhanh

---

## 📦 4 FILES BÀN GIAO

| File | Nội dung | Cho ai |
|------|----------|--------|
| `_Bible.md` | Nhân vật + Bối cảnh | Designer |
| `_Master.txt` | Kịch bản đầy đủ | Director |
| `_Prompts.txt` | Visual prompt only | AI Veo 3 |
| `_Dubbing.txt` | Lời thoại + Metadata | Voice Actor |

---

## 🎬 CẤU TRÚC PMCS (9 Clips)

| Phase | Clips | Nội dung |
|-------|-------|----------|
| **P**roblem | 1-2 | Giới thiệu vấn đề |
| **M**echanism | 3-5 | Giải thích cơ chế sinh học |
| **C**onsequence | 6 | Cảnh báo hậu quả |
| **S**olution | 7-9 | Bác sĩ đưa giải pháp |

---

## ⛔ 7 ĐIỀU CẤM KỴ TRONG VISUAL PROMPT

1. ❌ Số cụ thể: `"180mg/dL"`, `"Impact #7,432"`
2. ❌ Timer/Counter: `"30 minutes"`, `"+40%"`
3. ❌ Labels: `"DANGER ZONE 4-60°C"`
4. ❌ Gauges với số: `"Processing: 10g/hour"`
5. ❌ Tên bịa đặt: `"chị Lan"`
6. ❌ Mô tả thiếu nhân vật trong cảnh multi-character
7. ❌ Thoại không khớp hành động
8. ❌ Dấu `?` trong thoại, câu cụt, dấu nối `-` (VEO 3.1 Error)
9. ❌ Từ cam kết: "Trị dứt điểm", "Cam kết khỏi" (YMYL Violation)



---

## ✅ GIẢI PHÁP THAY THẾ

| Thay vì | Dùng |
|---------|------|
| `counter shows "7,432"` | `visible stress cracks spreading` |
| `timer shows "30 min"` | `lining turns visibly red and raw` |
| `meter shows "4x"` | `thermometer needle in red zone` |
| `label shows "4°C"` | `thermometer glows green in safe zone` |

---

## 📢 XƯNG HÔ THEO VAI TRÒ

| Vai | Xưng | Hô | Biểu cảm |
|-----|------|-----|----------|
| **Tích cực** (Bác sĩ) | tôi, mình | anh/chị, bạn | Thân thiện |
| **Phản diện** (Vi khuẩn, Mỡ) | ta, tao | mày, bà, ông | Đắc thắng, ác |
| **Trung lập** (Nội tạng than phiền) | tôi, tui | bà chủ, ông chủ | Mệt mỏi, khổ sở |
| **Thân mật** (Cùng phe) | mày-tao (vui) | mày-tao (vui) | Cười thoải mái |

---

## 🔄 KỸ THUẬT CHUYỂN CẢNH

1. **Zoom Out → Pan**: Từ cơ quan A → zoom out → thấy cơ quan B
2. **Character Walks In**: Nhân vật B nhảy/đi vào khung hình
3. **Match Cut**: Hình dạng tương đồng (tròn → tròn)
4. **Whip Pan**: Camera xoay nhanh
5. **Follow the Flow**: Theo dòng máu/dây dẫn

---

## 📝 TEMPLATE MÔ TẢ NHÂN VẬT

### Người thật:
```
A [tuổi] Asian [giới tính], [tuổi]s, wearing [trang phục], 
[biểu cảm expression], [hành động]
```

### Nhân hóa:
```
An anthropomorphic [đối tượng], [màu sắc], [đặc điểm nổi bật], 
[biểu cảm], [hành động]
```

---

## 🔢 QUY TẮC 8 GIÂY

| Tone | Tốc độ | Max từ |
|------|--------|--------|
| Hào hứng | 4 từ/s | 32 từ |
| Bình thường | 3 từ/s | 24 từ |
| Nghiêm túc | 2.5 từ/s | 20 từ |
 
 ---
 
 ## 🎙️ ĐỊNH DẠNG THOẠI NGHIÊM NGẶT (E19)
 
 1. **KHÔNG DÙNG `?`**: "Sao lại thế?" ❌ → "Lý do là vì..." ✅
 2. **KHÔNG CÂU CỤT**: "Hỏng." ❌ → "Bánh sẽ bị hỏng hoàn toàn." ✅
 3. **KHÔNG DẤU NỐI `-`**: "A-xít" ❌ → "A xít" ✅
 4. **SỐ RA CHỮ**: "1-2 ngày" ❌ → "một đến hai ngày" ✅


---

## 📁 CẤU TRÚC THƯ MỤC

```
📁 [Số]_[Tên_Topic]/
   ├── [Số]_Bible.md
   ├── [Số]_Master.txt
   ├── [Số]_Prompts.txt
   └── [Số]_Dubbing.txt
```

---

## 🛡️ TUÂN THỦ NỀN TẢNG (Platform Compliance)
1. **AI Labeling (E20)**: Bắt buộc tích "Altered content/AI-generated" khi upload.
2. **Medical Disclaimer (E21)**: Bắt buộc có dòng miễn trừ trách nhiệm trong mô tả.
3. **Personal Attributes (E22)**: Tránh zoom cận cảnh vào khuyết điểm cơ thể người thật (mụn, mỡ).

---

## 🎥 QUAY PHIM ĐIỆN ẢNH (E23) - CHEAT SHEET
| Hiệu ứng | Prompt Keyword | Dùng khi nào |
|----------|----------------|--------------|
| **Kịch tính** | `Slow dolly in` | Hook, soi chi tiết |
| **Kết thúc** | `Slow pull out` | Mở rộng bối cảnh |
| **Theo dõi** | `Tracking shot` | Nhân vật di chuyển |
| **Toàn diện** | `Orbit shot` | Giới thiệu nhân vật |
| **Bất an** | `Dutch angle` | Nguy hiểm, cảnh báo |
| **Quyền lực** | `Low angle shot` | Villain, Hero |

---

## 🚀 VIRAL RETENTION (E24)
- **3 Giây Đầu**: Phải có Movement nhanh + SFX lớn.
- **Mỗi 3-5s**: Đổi góc quay (Wide -> Close) hoặc đổi hành động.
- **Satisfying**: Dùng hình ảnh đối xứng, làm sạch, lấp đầy.

---

## 🧵 GHÉP NỐI LIỀN MẠCH (E31) - LONG FORM
| Kỹ thuật | Cách dùng Prompt nối tiếp |
|----------|---------------------------|
| **End-Start** | Clip sau mô tả lại TƯ THẾ KẾT THÚC của clip trước |
| **Mid-action** | Dùng từ `mid-air`, `blur`, `moving` để bảo toàn quán tính |
| **Whip Pan** | Kết Clip 1: `whip pan right blur`. Đầu Clip 2: `blur to sharp` |
| **Object Pass** | Kết Clip 1: `blocked by back`. Đầu Clip 2: `reveal new scene` |

---

## 🎣 BỘ TỨ SIÊU HOOK (E32) - DÙNG CHO 3S ĐẦU
| Loại Hook | Kỹ thuật (Keyword/Cách dùng) |
|-----------|------------------------------|
| **VISUAL** | `Breaking 4th Wall` (Gõ màn hình), `Reverse Motion`, `Macro Reveal` |
| **VOICE** | `The Whisper` (Thì thầm), `The Glitch` (Vấp), `Fast Pacing` (Liên thanh) |
| **DIALOGUE**| "Đừng bao giờ...", "Bí mật mà...", "Sự thật về...", "Đố bạn..." |
| **SFX** | `Snap` (Búng tay), `Silence Cut` (Tắt tiếng), `ASMR` (Nhai/Rót) |

---





**© 2026 - Veo 3 Production System**
