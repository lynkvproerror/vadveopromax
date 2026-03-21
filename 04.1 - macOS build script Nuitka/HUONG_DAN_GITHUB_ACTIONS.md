# ═══════════════════════════════════════════════════════════
# GitHub Actions — Hướng dẫn sử dụng Build macOS
# ═══════════════════════════════════════════════════════════
#
# KHÔNG CẦN MÁY MAC! GitHub Actions cung cấp macOS runner miễn phí.
#
# ── Cách 1: Manual Trigger (Đơn giản nhất) ──
#
#   1. Vào GitHub repo → tab "Actions"
#   2. Chọn workflow "Build macOS App" bên trái
#   3. Click "Run workflow" → chọn options → "Run workflow"
#   4. Chờ ~30-45 phút
#   5. Download artifact từ workflow run page
#
# ── Cách 2: Auto-trigger via Push ──
#
#   Sửa code trong "04 - MAC/" → git push → tự build
#   (Chỉ trigger khi push lên branch main hoặc build-macos)
#
# ── Cách 3: Release Tag ──
#
#   git tag v2.3.8-mac
#   git push origin v2.3.8-mac
#   → Build + tự tạo GitHub Release (draft)
#
# ── Sau khi build xong ──
#
#   1. Vào workflow run → tab "Artifacts"
#   2. Download "VEO-Pro-Max-macOS-v{VER}"
#   3. Unzip → VEO_Pro_Max_v{VER}_macOS.zip
#   4. Unzip → VEO_Pro_Max.app
#   5. Gửi cho user macOS
#
# ── User macOS cài đặt ──
#
#   1. Unzip file
#   2. Kéo "VEO Pro Max.app" vào /Applications
#   3. Right-click → Open → Open (bypass Gatekeeper lần đầu)
#   4. Hoặc: xattr -cr /Applications/VEO\ Pro\ Max.app
#
# ═══════════════════════════════════════════════════════════
