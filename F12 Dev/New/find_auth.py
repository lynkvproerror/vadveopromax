"""
Verify Content-Type in request vs response for ALL aisandbox-pa entries
"""
import json
from urllib.parse import urlparse

files = [
    r"D:\NEW VEO PRO MAX\veo-pro-max\F12 Dev\New\Test.har",
    r"D:\NEW VEO PRO MAX\veo-pro-max\F12 Dev\New\image flow.har",
]

for fn in files:
    with open(fn, "r", encoding="utf-8") as f:
        har = json.load(f)
    
    name = fn.split("\\")[-1]
    print(f"\n{'='*80}")
    print(f"FILE: {name}")
    print(f"{'='*80}")
    
    for i, entry in enumerate(har["log"]["entries"]):
        req = entry["request"]
        resp = entry["response"]
        url = req["url"]
        domain = urlparse(url).netloc
        path = urlparse(url).path
        method = req["method"]
        status = resp["status"]
        
        if domain != "aisandbox-pa.googleapis.com":
            continue
        if method == "OPTIONS":
            continue
            
        # Get request content-type
        req_ct = "NOT SET"
        for h in req.get("headers", []):
            if h["name"].lower() == "content-type":
                req_ct = h["value"]
        
        # Get response content-type
        resp_ct = "NOT SET"
        for h in resp.get("headers", []):
            if h["name"].lower() == "content-type":
                resp_ct = h["value"]
        
        # Get request postData mimeType
        post_mime = req.get("postData", {}).get("mimeType", "N/A")
        
        print(f"[{i:3d}] {method:4s} {path[:65]:65s} -> {status}")
        print(f"  REQ  content-type header: {req_ct}")
        if method == "POST":
            print(f"  REQ  postData mimeType:   {post_mime}")
        print(f"  RESP content-type header: {resp_ct}")
        print()
