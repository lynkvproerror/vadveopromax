# 🔄 Batch Operation Flow Documentation

> **Version**: 1.0  
> **Updated**: 2026-02-02

---

## 📋 Overview

Batch operations cho phép xử lý nhiều items cùng lúc trong VEO Pro Max.

---

## 1. Batch Video Generation

### Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    BATCH QUEUE                           │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐            │
│   │ Item 1  │───►│ Item 2  │───►│ Item 3  │───► ...    │
│   │ Pending │    │ Running │    │ Queued  │            │
│   └─────────┘    └─────────┘    └─────────┘            │
│                       │                                  │
│                       ▼                                  │
│              ┌──────────────┐                           │
│              │   Worker     │                           │
│              │ (Parallel 1-3)│                           │
│              └──────────────┘                           │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Queue States

| State | Description |
|-------|-------------|
| `queued` | Waiting in queue |
| `running` | Currently processing |
| `completed` | Successfully finished |
| `failed` | Error occurred |
| `cancelled` | User cancelled |

---

## 2. API Batch Request

### Request Format

```python
batch_items = [
    {
        "prompt": "A cat playing piano",
        "mode": "text_to_video",
        "model": "veo-2.0",
        "duration": 8,
        "aspect_ratio": "16:9"
    },
    {
        "prompt": "A dog surfing",
        "mode": "text_to_video",
        "model": "veo-2.0",
        "duration": 8,
        "aspect_ratio": "16:9"
    }
]
```

### Parallel Processing

```python
class BatchProcessor:
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.queue = asyncio.Queue()
        
    async def process_batch(self, items: list):
        # Add all items to queue
        for item in items:
            await self.queue.put(item)
        
        # Create workers
        workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.max_workers)
        ]
        
        # Wait for completion
        await self.queue.join()
        
    async def worker(self, worker_id: int):
        while True:
            item = await self.queue.get()
            try:
                await self.process_item(item)
            finally:
                self.queue.task_done()
```

---

## 3. Rate Limiting

### Limits by License Type

| Gói | Parallel Workers | Queue Size | Mô tả |
|-----|------------------|------------|-------|
| 🆓 Trial (7d) | 2 | 10 prompts/task | Giới hạn: 1 cookie, 2 threads |
| 💎 Premium (Paid) | Unlimited* | Unlimited | Không giới hạn |

*Premium bao gồm: 1 Tháng, 3 Tháng, 6 Tháng, 1 Năm, Vĩnh viễn

### Rate Limit Handling

```python
class RateLimiter:
    def __init__(self, tier: str):
        self.limits = TIER_LIMITS[tier]
        self.usage_today = 0
        
    def can_process(self) -> bool:
        return self.usage_today < self.limits['daily']
    
    def wait_if_needed(self) -> float:
        """Return seconds to wait if rate limited"""
        if self.is_rate_limited():
            return self.time_until_reset()
        return 0
```

---

## 4. Error Handling in Batch

### Retry Logic

```python
class BatchItem:
    max_retries = 3
    retry_delay = 5  # seconds
    
    async def process_with_retry(self):
        for attempt in range(self.max_retries):
            try:
                result = await self.process()
                return result
            except RateLimitError:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
            except TemporaryError:
                await asyncio.sleep(self.retry_delay)
            except PermanentError:
                self.status = 'failed'
                return None
        
        self.status = 'failed'
        return None
```

### Error Types

| Error | Retry? | Action |
|-------|--------|--------|
| RateLimitError | Yes | Wait + retry |
| NetworkError | Yes | Retry 3x |
| InvalidPrompt | No | Skip item |
| AuthError | No | Stop batch |
| QuotaExceeded | No | Pause batch |

---

## 5. Batch Status Tracking

### Status Object

```python
@dataclass
class BatchStatus:
    batch_id: str
    total: int
    completed: int
    failed: int
    running: int
    queued: int
    
    @property
    def progress(self) -> float:
        return (self.completed + self.failed) / self.total * 100
    
    @property
    def is_done(self) -> bool:
        return self.queued == 0 and self.running == 0
```

### Progress Callback

```python
def on_batch_progress(status: BatchStatus):
    print(f"Progress: {status.progress:.1f}%")
    print(f"Completed: {status.completed}/{status.total}")
    if status.failed > 0:
        print(f"Failed: {status.failed}")
```

---

## 6. Batch UI Integration

### Queue Panel

```
┌─────────────────────────────────────────┐
│ 📋 Batch Queue                    [3/10] │
├─────────────────────────────────────────┤
│ ▶ Item 1: A cat playing...    [Running] │
│   Item 2: A dog surfing...    [Queued]  │
│   Item 3: Ocean waves...      [Queued]  │
│ ✓ Item 4: Mountain view...    [Done]    │
│ ✗ Item 5: Invalid prompt      [Failed]  │
├─────────────────────────────────────────┤
│ [Pause] [Resume] [Cancel All]           │
└─────────────────────────────────────────┘
```

### Actions

| Action | Shortcut | Description |
|--------|----------|-------------|
| Pause | Ctrl+P | Pause queue processing |
| Resume | Ctrl+R | Resume paused queue |
| Cancel | Ctrl+C | Cancel all pending items |
| Retry Failed | - | Retry all failed items |
| Clear Completed | - | Remove completed from list |

---

## 7. Batch Export

### Export Results

```python
def export_batch_results(batch_id: str, output_dir: Path):
    """Export all completed videos to folder"""
    results = get_batch_results(batch_id)
    
    for item in results:
        if item.status == 'completed':
            # Download video
            download_video(item.video_url, output_dir / f"{item.id}.mp4")
            
            # Save metadata
            save_json(item.metadata, output_dir / f"{item.id}.json")
    
    return len([r for r in results if r.status == 'completed'])
```

---

*Batch Operation Flow Documentation for VEO Pro Max. Last updated: 2026-02-02*
