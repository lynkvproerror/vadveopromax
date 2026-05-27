"""Analyze complete flow logic from HAR+cURL: headers, reCAPTCHA, tokens, cadence."""
import json, re, os, sys
from datetime import datetime, timedelta
from collections import defaultdict

BASE = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02 - CLIENT - VEO PRO MAX"

HARS = [
    ("11.05", "All Har 11.05.2026.har"),
    ("12.05_full", "All Har 12.05.2026.har"),
    ("12.05_DL", "All Har 12.05.2026 (DOWNLOAD).har"),
    ("Fast_OK", "All Har 12.05.2026 (Fast Submit-download 720p-upscale th\u00e0nh c\u00f4ng).har"),
    ("Lite_OK", "All Har 12.05.2026 (Lite Submit-download 720p-upscale th\u00e0nh c\u00f4ng).har"),
    ("Err1", "All Har 12.05.2026 (L\u1ed7i T\u1ea1o Video).har"),
    ("Err2", "All Har 12.05.2026 (L\u1ed7i T\u1ea1o Video 2).har"),
]

CURLS = [
    ("Fast_cURL", "All Har 12.05.2026 (Fast Submit-download 720p-upscale th\u00e0nh c\u00f4ng).txt"),
    ("Lite_cURL", "All Har 12.05.2026 (Lite Submit-download 720p-upscale th\u00e0nh c\u00f4ng).txt"),
]

def parse_har(label, fname):
    path = os.path.join(BASE, fname)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    entries = data['log']['entries']
    results = []
    for e in entries:
        req = e['request']
        resp = e['response']
        url = req['url']
        hdrs = {h['name'].lower(): h['value'] for h in req['headers']}
        resp_hdrs = {h['name'].lower(): h['value'] for h in resp.get('headers', [])}
        ts = e.get('startedDateTime', '')
        
        # Classify
        short = url.split('?')[0].split('/')[-1][:50]
        domain = ''
        if 'aisandbox-pa' in url: domain = 'aisandbox'
        elif 'labs.google' in url and 'trpc' in url: domain = 'trpc'
        elif 'labs.google' in url and 'auth/session' in url: domain = 'session'
        elif 'recaptcha' in url: domain = 'recaptcha'
        elif 'google-analytics' in url: domain = 'ga'
        elif 'labs.google' in url: domain = 'labs_other'
        else: domain = 'other'
        
        # Extract key info
        has_auth = 'authorization' in hdrs
        has_xcd = 'x-client-data' in hdrs
        has_xbv = 'x-browser-validation' in hdrs
        status = resp.get('status', 0)
        method = req.get('method', 'GET')
        
        # Body for POST
        body_text = ''
        if req.get('postData', {}).get('text'):
            body_text = req['postData']['text'][:2000]
        
        # Response body
        resp_body = ''
        if resp.get('content', {}).get('text'):
            resp_body = resp['content']['text'][:3000]
        
        results.append({
            'ts': ts, 'url': url, 'short': short, 'domain': domain,
            'method': method, 'status': status,
            'has_auth': has_auth, 'has_xcd': has_xcd, 'has_xbv': has_xbv,
            'body': body_text, 'resp_body': resp_body,
            'hdrs': hdrs, 'resp_hdrs': resp_hdrs,
        })
    return results

