import json
import os
import urllib.parse

har_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
output_path = "full_endpoint_samples.txt"

har_files = sorted([f for f in os.listdir(har_dir) if f.endswith('.har')])

# Targets: all REST and TRPC endpoints we need real samples for
REST_TARGETS = [
    "/v1/credits",
    "/v1/flow/upsampleImage",
    "batchAsyncGenerateVideoStartImage",
    "batchAsyncGenerateVideoStartAndEndImage",
    "batchAsyncGenerateVideoUpsampleVideo",
    "generatePinholeGif",
    "getVideoCreditStatus",
    "checkAppAvailability",
    "fetchUserRecommendations",
    "flowMedia:batchGenerateImages",
    "uploadUserImage",
    "batchAsyncGenerateVideoReferenceImages",
    "batchCheckAsyncVideoGenerationStatus",
]

TRPC_TARGETS = [
    "auth/session",
    "general.fetchFeatureAvailability",
    "general.fetchToolAvailability",
    "general.fetchUserAcknowledgement",
    "general.fetchUserLocale",
    "general.fetchUserPreferences",
    "media.fetchFlowUserIngredients",
    "media.fetchUserHistoryDirectly",
    "project.getProject",
    "project.searchProjectScenes",
    "project.searchProjectWorkflows",
    "project.createProject",
    "videoFx.getFlowAppConfig",
    "videoFx.getUserSettings",
    "videoFx.getVideoModelConfig",
    "videoFx.listPreambles",
    "videoFx.setLastSelectedVideoModelKey",
    "videoFx.setLastSelectedVideoAspectRatio",
    "general.reportClientSideError",
    "general.submitBatchLog",
    "general.submitUserAcknowledgement",
]

RECAPTCHA_TARGETS = [
    "recaptcha/enterprise/reload",
    "recaptcha/enterprise/clr",
]

ALL_TARGETS = REST_TARGETS + TRPC_TARGETS + RECAPTCHA_TARGETS

# Track which targets we've seen to get only first occurrence
seen = set()

with open(output_path, "w", encoding="utf-8") as out:
    out.write("=== FULL ENDPOINT SAMPLE EXTRACTION ===\n\n")
    
    for har_file in har_files:
        har_path = os.path.join(har_dir, har_file)
        try:
            with open(har_path, 'r', encoding='utf-8') as f:
                har_data = json.load(f)
            
            for entry in har_data['log']['entries']:
                request = entry['request']
                url = request['url']
                
                for target in ALL_TARGETS:
                    if target in url and target not in seen:
                        seen.add(target)
                        out.write(f"{'='*80}\n")
                        out.write(f"TARGET: {target}\n")
                        out.write(f"SOURCE: {har_file}\n")
                        out.write(f"URL: {url[:200]}\n")
                        out.write(f"METHOD: {request['method']}\n")
                        
                        # Query params
                        parsed = urllib.parse.urlparse(url)
                        if parsed.query:
                            params = urllib.parse.parse_qs(parsed.query)
                            out.write("QUERY PARAMS:\n")
                            for k, v in params.items():
                                out.write(f"  {k}: {v[0][:100]}\n")
                        
                        # Custom headers only (x-*, content-type, cookie presence)
                        out.write("KEY HEADERS:\n")
                        has_cookie = False
                        for h in request['headers']:
                            name = h['name'].lower()
                            if name.startswith('x-') or name in ['content-type', 'authorization']:
                                out.write(f"  {h['name']}: {h['value'][:100]}\n")
                            if name == 'cookie':
                                has_cookie = True
                        out.write(f"  Cookie: {'YES' if has_cookie else 'NO'}\n")
                        
                        # Payload
                        if 'postData' in request:
                            text = request['postData'].get('text', '')
                            mime = request['postData'].get('mimeType', '')
                            out.write(f"PAYLOAD MIME: {mime}\n")
                            # For image uploads, truncate heavily
                            if 'rawImageBytes' in text:
                                out.write(f"PAYLOAD: [Image data - {len(text)} chars total]\n")
                                # Show just the structure
                                try:
                                    pdata = json.loads(text)
                                    keys = list(pdata.keys())
                                    out.write(f"PAYLOAD KEYS: {keys}\n")
                                    if 'imageInput' in pdata:
                                        out.write(f"  imageInput keys: {list(pdata['imageInput'].keys())}\n")
                                except:
                                    pass
                            else:
                                out.write(f"PAYLOAD: {text[:500]}\n")
                        
                        # Response
                        response = entry['response']
                        out.write(f"RESPONSE STATUS: {response['status']}\n")
                        if 'content' in response and 'text' in response['content']:
                            resp_text = response['content']['text']
                            out.write(f"RESPONSE MIME: {response['content'].get('mimeType', '')}\n")
                            out.write(f"RESPONSE: {resp_text[:500]}\n")
                        
                        out.write("\n")
                        break
        except Exception as e:
            out.write(f"ERROR processing {har_file}: {e}\n")
    
    # List any targets NOT found
    missing = set(ALL_TARGETS) - seen
    if missing:
        out.write(f"\n{'='*80}\n")
        out.write("TARGETS NOT FOUND IN ANY HAR:\n")
        for m in sorted(missing):
            out.write(f"  - {m}\n")

print(f"Extracted {len(seen)} endpoint samples to {output_path}")
