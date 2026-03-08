# TEMPLATE YÊU CẦU KỸ THUẬT NGHIÊM NGẶT (VEO 3 MASTER TEMPLATE)

> **MỤC ĐÍCH**: Đảm bảo tính nhất quán tuyệt đối về nhân vật, bối cảnh và mạch truyện cho video AI (Veo 3).
> **QUY CHUẨN BÀN GIAO (DELIVERY PACKAGE)**: Mỗi Video phải được bàn giao dưới dạng 1 THƯ MỤC chứa 5 files:
> 1.  `_Bible.md`: Hồ sơ thiết kế Nhân vật & Bối cảnh.
> 2.  `_Prompts.txt`: Chỉ chứa Prompt tạo video (Clean Text -> Cho AI Veo).
> 3.  `_Dubbing.txt`: Chỉ chứa Lời thoại (Cho Thu âm/TTS).
> 4.  `_Master.txt`: Kịch bản gốc (Visual + Audio chung 1 dòng - giống Golden Sample).
> 5.  `_SEO.txt`: Metadata SEO (Tiêu đề A/B/C, Hashtags, Description, Keywords).

---

## 0. CHỌN CHẾ ĐỘ NỘI DUNG (MODE SELECTION) - ĐỌC TRƯỚC TIÊN

> [!IMPORTANT]
> **BƯỚC ĐẦU TIÊN**: Xác định loại nội dung trước khi viết bất kỳ thứ gì

### Hai Chế Độ:
| Mode | Tên | Mục đích | Cấu trúc | Xem tài liệu |
|------|-----|----------|----------|--------------|
| **A** | Health Education | Giáo dục sức khỏe | PMCS (Problem-Mechanism-Consequence-Solution) | Phần E của file này |
| **B** | Entertainment | Giải trí (Action, Comedy, Drama) | 3-Act (Setup-Confrontation-Resolution) | `05_Entertainment_Template.md` |

### Quy Tắc CHUNG (Áp dụng CẢ HAI Mode):
- E7: Zero Text Policy
- E11: Sensitive Words Database
- E12: Simple Face (Anthropomorphic)
- E19: Strict TTS (Không !, ?, -)
- E28: Cinematic Camera Keywords
- E29: Retention Pacing
- E31: Seamless Stitching
- E32: Viral Hook Quartet

### Quy Tắc CHỈ CHO Mode A (Health):
- E2: Scientific Density (Facts + Sources)
- E3: Character Value (Each char = 1 knowledge)
- E4: PMCS Structure
- E17: Expert/Doctor Required
- A2: Chủ Thể/Vật Chủ (Human Subject) Required

### Quy Tắc CHỈ CHO Mode B (Entertainment):
- G2: Story Density (7 Plot Points)
- G3: Character Arc
- G4: Conflict Management
- G5: Emotional Beats
- 3-Act Structure

---


## 1. KHUNG ĐỊNH NGHĨA "KINH THÁNH" (GLOBAL BIBLE)
*Phần này phải được define trước khi viết bất kỳ prompt nào. Nội dung trong [] phải được copy paste y nguyên vào mọi prompt tương ứng.*

### A. Định Danh Nhân Vật (Character Bible)
**Quy tắc**: Mô tả từ đầu đến chân, ĐỘ TUỔI, chất liệu, phụ kiện, TRANG PHỤC.

#### A1. BẢNG ĐỘ TUỔI CHUẨN (Age Range Reference)
| Loại | Age Range | Voice Age | Đặc điểm |
|------|-----------|-----------|----------|
| Trẻ em | 5-12 | Child 8-10 | Cao, trong trẻo |
| Thiếu niên | 13-17 | Teen 15s | Năng động, hào hứng |
| Thanh niên | 18-29 | 20s | Trẻ trung, mạnh mẽ |
| Trung niên | 30-50 | 30s-40s | Trầm, chín chắn |
| Cao tuổi | 50+ | 60s+ | Chậm, ấm áp |

#### A2. TEMPLATE NHÂN VẬT (Phải có ĐỦ các mục)
```
## NHÂN VẬT: [Tên/Vai trò]
- **Độ tuổi**: [XX years old / XX tuổi]
- **Giới tính**: [Male/Female]
- **Ngoại hình**: [Build, hair, distinguishing features]
- **Trang phục thường ngày**: [Casual outfit description]
- **Trang phục đặc biệt**: [Festive/Work outfit if applicable]
- **Phụ kiện cố định**: [Glasses, watch, jewelry]
- **Biểu cảm mặc định**: [Friendly smile, worried expression]
```

#### A3. VÍ DỤ NHÂN VẬT
*   **Nhân vật Người (Human Character)**: 
    `[A middle-aged Asian mother, 42 years old, medium build, shoulder-length black hair tied back, wearing light blue cotton t-shirt and gray sweatpants for cleaning (casual), or red silk áo dài for Tet (festive), small silver earrings, warm friendly expression]`

*   **Nhân vật Nhân hóa (Anthropomorphic)**:
    `[An anthropomorphic reddish-brown liver organ, with simple dot eyes showing exhaustion (half-closed), curved tired mouth, no human facial features, sweating droplets on surface]`

*   **Chuyên gia/Bác sĩ (Expert - chuẩn hóa)**:
    `[A professional female doctor, 35 years old, wearing white lab coat over light blue scrubs, stethoscope around neck, glasses, confident warm expression, short neat black hair]`

#### A4. QUY TẮC TRANG PHỤC (Costume Consistency)
| Quy tắc | Chi tiết |
|---------|----------|
| Nhất quán | Cùng nhân vật = Cùng outfit xuyên suốt video |
| Thay đổi có lý do | Nếu đổi, phải mô tả: "now wearing clean festive clothes" |
| Phụ kiện cố định | Kính, đồng hồ, trang sức KHÔNG thay đổi giữa các scene |
| Màu sắc nhất quán | Palette màu trang phục phải khớp với Visual Style |

### A2. Định Danh Chủ Thể/Vật Chủ (Host/Subject Definition) - BẮT BUỘC khi dùng nhân vật nhân hoá
**Quy tắc**: Khi nội tạng/bộ phận được NHÂN HÓA, PHẢI define CHỦ THỂ (con người sở hữu) để hiển thị hậu quả.
*   **VÌ SAO CẦN**: Hậu quả (vàng da, phù chân, mệt mỏi) phải được thể hiện trên CON NGƯỜI, không chỉ trên nội tạng.
*   **FORMAT**:
    ```
    ## CHỦ THỂ (Host/Subject)
    - **Mô tả cơ bản**: [Tuổi, giới tính, ngoại hình tổng quan]
    - **Trang phục**: [Quần áo, phụ kiện]
    - **Trạng thái bình thường**: [Khỏe mạnh, da hồng, mắt sáng]
    - **Trạng thái khi có triệu chứng**: [Mệt mỏi, vàng da, phù mặt, etc.]
    ```
*   **VÍ DỤ**:
    ```
    ## CHỦ THỂ (Host/Subject)
    - **Mô tả cơ bản**: Middle-aged Asian man, 40s, average build
    - **Trang phục**: Casual home clothes, cotton t-shirt
    - **Trạng thái bình thường**: Healthy pink skin, bright eyes, alert expression
    - **Trạng thái khi có triệu chứng**:
      * Gan suy kiệt: Yellowish skin, yellow-tinted eyes, tired dark circles
      * Thận quá tải: Puffy face, swollen ankles, pale complexion
      * Tim loạn nhịp: Sweating, pale face, clutching chest
    ```
*   **KHI NÀO DÙNG**:
    | Loại video | Cần Host/Subject? |
    |------------|-------------------|
    | Nội tạng nhân hóa (Gan, Tim, Ruột...) | ✅ BẮT BUỘC |
    | Đồ vật nhân hóa (Đũa, Tủ lạnh...) | ⚠️ Khuyến nghị nếu có hậu quả sức khỏe |
    | Người thật là nhân vật chính | ❌ Không cần (đã có mô tả ở phần A) |
*   **CHUYỂN CẢNH GIỮA NỘI TẠNG VÀ CHỦ THỂ**:
    | Kỹ thuật | Mô tả |
    |----------|-------|
    | Zoom Out | Từ nội tạng (vi mô) → Zoom ra thấy cơ thể người (vĩ mô) |
    | Split Screen | Trái: Nội tạng / Phải: Người thể hiện triệu chứng |
    | Match Cut | Hình dạng tương đồng (gan → bụng người) |
    | Wipe Transition | Quét từ nội tạng sang người bên ngoài |

### B. Định Danh Bối Cảnh (Setting Bible)
**Quy tắc**: Ánh sáng, không gian, thời gian, vật thể cố định - PHẢI NHẤT QUÁN suốt video.

#### B1. TEMPLATE BỐI CẢNH (Setting Template)
```
## BỐI CẢNH: [Tên/Loại]
- **Địa điểm**: [Kitchen/Living room/Inside body/Hospital]
- **Thời gian**: [Morning/Afternoon/Night/Timeless]
- **Ánh sáng**: [Warm golden/Cool blue/Dramatic red/Natural daylight]
- **Palette màu**: [Earth tones/Vibrant/Muted/Medical white]
- **Props cố định**: [Furniture, decorations, medical equipment]
- **Không khí**: [Festive/Tense/Peaceful/Chaotic]
```

#### B2. VÍ DỤ BỐI CẢNH
*   **Bối cảnh Nhà (Home Setting)**:
    `[Vietnamese family living room, pre-Tet cleaning mode, dust balls visible, clutter everywhere, spiderwebs in corners, harsh sunlight revealing dust particles, warm but messy atmosphere]`

*   **Bối cảnh Trong cơ thể (Inside Body)**:
    `[Interior body environment, warm reddish-pink lighting, blood vessels visible, organic tissue textures, pulsing rhythm of heartbeat, microscopic cellular details]`

*   **Bối cảnh Y tế (Medical/Educational)**:
    `[Clean bright hospital or clinic setting, soft blue-white lighting, medical equipment in background, sterile atmosphere, professional environment]`

#### B3. QUY TẮC ĐỒNG BỘ BỐI CẢNH (Setting Consistency)
| Quy tắc | Chi tiết |
|---------|----------|
| **Copy-Paste** | Setting mô tả trong Bible PHẢI được paste y nguyên vào Master/Prompts |
| **Ánh sáng nhất quán** | Cùng location = Cùng lighting (trừ khi thời gian thay đổi) |
| **Props không biến mất** | Đồ vật trong scene 1 phải còn trong scene 2 nếu cùng location |
| **Thời gian logic** | Nếu bắt đầu buổi sáng, không thể đột ngột đêm (trừ montage) |

#### B4. BẢNG ÁNH SÁNG THEO CẢM XÚC
| Cảm xúc | Lighting | Color Temperature |
|---------|----------|-------------------|
| Vui vẻ/Festive | Warm golden | 3000K-4000K |
| Căng thẳng/Danger | Dramatic red/orange | Red warning glow |
| Y tế/Educational | Cool blue-white | 5000K-6500K |
| Buồn/Mệt mỏi | Dim, muted | Desaturated |
| Healthy/Recovery | Soft green-gold | Healing glow |

### C. Định Danh Chất Giọng & Phong Cách (Voice & Style)
*   **Tone giọng**: `[Deep, resonate, authoritative but warm, rapid pace for action, slow for emotional moments]`
*   **Ngôn ngữ cơ thể**: `[Exaggerated gestures for animation style, subtle micro-expressions for realistic style]`

### D. Định Dạng Phong Cách Hình Ảnh (Visual Style Bible)
*   **QUAN TRỌNG**: Phải chọn 1 trong các style sau và paste vào đầu mỗi Description Bối Cảnh.
*   **Options**:
    *   **3D Animation (Disney/Pixar)**: `[3D cute animation style, Pixar render, soft lighting, vibrant colors, expressive features]` (Khuyên dùng cho nhân vật đồ vật).
    *   **2D Anime (Ghibli)**: `[2D hand-drawn anime style, Studio Ghibli inspired, watercolor background, detailed line art]`
    *   **Hyper-Realistic (CGI Realism)**: `[Hyper-realistic CGI, live-action look, 8k textures, cinematic lighting]`
    *   **Claymation (Stop Motion)**: `[Stop-motion clay animation style, Aardman inspired, tactile texture, jagged movement]`

### E0. NÂNG CẤP Ý TƯỞNG - TRENDING BOOST (Idea Enhancement) - BẮT BUỘC
*   **MỤC ĐÍCH**: Biến ý tưởng cơ bản thành content viral, tránh outdate, tăng shock value.
*   **BƯỚC 1 - NGHIÊN CỨU XU HƯỚNG**:
    *   Trước khi viết, PHẢI search: `[chủ đề] + trending 2026 + viral TikTok/YouTube`
    *   Check các nguồn: Google Trends, TikTok Trending, YouTube Shorts Popular
    *   Xác định: Người ta đang nói gì về chủ đề này NGAY BÂY GIỜ?
*   **BƯỚC 2 - ÁP DỤNG CÔNG THỨC SHOCK VALUE**:
    | Kỹ thuật | Ví dụ SAI (Nhạt) | Ví dụ ĐÚNG (Shock) |
    |----------|------------------|-------------------|
    | Số liệu gây sốc | "Ăn nhiều đường hại sức khỏe" | "1 lon nước ngọt = 10 MUỖNG đường, tương đương ĂN 3 TÔ CƠM" |
    | So sánh bất ngờ | "Rượu hại gan" | "3 ly bia = gan ĐÁNH VẬT 8 TIẾNG như nhân viên OT không lương" |
    | Nhân cách hóa cực đoan | "Mỡ tích tụ trong gan" | "Mỡ như KẺ XÂM LƯỢC, chiếm đóng gan như đội quân zombie" |
    | Counter-intuitive | "Tập thể dục tốt" | "Tập GYM SAI CÁCH có thể HẠI HƠN ngồi yên không tập" |
    | Đập tan huyền thoại | "Uống nước ấm tốt" | "BẬT MÍ: Nước ấm KHÔNG giúp giảm cân như bạn nghĩ" |
*   **BƯỚC 3 - TRENDING KEYWORDS 2026**:
    | Từ khóa HOT | Cách dùng |
    |-------------|-----------|
    | "Cơ thể LÊN TIẾNG" | Nhân cách hóa bộ phận than phiền |
    | "X BỊ NGHĨ SAI" | Debunk myths phổ biến |
    | "X vs Y: Kẻ thù hay bạn?" | So sánh đối lập |
    | "4 SAI LẦM chết người" | Listicle với warning |
    | "Bác sĩ TIẾT LỘ" | Authority + secret reveal |
    | "ĐỪNG LÀM điều này" | Negative hook (tò mò) |
    | "Tại sao X lại Y?" | Question hook |
    | "Sự thật ĐÁNG SỢ về..." | Fear + curiosity |
*   **BƯỚC 4 - VALIDATE TRENDING**:
    - [ ] Chủ đề có đang được bàn tán trên MXH không?
    - [ ] Có số liệu/nghiên cứu MỚI 2025-2026 không?
    - [ ] Hook có đủ gây tò mò trong 3 giây đầu không?
    - [ ] Có yếu tố "phản trực giác" (counter-intuitive) không?
*   **XU HƯỚNG SỨC KHỎE 2026 (Cập nhật thường xuyên)**:
    | Trend | Ứng dụng |
    |-------|----------|
    | Phòng bệnh > Chữa bệnh | "Phát hiện SỚM = cứu sống" |
    | Gut Health / Đường ruột | "90% bệnh bắt nguồn từ ruột" |
    | Sleep Optimization | "Ngủ SAI giờ = uống 3 lon bia" |
    | Digital Detox | "Điện thoại ĐANG ăn mòn não bạn" |
    | Nguồn gốc thực phẩm | "80% thực phẩm Tết KHÔNG RÕ nguồn gốc" |
    | Mental Health | "Trầm cảm sau Tết - căn bệnh THẦM LẶNG" |

### E. Kiểm Chứng Khoa Học (Scientific Accuracy) - BẮT BUỘC
*   **BẮT BUỘC**: Mọi thông tin sức khỏe/meo vặt đều phải được SEARCH + VERIFY trước khi viết.
*   **TRÁNH SAI LỆCH**: Không lan truyền "mẹo dân gian" phản khoa học (ví dụ: bôi kem đánh răng lên vết bỏng -> SAI).
*   **QUY TRÌNH RESEARCH KHOA HỌC BẮT BUỘC**:
    | Bước | Hành động | Công cụ/Nguồn |
    |------|-----------|---------------|
    | 1 | Search `[chủ đề] + scientific study` | Web Search (Google Scholar) |
    | 2 | Tìm số liệu từ tổ chức y tế | WHO, CDC, Bộ Y tế VN |
    | 3 | Cross-check nhiều nguồn | Ít nhất 2-3 nguồn khác nhau |
    | 4 | Ghi chú nguồn vào Bible | Citation cụ thể |
    | 5 | Verify với nghiên cứu gần đây | Ưu tiên 2023-2026 |
*   **NGUỒN UY TÍN (ưu tiên)**:
    | Loại | Nguồn | Độ tin cậy |
    |------|-------|------------|
    | Tổ chức quốc tế | WHO, FDA, CDC | ⭐⭐⭐⭐⭐ |
    | Bộ Y tế | moh.gov.vn, Viện Dinh dưỡng | ⭐⭐⭐⭐⭐ |
    | Nghiên cứu | PubMed, Google Scholar | ⭐⭐⭐⭐ |
    | Bệnh viện lớn | Vinmec, Bạch Mai | ⭐⭐⭐⭐ |
    | Báo y tế | Sức khỏe đời sống | ⭐⭐⭐ |
    | Wikipedia | (chỉ để hiểu concept, KHÔNG cite) | ⭐⭐ |
