import re, json, sys, os

filepath = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\I2I\4.txt'
outpath = r'D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\F12 Dev\I2I\i2i_structure_output.txt'

with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

lines = content.split('\n')

out_lines = []

# Find where batchGenerateImages is
batch_lines = []
for i, line in enumerate(lines):
    if 'batchGenerateImages' in line:
        batch_lines.append(i)

out_lines.append(f'Found batchGenerateImages at lines (0-indexed): {batch_lines}')

# For each batchGenerateImages, find the data-raw
for idx, bl in enumerate(batch_lines):
    out_lines.append(f'\n=== batchGenerateImages #{idx+1} at line {bl+1} ===')
    out_lines.append(f'URL line: {lines[bl][:200]}')
    
    for j in range(bl, min(bl + 30, len(lines))):
        if '--data-raw' in lines[j]:
            line = lines[j].strip()
            
            # Extract payload
            if "--data-raw $'" in line:
                payload = line.split("--data-raw $'", 1)[1]
            elif "--data-raw '" in line:
                payload = line.split("--data-raw '", 1)[1]
            else:
                payload = line
            
            # Remove trailing
            if payload.endswith("' ;"):
                payload = payload[:-3]
            elif payload.endswith("';"):
                payload = payload[:-2]
            
            out_lines.append(f'Payload length: {len(payload)} chars')
            
            # Try to parse as JSON
            try:
                d = json.loads(payload)
                
                def show_structure(obj, prefix='', depth=0):
                    if depth > 5:
                        out_lines.append(f'{prefix}...')
                        return
                    if isinstance(obj, dict):
                        for key, val in obj.items():
                            if isinstance(val, str) and len(val) > 200:
                                out_lines.append(f'{prefix}{key}: "<string len={len(val)}>"')
                            elif isinstance(val, dict):
                                out_lines.append(f'{prefix}{key}: {{')
                                show_structure(val, prefix + '  ', depth+1)
                                out_lines.append(f'{prefix}}}')
                            elif isinstance(val, list):
                                out_lines.append(f'{prefix}{key}: [len={len(val)}]')
                                if val:
                                    for li, item in enumerate(val[:2]):
                                        if isinstance(item, dict):
                                            out_lines.append(f'{prefix}  [{li}]: {{')
                                            show_structure(item, prefix + '    ', depth+1)
                                            out_lines.append(f'{prefix}  }}')
                                        elif isinstance(item, str) and len(item) > 100:
                                            out_lines.append(f'{prefix}  [{li}]: "<string len={len(item)}>"')
                                        else:
                                            out_lines.append(f'{prefix}  [{li}]: {repr(item)}')
                                    if len(val) > 2:
                                        out_lines.append(f'{prefix}  ... ({len(val)-2} more)')
                            else:
                                out_lines.append(f'{prefix}{key}: {repr(val)}')
                    elif isinstance(obj, list):
                        out_lines.append(f'{prefix}[len={len(obj)}]')
                
                show_structure(d)
                
            except json.JSONDecodeError as e:
                out_lines.append(f'JSON parse error: {e}')
                # Manual key extraction
                keys = re.findall(r'"([a-zA-Z_][a-zA-Z0-9_]*?)":', payload[:3000])
                out_lines.append(f'Keys found in first 3000 chars: {keys}')
            break
    else:
        out_lines.append('No --data-raw found')

result = '\n'.join(out_lines)
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(result)

print(f'Output written to {outpath}')
print(f'Total lines: {len(out_lines)}')
