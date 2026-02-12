import json, os

har_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
out = []

for fname in sorted(os.listdir(har_dir)):
    if not fname.endswith(".har"):
        continue
    fpath = os.path.join(har_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    for entry in data.get("log", {}).get("entries", []):
        req = entry.get("request", {})
        url = req.get("url", "")
        if "batchAsyncGenerateVideoText" not in url:
            continue
        
        body = req.get("postData", {}).get("text", "")
        if not body:
            continue
        
        payload = json.loads(body)
        cc = payload.get("clientContext", {})
        reqs = payload.get("requests", [])
        
        # Collect auth header
        auth = "NOT FOUND"
        for h in req.get("headers", []):
            if h["name"].lower() == "authorization":
                auth = h["value"][:60]
        
        # Collect first request item
        r0 = reqs[0] if reqs else {}
        
        out.append({
            "file": fname,
            "auth_header": auth,
            "cc_keys": sorted(cc.keys()),
            "cc_tool": cc.get("tool"),
            "cc_paygate": cc.get("userPaygateTier"),
            "cc_has_recaptcha": "recaptchaContext" in cc,
            "req_count": len(reqs),
            "r0_keys": sorted(r0.keys()),
            "r0_aspectRatio": r0.get("aspectRatio"),
            "r0_videoModelKey": r0.get("videoModelKey"),
            "r0_seed": r0.get("seed"),
        })
        break

# Write structured output
with open("t2v_structured.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"Found {len(out)} T2V calls")
