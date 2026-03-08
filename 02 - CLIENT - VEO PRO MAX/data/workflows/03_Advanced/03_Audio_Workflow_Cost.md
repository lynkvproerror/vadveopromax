# AUDIO, WORKFLOW & COST GUIDE

**Version**: 1.0  
**Nguồn**: Extracted từ `15_Veo_Master_Guide_Template.md`  
**Áp dụng**: Veo 3.1

---

## 1. AUDIO PROMPTING (Veo 3.1)

> [!TIP]
> Mô tả âm thanh như một **kịch bản riêng biệt**.

### 3 Lớp Âm Thanh

| Lớp | Loại | Tiếng Việt | Mô tả |
|-----|------|------------|-------|
| 1 | **Dialogue** | Đối thoại | Lời nói của nhân vật |
| 2 | **Ambient Noise** | Tiếng ồn môi trường | Rain, traffic, crowd |
| 3 | **Score** | Nhạc nền | Emotional music |

### Ví Dụ Prompt Audio

**Score (Nhạc nền)**:
```
Audio: A slow-building thriller film score, layered with low strings and subtle pulses.
```

**Ambient (Môi trường)**:
```
Audio: Ambient city sounds, distant traffic, rain on pavement, occasional thunder.
```

**Dialogue (Lời thoại)**:
```
Audio: Character speaks in a calm, measured voice: "I've been waiting for you."
```

**Combined Example**:
```
Audio: Rain falling, distant city sounds, melancholic synth pad.
```

---

## 2. WORKFLOW SELECTION GUIDE

### So Sánh 3 Workflow

| Workflow | Tên | Mục tiêu | Điểm mạnh | Khi dùng |
|----------|-----|----------|-----------|----------|
| **T2V** | Text-to-Video | Sáng tạo tự do | Ý tưởng mới lạ, ngẫu nhiên | Thử nghiệm concept |
| **I2V** | Image-to-Video | Giữ nhất quán | Kiểm soát vật lý tốt | Logo, nhân vật qua nhiều shot |
| **S/E** | Start/End Frame | Chuyển cảnh mượt | Điểm đầu-cuối chính xác | Transition, loop |

---

### T2V (Text-to-Video)

**Khi nào dùng:**
- Thử nghiệm ý tưởng mới
- Khám phá phong cách khác nhau
- Không cần giữ nhất quán nhân vật

**Prompt mẫu:**
```
Subject: A young astronaut floating in zero gravity.
Context: Inside a futuristic space station, Earth visible through window.
Action: Reaches out to catch a floating apple.
Style: Cinematic, sci-fi, 4K, photorealistic.
Camera: Slow orbit around the character.
Audio: Soft ambient space sounds, distant hum of machinery.
```

---

### I2V (Image-to-Video)

> **Chuyển tư duy từ "Mô tả" sang "Chỉ đạo"**.  
> Hình ảnh đã định nghĩa Subject + Context. Prompt chỉ cần **Action, Camera, Audio**.

**Khi nào dùng:**
- Giữ nhất quán nhân vật qua nhiều shot
- Tạo logo animation
- Kiểm soát chính xác vật lý chuyển động

**Prompt mẫu (Logo Animation):**
```
Action: The logo subtly animates, lines drawing themselves.
Camera: Slow zoom-in toward the center of the image.
Motion: Gentle, organic movement, subtle parallax effect.
Audio: Soft ambient tone, gentle swoosh sound.
Negative: No morphing, no distortion, no color shift.
```

---

### S/E (Start/End Frames)

> Kiểm soát **tuyệt đối** điểm đầu (Point A) và điểm cuối (Point B).

**Khi nào dùng:**
- Chuyển cảnh mượt mà A → B
- Tạo vòng lặp (loop) hoàn hảo
- Transition effects

```
┌─────────────────┐          ┌─────────────────┐
│  Start Frame    │  ────►   │   End Frame     │
│   (Point A)     │  Prompt  │   (Point B)     │
│   Empty room    │  ────►   │  Furnished room │
└─────────────────┘          └─────────────────┘
```

**Prompt mẫu:**
```
Transition: A wave of energy sweeps through the room.
Action: Particles coalesce and form into furniture.
Camera: Static wide shot, no movement.
Audio: Magical whoosh sound, particles twinkling.
Style: Cinematic, VFX quality, smooth morph effect.
```

---

## 3. COST OPTIMIZATION

### 2 Chế Độ Render

| Chế độ | Giá | Chất lượng | Use case |
|--------|-----|------------|----------|
| **Fast** | $0.15/giây | 720p-1080p | Thử nghiệm prompt |
| **Standard** | $0.40/giây | 4K | Xuất file cuối cùng |

### Quy Trình Tiết Kiệm

> [!IMPORTANT]
> **Đừng render 4K ngay từ đầu!** Dùng Fast Mode để test trước.

```
┌─────────┐    ┌─────────────────┐    ┌──────────┐    ┌─────────────────────┐
│  Idea   │ ─► │  Fast Mode ($)  │ ─► │ Hài lòng?│ ─► │ Standard Mode ($$$) │
│         │    │ Thử nghiệm      │    │          │    │ Xuất file 4K        │
│         │    │ Prompt & Bố cục │    │   Yes    │    │ cuối cùng           │
└─────────┘    └─────────────────┘    └──────────┘    └─────────────────────┘
```

### Ví Dụ Tính Chi Phí

| Phương pháp | Chi tiết | Chi phí |
|-------------|----------|---------|
| ❌ **Sai** | Render thẳng 4K (8s × 3 lần thử) | 8s × 3 × $0.40 = **$9.60** |
| ✅ **Đúng** | Fast (8s × 2) + Standard (8s × 1) | (8s × 2 × $0.15) + (8s × 1 × $0.40) = **$5.60** |
| 💰 **Tiết kiệm** | | **$4.00 (~42%)** |

### Bảng Giá Nhanh

| Độ dài | Fast Mode | Standard Mode |
|--------|-----------|---------------|
| 4 giây | $0.60 | $1.60 |
| 8 giây | $1.20 | $3.20 |
| 12 giây | $1.80 | $4.80 |

---

## 4. QUICK REFERENCE

### Workflow Decision Tree

```
Cần giữ nhất quán nhân vật?
├─▶ CÓ → Dùng I2V (Image-to-Video)
└─▶ KHÔNG ↓

Cần chuyển cảnh mượt A → B?
├─▶ CÓ → Dùng S/E (Start/End)
└─▶ KHÔNG → Dùng T2V (Text-to-Video)
```

### Tỷ Lệ Khung Hình

| Nền tảng | Tỷ lệ |
|----------|-------|
| YouTube | 16:9 |
| TikTok, Shorts, Reels | 9:16 |
| Instagram Feed | 1:1 hoặc 4:5 |
| Cinema | 21:9 |

---

*Extracted từ 15_Veo_Master_Guide_Template.md - 2026-02-05*
