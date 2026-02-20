# 🏗️ Architecture Documentation

System architecture, API mapping, and design patterns.

---

## 📋 Files

| File | Size | Description |
|------|------|-------------|
| [ARCHITECTURE_OVERVIEW.md](../00_PROJECT/ARCHITECTURE_OVERVIEW.md) | 15KB | System diagram, data flow, component responsibilities |
| [API_MAPPING.md](./API_MAPPING.md) | 3KB | API endpoint → handler mapping |
| [ENGINE_PIPELINE_ARCHITECTURE.md](./ENGINE_PIPELINE_ARCHITECTURE.md) | 35KB | Engine pipeline phases, retry, reCAPTCHA, auto-export |
| [CONCURRENCY_MODEL.md](./CONCURRENCY_MODEL.md) | 12KB | ĐẠI CHỦ/CHỦ/THẦU/THỢ hierarchy, video-based units, account isolation |
| [ACCOUNT_AFFINITY_RULES.md](./ACCOUNT_AFFINITY_RULES.md) | 7KB | Account affinity rules for retry/reprocess operations |
| [AUTO_UPDATE_SYSTEM.md](./AUTO_UPDATE_SYSTEM.md) | 24KB | Auto-update: GitHub + Firebase, Windows self-replace |
| [UI_TO_API_PARAMETER_MAPPING.md](./UI_TO_API_PARAMETER_MAPPING.md) | 37KB | Complete UI control → API parameter conversion |
| [FRAME_CONTINUATION_WORKFLOW.md](./FRAME_CONTINUATION_WORKFLOW.md) | 5KB | Frame extraction & continuation chaining logic |
| [IMAGE_ENHANCER_SYSTEM.md](./IMAGE_ENHANCER_SYSTEM.md) | 8KB | Real-ESRGAN + GFPGAN: models, toggles, integration points |
| [WORKFLOW_ACTIVITY_DIAGRAMS.md](./WORKFLOW_ACTIVITY_DIAGRAMS.md) | 6KB | UML activity diagrams for key workflows |
| [VEO_System_Flow_Diagrams.md](./VEO_System_Flow_Diagrams.md) | 19KB | API flow diagrams for all generation modes |
| [UI_PERFORMANCE_ANALYSIS.md](./UI_PERFORMANCE_ANALYSIS.md) | 7KB | UI performance analysis and optimization |

## 📁 Sub-folders

| Folder | Contents |
|--------|----------|
| `diagrams/` | Architecture diagram images |

---

**Related**: [00_PROJECT](../00_PROJECT/) · [03_Backend](../03_Backend/) · [04_Workflows](../04_Workflows/)
