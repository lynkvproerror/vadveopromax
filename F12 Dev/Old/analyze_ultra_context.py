import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for entry in entries:
        if 'labs.google/fx/tools/flow' in entry['request']['url']:
            text = entry['response']['content'].get('text', '')
            if text and not text.strip().startswith('<'):
                try:
                    text = base64.b64decode(text).decode('utf-8')
                except:
                    pass
            
            print("--- HTML Analysis ---")
            
            # Find all ULTRA occurrences
            indices = [m.start() for m in re.finditer('ULTRA', text)]
            print(f"Found {len(indices)} occurrences of 'ULTRA' in HTML.")
            for idx in indices:
                context = text[max(0, idx-50):min(len(text), idx+50)].replace('\n', ' ')
                print(f"Context: ...{context}...")
                
            # Parse JSON
            if '__NEXT_DATA__' in text:
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
                if match:
                    json_str = match.group(1)
                    data = json.loads(json_str)
                    
                    print("\n--- JSON Analysis ---")
                    session = data.get('props', {}).get('pageProps', {}).get('session', {})
                    user = session.get('user', {})
                    
                    print(f"User Name: {user.get('name')}")
                    print(f"User Email: {user.get('email')}")
                    
                    # Search specifically for plan fields
                    def recursive_search(d, path=""):
                         if isinstance(d, dict):
                            for k,v in d.items():
                                if "ultra" in str(v).lower() or "pro" in str(v).lower():
                                     if "url" not in k.lower() and "image" not in k.lower(): # exclude images/urls
                                        print(f"JSON Match: {path}.{k} = {v}")
                                recursive_search(v, f"{path}.{k}")
                         elif isinstance(d, list):
                            for i, item in enumerate(d):
                                recursive_search(item, f"{path}[{i}]")
                    
                    recursive_search(data)

except Exception as e:
    print(f"Error: {e}")
