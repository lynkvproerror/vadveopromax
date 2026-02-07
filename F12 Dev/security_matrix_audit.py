import json
import os
import glob
from urllib.parse import urlparse, parse_qs

def analyze_security_matrix():
    base_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev"
    files = []
    files.extend(glob.glob(os.path.join(base_dir, "New", "*.har")))
    files.extend(glob.glob(os.path.join(base_dir, "Old", "*.har")))
    
    # Map: "POST /v1/video:generate" -> { "count": 10, "auth": 0, "cookie": 10, "recaptcha": 10, "api_key": 0, "x_browser": 10 }
    matrix = {}

    print(f"Scanning {len(files)} HAR files...")

    for f_path in files:
        fname = os.path.basename(f_path)
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries = data.get('log', {}).get('entries', [])
            for entry in entries:
                req = entry.get('request', {})
                url = req.get('url', '')
                method = req.get('method', 'UNKNOWN')
                
                # Filter relevant APIs
                if 'googleapis.com' not in url and 'labs.google' not in url:
                    continue
                if method == 'OPTIONS': # Skip CORS checks
                    continue
                if '/g/collect' in url or '/play/log' in url or 'google-analytics' in url:
                    continue

                # Normalize Endpoint
                parsed = urlparse(url)
                path = parsed.path
                
                # specific overrides for clarity
                if "batchAsyncGenerateVideoText" in path: normalized = "/video:generateText"
                elif "batchAsyncGenerateVideoStartAndEndImage" in path: normalized = "/video:generateStartEnd"
                elif "batchAsyncGenerateVideoUpsampleVideo" in path: normalized = "/video:upscaleVideo"
                elif "generatePinholeGif" in path: normalized = "/video:generateGif"
                elif "batchGenerateImages" in path: normalized = "/flowMedia:batchGenerateImages"
                elif "media.fetchUserHistoryDirectly" in path: normalized = "/media.fetchHistory"
                elif "project.searchProjectScenes" in path: normalized = "/project.searchScenes"
                elif "uploadUserImage" in path: normalized = "/uploadUserImage"
                elif "upsampleImage" in path: normalized = "/upsampleImage"
                elif "batchCheckAsyncVideoGenerationStatus" in path: normalized = "/video:checkStatus"
                elif path.startswith("/v1/media/") and len(path) > 15: normalized = "/v1/media/{ID}"
                elif path.startswith("/v1/projects/"): normalized = "/v1/projects/{ID}..."
                elif path.startswith("/v1/") and len(path.split('/')) == 3: normalized = f"/v1/{{ID}} ({method})" # generic resource
                else: 
                     # Better generic fallback
                     normalized = path
                     # simple UUID masking
                     parts = normalized.split('/')
                     masked = []
                     for p in parts:
                         if len(p) > 20 or (len(p) > 5 and any(c.isdigit() for c in p) and '-' in p):
                             masked.append("{ID}")
                         else:
                             masked.append(p)
                     normalized = "/".join(masked)

                key = f"{method} {normalized}"
                
                if key not in matrix:
                    matrix[key] = {
                        "total": 0,
                        "auth_bearer": 0,
                        "cookie": 0,
                        "api_key": 0,
                        "recaptcha": 0,
                        "x_browser": 0,
                        "client_tool": 0,
                        "files": set()
                    }
                
                stats = matrix[key]
                stats["total"] += 1
                stats["files"].add(fname)

                # Check Headers
                headers = {h['name'].lower(): h['value'] for h in req.get('headers', [])}
                
                if 'authorization' in headers and 'bearer' in headers['authorization'].lower():
                    stats["auth_bearer"] += 1
                if 'cookie' in headers:
                    stats["cookie"] += 1
                if any(k.startswith('x-browser-validation') for k in headers):
                    stats["x_browser"] += 1

                # Check Query Params
                qs = parse_qs(parsed.query)
                if 'key' in qs:
                    stats["api_key"] += 1
                if 'clientContext.tool' in qs:
                    stats["client_tool"] += 1

                # Check Body
                post_data = req.get('postData', {})
                if post_data and 'text' in post_data:
                    txt = post_data['text']
                    if 'recaptchaContext' in txt:
                        stats["recaptcha"] += 1
                    if 'clientContext' in txt and ('"tool":"PINHOLE"' in txt or '"tool": "PINHOLE"' in txt):
                        stats["client_tool"] += 1


        except Exception as e:
            pass # Skip malformed files

    # Output Table
    with open("security_compliance_matrix.md", "w", encoding="utf-8") as out:
        out.write("# VERIFIED SECURITY COMPLIANCE MATRIX\n")
        out.write(f"> Scanned {len(files)} HAR files.\n\n")
        out.write("| Method | Endpoint | Valid Auth (Bearer/Cookie) | reCAPTCHA | API Key | x-browser-* | Tool=PINHOLE | Notes |\n")
        out.write("|---|---|---|---|---|---|---|---|\n")

        for k in sorted(matrix.keys()):
            s = matrix[k]
            # No aggressive filtering this time, just empty check
            if s['total'] == 0: continue

            auth_status = "❌"
            if s['auth_bearer'] == s['total'] and s['total'] > 0: auth_status = "✅ Bearer"
            elif s['cookie'] > 0: auth_status = "⚠️ Cookie (Usually Stripped)"
            elif s['total'] > 0: auth_status = "❓ Stripped"

            recaptcha = "✅ REQUIRED" if s['recaptcha'] > 0 else "❌"
            apikey = "✅ REQUIRED" if s['api_key'] > 0 else "❌"
            x_browser = "✅ REQUIRED" if s['x_browser'] > 0 else "❌"
            tool = "✅ REQUIRED" if s['client_tool'] > 0 else "❌"
            
            # Extract clean endpoint
            endpoint_name = k.split(' ', 1)[1]
            method_name = k.split(' ', 1)[0]

            out.write(f"| {method_name} | `{endpoint_name}` | {auth_status} | {recaptcha} | {apikey} | {x_browser} | {tool} | Found in {len(s['files'])} files |\n")

    print("Matrix generated: security_compliance_matrix.md")

if __name__ == "__main__":
    analyze_security_matrix()
