import json
import requests

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\01. ingedients to video hoan thanh 4 video prompt 3 anh.har"

print(f"Opening HAR file: {file_path}")
try:
    with open(file_path, "r", encoding="utf-8") as f:
        har_data = json.load(f)

    entries = har_data['log']['entries']
    print(f"Processing {len(entries)} entries...")

    with open("har_analysis.txt", "w", encoding="utf-8") as out:
        for entry in entries:
            req = entry['request']
            url = req['url']
            method = req['method']
            
            if method == "POST":
                out.write(f"{method} {url}\n")
                
                # Check for sensitive headers if it's the aisandbox endpoint
                if "aisandbox-pa" in url:
                     out.write("Headers:\n")
                     for h in req['headers']:
                         out.write(f"  {h['name']}: {h['value'][:100]}...\n")

                if "postData" in req and "text" in req["postData"]:
                    out.write(f"Payload: {req['postData']['text'][:500]}...\n")
                out.write("-" * 20 + "\n")

    print("Analysis complete. Saved to har_analysis.txt")

except Exception as e:
    print(f"Error parsing HAR: {e}")
