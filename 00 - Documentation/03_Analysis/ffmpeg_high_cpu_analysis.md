# FFmpeg High CPU Analysis

**Date**: 2026-04-11  
**Severity**: P1  
**Scope**: Phan tich tai sao `ffmpeg` cua app an CPU cao, thuong 30-40% CPU moi process

---

## 1. Executive Summary

CPU cao khong den tu viec "ffmpeg bi loi", ma den tu **cach app dang goi ffmpeg**.

Ket luan chinh:

1. Nhánh an CPU nhat la **xoa watermark bang zoom+crop** sau khi download video.
2. Nhánh nay **re-encode toan bo video bang `libx264` software encode**.
3. App dang chon **quality-first settings**:
   - `-preset slow`
   - `-crf 15`
   - `scale=...:flags=lanczos,crop=...`
4. App **khong gioi han `-threads`**, nen `libx264` tu dong an nhieu core.
5. App **khong dung encoder GPU**, du binary FFmpeg hien tai co ho tro `h264_nvenc`, `h264_qsv`, `h264_amf`.
6. App **khong co semaphore rieng de limit so process ffmpeg zoom+crop chay dong thoi**.
7. Setting `download_non_watermark` hien dang mac dinh = `True`, nen nhánh nay duoc bat theo default.
8. Neu toi uu CPU trong tuong lai, thay doi do **khong duoc** hy sinh chat luong video. Chat luong la rang buoc uu tien cao hon toc do.

Vi vay, viec thay moi process `ffmpeg` an 30-40% CPU la **phu hop voi code hien tai**.

---

## 2. Muc Tieu Debug

Can xac dinh:

- FFmpeg dang duoc dung o nhung dau viec nao
- Dau viec nao thuc su an CPU
- Tai sao moi process lai an den 30-40%
- CPU cao la do bug hay do thiet ke hien tai

---

## 3. Cac Nhanh Su Dung FFmpeg Trong App

Qua doc source, FFmpeg duoc dung trong 3 nhom chinh:

### 3.1. Trich frame / tao thumbnail

File:

- `02 - CLIENT - VEO PRO MAX/core/frame_extractor.py`
- `02 - CLIENT - VEO PRO MAX/core/engine.py`

Tinh chat:

- Chi lay 1 frame
- Chay ngan
- Tai CPU co, nhung khong phai thu pham chinh gay 30-40% keo dai

### 3.2. Concat clip

File:

- `02 - CLIENT - VEO PRO MAX/core/production_pipeline.py`

Lenh concat dung:

- `-f concat`
- `-c copy`

Tuc la **stream copy, khong re-encode**.  
Nhanh nay thuong CPU thap hon rat nhieu va khong phai nguon gay tai CPU lon.

### 3.3. Zoom + crop de xoa watermark

File:

- `02 - CLIENT - VEO PRO MAX/core/engine.py`
- `02 - CLIENT - VEO PRO MAX/core/upscale_queue.py`

Day la nhanh nang nhat:

- scale toan bo frame
- crop toan bo frame
- re-encode lai video H.264

Day la nguon gay CPU cao chinh.

---

## 4. Nhanh CPU-Nang Nhất: Non-Watermark Zoom+Crop

Code nam tai:

- [engine.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L10625)

Command hien tai:

```python
cmd = [
    ffmpeg, "-y", "-i", str(filepath),
    "-vf", f"scale={zoomed_w}:{zoomed_h}:flags=lanczos,crop={orig_w}:{orig_h}",
    "-c:v", "libx264", "-preset", "slow", "-crf", "15",
    "-profile:v", "high", "-level", "5.1",
    "-pix_fmt", "yuv420p",
    "-c:a", "copy",
    "-movflags", "+faststart",
    str(tmp_path),
]
```

Chinh comment trong code cung ghi ro:

- `Quality-first settings`
- `CRF 15 + slow preset`
- `Tradeoff: ~3x slower encoding`

Dieu nay co nghia:

- app dang uu tien chat luong hinh anh sau khi zoom/crop
- doi lai bang CPU encode cao

---

## 5. Tai Sao Nhánh Nay An CPU Cao

### 5.1. Dung `libx264` software encode

App dang dung:

- `-c:v libx264`

Tuc la encode bang CPU, khong phai GPU.

Trong khi bundled FFmpeg hien tai co san:

