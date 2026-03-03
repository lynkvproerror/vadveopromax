import json
from pathlib import Path

# Check profiles.json
cfg = Path(r"D:\NEW VEO PRO MAX\veo-pro-max\02 - CLIENT - VEO PRO MAX\config\profiles.json")
data = json.load(open(cfg, encoding="utf-8"))
profiles = data.get("profiles", [])
print(f"=== profiles.json: {len(profiles)} profiles ===")
for p in profiles:
    email = p.get("email", "?")
    bp = p.get("browser_profile_path", "?")
    bp_name = Path(bp).name if bp else "?"
    print(f"  {email} -> {bp_name}")

# Check actual browser_session folders
base = Path(r"D:\NEW VEO PRO MAX\veo-pro-max\02 - CLIENT - VEO PRO MAX\config\browser_profiles")
folders = sorted(base.glob("browser_session_*"))
print(f"\n=== Folders on disk: {len(folders)} ===")
mapped_paths = {Path(p.get("browser_profile_path","")).name for p in profiles if p.get("browser_profile_path")}
for f in folders:
    status = "MAPPED" if f.name in mapped_paths else "ORPHAN"
    pid_file = list(f.glob("chrome_*.pid"))
    pid_info = f" (PID file: {pid_file[0].name})" if pid_file else ""
    print(f"  {f.name}: {status}{pid_info}")