*   **NGUỒN CẤM (tránh)**:
    - Blog cá nhân, diễn đàn
    - Video YouTube không có nguồn
    - Mẹo dân gian không kiểm chứng
    - Quảng cáo sản phẩm
*   **VÍ DỤ SAI (Không verify)**:
    ```
    "Uống nước chanh buổi sáng giúp giảm cân" ← Không có nguồn
    ```
*   **VÍ DỤ ĐÚNG (Có verify)**:
    ```
    "Theo nghiên cứu của Journal of Obesity (2024), việc uống nước 
    trước bữa ăn giúp giảm 44% lượng calo tiêu thụ" ← Có citation
    ```
*   **CHECKLIST VERIFY KHOA HỌC**:
    - [ ] Số liệu có nguồn nào confirm không?
    - [ ] Nguồn có phải tổ chức y tế uy tín không?
    - [ ] Nghiên cứu có mới (2023-2026) không?
    - [ ] Có ít nhất 2 nguồn cross-check không?

### E2. MẬT ĐỘ KHOA HỌC (Scientific Density) - QUAN TRỌNG
*   **ĐỊNH NGHĨA**: Video ngắn KHÔNG ĐƯỢC sáo rỗng. Mỗi clip phải chứa ít nhất 1 fact/số liệu/cơ chế khoa học cụ thể.
*   **YÊU CẦU TỐI THIỂU MỖI CLIP**:
    *   **Số liệu cụ thể**: "Đứng 4 tiếng liên tục tăng áp lực lên tĩnh mạch gấp 10 lần" (Không nói chung chung "đứng lâu hại chân").
    *   **Cơ chế sinh học**: "Máu dồn xuống chân -> Van tĩnh mạch yếu -> Giãn tĩnh mạch" (Không chỉ nói "chân sưng").
    *   **Hậu quả rõ ràng**: "Nguy cơ huyết khối tĩnh mạch sâu (DVT) nếu không điều trị" (Không chỉ nói "hại sức khỏe").
*   **THÁP BẰNG CHỨNG (Evidence Pyramid) - BẮT BUỘC**:
    *   Mỗi video phải có **TỐI THIỂU 5-7 SỐ LIỆU/FACTS** xuyên suốt để chứng minh tính NGHIÊM TRỌNG:
    | Tầng | Loại bằng chứng | Số lượng | Ví dụ |
    |------|-----------------|----------|-------|
    | 1. Hook | Số liệu GÂY SỐC mở đầu | 1 | "1 lon = 10 muỗng đường" |
    | 2. Mechanism | Cơ chế khoa học (CON SỐ) | 2-3 | "Gan xử lý 10g cồn/giờ", "1 ly bia = xử lý 2 tiếng" |
    | 3. Consequence | Hậu quả (THỐNG KÊ) | 1-2 | "Tăng 18% nguy cơ ung thư", "40% người Việt bị..." |
    | 4. Solution | Giải pháp (CON SỐ) | 1 | "Uống 2L nước/ngày", "Nghỉ 15 phút mỗi giờ" |
*   **LOẠI SỐ LIỆU HIỆU QUẢ**:
    | Loại | Ví dụ | Tác dụng |
    |------|-------|----------|
    | % Nguy cơ | "+48% nguy cơ đột quỵ" | Gây sợ hãi |
    | So sánh tương đương | "= 3 tô cơm", "= chạy 45 phút" | Dễ hình dung |
    | Thời gian | "chỉ sau 4 tiếng", "mỗi 15 phút" | Urgency |
    | Số người | "1000 người/ngày nhập viện" | Scale impact |
    | Bội số | "gấp 10 lần", "tăng 3 lần" | Magnitude |
    | Cơ thể | "7500 lần nén", "2L mồ hôi" | Body visualization |
*   **VÍ DỤ SAI (Chỉ có 1 số)**: 
    ```
    Tiêu đề: "1 lon nước ngọt = 10 muỗng đường"
    Nội dung: Chỉ nói đường hại sức khỏe, không có thêm số liệu nào.
    ```
    → **SAI**: 1 số không đủ chứng minh nghiêm trọng.
*   **VÍ DỤ ĐÚNG (5-7 số liệu)**:
    ```
    Hook: "1 lon = 10 muỗng đường = 3 tô cơm!"
    Mechanism 1: "Đường chuyển thành mỡ trong 30 PHÚT"
    Mechanism 2: "Insulin tăng đột biến GẤP 4 LẦN"
    Mechanism 3: "Gan xử lý quá tải, +30% mỡ gan"
    Consequence: "Nguy cơ tiểu đường TYPE 2 tăng 26%"
    Solution: "Thay bằng nước lọc, giảm 500 kcal/ngày"
    ```
    → **ĐÚNG**: 6 số liệu, escalate từ hook đến hậu quả.

### E3. GIÁ TRỊ NHÂN VẬT (Character Value)
*   **ĐỊNH NGHĨA**: Mỗi nhân vật nhân hóa phải đóng góp KIẾN THỨC ĐỘC ĐÁO, không chỉ than vãn chung chung.
*   **YÊU CẦU**:
    *   **Mỗi nhân vật = 1 bài học riêng**: Chân Trái dạy về "áp lực gót chân", Tĩnh Mạch dạy về "cơ chế giãn tĩnh mạch".
    *   **KHÔNG TRÙNG LẶP**: Nếu 2 nhân vật nói cùng 1 thông tin -> Xóa bớt 1.
*   **VÍ DỤ SAI**: Chân Trái: "Đau quá!" + Chân Phải: "Tôi cũng đau!" -> Trùng lặp, vô giá trị.
*   **VÍ DỤ ĐÚNG**: Chân Trái: "Gót chân chịu 60% trọng lượng!" + Tĩnh Mạch: "Van tĩnh mạch yếu vì máu ứ đọng!" -> Mỗi nhân vật 1 fact.

### E4. CẤU TRÚC PMCS (Problem-Mechanism-Consequence-Solution)
*   **BẮT BUỘC**: Mọi kịch bản phải theo cấu trúc 4 bước:
    1.  **P (Problem)**: Vấn đề phổ biến (Hook gây sốc).
    2.  **M (Mechanism)**: Cơ chế khoa học đằng sau (Tại sao xảy ra?).
    3.  **C (Consequence)**: Hậu quả nếu không sửa (Nguy hiểm thế nào?).
    4.  **S (Solution)**: Giải pháp cụ thể, có thể hành động ngay.

### E5. KIỂM TRA LOGIC NHẤT QUÁN (Logic Consistency Check) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Thoại của nhân vật phải KHỚP với bối cảnh hành động đang xảy ra. Không được mâu thuẫn.
*   **QUY TRÌNH**: Trước khi viết thoại, hỏi: "Nhân vật đang LÀM GÌ trong cảnh này?"
*   **VÍ DỤ SAI (Mâu thuẫn Logic)**:
    *   *Hành động*: Mẹ ĐI BỘ liên tục trong chợ.
    *   *Thoại Cơ Bắp Chân*: `"Bình thường tôi co bóp khi đi lại, nhưng ĐỨNG YÊN lâu quá tôi không làm việc được!"` → **SAI** (Đang đi bộ, không phải đứng yên).
*   **VÍ DỤ ĐÚNG (Logic nhất quán)**:
    *   *Hành động*: Mẹ ĐI BỘ liên tục trong chợ.
    *   *Thoại Cơ Bắp Chân*: `"Tôi co bóp suốt 5 tiếng liên tục! Lực nén lên gót chân mỗi bước gấp 1.5 lần trọng lượng! Mỏi quá rồi!"` → **ĐÚNG** (Khớp với hành động đi bộ).
*   **CHECKLIST**:
    - [ ] Nhân vật đang ĐI hay ĐỨNG? Thoại có khớp không?
    - [ ] Nhân vật đang ĂN hay CHƯA ĂN? Hậu quả có logic không?
    - [ ] Thời gian trong thoại có khớp với bối cảnh không?

### E6. MÔ TẢ CHUYỂN CẢNH NHÂN VẬT (Character Scene Transition) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Khi chuyển từ nhân vật nhân hóa A sang B, phải mô tả **camera movement** và/hoặc **character action** để dẫn dắt mắt người xem.
*   **VÌ SAO QUAN TRỌNG**: Veo 3 tạo video 8 giây độc lập. Nếu không có mô tả chuyển cảnh, các clip sẽ rời rạc, không liên kết.
*   **KỸ THUẬT CHUYỂN CẢNH CHO NHÂN VẬT NHÂN HÓA**:
    1.  **Zoom Out → Pan**: Từ Xương Gót (close-up) → Zoom out qua các lớp cơ → Pan thấy Tĩnh Mạch.
    2.  **Character Walks/Hops In**: Nhân vật A đang nói → Nhân vật B nhảy/đi vào khung hình, giới thiệu bản thân.
    3.  **Match Cut (Hình dạng tương đồng)**: Quả Thanh Long (tròn) → Cut sang Quả Dưa Chuột (dài) với hiệu ứng morph.
    4.  **Whip Pan (Xoay nhanh)**: Camera quay nhanh từ Gan sang Thận trong cùng khoang bụng.
    5.  **Follow the Flow**: Theo dòng máu/dây dẫn từ bộ phận A đến B.
*   **VÍ DỤ SAI (Thiếu chuyển cảnh)**:
    *   `Clip 2: Xương Gót nói: "..."` → `Clip 3: Tĩnh Mạch nói: "..."` (Đột ngột, không có kết nối).
*   **VÍ DỤ ĐÚNG (Có chuyển cảnh)**:
    *   `Clip 2: Xương Gót nói: "..." Camera begins to zoom out through muscle layers.`
    *   `Clip 3: Continuing zoom reveals Tĩnh Mạch wrapped around the calf muscle. It waves at the camera...`

### E7. LOẠI BỎ HOÀN TOÀN TEXT TRONG VISUAL (Zero Text Policy) - BẮT BUỘC NGHIÊM NGẶT
*   **ĐỊNH NGHĨA**: Veo 3.1 KHÔNG THỂ render chữ/số chính xác. Mọi text element sẽ bị lỗi, biến dạng, hoặc vô nghĩa.
*   **QUY TẮC BẮT BUỘC**: Mỗi prompt PHẢI kết thúc bằng suffix: `no text, no subtitles, no labels, no watermarks`

#### E7.1 DANH SÁCH TỪ KHÓA CẤM TUYỆT ĐỐI (Text-Trigger Blacklist)

| Category | Trigger Words (CẤM DÙNG) |
|----------|--------------------------|
| **Numbers** | `shows "X"`, `displays X`, `counter`, `timer`, `meter`, `clock`, `calendar`, `percentage`, `%`, `statistics` |
| **Labels** | `label`, `labeled`, `tag`, `tagged`, `caption`, `captioned`, `title`, `titled`, `name`, `named` |
| **Signs** | `sign`, `signage`, `poster`, `banner`, `billboard`, `placard`, `notice`, `announcement` |
| **Text Actions** | `reads`, `says`, `shows text`, `displays text`, `writes`, `written`, `spelled`, `spelling` |
| **UI Elements** | `button`, `menu`, `interface`, `screen showing`, `monitor displaying`, `phone screen` |
| **Charts** | `chart`, `graph`, `diagram with text`, `infographic`, `table`, `spreadsheet` |
| **Arrows** | `arrow with`, `labeled arrow`, `annotation`, `callout`, `tooltip` |
| **Logos** | `logo`, `brand`, `trademark`, `watermark`, `copyright`, `certification mark` |
| **Time** | `"X minutes"`, `"X hours"`, `"X days"`, `showing time`, `clock face` |
| **Quotes** | Bất kỳ text trong `"..."` trong phần visual description |

#### E7.2 REGEX PATTERN PHÁT HIỆN TEXT-TRIGGER
```
Patterns to AVOID in prompts:
- /"[^"]+"/  (Quoted text)
- /shows? "[^"]+"/ (Shows + quoted)
- /display(s|ing)? "[^"]+"/ (Displays + quoted)
- /\d+%/ (Percentages)
- /\d+ (minutes?|hours?|days?|seconds?)/ (Time with numbers)
- /label(ed)?|tag(ged)?|caption(ed)?/ (Label words)
- /sign (reads?|says?|shows?)/ (Sign + reading)
```

#### E7.3 BẢNG CHUYỂN ĐỔI MỞ RỘNG (Extended Replacements)

| ❌ SAI (Text-Trigger) | ✅ ĐÚNG (Visual Alternative) |
|----------------------|------------------------------|
| `clock shows "3:00 PM"` | `afternoon lighting, sun position indicating late day` |
| `calendar showing "2 WEEKS"` | `multiple day/night cycles passing in montage` |
| `thermometer displays "38°C"` | `red glowing thermometer, mercury at high level` |
| `phone screen showing message` | `phone glowing with notification light` |
| `sign reads "Danger"` | `red warning glow, pulsing danger light` |
| `label says "Toxic"` | `skull and crossbones symbol, green toxic fumes` |
| `counter shows "100"` | `rapidly filling container, overflowing` |
| `timer counting down` | `sand falling in hourglass, urgency building` |
| `percentage bar at 80%` | `container nearly full, almost overflowing` |
| `menu displaying options` | `hand gesturing at multiple floating items` |
| `button labeled "Start"` | `glowing circular button, finger approaching` |
| `graph showing increase` | `visual bars growing taller, escalating` |
| `text appears on screen` | `visual symbol fades in, icon materializes` |
| `subtitle showing` | (REMOVE - dùng voice thay thế) |
| `name tag showing "Dr. X"` | `professional doctor with stethoscope` |

#### E7.4 THAY THẾ BẰNG SYMBOLIC VISUALS

| Concept | Symbol Visual |
|---------|---------------|
| Warning/Danger | Red glow, pulsing light, sparks |
| Safe/Good | Green glow, soft white light, halo |
| Time passing | Sun/moon movement, shadows shifting |
| Quantity | Container filling, objects multiplying |
| Temperature | Color gradient (blue=cold, red=hot), steam/frost |
| Speed | Motion blur, trailing effects |
| Direction | Flowing particles, wind effects, movement lines |
| Comparison | Side-by-side placement, size difference |

#### E7.5 MANDATORY SUFFIX (Thêm vào CUỐI mỗi prompt)
```
[...rest of prompt], no text, no subtitles, no labels, no watermarks, no floating text, no UI elements
```

#### E7.6 CHECKLIST ZERO-TEXT (Phải check TRƯỚC khi submit)
- [ ] Không có text trong dấu ngoặc kép `"..."` trong visual?
- [ ] Không có từ: shows, displays, reads, says + text?
- [ ] Không có số liệu cụ thể trong visual (dùng voice thay thế)?
- [ ] Không có labels, signs, posters, buttons, menus?
- [ ] Không có charts/graphs với text labels?
- [ ] Không có phone/computer screens showing text?
- [ ] Không có timestamps, counters, timers?
- [ ] Đã thêm suffix `no text, no subtitles...` ở cuối prompt?

#### E7.7 LƯU Ý QUAN TRỌNG
*   **Số liệu khoa học**: CHỈ nói trong THOẠI (Dubbing), KHÔNG bao giờ hiển thị trong visual
*   **Thông tin text**: Chuyển thành SYMBOLS, COLORS, ICONS, ANIMATIONS
*   **Nếu text TUYỆT ĐỐI cần thiết**: Chỉ dùng TIẾNG ANH đơn giản (1-2 từ), và phải test trước

### E8. MÔ TẢ ĐẦY ĐỦ NHIỀU NHÂN VẬT (Full Multi-Character Description) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Khi 2+ nhân vật xuất hiện trong cùng 1 prompt, PHẢI mô tả ĐẦY ĐỦ tất cả nhân vật. KHÔNG được tóm tắt, bỏ qua, hoặc viết tắt.
*   **VÌ SAO QUAN TRỌNG**: Mỗi prompt Veo 3 là độc lập. Nếu bỏ mô tả, Veo sẽ tự sáng tác → mất nhất quán.
*   **VÍ DỤ SAI (Bỏ qua mô tả)**:
    ```
    Close-up. The Mom and Dr. Vascular give a thumbs up. Screen fades to black.
    ```
    → **SAI**: "Mom" và "Dr. Vascular" KHÔNG có mô tả ngoại hình → Veo tự sáng tác.
*   **VÍ DỤ ĐÚNG (Mô tả đầy đủ)**:
    ```
    Close-up. A middle-aged Asian mother, 40s, wearing comfortable clothes, smiling relaxed 
    AND A professional male doctor, 35s, sporty outfit, holding a diagram of leg circulation 
    do synchronized ankle circles then give a thumbs up to the camera.
    ```
    → **ĐÚNG**: Cả hai nhân vật đều có mô tả đầy đủ.
*   **CHECKLIST**:
    - [ ] Mỗi nhân vật có mô tả tuổi, trang phục, biểu cảm không?
    - [ ] Dù prompt dài cũng KHÔNG được lược bỏ mô tả.

### E9. TỐC ĐỘ ĐỌC LINH HOẠT (Flexible Reading Speed) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Lời thoại PHẢI đọc hết trong 8 giây. Tốc độ đọc có thể điều chỉnh.
*   **QUY TẮC ƯỚC LƯỢNG**:
    *   **Tốc độ bình thường**: ~3 từ/giây → 8s = ~24 từ tiếng Việt.
    *   **Tốc độ nhanh (hào hứng)**: ~4 từ/giây → 8s = ~32 từ tiếng Việt.
    *   **Tốc độ chậm (nghiêm túc)**: ~2.5 từ/giây → 8s = ~20 từ tiếng Việt.
