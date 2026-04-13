# Bao cao phan tich va sua loi LP worker cap

## 1. Muc tieu

Tai khoan co cau hinh gioi han worker theo tung loai model trong `Settings > Profile`, nhung khi submit queue thi so luong submit worker thuc te van co the vuot qua gioi han cua model LP. Loi nay lam:

- Queue LP bi reserve task qua muc.
- So foreman submit bi scale theo `max_workers` tong thay vi LP cap.
- Phat sinh nhieu request song song hon muc cho phep.
- Tang kha nang gap `PUBLIC_ERROR_HIGH_TRAFFIC`.

Bao cao nay ghi lai:

- Dau hieu loi tu log.
- Root cause trong code.
- Code truoc khi sua.
- Code sau khi sua.
- Giai thich tai sao ban fix nay giai quyet dung van de.
- Cach verify.

## 2. Dau hieu loi tu log

Nhung dong log quan trong:

```text
[Supervisor:levanlinh.kma@gmail.com] Spawned CHỦ + 5 Foremen (max_workers=20, output=4, retry=3, timeout=120s)
```

```text
[ScaleForemen:levanlinh.kma@gmail.com] Scaling 5 → 20 foremen (pending=15, optimal=20, max_workers=20)
```

```text
[Dispatcher] 📋 Task group_20260413_102652_task_6 READY → RESERVED (account=levanlinh.kma@gmail.com, running_count=7)
```

Voi queue LP `veo_3_1_t2v_lite_low_priority`, neu profile LP cap chi cho phep vi du `8 worker slots` va task co `output_count = 4`, thi concurrent submit dung phai xap xi:

```text
prompt_cap = floor(8 / 4) = 2 prompt
```

Nhung log cho thay he thong da:

- Spawn 5 foremen ngay tu dau.
- Sau do scale len 20 foremen.
- Dispatcher tiep tuc reserve task den `running_count=7`.

Nghia la logic dispatch/submit dang bo qua LP cap.

## 3. Root cause

Van de khong nam o session LP pool, vi LP pool da ton tai san.

Trong `core/session.py` da co:

```python
active_workers_lp: int = 0
max_workers_lp: int = 20
```

Root cause thuc te nam o 3 diem:

1. `engine` spawn foremen bang `account.max_workers / output_count`.
2. `engine` scale foremen tiep tuc dua tren `account.max_workers` tong.
3. `dispatcher` hard-cap dua tren `_per_account_running` theo don vi `prompt/task`, nhung so sanh voi `max_workers` theo don vi `worker slots`.

Day la loi sai don vi dem:

- `_per_account_running` dem so `prompt`.
- `max_workers` va `max_workers_lp` dem so `worker slots/output workers`.

Neu so prompt dang chay duoc so sanh truc tiep voi worker slots, hard-cap se sai.

## 4. Code truoc khi sua

Luu y: nhung snippet duoi day la snapshot duoc chup ngay truoc khi patch, chi gom dung phan lien quan den loi LP overflow.

### 4.1. Engine truyen callback cu cho dispatcher

Truoc khi sua, `dispatcher` chi duoc cap mot callback tra ve `max_workers` tong:

```python
# Hard cap: Wire max_workers lookup so dispatcher can cap _per_account_running
# Without this, T2I fire-and-forget releases session workers immediately,
# allowing unbounded task dispatch (e.g., 54 tasks for max_workers=20)
def _get_max_workers(email: str) -> int:
    for acc in self._account_manager._accounts:
        if acc.email == email:
            return acc.session.max_workers
    return 20  # Fallback default
self._dispatcher.set_max_workers_fn(_get_max_workers)
```

Van de:

- Khong phan biet LP hay Fast.
- Khong phan biet `output_count`.
- Dispatcher chi biet `tai khoan nay co max_workers = 20`.

### 4.2. Engine spawn foremen theo tong pool

```python
# RC4: Calculate foreman count from max_workers / typical_output.
# Multiple foremen allow parallel polling (20/20 workers active).
# 429 prevention relies on _GLOBAL_MIN_SUBMIT_GAP (45s) + SubmitGate,
# NOT on limiting foremen count.
import math
typical_output = self._get_typical_output_count()
raw_foreman_count = max(1, math.ceil(account.max_workers / typical_output))
```

Van de:

- Luon lay `account.max_workers`.
- Khong dung `max_workers_lp`.
- `typical_output` la trung binh cua queue, nen khi queue bi tron T2V LP va task output=1 khac, foreman co the bi scale sai hon nua.

### 4.3. Engine dynamic scaling van dua tren tong pool

