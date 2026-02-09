#!/usr/bin/env python3
"""
Full HAR Analysis — Processes ALL 51 HAR files exhaustively.
Extracts: endpoints, payloads, responses, headers, states, relationships.
Output: full_har_analysis_output.txt
"""

import json
import os
import glob
import re
from collections import defaultdict, OrderedDict
from urllib.parse import urlparse, parse_qs

HAR_DIR = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New"
OUTPUT_FILE = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\full_har_analysis_output.txt"

# Track all unique data across all files
all_endpoints = defaultdict(list)  # endpoint -> [{file, method, headers, payload, response, status_code}]
all_har_files = []
file_summaries = {}
unique_operations = set()
all_status_transitions = defaultdict(list)
all_model_keys_seen = set()
all_media_ids = defaultdict(set)  # prefix -> set of mediaIds
all_project_ids = set()
all_session_ids = set()
all_cookies = defaultdict(set)
all_query_params = defaultdict(set)  # endpoint -> set of query param keys
all_content_types = defaultdict(set)
all_error_responses = []
all_credit_values = []
polling_sequences = defaultdict(list)  # file -> polling data
all_unique_headers = defaultdict(set)  # domain -> set of header names
all_origins = defaultdict(set)
all_referers = defaultdict(set)

def classify_url(url):
    """Classify URL into domain and endpoint path."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path
    
    # Remove UUIDs from path for grouping
    path_normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '{UUID}', path)
    # Remove base64-like IDs
    path_normalized = re.sub(r'/CA[A-Za-z0-9_-]{20,}', '/{MEDIA_ID}', path_normalized)
    
    return host, path, path_normalized

def extract_payload(entry):
    """Extract request payload."""
    request = entry.get("request", {})
    post_data = request.get("postData", {})
    mime = post_data.get("mimeType", "")
    text = post_data.get("text", "")
    
    if not text:
        return None, mime
    
    # Try JSON parse
    try:
        return json.loads(text), mime
    except:
        # Binary/protobuf
        return text[:200] + "..." if len(text) > 200 else text, mime

def extract_response(entry):
    """Extract response content."""
    response = entry.get("response", {})
    content = response.get("content", {})
    mime = content.get("mimeType", "")
    text = content.get("text", "")
    status = response.get("status", 0)
    
    if not text:
        return None, mime, status
    
    # Try JSON parse
    try:
        parsed = json.loads(text)
        return parsed, mime, status
    except:
        # Check for anti-XSSI prefix
        if text.startswith(")]}'"):
            try:
                clean = text.split("\n", 1)[1] if "\n" in text else text[4:]
                return json.loads(clean), mime, status
            except:
                pass
        return text[:500] + "..." if len(text) > 500 else text, mime, status

def extract_headers_dict(headers_list):
    """Convert headers list to dict."""
    result = {}
    for h in headers_list:
        name = h.get("name", "").lower()
        value = h.get("value", "")
        result[name] = value
    return result

def get_json_keys_deep(obj, prefix="", max_depth=4):
    """Get all JSON keys recursively for structure analysis."""
    keys = []
    if isinstance(obj, dict) and max_depth > 0:
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            keys.append(full_key)
            if isinstance(v, (dict, list)):
                keys.extend(get_json_keys_deep(v, full_key, max_depth - 1))
    elif isinstance(obj, list) and len(obj) > 0 and max_depth > 0:
        keys.extend(get_json_keys_deep(obj[0], f"{prefix}[0]", max_depth - 1))
    return keys

def find_values_by_key(obj, target_key):
    """Find all values for a given key in nested JSON."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == target_key:
                results.append(v)
            elif isinstance(v, (dict, list)):
                results.extend(find_values_by_key(v, target_key))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(find_values_by_key(item, target_key))
    return results