- `h264_nvenc`
- `h264_qsv`
- `h264_amf`

Nhung code khong chon bat ky encoder GPU nao.

Ket qua:

- moi lan watermark removal = CPU encode
- GPU encoder support co san nhung khong duoc khai thac

### 5.2. Dung `preset slow`

`-preset slow` cua `libx264` co dac diem:

- toi uu hinh anh/bitrate tot hon
- nhung ton CPU cao hon ro ret so voi `veryfast`, `faster`, `fast`

Day la mot trong nhung ly do truc tiep nhat khien moi process ffmpeg an CPU lon.

### 5.3. Dung `crf 15`

`CRF 15` la muc chat luong cao.

Tac dong:

- encoder phai lam viec ky hon de giu detail
- bitrate cao hon
- thoi gian xu ly va CPU usage tang

No khong phai ly do duy nhat, nhung ket hop voi `preset slow` thi rat nang.

### 5.4. Co filter image-processing truoc khi encode

Video filter hien tai:

```text
scale=...:flags=lanczos,crop=...
```

Trong do:

- `scale` bat buoc phai xu ly moi frame
- `lanczos` la scaler chat luong cao, nang hon bilinear/bicubic mac dinh
- `crop` tiep tuc xu ly moi frame

Tuc la pipeline nay khong chi encode, ma con:

1. decode video
2. scale moi frame bang scaler chat luong cao
3. crop moi frame
4. encode lai bang x264

Day la pipeline CPU-bound ro rang.

### 5.5. Khong set `-threads`

Trong command hien tai:

- khong co `-threads N`

Vi vay:

- `libx264` tu dong chon so thread theo kha nang he thong
- no co xu huong an nhieu core logic de day throughput

Voi may hien tai:

- CPU: `Intel Core i5-14400F`
- `10` cores
- `16` logical processors

Neu Task Manager hien 30-40% CPU cho 1 process ffmpeg, dieu nay xap xi:

- 30% tong CPU ~= 4.8 logical cores
- 40% tong CPU ~= 6.4 logical cores

Con so nay **rat hop ly** voi `libx264` auto-threading + filter scale/crop.

### 5.6. Priority khong bi ha xuong o nhánh nang nhat

Trong `frame_extractor.py`, code co y dinh cho FFmpeg chay `BELOW_NORMAL_PRIORITY_CLASS`.

Nhung o nhánh zoom+crop trong `engine.py`, process duoc tao boi:

- `asyncio.create_subprocess_exec(...)`

va chi truyen:

- `CREATE_NO_WINDOW`

Khong co `BELOW_NORMAL_PRIORITY_CLASS`.

Ket qua:

- nhánh nặng CPU nhất lai chay o priority binh thuong
- no canh tranh CPU truc tiep voi Chrome va app

---

## 6. Vi Sao Khong Chi 1 Process, Ma Co The Co Nhieu FFmpeg Song Song

Van de khong chi nam o tung command, ma con o **muc do song song**.

### 6.1. `download_non_watermark` bat mac dinh

File:

