"""Set Developer Mode in all existing Chrome profiles."""
import json, os
from pathlib import Path

base = Path(__file__).resolve().parent.parent / "config" / "browser_profiles"
for profile in base.glob("browser_session_*"):
    prefs_dir = profile / "Default"
    prefs_dir.mkdir(parents=True, exist_ok=True)
    prefs_file = prefs_dir / "Preferences"
    
    prefs = {}
    if prefs_file.exists():
        try:
            raw = prefs_file.read_text(encoding="utf-8")
            if raw.strip():
                prefs = json.loads(raw)
        except Exception:
            pass
    
    prefs.setdefault("extensions", {}).setdefault("ui", {})["developer_mode"] = True
    prefs_file.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    print(f"{profile.name}: developer_mode = True")

print("Done!")
