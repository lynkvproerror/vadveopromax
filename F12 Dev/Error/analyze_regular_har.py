import json

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

    print("HAR Loaded. Searching for account status...")
    recursive_search(har_data, ["userPaygateTier", "sku", "credits"])
    print("Search complete.")

except Exception as e:
    print(f"Error: {e}")
