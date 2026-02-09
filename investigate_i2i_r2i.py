"""
Deep investigation of I2I (Image-to-Image) and R2I (Reference-to-Image) in ALL HAR files.
Goals:
1. Find all batchGenerateImages calls and check for imageInputs (I2I vs T2I)
2. Find any R2I-related calls or feature flags
3. Find any Whisk generation calls (BACKBONE tool usage)
4. Find any undocumented generation modes
"""
import json, os, glob, re
from collections import defaultdict

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
har_files = sorted(glob.glob(os.path.join(HAR_DIR, "*.har")))

lines = []
lines.append("=" * 90)
lines.append("I2I / R2I / GENERATION MODES — FULL HAR INVESTIGATION")
lines.append(f"Total HAR files: {len(har_files)}")
lines.append("=" * 90)

# ============================================================
# 1. ALL batchGenerateImages calls — T2I vs I2I
# ============================================================
lines.append("\n\n### 1. batchGenerateImages — T2I vs I2I CLASSIFICATION")
lines.append("-" * 60)

image_gen_calls = []
for hf in har_files:
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    for entry in data.get('log', {}).get('entries', []):
        url = entry.get('request', {}).get('url', '')
        if 'batchGenerateImages' not in url:
            continue
        body_text = entry.get('request', {}).get('postData', {}).get('text', '')
        try:
            body = json.loads(body_text)
        except:
            body = {}
        
        has_image_inputs = 'imageInputs' in body_text
        has_image_input_field = 'imageInput' in body_text
        tool = ''
        if 'clientContext' in body:
            tool = body.get('clientContext', {}).get('tool', '')
        elif '"tool"' in body_text:
            import re
            m = re.search(r'"tool"\s*:\s*"([^"]+)"', body_text)
            if m:
                tool = m.group(1)
        
        mode = 'I2I' if (has_image_inputs or has_image_input_field) else 'T2I'
        
        # Extract prompt snippet
        prompt = ''
        if 'prompt' in body:
            prompt = str(body.get('prompt', ''))[:80]
        elif '"prompt"' in body_text:
            m = re.search(r'"prompt"\s*:\s*"([^"]{0,80})', body_text)
            if m:
                prompt = m.group(1)
        
        image_gen_calls.append({
            'file': fname,
            'mode': mode,
            'tool': tool,
            'has_imageInputs': has_image_inputs,
            'has_imageInput': has_image_input_field,
            'prompt_snippet': prompt,
            'body_len': len(body_text),
            'url_path': url.split('?')[0].split('googleapis.com')[-1],
        })

t2i_count = sum(1 for c in image_gen_calls if c['mode'] == 'T2I')
i2i_count = sum(1 for c in image_gen_calls if c['mode'] == 'I2I')
lines.append(f"\nTotal batchGenerateImages calls: {len(image_gen_calls)}")
lines.append(f"  T2I (no imageInputs): {t2i_count}")
lines.append(f"  I2I (has imageInputs): {i2i_count}")

for c in image_gen_calls:
    lines.append(f"  [{c['mode']}] {c['file'][:45]:45s} | tool={c['tool']:10s} | imageInputs={c['has_imageInputs']} | body={c['body_len']}B | prompt={c['prompt_snippet'][:50]}")

# ============================================================
# 2. ALL video generation endpoints — classify modes
# ============================================================
lines.append("\n\n### 2. ALL VIDEO GENERATION ENDPOINTS — MODE CLASSIFICATION")
lines.append("-" * 60)

video_gen_calls = defaultdict(list)
for hf in har_files:
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    for entry in data.get('log', {}).get('entries', []):
        url = entry.get('request', {}).get('url', '')
        if 'batchAsync' not in url:
            continue
        # Classify
        if 'VideoText' in url:
            mode = 'T2V'
        elif 'StartAndEndImage' in url:
            mode = 'F2V (S+E)'
        elif 'StartImage' in url:
            mode = 'I2V'
        elif 'ReferenceImages' in url:
            mode = 'R2V'
        elif 'UpsampleVideo' in url:
            mode = 'Upscale'
        else:
            mode = 'Unknown'
        video_gen_calls[mode].append(fname)

