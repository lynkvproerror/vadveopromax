import json, os, re, sys, urllib.parse

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_action_scan.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev'
har_files = []
for root, dirs, files in os.walk(har_dir):
    for f in files:
        if f.endswith('.har'):
            har_files.append(os.path.join(root, f))

print(f'=== Scanning {len(har_files)} HAR files for reCAPTCHA action names ===\n')

# Strategy 1: Check enterprise/reload POST bodies (action is sent here)
reload_actions = []

# Strategy 2: Check JS source files for grecaptcha.enterprise.execute calls
js_execute_calls = []

# Strategy 3: Check enterprise/reload URL query params
reload_params = []

for hf in har_files:
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            method = entry.get('request', {}).get('method', '')
            
            # Strategy 1: enterprise/reload POST body
            if 'enterprise/reload' in url or 'enterprise/anchor' in url:
                # Check POST data
                post_data = entry.get('request', {}).get('postData', {})
                body = post_data.get('text', '') if post_data else ''
                
                # Parse URL params
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                
                reload_params.append({
                    'file': fname,
                    'url': url[:200],
                    'method': method,
                    'params': dict(params),
                    'body_preview': body[:500] if body else '(empty)',
                })
                
                # Look for action in body (URL-encoded form data)
                if body:
                    action_match = re.findall(r'action[=:]([^&\s"]+)', body)
                    if action_match:
                        for a in action_match:
                            reload_actions.append(f'[{fname}] action={a}')
            
            # Strategy 2: Check JS files for execute calls
            resp_content = entry.get('response', {}).get('content', {})
            mime = resp_content.get('mimeType', '')
            resp_text = resp_content.get('text', '') or ''
            
            if ('javascript' in mime or url.endswith('.js')) and 'enterprise' in resp_text:
                # Find grecaptcha.enterprise.execute calls
                matches = re.findall(r'grecaptcha\.enterprise\.execute\s*\([^)]*\)', resp_text)
                for m in matches:
                    js_execute_calls.append(f'[{fname}] {url.split("/")[-1][:50]}: {m[:200]}')
                
                # Also search for action: patterns near enterprise
                action_patterns = re.findall(r'action\s*:\s*["\']([^"\']+)["\']', resp_text)
                if action_patterns and 'enterprise' in resp_text:
                    for ap in action_patterns:
                        if ap not in ('submit', 'login', 'register'):  # skip generic
                            js_execute_calls.append(f'[{fname}] JS action pattern: action: "{ap}"')
                
                # Search for minified patterns like .execute(X,{action:Y})
                minified = re.findall(r'\.execute\([^,]+,\s*\{action:\s*["\']?([^"\'}\s,]+)', resp_text)
                for m in minified:
                    js_execute_calls.append(f'[{fname}] Minified execute action: "{m}"')
                    
    except Exception as e:
        pass

print('=' * 60)
print(f'1. enterprise/reload REQUESTS ({len(reload_params)} total)')
print('=' * 60)
seen = set()
for i, r in enumerate(reload_params[:15]):
    key = r['url'][:80]
    if key not in seen:
        seen.add(key)
        print(f'\n  [{i+1}] File: {r["file"]}')
        print(f'      Method: {r["method"]}')
        print(f'      URL: {r["url"]}')
        print(f'      Params: {r["params"]}')
        print(f'      Body: {r["body_preview"][:300]}')

print(f'\n{"=" * 60}')
print(f'2. ACTION NAMES FOUND IN RELOAD BODIES ({len(reload_actions)} total)')
print('=' * 60)
for a in sorted(set(reload_actions)):
    print(f'  {a}')

print(f'\n{"=" * 60}')
print(f'3. JS grecaptcha.enterprise.execute CALLS ({len(js_execute_calls)} total)')
print('=' * 60)
seen2 = set()
for j in js_execute_calls:
    if j not in seen2:
        seen2.add(j)
        print(f'  {j}')
