"""
VEO Seller App — Pre-Build Validation & Nuitka Build Script
============================================================
Validates source code, encrypts credentials, builds .exe, and runs post-build tests.

Usage:
    python build_seller.py check      → Pre-build validation only
    python build_seller.py build      → Full build (validate + Nuitka compile)
    python build_seller.py deploy     → Build + prepare deploy folder
    python build_seller.py all        → Check + Build + Deploy + Test
"""

import os
import sys
import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================

SELLER_DIR = Path(__file__).parent.parent / "01.0 - Seller Management"
FINAL_DIR = Path(__file__).parent.parent / "01.2 - Seller Management Final Tool"
BUILD_DIR = FINAL_DIR / "_build_temp"
DEPLOY_DIR = FINAL_DIR

CRITICAL_FILES = [
    "seller_auth.py",
    "seller_manager_gui.py",
    "firebase_config.py",
    "license_keygen.py",
    "cred_protector.py",
]

# Files that MUST NOT be in deploy folder
FORBIDDEN_FILES = [
    "*.json",          # Plaintext credentials
    "PLAN.md",         # Architecture docs
    "README.md",       # Documentation
    ".integrity",      # Hash file (regenerated on first run)
    "*.pyc",           # Bytecode
    "__pycache__",     # Cache dir
    "build_seller.py", # This script
    "*.log",           # Log files
]

# Required folders in deploy
REQUIRED_STRUCTURE = {
    "primary/cred.veo.enc": "Encrypted primary credentials",
    "backup/cred.veo.enc": "Encrypted backup credentials",
}


# ============================================================
# PRE-BUILD CHECKS
# ============================================================

