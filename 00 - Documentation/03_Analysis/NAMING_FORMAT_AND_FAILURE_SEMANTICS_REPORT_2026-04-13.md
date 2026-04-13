# Naming Format And Failure Semantics Report

Date: 2026-04-13

## 1. Executive Summary

Hiện tại codebase không có một naming system duy nhất cho mọi loại output. Nếu chỉ xét `runtime final outputs` của pipeline chính, `engine.py` và `upscale_queue.py` đã gần đồng bộ về format. Tuy nhiên nếu xét toàn codebase, vẫn còn nhiều format khác nhau cho:

- runtime final video/image
- manual or legacy batch download
- temp/intermediate files
- continuation frame
- legacy helper `upscaled_name`

Kết luận ngắn:

- Nếu chỉ nói về `runtime final video outputs`: hiện có `1 chuẩn runtime chính`, được dùng ở `2 path`
- Nếu nói về toàn codebase: hiện có ít nhất `5-6 format/pattern`
- Retry/replacement cho prompt nhiều output đã có logic preserve variant tốt hơn trước, nhưng naming chưa được chuẩn hóa thành một helper duy nhất

## 2. Current Formats In Codebase

### Format A: Runtime Final Video

Used by:

- `02 - CLIENT - VEO PRO MAX/core/engine.py:10944-11029`
- `02 - CLIENT - VEO PRO MAX/core/upscale_queue.py:2701-2743`

Format:

```text
{prompt_index_4digits}{variant?}_{timestamp?}_{quality?}_{model?}.mp4
```

Actual parts are controlled by settings:

- `include_timestamp`
- `include_quality`
- `include_model`
- `separator`

Examples:

- `0004_20260413_093259_720p.mp4`
- `0009a_20260413_092956_1080p.mp4`
- `0012c_20260413_101500_1080p_v31_pro.mp4`
- `9004d_20260413_093259_1080p.mp4`

### Format B: Runtime Final Image

Used by:

- `02 - CLIENT - VEO PRO MAX/core/engine.py:11024-11029`

Format:

```text
{prompt_index_4digits}{variant?}_{timestamp?}_{quality?}_{model?}.png
```

Examples:

- `0007_20260413_101000_1K.png`
- `0011b_20260413_101015_2K_v31_fast.png`

### Format C: Legacy / Manual Batch Video

Used by:

- `02 - CLIENT - VEO PRO MAX/utils/file_namer.py:76-102`
- called from `02 - CLIENT - VEO PRO MAX/core/queue_controller.py:311-315`

Format:

```text
{task}_{row:03d}_{output}_{quality}_{timestamp}.mp4
```

Examples:

- `batch_001_1_720p_20260413_103000.mp4`
- `Project_A_014_3_1080p_20260413_103015.mp4`

### Format D: Legacy / Manual Batch Image

Used by:

- `02 - CLIENT - VEO PRO MAX/utils/file_namer.py:104-128`

Format:

```text
{task}_{row:03d}_{output}_{timestamp}.png
```

Examples:

- `batch_001_1_20260413_103000.png`
- `Scene_A_014_2_20260413_103010.png`

### Format E: Temp / Intermediate Post-Process File

Used by watermark-removal / post-process flow in `engine.py` (`.tmp.mp4` behavior discussed separately).

Format:

```text
{final_base}.tmp.mp4
```

Examples:

- `0009d_20260413_064332_1080p.tmp.mp4`
- `0012_20260413_120100_720p.tmp.mp4`

### Format F: Continuation / Helper Legacy Patterns

Used by:

- `02 - CLIENT - VEO PRO MAX/utils/file_namer.py:130-147`
- `02 - CLIENT - VEO PRO MAX/utils/file_namer.py:149-165`

Formats:

```text
cont_{row:03d}_{timestamp}.png
{original_base}_{quality}_upscaled.mp4
```

Examples:

- `cont_014_20260413_103000.png`
- `scene_014_1080p_upscaled.mp4`

## 3. What Is The Runtime Naming Standard Right Now

The current runtime standard in the main pipeline is:

```text
{index(+variant)}_{timestamp}_{quality}_{model}
```

More precisely:

1. `prompt_num = prompt_index + 1`
2. `idx_str = zfill(4)`
3. variant is appended only when output belongs to a multi-output prompt or a retry/replacement of one slot in a multi-output prompt
4. timestamp is appended if `settings.include_timestamp`
5. quality is appended if `settings.include_quality`
6. model is appended if `settings.include_model`
7. extension is `.mp4` for video, `.png` for image

This logic is implemented in:

- `02 - CLIENT - VEO PRO MAX/core/engine.py:10944-11029`
- `02 - CLIENT - VEO PRO MAX/core/upscale_queue.py:2701-2743`

