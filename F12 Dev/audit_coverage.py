"""
Audit: Extract ALL unique client-server structures from 54 HAR files.
Output: unique endpoints, request structures, response patterns, headers, cookies.
"""
import json, os, glob
from collections import defaultdict, Counter
from urllib.parse import urlparse

har_dir = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New'
out_path = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\audit_coverage_result.txt'

lines = []
def log(s=''):
    lines.append(s)

# Collect data
all_endpoints = []  # (method, url_pattern, har_file)
all_request_bodies = []  # (url_pattern, body_keys, har_file)
all_response_bodies = []  # (url_pattern, resp_keys, status, har_file)
all_custom_headers = defaultdict(set)  # header_name -> set of values
all_cookies = defaultdict(set)  # cookie_name -> set of domains
all_content_types = defaultdict(int)  # url_pattern -> count
all_query_params = defaultdict(set)  # url_pattern -> set of param names

NOISE_DOMAINS = {
    'www.google-analytics.com', 'www.googletagmanager.com',
    'accounts.google.com', 'play.google.com',
    'www.gstatic.com', 'fonts.googleapis.com', 'fonts.gstatic.com',
    'apis.google.com', 'ssl.gstatic.com', 'lh3.googleusercontent.com',
    'safebrowsing.googleapis.com', 'content-autofill.googleapis.com',
    'optimizationguide-pa.googleapis.com', 'update.googleapis.com',
    'clientservices.googleapis.com', 'translate.googleapis.com',
    'mail.google.com', 'myaccount.google.com',
}

RELEVANT_DOMAINS = {
    'aisandbox-pa.googleapis.com',
    'labs.google.com',
    'generativelanguage.googleapis.com',
    'storage.googleapis.com',
}

def normalize_url(url):
    """Normalize URL: remove query params, replace UUIDs with {uuid}"""
    import re
    parsed = urlparse(url)
    path = parsed.path
    # Replace UUIDs
    path = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{uuid}', path)
    # Replace long numeric IDs
    path = re.sub(r'/\d{10,}/', '/{id}/', path)
    return f"{parsed.scheme}://{parsed.hostname}{path}"

def get_body_keys(body_text, depth=0, max_depth=3):
    """Extract all keys from JSON body recursively"""
    if depth > max_depth:
        return set()
    try:
        obj = json.loads(body_text) if isinstance(body_text, str) else body_text
    except:
        return set()
    
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            if isinstance(v, dict):
                for sk in get_body_keys(v, depth+1, max_depth):
                    keys.add(f"{k}.{sk}")
            elif isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                for sk in get_body_keys(v[0], depth+1, max_depth):
                    keys.add(f"{k}[].{sk}")
    return keys

