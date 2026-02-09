import json
import urllib.parse

har_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\01. ingedients to video hoan thanh 4 video prompt 3 anh.har"
target_key = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

try:
    with open(har_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    with open("key_origin_analysis.txt", "w", encoding="utf-8") as out:
        # 1. Search for Key in Responses
        out.write(f"--- Searching for Key: {target_key} in Responses ---\n")
        found = False
        for entry in har_data['log']['entries']:
            resp = entry['response']
            url = entry['request']['url']
            
            # Skip the reload request itself, we want to find WHERE it came from
            if "recaptcha/enterprise/reload" in url:
                continue

            if 'content' in resp and 'text' in resp['content']:
                content = resp['content']['text']
                if target_key in content:
                    out.write(f"FOUND in Response from: {url}\n")
                    out.write(f"MimeType: {resp['content']['mimeType']}\n")
                    # Context snippet
                    idx = content.find(target_key)
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 100)
                    out.write(f"Context: ...{content[start:end]}...\n\n")
                    found = True
        
        if not found:
            out.write("Key NOT found in any response body (might be in initial HTML not in this HAR or generated?).\n\n")

        # 2. Analyze Reload Parameters
        out.write("--- Analyzing Recaptcha Reload Parameters ---\n")
        for entry in har_data['log']['entries']:
            request = entry['request']
            url = request['url']
            if "recaptcha/enterprise/reload" in url and request['method'] == "POST":
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                out.write(f"Full URL: {url}\n")
                out.write("Query Parameters:\n")
                for k, v in params.items():
                    out.write(f"  {k}: {v[0]}\n")
                
                # Check for post data just in case
                if 'postData' in request:
                     out.write("Post Data (Payload):\n")
                     out.write(f"{request['postData']['text'][:500]}\n")
                break

except Exception as e:
    with open("key_origin_analysis.txt", "w", encoding="utf-8") as out:
        out.write(f"Error: {e}\n")
