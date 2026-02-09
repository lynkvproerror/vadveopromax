import json, os

BASE = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API"

files = [
    ("F12 Dev/New/Text to image.har", "TEXT TO IMAGE"),
    ("F12 Dev/New/image to image 2.har", "IMAGE TO IMAGE 2"),
]

for fname, label in files:
    path = os.path.join(BASE, fname)
    with open(path, "r", encoding="utf-8") as f:
        har = json.load(f)
    entries = har["log"]["entries"]
    print(f"\n{'='*80}")
    print(f"  {label}: {fname}")
    print(f"  Total entries: {len(entries)}")
    print(f"{'='*80}")
    
    # List ALL API calls (not just image gen)
    print("\n  ALL API CALLS:")
    for i, entry in enumerate(entries):
        url = entry["request"]["url"]
        method = entry["request"]["method"]
        status = entry["response"]["status"]
        
        # Classify
        if "labs.google/fx/api/trpc" in url:
            proc = url.split("trpc/")[-1].split("?")[0]
            print(f"  [{i:2d}] {method} TRPC: {proc} -> {status}")
        elif "aisandbox-pa" in url:
            path = url.split("googleapis.com")[1].split("?")[0]
            print(f"  [{i:2d}] {method} REST: {path[:80]} -> {status}")
        elif "recaptcha" in url:
            ep = "reload" if "reload" in url else "clr" if "clr" in url else "other"
            print(f"  [{i:2d}] {method} RECAP: {ep} -> {status}")
        elif "auth/session" in url:
            print(f"  [{i:2d}] {method} AUTH: session -> {status}")
        elif "storage.googleapis.com" in url or "ai-sandbox" in url:
            print(f"  [{i:2d}] {method} STORAGE: download -> {status}")
        else:
            domain = url.split("/")[2] if "/" in url else url
            print(f"  [{i:2d}] {method} OTHER: {domain[:50]} -> {status}")

    # Deep check: are both files truly identical in their batchGenerateImages calls?
    print("\n  UNIQUE IDENTIFIERS:")
    for i, entry in enumerate(entries):
        if "batchGenerateImages" in entry["request"]["url"]:
            post = entry["request"].get("postData", {}).get("text", "")
            if post:
                p = json.loads(post)
                reqs = p.get("requests", [])
                for r in reqs:
                    print(f"  seed={r.get('seed')}, model={r.get('imageModelName')}, has_imageInputs={'imageInputs' in r}")
                    if "imageInputs" in r:
                        for ii in r["imageInputs"]:
                            print(f"    imageInput.name={ii.get('name','')[:40]}")
                            print(f"    imageInput.type={ii.get('imageInputType')}")
                    else:
                        print(f"    ** PURE T2I - NO IMAGE INPUTS **")
