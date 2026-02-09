"""Extract T2V payload from new HAR files — save to file"""
import json, os

HAR_FILES = [
    r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\Text to video 1.har",
    r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\Text to video 2.har",
]

def sanitize(val, max_len=80):
    if isinstance(val, dict):
        return {k: sanitize(v, max_len) for k, v in val.items()}
    elif isinstance(val, list):
        if len(val) > 3:
            return [sanitize(val[0], max_len), f"... ({len(val)} items total)"]
        return [sanitize(item, max_len) for item in val]
    elif isinstance(val, str) and len(val) > max_len:
        return val[:max_len] + f"... ({len(val)} chars)"
    return val

lines = []

for hf in HAR_FILES:
    fname = os.path.basename(hf)
    lines.append(f"\n{'='*100}")
    lines.append(f"FILE: {fname}")
    lines.append(f"{'='*100}")
    
    with open(hf, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    entries = data.get('log', {}).get('entries', [])
    lines.append(f"Total entries: {len(entries)}")
    
    gen_keywords = [
        'batchAsyncGenerateVideo', 'batchGenerateImages', 'batchCheckAsync',
        'uploadUserImage', 'upsampleImage', 'generatePinholeGif'
    ]
    
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        method = entry.get('request', {}).get('method', '')
        
        if method != 'POST':
            continue
            
        path = url.split('?')[0]
        matched = any(kw in path for kw in gen_keywords)
        if not matched:
            continue
        
        body_text = entry.get('request', {}).get('postData', {}).get('text', '')
        resp_text = entry.get('response', {}).get('content', {}).get('text', '')
        status = entry.get('response', {}).get('status', 0)
        
        short_path = path.split('googleapis.com')[-1] if 'googleapis.com' in path else path[-80:]
        
        lines.append(f"\n--- {method} {short_path} (status: {status}) ---")
        lines.append(f"Body size: {len(body_text)} bytes")
        
        try:
            body = json.loads(body_text)
            lines.append(f"\nREQUEST PAYLOAD:")
            lines.append(json.dumps(sanitize(body), indent=2, ensure_ascii=False))
        except:
            lines.append(f"Body (raw): {body_text[:200]}")
        
        try:
            resp = json.loads(resp_text)
            lines.append(f"\nRESPONSE:")
            lines.append(json.dumps(sanitize(resp), indent=2, ensure_ascii=False))
        except:
            if resp_text:
                lines.append(f"Response (raw): {resp_text[:200]}")
            else:
                lines.append(f"Response: (empty)")

output = "\n".join(lines)
outpath = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\t2v_analysis.txt"
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(output)
print(f"Saved to {outpath}")
print(f"Total lines: {len(lines)}")