## 4. Variant Resolution Logic

Current runtime priority chain:

1. explicit `video_index`
2. `replace_target[1]`
3. `retry_original_indices`
4. fallback loop index

Relevant code:

- worker-side mapping: `02 - CLIENT - VEO PRO MAX/core/engine.py:5725-5728`
- retry task metadata copy: `02 - CLIENT - VEO PRO MAX/core/engine.py:9760-9766`
- final naming resolution in engine: `02 - CLIENT - VEO PRO MAX/core/engine.py:10954-11009`
- final naming resolution in UQ: `02 - CLIENT - VEO PRO MAX/core/upscale_queue.py:2708-2729`

This means the system now tries to preserve the original slot letter for single-output retry/replacement tasks that came from a multi-output original prompt.

## 5. Semantics By Prompt Shape

### Case A: Prompt With 1 Video Output

Expected runtime filename:

```text
{prompt4}_{timestamp}_{quality}.mp4
```

Example:

- `0004_20260413_093259_720p.mp4`

Rules:

- no `a/b/c/d` suffix is needed
- retry of a genuine single-output prompt should still remain single-output naming
- `9004_20260413_093259_1080p.mp4` is valid if the source task is truly a single-output prompt with `prompt_index = 9003`

### Case B: Prompt With N Video Outputs, 1 < N <= 4

Expected runtime filenames:

```text
{prompt4}a_{timestamp}_{quality}.mp4
{prompt4}b_{timestamp}_{quality}.mp4
{prompt4}c_{timestamp}_{quality}.mp4
{prompt4}d_{timestamp}_{quality}.mp4
```

Example for prompt `0009`:

- `0009a_20260413_092956_1080p.mp4`
- `0009b_20260413_092957_1080p.mp4`
- `0009c_20260413_092958_1080p.mp4`
- `0009d_20260413_092959_1080p.mp4`

Rules:

- suffix maps to original slot index, not to retry-order if retry metadata is available
- variant letters must remain stable across retry/replacement

## 6. What Happens When One Component Fails

### 6.1 If One Output Fails In A 1-Output Prompt

Expected behavior:

- retry task remains single-output
- no variant letter is introduced artificially

Example:

- original: `0004_20260413_093259_720p.mp4`
- retry: `0004_20260413_094010_1080p.mp4`

This is valid because there is no original multi-slot mapping to preserve.

### 6.2 If One Output Fails In An N-Output Prompt

Expected behavior:

- retry task may only download one output
- but filename must preserve original slot letter

Example:

- original prompt outputs:
  - `0009a_...`
  - `0009b_...`
  - `0009c_...`
  - `0009d_...`
- if only slot `d` fails:
  - retry output must still be `0009d_...`
  - not `0009_...`

This is what `replace_target` / `retry_original_indices` are for.

### 6.3 If Multiple Outputs Fail In An N-Output Prompt

Expected behavior:

- retry task may carry `retry_original_indices = [1, 3]`
- new outputs must preserve original letters:
  - worker 0 -> `b`
  - worker 1 -> `d`

Example:

- retry outputs:
  - `0009b_20260413_100100_1080p.mp4`
  - `0009d_20260413_100101_1080p.mp4`

### 6.4 If Prompt Index Info Is Missing

Current behavior:

- `prompt_index` falls back to `0`
- naming becomes `0001...`

This is syntactically valid but semantically dangerous because it can mislabel origin.

Recommended handling:

- log warning with task id
- optionally fail-fast in strict mode

### 6.5 If Variant Resolution Fails

Current behavior:

- fallback to loop index

This keeps file creation alive, but may produce a semantically wrong slot letter for retry/replacement.

Recommended handling:

- only fallback silently for fresh multi-output tasks
- for retry/replacement tasks, log warning if neither `replace_target` nor `retry_original_indices` is usable

### 6.6 If Timestamp Is Disabled

Current behavior:

- filenames can still be generated
- collision risk increases

Collision handling is not fully unified:

- engine/UQ use numeric suffix `_1`, `_2`, ...
- `FileNamer.ensure_unique()` uses `_v2`, `_v3`, ...

This is another remaining inconsistency.

## 7. Why Users Still See Different Naming Styles

There are 3 practical reasons:

### 7.1 Historical Files

Files created before the recent fix remain on disk. A new naming fix does not rename old files.

### 7.2 Different Pipeline Paths

`engine.py` and `upscale_queue.py` now use near-identical runtime naming, but `queue_controller.py` still uses `FileNamer.video_name()`.

### 7.3 Temp / Intermediate Files

Files such as `.tmp.mp4` are not final outputs. They follow a derivative temporary naming pattern and can remain if post-process cleanup is interrupted.

## 8. Current Gaps

### Gap 1: No Single Naming Helper

