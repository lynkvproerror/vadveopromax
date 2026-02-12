import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

def recursive_search(data, target_keys, path=""):
    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{path}.{k}" if path else k
            if any(t in k.lower() for t in target_keys):
                print(f"Found Key '{k}' at {new_path}: {v}")
            recursive_search(v, target_keys, new_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            recursive_search(item, target_keys, f"{path}[{i}]")

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for i, entry in enumerate(entries):
        url = entry['request']['url']
        text = entry['response']['content'].get('text', '')
        
        if 'labs.google/fx/tools/flow' in url and text:
            # Decode if base64
            if not text.strip().startswith('<'):
                try:
                    text = base64.b64decode(text).decode('utf-8')
                except:
                    pass
            
            if '__NEXT_DATA__' in text:
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
                if match:
                    json_str = match.group(1)
                    data = json.loads(json_str)
                    
                    print("\n--- Session User Data ---")
                    session = data.get('props', {}).get('pageProps', {}).get('session', {})
                    print(json.dumps(session, indent=2))
                    
                    print("\n--- Searching for Plan/Subscription Keys ---")
                    recursive_search(data, ['plan', 'subscri', 'tier', 'quota', 'entitle', 'feature', 'credit', 'payment'])
                    
                    break

except Exception as e:
    print(f"Error: {e}")