def analyze_session_flow(label, entries):
    """Analyze a complete session flow."""
    if not entries:
        return
    
    print(f"\n{'='*80}")
    print(f"SESSION: {label} ({len(entries)} entries)")
    print(f"{'='*80}")
    
    # 1. reCAPTCHA analysis
    recaptcha_entries = [e for e in entries if e['domain'] == 'recaptcha']
    print(f"\n--- reCAPTCHA ({len(recaptcha_entries)} calls) ---")
    for e in recaptcha_entries:
        print(f"  {e['ts'][:19]} {e['method']:5s} {e['short']:30s} S={e['status']} XCD={e['has_xcd']} XBV={e['has_xbv']}")
    
    # 2. Submit analysis  
    submits = [e for e in entries if 'batchAsync' in e['url'] and 'Generate' in e['url'] and 'Upsample' not in e['url']]
    print(f"\n--- Submits ({len(submits)}) ---")
    for e in submits:
        # Extract recaptcha token presence
        has_recap = 'recaptchaContext' in e['body']
        # Extract model
        model_match = re.search(r'"videoModelKey":"([^"]+)"', e['body'])
        model = model_match.group(1) if model_match else '?'
        seed_match = re.search(r'"seed":(\d+)', e['body'])
        seed = seed_match.group(1) if seed_match else '?'
        print(f"  {e['ts'][:19]} S={e['status']} model={model} seed={seed} reCAPTCHA={has_recap} Auth={e['has_auth']} XCD={e['has_xcd']} XBV={e['has_xbv']}")
    
    # 3. Poll analysis
    polls = [e for e in entries if 'batchCheck' in e['url']]
    print(f"\n--- Polls ({len(polls)}) ---")
    if polls:
        # Calculate intervals
        intervals = []
        for i in range(1, len(polls)):
            try:
                t1 = datetime.fromisoformat(polls[i-1]['ts'].replace('Z','+00:00'))
                t2 = datetime.fromisoformat(polls[i]['ts'].replace('Z','+00:00'))
                intervals.append((t2-t1).total_seconds())
            except: pass
        if intervals:
            print(f"  Intervals: min={min(intervals):.1f}s avg={sum(intervals)/len(intervals):.1f}s max={max(intervals):.1f}s")
        
        # Check poll results
        success_polls = [p for p in polls if 'SUCCESSFUL' in p.get('resp_body','')]
        pending_polls = [p for p in polls if 'PENDING' in p.get('resp_body','')]
        print(f"  PENDING: {len(pending_polls)}, SUCCESSFUL: {len(success_polls)}")
    
    # 4. Upscale analysis
    upscales = [e for e in entries if 'Upsample' in e['url']]
    print(f"\n--- Upscales ({len(upscales)}) ---")
    for e in upscales:
        has_recap = 'recaptchaContext' in e['body']
        print(f"  {e['ts'][:19]} S={e['status']} reCAPTCHA={has_recap} Auth={e['has_auth']}")
    
    # 5. Redirect (download) analysis  
    redirects = [e for e in entries if 'getMediaUrlRedirect' in e['url']]
    print(f"\n--- Redirects/Downloads ({len(redirects)}) ---")
    for e in redirects:
        is_upsampled = '_upsampled' in e['url']
        print(f"  {e['ts'][:19]} S={e['status']} upsampled={is_upsampled} Auth={e['has_auth']} XCD={e['has_xcd']} XBV={e['has_xbv']}")
    
    # 6. Credits check pattern
    credits = [e for e in entries if '/credits' in e['url'] and 'aisandbox' in e['url']]
    print(f"\n--- Credits checks ({len(credits)}) ---")
    if credits:
        print(f"  First: {credits[0]['ts'][:19]}, Last: {credits[-1]['ts'][:19]}")
        # Credits intervals relative to submits/polls
        if submits:
            sub_ts = datetime.fromisoformat(submits[0]['ts'].replace('Z','+00:00'))
            before = sum(1 for c in credits if datetime.fromisoformat(c['ts'].replace('Z','+00:00')) < sub_ts)
            after = len(credits) - before
            print(f"  Before submit: {before}, After submit: {after}")
    
    # 7. Session refresh pattern
    sessions = [e for e in entries if e['domain'] == 'session']
    print(f"\n--- Session refreshes ({len(sessions)}) ---")
    
    # 8. TRPC calls
    trpc = [e for e in entries if e['domain'] == 'trpc']
    ack_calls = [e for e in trpc if 'fetchUserAck' in e['url']]
    print(f"\n--- TRPC ({len(trpc)} total, {len(ack_calls)} ack heartbeats) ---")
    
    # 9. batchLog telemetry
    batch_logs = [e for e in entries if ':batchLog' in e['url'] and 'Frontend' not in e['url'] and 'aisandbox' in e['url']]
    frontend_logs = [e for e in entries if 'batchLogFrontendEvents' in e['url']]
    print(f"\n--- Telemetry (batchLog={len(batch_logs)}, frontendEvents={len(frontend_logs)}) ---")
    
    # 10. PATCH calls
    patches = [e for e in entries if e['method'] == 'PATCH']
    print(f"\n--- PATCH workflow updates ({len(patches)}) ---")
    
    # 11. Error analysis
    errors = [e for e in entries if e['status'] >= 400 and e['domain'] != 'other']
    print(f"\n--- Errors ({len(errors)}) ---")
    for e in errors:
        print(f"  {e['ts'][:19]} {e['method']:5s} {e['short']:40s} S={e['status']} domain={e['domain']}")
    
    # 12. COMPLETE FLOW TIMELINE
    print(f"\n--- COMPLETE FLOW TIMELINE ---")
    key_events = []
    for e in entries:
        if e['domain'] in ('ga', 'other'): continue
        ev_type = ''
        if 'batchAsyncGenerate' in e['url'] and 'Upsample' not in e['url']: ev_type = 'SUBMIT'
        elif 'batchAsyncGenerate' in e['url'] and 'Upsample' in e['url']: ev_type = 'UPSCALE'
        elif 'batchCheck' in e['url']: ev_type = 'POLL'
        elif 'getMediaUrlRedirect' in e['url']: ev_type = 'REDIRECT'
        elif '/credits' in e['url'] and 'aisandbox' in e['url']: ev_type = 'CREDITS'
        elif ':batchLog' in e['url'] and 'Frontend' not in e['url']: ev_type = 'BATCH_LOG'
        elif 'batchLogFrontend' in e['url']: ev_type = 'FRONTEND_LOG'
        elif 'recaptcha' in e['url'] and 'reload' in e['url']: ev_type = 'RECAP_RELOAD'
        elif 'recaptcha' in e['url'] and 'clr' in e['url']: ev_type = 'RECAP_CLR'
        elif 'recaptcha' in e['url'] and 'anchor' in e['url']: ev_type = 'RECAP_ANCHOR'
        elif e['domain'] == 'session': ev_type = 'SESSION'
        elif 'fetchUserAck' in e['url']: ev_type = 'ACK'
        elif e['domain'] == 'trpc': ev_type = 'TRPC'
        elif 'flowWorkflows' in e['url'] and e['method'] == 'PATCH': ev_type = 'PATCH_WF'
        elif 'fetchUserRec' in e['url']: ev_type = 'FETCH_REC'
        elif 'checkAppAvail' in e['url']: ev_type = 'CHECK_APP'
        else: ev_type = f"{e['domain']}:{e['short'][:20]}"
        
        key_events.append((e['ts'][:19], ev_type, e['status'], e['has_auth'], e['has_xcd'], e['has_xbv']))
    
    # Print condensed timeline
    prev_type = ''
    repeat_count = 0
    for ts, ev, status, auth, xcd, xbv in key_events:
        if ev == prev_type and ev in ('POLL', 'SESSION', 'ACK', 'CREDITS'):
            repeat_count += 1
            continue
        if repeat_count > 0:
            print(f"    ... ({repeat_count} more {prev_type})")
            repeat_count = 0
        auth_s = 'A' if auth else '-'
        xcd_s = 'X' if xcd else '-'
        xbv_s = 'B' if xbv else '-'
        print(f"  {ts} {ev:20s} S={status} [{auth_s}{xcd_s}{xbv_s}]")
        prev_type = ev
    if repeat_count > 0:
        print(f"    ... ({repeat_count} more {prev_type})")

def analyze_curl_recaptcha(label, fname):
    """Extract reCAPTCHA token details from cURL."""
    path = os.path.join(BASE, fname)
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find submit commands with recaptcha tokens
    recap_matches = re.findall(r'"token":"([^"]{20,50})', content)
    print(f"\n--- {label}: reCAPTCHA tokens in submit ({len(recap_matches)}) ---")
    for i, t in enumerate(recap_matches):
        print(f"  Token {i+1}: {t}... (unique prefix)")
    
    # Check if tokens are unique
    if len(recap_matches) > 1:
        unique = len(set(recap_matches))
        print(f"  Unique tokens: {unique}/{len(recap_matches)} {'(ALL UNIQUE)' if unique == len(recap_matches) else '(REUSED!)'}")

# Main
print("FLOW LOGIC ANALYSIS")
print("=" * 80)

# Analyze each HAR
for label, fname in HARS:
    entries = parse_har(label, fname)
    if entries:
        analyze_session_flow(label, entries)

# Analyze cURL reCAPTCHA tokens
for label, fname in CURLS:
    analyze_curl_recaptcha(label, fname)
