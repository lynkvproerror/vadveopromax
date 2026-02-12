import json, sys, os

har_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"

files_to_check = [
    "916 frame to video submit 4 video prompt - Upscale all done.har",
    "Download upscale 1080p 4 vid done.har",
]

for fname in files_to_check:
    fpath = os.path.join(har_dir, fname)
    if not os.path.exists(fpath):
        print(f"=== FILE NOT FOUND: {fname} ===\n")
        continue
    
    print(f"\n{'='*80}")
    print(f"FILE: {fname}")
    print(f"{'='*80}")
    
    with open(fpath, 'r', encoding='utf-8') as f:
        har = json.load(f)
    
    entries = har['log']['entries']
    print(f"Total entries: {len(entries)}\n")
    
    keywords = ['batchAsync', 'v1/video', 'v1/image', 'generate', 'operations', 'upscale']
    skip = ['.js', '.css', '.png', '.jpg', '.woff', 'gstatic', 'analytics', 'collect', 'trpc', 'recaptcha.net']
    
    for i, e in enumerate(entries):
        url = e['request']['url']
        method = e['request']['method']
        
        if any(k in url for k in skip):
            continue
        if not any(k in url for k in keywords):
            continue
        
        status = e['response']['status']
        print(f"--- Entry {i} [{method}] Status={status} ---")
        print(f"URL: {url[:250]}")
        
        # Show request body if POST
        if method == 'POST':
            post_data = e['request'].get('postData', {}).get('text', '')
            if post_data:
                try:
                    body = json.loads(post_data)
                    print(f"REQUEST BODY keys: {list(body.keys())}")
                    if 'requests' in body:
                        reqs = body['requests']
                        print(f"  requests count: {len(reqs)}")
                        for j, req in enumerate(reqs):
                            print(f"  req[{j}]:")
                            for k in sorted(req.keys()):
                                val = req[k]
                                if isinstance(val, str) and len(val) > 100:
                                    val = val[:100] + "..."
                                elif isinstance(val, dict):
                                    val = json.dumps(val)[:100]
                                print(f"    {k}: {val}")
                    if 'operations' in body:
                        ops = body['operations']
                        print(f"  operations in request: {len(ops)}")
                        for j, op in enumerate(ops):
                            print(f"  op[{j}]: {json.dumps(op)[:200]}")
                except Exception as ex:
                    print(f"REQUEST BODY parse error: {ex}")
        
        # Show response body
        resp_text = e['response']['content'].get('text', '')
        if resp_text:
            try:
                resp = json.loads(resp_text)
                if 'operations' in resp:
                    ops = resp['operations']
                    print(f"RESPONSE: {len(ops)} operations")
                    for j, op in enumerate(ops):
                        print(f"  op[{j}]:")
                        print(f"    status: {op.get('status', 'N/A')}")
                        print(f"    sceneId: {op.get('sceneId', 'N/A')}")
                        operation = op.get('operation', {})
                        if isinstance(operation, dict):
                            op_name = operation.get('name', 'N/A')
                            print(f"    operation.name: {op_name[:100]}")
                            metadata = operation.get('metadata', {})
                            if isinstance(metadata, dict):
                                meta_keys = list(metadata.keys())
                                print(f"    metadata keys: {meta_keys}")
                                if 'video' in metadata:
                                    video = metadata['video']
                                    fife = video.get('fifeUrl', 'N/A')
                                    print(f"    video.fifeUrl: {fife[:150]}")
                                    vid_keys = list(video.keys()) if isinstance(video, dict) else 'N/A'
                                    print(f"    video keys: {vid_keys}")
                                meta_name = metadata.get('name', '')
                                if meta_name:
                                    print(f"    metadata.name (mediaId): {meta_name[:80]}")
                else:
                    rkeys = list(resp.keys())
                    print(f"RESPONSE keys: {rkeys}")
                    resp_str = json.dumps(resp)[:500]
                    print(f"RESPONSE: {resp_str}")
            except:
                print(f"RESPONSE (raw): {resp_text[:300]}")
        
        print()
