#!/bin/bash
# ═══════════════════════════════════════════════════════════
# VEO Pro Max — macOS Post-Build Script
# ═══════════════════════════════════════════════════════════
#
# Run AFTER build_release_macos.py for additional packaging:
# 1. Create .icns icon from PNG (if needed)
# 2. Ad-hoc code sign
# 3. Create DMG with drag-and-drop install
# 4. Gatekeeper bypass helper
#
# Usage:
#   chmod +x post_build.sh
#   ./post_build.sh [version]   # e.g., ./post_build.sh 3.1.0
# ═══════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$BASE_DIR/04.2 - macOS final build"
APP_BUNDLE="$OUTPUT_DIR/VEO_Pro_Max.app"

VERSION=${1:-"0.0.0"}

echo "═══════════════════════════════════════"
echo "  VEO Pro Max — macOS Post-Build"
echo "  Version: $VERSION"
echo "  Architecture: $(uname -m)"
echo "═══════════════════════════════════════"

# ── Step 1: Check .app exists ──
if [ ! -d "$APP_BUNDLE" ]; then
    echo "❌ ERROR: $APP_BUNDLE not found!"
    echo "   Run build_release_macos.py first."
    exit 1
fi
echo "✅ Found: $APP_BUNDLE"

# ── Step 2: Create .icns from PNG (if icon.icns missing) ──
ICON_ICNS="$BASE_DIR/04 - MAC/assets/icon.icns"
ICON_PNG="$BASE_DIR/04 - MAC/assets/icon.png"

if [ ! -f "$ICON_ICNS" ] && [ -f "$ICON_PNG" ]; then
    echo ""
    echo "[2] Creating .icns from icon.png..."
    ICONSET_DIR=$(mktemp -d)/icon.iconset
    mkdir -p "$ICONSET_DIR"
    
    sips -z 16 16     "$ICON_PNG" --out "$ICONSET_DIR/icon_16x16.png"      2>/dev/null
    sips -z 32 32     "$ICON_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png"   2>/dev/null
    sips -z 32 32     "$ICON_PNG" --out "$ICONSET_DIR/icon_32x32.png"      2>/dev/null
    sips -z 64 64     "$ICON_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png"   2>/dev/null
    sips -z 128 128   "$ICON_PNG" --out "$ICONSET_DIR/icon_128x128.png"    2>/dev/null
    sips -z 256 256   "$ICON_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" 2>/dev/null
    sips -z 256 256   "$ICON_PNG" --out "$ICONSET_DIR/icon_256x256.png"    2>/dev/null
    sips -z 512 512   "$ICON_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" 2>/dev/null
    sips -z 512 512   "$ICON_PNG" --out "$ICONSET_DIR/icon_512x512.png"    2>/dev/null
    sips -z 1024 1024 "$ICON_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" 2>/dev/null
    
    iconutil -c icns "$ICONSET_DIR" -o "$ICON_ICNS"
    echo "  ✅ Created: $ICON_ICNS"
    
    # Copy into .app bundle
    cp "$ICON_ICNS" "$APP_BUNDLE/Contents/Resources/"
    echo "  ✅ Copied into .app bundle"
else
    echo "[2] Icon: $([ -f "$ICON_ICNS" ] && echo "✅ .icns exists" || echo "⚠️  No icon.png found")"
fi

# ── Step 3: Ad-hoc Code Sign ──
echo ""
echo "[3] Code signing (ad-hoc)..."

# Sign frameworks first
if [ -d "$APP_BUNDLE/Contents/Frameworks" ]; then
    find "$APP_BUNDLE/Contents/Frameworks" -name "*.dylib" -o -name "*.so" | while read lib; do
        codesign --force --sign - --timestamp "$lib" 2>/dev/null || true
    done
    find "$APP_BUNDLE/Contents/Frameworks" -name "*.framework" -type d | while read fw; do
        codesign --force --sign - --timestamp --deep "$fw" 2>/dev/null || true
    done
    echo "  ✅ Frameworks signed"
fi

# Sign main app
codesign --force --sign - --timestamp --deep --options runtime "$APP_BUNDLE" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "  ✅ App signed (ad-hoc)"
else
    echo "  ⚠️  Signing failed — app may trigger Gatekeeper warning"
fi

# Verify
codesign -v "$APP_BUNDLE" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "  ✅ Signature valid"
else
    echo "  ⚠️  Signature verification failed"
fi

# ── Step 4: Create DMG ──
echo ""
echo "[4] Creating DMG installer..."
DMG_PATH="$OUTPUT_DIR/VEO_Pro_Max_v${VERSION}_macOS.dmg"

if [ -f "$DMG_PATH" ]; then
    rm "$DMG_PATH"
fi

DMG_STAGING=$(mktemp -d)
cp -R "$APP_BUNDLE" "$DMG_STAGING/VEO Pro Max.app"
ln -s /Applications "$DMG_STAGING/Applications"

hdiutil create "$DMG_PATH" \
    -volname "VEO Pro Max" \
    -srcfolder "$DMG_STAGING" \
    -ov -format UDZO 2>/dev/null

if [ $? -eq 0 ]; then
    SIZE_MB=$(du -m "$DMG_PATH" | cut -f1)
    echo "  ✅ Created: $(basename "$DMG_PATH") (${SIZE_MB} MB)"
else
    echo "  ❌ DMG creation failed"
fi

rm -rf "$DMG_STAGING"

# ── Step 5: Print summary ──
echo ""
echo "═══════════════════════════════════════"
echo "  ✅ POST-BUILD COMPLETE"
echo ""
echo "  📦 App:  $APP_BUNDLE"
echo "  💿 DMG:  $DMG_PATH"
echo ""
echo "  📋 Distribution:"
echo "     ZIP: cd '$OUTPUT_DIR' && zip -r VEO_Pro_Max_v${VERSION}_macOS.zip VEO_Pro_Max.app"
echo ""
echo "  🔓 Gatekeeper bypass (unsigned builds):"
echo "     xattr -cr /Applications/VEO\\ Pro\\ Max.app"
echo "═══════════════════════════════════════"