Naming logic is duplicated in:

- `engine.py`
- `upscale_queue.py`
- `utils/file_namer.py`

This guarantees future drift unless unified.

### Gap 2: Runtime And Manual Export Naming Are Different

This may be intentional, but it is not documented clearly. Right now users can see two naming styles in the same project ecosystem.

### Gap 3: Collision Strategy Is Not Unified

- engine/UQ: `_1`, `_2`, ...
- FileNamer: `_v2`, `_v3`, ...

### Gap 4: Failure Semantics Are Implicit

The system already has retry metadata, but there is no single documented resolver contract for:

- fresh multi-output task
- single-slot retry
- multi-slot retry
- replacement task

## 9. Recommended Standard

Adopt one canonical runtime filename contract:

```text
{prompt4}{variant?}_{timestamp?}_{quality?}_{model?}.{ext}
```

Variant resolver contract:

1. explicit `video_index`
2. `replace_target[1]`
3. `retry_original_indices`
4. loop index fallback

Collision resolver contract:

```text
name.ext
name_1.ext
name_2.ext
...
```

Manual export can either:

- reuse the same runtime helper, or
- stay separate but be explicitly documented as a manual-export-only format

## 10. Detailed Implementation Plan

### Phase 0: Freeze The Contract

Create one short spec document or module docstring defining:

- index width = `4`
- variant rules
- timestamp rules
- quality/model rules
- extension rules
- collision suffix rules

Output:

- one canonical spec for runtime naming

### Phase 1: Extract Shared Helper

Create a shared helper, for example:

- `02 - CLIENT - VEO PRO MAX/core/output_naming.py`

Recommended API:

```python
build_output_filename(
    *,
    task,
    video_index: int = -1,
    loop_index: int = 0,
    total_outputs: int = 1,
    target_quality: str | None = None,
    quality_subfolder: str | None = None,
    ext: str,
    settings,
)
```

Recommended helper internals:

- resolve prompt index
- resolve variant index
- build parts in one order only
- apply separator
- return filename only

### Phase 2: Move Engine To Shared Helper

Replace duplicated block in:

- `02 - CLIENT - VEO PRO MAX/core/engine.py:10944-11029`

Expected result:

- main download path no longer owns its own naming logic

### Phase 3: Move UpscaleQueue To Shared Helper

Replace duplicated block in:

- `02 - CLIENT - VEO PRO MAX/core/upscale_queue.py:2701-2743`

Expected result:

- runtime final 1080p save path becomes guaranteed identical to engine path

### Phase 4: Decide Fate Of FileNamer

Choose one of two options:

#### Option A: Deprecate FileNamer For Video/Image Output

- keep it only for non-runtime helper files
- remove usage from `queue_controller.py`

#### Option B: Rewire FileNamer To Shared Helper

- `video_name()` and `image_name()` become wrappers around the shared naming helper

Recommended option:

- Option B if queue/manual download is still user-facing
- Option A if queue/manual export is legacy-only and should not define visible naming behavior

### Phase 5: Unify Collision Handling

Use one collision strategy everywhere:

- `_1`, `_2`, `_3`...

Touchpoints:

- engine overwrite-avoid loop: `02 - CLIENT - VEO PRO MAX/core/engine.py:11039-11043`
- UQ overwrite-avoid loop: `02 - CLIENT - VEO PRO MAX/core/upscale_queue.py:2746-2750`
- `FileNamer.ensure_unique()`: `02 - CLIENT - VEO PRO MAX/utils/file_namer.py:167+`

### Phase 6: Add Resolver Diagnostics

Add debug logging when retry/replacement naming is resolved:

- prompt index
- original slot index
- chosen variant
- source of mapping (`video_index`, `replace_target`, `retry_original_indices`, fallback)

This makes future naming disputes easy to verify from logs.

### Phase 7: Add Tests

Minimum test matrix:

1. single-output prompt
2. fresh 4-output prompt
3. replacement task with `replace_target`
4. retry task with `retry_original_indices = [3]`
5. retry task with `retry_original_indices = [1, 3]`
6. timestamp disabled
7. quality disabled
8. collision suffix behavior

### Phase 8: Optional Migration / Janitor

Do not rename historical user outputs automatically by default.

Optional tools:

- audit tool to classify existing files by format
- dry-run rename proposal for legacy outputs
- cleanup pass for stale `.tmp.mp4`

## 11. Recommended Final Position

The current state should be described as:

- `engine.py` and `upscale_queue.py` runtime naming are now largely aligned
- variant preservation for retry/replacement is improved
- naming is still not fully standardized across the entire codebase because `FileNamer` / `QueueController` remain on a different convention

This wording is accurate and avoids over-claiming that the whole naming system is already unified.
