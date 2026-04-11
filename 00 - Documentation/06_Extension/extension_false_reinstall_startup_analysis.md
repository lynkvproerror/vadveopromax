# Extension False Reinstall During Startup

**Date**: 2026-04-11  
**Severity**: P1  
**Scope**: Phan tich ly do app tu cai dat lai extension du extension da `registered`

---

## 1. Executive Summary

App cai dat lai extension khong phai vi extension "that su chua ton tai", ma vi logic kiem tra hien tai chi tin vao **CDP target cua MV3 service worker/background page**.  

Trong startup race, extension co the:

1. Da `register` qua `content_script` va WebSocket bridge
2. Nhung van **chua xuat hien** duoi dang target `service_worker` trong `http://127.0.0.1:{port}/json`
3. Hoac service worker da bi suspend dung luc `install_if_needed()` check

Khi do `install_if_needed()` ket luan sai la extension "not loaded" va di vao nhanh reinstall.

Ket luan ngan gon:

- `Extension registered` != `install_if_needed() se coi la loaded`
- Reinstall trong log la **false negative cua CDP-based extension detection trong luc startup**, khong phai bang chung chac chan rang extension da bi mat

---

## 2. Log Duoc Phan Tich

```text
[INFO ] 11:33:27 - core.extension_bridge - [ExtensionBridge] 📧 Extension registered: levanlinh.kma@gmail.com (v2.3.14, src=content_script, tabId=1860496487)
[INFO ] 11:33:27 - veo - [Status] Extension connected for levanlinh.kma@gmail.com
[WARNING] 11:33:29 - core.profiles_controller - [DEBUG] Step 4: ✅ Already on /tools/flow — skipping navigation
[INFO ] 11:33:29 - core.account_manager - [levanlinh.kma@gmail.com] Debug browser still launching (stage=starting, elapsed=0.0s) — continuing extension-only for now
[INFO ] 11:33:29 - core.account_manager - [malgorzataultra642094@imqg.dohaticammo.asia] ⏳ Debug browser launching (stage=starting)...
[INFO ] 11:33:29 - core.extension_manager - [ExtMgr] Extension not loaded after retries — reinstalling (will remove stale if any)...
[INFO ] 11:33:29 - core.extension_manager - [ExtMgr] 🔄 Reinstalling extension...
```

---

## 3. Trigger Chinh Xac Cua Reinstall

Reinstall xay ra tai:

- `02 - CLIENT - VEO PRO MAX/core/extension_manager.py`
- Ham `install_if_needed(port, extension_dir)`

Logic:

1. Goi `is_extension_loaded(port)`
2. Neu `False`, doi them 3 lan, moi lan 2 giay
3. Neu van `False`, log:
   - `[ExtMgr] Extension not loaded after retries — reinstalling (will remove stale if any)...`
4. Sau do goi `reinstall_extension(...)`

Dieu nay co nghia:

- Log reinstall trong snippet **khong phai** do version mismatch
- Khong phai do bridge mat ket noi
- Khong phai do content script bao loi
- No xay ra vi **CDP check khong tim thay extension target**

---

## 4. Vi Sao Da `registered` Roi Van Bi Reinstall

### 4.1. Hai he thong dang kiem tra hai dau hieu khac nhau

#### A. Extension bridge xem extension "song" khi nao

Bridge coi extension da ket noi khi background/content script da mo WebSocket va gui `register`.

Log nay:

```text
Extension registered: ... (src=content_script, tabId=1860496487)
```

chi chung minh:

- Content script dang chay tren tab
- Background da noi ve app
- Bridge da nhan duoc registration

No **khong chung minh** rang CDP dang nhin thay service worker target.

#### B. Extension installer xem extension "loaded" khi nao

`is_extension_loaded(port)` trong:

- `02 - CLIENT - VEO PRO MAX/core/extension_manager.py`

chi tra `True` khi trong `/json` co target:

- URL la `chrome-extension://...`
- target type la `service_worker` hoac `background_page`
- va khop extension cua app

Noi cach khac:

