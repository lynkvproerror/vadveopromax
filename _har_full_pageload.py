import json, os, re, sys, base64, gzip

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_full_pageload.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New'

# Files likely to have full page loads
target_files = [
    os.path.join(har_dir, 'labs.google.har'),
    os.path.join(har_dir, 'Login dieu huong Flow.har'),
    os.path.join(har_dir, 'Model Video (text to video).har'),
    os.path.join(har_dir, '0. Tao Project.har'),
]

for test_file in target_files:
    if not os.path.exists(test_file):
        continue
    
    fname = os.path.basename(test_file)
    print(f'\n{"=" * 70}')
    print(f'FILE: {fname}')
    print(f'{"=" * 70}')
    
    with open(test_file, 'r', encoding='utf-8', errors='ignore') as fp:
        data = json.load(fp)
    
    entries = data.get('log', {}).get('entries', [])
    print(f'Total entries: {len(entries)}')
    
    for i, entry in enumerate(entries):
        url = entry.get('request', {}).get('url', '')
        resp = entry.get('response', {}).get('content', {})
        mime = resp.get('mimeType', '') or ''
        size = resp.get('size', 0)
        encoding = resp.get('encoding', '')
        text = resp.get('text', '') or ''
        
        # Decode if needed
        decoded = text
        if encoding == 'base64' and text:
            try:
                raw = base64.b64decode(text)
                try:
                    decoded = gzip.decompress(raw).decode('utf-8', errors='ignore')
                except:
                    try:
                        import brotli
                        decoded = brotli.decompress(raw).decode('utf-8', errors='ignore')
                    except:
                        decoded = raw.decode('utf-8', errors='ignore')
            except:
                decoded = text
        
        # Check for recaptcha in decoded content
        has_recaptcha = 'recaptcha' in decoded.lower() or 'grecaptcha' in decoded or '6LdsFiUs' in decoded
        
        if has_recaptcha:
            print(f'\n  [{i}] 🎯 {url[:120]}')
            print(f'      mime={mime} size={size} encoding={encoding} decoded_len={len(decoded)}')
            
            # Search for action patterns
            # Pattern 1: execute(VAR, {action: "STRING"})
            for m in re.finditer(r'\.execute\s*\(\s*([^,]{1,60}?)\s*,\s*\{[^}]*?action\s*:\s*([^},]{1,80})', decoded):
                print(f'      🔥 EXECUTE: .execute({m.group(1)[:50]}, {{action: {m.group(2)[:80]}}})')
                ctx = decoded[max(0,m.start()-50):m.end()+50]
                print(f'      Context: {ctx[:250]}')
            
            # Pattern 2: action:"STRING" near recaptcha  
            for m in re.finditer(r'["\']action["\']\s*:\s*["\']([^"\']+)["\']', decoded):
                idx = m.start()
                nearby = decoded[max(0,idx-200):idx+200].lower()
                if 'recaptcha' in nearby or 'enterprise' in nearby or 'captcha' in nearby:
                    print(f'      🔥 ACTION STRING: "{m.group(1)}"')
                    print(f'      Context: {decoded[max(0,idx-80):idx+120][:250]}')
            
            # Pattern 3: recaptchaAction or similar config
            for m in re.finditer(r'recaptcha[A-Za-z_]*[Aa]ction\s*[:=]\s*["\']([^"\']+)', decoded):
                print(f'      🔥 RECAPTCHA_ACTION: "{m.group(1)}"')
            
            # Pattern 4: site key with nearby action
            for m in re.finditer(r'6LdsFiUs[A-Za-z0-9_-]+', decoded):
                sk_pos = m.start()
                # Look for 'action' within 500 chars
                nearby = decoded[sk_pos:sk_pos+500]
                action_m = re.search(r'action\s*[:=]\s*["\']([^"\']+)', nearby)
                if action_m:
                    print(f'      🔥 NEAR SITEKEY: action="{action_m.group(1)}"')
                    print(f'      Context: {nearby[:300]}')
                    
            # Pattern 5: show first 3 "action" refs in this file for context
            action_refs = re.findall(r'action\s*:\s*"([^"]+)"', decoded)
            if action_refs:
                unique = list(set(action_refs))[:10]
                print(f'      All action strings in this response: {unique}')

print('\n\nDONE')
