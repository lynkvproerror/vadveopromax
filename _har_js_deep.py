import json, os, re, sys

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_js_deep.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New'
har_files = []
for f in os.listdir(har_dir):
    if f.endswith('.har'):
        har_files.append(os.path.join(har_dir, f))

print(f'=== Scanning {len(har_files)} HAR files in New/ ===\n')

# We need to find the actual action string passed to grecaptcha.enterprise.execute()
# The VEO frontend JS is minified, so we look for various patterns

all_js_chunks = []  # Store all JS response bodies with enterprise/recaptcha references

for hf in har_files[:5]:  # Start with first 5 files
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
            size = resp.get('size', 0)
            
            if not text or len(text) < 100:
                continue
            
            # Focus on JS files that contain recaptcha-related code
            is_js = 'javascript' in mime or url.endswith('.js')
            is_html = 'text/html' in mime
            
            has_enterprise = 'enterprise' in text
            has_recaptcha = 'recaptcha' in text.lower() or 'grecaptcha' in text
            has_execute = '.execute(' in text
            
            if not (has_enterprise or has_recaptcha):
                continue
            
            # Strategy 1: Find .execute with action parameter (various minified forms)
            # Pattern: .execute(VAR, {action: "STRING"})
            # Pattern: .execute(VAR, {action: VAR})
            patterns_found = []
            
            # Readable form
            for m in re.finditer(r'\.execute\s*\(\s*([^,]+?)\s*,\s*\{[^}]*action\s*:\s*([^},]+)', text):
                ctx_start = max(0, m.start() - 80)
                ctx_end = min(len(text), m.end() + 80)
                patterns_found.append({
                    'type': 'execute_with_action',
                    'full_match': m.group(0)[:150],
                    'arg1': m.group(1)[:50],
                    'action_val': m.group(2)[:80],
                    'context': text[ctx_start:ctx_end].replace('\n', ' ')[:300]
                })
            
            # Search for string "enterprise" near "execute" 
            if has_enterprise and has_execute:
                for m in re.finditer(r'enterprise', text):
                    pos = m.start()
                    # Look ahead 500 chars for .execute
                    nearby = text[pos:pos+500]
                    exec_m = re.search(r'\.execute\s*\(([^)]{0,200})\)', nearby)
                    if exec_m:
                        patterns_found.append({
                            'type': 'enterprise_near_execute',
                            'context': nearby[:300].replace('\n', ' ')
                        })
            
            # Search for recaptchaAction or action string literals near recaptcha
            for m in re.finditer(r'recaptcha[A-Za-z]*[Aa]ction', text):
                ctx_start = max(0, m.start() - 50)
                ctx_end = min(len(text), m.end() + 150)
                patterns_found.append({
                    'type': 'recaptchaAction_ref',
                    'context': text[ctx_start:ctx_end].replace('\n', ' ')[:300]
                })
            
            # Look for action:"SOMETHING" near recaptcha context
            for m in re.finditer(r'action\s*:\s*"([^"]+)"', text):
                action_val = m.group(1)
                # Check if recaptcha is nearby (within 500 chars before or after)
                nearby_start = max(0, m.start() - 500)
                nearby_end = min(len(text), m.end() + 500)
                nearby = text[nearby_start:nearby_end].lower()
                if 'recaptcha' in nearby or 'enterprise' in nearby or 'captcha' in nearby:
                    patterns_found.append({
                        'type': 'action_near_recaptcha',
                        'action': action_val,
                        'context': text[max(0,m.start()-100):m.end()+100].replace('\n', ' ')[:300]
                    })
            
            if patterns_found:
                print(f'\n{"=" * 70}')
                print(f'FILE: {fname}')
                print(f'JS URL: {url[:120]}')
                print(f'MIME: {mime} | Size: {size}')
                print(f'Found {len(patterns_found)} patterns:')
                for i, p in enumerate(patterns_found):
                    print(f'\n  [{i+1}] Type: {p["type"]}')
                    for k, v in p.items():
                        if k != 'type':
                            print(f'      {k}: {v}')
                            
    except Exception as e:
        print(f'ERROR: {os.path.basename(hf)}: {e}')

# Part 2: Also search for the recaptcha init/config in HTML pages
print(f'\n\n{"=" * 70}')
print('PART 2: Searching HTML pages for reCAPTCHA config/init')
print('=' * 70)

for hf in har_files[:5]:
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
            
            if 'text/html' not in mime or not text:
                continue
            
            # Find __NEXT_DATA__ which may contain reCAPTCHA config
            next_data_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.DOTALL)
            if next_data_match:
                nd_text = next_data_match.group(1)
                if 'recaptcha' in nd_text.lower() or 'captcha' in nd_text.lower():
                    print(f'\n  [{fname}] __NEXT_DATA__ contains recaptcha reference!')
                    # Extract relevant section
                    for m in re.finditer(r'recaptcha[^"]*"?\s*:\s*["\{][^}]*', nd_text, re.IGNORECASE):
                        print(f'    Found: ...{nd_text[max(0,m.start()-30):m.end()+50]}...')
                else:
                    # Check for siteKey in __NEXT_DATA__
                    if '6LdsFiUs' in nd_text:
                        # Find context around site key
                        sk_pos = nd_text.find('6LdsFiUs')
                        ctx = nd_text[max(0,sk_pos-100):sk_pos+200]
                        print(f'\n  [{fname}] __NEXT_DATA__ contains site key!')
                        print(f'    Context: {ctx[:300]}')
                        
    except Exception as e:
        pass

# Part 3: Extract all unique script src URLs that load recaptcha
print(f'\n\n{"=" * 70}')
print('PART 3: All reCAPTCHA-related script src in HTML')
print('=' * 70)

for hf in har_files[:10]:
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            resp = entry.get('response', {}).get('content', {})
            text = resp.get('text', '') or ''
            mime = resp.get('mimeType', '') or ''
            
            if 'text/html' not in mime:
                continue
            
            scripts = re.findall(r'<script[^>]*src="([^"]*recaptcha[^"]*)"', text, re.IGNORECASE)
            for s in scripts:
                print(f'  [{fname}] <script src="{s}">')
                
    except:
        pass
