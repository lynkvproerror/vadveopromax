"""
Raw Header Dump - Inspects actual headers from HAR files for specific endpoints.
Goal: Verify if Cookie header and API key are really present/absent.
"""
import json, os, re, sys

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_header_dump.txt")

def main():
    har_files = sorted([f for f in os.listdir(HAR_DIR) if f.endswith('.har')])
    
    # Target: one sample each of different endpoint types
    targets = {
        "TRPC_sample": {"pattern": "trpc", "found": False, "max": 2},
        "AUTH_sample": {"pattern": "/fx/api/auth/session", "found": False, "max": 1},
        "REST_GET_credits": {"pattern": "/v1/credits", "found": False, "max": 1},
        "REST_GET_media": {"pattern": "/v1/media/", "found": False, "max": 1},
        "REST_POST_generate_video": {"pattern": "batchAsyncGenerateVideo", "found": False, "max": 2},
        "REST_POST_generate_image": {"pattern": "batchGenerateImages", "found": False, "max": 1},
        "REST_POST_upsample": {"pattern": "upsampleImage", "found": False, "max": 1},
        "REST_POST_upsample_video": {"pattern": "UpsampleVideo", "found": False, "max": 1},
        "REST_POST_poll": {"pattern": "batchCheckAsync", "found": False, "max": 1},
        "REST_POST_upload": {"pattern": "uploadUserImage", "found": False, "max": 1},
        "REST_POST_checkApp": {"pattern": "checkAppAvailability", "found": False, "max": 1},
        "REST_POST_recommend": {"pattern": "fetchUserRecommendations", "found": False, "max": 1},
        "REST_POST_gif": {"pattern": "generatePinholeGif", "found": False, "max": 1},
        "REST_POST_whisk_credit": {"pattern": "getVideoCreditStatus", "found": False, "max": 1},
        "RECAPTCHA_reload": {"pattern": "recaptcha/enterprise/reload", "found": False, "max": 1},
        "STORAGE_download": {"pattern": "storage.googleapis.com", "found": False, "max": 1},
    }
    
    counts = {k: 0 for k in targets}
    
    for har_file in har_files:
        filepath = os.path.join(HAR_DIR, har_file)
        try:
            data = json.load(open(filepath, 'r', encoding='utf-8'))
        except:
            continue
        
        for entry in data.get("log", {}).get("entries", []):
            url = entry.get("request", {}).get("url", "")
            method = entry.get("request", {}).get("method", "")
            
            for target_name, target_info in targets.items():
                if target_info["pattern"] in url and counts[target_name] < target_info["max"]:
                    counts[target_name] += 1
                    
                    print(f"\n{'='*100}")
                    print(f"TARGET: {target_name} (sample {counts[target_name]})")
                    print(f"FILE: {har_file}")
                    print(f"METHOD: {method}")
                    print(f"URL: {url[:200]}")
                    print(f"{'='*100}")
                    
                    # ALL request headers
                    headers = entry.get("request", {}).get("headers", [])
                    print(f"\n  REQUEST HEADERS ({len(headers)} total):")
                    for h in headers:
                        name = h["name"]
                        value = h["value"]
                        # Highlight auth-related headers
                        is_auth = any(kw in name.lower() for kw in [
                            "cookie", "authorization", "x-goog", "x-browser", 
                            "x-client", "x-same", "x-framework"
                        ])
                        marker = " ⭐" if is_auth else ""
                        if len(value) > 120:
                            value = value[:60] + " ... " + value[-40:]
                        print(f"    {name}: {value}{marker}")
                    
                    # Cookies array
                    cookies = entry.get("request", {}).get("cookies", [])
                    print(f"\n  COOKIES ARRAY ({len(cookies)} items):")
                    for c in cookies[:10]:
                        print(f"    {c.get('name','?')}: {str(c.get('value',''))[:60]}")
                    if len(cookies) > 10:
                        print(f"    ... and {len(cookies)-10} more")
                    
                    # Query params
                    qp = entry.get("request", {}).get("queryString", [])
                    if qp:
                        print(f"\n  QUERY PARAMS ({len(qp)}):")
                        for p in qp:
                            val = str(p.get('value', ''))
                            if len(val) > 80:
                                val = val[:40] + "..." + val[-20:]
                            print(f"    {p.get('name','?')}: {val}")
                    
                    # POST data (first 500 chars to see structure)
                    post_data = entry.get("request", {}).get("postData", {})
                    if post_data:
                        text = post_data.get("text", "")
                        mime = post_data.get("mimeType", "")
                        print(f"\n  POST DATA (mime: {mime}, length: {len(text)}):")
                        # Check for API key in body
                        if "AIzaSy" in text:
                            idx = text.index("AIzaSy")
                            print(f"    ⭐ API KEY FOUND IN BODY at position {idx}:")
                            print(f"    ...{text[max(0,idx-20):idx+50]}...")
                        else:
                            print(f"    No API key (AIzaSy) found in body")
                        
                        # Show first part of body
                        if len(text) > 300:
                            print(f"    Body preview: {text[:300]}...")
                        else:
                            print(f"    Body: {text}")
                    
                    print()

if __name__ == "__main__":
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        old = sys.stdout
        sys.stdout = f
        main()
        sys.stdout = old
    print(f"Output written to: {OUT_FILE}")