```python
# Calculate optimal foreman count per account
import math
typical_output = self._get_typical_output_count()
foreman_cap = 12 if self._is_image_only_workload() else account.max_workers
optimal = max(1, min(
    math.ceil(account.max_workers / typical_output),
    foreman_cap,
))
```

Van de:

- `optimal` van dua tren `account.max_workers`.
- Trong mixed workload, `typical_output` co the roi ve `1`, dan den scale truc tiep len `20`.

### 4.4. Dispatcher hard-cap sai don vi

```python
# Hard cap: prevent _per_account_running from exceeding max_workers
# Without this, T2I fire-and-forget releases session workers immediately,
# allowing unbounded task dispatch (e.g., 54 tasks for max_workers=20)
if account_email and self._get_max_workers_fn:
    my_running = self._per_account_running.get(account_email, 0)
    max_wk = self._get_max_workers_fn(account_email)
    if max_wk > 0 and my_running >= max_wk:
        log.debug(
            f"[Dispatcher] HardCap: {account_email} running={my_running} "
            f">= max_workers={max_wk} — yielding"
        )
        return None
```

Van de:

- `my_running` la so prompt.
- `max_wk` la so worker slots.
- So sanh nay khong dung cho LP queue co `output_count > 1`.

### 4.5. Dispatcher reserve task ma khong xet cap theo task

```python
# Smart Recovery: skip tasks that excluded this account
excluded = getattr(task, 'excluded_accounts', set())
if account_email and account_email in excluded:
    deferred.append((priority, group_key, prompt_idx, counter, task))
    continue  # Try next task

task.state = TaskState.RUNNING
task._counter_decremented = False  # Reset flag for new run
self._claim_task(task, account_email)
task.started_at = datetime.now()
self._running_count += 1
```

Van de:

- Sau khi qua excluded check la reserve task ngay.
- Khong tinh `task.model`.
- Khong tinh `task.output_count`.
- Khong tinh `LP cap`.

### 4.6. Clamp `output_count` chi dua theo tong pool

```python
# Edge case: if max_workers < output_count, clamp to max_workers
# Otherwise acquire_workers(output_count) would ALWAYS fail
if output_count > account.max_workers:
    log.warning(
        f"[{fid}] output_count={output_count} > "
        f"max_workers={account.max_workers} — clamping"
    )
    output_count = account.max_workers
```

Van de:

- LP task phai clamp theo `max_workers_lp`, khong phai tong pool.

## 5. Code sau khi sua

### 5.1. Engine truyen callback task-aware cho dispatcher

File hien tai: `02 - CLIENT - VEO PRO MAX/core/engine.py:3260`

```python
# Hard cap: expose task-aware prompt capacity so dispatcher reserves
# tasks against the correct model pool (LP vs Fast) and output_count.
def _get_max_workers(email: str, task: Task = None) -> int:
    for acc in self._account_manager._accounts:
        if acc.email == email:
            if task is not None:
                output_count = getattr(task, 'output_count', 1) or 1
                worker_cap = self._get_lp_worker_cap(acc) \
                    if self._task_uses_lp_workers(task) else acc.session.max_workers
                return self._get_prompt_concurrency_cap(worker_cap, output_count)
            return acc.session.max_workers
    return 20  # Fallback default
self._dispatcher.set_max_workers_fn(_get_max_workers)
```

Y nghia:

- Khi dispatcher dang xet mot `task` cu the, no se hoi engine:
  - task nay co phai LP khong?
  - `output_count` cua task nay la bao nhieu?
  - worker cap ung voi model nay la bao nhieu?
  - suy ra prompt cap = bao nhieu?

### 5.2. Engine co helper de doi worker cap sang prompt cap

File hien tai: `02 - CLIENT - VEO PRO MAX/core/engine.py:3456`

```python
def _peek_ready_tasks(self, limit: int = 10) -> List[Task]:
    """Peek READY tasks from dispatcher queue without consuming them."""
    ...

def _get_typical_output_count(self, ready_tasks: Optional[List[Task]] = None) -> int:
    """Determine typical output_count for foreman sizing."""
    ...

def _get_lp_worker_cap(self, account: AccountManager) -> int:
    """Return effective LP worker cap within the shared account pool."""
    total_cap = int(getattr(account.session, 'max_workers', 0) or 0)
    lp_cap = int(getattr(account.session, 'max_workers_lp', total_cap) or total_cap)
    if total_cap > 0 and lp_cap > 0:
        return min(total_cap, lp_cap)
    return max(total_cap, lp_cap, 1)

def _task_uses_lp_workers(self, task: Optional[Task]) -> bool:
    """Check whether a task should consume LP worker capacity."""
    ...

def _get_foreman_worker_cap(
    self,
    account: AccountManager,
    ready_tasks: Optional[List[Task]] = None,
) -> int:
    """Choose the worker pool cap used for foreman sizing.

    If the queued workload is mostly LP, size foremen from the LP pool.
    Mixed queues are still protected by dispatcher's task-aware hard cap.
    """
    ...

def _get_prompt_concurrency_cap(self, worker_cap: int, output_count: int) -> int:
    """Convert worker-slot capacity into concurrent prompt capacity."""
    worker_cap = max(1, int(worker_cap or 1))
    output_count = max(1, int(output_count or 1))
    return max(1, worker_cap // output_count)
```

