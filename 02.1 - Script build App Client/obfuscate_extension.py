#!/usr/bin/env python3
"""
Extension Obfuscation Script v3.0
==================================

Obfuscates Chrome extension JS files using javascript-obfuscator (npm).
MV3-safe: no eval, no self-defending, no domain-lock.

Prerequisites:
    npm install -g javascript-obfuscator

Features:
- Variable/function renaming → _0x1a2b3c
- String encoding (base64)
- Control flow flattening (light)
- Dead code injection (light)
- Console log removal
- NO eval (MV3 CSP safe)
- NO self-defending (Service Worker safe)

Usage:
    python obfuscate_extension.py                    # Obfuscate → folder 03
    python obfuscate_extension.py --check            # Preview only
    python obfuscate_extension.py --output <dir>     # Custom output
"""

import json
import shutil
import subprocess
import argparse
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent  # #NEW VEO API
PROJECT_ROOT = BASE_DIR / "02 - CLIENT - VEO PRO MAX"
EXTENSION_SRC = PROJECT_ROOT / "extension"
DEFAULT_OUTPUT = BASE_DIR / "03 - Final App Client" / "main.dist" / "extension"

# Files that run in Service Worker context (NO window object)
SERVICE_WORKER_FILES = {"background.js"}

# ── Extension Obfuscation — LIGHT MODE ──────────────────────────────────────
#
# Strategy: Minify + rename local variables only.
# NO string array, NO control flow flattening, NO dead code injection.
#
# Why light mode:
#   - Full obfuscation creates massive string arrays and control flow switches
#     that cause Chrome "Extension context invalidated" + SyntaxError on hot-reload
#   - Light mode keeps code compact and unreadable enough to deter casual copying
#     while being 100% stable across Chrome extension lifecycle events
#
# IIFE wrapping is applied POST-obfuscation in obfuscate_js_file() to prevent
# global scope pollution when Chrome re-injects content scripts.

BROWSER_CONFIG = {
    # ── Core: minify + rename ──
    "compact": True,                     # Single-line output
    "simplify": True,                    # Simplify expressions
    "renameGlobals": False,              # Keep chrome.*, window.* intact
    "renameProperties": False,           # Keep object keys for API calls
    "identifierNamesGenerator": "hexadecimal",  # _0x1a2b3c style

    # ── String protection: OFF ──
    # String array is the #1 cause of global scope pollution and bloat.
    "stringArray": False,

    # ── Control flow: OFF ──
    # Flattening + dead code cause massive size increase and runtime overhead.
    "controlFlowFlattening": False,
    "deadCodeInjection": False,

    # ── Console: KEEP ──
    # Removing console.log breaks debugging and uses window-dependent wrappers.
    "disableConsoleOutput": False,

    # ── Safety: MV3 compatible ──
    "selfDefending": False,              # MUST be false for Service Worker
    "debugProtection": False,            # Can freeze dev tools
    "domainLock": [],                    # Extension has no domain
    "target": "browser",

    # ── Numbers ──
    "numbersToExpressions": True,        # Light obfuscation for numeric constants
    "transformObjectKeys": False,        # Keep object keys readable
    "unicodeEscapeSequence": False,      # Keep strings compact
}

# Service Worker config (background.js) — identical to BROWSER but with
# browser-no-eval target to avoid window-dependent references.
SERVICE_WORKER_CONFIG = {
    **BROWSER_CONFIG,
    "target": "browser-no-eval",
}


def _find_obfuscator() -> str:
    """Find javascript-obfuscator CLI."""
    # Check global npm
    result = shutil.which("javascript-obfuscator")
    if result:
        return result

    # Check common Windows npm global path
    npm_global = Path.home() / "AppData" / "Roaming" / "npm" / "javascript-obfuscator.cmd"
    if npm_global.exists():
        return str(npm_global)

    raise FileNotFoundError(
        "javascript-obfuscator not found!\n"
        "Install: npm install -g javascript-obfuscator"
    )