for mode in sorted(video_gen_calls.keys()):
    files = video_gen_calls[mode]
    unique_files = sorted(set(files))
    lines.append(f"\n  {mode}: {len(files)} calls across {len(unique_files)} files")
    for uf in unique_files[:5]:
        lines.append(f"    - {uf}")
    if len(unique_files) > 5:
        lines.append(f"    ... and {len(unique_files)-5} more files")

# ============================================================
# 3. R2I (Reference-to-Image) — feature flags + any calls
# ============================================================
lines.append("\n\n### 3. R2I (Reference-to-Image) — FEATURE FLAGS & CALLS")
lines.append("-" * 60)

r2i_refs = []
for hf in har_files:
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    for entry in data.get('log', {}).get('entries', []):
        url = entry.get('request', {}).get('url', '')
        body_text = entry.get('request', {}).get('postData', {}).get('text', '')
        resp_text = ''
        if entry.get('response', {}).get('content', {}).get('text'):
            resp_text = entry['response']['content']['text']
        
        if 'R2I' in body_text or 'R2I' in resp_text:
            r2i_refs.append({
                'file': fname,
                'url': url.split('?')[0][-60:],
                'in_request': 'R2I' in body_text,
                'in_response': 'R2I' in resp_text,
                'body_snippet': body_text[:200] if 'R2I' in body_text else '',
                'resp_snippet': resp_text[:300] if 'R2I' in resp_text else '',
            })

lines.append(f"  Total R2I references: {len(r2i_refs)}")
for r in r2i_refs:
    lines.append(f"  [{r['file'][:40]:40s}] {r['url']}")
    if r['in_request']:
        lines.append(f"    Request: {r['body_snippet'][:150]}")
    if r['in_response']:
        lines.append(f"    Response: {r['resp_snippet'][:200]}")

# ============================================================
# 4. BACKBONE (Whisk) tool usage — any generation calls
# ============================================================
lines.append("\n\n### 4. BACKBONE (Whisk) — GENERATION CALLS")
lines.append("-" * 60)

backbone_calls = []
for hf in har_files:
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    for entry in data.get('log', {}).get('entries', []):
        body_text = entry.get('request', {}).get('postData', {}).get('text', '')
        url = entry.get('request', {}).get('url', '')
        if 'BACKBONE' in body_text and 'aisandbox-pa' in url:
            backbone_calls.append({
                'file': fname,
                'url': url.split('?')[0][-60:],
                'body_snippet': body_text[:300],
            })

lines.append(f"  Total BACKBONE calls to aisandbox-pa: {len(backbone_calls)}")
for b in backbone_calls:
    lines.append(f"  [{b['file'][:40]:40s}] {b['url']}")
    lines.append(f"    Body: {b['body_snippet'][:200]}")

# ============================================================
# 5. ANY undocumented endpoints
# ============================================================
lines.append("\n\n### 5. ALL UNIQUE aisandbox-pa ENDPOINTS (for completeness)")
lines.append("-" * 60)

all_endpoints = defaultdict(int)
for hf in har_files:
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    for entry in data.get('log', {}).get('entries', []):
        url = entry.get('request', {}).get('url', '')
        if 'aisandbox-pa' in url:
            path = url.split('?')[0].split('googleapis.com')[-1]
            method = entry.get('request', {}).get('method', '')
            all_endpoints[f"{method} {path}"] += 1

for ep in sorted(all_endpoints.keys()):
    lines.append(f"  {ep:80s} | {all_endpoints[ep]:4d} calls")

# ============================================================
# SUMMARY
# ============================================================
lines.append("\n\n### SUMMARY")
lines.append("=" * 60)
lines.append(f"Image generation (batchGenerateImages): {len(image_gen_calls)} calls")
lines.append(f"  → T2I: {t2i_count} | I2I: {i2i_count}")
lines.append(f"Video generation modes:")
for mode in sorted(video_gen_calls.keys()):
    lines.append(f"  → {mode}: {len(video_gen_calls[mode])} calls")
lines.append(f"R2I references: {len(r2i_refs)}")
lines.append(f"BACKBONE generation calls: {len(backbone_calls)}")
lines.append(f"Unique REST endpoints: {len(all_endpoints)}")

output = "\n".join(lines)
print(output)

with open(r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\i2i_r2i_investigation.txt", 'w', encoding='utf-8') as f:
    f.write(output)
print(f"\n\nSaved to i2i_r2i_investigation.txt")
