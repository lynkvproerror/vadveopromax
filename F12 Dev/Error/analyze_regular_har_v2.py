import json
import base64

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro haay Thuong.har"

def recursive_search(data, target_keys, path=""):
    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{path}.{k}"
            if k in target_keys:
                print(f"[MATCH] {k}: {v}")
            recursive_search(v, target_keys, new_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            recursive_search(item, target_keys, f"{path}[{i}]")

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    print(f"Total entries: {len(entries)}")
    
    for i, entry in enumerate(entries):
        text = entry['response']['content'].get('text', '')
        if text and not text.strip().startswith('<'): # Heuristic for non-HTML/XML
            try:
                decoded = base64.b64decode(text).decode('utf-8')
                # Try to parse as JSON
                try:
                    json_data = json.loads(decoded)
                    recursive_search(json_data, ["userPaygateTier", "sku", "credits"])
                except json.JSONDecodeError:
                    # If not JSON, just search string
                    if "userPaygateTier" in decoded:
                         print(f"Found 'userPaygateTier' in decoded text of entry {i}")
                         print(decoded[:200]) # Print snippet
            except Exception:
                pass
        elif text:
             # Try parsing text as JSON directly
            try:
                json_data = json.loads(text)
                recursive_search(json_data, ["userPaygateTier", "sku", "credits"])
            except:
                pass


except Exception as e:
    print(f"Error: {e}")