- Neu chi co `content_script` dang hoat dong
- Hoac MV3 service worker chua xuat hien / da suspend
- Thi installer van ket luan `not loaded`

### 4.2. Startup race lam hai dau hieu nay lech nhau

Ngay trong snippet, ca hai browser dang o trang thai:

- `still launching (stage=starting)`
- `launching (stage=starting)`

Day la dau hieu rat ro rang cho thay:

- Browser lifecycle chua on dinh
- Extension lifecycle va CDP lifecycle chua dong bo

Do do truong hop sau la hoan toan co the xay ra:

1. Content script da co mat tren tab Flow
2. Extension da `register` vao bridge
3. Nhung MV3 service worker target chua kip xuat hien trong CDP
4. `install_if_needed()` check trung thoi diem nay
5. Ket qua la false negative -> reinstall

---

## 5. Chuoi Su Kien Kha Di Nhat

### 11:33:27

`levanlinh.kma@gmail.com` da `registered` qua:

- `src=content_script`
- `tabId=1860496487`

Dieu nay cho thay profile/tab cua account nay da co content script va bridge dang song.

### 11:33:29

He thong van dang startup song song:

- `levanlinh...` van `still launching`
- `malgorzata...` van `launching`

Tuc la co nhieu luong/browser dang chay cung luc.

### 11:33:29

Mot caller nao do goi `install_if_needed()` tren mot port dang startup.

Tai thoi diem check:

- `is_extension_loaded(port)` tra `False`
- Sau retry van `False`
- App reinstall

---

## 6. Caller Nao Nhieu Kha Nang Gay Ra

Co 4 nhom caller quan trong:

### 6.1. `chrome_manager.launch_chrome()` - launch moi

File:

- `02 - CLIENT - VEO PRO MAX/core/chrome_manager.py`

Voi Branded Chrome:

- Sau khi CDP ready, ham nay log:
  - `Branded Chrome — installing extension NOW...`
- Sau do goi `install_if_needed(...)`

Day la caller **khong bridge-aware**.

Neu browser vua launch xong nhung MV3 service worker chua hien trong `/json`, no co the reinstall ngay.

### 6.2. `chrome_manager.launch_or_reconnect()` - reconnect

File:

- `02 - CLIENT - VEO PRO MAX/core/chrome_manager.py`

Khi reconnect:

1. Ham goi `reconnect_chrome(profile_path)`
2. Neu thay Chrome cu van song
3. No check `is_extension_loaded(port)`
4. Neu `False`, voi Branded Chrome no auto-install lai

Day la caller **khong bridge-aware** va rat de false-negative trong startup/reconnect.

### 6.3. `profiles_controller.open_browser_for_debug()` - reconnect path Step 1b

File:

- `02 - CLIENT - VEO PRO MAX/core/profiles_controller.py`

Trong reconnect path:

- `Step 1b: Extension install`
- goi `install_if_needed(cdp_port, ...)`

Day cung la caller **khong bridge-aware**.

### 6.4. `app_controller.ensure_all_extensions()` - batch check

File:

- `02 - CLIENT - VEO PRO MAX/core/app_controller.py`

Day la nhanh **bridge-aware**:

- Neu bridge da `is_connected(email)`
- Va version da khop
- No skip reinstall

Vi vay, nhin vao logic code hien tai, day la caller **it kha nang nhat** gay ra reinstall trong snippet nay.

---

## 7. Tai Sao Log Nay Co Kha Nang La Tu Browser/Luong Khac

Mot chi tiet quan trong:

Log:

```text
[DEBUG] Step 4: ✅ Already on /tools/flow — skipping navigation
```

nam trong reconnect flow cua `profiles_controller`, sau `Step 1b: Extension install`.

Tuy nhien trong snippet, reinstall log lai xuat hien **sau** `Step 4`.

Dieu nay dan toi ket luan kha chac chan:

- Log `Step 4` va log reinstall **khong thuoc cung mot thu tuyen tinh don le**
- Chung thuoc **nhieu luong/browser chay song song**

No phu hop voi boi canh startup:

- AutoLaunch mo nhieu browser
- Account manager connect nhieu account
- Extension install/check co the chay o browser A trong khi browser B vua log `Step 4`

