"""
Verify Authentication Methods per Endpoint from ALL HAR files.
Extracts actual headers and payload auth fields for each unique endpoint.
"""
import json
import os
import re
from collections import defaultdict

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"

# Auth detection functions
def has_cookie(entry):
    """Check if request has cookies"""
    cookies = entry.get("request", {}).get("cookies", [])
    cookie_header = next((h["value"] for h in entry.get("request", {}).get("headers", []) if h["name"].lower() == "cookie"), "")
    return len(cookies) > 0 or len(cookie_header) > 0

def get_api_key_location(entry):
    """Check API key: query param or header"""
    req = entry.get("request", {})
    url = req.get("url", "")
    headers = {h["name"].lower(): h["value"] for h in req.get("headers", [])}
    
    locations = []
    if "key=" in url:
        locations.append("query")
    if "x-goog-api-key" in headers:
        locations.append("header")
    return locations

def get_custom_headers(entry):
    """Check which x-browser-* and x-client-data headers are present"""
    headers = {h["name"].lower(): h["value"] for h in entry.get("request", {}).get("headers", [])}
    found = []
    for h in ["x-browser-channel", "x-browser-copyright", "x-browser-year", "x-browser-validation", "x-client-data"]:
        if h in headers:
            found.append(h)
    return found

def has_recaptcha_in_payload(entry):
    """Check if reCAPTCHA token is in request payload body"""
    post_data = entry.get("request", {}).get("postData", {})
    text = post_data.get("text", "")
    if not text:
        return False, None
    
    # Check for recaptchaContext in payload
    if "recaptchaContext" in text:
        return True, "payload"
    return False, None

def has_recaptcha_in_header(entry):
    """Check if reCAPTCHA token is in header (the WRONG way)"""
    headers = {h["name"].lower(): h["value"] for h in entry.get("request", {}).get("headers", [])}
    return "x-goog-recaptcha-token" in headers

def has_authorization_header(entry):
    """Check for Authorization: Bearer header"""
    headers = {h["name"].lower(): h["value"] for h in entry.get("request", {}).get("headers", [])}
    auth = headers.get("authorization", "")
    return "bearer" in auth.lower() if auth else False

def has_signed_url(entry):
    """Check for signed URL params"""
    url = entry.get("request", {}).get("url", "")
    return "GoogleAccessId=" in url and "Signature=" in url

def classify_endpoint(url, method):
    """Classify endpoint into category and name"""
    # AUTH
    if "/fx/api/auth/session" in url:
        return "AUTH", "GET /fx/api/auth/session"
    
    # TRPC
    trpc_match = re.search(r'/fx/api/trpc/([^?]+)', url)
    if trpc_match:
        procedures = trpc_match.group(1)
        return "TRPC", procedures
    
    # RECAPTCHA
    if "recaptcha/enterprise" in url:
        if "/reload" in url:
            return "RECAPTCHA", "recaptcha/enterprise/reload"
        if "/clr" in url:
            return "RECAPTCHA", "recaptcha/enterprise/clr"
        return "RECAPTCHA", "recaptcha/other"
    
    # STORAGE
    if "storage.googleapis.com" in url:
        return "STORAGE", "storage.googleapis.com/download"
    
    # REST (aisandbox-pa)
    if "aisandbox-pa.googleapis.com" in url:
        path_match = re.search(r'googleapis\.com(/v\d+/.+?)(?:\?|$)', url)
        if path_match:
            path = path_match.group(1)
            # Remove project IDs
            path = re.sub(r'/projects/[a-f0-9-]+/', '/projects/{projectId}/', path)
            return "REST", f"{method} {path}"
        return "REST", f"{method} (unknown path)"
    
    return None, None