*   **CÁCH XỬ LÝ NẾU THOẠI QUÁ DÀI**:
    1.  Đọc hết giây đầu tiên quyết định tốc độ dựa trên [Tone].
    2.  Nếu vẫn dài, chia nhỏ thành 2 clips.
    3.  **KHÔNG cắt bỏ nội dung khoa học quan trọng**.
*   **VÍ DỤ**:
    *   `[Tone: Hào hứng]` → Đọc nhanh 4 từ/giây, tối đa 32 từ.
    *   `[Tone: Nghiêm trọng/Cảnh báo]` → Đọc chậm 2.5 từ/giây, tối đa 20 từ.

### E10. LINH HOẠT XƯNG HÔ (Pronoun/Address Flexibility) - KHUYẾN KHÍCH
*   **ĐỊNH NGHĨA**: Cách xưng hô của nhân vật có thể thay đổi theo TÍNH CHẤT kịch bản và VAI TRÒ nhân vật.
*   **PHÂN LOẠI THEO VAI TRÒ**:
    *   **Nhân vật TÍCH CỰC (Bác sĩ, Chuyên gia, Nạn nhân tốt)**:
        *   Xưng: `tôi`, `mình`, `em` (khiêm tốn)
        *   Hô: `bạn`, `anh/chị`, `bà chủ/ông chủ` (tôn trọng)
        *   Biểu cảm: Thân thiện, lo lắng, quan tâm
    *   **Nhân vật PHẢN DIỆN (Vi khuẩn, Mỡ, Độc tố, Thực phẩm hỏng)**:
        *   Xưng: `ta`, `tao`, `bọn tao` (kiêu ngạo)
        *   Hô: `mày`, `bà`, `ông` (thách thức)
        *   Biểu cảm: Đắc thắng, hung hãn, cười ác
    *   **Nhân vật TRUNG LẬP (Narrator, Bộ phận cơ thể than phiền)**:
        *   Xưng: `tôi`, `tui` (miền Nam), `mình`
        *   Hô: `bà chủ`, `ông chủ`, `cô/chú`
        *   Biểu cảm: Khổ sở, mệt mỏi, kiệt sức
*   **TRƯỜNG HỢP ĐẶC BIỆT - XƯNG HÔ THÂN MẬT**:
    *   Nếu 2 nhân vật cùng phe hoặc bạn bè, có thể dùng `mày-tao` THÂN MẬT (không hung hãn).
    *   **VÍ DỤ**: Hai cơ quan nội tạng trò chuyện: `"Ê Gan ơi, mày mệt chưa?"` - `"Tao mệt bở hơi tai rồi Thận ơi!"`
    *   **LƯU Ý**: Biểu cảm khuôn mặt PHẢI thân thiện, cười thoải mái (không nhăn nhó, không gằn giọng).

### E11. TỪ KHÓA NHẠY CẢM (Sensitive Words) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Một số từ có thể bị YouTube/TikTok gắn cờ vi phạm. Cần thay thế bằng từ phù hợp.
*   **THAM CHIẾU**: Xem file `00_Templates/Sensitive_Words_Database.txt` để tra cứu từ thay thế.
*   **QUY TẮC**:
    1.  **Thuật ngữ y khoa/khoa học** → GIỮ NGUYÊN (ung thư, tiểu đường, nhồi máu...).
    2.  **Từ miêu tả bạo lực/chết chóc** → THAY THẾ theo tone kịch bản.
    3.  **Từ cấm tuyệt đối** (tự tử, tự gây thương tích...) → TRÁNH SỬ DỤNG.
*   **VÍ DỤ THAY THẾ THEO TONE**:
    | Từ gốc | Hài hước | Nghiêm trọng | Đời thường |
    |--------|----------|--------------|------------|
    | chết   | hẹo, tiêu đời | qua đời, thiệt mạng | hết hơi, tạch |
    | giết   | cho hẹo, bay màu | gây tử vong | tiêu diệt |
    | đau    | nhói, buốt | đau đớn | đau, nhức |

### E12. KHUÔN MẶT NHÂN VẬT NHÂN HÓA (Anthropomorphic Face Style) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Các nhân vật KHÔNG PHẢI CON NGƯỜI (bộ phận cơ thể, thực phẩm, dụng cụ, vi khuẩn, môi trường...) KHÔNG ĐƯỢC có khuôn mặt đầy đủ như người.
*   **VÌ SAO QUAN TRỌNG**: Veo 3 dễ lỗi khi render khuôn mặt người trên vật thể không phải người → biến dạng, uncanny valley.
*   **QUY TẮC MÔ TẢ**:
    *   ✅ **CHỈ DÙNG**: Mắt đơn giản (dots/circles), miệng đơn giản (line/curve), biểu cảm cơ bản
    *   ❌ **KHÔNG DÙNG**: Lông mày chi tiết, mũi, tai, cấu trúc mặt người đầy đủ
*   **VÍ DỤ SAI (Mặt người)**:
    ```
    An anthropomorphic liver with detailed human face, eyebrows furrowed, 
    nose wrinkled, full lips frowning...
    ```
    → **SAI**: Quá nhiều chi tiết mặt người → lỗi render
*   **VÍ DỤ ĐÚNG (Mặt đơn giản)**:
    ```
    An anthropomorphic liver, yellow-tinged, with simple dot eyes and 
    a curved frown expression, sweating droplets...
    ```
    → **ĐÚNG**: Mắt chấm, miệng đường cong, không có mũi/tai/lông mày
*   **TEMPLATE CHO NHÂN VẬT NHÂN HÓA**:
    ```
    An anthropomorphic [đối tượng], [màu sắc/chất liệu], with simple 
    [dot eyes/circle eyes] and [curved smile/frown/open mouth expression], 
    [hành động/trạng thái]
    ```
*   **BIỂU CẢM CHO PHÉP**:
    | Cảm xúc | Mô tả mắt | Mô tả miệng |
    |---------|-----------|-------------|
    | Vui | wide dot eyes, sparkles | curved upward smile |
    | Buồn | droopy dot eyes | curved downward frown |
    | Sợ | large circle eyes, shaking | open oval mouth |
    | Giận | narrowed eyes, red glow | zigzag angry mouth |
    | Mệt | half-closed eyes | wavy tired expression |
    | Đắc thắng | half-closed smug eyes | wide grin |

### E13. TIÊU ĐỀ VIDEO (Title Generation) - BẮT BUỘC
*   **MỤC ĐÍCH**: Tiêu đề quyết định 80% CTR (Click-through rate). Tiêu đề hay = nhiều người xem.
*   **CÔNG THỨC TIÊU ĐỀ VIRAL**:
    ```
    [HOOK gây sốc] + [CHỦ ĐỀ] + [YẾU TỐ TÒ MÒ/CẢM XÚC]
    ```
*   **CÁC LOẠI HOOK HIỆU QUẢ**:
    | Loại Hook | Công thức | Ví dụ |
    |-----------|-----------|-------|
    | Số liệu shock | "[SỐ] + [HẬU QUẢ]" | "1 lon nước ngọt = 10 muỗng đường" |
    | Cảnh báo | "[ĐỪNG/CẨN THẬN] + [HÀNH ĐỘNG]" | "ĐỪNG uống nước lạnh sau ăn" |
    | Bí mật | "[BẬT MÍ/TIẾT LỘ] + [CHỦ ĐỀ]" | "Bác sĩ TIẾT LỘ sự thật về..." |
    | Câu hỏi | "[TẠI SAO/THẾ NÀO] + [HIỆN TƯỢNG]?" | "Tại sao uống bia lại đau đầu?" |
    | So sánh | "[A] vs [B]: [CÂU HỎI]" | "Nước nóng vs nước lạnh: Uống gì khi ốm?" |
    | Nhân cách hóa | "[BỘ PHẬN] + [HÀNH ĐỘNG NGƯỜI]" | "Khi gan LÊN TIẾNG đòi nghỉ ngơi" |
    | Đập tan myths | "[SỰ THẬT] về [NIỀM TIN SAI]" | "SỰ THẬT về nước chanh giảm cân" |
    | Listicle | "[SỐ] + [CHỦ ĐỀ] + [HẬU QUẢ]" | "5 sai lầm NGUY HIỂM khi sơ cứu" |
*   **⚠️ HOOK PHẢI LIÊN QUAN TRỰC TIẾP ĐẾN SỨC KHỎE**:
    *   Hook phải nói về **HẬU QUẢ SỨC KHỎE CỤ THỂ**, KHÔNG dùng ẩn dụ công sở/mạng xã hội.
    | Từ/Cụm từ SÁO RỖNG ❌ | Tại sao SAI | Dùng thay ✅ |
    |------------------------|-------------|-------------|
    | "XIN NGHỈ VIỆC" | Ẩn dụ công sở, không liên quan sức khỏe | "KIỆT SỨC", "QUÁ TẢI", "NGỪNG HOẠT ĐỘNG" |
    | "du lịch" (vi khuẩn du lịch) | Ẩn dụ vui vẻ, không gây sốc | "XÂM NHẬP", "LÂY LAN", "TRÀN VÀO" |
    | "BÓC PHỐT" | Từ mạng xã hội, không y khoa | "PHÁT HIỆN", "CẢNH BÁO", "TỐ CÁO" |
    | "HỌP KHẨN" | Ẩn dụ công sở | "BÁO ĐỘNG", "KIỆT SỨC", "SỤP ĐỔ" |
    | "tăng ca" | Ẩn dụ công sở | "HOẠT ĐỘNG QUÁ SỨC", "QUÁ TẢI" |
    | "OT không lương" | Ẩn dụ công sở | "KIỆT SỨC", "CHỊU ĐỰNG" |
*   **NGUYÊN TẮC HOOK ĐÚNG**:
    - ✅ Hook phải nói về **TRIỆU CHỨNG THỰC**: đau, sưng, viêm, loét, tắc, nổ, sụp đổ
    - ✅ Hook phải gây **SỢ HÃI VỀ HẬU QUẢ Y TẾ**: ung thư, đột quỵ, sỏi thận, xơ gan
    - ✅ Hook phải có **SỐ LIỆU Y KHOA CỤ THỂ**: 400%, gấp 3 lần, 10.000 hạt
    - ❌ KHÔNG dùng: Ẩn dụ công sở, từ lóng MXH, metaphor không liên quan sức khỏe
*   **VÍ DỤ SỬA**:
    | SAI ❌ | ĐÚNG ✅ |
    |--------|---------|
    | "Gan đang XIN NGHỈ VIỆC" | "Gan đang SUY KIỆT: 5 dấu hiệu khẩn cấp!" |
    | "Vi khuẩn đi DU LỊCH sang miệng" | "Vi khuẩn XÂM NHẬP miệng bạn" |
    | "Bánh kẹo BÓC PHỐT sức khỏe" | "Bánh kẹo đang PHÁT HIỆN 5 bệnh ẩn!" |
    | "Nội tạng HỌP KHẨN" | "Nội tạng BÁO ĐỘNG: Gan, Thận SUY KIỆT!" |
*   **KEYWORDS SEO KHUYÊN DÙNG**:
    | Keyword | Tác dụng |
    |---------|----------|
    | "Sự thật" / "Bí mật" | Gây tò mò |
    | "ĐỪNG" / "Cẩn thận" | Negative hook (hiệu quả cao) |
    | "SAI LẦM" / "Nguy hiểm" | Fear factor |
    | "Bác sĩ" / "Chuyên gia" | Authority trust |
    | "[SỐ] + danh sách" | Clarity, easy to consume |
    | "ngay" / "tức thì" | Urgency |
    | "Cơ thể lên tiếng" | Trend 2026 |
*   **⚠️ TỪ KHÓA CẤM TRONG TIÊU ĐỀ** (Theo 03_Sensitive_Words_Database):
    | Từ CẤM | Thay bằng |
    |--------|-----------|
    | "chết người" | "nguy hiểm", "cực hại", "gây tổn thương" |
    | "giết" | "hủy diệt", "tàn phá", "gây hại" |
    | "tử vong" | "nguy hiểm đến sức khỏe" |
    | "chết" | "tiêu đời", "hẹo", "game over" |
    → **KIỂM TRA E11** trước khi đặt tiêu đề!
*   **QUY TẮC SỐ TRONG TIÊU ĐỀ LISTICLE**:
    | Loại nội dung | Số tối thiểu | Lý do |
    |---------------|-------------|-------|
    | Sai lầm/Lỗi | 4-5 | Đủ để thuyết phục "nhiều người mắc" |
    | Dấu hiệu/Triệu chứng | 5-7 | Đủ để người xem tự nhận ra |
    | Mẹo/Tips | 4-6 | Đủ để video có substance |
    | Thực phẩm/Đồ vật | 5-7 | Đủ danh sách phong phú |
    → **KHÔNG DÙNG**: "3 dấu hiệu" (quá ít), "2 sai lầm" (quá ít)
    → **NÊN DÙNG**: "5 dấu hiệu", "4 sai lầm", "7 thói quen"
*   **ĐỘ DÀI TỐI ƯU**:
    | Platform | Max ký tự | Khuyến nghị |
    |----------|-----------|-------------|
    | YouTube Shorts | 100 | 50-60 ký tự |
    | TikTok | 150 | 40-50 ký tự |
    | YouTube Long | 100 | 60-70 ký tự |
*   **VÍ DỤ TIÊU ĐỀ**:
    | Chủ đề | Tiêu đề NHẠT ❌ | Tiêu đề VIRAL ✅ |
    |--------|----------------|-----------------|
    | Rượu bia Tết | "Rượu bia hại gan" | "3 ly bia = gan ĐÁNH VẬT 8 tiếng không lương!" |
    | Bánh chưng rán | "Ăn bánh chưng rán không tốt" | "Bánh chưng rán: Combo HỦY DIỆT vòng eo Tết" |
    | Ngộ độc thực phẩm | "An toàn thực phẩm Tết" | "80% tủ lạnh ngày Tết là NGHĨA ĐỊA thực phẩm!" |
    | Đau lưng dọn nhà | "Dọn nhà đau lưng" | "5 thói quen dọn nhà đang TÀN PHÁ cột sống bạn!" |
*   **CHECKLIST TIÊU ĐỀ TRƯỚC KHI DÙNG**:
    - [ ] Không có từ nhạy cảm (chết, giết, tử vong)?
    - [ ] Số trong listicle >= 4?
    - [ ] Có hook gây sốc trong 3 từ đầu?
    - [ ] Độ dài < 60 ký tự?
*   **OUTPUT BẮT BUỘC**: Mỗi dự án phải có 3 phương án tiêu đề để A/B test.
    ```
    TIÊU ĐỀ A (Shock): [...]
    TIÊU ĐỀ B (Question): [...]
    TIÊU ĐỀ C (Listicle): [...]
    ```

### E14. NGHIÊN CỨU SEO (SEO Research) - BẮT BUỘC TRƯỚC KHI TẠO _SEO.txt
*   **MỤC ĐÍCH**: Keywords phải được NGHIÊN CỨU từ trending platforms, KHÔNG chỉ lấy từ tiêu đề.
*   **QUY TRÌNH BẮT BUỘC**:
    | Bước | Hành động | Công cụ |
    |------|-----------|---------|
    | 1 | Search `[chủ đề] + trending + [platform]` | Web Search |
    | 2 | Thu thập hashtags ĐANG HOT trên platforms | TikTok, YouTube, Facebook |
    | 3 | Tìm related/expanded keywords | Google Trends, Keyword Planner |
    | 4 | Xác minh volume search | TubeBuddy, VidIQ, Ahrefs |
    | 5 | Cross-check với đối thủ | Xem video top đang dùng hashtag gì |
*   **NGUỒN RESEARCH BẮT BUỘC**:
    | Platform | Công cụ/Trang | Cách dùng |
    |----------|---------------|-----------|
    | Facebook | Meta Inspiration Hub | Xem trending topics theo category |
    | TikTok | TikTok Creative Center | Xem hashtag trending theo ngành |
    | YouTube | YouTube Trending, VidIQ | Xem tags của video top |
    | Douyin | Douyin Hot Search | Xem xu hướng gốc từ Trung Quốc |
    | Google | Google Trends Vietnam | So sánh volume search |
*   **LOẠI KEYWORDS CẦN THU THẬP**:
    | Loại | Mô tả | Ví dụ |
    |------|-------|-------|
    | Primary | Keyword chính của chủ đề | "ngộ độc thực phẩm" |
    | Secondary | Keywords liên quan | "vi khuẩn salmonella", "tiêu chảy" |
    | Long-tail | Cụm từ tìm kiếm dài | "cách bảo quản thực phẩm tết an toàn" |
    | Trending | Đang hot trên platforms | "#TetAnToan", "#FoodSafety2026" |
    | Related | Mở rộng từ chủ đề | "bảo quản tủ lạnh", "nhiệt độ an toàn" |