Vi vay, kha nang cao nhat la:

- `levanlinh...` da register tren mot browser/tab
- trong khi mot browser khac, hoac chinh browser kia nhung o luong startup khac, dang chay `install_if_needed()` va false-negative

---

## 8. Root Cause Ky Thuat

### Root Cause 1: Single-source-of-truth khong thong nhat

Hien tai he thong co 2 dinh nghia khac nhau ve "extension dang song":

- Bridge: co WebSocket + `register`
- Installer: phai thay `service_worker/background_page` trong CDP `/json`

Khi hai tin hieu nay lech nhau, app co the:

- vua bao `Extension connected`
- vua tu reinstall ngay sau do

### Root Cause 2: MV3 service worker visibility khong on dinh

Voi MV3:

- service worker co the chua spawn kip
- co the vua bi suspend
- co the CDP `/json` tra ve danh sach target chua co worker dung luc check

Nhung content script van co the song va bridge van connected.

### Root Cause 3: Nhieu caller van goi `install_if_needed()` truoc khi bridge-aware batch check can thiep

Du da co nhanh `ensure_all_extensions()` co bridge-aware skip, nhieu nhanh khac van:

- launch moi
- reconnect
- debug browser setup

goi `install_if_needed()` truc tiep, khong can bridge state.

---

## 9. Danh Gia Muc Do Chac Chan

### Da xac nhan chac chan

1. Reinstall trong log duoc kich hoat boi:
   - `is_extension_loaded(port) == False` sau retry
2. `Extension registered ... src=content_script` khong du de `install_if_needed()` skip reinstall
3. He thong co nhieu caller khong bridge-aware van co the goi `install_if_needed()`
4. Snippet dang nam trong boi canh startup race cua nhieu browser/account song song

### Chua the xac nhan tu snippet don le

1. Chinh xac caller nao la nguon cua dong reinstall nay
2. Dong reinstall thuoc port/profile nao
3. Service worker thuc su chua spawn hay da bi suspend

De xac nhan 100%, can log them:

- `email/profile/port` ngay truoc moi lan `install_if_needed()`
- caller source: `launch_chrome`, `launch_or_reconnect`, `profiles_controller Step 1b`, hay `ensure_all_extensions`

---

## 10. Dieu Khong Lien Quan

Canh bao Node:

```text
[DEP0169] DeprecationWarning: url.parse()
```

khong lien quan toi quyet dinh reinstall.

No khong tham gia vao:

- `is_extension_loaded()`
- `install_if_needed()`
- `reinstall_extension()`

Day la warning doc lap cua runtime Node.

---

## 11. Ket Luan Cuoi Cung

Ly do app cai dat lai extension trong log nay la:

**installer khong tim thay MV3 extension target trong CDP `/json` sau retry, du bridge da nhan `register` tu content script.**

Day la mot false-negative startup race, phat sinh do:

1. `registered via bridge` va `loaded via CDP service worker` la 2 tieu chi khac nhau
2. MV3 service worker co the chua visible dung luc startup
3. Nhiem vu install/check extension dang duoc goi tu nhieu caller khong bridge-aware

Danh gia kha di nhat cho snippet cu the:

- `Extension registered` cua `levanlinh...` la that
- nhung mot luong/browser khac dang startup song song da goi `install_if_needed()`
- CDP check false-negative
- va he thong tu reinstall

---

## 12. Huong Xac Minh Tiep Theo

Neu can khoanh dung caller, can doi chieu them voi log theo mau sau:

1. Truoc moi `install_if_needed()`, log:
   - caller
   - email
   - profile
   - port
2. Log ket qua `is_extension_loaded(port)` truoc khi retry
3. Log danh sach target type/url rut gon tu `/json` khi false-negative
4. Tach log reinstall theo:
   - `new launch`
   - `reconnect`
   - `debug Step 1b`
   - `batch ensure_all_extensions`

Khong can doi logic truoc khi co buoc quan sat nay, nhung neu khong co telemetry bo sung thi rat kho xac dinh chinh xac caller tu log production rut gon.
