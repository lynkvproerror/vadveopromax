import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"

print("Starting analysis...")
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)
    print("HAR Loaded.")

    entries = har_data['log']['entries']
    if len(entries) > 0:
        entry = entries[0]
        url = entry['request']['url']
        print(f"Entry 0 URL: {url}")
        
        text = entry['response']['content'].get('text', '')
        print(f"Text length: {len(text)}")
        
        if text:
            if not text.strip().startswith('<'):
                try:
                    text = base64.b64decode(text).decode('utf-8')
                    print("Decoded base64.")
                except:
                    print("Decode failed.")
            
            # Search for ULTRA
            print("Searching for ULTRA...")
            if "ULTRA" in text:
                print("FOUND ULTRA!")
                start = text.find("ULTRA")
                print(f"Context: {text[start-100:start+100]}")
            else:
                print("ULTRA not found in text.")

            # Search for JSON
            if '__NEXT_DATA__' in text:
                print("Found __NEXT_DATA__")
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
                if match:
                    json_str = match.group(1)
                    data = json.loads(json_str)
                    
                    # Dump user object
                    session = data.get('props', {}).get('pageProps', {}).get('session', {})
                    print(f"Session User: {session.get('user')}")
                    
                    # Search specifically for the button text source
                    # The user showed <div ...>ULTRA</div>. This might come from a variable like 'planName' or similar.
                    # Or it might be the 'name' field.
                    
                    user_name = session.get('user', {}).get('name', '')
                    if "ULTRA" in user_name:
                         print(f"User Name contains ULTRA: '{user_name}'")

except Exception as e:
    print(f"Error: {e}")