def main():
    # Collect auth info per endpoint
    endpoint_auth = defaultdict(lambda: {
        "files": set(),
        "occurrences": 0,
        "has_cookie": set(),
        "api_key_location": set(),
        "custom_headers": defaultdict(int),
        "recaptcha_payload": set(),
        "recaptcha_header": set(),
        "authorization_bearer": set(),
        "signed_url": set(),
    })
    
    har_files = [f for f in os.listdir(HAR_DIR) if f.endswith('.har')]
    print(f"Processing {len(har_files)} HAR files...\n")
    
    for har_file in sorted(har_files):
        filepath = os.path.join(HAR_DIR, har_file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                har_data = json.load(f)
        except Exception as e:
            print(f"  ERROR reading {har_file}: {e}")
            continue
        
        entries = har_data.get("log", {}).get("entries", [])
        for entry in entries:
            url = entry.get("request", {}).get("url", "")
            method = entry.get("request", {}).get("method", "")
            
            category, endpoint_name = classify_endpoint(url, method)
            if not category:
                continue
            
            key = f"{category}:{endpoint_name}"
            info = endpoint_auth[key]
            info["files"].add(har_file)
            info["occurrences"] += 1
            info["has_cookie"].add(has_cookie(entry))
            info["api_key_location"].update(get_api_key_location(entry))
            
            custom = get_custom_headers(entry)
            for h in custom:
                info["custom_headers"][h] += 1
            
            has_recap, recap_loc = has_recaptcha_in_payload(entry)
            info["recaptcha_payload"].add(has_recap)
            info["recaptcha_header"].add(has_recaptcha_in_header(entry))
            info["authorization_bearer"].add(has_authorization_header(entry))
            info["signed_url"].add(has_signed_url(entry))
    
    # Print results
    print("=" * 140)
    print(f"{'ENDPOINT':<65} {'Count':>5} {'Cookie':>7} {'APIKey':>12} {'Headers':>8} {'reCAPT':>10} {'Bearer':>7} {'SignURL':>8}")
    print("=" * 140)
    
    # Group by category
    for category in ["AUTH", "TRPC", "REST", "RECAPTCHA", "STORAGE"]:
        cat_endpoints = {k: v for k, v in endpoint_auth.items() if k.startswith(f"{category}:")}
        if not cat_endpoints:
            continue
        
        print(f"\n--- {category} ---")
        for key in sorted(cat_endpoints.keys()):
            info = cat_endpoints[key]
            endpoint_display = key.split(":", 1)[1][:60]
            
            cookie_str = "YES" if True in info["has_cookie"] else "NO"
            
            api_key_parts = list(info["api_key_location"])
            api_key_str = ",".join(api_key_parts) if api_key_parts else "NO"
            
            num_custom = len(info["custom_headers"])
            headers_str = f"{num_custom}/5" if num_custom > 0 else "NO"
            
            recap_payload = True in info["recaptcha_payload"]
            recap_header = True in info["recaptcha_header"]
            if recap_payload and recap_header:
                recap_str = "PAYLOAD+HDR"
            elif recap_payload:
                recap_str = "PAYLOAD"
            elif recap_header:
                recap_str = "HEADER(!)"
            else:
                recap_str = "NO"
            
            bearer_str = "YES(!)" if True in info["authorization_bearer"] else "NO"
            signed_str = "YES" if True in info["signed_url"] else "NO"
            
            print(f"  {endpoint_display:<63} {info['occurrences']:>5} {cookie_str:>7} {api_key_str:>12} {headers_str:>8} {recap_str:>10} {bearer_str:>7} {signed_str:>8}")
    
    # Summary warnings
    print("\n" + "=" * 140)
    print("VERIFICATION SUMMARY")
    print("=" * 140)
    
    # Check for any Authorization: Bearer usage
    bearer_endpoints = [k for k, v in endpoint_auth.items() if True in v["authorization_bearer"]]
    if bearer_endpoints:
        print(f"\n⚠️  FOUND Authorization: Bearer in {len(bearer_endpoints)} endpoints:")
        for ep in bearer_endpoints:
            print(f"    - {ep}")
    else:
        print("\n✅ CONFIRMED: NO endpoint uses Authorization: Bearer header")
    
    # Check for reCAPTCHA in header (wrong way)
    recap_header_endpoints = [k for k, v in endpoint_auth.items() if True in v["recaptcha_header"]]
    if recap_header_endpoints:
        print(f"\n⚠️  FOUND x-goog-recaptcha-token HEADER in {len(recap_header_endpoints)} endpoints:")
        for ep in recap_header_endpoints:
            print(f"    - {ep}")
    else:
        print("\n✅ CONFIRMED: NO endpoint uses x-goog-recaptcha-token header")
    
    # List endpoints with reCAPTCHA in payload
    recap_payload_endpoints = [k for k, v in endpoint_auth.items() if True in v["recaptcha_payload"]]
    print(f"\n📋 Endpoints with reCAPTCHA token in PAYLOAD ({len(recap_payload_endpoints)}):")
    for ep in sorted(recap_payload_endpoints):
        print(f"    ✅ {ep}")
    
    # List endpoints WITHOUT reCAPTCHA
    no_recap_rest = [k for k, v in endpoint_auth.items() 
                     if k.startswith("REST:") and True not in v["recaptcha_payload"]]
    print(f"\n📋 REST endpoints WITHOUT reCAPTCHA ({len(no_recap_rest)}):")
    for ep in sorted(no_recap_rest):
        print(f"    ❌🤖 {ep}")
    
    # TRPC cookie verification
    trpc_endpoints = {k: v for k, v in endpoint_auth.items() if k.startswith("TRPC:")}
    trpc_all_cookie = all(True in v["has_cookie"] for v in trpc_endpoints.values())
    trpc_any_apikey = any(len(v["api_key_location"]) > 0 for v in trpc_endpoints.values())
    trpc_any_recap = any(True in v["recaptcha_payload"] for v in trpc_endpoints.values())
    print(f"\n📋 TRPC Auth Verification:")
    print(f"    All have cookies: {'✅ YES' if trpc_all_cookie else '❌ NO'}")
    print(f"    Any have API Key: {'❌ YES (unexpected!)' if trpc_any_apikey else '✅ NO (correct)'}")
    print(f"    Any have reCAPTCHA: {'❌ YES (unexpected!)' if trpc_any_recap else '✅ NO (correct)'}")
    
    print(f"\nTotal unique endpoints analyzed: {len(endpoint_auth)}")
    print(f"Total HAR files processed: {len(har_files)}")

if __name__ == "__main__":
    import sys
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_auth_output.txt")
    with open(out_path, 'w', encoding='utf-8') as f:
        old_stdout = sys.stdout
        sys.stdout = f
        main()
        sys.stdout = old_stdout
    print(f"Output written to: {out_path}")
