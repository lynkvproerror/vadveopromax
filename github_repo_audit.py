"""
GitHub Repo Audit & Cleanup Script
====================================
Kiểm tra và xoá toàn bộ nội dung repo GitHub:
- Commits, branches, tags
- Releases (bao gồm release assets)
- Release tags

Target: https://github.com/lynkvproerror/vadveopromax

Usage:
    python github_repo_audit.py                    # Kiểm tra (chỉ xem, không xoá)
    python github_repo_audit.py --delete-all       # Xoá toàn bộ releases, tags
    python github_repo_audit.py --nuke             # Xoá TOÀN BỘ repo (nguy hiểm!)

Yêu cầu:
    pip install requests
    Cần GitHub Personal Access Token có quyền: repo, delete_repo
"""

import requests
import sys
import argparse
import time

# ── Config ──────────────────────────────────────────────────────
OWNER = "lynkvproerror"
REPO = "vadveopromax"
API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"

# Token sẽ được nhập khi chạy script
TOKEN = None
HEADERS = {}


def setup_auth(token: str):
    """Setup authentication headers."""
    global TOKEN, HEADERS
    TOKEN = token
    HEADERS = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def api_get(endpoint: str, params=None):
    """GET request to GitHub API."""
    url = f"{API_BASE}/{endpoint}" if not endpoint.startswith("http") else endpoint
    resp = requests.get(url, headers=HEADERS, params=params)
    return resp


def api_delete(endpoint: str):
    """DELETE request to GitHub API."""
    url = f"{API_BASE}/{endpoint}" if not endpoint.startswith("http") else endpoint
    resp = requests.delete(url, headers=HEADERS)
    return resp


def check_repo_exists():
    """Check if repo exists and is accessible."""
    resp = requests.get(API_BASE, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json()
    elif resp.status_code == 404:
        return None
    else:
        print(f"  ❌ API Error: {resp.status_code} — {resp.text[:200]}")
        return None


# ═══════════════════════════════════════════════════════════════
#  AUDIT FUNCTIONS (read-only)
# ═══════════════════════════════════════════════════════════════

def audit_repo_info(repo_data):
    """Display basic repo info."""
    print(f"  📛 Name:        {repo_data['full_name']}")
    print(f"  📝 Description: {repo_data.get('description') or '(none)'}")
    print(f"  🌿 Default:     {repo_data['default_branch']}")
    print(f"  📏 Size:        {repo_data['size']} KB")
    print(f"  👁️  Visibility:  {'Private' if repo_data['private'] else 'Public'}")
    print(f"  ⭐ Stars:       {repo_data.get('stargazers_count', 0)}")
    print(f"  🍴 Forks:       {repo_data.get('forks_count', 0)}")
    print(f"  📅 Created:     {repo_data['created_at']}")
    print(f"  📅 Updated:     {repo_data['updated_at']}")
    print(f"  📅 Pushed:      {repo_data.get('pushed_at', 'N/A')}")
    
    has_content = repo_data['size'] > 0
    return has_content


def audit_branches():
    """List all branches."""
    branches = []
    page = 1
    while True:
        resp = api_get("branches", params={"per_page": 100, "page": page})
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        branches.extend(data)
        page += 1
    
    print(f"\n  🌿 Branches ({len(branches)}):")
    for b in branches:
        sha = b['commit']['sha'][:8]
        protected = " 🔒" if b.get('protected') else ""
        print(f"     • {b['name']} ({sha}){protected}")
    
    return branches


def audit_tags():
    """List all tags."""
    tags = []
    page = 1
    while True:
        resp = api_get("tags", params={"per_page": 100, "page": page})
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        tags.extend(data)
        page += 1
    
    print(f"\n  🏷️  Tags ({len(tags)}):")
    for t in tags:
        sha = t['commit']['sha'][:8]
        print(f"     • {t['name']} ({sha})")
    
    return tags


def audit_releases():
    """List all releases (including drafts)."""
    releases = []
    page = 1
    while True:
        resp = api_get("releases", params={"per_page": 100, "page": page})
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        releases.extend(data)
        page += 1
    
    print(f"\n  📦 Releases ({len(releases)}):")
    for r in releases:
        draft = " [DRAFT]" if r.get('draft') else ""
        prerelease = " [PRE]" if r.get('prerelease') else ""
        assets = r.get('assets', [])
        asset_info = f" — {len(assets)} asset(s)" if assets else ""
        
        total_size = sum(a.get('size', 0) for a in assets)
        size_info = f" ({total_size / 1024 / 1024:.1f}MB)" if total_size > 0 else ""
        
        print(f"     • {r['tag_name']}: {r['name'] or '(no title)'}{draft}{prerelease}{asset_info}{size_info}")
        
        for a in assets:
            a_size = a.get('size', 0) / 1024 / 1024
            dl = a.get('download_count', 0)
            print(f"       └─ {a['name']} ({a_size:.1f}MB, {dl} downloads)")
    
    return releases


def audit_commits(limit=10):
    """List recent commits."""
    resp = api_get("commits", params={"per_page": limit})
    if resp.status_code != 200:
        print(f"\n  📜 Commits: Could not fetch ({resp.status_code})")
        return []
    
    commits = resp.json()
    print(f"\n  📜 Recent Commits (showing {len(commits)}):")
    for c in commits:
        sha = c['sha'][:8]
        msg = c['commit']['message'].split('\n')[0][:60]
        author = c['commit']['author']['name']
        date = c['commit']['author']['date'][:10]
        print(f"     • {sha} {date} [{author}] {msg}")
    
    return commits


def audit_contents():
    """List root directory contents."""
    resp = api_get("contents/")
    if resp.status_code != 200:
        print(f"\n  📁 Contents: Empty or inaccessible ({resp.status_code})")
        return []
    
    contents = resp.json()
    if not isinstance(contents, list):
        contents = [contents]
    
    print(f"\n  📁 Root Contents ({len(contents)} items):")
    
    dirs = [c for c in contents if c['type'] == 'dir']
    files = [c for c in contents if c['type'] == 'file']
    
    for d in sorted(dirs, key=lambda x: x['name']):
        print(f"     📂 {d['name']}/")
    for f in sorted(files, key=lambda x: x['name']):
        size = f.get('size', 0)
        if size > 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.1f}MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f}KB"
        else:
            size_str = f"{size}B"
        print(f"     📄 {f['name']} ({size_str})")
    
    return contents


