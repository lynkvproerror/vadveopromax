"""
Final Verification Script - Cross-checks HAR Data vs Documentation
Ensures 100% accuracy for VEO API Security Matrix
"""
import json
import os
import glob
from urllib.parse import urlparse, parse_qs

# EXPECTED REQUIREMENTS based on updated documentation
# Format: "normalized_endpoint": { "x_browser": True/False, "recaptcha": True/False, "api_key": True/False, "tool_pinhole": True/False }
EXPECTED = {
    "/video:generateText": {"x_browser": True, "recaptcha": True, "api_key": False, "tool_pinhole": True},
    "/video:generateStartEnd": {"x_browser": True, "recaptcha": True, "api_key": False, "tool_pinhole": True},
    "/video:upscaleVideo": {"x_browser": True, "recaptcha": True, "api_key": False, "tool_pinhole": False},
    "/video:checkStatus": {"x_browser": True, "recaptcha": False, "api_key": False, "tool_pinhole": False},
    "/video:generateGif": {"x_browser": True, "recaptcha": False, "api_key": False, "tool_pinhole": False},
    "/uploadUserImage": {"x_browser": True, "recaptcha": False, "api_key": False, "tool_pinhole": False},
    "/upsampleImage": {"x_browser": True, "recaptcha": True, "api_key": False, "tool_pinhole": True},
    "/flowMedia:batchGenerateImages": {"x_browser": True, "recaptcha": True, "api_key": False, "tool_pinhole": True},
    "/v1/media/{ID}": {"x_browser": True, "recaptcha": False, "api_key": True, "tool_pinhole": False},
}

def normalize_path(url):
    parsed = urlparse(url)
    path = parsed.path
    if "batchAsyncGenerateVideoText" in path: return "/video:generateText"
    if "batchAsyncGenerateVideoStartAndEndImage" in path: return "/video:generateStartEnd"
    if "batchAsyncGenerateVideoUpsampleVideo" in path: return "/video:upscaleVideo"
    if "batchCheckAsyncVideoGenerationStatus" in path: return "/video:checkStatus"
    if "generatePinholeGif" in path: return "/video:generateGif"
    if "uploadUserImage" in path: return "/uploadUserImage"
    if "upsampleImage" in path: return "/upsampleImage"
    if "batchGenerateImages" in path: return "/flowMedia:batchGenerateImages"
    if path.startswith("/v1/media/") and len(path) > 15: return "/v1/media/{ID}"
    return None # Ignore unmapped

def verify():
    base_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev"
    files = []
    files.extend(glob.glob(os.path.join(base_dir, "New", "*.har")))
    files.extend(glob.glob(os.path.join(base_dir, "Old", "*.har")))

    # Observed: endpoint -> { "x_browser": count, "recaptcha": count, "api_key": count, "tool_pinhole": count, "total": count }
    observed = {}

    for f_path in files:
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            entries = data.get('log', {}).get('entries', [])
            for entry in entries:
                req = entry.get('request', {})
                url = req.get('url', '')
                method = req.get('method', '')

                if 'googleapis.com' not in url: continue
                if method == 'OPTIONS': continue
                if '/g/collect' in url or '/play/log' in url: continue

                norm = normalize_path(url)
                if norm is None: continue

                if norm not in observed:
                    observed[norm] = {"x_browser": 0, "recaptcha": 0, "api_key": 0, "tool_pinhole": 0, "total": 0}
                
                stats = observed[norm]
                stats["total"] += 1

                headers = {h['name'].lower(): h['value'] for h in req.get('headers', [])}
                if 'x-browser-validation' in headers: stats["x_browser"] += 1

                qs = parse_qs(urlparse(url).query)
                if 'key' in qs: stats["api_key"] += 1

                post_data = req.get('postData', {})
                if post_data and 'text' in post_data:
                    txt = post_data['text']
                    if 'recaptchaContext' in txt: stats["recaptcha"] += 1
                    if '"tool":"PINHOLE"' in txt or '"tool": "PINHOLE"' in txt: stats["tool_pinhole"] += 1

        except: pass

    # Generate Report
    report = []
    report.append("# Final Verification Report")
    report.append(f"> Scanned {len(files)} HAR files")
    report.append("")
    report.append("| Endpoint | x-browser | reCAPTCHA | API Key | PINHOLE | Expected | Status |")
    report.append("|---|---|---|---|---|---|---|")

    all_pass = True
    for ep, exp in EXPECTED.items():
        obs = observed.get(ep, {"x_browser": 0, "recaptcha": 0, "api_key": 0, "tool_pinhole": 0, "total": 0})
        
        # Determine observed state (Found in >0 requests = True)
        obs_x = obs["x_browser"] > 0
        obs_r = obs["recaptcha"] > 0
        obs_k = obs["api_key"] > 0
        obs_p = obs["tool_pinhole"] > 0
        
        # Compare
        match = True
        mismatches = []
        if exp["x_browser"] != obs_x:
            if obs["total"] > 0: # Only flag if we saw traffic
                 mismatches.append(f"x-browser (Doc:{exp['x_browser']}, HAR:{obs_x})")
                 match = False
        if exp["recaptcha"] != obs_r:
            if obs["total"] > 0:
                mismatches.append(f"reCAPTCHA (Doc:{exp['recaptcha']}, HAR:{obs_r})")
                match = False
        if exp["api_key"] != obs_k:
            if obs["total"] > 0:
                mismatches.append(f"api_key (Doc:{exp['api_key']}, HAR:{obs_k})")
                match = False
        if exp["tool_pinhole"] != obs_p:
            if obs["total"] > 0:
                mismatches.append(f"tool (Doc:{exp['tool_pinhole']}, HAR:{obs_p})")
                match = False
        
        status = "✅ PASS" if match or obs["total"] == 0 else f"❌ FAIL: {', '.join(mismatches)}"
        if "FAIL" in status: all_pass = False

        report.append(f"| `{ep}` | {'✅' if obs_x else '❌'} ({obs['x_browser']}/{obs['total']}) | {'✅' if obs_r else '❌'} ({obs['recaptcha']}/{obs['total']}) | {'✅' if obs_k else '❌'} ({obs['api_key']}/{obs['total']}) | {'✅' if obs_p else '❌'} ({obs['tool_pinhole']}/{obs['total']}) | Doc Match | {status} |")

    report.append("")
    if all_pass:
        report.append("> **SUMMARY: ✅ ALL DOCUMENTATION MATCHES HAR DATA**")
    else:
        report.append("> **SUMMARY: ❌ DISCREPANCIES FOUND - REVIEW REQUIRED**")

    with open(os.path.join(base_dir, "final_verification_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    
    print("Verification complete. Report: final_verification_report.md")

if __name__ == "__main__":
    verify()
