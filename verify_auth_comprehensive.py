"""
Comprehensive Auth Verification - Checks ALL auth patterns in ALL HAR files.
Verifies:
  1. Cookies (via Cookie header string, not just cookies array)
  2. API Key location (query, header, URL path, body)
  3. All custom headers individually
  4. reCAPTCHA token location (payload fields)
  5. Signed URL params
  6. Authorization header
  7. Content-Type
  8. Any unknown/undocumented auth patterns
  9. Complete endpoint inventory
"""
import json, os, re, sys
from collections import defaultdict

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_auth_comprehensive_output.txt")

API_KEY = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"

def get_headers_dict(entry):
    return {h["name"].lower(): h["value"] for h in entry.get("request", {}).get("headers", [])}

def get_cookie_header(entry):
    headers = get_headers_dict(entry)
    return headers.get("cookie", "")

def get_api_key_locations(entry):
    url = entry.get("request", {}).get("url", "")
    headers = get_headers_dict(entry)
    post_text = entry.get("request", {}).get("postData", {}).get("text", "")
    
    locations = []
    if f"key={API_KEY}" in url or "key=AIza" in url:
        locations.append("URL_query")
    if headers.get("x-goog-api-key", "") != "":
        locations.append("header_x-goog-api-key")
    if API_KEY in post_text:
        locations.append("body")
    # Check URL path for API key pattern
    if "/AIza" in url and "key=" not in url:
        locations.append("URL_path")
    return locations

def get_all_custom_headers(entry):
    headers = get_headers_dict(entry)
    found = {}
    check_headers = [
        "x-browser-channel", "x-browser-copyright", "x-browser-year", 
        "x-browser-validation", "x-client-data",
        "x-goog-api-key", "x-goog-recaptcha-token",
        "authorization", "x-goog-authuser", "x-goog-visitor-id",
        "x-same-domain", "x-framework-xsrf-token"
    ]
    for h in check_headers:
        if h in headers:
            val = headers[h]
            if len(val) > 80:
                val = val[:40] + "..." + val[-20:]
            found[h] = val
    return found

def get_recaptcha_details(entry):
    post_text = entry.get("request", {}).get("postData", {}).get("text", "")
    if not post_text:
        return None
    try:
        data = json.loads(post_text)
    except:
        return None
    
    # Check nested clientContext.recaptchaContext
    def find_recaptcha(obj, path=""):
        results = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                cur = f"{path}.{k}" if path else k
                if k == "recaptchaContext" or k == "recaptchaToken":
                    results.append(cur)
                results.extend(find_recaptcha(v, cur))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                results.extend(find_recaptcha(v, f"{path}[{i}]"))
        return results
    
    paths = find_recaptcha(data)
    return paths if paths else None

def classify_endpoint(url, method):
    if "/fx/api/auth/" in url:
        path = re.search(r'/fx/api/auth/([^?]+)', url)
        return "AUTH", f"{method} /fx/api/auth/{path.group(1)}" if path else f"{method} /fx/api/auth/?"
    
    trpc_match = re.search(r'/fx/api/trpc/([^?]+)', url)
    if trpc_match:
        # Split batch TRPC calls
        procs = trpc_match.group(1).split(",")
        return "TRPC", ",".join(sorted(procs))
    
    if "recaptcha/enterprise" in url:
        if "/reload" in url: return "RECAPTCHA", "POST recaptcha/enterprise/reload"
        if "/clr" in url: return "RECAPTCHA", "POST recaptcha/enterprise/clr"
        if "/anchor" in url: return "RECAPTCHA", "GET recaptcha/enterprise/anchor"
        return "RECAPTCHA", f"{method} recaptcha/enterprise/other"
    
    if "storage.googleapis.com" in url:
        return "STORAGE", f"{method} storage.googleapis.com"
    
    if "aisandbox-pa.googleapis.com" in url:
        path_match = re.search(r'googleapis\.com(/v\d+/[^?]+)', url)
        if path_match:
            path = path_match.group(1)
            # Normalize dynamic IDs
            path = re.sub(r'/projects/[a-f0-9-]+/', '/projects/{id}/', path)
            path = re.sub(r'/media/[A-Za-z0-9_=-]+', '/media/{id}', path)
            return "REST", f"{method} {path}"
        # Check for path without /v1/
        return "REST", f"{method} aisandbox(unknown)"
    
    return None, None

