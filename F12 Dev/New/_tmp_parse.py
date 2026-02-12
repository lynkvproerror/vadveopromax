import json

har_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\Tai Khoan Gmail Thuong co Ultra.har'
with open(har_path, 'r', encoding='utf-8') as f:
    har = json.load(f)

entries = har['log']['entries']
out = []

# Entry 48 - successful generate request body
e48 = entries[48]
req_body = json.loads(e48['request']['postData']['text'])
if 'clientContext' in req_body and 'recaptchaContext' in req_body['clientContext']:
    req_body['clientContext']['recaptchaContext']['token'] = '<REDACTED>'
out.append('=== GENERATE REQUEST BODY (Entry 48) ===')
out.append(json.dumps(req_body, indent=2, ensure_ascii=False))
out.append('')

# Entry 33 - Failed generate request (status 0)
e33 = entries[33]
req_body33 = json.loads(e33['request']['postData']['text'])
if 'clientContext' in req_body33 and 'recaptchaContext' in req_body33['clientContext']:
    req_body33['clientContext']['recaptchaContext']['token'] = '<REDACTED>'
out.append('=== GENERATE REQUEST BODY (Entry 33 - status 0) ===')
out.append(json.dumps(req_body33, indent=2, ensure_ascii=False))
out.append('')

# Entry 1 - credits
out.append('=== CREDITS (Entry 1) ===')
out.append(entries[1]['response']['content'].get('text', ''))
out.append('')

# Entry 2 - fetchUserRecommendations
out.append('=== FETCH USER RECOMMENDATIONS (Entry 2) ===')
out.append('REQ: ' + entries[2]['request']['postData']['text'])
out.append('RESP: ' + entries[2]['response']['content'].get('text', ''))
out.append('')

# Entry 3 - checkAppAvailability
out.append('=== CHECK APP AVAILABILITY (Entry 3) ===')
out.append('REQ: ' + entries[3]['request']['postData']['text'])
out.append('RESP: ' + entries[3]['response']['content'].get('text', ''))
out.append('')

# Headers for generate entry 48
out.append('=== GENERATE HEADERS (Entry 48) ===')
for h in e48['request']['headers']:
    n = h['name'].lower()
    if n in ['authorization', 'x-goog-api-key', 'content-type', 'origin', 'referer']:
        hname = h['name']
        hval = h['value'][:120]
        out.append('  {}: {}'.format(hname, hval))

outpath = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\har_deep_analysis.txt'
with open(outpath, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print('Written to har_deep_analysis.txt')
