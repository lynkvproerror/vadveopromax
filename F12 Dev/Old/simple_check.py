import json

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Full tạo ảnh.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    for entry in har_data['log']['entries']:
        if 'aisandbox-pa.googleapis.com' in entry['request']['url']:
            headers = {h['name'].lower(): h['value'] for h in entry['request']['headers']}
            print(f"Request: {entry['request']['url']}")
            print(f"Auth Header: {'YES' if 'authorization' in headers else 'NO'}")
            print(f"Cookie Header: {'YES' if 'cookie' in headers else 'NO'}")
            break # Just check the first one

except Exception as e:
    print(f"Error: {e}")