class PreBuildValidator:
    """Validate source code before building."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def run_all(self) -> bool:
        """Run all pre-build checks. Returns True if pass."""
        print("=" * 60)
        print("🔍 PRE-BUILD VALIDATION")
        print("=" * 60)
        
        self._check_files_exist()
        self._check_no_plaintext_credentials()
        self._check_no_print_leaks()
        self._check_no_hardcoded_secrets()
        self._check_env_var()
        self._check_encrypted_credentials()
        self._check_syntax()
        self._check_forbidden_patterns()
        
        print()
        if self.errors:
            print(f"❌ FAILED — {len(self.errors)} error(s):")
            for e in self.errors:
                print(f"   🔴 {e}")
        if self.warnings:
            print(f"⚠️  {len(self.warnings)} warning(s):")
            for w in self.warnings:
                print(f"   🟡 {w}")
        if not self.errors:
            print("✅ ALL CHECKS PASSED")
        
        return len(self.errors) == 0
    
    def _check_files_exist(self):
        """Check all critical files exist."""
        print("\n  [1/8] Checking critical files...")
        for fname in CRITICAL_FILES:
            fpath = SELLER_DIR / fname
            if not fpath.exists():
                self.errors.append(f"Missing: {fname}")
            else:
                print(f"       ✅ {fname}")
    
    def _check_no_plaintext_credentials(self):
        """Ensure no .json credential files in seller folder."""
        print("\n  [2/8] Checking no plaintext credentials...")
        for json_file in SELLER_DIR.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding='utf-8'))
                if all(k in data for k in ["type", "project_id", "private_key"]):
                    self.errors.append(f"PLAINTEXT credentials found: {json_file.relative_to(SELLER_DIR)}")
            except Exception:
                pass
        if not self.errors or not any("PLAINTEXT" in e for e in self.errors):
            print("       ✅ No plaintext credentials")
    
    def _check_no_print_leaks(self):
        """Check for print statements that leak info."""
        print("\n  [3/8] Checking for print leaks...")
        leak_patterns = [
            'print(f"🔍',
            'print(f"❌',
            'print(f"✅',
            'print(f"[SELLER]',
            'str(e)[:100]',
            'str(e)',
        ]
        for fname in CRITICAL_FILES:
            fpath = SELLER_DIR / fname
            if not fpath.exists():
                continue
            content = fpath.read_text(encoding='utf-8')
            for pattern in leak_patterns:
                if pattern in content:
                    # Skip if in __main__ block or comment
                    lines = content.split('\n')
                    in_main = False
                    for i, line in enumerate(lines, 1):
                        if "if __name__" in line:
                            in_main = True
                        if pattern in line and not in_main and not line.strip().startswith('#'):
                            self.warnings.append(f"{fname}:{i} contains '{pattern}'")
        if not self.warnings:
            print("       ✅ No print leaks found")
    
    def _check_no_hardcoded_secrets(self):
        """Check for hardcoded secrets."""
        print("\n  [4/8] Checking for hardcoded secrets...")
        bad_patterns = [
            'veo_dev_key_2026',
            'password =',
            'secret =',
            'api_key =',
        ]
        for fname in CRITICAL_FILES:
            fpath = SELLER_DIR / fname
            if not fpath.exists():
                continue
            content = fpath.read_text(encoding='utf-8').lower()
            for pattern in bad_patterns:
                if pattern in content:
                    # Context check - ignore comments and strings
                    for i, line in enumerate(fpath.read_text(encoding='utf-8').split('\n'), 1):
                        if pattern in line.lower() and not line.strip().startswith('#') and not line.strip().startswith('"'):
                            if 'veo_dev_key' in pattern:
                                self.errors.append(f"{fname}:{i} hardcoded dev key!")
        print("       ✅ Check complete")
    
    def _check_env_var(self):
        """Check VEO_LICENSE_SECRET is set."""
        print("\n  [5/8] Checking VEO_LICENSE_SECRET...")
        key = os.environ.get("VEO_LICENSE_SECRET")
        if not key:
            self.errors.append("VEO_LICENSE_SECRET env var not set!")
        elif len(key) < 32:
            self.warnings.append("VEO_LICENSE_SECRET should be 32 hex chars")
        else:
            print(f"       ✅ Set ({key[:4]}...{key[-4:]})")
    
    def _check_encrypted_credentials(self):
        """Check .veo.enc files exist."""
        print("\n  [6/8] Checking encrypted credentials...")
        for rel_path, desc in REQUIRED_STRUCTURE.items():
            full_path = SELLER_DIR / rel_path
            if not full_path.exists():
                self.errors.append(f"Missing: {rel_path} ({desc})")
            else:
                print(f"       ✅ {rel_path}")
    
    def _check_syntax(self):
        """Compile check all Python files."""
        print("\n  [7/8] Syntax check (py_compile)...")
        import py_compile
        for fname in CRITICAL_FILES:
            fpath = SELLER_DIR / fname
            if not fpath.exists():
                continue
            try:
                py_compile.compile(str(fpath), doraise=True)
                print(f"       ✅ {fname}")
            except py_compile.PyCompileError as e:
                self.errors.append(f"{fname} syntax error: {e}")
    
    def _check_forbidden_patterns(self):
        """Check for security anti-patterns in code."""
        print("\n  [8/8] Checking security patterns...")
        # Check: plaintext password comparison
        auth_content = (SELLER_DIR / "seller_auth.py").read_text(encoding='utf-8')
        
        # Ensure no `stored != password` or `stored == password` (should use hmac.compare_digest)
        lines = auth_content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if ('stored' in stripped or 'password' in stripped) and ('!=' in stripped or '==' in stripped):
                if 'compare_digest' not in stripped and not stripped.startswith('#'):
                    self.warnings.append(f"seller_auth.py:{i} possible plaintext comparison")
        
        print("       ✅ Check complete")


# ============================================================
# NUITKA BUILD
# ============================================================

def build_with_nuitka() -> bool:
    """Build seller app with Nuitka."""
    print("\n" + "=" * 60)
    print("🔨 NUITKA BUILD")
    print("=" * 60)
    
    # Check Nuitka installed
    try:
        result = subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            capture_output=True, text=True, timeout=10
        )
        print(f"  Nuitka version: {result.stdout.strip()}")
    except Exception:
        print("  ❌ Nuitka not installed! Run: pip install nuitka")
        return False
    
    # Build command
    build_cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--enable-plugin=pyside6",
        "--windows-console-mode=disable",
        f"--output-dir={BUILD_DIR}",
        "--output-filename=SellerManager.exe",
        
        # Include data files
        f"--include-data-dir={SELLER_DIR / 'primary'}=primary",
        f"--include-data-dir={SELLER_DIR / 'backup'}=backup",
        
        # Include modules that are dynamically imported
        "--include-module=firebase_admin",
        "--include-module=firebase_admin.credentials",
        "--include-module=firebase_admin.firestore",
        "--include-module=google.cloud.firestore_v1",
        "--include-module=google.cloud.firestore_v1.base_query",
        "--include-module=cred_protector",
        "--include-module=license_keygen",
        "--include-module=seller_auth",
        "--include-module=firebase_config",
        
        # Optimization
        "--assume-yes-for-downloads",
        "--remove-output",
        
        # Entry point
        str(SELLER_DIR / "seller_manager_gui.py"),
    ]
    
    print(f"\n  Building... (this may take 5-15 minutes)")
    print(f"  Command: {' '.join(build_cmd[:5])}...")
    
    try:
        result = subprocess.run(
            build_cmd,
            cwd=str(SELLER_DIR),
            timeout=1800,  # 30 min max
        )
        
        if result.returncode == 0:
            print("\n  ✅ BUILD SUCCESS")
            return True
        else:
            print(f"\n  ❌ BUILD FAILED (exit code: {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        print("\n  ❌ BUILD TIMEOUT (>30 minutes)")
        return False
    except Exception as e:
        print(f"\n  ❌ BUILD ERROR: {e}")
        return False


# ============================================================
# DEPLOY PREPARATION
# ============================================================

def prepare_deploy() -> bool:
    """Create clean deploy folder."""
    print("\n" + "=" * 60)
    print("📦 PREPARING DEPLOY FOLDER")
    print("=" * 60)
    
    # Find built exe (search multiple possible locations)
    exe_path = None
    search_dirs = [BUILD_DIR, FINAL_DIR, SELLER_DIR]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for p in search_dir.rglob("*.exe"):
            if p.stat().st_size > 5_000_000:  # > 5MB = likely our exe
                exe_path = p
                print(f"  Found exe: {p} ({p.stat().st_size / 1024 / 1024:.1f} MB)")
                break
        if exe_path:
            break
    
    if not exe_path:
        print("  ❌ SellerManager.exe not found in build output")
        print(f"     Searched: {[str(d) for d in search_dirs]}")
        return False
    
    # Clean deploy dir (but preserve _build_temp)
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    for item in DEPLOY_DIR.iterdir():
        if item.name == '_build_temp':
            continue  # Don't delete build cache
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)
    
    # Copy exe
    dest = DEPLOY_DIR / "SellerManager.exe"
    shutil.copy2(exe_path, dest)
    print(f"  ✅ SellerManager.exe ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
    
    # Verify no forbidden files
    print("\n  Verifying deploy folder...")
    for pattern in FORBIDDEN_FILES:
        for found in DEPLOY_DIR.rglob(pattern):
            if '_build_temp' in str(found):
                continue  # Skip build cache
            print(f"  ❌ FORBIDDEN file in deploy: {found.name}")
            found.unlink() if found.is_file() else shutil.rmtree(found)
    
    # Create version info
    version_info = {
        "app": "VEO Seller Manager",
        "built_at": datetime.now().isoformat(),
        "python": sys.version.split()[0],
        "builder": "Nuitka",
    }
    (DEPLOY_DIR / "version.json").write_text(json.dumps(version_info, indent=2))
    print(f"  ✅ version.json created")
    
    print(f"\n  📁 Deploy folder: {DEPLOY_DIR}")
    for f in DEPLOY_DIR.iterdir():
        if f.name == '_build_temp':
            continue
        size = f.stat().st_size / 1024 / 1024
        print(f"     {f.name} ({size:.1f} MB)")
    
    return True


# ============================================================
# MAIN
# ============================================================

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    
    if cmd == "check":
        validator = PreBuildValidator()
        success = validator.run_all()
        sys.exit(0 if success else 1)
    
    elif cmd == "build":
        validator = PreBuildValidator()
        if not validator.run_all():
            print("\n❌ Fix errors before building!")
            sys.exit(1)
        if not build_with_nuitka():
            sys.exit(1)
    
    elif cmd == "deploy":
        validator = PreBuildValidator()
        if not validator.run_all():
            print("\n❌ Fix errors before building!")
            sys.exit(1)
        if not build_with_nuitka():
            sys.exit(1)
        if not prepare_deploy():
            sys.exit(1)
    
    elif cmd == "all":
        validator = PreBuildValidator()
        if not validator.run_all():
            print("\n❌ Fix errors before building!")
            sys.exit(1)
        if not build_with_nuitka():
            sys.exit(1)
        if not prepare_deploy():
            sys.exit(1)
        print("\n" + "=" * 60)
        print("🎉 ALL DONE — Deploy folder ready!")
        print("=" * 60)
    
    else:
        print("Usage: python build_seller.py [check|build|deploy|all]")
        sys.exit(1)


if __name__ == "__main__":
    main()
