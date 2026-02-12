import json

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    if len(entries) > 1:
        entry = entries[1]
        print(f"Entry 1 URL: {entry['request']['url']}")
        print(f"Content: {entry['response']['content']['text']}")
    else:
        print("Entry 1 not found.")

except Exception as e:
    print(f"Error: {e}")
