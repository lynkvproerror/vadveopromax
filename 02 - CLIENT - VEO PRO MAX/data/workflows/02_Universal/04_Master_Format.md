# MASTER.TXT TEMPLATE - GOLDEN SAMPLE FORMAT
## Template chuẩn cho file `XX_Master.txt`

**Phiên bản**: 1.1  
**Cập nhật**: 2026-02-08  
**Áp dụng**: Tất cả dự án Mode A (Health) và Mode B (Entertainment)

---

## 📋 FORMAT CHUẨN MỖI DÒNG MASTER

```
[Scene type]. [Shot type]. [Visual Style]. [Setting]. [Character full description + action + expression/tone]. Audio [sound]. (Giọng: Vùng, Tuổi) "Thoại với số liệu."
```

**Multi-Segment format (2-3 phân cảnh / prompt):**
```
[Scene type] (N SEG). [Visual Style]. SEG1: [Shot]. [Description].
>> SEG2: [Shot]. [Description].
>> SEG3: [Shot]. [Description].
Audio [sound]. (Giọng: Vùng, Tuổi) "Thoại 15-20 từ TỔNG."
```

> [!NOTE]
> `>>` = dấu phân cách segment. Mỗi project có **10-12 prompts** (ưu tiên, min 8), mỗi prompt có **1-3 segments**.
> Dialogue: **15-20 từ tổng** cho cả prompt, bất kể số segments.
> Xem chi tiết: `05_Prompts_Format.md` §MULTI-SEGMENT PROMPTS

> [!CAUTION]
> **BLANK LINE BẮT BUỘC**: Giữa mỗi prompt PHẢI có **1 dòng trống** (enter 2 lần).
> **MULTI-SEGMENT BẮT BUỘC**: Ít nhất **3-5 prompts** phải dùng `>>` (Hook, Teaching, Demo).
> **SỐ LƯỢNG PROMPT**: KHÔNG mặc định 9. Ưu tiên 10-12 bằng cách thêm Demo/Reaction/Warning scenes.

---

## ✅ VÍ DỤ ĐÚNG (Mode A - Health)

```
Opening scene, establishing the problem. Medium shot. The 3D cute animation style, Pixar render, Vietnamese family kitchen with traditional Tet decorations, warm morning light. A middle-aged Asian mother, 42 years old, wearing light blue cotton t-shirt and gray sweatpants, standing at the counter, worried expression, furrowed brow, looking at leftover food containers. Audio of refrigerator humming. (Giọng: Miền Bắc, 42 tuổi) "Đồ ăn thừa từ hôm qua vẫn còn nguyên, liệu có ăn được không nhỉ."

Mechanism scene 1, explaining bacterial growth. Close-up. The 3D cute animation style, Pixar render, inside the leftover food container, microscopic view. An anthropomorphic green bacteria with simple dot eyes showing excitement, evil triumphant grin, multiplying rapidly with green glow effect. Audio of bubbling growth sounds. (Giọng: Miền Nam, 30 tuổi) "Haha, chỉ sau 2 tiếng ở nhiệt độ phòng, bọn ta đã nhân lên gấp 4 lần rồi."

Mechanism scene 2, showing toxin production. Medium shot. The 3D cute animation style, Pixar render, inside the food container, wider view showing bacteria colony. Multiple anthropomorphic bacteria with villainous grins and menacing expressions releasing purple toxic particles. Audio of hissing and bubbling. (Giọng: Miền Nam, 35 tuổi) "Bọn ta tiết ra độc tố mà dù nấu chín cũng không thể phá hủy được."

Consequence scene, split screen showing effect. Split screen view. The 3D cute animation style, Pixar render. Left side: Bacteria celebrating inside stomach. Right side: The same mother now sitting on couch, pale face with pained expression, holding stomach in pain, sweating. Audio of stomach gurgling and distressed sounds. (Giọng: Miền Bắc, 42 tuổi) "Đau bụng quá, chỉ vì tiếc 1 đĩa thức ăn mà giờ phải đi viện."

Solution scene, expert advice. Medium shot. The 3D cute animation style, Pixar render, clean bright hospital setting with soft blue-white lighting. A professional female doctor, 35 years old, wearing white lab coat over light blue scrubs, stethoscope around neck, confident warm smile, pointing at a diagram. Audio of calm background music. (Giọng: Miền Nam, 35 tuổi) "Quy tắc 2 tiếng, thức ăn để ngoài quá 2 tiếng phải bỏ ngay."
```

