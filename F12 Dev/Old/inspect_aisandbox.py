import json
import base64

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro haay Thuong.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for i in [1, 3, 4, 5]:
        if i < len(entries):
            entry = entries[i]
            print(f"\n--- Entry {i} ---")
            print(f"URL: {entry['request']['url']}")
            
            text = entry['response']['content'].get('text', '')
            if text:
                 # Check if base64 (heuristic)
                is_b64 = not text.strip().startswith('{') and not text.strip().startswith('<')
                
                if is_b64:
                    try:
                        decoded = base64.b64decode(text).decode('utf-8')
                        print(f"Content (Decoded): {decoded}")
                    except:
                        print(f"Content (Raw): {text[:200]}")
                else:
                    print(f"Content (Raw): {text}")

except Exception as e:
    print(f"Error: {e}")
