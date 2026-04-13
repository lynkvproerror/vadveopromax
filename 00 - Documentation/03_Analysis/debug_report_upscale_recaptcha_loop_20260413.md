# Debug Report: Upscale bi vong lap khong vuot qua reCAPTCHA

## 1. Pham vi va du lieu phan tich

- Log dau vao: `D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02 - CLIENT - VEO PRO MAX\logs\dev_logs_20260413_113331.txt`
- Muc tieu: phan tich ly do upscale bi loop recovery/reCAPTCHA, chi ra vi tri code lien quan, nguyen nhan, va huong giai quyet.
- Rang buoc: khong sua source code. Report nay chi phan tich.

## 2. Ket luan ngan gon

Van de khong phai la `submit_upscale` fail reCAPTCHA ngay tu dau. Trong giai doan dau, upscale submit qua Extension van thanh cong nhieu lan voi token hop le 2041-2254 chars.

Loop bat dau sau khi `UpscaleQueue` day do nhieu job song song tren cung 1 account/tab, trong khi cac foreman va warmup/recovery khac cung su dung cung browser/extension state. Sau do tab/extension bat dau suy thoai:

- `check_recaptcha_ready` timeout
- `x-browser-validation` mat hoac khong capture duoc
- reCAPTCHA chi tra ve token ngan 569 chars
- Extension tu dong reload tab lien tuc
- `AccountManager` retry 3s/6s, sau do circuit-breaker backoff
- `RecoveryCoordinator` co the resume queue qua som, khien backlog upscale tiep tuc de ap luc len tab chua recover xong

Co 2 nhom nguyen nhan:

1. Nguyen nhan goc ve van hanh:
- Nhieu upscale jobs pending/concurrent tren cung account/tab lam JS thread/phia extension bi nghen, dan den readiness check, request token, probe headers va submit tranh chap tren cung mot browser state.

2. Nguyen nhan goc ve code:
- `startup_probe()` trong `account_recovery_coordinator.py` van `return True` ngay ca khi `x-browser-validation` van rong sau 5s. Dieu nay cho phep coordinator mo gate va `UpscaleQueue RESUMED` qua som.
- `startup_probe()` dung `bridge.is_recaptcha_ready(email)`, ma method nay chi doc co cache `_recaptcha_readiness`; co nay khong duoc clear trong nhanh `tab_reloading`, nen co rui ro dung trang thai "warm" cu trong luc tab dang reload/recover.

## 3. Trieu chung quan sat trong log

### 3.1. Giai doan he thong con khoe

Log cho thay upscale submit van thanh cong lien tuc:

- Log line 423: `submit_upscale ... HTTP 200 (token 2190 chars)`
- Log line 497: `submit_upscale ... HTTP 200 (token 2041 chars)`
- Log line 555: `submit_upscale ... HTTP 200 (token 2233 chars)`
- Log line 579: `submit_upscale ... HTTP 200 (token 2190 chars)`
- Log line 941: `submit_upscale ... HTTP 200 (token 2190 chars)`
- Log line 1042: `submit_upscale ... HTTP 200 (token 2169 chars)`
- Log line 1159: `submit_upscale ... HTTP 200 (token 2169 chars)`
- Log line 1523: `submit_upscale ... HTTP 200 (token 2190 chars)`
- Log line 1918: `submit_upscale ... HTTP 200 (token 2190 chars)`
- Log line 2351: `submit_upscale ... HTTP 200 (token 2190 chars)`

=> Nghia la pipeline upscale ban dau van di qua reCAPTCHA duoc.

### 3.2. Diu hang do vao 1 account/tab

So luong job active tang dan:

- Log line 333: `active=1, limit=4`
- Log line 396: `active=2, limit=4`
- Log line 484: `active=4, limit=4`
- Log line 1002-1003: `active=4, limit=5` va `active=5, limit=5`
- Log line 1500-1501: `active=5, limit=6` va `active=6, limit=6`
- Log line 1896-1897: `active=6, limit=7` va `active=7, limit=7`
- Log line 2235-2236: `active=7, limit=8` va `active=8, limit=8`

Dong thoi co nhieu warmup dang cho:

- Log line 1015-1016: 2 job cung `waiting 15s for reCAPTCHA trust score`
- Log line 1508-1509: 2 job cung warmup 15s
- Log line 1904-1905: 2 job cung warmup 15s
- Log line 2243-2244: 2 job cung warmup 15s

=> Cung 1 account/tab dang bi nhieu luong upscale va recovery cung tac dong.

### 3.3. Dau hieu reCAPTCHA/recovery bat dau tranh chap

