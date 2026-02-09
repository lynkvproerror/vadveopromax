import json
import os
import urllib.parse

har_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
output_path = "deep_component_analysis.txt"

har_files = sorted([f for f in os.listdir(har_dir) if f.endswith('.har')])

# We need FULL data for these critical components
CRITICAL_TARGETS = {
    # Auth
    "auth/session": {"max_resp": 2000, "max_payload": 500},
    # Credits & Availability
    "/v1/credits": {"max_resp": 2000, "max_payload": 500},
    "checkAppAvailability": {"max_resp": 2000, "max_payload": 500},
    "getVideoCreditStatus": {"max_resp": 2000, "max_payload": 500},
    "fetchUserRecommendations": {"max_resp": 3000, "max_payload": 1000},
    # Model Config (CRITICAL - need full model list)
    "videoFx.getVideoModelConfig": {"max_resp": 15000, "max_payload": 500},
    # Video Generation variants - need full payload structure
    "batchAsyncGenerateVideoReferenceImages": {"max_resp": 3000, "max_payload": 3000},
    "batchAsyncGenerateVideoStartImage": {"max_resp": 3000, "max_payload": 3000},
    "batchAsyncGenerateVideoStartAndEndImage": {"max_resp": 3000, "max_payload": 3000},
    "batchAsyncGenerateVideoUpsampleVideo": {"max_resp": 3000, "max_payload": 3000},
    "batchCheckAsyncVideoGenerationStatus": {"max_resp": 5000, "max_payload": 3000},
    # Image
    "flowMedia:batchGenerateImages": {"max_resp": 3000, "max_payload": 3000},
    "/v1/flow/upsampleImage": {"max_resp": 500, "max_payload": 2000},
    "uploadUserImage": {"max_resp": 2000, "max_payload": 200},  # skip image bytes
    # GIF
    "generatePinholeGif": {"max_resp": 500, "max_payload": 2000},
    # Recaptcha
    "recaptcha/enterprise/reload": {"max_resp": 2000, "max_payload": 200},
    "recaptcha/enterprise/clr": {"max_resp": 2000, "max_payload": 200},
    # User settings (need full response)
    "videoFx.getUserSettings": {"max_resp": 3000, "max_payload": 500},
    "videoFx.getFlowAppConfig": {"max_resp": 5000, "max_payload": 500},
    # Download signed URL pattern
    "storage.googleapis.com": {"max_resp": 200, "max_payload": 200},
}

# Also collect ALL unique headers across all REST endpoints
all_rest_headers = {}
all_trpc_headers = {}

# Collect all status transitions for polling
polling_statuses = []

# Collect all media download URLs
download_urls = []

seen = set()

