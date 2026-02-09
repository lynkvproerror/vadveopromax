# 📹 TAB_01: Text-to-Video Workflow

## Tổng quan

Text-to-Video (T2V) là workflow cơ bản nhất, chuyển đổi prompt văn bản thành video sử dụng VEO AI.

---

## 🎯 Main Workflow Diagram

```mermaid
flowchart TD
    subgraph UI["🖥️ UI LAYER"]
        A[Nhập prompts vào Bulk Input] --> B[Click 📋 Parse Prompts]
        B --> C[Xem Parsed Prompts Table]
        C --> D{Chọn continuation mode?}
        D -->|Yes| E[Check continuation toggles]
        D -->|No| F[Giữ mặc định]
        E --> G[Click 📋 Add to Queue]
        F --> G
        G --> H[Job thêm vào Queue]
    end

    subgraph QUEUE["📋 QUEUE LAYER"]
        H --> I[Queue Manager nhận Job]
        I --> J[Click ▶️ Start]
        J --> K[TaskController.start]
    end

    subgraph Playwright["🔌 Playwright LAYER"]
        K --> L[Navigate to VEO Flow]
        L --> M[Click New Project]
        M --> N[Apply Settings]
        N --> O[Select Text Mode]
        O --> P[For each prompt]
        P --> Q[processPromptOnPage]
        Q --> R{More prompts?}
        R -->|Yes| P
        R -->|No| S[Start Scanner]
        S --> T[Wait for videos]
        T --> U[Download videos]
    end

    style UI fill:#e1f5fe
    style QUEUE fill:#fff3e0
    style Playwright fill:#f3e5f5
```

---

## 📋 Chi tiết từng nút bấm

### 1. Nút "📥 Import TXT"

```mermaid
flowchart LR
    A[Click Import TXT] --> B[filedialog.askopenfilename]
    B --> C{File selected?}
    C -->|No| D[Return]
    C -->|Yes| E[Read file content]
    E --> F[Split by \\n\\n]
    F --> G[Set to Bulk Input]
    G --> H[Auto-call Parse]
```

| Bước | Action | Wait Time |
|------|--------|-----------|
| 1 | Hiện file dialog | User action |
| 2 | Đọc nội dung file | 0ms |
| 3 | Split bằng `\n\n` | 0ms |
| 4 | Gán vào bulk_input | 0ms |
| 5 | Tự động gọi Parse | 0ms |

---

### 2. Nút "📋 Parse Prompts"

```mermaid
flowchart LR
    A[Click Parse] --> B[Get bulk_input text]
    B --> C[Split by blank lines]
    C --> D[Filter empty strings]
    D --> E[Create prompt objects]
    E --> F[Update parsed_table]
    F --> G[Update queue_preview]
```

**Code logic:**
```python
def on_parse_click():
    raw = bulk_input.get("1.0", "end").strip()
    prompts = [p.strip() for p in raw.split("\n\n") if p.strip()]
    
    for i, prompt in enumerate(prompts):
        parsed_table.add_row({
            "index": i + 1,
            "text": prompt[:50] + "...",
            "continuation": i > 0  # Default: continuation ON for 2nd+
        })
    
    queue_preview.update(
        jobs=1,
        tasks=len(prompts),
        total=len(prompts) * outputs_per_prompt
    )
```

---

### 3. Nút "📋 Add to Queue"

```mermaid
flowchart TD
    A[Click Add to Queue] --> B{prompts.length > 0?}
    B -->|No| C[Show error: No prompts]
    B -->|Yes| D[Create Job object]
    D --> E[job.mode = text-to-video]
    E --> F[job.prompts = parsed_list]
    F --> G[job.settings = sidebar values]
    G --> H[masterQueue.push job]
    H --> I[Save to storage]
    I --> J[Clear input fields]
    J --> K[Update queue counter]
```

**Job Object Structure:**
```python
job = {
    "id": "1737445615123",
    "mode": "text-to-video",
    "prompts": [
        "A sunset scene over mountains...",
        "Camera pans across the valley..."
    ],
    "images": [],  # Empty for T2V
    "downloadFolder": "T2V-Project-01",
    "repeatCount": "4",
    "model": "default",  # veo3_fast
    "aspectRatio": "landscape",
    "startFrom": 1,
    "status": "pending",
    "progress": {"completed": 0, "total": 2},
    "currentIndex": 0
}
```

---

## 🔌 Playwright Execution Flow

