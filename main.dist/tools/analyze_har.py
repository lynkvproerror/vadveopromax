import json
import sys

# Deep analysis of Fast Submit success HAR
har_file = 'All Har 12.05.2026 (Fast Submit-download 720p-upscale th\u00e0nh c\u00f4ng).har'
with open(har_file, 'r', encoding='utf-8') as f:
    data = json.load(f)
entries = data['log']['entries']

print('===== FAST SUCCESS: Submit request deep analysis =====')
for e in entries:
    url = e['request']['url']
    if 'batchAsyncGenerateVideoText' in url:
        print('--- Submit Request Headers ---')
        for h in sorted(e['request']['headers'], key=lambda x: x['name'].lower()):
            name = h['name']
            val = h['value'][:120]
            print(f'  {name}: {val}')

        body = e['request'].get('postData', {}).get('text', '')
        if body:
            try:
                parsed = json.loads(body)
                print('--- Submit Request Body Keys ---')
                for k in parsed:
                    v = parsed[k]
                    if isinstance(v, str) and len(v) > 100:
                        print(f'  {k}: {v[:100]}...')
                    elif isinstance(v, dict):
                        print(f'  {k}: {json.dumps(v)[:300]}')
                    elif isinstance(v, list):
                        print(f'  {k}: [{len(v)} items] -> {json.dumps(v)[:300]}')
                    else:
                        print(f'  {k}: {v}')
            except:
                print(f'  Raw body: {body[:500]}')

        print('--- Submit Response ---')
        print(f'  Status: {e["response"]["status"]}')
        resp_body = e['response'].get('content', {}).get('text', '')
        if resp_body:
            try:
                parsed_resp = json.loads(resp_body)
                print(f'  Response (trimmed): {json.dumps(parsed_resp, indent=2)[:800]}')
            except:
                print(f'  Response text: {resp_body[:500]}')
        break

print()
print('===== FAST SUCCESS: Upscale request =====')
for e in entries:
    url = e['request']['url']
    if 'UpsampleVideo' in url:
        print('--- Upscale Request Headers ---')
        for h in sorted(e['request']['headers'], key=lambda x: x['name'].lower()):
            name = h['name']
            val = h['value'][:120]
            print(f'  {name}: {val}')
        body = e['request'].get('postData', {}).get('text', '')
        if body:
            print(f'--- Upscale Body (trimmed) ---')
            print(f'  {body[:600]}')
        break

print()
print('===== FAST SUCCESS: Poll cadence (fetchUserAcknowledgement) =====')
poll_times = []
for e in entries:
    url = e['request']['url']
    if 'fetchUserAcknowledgement' in url:
        ts = e.get('startedDateTime', '')
        poll_times.append(ts)

for i, ts in enumerate(poll_times):
    print(f'  Poll {i+1}: {ts[:23]}')

print()
print('===== FAST SUCCESS: Redirect requests =====')
for e in entries:
    url = e['request']['url']
    if 'getMediaUrlRedirect' in url:
        print(f'  URL: {url[:250]}')
        print(f'  Response status: {e["response"]["status"]}')
        resp_headers = {h['name'].lower(): h['value'] for h in e['response']['headers']}
        if 'location' in resp_headers:
            loc = resp_headers['location'][:200]
            print(f'  Location: {loc}')
        print()

# Now check the status poll requests specifically
print()
print('===== LOOKING FOR STATUS POLL (batchCheckAsync) IN ALL 7 HARs =====')

all_hars = [
    ('11.05', 'All Har 11.05.2026.har'),
    ('12.05 full', 'All Har 12.05.2026.har'),
    ('12.05 download', 'All Har 12.05.2026 (DOWNLOAD).har'),
    ('Fast success', 'All Har 12.05.2026 (Fast Submit-download 720p-upscale th\u00e0nh c\u00f4ng).har'),
    ('Lite success', 'All Har 12.05.2026 (Lite Submit-download 720p-upscale th\u00e0nh c\u00f4ng).har'),
    ('Loi 1', 'All Har 12.05.2026 (L\u1ed7i T\u1ea1o Video).har'),
    ('Loi 2', 'All Har 12.05.2026 (L\u1ed7i T\u1ea1o Video 2).har'),
]

for label, har_file in all_hars:
    with open(har_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    entries = data['log']['entries']

    poll_entries = [e for e in entries if 'batchCheckAsync' in e['request']['url']]
    print(f'\n--- {label}: {len(poll_entries)} poll entries ---')

    if poll_entries:
        # Show first poll's full headers
        e = poll_entries[0]
        print(f'  First poll headers:')
        for h in sorted(e['request']['headers'], key=lambda x: x['name'].lower()):
            name = h['name']
            val = h['value'][:120]
            print(f'    {name}: {val}')

        # Show first poll's body
        body = e['request'].get('postData', {}).get('text', '')
        if body:
            print(f'  First poll body: {body[:400]}')

        # Show first poll's response
        resp_body = e['response'].get('content', {}).get('text', '')
        if resp_body:
            print(f'  First poll response (trimmed): {resp_body[:400]}')

        # Poll interval analysis
        if len(poll_entries) >= 3:
            from datetime import datetime
            times = []
            for pe in poll_entries:
                ts_str = pe.get('startedDateTime', '')[:23]
                try:
                    t = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    times.append(t)
                except:
                    pass
            if len(times) >= 3:
                intervals = [(times[i+1] - times[i]).total_seconds() for i in range(min(10, len(times)-1))]
                print(f'  Poll intervals (first 10): {[round(x, 1) for x in intervals]}')
                avg = sum(intervals) / len(intervals)
                print(f'  Average interval: {avg:.1f}s')
