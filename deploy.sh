#!/bin/bash
# Deployment script for HEIF/TTL Importer QGIS plugin

# Determine QGIS plugin directory based on OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    PLUGIN_DIR="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    PLUGIN_DIR="$HOME/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
else
    # Windows (Git Bash/WSL)
    PLUGIN_DIR="$APPDATA/QGIS/QGIS3/profiles/default/python/plugins"
fi

TARGET_DIR="$PLUGIN_DIR/heif_ttl_importer"

echo "Deploying HEIF/TTL Importer to: $TARGET_DIR"

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Copy plugin files
echo "Copying plugin files..."
cp -v __init__.py "$TARGET_DIR/"
cp -v heif_ttl_importer.py "$TARGET_DIR/"
cp -v heif_ttl_dialog.py "$TARGET_DIR/"
cp -v heif_ttl_dialog_base.ui "$TARGET_DIR/"
cp -v ttl_parser.py "$TARGET_DIR/"
cp -v heif_processor.py "$TARGET_DIR/"
cp -v iso19115_4_metadata.py "$TARGET_DIR/"
cp -v stac_converter.py "$TARGET_DIR/"
cp -v osm_fetcher.py "$TARGET_DIR/"
cp -v ido_annotator.py "$TARGET_DIR/"
cp -v metadata.txt "$TARGET_DIR/"
cp -v README.md "$TARGET_DIR/"
cp -v LICENSE "$TARGET_DIR/"

# Copy icon if exists
if [ -f "icon.png" ]; then
    cp -v icon.png "$TARGET_DIR/"
fi

# Copy SWIG binding package (compiled .so + Python wrapper)
if [ -d "libheif_binding" ]; then
    echo "Copying libheif_binding..."
    mkdir -p "$TARGET_DIR/libheif_binding"
    cp -v libheif_binding/__init__.py "$TARGET_DIR/libheif_binding/"
    # Copy compiled extension if present
    if ls libheif_binding/_libheif_core*.so 2>/dev/null | grep -q .; then
        cp -v libheif_binding/_libheif_core*.so "$TARGET_DIR/libheif_binding/"
        cp -v libheif_binding/libheif_core.py  "$TARGET_DIR/libheif_binding/"
        echo "  ✓ SWIG extension (.so) included"
    else
        echo "  ⚠ SWIG extension not compiled — heif_processor.py will fall back to byte-scan."
        echo "    To build: cd libheif_binding && ./build.sh"
    fi
fi

echo ""
echo "Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Restart QGIS"
echo "2. Go to Plugins → Manage and Install Plugins"
echo "3. Enable 'QGIS Raster Manager'"
echo ""
echo "Note: Make sure you have installed the required dependencies:"
echo "  pip install pillow pillow-heif gdal"
