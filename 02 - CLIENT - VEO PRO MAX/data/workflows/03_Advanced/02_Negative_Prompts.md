# NEGATIVE PROMPT TEMPLATE - LÀM CHỦ NEGATIVE PROMPT

## Cẩm nang xử lý lỗi "quái dị" cho video AI chuyên nghiệp

**Phiên bản**: 1.0  
**Cập nhật**: 2026-01-29  
**Áp dụng**: Google Veo, Pika, Runway và các AI Video khác

---

## 🎯 VŨ KHÍ CỦA BẠN: NEGATIVE PROMPT

> [!IMPORTANT]
> Thay vì chỉ mô tả những gì bạn **muốn** thấy, hãy ra lệnh cho AI về những gì bạn **không muốn** thấy.
> Đây là chìa khóa để kiểm soát và loại bỏ các yếu tố không mong muốn, giúp video của bạn trở nên sạch, đẹp và chuyên nghiệp.

### So sánh: Prompt Thuần túy vs Prompt + Negative

| Cách tiếp cận | Prompt | Kết quả |
|---------------|--------|---------|
| ❌ **Prompt Thuần túy** | `"a ceramic vase"` | Bình bị méo, tay cầm biến dạng |
| ✅ **Prompt + Negative** | `"a ceramic vase"` + `"no warped handle, no asymmetrical shape"` | Bình hoàn hảo, cân đối |

---

## 🔧 KỸ THUẬT #1: CẤM DỊ DẠNG HÌNH HỌC

### Lỗi thường gặp ❌

- Chân dài không đều, tay mọc thêm khối lạ
- Các góc polygon bị méo, khớp xương bị xoắn
- Cơ thể bị biến dạng khi di chuyển

### Câu Negative Prompt ✅

```
no deformed limbs
no warped geometry
no twisted joints
no melted shapes
```

### Cách sử dụng trong prompt:

```
[Main prompt]..., no deformed limbs, no warped geometry, no twisted joints, no melted shapes, no text, no subtitles, no labels, no watermarks.
```

---

## 🔧 KỸ THUẬT #2: CẤM "THÊM TAY - THÊM CHÂN - THÊM NGÓN"

### Lỗi thường gặp ❌

- AI "sáng tạo" quá mức, tạo ra tay mọc thêm
- Chân nhân đôi
- Các ngón tay thừa (6-7 ngón)

> [!WARNING]
> **Ghi chú**: Cực kỳ cần thiết cho các video theo phong cách **anime**, **action**, và **lowpoly**.

### Câu Negative Prompt ✅

```
no extra arms, no extra legs
no additional fingers
no duplicated limbs
```

### Cách sử dụng trong prompt:

```
[Main prompt]..., no extra arms, no extra legs, no additional fingers, no duplicated limbs, no text, no subtitles, no labels, no watermarks.
```

---

## 🔧 KỸ THUẬT #3: CẤM LỖI KHUÔN MẶT & BIỂU CẢM

### Lỗi thường gặp ❌

- Mặt méo, mắt lệch
- Mũi bị phồng
- Miệng dính vào nhau
- Đây là lỗi **phá hủy cảm xúc** của cảnh quay

### Câu Negative Prompt ✅

```
no distorted faces
no asymmetrical eyes
no fused lips
no stretched facial features
```

### Cách sử dụng trong prompt:

```
[Main prompt]..., no distorted faces, no asymmetrical eyes, no fused lips, no stretched facial features, no text, no subtitles, no labels, no watermarks.
```

---

## 📋 BẢNG TỔ HỢP NEGATIVE PROMPT THEO LOẠI LỖI

| Loại lỗi | Negative Prompt |
|----------|-----------------|
| **Hình học** | `no deformed limbs, no warped geometry, no twisted joints, no melted shapes` |
| **Thêm bộ phận** | `no extra arms, no extra legs, no additional fingers, no duplicated limbs` |
| **Khuôn mặt** | `no distorted faces, no asymmetrical eyes, no fused lips, no stretched facial features` |
| **Bắt buộc (mọi prompt)** | `no text, no subtitles, no labels, no watermarks` |

---

