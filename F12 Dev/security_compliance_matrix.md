# VERIFIED SECURITY COMPLIANCE MATRIX
> Scanned 46 HAR files.

| Method | Endpoint | Valid Auth (Bearer/Cookie) | reCAPTCHA | API Key | x-browser-* | Tool=PINHOLE | Notes |
|---|---|---|---|---|---|---|---|
| GET | `/ai-sandbox-videofx/video/{ID}` | ❓ Stripped | ❌ | ❌ | ✅ REQUIRED | ❌ | Found in 1 files |
| GET | `/fx/_next/data/{ID}/en/library.json` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 1 files |
| GET | `/fx/_next/data/{ID}/en/tools/flow.json` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 2 files |
| GET | `/fx/_next/data/{ID}/en/tools/flow/project/{ID}` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 1 files |
| GET | `/fx/api/auth/session` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 2 files |
| GET | `/fx/api/trpc/project.getProject` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 3 files |
| GET | `/fx/api/trpc/{ID}` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 20 files |
| GET | `/media.fetchHistory` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 23 files |
| GET | `/project.searchScenes` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 46 files |
| GET | `/v1/media/{ID}` | ❓ Stripped | ❌ | ✅ REQUIRED | ✅ REQUIRED | ✅ REQUIRED | Found in 12 files |
| GET | `/v1/{ID} (GET)` | ❓ Stripped | ❌ | ✅ REQUIRED | ✅ REQUIRED | ❌ | Found in 4 files |
| POST | `/flowMedia:batchGenerateImages` | ❓ Stripped | ✅ REQUIRED | ❌ | ✅ REQUIRED | ✅ REQUIRED | Found in 5 files |
| POST | `/fx/api/trpc/{ID}` | ❓ Stripped | ❌ | ❌ | ❌ | ❌ | Found in 45 files |
| POST | `/uploadUserImage` | ❓ Stripped | ❌ | ❌ | ✅ REQUIRED | ❌ | Found in 12 files |
| POST | `/upsampleImage` | ❓ Stripped | ✅ REQUIRED | ❌ | ✅ REQUIRED | ✅ REQUIRED | Found in 4 files |
| POST | `/v1/{ID} (POST)` | ❓ Stripped | ✅ REQUIRED | ❌ | ✅ REQUIRED | ✅ REQUIRED | Found in 6 files |
| POST | `/video:checkStatus` | ❓ Stripped | ❌ | ❌ | ✅ REQUIRED | ❌ | Found in 21 files |
| POST | `/video:generateGif` | ❓ Stripped | ❌ | ❌ | ✅ REQUIRED | ❌ | Found in 1 files |
| POST | `/video:generateStartEnd` | ❓ Stripped | ✅ REQUIRED | ❌ | ✅ REQUIRED | ✅ REQUIRED | Found in 8 files |
| POST | `/video:upscaleVideo` | ❓ Stripped | ✅ REQUIRED | ❌ | ✅ REQUIRED | ❌ | Found in 8 files |
| POST | `/{ID}` | ❓ Stripped | ❌ | ❌ | ✅ REQUIRED | ✅ REQUIRED | Found in 3 files |
