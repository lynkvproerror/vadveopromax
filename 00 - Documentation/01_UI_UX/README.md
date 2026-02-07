# 📐 UI Tabs Specification Index

This folder contains the complete UI/UX documentation for VEO Pro Max.

## 📚 Main Documents

| File | Description |
|------|-------------|
| [00_DESIGN_SYSTEM.md](00_DESIGN_SYSTEM.md) | 🎨 **Design System** - Colors, typography, architecture, components |

---

## Tab Overview

| # | Tab Name | Mode Index | Image Setup | continuation | Model |
|---|----------|------------|-------------|--------|-------|
| 1 | [Text-to-Video](TAB_01_TEXT_TO_VIDEO.md) | 0 | ❌ | ✅ | VEO |
| 2 | [Image-to-Video](TAB_02_IMAGE_TO_VIDEO.md) | 1 | ✅ (1 slot) | ✅ | VEO |
| 3 | [Ingredients](TAB_03_INGREDIENTS.md) | 2 | ✅ (3 slots) | ✅ | VEO |
| 4 | [Text-to-Image](TAB_04_TEXT_TO_IMAGE.md) | "last" | ❌ | ❌ | 🍌 Banana |
| 5 | [Image-to-Image](TAB_05_IMAGE_TO_IMAGE.md) | "last" | ✅ (1 slot) | ❌ | 🍌 Banana |
| 6 | [Queue Manager](TAB_06_QUEUE_MANAGER.md) | N/A | N/A | N/A | N/A |
| 7 | [Settings](TAB_07_SETTINGS.md) | N/A | N/A | N/A | N/A |
| 8 | [License](TAB_08_LICENSE.md) | N/A | N/A | N/A | N/A |
| 9 | [About](TAB_09_ABOUT.md) | N/A | N/A | N/A | N/A |
| 10 | [Dev Console](TAB_10_DEV_CONSOLE.md) | N/A | N/A | N/A | N/A |

---

## Layout Philosophy

All tabs use **Horizontal Split Layout** for optimal screen utilization:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ GLOBAL SETTINGS BAR (Always visible, top of tab)                             │
├────────────────────────┬─────────────────────────┬──────────────────────────┤
│ IMAGE SETUP (Left)     │ PROMPT INPUT (Center)   │ ACTIONS (Right)          │
│ (if applicable)        │ (always present)        │ (generate, queue)        │
└────────────────────────┴─────────────────────────┴──────────────────────────┘
```

---

## Color Coding

| Tab Type | Accent Color | Use |
|----------|--------------|-----|
| Video Generation (1-3) | `#2563EB` (Blue) | VEO model tabs |
| Image Generation (4-5) | `#8B5CF6` (Purple) | Banana Bro tabs |
| Management (6) | `#475569` (Gray) | Queue Manager |

---

## Implementation Priority

1. **Phase 1**: Tabs 1-3 (Core Video Generation)
2. **Phase 2**: Tab 6 (Queue Manager)
3. **Phase 3**: Tabs 4-5 (Image Generation - Bonus)
