import json

with open(r'D:\NEW VEO PRO MAX\veo-pro-max\F12 Dev\New\Test.har', 'r', encoding='utf-8') as f:
    data = json.load(f)

entries = [e for e in data['log']['entries'] if 'batchAsync' in e['request']['url']]
print(f"Found {len(entries)} batchAsync entries\n")

for i, e in enumerate(entries[:3]):
    print(f"--- Entry {i+1} ---")
    print(f"URL: {e['request']['url'][:120]}")
    print("Headers:")
    for h in e['request']['headers']:
        name = h['name'].lower()
        if name.startswith('x-') or name in ('content-type', 'authorization'):
            val = h['value'][:80] if len(h['value']) > 80 else h['value']
            print(f"  {h['name']}: {val}")
    
    # Show body structure
    if 'postData' in e['request']:
        try:
            body = json.loads(e['request']['postData']['text'])
            cc = body.get('clientContext', {})
            print(f"\nBody clientContext keys: {list(cc.keys())}")
            rc = cc.get('recaptchaContext', {})
            if rc:
                token = rc.get('token', '')
                print(f"  recaptchaContext.token length: {len(token)}")
                print(f"  recaptchaContext.applicationType: {rc.get('applicationType')}")
            print(f"  projectId: {cc.get('projectId', 'MISSING')}")
            print(f"  tool: {cc.get('tool', 'MISSING')}")
            print(f"  sessionId: {cc.get('sessionId', 'MISSING')}")
        except:
            print("  (could not parse body)")
    print()