def process_har_file(filepath):
    """Process a single HAR file and extract all data."""
    filename = os.path.basename(filepath)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return {"error": str(e), "filename": filename}
    
    entries = data.get("log", {}).get("entries", [])
    
    file_data = {
        "filename": filename,
        "total_entries": len(entries),
        "endpoints": [],
        "api_calls": [],
        "polling_count": 0,
        "status_transitions": [],
        "unique_features": [],
    }
    
    for i, entry in enumerate(entries):
        request = entry.get("request", {})
        url = request.get("url", "")
        method = request.get("method", "GET")
        
        # Skip non-API requests (css, js, images, fonts, etc.)
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path = parsed.path
        
        # Filter: only API-relevant domains
        relevant_domains = [
            "labs.google",
            "aisandbox-pa.googleapis.com",
            "storage.googleapis.com",
            "www.google.com",
        ]
        
        if not any(d in host for d in relevant_domains):
            continue
        
        # Skip static assets
        if any(path.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.ico', '.svg', '.woff', '.woff2', '.ttf']):
            continue
        if '/_next/' in path or '/static/' in path:
            continue
        
        host, raw_path, norm_path = classify_url(url)
        req_headers = extract_headers_dict(request.get("headers", []))
        payload, payload_mime = extract_payload(entry)
        resp_data, resp_mime, status_code = extract_response(entry)
        
        # Track query params
        query = parse_qs(parsed.query)
        for qk in query.keys():
            all_query_params[norm_path].add(qk)
        
        # Track headers per domain
        for h_name in req_headers.keys():
            if h_name.startswith('x-') or h_name.startswith(':') or h_name in ['authorization', 'cookie', 'content-type']:
                all_unique_headers[host].add(h_name)
        
        # Track origins and referers
        if 'origin' in req_headers:
            all_origins[host].add(req_headers['origin'])
        if 'referer' in req_headers:
            all_referers[host].add(req_headers['referer'][:100])
        
        # Track content types
        all_content_types[host].add(req_headers.get('content-type', 'none'))
        
        # Build endpoint key
        if 'trpc' in path:
            # Extract TRPC procedure name
            trpc_match = re.search(r'/trpc/([^?]+)', path)
            endpoint_key = f"TRPC:{trpc_match.group(1)}" if trpc_match else f"TRPC:{path}"
        elif 'recaptcha' in path:
            endpoint_key = f"RECAPTCHA:{path.split('?')[0]}"
        elif 'storage.googleapis.com' in host:
            endpoint_key = f"STORAGE:{norm_path}"
        elif 'auth/session' in path:
            endpoint_key = f"AUTH:{path}"
        else:
            endpoint_key = f"REST:{norm_path}"
        
        # Extract important values from payload/response
        if isinstance(payload, dict):
            # Model keys
            for mk in find_values_by_key(payload, 'videoModelKey'):
                all_model_keys_seen.add(mk)
            for mk in find_values_by_key(payload, 'modelKey'):
                all_model_keys_seen.add(mk)
            # Project IDs
            for pid in find_values_by_key(payload, 'projectId'):
                if isinstance(pid, str) and len(pid) > 10:
                    all_project_ids.add(pid)
            # Session IDs
            for sid in find_values_by_key(payload, 'sessionId'):
                all_session_ids.add(str(sid))
            # Media IDs
            for mid in find_values_by_key(payload, 'mediaId'):
                if isinstance(mid, str):
                    prefix = mid[:4] if len(mid) > 4 else mid
                    all_media_ids[prefix].add(mid[:30])
            for mid in find_values_by_key(payload, 'mediaGenerationId'):
                if isinstance(mid, str):
                    prefix = mid[:4] if len(mid) > 4 else mid
                    all_media_ids[prefix].add(mid[:30])
            # Status values
            for sv in find_values_by_key(payload, 'status'):
                if isinstance(sv, str) and 'GENERATION' in sv:
                    all_status_transitions[filename].append(sv)
        
        if isinstance(resp_data, dict):
            # Credits
            for cv in find_values_by_key(resp_data, 'credits'):
                if isinstance(cv, (int, float)):
                    all_credit_values.append((filename, cv))
            for cv in find_values_by_key(resp_data, 'remainingCredits'):
                if isinstance(cv, (int, float)):
                    all_credit_values.append((filename, cv))
            # Model keys in response
            for mk in find_values_by_key(resp_data, 'key'):
                if isinstance(mk, str) and mk.startswith('veo_'):
                    all_model_keys_seen.add(mk)
            # Error responses
            if status_code >= 400 or 'error' in resp_data:
                all_error_responses.append({
                    "file": filename,
                    "endpoint": endpoint_key,
                    "status": status_code,
                    "error": resp_data.get('error', resp_data) if isinstance(resp_data, dict) else str(resp_data)[:200]
                })
        
        # Detect polling
        is_polling = 'batchCheckAsync' in path
        if is_polling:
            file_data["polling_count"] += 1
            if isinstance(resp_data, dict):
                statuses = find_values_by_key(resp_data, 'status')
                gen_statuses = [s for s in statuses if isinstance(s, str) and 'GENERATION' in s]
                polling_sequences[filename].append({
                    "poll_index": file_data["polling_count"],
                    "statuses": set(gen_statuses),
                    "has_remaining_credits": 'remainingCredits' in json.dumps(resp_data) if resp_data else False
                })
        
        entry_data = {
            "index": i,
            "endpoint_key": endpoint_key,
            "method": method,
            "host": host,
            "path": raw_path,
            "norm_path": norm_path,
            "status_code": status_code,
            "payload_mime": payload_mime,
            "resp_mime": resp_mime,
            "payload_keys": get_json_keys_deep(payload) if isinstance(payload, dict) else [],
            "response_keys": get_json_keys_deep(resp_data) if isinstance(resp_data, dict) else [],
            "payload": payload,
            "response": resp_data,
            "is_polling": is_polling,
            "req_headers": req_headers,
        }
        
        file_data["api_calls"].append(entry_data)
        all_endpoints[endpoint_key].append({
            "file": filename,
            "method": method,
            "status_code": status_code,
            "payload": payload,
            "response": resp_data,
            "headers": req_headers,
            "payload_keys": entry_data["payload_keys"],
            "response_keys": entry_data["response_keys"],
            "host": host,
            "path": raw_path,
        })
    
    return file_data

def truncate_json(obj, max_str_len=100, max_list_items=3, depth=0, max_depth=5):
    """Truncate large JSON for display while preserving structure."""
    if depth > max_depth:
        return "..."
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            result[k] = truncate_json(v, max_str_len, max_list_items, depth+1, max_depth)
        return result
    elif isinstance(obj, list):
        if len(obj) <= max_list_items:
            return [truncate_json(item, max_str_len, max_list_items, depth+1, max_depth) for item in obj]
        else:
            truncated = [truncate_json(item, max_str_len, max_list_items, depth+1, max_depth) for item in obj[:max_list_items]]
            truncated.append(f"... ({len(obj)} items total)")
            return truncated
    elif isinstance(obj, str):
        if len(obj) > max_str_len:
            return obj[:max_str_len] + f"...({len(obj)} chars)"
        return obj
    else:
        return obj

def main():
    har_files = glob.glob(os.path.join(HAR_DIR, "*.har"))
    har_files.sort()
    
    print(f"Found {len(har_files)} HAR files")
    
    all_file_data = []
    for hf in har_files:
        print(f"  Processing: {os.path.basename(hf)}")
        fd = process_har_file(hf)
        all_file_data.append(fd)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        out.write("=" * 120 + "\n")
        out.write("FULL HAR ANALYSIS — ALL 51 FILES — EXHAUSTIVE EXTRACTION\n")
        out.write("=" * 120 + "\n\n")
        
        # =====================================================
        # SECTION 1: FILE INVENTORY
        # =====================================================
        out.write("=" * 120 + "\n")
        out.write("SECTION 1: FILE INVENTORY (ALL 51 HAR FILES)\n")
        out.write("=" * 120 + "\n\n")
        
        for i, fd in enumerate(all_file_data, 1):
            fn = fd.get("filename", "?")
            total = fd.get("total_entries", 0)
            api_count = len(fd.get("api_calls", []))
            poll_count = fd.get("polling_count", 0)
            error = fd.get("error", "")
            
            if error:
                out.write(f"  {i:2d}. {fn} — ERROR: {error}\n")
                continue
            
            # Get unique endpoints in this file
            endpoints_in_file = set()
            for ac in fd.get("api_calls", []):
                endpoints_in_file.add(ac["endpoint_key"])
            
            out.write(f"  {i:2d}. {fn}\n")
            out.write(f"      Total entries: {total}, API calls: {api_count}, Polling: {poll_count}\n")
            out.write(f"      Endpoints: {', '.join(sorted(endpoints_in_file))}\n\n")
        
        # =====================================================
        # SECTION 2: ALL UNIQUE ENDPOINTS (MASTER LIST)
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 2: ALL UNIQUE ENDPOINTS — MASTER LIST\n")
        out.write("=" * 120 + "\n\n")
        
        # Sort endpoints by category
        categories = defaultdict(list)
        for ep_key in sorted(all_endpoints.keys()):
            cat = ep_key.split(":")[0]
            categories[cat].append(ep_key)
        
        for cat in ["AUTH", "TRPC", "REST", "RECAPTCHA", "STORAGE"]:
            if cat not in categories:
                continue
            out.write(f"\n--- {cat} ENDPOINTS ---\n\n")
            for ep_key in categories[cat]:
                occurrences = all_endpoints[ep_key]
                files = sorted(set(o["file"] for o in occurrences))
                methods = set(o["method"] for o in occurrences)
                statuses = set(o["status_code"] for o in occurrences)
                hosts = set(o["host"] for o in occurrences)
                
                out.write(f"  ENDPOINT: {ep_key}\n")
                out.write(f"    Methods: {methods}\n")
                out.write(f"    Status codes: {statuses}\n")
                out.write(f"    Host(s): {hosts}\n")
                out.write(f"    Occurrences: {len(occurrences)} across {len(files)} files\n")
                out.write(f"    Files: {', '.join(files)}\n")
                
                # Show ALL unique payload structures
                unique_payload_structures = set()
                for o in occurrences:
                    if o["payload_keys"]:
                        key_sig = "|".join(sorted(o["payload_keys"]))
                        unique_payload_structures.add(key_sig)
                
                if unique_payload_structures:
                    out.write(f"    Unique payload structures: {len(unique_payload_structures)}\n")
                    for idx, struct in enumerate(unique_payload_structures, 1):
                        keys = struct.split("|")
                        out.write(f"      Structure {idx}: {keys}\n")
                
                # Show ALL unique response structures
                unique_response_structures = set()
                for o in occurrences:
                    if o["response_keys"]:
                        key_sig = "|".join(sorted(o["response_keys"]))
                        unique_response_structures.add(key_sig)
                
                if unique_response_structures:
                    out.write(f"    Unique response structures: {len(unique_response_structures)}\n")
                    for idx, struct in enumerate(unique_response_structures, 1):
                        keys = struct.split("|")
                        out.write(f"      Structure {idx}: {keys}\n")
                
                out.write("\n")
        
        # =====================================================
        # SECTION 3: FULL PAYLOAD/RESPONSE FOR EACH ENDPOINT
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 3: FULL PAYLOAD & RESPONSE SAMPLES — EVERY UNIQUE ENDPOINT\n")
        out.write("=" * 120 + "\n\n")
        
        for cat in ["AUTH", "TRPC", "REST", "RECAPTCHA", "STORAGE"]:
            if cat not in categories:
                continue
            out.write(f"\n{'='*80}\n")
            out.write(f"  CATEGORY: {cat}\n")
            out.write(f"{'='*80}\n\n")
            
            for ep_key in categories[cat]:
                occurrences = all_endpoints[ep_key]
                out.write(f"\n  {'─'*70}\n")
                out.write(f"  ENDPOINT: {ep_key}\n")
                out.write(f"  {'─'*70}\n")
                
                # Group by unique payload+response structure combos
                seen_combos = set()
                sample_count = 0
                
                for o in occurrences:
                    # Create a signature of this occurrence
                    p_sig = str(sorted(o["payload_keys"]))
                    r_sig = str(sorted(o["response_keys"]))
                    combo = f"{p_sig}||{r_sig}"
                    
                    if combo in seen_combos:
                        continue
                    seen_combos.add(combo)
                    sample_count += 1
                    
                    out.write(f"\n  --- Sample {sample_count} (from: {o['file']}) ---\n")
                    out.write(f"  Method: {o['method']} | Status: {o['status_code']} | Host: {o['host']}\n")
                    out.write(f"  Path: {o['path']}\n")
                    
                    # Headers
                    relevant_headers = {k: v for k, v in o['headers'].items() 
                                       if k.startswith('x-') or k in [':authority', ':method', ':path', 'content-type', 'origin', 'referer', 'cookie', 'authorization', 'sec-fetch-mode', 'sec-fetch-site']}
                    if relevant_headers:
                        out.write(f"  Headers:\n")
                        for hk, hv in sorted(relevant_headers.items()):
                            out.write(f"    {hk}: {hv[:150]}\n")
                    
                    # Payload
                    if o['payload'] is not None:
                        if isinstance(o['payload'], dict):
                            truncated = truncate_json(o['payload'], max_str_len=150, max_list_items=5)
                            out.write(f"  PAYLOAD:\n{json.dumps(truncated, indent=4, ensure_ascii=False)}\n")
                        else:
                            ptext = str(o['payload'])
                            out.write(f"  PAYLOAD (raw, {len(ptext)} chars): {ptext[:300]}\n")
                    else:
                        out.write(f"  PAYLOAD: (none)\n")
                    
                    # Response
                    if o['response'] is not None:
                        if isinstance(o['response'], dict):
                            truncated = truncate_json(o['response'], max_str_len=200, max_list_items=5)
                            out.write(f"  RESPONSE:\n{json.dumps(truncated, indent=4, ensure_ascii=False)}\n")
                        elif isinstance(o['response'], list):
                            truncated = truncate_json(o['response'], max_str_len=200, max_list_items=5)
                            out.write(f"  RESPONSE:\n{json.dumps(truncated, indent=4, ensure_ascii=False)}\n")
                        else:
                            rtext = str(o['response'])
                            out.write(f"  RESPONSE (raw, {len(rtext)} chars): {rtext[:500]}\n")
                    else:
                        out.write(f"  RESPONSE: (none/empty)\n")
                
                out.write(f"\n  Total unique samples for {ep_key}: {sample_count} out of {len(occurrences)} occurrences\n")
        
        # =====================================================
        # SECTION 4: HEADER ANALYSIS PER DOMAIN
        # =====================================================
        out.write("\n\n" + "=" * 120 + "\n")
        out.write("SECTION 4: HEADER ANALYSIS PER DOMAIN\n")
        out.write("=" * 120 + "\n\n")
        
        for domain in sorted(all_unique_headers.keys()):
            headers = all_unique_headers[domain]
            out.write(f"  Domain: {domain}\n")
            out.write(f"    Headers: {sorted(headers)}\n")
            out.write(f"    Origins: {sorted(all_origins.get(domain, set()))}\n")
            out.write(f"    Referers: {sorted(all_referers.get(domain, set()))}\n")
            out.write(f"    Content-Types: {sorted(all_content_types.get(domain, set()))}\n\n")
        
        # =====================================================
        # SECTION 5: ALL MODEL KEYS
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 5: ALL MODEL KEYS SEEN ACROSS ALL FILES\n")
        out.write("=" * 120 + "\n\n")
        
        for mk in sorted(all_model_keys_seen):
            # Find which files use this model
            files_using = set()
            for ep_key, occs in all_endpoints.items():
                for o in occs:
                    if isinstance(o['payload'], dict):
                        vals = find_values_by_key(o['payload'], 'videoModelKey') + find_values_by_key(o['payload'], 'modelKey')
                        if mk in vals:
                            files_using.add(o['file'])
            out.write(f"  {mk}\n")
            if files_using:
                out.write(f"    Used in: {', '.join(sorted(files_using))}\n")
        
        # =====================================================
        # SECTION 6: POLLING ANALYSIS 
        # =====================================================
        out.write("\n\n" + "=" * 120 + "\n")
        out.write("SECTION 6: POLLING ANALYSIS — ALL FILES WITH POLLING\n")
        out.write("=" * 120 + "\n\n")
        
        for filename, polls in sorted(polling_sequences.items()):
            out.write(f"  File: {filename}\n")
            out.write(f"    Total polls: {len(polls)}\n")
            
            # Track state transitions
            prev_statuses = None
            transitions = []
            for p in polls:
                current = frozenset(p["statuses"])
                if prev_statuses is not None and current != prev_statuses:
                    transitions.append(f"  Poll {p['poll_index']}: {set(prev_statuses)} → {set(current)}")
                prev_statuses = current
                if p["has_remaining_credits"]:
                    transitions.append(f"  Poll {p['poll_index']}: *** remainingCredits appeared ***")
            
            if transitions:
                out.write(f"    State transitions:\n")
                for t in transitions:
                    out.write(f"      {t}\n")
            
            # First and last poll status
            if polls:
                out.write(f"    First poll statuses: {polls[0]['statuses']}\n")
                out.write(f"    Last poll statuses: {polls[-1]['statuses']}\n")
                out.write(f"    Last poll has remainingCredits: {polls[-1]['has_remaining_credits']}\n")
            out.write("\n")
        
        # =====================================================
        # SECTION 7: CREDIT TRACKING
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 7: CREDIT VALUES ACROSS ALL FILES (CHRONOLOGICAL)\n")
        out.write("=" * 120 + "\n\n")
        
        for filename, value in all_credit_values:
            out.write(f"  {filename}: {value}\n")
        
        # =====================================================
        # SECTION 8: PROJECT IDs & SESSION IDs
        # =====================================================
        out.write("\n\n" + "=" * 120 + "\n")
        out.write("SECTION 8: ALL PROJECT IDs & SESSION IDs\n")
        out.write("=" * 120 + "\n\n")
        
        out.write("  Project IDs:\n")
        for pid in sorted(all_project_ids):
            # Find which files reference this project
            files_ref = set()
            for ep_key, occs in all_endpoints.items():
                for o in occs:
                    if isinstance(o['payload'], dict) and pid in json.dumps(o['payload']):
                        files_ref.add(o['file'])
                    if isinstance(o['response'], dict) and pid in json.dumps(o['response']):
                        files_ref.add(o['file'])
            out.write(f"    {pid}\n")
            out.write(f"      Files: {', '.join(sorted(files_ref))}\n")
        
        out.write("\n  Session IDs:\n")
        for sid in sorted(all_session_ids):
            out.write(f"    {sid}\n")
        
        # =====================================================
        # SECTION 9: MEDIA ID PREFIXES & PATTERNS
        # =====================================================
        out.write("\n\n" + "=" * 120 + "\n")
        out.write("SECTION 9: MEDIA ID PREFIXES & PATTERNS\n")
        out.write("=" * 120 + "\n\n")
        
        for prefix in sorted(all_media_ids.keys()):
            ids = all_media_ids[prefix]
            out.write(f"  Prefix: {prefix} — {len(ids)} unique IDs\n")
            for mid in sorted(ids)[:5]:  # Show up to 5 samples
                out.write(f"    Sample: {mid}\n")
            if len(ids) > 5:
                out.write(f"    ... and {len(ids)-5} more\n")
            out.write("\n")
        
        # =====================================================
        # SECTION 10: ERROR RESPONSES
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 10: ERROR RESPONSES\n")
        out.write("=" * 120 + "\n\n")
        
        if all_error_responses:
            for err in all_error_responses:
                out.write(f"  File: {err['file']}\n")
                out.write(f"  Endpoint: {err['endpoint']}\n")
                out.write(f"  Status: {err['status']}\n")
                err_text = json.dumps(err['error'], ensure_ascii=False, indent=4) if isinstance(err['error'], dict) else str(err['error'])
                out.write(f"  Error: {err_text[:500]}\n\n")
        else:
            out.write("  No error responses found.\n")
        
        # =====================================================
        # SECTION 11: PER-FILE DETAILED FLOW
        # =====================================================
        out.write("\n\n" + "=" * 120 + "\n")
        out.write("SECTION 11: PER-FILE DETAILED FLOW (CHRONOLOGICAL API CALL SEQUENCE)\n")
        out.write("=" * 120 + "\n\n")
        
        for fd in all_file_data:
            if fd.get("error"):
                continue
            fn = fd["filename"]
            api_calls = fd.get("api_calls", [])
            if not api_calls:
                continue
            
            out.write(f"\n{'='*80}\n")
            out.write(f"FILE: {fn}\n")
            out.write(f"{'='*80}\n")
            out.write(f"Total API calls: {len(api_calls)}\n\n")
            
            for ac in api_calls:
                poll_marker = " [POLL]" if ac["is_polling"] else ""
                out.write(f"  [{ac['index']:3d}] {ac['method']} {ac['endpoint_key']}{poll_marker} — HTTP {ac['status_code']}\n")
                
                # For non-polling calls, show truncated payload/response
                if not ac["is_polling"]:
                    if ac["payload_keys"]:
                        out.write(f"        Payload keys: {ac['payload_keys'][:15]}\n")
                    if ac["response_keys"]:
                        out.write(f"        Response keys: {ac['response_keys'][:15]}\n")
            
            out.write("\n")
        
        # =====================================================
        # SECTION 12: QUERY PARAMETERS PER ENDPOINT
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 12: QUERY PARAMETERS PER ENDPOINT\n")
        out.write("=" * 120 + "\n\n")
        
        for ep_path in sorted(all_query_params.keys()):
            params = all_query_params[ep_path]
            if params:
                out.write(f"  {ep_path}: {sorted(params)}\n")
        
        # =====================================================
        # SECTION 13: FILE-TO-FILE RELATIONSHIPS
        # =====================================================
        out.write("\n\n" + "=" * 120 + "\n")
        out.write("SECTION 13: FILE-TO-FILE RELATIONSHIPS (Shared Project/Session/Operation IDs)\n")
        out.write("=" * 120 + "\n\n")
        
        # Build file-to-projectId mapping
        file_projects = defaultdict(set)
        for ep_key, occs in all_endpoints.items():
            for o in occs:
                if isinstance(o['payload'], dict):
                    for pid in find_values_by_key(o['payload'], 'projectId'):
                        if isinstance(pid, str) and len(pid) > 10:
                            file_projects[o['file']].add(pid)
                if isinstance(o['response'], dict):
                    for pid in find_values_by_key(o['response'], 'projectId'):
                        if isinstance(pid, str) and len(pid) > 10:
                            file_projects[o['file']].add(pid)
        
        # Group files by shared project
        project_files = defaultdict(set)
        for f, pids in file_projects.items():
            for pid in pids:
                project_files[pid].add(f)
        
        out.write("  Files grouped by shared Project ID:\n\n")
        for pid, files in sorted(project_files.items(), key=lambda x: -len(x[1])):
            if len(files) > 1:
                out.write(f"  Project: {pid}\n")
                for f in sorted(files):
                    out.write(f"    - {f}\n")
                out.write("\n")
        
        # =====================================================
        # SECTION 14: FULL TRPC BATCH CALLS
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 14: TRPC BATCH CALLS (Multiple procedures in single request)\n")
        out.write("=" * 120 + "\n\n")
        
        for ep_key in sorted(all_endpoints.keys()):
            if 'TRPC' in ep_key and ',' in ep_key:
                occs = all_endpoints[ep_key]
                out.write(f"  Batch: {ep_key}\n")
                out.write(f"    Files: {sorted(set(o['file'] for o in occs))}\n")
                out.write(f"    Occurrences: {len(occs)}\n\n")
        
        # =====================================================
        # SECTION 15: UNIQUE FEATURES PER FILE (Not in previously analyzed set)
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SECTION 15: FILES NOT PREVIOUSLY ANALYZED — UNIQUE FEATURES\n")
        out.write("=" * 120 + "\n\n")
        
        previously_analyzed = {
            "0. Tao Project.har",
            "01. ingedients to video hoan thanh 4 video prompt 3 anh.har",
            "916 frame to video submit - done.har",  # approximate
            "Check Ultra.har",
            "Check trạng thái tài khoản Ultra hay Pro.har",
            "Download anh 2k.har",
            "Download gif 4 vid.har",
            "Download upscale 1080p 4 vid done.har",
            "Full tạo ảnh.har",
            "tao video vs anh first frame.har",
            "whisk 2.har",
        }
        
        for fd in all_file_data:
            if fd.get("error"):
                continue
            fn = fd["filename"]
            # Check if this was previously analyzed (fuzzy match)
            was_analyzed = any(pa in fn or fn in pa for pa in previously_analyzed)
            
            if not was_analyzed:
                api_calls = fd.get("api_calls", [])
                endpoints_in_file = set(ac["endpoint_key"] for ac in api_calls)
                
                out.write(f"  NEW FILE: {fn}\n")
                out.write(f"    API calls: {len(api_calls)}, Polling: {fd.get('polling_count', 0)}\n")
                out.write(f"    Endpoints: {sorted(endpoints_in_file)}\n")
                
                # Show non-polling, non-duplicate interesting calls
                for ac in api_calls:
                    if not ac["is_polling"]:
                        out.write(f"    [{ac['index']:3d}] {ac['method']} {ac['endpoint_key']} — HTTP {ac['status_code']}\n")
                        if isinstance(ac.get('payload'), dict):
                            out.write(f"          Payload: {json.dumps(truncate_json(ac['payload'], 80, 3), ensure_ascii=False)[:300]}\n")
                        if isinstance(ac.get('response'), dict):
                            out.write(f"          Response: {json.dumps(truncate_json(ac['response'], 80, 3), ensure_ascii=False)[:300]}\n")
                
                out.write("\n")
        
        # =====================================================
        # SUMMARY STATISTICS
        # =====================================================
        out.write("\n" + "=" * 120 + "\n")
        out.write("SUMMARY STATISTICS\n")
        out.write("=" * 120 + "\n\n")
        
        out.write(f"  Total HAR files processed: {len(all_file_data)}\n")
        out.write(f"  Total unique endpoints: {len(all_endpoints)}\n")
        out.write(f"  Total unique model keys: {len(all_model_keys_seen)}\n")
        out.write(f"  Total project IDs: {len(all_project_ids)}\n")
        out.write(f"  Total session IDs: {len(all_session_ids)}\n")
        out.write(f"  Total credit readings: {len(all_credit_values)}\n")
        out.write(f"  Total error responses: {len(all_error_responses)}\n")
        out.write(f"  Files with polling: {len(polling_sequences)}\n")
        total_polls = sum(len(v) for v in polling_sequences.values())
        out.write(f"  Total polling requests: {total_polls}\n")
        
        by_cat = {}
        for ep_key in all_endpoints:
            cat = ep_key.split(":")[0]
            by_cat[cat] = by_cat.get(cat, 0) + 1
        out.write(f"  Endpoints by category: {dict(sorted(by_cat.items()))}\n")
    
    print(f"\nAnalysis complete. Output written to: {OUTPUT_FILE}")
    print(f"Total endpoints: {len(all_endpoints)}")
    print(f"Total polls: {sum(len(v) for v in polling_sequences.values())}")

if __name__ == "__main__":
    main()