Y nghia:

- `max_workers_lp` van la don vi worker slots.
- Dispatcher va foreman can don vi prompt slots.
- Ham moi quy doi ro rang:

```text
prompt_cap = floor(worker_cap / output_count)
```

Vi du:

- `worker_cap = 8`
- `output_count = 4`
- `prompt_cap = 2`

### 5.3. Engine spawn foremen theo model-aware cap

File hien tai: `02 - CLIENT - VEO PRO MAX/core/engine.py:3588`

```python
# RC4: Size foremen from prompt concurrency, not raw worker slots.
# LP queues use the LP pool cap so submitters cannot exceed Settings >
# Profile limits for that model family.
ready_tasks = self._peek_ready_tasks(limit=10)
typical_output = self._get_typical_output_count(ready_tasks)
worker_cap = self._get_foreman_worker_cap(account, ready_tasks)
raw_foreman_count = self._get_prompt_concurrency_cap(worker_cap, typical_output)
```

Khac biet chinh:

- Truoc: `ceil(account.max_workers / typical_output)`
- Sau: `prompt_cap(worker_cap, typical_output)`

Noi cach khac:

- Truoc kia foreman duoc scale theo tong pool.
- Bay gio foreman duoc scale theo pool dung voi loai task dang cho.

### 5.4. Engine dynamic scaling theo cap moi

File hien tai: `02 - CLIENT - VEO PRO MAX/core/engine.py:3711`

```python
# Calculate optimal foreman count per account from the
# effective worker pool for the queued workload.
ready_tasks = self._peek_ready_tasks(limit=10)
typical_output = self._get_typical_output_count(ready_tasks)
worker_cap = self._get_foreman_worker_cap(account, ready_tasks)
optimal = self._get_prompt_concurrency_cap(worker_cap, typical_output)
if self._is_image_only_workload():
    optimal = min(optimal, 12)
```

Y nghia:

- `optimal` khong con scale bang `account.max_workers`.
- Mixed queue van an toan hon vi dispatcher con co hard-cap theo tung task o buoc reserve.

### 5.5. Dispatcher co helper cap theo task

File hien tai: `02 - CLIENT - VEO PRO MAX/core/dispatcher.py:473`

```python
def _get_account_task_cap(
    self,
    email: Optional[str],
    task: Optional['Task'] = None,
) -> int:
    """Resolve prompt hard-cap for an account, optionally task-aware."""
    if not email or not self._get_max_workers_fn:
        return 0
    try:
        if task is not None:
            return int(self._get_max_workers_fn(email, task) or 0)
        return int(self._get_max_workers_fn(email) or 0)
    except TypeError:
        try:
            return int(self._get_max_workers_fn(email) or 0)
        except Exception:
            return 0
    except Exception:
        return 0
```

Y nghia:

- Dispatcher gio co the hoi cap theo tung task.
- Van giu fallback de khong lam vo callback cu neu co noi khac chua update.

### 5.6. Dispatcher hard-cap tai dung cho reserve task

File hien tai: `02 - CLIENT - VEO PRO MAX/core/dispatcher.py:725`

```python
# Prompt-level hard cap: compare running prompt count against
# this task's effective prompt capacity, not raw worker slots.
if account_email and self._get_max_workers_fn:
    my_running = self._per_account_running.get(account_email, 0)
    task_cap = self._get_account_task_cap(account_email, task)
    if task_cap > 0 and my_running >= task_cap:
        deferred.append((priority, group_key, prompt_idx, counter, task))
        continue
```

Day la diem sua quan trong nhat.

Luc nay dispatcher se:

1. Lay task ra khoi queue.
2. Xem task nay la LP hay Fast.
3. Tinh cap theo `model + output_count`.
4. Neu da du prompt slot, task se bi `defer`, khong reserve.

