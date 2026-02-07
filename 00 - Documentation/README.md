# VEO API Documentation

Complete developer reference for building applications with Google VEO API.

---

## 🚀 Quick Start

**New to VEO?** Start here:
1. **[5-Minute Quick Start](./QUICK_START.md)** - Generate your first video
2. **[Authentication Guide](./03_Backend/ACCOUNT_SESSION_MANAGEMENT.md)** - Get API access
3. **[Cheat Sheet](./CHEATSHEET.md)** - Quick reference

---

## 📚 Guides (Step-by-Step Workflows)

Follow these guides to implement specific features:

| Guide | What You'll Build | Time |
|-------|-------------------|------|
| **[01. Text-to-Video](./04_Workflows/WORKFLOW_TAB_01_TEXT_TO_VIDEO.md)** | Generate videos from prompts | 15 min |
| **[02. Image-to-Video](./04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md)** | Animate images (single/dual frame) | 20 min |
| **[03. Ingredients-to-Video](./04_Workflows/WORKFLOW_TAB_03_INGREDIENTS.md)** | Multi-image reference (R2V) | 25 min |
| **[04. Text-to-Image](./04_Workflows/WORKFLOW_TAB_04_TEXT_TO_IMAGE.md)** | Generate images (IMAGEN_3_5) | 15 min |
| **[05. Image-to-Image](./04_Workflows/WORKFLOW_TAB_05_IMAGE_TO_IMAGE.md)** | Transform images | 10 min |
| **[06. Error Handling](./03_Backend/ERROR_HANDLING_STRATEGY.md)** | Debugging & recovery | 10 min |

---

## 🔧 API Reference

Technical specifications and reference documentation:

- **[API Mapping](./02_Architecture/API_MAPPING.md)** - All endpoints with payloads
- **[UI to API Parameter Mapping](./02_Architecture/UI_TO_API_PARAMETER_MAPPING.md)** - Complete parameter reference
- **[Architecture Overview](./00_PROJECT/ARCHITECTURE_OVERVIEW.md)** - System diagram
- **[Glossary](./00_PROJECT/GLOSSARY.md)** - Terms & abbreviations

---

## 🎯 Common Tasks

**Quick navigation** for specific use cases:

| I want to... | Go to |
|--------------|-------|
| Generate video from text | [Text-to-Video Workflow](./04_Workflows/WORKFLOW_TAB_01_TEXT_TO_VIDEO.md) |
| Animate an image | [Image-to-Video Workflow](./04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md) |
| Use multiple reference images | [Ingredients Workflow](./04_Workflows/WORKFLOW_TAB_03_INGREDIENTS.md) |
| Generate images | [Text-to-Image Workflow](./04_Workflows/WORKFLOW_TAB_04_TEXT_TO_IMAGE.md) |
| Fix an error | [Error Handling](./03_Backend/ERROR_HANDLING_STRATEGY.md) |
| Quick lookup | [Cheat Sheet](./CHEATSHEET.md) |

---

## 📖 Documentation Structure

```
Documentation/
├── QUICK_START.md              # ⚡ 5-minute tutorial
├── CHEATSHEET.md               # 📋 One-page reference
│
├── 00_PROJECT/                  # 📁 Project & overview docs
│   ├── ARCHITECTURE_OVERVIEW.md
│   ├── GLOSSARY.md
│   ├── CODE_STRUCTURE.md
│   ├── CHANGELOG.md
│   └── TROUBLESHOOTING.md
│
├── 01_UI_UX/                    # 🎨 UI specifications (19 files)
│   ├── TAB_01_TEXT_TO_VIDEO.md
│   ├── TAB_02_IMAGE_TO_VIDEO.md
│   └── ...
│
├── 02_Architecture/             # 🏗️ System architecture
│   ├── API_MAPPING.md
│   ├── UI_TO_API_PARAMETER_MAPPING.md
│   └── FRAME_CONTINUATION_WORKFLOW.md
│
├── 03_Backend/                  # ⚙️ Backend logic (14 files)
│   ├── MULTITHREADING_ARCHITECTURE.md
│   ├── ACCOUNT_SESSION_MANAGEMENT.md
│   └── ERROR_HANDLING_STRATEGY.md
│
├── 04_Workflows/                # 🔄 Workflow docs (16 files)
│   ├── VEO_PRODUCTION_WORKFLOWS.md
│   └── WORKFLOW_TAB_*.md
│
└── 05_Security/                 # 🔐 License & security package
    ├── admin/                   # Admin tools (DO NOT SHIP)
    └── client/                  # License validation
```

