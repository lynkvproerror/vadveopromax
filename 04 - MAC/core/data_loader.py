"""
VEO Pro Max — Data Loader (Runtime Decryptor)
=============================================

Transparent data file loader that supports both:
- Encrypted .enc files (production/compiled mode)
- Plaintext .md files (dev mode)

Usage:
    from core.data_loader import load_text, scan_data_files

    # Read a single file (auto-detects .enc or .md)
    content = load_text(Path("data/workflows/content-video.md"))

    # Scan directory for data files (.enc in production, .md in dev)
    files = scan_data_files(Path("data/workflows"), recursive=True)

Key principle: NEVER writes decrypted content to disk.
"""

import hashlib
import base64
import logging
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

# ── Key Derivation (must match encrypt_data.py) ──────────────────
_SALT = b"veo_pro_max_workflow_data_v1"
_PASSPHRASE = b"VPM_2026_AES_workflow_enc_key_!@#"
_ITERATIONS = 200_000

_fernet_instance = None


def _derive_key() -> bytes:
    """Derive Fernet key from passphrase + salt via PBKDF2."""
    raw = hashlib.pbkdf2_hmac("sha256", _PASSPHRASE, _SALT, _ITERATIONS)
    return base64.urlsafe_b64encode(raw)


def _get_fernet():
    """Get cached Fernet cipher instance (lazy init)."""
    global _fernet_instance
    if _fernet_instance is None:
        try:
            from cryptography.fernet import Fernet
            _fernet_instance = Fernet(_derive_key())
        except ImportError:
            log.warning("[DataLoader] cryptography not installed — .enc files cannot be decrypted")
            return None
    return _fernet_instance


def _decrypt_file(enc_path: Path) -> str:
    """Decrypt an .enc file and return content as string. Never writes to disk."""
    fernet = _get_fernet()
    if fernet is None:
        raise RuntimeError("cryptography library not available for decryption")
    
    ciphertext = enc_path.read_bytes()
    plaintext = fernet.decrypt(ciphertext)
    return plaintext.decode("utf-8", errors="ignore")


# ── Public API ───────────────────────────────────────────────────

def load_text(path: Path) -> str:
    """Load text content from a data file (transparent .enc/.md support).
    
    Priority:
    1. If path points to a .enc file → decrypt it
    2. If .enc sibling exists for a .md path → decrypt .enc
    3. If .md file exists → read plaintext (dev mode)
    4. Raise FileNotFoundError
    
    Args:
        path: Path to the data file (.md or .enc)
    
    Returns:
        File content as string (decrypted if .enc)
    """
    # Case 1: path is already .enc
    if path.suffix == ".enc" and path.exists():
        return _decrypt_file(path)
    
    # Case 2: path is .md but .enc sibling exists (production)
    enc_path = path.with_suffix(".enc")
    if enc_path.exists():
        return _decrypt_file(enc_path)
    
    # Case 3: .md exists (dev mode)
    if path.exists():
        return path.read_text(encoding="utf-8", errors="ignore")
    
    # Case 4: try .md if path was given without extension
    md_path = path.with_suffix(".md")
    if md_path.exists():
        return md_path.read_text(encoding="utf-8", errors="ignore")
    
    raise FileNotFoundError(f"Data file not found: {path} (tried .enc and .md)")


def scan_data_files(directory: Path, recursive: bool = True) -> List[Path]:
    """Scan directory for data files (.enc preferred, .md fallback).
    
    In production: finds .enc files
    In dev: finds .md files
    If both exist for same stem: prefers .enc
    
    Args:
        directory: Directory to scan
        recursive: If True, scan subdirectories
    
    Returns:
        Sorted list of Path objects (normalized to .md extension for compatibility)
    """
    if not directory.exists() or not directory.is_dir():
        return []
    
    pattern = "**/*" if recursive else "*"
    
    # Collect all .enc and .md files
    enc_files = set()
    md_files = set()
    
    for f in directory.glob(f"{pattern}.enc"):
        if f.is_file():
            enc_files.add(f.with_suffix(".md"))  # Normalize to .md stem
    
    for f in directory.glob(f"{pattern}.md"):
        if f.is_file():
            md_files.add(f)
    
    # Merge: .enc takes priority (already normalized to .md paths)
    all_files = enc_files | md_files
    
    return sorted(all_files)
