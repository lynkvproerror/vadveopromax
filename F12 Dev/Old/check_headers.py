import json

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Full tạo ảnh.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    print(f"Total entries: {len(entries)}")
    
    found_api = False
    for entry in entries:
        url = entry['request']['url']
        if 'aisandbox-pa.googleapis.com' in url:
            found_api = True
            print(f"\nAPI Request found: {url}")
            print("Headers:")
            headers = {h['name'].lower(): h['value'] for h in entry['request']['headers']}
            
            if 'authorization' in headers:
                print(f"- Authorization: {headers['authorization'][:20]}...")
            else:
                print("- Authorization: MISSING")
                
            if 'cookie' in headers:
                print(f"- Cookie: {headers['cookie'][:20]}... (Present)")
            else:
                print("- Cookie: MISSING")
            
            # Check for other auth related headers
            for k in headers:
                if 'auth' in k or 'token' in k or 'browser' in k:
                    print(f"- {k}: {headers[k][:50]}...")

    if not found_api:
        print("No requests to aisandbox-pa.googleapis.com found.")

except Exception as e:
    print(f"Error: {e}")
