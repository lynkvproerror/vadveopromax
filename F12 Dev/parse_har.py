import json

har_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\0. Tao Project.har'
with open(har_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

entries = data['log']['entries']
result = []
for i, e in enumerate(entries):
    url = e['request']['url']
    method = e['request']['method']
    if 'trpc' in url.lower():
        status = e['response']['status']
        result.append(f"=== Entry {i}: {method} {status} ===")
        result.append(f"URL: {url}")
        if method == 'POST' and e['request'].get('postData', {}).get('text'):
            body = e['request']['postData']['text']
            result.append(f"Body: {body[:500]}")
        resp_text = e['response'].get('content', {}).get('text', '')
        if resp_text:
            result.append(f"Response: {resp_text[:800]}")
        result.append("")

with open(r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\har_trpc_results.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(result))
print(f"Found {len([r for r in result if r.startswith('===')])} TRPC entries. Written to har_trpc_results.txt")
