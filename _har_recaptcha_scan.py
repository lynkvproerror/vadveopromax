import json, os, re, sys

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_scan_results.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev'
har_files = []
for root, dirs, files in os.walk(har_dir):
    for f in files:
        if f.endswith('.har'):
            har_files.append(os.path.join(root, f))

print(f'=== Found {len(har_files)} HAR files ===\n')

recaptcha_scripts = set()
recaptcha_full_urls = []
enterprise_evidence = []
action_names = set()
recaptcha_in_body = []
recaptcha_context_samples = []
site_keys = set()

for hf in har_files:
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            
            # 1. reCAPTCHA script loading
            if 'recaptcha' in url.lower():
                base = url.split('?')[0]
                recaptcha_scripts.add(base)
                recaptcha_full_urls.append(f'[{fname}] {url[:200]}')
                if 'enterprise' in url.lower():
                    enterprise_evidence.append(f'SCRIPT: [{fname}] {url[:200]}')
                # Extract siteKey from render= param
                render_match = re.search(r'render=([^&]+)', url)
                if render_match:
                    val = render_match.group(1)
                    if val not in ('explicit', 'onload'):
                        site_keys.add(val)
            
            # 2. Check request bodies for recaptcha tokens
            post_data = entry.get('request', {}).get('postData', {})
            req_body = post_data.get('text', '') if post_data else ''
            
            if req_body and 'recaptcha' in req_body.lower():
                # Extract action names
                for a in re.findall(r'"action"\s*:\s*"([^"]+)"', req_body):
                    action_names.add(a)
                
                # Extract recaptchaContext patterns
                ctx_match = re.search(r'"recaptchaContext"\s*:\s*\{[^}]*\}', req_body)
                if ctx_match:
                    recaptcha_context_samples.append(f'[{fname}] URL: {url[:120]}\n  Context: {ctx_match.group(0)[:300]}')
                
                # Extract recaptchaToken patterns
                token_match = re.search(r'"recaptchaToken"\s*:\s*"([^"]{0,50})', req_body)
                if token_match:
                    recaptcha_in_body.append(f'[{fname}] URL: {url[:120]}\n  Token prefix: {token_match.group(1)[:50]}...')
                
                # Also look for clientContext containing recaptcha
                client_ctx = re.search(r'"clientContext"\s*:\s*\{[^}]*recaptcha[^}]*\}', req_body, re.IGNORECASE)
                if client_ctx:
                    recaptcha_context_samples.append(f'[{fname}] clientContext: {client_ctx.group(0)[:400]}')
            
            # 3. Check response for enterprise.js references
            resp_content = entry.get('response', {}).get('content', {})
            resp_text = resp_content.get('text', '') or ''
            if 'enterprise.js' in resp_text and 'recaptcha' in resp_text.lower():
                enterprise_evidence.append(f'HTML_REF: [{fname}] Response contains enterprise.js reference')
                # Try to extract site key from enterprise script tag
                sk_match = re.findall(r'render=([A-Za-z0-9_-]{20,})', resp_text)
                for sk in sk_match:
                    site_keys.add(sk)
                    
    except Exception as e:
        pass

print('=' * 60)
print('1. reCAPTCHA SCRIPT BASE URLs')
print('=' * 60)
for s in sorted(recaptcha_scripts):
    print(f'  {s}')

print(f'\n{"=" * 60}')
print(f'2. ENTERPRISE EVIDENCE ({len(enterprise_evidence)} items)')
print('=' * 60)
seen = set()
for e in enterprise_evidence:
    short = e[:100]
    if short not in seen:
        seen.add(short)
        print(f'  {e}')

print(f'\n{"=" * 60}')
print(f'3. SITE KEYS FOUND')
print('=' * 60)
for sk in site_keys:
    print(f'  {sk}')

print(f'\n{"=" * 60}')
print(f'4. ACTION NAMES: {action_names if action_names else "NONE FOUND"}')
print('=' * 60)

print(f'\n{"=" * 60}')
print(f'5. reCAPTCHA CONTEXT IN REQUEST BODIES ({len(recaptcha_context_samples)} samples)')
print('=' * 60)
for i, s in enumerate(recaptcha_context_samples[:20]):
    print(f'\n  [{i+1}] {s}')

print(f'\n{"=" * 60}')
print(f'6. reCAPTCHA TOKENS IN REQUEST BODIES ({len(recaptcha_in_body)} samples)')
print('=' * 60)
for i, s in enumerate(recaptcha_in_body[:10]):
    print(f'\n  [{i+1}] {s}')

print(f'\n{"=" * 60}')
print(f'7. ALL reCAPTCHA SCRIPT URLs (with params) — first 20')
print('=' * 60)
seen2 = set()
for u in recaptcha_full_urls[:30]:
    if u not in seen2:
        seen2.add(u)
        print(f'  {u}')
