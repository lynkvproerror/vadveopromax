import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

def find_paths(data, target_terms, path="", found_paths=None):
    if found_paths is None:
        found_paths = []
    
    if isinstance(data, dict):
        for k, v in data.items():
            current_path = f"{path}.{k}"
            # Check key
            if any(term in k.lower() for term in target_terms):
                print(f"[KEY MATCH] {current_path}: {v}")
                found_paths.append((current_path, v))
            
            # Check value (if string)
            if isinstance(v, str) and any(term in v.lower() for term in target_terms):
                 # Avoid printing huge text blocks
                if len(v) < 200:
                    print(f"[VAL MATCH] {current_path}: {v}")
                    found_paths.append((current_path, v))
            
            find_paths(v, target_terms, current_path, found_paths)
            
    elif isinstance(data, list):
        for i, item in enumerate(data):
            find_paths(item, target_terms, f"{path}[{i}]", found_paths)
            
    return found_paths

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for entry in entries:
        url = entry['request']['url']
        if 'labs.google/fx/tools/flow' in url:
            text = entry['response']['content'].get('text', '')
            if not text: continue
            
            # Decode if needed
            if not text.strip().startswith('<'):
                try:
                    text = base64.b64decode(text).decode('utf-8')
                except:
                    pass
            
            if '__NEXT_DATA__' in text:
                print(f"\nAnalyzing response from {url}")
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
                if match:
                    json_str = match.group(1)
                    data = json.loads(json_str)
                    
                    # Search specifically for plan indicators
                    terms = ["tier", "plan", "pay", "sub", "allow", "capab", "limit", "balanc", "credit", "quota", "premium"]
                    find_paths(data, terms)
                    
except Exception as e:
    print(f"Error: {e}")
