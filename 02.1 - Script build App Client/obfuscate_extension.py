#!/usr/bin/env python3
"""
Extension Obfuscation Script v2.0
==================================

Minifies and obfuscates the Chrome extension JS files
before deploying to the release folder (03).

Features:
- Remove comments (// and /* */)  
- Remove console.log/console.debug statements (safe nested-paren handling)
- Minify whitespace
- Encode selected string literals (safe: only standalone strings, not inside templates)

Usage:
    python obfuscate_extension.py                    # Obfuscate → folder 03
    python obfuscate_extension.py --check            # Preview only
    python obfuscate_extension.py --output <dir>     # Custom output
"""

import re
import shutil
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent  # #NEW VEO API
PROJECT_ROOT = BASE_DIR / "02 - CLIENT - VEO PRO MAX"
EXTENSION_SRC = PROJECT_ROOT / "extension"
DEFAULT_OUTPUT = BASE_DIR / "03 - Final App Client" / "main.dist" / "extension"


def _remove_console_statements(code: str) -> str:
    """
    Safely remove console.log/debug/info/warn statements,
    handling nested parentheses correctly.
    """
    pattern = re.compile(r'console\.(log|debug|info|warn)\s*\(')
    result = []
    i = 0
    while i < len(code):
        m = pattern.search(code, i)
        if not m:
            result.append(code[i:])
            break
        
        # Append everything before the match
        result.append(code[i:m.start()])
        
        # Find matching closing paren (handle nesting)
        depth = 0
        j = m.end() - 1  # Position of the opening '('
        in_string = None
        escaped = False
        
        while j < len(code):
            ch = code[j]
            
            if escaped:
                escaped = False
                j += 1
                continue
            
            if ch == '\\':
                escaped = True
                j += 1
                continue
            
            if in_string:
                if ch == in_string:
                    in_string = None
            elif ch in ("'", '"', '`'):
                in_string = ch
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    # Skip past the closing paren and optional semicolon/whitespace
                    j += 1
                    while j < len(code) and code[j] in (' ', '\t'):
                        j += 1
                    if j < len(code) and code[j] == ';':
                        j += 1
                    # Also skip trailing newline
                    if j < len(code) and code[j] == '\r':
                        j += 1
                    if j < len(code) and code[j] == '\n':
                        j += 1
                    break
            j += 1
        
        i = j
    
    return ''.join(result)


def _remove_comments(code: str) -> str:
    """
    Remove JS comments (// and /* */) while respecting string literals.
    Does NOT remove // or /* that appear inside '...' or "..." or `...`.
    """
    result = []
    i = 0
    length = len(code)
    
    while i < length:
        ch = code[i]
        
        # Handle string literals — pass through without modification
        if ch in ("'", '"', '`'):
            quote = ch
            result.append(ch)
            i += 1
            while i < length:
                c = code[i]
                if c == '\\' and i + 1 < length:
                    result.append(c)
                    result.append(code[i + 1])
                    i += 2
                    continue
                result.append(c)
                i += 1
                if c == quote:
                    break
            continue
        
        # Handle multi-line comments /* ... */
        if ch == '/' and i + 1 < length and code[i + 1] == '*':
            # Skip until */
            j = code.find('*/', i + 2)
            if j != -1:
                i = j + 2
            else:
                i = length  # Unclosed comment, skip rest
            continue
        
        # Handle single-line comments // (but not URLs like https://)
        if ch == '/' and i + 1 < length and code[i + 1] == '/':
            # Check if preceded by ':' (URL protocol like https://)
            if i > 0 and code[i - 1] == ':':
                result.append(ch)
                i += 1
                continue
            # Skip until end of line
            while i < length and code[i] != '\n':
                i += 1
            continue
        
        result.append(ch)
        i += 1
    
    return ''.join(result)


def minify_js(source: str) -> str:
    """Minify JavaScript: remove comments, whitespace, console.log."""
    code = source

    # 1. Remove comments (string-aware — won't touch /* inside strings)
    code = _remove_comments(code)

    # 2. Remove console.log/debug/info/warn statements (safe paren matching)
    code = _remove_console_statements(code)

    # 3. Remove excessive whitespace
    lines = []
    for line in code.split('\n'):
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    code = '\n'.join(lines)

    # 4. Collapse multiple newlines
    code = re.sub(r'\n{2,}', '\n', code)

    return code


def obfuscate_js(source: str, filename: str = "") -> str:
    """Apply additional obfuscation to JavaScript source."""
    code = minify_js(source)

    # 1. Encode ONLY standalone debug/sensitive strings
    #    Safe: only match strings that are a complete value (after : or = or , or ()
    #    Skip strings inside template literals or complex expressions
    SENSITIVE_KEYWORDS = ['debug', 'error', 'warn', 'log ', 'info', 'status',
                          'tab_logout', 'login_redirect', 'email_not_found']
    
    def encode_debug_string(match):
        quote = match.group(0)[0]  # ' or "
        s = match.group(1)
        # Only encode if it contains sensitive keywords
        if any(kw in s.lower() for kw in SENSITIVE_KEYWORDS):
            # Don't encode if it looks like a URL, CSS selector, or object key pattern
            if s.startswith('http') or s.startswith('.') or s.startswith('#'):
                return match.group(0)
            # Don't encode if it contains template syntax or complex chars
            if '${' in s or '\\n' in s or '{' in s or '}' in s:
                return match.group(0)
            hex_chars = ','.join(f'0x{ord(c):02x}' for c in s)
            return f'String.fromCharCode({hex_chars})'
        return match.group(0)

    # Only match complete string values (preceded by : ,  = ( or start of line)
    # This avoids breaking object literals and template strings
    code = re.sub(r"(?<=[:,=(\s])'([^']{10,80})'", encode_debug_string, code)
    
    # 2. Add header comment only (no IIFE wrapper — files already have their own structure)
    header = "/* VEO Pro Max Extension v2.2.2 - Protected */\n"
    
    return header + code


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

        obfuscated = obfuscate_js(source, filename=js_file.name)
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
    print("  VEO Extension Obfuscator v2.0")
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