- Log line 1005, 1007, 1054, 1504, 1596, 1900, 1978, 2288, 2691:
  `reCAPTCHA recovery already in progress by another foreman — waiting for lock...`

=> Khong chi UpscaleQueue, ma cac foreman cua engine cung dang tranh chap cung mot recovery path.

### 3.4. Mat `x-browser-validation` va readiness timeout

Moc hu hong ro nhat bat dau tu khoang 11:09:45:

- Log line 2662-2663:
  `probe_browser_headers ... took 10.0s`
  `x-browser-validation NOT captured — API requests may get 403`

Sau do tiep tuc lap lai:

- Log line 2735-2736
- Log line 2849-2850
- Log line 3064-3065
- Log line 3290-3291
- Log line 3363-3364
- Log line 3429-3430
- Log line 3450-3451
- Log line 3528-3529
- Log line 3539-3540

Dong thoi `check_recaptcha_ready` timeout:

- Log line 2696: timeout 5s
- Log line 2712: timeout 5s
- Log line 2816: timeout 8s
- Log line 3440: timeout 20s
- Log line 3455: timeout 20s
- Log line 3518: timeout 20s

=> Browser tab/extension khong con dap ung on dinh cho readiness check va header probe.

### 3.5. Coordinator pause queue nhung resume rat som

Log line 2818-2834:

- 2818: `reCAPTCHA still not ready after reload + 25s wait + 3 verify attempts`
- 2819: foreman escalate hard recovery
- 2824-2825: `pending=12 jobs frozen`, `UpscaleQueue PAUSED`
- 2833-2834: `UpscaleQueue RESUMED`, `State → HEALTHY`
- 2838-2840: ngay sau do `request_recaptcha` van fail timeout va `Extension bridge returned no reCAPTCHA token`

=> Recovery vua resume queue xong thi token van fail ngay lap tuc. Day la dau hieu resume som hon trang thai that cua tab.

### 3.6. reCAPTCHA roi vao vong lap token ngan 569 chars

Sau giai doan recovery, log lap lai cung mot mau:

- Log line 3003, 3037, 3040, 3316, 3379, 3505, 3566:
  `grecaptcha NOT ready ... tokenLen=569`

- Log line 3037, 3042, 3046
- Log line 3341, 3345, 3349
- Log line 3413, 3417, 3432
- Log line 3501, 3507, 3511
- Log line 3579, 3582, 3587
  `Token too short (569 chars, need ≥1500)`

- Log line 3045, 3348, 3420, 3510, 3586:
  `Tab reloading ... reason: short-token-threshold`

- Log line 3443, 3458, 3521:
  `Tab reloading ... reason: recaptcha-check-timeout`

- Log line 3039, 3044, 3343, 3347, 3415, 3419, 3503, 3509, 3581, 3584:
  `Retrying reCAPTCHA in 3s/6s...`

- Log line 3051:
  `reCAPTCHA circuit-breaker: 5 consecutive failures → backing off 120s`

=> He thong roi vao mot loop: token ngan -> reload -> van token ngan -> retry -> timeout -> reload tiep.

## 4. Phan tich code lien quan

### 4.1. `UpscaleQueue` tang concurrency tren cung account/tab

File:
[upscale_queue.py](D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py)

Doan code:

- Line 879-888: tao `asyncio.create_task(self._process_job_tracked(job))` va log `launched job ... (active=..., limit=...)`
- Line 1222-1232: moi job deu `simulate_activity()` roi `await asyncio.sleep(warmup_wait)`
- Line 1399-1401 va 2146-2148: moi job deu goi `ext_bridge.submit_upscale(...)`

Y nghia:

- Job upscale cua cung 1 account duoc chay song song.
- Moi job deu warmup, doi trust score, submit, poll.
- Khi active jobs tang den 5, 6, 7, 8, toan bo van dua vao cung `extension_bridge`, cung browser tab, cung reCAPTCHA/widget state.

Day la nguyen nhan van hanh chinh gay nghen va lam quality cua state giam dan.

### 4.2. `engine.py` co lock recovery, nhung chi giam tranh chap giua foreman, khong giam tai tu UpscaleQueue

File:
[engine.py](D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py)

Doan code:

- Line 9039-9057: lock `self._recaptcha_recovery_locks[email]`
- Line 9043-9044: log `reCAPTCHA recovery already in progress ... waiting for lock`
- Line 9097: `bridge.check_recaptcha_ready(..., timeout=5.0)`
- Line 9147-9150: sau khi qua max wait thi trigger full reload
- Line 9219-9235: escalate sang `RecoveryCoordinator`

Y nghia:

