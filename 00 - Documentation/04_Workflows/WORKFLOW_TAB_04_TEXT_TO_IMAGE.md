# 🎯 TAB_04: Text-to-Image Workflow

## Tổng quan

Text-to-Image (T2I) sử dụng **Banana Model** (không phải VEO) để tạo ảnh từ prompt văn bản. Workflow khác biệt với TAB_01-03.

---

## 🎯 Main Workflow Diagram

```mermaid
flowchart TD
    subgraph UI["🖥️ UI LAYER"]
        A[Nhập prompts vào Bulk Input] --> B[Click 📋 Parse Prompts]
        B --> C[Xem Parsed Prompts Table]
        C --> D[Không có continuation column]
        D --> E[Click 📋 Add to Queue]
    end

    subgraph QUEUE["📋 QUEUE LAYER"]
        E --> F[Create Job với mode=textToImage]
        F --> G[Queue Manager nhận Job]
    end

    subgraph BANANA["🍌 BANANA ENGINE"]
        G --> H[Navigate to Banana page]
        H --> I[Apply Image Settings]
        I --> J[For each prompt]
        J --> K[processTextToImage]
        K --> L{More prompts?}
        L -->|Yes| J
        L -->|No| M[Scan & Download images]
    end

    style UI fill:#f3e5f5
    style QUEUE fill:#fff3e0
    style BANANA fill:#fff9c4
```

---

## ⚠️ Key Differences from Video Workflows

| Aspect | Video (TAB_01-03) | Image (TAB_04) |
|--------|-------------------|----------------|
| Engine | VEO Flow | Banana Model |
| Page URL | `/tools/flow` | `/tools/banana` (TBD) |
| Output | .mp4 videos | .png/.jpg images |
| continuation | ✅ Supported | ❌ Not applicable |
| Quality | 720p/1080p/4K | 2K/4K |
| Aspect | 16:9 / 9:16 | 16:9 / 9:16 / 1:1 |

---

## 🔌 Playwright Execution Flow

### Phase 1: Navigate to Banana Page

```mermaid
sequenceDiagram
    participant App as VEO App
    participant Tab as Browser Tab
    participant Banana as Banana Page
    
    App->>Tab: Navigate to labs.google/fx/tools/banana
    Tab-->>App: Page loaded
    App->>Banana: Wait for UI ready
    App->>App: Wait 2s
```

> ⚠️ **Note**: Cần verify URL chính xác từ extension 2.2.0.0_0

---

### Phase 2: Settings Configuration

```mermaid
sequenceDiagram
    participant App as VEO App
    participant Settings as Settings Panel
    
    Note over App,Settings: Image-specific settings
    
    App->>Settings: Select Model (Banana Bro/Pro)
    App->>App: Wait 500ms
    
    App->>Settings: Select Aspect Ratio (16:9/9:16/1:1)
    App->>App: Wait 500ms
    
    App->>Settings: Select Quality (2K/4K)
    App->>App: Wait 500ms
    
    App->>Settings: Select Output Count (1-4)
    App->>App: Wait 500ms
```

**Model Options:**
| Model | Description |
|-------|-------------|
| `banana_bro` | Standard quality, faster |
| `banana_pro` | Higher quality, slower |

**Quality Options:**
| Quality | Resolution |
|---------|------------|
| `2K` | 2048px |
| `4K` | 4096px |

---

### Phase 3: processTextToImage Flow

```mermaid
sequenceDiagram
    participant App as VEO App
    participant Textarea as Prompt Textarea
    participant Button as Generate Button
    participant Toast as Toast Notification
    
    App->>Textarea: getElementById(PROMPT_TEXTAREA_ID)
    App->>Textarea: focus()
    App->>App: Wait 50ms
    
    App->>Textarea: Set prompt value
    App->>Textarea: Dispatch 'input' event
    App->>App: Wait 50ms
    
    App->>Textarea: blur()
    App->>App: Wait 50ms
    
    loop Poll for button (30 iterations)
        App->>Button: Check GENERATE_BUTTON enabled
        alt Button enabled
            App->>Button: click()
            App->>App: Wait 1s
            
            loop Check for errors (10x)
                App->>Toast: Check QUEUE_FULL
                App->>Toast: Check POLICY_ERROR
            end
            App-->>App: Return success
        else Button disabled
            App->>App: Wait 200ms
        end
    end
```

---

### Phase 4: Image Scanning & Download

```mermaid
flowchart TD
    A[All prompts submitted] --> B[Start Image Scanner]
    B --> C[Find img elements]
    C --> D[Compare with downloaded set]
    D --> E{New images found?}
    E -->|Yes| F[Add to download queue]
    E -->|No| G[Continue scanning]
    F --> G
    G --> H{All images complete?}
    H -->|No| I[Wait 5s]
    I --> C
    H -->|Yes| J[Stop scanner]
```

**Image Detection:**
```javascript
// Scan for generated images
function scanGeneratedImages(selectors) {
    const images = [];
    const containers = document.querySelectorAll('[data-generated-image]');
    
    containers.forEach(container => {
        const img = container.querySelector('img[src^="http"]');
        if (img) {
            const src = img.getAttribute('src').split('?')[0];
            images.push(src);
        }
    });
    
    return images;
}
```

---

## ⏱️ Timing Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `FOCUS_DELAY` | 50ms | After focus/blur |
| `INPUT_DELAY` | 50ms | After setting value |
| `BUTTON_POLL_INTERVAL` | 200ms | Between checks |
| `BUTTON_POLL_MAX` | 30 | Max iterations |
| `POST_CLICK_DELAY` | 1000ms | After Generate click |
| `ERROR_CHECK_ITERATIONS` | 10 | Error popup checks |
| `SCAN_INTERVAL` | 5000ms | Image scan interval |
| `GENERATION_TIMEOUT` | 180s | Max wait per image |

---

## 📊 Estimated Times

| Output Count | Est. Time per Prompt |
|--------------|---------------------|
| 1 image | ~30-60s |
| 2 images | ~45-90s |
| 3 images | ~60-120s |
| 4 images | ~75-150s |

---

## ❌ Error Handling

| Error Type | Detection | Action |
|------------|-----------|--------|
| POLICY_PROMPT | Toast with error icon | Mark failed, skip |
| QUEUE_FULL | Toast with "5" | Retry loop (30x) |
| TIMEOUT | No result in 180s | Reload, retry (max 3) |
| NETWORK | Connection lost | Stop queue |

---

## 🔗 Related Files

| File | Description |
|------|-------------|
| [TAB_04_TEXT_TO_IMAGE.md](../01_UI_UX/TAB_04_TEXT_TO_IMAGE.md) | UI Layout & Widgets |
| [WORKFLOW_TAB_01_TEXT_TO_VIDEO.md](./WORKFLOW_TAB_01_TEXT_TO_VIDEO.md) | Similar prompt flow |
