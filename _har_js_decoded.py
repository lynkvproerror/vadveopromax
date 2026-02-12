import json, os, re, sys, base64, gzip, io

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_js_decoded.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New'

# Pick one representative file
test_file = os.path.join(har_dir, 'Text to video 1.har')
print(f'=== Analyzing: {os.path.basename(test_file)} ===\n')

with open(test_file, 'r', encoding='utf-8', errors='ignore') as fp:
    data = json.load(fp)

entries = data.get('log', {}).get('entries', [])
print(f'Total entries: {len(entries)}\n')

# Show ALL entries with their URL, mime, size, and encoding
js_entries = []
html_entries = []

for i, entry in enumerate(entries):
    url = entry.get('request', {}).get('url', '')
    resp = entry.get('response', {}).get('content', {})
    mime = resp.get('mimeType', '')
    size = resp.get('size', 0)
    encoding = resp.get('encoding', 'none')
    text = resp.get('text', '') or ''
    text_len = len(text)
    
    is_js = 'javascript' in str(mime) or '.js' in url.split('?')[0][-5:]
    is_html = 'html' in str(mime)
    
    if is_js or is_html:
        entry_info = {
            'idx': i,
            'url': url[:120],
            'mime': mime,
            'size': size,
            'encoding': encoding,
            'text_len': text_len,
            'has_text': bool(text),
        }
        if is_js:
            js_entries.append((entry_info, text))
        if is_html:
            html_entries.append((entry_info, text))

print(f'JS entries: {len(js_entries)}')
print(f'HTML entries: {len(html_entries)}')

print(f'\n{"=" * 70}')
print('JS ENTRIES OVERVIEW:')
print('=' * 70)
for info, text in js_entries:
    print(f'  [{info["idx"]}] {info["url"]}')
    print(f'      mime={info["mime"]} size={info["size"]} encoding={info["encoding"]} text_len={info["text_len"]}')

# Try to decode JS bodies that have content
print(f'\n{"=" * 70}')
print('SEARCHING JS BODIES FOR enterprise/recaptcha:')
print('=' * 70)

for info, raw_text in js_entries:
    if not raw_text:
        continue
    
    text = raw_text
    # If base64 encoded, decode it
    if info['encoding'] == 'base64':
        try:
            decoded = base64.b64decode(raw_text)
            # Try gzip decompress
            try:
                text = gzip.decompress(decoded).decode('utf-8', errors='ignore')
            except:
                text = decoded.decode('utf-8', errors='ignore')
        except:
            text = raw_text
    
    if 'enterprise' in text or 'recaptcha' in text.lower() or 'grecaptcha' in text:
        print(f'\n  [{info["idx"]}] {info["url"]}')
        print(f'      Text length after decode: {len(text)}')
        
        # Find execute with action
        for m in re.finditer(r'\.execute\s*\(\s*([^,]+?)\s*,\s*\{[^}]*action\s*:\s*([^},]+)', text):
            print(f'      🎯 EXECUTE: .execute({m.group(1)[:50]}, {{action: {m.group(2)[:80]}}})')
            ctx_start = max(0, m.start() - 100)
            ctx_end = min(len(text), m.end() + 100)
            print(f'      Context: {text[ctx_start:ctx_end][:300]}')
        
        # Find action: "STRING" near recaptcha
        for m in re.finditer(r'action\s*:\s*"([^"]+)"', text):
            nearby_start = max(0, m.start() - 300)
            nearby_end = min(len(text), m.end() + 300)
            nearby = text[nearby_start:nearby_end].lower()
            if 'recaptcha' in nearby or 'enterprise' in nearby:
                print(f'      🎯 ACTION: "{m.group(1)}"')
                print(f'      Context: ...{text[max(0,m.start()-80):m.end()+80]}...')

# Also check HTML for __NEXT_DATA__
print(f'\n{"=" * 70}')
print('HTML __NEXT_DATA__ SEARCH:')
print('=' * 70)

for info, raw_text in html_entries:
    if not raw_text:
        continue
    
    text = raw_text
    if info['encoding'] == 'base64':
        try:
            decoded = base64.b64decode(raw_text)
            try:
                text = gzip.decompress(decoded).decode('utf-8', errors='ignore')
            except:
                text = decoded.decode('utf-8', errors='ignore')
        except:
            text = raw_text
    
    print(f'  [{info["idx"]}] {info["url"]}')
    print(f'      Text length: {len(text)}')
    
    # Search for site key
    if '6LdsFiUs' in text:
        pos = text.find('6LdsFiUs')
        ctx = text[max(0,pos-200):pos+200]
        print(f'      🎯 SITE KEY FOUND! Context: {ctx[:400]}')
    
    # Search for recaptcha/enterprise in HTML
    if 'enterprise' in text and 'recaptcha' in text.lower():
        # Find script tags
        for m in re.finditer(r'enterprise', text):
            ctx = text[max(0,m.start()-100):m.end()+200]
            # Only show if it's in a script tag or inline JS
            if 'script' in ctx.lower() or 'src=' in ctx:
                print(f'      Enterprise ref: {ctx[:300]}')
                break
    
    # Check __NEXT_DATA__
    nd_match = re.search(r'__NEXT_DATA__[^>]*>(.*?)</script>', text, re.DOTALL)
    if nd_match:
        nd = nd_match.group(1)
        if '6LdsFiUs' in nd or 'recaptcha' in nd.lower():
            print(f'      🎯 __NEXT_DATA__ has recaptcha config!')
            # Find the recaptcha key context
            for term in ['6LdsFiUs', 'recaptcha', 'captcha']:
                idx = nd.lower().find(term.lower())
                if idx >= 0:
                    print(f'      Context ({term}): {nd[max(0,idx-100):idx+200]}')
        else:
            print(f'      __NEXT_DATA__ size: {len(nd)} chars (no recaptcha ref)')
