"""
Deep investigation of Custom Headers (x-browser-*) patterns across all HAR files.
Goal: Understand structure, variability, and client→server relationship.
"""
import json, os, glob, base64, hashlib
from collections import defaultdict, Counter

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"

# Collect all x-browser-* and x-client-data values across all HAR entries
header_data = []
domain_header_map = defaultdict(lambda: defaultdict(set))  # domain → header → set of values
per_file_sessions = defaultdict(dict)  # file → {validation, client_data, channel, etc}

har_files = sorted(glob.glob(os.path.join(HAR_DIR, "*.har")))

for hf in har_files:
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    
    entries = data.get('log', {}).get('entries', [])
    for i, entry in enumerate(entries):
        url = entry.get('request', {}).get('url', '')
        req = entry.get('request', {})
        headers = {h['name'].lower(): h['value'] for h in req.get('headers', [])}
        
        # Only look at cross-site requests (REST/STORAGE/RECAPTCHA)
        if 'x-browser-channel' not in headers:
            continue
        
        # Determine domain
        if 'aisandbox-pa' in url:
            domain = 'REST (aisandbox-pa)'
        elif 'storage.googleapis' in url:
            domain = 'STORAGE'
        elif 'recaptcha' in url:
            domain = 'RECAPTCHA'
        else:
            domain = 'OTHER'
        
        channel = headers.get('x-browser-channel', '')
        copyright_h = headers.get('x-browser-copyright', '')
        validation = headers.get('x-browser-validation', '')
        year = headers.get('x-browser-year', '')
        client_data = headers.get('x-client-data', '')
        
        domain_header_map[domain]['channel'].add(channel)
        domain_header_map[domain]['copyright'].add(copyright_h)
        domain_header_map[domain]['validation'].add(validation)
        domain_header_map[domain]['year'].add(year)
        domain_header_map[domain]['client_data'].add(client_data)
        
        per_file_sessions[fname]['validation'] = per_file_sessions[fname].get('validation', set())
        per_file_sessions[fname]['validation'].add(validation)
        per_file_sessions[fname]['client_data'] = per_file_sessions[fname].get('client_data', set())
        per_file_sessions[fname]['client_data'].add(client_data)
        
        header_data.append({
            'file': fname,
            'domain': domain,
            'url_short': url.split('?')[0][-60:],
            'channel': channel,
            'copyright': copyright_h,
            'validation': validation,
            'year': year,
            'client_data': client_data,
            'timestamp': entry.get('startedDateTime', '')[:19],
        })

# Analysis
lines = []
lines.append("=" * 90)
lines.append("CUSTOM HEADERS (x-browser-*) DEEP INVESTIGATION")
lines.append(f"Total requests with x-browser-* headers: {len(header_data)}")
lines.append("=" * 90)

# 1. Unique values per header
lines.append("\n\n### 1. UNIQUE VALUES PER HEADER (across ALL domains)")
lines.append("-" * 60)

all_channels = set(h['channel'] for h in header_data)
all_copyrights = set(h['copyright'] for h in header_data)
all_validations = set(h['validation'] for h in header_data)
all_years = set(h['year'] for h in header_data)
all_client_data = set(h['client_data'] for h in header_data)

lines.append(f"\nx-browser-channel ({len(all_channels)} unique):")
for v in sorted(all_channels):
    count = sum(1 for h in header_data if h['channel'] == v)
    lines.append(f"  '{v}' → {count} requests")

lines.append(f"\nx-browser-copyright ({len(all_copyrights)} unique):")
for v in sorted(all_copyrights):
    count = sum(1 for h in header_data if h['copyright'] == v)
    lines.append(f"  '{v}' → {count} requests")

lines.append(f"\nx-browser-year ({len(all_years)} unique):")
for v in sorted(all_years):
    count = sum(1 for h in header_data if h['year'] == v)
    lines.append(f"  '{v}' → {count} requests")

lines.append(f"\nx-browser-validation ({len(all_validations)} unique):")
for v in sorted(all_validations):
    count = sum(1 for h in header_data if h['validation'] == v)
    files_with = set(h['file'] for h in header_data if h['validation'] == v)
    lines.append(f"  '{v}' → {count} requests across {len(files_with)} files")
    # Analyze: base64 decode length
    try:
        decoded = base64.b64decode(v)
        lines.append(f"    Base64 decoded: {len(decoded)} bytes, hex: {decoded.hex()}")
    except:
        lines.append(f"    Not valid base64")

