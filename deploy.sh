#!/bin/bash
# Deployment script for GIMI Imagery Workbench QGIS plugin
# Requires GDAL >= 3.13.0 and Grok >= 20.3 for JP2GROK support.
# macOS quick install:  brew install gdal grok
# (GDAL Homebrew formula links against Grok since GDAL 3.13)

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[info]${RESET}  $*"; }
ok()      { echo -e "${GREEN}[  ok]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[warn]${RESET}  $*"; }
error()   { echo -e "${RED}[fail]${RESET}  $*"; }
section() { echo -e "\n${BOLD}$*${RESET}"; }

# ── ask_install <package> <description> ──────────────────────────────
# Prompts the user for permission to install a Homebrew package.
# Returns 0 if install succeeded or was already present, 1 if skipped.
ask_install() {
    local pkg="$1"
    local desc="$2"
    echo -e "\n${YELLOW}[missing]${RESET}  ${BOLD}${pkg}${RESET} — ${desc}"
    printf "  Install with 'brew install %s'? [y/N] " "$pkg"
    local ans
    read -r ans
    case "$ans" in
        [yY]|[yY][eE][sS])
            if ! command -v brew &>/dev/null; then
                error "Homebrew not found. Install from https://brew.sh then re-run deploy.sh"
                return 1
            fi
            info "Running: brew install ${pkg}"
            if brew install "$pkg"; then
                ok "${pkg} installed."
                return 0
            else
                error "brew install ${pkg} failed. See output above."
                return 1
            fi
            ;;
        *)
            warn "Skipping ${pkg}. Some plugin features may be unavailable."
            return 1
            ;;
    esac
}

# ── GDAL version check ────────────────────────────────────────────────
section "=== Checking GDAL ==="
GDAL_MIN_MAJOR=3; GDAL_MIN_MINOR=13

_gdal_version_ok=false
_gdal_found=false

if command -v gdal-config &>/dev/null; then
    _gdal_found=true
    GDAL_VER=$(gdal-config --version 2>/dev/null || echo "0.0.0")
    GDAL_MAJOR=$(echo "$GDAL_VER" | cut -d. -f1)
    GDAL_MINOR=$(echo "$GDAL_VER" | cut -d. -f2)
    info "Found GDAL ${GDAL_VER}"
    if [[ "$GDAL_MAJOR" -gt "$GDAL_MIN_MAJOR" ]] || \
       { [[ "$GDAL_MAJOR" -eq "$GDAL_MIN_MAJOR" ]] && [[ "$GDAL_MINOR" -ge "$GDAL_MIN_MINOR" ]]; }; then
        ok "GDAL ${GDAL_VER} satisfies requirement (>= ${GDAL_MIN_MAJOR}.${GDAL_MIN_MINOR})"
        _gdal_version_ok=true
    else
        warn "GDAL ${GDAL_VER} is older than required ${GDAL_MIN_MAJOR}.${GDAL_MIN_MINOR}.x"
        warn "JP2GROK driver is only available in GDAL >= 3.13. The plugin will work"
        warn "but will fall back to JP2OpenJPEG for JPEG-2000 output."
        printf "\n  Upgrade GDAL to >= 3.13 via 'brew upgrade gdal'? [y/N] "
        read -r _ans
        case "$_ans" in
            [yY]|[yY][eE][sS])
                if command -v brew &>/dev/null; then
                    info "Running: brew upgrade gdal"
                    brew upgrade gdal && _gdal_version_ok=true \
                        && ok "GDAL upgraded." \
                        || warn "brew upgrade gdal failed — continuing with existing GDAL."
                else
                    error "Homebrew not found. Install from https://brew.sh"
                fi
                ;;
            *) warn "Keeping existing GDAL ${GDAL_VER}." ;;
        esac
    fi
else
    warn "gdal-config not found — GDAL may not be installed or not on PATH."
    ask_install "gdal" "Geospatial Data Abstraction Library (required)" && _gdal_version_ok=true || true
fi

# ── Grok (libgrok / grk_compress) check ──────────────────────────────
section "=== Checking Grok JP2 library ==="
_grok_found=false

# grk_compress is the Grok command-line encoder; its presence confirms the library is installed.
if command -v grk_compress &>/dev/null; then
    GROK_VER=$(grk_compress --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "unknown")
    ok "Grok found (${GROK_VER}) — JP2GROK driver will be active in GDAL >= 3.13"
    _grok_found=true
