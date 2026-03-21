# Build Rules — VEO Pro Max macOS
# ====================================

## 🔑 Git & Repository Info

| Item | Value |
|------|-------|
| Private Repo (source) | `https://github.com/lynkvproerror/veo-pro-max` |
| Public Repo (releases) | `https://github.com/lynkvproerror/vadveopromax` |
| Source folder (macOS) | `04 - MAC` |
| Build script folder | `04.1 - macOS build script Nuitka` |
| Build output folder | `04.2 - macOS final build` |

---

## 📌 Rule #1: macOS Build Prerequisites

### 1a. Cần chạy trên máy Mac THẬT

> [!CAUTION]
> **KHÔNG THỂ cross-compile từ Windows sang macOS!**
> Nuitka yêu cầu native macOS toolchain (Xcode CLT, clang, macOS SDK).
> Phải build trực tiếp trên máy Mac (Intel hoặc Apple Silicon).

### 1b. Dependencies

```bash
# 1. Xcode Command Line Tools (BẮT BUỘC)
xcode-select --install

# 2. Python 3.13+ (via Homebrew nếu chưa có)
brew install python@3.13

# 3. Build tools
pip install nuitka ordered-set zstandard cryptography

# 4. App dependencies (từ 04 - MAC/)
pip install -r requirements.txt
```

### 1c. Architecture

| Mac | Architecture | Nuitka flag | Output |
|-----|-------------|-------------|--------|
| Apple Silicon (M1/M2/M3) | `arm64` | Auto-detect | Native ARM binary |
| Intel Mac | `x86_64` | Auto-detect | Native x86 binary |

> [!IMPORTANT]
> Build trên M1 → chỉ chạy trên Apple Silicon.
> Build trên Intel → chỉ chạy trên Intel Mac.
> Nếu cần Universal Binary (cả 2), phải build 2 lần rồi dùng `lipo` merge.

---

## 📌 Rule #2: Nuitka macOS vs Windows — Khác biệt

| Tính năng | Windows | macOS |
|-----------|---------|-------|
| Output format | `.exe` | `.app` bundle |
| Console disable | `--windows-console-mode=disable` | `--macos-app-mode=gui` |
| Icon format | `.ico` | `.icns` |
| Code signing | Không cần | **Nên có** (Gatekeeper) |
| Notarization | Không có | Cần cho phân phối ngoài App Store |
| DLL hiding | `attrib +H +S` | Tự động (trong .app bundle) |
| File structure | Flat (exe + DLLs) | `.app/Contents/{MacOS,Resources,Frameworks}` |

### 2a. .app Bundle Structure

```
VEO_Pro_Max.app/
└── Contents/
    ├── Info.plist              # App metadata (Nuitka auto-generates)
    ├── MacOS/
    │   └── VEO_Pro_Max         # Native binary (C compiled)
    ├── Resources/
    │   ├── config/locales/     # Language files
    │   ├── assets/             # Icons, images
    │   ├── data/               # Encrypted workflow data (.enc)
    │   ├── extension/          # Chrome extension (obfuscated)
    │   └── icon.icns           # App icon
    └── Frameworks/
        ├── libpython3.13.dylib # Python runtime
        ├── QtCore.framework/   # PySide6
        └── ...                 # Other .dylib/.framework
```

> **Ưu điểm so với Windows**: DLLs tự động ẩn trong bundle, user chỉ thấy 1 file `.app`.

---

## 📌 Rule #3: macOS Code Signing

### 3a. Ad-hoc signing (Dev/Testing)

```bash
# Sign không cần Apple Developer account
python build_release_macos.py
# → Tự động ad-hoc sign (identity "-")
```

- ✅ Chạy được trên cùng máy build
- ⚠️ Gatekeeper hiện cảnh báo "unidentified developer" trên máy khác
- User bypass: `Right-click → Open` → `Open` (lần đầu tiên)

### 3b. Developer ID signing (Distribution)

```bash
# Sign với Apple Developer ID (trả phí $99/năm)
python build_release_macos.py --sign-identity "Developer ID Application: Your Name (TEAMID)"
```

