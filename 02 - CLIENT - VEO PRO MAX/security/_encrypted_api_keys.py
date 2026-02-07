"""
Encrypted API Keys for Firebase REST Client v2.5
=================================================

Supports both:
- Hardware-bound keys (more secure, machine-specific)
- Static keys (works on any machine)

Generated: 2026-02-04
Encryption: AES-256 with PBKDF2 (100k iterations)

Usage:
    from _encrypted_api_keys import set_runtime_keys
    set_runtime_keys()  # Call at app startup
"""

from firebase_rest_client import _AES256Encryptor, _HardwareBinder, SecureFirebaseConfig


# ============================================================
# CONFIGURATION
# ============================================================

# Toggle between hardware-bound and static keys
# Set to True for development/multi-machine
# Set to False for production (more secure)
USE_STATIC_KEY = False


# ============================================================
# API KEYS (Will be encrypted at runtime)
# ============================================================

_RAW_PRIMARY = 'AIzaSyDpVLX01lnwlwi54bX9A9fZL_55uET5W9w'
_RAW_BACKUP = 'AIzaSyBWvaGugfWmspFvRd9wcLbBdT8UCI6MNY8'

# Cached encrypted keys
_PRIMARY_ENCRYPTED = None
_BACKUP_ENCRYPTED = None
_KEYS_INITIALIZED = False


# ============================================================
# KEY MANAGEMENT
# ============================================================

def _get_encryption_key():
    """Get the encryption key based on mode."""
    if USE_STATIC_KEY:
        return SecureFirebaseConfig._STATIC_KEY
    return _HardwareBinder.get_machine_key()


def _initialize_keys():
    """Initialize encrypted keys."""
    global _PRIMARY_ENCRYPTED, _BACKUP_ENCRYPTED, _KEYS_INITIALIZED
    
    if _KEYS_INITIALIZED:
        return
    
    key = _get_encryption_key()
    _PRIMARY_ENCRYPTED = _AES256Encryptor.encrypt(_RAW_PRIMARY, key)
    _BACKUP_ENCRYPTED = _AES256Encryptor.encrypt(_RAW_BACKUP, key)
    _KEYS_INITIALIZED = True


def set_runtime_keys():
    """Set encrypted keys in SecureFirebaseConfig at runtime."""
    # Set mode first
    SecureFirebaseConfig.set_static_mode(USE_STATIC_KEY)
    
    # Initialize if needed
    _initialize_keys()
    
    # Set keys
    SecureFirebaseConfig.set_encrypted_keys(_PRIMARY_ENCRYPTED, _BACKUP_ENCRYPTED)
    return True


def get_key_mode():
    """Get current key mode."""
    return SecureFirebaseConfig.get_key_mode()


def set_static_mode(enabled: bool):
    """Toggle static key mode."""
    global USE_STATIC_KEY, _KEYS_INITIALIZED
    USE_STATIC_KEY = enabled
    _KEYS_INITIALIZED = False  # Force re-initialization
    set_runtime_keys()


# ============================================================
# AUTO-INITIALIZATION
# ============================================================

if __name__ != "__main__":
    try:
        set_runtime_keys()
    except Exception as e:
        print(f"Warning: Could not initialize API keys: {e}")


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    print("🔐 Encrypted API Keys v2.5")
    print("=" * 50)
    
    # Test hardware-bound mode
    print("Testing hardware-bound mode...")
    set_static_mode(False)
    print(f"Mode: {get_key_mode()}")
    
    config = SecureFirebaseConfig()
    primary = config.get_primary_config()
    backup = config.get_backup_config()
    
    print(f"Primary: {primary['api_key'][:15]}..." if primary['api_key'] else "Primary: FAILED")
    print(f"Backup: {backup['api_key'][:15]}..." if backup['api_key'] else "Backup: FAILED")
    
    hw_ok = primary['api_key'] == _RAW_PRIMARY and backup['api_key'] == _RAW_BACKUP
    print("✅ Hardware-bound OK!" if hw_ok else "❌ Hardware-bound FAILED!")
    
    # Test static mode
    print("\n" + "=" * 50)
    print("Testing static mode...")
    set_static_mode(True)
    print(f"Mode: {get_key_mode()}")
    
    config2 = SecureFirebaseConfig()
    p2 = config2.get_primary_config()
    b2 = config2.get_backup_config()
    
    print(f"Primary: {p2['api_key'][:15]}..." if p2['api_key'] else "Primary: FAILED")
    print(f"Backup: {b2['api_key'][:15]}..." if b2['api_key'] else "Backup: FAILED")
    
    static_ok = p2['api_key'] == _RAW_PRIMARY and b2['api_key'] == _RAW_BACKUP
    print("✅ Static OK!" if static_ok else "❌ Static FAILED!")
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY:")
    print(f"  Hardware-bound: {'✅' if hw_ok else '❌'}")
    print(f"  Static mode: {'✅' if static_ok else '❌'}")
