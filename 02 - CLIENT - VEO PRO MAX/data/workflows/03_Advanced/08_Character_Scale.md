# KHÓA TỶ LỆ NHÂN VẬT (CHARACTER SCALE LOCK)

## Giải Pháp Cho Vấn Đề "Phình To, Teo Nhỏ"

**Phiên bản**: 1.0  
**Cập nhật**: 2026-01-30  
**Nguồn**: VEO3.1 AI Video Prompting Masterclass

---

## 🎯 VẤN ĐỀ PHỔ BIẾN NHẤT TRONG VIDEO AI

> [!WARNING]
> **TẠI SAO NHÂN VẬT AI CỦA BẠN CỨ "PHÌNH TO, TEO NHỎ"?**
> 
> Thất bại phổ biến nhất trong video AI—và cách khắc phục bằng tư duy của một đạo diễn.

---

## 🔍 THE GLITCH vs THE VISION

| ❌ THE GLITCH | ✅ THE VISION |
|---------------|---------------|
| Lỗi Phình Teo | Tầm Nhìn Nhất Quán |
| Nhân vật thay đổi kích thước giữa các cảnh | Nhân vật giữ nguyên tỷ lệ xuyên suốt |
| Trang phục, màu sắc, chi tiết hỗn loạn | Chi tiết nhất quán, ổn định |
| Chỉ qua một cảnh mới, họ lập tức biến dạng | Mượt mà, liền mạch |

**Vấn đề không nằm ở prompt mô tả của bạn.**

---

## 🎬 BÍ MẬT: VEO "NGHE" NGÔN NGỮ MÁY QUAY

> **Camera Grammar > Character Description**

### Veo 3.1 Ưu Tiên Gì?

Veo 3.1 ưu tiên phân tích các lệnh về **điện ảnh (cinematography grammar)** trước tiên:

```
Mô Tả Nhân Vật ──────────► Lệnh Điện Ảnh ──────────► Video Output
(Thứ yếu)                   (Ưu tiên)
```

---

### 🔑 INSIGHT THEN TRỌNG:

> **Các yếu tố như shot type, composition, lens & focus quyết định đến 80% cảm nhận về "độ lớn" của nhân vật trong khung hình.**

Khi bạn thay đổi shot từ:
- `wide` → `medium` → `close-up`

AI sẽ tuân thủ lệnh máy quay đó, và điều này **vô tình làm thay đổi kích thước nhân vật**.

---

## 💡 NGUYÊN TẮC CỐT LÕI

> **Đừng ra lệnh như một nhà văn. Hãy chỉ đạo như một đạo diễn.**

Để làm chủ sự nhất quán, bạn cần **cảm tách máy quay AI**. Đây là cách.

---

# 🎯 5 QUY TẮC VÀNG ĐỂ "KHÓA TỶ LỆ" (SCALE LOCK)

## Bộ Quy Tắc Của Đạo Diễn AI Để Kiểm Soát Hoàn Toàn Kích Thước Nhân Vật

---

## QUY TẮC #1: CHỌN MỘT SHOT TYPE CỐ ĐỊNH CHO TỪNG PHÂN ĐOẠN

> **Veo hiểu rất rõ các shot type (wide, medium, close-up) và sẽ bám sát chúng.**

### ⚠️ NGUYÊN NHÂN CHÍNH:

**Việc nhảy shot liên tục là nguyên nhân chính gây ra "size-drift".**

---

### ✅ GIẢI PHÁP:

Nếu bạn muốn nhân vật giữ đúng tỷ lệ trong **3-5 cảnh**, hãy **giữ nguyên một shot type xuyên suốt**.

**Ví dụ:**
- Luôn là `medium full-body`
- Hoặc luôn là `medium close-up`

---

### 📋 SO SÁNH: DON'T vs DO

#### ❌ DON'T: Nhảy Shot Loạn Xạ

```
Scene 1: "Wide shot of a character in the desert..."
Scene 2: "Extreme close-up on her face..."
Scene 3: "Medium shot of the character walking..."
```

**Kết quả**: Kích thước nhảy lung tung giữa các cảnh

---

#### ✅ DO: Giữ Nguyên Shot Type

```
Scene 1: "Medium full-body shot of a character (age 28, blue jacket) 
         standing in the desert..."
         
Scene 2: "Medium full-body shot of the same character (age 28, blue jacket) 
         walking forward..."
         
Scene 3: "Medium full-body shot of the same character (age 28, blue jacket) 
         looking at the horizon..."
```

