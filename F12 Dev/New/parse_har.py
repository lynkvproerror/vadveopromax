"""Parse HAR files for T2I image download/upscale API structure."""
import json
import os

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
FILES = [
    "Download anh 1k.har",
    "Download anh 2k.har",
    "Download anh 4k bat dau.har",
    "Download anh 4k hoan thanh.har",
]

KEYWORDS = [
    "labs.google", "GenerateService", "ImageFx", "generate", 
    "upscale", "enhance", "aisandbox", "alkali", "fife", 
    "lh3.google", "ggpht", "trcreate"
]

for fname in FILES:
    path = os.path.join(HAR_DIR, fname)
    print(f"\n{'='*80}")
    print(f"FILE: {fname}")
    print(f"{'='*80}")
    
    with open(path, "r", encoding="utf-8") as f:
        har = json.load(f)
    
    entries = har["log"]["entries"]
    print(f"Total entries: {len(entries)}")
    
    for i, e in enumerate(entries):
        req = e["request"]
        resp = e["response"]
        url = req["url"]
        
        if not any(k.lower() in url.lower() for k in KEYWORDS):
            continue
        
        # Skip static assets
        if any(ext in url for ext in [".js", ".css", ".woff", ".svg", ".ico", ".json"]):
            continue
        
        print(f"\n--- Entry [{i}] ---")
        print(f"  Method:  {req['method']}")
        print(f"  URL:     {url[:200]}")
        print(f"  Status:  {resp['status']}")
        
        ct = resp.get("content", {}).get("mimeType", "")
        body_size = resp.get("content", {}).get("size", 0)
        print(f"  RespType: {ct}")
        print(f"  RespSize: {body_size}")
        
        if req.get("postData"):
            pd_text = req["postData"].get("text", "")
            if pd_text:
                try:
                    pd_json = json.loads(pd_text)
                    if isinstance(pd_json, dict):
                        print(f"  PostData (JSON keys): {list(pd_json.keys())}")
                    pretty = json.dumps(pd_json, indent=2, ensure_ascii=False)
                    if len(pretty) > 2000:
                        print(f"  PostData (first 2000 chars):")
                        print(f"    {pretty[:2000]}")
                    else:
                        print(f"  PostData:")
                        for line in pretty.split("\n"):
                            print(f"    {line}")
                except json.JSONDecodeError:
                    print(f"  PostData (raw, first 500 chars): {pd_text[:500]}")
        
        resp_text = resp.get("content", {}).get("text", "")
        if resp_text and ct and "json" in ct.lower():
            try:
                resp_json = json.loads(resp_text)
                if isinstance(resp_json, dict):
                    print(f"  RespData (JSON keys): {list(resp_json.keys())}")
                    pretty_resp = json.dumps(resp_json, indent=2, ensure_ascii=False)
                    if len(pretty_resp) > 3000:
                        print(f"  RespData (first 3000 chars):")
                        print(f"    {pretty_resp[:3000]}")
                    else:
                        print(f"  RespData:")
                        for line in pretty_resp.split("\n"):
                            print(f"    {line}")
            except Exception:
                pass
