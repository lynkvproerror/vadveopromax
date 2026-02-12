import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for entry in entries:
        url = entry['request']['url']
        if 'labs.google' in url:
            print(f"Checking URL: {url}")
            text = entry['response']['content'].get('text', '')
            
            if not text:
                print("No text content.")
                continue
                
            # Decode if base64
            # Heuristic: if it doesn't start with < and looks like b64
            if not text.strip().startswith('<'):
                try:
                    decoded = base64.b64decode(text).decode('utf-8')
                    text = decoded
                    print("Decoded base64 content.")
                except:
                    pass

            # Search for "ULTRA" in HTML
            if "ULTRA" in text:
                print("Found 'ULTRA' in HTML body!")
                # Print context
                start = text.find("ULTRA")
                print(f"Context: ...{text[start-50:start+50]}...")
            
            # Search for class "sc-92e84304-9"
            if "sc-92e84304-9" in text:
                print("Found class 'sc-92e84304-9' in HTML body!")
            
            # Re-check JSON data
            if '__NEXT_DATA__' in text:
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
                if match:
                    json_str = match.group(1)
                    if "ULTRA" in json_str:
                        print("Found 'ULTRA' in __NEXT_DATA__ JSON!")
                        start = json_str.find("ULTRA")
                        print(f"JSON Context: ...{json_str[start-50:start+50]}...")

except Exception as e:
    print(f"Error: {e}")
