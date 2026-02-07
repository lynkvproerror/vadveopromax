
import json
import os
import glob
from urllib.parse import urlparse

def analyze_har(file_path):
    print(f"\n--- Analyzing: {os.path.basename(file_path)} ---")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    entries = data.get('log', {}).get('entries', [])
    for entry in entries:
        req = entry.get('request', {})
        url = req.get('url', '')
        
        if 'aisandbox-pa.googleapis.com' in url or 'generateVideo' in url or 'uploadUserImage' in url or 'upsample' in url.lower():
            method = req.get('method')
            print(f"URL: {url}")
            print(f"Method: {method}")
            
            if method == 'POST':
                post_data = req.get('postData', {})
                text = post_data.get('text', '')
                if text:
                    try:
                        # Try to parse valid JSON
                        json_body = json.loads(text)
                        
                        # recursively find 'model' key
                        def find_keys(obj, target_key):
                            results = []
                            if isinstance(obj, dict):
                                for k, v in obj.items():
                                    if k == target_key:
                                        results.append(v)
                                    if isinstance(v, (dict, list)):
                                        results.extend(find_keys(v, target_key))
                            elif isinstance(obj, list):
                                for item in obj:
                                    results.extend(find_keys(item, target_key))
                            return results

                        models = find_keys(json_body, 'model')
                        aspects = find_keys(json_body, 'aspectRatio')
                        
                        if models:
                            print(f"  > Models found: {models}")
                        if aspects:
                            print(f"  > Aspect Ratios: {aspects}")
                            
                        # Dump snippets of interesting parts
                        print(f"  > Payload Snippet: {text[:200]}...")
                        
                    except json.JSONDecodeError:
                        print(f"  > Payload (Raw): {text[:200]}...")

def main():
    base_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
    har_files = glob.glob(os.path.join(base_dir, "*.har"))
    
    if not har_files:
        print("No HAR files found in New directory.")
        return

    for har in har_files:
        analyze_har(har)

if __name__ == "__main__":
    main()
