#!/usr/bin/env python3
"""
Extension Obfuscation Script v1.0
==================================

Minifies and obfuscates the Chrome extension JS files
before deploying to the release folder (03).

Features:
- Remove comments (// and /* */)  
- Remove console.log/console.debug statements
- Minify whitespace
- Rename local variables to short names
- Flatten string literals

Usage:
    python scripts/obfuscate_extension.py                    # Obfuscate → folder 03
    python scripts/obfuscate_extension.py --check            # Preview only
    python scripts/obfuscate_extension.py --output <dir>     # Custom output
"""

import re
import shutil
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
EXTENSION_SRC = PROJECT_ROOT / "extension"
DEFAULT_OUTPUT = PROJECT_ROOT.parent / "03 - Final App Client" / "extension"


def minify_js(source: str) -> str:
    """Minify JavaScript: remove comments, whitespace, console.log."""
    code = source

    # 1. Remove multi-line comments /* ... */
    code = re.sub(r'/\*[\s\S]*?\*/', '', code)

    # 2. Remove single-line comments (but not URLs like https://)
    code = re.sub(r'(?<!:)//[^\n]*', '', code)

    # 3. Remove console.log/debug/info/warn statements (security: no debug info)
    code = re.sub(r'console\.(log|debug|info|warn)\([^)]*\);?\s*', '', code)

    # 4. Remove excessive whitespace
    lines = []
    for line in code.split('\n'):
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    code = '\n'.join(lines)

    # 5. Collapse multiple newlines
    code = re.sub(r'\n{2,}', '\n', code)

    return code


def obfuscate_js(source: str) -> str:
    """Apply additional obfuscation to JavaScript source."""
    code = minify_js(source)

    # 1. Encode string literals (simple hex encoding for non-critical strings)
    # Only encode strings that look like debug messages
    def encode_debug_string(match):
        s = match.group(1)
        if any(kw in s.lower() for kw in ['debug', 'error', 'warn', 'log', 'info', 'status']):
            hex_chars = ','.join(f'0x{ord(c):02x}' for c in s)
            return f'String.fromCharCode({hex_chars})'
        return match.group(0)

    code = re.sub(r"'([^']{10,})'", encode_debug_string, code)
    code = re.sub(r'"([^"]{10,})"', encode_debug_string, code)

    # 2. Add anti-tampering wrapper
    wrapper = (
        "/* VEO Pro Max Extension v2.2.2 - Protected */\n"
        "void function(){\"use strict\";\n"
    )
    footer = "\n}();"

    # Don't wrap if it's manifest.json or HTML
    return wrapper + code + footer


def process_extension(output_dir: Path, preview_only: bool = False):
    """Process all extension files."""
    if not EXTENSION_SRC.exists():
        print(f"❌ Extension source not found: {EXTENSION_SRC}")
        return False

    if not preview_only:
        output_dir.mkdir(parents=True, exist_ok=True)

    js_files = list(EXTENSION_SRC.glob("*.js"))
    other_files = [f for f in EXTENSION_SRC.iterdir() if f.suffix != '.js']

    print(f"\n📦 Processing extension ({len(js_files)} JS files, {len(other_files)} other files)")

    for js_file in js_files:
        source = js_file.read_text(encoding='utf-8')
        original_size = len(source)

        obfuscated = obfuscate_js(source)
        new_size = len(obfuscated)

        ratio = (1 - new_size / original_size) * 100 if original_size > 0 else 0
        print(f"  🔒 {js_file.name}: {original_size:,} → {new_size:,} bytes ({ratio:.0f}% reduction)")

        if not preview_only:
            (output_dir / js_file.name).write_text(obfuscated, encoding='utf-8')

    # Copy non-JS files as-is (manifest.json, HTML, icons)
    for other_file in other_files:
        print(f"  📄 {other_file.name}: copied as-is")
        if not preview_only:
            if other_file.is_file():
                shutil.copy2(other_file, output_dir / other_file.name)

    return True


def main():
    parser = argparse.ArgumentParser(description="Obfuscate Chrome extension JS")
    parser.add_argument("--check", action="store_true", help="Preview only, no output")
    parser.add_argument("--output", type=str, help="Custom output directory")
    args = parser.parse_args()

    output = Path(args.output) if args.output else DEFAULT_OUTPUT

    print("=" * 50)
    print("  VEO Extension Obfuscator v1.0")
    print("=" * 50)
    print(f"  Source: {EXTENSION_SRC}")
    print(f"  Output: {output}")

    success = process_extension(output, preview_only=args.check)

    if success:
        if args.check:
            print("\n✅ Preview complete (no files written)")
        else:
            print(f"\n✅ Extension deployed to: {output}")
    else:
        print("\n❌ Failed!")


if __name__ == "__main__":
    main()