## 🎬 TEMPLATE NEGATIVE PROMPT ĐẦY ĐỦ

### Cho video Realistic/Cinematic:

```
no deformed limbs, no warped geometry, no twisted joints, no melted shapes, 
no extra arms, no extra legs, no additional fingers, no duplicated limbs, 
no distorted faces, no asymmetrical eyes, no fused lips, no stretched facial features, 
no text, no subtitles, no labels, no watermarks
```

### Cho video Anime/Lowpoly (cần thêm):

```
no deformed limbs, no warped geometry, no twisted joints, no melted shapes, 
no extra arms, no extra legs, no additional fingers, no duplicated limbs, 
no distorted faces, no asymmetrical eyes, no fused lips, no stretched facial features, 
no color shifts, no texture distortion,
no text, no subtitles, no labels, no watermarks
```

---

## ✅ CHECKLIST NEGATIVE PROMPT (Part 1)

- [ ] Có negative prompt cho **hình học** (limbs, geometry, joints)
- [ ] Có negative prompt cho **bộ phận thừa** (extra arms, fingers)
- [ ] Có negative prompt cho **khuôn mặt** (faces, eyes, lips)
- [ ] Có negative prompt **bắt buộc** (no text, no subtitles...)
- [ ] Negative prompt đặt ở **cuối prompt**, trước dấu chấm

---

# PHẦN 2: KỸ THUẬT NÂNG CAO

---

## 🔧 KỸ THUẬT #4: CẤM LỖI HÒA TRỘN CHẤT LIỆU

### Lỗi thường gặp ❌

- Màu sắc dính vào nhau, texture bị nhòe (blur)
- Các vật thể trông như đang tan chảy
- **Đặc biệt phổ biến** với phong cách lowpoly hoặc đồ chơi nhựa

### Câu Negative Prompt ✅

```
no texture bleeding
no color smearing
no melting textures
no glossy plastic reflection (nếu muốn hiệu ứng matte)
```

### Cách sử dụng trong prompt:

```
[Main prompt]..., no texture bleeding, no color smearing, no melting textures, no text, no subtitles, no labels, no watermarks.
```

---

## 🔧 KỸ THUẬT #5: CẤM AI "BỊA THÊM" PHỤ KIỆN & CHI TIẾT

### Lỗi thường gặp ❌

- Google Veo đôi khi tự động thêm các chi tiết không có trong prompt:
  - Khăn quàng
  - Dây thừng
  - Logo
  - Các họa tiết lạ
- Làm nhân vật mất tính nhất quán (continuity)

> [!WARNING]
> **Ghi chú**: Quan trọng khi tạo nhân vật theo phong cách **Disney**, **Anime**, hoặc **Plastic Toy**.

### Câu Negative Prompt ✅

```
no extra accessories
no random objects
no unwanted patterns
```

### Cách sử dụng trong prompt:

```
[Main prompt]..., no extra accessories, no random objects, no unwanted patterns, no text, no subtitles, no labels, no watermarks.
```

---

## 🔧 KỸ THUẬT #6: CẤM ĐỔI MÀU & CHẤT LIỆU GIỮA CÁC CẢNH

### Lỗi thường gặp ❌

- Cảnh 1 áo màu xanh → cảnh 2 biến thành xanh neon
- Chất liệu từ matte chuyển thành glossy
- Đây là **lỗi continuity** mà ai cũng sợ

> [!TIP]
> **Mẹo chuyên nghiệp**: Kết hợp các lệnh này với mô tả mã màu HEX trong prompt chính để đạt độ ổn định 95-100%.

### Câu Negative Prompt ✅

```
no color shifts
no inconsistent materials
no lighting inconsistencies
```

### Cách sử dụng trong prompt:

```
[Main prompt with HEX colors]..., no color shifts, no inconsistent materials, no lighting inconsistencies, no text, no subtitles, no labels, no watermarks.
```

---

## ⚠️ SAI LẦM PHỔ BIẾN: NHỒI NHÉT QUÁ NHIỀU CÂU LỆNH

> [!CAUTION]
> Một negative prompt dài 20-30 dòng không phải lúc nào cũng tốt.
> Việc đưa vào quá nhiều lệnh cấm riêng lẻ có thể khiến AI "bối rối", dẫn đến kết quả không thể đoán trước và làm giảm hiệu quả của các lệnh quan trọng.

