# 🪟 Popup Layouts Master Document

**Version**: 1.0  
**Last Updated**: 2026-02-03  
**Status**: ✅ Approved for Implementation

---

## 📋 Popup Inventory

| ID | Popup Name | Used In | Type |
|----|------------|---------|------|
| P01 | [Edit Prompt Popup](#p01-edit-prompt-popup) | T2V, I2V, R2V, T2I, I2I, Queue | Shared |
| P02 | [Image Manager Popup](#p02-image-manager-popup) | I2V, R2V, I2I | Shared |
| P03 | [Folder Picker Dialog](#p03-folder-picker-dialog) | All Tabs | System |
| P04 | [File Import Dialog](#p04-file-import-dialog) | T2V, I2V, R2V, T2I, I2I | System |
| P05 | [Help Tooltip Popup](#p05-help-tooltip-popup) | I2V | Tab-specific |
| P06 | [Video Player Popup](#p06-video-player-popup) | Queue | Tab-specific |
| P07 | [Settings Popup](#p07-settings-popup) | Queue | Tab-specific |
| P08 | [Add Profile Dialog](#p08-add-profile-dialog) | Settings | Tab-specific |
| P09 | [Rename Dialog](#p09-rename-dialog) | Settings | Tab-specific |
| P10 | [Confirm Dialog](#p10-confirm-dialog) | All Tabs | Shared |
| P11 | [Error Dialog](#p11-error-dialog) | All Tabs | Shared |
| P12 | [License Expiration Dialog](#p12-license-expiration-dialog) | App Startup, License Tab | License |

---

## P01: Edit Prompt Popup

> **Trigger**: Click `[✏]` button in PARSED PROMPTS table

```
┌─────────────────────────────────────────────────────────────┐
│ 📝 EDIT PROMPT - Row #1                              [X]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ A sunset scene over mountains with golden light         │ │
│ │ Camera slowly pans across the misty valley              │ │
│ │ Birds flying in formation against the orange sky        │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Character Count: 142/500                                    │
│                                                             │
│                            [Cancel]  [💾 Save]              │
└─────────────────────────────────────────────────────────────┘
```

### Widget Specifications

| Widget | Type | Properties |
|--------|------|------------|
| `title_label` | CTkLabel | "📝 EDIT PROMPT - Row #N" |
| `close_btn` | CTkButton | "[X]" → Close popup |
| `prompt_textbox` | CTkTextbox | Multi-line, 500 char max |
| `char_count_label` | CTkLabel | Dynamic count |
| `cancel_btn` | CTkButton | Close without save |
| `save_btn` | CTkButton | Save and close |

### Behavior

| Action | Result |
|--------|--------|
| Save | Update prompt in table, close popup |
| Cancel / [X] | Discard changes, close popup |
| ESC key | Same as Cancel |

---

## P02: Image Manager Popup

> **Trigger**: Click `[📂 Manage Images]` button in Sidebar

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 🖼️ IMAGE LIBRARY MANAGER                                          [X]   │
├──────────────────────────────────────────────────────────────────────────┤
│ ┌────────────────────┬───────────────────────────────────────────────────┤
│ │ 📁 CATEGORIES      │ 🖼️ IMAGES IN: char_                              │ │
│ │ ┌────────────────┐ │ ┌─────────────────────────────────────────────────┤
│ │ │ ▼ char_ (12)   │ │ │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│
│ │ │   ► bg_ (8)    │ │ │ │ [hero]  │ │ [villain│ │ [mentor]│ │ [child] ││
│ │ │   ► style_ (5) │ │ │ │  ████   │ │  ████   │ │  ████   │ │  ████   ││
│ │ │   ► ref_ (3)   │ │ │ └─────────┘ └─────────┘ └─────────┘ └─────────┘│
│ │ └────────────────┘ │ │ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│
│ │                    │ │ │ [npc_1] │ │ [npc_2] │ │ [elder] │ │ [guard] ││
│ │ [+ Add Category]   │ │ │  ████   │ │  ████   │ │  ████   │ │  ████   ││
│ │                    │ │ └─────────┘ └─────────┘ └─────────┘ └─────────┘│
│ └────────────────────┴───────────────────────────────────────────────────┤
│ ─────────────────────────────────────────────────────────────────────────│
│ [📥 Import Images] [🗑️ Delete Selected] [✏️ Rename Tag]       [Close]   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Widget Specifications

| Widget | Type | Properties |
|--------|------|------------|
| `category_tree` | CTkScrollableFrame | Collapsible categories |
| `image_grid` | CTkScrollableFrame | 4-column grid |
| `image_card` | CTkFrame + CTkLabel | Thumbnail + tag name |
| `import_btn` | CTkButton | Opens file picker |
| `delete_btn` | CTkButton | Delete selected images |
| `rename_btn` | CTkButton | Rename tag dialog |
| `close_btn` | CTkButton | Close popup |

### Tag Naming Convention

| Prefix | Usage | Example |
|--------|-------|---------|
| `char_` | Characters | `[char_hero]`, `[char_villain]` |
| `bg_` | Backgrounds | `[bg_forest]`, `[bg_castle]` |
| `style_` | Style references | `[style_anime]`, `[style_realistic]` |
| `ref_` | General references | `[ref_lighting]`, `[ref_pose]` |

---

## P03: Folder Picker Dialog

> **Trigger**: Click `[📂 Browse]` button

**Type**: System Native Dialog (tkinter.filedialog.askdirectory)

```python
from tkinter import filedialog

path = filedialog.askdirectory(
    title="Select Output Folder",
    initialdir=current_path or os.path.expanduser("~")
)
```

---

## P04: File Import Dialog

> **Trigger**: Click `[📥 Import TXT]` button

**Type**: System Native Dialog (tkinter.filedialog.askopenfilename)

```python
from tkinter import filedialog

path = filedialog.askopenfilename(
    title="Import Prompts",
    filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
)
```

---

## P05: Help Tooltip Popup

> **Trigger**: Click `[❓ Help]` button in PARSED PROMPTS section (TAB_02)

```
┌────────────────────────────────────────────────┐
│ ❓ HELP: Image Upload Symbols                  │
├────────────────────────────────────────────────┤
│ [🖼️ + ]  → Click to add image                 │
│ [🖼️ ✓ ]  → Image uploaded                     │
│ 🔒        → Locked (Continuation or N/A mode) │
│                                                │
│ Frame Mode Column States:                        │
│ • Start Only: Start active, End 🔒 locked       │
│ • End Only: Start 🔒 locked, End active         │
│ • Start+End: Both active                        │
│                                   [Got it!]    │
└────────────────────────────────────────────────┘
```

---

## P06: Video Player Popup

> **Trigger**: Click thumbnail in Queue Manager (TAB_06)
> **📍 Full spec in**: [TAB_06_QUEUE_MANAGER.md](TAB_06_QUEUE_MANAGER.md#video-player-popup)

```
┌─────────────────────────────────────────────────────────────┐
│ 🎬 VIDEO PLAYER - Task #5                            [X]    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                                                         │ │
│ │                    [VIDEO FRAME]                        │ │
│ │                                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ▶️ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  0:00/8s │
│                                                             │
│ [📂 Open Folder] [📋 Copy Path] [🔗 Open in Browser]        │
└─────────────────────────────────────────────────────────────┘
```

---

## P07: Settings Popup

> **Trigger**: Click `[⚙️]` button in Queue Manager (TAB_06)
> **📍 Full spec in**: [TAB_06_QUEUE_MANAGER.md](TAB_06_QUEUE_MANAGER.md#settings-popup)

```
┌─────────────────────────────────────────────────────────────┐
│ ⚙️ QUEUE SETTINGS                                    [X]    │
├─────────────────────────────────────────────────────────────┤
│ 🔄 Max Concurrent Tasks:  [3 ▼]                             │
│ ⏱️ Retry Delay (seconds): [30   ]                           │
│ 🔁 Max Retries:           [2 ▼]                             │
│ 📁 Default Output Folder: [D:/Output       ] [📂]           │
│ ─────────────────────────────────────────────────────────── │
│ ☑️ Auto-start on add                                        │
│ ☑️ Delete video after download                              │
│ ☐ Notify on completion                                      │
│                                                             │
│                            [Cancel]  [💾 Save]              │
└─────────────────────────────────────────────────────────────┘
```

---

## P08: Add Profile Dialog

> **Trigger**: Click `[+ Add]` button in Settings (TAB_07)
> **📍 Full spec in**: [TAB_07_SETTINGS.md](TAB_07_SETTINGS.md#add-profile-dialog)

```
┌─────────────────────────────────────────────────────────────┐
│ ➕ ADD NEW PROFILE                                   [X]    │
├─────────────────────────────────────────────────────────────┤
│ Account Email:    [user@gmail.com              ]            │
│ Plan:             [Free ▼]                                  │
│ Cookie Source:    [Paste ●] [File ○]                        │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Paste cookie here...                                    │ │
│ │                                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ [🔍 Validate Cookie]                [Cancel]  [💾 Save]     │
└─────────────────────────────────────────────────────────────┘
```

---

## P09: Rename Dialog

> **Trigger**: Click `[✏️]` button on profile row (TAB_07)

```
┌────────────────────────────────────────────────┐
│ ✏️ RENAME PROFILE                        [X]   │
├────────────────────────────────────────────────┤
│ Current: work@gmail.com                        │
│ New Name: [work-main@gmail.com        ]        │
│                                                │
│                     [Cancel]  [💾 Save]        │
└────────────────────────────────────────────────┘
```

---

## P10: Confirm Dialog

> **Trigger**: Destructive actions (delete, clear, etc.)

```
┌────────────────────────────────────────────────┐
│ ⚠️ CONFIRM ACTION                        [X]   │
├────────────────────────────────────────────────┤
│                                                │
│ Are you sure you want to delete 3 items?       │
│ This action cannot be undone.                  │
│                                                │
│                    [Cancel]  [🗑️ Delete]       │
└────────────────────────────────────────────────┘
```

---

## P11: Error Dialog

> **Trigger**: Error conditions (API failure, validation error, etc.)

```
┌────────────────────────────────────────────────┐
│ ❌ ERROR                                 [X]   │
├────────────────────────────────────────────────┤
│                                                │
│ Failed to extract frame from video.            │
│                                                │
│ Details: Video file not found or corrupted.    │
│                                                │
│                              [OK]  [📋 Copy]   │
└────────────────────────────────────────────────┘
```

---

## P12: License Expiration Dialog

> **Trigger**: Auto-show on app startup when license is expired/expiring, or click from License Tab

### Variant A: License Expired (Blocking)

```
┌──────────────────────────────────────────────────────────────┐
│ ⚠️ LICENSE HẾT HẠN                                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│          ┌────────────────────────────────────┐              │
│          │         ⏰ HẾT HẠN                 │              │
│          │                                    │              │
│          │    License của bạn đã hết hạn     │              │
│          │    vào ngày 2026-02-01            │              │
│          │                                    │              │
│          └────────────────────────────────────┘              │
│                                                              │
│   📋 License Key: F208-72DF-9B1D-4BF6-****-****              │
│   👤 Machine ID: ABC123DEF456                                │
│   📅 Expired: 2026-02-01 00:00:00                           │
│                                                              │
│ ─────────────────────────────────────────────────────────── │
│                                                              │
│   💡 Để tiếp tục sử dụng, vui lòng:                         │
│      • Liên hệ admin để gia hạn license                     │
│      • Hoặc nhập license key mới bên dưới                   │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ ____-____-____-____-____-____-____-____              │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                              │
│        [📋 Copy Machine ID]  [🔑 Kích Hoạt]  [❌ Thoát App]  │
└──────────────────────────────────────────────────────────────┘
```

### Variant B: License Expiring Soon (Warning)

```
┌──────────────────────────────────────────────────────────────┐
│ ⏰ LICENSE SẮP HẾT HẠN                                  [X]  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│          ┌────────────────────────────────────┐              │
│          │         ⚠️ CẢNH BÁO                │              │
│          │                                    │              │
│          │    License sẽ hết hạn sau         │              │
│          │          3 NGÀY                    │              │
│          │                                    │              │
│          └────────────────────────────────────┘              │
│                                                              │
│   📋 License Key: F208-72DF-9B1D-4BF6-****-****              │
│   📅 Expires: 2026-02-07 23:59:59                           │
│   ⏱️ Remaining: 3 days, 12 hours                            │
│                                                              │
│ ─────────────────────────────────────────────────────────── │
│                                                              │
│   💡 Liên hệ admin để gia hạn trước khi hết hạn            │
│                                                              │
│              [📋 Copy Info]  [Nhắc sau]  [✅ Đã hiểu]        │
└──────────────────────────────────────────────────────────────┘
```

### Variant C: Trial Ended (Upgrade Prompt)

```
┌──────────────────────────────────────────────────────────────┐
│ 🎁 TRIAL ĐÃ KẾT THÚC                                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│          ┌────────────────────────────────────┐              │
│          │        🎉 CẢM ƠN BẠN!             │              │
│          │                                    │              │
│          │   Bạn đã sử dụng hết 7 ngày       │              │
│          │   dùng thử VEO Pro Max             │              │
│          │                                    │              │
│          └────────────────────────────────────┘              │
│                                                              │
│   ✅ Đã tạo: 25 videos                                       │
│   ✅ Đã xử lý: 150 prompts                                   │
│   ✅ Thời gian sử dụng: 7 ngày                               │
│                                                              │
│ ─────────────────────────────────────────────────────────── │
│                                                              │
│   🚀 Nâng cấp ngay để tiếp tục:                             │
│      • PRO: 500 credits/tháng                               │
│      • ULTRA: Unlimited credits                              │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ ____-____-____-____-____-____-____-____              │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                              │
│        [📋 Copy Machine ID]  [🔑 Kích Hoạt]  [❌ Thoát App]  │
└──────────────────────────────────────────────────────────────┘
```

### Widget Specifications

| Widget | Type | Properties |
|--------|------|------------|
| `status_icon` | CTkLabel | ⚠️/⏰/🎁 based on variant |
| `status_box` | CTkFrame | `border_color` by status |
| `license_key_label` | CTkLabel | Masked key display |
| `machine_id_label` | CTkLabel | Hardware ID |
| `expiry_label` | CTkLabel | Expiration date/time |
| `remaining_label` | CTkLabel | Countdown (Variant B) |
| `new_key_entry` | CTkEntry | Placeholder: `____-____-____-____-____-____-____-____` |
| `copy_btn` | CTkButton | Copy machine ID to clipboard |
| `activate_btn` | CTkButton | Validate and activate new key |
| `exit_btn` | CTkButton | Exit application |
| `remind_btn` | CTkButton | Dismiss for now (Variant B only) |

### Status Box Colors

| Variant | Border Color | Background |
|---------|--------------|------------|
| A: Expired | `#EF4444` (red) | `#1a1a2e` |
| B: Expiring | `#EAB308` (yellow) | `#1a1a2e` |
| C: Trial Ended | `#3B82F6` (blue) | `#1a1a2e` |

### Behavior

| Action | Result |
|--------|--------|
| Copy Machine ID | Copy to clipboard, show toast |
| Activate | Validate key → Success: restart app / Fail: show error |
| Exit App | Close application completely |
| Remind Later (B) | Dismiss, remind again in 24h |
| [X] (B only) | Same as Remind Later |

### Auto-Show Rules

| Condition | Behavior |
|-----------|----------|
| License expired | Show Variant A on every startup (blocking) |
| License ≤ 7 days | Show Variant B on startup (can dismiss) |
| License ≤ 3 days | Show Variant B on startup + every 4 hours |
| Trial ended | Show Variant C (blocking) |

---

## 🎨 Popup Style Guidelines

### Dimensions

| Popup Type | Default Size | Min Size |
|------------|--------------|----------|
| Small (Confirm, Error, Rename) | 400×200 | 350×150 |
| Medium (Edit Prompt, Help) | 500×350 | 450×250 |
| Large (Image Manager, Video Player) | 800×600 | 700×500 |

### Common Elements

| Element | Style |
|---------|-------|
| Title Bar | `bg="#1a1a2e"`, 32px height |
| Close [X] | Top-right, hover red |
| Primary Button | `fg_color="#4a90d9"` |
| Cancel Button | `fg_color="transparent"`, border |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `ESC` | Close popup (Cancel) |
| `Enter` | Submit/Save (focus on primary button) |
| `Tab` | Navigate between fields |

---

## 📍 Cross-References

| Tab | Inline Popup Section |
|-----|---------------------|
| TAB_01 | [Text to Video - Popups](TAB_01_TEXT_TO_VIDEO.md#popups) |
| TAB_02 | [Image to Video - Popups](TAB_02_IMAGE_TO_VIDEO.md#popups) |
| TAB_03 | [Ingredients - Popups](TAB_03_INGREDIENTS.md#popups) |
| TAB_04 | [Text to Image - Popups](TAB_04_TEXT_TO_IMAGE.md#popups) |
| TAB_05 | [Image to Image - Popups](TAB_05_IMAGE_TO_IMAGE.md#popups) |
| TAB_06 | [Queue Manager - Popups](TAB_06_QUEUE_MANAGER.md#popups) |
| TAB_07 | [Settings - Popups](TAB_07_SETTINGS.md#popups) |