- Lock nay chi serialize recovery giua cac foreman.
- Nhung `UpscaleQueue` van tiep tuc giu backlog/pending jobs, warmup, submit va poll trong cung account.
- Nhu vay tai tren tab khong duoc giam thuc su; no chi doi recovery xong roi lai tiep tuc day len.

### 4.3. `ExtensionBridge` cho thay ro he thong dang bi kiet state, khong chi fail API

File:
[extension_bridge.py](D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py)

Doan code quan trong:

- Line 1317-1322: `submit_upscale()` co lock per-account, nhung van su dung cung 1 browser/extension state
- Line 1367-1385: `submit_upscale` log token length
- Line 1643-1745: `check_recaptcha_ready()`
- Line 1705-1710: neu trial token ngan thi ep `NOT ready`
- Line 1740-1744: timeout => coi nhu false
- Line 1949-1958: `probe_browser_headers()` co the tra `x-browser-validation NOT captured`
- Line 2301-2312: `tab_reloading` chi set grace period, khong xoa ngay readiness cache
- Line 920-950 va 957-975: `request_recaptcha()` coi token ngan la fail va den threshold thi de Extension auto-reload tab
- Line 3108-3110: `is_recaptcha_ready()` chi doc co cache `_recaptcha_readiness`

Y nghia:

- Code da co nhieu guard de chong token ngan va timeout.
- Tuy nhien khi tab da roi vao state xau, cac guard nay chu yeu phat hien va reload, khong cat duoc vong lap backlog/recovery.

### 4.4. `AccountManager` tiep tuc retry va backoff, nhung van la loop o cap token

File:
[account_manager.py](D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/account_manager.py)

Doan code:

- Line 483-502: toi da 3 attempts, retry 3s/6s
- Line 504-509: neu that bai thi tang `consecutive_failures`
- Line 439-448: circuit-breaker backoff 30s -> 60s -> 120s

Y nghia:

- Day khong phai sua duoc state xau; no chi lam giam tan suat retry.
- Khi UQ va engine van con backlog/cac luong recovery, account manager van tiep tuc gap token ngan hoac timeout.

### 4.5. Loi code nghiem trong trong `RecoveryCoordinator.startup_probe()`

File:
[account_recovery_coordinator.py](D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/account_recovery_coordinator.py)

Doan code:

- Line 537-544: probe check `bridge.is_recaptcha_ready(email)`; neu false thi doi 3s roi check lai
- Line 546-566: kiem tra `x-browser-validation`; neu rong thi doi them 5s
- Line 568-572: comment `Not a hard failure — header may arrive later`, sau do `return True`
- Line 381-398: neu probe khong bi fail, coordinator mo gate, unpause UQ, va set state `HEALTHY`

Day la diem loi code ro rang nhat trong flow recovery:

- Ngay ca khi `x-browser-validation` van rong sau 5s, `startup_probe()` van pass.
- `bridge.is_recaptcha_ready(email)` o day chi la check co cache, khong phai mot lan goi `check_recaptcha_ready()` that su toi Extension.
- Vi vay coordinator co the ket luan account "HEALTHY" du tab van chua co header dung hoac reCAPTCHA van chua thuc su on dinh.

Log thuc te khop voi dieu nay:

- Log line 2824-2834: queue bi pause, sau do resume va set `HEALTHY` trong cung giay
- Log line 2838-2840: ngay lap tuc `request_recaptcha` fail timeout
- Log line 2849-2850: `x-browser-validation NOT captured`

=> Day la mot bang chung manh rang recovery dang resume qua som.

### 4.6. Rui ro bo sung: readiness cache co the bi stale trong luc tab dang reload

