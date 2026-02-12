import json, os, re, sys, base64, gzip

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_nextdata.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

# Scan ALL HAR files in both Error and New directories
har_dirs = [
    r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New',
    r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\Error',
]

har_files = []
for d in har_dirs:
    for f in os.listdir(d):
        if f.endswith('.har'):
            har_files.append(os.path.join(d, f))

print(f'=== Scanning {len(har_files)} HAR files for _next/data recaptcha config ===\n')

# Strategy: Extract recaptchaKey / recaptchaSiteKey from _next/data JSON responses
found_configs = set()
found_actions = set()

for hf in har_files:
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            resp = entry.get('response', {}).get('content', {})
            encoding = resp.get('encoding', '')
            text = resp.get('text', '') or ''
            
            if not text:
                continue
            
            # Decode if base64
            decoded = text
            if encoding == 'base64':
                try:
                    raw = base64.b64decode(text)
                    try:
                        decoded = gzip.decompress(raw).decode('utf-8', errors='ignore')
                    except:
                        decoded = raw.decode('utf-8', errors='ignore')
                except:
                    decoded = text
            
            # Check for site key or recaptcha config
            if '6LdsFiUs' not in decoded:
                continue
            
            # Found site key reference!
            key = f'{fname}|{url[:80]}'
            if key in found_configs:
                continue
            found_configs.add(key)
            
            print(f'\n{"=" * 70}')
            print(f'FILE: {fname}')
            print(f'URL: {url[:150]}')
            print(f'Size: {len(decoded)} chars')
            
            # Try to parse as JSON
            try:
                j = json.loads(decoded)
                # Deep search for recaptcha config
                def search_json(obj, path=''):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if 'recaptcha' in k.lower() or 'captcha' in k.lower():
                                print(f'  KEY: {path}.{k} = {json.dumps(v)[:300]}')
                            if isinstance(v, str) and '6LdsFiUs' in v:
                                print(f'  SITEKEY: {path}.{k} = "{v}"')
                            if isinstance(v, str) and 'action' in k.lower():
                                if 'recaptcha' in path.lower():
                                    print(f'  ACTION: {path}.{k} = "{v}"')
                                    found_actions.add(v)
                            if isinstance(v, (dict, list)):
                                search_json(v, f'{path}.{k}')
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            if isinstance(item, (dict, list)):
                                search_json(item, f'{path}[{i}]')
                
                search_json(j)
            except:
                # Not JSON, search as text
                for m in re.finditer(r'6LdsFiUs[A-Za-z0-9_-]+', decoded):
                    pos = m.start()
                    ctx = decoded[max(0,pos-200):pos+300]
                    print(f'  SITEKEY context: ...{ctx[:500]}...')
                    break
                
    except Exception as e:
        pass

print(f'\n\n{"=" * 70}')
print(f'SUMMARY: Found configs in {len(found_configs)} entries')
print(f'Unique action values found: {found_actions}')
print('=' * 70)