**Kết quả**: Nhân vật nhất quán về tỷ lệ và chi tiết

---

## QUY TẮC #2: CHỈ ĐỊNH RÕ RÀNG FRAMING (BỐ CỤC KHUNG HÌNH)

> **Một 'medium shot' có thể có nhiều biến thể. Hãy khóa chặt ý đồ của bạn bằng cách chỉ định rõ cách nhân vật được đóng khung.**

---

### 📐 CÁC LỰA CHỌN FRAMING CHO "MEDIUM SHOT":

| Framing Option | Mô Tả | Ứng Dụng |
|----------------|-------|----------|
| **`full-body in frame`** | Toàn thân trong khung hình | Cảnh thiết lập, hành động toàn thân |
| **`waist-up`** | Từ thắt lưng trở lên | Hội thoại, tương tác chính |
| **`head-and-shoulders`** | Từ vai trở lên | Cận cảnh cảm xúc, tiết lộ quan trọng |
| **`consistent headroom`** | Giữ khoảng trống trên đầu không đổi | Duy trì nhất quán giữa các cảnh |

---

### ✅ CÁCH VIẾT CHUẨN:

```
"Medium full-body shot, the character fills 60% of frame height, 
consistent headroom and footroom, centered composition..."
```

---

### 🎯 BẢNG THAM KHẢO % KHUNG HÌNH:

| Shot Type | % Khung Hình | Mô Tả |
|-----------|--------------|-------|
| **Wide Shot** | 20-40% | Nhân vật nhỏ, môi trường lớn |
| **Medium Full-Body** | 50-60% | Toàn thân, khoảng trống đầu/chân nhất quán |
| **Medium Waist-Up** | 60-70% | Từ thắt lưng trở lên |
| **Close-up** | 70-90% | Chỉ có đầu và vai |
| **Extreme Close-up** | 90-100% | Chỉ có mặt hoặc chi tiết |

---

## QUY TẮC #3: GIỮ CHUYỂN ĐỘNG CAMERA ĐƠN GIẢN (HOẶC TĨNH)

> **Khi bạn yêu cầu quá nhiều chuyển động cùng lúc (ví dụ: orbit + dolly + zoom), Veo có thể ưu tiên "giữ cho cảnh đẹp" hơn là "giữ đúng tỷ lệ nhân vật". Điều này dẫn đến việc nhân vật bị co giãn theo nhịp chuyển động.**

Chỉ chọn **một chuyển động chính cho mỗi cảnh 8 giây**. Các lệnh như `static tripod`, `slow tracking`, hoặc `slow dolly` là những lựa chọn an toàn nhất để tránh AI tự động zoom.

---

### 📊 SO SÁNH: PHỨC TẠP vs ĐƠN GIẢN

| ❌ PHỨC TẠP (Nguy Hiểm) | ✅ ĐƠN GIẢN (An Toàn) |
|------------------------|----------------------|
| `orbit + dolly + zoom` | `slow tracking` |
| `360° crane move` | `static tripod` |
| `handheld + pan` | `slow dolly-in` |
| `dynamic rotation` | `gentle tilt up/down` |

---

### ✅ PROMPT MẪU:

```
"Static tripod (or slow tracking), medium shot, 
a character (age 28, blue jacket) stands in frame, 
minimal movement, character stays the same size in frame..."
```

---

## QUY TẮC #4: CHỐT LENS & FOCUS ĐỂ TRÁNH MÉO HÌNH

> **Các lựa chọn về lens và focus có thể tạo ra cảm giác méo hình, làm nhân vật trông to hoặc nhỏ hơn một cách bất thường. Sự nhất quán là chìa khóa.**

### ⚠️ CÁC LỖI VỀ MÉO HÌNH THƯỜNG GẶP:

| Kỹ Thuật | Hiệu Ứng | Khi Nào Dùng |
|----------|---------|-------------|
| **`wide-angle lens`** | Nhân vật ở gần camera trông 'to bất thường' | Chỉ khi bạn muốn hiệu ứng méo hình |
| **`shallow depth of field`** (camera gần) | Sẽ làm khuôn mặt 'chiếm trọn khung hình' | Chỉ khi bạn muốn close-up cảm xúc |

---

### ✅ CHIẾN LƯỢC:

Nếu mục tiêu là **tỷ lệ ổn định**, hãy **giữ nguyên các thiết lập về lens/focus giữa các cảnh**.

**Ví dụ:**
- Luôn dùng `deep focus` hoặc luôn dùng `shallow depth of field` với khoảng cách camera tương tự.

---