# ═══════════════════════════════════════════════════════════════
#  DELETE FUNCTIONS (destructive!)
# ═══════════════════════════════════════════════════════════════

def delete_all_releases(releases):
    """Delete all releases and their assets."""
    if not releases:
        print("  ✅ No releases to delete")
        return
    
    print(f"\n🗑️  Deleting {len(releases)} release(s)...")
    for r in releases:
        # Delete assets first
        for a in r.get('assets', []):
            resp = api_delete(f"releases/assets/{a['id']}")
            if resp.status_code == 204:
                print(f"  ✅ Deleted asset: {a['name']}")
            else:
                print(f"  ❌ Failed to delete asset {a['name']}: {resp.status_code}")
            time.sleep(0.3)
        
        # Delete release
        resp = api_delete(f"releases/{r['id']}")
        if resp.status_code == 204:
            print(f"  ✅ Deleted release: {r['tag_name']} — {r.get('name', '')}")
        else:
            print(f"  ❌ Failed to delete release {r['tag_name']}: {resp.status_code}")
        time.sleep(0.3)


def delete_all_tags(tags):
    """Delete all tags via git refs API."""
    if not tags:
        print("  ✅ No tags to delete")
        return
    
    print(f"\n🗑️  Deleting {len(tags)} tag(s)...")
    for t in tags:
        resp = api_delete(f"git/refs/tags/{t['name']}")
        if resp.status_code == 204:
            print(f"  ✅ Deleted tag: {t['name']}")
        elif resp.status_code == 422:
            print(f"  ⚠️  Tag already deleted or not found: {t['name']}")
        else:
            print(f"  ❌ Failed to delete tag {t['name']}: {resp.status_code} {resp.text[:100]}")
        time.sleep(0.3)


def delete_all_branches(branches, default_branch):
    """Delete all non-default branches."""
    non_default = [b for b in branches if b['name'] != default_branch]
    if not non_default:
        print("  ✅ No non-default branches to delete")
        return
    
    print(f"\n🗑️  Deleting {len(non_default)} branch(es) (keeping '{default_branch}')...")
    for b in non_default:
        if b.get('protected'):
            print(f"  🔒 Skipping protected branch: {b['name']}")
            continue
        resp = api_delete(f"git/refs/heads/{b['name']}")
        if resp.status_code == 204:
            print(f"  ✅ Deleted branch: {b['name']}")
        else:
            print(f"  ❌ Failed to delete branch {b['name']}: {resp.status_code}")
        time.sleep(0.3)


