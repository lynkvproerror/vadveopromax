import json

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

def recursive_search(data, target, path=""):
    if isinstance(data, dict):
        for k, v in data.items():
            new_path = f"{path}.{k}"
            if isinstance(v, str):
                if target in v:
                    # Avoid easy matches like user name if we want to confirm others
                    # But print ALL for now
                    if len(v) < 200:
                        print(f"MATCH: {new_path} = {v}")
                    else:
                        print(f"MATCH (long): {new_path} (len={len(v)})")
                        # Try to show context in long string
                        idx = v.find(target)
                        print(f"   Context: ...{v[idx-50:idx+50]}...")
            recursive_search(v, target, new_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            recursive_search(item, target, f"{path}[{i}]")

print("Loading HAR...")
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)
    print("HAR Loaded. Searching for 'ULTRA'...")
    recursive_search(har_data, "ULTRA")
    print("Search complete.")

except Exception as e:
    print(f"Error: {e}")
