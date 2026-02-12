import json

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    if len(entries) > 1:
        print(f"URL: {entries[1]['request']['url']}")
except Exception:
    pass
