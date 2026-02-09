import json
import os
import urllib.parse
from collections import defaultdict

har_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
output_path = "har_audit_report.txt"

har_files = [f for f in os.listdir(har_dir) if f.endswith('.har')]

# Collect ALL unique endpoints grouped by domain
endpoints_by_domain = defaultdict(set)
# Collect ALL unique headers per domain
headers_by_domain = defaultdict(set)
# Collect ALL unique cookies sent
cookies_all = set()
# Collect response content types per domain
response_types = defaultdict(set)
# Collect POST payloads snippets for non-analytics endpoints
payload_samples = []
# Collect x-* custom headers
custom_headers = defaultdict(set)

SKIP_DOMAINS = [
    "www.google-analytics.com",
    "www.googletagmanager.com",
    "play.google.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "lh3.googleusercontent.com",
    "ssl.gstatic.com",
]

for har_file in har_files:
    har_path = os.path.join(har_dir, har_file)
    try:
        with open(har_path, 'r', encoding='utf-8') as f:
            har_data = json.load(f)
        
        for entry in har_data['log']['entries']:
            request = entry['request']
            url = request['url']
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc
            
            # Skip analytics/tracking
            if any(skip in domain for skip in SKIP_DOMAINS):
                continue
            
            method = request['method']
            path = parsed.path
            
            # Collect endpoint
            endpoints_by_domain[domain].add(f"{method} {path}")
            
            # Collect headers
            for h in request['headers']:
                name = h['name'].lower()
                headers_by_domain[domain].add(name)
                if name.startswith('x-'):
                    custom_headers[domain].add(f"{name}: {h['value'][:80]}")
            
            # Collect cookies
            for c in request.get('cookies', []):
                cookies_all.add(c['name'])
            
            # Collect POST payloads (non-analytics)
            if method == "POST" and 'postData' in request:
                text = request['postData'].get('text', '')
                if text and len(text) > 5:
                    payload_samples.append({
                        'file': har_file,
                        'url': url[:120],
                        'snippet': text[:200],
                        'mime': request['postData'].get('mimeType', 'unknown')
                    })
            
            # Response content types
            resp = entry['response']
            if 'content' in resp:
                ct = resp['content'].get('mimeType', 'unknown')
                response_types[domain].add(ct)
                
    except Exception as e:
        print(f"Error processing {har_file}: {e}")

# Write report
with open(output_path, 'w', encoding='utf-8') as out:
    out.write("=== HAR AUDIT REPORT ===\n\n")
    
    out.write("--- 1. ALL DOMAINS & ENDPOINTS ---\n")
    for domain in sorted(endpoints_by_domain.keys()):
        out.write(f"\n[{domain}]\n")
        for ep in sorted(endpoints_by_domain[domain]):
            out.write(f"  {ep}\n")
    
    out.write("\n\n--- 2. CUSTOM HEADERS (x-*) PER DOMAIN ---\n")
    for domain in sorted(custom_headers.keys()):
        out.write(f"\n[{domain}]\n")
        for h in sorted(custom_headers[domain]):
            out.write(f"  {h}\n")
    
    out.write("\n\n--- 3. ALL COOKIES SENT ---\n")
    for c in sorted(cookies_all):
        out.write(f"  {c}\n")
    
    out.write("\n\n--- 4. POST PAYLOADS (Non-Analytics) ---\n")
    for p in payload_samples[:30]:  # Limit to 30
        out.write(f"\nFile: {p['file']}\n")
        out.write(f"URL: {p['url']}\n")
        out.write(f"MIME: {p['mime']}\n")
        out.write(f"Snippet: {p['snippet']}\n")
    
    out.write(f"\n\n--- 5. RESPONSE CONTENT TYPES PER DOMAIN ---\n")
    for domain in sorted(response_types.keys()):
        out.write(f"\n[{domain}]\n")
        for ct in sorted(response_types[domain]):
            out.write(f"  {ct}\n")

print(f"Report written to {output_path}")
