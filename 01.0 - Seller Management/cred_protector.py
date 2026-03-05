"""
Credential Protector — Encrypt/Decrypt Firebase credential JSON files
=====================================================================
ADMIN TOOL: Run once to encrypt credentials before distributing seller app.

Usage:
    python cred_protector.py encrypt   → Encrypt all .json credentials → .veo.enc files
    python cred_protector.py decrypt   → Decrypt .veo.enc back (admin only, for debugging)
    
Seller app loads .veo.enc files via secure_firebase_config.py at runtime.
The encryption key is derived from machine-independent app signature.
"""

import os
import sys
import json
import hashlib
import hmac
import base64
from pathlib import Path
from typing import Optional


# App signature — derived from multiple sources, NOT a single string
def _derive_app_key() -> bytes:
    """
    Derive encryption key from multiple app-level signals.
    NOT machine-specific — same key across all seller installations.
    Changed per version to invalidate old encrypted credentials.
    """
    components = [
        b"VEO_CRED_PROTECT_v2",          # Version marker
        b"2026_seller_management",         # App identifier
        hashlib.sha256(b"credential_layer_2").digest()[:8],  # Extra entropy
    ]
    combined = b"|".join(components)
    return hmac.new(b"veo_cred_wrap", combined, hashlib.sha256).digest()


def encrypt_credential(json_path: Path, output_path: Path = None) -> bool:
    """Encrypt a Firebase credential JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        key = _derive_app_key()
        data = content.encode('utf-8')
        
        # XOR encrypt with derived key (repeating)
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        
        # Add HMAC for integrity
        sig = hmac.new(key, encrypted, hashlib.sha256).hexdigest()[:16]
        
        output = output_path or json_path.with_suffix('.veo.enc')
        with open(output, 'w', encoding='utf-8') as f:
            f.write(f"{sig}\n{base64.b64encode(encrypted).decode()}")
        
        print(f"✅ Encrypted: {json_path.name} → {output.name}")
        return True
    except Exception as e:
        print(f"❌ Failed: {json_path.name}: {e}")
        return False


def decrypt_credential(enc_path: Path) -> Optional[dict]:
    """Decrypt a .veo.enc credential file. Returns parsed JSON dict."""
    try:
        with open(enc_path, 'r', encoding='utf-8') as f:
            lines = f.read().strip().split('\n', 1)
        
        if len(lines) != 2:
            return None
        
        stored_sig, b64_data = lines
        encrypted = base64.b64decode(b64_data)
        key = _derive_app_key()
        
        # Verify integrity
        expected_sig = hmac.new(key, encrypted, hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(stored_sig, expected_sig):
            return None  # Tampered
        
        # Decrypt
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(encrypted))
        return json.loads(decrypted.decode('utf-8'))
    except Exception:
        return None


def encrypt_all_in_dir(directory: Path = None):
    """Encrypt all Firebase credential JSONs in directory."""
    directory = directory or Path(__file__).parent
    count = 0
    for json_file in directory.rglob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if all(k in data for k in ["type", "project_id", "private_key", "client_email"]):
                if encrypt_credential(json_file):
                    count += 1
        except Exception:
            continue
    print(f"\n{'='*40}")
    print(f"Encrypted {count} credential file(s)")
    print(f"You can now DELETE the original .json files from seller app folder.")
    print(f"Seller app will load .veo.enc files automatically.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "encrypt"
    
    if cmd == "encrypt":
        print("🔒 Encrypting Firebase credentials...")
        encrypt_all_in_dir()
    elif cmd == "decrypt":
        print("🔓 Decrypting (admin debug)...")
        for enc_file in Path(__file__).parent.rglob("*.veo.enc"):
            result = decrypt_credential(enc_file)
            if result:
                print(f"✅ {enc_file.name}: project={result.get('project_id')}")
            else:
                print(f"❌ {enc_file.name}: FAILED (tampered?)")
    else:
        print("Usage: python cred_protector.py [encrypt|decrypt]")
