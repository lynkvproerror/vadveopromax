# VEO Advanced Image Features

**Scope**: Nanobanana models, Image upscaling (2K/4K), C2PA metadata

---

## Model Keys

| UI Name | Model Key | Details |
|---------|-----------|---------|
| **Nanobanana** | `GEM_PIX` | Fast generation |
| **Nanobanana Pro** | `GEM_PIX_2` | Higher quality, enhanced detail |
| **Standard Image** | `IMAGEN_3_5` | Legacy/Standard |

---

## Direct Download

**Endpoint**: `GET /v1/media/{mediaId}`  
**Parameters**: `key` (API Key), `clientContext.tool: PINHOLE`  
**Use**: Original resolution download (no upscaling)

---

## Upscale Pipeline (2K & 4K)

**Endpoint**: `POST /v1/flow/upsampleImage`

**Payload**:
```json
{
  "mediaId": "CAMSJGY1ZGIxMz...",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_2K",  // or UPSAMPLE_IMAGE_RESOLUTION_4K
  "clientContext": {
    "recaptchaContext": {
      "token": "...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769880165773",
    "projectId": "f5db1342-...",
    "tool": "PINHOLE"
  }
}
```

**Response** (Synchronous):
```json
{
  "encodedImage": "/9j/4AAQSkZJRgABAQEBLAEsAAD/61cLSlAAAQ..."
}
```

**Processing Time**:
- 2K: ~3-5 seconds
- 4K: ~6-8 seconds

**Note**: Returns Base64-encoded JPEG directly (not job ID). Includes C2PA metadata.

**Decode Example**:
```python
import base64

encoded_img = response.json()["encodedImage"]
image_data = base64.b64decode(encoded_img)

with open("upscaled_image.jpg", "wb") as f:
    f.write(image_data)
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success (Base64 JPEG in `encodedImage`) |
| 400 | Invalid `mediaId` or `targetResolution` |
| 401 | Invalid auth token |
| 403 | reCAPTCHA validation failed |
| 404 | Media not found |
| 429 | Rate limit (use exponential backoff) |

---

## C2PA Metadata

All upscaled images include **C2PA (Coalition for Content Provenance and Authenticity)** metadata embedded in JPEG:

**Structure (JUMBF container)**:
- `instanceID`: Unique identifier
- `claim_generator_info`: Google C2PA Core Generator Library
- Digital signature & timestamp
- Modification history (`c2pa.opened`, `c2pa.transcoded`)

**Purpose**: Verifies image origin (Google Generative AI) and modification chain.

---

**Last Updated**: 2026-02-01  
**Source**: HAR file analysis
