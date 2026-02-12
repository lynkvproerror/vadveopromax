import json, os, re, sys

out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\_har_action_deep.txt'
sys.stdout = open(out_path, 'w', encoding='utf-8')

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev'
har_files = []
for root, dirs, files in os.walk(har_dir):
    for f in files:
        if f.endswith('.har'):
            har_files.append(os.path.join(root, f))

print(f'=== Deep scan {len(har_files)} HAR files ===\n')

all_enterprise_js = []
all_action_contexts = []

for hf in har_files:
    try:
        with open(hf, 'r', encoding='utf-8', errors='ignore') as fp:
            data = json.load(fp)
        entries = data.get('log', {}).get('entries', [])
        fname = os.path.basename(hf)
        
        for entry in entries:
            url = entry.get('request', {}).get('url', '')
            resp_content = entry.get('response', {}).get('content', {})
            resp_text = resp_content.get('text', '') or ''
            
            if not resp_text:
                continue
            
            # Strategy 1: Find ANY JS that contains both "enterprise" and "execute"
            if 'enterprise' in resp_text and 'execute' in resp_text:
                # Find all patterns like execute(X, {action: "Y"})
                # Minified: .execute(a,{action:b}) or .execute(key,{action:"name"})
                patterns = re.findall(
                    r'\.execute\s*\(\s*[^,]+\s*,\s*\{\s*action\s*:\s*["\']?([^"\'}\s,)]+)',
                    resp_text
                )
                for p in patterns:
                    context_start = resp_text.find(p) - 100
                    context = resp_text[max(0, context_start):context_start + 250]
                    all_enterprise_js.append({
                        'file': fname,
                        'url': url.split('/')[-1][:60],
                        'action': p,
                        'context': context.replace('\n', ' ')[:200]
                    })
                
                # Also look for "recaptcha" near "action"
                recaptcha_action = re.findall(
                    r'recaptcha[^{]*\{[^}]*action\s*[:=]\s*["\']([^"\']+)["\']',
                    resp_text, re.IGNORECASE
                )
                for ra in recaptcha_action:
                    all_action_contexts.append(f'[{fname}] {url.split("/")[-1][:40]}: recaptcha action="{ra}"')
            
            # Strategy 2: Search in HTML pages for embedded recaptcha config  
            if 'text/html' in str(resp_content.get('mimeType', '')):
                # Look for action in script tags
                action_in_html = re.findall(
                    r'(?:action|recaptchaAction)\s*[:=]\s*["\']([^"\']+)["\']',
                    resp_text
                )
                for ah in action_in_html:
                    if 'enterprise' in resp_text.lower() or 'recaptcha' in resp_text.lower():
                        all_action_contexts.append(f'[{fname}] HTML: action="{ah}"')
            
            # Strategy 3: Check initiator chain for enterprise/reload calls
            # The reload POST typically has action encoded in protobuf
            if 'enterprise/reload' in url:
                # Try to extract from binary body as raw text
                post_data = entry.get('request', {}).get('postData', {})
                body = post_data.get('text', '') if post_data else ''
                if body:
                    # Look for readable strings in binary
                    readable = re.findall(r'[A-Za-z_]{3,30}', body)
                    interesting = [r for r in readable if r not in (
                        'gYdqkxiddE', 'aXrugNbBbKgtN', 'AFcWeA', 'https', 'www',
                        'google', 'com', 'recaptcha', 'enterprise'
                    )]
                    if interesting:
                        all_action_contexts.append(f'[{fname}] reload body readable strings: {interesting[:15]}')
                        
    except Exception as e:
        pass

print('=' * 60)
print(f'1. .execute() CALLS WITH ACTION ({len(all_enterprise_js)} found)')
print('=' * 60)
seen = set()
for item in all_enterprise_js:
    key = item['action']
    if key not in seen:
        seen.add(key)
        print(f'\n  Action: "{item["action"]}"')
        print(f'  File: {item["file"]}')
        print(f'  JS: {item["url"]}')
        print(f'  Context: ...{item["context"]}...')

print(f'\n{"=" * 60}')
print(f'2. RECAPTCHA ACTION CONTEXTS ({len(all_action_contexts)} found)')
print('=' * 60)
seen2 = set()
for ac in all_action_contexts:
    if ac not in seen2:
        seen2.add(ac)
        print(f'  {ac}')

# Strategy 4: Summary of unique action values
print(f'\n{"=" * 60}')
print(f'3. UNIQUE ACTION VALUES')
print('=' * 60)
unique_actions = set()
for item in all_enterprise_js:
    unique_actions.add(item['action'])
for ac in all_action_contexts:
    m = re.search(r'action="([^"]+)"', ac)
    if m:
        unique_actions.add(m.group(1))
for ua in sorted(unique_actions):
    print(f'  - {ua}')
