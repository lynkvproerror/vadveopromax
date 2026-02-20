import json, re

with open(r"D:\NEW VEO PRO MAX\veo-pro-max\F12 Dev\New\image flow.har", "r", encoding="utf-8") as f:
    har = json.load(f)
entries = har["log"]["entries"]

models_found = set()
pattern = re.compile(r'"(imageModelName|modelNameType|imageModel)"\s*:\s*"([^"]+)"')

for i, e in enumerate(entries):
    # Check request body
    body = e["request"].get("postData", {}).get("text", "")
    if body:
        for m in pattern.finditer(body):
            val = m.group(2)
            if val not in models_found:
                print(f"  Entry {i} request: {m.group(1)}={val}")
                models_found.add(val)
    
    # Check response body  
    resp = e["response"].get("content", {}).get("text", "")
    if resp and len(resp) < 50000:  # skip huge base64 responses
        for m in pattern.finditer(resp):
            val = m.group(2)
            if val not in models_found:
                print(f"  Entry {i} response: {m.group(1)}={val}")
                models_found.add(val)

print(f"\nAll unique model values: {sorted(models_found)}")

# Also search for Nano, Imagen, Banana in any text
print("\n--- Searching for 'Nano', 'Imagen', 'Banana', 'imagen_4' ---")
for i, e in enumerate(entries):
    for source_name, text in [("req", e["request"].get("postData", {}).get("text", "")),
                               ("resp", e["response"].get("content", {}).get("text", ""))]:
        if not text or len(text) > 100000:
            continue
        lower = text.lower()
        for keyword in ["nano", "imagen_4", "banana", "imagen4"]:
            if keyword in lower:
                # Find context
                idx = lower.index(keyword)
                snippet = text[max(0,idx-40):idx+60]
                print(f"  Entry {i} {source_name}: ...{snippet}...")
                break