---

## 🌟 Key Features

**VEO 3.1** offers:
- ✅ **Text-to-Video**: Generate from prompts
- ✅ **Image-to-Video**: Animate single or dual frames
- ✅ **Ingredients (R2V)**: Multi-image prompting (up to 3 images)
- ✅ **Image Generation**: IMAGEN_3_5 models
- ✅ **Upscaling**: 720p → 1080p/4K
- ✅ **Batch Processing**: Generate 4 videos simultaneously
- ✅ **Seed Control**: Reproducible variations

---

## 🔑 Model Keys

| Model Family | Keys Available | Use Case |
|--------------|----------------|----------|
| **Text-to-Video** | `veo_3_1_t2v_fast_*` (+ relaxed) | Generate from prompts |
| **Image-to-Video** | `veo_3_1_i2v_s_fast_*` (+ relaxed) | Animate images |
| **Reference-to-Video** | `veo_3_1_r2v_fast_*` (+ relaxed) | Multi-image prompting |
| **Upsampling** | `veo_3_1_upsampler_*` | 1080p/4K upscaling |
| **Image Generation** | `IMAGEN_3_5`, `GEM_PIX_2` | Static images |

**Total**: 21 models (18 video + 3 image)  
**Priority variants**: All video models have normal + lower priority (`_relaxed`) options

---

## ⚡ Getting Started Path

**Recommended learning order**:

1. **Setup** (10 min)
   - Read [Quick Start](./QUICK_START.md)
   - Set up [Authentication](./03_Backend/ACCOUNT_SESSION_MANAGEMENT.md)

2. **Basic Workflows** (30 min)
   - [Text-to-Video](./04_Workflows/WORKFLOW_TAB_01_TEXT_TO_VIDEO.md)
   - [Image-to-Video](./04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md)

3. **Advanced Features** (1 hour)
   - [Ingredients](./04_Workflows/WORKFLOW_TAB_03_INGREDIENTS.md)
   - [Multi-Account Parallel](./04_Workflows/WORKFLOW_MULTI_ACCOUNT_PARALLEL.md)

4. **Production Ready** (30 min)
   - [Error Handling](./03_Backend/ERROR_HANDLING_STRATEGY.md)
   - [Cheat Sheet](./CHEATSHEET.md) bookmark

---

## 📊 Coverage

- **Endpoints**: 18+ documented
- **Workflows**: 8 (T2V, I2V single/dual, R2V, Image Gen, Upscale, GIF, Status)
- **Models**: 21 model keys (18 video + 3 image)
- **Verification**: 98% accuracy against HAR files

---

## 🔄 Recent Updates

**2026-02-04**:
- ✅ Fixed orphan links (guides/, reference/ → actual paths)
- ✅ Updated documentation structure to match actual folders
- ✅ Standardized model count (21 models)

**2026-02-01**:
- ✅ Completed R2V (Ingredients) workflow with completion structure
- ✅ Restructured documentation (16 → 12 user-facing files)
- ✅ Added Quick Start guide

---

## 📞 Support

- **Issues?** Check [Error Handling](./03_Backend/ERROR_HANDLING_STRATEGY.md)
- **Troubleshooting?** See [Troubleshooting Guide](./00_PROJECT/TROUBLESHOOTING.md)
- **Quick lookup?** Use [Cheat Sheet](./CHEATSHEET.md)

---

**Last Updated**: 2026-02-07  
**Based on**: HAR file analysis + working implementations