- ✅ Gatekeeper không chặn
- ⚠️ Yêu cầu Notarization (step bổ sung)

### 3c. Notarization (Optional, recommended)

```bash
# Sau khi sign:
xcrun notarytool submit VEO_Pro_Max.app \
    --apple-id your@email.com \
    --team-id TEAMID \
    --password app-specific-password \
    --wait

# Staple notarization ticket:
xcrun stapler staple VEO_Pro_Max.app
```

> [!TIP]
> Không có Developer ID? User bypass Gatekeeper:
> 1. Right-click `.app` → Open → Open (confirm)
> 2. Hoặc: `System Settings → Privacy & Security → Open Anyway`
> 3. Hoặc terminal: `xattr -cr VEO_Pro_Max.app`

---

## 📌 Rule #4: Icon (.icns) Conversion

macOS cần `.icns` format (không phải `.ico`):

```bash
# Convert từ .ico hoặc .png → .icns
# Cần file 1024x1024 PNG

mkdir icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset

# Copy vào assets/
cp icon.icns "04 - MAC/assets/icon.icns"
```

---

## 📌 Rule #5: macOS Build Pipeline (One-Command)

```bash
python build_release_macos.py    # ← MỘT LỆNH DUY NHẤT
```

### Pipeline (9 bước)

```
[1]     Check dependencies (Python, Nuitka, Xcode CLT, PySide6)
[2]     Generate SHA-256 hashes (8 security files)
[3]     Save build_info.json → folder 04.2
[3.5]   Inject integrity hashes into source
[4]     Nuitka standalone compile → .app bundle
[4.5]   Restore integrity_check.py (source clean)
[5]     Organize .app bundle (copy extension, data)
[5.5]   Obfuscate extension JS
[5.8]   Encrypt workflow data (.md → .enc)
[6]     Code signing (ad-hoc or Developer ID)
[6.5]   Generate version.json
[7]     Create ZIP + optional DMG
```

### Flags

| Flag | Mô tả |
|---|---|
| `--check` | Chỉ kiểm tra dependencies |
| `--hash-only` | Chỉ generate hashes |
| `--skip-compile` | Bỏ qua Nuitka |
| `--skip-sign` | Bỏ qua code signing |
| `--skip-publish` | Bỏ qua ZIP creation |
| `--dmg` | Tạo thêm DMG installer |
| `--sign-identity "..."` | Developer ID signing |

---

## 📌 Rule #6: Anti-Crack Protection Layers

### 6a. So sánh Windows vs macOS

| Layer | Windows (Nuitka) | macOS (Nuitka) | Note |
|-------|-----------------|----------------|------|
| Code compilation | ✅ C binary (.exe) | ✅ C binary (Mach-O) | **Tương đương** |
| Decompile difficulty | Rất khó | Rất khó | Cùng level |
| Integrity hash | ✅ SHA-256 injected | ✅ SHA-256 injected | Tương đương |
| Anti-debug | IsDebuggerPresent | sysctl P_TRACED | ✅ Ported |
| VM detection | WMI/Registry | ioreg/system_profiler | ✅ Ported |
| Trial markers | 3 locations | 3 locations | ✅ Ported |
| Code signing | N/A | ✅ codesign | **macOS bổ sung** |
| Monkey-patch detect | ✅ id() check | ✅ id() check | Tương đương |

### 6b. macOS-Exclusive Protection

1. **Gatekeeper**: macOS tự chặn app chưa sign — user phải explicitly allow
2. **SIP (System Integrity Protection)**: macOS protect system files khỏi injection
3. **Hardened Runtime** (`--options runtime`): chặn code injection, DYLD hijacking

### 6c. Còn yếu điểm nào?

| Attack Vector | Risk | Mitigation |
|---------------|------|------------|
| `class-dump` / Hopper | 🟡 Medium | LTO obfuscation giảm readable symbols |
| Memory patching | 🟡 Medium | Anti-debug check P_TRACED |
| DYLIB injection | 🟢 Low | Hardened Runtime + SIP chặn |
| `.app` chỉnh sửa → re-sign | 🟡 Medium | Integrity hash detect |
| License key sharing | 🔴 High | Server-side validation |

