# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
GIMI Imagery Workbench
A QGIS plugin for importing any GDAL-readable raster and exporting to any GDAL-writable format,
with optional TTL/RDF metadata georeferencing support.
"""

# ---------------------------------------------------------------------------
# Pre-emptive NumPy ABI guard
# ---------------------------------------------------------------------------
# QGIS-LTR 3.40.x ships NumPy 2.0.x but some packages in its site-packages
# were compiled against NumPy 1.x.  Importing them causes:
#     AttributeError: _ARRAY_API not found  (+ a NumPy compatibility warning
#     printed to stderr that QGIS's error handler reports as a plugin crash).
#
# Known broken versions (need NumPy >= 2.x-compatible rebuild):
#   matplotlib < 3.7   (3.3.0 in QGIS-LTR 3.40.5)
#   scipy      < 1.11  (1.5.1 in QGIS-LTR 3.40.5)
#
# We inspect dist-info metadata (no C code runs) and pre-tombstone any
# package whose installed version is too old for NumPy 2.x.  Tombstoning
# means every subsequent `import <pkg>` in ANY plugin raises a clean
# ImportError instead of crashing the QGIS Python interpreter.
import sys as _sys

def _pkg_version_tuple(name: str):
    """Return (major, minor) int tuple for an installed package, or None."""
    try:
        import importlib.metadata as _im
        parts = _im.version(name).split('.')
        return tuple(int(x) for x in parts[:2])
    except Exception:
        return None

def _numpy_major() -> int:
    try:
        import numpy as _np
        return int(_np.__version__.split('.')[0])
    except Exception:
        return 0

if _numpy_major() >= 2:
    # Packages that require numpy >= 2-compatible C extensions.
    # Tombstone only the known-broken versions; leave newer installs alone.
    _NEEDS_TOMBSTONE = {
        'matplotlib': (3, 7),   # < 3.7 built for numpy 1.x
        'scipy':      (1, 11),  # < 1.11 built for numpy 1.x
    }
    for _pkg, _min_ver in _NEEDS_TOMBSTONE.items():
        if _pkg in _sys.modules:
            continue  # already loaded by another plugin – don't touch
        _ver = _pkg_version_tuple(_pkg)
        if _ver is not None and _ver < _min_ver:
            # Tombstone: any future import raises clean ImportError, no stderr noise
            _sys.modules[_pkg] = None  # type: ignore[assignment]
    del _pkg, _min_ver, _ver

del _pkg_version_tuple, _numpy_major


def classFactory(iface):
    from .heif_ttl_importer import HEIFTTLImporter
    return HEIFTTLImporter(iface)
