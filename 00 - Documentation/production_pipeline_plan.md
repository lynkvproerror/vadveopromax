# Full Production Pipeline — Implementation Plan

## Mục tiêu

Biến Project Builder từ **text-only generator** thành **full production pipeline** với 7 giai đoạn:

```
[1. Duration] →✓→ [2. Script Analysis] →✓→ [3. Scene Breakdown] →✓→ [4. Character T2I] →✓→ [5. Scene T2I] →✓→ [6. Video I2V/R2V] →✓→ [7. Concat]
```

Mỗi stage dừng lại → user review/confirm → mới chạy stage tiếp.

## Thiết kế cốt lõi

### 1. Sequential with Checkpoints
Mỗi stage hoàn thành → **dừng lại** → user review kết quả → confirm/edit → mới chạy stage tiếp theo.

### 2. Sidebar Pipeline Mode Toggle
SetupMatrix sidebar dropdown:
- **"📝 Prompt Text Only"** → pipeline cũ (Research → Bible → Prompts → SEO)
- **"🎬 Full Production"** → pipeline mới 7 stages

### 3. Reuse Existing Engine Tabs
Stage 4-7 sử dụng Queue tab + engine tabs (T2V/I2V/R2V) bình thường.
Kết quả hiển thị **cả 2 nơi** (Queue tab + Project Builder tab) để đánh giá chọn.

---

## Hiện trạng

| Component | Đã có | Cần thêm |
|-----------|-------|----------|
| Duration Estimation | ✅ `setup_matrix.py` | — |
| Gemini API text gen | ✅ `project_builder.py` | Script analysis + Scene breakdown |
| T2I pipeline | ✅ `engine.py` | Feed từ Builder |
| R2V | ✅ `engine.py` | Feed từ Builder |
| Queue tab | ✅ `tab_queue.py` | Mirror results to Builder |
| FFmpeg concat | ✅ `frame_extractor.py` | Concat step |
| Pipeline orchestrator | ❌ | **NEW: `ProductionPipeline`** |
| Checkpoint UI | ❌ | **NEW: stage review panel** |

---

## Architecture

### [NEW] `core/production_pipeline.py`

```python
class ProductionPipeline:
    STAGES = [
        "duration_estimate",   # 1. Auto from sidebar
        "script_analysis",     # 2. Gemini → JSON
        "scene_breakdown",     # 3. Gemini → scenes list
        "character_gen",       # 4. Prompts → Queue tab (T2I)
        "scene_image_gen",     # 5. Prompts → Queue tab (T2I)
        "video_gen",           # 6. Queue tab (I2V/R2V)
        "concat",              # 7. FFmpeg
    ]
    
    async def run_stage(self, stage_name, input_data) -> StageResult:
        """Run ONE stage. Returns result for user review."""
```

### Per-stage data flow

| Stage | Input | Engine Tab? | Output | User Checkpoint |
|-------|-------|-------------|--------|----------------|
| 1 | sidebar config | No | scene_count, clip_duration | Confirm số scene |
| 2 | topic + scene_count | No (Gemini) | script JSON | Review/edit kịch bản |
| 3 | script JSON | No (Gemini) | scene prompts list | Review/edit prompts |
| 4 | character descriptions | Queue (T2I) | character images | Chọn ảnh tốt nhất |
| 5 | scene desc + char ref | Queue (T2I) | scene images | Chọn ảnh tốt nhất |
| 6 | scene images + prompts | Queue (I2V/R2V) | video clips | Review clips |
| 7 | video clips | FFmpeg | final_video.mp4 | Preview & export |

---

## Files Modified

| File | Changes |
|------|---------|
| `setup_matrix.py` | Pipeline Mode toggle, `get_config().pipeline_mode` |
| `project_builder.py` | `TopicResult` new fields, `STEP_MODEL_CONFIG` for ScriptAnalysis/SceneBreakdown |
| `tab_project.py` | Stage progress bar, checkpoint UI, mode-based button visibility |
| `parsed_projects.py` | Stage badges, image/video preview, results mirror from Queue |
| `core/production_pipeline.py` | **NEW** — Pipeline orchestrator |

---

## Phân giai đoạn triển khai

| Phase | Stages | Scope |
|-------|--------|-------|
| **Phase 1** | 1-3 + Sidebar toggle + Checkpoint UI | Gemini API only |
| **Phase 2** | 4-5 + Queue mirror + Image preview | Engine T2I |
| **Phase 3** | 6-7 + Video preview + FFmpeg concat | Engine I2V/R2V |
