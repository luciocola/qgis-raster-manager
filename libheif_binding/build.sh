#!/usr/bin/env bash
# build.sh — Build the libheif_core SWIG extension in-place.
#
# Usage:
#   cd libheif_binding
#   ./build.sh
#
# After a successful build, libheif_core.py and _libheif_core*.so will be
# present in this directory and will be importable by heif_processor.py.
#
# Requirements:
#   - SWIG 4.0+         (brew install swig  /  apt install swig)
#   - libheif dev libs  (brew install libheif  /  apt install libheif-dev)
#   - Python 3.8+

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Verify SWIG is available ───────────────────────────────────────────
if ! command -v swig &>/dev/null; then
    echo "ERROR: swig not found."
    echo "  macOS : brew install swig"
    echo "  Linux : apt install swig"
    exit 1
fi
echo "SWIG: $(swig -version | head -1)"

# ── Verify libheif headers are reachable ──────────────────────────────
HEIF_HEADER=""
for candidate in \
    /opt/homebrew/include/libheif/heif.h \
    /usr/local/include/libheif/heif.h \
    /usr/include/libheif/heif.h; do
    if [[ -f "$candidate" ]]; then
        HEIF_HEADER="$candidate"
        break
    fi
done

if [[ -z "$HEIF_HEADER" ]]; then
    echo "ERROR: libheif/heif.h not found."
    echo "  macOS : brew install libheif"
    echo "  Linux : apt install libheif-dev"
    exit 1
fi
echo "libheif header: $HEIF_HEADER"

# ── Build ─────────────────────────────────────────────────────────────
echo ""
echo "Building _libheif_core extension..."
python setup.py build_ext --inplace 2>&1

echo ""
echo "Build complete.  Generated files:"
ls -1 libheif_core.py _libheif_core*.so 2>/dev/null || true
echo ""
echo "Test the binding:"
echo "  python -c \"import libheif_core; print('OK')\""
