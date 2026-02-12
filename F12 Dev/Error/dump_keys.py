import json
import base64
import re

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro.har"
output_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\props_keys.txt"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    
    for entry in entries:
        text = entry['response']['content'].get('text', '')
        if '__NEXT_DATA__' in text:
            if not text.strip().startswith('<'):
                try:
                    text = base64.b64decode(text).decode('utf-8')
                except:
                    pass
            
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
            if match:
                data = json.loads(match.group(1))
                page_props = data.get('props', {}).get('pageProps', {})
                
                with open(output_path, 'w', encoding='utf-8') as out:
                    out.write(f"Keys in props.pageProps:\n")
                    for k in page_props.keys():
                        out.write(f"- {k}\n")
                        
                    # Also check user object keys just in case
                    session = page_props.get('session', {})
                    user = session.get('user', {})
                    out.write(f"\nKeys in session.user:\n")
                    for k in user.keys():
                        out.write(f"- {k}\n")
                        
                print(f"Dumped keys to {output_path}")
                break

except Exception as e:
    print(f"Error: {e}")
