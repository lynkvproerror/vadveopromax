"""
VEO Pro Max - Auto Git Push Script
===================================
Tự động push toàn bộ codebase lên GitHub.
Xử lý: large files, .gitignore, filter-branch cleanup.

Usage:
    python git_push.py                          # Auto commit + push
    python git_push.py -m "custom message"      # Custom commit message
    python git_push.py --tag v2.3.12            # Commit + push + create tag
    python git_push.py --dry-run                # Preview only, no changes
"""

import subprocess
import sys
import os
import argparse
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────
REPO_DIR = Path(__file__).parent
REMOTE = "origin"
GITHUB_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
WARNING_FILE_SIZE = 50 * 1024 * 1024       # 50MB — warn above this

# Extensions and patterns to always ignore
ALWAYS_IGNORE = [
    "*.dmg",
    "*.iso",
    "*.msi",
    "*.exe",
    "*.zip",
    "*.7z",
    "*.rar",
    "*.tar.gz",
    "*.tar.bz2",
    "__pycache__/",
    "*.pyc",
    ".env",
    "node_modules/",
    "*.log",
]

# Directories to skip when scanning for large files
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def run(cmd, cwd=None, check=True, capture=True):
    """Run a shell command and return output."""
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_DIR,
        capture_output=capture,
        text=True,
        shell=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        print(f"  ❌ Command failed: {cmd}")
        if result.stderr:
            print(f"     {result.stderr.strip()[:500]}")
        return None
    return result.stdout.strip() if capture else ""


def get_current_branch():
    """Get current git branch name."""
    return run("git branch --show-current") or "main"


def get_status():
    """Get git status summary."""
    output = run("git status --porcelain", check=False)
    if not output:
        return []
    return [line for line in output.split("\n") if line.strip()]


def scan_large_files():
    """Scan for files exceeding GitHub's size limit."""
    large_files = []
    warning_files = []
    
    for root, dirs, files in os.walk(REPO_DIR):
        # Skip .git and other irrelevant dirs
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for fname in files:
            fpath = Path(root) / fname
            try:
                size = fpath.stat().st_size
                rel_path = fpath.relative_to(REPO_DIR)
                
                if size > GITHUB_MAX_FILE_SIZE:
                    large_files.append((str(rel_path), size))
                elif size > WARNING_FILE_SIZE:
                    warning_files.append((str(rel_path), size))
            except (OSError, PermissionError):
                pass
    
    return large_files, warning_files


def ensure_gitignore(large_files):
    """Add large files to .gitignore if not already there."""
    gitignore_path = REPO_DIR / ".gitignore"
    
    # Read existing .gitignore
    existing = set()
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            existing = {line.strip() for line in f if line.strip() and not line.startswith("#")}
    
    # Determine what needs to be added
    to_add = []
    for fpath, size in large_files:
        # Normalize path separators
        normalized = fpath.replace("\\", "/")
        if normalized not in existing:
            to_add.append(normalized)
    
    if not to_add:
        return False
    
    # Append to .gitignore
    with open(gitignore_path, "a", encoding="utf-8") as f:
        f.write("\n# === Auto-added by git_push.py (files > 100MB) ===\n")
        for entry in to_add:
            f.write(f"{entry}\n")
            print(f"  📝 Added to .gitignore: {entry}")
    
    return True


def remove_large_from_index(large_files):
    """Remove large files from git index (keep on disk)."""
    for fpath, size in large_files:
        normalized = fpath.replace("\\", "/")
        result = run(f'git rm --cached --ignore-unmatch "{normalized}"', check=False)
        if result is not None:
            size_mb = size / (1024 * 1024)
            print(f"  🗑️  Removed from index: {normalized} ({size_mb:.1f}MB)")


def check_history_large_files():
    """Check if any large files exist in unpushed commits."""
    # Get list of objects in unpushed commits
    branch = get_current_branch()
    output = run(
        f"git rev-list --objects {REMOTE}/{branch}..HEAD 2>nul",
        check=False,
    )
    if not output:
        return []
    
    large_in_history = []
    for line in output.split("\n"):
        parts = line.strip().split(" ", 1)
        if len(parts) < 2:
            continue
        obj_hash, obj_path = parts
        # Check object size
        size_str = run(f"git cat-file -s {obj_hash}", check=False)
        if size_str and size_str.isdigit():
            size = int(size_str)
            if size > GITHUB_MAX_FILE_SIZE:
                large_in_history.append((obj_path, size, obj_hash))
    
    return large_in_history


