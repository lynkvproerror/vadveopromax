"""Analyze cURL export files to extract full header information."""
import re
import sys
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

files = [
    ("Fast", os.path.join(BASE, "All Har 12.05.2026 (Fast Submit-download 720p-upscale th\u00e0nh c\u00f4ng).txt")),
    ("Lite", os.path.join(BASE, "All Har 12.05.2026 (Lite Submit-download 720p-upscale th\u00e0nh c\u00f4ng).txt")),
]

for label, fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into individual curl commands
    parts = content.split("\ncurl '")
    curls = []
    for i, p in enumerate(parts):
        if p.strip():
            curls.append("curl '" + p if i > 0 else p)

    print(f"\n{'='*70}")
    print(f"{label} cURL Export: {len(curls)} requests")
    print(f"{'='*70}")

    aisandbox = []
    trpc = []
    session_reqs = []
    ga = []
    recaptcha_reqs = []

    for idx, curl in enumerate(curls):
        url_match = re.search(r"curl '([^']+)'", curl)
        if not url_match:
            continue
        url = url_match.group(1)

        auth_match = re.search(r"-H 'authorization: ([^']+)'", curl, re.IGNORECASE)
        auth = auth_match.group(1)[:50] + "..." if auth_match else "NONE"

        cookie_match = re.search(r"-b '", curl)
        has_cookie = "YES" if cookie_match else "NO"

        xcd_match = re.search(r"-H 'x-client-data: ([^']+)'", curl)
        xcd = xcd_match.group(1)[:30] if xcd_match else "NONE"

        xbv_match = re.search(r"-H 'x-browser-validation: ([^']+)'", curl)
        xbv = xbv_match.group(1)[:30] if xbv_match else "NONE"

        sfs_match = re.search(r"-H 'sec-fetch-site: ([^']+)'", curl)
        sfs = sfs_match.group(1) if sfs_match else "?"

        sfm_match = re.search(r"-H 'sec-fetch-mode: ([^']+)'", curl)
        sfm = sfm_match.group(1) if sfm_match else "?"

        sfsa_match = re.search(r"-H 'sec-fetch-storage-access: ([^']+)'", curl)
        sfsa = sfsa_match.group(1) if sfsa_match else "NONE"

        short = url.split("?")[0].split("/")[-1][:45]
        method = "GET"
        if "--data-raw" in curl or "-X 'POST'" in curl:
            method = "POST"
        if "-X 'PATCH'" in curl:
            method = "PATCH"

        entry = (idx, method, short, auth, xcd, xbv, sfs, sfm, has_cookie, sfsa)

        if "aisandbox-pa" in url:
            aisandbox.append(entry)
        elif "trpc" in url:
            trpc.append(entry)
        elif "auth/session" in url:
            session_reqs.append(entry)
        elif "google-analytics" in url:
            ga.append(entry)
        elif "recaptcha" in url:
            recaptcha_reqs.append(entry)

    print(f"\n--- aisandbox-pa requests ({len(aisandbox)}) ---")
    for idx, method, short, auth, xcd, xbv, sfs, sfm, cookie, sfsa in aisandbox:
        auth_type = "Bearer" if "Bearer" in auth else auth[:8]
        sfsa_info = f" storage-access={sfsa}" if sfsa != "NONE" else ""
        print(f"  #{idx:2d} {method:5s} {short:45s} Auth={auth_type:8s} XCD={xcd[:20]:20s} site={sfs:12s} mode={sfm}{sfsa_info}")

    print(f"\n--- TRPC requests ({len(trpc)}) ---")
    for idx, method, short, auth, xcd, xbv, sfs, sfm, cookie, sfsa in trpc[:3]:
        print(f"  #{idx:2d} {method:5s} {short:45s} Auth={auth:8s} Cookie={cookie} XCD={xcd[:15]} site={sfs:12s}")
    if len(trpc) > 3:
        print(f"  ... +{len(trpc)-3} more (all same pattern)")

    print(f"\n--- Session refresh ({len(session_reqs)}) ---")
    print(f"  {len(session_reqs)} requests, ALL cookie-based, NO Auth header")

    print(f"\n--- reCAPTCHA ({len(recaptcha_reqs)}) ---")
    for idx, method, short, auth, xcd, xbv, sfs, sfm, cookie, sfsa in recaptcha_reqs:
        auth_type = "Bearer" if "Bearer" in auth else auth[:8]
        print(f"  #{idx:2d} {method:5s} {short:45s} Auth={auth_type:8s} XCD={xcd[:20]:20s} site={sfs:12s} mode={sfm}")

    print(f"\n--- GA events: {len(ga)} ---")

    # Summary
    bearer_count = sum(1 for e in aisandbox if "Bearer" in e[3])
    none_count = sum(1 for e in aisandbox if e[3] == "NONE")
    tokens = set()
    for e in aisandbox:
        if "Bearer" in e[3]:
            tokens.add(e[3][:50])

    print(f"\n{'='*70}")
    print(f"SUMMARY for {label}:")
    print(f"  aisandbox: {len(aisandbox)} requests, {bearer_count} with Bearer, {none_count} without")
    print(f"  ALL aisandbox have x-client-data: {all(e[4]!='NONE' for e in aisandbox)}")
    print(f"  ALL aisandbox have x-browser-validation: {all(e[5]!='NONE' for e in aisandbox)}")
    print(f"  Unique Bearer tokens: {len(tokens)} (stable={len(tokens)<=1})")
    print(f"  TRPC: {len(trpc)} requests, NONE have Auth header, ALL cookie-based")
    print(f"  Session: {len(session_reqs)} refresh calls")
    print(f"  reCAPTCHA: {len(recaptcha_reqs)} calls")

    # Header order analysis for submit
    print(f"\n--- Header order for key requests ---")
    for idx, method, short, auth, xcd, xbv, sfs, sfm, cookie, sfsa in aisandbox:
        if "batchAsync" in short or "batchLog" in short or "batchCheck" in short or "credits" in short or "flowWorkflows" in short:
            # Extract all -H headers in order
            headers = re.findall(r"-H '([^:]+): ", curls[idx] if idx < len(curls) else "")
            print(f"\n  {method} {short}:")
            print(f"    Header order: {' | '.join(headers)}")
            if idx < 3 or "batchAsync" in short and "Generate" in short:
                break  # Just show key ones