### Phase 1: Project Initialization

```mermaid
sequenceDiagram
    participant App as VEO App
    participant Tab as Browser Tab
    participant Flow as VEO Flow Page
    
    App->>Tab: Navigate to labs.google/fx/tools/flow
    Tab-->>App: Page loaded
    App->>Tab: Wait 2s
    App->>Flow: Click NEW_PROJECT_BUTTON
    Tab-->>App: Navigate to /project/{id}
    App->>Tab: Set zoom 50%
    App->>Flow: Click GRID_VIEW_BUTTON
    App->>Flow: Click VIDEOCAM_BUTTON
```

| Bước | XPath Selector | Wait After |
|------|---------------|------------|
| 1 | Navigate URL | Tab load (60s max) |
| 2 | `NEW_PROJECT_BUTTON_XPATH` | Tab load (60s max) |
| 3 | `setZoom(0.5)` | 2s |
| 4 | `GRID_VIEW_BUTTON_XPATH` | 500ms |
| 5 | `VIDEOCAM_BUTTON_XPATH` | 500ms |

---

### Phase 2: Settings Configuration

```mermaid
sequenceDiagram
    participant App as VEO App
    participant Settings as Settings Panel
    
    App->>Settings: Click SETTINGS_BUTTON
    Note over Settings: Panel opens
    App->>Settings: Wait 1s
    
    App->>Settings: Click OUTPUT_NUMBER_BUTTON
    App->>Settings: Wait 500ms
    App->>Settings: Click OUTPUT_NUMBER_{N}_XPATH
    App->>Settings: Wait 500ms
    
    App->>Settings: Click MODEL_SELECTION_BUTTON
    App->>Settings: Wait 500ms
    App->>Settings: Click MODEL_{type}_XPATH
    App->>Settings: Wait 500ms
    
    App->>Settings: Click ASPECT_RATIO_DROPDOWN
    App->>Settings: Wait 500ms
    App->>Settings: Click LANDSCAPE/PORTRAIT_XPATH
    App->>Settings: Wait 500ms
    
    App->>Settings: Press Escape key
    App->>Settings: Wait 1s
```

**Selectors Used:**
| Setting | Button Selector | Option Selector |
|---------|----------------|-----------------|
| Output Count | `OUTPUT_NUMBER_BUTTON_XPATH` | `OUTPUT_NUMBER_{1,2,3,4}_XPATH` |
| Model | `MODEL_SELECTION_BUTTON_XPATH` | `MODEL_VEO_{2,3}_{FAST,QUALITY}_XPATH` |
| Aspect | `ASPECT_RATIO_DROPDOWN_XPATH` | `LANDSCAPE/PORTRAIT_ASPECT_RATIO_XPATH` |

---

### Phase 3: Mode Selection

```mermaid
flowchart LR
    A[Check MODE_DROPDOWN text] --> B{Contains 'Text-to-Video'?}
    B -->|Yes| C[Already correct - skip]
    B -->|No| D[Click MODE_DROPDOWN]
    D --> E[Wait 500ms]
    E --> F[Click TEXT_TO_VIDEO_MODE]
    F --> G[Wait 500ms]
```

---

### Phase 4: Prompt Processing (processPromptOnPage)

```mermaid
sequenceDiagram
    participant App as VEO App  
    participant Textarea as Prompt Textarea
    participant Button as Generate Button
    participant Toast as Toast Notification
    
    App->>Textarea: getElementById(PROMPT_TEXTAREA_ID)
    App->>Textarea: focus()
    App->>App: Wait 50ms
    
    App->>Textarea: Set value via prototype
    App->>Textarea: Dispatch 'input' event
    App->>App: Wait 50ms
    
    App->>Textarea: blur()
    App->>App: Wait 50ms
    
    loop Poll for button (30 iterations)
        App->>Button: Check GENERATE_BUTTON enabled
        alt Button enabled
            App->>Button: click()
            App->>App: Wait 1s
            
            loop Check for errors (10 iterations)
                App->>Toast: Check QUEUE_FULL_POPUP
                alt Queue Full
                    App-->>App: Return "QUEUE_FULL"
                end
                App->>Toast: Check POLICY_ERROR_POPUP
                alt Policy Error
                    App-->>App: Return "POLICY_PROMPT"
                end
                App->>App: Wait 1s
            end
            App-->>App: Return true
        else Button disabled
            App->>App: Wait 200ms
        end
    end
    App-->>App: Return false (timeout)
```

