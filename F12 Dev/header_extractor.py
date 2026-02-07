"""
Extract x-browser-* headers from HAR files
"""
import json
import os
import glob

def extract_headers():
    base_dir = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev"
    files = []
    files.extend(glob.glob(os.path.join(base_dir, "New", "*.har")))
    files.extend(glob.glob(os.path.join(base_dir, "Old", "*.har")))
    
    browser_headers = {}
    
    for f_path in files:
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries = data.get('log', {}).get('entries', [])
            for entry in entries:
                req = entry.get('request', {})
                url = req.get('url', '')
                
                if 'googleapis.com' not in url:
                    continue
                
                for h in req.get('headers', []):
                    name = h['name'].lower()
                    if name.startswith('x-browser') or name == 'x-client-data':
                        if name not in browser_headers:
                            browser_headers[name] = []
                        val = h['value']
                        if val not in browser_headers[name] and len(val) < 200:
                            browser_headers[name].append(val)
        except:
            pass

    output = []
    output.append("# Browser Headers Extraction\n")
    for name, values in sorted(browser_headers.items()):
        output.append(f"\n## `{name}`\n")
        output.append(f"Found {len(values)} unique values:\n")
        for v in values[:5]:  # Limit to 5 samples
            output.append(f"- `{v}`\n")
    
    with open("browser_headers_dump.md", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    
    print("Headers extracted to browser_headers_dump.md")

if __name__ == "__main__":
    extract_headers()