Nghia la task LP se khong the tiep tuc bi `READY -> RESERVED` vuot muc profile.

### 5.7. Clamp `output_count` theo worker cap dung cua task

File hien tai: `02 - CLIENT - VEO PRO MAX/core/engine.py:4278`

```python
# Edge case: if the model-specific worker cap is smaller than
# output_count, clamp before trying to acquire workers.
task_worker_cap = (
    self._get_lp_worker_cap(account)
    if getattr(task, "_is_lp_task", False)
    else max(1, int(account.max_workers or 1))
)
if output_count > task_worker_cap:
    log.warning(
        f"[{fid}] output_count={output_count} > "
        f"worker_cap={task_worker_cap} — clamping"
    )
    output_count = task_worker_cap
    task.output_count = output_count
```

Y nghia:

- LP task neu output_count vuot LP cap thi se bi clamp som.
- Tranh truong hop submit xong moi phat hien khong du capacity.

## 6. Tai sao ban fix nay dung

### 6.1. Sua dung don vi dem

Day la phan quan trong nhat.

Truoc khi sua:

- Engine va dispatcher dem lung tung giua:
  - `prompt/task`
  - `worker slots`

Sau khi sua:

- Session van quan ly `worker slots`.
- Engine/dispatcher doi ve `prompt slots` truoc khi quyet dinh concurrent submit.

Nghia la he thong da thong nhat don vi:

```text
LP profile cap (worker slots)
-> chia cho output_count
-> ra prompt cap
-> dispatcher reserve theo prompt cap
-> engine spawn/scale foreman theo prompt cap
```

### 6.2. Chan loi ngay tu cua vao

Neu chi sua o `acquire_workers_lp()` thi van chua du, vi:

- Foreman van co the bi spawn qua nhieu.
- Dispatcher van co the reserve qua nhieu task.
- Queue van bi dong nghen va spam retry/reserve.

Ban fix moi chan ngay tu 3 tang:

1. `dispatcher` khong reserve task vuot cap.
2. `engine` khong spawn foreman vuot cap.
3. `engine` khong de `output_count` vuot cap model.

### 6.3. Giam tac dong cua mixed workload

Trong log cua ban co ca:

- T2V LP `output_count=4`
- I2I/NARWHAL `output_count=1`

Truoc kia:

- `typical_output_count` co the bi queue khac keo lech.
- Dynamic scaling co the scale theo task output=1, roi dung cap do de phuc vu task LP.

Sau khi sua:

- Foreman sizing da model-aware hon.
- Quan trong hon, dispatcher van hard-cap tren tung task.

Vay nen ngay ca khi queue mixed, task LP van khong bi reserve vuot prompt cap.

## 7. Hanh vi ky vong sau khi sua

Voi vi du:

- `max_workers = 20`
- `max_workers_lp = 8`
- `output_count = 4`
- model = LP

Thi ky vong:

```text
worker_cap = 8
prompt_cap = floor(8 / 4) = 2
```

Hanh vi mong muon:

- Dispatcher chi cho toi da 2 prompt LP cung luc o trang thai da reserve/running tren account do.
- Engine spawn foremen ban dau xap xi 2, khong phai 5.
- Dynamic scaling khong scale 5 -> 20 cho queue LP nua.
- Log `READY -> RESERVED` se khong tang vuot prompt cap cua LP.

## 8. Verification da thuc hien

Da compile 2 file sau khi patch:

```powershell
python -m py_compile '02 - CLIENT - VEO PRO MAX/core/engine.py' '02 - CLIENT - VEO PRO MAX/core/dispatcher.py'
```

Ket qua:

```text
Exit code: 0
```

## 9. Cach test runtime de xac nhan

De xac nhan bang log khi chay that:

1. Dat `max_workers_lp` nho hon `max_workers`, vi du `8`.
2. Tao queue LP voi `output_count = 4`.
3. Start queue.
4. Theo doi log.

Ban sua duoc xem la dung neu:

- Khong con log kieu:

```text
Spawned CHỦ + 5 Foremen (max_workers=20, output=4, ...)
```

- Khong con log kieu:

```text
Scaling 5 → 20 foremen ...
```

- `READY -> RESERVED` cho LP khong vuot prompt cap mong muon.

## 10. Pham vi bao cao

Worktree hien tai da co nhieu thay doi khac trong cung `engine.py` va `dispatcher.py`. Bao cao nay chi tach va phan tich dung nhung thay doi lien quan den fix:

- LP model worker cap
- prompt concurrency cap
- foreman sizing
- dispatcher reserve cap
- output_count clamp theo model cap