> [!IMPORTANT]
> Lưu ý: Ví dụ trên có **blank line giữa mỗi prompt** — đây là BẮT BUỘC. KHÔNG dồn liền.

---

## ❌ FORMAT SAI (KHÔNG DÙNG)

```
CLIP 1:
[Visual:] Mother in kitchen
[Audio:] Worried voice
[Dialogue:] "Đồ ăn thừa..."

---

HOẶC:

Scene 1 - Opening
Visual: Kitchen, morning
Character: Mom
Action: Looking at food
Voice: "Đồ ăn thừa..."
```

---

## 📝 CHECKLIST MỖI DÒNG MASTER

### Bắt buộc có:
- [ ] **Scene type**: Opening/Mechanism 1/Consequence/Solution...
- [ ] **Shot type**: Medium shot/Close-up/Wide shot/Split screen
- [ ] **Multi-segment** (nếu dùng): Có `(N SEG)` + `>>` phân cách + camera logic
- [ ] **Blank line**: 1 dòng trống giữa mỗi prompt 🔴 NEW v1.1
- [ ] **Visual Style prefix**: `The 3D cute animation style, Pixar render`
- [ ] **Setting**: Kitchen/Inside body/Hospital...
- [ ] **Character description ĐẦY ĐỦ**: Tuổi, trang phục, biểu cảm, hành động, **cách nói** (tone/emotion trong visual)
- [ ] **Audio cue**: `Audio of [sound description]`
- [ ] **Voice Metadata**: `(Giọng: Vùng, Tuổi)` (Giới tính từ Bible, Tone trong visual)
- [ ] **Dialogue trong dấu ngoặc kép**: `"Thoại..."`
- [ ] **Prompt count**: 10-12 ưu tiên (min 8), KHÔNG mặc định 9 🔴 NEW v1.1
- [ ] **Multi-segment ≥3 prompts**: Hook, Teaching, Demo BẮT BUỘC dùng `>>` 🔴 NEW v1.1

### Không được có:
- [ ] ❌ Dấu `?` trong thoại
- [ ] ❌ Dấu `!` trong thoại (thay bằng `.`)
- [ ] ❌ Dấu `-` nối từ (a-xít → a xít)
- [ ] ❌ Câu cụt dưới 5 chữ
- [ ] ❌ Format cũ `[Region: X] [Gender: X]`
- [ ] ❌ Prompts dồn liền không blank line 🔴 NEW v1.1
- [ ] ❌ 100% prompts chỉ 1 segment (thiếu `>>`) 🔴 NEW v1.1
- [ ] ❌ Luôn cố định 9 prompts 🔴 NEW v1.1

---

## 🎬 CẤU TRÚC CHUẨN (Mode A - PMCS)

| # | Scene Type | Nội dung | Nhân vật |
|---|------------|----------|----------|
| 1 | Opening | Giới thiệu vấn đề | Chủ thể (Human) |
| 2 | Mechanism 1 | Cơ chế khoa học 1 | Nhân vật nhân hóa |
| 3 | Mechanism 2 | Cơ chế khoa học 2 | Nhân vật nhân hóa |
| 4 | Mechanism 3 | Cơ chế khoa học 3 | Nhân vật nhân hóa |
| 5 | Consequence | Hậu quả (Split screen) | Nhân hóa + Chủ thể |
| 6 | Warning | Cảnh báo thêm | Narrator hoặc Nhân hóa |
| 7 | Solution 1 | Giải pháp 1 | Expert/Doctor |
| 8 | Solution 2 | Giải pháp 2 | Expert/Doctor |
| 9 | Closing | Kết thúc vui vẻ | Chủ thể khỏe mạnh |

---

## 🎭 CẤU TRÚC CHUẨN (Mode B - 3-Act)

