# R2V (Reference-to-Voice) Pipeline — Complete Analysis

> Consolidated from F12 Dev Tools network traffic + UI HTML analysis of `labs.google/fx` Flow.
> Source: `F12 Dev/Thu Nghiem Voice/Thu Nghiem Voice.txt` (25228 lines)

---

## 1. R2V Video Model Key

R2V uses a **dedicated model key** different from standard T2V:

```
veo_3_1_r2v_fast_landscape_ultra_relaxed
```

**Naming Pattern**: `veo_3_1_r2v_{speed}_{aspect}_{quality}_{priority}`

| Segment | Value | Meaning |
|---|---|---|
| `veo_3_1` | VEO 3.1 | Model version |
| `r2v` | Reference-to-Voice | Pipeline mode (vs `t2v`, `i2v`) |
| `fast` | Fast | Speed tier |
| `landscape` | Landscape | Aspect ratio (`VIDEO_ASPECT_RATIO_LANDSCAPE`) |
| `ultra` | Ultra quality | Quality tier |
| `relaxed` | Relaxed priority | Queue priority |

---

## 2. Complete Voice Catalog — 30 Voices

### 👩 FEMALE VOICES (12)

| # | Voice ID (API) | Display Name | Tone | Pitch | Preview |
|---|---|---|---|---|---|
| 1 | `achernar` | Achernar | soft | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Achernar.wav) |
| 2 | `algieba` | Algieba | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Algieba.wav) |
| 3 | `aoede` | Aoede | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Aoede.wav) |
| 4 | `callirrhoe` | Callirrhoe | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Callirrhoe.wav) |
| 5 | `erinome` | Erinome | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Erinome.wav) |
| 6 | `gacrux` | Gacrux | mature | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Gacrux.wav) |
| 7 | `kore` | Kore | firm | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Kore.wav) |
| 8 | `laomedeia` | Laomedeia | upbeat | mid-high | [WAV](https://www.gstatic.com/aistudio/voices/samples/Laomedeia.wav) |
| 9 | `leda` | Leda | youthful | mid-high | [WAV](https://www.gstatic.com/aistudio/voices/samples/Leda.wav) |
| 10 | `sulafat` | Sulafat | warm | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Sulafat.wav) |
| 11 | `vindemiatrix` | Vindemiatrix | gentle | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Vindemiatrix.wav) |
| 12 | `zephyr` | Zephyr | bright | mid-high | [WAV](https://www.gstatic.com/aistudio/voices/samples/Zephyr.wav) |

### 👨 MALE VOICES (13)

| # | Voice ID (API) | Display Name | Tone | Pitch | Preview |
|---|---|---|---|---|---|
| 1 | `achird` | Achird | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Achird.wav) |
| 2 | `algenib` | Algenib | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Algenib.wav) |
| 3 | `alnilam` | Alnilam | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Alnilam.wav) |
| 4 | `charon` | Charon | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Charon.wav) |
| 5 | `enceladus` | Enceladus | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Enceladus.wav) |
| 6 | `fenrir` | Fenrir | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Fenrir.wav) |
| 7 | `iapetus` | Iapetus | clear | mid-low | [WAV](https://www.gstatic.com/aistudio/voices/samples/Iapetus.wav) |
| 8 | `orus` | Orus | firm | mid-low | [WAV](https://www.gstatic.com/aistudio/voices/samples/Orus.wav) |
| 9 | `puck` | Puck | upbeat | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Puck.wav) |
| 10 | `rasalgethi` | Rasalgethi | informative | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Rasalgethi.wav) |
| 11 | `sadachbia` | Sadachbia | lively | low | [WAV](https://www.gstatic.com/aistudio/voices/samples/Sadachbia.wav) |
| 12 | `sadaltager` | Sadaltager | knowledgeable | mid | [WAV](https://www.gstatic.com/aistudio/voices/samples/Sadaltager.wav) |
| 13 | `schedar` | Schedar | even | mid-low | [WAV](https://www.gstatic.com/aistudio/voices/samples/Schedar.wav) |

### 🔄 OTHER (5)

| # | Voice ID | Display Name | Gender | Tone | Pitch | Preview |
|---|---|---|---|---|---|---|
| 1 | `autonoe` | Autonoe | unknown | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Autonoe.wav) |
| 2 | `despina` | Despina | unknown | — | — | [WAV](https://www.gstatic.com/aistudio/voices/samples/Despina.wav) |
| 3 | `pulcherrima` | Pulcherrima | Ungendered | forward | mid-high | [WAV](https://www.gstatic.com/aistudio/voices/samples/Pulcherrima.wav) |
| 4 | `umbriel` | Umbriel | Male | smooth | lower | [WAV](https://www.gstatic.com/aistudio/voices/samples/Umbriel.wav) |
| 5 | `zubenelgenubi` | Zubenelgenubi | Male | casual | mid-low | [WAV](https://www.gstatic.com/aistudio/voices/samples/Zubenelgenubi.wav) |

---

## 3. Voice Preview — gstatic.com WAV URLs

### URL Template
```
https://www.gstatic.com/aistudio/voices/samples/{VoiceName}.wav
```

**Rules:**
- Voice name is **PascalCase** (first letter uppercase): `Achernar`, `Aoede`, `Zubenelgenubi`
- File format: `.wav`
- **No authentication required** — public Google CDN
- Referer header: `https://labs.google/`
- `sec-fetch-dest: audio`
- Also accessible via `https://gstatic.com/aistudio/voices/samples/{Name}.wav` (without www)

> **IMPORTANT:** The voice `mediaId` in the submit payload is **lowercase** (`"aoede"`), but the WAV filename is **PascalCase** (`Aoede.wav`).

---

## 4. Core Submit Payload — `MEDIA_GENERATION_SETTINGS`

The **critical JSON structure** extracted from `FLOW_GENERATE_VIDEO_ERROR` event:

```json
{
  "json": {
    "resolution": null,
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "seed": 12565,
    "textInput": {
      "structuredPrompt": {
        "parts": [
          { "text": "hi mom, hi baby" }
        ]
      }
    },
    "videoModelKey": "veo_3_1_r2v_fast_landscape_ultra_relaxed",
    "metadata": {
      "workflowId": null,
      "collectionId": null
    },
    "referenceImages": [
      {
        "mediaId": "170928f2-3587-4c60-b3fa-de461b2dec7e",
        "cropCoordinates": null,
        "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"
      },
      {
        "mediaId": "44c0cbc5-41ac-45bf-b6b3-d4fbd29ca108",
        "cropCoordinates": null,
        "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"
      }
    ],
    "referenceAudio": [
      {
        "mediaId": "aoede"
      }
    ]
  },
  "meta": {
    "values": {
      "resolution": ["undefined"],
      "metadata.workflowId": ["undefined"],
      "metadata.collectionId": ["undefined"],
      "referenceImages.0.cropCoordinates": ["undefined"],
      "referenceImages.1.cropCoordinates": ["undefined"]
    }
  }
}
```

### Key Differences from Standard T2V

| Field | T2V | R2V |
|---|---|---|
| `videoModelKey` | `veo_3_generate_video_*` | `veo_3_1_r2v_*` |
| `referenceAudio` | ❌ absent | ✅ `[{"mediaId": "<voice-name>"}]` |
| `referenceImages` | Optional (I2V only) | ✅ Used alongside audio |
| `imageUsageType` | `IMAGE_USAGE_TYPE_STYLE_REFERENCE` | `IMAGE_USAGE_TYPE_ASSET` |
| `textInput` | Full prompt | Short dialogue/narration prompt |

> **IMPORTANT:** Voice `mediaId` is a **plain string name** (e.g., `"aoede"`), NOT a UUID. This is different from `referenceImages` which use UUID `mediaId` values.

---

## 5. Request Flow Sequence

```mermaid
sequenceDiagram
    participant UI as Labs.google UI
    participant API as aisandbox-pa.googleapis.com
    participant GS as gstatic.com
    participant TRPC as labs.google/fx/api/trpc
    participant LOG as Analytics/Logging

    Note over UI: User opens voice picker
    UI->>GS: GET /aistudio/voices/samples/{Name}.wav
    GS-->>UI: WAV audio file (voice preview)

    Note over UI: User selects voice
    UI->>API: POST /v1:batchLog<br/>event: ADD_REFERENCE_AUDIO<br/>REFERENCE_AUDIO_ID: "aoede"
    UI->>API: POST /v1/flow:batchLogFrontendEvents<br/>Same event (dual logging)
    
    Note over UI: User uploads reference images
    UI->>API: POST /v1/flow/uploadImage<br/>imageBytes: base64 (with C2PA metadata)
    API-->>UI: Returns mediaId UUID
    
    Note over UI: User clicks Generate
    UI->>TRPC: POST general.generateVideo<br/>MEDIA_GENERATION_SETTINGS JSON
    
    alt Success
        TRPC-->>UI: Returns operation/media ID
        UI->>API: POST /v1/video:batchCheckAsyncVideoGenerationStatus
    else Error (audio filtered)
        TRPC-->>UI: PUBLIC_ERROR_AUDIO_FILTERED
        UI->>API: POST /v1:batchLog<br/>event: FLOW_GENERATE_VIDEO_ERROR
    end
```

---

## 6. Dual Logging System

Every user action is logged to **two endpoints simultaneously**:

### Endpoint 1: `POST /v1:batchLog` (Legacy format)
```json
{
  "appEvents": [{
    "event": "ADD_REFERENCE_AUDIO",
    "eventProperties": [
      {"key": "REFERENCE_AUDIO_ID", "stringValue": "gacrux"},
      {"key": "MEDIA_GENERATION_PAYGATE_TIER", "stringValue": "PAYGATE_TIER_TWO"},
      {"key": "USER_AGENT", "stringValue": "..."},
      {"key": "IS_DESKTOP", "booleanValue": true}
    ],
    "eventMetadata": {"sessionId": ";1775420258353"},
    "eventTime": "2026-04-05T20:13:11.963Z"
  }]
}
```

### Endpoint 2: `POST /v1/flow:batchLogFrontendEvents` (Modern format)
```json
{
  "events": [{
    "eventType": "ADD_REFERENCE_AUDIO",
    "metadata": {
      "sessionId": ";1775420258353",
      "createTime": "2026-04-05T20:13:11.963Z",
      "additionalParams": {
        "REFERENCE_AUDIO_ID": {
          "@type": "type.googleapis.com/google.protobuf.StringValue",
          "value": "gacrux"
        },
        "MEDIA_GENERATION_PAYGATE_TIER": {
          "@type": "type.googleapis.com/google.protobuf.StringValue",
          "value": "PAYGATE_TIER_TWO"
        }
      }
    }
  }]
}
```

---

## 7. Image Upload with C2PA Metadata

Reference images are uploaded via `POST /v1/flow/uploadImage`:

```json
{
  "clientContext": {
    "projectId": "e1448f85-6951-4913-bc1d-2c44947f574e",
    "tool": "PINHOLE"
  },
  "imageBytes": "/9j/4AAQSkZJRgAB..."
}
```

> **NOTE:** Uploaded images contain **C2PA (Content Credentials)** metadata:
> - Google C2PA Media Services certificates
> - `c2pa.created` action: "Created by Google Generative AI"
> - `c2pa.edited` action: "Applied imperceptible SynthID watermark"
> - Digital source type: `trainedAlgorithmicMedia`
> — This means the reference images were themselves AI-generated by Google.

---

## 8. Error: `PUBLIC_ERROR_AUDIO_FILTERED`

The captured session shows a **voice generation failure**:

```
PUBLIC_ERROR_CODE: PUBLIC_ERROR_AUDIO_FILTERED
DISPLAYED_ERROR_MESSAGE_KEY: pinhole_audio_filter_failed_error
```

This indicates Google's content safety filter rejected the audio output. The prompt was `"hi mom, hi baby"` — likely triggered an unexpected content filter.

---

## 9. Voice UI Ordering Pattern

From `ADD_REFERENCE_AUDIO` event timestamps, voice picker fires events as cards become visible (user scrolls):

```
Pair 1:  achernar, achird        (20:03:13)
Pair 2:  algenib, alnilam        (20:03:21)
Pair 3:  autonoe, callirrhoe     (20:03:27)
Pair 4:  zubenelgenubi           (20:03:39)  ← end of list
Pair 5:  zephyr                  (20:03:46)
---
Pair 6:  aoede                   (20:12:25)  ← user scrolled back
Pair 7:  autonoe, erinome        (20:12:55)
Pair 8:  enceladus, iapetus      (20:13:04)
Pair 9:  gacrux, kore            (20:13:11)
---
Session 3 (20:44+): Full traversal with new voices:
         algieba, aoede               (20:44:23)
         callirrhoe, charon, despina  (20:45:14)
         fenrir                       (20:45:29)
```

UI = scrollable **virtuoso list** with 30 items (data-index 0–29), alphabetically sorted.

---

## 10. Full Voice Index (UI Order)

| Index | Voice ID | Gender | Tone | Pitch |
|---|---|---|---|---|
| 0 | `achernar` | Female | soft | mid |
| 1 | `achird` | Male | — | — |
| 2 | `algenib` | Male | — | — |
| 3 | `algieba` | Female | — | — |
| 4 | `alnilam` | Male | — | — |
| 5 | `aoede` | Female | — | — |
| 6 | `autonoe` | — | — | — |
| 7 | `callirrhoe` | Female | — | — |
| 8 | `charon` | Male | — | — |
| 9 | `despina` | — | — | — |
| 10 | `enceladus` | Male | — | — |
| 11 | `erinome` | Female | — | — |
| 12 | `fenrir` | Male | — | — |
| 13 | `gacrux` | Female | mature | mid |
| 14 | `iapetus` | Male | clear | mid-low |
| 15 | `kore` | Female | firm | mid |
| 16 | `laomedeia` | Female | upbeat | mid-high |
| 17 | `leda` | Female | youthful | mid-high |
| 18 | `orus` | Male | firm | mid-low |
| 19 | `puck` | Male | upbeat | mid |
| 20 | `pulcherrima` | Ungendered | forward | mid-high |
| 21 | `rasalgethi` | Male | informative | mid |
| 22 | `sadachbia` | Male | lively | low |
| 23 | `sadaltager` | Male | knowledgeable | mid |
| 24 | `schedar` | Male | even | mid-low |
| 25 | `sulafat` | Female | warm | mid |
| 26 | `umbriel` | Male | smooth | lower |
| 27 | `vindemiatrix` | Female | gentle | mid |
| 28 | `zephyr` | Female | bright | mid-high |
| 29 | `zubenelgenubi` | Male | casual | mid-low |

---

## 11. API Endpoints Summary

| Purpose | Method | URL |
|---|---|---|
| Voice preview WAV | GET | `https://www.gstatic.com/aistudio/voices/samples/{Name}.wav` |
| Upload image | POST | `aisandbox-pa.googleapis.com/v1/flow/uploadImage` |
| Generate video | POST | `labs.google/fx/api/trpc/general.generateVideo` |
| Poll status | POST | `aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus` |
| Update workflow | PATCH | `aisandbox-pa.googleapis.com/v1/flowWorkflows/{id}` |
| Log events (legacy) | POST | `aisandbox-pa.googleapis.com/v1:batchLog` |
| Log events (modern) | POST | `aisandbox-pa.googleapis.com/v1/flow:batchLogFrontendEvents` |
| Check credits | GET | `aisandbox-pa.googleapis.com/v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY` |
| Fetch recommendations | POST | `aisandbox-pa.googleapis.com/v1:fetchUserRecommendations` |
| User acknowledgement | GET | `labs.google/fx/api/trpc/general.fetchUserAcknowledgement` |

---

## 12. Integration Code for VEO Pro Max

```python
R2V_VOICES = {
    # ─── FEMALE ─────────────────────────────────────
    "achernar":      {"gender": "female", "tone": "soft",      "pitch": "mid"},
    "algieba":       {"gender": "female", "tone": "",          "pitch": ""},
    "aoede":         {"gender": "female", "tone": "",          "pitch": ""},
    "callirrhoe":    {"gender": "female", "tone": "",          "pitch": ""},
    "erinome":       {"gender": "female", "tone": "",          "pitch": ""},
    "gacrux":        {"gender": "female", "tone": "mature",    "pitch": "mid"},
    "kore":          {"gender": "female", "tone": "firm",      "pitch": "mid"},
    "laomedeia":     {"gender": "female", "tone": "upbeat",    "pitch": "mid-high"},
    "leda":          {"gender": "female", "tone": "youthful",  "pitch": "mid-high"},
    "sulafat":       {"gender": "female", "tone": "warm",      "pitch": "mid"},
    "vindemiatrix":  {"gender": "female", "tone": "gentle",    "pitch": "mid"},
    "zephyr":        {"gender": "female", "tone": "bright",    "pitch": "mid-high"},
    # ─── MALE ───────────────────────────────────────
    "achird":        {"gender": "male",   "tone": "",              "pitch": ""},
    "algenib":       {"gender": "male",   "tone": "",              "pitch": ""},
    "alnilam":       {"gender": "male",   "tone": "",              "pitch": ""},
    "charon":        {"gender": "male",   "tone": "",              "pitch": ""},
    "enceladus":     {"gender": "male",   "tone": "",              "pitch": ""},
    "fenrir":        {"gender": "male",   "tone": "",              "pitch": ""},
    "iapetus":       {"gender": "male",   "tone": "clear",         "pitch": "mid-low"},
    "orus":          {"gender": "male",   "tone": "firm",           "pitch": "mid-low"},
    "puck":          {"gender": "male",   "tone": "upbeat",         "pitch": "mid"},
    "rasalgethi":    {"gender": "male",   "tone": "informative",    "pitch": "mid"},
    "sadachbia":     {"gender": "male",   "tone": "lively",         "pitch": "low"},
    "sadaltager":    {"gender": "male",   "tone": "knowledgeable",  "pitch": "mid"},
    "schedar":       {"gender": "male",   "tone": "even",           "pitch": "mid-low"},
    "umbriel":       {"gender": "male",   "tone": "smooth",         "pitch": "lower"},
    "zubenelgenubi": {"gender": "male",   "tone": "casual",         "pitch": "mid-low"},
    # ─── OTHER ──────────────────────────────────────
    "autonoe":       {"gender": "unknown",    "tone": "",        "pitch": ""},
    "despina":       {"gender": "unknown",    "tone": "",        "pitch": ""},
    "pulcherrima":   {"gender": "ungendered", "tone": "forward", "pitch": "mid-high"},
}

def get_preview_url(voice_id: str) -> str:
    """Get gstatic.com WAV preview URL for a voice."""
    name = voice_id[0].upper() + voice_id[1:]
    return f"https://www.gstatic.com/aistudio/voices/samples/{name}.wav"

def build_r2v_payload(prompt: str, voice_id: str, image_ids: list, aspect: str = "landscape", seed: int = None):
    """Build R2V generation payload."""
    import random
    return {
        "json": {
            "resolution": None,
            "aspectRatio": f"VIDEO_ASPECT_RATIO_{aspect.upper()}",
            "seed": seed or random.randint(1000, 99999),
            "textInput": {
                "structuredPrompt": {
                    "parts": [{"text": prompt}]
                }
            },
            "videoModelKey": f"veo_3_1_r2v_fast_{aspect}_ultra_relaxed",
            "metadata": {"workflowId": None, "collectionId": None},
            "referenceImages": [
                {"mediaId": mid, "cropCoordinates": None, "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"}
                for mid in image_ids
            ],
            "referenceAudio": [{"mediaId": voice_id}]
        },
        "meta": {
            "values": {
                "resolution": ["undefined"],
                "metadata.workflowId": ["undefined"],
                "metadata.collectionId": ["undefined"],
                **{f"referenceImages.{i}.cropCoordinates": ["undefined"] for i in range(len(image_ids))}
            }
        }
    }
```

---

## 13. Key Integration Takeaways

| Aspect | Detail |
|---|---|
| **Total voices** | 30 (12 Female, 13 Male, 1 Ungendered, 4 unknown gender) |
| **Voice ID format** | Plain lowercase string (star/moon names) |
| **Preview URL** | `https://www.gstatic.com/aistudio/voices/samples/{PascalCase}.wav` — **public, no auth** |
| **Model key** | `veo_3_1_r2v_{speed}_{aspect}_{quality}_{priority}` |
| **referenceAudio** | Array of `{"mediaId": "voice_name"}` |
| **referenceImages** | Uses `IMAGE_USAGE_TYPE_ASSET` (not `STYLE_REFERENCE`) |
| **Paygate tier** | All voices: `PAYGATE_TIER_TWO` (premium) |
| **TTS mapping** | Same voice names as Google Cloud TTS / Gemini-TTS |
| **UI component** | Virtuoso scrollable list, 30 items, alphabetically sorted |
| **Credits API key** | `AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY` |