*   **TEMPLATE FILE _SEO.txt SAU RESEARCH**:
    ```
    # SEO METADATA - [TÊN DỰ ÁN]
    # Ngày research: YYYY-MM-DD
    # Nguồn: [Liệt kê platforms đã research]
    
    ## TIÊU ĐỀ (A/B TEST)
    A (Shock): [...]
    B (Question): [...]
    C (Listicle): [...]
    
    ## HASHTAGS TRENDING (từ research)
    ### TikTok:
    - #Hashtag1 (view count: X)
    - #Hashtag2 (view count: X)
    
    ### YouTube:
    - #Hashtag1
    - #Hashtag2
    
    ## KEYWORDS (từ research)
    ### Primary: keyword1, keyword2
    ### Secondary: keyword3, keyword4
    ### Long-tail: "cụm từ dài 1", "cụm từ dài 2"
    
    ## SEARCH VOLUME (từ VidIQ/TubeBuddy)
    - keyword1: XX,XXX searches/month
    - keyword2: XX,XXX searches/month
    
    ## COMPETITOR TAGS (từ video top)
    tags từ video đang top: tag1, tag2, tag3...
    
    ## DESCRIPTION (YouTube)
    [Mô tả có chứa keywords tự nhiên]
    ```
*   **VÍ DỤ SAI (Không research)**:
    ```
    Keywords: dọn nhà, tết, hóa chất  ← Chỉ lấy từ tiêu đề, quá chung chung
    ```
*   **VÍ DỤ ĐÚNG (Có research)**:
    ```
    ## KEYWORDS (từ research 2026-01-05)
    ### Primary: hóa chất tẩy rửa độc hại, ngộ độc hóa chất
    ### Secondary: VOC, benzene, amoniac, chlorine, formalin
    ### Long-tail: "cách dọn nhà an toàn không hít hóa chất"
    ### Trending TikTok: #DonNhaDonTet (5M views), #HoaChatDocHai (2M)
    ### Competitor tags: cleaning safety, toxic chemicals home
    ```
*   **CHECKLIST TRƯỚC KHI TẠO _SEO.txt**:
    - [ ] Đã search trending trên TikTok?
    - [ ] Đã check hashtags YouTube?
    - [ ] Đã tìm related keywords?
    - [ ] Đã xem tags của video đối thủ top?
    - [ ] Đã ghi chú nguồn research?

### E15. LOGIC HIỂN THỊ HẬU QUẢ (Consequence Visualization Logic) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Hậu quả phải được hiển thị trên CHỦ THỂ CHỊU TÁC ĐỘNG (con người), không chỉ trên nội tạng/cơ quan bên trong.
*   **VÌ SAO QUAN TRỌNG**: Người xem cần thấy hậu quả NHÌN THẤY ĐƯỢC trên cơ thể họ, không chỉ là cơ chế bên trong.
*   **NGUYÊN TẮC**:
    | Cơ quan gây vấn đề | Hậu quả NHÌN THẤY trên người | Cách mô tả ĐÚNG |
    |-------------------|------------------------------|-----------------|
    | Gan (bilirubin) | Vàng DA người, vàng MẮT người | "Human skin turning yellowish, eyes showing yellow tint" |
    | Thận (muối) | Phù CHÂN người, phù MẶT người | "Person's legs visibly swollen, puffy face" |
    | Tim (loạn nhịp) | Người đổ mồ hôi, tái mặt | "Person sweating, pale face, clutching chest" |
    | Ruột (táo bón) | Người bụng phình, khó chịu | "Person with bloated belly, uncomfortable expression" |
    | Phổi (viêm) | Người ho, khó thở | "Person coughing, gasping for breath" |
*   **VÍ DỤ SAI (Chỉ trên nội tạng)**:
    ```
    Consequence: Liver turning yellowish, yellowish tint appearing on liver edges
    ```
    → **SAI**: Gan vàng nhưng NGƯỜI XEM không thấy vàng da ở đâu!
*   **VÍ DỤ ĐÚNG (Trên cả nội tạng VÀ con người)**:
    ```
    Split screen. Left: Anthropomorphic liver with tired expression, bilirubin 
    particles accumulating. Right: Human person with visibly yellow skin and 
    yellowish eyes, looking tired and unwell.
    ```
    → **ĐÚNG**: Vừa thấy cơ chế (gan) VÀ hậu quả nhìn thấy (người vàng da).
*   **KỸ THUẬT SPLIT SCREEN CHO HẬU QUẢ**:
    | Cảnh trái | Cảnh phải |
    |-----------|-----------|
    | Nội tạng đang gặp vấn đề | Con người thể hiện triệu chứng |
    | Cơ chế bên trong | Biểu hiện bên ngoài |
    | Nguyên nhân (vi mô) | Hậu quả (vĩ mô nhìn thấy) |
*   **CHECKLIST**:
    - [ ] Hậu quả có hiển thị trên CON NGƯỜI không?
    - [ ] Người xem có thể TỰ NHẬN RA triệu chứng trên bản thân không?
    - [ ] Có dùng Split Screen nếu cần thể hiện cả cơ chế và hậu quả không?
    - [ ] Triệu chứng có NHÌN THẤY ĐƯỢC (da, mắt, dáng đi, mồ hôi) không?

### E16. ĐỒNG BỘ BIBLE ↔ MASTER ↔ PROMPTS (Sync Rule) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Mô tả nhân vật/bối cảnh trong Bible PHẢI được COPY-PASTE Y NGUYÊN sang Master và Prompts.
*   **VÌ SAO QUAN TRỌNG**: Mỗi prompt Veo 3 là độc lập → Mô tả khác = Render khác = Mất nhất quán.
*   **NGUYÊN TẮC SYNC**:
    | Từ | Sang | Cách thực hiện |
    |----|------|----------------|
    | Bible: Nhân vật | Master: Character description | COPY-PASTE chính xác |
    | Bible: Nhân vật | Prompts: Character description | COPY-PASTE chính xác (bỏ thoại) |
    | Bible: Bối cảnh | Master: Setting description | COPY-PASTE chính xác |
    | Bible: Chủ Thể | Master: Host description | COPY-PASTE chính xác |
    | Bible: Visual Style | Master: Prefix mỗi prompt | COPY-PASTE chính xác |
*   **VÍ DỤ SAI (Diễn đạt khác nhau)**:
    ```
    BIBLE: "An anthropomorphic liver with simple dot eyes showing exhaustion"
    MASTER: "A tired liver character with half-closed eyes"
    PROMPTS: "Exhausted liver organ with sleepy expression"
    ```
    → **SAI**: 3 cách diễn đạt khác nhau → Veo render 3 nhân vật KHÁC NHAU!
*   **VÍ DỤ ĐÚNG (Copy-paste chính xác)**:
    ```
    BIBLE: "An anthropomorphic reddish-brown liver with simple dot eyes 
           showing exhaustion (half-closed), curved tired mouth"
    
    MASTER: "[...] An anthropomorphic reddish-brown liver with simple dot eyes 
            showing exhaustion (half-closed), curved tired mouth [...]"
    
    PROMPTS: "An anthropomorphic reddish-brown liver with simple dot eyes 
             showing exhaustion (half-closed), curved tired mouth"
    ```
    → **ĐÚNG**: Cùng 1 mô tả = Veo render nhất quán!
*   **QUY TRÌNH VIẾT**:
    1. **Bước 1**: Define trong Bible (nguồn chính thức)
    2. **Bước 2**: Copy-paste sang Master (thêm context, thoại)
    3. **Bước 3**: Copy-paste sang Prompts (bỏ thoại, bỏ audio)
    4. **Bước 4**: Cross-check 3 file có CÙNG mô tả không
*   **MAPPING BIBLE → OUTPUT**:
    | Section trong Bible | Vị trí trong Master | Vị trí trong Prompts |
    |--------------------|---------------------|---------------------|
    | 2. Nhân vật | Mỗi dòng: Character description | Mỗi prompt: Character |
    | 3. Chủ Thể | Consequence scenes | Consequence scenes |
    | 4. Bối cảnh | Mỗi dòng: Setting | Mỗi prompt: Setting |
    | 5. Voice & Style | [Region][Gender][Age][Tone] | - (không cần) |
    | 6. Visual Style | Prefix mỗi dòng | Prefix mỗi prompt |
*   **CHECKLIST**:
    - [ ] Mô tả nhân vật Bible = Master = Prompts?
    - [ ] Mô tả bối cảnh Bible = Master = Prompts?
    - [ ] Visual Style prefix nhất quán trong mọi prompt?
    - [ ] Chủ Thể mô tả giống nhau khi xuất hiện?

### E17. TUYẾN NHÂN VẬT BẮT BUỘC (Character Lineup Structure) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Mỗi video short-form PHẢI có 3 loại nhân vật để đảm bảo logic kể chuyện hoàn chỉnh.
*   **3 LOẠI NHÂN VẬT**:
    | # | Loại | Vai trò | Scene xuất hiện |
    |---|------|---------|-----------------|
    | 1 | **CHỦ THỂ (Human Subject)** | Người chịu tác động | Opening + Consequence |
    | 2 | **NHÂN VẬT NHÂN HÓA** | Giải thích cơ chế | Mechanism |
    | 3 | **CHUYÊN GIA (Expert)** | Cung cấp giải pháp | Solution |
*   **CHI TIẾT**:
    *   **CHỦ THỂ**: Con người THẬT chịu tác động từ vấn đề
        - Template: `A [age-range] Asian [man/woman], [age]s, wearing [trang-phục]`
        - Trạng thái: Bình thường → Có triệu chứng → Hồi phục
    *   **NHÂN VẬT NHÂN HÓA**: Đồ vật/nội tạng được nhân cách hóa
        - Template: `An anthropomorphic [màu] [hình] with simple dot eyes showing [emotion], curved [kiểu] mouth`
        - Loại: Nội tạng (Gan, Tim) / Thực phẩm / Dụng cụ
    *   **CHUYÊN GIA**: Người có chuyên môn (Bác sĩ, Dinh dưỡng viên)
        - Template chuẩn: `A professional [male/female] doctor, [35s/40s], wearing white coat, confident expression`
*   **PHÂN BỐ THEO PMCS**:
    | Scene | Nhân vật |
    |-------|----------|
    | Opening (P) | Chủ thể + Nhân vật nhân hóa |
    | Mechanism (M) | Nhân vật nhân hóa (giải thích) |
    | Consequence (C) | **Split Screen**: Nhân vật + Chủ thể có triệu chứng |
    | Solution (S) | Chuyên gia + Chủ thể hồi phục |
*   **CHECKLIST**:
    - [ ] Có Chủ thể với trạng thái bình thường + triệu chứng?
    - [ ] Có ít nhất 1 nhân vật nhân hóa?
    - [ ] Có Chuyên gia cho Solution scene?

### E18. NHẤT QUÁN GIỌNG NÓI (Voice Consistency) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Mỗi nhân vật PHẢI giữ nguyên Voice Metadata xuyên suốt video.
*   **QUY TẮC**:
    | Nhân vật | Voice xuyên suốt? | Quy tắc |
    |----------|-------------------|---------|
    | Chủ thể | ✅ Giữ nguyên | Cùng Region/Gender/Age khi xuất hiện |
    | Nhân vật chính (Gan, Tim) | ✅ Giữ nguyên | Nói xuyên Mechanism + Consequence |
    | Nhân vật phụ (Virus, Enzym) | ⚠️ Có thể khác | Khác giọng để phân biệt với NV chính |
    | Chuyên gia | ✅ CHUẨN HÓA | Luôn dùng: [Nam] [Female] [35s] [Chuyên nghiệp] |
*   **VÍ DỤ**:
    ```
    Scene 1 (Opening): Gan nói [Nam 40s, Mệt mỏi]
    Scene 3 (Mechanism): Gan nói [Nam 40s, Hoảng loạn] ← CÙNG Gender/Age
    Scene 5 (Consequence): Gan nói [Nam 40s, Đau đớn] ← CÙNG Gender/Age
    Scene 7 (Solution): Bác sĩ nói [Nữ 35s, Chuyên nghiệp] ← CHUẨN cho Expert
    ```
*   **CHECKLIST**:
    - [ ] Cùng nhân vật = Cùng Region/Gender/Age?
    - [ ] Chuyên gia dùng voice chuẩn hóa?
    - [ ] Nhân vật phụ có voice khác biệt?

### E19. FILE PROMPTS_REF CHO ĐỐI CHIẾU HÌNH ẢNH (Prompts_Ref Format) - BẮT BUỘC
*   **MỤC ĐÍCH**: Tạo file `_Prompts_Ref.txt` chứa character tags để auto-match với file hình ảnh bên ngoài.
*   **VÌ SAO CẦN**: 
    - Tăng tính đồng bộ hình ảnh nhân vật
    - Hỗ trợ tool auto-match image theo filename
    - Mỗi prompt cách nhau 1 dòng trống để tách biệt
*   **QUY TẮC TÊN VIẾT TẮT**:
    | Loại | Quy tắc | Ví dụ |
    |------|---------|-------|
    | Nội tạng | Tên tiếng Việt không dấu, viết hoa | `[GAN]`, `[TIM]`, `[THAN]`, `[RUOT]` |
    | Thực phẩm | Tên viết tắt không dấu | `[BANH_CHUNG]`, `[MUT]`, `[BIA]` |
    | Người | Vai trò viết tắt | `[CHU_THE]`, `[BAC_SI]`, `[ME]`, `[BO]` |
    | Dụng cụ | Tên viết tắt | `[TU_LANH]`, `[DUA]`, `[NOI]` |
    | Vi khuẩn/Virus | Tên viết tắt | `[VI_KHUAN]`, `[ETHANOL]`, `[DUONG]` |
*   **FORMAT FILE `_Prompts_Ref.txt`**:
    ```
    [TAG_NV1] [TAG_NV2] Prompt text here...
    
    [TAG_NV1] Prompt text for next scene...
    
    [TAG_NV1] [CHU_THE] Split screen prompt...
    ```
*   **VÍ DỤ TOPIC 19 (Gan Lên Tiếng)**:
    ```
    [GAN] Opening scene. The 3D cute animation style, Pixar render, soft lighting. 
    An anthropomorphic reddish-brown liver organ with simple dot eyes showing 
    exhaustion (half-closed), curved tired mouth...

    [GAN] [ETHANOL] Mechanism 1. Close-up shot. Tiny green spherical enzyme 
    particles (ALT, AST) with simple dot eyes frantically moving...

    [GAN] [CHU_THE] Consequence 2 - Split Screen. Left: An anthropomorphic 
    reddish-brown liver organ... Right: A middle-aged Asian man with yellowish skin...

    [BAC_SI] Solution. A professional female doctor, 35s, wearing white coat...
    ```
*   **QUY TẮC TAGS**:
    - Tag đặt ở ĐẦU mỗi prompt, TRƯỚC nội dung
    - Nếu có nhiều nhân vật trong 1 scene → Liệt kê tất cả tags
    - Dùng `[CHU_THE]` cho Human Subject
    - Dùng `[BAC_SI]` hoặc `[CHUYEN_GIA]` cho Expert
*   **BẢNG TAGS CHUẨN HÓA**:
    | Nhân vật | Tag chuẩn |
    |----------|-----------|
    | Gan | `[GAN]` |
    | Tim | `[TIM]` |
    | Thận | `[THAN]` |
    | Dạ dày | `[DA_DAY]` |
    | Ruột | `[RUOT]` |
    | Phổi | `[PHOI]` |
    | Não | `[NAO]` |
    | Chủ thể (người) | `[CHU_THE]` |
    | Bác sĩ | `[BAC_SI]` |
    | Enzym | `[ENZYM]` |
    | Ethanol/Cồn | `[ETHANOL]` |
    | Đường | `[DUONG]` |
    | Vi khuẩn | `[VI_KHUAN]` |
*   **DELIVERY PACKAGE MỚI (6 files)**:
    | # | File | Mục đích |
    |---|------|----------|
    | 1 | `_Bible.md` | Nhân vật, Bối cảnh, PMCS |
    | 2 | `_Master.txt` | Kịch bản gốc (Visual + Audio) |
    | 3 | `_Prompts.txt` | Visual prompts (clean) |
    | 4 | `_Prompts_Ref.txt` | Visual prompts + Character tags |
    | 5 | `_Dubbing.txt` | Lời thoại |
    | 6 | `_SEO.txt` | Tiêu đề, Hashtags, Keywords |
*   **CHECKLIST**:
    - [ ] Mỗi prompt cách nhau 1 dòng trống?
    - [ ] Tags đặt ở đầu mỗi prompt?
    - [ ] Đã liệt kê tất cả nhân vật xuất hiện trong scene?
    - [ ] Tags dùng format chuẩn (không dấu, viết hoa)?

### E20. THƯ VIỆN CHUYỂN CẢNH HOLLYWOOD (Professional Transitions Library) - BẮT BUỘC
*   **MỤC ĐÍCH**: Sử dụng kỹ thuật chuyển cảnh chuyên nghiệp như các hãng phim lớn (Pixar, Disney, Marvel).
*   **BẢNG KỸ THUẬT CHUYỂN CẢNH**:

