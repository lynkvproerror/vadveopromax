# Phan Tich `3/12` So Voi Anh UI

## Ket luan ngan

`3/12` khong phai la bang chung chac chan rang counter dang sai khi doi chieu voi anh ban gui.

Theo code hien tai, `3/12` dang duoc render voi y nghia:

- `3` = so `LP slots held`
- `12` = `LP cap` hieu luc

No **khong** phai:

- so row dang hien thi khong `READY`
- so prompt dang thay tren man hinh
- so output boxes dang sang mau
- tong so `4 x 3 = 12` operation workers vua duoc submit

Vi vay, neu chi nhin anh roi ket luan `3/12` "sai" thi chua du co so. Dieu dung hon la: metric nay **rat de bi hieu sai** so voi cach UI dang trinh bay task.

## Code Dang Hien Thi Gi

Status bar o UI lay gia tri `active_workers_lp` va `eff_capacity_lp`, roi render thanh:

- `🐢 {active_lp}/{cap_lp}`

Bang chung:

- [app.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/app.py:819>) ghi chu `Workers: per-pool slot counts from telemetry contract`
- [app.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/app.py:826>) doc `active_workers_lp`
- [app.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/app.py:876>) tooltip ghi ro `LP slots held / LP cap`
- [app.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/app.py:882>) tooltip ghi `Slots held ≠ visible prompts.`
- [app.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/ui/app.py:883>) tooltip ghi `Tasks release most slots after submit, keeping 1 pipeline slot.`

Backend summary cung tra ve dung cap nay:

- [app_controller.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py:5590>) mo ta `active_workers_lp` la `LP ops slots held`
- [app_controller.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py:5609>) tra `active_workers_lp`
- [app_controller.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/app_controller.py:5614>) tra `eff_capacity_lp`

Gia tri `active_workers_lp` duoc cong tu session:

- [multi_account.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/multi_account.py:99>) `total_active_lp`
- [session.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/session.py:90>) `active_workers_lp`
- [session.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/session.py:154>) `effective_lp_capacity`
- [session.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/session.py:162>) LP cap = `min(max_workers_lp, total_remaining)`

## Tai Sao `3/12` Van Co The Dung Theo Semantics Hien Tai

Log ban gui cho thay:

- `10:59:16`: `Spawned CHỦ + 3 Foremen (worker_cap=12, output=4, ...)`
- Moi task LP luc submit se fan-out thanh `4 ops`
- Nhung engine **khong giu ca 4 slot do trong suot pipeline**

Doan code quan trong:

- [engine.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py:4192>) acquire `1` LP slot ban dau
- [engine.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py:4292>) acquire them `extra = output_count - 1`
- [engine.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py:4427>) sau submit: `free extra slots, keep 1 as pipeline slot`
- [engine.py](</D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py:5472>) lap lai logic `keep 1 slot, release the rest`

Nghia la:

1. Task LP co the tam thoi can `4` worker slots de submit 4 outputs.
2. Ngay sau khi submit xong, engine nha `3` slot.
3. Task chi giu lai `1 pipeline slot` trong giai doan poll/download/finalize.

Vi the, `3/12` khong co nghia la "chi co 3 output workers dang ton tai".
No co nghia la "co 3 LP pipelines dang giu slot".

## Doi Chieu Truc Tiep Voi Anh Ban Gui

Anh cho thay:

- 1 row `Generation complete`
- 1 row `Submitting 1 upscales.`
- 1 row `Processing`
- 1 row `Waiting (6s)`
- cac row con lai `READY`

Day la ly do khong nen doc `3/12` theo "dem so row khong READY":

- row `Generation complete` van con hien tren queue, nhung co the da roi khoi LP generation pool va da handoff sang upscale/finalizer
- row `Submitting 1 upscales.` co the dang dung upscale capacity, khong con chiem du `4` LP generation slots nhu luc moi submit
- row `Processing` va row `Waiting (6s)` nhieu kha nang van dang giu `pipeline slot`

Anh bottom bar ban gui thuc ra rat hop logic voi semantics nay:

- `⚡ 0/20`
- `🐢 3/12`
- `⬆️ 4/8`
- `Σ 7`

So hoc o day rat hop:

- `0` fast slots
- `3` LP pipeline slots
- `4` upscale slots
- tong `Σ = 7`

Neu `3/12` thuc su "sai theo anh", thong thuong ta se thay `Σ` khong khop. Nhung trong anh, `3 + 4 = 7` lai khop hoan toan.

## Diem Gay Nham Lan Thuc Su

Van de khong nam o viec `3/12` chac chan sai, ma o cho:

- UI hang task la `task-centric`
- cac o thumbnail la `output-centric`
- status bar duoi cung lai la `slot-centric`

Ba lop nay dang dung ba don vi khac nhau.

Nen nguoi dung rat de doc nham:

- thay 4 row dang co chuyen dong -> nghi counter phai la `4/x`
- thay moi row co 4 o -> nghi counter phai la `12/12`
- thay `3/12` -> nghi app dang tinh thieu

Trong khi code hien tai dang muon bieu dien:

- bao nhieu LP pipelines con giu slot sau khi da nha bớt worker outputs

## Cach Phat Bieu Chinh Xac Hon

Thay vi noi:

- "`3/12` khong chinh xac so voi anh"

Nen noi:

- "Tu anh alone, khong du co so ket luan `3/12` sai."
- "`3/12` dang dung theo nghia `LP slots held / LP cap`, nhung nghia nay de bi hieu nham khi dat canh queue rows va output boxes."
- "Neu intent san pham la hien thi so prompt/output dang thay tren UI, thi metric hien tai sai don vi, khong phai nhat thiet sai counter."

## Ket Luan Cuoi

Voi code hien tai, `3/12` co kha nang **dung theo telemetry contract**, va anh ban gui khong phu dinh duoc dieu do.

Thu can sua trong tu duy phan tich la:

- khong dong nhat `LP slots held` voi `visible active rows`
- khong dong nhat `LP slots held` voi `4-output fan-out workers`

Noi ngan gon:

- `3/12` khong chung minh bug arithmetic
- no chung minh UI/wording rat de gay nham ve semantics