def nuke_repo():
    """Delete the entire repository. EXTREMELY DANGEROUS!"""
    print("\n" + "=" * 60)
    print("☢️  DANGER: This will DELETE the entire repository!")
    print(f"   Repo: https://github.com/{OWNER}/{REPO}")
    print("=" * 60)
    
    confirm = input(f"\n  Type '{REPO}' to confirm deletion: ").strip()
    if confirm != REPO:
        print("  ❌ Cancelled — repo name did not match")
        return False
    
    confirm2 = input("  Type 'YES DELETE' to double-confirm: ").strip()
    if confirm2 != "YES DELETE":
        print("  ❌ Cancelled")
        return False
    
    resp = api_delete("")
    if resp.status_code == 204:
        print(f"\n  ☢️  Repository {OWNER}/{REPO} has been DELETED")
        return True
    else:
        print(f"\n  ❌ Failed to delete repo: {resp.status_code}")
        print(f"     {resp.text[:300]}")
        print(f"     💡 Token needs 'delete_repo' permission")
        return False


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Audit & cleanup GitHub repo")
    parser.add_argument("--token", default=None, help="GitHub Personal Access Token")
    parser.add_argument("--delete-all", action="store_true",
                        help="Delete all releases, tags, and non-default branches")
    parser.add_argument("--nuke", action="store_true",
                        help="DELETE the entire repository (irreversible!)")
    args = parser.parse_args()
    
    # ── Get token ─────────────────────────────────────────────
    token = args.token
    if not token:
        # Try gh CLI
        import subprocess
        try:
            result = subprocess.run(
                "gh auth token", shell=True, capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                token = result.stdout.strip()
                print("🔑 Using token from GitHub CLI (gh)")
        except Exception:
            pass
    
    if not token:
        # Try environment variable
        import os
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            print("🔑 Using token from environment variable")
    
    if not token:
        print("🔑 Enter GitHub Personal Access Token")
        print("   (Create at: https://github.com/settings/tokens)")
        print("   Required scopes: repo, delete_repo")
        token = input("   Token: ").strip()
    
    if not token:
        print("❌ No token provided. Exiting.")
        return
    
    setup_auth(token)
    
    # ── Audit ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"🔍 Auditing: https://github.com/{OWNER}/{REPO}")
    print("=" * 60)
    
    repo_data = check_repo_exists()
    if not repo_data:
        print(f"\n  ❌ Repo '{OWNER}/{REPO}' not found or not accessible")
        print("  💡 Check if the repo exists and token has 'repo' scope")
        return
    
    has_content = audit_repo_info(repo_data)
    default_branch = repo_data['default_branch']
    
    branches = audit_branches()
    tags = audit_tags()
    releases = audit_releases()
    commits = audit_commits(limit=10)
    
    if has_content:
        contents = audit_contents()
    
    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    
    has_code = has_content and len(commits) > 0
    print(f"  Contains code:    {'✅ YES' if has_code else '❌ NO'}")
    print(f"  Repo size:        {repo_data['size']} KB")
    print(f"  Branches:         {len(branches)}")
    print(f"  Tags:             {len(tags)}")
    print(f"  Releases:         {len(releases)}")
    print(f"  Recent commits:   {len(commits)}")
    
    if has_code:
        print(f"\n  ⚠️  Repo CÓ CHỨA code/data!")
    else:
        print(f"\n  ✅ Repo rỗng hoặc không có code")
    
    # ── Delete actions ────────────────────────────────────────
    if args.nuke:
        nuke_repo()
        return
    
    if args.delete_all:
        print("\n" + "=" * 60)
        print("🗑️  DELETE ALL: releases, tags, non-default branches")
        print("=" * 60)
        
        total = len(releases) + len(tags) + max(0, len(branches) - 1)
        if total == 0:
            print("  ✅ Nothing to delete")
            return
        
        print(f"  Will delete:")
        print(f"    • {len(releases)} release(s) + assets")
        print(f"    • {len(tags)} tag(s)")
        print(f"    • {max(0, len(branches) - 1)} branch(es) (keeping '{default_branch}')")
        
        confirm = input(f"\n  ⚠️  Continue? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("  ❌ Cancelled")
            return
        
        delete_all_releases(releases)
        delete_all_tags(tags)
        delete_all_branches(branches, default_branch)
        
        print("\n" + "=" * 60)
        print("✅ Cleanup complete!")
        print("=" * 60)
        print(f"\n  💡 To completely empty the repo, also run:")
        print(f"     python github_repo_audit.py --nuke")
        print(f"     (This will DELETE the entire repo — irreversible!)")
    
    elif has_code:
        print(f"\n  💡 To clean up, run:")
        print(f"     python github_repo_audit.py --delete-all     # Delete releases/tags/branches")
        print(f"     python github_repo_audit.py --nuke           # Delete entire repo")


if __name__ == "__main__":
    main()
