import json, os, glob, re
from urllib.parse import urlparse
from collections import defaultdict

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New'
doc_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\00 - Documentation\VEO_Web_Client_Protocol_Analysis.md'

# Read doc
with open(doc_path, 'r', encoding='utf-8-sig') as f:
    doc = f.read()

# Normalize URL for matching
def norm(url):
    p = urlparse(url)
    path = p.path
    path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{uuid}', path)
    path = re.sub(r'/\d{10,}/', '/{id}/', path)
    return "{}{}".format(p.hostname, path)

# Classify endpoints
endpoints = defaultdict(lambda: {'methods': set(), 'count': 0, 'files': set()})

har_files = sorted(glob.glob(os.path.join(har_dir, '*.har')))

for hf in har_files:
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except:
        continue
    for entry in data.get('log', {}).get('entries', []):
        req = entry.get('request', {})
        url = req.get('url', '')
        method = req.get('method', '')
        
        parsed = urlparse(url)
        host = parsed.hostname or ''
        path = parsed.path or ''
        
        # Skip static assets
        skip_exts = ['.js', '.css', '.woff2', '.woff', '.ttf', '.png', '.jpg', '.jpeg', 
                     '.gif', '.svg', '.ico', '.webp', '.map']
        if any(path.endswith(ext) for ext in skip_exts):
            continue
        # Skip non-relevant domains
        skip_domains = ['fonts.googleapis.com', 'fonts.gstatic.com', 'play.google.com', 
                       'accounts.google.com', 'apis.google.com', 'lh3.googleusercontent.com',
                       'www.gstatic.com', 'ssl.gstatic.com', 'fundingchoicesmessages.google.com',
                       'pagead2.googlesyndication.com', 'id.google.com', 'myaccount.google.com',
                       'content-aisandbox-pa.googleapis.com']
        if host in skip_domains:
            continue
        if method == 'OPTIONS':
            continue
            
        key = norm(url)
        endpoints[key]['methods'].add(method)
        endpoints[key]['count'] += 1
        endpoints[key]['files'].add(fname)

# Categorize
categories = {
    'aisandbox-pa': [],
    'labs.google_trpc': [],
    'labs.google_auth': [],
    'labs.google_next': [],
    'labs.google_other': [],
    'storage': [],
    'recaptcha': [],
    'other': []
}

for ep, info in sorted(endpoints.items()):
    if 'aisandbox-pa' in ep:
        categories['aisandbox-pa'].append((ep, info))
    elif 'labs.google' in ep and '/api/trpc/' in ep:
        categories['labs.google_trpc'].append((ep, info))
    elif 'labs.google' in ep and '/api/auth/' in ep:
        categories['labs.google_auth'].append((ep, info))
    elif 'labs.google' in ep and '/_next/' in ep:
        categories['labs.google_next'].append((ep, info))
    elif 'labs.google' in ep:
        categories['labs.google_other'].append((ep, info))
    elif 'storage.googleapis.com' in ep:
        categories['storage'].append((ep, info))
    elif 'recaptcha' in ep:
        categories['recaptcha'].append((ep, info))
    else:
        categories['other'].append((ep, info))

# Check doc coverage
def check_in_doc(endpoint_key):
    searches = []
    
    # Extract action names from various URL patterns
    if 'batchAsync' in endpoint_key or 'batchCheck' in endpoint_key or 'batchGenerate' in endpoint_key:
        m = re.search(r'(batchAsync\w+|batchCheck\w+|batchGenerate\w+)', endpoint_key)
        if m:
            searches.append(m.group(1))
    if ':' in endpoint_key:
        action = endpoint_key.split(':')[-1]
        if action:
            searches.append(action)
    if '/api/trpc/' in endpoint_key:
        trpc_name = endpoint_key.split('/api/trpc/')[-1].split('?')[0]
        searches.append(trpc_name)
    if '/api/auth/' in endpoint_key:
        searches.append('auth/session')
    if '_next/data' in endpoint_key:
        searches.append('Next.js Data')
    if '/v1/credits' in endpoint_key:
        searches.append('/v1/credits')
    if '/v1/media/' in endpoint_key:
        searches.append('Media Fetch')
        searches.append('/v1/media/')
    if 'recaptcha' in endpoint_key:
        searches.append('recaptcha')
    if 'storage.googleapis.com' in endpoint_key:
        searches.append('Signed URL')
    if 'upsampleImage' in endpoint_key:
        searches.append('upsampleImage')
    if 'getVideoCreditStatus' in endpoint_key:
        searches.append('getVideoCreditStatus')
    if 'generatePinholeGif' in endpoint_key:
        searches.append('generatePinholeGif')
    
    # Last path segment
    last_seg = endpoint_key.rstrip('/').split('/')[-1]
    if last_seg and not last_seg.startswith('{') and len(last_seg) > 3:
        searches.append(last_seg)
    
    for s in searches:
        if s in doc:
            return True
    return False

# Output
out = []
out.append('=' * 80)
out.append('COMPREHENSIVE COVERAGE AUDIT: HAR Files vs Documentation')
out.append('=' * 80)
out.append('HAR files: {}'.format(len(har_files)))
out.append('Total unique endpoints (excl. static): {}'.format(len(endpoints)))
out.append('')

covered = 0
not_covered = 0
not_covered_list = []

cat_order = [
    ('aisandbox-pa', 'REST API (aisandbox-pa.googleapis.com)'),
    ('labs.google_trpc', 'TRPC (labs.google/fx/api/trpc)'),
    ('labs.google_auth', 'Auth (labs.google/fx/api/auth)'),
    ('labs.google_next', 'Next.js Data Routes (labs.google/_next)'),
    ('labs.google_other', 'Other labs.google'),
    ('storage', 'Storage (storage.googleapis.com)'),
    ('recaptcha', 'reCAPTCHA (www.google.com/recaptcha)'),
    ('other', 'Other Domains')
]

for cat_name, cat_label in cat_order:
    items = categories[cat_name]
    if not items:
        continue
    out.append('--- {} ({} endpoints) ---'.format(cat_label, len(items)))
    for ep, info in items:
        is_covered = check_in_doc(ep)
        status = 'COVERED' if is_covered else '>>> MISSING'
        methods = '/'.join(sorted(info['methods']))
        cnt = info['count']
        fcount = len(info['files'])
        out.append('  [{}] {:6s} {}  ({} calls, {} files)'.format(status, methods, ep, cnt, fcount))
        if is_covered:
            covered += 1
        else:
            not_covered += 1
            not_covered_list.append((ep, info))
    out.append('')

total = covered + not_covered
pct = covered / total * 100 if total > 0 else 0
out.append('=' * 80)
out.append('SUMMARY: {} COVERED / {} MISSING / {} TOTAL'.format(covered, not_covered, total))
out.append('Coverage: {:.1f}%'.format(pct))
out.append('=' * 80)

if not_covered_list:
    out.append('')
    out.append('MISSING ENDPOINTS DETAIL:')
    for ep, info in not_covered_list:
        methods = '/'.join(sorted(info['methods']))
        files_list = sorted(info['files'])[:3]
        files_str = ', '.join(files_list)
        out.append('  {:6s} {}'.format(methods, ep))
        out.append('         {} calls in {} files: {}...'.format(info['count'], len(info['files']), files_str))

result = '\n'.join(out)
outpath = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\coverage_audit.txt'
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(result)
print(result)