| # | Kỹ thuật | Mô tả | Khi dùng | Ví dụ mô tả trong prompt |
|---|----------|-------|----------|--------------------------|
| 1 | **Hard Cut** | Cắt trực tiếp, không hiệu ứng | Chuyển nhanh giữa các hành động | `Cut to...` |
| 2 | **Match Cut** | Cắt theo hình dạng/màu sắc tương đồng | Liên kết 2 ý tưởng, time skip | `Match cut from circular liver to round belly of human` |
| 3 | **J-Cut** | Âm thanh scene SAU nghe trước khi hình đổi | Tạo anticipation, smooth dialogue | `Audio of screaming begins while still showing calm scene...` |
| 4 | **L-Cut** | Âm thanh scene TRƯỚC tiếp tục khi hình đã đổi | Duy trì emotion trong dialogue | `Previous dialogue continues over new visual...` |
| 5 | **Dissolve/Crossfade** | Hình mờ dần chồng lên hình mới | Passage of time, dream sequence | `Slowly dissolves to...`, `Fading transition to...` |
| 6 | **Wipe** | Hình mới "quét" qua hình cũ | Sci-fi, stylized, Star Wars style | `Wipe transition from left to right reveals...` |
| 7 | **Smash Cut** | Cắt đột ngột, gây sốc | Comedy, horror, irony | `Abruptly cuts to...` |
| 8 | **Montage** | Nhiều shot ngắn ghép lại với nhạc | Training, time passage, compilation | `Montage sequence showing...` |
| 9 | **Zoom Out → Pan** | Từ close-up zoom ra rồi pan sang | Nối 2 nhân vật trong cùng space | `Camera zooms out then pans to reveal...` |
| 10 | **Follow the Flow** | Camera theo dòng chất lỏng/đường dẫn | Nội tạng, máu, dây điện | `Camera follows the blood flow from heart to liver...` |
| 11 | **Invisible Wipe** | Ẩn cut sau vật che (cột, người đi qua) | Seamless, ẩn cut | `As person walks past, scene transforms to...` |
| 12 | **Whip Pan** | Camera quay cực nhanh | Action, chaos, urgency | `Rapid whip pan to...` |

*   **KỸ THUẬT THEO LOẠI CONTENT**:

| Loại Video | Kỹ thuật khuyên dùng |
|------------|---------------------|
| Health/Medical | Match Cut, Follow the Flow, Split Screen |
| Comedy/Entertainment | Smash Cut, Whip Pan, Jump Cut |
| Educational | Dissolve, L-Cut, Zoom Out → Pan |
| Dramatic/Emotional | J-Cut, Dissolve, Match Cut |
| Action/Intense | Hard Cut, Whip Pan, Smash Cut |

*   **VÍ DỤ ÁP DỤNG CHO TET SERIES**:

| Từ cảnh | Sang cảnh | Kỹ thuật | Mô tả prompt |
|---------|-----------|----------|--------------|
| Gan đang than phiền | Người vàng da | Match Cut | `Match cut from yellowish liver surface to person's yellowish skin tone` |
| Bác sĩ đang nói | Người áp dụng lời khuyên | L-Cut | `Doctor's voice continues as visual transitions to person drinking water` |
| Đồ ăn thối | Vi khuẩn xâm nhập | Follow the Flow | `Camera follows bacteria particles as they travel from food into stomach` |
| Cảnh yên bình | Cảnh hỗn loạn | Smash Cut | `Peaceful sleeping scene smash cuts to alarm blaring chaos` |

*   **TEMPLATE MÔ TẢ TRONG MASTER**:
```
[Scene Type]. [Transition: Kỹ thuật]. [Shot type]. [Visual Style]. [Setting]. [Character + Action]. [Audio]. [Voice] "Thoại"
```
Ví dụ:
```
Consequence scene. Match cut from liver to human. Split screen. The 3D cute animation style, Pixar render. Left: Interior body. Right: Living room. Left: Liver with exhausted expression. Right: Man with yellow skin. Audio of tired sigh. [Nam 40s, Mệt mỏi] "Thấy chưa, tôi mệt quá nên da ông cũng vàng theo đó!"
```

*   **CHECKLIST**:
    - [ ] Đã chọn transition phù hợp với mood scene?
    - [ ] Transition được mô tả rõ ràng trong prompt?
    - [ ] Logic giữa 2 scene được kết nối?
    - [ ] Không dùng quá nhiều kỹ thuật khác nhau (gây rối)?

### E21. COPY-PASTE CHARACTER BIBLE (Character Description Enforcement) - BẮT BUỘC NGHIÊM NGẶT
*   **ĐỊNH NGHĨA**: Mô tả nhân vật trong Master/Prompts PHẢI được COPY-PASTE từ Bible.md. KHÔNG ĐƯỢC tự viết tắt, tóm tắt, hoặc đơn giản hóa.
*   **VÌ SAO QUAN TRỌNG**: 
    - Veo 3 tạo mỗi clip ĐỘC LẬP nên KHÔNG NHỚT nhân vật từ clip trước
    - Nếu thiếu mô tả → Veo tự sáng tác → MẤT NHẤT QUÁN
    - Mỗi prompt là 1 unit riêng biệt, phải chứa đầy đủ thông tin

*   **QUY TẮC BẮT BUỘC**:

| # | Yêu cầu | Chi tiết |
|---|---------|----------|
| 1 | **MINIMUM 30 WORDS** per character | Mỗi nhân vật ≥ 30 từ tiếng Anh trong mô tả |
| 2 | **COPY từ Bible** | KHÔNG tự viết mới, phải lấy từ Bible.md |
| 3 | **Age BẮT BUỘC** | "X years old" PHẢI có trong mô tả |
| 4 | **Trang phục BẮT BUỘC** | "wearing..." PHẢI có |
| 5 | **Biểu cảm BẮT BUỘC** | "...expression" PHẢI có |
| 6 | **Prompt Length** | Mỗi scene ≥ 150 words tổng |

*   **VÍ DỤ SAI (Abbreviated - TUYỆT ĐỐI CẤM)**:
    ```
    Brain with sad expression, gray cloud above
    ```
    → ❌ **SAI**: Chỉ 6 từ, thiếu chi tiết, không có age, outfit

*   **VÍ DỤ SAI #2**:
    ```
    Doctor appearing with comforting gesture
    ```
    → ❌ **SAI**: Không có age, không có trang phục, không có ngoại hình

*   **VÍ DỤ ĐÚNG (Full Description - BẮT BUỘC)**:
    ```
    An anthropomorphic pink brain organ, wrinkled surface, with simple dot eyes 
    showing sadness (half-closed, downturned), curved sad mouth, gray cloud 
    hovering above representing blues
    ```
    → ✅ **ĐÚNG**: 32 từ, đầy đủ chi tiết về shape, color, eyes, mouth, accessory

*   **VÍ DỤ ĐÚNG #2**:
    ```
    A professional female psychologist, 40 years old, wearing casual professional 
    clothes (light cardigan over blouse), warm comforting expression, gentle eyes, 
    holding hands in supportive gesture
    ```
    → ✅ **ĐÚNG**: 30 từ, có age, outfit, expression, action

*   **WORKFLOW VIẾT MASTER/PROMPTS**:
    1. Mở file `_Bible.md` của topic
    2. Tìm phần "COPY-PASTE vào Master/Prompts"
    3. COPY NGUYÊN VĂN mô tả nhân vật
    4. PASTE vào Master.txt / Prompts.txt
    5. KHÔNG ĐƯỢC sửa đổi, rút gọn

*   **CHARACTER FORMAT CHUẨN TRONG MASTER**:
    ```
    [Scene type]. [Shot type]. [Visual style]. [Setting description]. 
    [FULL CHARACTER DESCRIPTION từ Bible - ≥30 words]. [Action]. 
    [Audio]. [Voice metadata] "Thoại", no text, no subtitles, no labels, no watermarks
    ```

*   **CHECKLIST E21** (PHẢI check TRƯỚC khi submit):
    - [ ] Mỗi nhân vật có ≥ 30 từ mô tả?
    - [ ] Mô tả có COPY từ Bible.md không?
    - [ ] Có "X years old" (tuổi) với nhân vật người?
    - [ ] Có "wearing..." (trang phục)?
    - [ ] Có "...expression" (biểu cảm)?
    - [ ] Mỗi scene ≥ 150 words?
    - [ ] So sánh với Golden Sample (Topic 31) - format giống không?
    - [ ] **KHÔNG thiếu chi tiết nhỏ** (accessories, props, facial features)?

### E21.1 PHÁT HIỆN LỖI ĐỒNG BỘ - BẮT BUỘC

*   **QUY TẮC KIỂM TRA**: So sánh CHÍNH XÁC từng từ giữa Bible và Master/Prompts

**VÍ DỤ LỖI THƯỜNG GẶP** (CẤM TUYỆT ĐỐI):

| Bible (Nguồn gốc) | Master (SAI - thiếu chi tiết) | LÝ DO SAI |
|-------------------|-------------------------------|-----------|
| "small dark purple rod-shaped villain **with spiky projections**, wearing tiny black cloak, **menacing** red glowing eyes, **villainous grin showing sharp teeth**, **holding miniature syringe filled with glowing green toxin**" | "small dark purple rod-shaped villain wearing tiny black cloak, red glowing eyes, villainous grin" | ❌ Thiếu: spiky projections, sharp teeth, syringe - Veo sẽ render khác |
| "A middle-aged Vietnamese woman, 42 years old, **medium build**, **shoulder-length black hair tied back**, wearing **casual home clothes (light blue cotton t-shirt and gray sweatpants)**, **warm but tired expression with slight dark circles under eyes**" | "A middle-aged Vietnamese woman, 42 years old, wearing light blue t-shirt and gray sweatpants" | ❌ Thiếu: medium build, hair details, tired expression - Mất nhất quán |
| "An anthropomorphic reddish-brown liver organ, **round squishy shape** with simple dot eyes **showing concern**, **curved worried mouth**, **no human facial features like nose or ears**, **wearing tiny medical mask for protection**" | "A reddish-brown anthropomorphic liver with worried dot eyes and medical mask" | ❌ Thiếu: shape, mouth detail, no nose/ears - Render sai hình dáng |

**WORKFLOW ĐÚNG** (BẮT BUỘC tuân thủ):
1. Mở `_Bible.md` 
2. Tìm phần mô tả nhân vật (ví dụ: `### [BOTULINUM] Clostridium Botulinum Bacteria`)
3. **SELECT TOÀN BỘ** mô tả (Ctrl+A vùng text)
4. **COPY** (Ctrl+C)
5. Mở `_Master.txt`
6. **PASTE** (Ctrl+V) vào đúng vị trí `[BOTULINUM] ...`
7. **KHÔNG SỬA GÌ** - giữ nguyên 100%
8. Lặp lại cho `_Prompts.txt`

**CHECKLIST BẮT BUỘC SAU KHI VIẾT XONG**:
- [ ] Word count: Bible description = Master description?
- [ ] Character count: Bible = Master (±5 ký tự do xuống dòng)?
- [ ] Accessories/Props: Bible mentions syringe → Master PHẢI có syringe?
- [ ] Visual details: Bible mentions "spiky" → Master PHẢI có "spiky"?
- [ ] Facial features: Bible mentions "sharp teeth" → Master PHẢI có "sharp teeth"?

**CÔNG CỤ KIỂM TRA NHANH** (Terminal):
```bash
# So sánh word count
grep "\[BOTULINUM\]" Bible.md | wc -w
grep "\[BOTULINUM\]" Master.txt | wc -w
# Kết quả phải BẰNG NHAU (±2 từ)
```



### E22. LINH HOẠT 8-12 PHÂN CẢNH (Flexible Scene Count) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Mỗi video PHẢI có **8-12 phân cảnh** (linh hoạt theo chủ đề) để đảm bảo giải thích kỹ lưỡng.
*   **VÌ SAO QUAN TRỌNG**:
    - Ít scenes = Nội dung nén = Nói nhanh = Thiếu thông tin
    - Video ngắn cần đủ scenes để cover đầy đủ PMCS
    - Người xem cần thời gian tiêu hóa thông tin

*   **CẤU TRÚC 8-12 SCENES CHUẨN (Linh hoạt)**:

| # | Scene Type | Mục đích | Số lượng |
|---|------------|----------|----------|
| 1 | **Opening/Hook** | Thu hút, giới thiệu vấn đề | 1 scene |
| 2 | **Problem Detail** | Chi tiết vấn đề, số liệu gây sốc | 1 scene |
| 3-5 | **Mechanism 1-3** | Cơ chế sinh học, khoa học | 3 scenes |
| 6-7 | **Consequence 1-2** | Hậu quả, tác hại cụ thể | 2 scenes |
| 8-9 | **Solution 1-2** | Giải pháp chi tiết | 2 scenes |
| 10 | **Outro/CTA** | Kết thúc, kêu gọi chia sẻ | 1 scene |

*   **CÔNG THỨC MỞ RỘNG NẾU CẦN (12 scenes)**:

| # | Scene Type | Chi tiết |
|---|------------|----------|
| 1 | Opening/Hook | Gây sốc ngay giây đầu |
| 2 | Problem Intro | Nhân vật chính than phiền |
| 3 | Mechanism 1 | Cơ chế khoa học A |
| 4 | Mechanism 2 | Cơ chế khoa học B |
| 5 | Mechanism 3 | Cơ chế khoa học C |
| 6 | Consequence 1 | Hậu quả trên cơ thể |
| 7 | Consequence 2 | Hậu quả nghiêm trọng hơn |
| 8 | Solution Intro | Chuyên gia xuất hiện |
| 9 | Solution 1 | Giải pháp A |
| 10 | Solution 2 | Giải pháp B + C |
| 11 | Conclusion | Nhân vật hồi phục |
| 12 | Outro/CTA | Kêu gọi hành động |

*   **VÍ DỤ SAI (Chỉ 5 scenes)**:
    ```
    1. Opening
    2. Mechanism (nhồi nhét 3 cơ chế)
    3. Consequence
    4. Solution (nhồi nhét 2 giải pháp)
    5. Conclusion
    6. Outro
    ```
    → ❌ SAI: Mechanism và Solution bị nén, nói quá nhanh

*   **VÍ DỤ ĐÚNG (10 scenes - Tham khảo Topic 31, hoặc 8 scenes cho topic ngắn)**:
    ```
    1. Opening - Woman opens refrigerator
    2. Problem Hook - Bánh chưng speaks
    3. Mechanism 1 - Bacteria multiplying
    4. Mechanism 2 - Danger Zone
    5. Mechanism 3 - Clostridium toxin
    6. Consequence 1 - Woman eats
    7. Consequence 2 - Stomach invasion
    8. Solution 1 - Doctor appears
    9. Solution 2 - Proper storage
    10. Solution 3 - Reheat properly
    11. Conclusion - Happy ending
    12. Outro - CTA
    ```
    → ✅ ĐÚNG: 12 scenes, mỗi scene 1 focus

*   **CHECKLIST E22**:
    - [ ] Đếm số scenes ≥ 10?
    - [ ] Mechanism có 3+ scenes riêng biệt?
    - [ ] Solution có 2+ scenes riêng biệt?
    - [ ] Mỗi scene chỉ có 1 focus chính?
    - [ ] Không nhồi nhét nhiều thông tin vào 1 scene?

### E23. GIỚI HẠN ĐỘ DÀI THOẠI (Dialogue Length Limit) - BẮT BUỘC NGHIÊM NGẶT
*   **ĐỊNH NGHĨA**: Mỗi scene KHÔNG ĐƯỢC có thoại quá 20 từ tiếng Việt.
*   **VÌ SAO QUAN TRỌNG**:
    - Clip 8 giây × 3 từ/giây = 24 từ maximum
    - Buffer 4 từ cho ngắt nghỉ, emphasis
    - Thoại dài = Đọc nhanh = Người xem không kịp hiểu

*   **BẢNG TÍNH TOÁN**:

| Thời lượng clip | Tốc độ đọc | Từ tối đa | An toàn (buffer) |
|-----------------|------------|-----------|------------------|
| 8 giây | 3 từ/giây | 24 từ | **20 từ** |
| 8 giây | 4 từ/giây (nhanh) | 32 từ | 28 từ |
| 8 giây | 2.5 từ/giây (chậm) | 20 từ | 18 từ |

*   **CÁCH ĐẾM TỪ**:
    - Đếm từ thực tế (không tính dấu câu)
    - Số cũng tính là 1 từ (VD: "40%" = 1 từ)
    - Từ ghép tính riêng ("Hệ miễn dịch" = 3 từ)

*   **VÍ DỤ SAI (Quá dài - 25 từ)**:
    ```
    "Tết vui quá, dopamine và serotonin TIẾT NHIỀU. Hết Tết, chúng DROP xuống - 
    não cảm thấy TRỐNG RỖNG! Đây là điều hoàn toàn bình thường!"
    ```
    → ❌ SAI: 25 từ, quá dài, phải chia

*   **VÍ DỤ ĐÚNG (Chia thành 2 scenes)**:
    ```
    Scene 5: "Tết vui quá, dopamine và serotonin TIẾT NHIỀU!"  (9 từ)
    Scene 6: "Hết Tết, chúng DROP - não cảm thấy TRỐNG RỖNG!" (10 từ)
    ```
    → ✅ ĐÚNG: Mỗi scene ≤20 từ, có thời gian để emphasis

*   **WORKFLOW KHI THOẠI QUÁ DÀI**:
    1. Đếm số từ trong thoại
    2. Nếu >20 từ → SPLIT thành 2 scenes
    3. Mỗi scene mới cần visual riêng
    4. Thêm transition giữa 2 scenes mới

*   **CHECKLIST E23**:
    - [ ] Mỗi thoại ≤ 20 từ tiếng Việt?
    - [ ] Nếu >20 từ, đã chia thành scenes riêng?
    - [ ] Có buffer cho ngắt nghỉ, emphasis?
    - [ ] Thoại không quá nhanh khi đọc thử?

