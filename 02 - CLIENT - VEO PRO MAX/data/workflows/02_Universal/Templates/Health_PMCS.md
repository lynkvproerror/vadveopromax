---
template_id: "health_pmcs"
display_name: "Health PMCS"
group: "health"
keywords: [sức khỏe, health, y tế, bệnh, thuốc, thảo dược, gan, thận, tim, phổi, dinh dưỡng, vitamin, triệu chứng, khoa học]
visual_style: "3D Pixar Animation"
structure: "pmcs"
scene_count_range: [8, 12]
output_files: [Bible, Master, Prompts, Dubbing, SEO]
shared_rules: [01_Technical_Rules, 03_Quality_Checklist, 04_Master_Format, 05_Prompts_Format, 06_Dubbing_Format, 07_SEO_Format]
advanced_rules: [02_Negative_Prompts, 03_Dialogue_Scene, 05_Prompt_Adherence, 07_Golden_Phrases, 08_Character_Scale]
---

# BIBLE TEMPLATE - FORMAT CHUẨN

> **MỤC ĐÍCH**: Template chuẩn cho file `_Bible.md` - Đảm bảo đầy đủ thông tin cho Master và Prompts
> **COPY template này khi tạo topic mới, điền thông tin vào [...]**

---

## 1. THÔNG TIN KHOA HỌC (Scientific Research)

### Nguồn tham khảo:
- [Nguồn 1: WHO/CDC/Bộ Y tế...]
- [Nguồn 2]
- [Nguồn 3]

### Số liệu chính (5-7 số):
- [Số liệu 1 + nguồn]
- [Số liệu 2 + nguồn]
- [Số liệu 3 + nguồn]
- [Số liệu 4 + nguồn]
- [Số liệu 5 + nguồn]

### Key facts:
1. **[Fact 1]** - [Mô tả ngắn]
2. **[Fact 2]** - [Mô tả ngắn]
3. **[Fact 3]** - [Mô tả ngắn]

---

## 2. NHÂN VẬT (Character Bible) - COPY-PASTE CHÍNH XÁC SANG MASTER/PROMPTS

### Nhân vật chính: [TÊN]
- **Mô tả đầy đủ** (COPY-PASTE):
  ```
  [An anthropomorphic [màu-sắc] [hình-dạng] with simple dot eyes 
  showing [biểu-cảm], curved [kiểu-mouth] mouth, [chi-tiết-thêm]]
  ```
- **Tính cách**: [...]
- **Visual cue**: [Mồ hôi, khói, ánh sáng...]

### Nhân vật phụ: [TÊN]
- **Mô tả đầy đủ** (COPY-PASTE):
  ```
  [...]
  ```

### Nhân vật phản diện: [TÊN]
- **Mô tả đầy đủ** (COPY-PASTE):
  ```
  [...]
  ```

---

## 3. CHỦ THỂ/VẬT CHỦ (Host/Subject) - BẮT BUỘC khi nhân hóa nội tạng

### Mô tả cơ bản (COPY-PASTE khi cần hiển thị người):
```
[A middle-aged Asian [man/woman], [age]s, [body-type], 
wearing [trang-phục]]
```

### Trạng thái bình thường:
```
[Healthy pink skin, bright eyes, alert expression]
```

### Trạng thái triệu chứng (COPY-PASTE vào Consequence scenes):
| Triệu chứng | Mô tả tiếng Anh |
|-------------|-----------------|
| Vàng da | `Yellowish skin, yellow-tinted eyes, tired dark circles` |
| Phù mặt | `Puffy face, swollen ankles, pale complexion` |
| Mệt mỏi | `Exhausted expression, droopy posture, dark circles` |
| [Thêm...] | [...] |

---

## 4. BỐI CẢNH (Setting Bible) - COPY-PASTE CHÍNH XÁC

### Cảnh 1: [Tên cảnh]
```
[Mô tả setting, ánh sáng, màu sắc - COPY-PASTE vào Master/Prompts]
```

### Cảnh 2: [Tên cảnh]
```
[...]
```

### Cảnh 3: [Tên cảnh]
```
[...]
```

## 5. CHUYÊN GIA (Expert/Doctor) - E17

### Mô tả chuẩn (COPY-PASTE):
```
A professional [male/female] doctor, [35s/40s], wearing white coat, 
confident expression, [holding relevant item]
```

### Voice chuẩn hóa (LUÔN DÙNG cho Expert):
```
[Giọng: Miền Nam, 35 tuổi]
```

> **Lưu ý (2026)**: Giới tính xác định trong mô tả nhân vật, Tone mô tả trong visual prompt.

---

## 6. VOICE & STYLE

### Tone giọng chung:
- **Phong cách**: [Hài hước + Cảnh báo / Nghiêm túc + Giáo dục / ...]
- **Nhịp độ**: [Nhanh khi hành động, chậm khi cảnh báo]

### Voice Consistency (E18) - Giữ nguyên voice cho cùng nhân vật:
| Nhân vật | Voice xuyên video | Format |
|----------|-------------------|--------|
| Chủ thể | ✅ Cùng | `[Giọng: Vùng, Tuổi]` |
| NV Chính | ✅ Cùng | `[Giọng: Vùng, Tuổi]` |
| NV Phụ | ⚠️ Khác để phân biệt | Khác Vùng hoặc Tuổi |
| Expert | ✅ CHUẨN HÓA | `[Giọng: Miền Nam, 35 tuổi]` |

### Voice Metadata theo Scene:
| Scene | Nhân vật | Voice |
|-------|----------|-------|
| Opening | Chủ thể / NV Chính | [Tò mò/Lo lắng] |
| Mechanism | NV Chính | [Nghiêm trọng/Hoảng loạn] |
| Consequence | NV Chính | [Đau đớn/Cảnh báo] |
| Solution | EXPERT | Nữ 35s Chuyên nghiệp |

---

## 7. VISUAL STYLE - COPY-PASTE làm prefix mỗi prompt

### Style chọn (copy 1):
```
The 3D cute animation style, Pixar render, soft lighting, vibrant colors
```

---

## 8. CHUYỂN CẢNH DỰ KIẾN

| Từ cảnh | Sang cảnh | Kỹ thuật |
|---------|-----------|----------|
| Opening (bên ngoài) | Mechanism (bên trong) | [Zoom In / Match Cut] |
| Mechanism (nội tạng) | Consequence (người) | [Split Screen / Zoom Out] |
| Consequence | Solution | [Wipe / Fade] |

---

## 9. CẤU TRÚC PMCS

### P (Problem):
[Hook gây sốc, gợi tò mò - 1-2 câu]

### M (Mechanism):
[Cơ chế khoa học - có số liệu]
- Bước 1: [...]
- Bước 2: [...]
- Bước 3: [...]

### C (Consequence):
[Hậu quả - PHẢI hiển thị trên CHỦ THỂ!]
- [Triệu chứng 1] → [Mô tả trên người]
- [Triệu chứng 2] → [Mô tả trên người]

### S (Solution):
1. [Giải pháp 1 - cụ thể]
2. [Giải pháp 2 - cụ thể]
3. [Giải pháp 3 - cụ thể]

---

## 10. TIÊU ĐỀ A/B/C (E13)

| Loại | Tiêu đề |
|------|---------|
| A (Số liệu) | **"[Số] + [Kết quả sốc]!"** |
| B (Fear) | **"[Hành động] = [Hậu quả đáng sợ]!"** |
| C (Listicle) | **"[Số] [loại] + [kết quả]!"** |

---

*Template version: 2.1 - Updated: 2026-02-05 - Voice format 2026*
