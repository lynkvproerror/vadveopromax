"""Deep audit: Scan ALL Python files for protocol mismatches vs documentation."""
import os, re, glob

CODE_DIR = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02 - CLIENT - VEO PRO MAX'

# Patterns that indicate protocol-related code
PATTERNS = {
    'Authorization': r'Authorization|Bearer\s',
    'x-goog-recaptcha': r'x-goog-recaptcha',
    'Content-Type-json': r'application/json',
    'Content-Type-text': r'text/plain',
    'IN_PROGRESS': r'IN_PROGRESS|MEDIA_GENERATION_STATUS_IN_PROGRESS',
    'ACTIVE_status': r'MEDIA_GENERATION_STATUS_ACTIVE',
    'access_token_param': r'access_token',
    'recaptcha_token_param': r'recaptcha_token',
    'api_key': r'api_key|x-goog-api-key|AIzaSy',
    'base_url_ref': r'aisandbox-pa|googleapis\.com',
    'trpc_ref': r'trpc|labs\.google',
    'cookie_ref': r'cookie|Cookie|session-token|__Secure',
    'polling_ref': r'poll|check_status|batchCheck',
    'upscale_ref': r'upscale|upsample|Upsample',
    'upload_ref': r'upload|uploadUserImage',
    'download_ref': r'download|servingBaseUri|Signed URL|storage\.google',
    'generate_ref': r'generate|batchAsync',
    'project_ref': r'project_id|projectId|create_project',
    'paygate_ref': r'paygate|PAYGATE_TIER|userPaygateTier',
    'browser_headers_ref': r'x-browser|browser-validation|browser-channel|browser-copyright|browser-year',
    'client_data_ref': r'x-client-data|client_data',
    'recaptcha_body_ref': r'recaptchaContext',
    'session_id_ref': r'sessionId',
    'seed_ref': r'seed|SEED_MIN|SEED_MAX|32767',
    'model_key_ref': r'videoModelKey|imageModelName|veo_3|GEM_PIX',
    'remaining_credits': r'remainingCredits|remaining_credits',
    'signed_url_ref': r'GoogleAccessId|Signature|Expires',
    'credits_ref': r'/v1/credits|get_credits',
    'media_fetch_ref': r'/v1/media/',
    'ASSET_MANAGER': r'ASSET_MANAGER',
    'PINHOLE': r'PINHOLE',
    'create_project_call': r'create_project\(',
    'close_session': r'close\(\)|_session\.close',
    'content_type_override': r'content_type|Content-Type',
}

results = {}

for py_file in sorted(glob.glob(os.path.join(CODE_DIR, '**', '*.py'), recursive=True)):
    if '__pycache__' in py_file:
        continue
    rel = os.path.relpath(py_file, CODE_DIR)
    
    try:
        with open(py_file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            lines = content.split('\n')
    except:
        continue
    
    file_matches = {}
    for pattern_name, regex in PATTERNS.items():
        matches = []
        for i, line in enumerate(lines, 1):
            if re.search(regex, line, re.IGNORECASE):
                matches.append((i, line.strip()[:120]))
        if matches:
            file_matches[pattern_name] = matches
    
    if file_matches:
        results[rel] = {
            'total_lines': len(lines),
            'matches': file_matches
        }

# Output report
out = []
out.append('=' * 100)
out.append('DEEP AUDIT: All Python Files - Protocol-Related Patterns')
out.append('=' * 100)
out.append('Files scanned: {}'.format(len(glob.glob(os.path.join(CODE_DIR, '**', '*.py'), recursive=True))))
out.append('Files with protocol patterns: {}'.format(len(results)))
out.append('')

# Summary table
out.append('--- SUMMARY TABLE ---')
out.append('{:<45} {:>6} {:>6} {:>6} {:>6} {:>6} {:>6}'.format(
    'File', 'Lines', 'Auth', 'reCap', 'CType', 'Poll', 'Heads'))

for rel, info in sorted(results.items()):
    m = info['matches']
    auth_count = len(m.get('Authorization', []))
    recap_count = len(m.get('x-goog-recaptcha', []))
    ctype_count = len(m.get('Content-Type-json', []))
    poll_count = len(m.get('polling_ref', []))
    heads_count = len(m.get('browser_headers_ref', []))
    out.append('{:<45} {:>6} {:>6} {:>6} {:>6} {:>6} {:>6}'.format(
        rel, info['total_lines'], auth_count, recap_count, ctype_count, poll_count, heads_count))

out.append('')

# Detailed per-file report
for rel, info in sorted(results.items()):
    out.append('=' * 80)
    out.append('FILE: {} ({} lines)'.format(rel, info['total_lines']))
    out.append('-' * 80)
    
    for pattern_name, matches in sorted(info['matches'].items()):
        out.append('  [{}] ({} hits):'.format(pattern_name, len(matches)))
        for lineno, text in matches[:5]:  # limit to 5 per pattern
            out.append('    L{}: {}'.format(lineno, text))
        if len(matches) > 5:
            out.append('    ... and {} more'.format(len(matches) - 5))
    out.append('')

report = '\n'.join(out)
outpath = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\deep_audit_result.txt'
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(report)
print('Report saved to:', outpath)
print('Total files with patterns:', len(results))
print()
# Print summary immediately
for line in out[:50]:
    print(line)
