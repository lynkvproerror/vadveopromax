import json, os, glob
from collections import defaultdict

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New'
out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\token_analysis_result.txt'

lines = []
def log(s=''):
    lines.append(s)

log("="*80)
log("reCAPTCHA TOKEN ANALYSIS FROM 54 HAR FILES")
log("="*80)

# Find ALL POST requests with recaptcha in body
all_tokens = []
all_generate_urls = []

for har_path in sorted(glob.glob(os.path.join(har_dir, '*.har'))):
    fname = os.path.basename(har_path)
    try:
        with open(har_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        continue

    # Quick check if recaptcha appears in file at all
    has_recaptcha = 'recaptcha' in content.lower() or 'captcha' in content.lower()
    
    try:
        har = json.loads(content)
    except:
        continue
    
    for entry in har['log']['entries']:
        url = entry['request']['url']
        method = entry['request']['method']
        
        # Track all generate-like URLs
        if method == 'POST' and any(kw in url for kw in ['generate', 'Generate', 'upscale', 'Upscale']):
            all_generate_urls.append({'file': fname, 'url': url[:120], 'method': method})
        
        if method != 'POST':
            continue
            
        post_data = entry['request'].get('postData', {}).get('text', '')
        if not post_data:
            continue
        
        # Search in JSON body
        try:
            body = json.loads(post_data)
        except:
            continue
            
        # Recursive search for recaptcha keys
        def find_recaptcha(obj, path=''):
            results = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if 'captcha' in k.lower() or 'recaptcha' in k.lower():
                        results.append((path + '.' + k if path else k, str(v)))
                    else:
                        results.extend(find_recaptcha(v, path + '.' + k if path else k))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    results.extend(find_recaptcha(item, f'{path}[{i}]'))
            return results
        
        found = find_recaptcha(body)
        for key_path, token_val in found:
            if len(token_val) > 10:  # Skip empty/short values
                all_tokens.append({
                    'file': fname,
                    'url': url[:100],
                    'key': key_path,
                    'token_first30': token_val[:30],
                    'token_last20': token_val[-20:],
                    'token_len': len(token_val),
                    'token_hash': hash(token_val),
                })

log(f"\nTotal POST requests with recaptcha token found: {len(all_tokens)}")
log(f"Total generate/upscale URLs found: {len(all_generate_urls)}")

log("\n" + "="*80)
log("DETAIL: Each reCAPTCHA token found")
log("="*80)
for i, t in enumerate(all_tokens):
    log(f"\n[{i+1}] FILE: {t['file']}")
    log(f"    URL: {t['url']}")
    log(f"    KEY: {t['key']}")
    log(f"    TOKEN: \"{t['token_first30']}...{t['token_last20']}\" (len={t['token_len']})")

# Group by file
log("\n" + "="*80)
log("UNIQUENESS CHECK: Per-file token analysis")
log("="*80)

by_file = defaultdict(list)
for t in all_tokens:
    by_file[t['file']].append(t)

total_unique_check = 0
total_all_unique = 0
for fname in sorted(by_file.keys()):
    tokens = by_file[fname]
    log(f"\n--- {fname} ---")
    log(f"    Token count: {len(tokens)}")
    
    token_hashes = [t['token_hash'] for t in tokens]
    unique_hashes = set(token_hashes)
    
    for i, t in enumerate(tokens):
        log(f"    [{i+1}] {t['key']}: \"{t['token_first30']}...\" len={t['token_len']}")
    
    if len(tokens) > 1:
        total_unique_check += 1
        if len(unique_hashes) == len(token_hashes):
            log(f"    >>> ALL {len(tokens)} TOKENS ARE UNIQUE (DIFFERENT)")
            total_all_unique += 1
        else:
            log(f"    >>> DUPLICATES FOUND: {len(unique_hashes)} unique out of {len(token_hashes)} total")

log("\n" + "="*80)
log("GENERATE/UPSCALE URL PATTERNS")
log("="*80)
for g in all_generate_urls:
    log(f"  {g['file']}: {g['method']} {g['url']}")

log("\n" + "="*80)
log("FINAL SUMMARY")
log("="*80)
log(f"HAR files scanned: 54")
log(f"HAR files with recaptcha tokens: {len(by_file)}")
log(f"Total recaptcha tokens found: {len(all_tokens)}")
log(f"Files with 2+ tokens (can check uniqueness): {total_unique_check}")
log(f"Files where ALL tokens are unique: {total_all_unique}")

output = '\n'.join(lines)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(output)
print(f"Results written to: {out_path}")
print(f"Total tokens: {len(all_tokens)}, Files: {len(by_file)}")
