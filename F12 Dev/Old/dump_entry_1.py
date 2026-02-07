import json

file_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\Check trạng thái tài khoản Ultra hay Pro haay Thuong.har"
output_path = r"D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\F12 Dev\entry_1_regular.json"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    entry = har_data['log']['entries'][1]
    text = entry['response']['content'].get('text', '')
    
    with open(output_path, 'w', encoding='utf-8') as out:
        out.write(text)
        
    print(f"Dumped Entry 1 to {output_path}")

except Exception as e:
    print(f"Error: {e}")