**Timing Constants:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `FOCUS_DELAY` | 50ms | After focus/blur/input |
| `BUTTON_POLL_INTERVAL` | 200ms | Between button checks |
| `BUTTON_POLL_MAX` | 30 | Max button poll iterations |
| `POST_CLICK_DELAY` | 1000ms | After clicking Generate |
| `ERROR_CHECK_ITERATIONS` | 10 | Times to check for popups |

---

### Phase 5: Queue Full Handling

```mermaid
flowchart TD
    A[QUEUE_FULL detected] --> B[Start retry loop]
    B --> C[Attempt 1-10: Wait 10s each]
    C --> D{Queue cleared?}
    D -->|Yes| E[Continue processing]
    D -->|No| F[Wait 30s]
    F --> G[Attempt 11-20: Wait 10s each]
    G --> H{Queue cleared?}
    H -->|Yes| E
    H -->|No| I[Attempt 21-30: Wait 10s each]
    I --> J{Queue cleared?}
    J -->|Yes| E
    J -->|No| K[Mark as failed, stop]
```

**Retry Configuration:**
| Phase | Attempts | Interval | Total Wait |
|-------|----------|----------|------------|
| Phase 1 | 10 | 10s | 100s |
| Wait | - | 30s | 30s |
| Phase 2 | 10 | 10s | 100s |
| Phase 3 | 10 | 10s | 100s |
| **Total** | **30** | - | **~5.5 min** |

---

### Phase 6: Video Scanning & Download

```mermaid
flowchart TD
    A[All prompts submitted] --> B[Start Scanner]
    B --> C[scanExistingVideos]
    C --> D[Compare with downloadedVideoUrls]
    D --> E{New videos found?}
    E -->|Yes| F[Add to download queue]
    E -->|No| G[Continue scanning]
    F --> G
    G --> H{Job complete?}
    H -->|No| I[Wait SCAN_INTERVAL]
    I --> C
    H -->|Yes| J[Stop scanner]
    J --> K[Move to next job]
```

**Scanner Configuration:**
| Setting | Value |
|---------|-------|
| `SCAN_INTERVAL` | 5000ms (5s) |
| `FINAL_SCAN_TIMEOUT` | 180000ms (3 min) |
| `FINAL_SCAN_CHECK_INTERVAL` | 5000ms (5s) |

---

## ❌ Error Handling

| Error Type | Detection | Action |
|------------|-----------|--------|
| QUEUE_FULL | XPath: `...contains(., '5')` | Retry loop (30 attempts) |
| POLICY_PROMPT | XPath: `...@data-sonner-toast...error` | Mark failed, skip |
| TIMEOUT | Button not enabled in 6s | Reload page, retry (max 3) |
| NETWORK | Tab closed/navigation error | Stop queue |

## 🔄 Continuation Mode (Frame Chaining)

Khi continuation mode được bật (per-prompt toggle), worker tự chuyển sang F2V workflow:

```mermaid
flowchart LR
    A[Video #1 complete] --> B[Download 720p]
    B --> C[FFmpeg Extract Frame]
    C --> D[Base64 Encode]
    D --> E[Upload Image API]
    E --> F[Get mediaId]
    F --> G[Generate Video #2 via F2V]
```

### T2V + Continuation Logic

| Prompt | CONT | Workflow thực tế | Image Source |
|--------|------|-----------------|-------------|
| #1 | OFF | T2V | — |
| #2 | ON | **F2V** | Extracted frame từ #1 |
| #3 | ON | **F2V** | Extracted frame từ #2 |
| #4 | OFF | T2V | — (new chain) |

> [!NOTE]
> T2V + CONT ON = Worker tự động chuyển workflow thành F2V, dùng extracted frame làm `startImage` (hoặc `endImage` nếu `frame_source=FIRST`).

Xem chi tiết matrix: [FRAME_CONTINUATION_WORKFLOW.md](../02_Architecture/FRAME_CONTINUATION_WORKFLOW.md)

---

## 🔗 Related Files

| File | Description |
|------|-------------|
| [TAB_01_TEXT_TO_VIDEO.md](../01_UI_UX/TAB_01_TEXT_TO_VIDEO.md) | UI Layout & Widgets |
| [FRAME_CONTINUATION_WORKFLOW.md](../02_Architecture/FRAME_CONTINUATION_WORKFLOW.md) | Full continuation workflow & terminology |