---

## 📌 Rule #7: Accessibility Permissions

> [!WARNING]
> **macOS app cần Accessibility permission cho AppleScript automation!**

Các tính năng cần Accessibility:
- Extension installation (AppleScript folder picker)
- Chrome window management (hide/show)
- Client data extraction (hide temp Chrome)

User cấp quyền:
1. `System Settings → Privacy & Security → Accessibility`
2. Click `+` → add `VEO_Pro_Max.app` (hoặc `Terminal.app` khi dev)
3. Toggle ON

> First-run: macOS tự hiện dialog xin permission. User chỉ cần click `OK`.

---

## 📌 Rule #8: FFmpeg Bundle cho macOS

### 8a. Cấu trúc

```
04 - MAC (source)
└── tools/ffmpeg/
    ├── ffmpeg           # macOS ARM64 hoặc x86_64 binary
    └── ffprobe          # macOS binary
```

### 8b. Download FFmpeg cho macOS

```bash
# Apple Silicon (arm64):
curl -L "https://evermeet.cx/ffmpeg/ffmpeg-arm64" -o tools/ffmpeg/ffmpeg
curl -L "https://evermeet.cx/ffmpeg/ffprobe-arm64" -o tools/ffmpeg/ffprobe
chmod +x tools/ffmpeg/ffmpeg tools/ffmpeg/ffprobe

# Intel (x86_64):
curl -L "https://evermeet.cx/ffmpeg/ffmpeg" -o tools/ffmpeg/ffmpeg
curl -L "https://evermeet.cx/ffmpeg/ffprobe" -o tools/ffmpeg/ffprobe
chmod +x tools/ffmpeg/ffmpeg tools/ffmpeg/ffprobe
```

### 8c. Search Order (frame_extractor.py)

| Priority | Location |
|----------|----------|
| 0 | `<app_dir>/tools/ffmpeg/ffmpeg` |
| 1 | `/opt/homebrew/bin/ffmpeg` (Homebrew ARM) |
| 2 | `/usr/local/bin/ffmpeg` (Homebrew Intel) |
| 3 | System PATH (`which ffmpeg`) |
| 4 | Auto-download → `tools/ffmpeg/` |

---

## 📌 Rule #9: Distribution Methods

### 9a. Option 1: ZIP (Đơn giản nhất)

```
VEO_Pro_Max_v{VER}_macOS.zip
└── VEO_Pro_Max.app/
```

User download → unzip → drag `.app` to `/Applications` → done.

### 9b. Option 2: DMG (Chuyên nghiệp hơn)

```bash
python build_release_macos.py --dmg
```

Tạo `.dmg` với drag-and-drop install (icon app → /Applications folder).

### 9c. Gatekeeper bypass (cho unsigned builds)

```bash
# User chạy 1 lần sau khi download:
xattr -cr /Applications/VEO\ Pro\ Max.app

# Hoặc: Right-click → Open → Open (confirm dialog)
```

---

## 📌 Rule #10: macOS-Specific Quy trình Release

```
1. Sửa code trong folder 04 - MAC
2. Bump APP_VERSION (nếu thay đổi) và/hoặc manifest.json version
3. Copy build_release_macos.py sang máy Mac (hoặc git pull)
4. Trên máy Mac: python build_release_macos.py
5. Upload VEO_Pro_Max_v{VER}_macOS.zip lên GitHub Release
6. Push version.json (macOS-specific) → separate endpoint hoặc cùng repo
7. Verify: download + chạy trên máy Mac khác
```

> [!IMPORTANT]
> **macOS build TÁCH BIỆT với Windows build!**
> - Windows: `02 → 02.1 → 03` pipeline
> - macOS: `04 → 04.1 → 04.2` pipeline
> - Hai cái KHÔNG ảnh hưởng lẫn nhau