def main():
    endpoint_data = defaultdict(lambda: {
        "occurrences": 0,
        "files": set(),
        "methods": set(),
        "has_cookie_header": {"yes": 0, "no": 0},
        "cookie_names": set(),
        "api_key_locations": defaultdict(int),
        "custom_headers_present": defaultdict(int),
        "custom_headers_absent": defaultdict(int),
        "recaptcha_paths": set(),
        "has_recaptcha_payload": 0,
        "no_recaptcha_payload": 0,
        "has_signed_url": 0,
        "content_types": set(),
        "all_header_names": set(),
        "sample_url": "",
    })
    
    har_files = sorted([f for f in os.listdir(HAR_DIR) if f.endswith('.har')])
    print(f"Processing {len(har_files)} HAR files from: {HAR_DIR}\n")
    
    skipped = 0
    for har_file in har_files:
        filepath = os.path.join(HAR_DIR, har_file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                har_data = json.load(f)
        except Exception as e:
            print(f"ERROR reading {har_file}: {e}")
            continue
        
        for entry in har_data.get("log", {}).get("entries", []):
            url = entry.get("request", {}).get("url", "")
            method = entry.get("request", {}).get("method", "")
            
            cat, ep_name = classify_endpoint(url, method)
            if not cat:
                skipped += 1
                continue
            
            key = f"{cat}|{ep_name}"
            d = endpoint_data[key]
            d["occurrences"] += 1
            d["files"].add(har_file)
            d["methods"].add(method)
            if not d["sample_url"]:
                d["sample_url"] = url[:150]
            
            # 1. Cookie header check
            cookie_str = get_cookie_header(entry)
            if cookie_str:
                d["has_cookie_header"]["yes"] += 1
                for part in cookie_str.split(";"):
                    name = part.strip().split("=")[0].strip()
                    if name:
                        d["cookie_names"].add(name)
            else:
                d["has_cookie_header"]["no"] += 1
            
            # 2. API Key
            for loc in get_api_key_locations(entry):
                d["api_key_locations"][loc] += 1
            
            # 3. Custom headers
            all_headers = get_headers_dict(entry)
            d["all_header_names"].update(all_headers.keys())
            custom = get_all_custom_headers(entry)
            for h in ["x-browser-channel", "x-browser-copyright", "x-browser-year", "x-browser-validation", "x-client-data"]:
                if h in custom:
                    d["custom_headers_present"][h] += 1
                else:
                    d["custom_headers_absent"][h] += 1
            for h in ["x-goog-api-key", "x-goog-recaptcha-token", "authorization", 
                       "x-goog-authuser", "x-same-domain", "x-framework-xsrf-token"]:
                if h in custom:
                    d["custom_headers_present"][h] += 1
            
            # 4. reCAPTCHA in payload
            recap_paths = get_recaptcha_details(entry)
            if recap_paths:
                d["has_recaptcha_payload"] += 1
                d["recaptcha_paths"].update(recap_paths)
            else:
                d["no_recaptcha_payload"] += 1
            
            # 5. Signed URL
            if "GoogleAccessId=" in url and "Signature=" in url:
                d["has_signed_url"] += 1
            
            # 6. Content-Type
            ct = all_headers.get("content-type", "")
            if ct:
                d["content_types"].add(ct.split(";")[0].strip())
    
    print(f"Skipped {skipped} non-API requests (CSS, JS, images, etc.)\n")
    
    # ==================== SECTION 1: Full Auth Matrix ====================
    print("=" * 120)
    print("SECTION 1: FULL AUTH MATRIX PER ENDPOINT (Normalized)")
    print("=" * 120)
    
    for cat in ["AUTH", "TRPC", "REST", "RECAPTCHA", "STORAGE"]:
        cat_eps = {k: v for k, v in endpoint_data.items() if k.startswith(f"{cat}|")}
        if not cat_eps:
            continue
        
        print(f"\n{'='*60}")
        print(f"  CATEGORY: {cat} ({len(cat_eps)} unique endpoints)")
        print(f"{'='*60}")
        
        for key in sorted(cat_eps.keys()):
            d = cat_eps[key]
            ep = key.split("|", 1)[1]
            total = d["occurrences"]
            
            print(f"\n  [{ep}]")
            print(f"    Occurrences: {total} across {len(d['files'])} files")
            
            # Cookie
            yes_c = d["has_cookie_header"]["yes"]
            no_c = d["has_cookie_header"]["no"]
            cookie_pct = (yes_c / total * 100) if total > 0 else 0
            print(f"    Cookie header: {yes_c}/{total} ({cookie_pct:.0f}%)")
            if d["cookie_names"]:
                names = sorted(d["cookie_names"])
                print(f"      Cookie names: {', '.join(names[:10])}")
                if len(names) > 10:
                    print(f"        ... and {len(names)-10} more")
            
            # API Key
            if d["api_key_locations"]:
                locs = dict(d["api_key_locations"])
                print(f"    API Key: {locs}")
            else:
                print(f"    API Key: NONE")
            
            # Custom x-browser-* headers
            browser_h = ["x-browser-channel", "x-browser-copyright", "x-browser-year", "x-browser-validation", "x-client-data"]
            present_counts = {h: d["custom_headers_present"].get(h, 0) for h in browser_h}
            all_present = all(c == total for c in present_counts.values())
            any_present = any(c > 0 for c in present_counts.values())
            if all_present:
                print(f"    Custom Headers (5/5): ALL PRESENT in every request")
            elif any_present:
                for h in browser_h:
                    p = present_counts[h]
                    print(f"    {h}: {p}/{total}")
            else:
                print(f"    Custom Headers: NONE")
            
            # Special headers
            for h in ["x-goog-api-key", "x-goog-recaptcha-token", "authorization", 
                       "x-goog-authuser", "x-same-domain", "x-framework-xsrf-token"]:
                c = d["custom_headers_present"].get(h, 0)
                if c > 0:
                    print(f"    SPECIAL HEADER [{h}]: {c}/{total}")
            
            # reCAPTCHA in payload
            if d["has_recaptcha_payload"] > 0:
                print(f"    reCAPTCHA in payload: YES ({d['has_recaptcha_payload']}/{total})")
                print(f"      Paths: {', '.join(sorted(d['recaptcha_paths']))}")
            else:
                print(f"    reCAPTCHA in payload: NO")
            
            # Signed URL
            if d["has_signed_url"] > 0:
                print(f"    Signed URL: YES ({d['has_signed_url']}/{total})")
            
            # Content-Type
            if d["content_types"]:
                print(f"    Content-Type: {', '.join(sorted(d['content_types']))}")
    
    # ==================== SECTION 2: Cookies Deep Dive ====================
    print(f"\n\n{'='*120}")
    print("SECTION 2: COOKIES DEEP DIVE")
    print("=" * 120)
    
    all_cookie_names = set()
    for d in endpoint_data.values():
        all_cookie_names.update(d["cookie_names"])
    
    print(f"\nAll unique cookie names found across all endpoints ({len(all_cookie_names)}):")
    for name in sorted(all_cookie_names):
        print(f"  - {name}")
    
    # Which categories have cookies?
    for cat in ["AUTH", "TRPC", "REST", "RECAPTCHA", "STORAGE"]:
        cat_eps = {k: v for k, v in endpoint_data.items() if k.startswith(f"{cat}|")}
        if not cat_eps:
            continue
        total_with = sum(1 for d in cat_eps.values() if d["has_cookie_header"]["yes"] > 0)
        total_without = sum(1 for d in cat_eps.values() if d["has_cookie_header"]["yes"] == 0)
        print(f"\n  {cat}: {total_with} endpoints WITH cookies, {total_without} WITHOUT")
    
    # ==================== SECTION 3: TRPC Special Headers ====================
    print(f"\n\n{'='*120}")
    print("SECTION 3: TRPC AUTHENTICATION DETAILS")
    print("=" * 120)
    
    trpc_eps = {k: v for k, v in endpoint_data.items() if k.startswith("TRPC|")}
    for key in sorted(trpc_eps.keys()):
        d = trpc_eps[key]
        ep = key.split("|", 1)[1]
        total = d["occurrences"]
        
        # Check for x-same-domain and other TRPC-specific headers
        special = {}
        for h in ["x-same-domain", "x-framework-xsrf-token", "x-goog-authuser"]:
            c = d["custom_headers_present"].get(h, 0)
            if c > 0:
                special[h] = c
        
        has_cookies = d["has_cookie_header"]["yes"]
        print(f"  {ep}: cookies={has_cookies}/{total}, special_headers={special if special else 'none'}")
    
    # ==================== SECTION 4: REST API Key Analysis ====================
    print(f"\n\n{'='*120}")
    print("SECTION 4: REST POST API KEY DEEP ANALYSIS")
    print("=" * 120)
    
    rest_post_eps = {k: v for k, v in endpoint_data.items() 
                     if k.startswith("REST|") and "POST" in k}
    for key in sorted(rest_post_eps.keys()):
        d = rest_post_eps[key]
        ep = key.split("|", 1)[1]
        total = d["occurrences"]
        api_locs = dict(d["api_key_locations"]) if d["api_key_locations"] else "NONE"
        has_goog_key = d["custom_headers_present"].get("x-goog-api-key", 0)
        print(f"  {ep}")
        print(f"    Total: {total}, API Key locations: {api_locs}, x-goog-api-key header: {has_goog_key}/{total}")
    
    # ==================== SECTION 5: Gap Analysis ====================
    print(f"\n\n{'='*120}")
    print("SECTION 5: GAP ANALYSIS - Endpoints in HAR but possibly NOT in doc §1.4.D")
    print("=" * 120)
    
    documented_endpoints = [
        "GET /fx/api/auth/session",
        "project.createProject", "project.getProject", "project.searchProjectScenes",
        "project.searchProjectWorkflows",
        "videoFx.getUserSettings", "videoFx.getVideoModelConfig", "videoFx.getFlowAppConfig",
        "videoFx.listPreambles", "videoFx.setLastSelectedVideoModelKey", 
        "videoFx.setLastSelectedVideoAspectRatio",
        "general.fetchUserPreferences", "general.fetchUserAcknowledgement",
        "general.fetchUserLocale", "general.submitBatchLog", "general.reportClientSideError",
        "media.fetchFlowUserIngredients", "media.fetchUserHistoryDirectly",
        "recaptcha/enterprise/reload", "recaptcha/enterprise/clr",
        "/v1/credits", "checkAppAvailability", "fetchUserRecommendations",
        "getVideoCreditStatus", "/v1/media/",
        "batchAsyncGenerateVideo", "batchAsync...StartImage", "batchAsync...StartAndEndImage",
        "batchAsync...ReferenceImages", "batchAsync...Reshoot", "batchAsync...ExtendVideo",
        "batchAsync...UpsampleVideo",
        "batchGenerateImages", "upsampleImage", "generateVideoGif",
        "batchCheckAsync", "uploadUserImage",
        "storage.googleapis.com",
        "submitBatchLog", "reportClientSideError",
        # Whisk
        "getWhiskRecentMediaGroupIds",
        # TRPC extras
        "general.fetchFeatureAvailability", "general.fetchToolAvailability",
        "general.submitUserAcknowledgement",
    ]
    
    print("\nEndpoints found in HAR but possibly UNDOCUMENTED:")
    for key in sorted(endpoint_data.keys()):
        ep = key.split("|", 1)[1]
        found = False
        for doc_ep in documented_endpoints:
            if doc_ep.lower() in ep.lower():
                found = True
                break
        if not found:
            d = endpoint_data[key]
            print(f"  ❓ {ep} (count: {d['occurrences']}, files: {len(d['files'])})")
    
    # ==================== SECTION 6: Complete Endpoint Inventory ====================
    print(f"\n\n{'='*120}")
    print("SECTION 6: COMPLETE ENDPOINT INVENTORY")
    print("=" * 120)
    
    for cat in ["AUTH", "TRPC", "REST", "RECAPTCHA", "STORAGE"]:
        cat_eps = {k: v for k, v in endpoint_data.items() if k.startswith(f"{cat}|")}
        if not cat_eps:
            continue
        print(f"\n  {cat} ({len(cat_eps)} unique):")
        for key in sorted(cat_eps.keys()):
            d = cat_eps[key]
            ep = key.split("|", 1)[1]
            print(f"    {ep} [{d['occurrences']} calls, {len(d['files'])} files]")
    
    # ==================== SECTION 7: Summary Stats ====================
    print(f"\n\n{'='*120}")
    print("SECTION 7: SUMMARY STATISTICS")
    print("=" * 120)
    
    total_endpoints = len(endpoint_data)
    total_requests = sum(d["occurrences"] for d in endpoint_data.values())
    
    print(f"\n  Total unique endpoints: {total_endpoints}")
    print(f"  Total API requests analyzed: {total_requests}")
    print(f"  Total HAR files: {len(har_files)}")
    print(f"  Skipped non-API requests: {skipped}")
    
    # Auth method summary
    has_bearer = [k for k, d in endpoint_data.items() if d["custom_headers_present"].get("authorization", 0) > 0]
    has_recap_header = [k for k, d in endpoint_data.items() if d["custom_headers_present"].get("x-goog-recaptcha-token", 0) > 0]
    has_recap_payload = [k for k, d in endpoint_data.items() if d["has_recaptcha_payload"] > 0]
    has_signed = [k for k, d in endpoint_data.items() if d["has_signed_url"] > 0]
    has_cookies = [k for k, d in endpoint_data.items() if d["has_cookie_header"]["yes"] > 0]
    has_api_key = [k for k, d in endpoint_data.items() if len(d["api_key_locations"]) > 0]
    has_custom5 = [k for k, d in endpoint_data.items() 
                   if all(d["custom_headers_present"].get(h, 0) > 0 
                          for h in ["x-browser-channel", "x-browser-copyright", "x-browser-year", "x-browser-validation", "x-client-data"])]
    
    print(f"\n  Auth Method Distribution:")
    print(f"    Endpoints with Cookie header:      {len(has_cookies)}/{total_endpoints}")
    print(f"    Endpoints with API Key:             {len(has_api_key)}/{total_endpoints}")
    print(f"    Endpoints with Custom Headers 5/5:  {len(has_custom5)}/{total_endpoints}")
    print(f"    Endpoints with reCAPTCHA payload:    {len(has_recap_payload)}/{total_endpoints}")
    print(f"    Endpoints with Signed URL:           {len(has_signed)}/{total_endpoints}")
    print(f"    Endpoints with Authorization hdr:    {len(has_bearer)}/{total_endpoints}")
    print(f"    Endpoints with x-goog-recaptcha hdr: {len(has_recap_header)}/{total_endpoints}")

if __name__ == "__main__":
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        old = sys.stdout
        sys.stdout = f
        main()
        sys.stdout = old
    print(f"Output written to: {OUT_FILE}")