| # | Scene Type | Nội dung | Thời lượng |
|---|------------|----------|------------|
| 1-2 | ACT 1 - Setup | Giới thiệu nhân vật, thế giới | 25% |
| 3 | Inciting Incident | Sự kiện kích hoạt | - |
| 4-6 | ACT 2 - Confrontation | Xung đột, cao trào dần | 50% |
| 7 | Midpoint Twist | Bước ngoặt giữa | - |
| 8 | All Is Lost | Điểm đen tối nhất | - |
| 9-10 | ACT 3 - Resolution | Climax và kết thúc | 25% |

---

## 📐 QUY TẮC THOẠI (E19, E23-E29)

### Độ dài thoại:
| Tone | Tốc độ | Max từ/clip |
|------|--------|-------------|
| Hào hứng/Nhanh | 4 từ/s | 32 từ |
| Bình thường | 3 từ/s | 24 từ |
| Nghiêm túc/Chậm | 2.5 từ/s | 20 từ |

### Format số liệu trong thoại:
| ❌ SAI | ✅ ĐÚNG |
|--------|---------|
| `60-80%` | `60 đến 80 phần trăm` |
| `>5 tiếng` | `hơn 5 tiếng` |
| `2-3 ngày` | `hai đến ba ngày` |
| `pH=4.5` | `pH bằng bốn phẩy năm` |

### Xưng hô theo vai trò:
| Vai | Xưng | Hô | Tone |
|-----|------|-----|------|
| Hero/Victim | tôi, mình | bạn, anh chị | Lo lắng, Đau đớn |
| Villain | ta, bọn ta | mày, bà, ông | Đắc thắng, Cười ác |
| Expert | tôi | bạn, các bạn | Chuyên nghiệp |

---

## 🎨 QUY TẮC SÁNG TẠO THOẠI (Dialogue Originality) - BẮT BUỘC

> [!IMPORTANT]
> Lời thoại phải SÁNG TẠO theo hoàn cảnh cụ thể và tone đã chọn trong Bible.
> CHỈ copy-paste visual/character descriptions, KHÔNG copy-paste dialogue.

### Phân biệt COPY-PASTE vs SÁNG TẠO:
| Yếu tố | Copy-paste ✅ | Sáng tạo ✅ |
|---------|-------------|------------|
| Character visual description | ✅ Y nguyên từ Bible | - |
| Setting description | ✅ Y nguyên từ Bible | - |
| HEX colors, Profile Lock | ✅ Y nguyên từ Bible | - |
| **Màu sắc trong Master** | ❌ KHÔNG dùng raw HEX | ✅ Text description từ Bible |
| **Lời thoại/Dialogue** | ❌ KHÔNG copy template | ✅ Mới theo hoàn cảnh + tone |
| **Catchphrase** | ❌ KHÔNG nguyên văn | ✅ Biến tấu theo personality |

### Quy tắc:
1. **Thoại = phản ánh nội dung**: Mỗi câu LOGIC với mẹo/kiến thức đang dạy
2. **Thoại = phản ánh tone**: NHẤT QUÁN với Dialogue Tone đã chọn trong Bible
3. **Thoại = phản ánh personality**: Cách nói đặc trưng cho nhân vật cụ thể
4. **≥70% câu thoại sáng tạo** (không từ ngân hàng mẫu)
5. **Không lặp pattern** giữa các project (clip 4 không luôn kết bằng cùng catchphrase)
6. **Màu sắc = text description**: Bible có `#XXXXXX - text`, Master chỉ dùng `text` (VD: `deep jet black` thay vì `#0B0B0B`)

---

## 🔗 LIÊN KẾT VỚI CÁC FILE KHÁC

| File | Quan hệ với Master.txt |
|------|------------------------|
| `_Bible.md` | Copy-paste Character/Setting description |
| `_Prompts.txt` | Tách phần Visual (bỏ thoại, metadata) |
| `_Dubbing.txt` | Tách phần Dialogue (bỏ visual) |
| `_SEO.txt` | Dùng chủ đề để research |

---

*Master Template v1.1 - 2026-02-08 - Updated with Blank Line + Multi-Segment + Flexible Count*
