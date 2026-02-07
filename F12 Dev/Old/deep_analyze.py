import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

def search_json(data, search_term, path=""):
    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{path}.{k}"
            if search_term.lower() in k.lower():
                print(f"[MATCH KEY] {new_path}: {v}")
            if isinstance(v, (str, int, float, bool)) and search_term.lower() in str(v).lower():
                print(f"[MATCH VAL] {new_path}: {v}")
            search_json(v, search_term, new_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            search_json(item, search_term, f"{path}[{i}]")

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for entry in entries:
        url = entry['request']['url']
        text = entry['response']['content'].get('text', '')
        
        if 'labs.google/fx/tools/flow' in url and text:
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
                    
                    print("--- Searching for specific terms ---")
                    terms = ["plan", "subscri", "tier", "quota", "credit", "limit", "ultra", "pro", "account"]
                    for term in terms:
                        print(f"\nSearching for: {term}")
                        search_json(data, term)
                    break

except Exception as e:
    print(f"Error: {e}")
