# Image Upscale Queue Concurrency Report

Ngay phan tich: 2026-04-12
Log doi chieu: `logs/dev_logs_20260412_093652.txt`

## Ket luan ngan

Van de khong phai la `UpscaleQueue` chi tao duoc 1 image job. Trong log, queue van launch duoc toi `4` image jobs cung luc. Van de that su la:

1. Image upscale API per-account bi khoa cung o `Semaphore(1)`.
2. Permit do bi giu trong toan bo vong doi cua moi image attempt, bao gom wait bridge, wait reCAPTCHA, submit, timeout, retry, va sleep backoff.
3. Vi vay, nhin tu runtime se thay co nhieu `active jobs`, nhung chi co `1` image upscale request thuc su dang chay tai 1 thoi diem.
4. Nhanh image khong feed ket qua vao `AdaptiveJobController`, nen khong co co che tang/giam "thong minh" nhu nhanh video.

Noi gon: image upscale hien tai la `multi-job queue + single-lane submit`.

## Bang chung tu log

### 1. Queue launch duoc nhieu image jobs

Trong log co day du dau vet queue mo rong so job active:

- `09:31:49`: `launched job ... (active=1, limit=4, burst=0/2)`
- `09:32:16`: `launched job ... (active=2, limit=4, burst=0/2)`
- `09:32:20`: `launched job ... (active=3, limit=4, burst=0/2)`
- `09:32:44`: `launched job ... (active=4, limit=4, burst=0/2)`

Nhung ngay sau cac moc `active=2/3/4`, khong co them nhieu dong `upscaling mediaId=...` xuat hien song song.

### 2. Thuc te chi co 1 image upscale request chay tai 1 thoi diem

Chuoi log cho thay pattern serialize rat ro:

- `09:31:49`: job dau tien bat dau `upscaling mediaId=21a12464...`
- `09:33:54`: job nay `timeout (attempt 1/3)`
- `09:33:59`: van chinh job nay retry `attempt 2`
- `09:34:40`: job nay moi thanh cong, va chi luc do job tiep theo moi bat dau `upscaling mediaId=cff8cd42...`
- `09:35:50`: job tiep theo xong, roi moi den `mediaId=3d48a032...`
- `09:36:00`: job tiep theo xong, roi moi den `mediaId=d8eed02f...`
- `09:36:16`: roi moi den `mediaId=7234b83f...`
- `09:36:32`: roi moi den `mediaId=a80681c4...`
- `09:36:47`: roi moi den `mediaId=0a74ee48...`

Nghia la queue van giu 4 job "active", nhung lane submit thuc te chi co 1.

### 3. Moi image task enqueue vao queue chi mang 1 image

Trong log:

- `Task ...: enqueued 1 images to UpscaleQueue`
- `UpscaleQ-Image] Task ...: 1 images -> 2k`

Trong run nay, moi image upscale job deu la `1 image / 1 job`. Khi ket hop voi `Semaphore(1)`, thong luong thuc te se thanh `1 request/account`.

## Nguyen nhan trong code

### A. Image path tu tao semaphore rieng va hardcode = 1

Trong [upscale_queue.py:2739](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2739):

```python
if job.account_email not in self._upscale_api_sems:
    self._upscale_api_sems[job.account_email] = asyncio.Semaphore(1)
```

Day la khac biet lon nhat giua image va video.

Nhanh video duoc DI vao `semaphore_fn=self._get_upscale_api_semaphore` tu engine, trong khi engine set per-account upscale semaphore = `3` o [engine.py:1145](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L1145).

Nhanh image khong tai su dung semaphore nay. No tu mo mot lane rieng va khoa cung thanh `1`.

### B. Semaphore cua image bi giu qua nhieu doan viec

Trong [upscale_queue.py:2966](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2966):

```python
async with upscale_sem:
    return await _upscale_single(i)
```

Van de la `_upscale_single()` khong chi submit API. No bao tron:

- wait cooldown o [upscale_queue.py:2769](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2769)
- wait bridge connect o [upscale_queue.py:2777](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2777)
- wait reCAPTCHA warm-up o [upscale_queue.py:2796](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2796)
- `submit_prompt()` o [upscale_queue.py:2836](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2836)
- sleep khi 403/429/timeout/error o [upscale_queue.py:2917](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2917), [upscale_queue.py:2932](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2932), [upscale_queue.py:2942](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2942)

Nghia la chi can 1 image bi timeout hay backoff, no se giu lane duy nhat va chan tat ca image jobs con lai.

### C. Image job co "active=4" nhung day chi la queue-level, khong phai API-level

Worker loop launch toi `max_jobs` o [upscale_queue.py:747](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L747) va log `active={len(active_jobs)}, limit={max_jobs}` o [upscale_queue.py:791](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L791).

Nhung voi image path:

- `active_jobs` = so coroutine dang ton tai
- khong phai so `UPSCALE_IMAGE` request dang in-flight

Do do log `active=4, limit=4` rat de gay hieu nham. 4 job da duoc spawn, nhung 3 trong so do chi dang xep hang cho permit duy nhat.

### D. Image path khong su dung AIMD outcome feedback nhu video

`AdaptiveJobController` duoc dinh nghia o [upscale_queue.py:128](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L128) va worker loop doc `max_jobs` tu no o [upscale_queue.py:749](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L749).

Nhanh video co goi `_apply_job_outcome(...)` o [upscale_queue.py:2353](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2353) va [upscale_queue.py:2395](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2395), nen limit co the tang/giam theo ket qua that.

