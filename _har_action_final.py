import json, os, re, sys

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_action_final.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev'
har_files = []
for root, dirs, files in os.walk(har_dir):
    for f in files:
        if f.endswith('.har'):
            har_files.append(os.path.join(root, f))

# Focus: find the recaptcha token being SENT in API requests
# and look at the surrounding JSON for any "action" field

print(f'=== Final scan: {len(har_files)} HAR files ===\n')

# Part 1: Extract full recaptchaContext JSON from API requests
print('=' * 70)
print('PART 1: Full recaptchaContext in API Request Bodies')
print('=' * 70)

contexts_found = 0
for hf in har_files[:10]:  # Check first 10 files
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            post_data = entry.get('request', {}).get('postData', {})
            body = post_data.get('text', '') if post_data else ''
            
            if not body or 'recaptchaContext' not in body:
                continue
            
            try:
                body_json = json.loads(body)
                # Find recaptchaContext at any depth
                def find_recaptcha(obj, path=''):
                    global contexts_found
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k == 'recaptchaContext':
                                print(f'\n  File: {fname}')
                                print(f'  URL: {url[:120]}')
                                print(f'  Path: {path}.{k}')
                                # Show full context but truncate token
                                ctx = dict(v)
                                if 'token' in ctx:
                                    ctx['token'] = ctx['token'][:40] + '...'
                                print(f'  recaptchaContext: {json.dumps(ctx, indent=4)}')
                                contexts_found += 1
                            elif isinstance(v, (dict, list)):
                                find_recaptcha(v, f'{path}.{k}')
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            find_recaptcha(item, f'{path}[{i}]')
                
                find_recaptcha(body_json)
            except json.JSONDecodeError:
                pass
                
    except Exception as e:
        pass

# Part 2: Check if action name exists ANYWHERE near recaptcha in request bodies
print(f'\n\n{"=" * 70}')
print('PART 2: Check for "action" field near recaptchaContext')
print('=' * 70)

for hf in har_files:
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            post_data = entry.get('request', {}).get('postData', {})
            body = post_data.get('text', '') if post_data else ''
            
            if 'recaptchaContext' not in body:
                continue
            
            try:
                body_json = json.loads(body)
                # Check if there's an "action" key at clientContext level
                client_ctx = body_json.get('clientContext', {})
                recaptcha_ctx = client_ctx.get('recaptchaContext', {})
                
                # Print ALL keys in recaptchaContext
                if recaptcha_ctx:
                    print(f'  [{fname}] recaptchaContext keys: {list(recaptcha_ctx.keys())}')
                    break  # one per file is enough
                    
            except json.JSONDecodeError:
                pass
    except:
        pass

# Part 3: Check what JS source files are loaded from aisandbox/labs.google
print(f'\n\n{"=" * 70}')  
print('PART 3: Looking for recaptcha init in HTML page source')
print('=' * 70)

for hf in har_files[:20]:
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            resp = entry.get('response', {}).get('content', {})
            text = resp.get('text', '') or ''
            mime = resp.get('mimeType', '') or ''
            
            if 'text/html' not in mime:
                continue
            
            # Look for reCAPTCHA enterprise script tags  
            if 'enterprise' in text and 'recaptcha' in text.lower():
                # Extract the script tag
                script_tags = re.findall(r'<script[^>]*recaptcha[^>]*enterprise[^>]*>', text, re.IGNORECASE)
                if not script_tags:
                    script_tags = re.findall(r'<script[^>]*enterprise[^>]*recaptcha[^>]*>', text, re.IGNORECASE)
                if script_tags:
                    print(f'  [{fname}] Script tags: {script_tags[:3]}')
                
                # Also look for grecaptcha.enterprise.execute in inline scripts
                inline_exec = re.findall(r'grecaptcha\.enterprise\.execute[^;]*;', text)
                if inline_exec:
                    print(f'  [{fname}] Inline execute: {inline_exec[:3]}')
                    
    except:
        pass
