"""
Full verification:
1. Count all HAR files
2. Extract chronological order of API calls within each session
3. Build a typical execution sequence
4. Cross-reference every endpoint against doc §1.4.D
"""
import json, os, re, sys
from collections import defaultdict, OrderedDict
from datetime import datetime

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_order_crossref_output.txt")

def classify_endpoint(url, method):
    if "/fx/api/auth/" in url:
        path = re.search(r'/fx/api/auth/([^?]+)', url)
        return "AUTH", f"GET /fx/api/auth/{path.group(1)}" if path else "AUTH unknown"
    
    trpc_match = re.search(r'/fx/api/trpc/([^?,]+)', url)
    if trpc_match:
        return "TRPC", trpc_match.group(1)
    
    if "recaptcha/enterprise" in url:
        if "/reload" in url: return "RECAPTCHA", "recaptcha/enterprise/reload"
        if "/clr" in url: return "RECAPTCHA", "recaptcha/enterprise/clr"
        return "RECAPTCHA", "recaptcha/other"
    
    if "storage.googleapis.com" in url:
        return "STORAGE", "storage.googleapis.com download"
    
    if "aisandbox-pa.googleapis.com" in url:
        # Handle /v1:action format
        colon_match = re.search(r'/v1:(\w+)', url)
        if colon_match:
            return "REST", f"POST /v1:{colon_match.group(1)}"
        
        # Handle /v1/path:action format
        path_match = re.search(r'googleapis\.com(/v\d+/[^?]+)', url)
        if path_match:
            path = path_match.group(1)
            path = re.sub(r'/projects/[a-f0-9-]+/', '/projects/{id}/', path)
            path = re.sub(r'/media/[A-Za-z0-9_=-]+', '/media/{id}', path)
            return "REST", f"{method} {path}"
        
        return "REST", f"{method} aisandbox(unknown)"
    
    return None, None