with open(output_path, "w", encoding="utf-8") as out:
    out.write("=" * 100 + "\n")
    out.write("DEEP COMPONENT ANALYSIS — FULL EXTRACTION\n")
    out.write("=" * 100 + "\n\n")
    
    for har_file in har_files:
        har_path = os.path.join(har_dir, har_file)
        try:
            with open(har_path, 'r', encoding='utf-8') as f:
                har_data = json.load(f)
            
            for entry in har_data['log']['entries']:
                request = entry['request']
                response = entry['response']
                url = request['url']
                
                # Collect signed URL patterns
                if 'storage.googleapis.com' in url and 'download' in url:
                    parsed = urllib.parse.urlparse(url)
                    params = urllib.parse.parse_qs(parsed.query)
                    download_urls.append({
                        'source': har_file,
                        'path': parsed.path,
                        'params': {k: v[0][:30] + '...' if len(v[0]) > 30 else v[0] for k, v in params.items()},
                        'status': response['status'],
                        'content_type': response.get('content', {}).get('mimeType', ''),
                    })
                
                # Collect REST headers
                if 'aisandbox-pa' in url:
                    for h in request['headers']:
                        name = h['name'].lower()
                        if name.startswith('x-') or name in ['content-type', 'authorization', 'cookie']:
                            if name not in all_rest_headers:
                                all_rest_headers[name] = h['value']
                
                # Collect TRPC headers
                if 'labs.google/fx/api/trpc' in url or 'labs.google/fx/api/auth' in url:
                    for h in request['headers']:
                        name = h['name'].lower()
                        if name.startswith('x-') or name in ['content-type', 'cookie', ':authority', ':path', ':method', ':scheme']:
                            if name not in all_trpc_headers:
                                all_trpc_headers[name] = h['value'][:100]
                
                # Collect polling status transitions
                if 'batchCheckAsyncVideoGenerationStatus' in url:
                    resp_text = response.get('content', {}).get('text', '')
                    if resp_text:
                        try:
                            resp_json = json.loads(resp_text)
                            statuses = [op.get('status', '') for op in resp_json.get('operations', [])]
                            polling_statuses.append({
                                'source': har_file,
                                'statuses': statuses,
                                'has_video': 'video' in resp_text.lower() and 'videoUrl' in resp_text or 'encodedVideo' in resp_text,
                                'resp_keys': list(resp_json.keys()) if isinstance(resp_json, dict) else [],
                            })
                            # If complete, get more detail
                            if any('COMPLETE' in s for s in statuses):
                                # Get a complete operation's full structure
                                for op in resp_json.get('operations', []):
                                    if 'COMPLETE' in op.get('status', ''):
                                        out.write(f"\n{'='*80}\n")
                                        out.write("POLLING COMPLETE OPERATION (FULL STRUCTURE):\n")
                                        out.write(f"Source: {har_file}\n")
                                        out.write(json.dumps(op, indent=2)[:5000] + "\n")
                                        break
                        except:
                            pass
                
                # Extract critical targets
                for target, config in CRITICAL_TARGETS.items():
                    if target in url and target not in seen:
                        seen.add(target)
                        out.write(f"\n{'='*100}\n")
                        out.write(f"COMPONENT: {target}\n")
                        out.write(f"SOURCE: {har_file}\n")
                        out.write(f"URL: {url[:300]}\n")
                        out.write(f"METHOD: {request['method']}\n")
                        
                        # Full headers
                        out.write("ALL HEADERS:\n")
                        for h in request['headers']:
                            val = h['value']
                            if h['name'].lower() == 'cookie':
                                # Just show cookie names
                                cookies = [c.split('=')[0].strip() for c in val.split(';')]
                                out.write(f"  Cookie names: {cookies}\n")
                            elif len(val) > 150:
                                out.write(f"  {h['name']}: {val[:150]}...\n")
                            else:
                                out.write(f"  {h['name']}: {val}\n")
                        
                        # Query params
                        parsed = urllib.parse.urlparse(url)
                        if parsed.query:
                            params = urllib.parse.parse_qs(parsed.query)
                            out.write("QUERY PARAMS:\n")
                            for k, v in params.items():
                                val = v[0]
                                out.write(f"  {k}: {val[:200]}\n")
                        
                        # Payload
                        if 'postData' in request:
                            text = request['postData'].get('text', '')
                            mime = request['postData'].get('mimeType', '')
                            out.write(f"PAYLOAD MIME: {mime}\n")
                            
                            if 'rawImageBytes' in text or 'encodedImage' in text or 'encodedGif' in text:
                                # For image data, show structure only
                                try:
                                    pdata = json.loads(text)
                                    # Remove binary data
                                    def strip_binary(obj):
                                        if isinstance(obj, dict):
                                            return {k: '[BINARY_DATA]' if k in ('rawImageBytes', 'encodedImage', 'encodedGif') else strip_binary(v) for k, v in obj.items()}
                                        elif isinstance(obj, list):
                                            return [strip_binary(i) for i in obj]
                                        return obj
                                    cleaned = strip_binary(pdata)
                                    out.write(f"PAYLOAD STRUCTURE:\n{json.dumps(cleaned, indent=2)[:config['max_payload']]}\n")
                                except:
                                    out.write(f"PAYLOAD: {text[:config['max_payload']]}\n")
                            else:
                                # Try to pretty-print JSON
                                try:
                                    pdata = json.loads(text)
                                    pretty = json.dumps(pdata, indent=2)
                                    out.write(f"PAYLOAD:\n{pretty[:config['max_payload']]}\n")
                                except:
                                    out.write(f"PAYLOAD: {text[:config['max_payload']]}\n")
                        
                        # Response
                        out.write(f"RESPONSE STATUS: {response['status']}\n")
                        resp_text = response.get('content', {}).get('text', '')
                        resp_mime = response.get('content', {}).get('mimeType', '')
                        out.write(f"RESPONSE MIME: {resp_mime}\n")
                        if resp_text:
                            if 'encodedImage' in resp_text or 'encodedGif' in resp_text or 'encodedVideo' in resp_text:
                                try:
                                    rdata = json.loads(resp_text)
                                    def strip_binary_resp(obj):
                                        if isinstance(obj, dict):
                                            return {k: f'[BINARY_{k.upper()}_DATA, len={len(v)}]' if k in ('encodedImage', 'encodedGif', 'encodedVideo') and isinstance(v, str) and len(v) > 100 else strip_binary_resp(v) for k, v in obj.items()}
                                        elif isinstance(obj, list):
                                            return [strip_binary_resp(i) for i in obj]
                                        return obj
                                    cleaned = strip_binary_resp(rdata)
                                    out.write(f"RESPONSE:\n{json.dumps(cleaned, indent=2)[:config['max_resp']]}\n")
                                except:
                                    out.write(f"RESPONSE: {resp_text[:config['max_resp']]}\n")
                            else:
                                try:
                                    rdata = json.loads(resp_text)
                                    pretty = json.dumps(rdata, indent=2)
                                    out.write(f"RESPONSE:\n{pretty[:config['max_resp']]}\n")
                                except:
                                    out.write(f"RESPONSE: {resp_text[:config['max_resp']]}\n")
                        
                        out.write("\n")
                        break
        except Exception as e:
            out.write(f"ERROR processing {har_file}: {e}\n")
    
    # Write collected analysis
    out.write(f"\n{'='*100}\n")
    out.write("ANALYSIS: ALL REST HEADERS (aisandbox-pa)\n")
    out.write(f"{'='*100}\n")
    for name, val in sorted(all_rest_headers.items()):
        out.write(f"  {name}: {val[:150]}\n")
    
    out.write(f"\n{'='*100}\n")
    out.write("ANALYSIS: ALL TRPC HEADERS (labs.google)\n")
    out.write(f"{'='*100}\n")
    for name, val in sorted(all_trpc_headers.items()):
        out.write(f"  {name}: {val[:150]}\n")
    
    out.write(f"\n{'='*100}\n")
    out.write(f"ANALYSIS: POLLING STATUS TRANSITIONS ({len(polling_statuses)} polls)\n")
    out.write(f"{'='*100}\n")
    for i, p in enumerate(polling_statuses):
        unique = set(p['statuses'])
        out.write(f"  Poll {i+1} ({p['source']}): {unique} keys={p['resp_keys']}\n")
    
    out.write(f"\n{'='*100}\n")
    out.write(f"ANALYSIS: DOWNLOAD URLS ({len(download_urls)} downloads)\n")
    out.write(f"{'='*100}\n")
    for i, d in enumerate(download_urls[:5]):  # First 5
        out.write(f"  Download {i+1}:\n")
        out.write(f"    Source: {d['source']}\n")
        out.write(f"    Path: {d['path'][:100]}\n")
        out.write(f"    Params: {d['params']}\n")
        out.write(f"    Status: {d['status']}\n")
        out.write(f"    Content-Type: {d['content_type']}\n")

    # Missing targets
    missing = set(CRITICAL_TARGETS.keys()) - seen
    if missing:
        out.write(f"\n{'='*100}\n")
        out.write("TARGETS NOT FOUND:\n")
        for m in sorted(missing):
            out.write(f"  - {m}\n")

print(f"Deep analysis complete. Extracted {len(seen)} components to {output_path}")
