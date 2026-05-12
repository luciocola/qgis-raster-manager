# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
hsi_adapter.py – thin bridge to the asbestos_hsi_manager (or any sibling HSI plugin).

Adds the parent plugins directory to sys.path so that
``asbestos_hsi_manager.hsi_loader`` can be imported without requiring the
plugin to be formally installed.  Degrades gracefully when the sibling plugin
is absent — all public names remain importable; ``HSI_AVAILABLE`` is False.

Public API
----------
``HSI_AVAILABLE`` : bool
    True when the sibling HSI plugin was found and imported successfully.

``HSI_ERROR`` : str
    Non-empty error string when the import failed; empty otherwise.

``probe_hsi_file(filepath)`` → dict
    Quick band-count / spatial-dims / wavelength-range probe.

``load_hsi_cube(filepath)`` → (cube, wavelengths, crs_wkt, geotransform)
    Load an HSI file as a ``(bands, H, W) float32`` NumPy array.
    Returns None components on failure.

``make_false_colour(cube, wavelengths, method)`` → ndarray | None
    Produce a ``(H, W, 3) uint8`` false-colour RGB from an HSI cube.
    *method* is ``'pca'`` (default) or ``'band_select'``.
"""
from __future__ import annotations

import os
import re
import sys
from typing import List, Optional, Tuple

# numpy is imported lazily (inside functions) to avoid any module-level ABI
# conflict when loaded inside QGIS's embedded Python interpreter.

# ---------------------------------------------------------------------------
# Locate sibling plugin directory (same as dji_adapter.py pattern)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)   # parent directory of both plugins

if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

# ---------------------------------------------------------------------------
# Graceful import of the sibling plugin's HSILoader
# ---------------------------------------------------------------------------
HSI_AVAILABLE: bool = False
HSI_ERROR: str = ""

_HSILoader = None

try:
    from asbestos_hsi_manager.hsi_loader import HSILoader as _HSILoader  # type: ignore[import]
    HSI_AVAILABLE = True
except (ImportError, AttributeError, Exception) as _e:
    # AttributeError: _ARRAY_API not found when hsi_loader's C deps (numpy, scipy)
    # were compiled against a different NumPy ABI than QGIS's embedded interpreter.
    HSI_ERROR = str(_e)
    HSI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Internal helper – parse ENVI .hdr wavelength list
# ---------------------------------------------------------------------------

def _parse_envi_wavelengths(filepath: str) -> Optional[List[float]]:
    """Return wavelength list (nm) from a co-located ENVI .hdr file, or None."""
    base = os.path.splitext(filepath)[0]
    hdr = base + '.hdr'
    if not os.path.exists(hdr):
        return None
    try:
        with open(hdr, 'r', encoding='utf-8', errors='ignore') as fh:
            content = fh.read()
        m = re.search(r'wavelength\s*=\s*\{([^}]+)\}', content, re.IGNORECASE)
        if m:
            return [float(v.strip()) for v in m.group(1).split(',') if v.strip()]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Public: probe_hsi_file
# ---------------------------------------------------------------------------

def probe_hsi_file(filepath: str) -> dict:
    """Quick probe: return band count, spatial dimensions, and wavelength range.

    Always returns a dict with keys:
        path, bands, width, height,
        wavelength_min, wavelength_max, has_wavelengths, format
    """
    info: dict = {
        'path': filepath,
        'bands': 0,
        'width': 0,
        'height': 0,
        'wavelength_min': None,
        'wavelength_max': None,
        'has_wavelengths': False,
        'format': 'Unknown',
    }
    try:
        from osgeo import gdal
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        ds = gdal.Open(filepath, gdal.GA_ReadOnly)
        gdal.PopErrorHandler()
        if ds is not None:
            info['bands'] = ds.RasterCount
            info['width'] = ds.RasterXSize
            info['height'] = ds.RasterYSize
            info['format'] = ds.GetDriver().ShortName
            ds = None
    except Exception:
        pass

    wavelengths = _parse_envi_wavelengths(filepath)
    if wavelengths:
        info['wavelength_min'] = min(wavelengths)
        info['wavelength_max'] = max(wavelengths)
        info['has_wavelengths'] = True

    return info


# ---------------------------------------------------------------------------
# Public: load_hsi_cube
# ---------------------------------------------------------------------------

def load_hsi_cube(
    filepath: str,
) -> Tuple[Optional[np.ndarray], Optional[List[float]], Optional[str], Optional[tuple]]:
    """Load an HSI file as a (bands, H, W) float32 NumPy cube.

    Tries GDAL first (handles GeoTIFF, ENVI, HDF5 via GDAL drivers).
    Falls back to ``HSILoader.read_hsi_data()`` from the sibling plugin when
    GDAL cannot open the file.

    Returns
    -------
    cube : ndarray or None
        Shape ``(bands, H, W)``, dtype float32.
    wavelengths : list[float] or None
        Band centre wavelengths in nm (from ENVI .hdr or GDAL band metadata).
    crs_wkt : str or None
        Well-Known Text CRS string, or None if not present.
    geotransform : tuple or None
        GDAL 6-element geotransform, or None if absent / identity.
    """
    import numpy as np  # lazy import — avoids top-level ABI conflict in QGIS
    wavelengths: Optional[List[float]] = None
    crs_wkt: Optional[str] = None
    geotransform: Optional[tuple] = None
    cube = None

    # ── GDAL path ──────────────────────────────────────────────────────
    try:
        from osgeo import gdal, osr
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        ds = gdal.Open(filepath, gdal.GA_ReadOnly)
        gdal.PopErrorHandler()
        if ds is not None:
            bands = ds.RasterCount
            h = ds.RasterYSize
            w = ds.RasterXSize
            cube = np.zeros((bands, h, w), dtype=np.float32)
            for b in range(bands):
                # Use ReadRaster + np.frombuffer instead of ReadAsArray to avoid
                # the gdal_array C-extension which crashes on NumPy 2.x / 1.x ABI
                # mismatch (AttributeError: _ARRAY_API not found).
                raw = ds.GetRasterBand(b + 1).ReadRaster(
                    0, 0, w, h, buf_type=gdal.GDT_Float32
                )
                cube[b] = np.frombuffer(raw, dtype=np.float32).reshape(h, w)

            # Wavelengths from GDAL band metadata
            wl_list: List[float] = []
            for b in range(bands):
                meta = ds.GetRasterBand(b + 1).GetMetadata()
                wl = meta.get('wavelength') or meta.get('Wavelength')
                if wl:
                    try:
                        wl_list.append(float(wl))
                    except ValueError:
                        break
            if len(wl_list) == bands:
                wavelengths = wl_list

            # CRS
            proj = ds.GetProjection()
            if proj:
                crs_wkt = proj

            # Geotransform
            gt = ds.GetGeoTransform()
            _identity = (0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
            if gt and gt != _identity and not all(v == 0 for v in gt):
                geotransform = gt

            ds = None
    except Exception as exc:
        print(f"[hsi_adapter] GDAL load error: {exc}")

    # ── Fallback: HSILoader from sibling plugin ────────────────────────
    if cube is None and HSI_AVAILABLE and _HSILoader is not None:
        try:
            loader = _HSILoader()
            raw = loader.read_hsi_data(filepath)   # (H, W, B)
            if raw is not None:
                cube = np.transpose(raw.astype(np.float32), (2, 0, 1))  # → (B, H, W)
        except Exception as exc:
            print(f"[hsi_adapter] HSILoader fallback error: {exc}")

    # ── ENVI .hdr wavelengths (always try, overrides GDAL metadata if richer) ──
    envi_wl = _parse_envi_wavelengths(filepath)
    if envi_wl and cube is not None and len(envi_wl) == cube.shape[0]:
        wavelengths = envi_wl

    return cube, wavelengths, crs_wkt, geotransform


# ---------------------------------------------------------------------------
# Public: make_false_colour
# ---------------------------------------------------------------------------

def make_false_colour(
    cube,
    wavelengths: Optional[List[float]] = None,
    method: str = 'pca',
):
    """Produce a (H, W, 3) uint8 false-colour RGB from an HSI cube (B, H, W).

    Parameters
    ----------
    cube : ndarray (B, H, W) float32
    wavelengths : list of B floats, band centres in nm (optional)
    method : 'pca' (default) or 'band_select'
        'pca'         — compute first 3 principal components across the
                        spectral axis; good general-purpose false-colour.
        'band_select' — select bands closest to visible R≈650nm,
                        G≈550nm, B≈450nm; requires wavelengths.
                        Falls back to PCA if wavelengths are absent.

    Returns
    -------
    ndarray (H, W, 3) uint8, or None on error.
    """
    try:
        import numpy as np  # lazy import — avoids top-level ABI conflict in QGIS
        bands, h, w = cube.shape

        indices: Optional[List[int]] = None

        # ── band_select ────────────────────────────────────────────────
        if method == 'band_select' and wavelengths and len(wavelengths) == bands:
            targets = [650.0, 550.0, 450.0]   # R, G, B targets in nm
            indices = [
                min(range(bands), key=lambda i: abs(wavelengths[i] - t))
                for t in targets
            ]

        # ── PCA ────────────────────────────────────────────────────────
        elif method == 'pca' or indices is None:
            if bands < 3:
                # Not enough bands for PCA → replicate
                indices = list(range(bands))
                while len(indices) < 3:
                    indices.append(indices[-1])
            else:
                pixels = cube.reshape(bands, -1).T.astype(np.float64)   # (N, B)
                mean = pixels.mean(axis=0)
                centred = pixels - mean
                cov = np.cov(centred.T)
                from numpy import linalg as la
                _, vecs = la.eigh(cov)
                comps = vecs[:, -3:][:, ::-1]       # (B, 3)
                projected = centred @ comps            # (N, 3)
                rgb_flat = projected.T.reshape(3, h, w)
                result = np.zeros((h, w, 3), dtype=np.uint8)
                for i in range(3):
                    ch = rgb_flat[i]
                    lo, hi = np.percentile(ch, 2), np.percentile(ch, 98)
                    if hi > lo:
                        ch = np.clip((ch - lo) / (hi - lo) * 255.0, 0, 255)
                    else:
                        ch = np.zeros_like(ch)
                    result[:, :, i] = ch.astype(np.uint8)
                return result

        # ── index-based render (band_select or fallback) ───────────────
        result = np.zeros((h, w, 3), dtype=np.uint8)
        for out_idx, band_idx in enumerate(indices):
            ch = cube[band_idx].astype(np.float32)
            lo, hi = np.percentile(ch, 2), np.percentile(ch, 98)
            if hi > lo:
                ch = np.clip((ch - lo) / (hi - lo) * 255.0, 0, 255)
            else:
                ch = np.zeros_like(ch)
            result[:, :, out_idx] = ch.astype(np.uint8)
        return result

    except Exception as exc:
        print(f"[hsi_adapter] make_false_colour error: {exc}")
        return None
