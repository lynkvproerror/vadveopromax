import json

har_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\0. Tao Project.har"

try:
    with open(har_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    with open("project_create_details.txt", "w", encoding="utf-8") as out:
        for entry in har_data['log']['entries']:
            request = entry['request']
            url = request['url']
            if "project.createProject" in url:
                out.write(f"Found Request: {url}\n")
                out.write(f"Method: {request['method']}\n")
                out.write("Headers:\n")
                for h in request['headers']:
                    out.write(f"  {h['name']}: {h['value']}\n")
                
                if 'postData' in request:
                    out.write("Payload:\n")
                    out.write(request['postData']['text'] + "\n")
                else:
                    out.write("No Payload\n")
                break
        else:
            out.write("Request not found.\n")

except Exception as e:
    with open("project_create_details.txt", "w", encoding="utf-8") as out:
        out.write(f"Error: {e}\n")
