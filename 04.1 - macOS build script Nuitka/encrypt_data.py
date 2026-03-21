#!/usr/bin/env python3
"""
VEO Pro Max — Workflow Data Encryptor (Build Tool) — macOS Version
===================================================================

Encrypts all .md files in a target directory to .enc using Fernet (AES-128-CBC).
Deletes original .md files after successful encryption.

Usage (standalone):
    python encrypt_data.py <target_dir>
    python encrypt_data.py "/path/to/VEO_Pro_Max.app/Contents/Resources/data"

Usage (from build_release_macos.py):
    from encrypt_data import encrypt_directory
    encrypt_directory(Path("04.2 - macOS final build/VEO_Pro_Max.app/Contents/Resources/data"))

Key derivation: PBKDF2-HMAC-SHA256 with fixed salt (not machine-bound,
so all builds produce the same key regardless of build machine).
Nuitka compiles the key derivation logic into native code, hiding it
from simple string extraction.

NOTE: Key MUST match core/data_loader.py in 04 - MAC/
"""

import hashlib
import base64
import sys
from pathlib import Path

# ── Key Derivation ──────────────────────────────────────────────
# Fixed components (hidden in compiled binary by Nuitka):
_SALT = b"veo_pro_max_workflow_data_v1"
_PASSPHRASE = b"VPM_2026_AES_workflow_enc_key_!@#"
_ITERATIONS = 200_000


def _derive_key() -> bytes:
    """Derive Fernet key from passphrase + salt via PBKDF2."""
    raw = hashlib.pbkdf2_hmac("sha256", _PASSPHRASE, _SALT, _ITERATIONS)
    return base64.urlsafe_b64encode(raw)


def _get_fernet():
    """Get Fernet cipher instance."""
    from cryptography.fernet import Fernet
    return Fernet(_derive_key())


def encrypt_file(src: Path, dst: Path) -> int:
    """Encrypt a single file. Returns encrypted size in bytes."""
    plaintext = src.read_bytes()
    ciphertext = _get_fernet().encrypt(plaintext)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(ciphertext)
    return len(ciphertext)


def encrypt_directory(target_dir: Path) -> int:
    """Encrypt all .md files in target_dir (recursively).
    
    Replaces each .md with .enc and deletes the original .md.
    
    Args:
        target_dir: Directory to process (e.g., .app/Contents/Resources/data/)
    
    Returns:
        Number of files encrypted.
    """
    if not target_dir.exists():
        print(f"  [WARN] Target directory not found: {target_dir}")
        return 0
    
    fernet = _get_fernet()
    encrypted_count = 0
    total_bytes = 0
    
    for md_file in sorted(target_dir.rglob("*.md")):
        try:
            # Read plaintext
            plaintext = md_file.read_bytes()
            
            # Encrypt
            ciphertext = fernet.encrypt(plaintext)
            
            # Write .enc (same path, different extension)
            enc_file = md_file.with_suffix(".enc")
            enc_file.write_bytes(ciphertext)
            
            # Delete original .md
            md_file.unlink()
            
            encrypted_count += 1
            total_bytes += len(ciphertext)
            rel = md_file.relative_to(target_dir)
            print(f"  [ENC] {rel} → {rel.with_suffix('.enc')} ({len(plaintext)} → {len(ciphertext)} bytes)")
            
        except Exception as e:
            print(f"  [ERR] Failed to encrypt {md_file}: {e}")
    
    print(f"\n  [DONE] Encrypted {encrypted_count} files ({total_bytes / 1024:.1f} KB total)")
    return encrypted_count


# ── CLI Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python encrypt_data.py <target_dir>")
        print('Example: python encrypt_data.py "../04.2 - macOS final build/VEO_Pro_Max.app/Contents/Resources/data"')
        sys.exit(1)
    
    target = Path(sys.argv[1])
    if not target.exists():
        print(f"Error: {target} does not exist")
        sys.exit(1)
    
    print(f"Encrypting .md files in: {target}")
    count = encrypt_directory(target)
    
    # Verify: no .md files should remain
    remaining = list(target.rglob("*.md"))
    if remaining:
        print(f"\n[WARN] {len(remaining)} .md files still remain!")
        for f in remaining:
            print(f"  - {f.relative_to(target)}")
    else:
        print(f"\n[OK] All .md files encrypted. 0 plaintext files remain.")