File:
[extension_bridge.py](D:/Music/Ruby/Produce%20for%20Customer/##Tools/VEO%20Tool/%23NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/extension_bridge.py)

Doan code:

- Line 2278-2283: `_recaptcha_readiness[email] = ready` khi nhan `recaptcha_warmth`
- Line 2236-2255: readiness chi duoc clear tren `tab_closed`
- Line 2301-2312: tren `tab_reloading` khong clear `_recaptcha_readiness`
- Line 3108-3110: `is_recaptcha_ready()` doc truc tiep cache nay

Danh gia:

- Day la contributing factor "rat co kha nang", khong phai bang chung duy nhat.
- Neu tab dang reload ma co readiness cache cu = `True`, `startup_probe()` co the dua vao co cu de pass qua buoc reCAPTCHA.
- Dac biet nguy hiem vi sau do `startup_probe()` lai khong fail cung khi `x-browser-validation` van rong.

## 5. Chuoi nguyen nhan day du

1. Upscale backlog tang dan va duoc chay song song qua nhieu job tren cung account/tab.
2. Moi job deu warmup, submit, poll, trong khi engine foreman cung check/recover reCAPTCHA.
3. Browser/extension state bat dau cham:
- `probe_browser_headers` cham
- `check_recaptcha_ready` timeout
- `x-browser-validation` mat
4. reCAPTCHA widget roi vao state xau, tra ve token ngan 569 chars.
5. Extension auto reload tab vi `short-token-threshold` va `recaptcha-check-timeout`.
6. `AccountManager` retry 3s/6s, sau do backoff, nhung backlog upscale van con.
7. `RecoveryCoordinator` pause queue, nhung co the resume som vi `startup_probe()` qua de dat:
- dung readiness cache
- khong fail cung khi `x-browser-validation` van rong
8. Queue resume khi tab chua khoe, backlog tiep tuc day ap luc, loop lap lai.

## 6. Diem loi can xem la "confirmed" va "likely"

### 6.1. Confirmed

1. `startup_probe()` van `return True` du `x-browser-validation` van rong.
- Code: `account_recovery_coordinator.py:546-572`
- Log ho tro: `UpscaleQueue RESUMED` / `State → HEALTHY` tai line 2833-2834, nhung ngay sau do token van fail va header van missing.

2. Upscale queue dang chay concurrency cao tren cung account.
- Code: `upscale_queue.py:879-888`, `1219-1232`, `1399-1401`
- Log ho tro: `active=5..8`, nhieu warmup 15s song song.

3. reCAPTCHA sau do tra token ngan 569 chars va loop reload.
- Code: `extension_bridge.py:920-950`, `1643-1745`
- Log ho tro: 3037-3047, 3341-3350, 3413-3433, 3501-3512, 3579-3588.

### 6.2. Likely / inference manh

1. Readiness cache `_recaptcha_readiness` co the stale trong giai doan `tab_reloading`.
- Code: `extension_bridge.py:2278-2283`, `2301-2312`, `3108-3110`
- Ly do: `tab_reloading` khong clear readiness cache; `startup_probe()` lai dung `is_recaptcha_ready()`.

2. Extension/browser JS thread bi nghen do nhieu warmup/recovery/submit/poll cung 1 tab.
- Ho tro manh tu log `check_recaptcha_ready TIMEOUT`, `probe_browser_headers` cham, active jobs tang dan, pending jobs frozen=12.

## 7. Huong giai quyet de xuat (khong ap dung trong lan debug nay)

### 7.1. Sua recovery gate

- Bat `startup_probe()` fail khi `x-browser-validation` van rong sau khoang doi.
- Khong `return True` theo comment "header may arrive later" neu recovery vua hard-recover xong ma header van mat.
- Sau recovery, thay vi chi doc `is_recaptcha_ready()`, bat goi `await check_recaptcha_ready()` that voi timeout hop ly roi moi cho resume.

### 7.2. Clear readiness state dung luc

- Clear `_recaptcha_readiness[email]` khi nhan `tab_reloading`.
- Clear readiness khi gap `short-token-threshold` hoac `check_recaptcha_ready TIMEOUT`, tranh dung co "warm" cu.

### 7.3. Giam tai tren 1 account trong luc recovery

- Khi account dang recover hoac vua recover xong, han che `UpscaleQueue` launch them jobs moi.
- Khong resume UQ neu pending backlog lon ma readiness/header chua du dieu kien.
- Co the can them backpressure khi active jobs tren cung account da dat nguong nhay cam.

### 7.4. Tach dieu kien "tab connected" va "tab healthy"

- Extension reconnect khong co nghia la reCAPTCHA da khoe.
- Khong nen coi `Extension connected` + `access token refreshed` la du de mo queue neu `x-browser-validation` va reCAPTCHA trial token chua dat chuan.

## 8. Danh gia cuoi cung

Neu chi nhin log, bieu hien ben ngoai la "upscale bi loop reCAPTCHA". Nhung khi ghep log va code lai, ban chat van de la:

- 1 account/tab bi dồn qua nhieu upscale jobs song song
- recovery duoc trigger dung, nhung co logic resume qua som
- sau khi resume, backlog tiep tuc day len tab dang chua recover hoan toan
- he thong roi vao loop token ngan 569 chars + reload + retry + timeout

Noi cach khac, day la bai toan ket hop giua:

- pressure/concurrency tren cung browser state
- recovery probe qua de
- readiness cache co kha nang stale

## 9. Trang thai thao tac

- Da tao report debug nay.
- Khong sua bat ky file source code nao trong lan phan tich nay.
