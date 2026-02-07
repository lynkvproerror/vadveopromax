"""HAR Analysis Script for VEO API Documentation Audit"""
import json
import os
from collections import defaultdict
from pathlib import Path

def analyze_har_file(har_path):
    """Analyze a single HAR file and extract API details"""
    with open(har_path, 'r', encoding='utf-8') as f:
        har = json.load(f)
    
    entries = har['log']['entries']
    api_calls = []
    
    for entry in entries:
        url = entry['request']['url']
        method = entry['request']['method']
        status = entry['response']['status']
        
        # Filter relevant Google/VEO APIs
        if any(x in url for x in ['aisandbox', 'generativelanguage', 'googleapis.com/v1', 'firebaseapp', 'vertexai', 'labs.google']):
            # Extract request body if POST
            req_body = None
            if method == 'POST' and entry['request'].get('postData'):
                try:
                    req_body = entry['request']['postData'].get('text', '')[:500]
                except:
                    pass
            
            # Extract response body
            resp_body = None
            if entry['response'].get('content', {}).get('text'):
                resp_body = entry['response']['content']['text'][:500]
            
            # Extract endpoint
            endpoint = url.split('?')[0]
            if 'googleapis.com' in endpoint:
                endpoint = endpoint.split('googleapis.com')[1]
            
            api_calls.append({
                'method': method,
                'status': status,
                'endpoint': endpoint,
                'url': url[:200],
                'req_body': req_body,
                'resp_body': resp_body
            })
    
    return api_calls

def analyze_directory(har_dir, output_file):
    """Analyze all HAR files in a directory"""
    results = {}
    
    for filename in sorted(os.listdir(har_dir)):
        if filename.endswith('.har'):
            har_path = os.path.join(har_dir, filename)
            try:
                api_calls = analyze_har_file(har_path)
                results[filename] = api_calls
                print(f"Parsed: {filename} - {len(api_calls)} API calls")
            except Exception as e:
                results[filename] = [{'error': str(e)}]
                print(f"Error parsing {filename}: {e}")
    
    # Write results to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    return results

def generate_report(results, output_md):
    """Generate markdown report from analysis results"""
    report = ["# HAR Analysis Report\n\n"]
    
    # Summary
    total_files = len(results)
    total_calls = sum(len(calls) for calls in results.values())
    report.append(f"**Total Files:** {total_files}\n")
    report.append(f"**Total API Calls:** {total_calls}\n\n")
    
    # Collect all unique endpoints
    all_endpoints = defaultdict(list)
    for filename, calls in results.items():
        for call in calls:
            if isinstance(call, dict) and 'endpoint' in call:
                ep_key = f"{call['method']} {call['endpoint']}"
                all_endpoints[ep_key].append({
                    'file': filename,
                    'status': call['status'],
                    'req_sample': call.get('req_body', '')[:200] if call.get('req_body') else None
                })
    
    report.append("## Unique API Endpoints\n\n")
    report.append("| Method | Endpoint | Count | Status Codes |\n")
    report.append("|--------|----------|-------|-------------|\n")
    
    for ep_key in sorted(all_endpoints.keys()):
        occurrences = all_endpoints[ep_key]
        method, endpoint = ep_key.split(' ', 1)
        statuses = set(o['status'] for o in occurrences)
        report.append(f"| {method} | `{endpoint[:60]}` | {len(occurrences)} | {', '.join(map(str, statuses))} |\n")
    
    report.append("\n## Per-File Details\n\n")
    
    for filename, calls in sorted(results.items()):
        report.append(f"### {filename}\n\n")
        report.append(f"API Calls: {len(calls)}\n\n")
        
        if calls and isinstance(calls[0], dict) and 'endpoint' in calls[0]:
            ep_counts = defaultdict(int)
            for call in calls:
                ep_counts[f"{call['method']} {call['status']} {call['endpoint'][:50]}"] += 1
            
            for ep, count in sorted(ep_counts.items(), key=lambda x: -x[1])[:10]:
                report.append(f"- `{ep}`" + (f" (x{count})" if count > 1 else "") + "\n")
        report.append("\n")
    
    with open(output_md, 'w', encoding='utf-8') as f:
        f.writelines(report)
    
    return ''.join(report)

if __name__ == '__main__':
    import sys
    har_dir = sys.argv[1] if len(sys.argv) > 1 else r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else r'.'
    
    print(f"=== Analyzing HAR Files in {har_dir} ===")
    results = analyze_directory(har_dir, os.path.join(output_dir, 'har_raw.json'))
    generate_report(results, os.path.join(output_dir, 'HAR_ANALYSIS.md'))
    print(f"\nDone! Check HAR_ANALYSIS.md")