def filter_branch_cleanup(file_paths):
    """Use git filter-branch to remove files from history."""
    if not file_paths:
        return
    
    print("\n🔧 Cleaning large files from git history...")
    
    for fpath in file_paths:
        normalized = fpath.replace("\\", "/")
        print(f"  Filtering: {normalized}")
        
        # Set environment to suppress warning
        env = os.environ.copy()
        env["FILTER_BRANCH_SQUELCH_WARNING"] = "1"
        
        subprocess.run(
            f'git filter-branch --force --index-filter '
            f'"git rm --cached --ignore-unmatch \'{normalized}\'" '
            f'--prune-empty -- --all',
            cwd=REPO_DIR,
            shell=True,
            env=env,
            capture_output=True,
            text=True,
        )
    
    # Cleanup
    run("git reflog expire --expire=now --all", check=False)
    run("git gc --prune=now", check=False)
    print("  ✅ History cleaned")


def main():
    parser = argparse.ArgumentParser(description="Auto push VEO Pro Max to GitHub")
    parser.add_argument("-m", "--message", default=None, help="Commit message")
    parser.add_argument("--tag", default=None, help="Create and push a tag (e.g. v2.3.12)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--force", action="store_true", help="Force push")
    parser.add_argument("--branch", default=None, help="Target branch (auto-detect if not set)")
    args = parser.parse_args()
    
    os.chdir(REPO_DIR)
    branch = args.branch or get_current_branch()
    
    print("=" * 60)
    print("🚀 VEO Pro Max — Auto Git Push")
    print("=" * 60)
    print(f"  📂 Repo:   {REPO_DIR}")
    print(f"  🌿 Branch: {branch}")
    print(f"  🔗 Remote: {REMOTE}")
    print()
    
    # ── Step 1: Scan for large files ──────────────────────────
    print("📏 Step 1: Scanning for large files...")
    large_files, warning_files = scan_large_files()
    
    if large_files:
        print(f"  ⚠️  Found {len(large_files)} file(s) > 100MB:")
        for fp, sz in large_files:
            print(f"     🔴 {fp} ({sz / 1024 / 1024:.1f}MB)")
    
    if warning_files:
        print(f"  ⚡ {len(warning_files)} file(s) > 50MB (warning):")
        for fp, sz in warning_files[:5]:
            print(f"     🟡 {fp} ({sz / 1024 / 1024:.1f}MB)")
        if len(warning_files) > 5:
            print(f"     ... and {len(warning_files) - 5} more")
    
    if not large_files and not warning_files:
        print("  ✅ No oversized files found")
    
    if args.dry_run and large_files:
        print("\n  [DRY RUN] Would add these to .gitignore and remove from index")
        return
    
    # ── Step 2: Handle large files ────────────────────────────
    if large_files:
        print("\n🛡️  Step 2: Handling large files...")
        ensure_gitignore(large_files)
        remove_large_from_index(large_files)
    else:
        print("✅ Step 2: No large files to handle")
    
    # ── Step 3: Stage all changes ─────────────────────────────
    print("\n📦 Step 3: Staging all changes...")
    run("git add -A", check=False)
    
    status = get_status()
    if not status:
        print("  ✅ Working tree clean — nothing to commit")
    else:
        print(f"  📋 {len(status)} file(s) staged:")
        # Show summary by type
        added = sum(1 for s in status if s.startswith("A") or s.startswith("??"))
        modified = sum(1 for s in status if s.startswith("M"))
        deleted = sum(1 for s in status if s.startswith("D"))
        renamed = sum(1 for s in status if s.startswith("R"))
        
        parts = []
        if added: parts.append(f"{added} added")
        if modified: parts.append(f"{modified} modified")
        if deleted: parts.append(f"{deleted} deleted")
        if renamed: parts.append(f"{renamed} renamed")
        print(f"     {', '.join(parts)}")
        
        # Show first 10 files
        for s in status[:10]:
            print(f"     {s}")
        if len(status) > 10:
            print(f"     ... and {len(status) - 10} more")
    
    if args.dry_run:
        print("\n  [DRY RUN] Would commit and push here")
        return
    
    # ── Step 4: Commit ────────────────────────────────────────
    if status:
        print("\n💾 Step 4: Committing...")
        
        if args.message:
            msg = args.message
        else:
            # Auto-generate commit message
            msg = f"update: {len(status)} file(s) changed"
            if large_files:
                msg += f" | {len(large_files)} large file(s) excluded"
        
        # Use file for commit message to avoid shell escaping issues
        msg_file = REPO_DIR / ".git" / "COMMIT_MSG_TEMP"
        with open(msg_file, "w", encoding="utf-8") as f:
            f.write(msg)
        
        result = run(f'git commit -F "{msg_file}"', check=False)
        
        try:
            msg_file.unlink()
        except Exception:
            pass
        
        if result is None:
            print("  ⚠️  Commit may have failed — checking status...")
            # Check if there's actually something to commit
            recheck = run("git status --porcelain", check=False)
            if not recheck:
                print("  ✅ Already committed (amend not needed)")
            else:
                print("  ❌ Commit failed. Please check manually.")
                return
        else:
            print(f"  ✅ Committed: {msg[:80]}")
    else:
        print("\n✅ Step 4: Nothing to commit")
    
    # ── Step 5: Check history for large blobs ─────────────────
    print("\n🔍 Step 5: Checking unpushed history for large blobs...")
    
    # Quick check: try a dry-run push to see if it would fail
    dry_push = run(f"git push --dry-run {REMOTE} {branch} 2>&1", check=False)
    if dry_push and "exceeds GitHub" in dry_push:
        print("  ⚠️  Large file detected in history!")
        # Extract filename from error
        for line in dry_push.split("\n"):
            if "exceeds" in line:
                print(f"     {line.strip()}")
        
        # Try filter-branch
        large_in_hist = check_history_large_files()
        if large_in_hist:
            paths = [p for p, _, _ in large_in_hist]
            filter_branch_cleanup(paths)
    else:
        print("  ✅ No large blobs in history")
    
    # ── Step 6: Push ──────────────────────────────────────────
    print(f"\n🚀 Step 6: Pushing to {REMOTE}/{branch}...")
    
    force_flag = "--force" if args.force else ""
    result = run(f"git push {force_flag} {REMOTE} {branch} 2>&1", check=False)
    
    if result is None or (result and "error" in result.lower() and "rejected" in result.lower()):
        print(f"  ⚠️  Push failed. Output:")
        if result:
            for line in result.split("\n")[:10]:
                print(f"     {line}")
        
        # Check if it's a large file issue
        if result and ("exceeds" in result or "large files" in result.lower()):
            print("\n  🔧 Large file in history detected. Attempting filter-branch cleanup...")
            
            # Stash, filter, pop
            run("git stash", check=False)
            
            # Find the problematic file from error message
            problem_files = []
            for line in result.split("\n"):
                if "exceeds" in line:
                    # Extract path: "File some/path.dmg is 146.48 MB"
                    parts = line.split("File ")
                    if len(parts) > 1:
                        path_part = parts[1].split(" is ")[0].strip()
                        problem_files.append(path_part)
            
            if problem_files:
                filter_branch_cleanup(problem_files)
                
                # Also ensure these are in .gitignore
                for pf in problem_files:
                    normalized = pf.replace("\\", "/")
                    gitignore_path = REPO_DIR / ".gitignore"
                    with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if normalized not in content:
                        with open(gitignore_path, "a", encoding="utf-8") as f:
                            f.write(f"\n{normalized}\n")
                        print(f"  📝 Added to .gitignore: {normalized}")
                
                run("git stash pop", check=False)
                run("git add .gitignore", check=False)
                run('git commit --amend --no-edit', check=False)
                
                # Retry push with force
                print("\n  🔄 Retrying push with --force...")
                retry = run(f"git push --force {REMOTE} {branch} 2>&1", check=False)
                if retry and "error" not in retry.lower():
                    print(f"  ✅ Push successful!")
                else:
                    print(f"  ❌ Push still failed:")
                    if retry:
                        for line in retry.split("\n")[:5]:
                            print(f"     {line}")
                    return
            else:
                run("git stash pop", check=False)
                print("  ❌ Could not identify problematic file. Fix manually.")
                return
        else:
            # Non-large-file error — maybe need force push
            print("\n  💡 Try running with --force flag:")
            print(f"     python git_push.py --force")
            return
    else:
        print(f"  ✅ Push successful!")
        if result:
            # Show last few lines of push output
            lines = result.strip().split("\n")
            for line in lines[-3:]:
                print(f"     {line}")
    
    # ── Step 7: Tag (optional) ────────────────────────────────
    if args.tag:
        print(f"\n🏷️  Step 7: Creating tag {args.tag}...")
        
        tag_msg_file = REPO_DIR / ".git" / "TAG_MSG_TEMP"
        tag_msg = args.message or f"Release {args.tag}"
        with open(tag_msg_file, "w", encoding="utf-8") as f:
            f.write(tag_msg)
        
        run(f'git tag -a {args.tag} -F "{tag_msg_file}"', check=False)
        run(f"git push {REMOTE} {args.tag}", check=False)
        
        try:
            tag_msg_file.unlink()
        except Exception:
            pass
        
        print(f"  ✅ Tag {args.tag} created and pushed")
        print(f"  🔗 https://github.com/lynkvproerror/veo-pro-max/releases/new?tag={args.tag}")
    
    # ── Done ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("✅ All done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