- [settings.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/config/settings.py#L25)

Setting hien tai:

```python
download_non_watermark: bool = True
```

Tuc la theo mac dinh:

- moi video download xong se di qua watermark-removal path

### 6.2. Download 720p goi zoom+crop ngay sau khi tai xong

File:

- [engine.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L10487)

Flow:

1. download video
2. neu `download_non_watermark=True`
3. goi `await self._remove_watermark_zoom_crop(...)`

Moi worker/pipeline deu co the cham den nhanh nay.

### 6.3. Download video upscale cung goi zoom+crop

File:

- [upscale_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2520)

TRPC download path cho video upscale sau khi tai xong cung goi:

- `await self._zoom_crop_fn(...)`

Tuc la:

- 720p path co ffmpeg
- 1080p/4K download path cung co ffmpeg

### 6.4. Khong co semaphore rieng de limit so FFmpeg jobs

Code hien tai co semaphore cho:

- submit API
- upscale API
- upload image

Nhung **khong co semaphore danh rieng cho ffmpeg zoom+crop**.

Dieu nay co nghia:

- neu nhieu worker/job cung download xong gan nhau
- nhieu ffmpeg se duoc spawn cung luc

### 6.5. App co kha nang chay nhieu pipeline song song

Theo `session.py`, mac dinh:

- `max_workers = 20`

Theo `upscale_queue.py`, job concurrency per-account:

- `INITIAL = 4`
- `MAX = 8`

No khong co nghia luc nao cung co 20 ffmpeg, nhung no cho thay kien truc cho phep:

- nhieu generation/download pipeline song song
- nhieu upscale jobs song song

Khi cac pipeline nay den giai doan download xong gan nhau, watermark-removal co the bung ra nhieu process ffmpeg mot luc.

---

## 7. Nhanh Nao Khong Phai Thu Pham Chinh

### 7.1. Frame extraction

File:

- [frame_extractor.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/frame_extractor.py#L370)

Lenh nay:

- chi extract 1 frame
- timeout ngan
- khong re-encode full video

CPU co tang nhung chi trong khoang ngan.  
Khong phai nguon gay 30-40% keo dai tren moi process.

### 7.2. FFmpeg concat

File:

- [production_pipeline.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/production_pipeline.py#L2925)

Lenh concat dung:

```text
-c copy
```

Tuc la copy stream, khong encode lai.  
CPU co the tang nhe, nhung day khong phai nguon gay tai CPU lon.

---

## 8. Phan Tich Muc 30-40% CPU Moi Process

Voi CPU hien tai:

- `16` logical processors

Neu 1 process ffmpeg an:

- `30%` tong CPU -> tuong duong ~`4.8` logical cores
- `40%` tong CPU -> tuong duong ~`6.4` logical cores

Dieu nay rat hop logic voi command hien tai vi no:

1. decode video
2. scale bang `lanczos`
3. crop
4. encode lai bang `libx264`
5. cho phep x264 tu dong mo nhieu threads

Tuc la muc 30-40%/process **khong bat thuong** doi voi command nay.

Neu co 2-3 ffmpeg chay dong thoi, tong CPU system co the tang rat ro.

---

## 9. Root Cause Tong Hop

CPU cao la ket qua cua **4 yeu to cong don**:

### Root Cause 1: Feature mac dinh dang bat

- `download_non_watermark = True`

Nen ffmpeg watermark-removal duoc goi rat thuong xuyen.

### Root Cause 2: Command re-encode qua nang

App chon:

- `libx264`
- `preset slow`
- `crf 15`
- `scale ... flags=lanczos`

Day la bo setting uu tien chat luong, khong uu tien CPU.

### Root Cause 3: Khong gioi han thread encoder

Khong co `-threads`, nen x264 auto chiem nhieu core.

### Root Cause 4: Khong gioi han so ffmpeg jobs song song

Khong co semaphore rieng cho zoom+crop, nen nhieu pipeline co the spawn ffmpeg cung luc.

---

## 10. Day La Bug Hay Hanh Vi Theo Thiet Ke?

**Ca hai, nhung nghieng ve thiet ke hien tai hon la bug runtime.**

### Khong phai bug theo nghia "ffmpeg loi"

Khong co dau hieu:

- ffmpeg crash
- loop vo han
- memory leak ro rang
- command sai

### La van de thiet ke / performance policy

Code hien tai dang chu dong chon:

- chat luong cao hon toc do
- CPU encode hon GPU encode
- khong cap thread
- khong cap concurrency cho ffmpeg jobs

Do do CPU cao la he qua tu nhien cua policy nay.

---

## 11. Uu Tien Anh Huong

Theo muc do tac dong den CPU, uu tien giam tai neu muon toi uu se la:

1. **Tat hoac giam tan suat `download_non_watermark`**
2. **Giam do nang cua x264 settings**
3. **Gioi han `-threads`**
4. **Them semaphore rieng cho ffmpeg jobs**
5. **Can nhac encoder GPU neu may co NVENC/QSV/AMF**

Bao cao nay chi phan tich, khong de xuat sua code cu the.

---

## 12. Rang Buoc Bat Buoc: Moi Thay Doi Phai Giu Chat Luong Video Toi Da

Neu sau nay dieu chinh nhánh FFmpeg de giam CPU, thi tai lieu nay quy dinh ro:

### 12.1. Uu tien ky thuat

Thu tu uu tien phai la:

1. **Chat luong video**
2. Do on dinh / tinh tuong thich
3. Toc do xu ly / CPU

Tuc la:

- khong duoc danh doi chat luong lay toc do neu chua co bang chung dinh luong ro rang
- moi toi uu CPU chi hop le neu chat luong dau ra van giu muc toi da cho phep

### 12.2. "Giu chat luong toi da" co nghia la gi

Trong boi canh nhánh `zoom+crop` nay, "giu chat luong toi da" duoc hieu la:

1. Khong lam giam do net nhin thay bang mat thuong so voi baseline hien tai
2. Khong tang banding, blocking, ringing, blur, smear, hoac chroma artifacts
3. Khong lam mat chi tiet o cac canh:
   - low light
   - texture min
   - gradient troi / nuoc / khoi
   - chuyen dong nhanh
4. Khong duoc ha do phan giai sau crop so voi output muc tieu hien tai
5. Khong duoc tao output xau hon ro rang so voi command baseline dang dung

### 12.3. Baseline chat luong hien tai

Baseline hien tai de doi chieu la command:

```text
-vf scale=...:flags=lanczos,crop=...
-c:v libx264
-preset slow
-crf 15
-profile:v high
-level 5.1
-pix_fmt yuv420p
-c:a copy
```

Luu y:

- baseline nay **chat luong cao**, nhung khong phai mathematically lossless
- moi thay doi sau nay phai dat chat luong **it nhat bang** baseline nay
- neu muon noi la "tot hon", phai co bang chung so sanh

### 12.4. Tieu chi chap nhan cho moi thay doi

Bat ky thay doi nao lien quan den FFmpeg watermark-removal chi duoc coi la chap nhan neu dat du 4 nhom dieu kien sau:

#### A. Visual acceptance

- So sanh side-by-side voi baseline tren nhieu video mau
- Khong thay giam chi tiet ro rang khi xem 100%
- Khong thay artifact moi xuat hien ro rang

#### B. Edge-case acceptance

Phai test tren toi thieu:

- 720p
- 1080p
- 4K neu co
- canh toi / low contrast
- canh nhieu texture
- canh chuyen dong nhanh
- portrait va landscape

#### C. Technical acceptance

- Output mo duoc binh thuong tren player thong dung
- Audio van duoc giu nguyen neu source co audio
- Khong lam loi mux / timestamp / moov atom

#### D. Regression acceptance

- Kich thuoc file co the thay doi, nhung chat luong khong duoc giam ro rang
- Neu CPU giam ma chat luong giam, thay doi do bi coi la khong dat

### 12.5. Cac thay doi bi xem la rui ro chat luong cao

Neu sau nay can toi uu, cac huong duoi day mac dinh phai xem la rui ro cao ve chat luong:

- tang CRF len dang ke
- doi `preset slow` xuong qua nhanh ma khong co doi chieu visual
- doi scaler `lanczos` sang scaler yeu hon ma khong test lai
- doi pixel format theo huong giam chat luong
- doi encoder GPU nhung khong benchmark visual voi baseline

### 12.6. Ket luan rang buoc

Tai lieu nay duoc cap nhat de chot ro:

**Moi thay doi nham giam CPU cho FFmpeg watermark-removal phai duoc thiet ke va kiem chung theo huong giu chat luong video toi da. CPU la bai toan toi uu thu cap; chat luong hinh anh la rang buoc khong duoc phep lui.**

---

## 13. Ket Luan Cuoi Cung

Ly do ffmpeg trong app an 30-40% CPU moi process la:

**app dang dung FFmpeg de re-encode toan bo video bang `libx264` software encode, voi `preset slow`, `crf 15`, va filter `scale+lanczos+crop`, trong khi khong gioi han `threads` va khong gioi han so process ffmpeg watermark-removal chay dong thoi.**

Vi the:

- CPU cao la dung voi command hien tai
- process nao dang xu ly watermark-removal se an CPU cao
- neu nhieu video hoan tat cung luc, tong CPU se tang manh hon nua

---

## 14. Files Lien Quan Da Doi Chieu

- [engine.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L10487)
- [engine.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/engine.py#L10625)
- [upscale_queue.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/upscale_queue.py#L2520)
- [frame_extractor.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/frame_extractor.py#L31)
- [production_pipeline.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/production_pipeline.py#L2925)
- [settings.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/config/settings.py#L25)
- [session.py](/D:/Music/Ruby/Produce%20for%20Customer/##Tools%20/VEO%20Tool/#NEW%20VEO%20API/02%20-%20CLIENT%20-%20VEO%20PRO%20MAX/core/session.py#L86)