### E24. CHUYỂN ĐỔI KÝ TỰ ĐẶC BIỆT TRONG THOẠI (Special Character Conversion) - BẮT BUỘC NGHIÊM NGẶT
*   **ĐỊNH NGHĨA**: Veo TTS có thể đọc sai hoặc BỎ QUA hoàn toàn các ký tự đặc biệt. Phải chuyển về dạng chữ tự nhiên.
*   **VÌ SAO QUAN TRỌNG**:
    - Ký tự như `>`, `=`, `-`, `!`, `:` thường bị đọc sai hoặc bỏ qua
    - Số liệu quan trọng bị mất nghĩa
    - Người xem không hiểu đầy đủ thông tin
    - Thoại nghe không tự nhiên

*   **BẢNG CHUYỂN ĐỔI BẮT BUỘC**:

| Ký tự | Veo đọc thành | Chuyển thành (Tiếng Việt tự nhiên) |
|-------|---------------|-------------------------------------|
| `>` | (bỏ qua) | "lớn hơn", "hơn", "vượt", "trên" |
| `<` | (bỏ qua) | "nhỏ hơn", "dưới", "ít hơn" |
| `=` | (bỏ qua) | **LOẠI BỎ**, dùng câu nối: "sẽ dẫn đến", "gây ra", "khiến" |
| `!` | (giọng hét) | **LOẠI BỎ**, dùng dấu chấm `.` hoặc viết lại câu |
| `%` | "phần trăm" | "phần trăm" (viết đầy đủ) |
| `-` (range) | (bỏ qua) | "đến", "tới", "khoảng" |
| `+` | (bỏ qua) | "cộng", "tăng thêm", "và" |
| `/` | (bỏ qua) | "trên", "mỗi", "chia" |
| `°` | (bỏ qua) | "độ" |
| `:` (ratio) | (bỏ qua) | "phần", "trên" |
| `:` (list) | (bỏ qua) | Dùng từ nối: ", bạn nên", ", hãy" |
| `×` hoặc `x` | (bỏ qua) | "nhân", "lần" |

#### E24.1 LOẠI BỎ DẤU BẰNG `=` - Dùng câu nối tự nhiên

| ❌ SAI (Dùng =) | ✅ ĐÚNG (Câu nối tự nhiên) |
|----------------|---------------------------|
| `"Ăn mứt nhiều = SÂU RĂNG!"` | `"Ăn mứt nhiều sẽ dẫn đến sâu răng đau đớn."` |
| `"Đường cao = tiểu đường!"` | `"Đường cao khiến bạn có nguy cơ tiểu đường."` |
| `"Thịt ôi = ngộ độc!"` | `"Thịt ôi gây ra ngộ độc thực phẩm."` |
| `"Lá héo = mất chlorophyll"` | `"Lá héo nghĩa là đã mất chất diệp lục bảo vệ."` |

#### E24.2 LOẠI BỎ DẤU CHẤM THAN `!` - Dùng giọng điệu thay vì ký tự

| ❌ SAI (Nhiều !) | ✅ ĐÚNG (Không có !) |
|-----------------|---------------------|
| `"CẢNH BÁO! Đường huyết TĂNG VỌT!"` | `"Cảnh báo, đường huyết đang tăng vọt."` |
| `"Nguy hiểm! Sâu răng!"` | `"Đây là dấu hiệu nguy hiểm của sâu răng."` |
| `"Hahaha! Ta sẽ phá hủy!"` | `"Hahaha, ta sẽ phá hủy mày."` |

**LƯU Ý**: Sự nhấn mạnh nên thể hiện qua **[Tone]** trong voice metadata, KHÔNG qua dấu `!`

#### E24.3 LOẠI BỎ DẤU HAI CHẤM `:` TRONG LIST - Dùng từ nối tự nhiên

| ❌ SAI (Dùng :) | ✅ ĐÚNG (Từ nối tự nhiên) |
|----------------|--------------------------|
| `"Một: Đánh răng sau 30 phút"` | `"Một, bạn nên đánh răng sau 30 phút ăn mứt."` |
| `"Hai: ĐÁNH RĂNG sau 30 phút ăn mứt!"` | `"Hai, hãy đánh răng sau 30 phút sau khi ăn mứt hoặc bánh kẹo."` |
| `"Ba: Uống nước súc miệng"` | `"Ba, bạn có thể súc miệng bằng nước muối ấm."` |
| `"Cấp 1: Nơi thoáng mát"` | `"Cấp một, để ở nơi thoáng mát được 3 đến 5 ngày."` |

**MẪU CÂU THAY THẾ CHO LIST**:
- "Một, bạn nên..."
- "Hai, hãy..."
- "Ba, bạn có thể..."
- "Thứ nhất, điều quan trọng là..."
- "Tiếp theo, bạn cần..."
- "Cuối cùng, đừng quên..."

#### E24.4 DỊCH THUẬT NGỮ Y HỌC SANG TIẾNG VIỆT

| ❌ SAI (Thuật ngữ gốc) | ✅ ĐÚNG (Tiếng Việt dễ hiểu) |
|-----------------------|-----------------------------|
| `"ACID ăn mòn răng"` | `"Chất a-xít ăn mòn men răng"` |
| `"bacteria sinh sôi"` | `"Vi khuẩn sinh sôi"` |
| `"cholesterol cao"` | `"Mỡ máu cao"` hoặc `"Chô-lét-tơ-rôn cao"` |
| `"glucose trong máu"` | `"Đường trong máu"` |
| `"insulin kiệt sức"` | `"In-su-lin kiệt sức"` hoặc `"Chất điều hòa đường huyết kiệt sức"` |
| `"enzyme tiêu hóa"` | `"En-zim tiêu hóa"` hoặc `"Chất men tiêu hóa"` |
| `"aflatoxin độc hại"` | `"Chất độc a-fla-tốc-xin"` |
| `"GI (Glycemic Index)"` | `"Chỉ số đường huyết"` |
| `"calories tăng"` | `"Ca-lo tăng"` hoặc `"Năng lượng tăng"` |
| `"pH trong miệng"` | `"Độ a-xít trong miệng"` |


**NGUYÊN TẮC DỊCH THUẬT NGỮ**:
1. Nếu từ phổ biến (bacteria, acid) → Dịch sang tiếng Việt thuần
2. Nếu từ chuyên môn (insulin, enzyme) → Phiên âm + giải thích
3. Nếu viết tắt (GI, pH, ALT) → Đọc từng chữ hoặc dịch nghĩa

#### E24.5 PHIÊN ÂM THUẬT NGỮ VI SINH - VI KHUẨN (Microbiology Terms) - BẮT BUỘC

*   **VÌ SAO QUAN TRỌNG**: Tên vi khuẩn thường là tiếng Latin phức tạp, TTS sẽ đọc sai hoàn toàn nếu không phiên âm.
*   **QUY TẮC**: Phải chia thành từng âm tiết bằng dấu gạch ngang `-`

| ❌ SAI (Tên gốc Latin) | ✅ ĐÚNG (Phiên âm tiếng Việt) |
|-----------------------|------------------------------|
| `"Clostridium botulinum"` | `"Cờ-lô-stri-đi-um bo-tu-li-num"` |
| `"Salmonella"` | `"San-mô-nen-la"` hoặc `"Vi khuẩn San-mô-nen-la"` |
| `"E. coli"` | `"I cô-lai"` hoặc `"E cô-lai"` |
| `"Staphylococcus aureus"` | `"Sta-phi-lô-cốc-cút ô-rê-út"` |
| `"Listeria monocytogenes"` | `"Li-stê-ri-a mô-nô-xai-tô-gin"` |
| `"Vibrio cholerae"` | `"Vi-bri-ô Cô-lê-ra"` (Vi khuẩn tả) |
| `"Bacillus cereus"` | `"Ba-xi-lút xê-rê-út"` |

**MẪU CÂU SỬ DỤNG**:
```
✅ ĐÚNG: "Ta là Cờ-lô-stri-đi-um bo-tu-li-num, sinh ra độc tố mạnh gấp 100 ngàn lần xyanua!"
❌ SAI: "Ta là Clostridium botulinum..." (TTS sẽ đọc lung tung)

✅ ĐÚNG: "Vi khuẩn San-mô-nen-la gây ngộ độc thực phẩm nghiêm trọng."
❌ SAI: "Salmonella gây ngộ độc..." (TTS đọc sai)
```

**LƯU Ý ĐẶC BIỆT**:
- Nếu tên quá dài (>15 âm tiết) → Dùng tên tiếng Việt thay thế
  - VD: "Staphylococcus aureus" → "Vi khuẩn tụ cầu vàng"
  - VD: "Vibrio cholerae" → "Vi khuẩn tả"
- Villain character PHẢI xưng tên đầy đủ lần đầu xuất hiện
- Lần sau có thể rút gọn: "Ta" thay vì lặp lại tên dài



*   **VÍ DỤ CHUYỂN ĐỔI TOÀN DIỆN**:

| ❌ SAI (Tổng hợp lỗi) | ✅ ĐÚNG (Đã sửa) |
|---------------------|-----------------|
| `"GI > 70 = RẤT CAO!"` | `"Chỉ số đường huyết vượt 70, nghĩa là rất cao."` |
| `"Vi khuẩn tạo ra ACID ăn mòn răng!"` | `"Vi khuẩn tạo ra chất a-xít ăn mòn men răng."` |
| `"Hai: ĐÁNH RĂNG sau 30 phút ăn mứt!"` | `"Hai, bạn nên đánh răng sau 30 phút sau khi ăn mứt."` |
| `"Mứt chứa 60-80% ĐƯỜNG!"` | `"Mứt chứa 60 đến 80 phần trăm đường."` |
| `"Aflatoxin = UNG THƯ GAN!"` | `"Chất độc a-fla-tốc-xin gây ra ung thư gan."` |

*   **CHECKLIST E24** (Phải check TRƯỚC khi submit):
    - [ ] Không có `>` hoặc `<` trong thoại?
    - [ ] Không có `=` trong thoại? (dùng câu nối)
    - [ ] Không có `!` trong thoại? (dùng dấu chấm)
    - [ ] Không có `:` sau số thứ tự? (dùng từ nối)
    - [ ] Không có `-` dùng làm range (VD: 60-80)?
    - [ ] Thuật ngữ y học đã dịch/phiên âm tiếng Việt?
    - [ ] **Tên vi khuẩn/vi rút đã chia âm tiết bằng gạch ngang?** (E24.5)
    - [ ] Tất cả số liệu đọc rõ được bằng giọng tự nhiên?

### E25. THOẠI VILLAIN - PHONG CÁCH PHẢN DIỆN (Villain Dialogue Style) - BẮT BUỘC
*   **ĐỊNH NGHĨA**: Nhân vật phản diện (vi khuẩn, độc tố, thực phẩm bẩn, đường, mỡ...) PHẢI có tính cách GIAN TRÁ, ĐE DỌA, KIÊU NGẠO trong thoại.
*   **VÌ SAO QUAN TRỌNG**:
    - Tạo dramatic tension
    - Người xem cảm nhận được MỐI NGUY thực sự
    - Video không bị nhạt, sáo rỗng
    - Tăng engagement và fear factor

*   **ĐẶC ĐIỂM THOẠI VILLAIN**:

| Yếu tố | Mô tả | Ví dụ |
|--------|-------|-------|
| **Xưng hô** | "Ta", "Bọn ta", "Tao" (kiêu ngạo) | `"Ta sẽ xâm nhập!"` KHÔNG `"Tôi sẽ vào"` |
| **Giọng điệu** | Đắc thắng, cười ác, đe dọa | `[Tone: Đắc thắng/Cười ác]` |
| **Hành động** | Chủ động TẤN CÔNG, XÂMM NHẬP | `"Ta đang TRÀN VÀO máu mày!"` |
| **Đe dọa** | Cụ thể HẬU QUẢ + THỜI GIAN | `"Gan mày sẽ KIỆT SỨC trong 4 giờ!"` |
| **Số liệu** | Dùng để ĐE DỌA, khoe khoang | `"Mỗi giờ ta NHÂN LÊN 1 triệu lần!"` |
| **Thái độ** | Coi thường nạn nhân | `"Mày tưởng có thể ngăn ta sao?"` |

*   **VOICE METADATA CHO VILLAIN**:
    ```
    [Region: Bắc/Nam] [Gender: Male/Female] [Age: 40s] [Tone: Đắc thắng/Cười ác/Đe dọa/Kiêu ngạo]
    ```

*   **VÍ DỤ THOẠI VILLAIN ĐÚNG**:
    ```
    [Character: ĐƯỜNG] [Tone: Đắc thắng/Cười ác]
    "Hahaha! Ta đang tràn vào máu mày với tốc độ GẤP 3 LẦN bình thường! 
    Insulin sẽ KIỆT SỨC trong vòng 30 phút!"
    ```
    
    ```
    [Character: VI_KHUẨN] [Tone: Đe dọa/Gian xảo]
    "Hehe! Mày để thức ăn ở nhiệt độ phòng à? TUYỆT VỜI! 
    Trong 2 tiếng, bọn ta sẽ nhân lên HÀNG TRIỆU CON!"
    ```
    
    ```
    [Character: AFLATOXIN] [Tone: Độc ác/Thì thầm]
    "Ta là AFLATOXIN! Mày không nhìn thấy, không ngửi thấy, 
    nhưng ta đang TÍCH TỤ trong gan mày từng ngày!"
    ```

*   **VÍ DỤ THOẠI VILLAIN SAI** (quá nhẹ nhàng, neutral):

| ❌ SAI (Neutral) | ✅ ĐÚNG (Villain style) |
|------------------|------------------------|
| `"Đường được hấp thu vào máu."` | `"Ta đang TRÀN VÀO máu mày không thể ngăn cản!"` |
| `"Vi khuẩn sinh sôi nhanh chóng."` | `"Haha! Cứ mỗi 20 phút, bọn ta NHÂN ĐÔI!"` |
| `"Mỡ tích tụ trong gan."` | `"Ta sẽ CHIẾM ĐÓNG gan mày! Mày không thể đuổi ta đi!"` |
| `"Đường không tốt cho người tiểu đường."` | `"Với người tiểu đường, ta là HUNG THẦN! Một miếng thôi - đường huyết mày SẼ VỌT LÊN 50 ĐIỂM!"` |

*   **CHECKLIST E25**:
    - [ ] Nhân vật villain xưng "Ta/Bọn ta", không xưng "Tôi"?
    - [ ] Có tone Đắc thắng/Cười ác/Đe dọa trong metadata?
    - [ ] Thoại có đe dọa cụ thể (số liệu + hậu quả + thời gian)?
    - [ ] Không có thoại neutral cho villain?
    - [ ] Villain thể hiện sự kiêu ngạo, coi thường?

### E26. THOẠI CÓ TÁC ĐỘNG - KHÔNG SÁO RỖNG (Impact Dialogue - No Vague Content) - BẮT BUỘC NGHIÊM NGẶT
*   **ĐỊNH NGHĨA**: Mỗi câu thoại PHẢI có ít nhất 1 trong 3 yếu tố: SỐ LIỆU CỤ THỂ, HẬU QUẢ RÕ RÀNG, SO SÁNH GÂY SHOCK.
*   **VÌ SAO QUAN TRỌNG**:
    - Thoại sáo rỗng = Người xem không nhớ, không sợ, không chia sẻ
    - Thiếu số liệu = Thiếu credibility
    - Thiếu hậu quả = Người xem không quan tâm

*   **3 YẾU TỐ TẠO TÁC ĐỘNG**:

| Yếu tố | Mô tả | Ví dụ |
|--------|-------|-------|
| **Số liệu cụ thể** | Bao nhiêu? Bao lâu? Gấp mấy lần? | `"TĂNG 40%"`, `"trong 30 phút"`, `"gấp 3 lần"` |
| **Hậu quả rõ ràng** | Sẽ xảy ra gì? Ảnh hưởng thế nào? | `"nguy cơ ĐỘT QUỴ"`, `"gan KIỆT SỨC"` |
| **So sánh gây shock** | Tương đương cái gì quen thuộc? | `"bằng 3 TÔ CƠM"`, `"như chạy 10km"` |

*   **BẢNG CHUYỂN ĐỔI TỪ SÁO RỖNG SANG CÓ TÁC ĐỘNG**:

| ❌ SAI (Sáo rỗng, vô nghĩa) | ✅ ĐÚNG (Có tác động) |
|-----------------------------|----------------------|
| `"Rất nguy hiểm!"` | `"Nguy cơ đột quỵ TĂNG 40 phần trăm!"` |
| `"Hấp thu nhanh vào máu"` | `"CHỈ 15 PHÚT là đường đã tràn ngập máu!"` |
| `"Ảnh hưởng đến sức khỏe"` | `"Gan phải làm việc LIÊN TỤC 8 tiếng để xử lý!"` |
| `"Không tốt cho cơ thể"` | `"Mỗi miếng tương đương 3 MUỖNG đường đổ thẳng vào máu!"` |
| `"Người tiểu đường nguy hiểm"` | `"Với người tiểu đường: 1 miếng mứt tương đương tăng đường huyết 50 điểm trong 20 phút!"` |
| `"Gây ra nhiều vấn đề"` | `"Tăng nguy cơ 5 BỆNH: tiểu đường, tim mạch, béo phì, sỏi thận, gan nhiễm mỡ!"` |
| `"Đường huyết tăng"` | `"Đường huyết TĂNG VỌT từ 100 lên 180 chỉ trong 15 phút!"` |
| `"Cần cẩn thận"` | `"Ăn quá 2 miếng mỗi ngày là bạn đang nạp GẤP ĐÔI lượng đường cho phép!"` |

