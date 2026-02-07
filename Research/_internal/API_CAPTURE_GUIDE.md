# 🕵️‍♂️ VEO API Capture Checklist

Để hoàn thiện API Integration, chúng ta cần "bắt" các gói tin sau từ **F12 > Network**.

## 🛠️ Cách thực hiện chung
1. Mở **VEO Flow** trên trình duyệt (Chrome).
2. Nhấn **F12** -> chọn tab **Network**.
3. Ô Filter (góc trên trái): Nhập từ khóa **`video:`** hoặc **`batch`**.
4. Thực hiện thao tác trên web (ví dụ: đổi model, bấm Generate).
5. Click vào dòng request mới hiện ra -> chọn tab **Payload** -> **Copy toàn bộ JSON**.

---

## 📋 Danh sách cần thu thập

### 1. Model Keys & Settings (Quan trọng nhất)
*Mục đích: Lấy đúng mã `videoModelKey` cho từng loại model.*

*   [ ] **Veo 3.1 - Quality**: Chọn model này -> Bấm Generate -> Copy Payload.
*   [ ] **Veo 3.1 - Fast (Portrait)**: Chọn tỷ lệ 9:16 -> Bấm Generate -> Copy Payload.
*   [ ] **Veo 2 - Fast**: Chọn model Veo 2 -> Bấm Generate -> Copy Payload.

### 2. Image Upload (Khó nhất)
*Mục đích: Tìm API để upload ảnh lên server Google.*

1.  Xóa filter cũ, nhập filter mới: **`upload`** hoặc **`scotty`**.
2.  Bấm dấu **(+)** để upload 1 ảnh bất kỳ.
3.  Tìm request có tên kiểu `uploadVideoImage` hoặc `start`.
4.  **Capture**:
    *   **URL** (địa chỉ gửi đi đâu?)
    *   **Headers** (đặc biệt là `Content-Type`, `X-Goog-Upload-Protocol`)
    *   **Response** (kết quả trả về là gì? ID của ảnh hay URL?)

### 3. Image-to-Video Generation
*Mục đích: Xem cách gửi thông tin ảnh đã upload để tạo video.*

1.  Sau khi upload ảnh xong.
2.  Filter lại: **`video:`**.
3.  Bấm **Generate**.
4.  **Capture Payload**: Chú ý phần `imageInput` hoặc `fileId`. Nó gửi cái gì? (Scotty ID hay URL?)

### 4. Kết quả trả về (Polling Response)
*Mục đích: Xác định chính xác vị trí link download (`fifeUrl`).*

1.  Đợi video tạo xong (thành công).
2.  Tìm request **`batchCheckAsyncVideoGenerationStatus`** cuối cùng.
3.  Tab **Response** -> Copy JSON.
4.  Chúng ta cần tìm xem link video nằm ở `metadata.video.fifeUrl` hay chỗ nào khác.

---

## 💡 Ví dụ Payload mẫu (Text-to-Video)
```json
{
  "requests": [
    {
      "videoModelKey": "veo_3_1_t2v_fast", // <-- Cần tìm cái này cho các model khác
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
      "textInput": { "prompt": "..." }
    }
  ]
}
```
