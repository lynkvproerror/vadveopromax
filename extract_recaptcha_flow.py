import json

har_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\New\01. ingedients to video hoan thanh 4 video prompt 3 anh.har"

try:
    with open(har_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    reload_response_token = None
    
    with open("recaptcha_flow_details.txt", "w", encoding="utf-8") as out:
        for entry in har_data['log']['entries']:
            request = entry['request']
            url = request['url']
            
            # 1. Find the Recaptcha Reload Call and its Response
            if "recaptcha/enterprise/reload" in url and request['method'] == "POST":
                out.write(f"--- 1. Found Recaptcha Reload Request ---\n")
                out.write(f"URL: {url}\n")
                
                response = entry['response']
                content = response['content']
                if 'text' in content:
                    resp_text = content['text']
                    out.write(f"Response Body (First 200 chars): {resp_text[:200]}...\n")
                    # Try to extract something that looks like the token to verify
                    # The response is usually like: ")]}'\n[\"rresp\",\"03AFcWeA...\"]"
                    # We just log it for visual confirmation now.
                else:
                     out.write("Response Body: [No Text Content]\n")
                out.write("\n")

            # 2. Find the Generate Call and its Payload
            if "batchAsyncGenerateVideoReferenceImages" in url and request['method'] == "POST":
                out.write(f"--- 2. Found Video Generation Request ---\n")
                out.write(f"URL: {url}\n")
                if 'postData' in request:
                     payload = request['postData']['text']
                     out.write(f"Payload (First 500 chars): {payload[:500]}...\n")
                     # Check if we can find the token format
                out.write("\n")

except Exception as e:
    with open("recaptcha_flow_details.txt", "w", encoding="utf-8") as out:
        out.write(f"Error: {e}\n")