for har_path in sorted(glob.glob(os.path.join(har_dir, '*.har'))):
    fname = os.path.basename(har_path)
    try:
        with open(har_path, 'r', encoding='utf-8') as f:
            har = json.load(f)
    except:
        continue
    
    for entry in har['log']['entries']:
        url = entry['request']['url']
        method = entry['request']['method']
        parsed = urlparse(url)
        
        # Skip noise
        if parsed.hostname in NOISE_DOMAINS:
            continue
        
        # Only keep relevant domains (or unknown ones that might be interesting)
        is_relevant = parsed.hostname in RELEVANT_DOMAINS
        is_cdn = 'storage.googleapis.com' in (parsed.hostname or '')
        
        if not is_relevant and not is_cdn:
            # Check if it's a third-party we should note
            if parsed.hostname and 'google' not in (parsed.hostname or ''):
                continue  # Skip non-google
            # Skip static resources
            if any(url.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.svg', '.ico', '.woff2', '.woff', '.ttf']):
                continue
        
        normalized = normalize_url(url)
        all_endpoints.append((method, normalized, fname))
        
        # Extract query params
        if parsed.query:
            import re
            params = re.findall(r'([^&=]+)=', parsed.query)
            for p in params:
                all_query_params[normalized].add(p)
        
        # Extract request body structure
        post_data = entry['request'].get('postData', {}).get('text', '')
        if post_data and method == 'POST':
            body_keys = get_body_keys(post_data)
            if body_keys:
                all_request_bodies.append((normalized, body_keys, fname))
        
        # Extract custom headers
        for h in entry['request'].get('headers', []):
            name = h['name'].lower()
            if name.startswith('x-') or name in ['authorization', 'cookie']:
                if name == 'cookie':
                    # Parse cookie names
                    for cookie in h['value'].split(';'):
                        cookie_name = cookie.strip().split('=')[0]
                        all_cookies[cookie_name].add(parsed.hostname or '')
                else:
                    all_custom_headers[name].add(h['value'][:50] + '...' if len(h['value']) > 50 else h['value'])
        
        # Extract response structure
        resp = entry.get('response', {})
        status = resp.get('status', 0)
        resp_body = resp.get('content', {}).get('text', '')
        if resp_body and status in [200, 201]:
            resp_keys = get_body_keys(resp_body)
            if resp_keys:
                all_response_bodies.append((normalized, resp_keys, status, fname))

# ============================================================
# OUTPUT
# ============================================================

log("="*100)
log("AUDIT: ALL CLIENT-SERVER STRUCTURES FROM 54 HAR FILES")
log("="*100)

# 1. Unique endpoints
log("\n" + "="*100)
log("1. UNIQUE ENDPOINTS (method + normalized URL)")
log("="*100)

endpoint_counter = Counter()
endpoint_files = defaultdict(set)
for method, url, fname in all_endpoints:
    key = f"{method} {url}"
    endpoint_counter[key] += 1
    endpoint_files[key].add(fname)

for key, count in sorted(endpoint_counter.items(), key=lambda x: x[1], reverse=True):
    log(f"\n  [{count:3d}x] {key}")
    if count <= 3:
        for f in sorted(endpoint_files[key]):
            log(f"         ← {f}")

# 2. Unique request body structures
log("\n\n" + "="*100)
log("2. UNIQUE REQUEST BODY STRUCTURES (POST endpoints)")
log("="*100)

body_by_endpoint = defaultdict(set)
for url, keys, fname in all_request_bodies:
    body_by_endpoint[url].update(keys)

for url in sorted(body_by_endpoint.keys()):
    keys = sorted(body_by_endpoint[url])
    log(f"\n  {url}")
    for k in keys:
        log(f"    → {k}")

# 3. Unique response body structures
log("\n\n" + "="*100)
log("3. UNIQUE RESPONSE BODY STRUCTURES (200/201 responses)")
log("="*100)

resp_by_endpoint = defaultdict(set)
for url, keys, status, fname in all_response_bodies:
    resp_by_endpoint[url].update(keys)

for url in sorted(resp_by_endpoint.keys()):
    keys = sorted(resp_by_endpoint[url])
    log(f"\n  {url}")
    for k in keys[:20]:  # Limit to 20 keys
        log(f"    ← {k}")
    if len(keys) > 20:
        log(f"    ... (+{len(keys)-20} more keys)")

# 4. Custom headers
log("\n\n" + "="*100)
log("4. CUSTOM HEADERS (x-* and auth)")
log("="*100)

for name in sorted(all_custom_headers.keys()):
    values = all_custom_headers[name]
    log(f"\n  {name}: ({len(values)} unique values)")
    for v in sorted(values)[:5]:
        log(f"    → {v}")

# 5. Cookies
log("\n\n" + "="*100)
log("5. COOKIES SENT")
log("="*100)

for name in sorted(all_cookies.keys()):
    domains = all_cookies[name]
    log(f"  {name}: {', '.join(sorted(domains))}")

# 6. Query params
log("\n\n" + "="*100)
log("6. QUERY PARAMETERS BY ENDPOINT")
log("="*100)

for url in sorted(all_query_params.keys()):
    params = sorted(all_query_params[url])
    log(f"  {url}")
    for p in params:
        log(f"    ?{p}=...")

# Summary
log("\n\n" + "="*100)
log("SUMMARY")
log("="*100)
log(f"Total unique endpoints: {len(endpoint_counter)}")
log(f"Total unique POST body structures: {len(body_by_endpoint)}")
log(f"Total unique response structures: {len(resp_by_endpoint)}")
log(f"Total custom headers: {len(all_custom_headers)}")
log(f"Total cookies: {len(all_cookies)}")

output = '\n'.join(lines)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(output)
print(f"Results written to: {out_path}")
print(f"Endpoints: {len(endpoint_counter)}, Bodies: {len(body_by_endpoint)}, Responses: {len(resp_by_endpoint)}")
