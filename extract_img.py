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

    gen_count = 0
    upload_count = 0
    upsample_count = 0

    for i, entry in enumerate(entries):
        url = entry["request"]["url"]
        method = entry["request"]["method"]

        if "batchGenerateImages" in url:
            gen_count += 1
            print(f"\n--- batchGenerateImages #{gen_count} (Entry {i}) ---")
            
            # Extract URL path
            if "googleapis.com" in url:
                short = url.split("googleapis.com")[1]
            else:
                short = url
            print(f"  URL: {short[:150]}")

            post_data = entry["request"].get("postData", {}).get("text", "")
            if post_data:
                payload = json.loads(post_data)
                reqs = payload.get("requests", [])
                for r in reqs:
                    has_ii = "imageInputs" in r
                    mode = "I2I" if has_ii else "T2I_PURE"
                    print(f"  MODE: {mode}")
                    print(f"  prompt: {r.get('prompt', 'N/A')[:120]}")
                    print(f"  imageModelName: {r.get('imageModelName', 'N/A')}")
                    print(f"  imageAspectRatio: {r.get('imageAspectRatio', 'N/A')}")
                    print(f"  seed: {r.get('seed', 'N/A')}")
                    if has_ii:
                        for ii in r["imageInputs"]:
                            print(f"  imageInput: name={ii.get('name','')[:30]}... type={ii.get('imageInputType')}")
                    else:
                        print(f"  ** NO imageInputs -> PURE T2I **")

                cc = payload.get("clientContext", {})
                print(f"  cc.tool: {cc.get('tool', 'MISSING')}")
                print(f"  cc.projectId: {str(cc.get('projectId', 'MISSING'))[:40]}")
                print(f"  cc.userPaygateTier: {cc.get('userPaygateTier', 'MISSING')}")
                print(f"  cc.recaptcha: {'YES' if 'recaptchaContext' in cc else 'NO'}")
                print(f"  cc.sessionId: {cc.get('sessionId', 'MISSING')[:30]}")

            # Response
            resp_text = entry["response"].get("content", {}).get("text", "")
            status = entry["response"]["status"]
            print(f"  HTTP Status: {status}")
            if resp_text:
                try:
                    resp = json.loads(resp_text)
                    media = resp.get("media", [])
                    print(f"  Response: {len(media)} images returned")
                    for m in media[:2]:
                        gi = m.get("image", {}).get("generatedImage", {})
                        print(f"    resp.prompt: {gi.get('prompt', '')[:80]}")
                        print(f"    resp.model: {gi.get('modelNameType')}")
                        print(f"    resp.seed: {gi.get('seed')}")
                        rd = gi.get("requestData", {})
                        pi = rd.get("promptInputs", [])
                        if pi:
                            print(f"    original_prompt: {pi[0].get('textInput', '')[:80]}")
                        igd = rd.get("imageGenerationRequestData", {})
                        iii = igd.get("imageGenerationImageInputs", [])
                        print(f"    resp.imageInputs: {len(iii)} items")
                        if iii:
                            for item in iii:
                                print(f"      -> type={item.get('imageInputType')}, id={str(item.get('mediaGenerationId',''))[:30]}")
                except Exception as e:
                    print(f"  Response parse error: {e}")

        elif "uploadUserImage" in url:
            upload_count += 1
            print(f"\n--- uploadUserImage #{upload_count} (Entry {i}) ---")
            post_data = entry["request"].get("postData", {}).get("text", "")
            if post_data:
                payload = json.loads(post_data)
                cc = payload.get("clientContext", {})
                print(f"  cc.tool: {cc.get('tool', 'MISSING')}")
                ii = payload.get("imageInput", {})
                print(f"  mimeType: {ii.get('mimeType')}")
                print(f"  isUserUploaded: {ii.get('isUserUploaded')}")
                print(f"  aspectRatio: {ii.get('aspectRatio')}")
            resp_text = entry["response"].get("content", {}).get("text", "")
            if resp_text:
                resp = json.loads(resp_text)
                mgid = resp.get("mediaGenerationId", {})
                print(f"  mediaGenerationId: {str(mgid)[:80]}")
                print(f"  width: {resp.get('width')}, height: {resp.get('height')}")

        elif "upsampleImage" in url:
            upsample_count += 1
            print(f"\n--- upsampleImage #{upsample_count} (Entry {i}) ---")
            post_data = entry["request"].get("postData", {}).get("text", "")
            if post_data:
                payload = json.loads(post_data)
                print(f"  targetResolution: {payload.get('targetResolution')}")

    print(f"\n  SUMMARY: {gen_count} generate, {upload_count} upload, {upsample_count} upsample")
    
    # Also dump full payload for first batchGenerateImages call
    print(f"\n{'='*80}")
    print(f"  FULL PAYLOAD DUMP - First batchGenerateImages call")
    print(f"{'='*80}")
    for i, entry in enumerate(entries):
        if "batchGenerateImages" in entry["request"]["url"]:
            post_data = entry["request"].get("postData", {}).get("text", "")
            if post_data:
                payload = json.loads(post_data)
                print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])
            break