### 🎯 MẸO MINH HỌA HIỆU ỨNG:

```
┌─────────────────────┐        ┌─────────────────────┐
│  WIDE-ANGLE LENS    │        │  SHALLOW DOF (NEAR) │
│  (Hiệu ứng méo)     │        │  (Khuôn mặt chiếm   │
│                     │        │   trọn khung hình)  │
│    🧍 ← To bất      │        │       👁️👃👁️        │
│       thường        │        │                     │
└─────────────────────┘        └─────────────────────┘
```

---

### 📋 BẢNG THAM KHẢO LENS:

| Lens | Focal Length | Perspective | Sử Dụng Khi |
|------|--------------|-------------|-------------|
| **Wide Lens** | 24mm-35mm | Môi trường rộng, biến dạng nhẹ ở rìa | Establishing shot |
| **Normal Lens** | 50mm | Tự nhiên, gần với mắt người | Dialogue, medium shot |
| **Telephoto** | 85mm-135mm | Nén không gian, bokeh đẹp | Portrait, close-up |

---

## QUY TẮC #5: THÊM "MỐC TỶ LỆ" VÀO KHUNG HÌNH

> **"Tỷ lệ không chỉ là về nhân vật—mà là về mối quan hệ giữa nhân vật và đồ vật xung quanh."**

---

### 🔑 INSIGHT:

Đặt một **vật thể có kích thước không đổi** (cửa ra vào, bàn, ghế, lan can) trong cảnh. AI sẽ sử dụng vật thể đó làm **mốc tham chiếu để giữ cho tỷ lệ nhân vật của bạn ổn định**.

---

### 🎯 ACTION - MỐC TỶ LỆ:

Thêm một **vật thể có kích thước cố định** vào prompt:

```
"Medium shot, a woman (age 28, 165cm tall) stands next to a 
standard wooden door (2m height), her hand near the doorknob..."
```

---

### 📝 PROMPT EXAMPLES:

**Example 1:**
```
"a woman stands next to a standard door, her hand near the doorknob"
```

**Example 2:**
```
"a man sits at a small café table, the chair is visible full frame"
```

---

### ✅ CÁC ANCHOR OBJECT TỐT:

| Object | Kích Thước Chuẩn | Ưu Điểm |
|--------|------------------|---------|
| **Cửa ra vào** | ~2m chiều cao | Quen thuộc, dễ nhận diện |
| **Bàn làm việc** | ~75cm chiều cao | Phổ biến, ổn định |
| **Ghế** | ~45cm chiều cao (ngồi) | Tham chiếu rõ ràng |
| **Lan can** | ~1m chiều cao | Thường thấy trong cảnh outdoor |
| **Xe hơi** | ~1.5m chiều cao | Kích thước rõ ràng |
| **Cây cột điện** | ~10m | Tham chiếu quy mô lớn |

---

# 🎯 CASE STUDY: ÁP DỤNG 5 QUY TẮC VÀO THỰC TẾ

## Cùng Xem Cách Chúng Ta Giữ Ổn Định Tỷ Lệ Nhân Vật Qua 3 Cảnh 8 Giây

### 📋 THE SETUP

**Mục tiêu (Objective):** Một nhân vật nữ bước đến và mở cửa, giữ nguyên kích thước cơ thể.

**Chiến lược (Strategy):** Áp dụng các quy tắc Scale Lock

| Quy Tắc | Áp Dụng |
|---------|---------|
| ✅ **Shot Type Cố Định** | `Medium full-body` |
| ✅ **Framing Cố Định** | Luôn thấy toàn thân |
| ✅ **Camera Move Đơn Giản** | `Static` và `Slow tracking` |
| ✅ **Lens Nhất Quán** | `50mm, deep focus` |
| ✅ **Mốc Tỷ Lệ (Anchor)** | Cánh cửa |

---

### 🎬 KẾT QUẢ: MỘT CHUỖI CẢNH MƯỢT MÀ, NHẤT QUÁN

#### SCENE 1: Thiết Lập
```
Prompt: "Medium full-body shot, static camera, 50mm lens, 
a woman (age 28, green jacket, dark jeans) stands in an empty room 
next to a standard wooden door (2m height), consistent headroom..."
```
**Hành động:** Nhân vật đứng cạnh cửa.

---

#### SCENE 2: Chuyển Động
```
Prompt: "Medium full-body shot, slow tracking, 50mm lens, 
the same woman (age 28, green jacket, dark jeans) walks 2 steps forward, 
the door stays in frame, consistent headroom..."
```
**Hành động:** Nhân vật bước 2 bước, cửa vẫn ở nền.

