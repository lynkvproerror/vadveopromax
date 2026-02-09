"""
Investigate uploadUserImage API Key inconsistency.
For every uploadUserImage call across all HAR files, extract:
- Which HAR file
- Request timestamp
- Whether x-goog-api-key header is present
- Whether ?key= is in URL
- All auth-related headers
"""
import json, os, glob
from datetime import datetime

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"

results = []

har_files = glob.glob(os.path.join(HAR_DIR, "*.har"))
print(f"=== Scanning {len(har_files)} HAR files for uploadUserImage ===\n")

for hf in sorted(har_files):
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    
    entries = data.get('log', {}).get('entries', [])
    for i, entry in enumerate(entries):
        url = entry.get('request', {}).get('url', '')
        if 'uploadUserImage' not in url:
            continue
        
        req = entry.get('request', {})
        headers = {h['name'].lower(): h['value'] for h in req.get('headers', [])}
        
        has_api_key_header = 'x-goog-api-key' in headers
        has_api_key_query = 'key=' in url
        has_browser_validation = 'x-browser-validation' in headers
        has_browser_channel = 'x-browser-channel' in headers
        has_browser_copyright = 'x-browser-copyright' in headers
        has_browser_year = 'x-browser-year' in headers
        has_client_data = 'x-client-data' in headers
        sec_fetch_site = headers.get('sec-fetch-site', 'N/A')
        
        api_key_value = headers.get('x-goog-api-key', 'NONE')
        validation_value = headers.get('x-browser-validation', 'NONE')
        
        ts = entry.get('startedDateTime', 'N/A')
        
        results.append({
            'file': fname,
            'index': i,
            'timestamp': ts,
            'has_api_key_header': has_api_key_header,
            'has_api_key_query': has_api_key_query,
            'api_key_value': api_key_value[:30] if api_key_value != 'NONE' else 'NONE',
            'has_browser_validation': has_browser_validation,
            'has_browser_channel': has_browser_channel,
            'has_browser_copyright': has_browser_copyright,
            'has_browser_year': has_browser_year,
            'has_client_data': has_client_data,
            'sec_fetch_site': sec_fetch_site,
            'validation_value': validation_value[:30] if validation_value != 'NONE' else 'NONE',
            'all_x_headers': {k: v[:40] for k, v in headers.items() if k.startswith('x-')},
        })

# Output
output_lines = []
output_lines.append(f"=== uploadUserImage API Key Investigation ===")
output_lines.append(f"Total uploadUserImage calls found: {len(results)}")
output_lines.append(f"With x-goog-api-key header: {sum(1 for r in results if r['has_api_key_header'])}")
output_lines.append(f"Without x-goog-api-key header: {sum(1 for r in results if not r['has_api_key_header'])}")
output_lines.append(f"With ?key= in URL: {sum(1 for r in results if r['has_api_key_query'])}")
output_lines.append("")

# Group by WITH and WITHOUT API key
with_key = [r for r in results if r['has_api_key_header']]
without_key = [r for r in results if not r['has_api_key_header']]

output_lines.append("=" * 80)
output_lines.append(f"CALLS WITH x-goog-api-key ({len(with_key)} calls):")
output_lines.append("=" * 80)
for r in with_key:
    output_lines.append(f"\n  File: {r['file']}")
    output_lines.append(f"  Index: {r['index']}")
    output_lines.append(f"  Timestamp: {r['timestamp']}")
    output_lines.append(f"  API Key: {r['api_key_value']}")
    output_lines.append(f"  x-browser-validation: {r['validation_value']}")
    output_lines.append(f"  sec-fetch-site: {r['sec_fetch_site']}")
    output_lines.append(f"  All x-* headers: {json.dumps(r['all_x_headers'], indent=4)}")

output_lines.append("\n" + "=" * 80)
output_lines.append(f"CALLS WITHOUT x-goog-api-key ({len(without_key)} calls):")
output_lines.append("=" * 80)
for r in without_key:
    output_lines.append(f"\n  File: {r['file']}")
    output_lines.append(f"  Index: {r['index']}")
    output_lines.append(f"  Timestamp: {r['timestamp']}")
    output_lines.append(f"  x-browser-validation: {r['validation_value']}")
    output_lines.append(f"  sec-fetch-site: {r['sec_fetch_site']}")
    output_lines.append(f"  All x-* headers: {json.dumps(r['all_x_headers'], indent=4)}")

# Compare validation values
output_lines.append("\n" + "=" * 80)
output_lines.append("ANALYSIS: Pattern comparison")
output_lines.append("=" * 80)

# Check if API key presence correlates with file, timestamp, or validation value
with_key_files = set(r['file'] for r in with_key)
without_key_files = set(r['file'] for r in without_key)
both_files = with_key_files & without_key_files

output_lines.append(f"\nFiles with ONLY with-key calls: {with_key_files - without_key_files}")
output_lines.append(f"Files with ONLY without-key calls: {without_key_files - with_key_files}")
output_lines.append(f"Files with BOTH: {both_files}")

# Check validation values
with_key_validations = set(r['validation_value'] for r in with_key)
without_key_validations = set(r['validation_value'] for r in without_key)
output_lines.append(f"\nValidation values in WITH-key: {with_key_validations}")
output_lines.append(f"Validation values in WITHOUT-key: {without_key_validations}")

# Check timestamps - are WITH-key calls older or newer?
with_key_times = sorted(r['timestamp'] for r in with_key)
without_key_times = sorted(r['timestamp'] for r in without_key)
output_lines.append(f"\nWITH-key timestamp range: {with_key_times[0][:19]} → {with_key_times[-1][:19]}" if with_key_times else "")
output_lines.append(f"WITHOUT-key timestamp range: {without_key_times[0][:19]} → {without_key_times[-1][:19]}" if without_key_times else "")

# Check all custom headers consistency
output_lines.append(f"\n{'='*80}")
output_lines.append("HEADER COMPLETENESS CHECK:")
output_lines.append(f"{'='*80}")
for r in results:
    tag = "✅ HAS_KEY" if r['has_api_key_header'] else "❌ NO_KEY"
    headers_present = []
    if r['has_browser_channel']: headers_present.append('channel')
    if r['has_browser_copyright']: headers_present.append('copyright')
    if r['has_browser_validation']: headers_present.append('validation')
    if r['has_browser_year']: headers_present.append('year')
    if r['has_client_data']: headers_present.append('client-data')
    output_lines.append(f"  {tag} | {r['file'][:50]:50s} | Headers: {', '.join(headers_present)} | sec-fetch: {r['sec_fetch_site']}")

output = "\n".join(output_lines)
print(output)

with open(r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\upload_apikey_investigation.txt", 'w', encoding='utf-8') as f:
    f.write(output)

print(f"\n\nOutput saved to upload_apikey_investigation.txt")
