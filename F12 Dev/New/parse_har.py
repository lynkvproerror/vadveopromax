"""
Comprehensive HAR Deep Analysis
- Strictly uses ONLY data from the HAR files
- Clearly separates REQUEST (client -> server) and RESPONSE (server -> client)
- No prior assumptions
- Outputs to file for review
"""
import json
import sys
import os

OUTPUT_FILE = r"D:\NEW VEO PRO MAX\veo-pro-max\F12 Dev\New\deep_har_analysis.txt"

def write(f, text=""):
    f.write(text + "\n")

def analyze_har(filepath, label, f):
    with open(filepath, "r", encoding="utf-8") as hf:
        har = json.load(hf)
    
    entries = har["log"]["entries"]
    
    write(f, "#" * 100)
    write(f, f"# FILE: {label}")
    write(f, f"# Path: {filepath}")
    write(f, f"# Total entries: {len(entries)}")
    write(f, "#" * 100)
    write(f)
    
    # Categorize all entries by domain
    domains = {}
    for i, entry in enumerate(entries):
        req = entry["request"]
        url = req["url"]
        # Extract domain
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain not in domains:
            domains[domain] = []
        domains[domain].append((i, entry))
    
    write(f, "=" * 80)
    write(f, "SECTION 1: OVERVIEW - ALL DOMAINS")
    write(f, "=" * 80)
    for domain, ents in sorted(domains.items()):
        methods = {}
        for _, e in ents:
            m = e["request"]["method"]
            methods[m] = methods.get(m, 0) + 1
        write(f, f"  {domain}: {len(ents)} entries ({methods})")
    write(f)
    
    # Only focus on aisandbox-pa requests
    aisandbox_entries = domains.get("aisandbox-pa.googleapis.com", [])
    
    if not aisandbox_entries:
        write(f, "No aisandbox-pa entries found!")
        return
    
    # Group by endpoint + method
    endpoint_groups = {}
    for i, entry in aisandbox_entries:
        req = entry["request"]
        url = req["url"]
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path
        method = req["method"]
        key = f"{method} {path}"
        if key not in endpoint_groups:
            endpoint_groups[key] = []
        endpoint_groups[key].append((i, entry))
    
    write(f, "=" * 80)
    write(f, "SECTION 2: ENDPOINT SUMMARY")
    write(f, "=" * 80)
    for key, ents in sorted(endpoint_groups.items()):
        statuses = [e["response"]["status"] for _, e in ents]
        status_counts = {}
        for s in statuses:
            status_counts[s] = status_counts.get(s, 0) + 1
        write(f, f"  {key}: {len(ents)}x  statuses={status_counts}")
    write(f)
    
    # Detailed analysis of each POST request (generation/upscale calls)
    write(f, "=" * 80)
    write(f, "SECTION 3: DETAILED POST REQUESTS (client -> server)")
    write(f, "           Only showing unique generation/upscale requests")
    write(f, "           Skipping repeated status polling")
    write(f, "=" * 80)
    
    seen_poll = set()  # track polling calls to deduplicate
    
    for i, entry in aisandbox_entries:
        req = entry["request"]
        resp = entry["response"]
        url = req["url"]
        method = req["method"]
        status = resp["status"]
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path
        
        # For polling (batchCheckAsync), only show first + last
        is_poll = "batchCheckAsync" in path
        if is_poll:
            poll_key = path
            if poll_key in seen_poll:
                continue
            seen_poll.add(poll_key)
            write(f, f"\n{'='*80}")
            write(f, f"[Entry {i}] {method} {path}")
            write(f, f"  (Polling endpoint - showing first occurrence only, see summary above for count)")
        elif method == "OPTIONS":
            write(f, f"\n{'='*80}")  
            write(f, f"[Entry {i}] {method} {path}")
            write(f, f"  (CORS Preflight)")
        elif method == "GET" and "/v1/media/" in path:
            # Media download - show briefly
            write(f, f"\n{'='*80}")
            write(f, f"[Entry {i}] {method} {path[:60]}...")
            write(f, f"  (Media download)")
        else:
            write(f, f"\n{'='*80}")
            write(f, f"[Entry {i}] {method} {path}")
        
        write(f, f"Response Status: {status} {resp.get('statusText', '')}")
        write(f)
        
        # === REQUEST (client -> server) ===
        write(f, "  --- REQUEST (Client -> Server) ---")
        write(f, "  ALL Request Headers:")
        for h in req.get("headers", []):
            name = h["name"]
            val = h["value"]
            # Truncate very long values
            if len(val) > 150:
                val = val[:150] + f"... [{len(h['value'])} total chars]"
            write(f, f"    {name}: {val}")
        
        # Request body
        post_data = req.get("postData", {})
        text = post_data.get("text", "")
        mime = post_data.get("mimeType", "")
        if text:
            write(f, f"  Request Body (mimeType: {mime}):")
            try:
                body = json.loads(text)
                # Mask long tokens but preserve structure
                def mask_deep(obj, depth=0):
                    if isinstance(obj, dict):
                        result = {}
                        for k, v in obj.items():
                            if k == "token" and isinstance(v, str) and len(v) > 50:
                                result[k] = f"<{len(v)} chars>"
                            elif k == "rawImageBytes" and isinstance(v, str) and len(v) > 50:
                                result[k] = f"<base64 {len(v)} chars>"
                            else:
                                result[k] = mask_deep(v, depth + 1)
                        return result
                    elif isinstance(obj, list):
                        return [mask_deep(item, depth + 1) for item in obj]
                    else:
                        return obj
                
                masked = mask_deep(body)
                body_str = json.dumps(masked, indent=4, ensure_ascii=False)
                write(f, body_str)
            except json.JSONDecodeError:
                write(f, f"    [Non-JSON body, {len(text)} chars]: {text[:200]}...")
        elif req.get("queryString"):
            write(f, "  Query Parameters:")
            for q in req["queryString"]:
                val = q["value"]
                if len(val) > 200:
                    val = val[:200] + "..."
                write(f, f"    {q['name']}: {val}")
        
        write(f)
        
        # === RESPONSE (server -> client) ===
        write(f, "  --- RESPONSE (Server -> Client) ---")
        write(f, f"  Status: {status} {resp.get('statusText', '')}")
        write(f, "  Response Headers:")
        for h in resp.get("headers", []):
            name = h["name"]
            val = h["value"]
            if len(val) > 200:
                val = val[:200] + f"... [{len(h['value'])} total chars]"
            write(f, f"    {name}: {val}")
        
        # Response body
        resp_content = resp.get("content", {})
        resp_text = resp_content.get("text", "")
        resp_mime = resp_content.get("mimeType", "")
        resp_size = resp_content.get("size", 0)
        
        if resp_text:
            write(f, f"  Response Body (mimeType: {resp_mime}, size: {resp_size}):")
            try:
                resp_body = json.loads(resp_text)
                masked_resp = mask_deep(resp_body)
                resp_str = json.dumps(masked_resp, indent=4, ensure_ascii=False)
                # Limit output length per entry
                if len(resp_str) > 3000:
                    write(f, resp_str[:3000])
                    write(f, f"    ... [truncated, {len(resp_str)} total chars]")
                else:
                    write(f, resp_str)
            except json.JSONDecodeError:
                if len(resp_text) > 500:
                    write(f, f"    [Non-JSON response, {len(resp_text)} chars]: {resp_text[:500]}...")
                else:
                    write(f, f"    [Non-JSON response]: {resp_text}")
        else:
            write(f, f"  Response Body: (empty or binary, size: {resp_size})")
        
        # Timing
        time_ms = entry.get("time", 0)
        write(f, f"  Timing: {time_ms:.0f}ms")
        write(f)

    # === SECTION 4: TRPC CALLS ===
    labs_entries = []
    for domain, ents in domains.items():
        if "labs.google" in domain:
            labs_entries.extend(ents)
    
    trpc_entries = [(i, e) for i, e in labs_entries if "/fx/api/trpc/" in e["request"]["url"]]
    
    if trpc_entries:
        write(f, "\n" + "=" * 80)
        write(f, "SECTION 4: TRPC CALLS (labs.google)")
        write(f, "=" * 80)
        
        # Group by procedure name
        trpc_procs = {}
        for i, entry in trpc_entries:
            url = entry["request"]["url"]
            # Extract procedure name from URL
            path = url.split("/fx/api/trpc/")[-1].split("?")[0]
            method = entry["request"]["method"]
            status = entry["response"]["status"]
            if path not in trpc_procs:
                trpc_procs[path] = {"count": 0, "methods": set(), "statuses": []}
            trpc_procs[path]["count"] += 1
            trpc_procs[path]["methods"].add(method)
            trpc_procs[path]["statuses"].append(status)
        
        for proc, info in sorted(trpc_procs.items()):
            status_counts = {}
            for s in info["statuses"]:
                status_counts[s] = status_counts.get(s, 0) + 1
            write(f, f"  {proc}: {info['count']}x  methods={info['methods']}  statuses={status_counts}")
        
        # Show details of first TRPC call (for header comparison)
        write(f, "\n  --- FIRST TRPC REQUEST (for header comparison) ---")
        first_trpc = trpc_entries[0]
        req = first_trpc[1]["request"]
        write(f, f"  URL: {req['url'][:150]}...")
        write(f, "  Headers:")
        for h in req.get("headers", []):
            name = h["name"]
            val = h["value"]
            if len(val) > 120:
                val = val[:120] + "..."
            write(f, f"    {name}: {val}")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    write(f, "DEEP HAR ANALYSIS REPORT")
    write(f, "========================")
    write(f, "Only data from HAR files — no prior assumptions")
    write(f, "Clear separation: REQUEST (client->server) vs RESPONSE (server->client)")
    write(f)
    
    analyze_har(
        r"D:\NEW VEO PRO MAX\veo-pro-max\F12 Dev\New\Test.har",
        "Test.har (Video Flow)",
        f
    )
    
    write(f, "\n" * 3)
    
    analyze_har(
        r"D:\NEW VEO PRO MAX\veo-pro-max\F12 Dev\New\image flow.har",
        "image flow.har (Image Flow)",
        f
    )

print(f"Analysis written to: {OUTPUT_FILE}")
file_size = os.path.getsize(OUTPUT_FILE)
print(f"File size: {file_size:,} bytes")