lines.append(f"\nx-client-data ({len(all_client_data)} unique):")
for v in sorted(all_client_data):
    count = sum(1 for h in header_data if h['client_data'] == v)
    files_with = set(h['file'] for h in header_data if h['client_data'] == v)
    lines.append(f"  '{v}' → {count} requests across {len(files_with)} files")
    try:
        decoded = base64.b64decode(v)
        lines.append(f"    Base64 decoded: {len(decoded)} bytes, hex: {decoded.hex()}")
    except:
        lines.append(f"    Not valid base64")

# 2. Per-domain breakdown
lines.append("\n\n### 2. HEADER CONSISTENCY PER DOMAIN")
lines.append("-" * 60)
for domain in sorted(domain_header_map.keys()):
    hm = domain_header_map[domain]
    count = sum(1 for h in header_data if h['domain'] == domain)
    lines.append(f"\n[{domain}] ({count} requests):")
    for header_name, values in sorted(hm.items()):
        if len(values) == 1:
            lines.append(f"  {header_name}: CONSTANT = '{list(values)[0][:50]}'")
        else:
            lines.append(f"  {header_name}: {len(values)} VARIANTS:")
            for v in sorted(values):
                c = sum(1 for h in header_data if h['domain'] == domain and h.get(header_name if header_name != 'client_data' else 'client_data') == v)
                lines.append(f"    '{v[:50]}' ({c} requests)")

# 3. Per-file session analysis
lines.append("\n\n### 3. VALIDATION VALUE VS FILE (session correlation)")
lines.append("-" * 60)
lines.append("Does x-browser-validation change WITHIN a single HAR file (= single browser session)?")
for fname in sorted(per_file_sessions.keys()):
    vals = per_file_sessions[fname].get('validation', set())
    cds = per_file_sessions[fname].get('client_data', set())
    change_flag = "⚠️ CHANGES" if len(vals) > 1 else "✅ CONSTANT"
    cd_flag = "⚠️ CHANGES" if len(cds) > 1 else "✅ CONSTANT"
    lines.append(f"  {fname[:55]:55s} | validation: {change_flag} ({len(vals)}) | client_data: {cd_flag} ({len(cds)})")

# 4. Timestamp correlation
lines.append("\n\n### 4. VALIDATION VALUE VS TIMESTAMP (time-based pattern?)")
lines.append("-" * 60)
# Group by validation value, show date range
for val in sorted(all_validations):
    entries_with = [(h['timestamp'], h['file']) for h in header_data if h['validation'] == val]
    entries_with.sort()
    first_ts = entries_with[0][0]
    last_ts = entries_with[-1][0]
    lines.append(f"  '{val}':")
    lines.append(f"    Time range: {first_ts} → {last_ts}")
    lines.append(f"    Files: {len(set(e[1] for e in entries_with))}")

# 5. Requests WITHOUT x-browser-* (TRPC)
lines.append("\n\n### 5. REQUESTS WITHOUT x-browser-* (TRPC/AUTH verification)")
lines.append("-" * 60)
trpc_count = 0
trpc_with_xbrowser = 0
for hf in har_files[:5]:  # Sample first 5
    fname = os.path.basename(hf)
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        continue
    entries = data.get('log', {}).get('entries', [])
    for entry in entries:
        url = entry.get('request', {}).get('url', '')
        if '/fx/api/trpc/' in url:
            headers = {h['name'].lower() for h in entry.get('request', {}).get('headers', [])}
            trpc_count += 1
            if 'x-browser-channel' in headers:
                trpc_with_xbrowser += 1
lines.append(f"  TRPC calls sampled (first 5 files): {trpc_count}")
lines.append(f"  TRPC with x-browser-*: {trpc_with_xbrowser}")
lines.append(f"  → TRPC {'NEVER' if trpc_with_xbrowser == 0 else 'SOMETIMES'} has custom headers")

output = "\n".join(lines)
print(output)

with open(r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\custom_headers_investigation.txt", 'w', encoding='utf-8') as f:
    f.write(output)
print(f"\n\nSaved to custom_headers_investigation.txt")
