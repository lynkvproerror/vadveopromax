"""
DEEP PAYLOAD STRUCTURE ANALYSIS — All Generation Modes
Phân tích cấu trúc gói tin gửi cho từng chế độ tạo nội dung.

Modes to investigate:
  VIDEO: T2V, I2V (3 sub-cases), R2V, Upscale
  IMAGE: T2I, I2I
"""
import json, os, glob, re, copy
from collections import defaultdict

HAR_DIRS = [
    r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New",
    r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\Old",
]

def load_all_hars():
    """Load all HAR files from all directories"""
    entries_with_file = []
    file_count = 0
    for d in HAR_DIRS:
        if not os.path.isdir(d):
            continue
        for hf in sorted(glob.glob(os.path.join(d, "*.har"))):
            fname = os.path.basename(hf)
            folder = os.path.basename(os.path.dirname(hf))
            try:
                with open(hf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                file_count += 1
            except Exception as e:
                continue
            for entry in data.get('log', {}).get('entries', []):
                entries_with_file.append((f"{folder}/{fname}", entry))
    return entries_with_file, file_count


def sanitize_payload(body, max_str_len=80):
    """Recursively truncate long string values for readability"""
    if isinstance(body, dict):
        result = {}
        for k, v in body.items():
            result[k] = sanitize_payload(v, max_str_len)
        return result
    elif isinstance(body, list):
        if len(body) > 3:
            return [sanitize_payload(body[0], max_str_len), f"... ({len(body)} items total)"]
        return [sanitize_payload(item, max_str_len) for item in body]
    elif isinstance(body, str) and len(body) > max_str_len:
        return body[:max_str_len] + f"... ({len(body)} chars)"
    return body


def classify_generation(url, body_text):
    """Classify the generation mode from URL and body"""
    path = url.split('?')[0]
    
    # VIDEO generation
    if 'batchAsyncGenerateVideoText' in path:
        return 'T2V'
    elif 'batchAsyncGenerateVideoStartAndEndImage' in path:
        return 'I2V_START_END'  # F2V
    elif 'batchAsyncGenerateVideoStartImage' in path:
        return 'I2V_START_ONLY'
    elif 'batchAsyncGenerateVideoReferenceImages' in path:
        return 'R2V'
    elif 'batchAsyncGenerateVideoUpsampleVideo' in path:
        return 'VIDEO_UPSCALE'
    elif 'generatePinholeGif' in path:
        return 'GIF_PREVIEW'
    
    # IMAGE generation  
    elif 'batchGenerateImages' in path:
        has_image_inputs = 'imageInputs' in body_text or 'imageInput' in body_text
        return 'I2I' if has_image_inputs else 'T2I'
    elif 'upsampleImage' in path:
        return 'IMAGE_UPSCALE'
    elif 'uploadUserImage' in path:
        return 'UPLOAD_IMAGE'
    
    return None


def extract_payload_schema(body):
    """Extract schema structure showing field names, types, and sample values"""
    if isinstance(body, dict):
        result = {}
        for k, v in body.items():
            result[k] = extract_payload_schema(v)
        return result
    elif isinstance(body, list):
        if len(body) == 0:
            return "[] (empty)"
        return [extract_payload_schema(body[0])]
    elif isinstance(body, str):
        if len(body) > 100:
            # Check if it's base64 image data
            if body.startswith('/9j/') or body.startswith('iVBOR'):
                return f"<base64_image, {len(body)} chars>"
            return f"<string, {len(body)} chars> = \"{body[:60]}...\""
        return body
    elif isinstance(body, (int, float)):
        return body
    elif isinstance(body, bool):
        return body
    elif body is None:
        return None
    return str(body)


def main():
    entries, file_count = load_all_hars()
    
    lines = []
    lines.append("=" * 100)
    lines.append("DEEP PAYLOAD STRUCTURE ANALYSIS — ALL GENERATION MODES")
    lines.append(f"Total HAR files scanned: {file_count} (from {len(HAR_DIRS)} directories)")
    lines.append(f"Total entries scanned: {len(entries)}")
    lines.append("=" * 100)
    
    # Classify all generation calls
    gen_calls = defaultdict(list)
    
    for source_file, entry in entries:
        url = entry.get('request', {}).get('url', '')
        method = entry.get('request', {}).get('method', '')
        body_text = entry.get('request', {}).get('postData', {}).get('text', '')
        
        mode = classify_generation(url, body_text)
        if mode is None:
            continue
        
        try:
            body = json.loads(body_text) if body_text else {}
        except:
            body = {'_raw_body': body_text[:200] if body_text else '(empty)'}
        
        # Get response
        resp_text = entry.get('response', {}).get('content', {}).get('text', '')
        try:
            resp = json.loads(resp_text) if resp_text else {}
        except:
            resp = {}
        
        status = entry.get('response', {}).get('status', 0)
        path = url.split('?')[0].split('googleapis.com')[-1] if 'googleapis.com' in url else url.split('?')[0][-80:]
        
        gen_calls[mode].append({
            'file': source_file,
            'path': path,
            'method': method,
            'body': body,
            'body_text': body_text,
            'response': resp,
            'status': status,
        })
    
    # ========================================================
    # Report for each mode
    # ========================================================
    mode_order = [
        ('T2V', 'Text-to-Video', 'batchAsyncGenerateVideoText'),
        ('I2V_START_ONLY', 'Image-to-Video (Start Image Only)', 'batchAsyncGenerateVideoStartImage'),
        ('I2V_START_END', 'Image-to-Video (Start + End Image = F2V)', 'batchAsyncGenerateVideoStartAndEndImage'),
        ('R2V', 'Reference-to-Video (Ingredients)', 'batchAsyncGenerateVideoReferenceImages'),
        ('VIDEO_UPSCALE', 'Video Upscale', 'batchAsyncGenerateVideoUpsampleVideo'),
        ('GIF_PREVIEW', 'GIF Preview', 'generatePinholeGif'),
        ('T2I', 'Text-to-Image', 'batchGenerateImages (no imageInputs)'),
        ('I2I', 'Image-to-Image', 'batchGenerateImages (with imageInputs)'),
        ('IMAGE_UPSCALE', 'Image Upscale', 'upsampleImage'),
        ('UPLOAD_IMAGE', 'Upload Image', 'uploadUserImage'),
    ]
    
    for mode_key, mode_name, endpoint in mode_order:
        calls = gen_calls.get(mode_key, [])
        lines.append(f"\n\n{'='*100}")
        lines.append(f"### {mode_name}")
        lines.append(f"    Endpoint: POST {endpoint}")
        lines.append(f"    Total calls: {len(calls)}")
        
        if not calls:
            lines.append(f"    ⚠️ KHÔNG CÓ TRONG HAR DATA — Endpoint tồn tại nhưng chưa ghi nhận request")
            unique_files = set()
        else:
            unique_files = sorted(set(c['file'] for c in calls))
            lines.append(f"    Files: {len(unique_files)}")
            for uf in unique_files:
                lines.append(f"      - {uf}")
        
        if not calls:
            lines.append(f"    (Showing expected structure from documentation)")
            continue
        
        # Show FIRST call as representative payload
        lines.append(f"\n    --- REPRESENTATIVE REQUEST PAYLOAD (call #1) ---")
        rep = calls[0]
        schema = extract_payload_schema(rep['body'])
        lines.append(f"    File: {rep['file']}")
        lines.append(f"    Path: {rep['path']}")
        lines.append(f"    Body size: {len(rep['body_text'])} bytes")
        lines.append(f"    Status: {rep['status']}")
        lines.append(f"\n    Payload schema:")
        lines.append(json.dumps(schema, indent=4, ensure_ascii=False))
        
        # Show SANITIZED full payload (truncated strings)
        lines.append(f"\n    --- SANITIZED FULL PAYLOAD ---")
        sanitized = sanitize_payload(rep['body'])
        lines.append(json.dumps(sanitized, indent=4, ensure_ascii=False))
        
        # If there are multiple calls, show field-level comparison
        if len(calls) > 1:
            lines.append(f"\n    --- FIELD COMPARISON ACROSS {len(calls)} CALLS ---")
            # Compare top-level keys
            all_keys = set()
            for c in calls:
                if isinstance(c['body'], dict):
                    all_keys.update(c['body'].keys())
            
            for key in sorted(all_keys):
                values = []
                for c in calls:
                    if isinstance(c['body'], dict):
                        v = c['body'].get(key)
                        if isinstance(v, str) and len(v) > 50:
                            values.append(f"<{len(v)} chars>")
                        elif isinstance(v, dict):
                            values.append(f"<dict {len(v)} keys>")
                        elif isinstance(v, list):
                            values.append(f"<list {len(v)} items>")
                        else:
                            values.append(str(v)[:50] if v is not None else "MISSING")
                    else:
                        values.append("N/A")
                
                unique_vals = set(values)
                if len(unique_vals) == 1:
                    lines.append(f"    {key:30s} = CONSTANT: {values[0]}")
                else:
                    lines.append(f"    {key:30s} = VARIES:")
                    for i, v in enumerate(values[:5]):
                        lines.append(f"      call[{i}]: {v}")
                    if len(values) > 5:
                        lines.append(f"      ... ({len(values) - 5} more)")
        
        # Show response structure
        if rep['response'] and isinstance(rep['response'], dict):
            lines.append(f"\n    --- RESPONSE STRUCTURE ---")
            resp_schema = extract_payload_schema(rep['response'])
            lines.append(json.dumps(resp_schema, indent=4, ensure_ascii=False))

    # ========================================================
    # COMPREHENSIVE SUMMARY TABLE
    # ========================================================
    lines.append(f"\n\n{'='*100}")
    lines.append("### TỔNG HỢP — PHÂN LOẠI THEO CẤU TRÚC GÓI TIN")
    lines.append("=" * 100)
    
    lines.append(f"\n{'Mode':<25} {'Endpoint':<55} {'Calls':>5} {'Files':>5} {'Key Payload Fields'}")
    lines.append("-" * 130)
    
    for mode_key, mode_name, endpoint in mode_order:
        calls = gen_calls.get(mode_key, [])
        n_files = len(set(c['file'] for c in calls)) if calls else 0
        
        # Extract key fields
        if calls and isinstance(calls[0]['body'], dict):
            key_fields = ', '.join(sorted(calls[0]['body'].keys())[:6])
        else:
            key_fields = "(no data)"
        
        lines.append(f"{mode_name:<25} {endpoint:<55} {len(calls):>5} {n_files:>5} {key_fields}")

    output = "\n".join(lines)
    
    outpath = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\payload_structure_analysis.txt"
    with open(outpath, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(output[-3000:])  # Print last 3000 chars
    print(f"\n\nFull output saved to: {outpath}")
    print(f"Total lines: {len(lines)}")


if __name__ == '__main__':
    main()