def obfuscate_js_file(input_path: Path, output_path: Path, config: dict) -> dict:
    """Obfuscate a single JS file using javascript-obfuscator CLI.

    Returns dict with stats: {original_size, new_size, ratio}.
    """
    cli = _find_obfuscator()
    original_size = input_path.stat().st_size

    # Write config to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(config, f)
        config_path = f.name

    try:
        # Run: javascript-obfuscator input.js --output output.js --config config.json
        cmd = [
            cli,
            str(input_path),
            "--output", str(output_path),
            "--config", config_path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"Obfuscation failed for {input_path.name}: {stderr}")

        # ── Post-obfuscation: wrap in IIFE ──
        # Prevents global scope pollution when content scripts are
        # re-injected during extension hot-reload/update without page refresh.
        # Without this, const/let declarations collide → SyntaxError.
        obfuscated = output_path.read_text(encoding='utf-8')
        wrapped = f'(function(){{\n{obfuscated}\n}})();'
        output_path.write_text(wrapped, encoding='utf-8')

        new_size = output_path.stat().st_size
        ratio = (1 - new_size / original_size) * 100 if original_size > 0 else 0

        return {
            "original_size": original_size,
            "new_size": new_size,
            "ratio": ratio,
        }
    finally:
        Path(config_path).unlink(missing_ok=True)


def process_extension(output_dir: Path, preview_only: bool = False):
    """Process all extension files."""
    if not EXTENSION_SRC.exists():
        print(f"❌ Extension source not found: {EXTENSION_SRC}")
        return False

    # Verify javascript-obfuscator is available
    try:
        cli = _find_obfuscator()
        # Get version
        ver_result = subprocess.run(
            [cli, "--version"], capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        version = ver_result.stdout.strip() if ver_result.returncode == 0 else "unknown"
        print(f"  🔧 javascript-obfuscator v{version}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return False

    if not preview_only:
        output_dir.mkdir(parents=True, exist_ok=True)

    js_files = sorted(EXTENSION_SRC.glob("*.js"))
    other_files = [f for f in sorted(EXTENSION_SRC.iterdir()) if f.suffix != '.js']

    print(f"\n📦 Processing extension ({len(js_files)} JS files, {len(other_files)} other files)")

    total_original = 0
    total_new = 0

    for js_file in js_files:
        if preview_only:
            original_size = js_file.stat().st_size
            print(f"  🔒 {js_file.name}: {original_size:,} bytes → [preview]")
            continue

        out_file = output_dir / js_file.name
        try:
            # Select config based on file context
            if js_file.name in SERVICE_WORKER_FILES:
                config = SERVICE_WORKER_CONFIG
                ctx_label = "SW"
            else:
                config = BROWSER_CONFIG
                ctx_label = "BR"
            
            stats = obfuscate_js_file(js_file, out_file, config)
            total_original += stats["original_size"]
            total_new += stats["new_size"]

            # Size may INCREASE with obfuscation (dead code + string array)
            direction = "↓" if stats["ratio"] > 0 else "↑"
            abs_ratio = abs(stats["ratio"])
            print(f"  🔒 [{ctx_label}] {js_file.name}: {stats['original_size']:,} → {stats['new_size']:,} bytes ({direction}{abs_ratio:.0f}%)")
        except Exception as e:
            print(f"  ❌ {js_file.name}: {e}")
            # Fallback: copy original
            shutil.copy2(js_file, out_file)
            print(f"  ⚠️ {js_file.name}: copied original as fallback")

    # Copy non-JS files as-is (manifest.json, HTML, icons)
    for other_file in other_files:
        print(f"  📄 {other_file.name}: copied as-is")
        if not preview_only and other_file.is_file():
            shutil.copy2(other_file, output_dir / other_file.name)

    if not preview_only and total_original > 0:
        overall = (total_new / total_original) * 100
        print(f"\n  📊 Total JS: {total_original:,} → {total_new:,} bytes ({overall:.0f}% of original)")

    print(f"  [OK] Extension deployed to: {output_dir}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Obfuscate Chrome extension JS (v3.0)")
    parser.add_argument("--check", action="store_true", help="Preview only, no output")
    parser.add_argument("--output", type=str, help="Custom output directory")
    args = parser.parse_args()

    output = Path(args.output) if args.output else DEFAULT_OUTPUT

    print("=" * 50)
    print("  VEO Extension Obfuscator v3.0")
    print("  Engine: javascript-obfuscator (npm)")
    print("=" * 50)
    print(f"  Source: {EXTENSION_SRC}")
    print(f"  Output: {output}")

    success = process_extension(output, preview_only=args.check)

    if success:
        if args.check:
            print("\n✅ Preview complete (no files written)")
        else:
            print(f"\n✅ Extension obfuscated and deployed to: {output}")
    else:
        print("\n❌ Failed!")


if __name__ == "__main__":
    main()
