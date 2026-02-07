import json
import os
import glob
from urllib.parse import urlparse, parse_qs

def get_files(base_dir):
    new_dir = os.path.join(base_dir, "New")
    old_dir = os.path.join(base_dir, "Old")
    files = []
    files.extend(glob.glob(os.path.join(new_dir, "*.har")))
    files.extend(glob.glob(os.path.join(old_dir, "*.har")))
    return files

def normalize_url(url):
    parsed = urlparse(url)
    path = parsed.path
    # Simple heuristic to replace UUID-like or long numeric segments with {ID}
    parts = path.split('/')
    new_parts = []
    for p in parts:
        if len(p) > 20 or (len(p) > 10 and '-' in p) or (p.isdigit() and len(p) > 5):
             new_parts.append("{ID}")
        else:
            new_parts.append(p)
    return "/".join(new_parts)

def analyze_hars():
    base_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev"
    files = get_files(base_path)
    
    endpoint_stats = {}

    print(f"Found {len(files)} HAR files.")

    for f_path in files:
        fname = os.path.basename(f_path)
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries = data.get('log', {}).get('entries', [])
            for entry in entries:
                req = entry.get('request', {})
                url = req.get('url', '')
                
                # Filter for google apis
                if 'googleapis.com' not in url and 'labs.google' not in url:
                    continue
                
                # Filter out obvious static assets if needed, but user said "don't ignore any file"
                # so we keep logic broad but maybe filter by extension if it gets noisy.
                # For now, let's keep API-like URLs.

                method = req.get('method')
                clean_path = normalize_url(url)
                
                key = f"{method} {clean_path}"
                
                if key not in endpoint_stats:
                    endpoint_stats[key] = {
                        "auth_bearer": False,
                        "api_key": False,
                        "recaptcha": False,
                        "client_tool": False,
                        "cookie": False,
                        "sources": set()
                    }
                
                stats = endpoint_stats[key]
                stats["sources"].add(fname)

                # Check headers
                headers = req.get('headers', [])
                for h in headers:
                    h_name = h['name'].lower()
                    if h_name == 'authorization' and 'bearer' in h['value'].lower():
                        stats["auth_bearer"] = True
                    if h_name == 'cookie':
                        stats["cookie"] = True

                # Check Query Params
                query_params = req.get('queryString', [])
                for q in query_params:
                    q_name = q['name']
                    if q_name == 'key':
                        stats["api_key"] = True
                    if 'clientContext.tool' in q_name: # Handle nested param format if present in query
                        stats["client_tool"] = True

                # Check Post Data (JSON)
                post_data = req.get('postData', {})
                if post_data and 'text' in post_data:
                    try:
                        body = json.loads(post_data['text'])
                        
                        # Check recursively for clientContext details if deep nested
                        # But typically it's at top level for these APIs
                        client_ctx = body.get('clientContext', {})
                        if client_ctx:
                            if 'tool' in client_ctx:
                                stats["client_tool"] = True
                            if 'recaptchaContext' in client_ctx:
                                stats["recaptcha"] = True
                    except:
                        pass
                        
        except Exception as e:
            print(f"Error processing {fname}: {e}")

    # Debug Mode: Dump headers for one request in Old directory
    base_old = os.path.join(base_path, "Old")
    old_files = glob.glob(os.path.join(base_old, "*.har"))
    
    with open("auth_header_dump.txt", "w", encoding="utf-8") as debug_out:
        if old_files:
            found_any = False
            for target_har in old_files:
                if found_any: break
                
                # debug_out.write(f"Inspecting file: {target_har}\\n") # Too verbose
                try:
                    with open(target_har, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    entries = data.get('log', {}).get('entries', [])
                    
                    for entry in entries:
                        req = entry.get('request', {})
                        if 'generateVideo' in req['url'] or 'googleapis.com/v1/video' in req['url']:
                            debug_out.write(f"\\nFound relevant request in: {target_har}\\n")
                            debug_out.write(f"URL: {req['url']}\\n")
                            debug_out.write("Headers found:\\n")
                            for h in req.get('headers', []):
                                # Mask value but show first few chars
                                val = h['value']
                                masked = val[:10] + "..." if len(val) > 10 else val
                                debug_out.write(f"  {h['name']}: {masked}\\n")
                            
                            # Check cookies array too
                            debug_out.write("Cookies found in object:\\n")
                            for c in req.get('cookies', []):
                                 debug_out.write(f"  {c['name']}\\n")
                                 
                            found_any = True
                            break 
                except Exception as e:
                    pass
            if not found_any:
                debug_out.write("No generateVideo/googleapis request found in ANY Old file.\\n")
        else:
            debug_out.write("No files found in Old directory.\\n")

    print("Debug dump complete. Results written to auth_header_dump.txt")

if __name__ == "__main__":
    analyze_hars()
