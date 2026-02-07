import json

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro haay Thuong.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    for i, entry in enumerate(entries):
        if 'aisandbox' in entry['request']['url']:
            print(f"Index {i}: {entry['request']['url']}")

except Exception as e:
    print(f"Error: {e}")