def main():
    har_files = sorted([f for f in os.listdir(HAR_DIR) if f.endswith('.har')])
    
    print(f"Total HAR files found: {len(har_files)}")
    print("=" * 80)
    for i, f in enumerate(har_files):
        # Sanitize filename for output
        safe_name = f.encode('ascii', errors='replace').decode('ascii')
        print(f"  {i+1:>2}. {safe_name}")
    
    # ==================== SECTION 1: Chronological Order per File ====================
    print(f"\n\n{'='*100}")
    print("SECTION 1: CHRONOLOGICAL ORDER OF API CALLS (per HAR file)")
    print("=" * 100)
    print("Shows the ORDER in which endpoints are called within each session.\n")
    
    all_sequences = []  # Collect for aggregation
    
    for har_file in har_files:
        filepath = os.path.join(HAR_DIR, har_file)
        try:
            data = json.load(open(filepath, 'r', encoding='utf-8'))
        except Exception as e:
            continue
        
        # Extract all API entries with timestamps
        entries = []
        for entry in data.get("log", {}).get("entries", []):
            url = entry.get("request", {}).get("url", "")
            method = entry.get("request", {}).get("method", "")
            started = entry.get("startedDateTime", "")
            
            cat, ep = classify_endpoint(url, method)
            if cat:
                entries.append({
                    "time": started,
                    "cat": cat,
                    "ep": ep,
                    "method": method
                })
        
        if not entries:
            continue
        
        # Sort by time
        entries.sort(key=lambda x: x["time"])
        
        # Build ordered unique sequence (first occurrence of each endpoint)
        seen = set()
        order = []
        for e in entries:
            key = f"{e['cat']}|{e['ep']}"
            if key not in seen:
                seen.add(key)
                order.append(e)
        
        safe_name = har_file.encode('ascii', errors='replace').decode('ascii')
        print(f"\n--- {safe_name} ({len(entries)} total calls, {len(order)} unique) ---")
        for i, e in enumerate(order):
            time_short = e["time"][11:19] if len(e["time"]) > 19 else e["time"]
            print(f"  {i+1:>2}. [{time_short}] [{e['cat']:10s}] {e['ep']}")
        
        all_sequences.append(order)
    
    # ==================== SECTION 2: Aggregated First-Call Order ====================
    print(f"\n\n{'='*100}")
    print("SECTION 2: AGGREGATED TYPICAL EXECUTION ORDER")
    print("=" * 100)
    print("Shows the AVERAGE position of each endpoint across all sessions.\n")
    
    # For each endpoint, collect its position in each session
    ep_positions = defaultdict(list)
    ep_files_count = defaultdict(int)
    
    for seq in all_sequences:
        for i, e in enumerate(seq):
            key = f"{e['cat']}|{e['ep']}"
            ep_positions[key].append(i + 1)  # 1-based position
            ep_files_count[key] += 1
    
    # Calculate average position
    avg_positions = {}
    for key, positions in ep_positions.items():
        avg_positions[key] = {
            "avg": sum(positions) / len(positions),
            "min": min(positions),
            "max": max(positions),
            "count": len(positions),
            "cat": key.split("|")[0],
            "ep": key.split("|", 1)[1]
        }
    
    # Sort by average position
    sorted_eps = sorted(avg_positions.items(), key=lambda x: x[1]["avg"])
    
    print(f"{'#':>3}  {'Avg Pos':>7}  {'Min-Max':>7}  {'Files':>5}  {'Category':10s}  Endpoint")
    print("-" * 90)
    for rank, (key, info) in enumerate(sorted_eps, 1):
        print(f"{rank:>3}  {info['avg']:>7.1f}  {info['min']:>2}-{info['max']:<4d}  {info['count']:>5}  {info['cat']:10s}  {info['ep']}")
    
    # ==================== SECTION 3: Cross-Reference with §1.4.D ====================
    print(f"\n\n{'='*100}")
    print("SECTION 3: CROSS-REFERENCE — HAR endpoints vs §1.4.D Documentation")
    print("=" * 100)
    
    # All endpoints documented in §1.4.D
    documented = {
        # Nhom 1
        "AUTH|GET /fx/api/auth/session": "Nhom 1: Lay session",
        "TRPC|project.createProject": "Nhom 1: Tao project",
        "TRPC|project.getProject": "Nhom 1: Load project",
        "TRPC|project.searchProjectScenes": "Nhom 1: Load scenes",
        "TRPC|project.searchProjectWorkflows": "Nhom 1: Load workflows",
        "TRPC|videoFx.getUserSettings": "Nhom 1: Lay user settings",
        "TRPC|videoFx.getVideoModelConfig": "Nhom 1: Lay model config",
        "TRPC|videoFx.getFlowAppConfig": "Nhom 1: Lay app config",
        "TRPC|videoFx.listPreambles": "Nhom 1: Lay preambles",
        "TRPC|general.fetchUserPreferences": "Nhom 1: Lay preferences",
        "TRPC|general.fetchUserAcknowledgement": "Nhom 1: Lay acknowledgement",
        "TRPC|general.submitUserAcknowledgement": "Nhom 1: Xac nhan acknowledgement",
        "TRPC|general.fetchUserLocale": "Nhom 1: Lay locale",
        "TRPC|general.fetchFeatureAvailability": "Nhom 1: Lay feature flags",
        "TRPC|general.fetchToolAvailability": "Nhom 1: Lay tool flags",
        "TRPC|media.fetchFlowUserIngredients": "Nhom 1: Lay ingredients",
        "TRPC|media.fetchUserHistoryDirectly": "Nhom 1: Lay lich su",
        "REST|GET /v1/credits": "Nhom 1: Kiem tra credits",
        "REST|POST /v1:checkAppAvailability": "Nhom 1: Kiem tra availability",
        "REST|POST /v1:fetchUserRecommendations": "Nhom 1: Lay recommendations",
        "REST|POST /v1/whisk:getVideoCreditStatus": "Nhom 1: Lay credit status",
        "REST|GET /v1/media/{id}": "Nhom 1: Load media item",
        # Nhom 2
        "RECAPTCHA|recaptcha/enterprise/reload": "Nhom 2: Lay token moi",
        "RECAPTCHA|recaptcha/enterprise/clr": "Nhom 2: Log ket qua",
        # Nhom 3
        "REST|POST /v1:uploadUserImage": "Nhom 3: Upload anh",
        "REST|POST /v1/video:batchAsyncGenerateVideoStartImage": "Nhom 3: I2V start",
        "REST|POST /v1/video:batchAsyncGenerateVideoStartAndEndImage": "Nhom 3: I2V S+E",
        "REST|POST /v1/video:batchAsyncGenerateVideoReferenceImages": "Nhom 3: R2V",
        "REST|POST /v1/video:batchAsyncGenerateVideoUpsampleVideo": "Nhom 3: Upscale video",
        "REST|POST /v1/projects/{id}/flowMedia:batchGenerateImages": "Nhom 3: Generate anh",
        "REST|POST /v1/flow/upsampleImage": "Nhom 3: Upscale anh",
        # Nhom 4
        "REST|POST /v1/video:batchCheckAsyncVideoGenerationStatus": "Nhom 4: Poll trang thai",
        "REST|POST /v1/video:generatePinholeGif": "Nhom 4: Generate GIF",
        # Nhom 5
        "STORAGE|storage.googleapis.com download": "Nhom 5: Tai video",
        # Nhom 6
        "TRPC|videoFx.setLastSelectedVideoModelKey": "Nhom 6: Set model key",
        "TRPC|videoFx.setLastSelectedVideoAspectRatio": "Nhom 6: Set aspect ratio",
        "TRPC|general.submitBatchLog": "Nhom 6: Logging event",
        "TRPC|general.reportClientSideError": "Nhom 6: Report error",
    }
    
    # All endpoints found in HAR
    all_har_endpoints = set()
    for seq in all_sequences:
        for e in seq:
            all_har_endpoints.add(f"{e['cat']}|{e['ep']}")
    
    # 3A: In HAR but NOT documented
    print(f"\n3A. Endpoints in HAR but NOT in doc ({len(all_har_endpoints - set(documented.keys()))}):")
    for ep in sorted(all_har_endpoints - set(documented.keys())):
        info = avg_positions.get(ep, {})
        count = info.get("count", 0)
        print(f"  MISSING: {ep} (appears in {count} files)")
    
    # 3B: Documented but NOT in HAR
    print(f"\n3B. Endpoints in doc but NOT in HAR ({len(set(documented.keys()) - all_har_endpoints)}):")
    for ep in sorted(set(documented.keys()) - all_har_endpoints):
        print(f"  NOT FOUND: {ep} -> {documented[ep]}")
    
    # 3C: Both matched
    matched = all_har_endpoints & set(documented.keys())
    print(f"\n3C. Matched endpoints ({len(matched)}/{len(documented)}):")
    for ep in sorted(matched):
        info = avg_positions.get(ep, {})
        print(f"  OK: {ep} -> {documented[ep]} (avg pos: {info.get('avg', '?'):.1f}, {info.get('count', 0)} files)")
    
    # ==================== SECTION 4: Recommended Order ====================
    print(f"\n\n{'='*100}")
    print("SECTION 4: RECOMMENDED CHRONOLOGICAL ORDER FOR §1.4.D")
    print("=" * 100)
    print("Based on actual execution order observed across all sessions:\n")
    
    # Map documented endpoints to their avg position
    doc_with_pos = []
    for ep, label in documented.items():
        if ep in avg_positions:
            doc_with_pos.append((avg_positions[ep]["avg"], ep, label, avg_positions[ep]["count"]))
        else:
            doc_with_pos.append((999, ep, label + " [NO HAR DATA]", 0))
    
    doc_with_pos.sort()
    
    current_phase = ""
    for rank, (avg, ep, label, count) in enumerate(doc_with_pos, 1):
        # Detect phase transitions
        if avg < 5:
            phase = "PHASE 1: Init & Config"
        elif avg < 10:
            phase = "PHASE 2: Load Project & Data"
        elif avg < 15:
            phase = "PHASE 3: Pre-Generate (reCAPTCHA, upload)"
        elif avg < 20:
            phase = "PHASE 4: Generate & Submit"
        elif avg < 25:
            phase = "PHASE 5: Poll & Wait"
        elif avg < 30:
            phase = "PHASE 6: Download & Post-process"
        else:
            phase = "PHASE 7: Throughout session (telemetry)"
        
        if phase != current_phase:
            current_phase = phase
            print(f"\n  === {phase} ===")
        
        pos_str = f"{avg:>5.1f}" if avg < 999 else "  N/A"
        count_str = f"{count:>2} files" if count > 0 else "no HAR"
        print(f"  {rank:>2}. [{pos_str}] {ep.split('|',1)[1]:55s} ({count_str})")

if __name__ == "__main__":
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        old = sys.stdout
        sys.stdout = f
        main()
        sys.stdout = old
    print(f"Output written to: {OUT_FILE}")