Nhanh image ket thuc o [upscale_queue.py:2973](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2973) den [upscale_queue.py:3001](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L3001) nhung khong call `_apply_job_outcome`.

He qua:

- limit job cho image khong hoc theo thanh cong/that bai
- log `limit=4` la gia tri khoi tao, khong phai gia tri "thong minh" da duoc dieu chinh

### E. Nhanh image khong co adaptive burst tuong duong video

Nhanh video co `AdaptiveBurstController` cho poll o [upscale_queue.py:33](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L33) va su dung trong phase poll o [upscale_queue.py:1927](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L1927).

Nhanh image la synchronous submit -> decode -> save, nen khong co poll burst. Khi ket hop voi `Semaphore(1)`, no thanh lane don hoan toan.

### F. Comment hien tai gay hieu nham

O [upscale_queue.py:2957](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2957) co comment:

```python
# Launch all upscales concurrently (semaphore limits to 4)
```

Nhung semaphore thuc te dang la `1` o [upscale_queue.py:2742](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2742).

Comment nay khong con dung va rat de dan den nhan dinh sai khi debug.

## Vi sao video "co ve thong minh hon"

Ghi chu: log `dev_logs_20260412_093652.txt` chu yeu cho thay image upscale runtime. Phan so sanh voi video duoc suy ra tu code path cua `upscale_queue.py` va `engine.py`, khong phai tu chinh log runtime nay.

Can tach 2 lop:

### 1. Job concurrency

Video queue thuc te co co che job-level AIMD:

- bat dau tu `INITIAL = 4`
- co the scale up/down o [upscale_queue.py:128](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L128)
- duoc cap nhat boi `_apply_job_outcome()`

### 2. Poll concurrency

Video queue con co them adaptive burst cho phase poll:

- `2 -> 4 -> 6 -> 8`
- scale up/down theo success/failure

Nen video co 2 tang dieu tiet concurrency, con image hien tai khong co tang nao thuc su active quanh `UPSCALE_IMAGE` submit.

## Tom tat ban chat van de

Van de khong phai:

- queue worker khong launch du job
- hay image upscale bi mat queue

Van de la:

- image path dang "gia lap" nhieu active jobs
- nhung lane submit thuc su bi ep ve 1
- lane do lai bi giu qua ca timeout va backoff

Do do throughput thuc te cua image upscale khong phu thuoc vao `active=4`, ma phu thuoc vao `1 permit` duy nhat.

## Huong dieu chinh nen can nhac

Khong sua code trong bao cao nay. Day la huong dieu chinh nen can nhac de image upscale co hanh vi gan video hon.

### P1. Tach "job concurrency" va "submit concurrency" cho image

Hien tai 2 khai niem nay dang bi tron vao nhau.

Nen co:

- `job concurrency`: bao nhieu image jobs duoc active trong queue
- `image submit concurrency`: bao nhieu `UPSCALE_IMAGE` request thuc su duoc phep in-flight/account

Neu khong tach 2 lop nay, `active=4` se tiep tuc la chi so gay nhieu hieu nham.

### P2. Khong giu submit semaphore trong toan bo retry loop

Permit chi nen duoc nam quanh doan submit that su, khong nen om ca:

- wait bridge
- wait reCAPTCHA
- timeout handling
- 403/429 sleep
- generic retry sleep

Neu van giu permit qua ca sleep, chi can 1 image loi la se dong bang toan bo image upscale queue cho account do.

### P3. Bo hardcoded `Semaphore(1)` va dung controller co the dieu chinh

Co 2 huong hop ly:

- tai su dung `self._semaphore_fn(account.email)` de dong bo tu duy voi video
- hoac tao `image_upscale_submit_controller` rieng, co `min/start/max` va AIMD rieng cho image

Khong nen nhay thang tu `1 -> 4` cung. Image upscale van dung reCAPTCHA va cung co nguy co 429, nen can tang dan.

### P4. Feed image jobs vao `_apply_job_outcome()`

Neu muon queue "thong minh", image job phai bao ket qua vao `AdaptiveJobController`, giong video.

Neu khong:

- limit se mai dung o gia tri khoi tao
- khong co scale down khi xuat hien 403/429/timeout
- khong co scale up khi lane on dinh

### P5. Them metric/observability dung ban chat

Nen co them:

- `active_image_jobs`
- `image_submit_inflight`
- `image_submit_waiting`
- `image_submit_limit`
- `time_waiting_for_image_submit_sem`

Neu khong, log `active=4` se tiep tuc trong co ve "dang upscale 4 cai", trong khi thuc te chi co 1 submit lane.

### P6. Sua comment va status de tranh debug sai

Can dong bo:

- comment o [upscale_queue.py:2957](/D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2957)
- status/log thong bao `active jobs` vs `actual submit inflight`

## Danh gia cuoi

Tu log `dev_logs_20260412_093652.txt` va code hien tai, co the ket luan chac chan:

1. Image upscale queue khong bi ket o muc queue spawning.
2. Van de nam o lane submit per-account bi khoa `1`.
3. Lane do bi giu qua toan bo retry/backoff lifecycle.
4. Nhanh image chua tham gia vao co che adaptive concurrency nhu video.

Do do hanh vi hien tai cua image upscale la:

- be ngoai: `active jobs` co the la `4`
- thuc te: `1 UPSCALE_IMAGE request/account` tai mot thoi diem

Neu muc tieu la de image upscale "tang/giam trong khoang so luong toi da mot cach thong minh" nhu video, thi diem dau tien phai doi khong phai la queue worker, ma la cach quan ly `submit lane` cua nhanh image.