*   **CÔNG THỨC TẠO THOẠI CÓ TÁC ĐỘNG**:
    ```
    [Hành động] + [Số liệu SO SÁNH] + [Hậu quả cụ thể] + [Thời gian nếu có]
    
    Ví dụ:
    "Mỗi miếng mứt (hành động) = 3 muỗng đường (số liệu so sánh) 
    → đường huyết tăng vọt 50 điểm (hậu quả) trong chỉ 20 phút (thời gian)!"
    ```

*   **DANH SÁCH TỪ CẤM (SÁO RỖNG)**:
    | Cụm từ CẤM | Lý do | Thay bằng |
    |------------|-------|-----------|
    | "rất nguy hiểm" | Quá chung chung | [Số liệu cụ thể] |
    | "không tốt" | Không shock | "gây [bệnh cụ thể]" |
    | "ảnh hưởng" | Không rõ | "[hậu quả cụ thể]" |
    | "cần cẩn thận" | Không urgency | "[số liệu + hậu quả]" |
    | "nhiều vấn đề" | Mơ hồ | "5 BỆNH: [liệt kê]" |
    | "có hại" | Nhẹ nhàng | "GÂY [bệnh], TĂNG [%] nguy cơ" |

*   **CHECKLIST E26** (BẮT BUỘC check mọi câu thoại):
    - [ ] Câu thoại có ít nhất 1 số liệu cụ thể?
    - [ ] Hoặc có hậu quả rõ ràng (tên bệnh, triệu chứng)?
    - [ ] Hoặc có so sánh gây shock (bằng X, tương đương Y)?
    - [ ] KHÔNG có các cụm từ sáo rỗng?
    - [ ] Người xem có thể HÌNH DUNG được mức độ nghiêm trọng?

### E27. SỐ LIỆU PHẢI CÓ ĐƠN VỊ CỤ THỂ (Specific Units for Numbers) - BẮT BUỘC NGHIÊM NGẶT
*   **ĐỊNH NGHĨA**: Mọi số liệu y học PHẢI có đơn vị đo lường cụ thể, viết đầy đủ bằng tiếng Việt.
*   **VÌ SAO QUAN TRỌNG**:
    - Số không có đơn vị = VÔ NGHĨA, không credible
    - "50 điểm" không rõ là gì → Người xem không hiểu
    - Đơn vị cụ thể = Chuyên nghiệp, đáng tin cậy

*   **BẢNG ĐƠN VỊ Y HỌC CHUẨN (Viết tiếng Việt)**:

| Chỉ số | Đơn vị gốc | Viết tiếng Việt đọc được |
|--------|-----------|--------------------------|
| Đường huyết | mg/dL | "mi-li-gam trên đề-xi-lít" |
| Huyết áp | mmHg | "mi-li-mét thủy ngân" |
| Cholesterol | mg/dL | "mi-li-gam trên đề-xi-lít" |
| Nhiệt độ | °C | "độ xê" hoặc "độ C" |
| Cân nặng | kg | "ki-lô-gam" hoặc "ký" |
| Thời gian | phút, giờ, ngày | "phút", "tiếng", "ngày" |
| Phần trăm | % | "phần trăm" |
| Năng lượng | kcal | "ki-lô ca-lo" hoặc "ca-lo" |
| Thể tích | mL, L | "mi-li-lít", "lít" |

*   **VÍ DỤ CHUYỂN ĐỔI**:

| ❌ SAI (Số không có đơn vị rõ) | ✅ ĐÚNG (Có đơn vị cụ thể) |
|-------------------------------|---------------------------|
| `"đường huyết vọt lên 50 điểm"` | `"đường huyết vọt lên 250 mi-li-gam trên đề-xi-lít"` |
| `"tăng lên 180"` | `"tăng lên 180 mi-li-gam trên đề-xi-lít"` |
| `"huyết áp 140/90"` | `"huyết áp 140 trên 90 mi-li-mét thủy ngân"` |
| `"mỡ máu cao 300"` | `"mỡ máu cao 300 mi-li-gam trên đề-xi-lít"` |
| `"nhiệt độ 38"` | `"nhiệt độ 38 độ xê"` |
| `"giảm 10"` | `"giảm 10 ki-lô-gam"` hoặc `"giảm 10 phần trăm"` |

*   **CÁCH VIẾT KHOẢNG/RANGE**:

| ❌ SAI | ✅ ĐÚNG |
|--------|---------|
| `"100-140"` | `"từ 100 đến 140 mi-li-gam trên đề-xi-lít"` |
| `"trên 200"` | `"vượt quá 200 mi-li-gam trên đề-xi-lít"` |
| `"dưới 100"` | `"dưới mức 100 mi-li-gam trên đề-xi-lít"` |

*   **NGUYÊN TẮC VIẾT SỐ LIỆU Y HỌC**:
    1. **LUÔN có đơn vị**: Không bao giờ nói số một mình
    2. **Viết phiên âm**: mg/dL → "mi-li-gam trên đề-xi-lít"
    3. **Giải thích nếu cần**: "250 mi-li-gam trên đề-xi-lít, gấp đôi mức bình thường"
    4. **So sánh dễ hiểu**: "cao gấp 2 lần người khỏe mạnh"

*   **MẪU CÂU CHUẨN**:
    ```
    "[Chỉ số] sẽ [hành động] lên/xuống [CON SỐ] [ĐƠN VỊ], [so sánh với mức bình thường]"
    
    Ví dụ:
    "Đường huyết sẽ vọt lên 250 mi-li-gam trên đề-xi-lít, cao gấp đôi mức an toàn."
    "Huyết áp tăng lên 160 trên 100 mi-li-mét thủy ngân, vào vùng nguy hiểm."
    ```

*   **CHECKLIST E27** (BẮT BUỘC check mọi số liệu):
    - [ ] Mọi số liệu y học có đơn vị kèm theo?
    - [ ] Đơn vị đã phiên âm tiếng Việt đọc được?
    - [ ] Có so sánh với mức bình thường?
    - [ ] Người xem có thể HIỂU được mức độ qua đơn vị?

    - [ ] Người xem có thể HIỂU được mức độ qua đơn vị?

### E28. TIÊU CHUẨN QUAY PHIM ĐIỆN ẢNH (Cinematic Camera Standards) - BẮT BUỘC
*   **MỤC ĐÍCH**: Biến video AI thành phim điện ảnh chuyên nghiệp. Tránh góc quay tĩnh (static) nhàm chán.
*   **TỪ KHÓA CAMERA MOVEMENT (Dùng trong Prompt Visual)**:
    | Kỹ thuật | Prompt Keyword | Tác dụng | Khi nào dùng |
    |----------|----------------|----------|--------------|
    | **Tiến sâu** | `Slow dolly in`, `Push in` | Tăng kịch tính, tập trung vào chi tiết | Hook, Mechanism (soi chi tiết) |
    | **Lùi ra** | `Slow pull out`, `Dolly out` | Hé lộ bối cảnh, cô đơn, kết thúc | Ending, thấy toàn cảnh hậu quả |
    | **Đi theo** | `Tracking shot`, `Follow cam` | Theo chân nhân vật di chuyển | Nhân vật đi lại, dòng máu chảy |
    | **Xoay vòng** | `Orbit shot`, `Arc shot` | Show toàn diện đối tượng 360 độ | Giới thiệu nhân vật/sản phẩm |
    | **Góc thấp** | `Low angle shot` | Làm nhân vật trông quyền lực/đáng sợ | Villain (Vi khuẩn, Mỡ), Hero |
    | **Góc cao** | `High angle shot` | Làm nhân vật trông yếu đuối | Nạn nhân, Bộ phận bị bệnh |
    | **Nghiêng** | `Dutch angle` | Gây bất an, chóng mặt, nguy hiểm | Cảnh cảnh báo, nguy kịch |
    | **Rung** | `Handheld camera movement` | Tạo cảm giác thực tế, hoảng loạn | Cảnh cấp cứu, hỗn loạn |
*   **GÓC MÁY (SHOT SIZES)**:
    -   `Extreme Close-up (ECU)`: Soi tế bào, giọt mồ hôi, mắt.
    -   `Close-up (CU)`: Mặt nhân vật, biểu cảm.
    -   `Medium Shot (MS)`: Thấy nửa người, hành động tay.
    -   `Wide Shot (WS)`: Thấy toàn thân + bối cảnh phòng.
*   **QUY TẮC PHỐI HỢP**:
    -   Prompt PHẢI có ít nhất 1 từ khóa Movement + 1 từ khóa Shot Size.
    -   Ví dụ: `[Extreme Close-up], [Slow dolly in] on the liver surface...`

### E29. CÔNG THỨC VIRAL RETENTION (Retention Dynamics) - BẮT BUỘC
*   **MỤC ĐÍCH**: Giữ chân người xem không rời đi sau 3 giây đầu.
*   **QUY TẮC "MỖI 3 GIÂY PHẢI CÓ THAY ĐỔI" (Visual Pacing)**:
    -   Không bao giờ để 1 góc máy tĩnh quá 3 giây.
    -   Phải thay đổi bằng: Movement, Cut cảnh, Zoom, hoặc Action mới.
*   **CẤU TRÚC GIỮ CHÂN (RETENTION ARC)**:
    | Giây | Giai đoạn | Nhiệm vụ Visual | Kỹ thuật Audio |
    |------|-----------|-----------------|----------------|
    | 0-3s | **THE HOOK** | Chuyển động nhanh, Cận cảnh (ECU), Shock visual | SFX: Rầm, Woosh, Tiếng vỡ (Lớn) |
    | 3-15s | **THE BUILD UP** | Dolly in liên tục (tăng áp lực), Show cơ chế lạ | SFX: Tiếng tim đập, tiếng tích tắc (Tăng dần) |
    | 15-45s | **THE PAYOFF** | Góc quay thay đổi liên tục (Wide -> Close), Split Screen | BGM: Dồn dập -> Vỡ òa |
    | 45-60s | **THE RELIEF** | Màu sáng hơn, Dolly out, High key lighting | BGM: Thư giãn, Hy vọng |
*   **CÁC YẾU TỐ "THỎA MÃN THỊ GIÁC" (Satisfying Visuals)**:
    -   `Symmetry`: Cân đối hoàn hảo (Wes Anderson style).
    -   `Cleaning/Restoring`: Từ bẩn/hỏng -> Sạch/Mới (Cực cuốn).
    -   `Filling up`: Đổ đầy nước, thanh năng lượng tăng.
    -   `Matching transitions`: Chuyển cảnh mượt mà theo hình dáng.
*   **CHECKLIST RETENTION**:
    - [ ] 3s đầu có gây sốc visual không?
    - [ ] Có thay đổi góc máy/movement mỗi 3-5s không?
    - [ ] Có hiệu ứng âm thanh (SFX) đi kèm visual không?

### E30. TUÂN THỦ NỀN TẢNG (Platform Compliance) - BẮT BUỘC
*   **E30.1 KHAI BÁO AI (AI Labeling)**:
    - YouTube/TikTok: Bắt buộc tích "Altered content" hoặc "AI-generated".
    - Description: Thêm dòng "Video minh họa bởi công nghệ AI để mục đích giáo dục".
*   **E30.2 TUYÊN BỐ MIỄN TRỪ Y KHOA (Medical Disclaimer)**:
    - Bắt buộc có dòng: "Thông tin chỉ mang tính chất tham khảo, không thay thế lời khuyên y tế chuyên nghiệp."
    - CẤM từ cam kết: "Trị dứt điểm", "Cam kết khỏi 100%".
*   **E30.3 CHÍNH SÁCH HÌNH ẢNH (Personal Attributes)**:
    - Facebook cấm zoom vào khuyết điểm cơ thể (mụn, mỡ) của NGƯỜI THẬT.
    - GIẢI PHÁP: Dùng 3D Animation Character cho các cảnh bệnh lý/triệu chứng xấu.

    - [ ] GIẢI PHÁP: Dùng 3D Animation Character cho các cảnh bệnh lý/triệu chứng xấu.

### E31. GIAO THỨC GHÉP NỐI LIỀN MẠCH (Seamless Stitching Protocol) - BẮT BUỘC CHO LONG-FORM
*   **MỤC ĐÍCH**: Giải quyết giới hạn 8s để tạo ra các trường đoạn dài mượt mà như phim điện ảnh.
*   **VẤN ĐỀ**: Video AI thường bị "giật" (jump cut) giữa các clip do AI không nhớ chính xác vị trí vật lý của clip trước.
*   **GIẢI PHÁP**: Áp dụng 4 kỹ thuật "Khâu" (Stitching) sau trong Prompt:

#### E31.1 KỸ THUẬT END-START MATCHING (Khớp Đầu-Cuối)
- **Quy tắc**: Prompt của Clip $N$ phải có visual giống hệt Prompt của Clip $N-1$ tại điểm cắt.
- **Cách làm**:
    - Xác định Clip $N-1$ kết thúc thế nào? (Tay đang giơ, mồm đang há, chân đang bước trái).
    - Prompt Clip $N$ bắt đầu BẰNG CHÍNH TRẠNG THÁI ĐÓ.
- **Ví dụ**:
    - *Kết Clip 1*: `...The doctor raises her right hand to point at the screen.`
    - *Đầu Clip 2*: `...The doctor's right hand is raised pointing at the screen, then she taps it.`
    - **SAI**: Clip 2 chỉ viết `The doctor points...` (AI sẽ tự vẽ lại tay từ dưới đưa lên -> Bị lặp động tác).

#### E31.2 KỸ THUẬT PHYSICS INERTIA (Quán Tính Vật Lý)
- **Quy tắc**: Bảo toàn lực và tốc độ chuyển động giữa 2 clip.
- **Áp dụng**:
    - Nếu Clip 1 nhân vật đang CHẠY NHANH -> Clip 2 phải bắt đầu bằng Motion Blur, tóc bay, chân đang trên không. KHÔNG ĐƯỢC đứng yên "lấy đà".
    - Nếu Clip 1 nước đang ĐỔ XUỐNG -> Clip 2 nước phải đang VA CHẠM bề mặt, tung bọt.
- **Prompt Keyword**: `mid-action`, `motion blur`, `continuing momentum`, `flying hair`.

#### E31.3 KỸ THUẬT ENVIRONMENT ANCHORING (Neo Bối Cảnh)
- **Quy tắc**: "Khóa chết" ánh sáng và không gian để không bị sai màu.
- **Cách làm**: Copy nguyên block `[Setting]` của clip trước, KHÔNG ĐỔI dù chỉ 1 chữ.
- **Mẹo**: Dùng `Uniform lighting`, `Fixed camera exposure` để tránh AI tự đổi ánh sáng (lỗi Flicker).

#### E31.4 KỸ THUẬT INVISIBLE CUTS (Cắt Vô Hình)
- **Dùng cho**: Chuyển cảnh khó, đổi góc quay phức tạp.
- **Các chiêu thức**:
    | Kỹ thuật | Prompt Cuối Clip 1 | Prompt Đầu Clip 2 |
    |----------|-------------------|-------------------|
    | **Whip Pan** | `...rapid camera whip pan to the right blurring everything.` | `Starting from a blur, rapid whip pan stops to reveal [New Scene].` |
    | **Object Pass** | `...a dark waiter walks past covering the lens completely.` | `Camera blocked by dark cloth then reveals [New Scene] as waiter walks away.` |
    | **Light Flare** | `...bright lens flare blinds the camera.` | `...light flare fades down revealing [New Scene].` |

    - [ ] Bối cảnh (Lighting, Weather) có copy y nguyên không?
    - [ ] Có dùng Invisible Cut cho đoạn chuyển cảnh khó không?

### E32. BỘ TỨ SIÊU HOOK (The Viral Hook Quartet) - ENCYCLOPEDIA
*   **MỤC ĐÍCH**: Cung cấp kho vũ khí "Catchy" nhất để giữ chân người xem trong 3 giây đầu.
*   **QUY TẮC**: Mỗi video BẮT BUỘC phải dùng ít nhất **2 trong 4** loại Hook dưới đây ngay tại giây 0.

#### 32.1 HOOK MATRIX (Bảng Phối Hợp Chính Xác)
*   **Hướng dẫn sử dụng**: Xác định mục tiêu cảm xúc -> Chọn Combo Hook tương ứng.
    | Mục đích Video | Cảm xúc chủ đạo | Visual Hook (Thị giác) | Voice/Audio Hook (Thính giác) | Dialogue Hook (Lời thoại) |
    |----------------|-----------------|------------------------|-------------------------------|---------------------------|
    | **Cảnh báo** | Sợ hãi, Lo lắng | *Extreme Close-up (Soi tế bào, Máu)* | *The Whisper (Thì thầm), Heartbeat* | "Cảnh báo khẩn cấp..." |
    | **Bật mí** | Tò mò, Kích thích | *Reverse Motion (Quay ngược), Blur Reveal* | *Silence Cut (Im lặng), Glitch Sound* | "Bí mật mà bác sĩ..." |
    | **Tranh luận** | Bất ngờ, Phẫn nộ | *Split Screen (Đúng/Sai), Impossible Object* | *Fast Pacing (Nói nhanh), Alarm* | "Bạn đã sai lầm..." |
    | **Giải trí** | Thỏa mãn, Vui vẻ | *Symmetry (Đối xứng), Cleaning/Restoring* | *ASMR (Nhai, Rót nước), Ding Sound* | "Xem đến cuối nhé..." |

#### 32.2 THƯ VIỆN HOOK CHI TIẾT (Rich Library)

