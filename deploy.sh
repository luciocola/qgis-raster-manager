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
cp -v metadata.txt "$TARGET_DIR/"
cp -v README.md "$TARGET_DIR/"

# Copy icon if exists
if [ -f "icon.png" ]; then
    cp -v icon.png "$TARGET_DIR/"
fi

echo ""
echo "Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Restart QGIS"
echo "2. Go to Plugins → Manage and Install Plugins"
echo "3. Enable 'HEIF/TTL Imagery Importer'"
echo ""
echo "Note: Make sure you have installed the required dependencies:"
echo "  pip install pillow pillow-heif gdal"
