#!/bin/bash
# package_release.sh — Build a QGIS-compatible release ZIP for GIMI Imagery Workbench.
#
# The ZIP can be installed on ANY platform (Windows, macOS, Linux) via:
#   QGIS → Plugins → Manage and Install Plugins → Install from ZIP
#
# Usage:
#   bash package_release.sh [--version X.Y.Z]
#
# Output:
#   dist/heif_ttl_importer-<version>.zip
#   dist/heif_ttl_importer-latest.zip   (symlink / copy)

set -euo pipefail

PLUGIN_ID="heif_ttl_importer"
DIST_DIR="$(pwd)/dist"

# ── Resolve version ────────────────────────────────────────────────────
VERSION=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    # Read from metadata.txt
    VERSION=$(grep -E '^version=' metadata.txt 2>/dev/null | head -1 | cut -d= -f2 | tr -d '[:space:]')
    if [[ -z "$VERSION" ]]; then
        VERSION="1.0.0"
    fi
fi

ZIP_NAME="${PLUGIN_ID}-${VERSION}.zip"
LATEST_NAME="${PLUGIN_ID}-latest.zip"

echo "=== GIMI Imagery Workbench — release packager ==="
echo "  Plugin ID : $PLUGIN_ID"
echo "  Version   : $VERSION"
echo "  Output    : $DIST_DIR/$ZIP_NAME"
echo ""

# ── Files to include ───────────────────────────────────────────────────
PLUGIN_FILES=(
    __init__.py
    heif_ttl_importer.py
    heif_ttl_dialog.py
    heif_ttl_dialog_base.ui
    ttl_parser.py
    heif_processor.py
    iso19115_4_metadata.py
    stac_converter.py
    osm_fetcher.py
    ido_annotator.py
    dji_adapter.py
    drone_mf_attributes.py
    hsi_adapter.py
    cs_api_client.py
    metadata.txt
    README.md
    LICENSE
    icon.png
    local_secrets.example.py
)

# ── Build in a temp staging directory ─────────────────────────────────
STAGING=$(mktemp -d)
trap 'rm -rf "$STAGING"' EXIT

STAGE_PLUGIN="$STAGING/$PLUGIN_ID"
mkdir -p "$STAGE_PLUGIN"

echo "Staging plugin files…"
for f in "${PLUGIN_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        cp "$f" "$STAGE_PLUGIN/"
        echo "  + $f"
    else
        echo "  [warn] $f not found — skipped"
    fi
done

# libheif_binding (Python package + compiled .so if present)
if [[ -d "libheif_binding" ]]; then
    mkdir -p "$STAGE_PLUGIN/libheif_binding"
    cp libheif_binding/__init__.py "$STAGE_PLUGIN/libheif_binding/"
    echo "  + libheif_binding/__init__.py"

    # Include compiled extension for the current platform only if present.
    # Windows releases: copy .pyd files; Linux/macOS: .so files.
    for ext in pyd so; do
        if ls libheif_binding/*."$ext" 2>/dev/null | grep -q .; then
            cp libheif_binding/*."$ext" "$STAGE_PLUGIN/libheif_binding/"
            cp libheif_binding/libheif_core.py "$STAGE_PLUGIN/libheif_binding/" 2>/dev/null || true
            echo "  + libheif_binding/*.${ext} (compiled extension)"
        fi
    done
fi

# Rename local_secrets.example.py → local_secrets.py  (default install)
if [[ -f "$STAGE_PLUGIN/local_secrets.example.py" ]]; then
    cp "$STAGE_PLUGIN/local_secrets.example.py" "$STAGE_PLUGIN/local_secrets.py"
    echo "  + local_secrets.py (seeded from example)"
fi

# ── Create ZIP ─────────────────────────────────────────────────────────
mkdir -p "$DIST_DIR"
ZIP_PATH="$DIST_DIR/$ZIP_NAME"

# Remove stale ZIP
rm -f "$ZIP_PATH"

pushd "$STAGING" >/dev/null
zip -r "$ZIP_PATH" "$PLUGIN_ID/" \
    --exclude "*/__pycache__/*" \
    --exclude "*/.git/*" \
    --exclude "*.pyc"
popd >/dev/null

# Symlink / copy as latest
cp "$ZIP_PATH" "$DIST_DIR/$LATEST_NAME"

ZIP_SIZE=$(du -sh "$ZIP_PATH" | cut -f1)
echo ""
echo "=== Done ==="
echo "  $DIST_DIR/$ZIP_NAME  ($ZIP_SIZE)"
echo "  $DIST_DIR/$LATEST_NAME"
echo ""
echo "Install on QGIS (any platform):"
echo "  Plugins → Manage and Install Plugins → Install from ZIP"
echo ""
echo "Or use the Windows PowerShell installer:"
echo "  powershell -ExecutionPolicy Bypass -File install_windows.ps1"