**1. VISUAL HOOKS (Thị giác - Gây sốc ngay lập tức)**
*   `Breaking 4th Wall`: Nhân vật gõ vào màn hình kính, nhìn xuyên thấu lens.
*   `Reverse Motion`: Nước đổ ngược vào ly, kính vỡ tự lành lại.
*   `Impossible Object`: Vật thể phi vật lý (Cầu thang Escher, nước chảy lên).
*   `Transition Match`: Biến hình mượt mà (Quả cam xoay -> Mặt trời).
*   `Macro Reveal`: Soi lỗ chân lông/vi khuẩn -> Zoom out ra mặt cô gái xinh đẹp.
*   `Motion Intro`: Vật thể bay thẳng vào lens (Ném dép, tạt nước, phi dao).
*   `Glitch Effect`: Hình ảnh bị nhiễu sóng, vỡ pixel giả lập lỗi.

**2. VOICE HOOKS (Giọng nói - Gây chú ý não bộ)**
*   `The Whisper`: Nói thầm vào tai (Hiệu ứng 8D Audio trái/phải). *Dùng cho bí mật.*
*   `The Glitch`: Giọng bị méo, lặp từ, vấp đĩa ("KHOAN... Khoan... dừng lại").
*   `The Breath`: Tiếng lấy hơi cực mạnh/gấp gáp ngay giây đầu.
*   `The Scream`: Tiếng hét thất thanh (Chỉ dùng cho cảnh nguy hiểm).
*   `Fast Pacing`: Nói liên thanh dồn dập không nghỉ (Tạo áp lực).

**3. DIALOGUE HOOKS (Lời thoại - Kích thích tâm lý)**
*   `Negative Command`: "Đừng bao giờ ăn...", "Dừng lướt ngay!". (Não bộ thích phủ định).
*   `The "If" Scenario`: "Nếu bạn chỉ còn 1 ngày để sống...", "Nếu mặt trời tắt ngấm...".
*   `The Counter-Intuitive`: "Ăn mỡ để giảm cân?", "Uống thuốc độc để khỏe?". (Nghịch lý).
*   `The Secret`: "Sự thật về...", "Điều mà không ai nói cho bạn...".
*   `The Challenge`: "Đố bạn không chớp mắt...", "Thử nín thở xem...".

**4. SFX HOOKS (Âm thanh - Kích hoạt giác quan)**
*   `The Snap`: Tiếng búng tay sắc lẹm chuyển cảnh.
*   `The Slap`: Tiếng tát, va chạm da thịt tàn khốc.
*   `Shepard Tone`: Âm thanh tăng cao độ vô tận (Gây căng thẳng tột độ).
*   `Silence Cut`: Đang ồn ào bỗng tắt bụp toàn bộ âm thanh 0.5s.
*   `ASMR Triggers`: Tiếng nhai rộp rộp, tiếng rót nước, tiếng gõ móng tay.

*   **CHECKLIST HOOK**:
    - [ ] Intro có dùng ít nhất 2 loại Hook không?
    - [ ] Hook có phù hợp với mục đích cảm xúc (Matrix) không?
    - [ ] 3 giây đầu có giữ chân được người xem không?


### F. Định Dạng Video (Video Format Mode)


*   **QUYẾT ĐỊNH**: Trước khi viết, phải xác định loại video để căn chỉnh nhịp độ.
*   **Options**:
    *   **YouTube Shorts / TikTok (Vertical 9:16)**:
        *   *Thời lượng*: Dưới 60s (Khoảng 5-7 clips).
        *   *Nhịp độ*: Cực nhanh (Fast-paced), Hook ngay giây đầu.
        *   *Cấu trúc*: 1 Intro gây sốc -> 3 Thân bài -> 1 Outro kêu gọi.
    *   **Long Form Video (Horizontal 16:9)**:
        *   *Thời lượng*: > 1 phút (15+ clips).
        *   *Nhịp độ*: Từ tốn, kể chuyện có chiều sâu (Storytelling).
        *   *Cấu trúc*: Intro -> Dẫn dắt -> Cao trào -> Giải quyết -> Bài học.
    *   **Music Video (MV)**:
        *   *Nhịp độ*: Khớp theo từng beat nhạc. Hình ảnh trừu tượng/nghệ thuật hơn.

---

## 2. CÔNG THỨC VIẾT PROMPT NGHIÊM NGẶT (STRICT FORMULA)

`[1. KẾT NỐI MẠCH TRUYỆN] + [2. KỸ THUẬT QUAY] + [3. BỐI CẢNH (Natural Text)] + [4. NHÂN VẬT (Natural Text) + HÀNH ĐỘNG] + [5. ÂM THANH/ÁNH SÁNG]`

**QUY TẮC VÀNG: "CLEAN PROMPT" (KHÔNG RÁC)**
*   **SAI**: `The [Character: A cool boy] runs.` (AI sẽ hiểu nhầm dấu ngoặc).
*   **SAI**: `[CLIP 0-8s] The cool boy runs.` (Không xuất tiêu đề thời gian/Clip Header).
*   **ĐÚNG**: `The cool boy runs.` (Chỉ lấy nội dung mô tả, bỏ khung, bỏ nhãn, bỏ header).

### Chi tiết từng phần:

#### [1. CẦU NỐI HÌNH ẢNH & VẬT LÝ] (The Visual Bridge)
*   **TUYỆT ĐỐI KHÔNG**: Dùng từ chung chung như "Continuing from...", "Matching the scene...".
*   **YÊU CẦU**: Phải mô tả **3 yếu tố vật lý** để nối cảnh cũ sang cảnh mới:
    1.  **Camera Handover**: Camera cảnh trước đang lia/zoom thế nào? Cảnh này phải bắt đầu từ đó hoặc cắt dứt khoát.
    2.  **Vật lý/Quán tính (Physics/Inertia)**: Tóc, quần áo, đồ vật đang bay/rơi với tốc độ nào?
    3.  **Hành động nối tiếp (Connective Action)**: Cảnh trước "giơ tay lên", cảnh này phải là "tay đập xuống". Mô tả cụ thể chuyển động cơ thể.
*   **Ví dụ SAI**: "Continuing from the previous shot."
*   **Ví dụ ĐÚNG**: "Camera completes the rapid whip-pan to the left. The Mom's hair is strictly flying to the right due to the spin. Her hand, previously raised mid-air, now slams down violently onto the table surface..." (Mô tả cụ thể từng chuyển động).

#### [2. KỸ THUẬT QUAY] (Camera Tech Specs)
*   *Yêu cầu*: Phải thay đổi góc máy so với prompt trước.
*   *Options*:
    *   `Extreme Close-up shot (focus on eyes/mouth)`
    *   `Medium shot (waist up, interaction)`
    *   `Wide Cinematic shot (establishing environment)`
    *   `Low angle (to show dominance)`
    *   `Drone flyover (overview)`
    *   `Handheld camera movement (adds chaos/realism)`

#### [3. BỐI CẢNH] (Setting Block)
*   **ACTION**: PASTE đoạn "Bối cảnh Chính" từ mục 1 vào đây.
*   *Bổ sung*: Thêm chi tiết thời gian/thời tiết hiện tại (e.g., `stormy weather`, `night time`).

#### [4. NHÂN VẬT + HÀNH ĐỘNG] (Character Block)
*   **ACTION**: PASTE đoạn "Nhân vật Chính" từ mục 1 vào đây. **KHÔNG VIẾT TẮT**.
*   *Hành động (Action)*: Mô tả hành động cụ thể trong 8 giây này.
*   *Biểu cảm (Expression)*: Mô tả cơ mặt, ánh mắt khớp với nội dung thoại.
*   *Tương tác*: Nếu có 2 nhân vật, PASTE cả mô tả nhân vật 2 vào.

*   **QUY TẮC "CHÀO SÂN" (First Appearance Rule)**:
    *   Với nhân vật nhân hóa (đồ vật/cơ thể), câu thoại ĐẦU TIÊN xuất hiện phải chứa **Tên/Danh xưng** để khán giả biết là cái gì.
    *   *Ví dụ*: `[Voice: Nam] "Ta là Dạ Dày đây! Đau quá!"` (Đúng).
    *   *Ví dụ*: `[Voice: Nam] "Đau quá!"` (Sai -> Khán giả không biết là bộ phận nào đang nói).

#### [5. ÂM THANH/ÁNH SÁNG] (Audio/Lighting Block)
*   *Yêu cầu*: Mô tả âm thanh, ánh sáng, hiệu ứng đặc biệt.
*   *Options*:
    *   `Cinematic dramatic lighting, high contrast`
    *   `Soft natural lighting, warm tones`
    *   `Loud thunder clap, panic atmospherics`
    *   `Upbeat background music, cheerful sound effects`

### 6. THOẠI & GIỌNG ĐỌC (DIALOGUE & VOICE)
*   **QUY TẮCK MATCHING**: Giọng phải khớp với vùng miền và tính cách nhân vật.
*   **CẤU TRÚC TAG ĐƠN GIẢN 2026 (BẮT BUỘC)**: `[Giọng: Vùng, Tuổi]`
    *   *Vùng Options*:
        *   `Miền Bắc`: Sang trọng, tin cậy, chính luận.
        *   `Miền Nam`: Năng động, thân thiện, giải trí.
        *   `Miền Tây`: Mộc mạc, hài hước, hào sảng.
        *   `Miền Trung`: Đặc trưng vùng miền (dùng khi cần thiết).
    *   *Ví dụ*: `[Giọng: Miền Bắc, 30 tuổi]`
    *   *Ví dụ*: `[Giọng: Miền Nam, Teen]`

> [!IMPORTANT]
> **Giới tính**: Xác định trong Character Bible → Copy-paste cho toàn bộ kịch bản
> **Tone/Cảm xúc**: Mô tả trong prompt visual (VD: "villainous grin", "worried expression")

> [!CAUTION]
> **FORMAT CŨ (KHÔNG DÙNG NỮA)**: `[Region: X] [Gender: X] [Age: X] [Tone: X]` hoặc `[Giọng: Vùng, Giới tính, Tuổi, Tone]`
> Nếu thấy format cũ, phải chuyển sang format mới.
*   **QUY TẮC "CHÀO SÂN" (First Appearance Rule)**:
    *   **BẮT BUỘC**: Nhân vật KHÔNG PHẢI NGƯỜI (Đồ vật, Con vật, Bộ phận cơ thể) phải **Xưng Tên** hoặc **Được Gọi Tên** ngay trong câu thoại đầu tiên.
    *   *Ví dụ Sai*: `[Voice: Nam] "Đau quá bà chủ ơi!"` (Khán giả không biết là ai).
    *   *Ví dụ Đúng*: `[Voice: Nam] "Tôi là Cột Sống đây! Đau quá bà chủ ơi!"`
    *   *Ví dụ Đúng*: `[Voice: Nữ] "Chị Gan ơi, sao chị khóc thế?"` (Gọi tên đối phương).
*   **QUY TẮC "NÓI THẲNG" (Direct Dialogue Rule)**:
    *   **BẮT BUỘC**: Thoại của nhân vật phải **NÓI THẲNG VÀO VẤN ĐỀ THỰC TẾ** đang xảy ra. Tránh dùng ẩn dụ, nói bóng gió không liên quan đến bản chất nhân vật.
    *   *Ví dụ Sai*: Bánh chưng nói: `"Em chỉ bị 'sâu răng' tí thôi"` (Bánh chưng không có răng -> Vô nghĩa).
    *   *Ví dụ Đúng*: Bánh chưng nói: `"Em chỉ bị mốc chút xíu thôi mà!"` (Nói thẳng vào vấn đề thực tế: mốc).
*   **QUY TẮC "KHÔNG TỰ ĐẶT TÊN" (No Invented Names Rule)**:
    *   **BẮT BUỘC**: KHÔNG được tự đặt tên riêng cho nhân vật (ví dụ: "chị Lan", "anh Hùng") nếu User chưa cung cấp.
    *   **Thay vào đó, dùng Đại từ/Xưng hô chung PHÙ HỢP VỚI VAI TRÒ**:
        *   **Nhân vật Chuyên gia/Dẫn truyện** (Doctor, Firefighter...): Dùng `"chị ơi"`, `"các chị ơi"`, `"anh ơi"` (Trang trọng, phổ quát).
        *   **Nhân vật Đồ vật/Cơ thể** (Banh Chung, Spine...): Dùng `"bà chủ ơi"`, `"ông chủ ơi"` (Quan hệ Chủ-Tớ, phù hợp bản chất).
    *   *Ví dụ Sai*: Bác sĩ nói: `"Dừng lại ngay chị Lan!"` (Tự đặt tên).
    *   *Ví dụ Sai*: Bác sĩ nói: `"Dừng lại ngay bà chủ ơi!"` (Bác sĩ không phải đồ vật của bà chủ).
    *   *Ví dụ Đúng*: Bác sĩ nói: `"Dừng lại ngay chị ơi!"` (Xưng hô chung, đúng vai).

### 7. KẾT THÚC (Action Outro)
*   **TUYỆT ĐỐI KHÔNG**: Dùng "Ending Card", "Static Logo", "Graphic".
*   **YÊU CẦU**: Phải là một cảnh **Hành động chào kết** của nhân vật.
*   **Ví dụ**: "Nhân vật vẫy tay chào khán giả", "Nhân vật chỉ vào nút Subscribe ảo", "Nhân vật ôm nhau cười".
*   **LƯU Ý QUAN TRỌNG**: Đây là prompt **CUỐI CÙNG**. Không được viết thêm dòng "Ending Card" hay "Logo" nào sau đó. Kết thúc tại đây.

### 8. MASTER SCRIPT (File Tổng Hợp)
*   **Mục đích**: File duy nhất dùng để sản xuất (Human & AI đọc).
*   **Quy tắc Vàng**:
    *   **NO HEADERS**: Không được chứa tiêu đề file (ví dụ: `# MASTER SCRIPT...`) hay link tham chiếu (ví dụ: `[Reference...]`) ở đầu file. Bắt đầu ngay vào Prompts.
    *   **NO VIETNAMESE TEXT IN VISUALS**: Phần mô tả hình ảnh tuyệt đối KHÔNG chứa tiếng Việt (ví dụ: biển hiệu, nhãn mác). Nếu bắt buộc phải có chữ trong video, chỉ dùng TIẾNG ANH (ví dụ: "Danger" thay vì "Nguy hiểm").
    *   **One-Block**: Prompt Hình ảnh và Thoại ghép chung 1 đoạn.
    *   **Stateless**: Lặp lại full mô tả nhân vật.
    *   **Self-Intro**: Nhân vật ảo phải xưng tên.

### G. QUY TẮC "STATELESS PROMPT" (QUAN TRỌNG NHẤT)
*   **ĐỊNH NGHĨA**: Mỗi Prompt là một thế giới riêng biệt. AI vẽ video KHÔNG NHỚ clip trước đó.
*   **YÊU CẦU**: Phải **COPY-PASTE LẠI TOÀN BỘ** mô tả ngoại hình (Visual Bible) của nhân vật/bối cảnh vào **MỌI CLIP** mà chúng xuất hiện.
*   **CẤM**: Dùng từ thay thế chung chung như "The man", "He", "She", "The room".
*   **PHẢI DÙNG**: Full Description (ví dụ: "The friendly Asian mother character, 40s, wearing old clothes...").

---

## 3. CHECKLIST KIỂM TRA ĐỘNG (DYNAMIC CHECKLIST)

Trước khi chốt một prompt, phải tích đủ các ô sau:
- [ ] **Tính Liên Mạch**: Prompt này có bắt đầu bằng ngữ cảnh của cảnh trước không?
- [ ] **Tính Đầy Đủ**: Đã copy nguyên văn mô tả ngoại hình nhân vật (Bible) chưa? (Cấm viết "he", "the man" mà không kèm mô tả).
- [ ] **Tính Kỹ Thuật**: Góc máy có khác cảnh trước không? Có set FPS/Resolution không? (4k, 60fps).
- [ ] **Tính Đồng Bộ**: Biểu cảm nhân vật có khớp với lời thoại/tình huống không? (Ví dụ: Đang sợ hãi thì không thể "neutral face").
- [ ] **Tính Nhân Quả (Causality)**: Hành động của nhân vật B có phải là HỆ QUẢ của hành động nhân vật A ở clip trước không? (Ví dụ: Dạ Dày đau -> Phải có cảnh Người ăn thực phẩm bẩn. Nếu không có cảnh ăn -> Dạ Dày không thể bị đau).
- [ ] **Không Có Text Rác**: Đã thêm "no floating text, no subtitles" chưa?

---

## 4. VÍ DỤ ÁP DỤNG (EXAMPLE)

**Cảnh 1 (Trước đó)**: Người cha nhìn thấy bóng khủng long.
**Cảnh 2 (Hiện tại)**: Người cha hét lên cảnh báo gia đình.

**PROMPT (Strict output):**
> "Continuing from the moment the shadow appeared, now intense action sequence. Extreme close-up shot of **[The Father: a rugger caveman, 40 years old, muscular build, messy black hair, thick beard, scar on left cheek, wearing leopard skin loincloth, rugged realistic face]**. He screams frantically with wide terrified eyes, veins popping on neck, turning his head to look back. Background is **[Prehistoric cave entrance, massive gray rocky walls, fire pit burning wildly, dark ominous shadows]**. Cinematic dramatic lighting, high contrast. Audio includes shouting voice in Vietnamese, loud thunder clap, panic atmospherics. 4k resolution, hyper-realistic."

---
*Template này có thể thay đổi nội dung (text trong ngoặc vuông) tuỳ dự án, nhưng CẤU TRÚC 5 PHẦN và QUY TẮC "COPY BIBLE" là bắt buộc không đổi.*