| ❌ KHÔNG HIỆU QUẢ | ✅ HIỆU QUẢ |
|-------------------|------------|
| Danh sách dài 30 dòng lộn xộn | Nhóm theo 3 "khóa" chính |
| AI bị overload | AI tập trung vào ưu tiên |

**Cần một cách tiếp cận thông minh hơn là chỉ thêm vào một danh sách dài.**

---

## 🔐 HỆ THỐNG TỐI ƯU: 3 "KHÓA" QUAN TRỌNG

> [!IMPORTANT]
> Thay vì một danh sách dài, hãy nhóm các negative prompt thành **3 "khóa" chính**.
> Cách tiếp cận này ngắn gọn, rõ ràng, tập trung và **hiệu quả hơn gấp đôi**.

### 🦴 GEOMETRY LOCK (Khóa Hình Học)

**Mục đích**: Bảo vệ cấu trúc cơ thể

```
no deformed limbs, no extra fingers, no warped joints
```

### 👤 FACE LOCK (Khóa Khuôn Mặt)

**Mục đích**: Bảo vệ khuôn mặt và biểu cảm

```
no distorted faces, no asymmetrical eyes, no fused features
```

### 🎨 MATERIAL LOCK (Khóa Chất Liệu)

**Mục đích**: Bảo vệ màu sắc và texture

```
no melting textures, no color shifts, no texture bleeding
```

---

## 📋 BẢNG TỔ HỢP 3 KHÓA (KHUYẾN NGHỊ)

| Khóa | Negative Prompt | Khi nào dùng |
|------|-----------------|--------------|
| **Geometry Lock** | `no deformed limbs, no extra fingers, no warped joints` | Mọi video có nhân vật |
| **Face Lock** | `no distorted faces, no asymmetrical eyes, no fused features` | Close-up, biểu cảm |
| **Material Lock** | `no melting textures, no color shifts, no texture bleeding` | Lowpoly, Plastic Toy, Anime |

---

## 🎬 TEMPLATE TỐI ƯU (3-LOCK SYSTEM)

### Template Ngắn Gọn (Khuyến nghị):

```
[Main prompt with Character Profile Lock + HEX colors]..., 
no deformed limbs, no extra fingers, no warped joints, 
no distorted faces, no asymmetrical eyes, no fused features, 
no melting textures, no color shifts, no texture bleeding, 
no text, no subtitles, no labels, no watermarks.
```

### Template Đầy Đủ (Khi cần chi tiết hơn):

```
[Main prompt]..., 
no deformed limbs, no warped geometry, no twisted joints, no melted shapes, 
no extra arms, no extra legs, no additional fingers, no duplicated limbs, 
no distorted faces, no asymmetrical eyes, no fused lips, no stretched facial features, 
no texture bleeding, no color smearing, no melting textures, 
no color shifts, no inconsistent materials, no lighting inconsistencies, 
no extra accessories, no random objects, no unwanted patterns, 
no text, no subtitles, no labels, no watermarks.
```

---

## ✅ CHECKLIST NEGATIVE PROMPT HOÀN CHỈNH

### Part 1: Cơ bản
- [ ] Có negative prompt cho **hình học** (limbs, geometry, joints)
- [ ] Có negative prompt cho **bộ phận thừa** (extra arms, fingers)
- [ ] Có negative prompt cho **khuôn mặt** (faces, eyes, lips)

### Part 2: Nâng cao
- [ ] Có negative prompt cho **chất liệu** (texture, color smearing)
- [ ] Có negative prompt cho **phụ kiện thừa** (accessories, patterns)
- [ ] Có negative prompt cho **continuity** (color shifts, materials)

### Bắt buộc
- [ ] Có negative prompt **bắt buộc** cuối cùng (no text, no subtitles...)
- [ ] Đã nhóm theo **3-Lock System** để tối ưu
- [ ] Không nhồi nhét quá nhiều (max 15-20 items)

---

*Negative Prompt Template v1.1 - 2026-01-29 - Complete with 3-Lock System*