else
    # Also check for the library itself (Homebrew installs libgrok)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if brew list grok &>/dev/null 2>&1; then
            ok "Grok Homebrew package is installed (grk_compress not on PATH — likely fine)."
            _grok_found=true
        fi
    fi

    if ! $_grok_found; then
        ask_install "grok" \
            "World's leading open-source JPEG 2000 codec; enables JP2GROK driver in GDAL 3.13+" \
            && _grok_found=true || true
    fi
fi

if ! $_grok_found; then
    warn "Grok not installed. The plugin will use JP2OpenJPEG for JPEG-2000 output."
    warn "For HTJ2K + TLM/PLT random-access JP2, install later: brew install grok"
fi

# ── GDAL JP2GROK driver probe ─────────────────────────────────────────
section "=== Probing GDAL JP2GROK driver ==="
if $_gdal_version_ok && $_grok_found; then
    if python3 -c "from osgeo import gdal; assert gdal.GetDriverByName('JP2GROK') is not None" 2>/dev/null; then
        ok "JP2GROK driver is compiled into the running GDAL — optimal JPEG-2000 output enabled."
    else
        warn "JP2GROK driver NOT found in the running GDAL Python bindings."
        warn "This usually means the GDAL Python package (osgeo) is a different build"
        warn "than the gdal-config / grk_compress on PATH."
        warn "The QGIS embedded GDAL will be probed again at plugin startup."
    fi
elif $_gdal_version_ok && ! $_grok_found; then
    warn "GDAL >= 3.13 present but Grok not installed — JP2GROK driver unavailable."
fi

# ── Determine QGIS plugin directory ──────────────────────────────────
section "=== Deploying plugin files ==="
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLUGIN_DIR="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLUGIN_DIR="$HOME/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
else
    PLUGIN_DIR="$APPDATA/QGIS/QGIS3/profiles/default/python/plugins"
fi

TARGET_DIR="$PLUGIN_DIR/heif_ttl_importer"

info "Target: $TARGET_DIR"

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Clear stale Python bytecode so QGIS always loads fresh .py files
find "$TARGET_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$TARGET_DIR" -name "*.pyc" -delete 2>/dev/null || true

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
cp -v dji_adapter.py "$TARGET_DIR/"
cp -v drone_mf_attributes.py "$TARGET_DIR/"
cp -v hsi_adapter.py "$TARGET_DIR/"
cp -v cs_api_client.py "$TARGET_DIR/"
cp -v metadata.txt "$TARGET_DIR/"
cp -v README.md "$TARGET_DIR/"
cp -v LICENSE "$TARGET_DIR/"
# Copy local_secrets template (never overwrite an existing local_secrets.py,
# but add any missing keys that appear in the example file).
if [ ! -f "$TARGET_DIR/local_secrets.py" ]; then
    cp -v local_secrets.example.py "$TARGET_DIR/local_secrets.py"
    echo "local_secrets.py -> $TARGET_DIR/local_secrets.py  (seeded from example)"
else
    # Patch: add keys that are in the example but absent in the deployed file
    _patched=0
    while IFS= read -r _line; do
        _key=$(echo "$_line" | sed 's/[[:space:]]*=.*//')
        if [ -n "$_key" ] && ! grep -q "^${_key}\s*=" "$TARGET_DIR/local_secrets.py"; then
            echo "$_line" >> "$TARGET_DIR/local_secrets.py"
            echo "[info]  Added missing key '${_key}' to deployed local_secrets.py"
            _patched=1
        fi
    done < <(grep -E '^[A-Z_]+\s*=' local_secrets.example.py)
    if [ "$_patched" -eq 0 ]; then
        echo "[info]  local_secrets.py already up-to-date (no new keys to add)"
    fi
fi

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
        ok "SWIG extension (.so) included"
    else
        warn "SWIG extension not compiled — heif_processor.py will fall back to byte-scan."
        echo "    To build: cd libheif_binding && ./build.sh"
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────
section "=== Deployment summary ==="
ok "Plugin files copied to: $TARGET_DIR"
echo ""
echo -e "  GDAL >= 3.13 : $(${_gdal_version_ok} && echo -e "${GREEN}yes${RESET}" || echo -e "${YELLOW}no / not confirmed${RESET}")"
echo -e "  Grok library : $(${_grok_found}      && echo -e "${GREEN}yes${RESET}" || echo -e "${YELLOW}no (JP2OpenJPEG fallback)${RESET}")"
echo ""
echo "Next steps:"
echo "  1. Restart QGIS"
echo "  2. Plugins → Manage and Install Plugins → Installed → enable 'GIMI Imagery Workbench'"
echo ""
echo "Python dependencies (if not already installed in QGIS Python):"
echo "  pip install pillow pillow-heif"

