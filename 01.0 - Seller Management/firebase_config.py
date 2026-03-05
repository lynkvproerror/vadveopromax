"""
Firebase Configuration for VEO Pro Max License System v2.4
============================================================

AUTO-DISCOVERY: Automatically finds all Firebase credential files
No hardcoded folder names or project IDs needed!

Usage:
    from firebase_config import get_primary_db, get_backup_db, get_failover_db
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Tuple

# Flag to track initialization
_initialized = {"primary": False, "backup": False}
_apps = {"primary": None, "backup": None}
_discovered_credentials = None


# ============================================================
# AUTO-DISCOVERY SYSTEM
# ============================================================

def _is_firebase_credential(file_path: Path) -> bool:
    """Check if a JSON file is a Firebase Admin SDK credential."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Firebase Admin SDK files have these required fields
        required_fields = ["type", "project_id", "private_key", "client_email"]
        return all(field in data for field in required_fields)
    except:
        return False


def _get_project_info(file_path: Path) -> Optional[dict]:
    """Extract project info from credential file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            "path": file_path,
            "project_id": data.get("project_id"),
            "client_email": data.get("client_email"),
        }
    except:
        return None


def _discover_credentials() -> List[dict]:
    """
    Auto-discover Firebase credential files.
    Priority: .veo.enc (encrypted) > .json (plain)
    """
    global _discovered_credentials
    
    if _discovered_credentials is not None:
        return _discovered_credentials
    
    admin_dir = Path(__file__).parent
    credentials = []
    
    # Priority 1: Encrypted .veo.enc files
    try:
        from cred_protector import decrypt_credential
        for enc_file in admin_dir.rglob("*.veo.enc"):
            data = decrypt_credential(enc_file)
            if data and all(k in data for k in ["type", "project_id", "private_key"]):
                credentials.append({
                    "path": enc_file,
                    "project_id": data.get("project_id"),
                    "client_email": data.get("client_email"),
                    "_decrypted": data,  # Keep in memory, not on disk
                })
    except ImportError:
        pass
    
    # Priority 2: Plain .json files (fallback, admin/dev only)
    if not credentials:
        for json_file in admin_dir.rglob("*.json"):
            if _is_firebase_credential(json_file):
                info = _get_project_info(json_file)
                if info:
                    credentials.append(info)
    
    # Also check environment variables
    env_paths = [
        os.environ.get("VEO_PRIMARY_CRED"),
        os.environ.get("VEO_BACKUP_CRED"),
    ]
    for env_path in env_paths:
        if env_path and Path(env_path).exists():
            if _is_firebase_credential(Path(env_path)):
                info = _get_project_info(Path(env_path))
                if info and info not in credentials:
                    credentials.append(info)
    
    # Also check user config file
    config_path = Path.home() / ".veoauto" / "config.json"
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            for key in ["primary_cred", "backup_cred"]:
                cred_path = config.get(key)
                if cred_path and Path(cred_path).exists():
                    if _is_firebase_credential(Path(cred_path)):
                        info = _get_project_info(Path(cred_path))
                        if info and info not in credentials:
                            credentials.append(info)
        except:
            pass
    
    _discovered_credentials = credentials
    return credentials


def get_discovered_credentials() -> List[dict]:
    """Get list of all discovered Firebase credentials."""
    return _discover_credentials()


def refresh_discovery():
    """Force re-discovery of credentials."""
    global _discovered_credentials
    _discovered_credentials = None
    return _discover_credentials()


# ============================================================
# FIREBASE INITIALIZATION
# ============================================================

def _get_credential_by_index(index: int) -> Optional[Path]:
    """Get credential by index (0 = primary, 1 = backup)."""
    creds = _discover_credentials()
    if index < len(creds):
        return creds[index]["path"]
    return None


def _init_firebase(which: str):
    """Initialize Firebase app."""
    global _apps, _initialized
    
    if _initialized[which]:
        return _apps[which]
    
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        # Get credential by index
        index = 0 if which == "primary" else 1
        cred_path = _get_credential_by_index(index)
        
        if not cred_path:
            return None
        
        app_name = f"veo_{which}"
        
        # Check if already exists
        try:
            _apps[which] = firebase_admin.get_app(app_name)
        except ValueError:
            # Check if we have decrypted data (from .veo.enc)
            creds_list = _discover_credentials()
            cred_entry = creds_list[index] if index < len(creds_list) else None
            
            if cred_entry and '_decrypted' in cred_entry:
                # Load from decrypted dict — no plaintext JSON on disk
                cred = credentials.Certificate(cred_entry['_decrypted'])
            else:
                # Load from plain .json file
                cred = credentials.Certificate(str(cred_path))
            
            _apps[which] = firebase_admin.initialize_app(cred, name=app_name)
        
        _initialized[which] = True
        return _apps[which]
    
    except Exception:
        return None


# ============================================================
# PUBLIC API
# ============================================================

def get_primary_db():
    """Get primary Firestore client."""
    app = _init_firebase("primary")
    if app:
        from firebase_admin import firestore
        return firestore.client(app)
    return None


def get_backup_db():
    """Get backup Firestore client."""
    app = _init_firebase("backup")
    if app:
        from firebase_admin import firestore
        return firestore.client(app)
    return None


def get_failover_db():
    """
    Get Firestore client with FAILOVER logic.
    Try Primary first, fallback to Backup.
    
    Returns:
        (db, which) - database client and which one ('primary' or 'backup')
    """
    # Try primary
    db = get_primary_db()
    if db:
        try:
            # Quick connection test
            db.collection("_lic").limit(1).get()
            return db, "primary"
        except:
            pass
    
    # Fallback to backup
    db = get_backup_db()
    if db:
        try:
            db.collection("_lic").limit(1).get()
            return db, "backup"
        except:
            pass
    
    return None, None


def get_connection_info() -> str:
    """Get current connection information."""
    creds = _discover_credentials()
    
    if not creds:
        return "No Firebase credentials found"
    
    info_parts = []
    for i, cred in enumerate(creds):
        role = "Primary" if i == 0 else "Backup" if i == 1 else f"Extra-{i}"
        status = "✅" if _initialized.get("primary" if i == 0 else "backup", False) else "⏳"
        info_parts.append(f"{status} {cred['project_id']} ({role})")
    
    return " | ".join(info_parts)


# ============================================================
# SYNC UTILITIES
# ============================================================

def sync_to_backup(license_data: dict) -> bool:
    """Sync license data from primary to backup."""
    try:
        backup_db = get_backup_db()
        if not backup_db:
            return False
        
        key = license_data.get("key")
        if not key:
            return False
        
        backup_db.collection("_lic").document(key).set(license_data)
        return True
    except Exception:
        return False


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    print("🔥 Firebase Config v2.4 - Auto-Discovery Test")
    print("=" * 50)
    
    creds = _discover_credentials()
    print(f"\nFound {len(creds)} credential(s)")
    
    for i, cred in enumerate(creds):
        print(f"  [{i}] {cred['project_id']}")
        print(f"      Path: {cred['path']}")
    
    print("\n" + "=" * 50)
    print("Testing failover...")
    db, which = get_failover_db()
    if db:
        print(f"✅ Connected to: {which}")
    else:
        print("❌ No connection")