---

#### SCENE 3: Kết Thúc
```
Prompt: "Medium full-body shot, static camera, 50mm lens, 
the same woman (age 28, green jacket, dark jeans) stops and reaches 
her hand toward the door handle, consistent headroom..."
```
**Hành động:** Nhân vật dừng lại, đưa tay lên tay nắm cửa.

---

### ✅ KẾT LUẬN

> **Thành công!** Bởi vì **shot type, framing, và mốc tỷ lệ (cửa)** không đổi, nhân vật đã không bị 'phình/teo' giữa các cảnh.

---

### 💡 BẠN KHÔNG CHỈ ĐANG VIẾT PROMPT. BẠN ĐANG ĐẠO DIỄN.

> Chào mừng đến với kỷ nguyên mới của sáng tạo video AI.

---

# 📝 CHECKLIST KHÓA TỶ LỆ NHÂN VẬT

✅ Đã chọn **một shot type cố định** cho cả chuỗi cảnh?

✅ Đã chỉ định **% khung hình** nhân vật chiếm?

✅ Đã giữ **camera move đơn giản** (static/pan/tilt)?

✅ Đã dùng **cùng một lens** (50mm, 85mm,...)?

✅ Đã thêm **anchor object** (cửa, bàn, xe,...)?

✅ Đã mô tả **chi tiết nhất quán** (tuổi, trang phục, màu sắc)?

---

---

# 🎬 BỘ CÔNG CỤ CỦA ĐẠO DIỄN: TEMPLATE PROMPT "SCALE LOCK"

## Copy-Paste Và Tùy Chỉnh Nội Dung Trong Ngoặc Đề Bắt Đầu

```
Cinematography: Medium full-body shot, eye-level, static tripod (or slow tracking), 
                consistent headroom and footroom, character stays the same size in frame.
                
Lens & focus: (same lens/focus each scene, e.g., deep focus), no zoom.

Subject: (character description + outfit + colors).

Action: (one main action).

Context: (same location cues + 1 anchor object like a door/table).

Style: (same style).

Negative: no auto zoom, no size changes, no distorted anatomy, no extra people, 
          no text overlay.
```

### 💡 LƯU Ý:

> Phần **'Cinematography/shot specification'** là quan trọng nhất. Đây là phần thiết lập khung hình để AI bám theo ý đồ của bạn.

---

# 🎬 VÍ DỤ PROMPT HOÀN CHỈNH

## ✅ CHUỖI 3 CẢNH NHẤT QUÁN

### Scene 1:
```
"Medium full-body shot, static camera, 50mm lens, 
a woman (age 28, 165cm, wearing blue denim jacket, brown hair in ponytail) 
stands next to a standard wooden door (2m height), 
she fills 60% of frame height, centered composition, 
soft natural lighting..."
```

### Scene 2:
```
"Medium full-body shot, static camera, 50mm lens, 
the same woman (age 28, 165cm, blue denim jacket, brown hair in ponytail) 
walks toward the door and reaches for the handle, 
she fills 60% of frame height, centered composition, 
soft natural lighting..."
```

### Scene 3:
```
"Medium full-body shot, static camera, 50mm lens, 
the same woman (age 28, 165cm, blue denim jacket, brown hair in ponytail) 
opens the door and steps through, 
she fills 60% of frame height, centered composition, 
soft natural lighting..."
```

---

## 🔗 LIÊN KẾT VỚI CÁC TEMPLATE KHÁC

| Template | File | Sử dụng khi |
|----------|------|-------------|
| **Director Thinking** | [21_Director_Thinking_Template.md](file:///D:/Music/Ruby/Produce%20for%20Customer/Research/My%20Content/00_System/21_Director_Thinking_Template.md) | Tư duy shot type, camera move |
| **10 Golden Phrases** | [20_10_Golden_Phrases_Template.md](file:///D:/Music/Ruby/Produce%20for%20Customer/Research/My%20Content/00_System/20_10_Golden_Phrases_Template.md) | Ánh sáng, visual, mood |
| **Camera Structure** | [13_Camera_Structure_Template.md](file:///D:/Music/Ruby/Produce%20for%20Customer/Research/My%20Content/00_System/13_Camera_Structure_Template.md) | Cấu trúc camera movement |

---

> **Camera Grammar > Character Description. Hãy chỉ đạo như một đạo diễn.** 🎬

*Character Scale Lock Template v1.0 - 2026-01-30 - VEO3.1 AI Video Prompting Masterclass*
