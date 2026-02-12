import json
import base64

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro haay Thuong.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for i in [6, 7]:
        if i < len(entries):
            entry = entries[i]
            print(f"\nEntry {i} URL: {entry['request']['url']}")
            text = entry['response']['content'].get('text', '')
            if text:
                 # Try decode
                try:
                    decoded = base64.b64decode(text).decode('utf-8')
                    print(f"Content (Decoded): {decoded}")
                except:
                     print(f"Content (Raw): {text[:500]}") # Print first 500 chars if not b64

except Exception as e:
    print(f"Error: {e}")
