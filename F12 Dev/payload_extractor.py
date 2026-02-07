"""
HAR Payload Extractor - Extract exact JSON payloads from HAR files
For creating PAYLOAD_SCHEMAS.md documentation
"""
import json
import os
import glob
from urllib.parse import urlparse

# Target endpoints we need payloads for
TARGETS = {
    "T2V": "batchAsyncGenerateVideoText",
    "I2V_SINGLE": "batchAsyncGenerateVideoStartImage",  # Or just imageInput in payload
    "F2V_DUAL": "batchAsyncGenerateVideoStartAndEndImage",
    "R2V": "batchAsyncGenerateVideoReferenceImages",  # Or referenceImages in payload
    "T2I": "batchGenerateImages",
    "VIDEO_UPSCALE": "batchAsyncGenerateVideoUpsampleVideo",
    "IMAGE_UPSCALE": "upsampleImage",
    "STATUS_CHECK": "batchCheckAsyncVideoGenerationStatus",
    "UPLOAD_IMAGE": "uploadUserImage",
    "DOWNLOAD": "/v1/media/",
}

def extract_payloads():
    base_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev"
    files = []
    files.extend(glob.glob(os.path.join(base_dir, "New", "*.har")))
    files.extend(glob.glob(os.path.join(base_dir, "Old", "*.har")))
    
    found = {k: None for k in TARGETS.keys()}
    
    for f_path in files:
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries = data.get('log', {}).get('entries', [])
            for entry in entries:
                req = entry.get('request', {})
                url = req.get('url', '')
                method = req.get('method', '')
                
                for key, pattern in TARGETS.items():
                    if found[key] is not None:
                        continue  # Already found
                    
                    if pattern in url:
                        post_data = req.get('postData', {})
                        if post_data and 'text' in post_data:
                            try:
                                payload = json.loads(post_data['text'])
                                found[key] = {
                                    "url": url,
                                    "method": method,
                                    "payload": payload,
                                    "source": os.path.basename(f_path)
                                }
                            except:
                                pass
                        elif method == "GET" and key == "DOWNLOAD":
                            # For GET requests, capture query params
                            found[key] = {
                                "url": url,
                                "method": method,
                                "payload": None,
                                "source": os.path.basename(f_path)
                            }
        except:
            pass

    # Output results
    output = []
    output.append("# PAYLOAD EXTRACTION RESULTS\n")
    
    for key, data in found.items():
        output.append(f"\n## {key}\n")
        if data:
            output.append(f"**Source:** `{data['source']}`\n")
            output.append(f"**URL:** `{data['url'][:100]}...`\n")
            output.append(f"**Method:** `{data['method']}`\n")
            if data['payload']:
                output.append("```json\n")
                output.append(json.dumps(data['payload'], indent=2, ensure_ascii=False)[:3000])
                output.append("\n```\n")
            else:
                output.append("*No POST payload (GET request)*\n")
        else:
            output.append("**NOT FOUND** - May need different search pattern\n")
    
    with open("payload_extraction_results.md", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    
    print("Extraction complete. Results in payload_extraction_results.md")

if __name__ == "__main__":
    extract_payloads()
