import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for i, entry in enumerate(entries):
        url = entry['request']['url']
        if 'labs.google' in url:
            mime = entry['response']['content'].get('mimeType', 'unknown')
            text = entry['response']['content'].get('text', '')
            size = entry['response']['content'].get('size', 0)
            status = entry['response']['status']
            
            print(f"[{i}] {status} {url} (Mime: {mime}, Size: {size}, TextLen: {len(text)})")
            
            if size > 0 and text:
                if not text.strip().startswith('<'):
                    try:
                        decoded = base64.b64decode(text).decode('utf-8')
                        text = decoded
                        print("  (Decoded base64)")
                    except:
                        pass
                
                if "ULTRA" in text:
                    print("  !!! FOUND 'ULTRA' IN CONTENT !!!")
                    start = text.find("ULTRA")
                    print(f"  Context: ...{text[start-50:start+50]}...")
                
                if "sc-92e84304-9" in text:
                    print("  !!! FOUND CLASS 'sc-92e84304-9' !!!")

                if '__NEXT_DATA__' in text:
                    print("  !!! FOUND __NEXT_DATA__ !!!")
                    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
                    if match:
                        json_str = match.group(1)
                        data = json.loads(json_str)
                         # Look for capabilities or flags in user object or props
                        def search_json(d, path=""):
                            if isinstance(d, dict):
                                for k,v in d.items():
                                    if k == "user" and isinstance(v, dict):
                                        print(f"  User Object Keys: {v.keys()}")
                                        print(f"  User Data: {v}")
                                    search_json(v, f"{path}.{k}")
                            elif isinstance(d, list):
                                for item in d:
                                    search_json(item, path)
                        
                        search_json(data)

except Exception as e:
    print(f"Error: {e}")
