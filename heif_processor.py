# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
HEIF Image Processor - Converts HEIF images to GeoTIFF format
"""
import os
import tempfile
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, List
from pathlib import Path

try:
    from PIL import Image
    from pillow_heif import register_heif_opener
    import pillow_heif
    # Register HEIF format with PIL
    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False
    pillow_heif = None

try:
    import blake3
    BLAKE3_AVAILABLE = True
except ImportError:
    BLAKE3_AVAILABLE = False
    import hashlib

from osgeo import gdal, osr

# Import ISO 19115-4 metadata extractor
try:
    from .iso19115_4_metadata import ISO19115_4MetadataExtractor
    ISO19115_4_AVAILABLE = True
except ImportError:
    try:
        from iso19115_4_metadata import ISO19115_4MetadataExtractor
        ISO19115_4_AVAILABLE = True
    except ImportError:
        ISO19115_4_AVAILABLE = False

# Import the SWIG-generated libheif binding (optional — degrades gracefully)
try:
    from .libheif_binding import HeifContext as _HeifContext, SWIG_BINDING_AVAILABLE as _SWIG_OK
except ImportError:
    try:
        from libheif_binding import HeifContext as _HeifContext, SWIG_BINDING_AVAILABLE as _SWIG_OK  # type: ignore[no-redef]
    except ImportError:
        _HeifContext = None  # type: ignore[assignment,misc]
        _SWIG_OK = False


class HEIFProcessor:
    """Processes HEIF images and converts them to GeoTIFF with GCPs"""
    
    def __init__(self):
        self.temp_files = []
        self.internal_rdf = None
        self.internal_rdf_format = None
        self.heif_convert_cmd = None  # Will be set by check_heif_convert_available()
        self.heif_enc_cmd = None  # heif-enc for encoding
        self.tiling_mode = None  # 'grid', 'tili', or 'unci'
        self.supports_signed_int = False  # ISO/IEC 23001-17 signed integers (PR #1644)
        self.supports_sai = False  # Sample Auxiliary Information for GIMI
        self.export_format = 'GTIFF'  # 'GTIFF' or 'JP2'
        
    def is_heif_supported(self) -> bool:
        """Check if HEIF format is supported"""
        return HEIF_AVAILABLE
    
    def check_heif_enc_available(self) -> bool:
        """
        Check if heif-enc command-line tool is available.
        
        heif-enc provides advanced encoding features:
        - Tiled image encoding (grid, tili, unci modes)
        - Uncompressed codec with signed integer support
        - SAI (Sample Auxiliary Information) for GIMI content IDs
        - Multi-resolution pyramids
        - Image sequences with metadata tracks
        
        See: https://github.com/strukturag/libheif/wiki/heif%E2%80%90enc-Command-Line-Tool
        
        Returns:
            True if heif-enc is available, False otherwise
        """
        import subprocess
        
        for cmd in ['heif-enc', '/usr/local/bin/heif-enc', os.path.expanduser('~/Downloads/libheif/build/examples/heif-enc')]:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0 or 'heif-enc' in result.stdout or 'heif-enc' in result.stderr:
                    self.heif_enc_cmd = cmd
                    print(f"Found heif-enc at: {cmd}")
                    
                    # Check for advanced features in help output
                    help_result = subprocess.run([cmd, '--help'], 
                                                capture_output=True, 
                                                text=True, 
                                                timeout=5)
                    help_text = help_result.stdout + help_result.stderr
                    
                    # Check for tiling support
                    if '--tiled-input' in help_text:
                        print("  ✓ Tiled image encoding supported")
                    if '--unci' in help_text or '--uncompressed' in help_text:
                        print("  ✓ Uncompressed codec supported")
                        self.supports_signed_int = True  # PR #1644 feature
                    if '--sai-data-file' in help_text:
                        print("  ✓ SAI metadata supported (GIMI content IDs)")
                        self.supports_sai = True
                    
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        
        print("heif-enc not found. Advanced encoding features unavailable.")
        print("Install libheif and build with: cmake .. && make")
        print("See: https://github.com/strukturag/libheif")
        return False
    
    def check_heif_convert_available(self) -> bool:
        """
        Check if heif-convert command-line tool is available.
        
        Returns:
            True if heif-convert is available, False otherwise
        """
        import subprocess
        
        for cmd in ['heif-convert', '/usr/local/bin/heif-convert', os.path.expanduser('~/Downloads/libheif/build/examples/heif-convert')]:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0 or 'heif-convert' in result.stdout or 'heif-convert' in result.stderr:
                    self.heif_convert_cmd = cmd
                    print(f"Found heif-convert at: {cmd}")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        
        return False
    
    def calculate_file_hash(self, file_path: str) -> Tuple[str, str]:
        """
        Calculate cryptographic hash of file using BLAKE3 (preferred) or SHA256 (fallback).
        
        Args:
            file_path: Path to file to hash
            
        Returns:
            Tuple of (hash_value, hash_algorithm)
            hash_value includes multihash prefix (0x1e for BLAKE3, 0x12 for SHA256)
        """
        try:
            if BLAKE3_AVAILABLE:
                hasher = blake3.blake3()
                hash_algo = "blake3"
                # Multihash prefix for BLAKE3: 0x1e
                prefix = "1e20"  # 0x1e (blake3) + 0x20 (32 bytes)
            else:
                hasher = hashlib.sha256()
                hash_algo = "sha256"
                # Multihash prefix for SHA256: 0x12
                prefix = "1220"  # 0x12 (sha256) + 0x20 (32 bytes)
            
            # Read file in chunks
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            
            hash_value = prefix + hasher.hexdigest()
            return hash_value, hash_algo
            
        except Exception as e:
            print(f"Error calculating file hash: {e}")
            return "", "unknown"
    
    def detect_tiling_mode(self, heif_path: str) -> Optional[str]:
        """
        Detect the tiling mode used in a HEIF file.

        Tiling modes from libheif:
        - 'grid': Default method with best decoder compatibility (max 65535 tiles)
        - 'tili': Efficient tiling with little overhead (unlimited tiles, requires
                  libheif built with -DENABLE_EXPERIMENTAL_FEATURES=on; pending
                  inclusion in ISO 23008-12, Amd-2)
        - 'unci': ISO 23001-17 uncompressed codec internal tiling

        See: https://github.com/strukturag/libheif/wiki/heif%E2%80%90enc-Command-Line-Tool#tiling-modes

        IMPORTANT — implementation note
        ---------------------------------
        The clean approach is to use the libheif C API:

            heif_context_get_list_of_item_IDs(ctx, ids, count)

        and inspect each item's type (4-byte box type) via
        ``heif_context_get_image_handle()`` / ``heif_image_handle_get_item_type()``.
        The byte-scan fallback below is **fragile**: the four-byte strings 'grid',
        'tili', or 'unci' can legitimately appear anywhere in compressed image data,
        leading to false positives.  Conversely they may be stored in an ISO Base
        Media File Format box that is not in the first 16 KB, causing false negatives.

        Once pillow-heif exposes the libheif tile access API (in progress by the
        pillow-heif maintainer), this method should be rewritten to use that API.
        For now, ctypes bindings to libheif are used when available; keyword-scan
        is retained only as a last resort with a logged warning.

        Args:
            heif_path: Path to HEIF file

        Returns:
            Tiling mode string ('grid', 'tili', 'unci') or None if not tiled
        """
        # ------------------------------------------------------------------
        # Preferred path: SWIG binding → libheif C API
        # ------------------------------------------------------------------
        if _SWIG_OK and _HeifContext is not None:
            try:
                with _HeifContext.from_file(heif_path) as ctx:
                    mode = ctx.detect_tiling_mode()
                if mode is not None:
                    self.tiling_mode = mode
                    return mode
                # mode == None means no tiling detected via C API
                return None
            except Exception as _swig_err:
                print(f"[detect_tiling_mode] SWIG binding error: {_swig_err}")

        # ------------------------------------------------------------------
        # Last-resort: byte-scan (fragile — false-positive/negative risk)
        # WARNING: 4-byte strings may appear in compressed image data.
        # Build libheif_binding (./libheif_binding/build.sh) to avoid this path.
        # ------------------------------------------------------------------
        try:
            with open(heif_path, 'rb') as f:
                data = f.read(16384)  # Read first 16 KB

            # Scan for 4-byte box-type codes at ISOBMFF box boundaries would
            # require full box parsing.  This naive search is a heuristic only.
            if b'grid' in data:
                print("[detect_tiling_mode] WARNING: 'grid' found via byte-scan (heuristic)")
                self.tiling_mode = 'grid'
                return 'grid'
            if b'tili' in data:
                print("[detect_tiling_mode] WARNING: 'tili' found via byte-scan (heuristic)")
                self.tiling_mode = 'tili'
                return 'tili'
            if b'unci' in data:
                print("[detect_tiling_mode] WARNING: 'unci' found via byte-scan (heuristic)")
                self.tiling_mode = 'unci'
                return 'unci'

            return None
        except Exception as e:
            print(f"Error detecting tiling mode: {e}")
            return None
    
    def has_internal_rdf(self, heif_path: str) -> bool:
        """
        Check if HEIF file has internal RDF/XMP metadata.

        Supports both XML/RDF and Turtle formats (TB21 GIMI).

        IMPLEMENTATION NOTE
        -------------------
        The authoritative approach is to iterate over the ISO BMFF item list via
        the libheif C API::

            heif_context_get_list_of_item_IDs(ctx, ids, count)

        and inspect each item for a MIME content-type of ``text/turtle`` or
        ``application/rdf+xml``.  The command-line equivalent is::

            heif-dec --extract-mime-item text/turtle input.heif rdf_out.ttl
            # (--extract-mime-item was added in a recent libheif release)

        The byte-scan below is a fallback: it searches the raw file bytes for
        known RDF markers, which may produce false positives if those byte
        sequences appear in compressed media data.

        Args:
            heif_path: Path to HEIF file

        Returns:
            True if internal RDF metadata found, False otherwise
        """
        # ------------------------------------------------------------------
        # Preferred path: SWIG binding → libheif C API metadata block inspection
        # ------------------------------------------------------------------
        if _SWIG_OK and _HeifContext is not None:
            try:
                with _HeifContext.from_file(heif_path) as ctx:
                    _data, fmt = ctx.find_rdf_metadata()
                if fmt is not None:
                    self.internal_rdf_format = fmt
                    return True
                # Binding found no RDF — trust the API result
                return False
            except Exception as _swig_err:
                print(f"[has_internal_rdf] SWIG binding error: {_swig_err}")
                # Fall through to byte-scan below

        # ------------------------------------------------------------------
        # Fallback: byte-scan (fragile — false-positive/negative risk)
        # Build libheif_binding (./libheif_binding/build.sh) to avoid this path.
        # ------------------------------------------------------------------
        try:
            with open(heif_path, 'rb') as f:
                data = f.read()
                if b'<rdf:RDF' in data or b'<?xpacket' in data:
                    self.internal_rdf_format = 'xml'
                    return True
                if b'@prefix rdf:' in data or b'@prefix rdfs:' in data:
                    self.internal_rdf_format = 'turtle'
                    return True
                return False
        except Exception as e:
            print(f"Error checking for internal RDF: {e}")
            return False
    
    def extract_internal_rdf(self, heif_path: str) -> Optional[str]:
        """
        Extract internal RDF metadata from HEIF file.

        Args:
            heif_path: Path to HEIF file

        Returns:
            RDF content as string, or None if not found
        """
        # ------------------------------------------------------------------
        # Preferred path: SWIG binding → libheif C API metadata block read
        # ------------------------------------------------------------------
        if _SWIG_OK and _HeifContext is not None:
            try:
                with _HeifContext.from_file(heif_path) as ctx:
                    raw, fmt = ctx.find_rdf_metadata()
                if raw is not None and fmt is not None:
                    text = raw.decode('utf-8', errors='ignore')
                    self.internal_rdf = text
                    self.internal_rdf_format = fmt
                    print(f"[extract_internal_rdf] SWIG binding: {len(text)} chars ({fmt})")
                    return self.internal_rdf
                return None
            except Exception as _swig_err:
                print(f"[extract_internal_rdf] SWIG binding error: {_swig_err}")
                # Fall through to byte-scan below

        # ------------------------------------------------------------------
        # Fallback: byte-scan (fragile — false-positive/negative risk)
        # Build libheif_binding (./libheif_binding/build.sh) to avoid this path.
        # ------------------------------------------------------------------
        try:
            with open(heif_path, 'rb') as f:
                data = f.read()

                # Extract XML/RDF format
                if b'<rdf:RDF' in data:
                    idx = data.find(b'<rdf:RDF')
                    end_idx = data.find(b'</rdf:RDF>', idx)
                    if end_idx > 0:
                        rdf_data = data[idx:end_idx + 10]
                        self.internal_rdf = rdf_data.decode('utf-8', errors='ignore')
                        self.internal_rdf_format = 'xml'
                        return self.internal_rdf

                # Extract Turtle format RDF (TB21 GIMI files)
                elif b'@prefix rdf:' in data or b'@prefix rdfs:' in data:
                    idx = data.find(b'@prefix')
                    # Extract up to 100KB to ensure all GCP data is captured
                    end_idx = min(idx + 100000, len(data))
                    chunk = data[idx:end_idx]
                    try:
                        turtle_text = chunk.decode('utf-8', errors='ignore')
                        self.internal_rdf = turtle_text
                        self.internal_rdf_format = 'turtle'
                        print(f"Extracted {len(self.internal_rdf)} characters of Turtle RDF")
                        return self.internal_rdf
                    except Exception as e:
                        print(f"Error decoding Turtle RDF: {e}")
                        return None

                # Check for XMP packet if RDF not found
                if b'<?xpacket' in data:
                    idx = data.find(b'<?xpacket')
                    end_idx = data.find(b'<?xpacket end', idx)
                    if end_idx > 0:
                        xmp_data = data[idx:end_idx + 50]
                        self.internal_rdf = xmp_data.decode('utf-8', errors='ignore')
                        self.internal_rdf_format = 'xmp'
                        return self.internal_rdf

                return None

        except Exception as e:
            print(f"Error extracting internal RDF: {e}")
            return None
    
    # ------------------------------------------------------------------
    # Format probing and multi-format support
    # ------------------------------------------------------------------

    # Mapping GDAL short driver name → display name
    _GDAL_FORMAT_FRIENDLY = {
        'GTiff':        'GeoTIFF',
        'JP2OpenJPEG':  'JPEG2000 (OpenJPEG)',
        'JP2KAK':       'JPEG2000 (Kakadu)',
        'JP2ECW':       'JPEG2000 (ECW)',
        'JPEG2000':     'JPEG2000',
        'PNG':          'PNG',
        'JPEG':         'JPEG',
        'BMP':          'BMP',
        'HFA':          'ERDAS Imagine (.img)',
        'VRT':          'GDAL Virtual (.vrt)',
        'ECW':          'ECW',
        'MrSID':        'MrSID',
        'NITF':         'NITF',
        'DTED':         'DTED',
        'GeoRaster':    'GeoRaster',
    }

    # World-file extensions by GDAL driver
    _WORLDFILE_EXTS = {
        'GTiff':        ['.tfw', '.tifw', '.wld'],
        'PNG':          ['.pgw', '.pngw', '.wld'],
        'JPEG':         ['.jgw', '.jpgw', '.wld'],
        'JP2OpenJPEG':  ['.j2w', '.jp2w', '.wld'],
        'JP2KAK':       ['.j2w', '.jp2w', '.wld'],
        'JP2ECW':       ['.j2w', '.jp2w', '.wld'],
        'JPEG2000':     ['.j2w', '.jp2w', '.wld'],
        'BMP':          ['.bpw', '.bmpw', '.wld'],
    }

    def export_gdal(self, src_path: str, dst_path: str, driver: str,
                    creation_options: Optional[List[str]] = None) -> str:
        """Export *src_path* to *dst_path* using the given GDAL driver.

        Supports any GDAL-writable raster driver (GTiff, COG, JP2OpenJPEG,
        PNG, JPEG, HFA, ECW, NITF, GPKG, ENVI, VRT, netCDF, HDF5, Zarr …).

        Args:
            src_path:         Absolute path to the source raster (any GDAL-readable format).
            dst_path:         Absolute path for the output file.
            driver:           GDAL short driver name, e.g. ``'GTiff'``, ``'COG'``, ``'JP2OpenJPEG'``.
            creation_options: List of GDAL creation-option strings in ``KEY=VALUE`` form.
                              ``None`` uses sensible defaults per driver.

        Returns:
            *dst_path* on success.

        Raises:
            RuntimeError: if GDAL cannot open *src_path* or translate to the target.
        """
        creation_options = creation_options or []

        # Per-driver sensible defaults when caller provides none
        _DEFAULTS: dict = {
            "GTiff":       ["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"],
            "COG":         ["COMPRESS=DEFLATE", "OVERVIEW_RESAMPLING=NEAREST"],
            "JP2OpenJPEG": [],
            "JPEG":        ["QUALITY=95"],
            "GPKG":        ["TILE_FORMAT=PNG"],
        }
        if not creation_options:
            creation_options = _DEFAULTS.get(driver, [])

        src_ds = gdal.Open(src_path, gdal.GA_ReadOnly)
        if src_ds is None:
            raise RuntimeError(f"GDAL could not open source file: {src_path}")

        # For HEIF inputs not readable by GDAL, fall back to pillow + GDAL mem driver
        if src_ds is None and HEIF_AVAILABLE:
            src_ds = self._heif_to_gdal_mem(src_path)

        if src_ds is None:
            raise RuntimeError(f"Cannot read source raster: {src_path}")

        os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)

        # Use gdal.Translate for format conversion
        translate_opts = gdal.TranslateOptions(
            format=driver,
            creationOptions=creation_options,
        )
        result = gdal.Translate(dst_path, src_ds, options=translate_opts)
        src_ds = None  # close
        if result is None:
            raise RuntimeError(
                f"GDAL Translate failed for driver '{driver}'.\n"
                f"Check that the driver is compiled into your GDAL build and that\n"
                f"the creation options are valid: {creation_options}"
            )
        result = None  # flush & close
        print(f"[export_gdal] {src_path} → {dst_path}  (driver={driver})")
        return dst_path

    def _heif_to_gdal_mem(self, heif_path: str):
        """Convert a HEIF file to an in-memory GDAL dataset via pillow-heif.

        Used as a fallback when the installed GDAL does not include a HEIF driver.

        Returns:
            A GDAL in-memory Dataset, or None on failure.
        """
        if not HEIF_AVAILABLE:
            return None
        try:
            import numpy as np
            import pillow_heif as _ph
            hf = _ph.open_heif(heif_path)
            if len(hf) == 0:
                return None
            img = hf[0]
            arr = np.frombuffer(img.data, dtype=np.uint8)
            w, h = img.size
            bands = len(img.mode)
            arr = arr.reshape(h, w, bands)

            mem_driver = gdal.GetDriverByName("MEM")
            ds = mem_driver.Create("", w, h, bands, gdal.GDT_Byte)
            for b in range(bands):
                ds.GetRasterBand(b + 1).WriteArray(arr[:, :, b])
            return ds
        except Exception as e:
            print(f"[_heif_to_gdal_mem] {e}")
            return None

    def probe_raster_format(self, path: str) -> dict:
        """
        Probe *path* to determine its raster format and georeferencing status.
        Uses GDAL IdentifyDriver as the primary mechanism, with a HEIF binary-
        scan fallback for files not recognised by GDAL (GDAL may lack the HEIF
        driver on some installs).

        Returns a dict with keys:
            path, format_name, driver_name, is_heif, is_gdal_readable,
            is_geo_enabled, geotransform_valid, has_gcps, gcp_count,
            crs_wkt, crs_epsg, width, height, band_count,
            available_geo_sources   (list[dict])
        """
        result: dict = {
            'path':               path,
            'format_name':        'Unknown',
            'driver_name':        '',
            'is_heif':            False,
            'is_gdal_readable':   False,
            'is_geo_enabled':     False,
            'geotransform_valid': False,
            'has_gcps':           False,
            'gcp_count':          0,
            'crs_wkt':            None,
            'crs_epsg':           None,
            'width':              0,
            'height':             0,
            'band_count':         0,
            'available_geo_sources': [],
        }

        if not os.path.exists(path):
            return result

        # ---- Step 1: try GDAL IdentifyDriver ----
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        try:
            drv = gdal.IdentifyDriver(path)
            if drv is not None:
                short_name = drv.ShortName
                result['driver_name']      = short_name
                result['format_name']      = self._GDAL_FORMAT_FRIENDLY.get(short_name, short_name)
                result['is_gdal_readable'] = True
                result['is_heif']          = False  # GDAL JP2/TIFF ≠ HEIF

                # Open with GDAL to read spatial metadata
                ds = gdal.Open(path, gdal.GA_ReadOnly)
                if ds is not None:
                    result['width']      = ds.RasterXSize
                    result['height']     = ds.RasterYSize
                    result['band_count'] = ds.RasterCount

                    # Check geotransform
                    gt = ds.GetGeoTransform()
                    identity = (0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
                    gt_valid = (gt is not None and gt != identity
                                and not all(v == 0 for v in gt))
                    result['geotransform_valid'] = gt_valid

                    # Check GCPs
                    gcps = ds.GetGCPs()
                    result['has_gcps']  = bool(gcps)
                    result['gcp_count'] = len(gcps) if gcps else 0

                    # CRS
                    proj = ds.GetProjection() or (ds.GetGCPProjection() if gcps else None)
                    if proj:
                        result['crs_wkt'] = proj
                        srs = osr.SpatialReference()
                        srs.ImportFromWkt(proj)
                        srs.AutoIdentifyEPSG()
                        code = srs.GetAuthorityCode('PROJCS') or srs.GetAuthorityCode('GEOGCS')
                        if code:
                            try:
                                result['crs_epsg'] = int(code)
                            except ValueError:
                                pass

                    result['is_geo_enabled'] = gt_valid or bool(gcps)
                    ds = None
        except Exception:
            pass
        finally:
            gdal.PopErrorHandler()

        # ---- Step 2: HEIF fallback (GDAL usually can't identify HEIF) ----
        if not result['is_gdal_readable']:
            ext = Path(path).suffix.lower()
            if ext in ('.heif', '.heic'):
                result['is_heif']      = True
                result['format_name']  = 'HEIF/HEIC'
                result['driver_name']  = 'heif'
            else:
                # Try binary probe for HEIF magic bytes regardless of extension
                try:
                    with open(path, 'rb') as fh:
                        header = fh.read(16)
                    if header[4:8] == b'ftyp':
                        result['is_heif']     = True
                        result['format_name'] = 'HEIF/HEIC'
                        result['driver_name'] = 'heif'
                except OSError:
                    pass

            if result['is_heif']:
                # Try to get image dimensions via pillow_heif
                try:
                    import pillow_heif as _ph
                    hf = _ph.open_heif(path)
                    if len(hf) > 0:
                        img = hf[0]
                        result['width']  = img.size[0]
                        result['height'] = img.size[1]
                        result['band_count'] = len(img.mode)
                except Exception:
                    pass

                # Geo check: embedded RDF counts as potential geo source (not confirmed geo)
                if self.has_internal_rdf(path):
                    result['is_geo_enabled'] = False  # needs parsing; mark as geo-capable via metadata

        # ---- Step 3: discover external georeferencing sources ----
        result['available_geo_sources'] = self._find_geo_sources(path, result['driver_name'])

        return result

    def _find_geo_sources(self, path: str, driver_name: str) -> list:
        """
        Scan the file system and file bytes for available georeferencing metadata
        sources associated with *path*.

        Returns a list of dicts, each with keys:
            source       – one of: 'sidecar_ttl', 'worldfile', 'prj_file',
                           'gdal_aux', 'exif_gps', 'embedded_rdf'
            description  – human readable string
            path         – absolute path (if file-based), else None
            bbox_wgs84   – [min_lon, min_lat, max_lon, max_lat] if derivable, else None
        """
        sources = []
        stem   = Path(path).stem
        parent = Path(path).parent

        # -- Sidecar TTL / provenance --
        for candidate_name in (
            f'{stem}.ttl',
            f'{stem}_provenance.ttl',
            f'{stem}_georef.ttl',
        ):
            candidate = parent / candidate_name
            if candidate.exists():
                sources.append({
                    'source':      'sidecar_ttl',
                    'description': f'TTL sidecar with GCPs ({candidate.name})',
                    'path':        str(candidate),
                    'bbox_wgs84':  None,
                })

        # -- Sidecar JSON provenance --
        for candidate_name in (
            f'{stem}_provenance.json',
            f'{stem}.json',
        ):
            candidate = parent / candidate_name
            if candidate.exists():
                sources.append({
                    'source':      'sidecar_json',
                    'description': f'JSON provenance sidecar ({candidate.name})',
                    'path':        str(candidate),
                    'bbox_wgs84':  None,
                })

        # -- World file --
        world_exts = (self._WORLDFILE_EXTS.get(driver_name, [])
                      + ['.wld'])  # generic fallback
        for wext in set(world_exts):
            wf = parent / (stem + wext)
            if wf.exists():
                sources.append({
                    'source':      'worldfile',
                    'description': f'World file ({wf.name}) — affine geotransform',
                    'path':        str(wf),
                    'bbox_wgs84':  None,
                })
                break  # one is enough

        # -- PRJ sidecar (CRS only, not a geo-position) --
        prj = parent / (stem + '.prj')
        if prj.exists():
            sources.append({
                'source':      'prj_file',
                'description': f'CRS definition file ({prj.name})',
                'path':        str(prj),
                'bbox_wgs84':  None,
            })

        # -- GDAL AUX.XML (band stats, optional CRS) --
        aux = Path(path).with_suffix(Path(path).suffix + '.aux.xml')
        if aux.exists():
            sources.append({
                'source':      'gdal_aux',
                'description': 'GDAL .aux.xml statistics / metadata',
                'path':        str(aux),
                'bbox_wgs84':  None,
            })

        # -- EXIF GPS (for JPEG, TIFF, HEIF) --
        gps_info = self._extract_exif_gps(path)
        if gps_info:
            lat, lon = gps_info['lat'], gps_info['lon']
            sources.append({
                'source':      'exif_gps',
                'description': (f'EXIF GPS tag  lat={lat:.6f}  lon={lon:.6f}'
                                + (f'  alt={gps_info["alt"]:.1f} m'
                                   if gps_info.get('alt') is not None else '')),
                'path':        None,
                'bbox_wgs84':  [lon, lat, lon, lat],  # point — caller may expand
            })

        # -- Embedded RDF/XMP --
        if self.has_internal_rdf(path):
            fmt = (self.internal_rdf_format or 'RDF').upper()
            sources.append({
                'source':      'embedded_rdf',
                'description': f'Embedded {fmt} metadata (may contain GCPs)',
                'path':        None,
                'bbox_wgs84':  None,
            })

        return sources

    def _extract_exif_gps(self, path: str) -> Optional[dict]:
        """
        Extract GPS coordinates from EXIF metadata using PIL.

        Returns dict with 'lat', 'lon', (optional) 'alt', or None.
        """
        try:
            from PIL import Image as _Image
            img = _Image.open(path)
            exif_data = img._getexif() if hasattr(img, '_getexif') else None
            if exif_data is None:
                # Try getexif() (Pillow >= 7.0)
                try:
                    raw = img.getexif()
                    exif_data = dict(raw) if raw else None
                except Exception:
                    pass
            if not exif_data:
                return None

            GPS_IFD_TAG = 34853
            gps_ifd = exif_data.get(GPS_IFD_TAG)
            if not gps_ifd:
                return None

            def _dms_to_decimal(dms, ref):
                """Convert DMS tuple to decimal degrees."""
                try:
                    deg, mins, secs = dms
                    # Each value may be a Fraction/IFDRational
                    to_float = lambda v: float(v.numerator) / float(v.denominator) if hasattr(v, 'numerator') else float(v)
                    decimal = to_float(deg) + to_float(mins) / 60.0 + to_float(secs) / 3600.0
                    if ref in ('S', 'W'):
                        decimal = -decimal
                    return decimal
                except Exception:
                    return None

            lat_dms = gps_ifd.get(2)
            lat_ref = gps_ifd.get(1, 'N')
            lon_dms = gps_ifd.get(4)
            lon_ref = gps_ifd.get(3, 'E')

            if not lat_dms or not lon_dms:
                return None

            lat = _dms_to_decimal(lat_dms, lat_ref)
            lon = _dms_to_decimal(lon_dms, lon_ref)
            if lat is None or lon is None:
                return None

            result = {'lat': lat, 'lon': lon}
            alt_val = gps_ifd.get(6)
            if alt_val is not None:
                try:
                    result['alt'] = float(alt_val.numerator) / float(alt_val.denominator) if hasattr(alt_val, 'numerator') else float(alt_val)
                except Exception:
                    pass
            return result

        except Exception:
            return None

    def copy_raster_to_tiff(self, raster_path: str,
                            output_path: Optional[str] = None) -> Optional[str]:
        """
        Copy any GDAL-readable raster to a temporary GeoTIFF using ``gdal.Translate``.

        Preserves existing geotransform, GCPs, and CRS so that the rest of the
        pipeline can work with a canonical TIFF regardless of input format.

        Args:
            raster_path:  Source raster (GeoTIFF, JP2, PNG, …).
            output_path:  Optional destination path; if None a temp file is used.

        Returns:
            Path to the output TIFF or None on failure.
        """
        try:
            if output_path is None:
                tmp = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
                output_path = tmp.name
                tmp.close()
                self.temp_files.append(output_path)

            gdal.PushErrorHandler('CPLQuietErrorHandler')
            ds_out = gdal.Translate(
                output_path,
                raster_path,
                format='GTiff',
                creationOptions=['COMPRESS=LZW', 'TILED=YES'],
            )
            gdal.PopErrorHandler()

            if ds_out is None:
                print(f"gdal.Translate failed for {raster_path}")
                return None
            ds_out = None  # flush / close
            return output_path
        except Exception as exc:
            print(f"copy_raster_to_tiff error: {exc}")
            return None

    def convert_any_to_tiff(self, path: str,
                            output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert *path* to a TIFF using the appropriate method:

        - HEIF/HEIC  → ``convert_heif_to_tiff()`` (pillow_heif + heif-dec fallback)
        - Everything else → ``copy_raster_to_tiff()`` via GDAL Translate

        Returns the output TIFF path or None on failure.
        """
        ext = Path(path).suffix.lower()
        is_heif_ext = ext in ('.heif', '.heic')

        if is_heif_ext:
            return self.convert_heif_to_tiff(path, output_path)

        # Check HEIF magic bytes in case extension is wrong
        try:
            with open(path, 'rb') as fh:
                if fh.read(16)[4:8] == b'ftyp':
                    return self.convert_heif_to_tiff(path, output_path)
        except OSError:
            pass

        return self.copy_raster_to_tiff(path, output_path)

    # ------------------------------------------------------------------

    def display_heif_structure(self, heif_path: str) -> str:
        """
        Display the complete HEIF/HEVC file structure including boxes, metadata, and images.
        For non-HEIF raster formats (GeoTIFF, JP2, PNG, …) a GDAL metadata summary is
        returned instead so callers can always use this method regardless of format.

        IMPLEMENTATION NOTE
        -------------------
        The structure information below is assembled through ad-hoc parsing of
        pillow-heif high-level attributes and raw byte inspection.  This is
        fragile: it may miss items, mis-classify box types, or fail on unusual
        HEIF variants.  The robust approach is to use the libheif C API directly
        (e.g. ``heif_context_get_list_of_item_IDs``, ``heif_image_handle_*``,
        ``heif_item_get_item_content_type``) which gives typed, structured access
        to every box in the file without manual byte parsing.

        Args:
            heif_path: Path to input file (any GDAL-readable raster, or HEIF/HEIC)

        Returns:
            String containing formatted file structure / metadata information
        """
        # ------------------------------------------------------------------
        # Guard: if file is not HEIF, return GDAL-based metadata summary
        # ------------------------------------------------------------------
        probe = self.probe_raster_format(heif_path)
        if not probe['is_heif']:
            lines = [
                '=' * 80,
                f'RASTER FILE STRUCTURE: {os.path.basename(heif_path)}',
                '=' * 80,
                '',
                f'Format:     {probe["format_name"]}  (driver: {probe["driver_name"]})',
                f'File size:  {os.path.getsize(heif_path):,} bytes  '
                f'({os.path.getsize(heif_path) / 1024 / 1024:.2f} MB)',
                f'Dimensions: {probe["width"]} × {probe["height"]} px',
                f'Bands:      {probe["band_count"]}',
                '',
            ]
            if probe['is_geo_enabled']:
                crs_hint = f'EPSG:{probe["crs_epsg"]}' if probe['crs_epsg'] else (
                    probe['crs_wkt'][:60] + '…' if probe['crs_wkt'] else 'unknown CRS')
                if probe['has_gcps']:
                    lines.append(f'Georef:     ✓ {probe["gcp_count"]} embedded GCPs  |  CRS: {crs_hint}')
                else:
                    lines.append(f'Georef:     ✓ Geotransform  |  CRS: {crs_hint}')
            else:
                lines.append('Georef:     ✗ Not georeferenced')

            sources = probe.get('available_geo_sources', [])
            if sources:
                lines += ['', 'Available Georeferencing Sources:']
                for s in sources:
                    lines.append(f'  [{s["source"]}]  {s["description"]}')
            else:
                lines += ['', 'No external georeferencing sources detected.']

            # Try to add GDAL gdalinfo-style detail
            try:
                gdal.UseExceptions()
                ds = gdal.Open(heif_path, gdal.GA_ReadOnly)
                if ds is not None:
                    gt = ds.GetGeoTransform()
                    if gt and gt != (0, 1, 0, 0, 0, 1):
                        lines += [
                            '',
                            'GeoTransform:',
                            f'  Origin (top-left): ({gt[0]:.6f}, {gt[3]:.6f})',
                            f'  Pixel size X:  {gt[1]:.10f}',
                            f'  Pixel size Y:  {gt[5]:.10f}',
                        ]
                    gcps = ds.GetGCPs()
                    if gcps:
                        lines += ['', f'Embedded GCPs ({len(gcps)}):']
                        for i, gcp in enumerate(gcps[:6]):
                            lines.append(
                                f'  GCP {i+1}:  pixel=({gcp.GCPPixel:.1f}, {gcp.GCPLine:.1f})'
                                f'  →  lon={gcp.GCPX:.6f}  lat={gcp.GCPY:.6f}'
                            )
                        if len(gcps) > 6:
                            lines.append(f'  … and {len(gcps)-6} more')
                    ds = None
            except Exception:
                pass

            return '\n'.join(lines)

        # ------------------------------------------------------------------
        # HEIF path — original implementation follows
        # ------------------------------------------------------------------
        if not HEIF_AVAILABLE:
            return "ERROR: pillow-heif not installed. Install with: pip install pillow-heif"

        structure = []
        structure.append("=" * 80)
        structure.append(f"HEIF/HEVC FILE STRUCTURE: {os.path.basename(heif_path)}")
        structure.append("=" * 80)
        structure.append("")
        
        try:
            import pillow_heif
            
            # Get file size
            file_size = os.path.getsize(heif_path)
            structure.append(f"File Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
            structure.append("")
            
            # Open HEIF file with pillow_heif
            heif_file = pillow_heif.open_heif(heif_path)
            
            # File-level information
            structure.append("FILE INFORMATION:")
            structure.append("-" * 80)
            
            # Check if container has images
            num_images = len(heif_file)
            
            # Brand (may not exist in all versions)
            try:
                structure.append(f"  Brand: {heif_file.brand}")
            except AttributeError:
                structure.append(f"  Brand: HEIF (unknown)")
            
            structure.append(f"  Number of Images: {num_images}")
            
            if num_images == 0:
                structure.append("  Type: Metadata-only container (no image data)")
                structure.append("")
                structure.append("⚠️  This HEIF file contains no actual image data detected by pillow_heif.")
                structure.append("    It may only contain embedded metadata (RDF, XMP, etc.)")
                structure.append("    OR the image encoding may not be supported by the current pillow_heif version.")
                structure.append("")
                
                # Try to get more info about the file structure
                with open(heif_path, 'rb') as f:
                    # Read more data to analyze structure
                    data = f.read(8192)  # Read first 8KB
                    
                    # Parse ftyp box to get compatible brands
                    ftyp_idx = data.find(b'ftyp')
                    if ftyp_idx > 0:
                        # ftyp box contains major brand and compatible brands
                        ftyp_start = ftyp_idx + 4
                        if ftyp_start + 8 < len(data):
                            major_brand = data[ftyp_start:ftyp_start+4].decode('ascii', errors='ignore')
                            minor_version = int.from_bytes(data[ftyp_start+4:ftyp_start+8], 'big')
                            structure.append(f"  File Type Box (ftyp):")
                            structure.append(f"    Major brand: {major_brand}")
                            
                            # Check compatible brands
                            compat_brands = []
                            offset = ftyp_start + 8
                            while offset + 4 < min(ftyp_start + 100, len(data)):
                                brand = data[offset:offset+4]
                                if brand.isalnum() or b'\x00' in brand:
                                    brand_str = brand.decode('ascii', errors='ignore').strip('\x00')
                                    if brand_str and len(brand_str) >= 3:
                                        compat_brands.append(brand_str)
                                offset += 4
                            
                            if compat_brands:
                                structure.append(f"    Compatible brands: {', '.join(compat_brands[:10])}")
                        structure.append("")
                    
                    # Look for item type information (infe boxes contain 'item_type')
                    # Common types: 'hvc1' (HEVC), 'jpeg' (JPEG), 'unci' (uncompressed), 'av01' (AV1)
                    encoding_types = []
                    
                    # Search for common codec identifiers
                    if b'hvc1' in data or b'hevc' in data.lower():
                        encoding_types.append('HEVC (H.265) - NOT supported by pillow_heif')
                    if b'hev1' in data:
                        encoding_types.append('HEVC variant - NOT supported')
                    if b'unci' in data:
                        encoding_types.append('Uncompressed - May NOT be supported by pillow_heif')
                    if b'jpeg' in data.lower() and b'Exif' in data:
                        encoding_types.append('JPEG')
                    if b'av01' in data or b'AV1' in data:
                        encoding_types.append('AV1 - NOT supported by pillow_heif')
                    if b'avc1' in data or b'h264' in data.lower():
                        encoding_types.append('H.264/AVC - May NOT be supported')
                    
                    # Look for HEIF boxes
                    box_types = []
                    if b'ftyp' in data:
                        box_types.append('ftyp (file type)')
                    if b'meta' in data:
                        box_types.append('meta (metadata)')
                    if b'mdat' in data:
                        box_types.append('mdat (media data) ✓')
                    if b'idat' in data:
                        box_types.append('idat (item data) ✓')
                    if b'iref' in data:
                        box_types.append('iref (item references)')
                    if b'iprp' in data:
                        box_types.append('iprp (item properties)')
                    if b'pitm' in data:
                        box_types.append('pitm (primary item) ✓')
                    if b'iinf' in data:
                        box_types.append('iinf (item information)')
                    if b'iloc' in data:
                        box_types.append('iloc (item location)')
                    
                    if box_types:
                        structure.append("  Detected HEIF boxes:")
                        for bt in box_types:
                            structure.append(f"    - {bt}")
                        structure.append("")
                    
                    if encoding_types:
                        structure.append("  🔍 Detected image encoding(s):")
                        for et in encoding_types:
                            structure.append(f"    - {et}")
                        structure.append("")
                        
                        # Check if it's the uncompressed unci format
                        if any('Uncompressed' in et or 'unci' in et for et in encoding_types):
                            structure.append("  ⚠️  UNCOMPRESSED HEIF (unci) DETECTED:")
                            structure.append("      Uncompressed HEIF is supported by custom-built libheif.")
                            structure.append("      Your system uses custom libheif with unci decoder enabled.")
                            structure.append("")
                            structure.append("  ✓ SOLUTION:")
                            structure.append("      This plugin will automatically use the custom heif-dec decoder")
                            structure.append("      located at: ~/Downloads/libheif/build/examples/heif-dec")
                            structure.append("      The conversion will proceed automatically.")
                            structure.append("")
                            structure.append("  📝 Note: If conversion fails, homebrew libheif does NOT support unci.")
                            structure.append("      The custom-built version is required for uncompressed files.")
                        else:
                            structure.append("  ⚠️  SOLUTION:")
                            structure.append("      This file uses an image codec not supported by pillow_heif.")
                            structure.append("      Supported codecs: HEIC (libheif with HEVC decoder)")
                            structure.append("      Try:")
                            structure.append("      1. Convert the image with: heif-dec input.heif output.png")
                            structure.append("      2. Or use libheif tools to extract the image")
                            structure.append("      3. Check if libheif-dev is installed with HEVC support")
                        structure.append("")
                    elif 'mdat' in str(box_types) or 'idat' in str(box_types):
                        structure.append("  ℹ️  File contains media/item data boxes - image may be present")
                        structure.append("      but encoded in a format not supported by pillow_heif.")
                        structure.append("      Common unsupported formats: Uncompressed, HEVC without decoder")
                        structure.append("")
                        structure.append("  Try: heif-dec input.heif output.png")
            else:
                # Only access info if there are images
                try:
                    file_format = heif_file.info.get('format', 'HEIF')
                    structure.append(f"  Format: {file_format}")
                except (IndexError, AttributeError):
                    structure.append(f"  Format: HEIF (container)")
                
                # Check for HDR
                try:
                    has_hdr = any(img.info.get('hdr_to_8bit') is not None for img in heif_file)
                    structure.append(f"  HDR Content: {'Yes' if has_hdr else 'No'}")
                except:
                    pass
                
                # Color profiles - only if there are images
                try:
                    if heif_file.info.get('icc_profile'):
                        structure.append(f"  ICC Profile: Present ({len(heif_file.info['icc_profile'])} bytes)")
                    if heif_file.info.get('exif'):
                        structure.append(f"  EXIF Data: Present ({len(heif_file.info['exif'])} bytes)")
                    if heif_file.info.get('xmp'):
                        structure.append(f"  XMP Data: Present ({len(heif_file.info['xmp'])} bytes)")
                except (IndexError, AttributeError):
                    pass
            
            structure.append("")
            
            # Iterate through all images in the container
            for idx, img in enumerate(heif_file):
                structure.append(f"IMAGE #{idx + 1}:")
                structure.append("-" * 80)
                
                # Image properties
                structure.append(f"  Size: {img.size[0]} x {img.size[1]} pixels")
                structure.append(f"  Mode: {img.mode}")
                structure.append(f"  Bit Depth: {img.info.get('bits_per_pixel', 'N/A')} bits per pixel")
                
                # Check if this is primary image
                if hasattr(img, 'primary') and img.primary:
                    structure.append(f"  Primary Image: Yes")
                
                # Thumbnails
                if hasattr(img, 'thumbnails') and img.thumbnails:
                    structure.append(f"  Thumbnails: {len(img.thumbnails)}")
                    for tidx, thumb in enumerate(img.thumbnails):
                        structure.append(f"    Thumbnail {tidx + 1}: {thumb.size[0]}x{thumb.size[1]}")
                
                # Encoding information
                if 'encoder' in img.info:
                    structure.append(f"  Encoder: {img.info['encoder']}")
                
                # Compression
                if 'compression' in img.info:
                    structure.append(f"  Compression: {img.info['compression']}")
                
                # Color information
                if 'color_primaries' in img.info:
                    structure.append(f"  Color Primaries: {img.info['color_primaries']}")
                if 'color_matrix' in img.info:
                    structure.append(f"  Color Matrix: {img.info['color_matrix']}")
                if 'color_transfer' in img.info:
                    structure.append(f"  Transfer Function: {img.info['color_transfer']}")
                
                # HDR metadata
                if 'hdr_to_8bit' in img.info:
                    structure.append(f"  HDR: Yes")
                    structure.append(f"    HDR to 8-bit conversion: {img.info['hdr_to_8bit']}")
                
                # Orientation
                if 'orientation' in img.info:
                    structure.append(f"  Orientation: {img.info['orientation']}")
                
                # Stride (for planar formats) - skip if pillow-heif lacks codec support
                try:
                    if hasattr(img, 'stride'):
                        structure.append(f"  Stride: {img.stride}")
                except RuntimeError as e:
                    if "compression format has not been built in" in str(e):
                        structure.append(f"  ⚠ Advanced analysis unavailable (pillow-heif lacks JPEG2000 decoder)")
                        structure.append(f"  → Use heif-info or heif-convert for full details")
                    else:
                        raise
                
                # Image-specific metadata
                if 'exif' in img.info and img.info['exif']:
                    structure.append(f"  EXIF: Present")
                    # Try to parse EXIF
                    try:
                        from PIL import ExifTags
                        pil_img = img.to_pillow()
                        exif_data = pil_img.getexif()
                        if exif_data:
                            structure.append("    EXIF Tags:")
                            for tag_id, value in list(exif_data.items())[:10]:  # Show first 10
                                tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                                # Truncate long values
                                value_str = str(value)[:50]
                                if len(str(value)) > 50:
                                    value_str += "..."
                                structure.append(f"      {tag_name}: {value_str}")
                            if len(exif_data) > 10:
                                structure.append(f"      ... and {len(exif_data) - 10} more tags")
                    except Exception as e:
                        structure.append(f"    (Could not parse EXIF: {e})")
                
                if 'xmp' in img.info and img.info['xmp']:
                    xmp_data = img.info['xmp']
                    structure.append(f"  XMP: Present ({len(xmp_data)} bytes)")
                    # Show preview of XMP
                    try:
                        xmp_str = xmp_data.decode('utf-8', errors='ignore')[:200]
                        structure.append(f"    Preview: {xmp_str}...")
                    except:
                        pass
                
                if 'icc_profile' in img.info and img.info['icc_profile']:
                    structure.append(f"  ICC Profile: Present ({len(img.info['icc_profile'])} bytes)")
                
                structure.append("")
            
            # Check for internal RDF
            structure.append("EMBEDDED RDF METADATA:")
            structure.append("-" * 80)
            has_rdf = self.has_internal_rdf(heif_path)
            if has_rdf:
                rdf_content = self.extract_internal_rdf(heif_path)
                structure.append(f"  Format: {self.internal_rdf_format.upper()}")
                structure.append(f"  Size: {len(rdf_content)} bytes")
                structure.append("  Content:")
                structure.append("")
                # Show ALL RDF content (no truncation)
                for line in rdf_content.split('\n'):
                    structure.append(f"    {line}")
            else:
                structure.append("  No internal RDF metadata found")
            
            structure.append("")
            structure.append("=" * 80)
            
        except Exception as e:
            structure.append(f"ERROR analyzing HEIF structure: {e}")
            import traceback
            structure.append(traceback.format_exc())
        
        return '\n'.join(structure)
    
    def check_heif_convert_available(self) -> bool:
        """
        Check if heif-dec command-line tool is available.
        Prioritizes custom-built version with uncompressed (unci) codec support.
        
        Returns:
            True if heif-dec is available, False otherwise
        """
        import subprocess
        import os
        
        # Possible locations for heif-dec (decoder) - heif-convert was renamed to heif-dec in newer versions
        # PRIORITIZE custom-built version with unci support first
        possible_paths = [
            os.path.expanduser('~/Downloads/libheif/build/examples/heif-dec'),  # Custom build with unci support
            os.path.expanduser('~/local-libheif/bin/heif-dec'),  # Installed custom build
            '/opt/homebrew/bin/heif-dec',  # Homebrew on Apple Silicon (may not have unci)
            '/usr/local/bin/heif-dec',  # Homebrew on Intel Mac
            '/usr/bin/heif-dec',  # System installation
            # Fallback to older heif-convert name if it exists
            '/opt/homebrew/bin/heif-convert',
            '/usr/local/bin/heif-convert',
        ]
        
        for cmd in possible_paths:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0 or result.returncode == 1:  # Some versions return 1 for --version
                    self.heif_convert_cmd = cmd
                    # Log which version we're using
                    print(f"✓ Using HEIF decoder from: {cmd}")
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        self.heif_convert_cmd = None
        return False
    
    def convert_heif_with_libheif(self, heif_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert HEIF to PNG/JP2 using heif-dec command-line tool.
        This is a fallback for formats not supported by pillow_heif (e.g., JPEG2000).
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path. If None, creates temp file
            
        Returns:
            Path to output file (PNG or JP2) or None on error
        """
        import subprocess
        
        # Ensure we have the command path
        if not hasattr(self, 'heif_convert_cmd') or self.heif_convert_cmd is None:
            if not self.check_heif_convert_available():
                print("heif-dec not found. Install libheif with: brew install libheif")
                print("Or build from source with JPEG2000 codec support.")
                return None
        
        try:
            # First check what codec is used in the HEIF file
            codec_type = "unknown"
            heif_info_cmd = self.heif_convert_cmd.replace('heif-dec', 'heif-info')
            if os.path.exists(heif_info_cmd):
                try:
                    plugin_dir = os.path.join(os.path.dirname(self.heif_convert_cmd), '..', 'libheif', 'plugins')
                    info_cmd = [heif_info_cmd]
                    # heif-info accepts --plugin-directory; however prefer the
                    # LIBHEIF_PLUGIN_PATH environment variable for consistency.
                    env_info = os.environ.copy()
                    if os.path.exists(plugin_dir):
                        env_info['LIBHEIF_PLUGIN_PATH'] = plugin_dir
                    info_cmd.append(heif_path)
                    
                    info_result = subprocess.run(info_cmd, capture_output=True, text=True,
                                                   timeout=10, env=env_info)
                    if 'jpeg2000' in info_result.stdout.lower() or 'j2k' in info_result.stdout.lower():
                        codec_type = "jpeg2000"
                        print("Detected JPEG2000 codec in HEIF")
                    elif 'hevc' in info_result.stdout.lower() or 'h265' in info_result.stdout.lower():
                        codec_type = "hevc"
                        print("Detected HEVC codec in HEIF")
                except Exception as e:
                    print(f"Could not detect codec: {e}")
            
            # Determine output format and extension based on codec
            if codec_type == "jpeg2000":
                output_ext = '.jp2'
                print("Will extract as JPEG2000 (.jp2)")
            else:
                output_ext = '.png'
                print("Will extract as PNG")
            
            # Determine output path
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix=output_ext, delete=False)
                output_path = temp_file.name
                temp_file.close()
                self.temp_files.append(output_path)
            
            # Use heif-dec to extract image
            print(f"Converting HEIF with custom libheif decoder...")
            print(f"Command: {self.heif_convert_cmd}")
            
            # Build command - heif-dec doesn't support --plugin-directory
            # Instead, set LIBHEIF_PLUGIN_PATH environment variable
            cmd = [self.heif_convert_cmd, heif_path, output_path]
            
            # Set environment variable for plugin directory (for JPEG2000 support)
            env = os.environ.copy()
            plugin_dir = os.path.join(os.path.dirname(self.heif_convert_cmd), '..', 'libheif', 'plugins')
            if os.path.exists(plugin_dir):
                env['LIBHEIF_PLUGIN_PATH'] = plugin_dir
                print(f"Using plugin directory: {plugin_dir} (via LIBHEIF_PLUGIN_PATH)")
            
            print(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )
            
            print(f"heif-dec return code: {result.returncode}")
            if result.stdout:
                print(f"stdout: {result.stdout}")
            if result.stderr:
                print(f"stderr: {result.stderr}")
            
            # heif-dec may return 0 on success or 1 with warnings
            if result.returncode != 0 and not os.path.exists(output_path):
                print(f"heif-dec failed with return code {result.returncode}")
                print(f"stderr: {result.stderr}")
                print(f"stdout: {result.stdout}")
                
                # Check for specific unsupported codec errors
                if 'unci' in result.stderr.lower() or 'uncompressed' in result.stderr.lower():
                    print("\n" + "=" * 80)
                    print("UNSUPPORTED CODEC: Uncompressed HEIF (unci)")
                    print("=" * 80)
                    print("This HEIF file uses uncompressed encoding which is not supported by this libheif build.")
                    print("The image data IS present but cannot be decoded with this version.")
                    print("\nRECOMMENDED SOLUTIONS:")
                    print("1. Use custom-built libheif with WITH_UNCOMPRESSED_CODEC=ON")
                    print("2. Ask the data provider for a HEVC-compressed version")
                    print("3. Try the custom build at: ~/Downloads/libheif/build/examples/heif-dec")
                    print("=" * 80 + "\n")
                
                return None
            
            if not os.path.exists(output_path):
                print(f"heif-dec did not create output file: {output_path}")
                return None
            
            print(f"Successfully converted HEIF using heif-convert: {output_path}")
            return output_path
            
        except subprocess.TimeoutExpired:
            print("heif-convert timed out")
            return None
        except Exception as e:
            print(f"Error using heif-convert: {e}")
            import traceback
            traceback.print_exc()
            return None

    def convert_heif_to_tiff(self, heif_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert HEIF image to TIFF format
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path. If None, creates temp file
            
        Returns:
            Path to output TIFF file or None on error
        """
        if not HEIF_AVAILABLE:
            print("ERROR: pillow-heif not installed. Install with: pip install pillow-heif")
            # Try heif-convert as fallback
            if self.check_heif_convert_available():
                print("Attempting conversion with heif-convert...")
                png_path = self.convert_heif_with_libheif(heif_path)
                if png_path:
                    # Convert PNG to TIFF
                    try:
                        img = Image.open(png_path)
                        if output_path is None:
                            temp_file = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
                            output_path = temp_file.name
                            temp_file.close()
                            self.temp_files.append(output_path)
                        img.save(output_path, 'TIFF', compression='lzw')
                        return output_path
                    except Exception as e:
                        print(f"Error converting PNG to TIFF: {e}")
            return None
            
        try:
            # Ensure HEIF opener is registered
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except Exception as e:
                print(f"Warning: Could not register HEIF opener: {e}")
            
            # Try to open HEIF image with PIL
            img = None
            try:
                img = Image.open(heif_path)
            except Exception as img_error:
                # Try with pillow_heif directly as fallback
                print(f"PIL Image.open failed: {img_error}")
                print("Trying pillow_heif direct method...")
                try:
                    import pillow_heif
                    heif_file = pillow_heif.open_heif(heif_path)
                    
                    # Check if file contains any images
                    if len(heif_file) == 0:
                        print("WARNING: HEIF file contains 0 images detected by pillow_heif")
                        print("Attempting conversion with heif-convert...")
                        
                        # Try heif-convert as final fallback
                        if self.check_heif_convert_available():
                            png_path = self.convert_heif_with_libheif(heif_path)
                            if png_path:
                                # Convert PNG to TIFF
                                img = Image.open(png_path)
                                # Continue with normal flow below
                            else:
                                error_msg = (
                                    "Cannot decode HEIF image. The file contains image data but uses "
                                    "an unsupported codec (likely uncompressed 'unci' format).\n\n"
                                    "This is a limitation of the available HEIF libraries. "
                                    "Please request a HEVC-compressed version of this image from your data provider."
                                )
                                raise Exception(error_msg)
                        else:
                            print("heif-convert not available. Install with: brew install libheif")
                            error_msg = (
                                "Cannot decode HEIF image. Install libheif tools: brew install libheif"
                            )
                            raise Exception(error_msg)
                    else:
                        # Get first image
                        try:
                            img = pillow_heif.to_pillow(heif_file[0])
                        except RuntimeError as load_error:
                            # Check if this is a codec support issue (e.g., JPEG2000)
                            if "compression format has not been built in" in str(load_error):
                                print(f"pillow-heif lacks decoder for this codec: {load_error}")
                                print("Attempting conversion with heif-convert...")
                                
                                if self.check_heif_convert_available():
                                    png_path = self.convert_heif_with_libheif(heif_path)
                                    if png_path:
                                        img = Image.open(png_path)
                                    else:
                                        raise Exception(f"heif-convert failed to decode file: {load_error}")
                                else:
                                    raise Exception(
                                        f"HEIF file uses codec not supported by pillow-heif: {load_error}\n"
                                        f"Install libheif tools for decoding: brew install libheif"
                                    )
                            else:
                                raise
                except Exception as heif_error:
                    print(f"pillow_heif direct method also failed: {heif_error}")
                    
                    # Try heif-convert as final fallback
                    if self.check_heif_convert_available():
                        print("Attempting conversion with heif-convert as final fallback...")
                        png_path = self.convert_heif_with_libheif(heif_path)
                        if png_path:
                            # Verify PNG file exists and has content
                            if not os.path.exists(png_path):
                                raise Exception(f"heif-convert output file not found: {png_path}")
                            
                            file_size = os.path.getsize(png_path)
                            if file_size == 0:
                                raise Exception(f"heif-convert created empty file: {png_path}")
                            
                            print(f"  PNG file created: {file_size:,} bytes")
                            
                            # Try to open with explicit format
                            try:
                                with open(png_path, 'rb') as f:
                                    img = Image.open(f)
                                    img.load()  # Force load to verify it's readable
                            except Exception as png_error:
                                print(f"  Failed to load PNG: {png_error}")
                                raise Exception(f"heif-convert created unreadable PNG file: {png_error}")
                        else:
                            raise heif_error
                    else:
                        raise
            
            if img is None:
                print("ERROR: Could not load image from HEIF file")
                return None
            
            # Convert to RGB if needed
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Determine output path
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
                output_path = temp_file.name
                temp_file.close()
                self.temp_files.append(output_path)
            
            # Save as TIFF
            img.save(output_path, 'TIFF', compression='lzw')
            
            print(f"Converted HEIF to TIFF: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error converting HEIF to TIFF: {e}")
            return None
    
    def convert_heif_to_jp2(self, heif_path: str, output_path: Optional[str] = None, 
                           lossless: bool = True) -> Optional[str]:
        """
        Convert HEIF to JPEG2000 using heif-enc (experimental).
        
        JPEG2000 advantages:
        - Better compression than TIFF (20-30% smaller)
        - Native QGIS/GDAL support
        - Multi-resolution pyramids
        - Lossless and lossy modes
        - Excellent for large imagery
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path. If None, creates temp file
            lossless: If True, use lossless compression (default)
            
        Returns:
            Path to output JP2 file or None on error
        """
        if not self.heif_enc_cmd:
            if not self.check_heif_enc_available():
                print("heif-enc not available. Cannot convert to JPEG2000.")
                print("Install libheif: https://github.com/strukturag/libheif")
                return None
        
        # Determine output path
        if output_path is None:
            temp_file = tempfile.NamedTemporaryFile(suffix='.jp2', delete=False)
            output_path = temp_file.name
            temp_file.close()
            self.temp_files.append(output_path)
        
        # Build command
        cmd = [
            self.heif_enc_cmd,
            '--jpeg2000',
            heif_path,
            '-o', output_path
        ]
        
        if lossless:
            cmd.insert(2, '-L')  # Lossless mode
        
        try:
            print(f"Converting HEIF to JPEG2000: {os.path.basename(heif_path)}")
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=60)
            
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"Successfully converted to JPEG2000: {output_path}")
                return output_path
            else:
                print(f"JPEG2000 conversion failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("JPEG2000 conversion timed out")
            return None
        except Exception as e:
            print(f"Error converting to JPEG2000: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def convert_heif_to_jp2_via_gdal(self, heif_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert HEIF to JPEG2000 via TIFF intermediate (fallback method).
        
        Uses: HEIF → TIFF → JPEG2000
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path for JP2 file
            
        Returns:
            Path to output JP2 file or None on error
        """
        try:
            # Step 1: Convert HEIF to TIFF
            tiff_path = self.convert_heif_to_tiff(heif_path)
            if not tiff_path:
                return None
            
            # Determine output path
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.jp2', delete=False)
                output_path = temp_file.name
                temp_file.close()
                self.temp_files.append(output_path)
            
            # Step 2: Convert TIFF to JPEG2000 using GDAL
            ds = gdal.Open(tiff_path, gdal.GA_ReadOnly)
            if ds is None:
                print(f"Could not open TIFF: {tiff_path}")
                return None
            
            # Try JP2OpenJPEG driver (most common)
            driver = gdal.GetDriverByName('JP2OpenJPEG')
            if driver is None:
                # Try other JP2 drivers
                for driver_name in ['JP2KAK', 'JP2ECW', 'JPEG2000']:
                    driver = gdal.GetDriverByName(driver_name)
                    if driver:
                        break
            
            if driver is None:
                print("No JPEG2000 driver available in GDAL")
                return None
            
            # Create JPEG2000 with options
            options = [
                'QUALITY=100',      # Lossless quality
                'REVERSIBLE=YES',   # Lossless compression
                'YCBCR420=NO',      # Preserve full color
                'GMLJP2=NO'         # Skip GML boxes for now
            ]
            
            print(f"Converting TIFF to JPEG2000 using {driver.ShortName}...")
            out_ds = driver.CreateCopy(output_path, ds, strict=0, options=options)
            
            if out_ds:
                out_ds.FlushCache()
                out_ds = None
                ds = None
                print(f"Successfully converted to JPEG2000: {output_path}")
                return output_path
            else:
                ds = None
                print("JPEG2000 creation failed")
                return None
                
        except Exception as e:
            print(f"Error in GDAL JPEG2000 conversion: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def convert_tiff_to_jp2(self, tiff_path: str, output_path: str) -> bool:
        """
        Convert a GeoTIFF to JPEG2000, preserving georeferencing.
        
        Args:
            tiff_path: Path to input GeoTIFF
            output_path: Path for output JP2 file
            
        Returns:
            True on success, False on error
        """
        try:
            ds = gdal.Open(tiff_path, gdal.GA_ReadOnly)
            if ds is None:
                print(f"Could not open TIFF: {tiff_path}")
                return False
            
            # Find JPEG2000 driver
            driver = gdal.GetDriverByName('JP2OpenJPEG')
            if driver is None:
                for driver_name in ['JP2KAK', 'JP2ECW', 'JPEG2000']:
                    driver = gdal.GetDriverByName(driver_name)
                    if driver:
                        break
            
            if driver is None:
                print("No JPEG2000 driver available in GDAL")
                return False
            
            # JPEG2000 creation options
            options = [
                'QUALITY=100',
                'REVERSIBLE=YES',
                'YCBCR420=NO',
                'GMLJP2=YES',
                'GeoJP2=YES'
            ]
            
            print(f"Converting to JPEG2000 using {driver.ShortName}...")
            out_ds = driver.CreateCopy(output_path, ds, strict=0, options=options)
            
            if out_ds:
                out_ds.FlushCache()
                out_ds = None
                ds = None
                print(f"Successfully converted to JPEG2000: {output_path}")
                return True
            else:
                ds = None
                print("JPEG2000 conversion failed")
                return False
                
        except Exception as e:
            print(f"Error converting TIFF to JPEG2000: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_georeferenced_tiff(self, input_tiff: str, gcps: list, output_path: str, 
                                  epsg: int = 4326) -> bool:
        """
        Create a georeferenced GeoTIFF using Ground Control Points
        
        Args:
            input_tiff: Path to input TIFF file
            gcps: List of GCPs as (pixel_x, pixel_y, lon, lat) tuples
            output_path: Path for output GeoTIFF
            epsg: EPSG code for coordinate system (default 4326 = WGS84)
            
        Returns:
            True on success, False on error
        """
        try:
            # Open input dataset
            src_ds = gdal.Open(input_tiff, gdal.GA_ReadOnly)
            if src_ds is None:
                print(f"Could not open {input_tiff}")
                return False
            
            # Get raster dimensions
            width = src_ds.RasterXSize
            height = src_ds.RasterYSize
            bands = src_ds.RasterCount
            
            # Create GCP list for GDAL
            gdal_gcps = []
            for i, (px, py, lon, lat) in enumerate(gcps):
                gcp = gdal.GCP(lon, lat, 0, px, py, f"GCP_{i}", str(i))
                gdal_gcps.append(gcp)
            
            # Create spatial reference
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(epsg)
            
            # Create output dataset
            driver = gdal.GetDriverByName('GTiff')
            dst_ds = driver.Create(output_path, width, height, bands, gdal.GDT_Byte,
                                  options=['COMPRESS=LZW', 'TILED=YES'])
            
            if dst_ds is None:
                print(f"Could not create {output_path}")
                return False
            
            # Copy raster data
            for band_idx in range(1, bands + 1):
                src_band = src_ds.GetRasterBand(band_idx)
                dst_band = dst_ds.GetRasterBand(band_idx)
                data = src_band.ReadAsArray()
                dst_band.WriteArray(data)
                
                # Copy color interpretation
                dst_band.SetColorInterpretation(src_band.GetColorInterpretation())
            
            # Set GCPs and projection
            dst_ds.SetGCPs(gdal_gcps, srs.ExportToWkt())
            
            # Flush to disk
            dst_ds.FlushCache()
            dst_ds = None
            src_ds = None
            
            print(f"Created georeferenced GeoTIFF with {len(gcps)} GCPs: {output_path}")
            return True
            
        except Exception as e:
            print(f"Error creating georeferenced TIFF: {e}")
            return False
    
    def create_georeferenced_jp2(self, input_tiff: str, gcps: list, output_path: str, 
                                 epsg: int = 4326) -> bool:
        """
        Create a georeferenced JPEG2000 file using Ground Control Points.
        
        Args:
            input_tiff: Path to input TIFF file
            gcps: List of GCPs as (pixel_x, pixel_y, lon, lat) tuples
            output_path: Path for output JP2 file
            epsg: EPSG code for coordinate system (default 4326 = WGS84)
            
        Returns:
            True on success, False on error
        """
        try:
            # First create georeferenced GeoTIFF
            temp_geotiff = tempfile.NamedTemporaryFile(suffix='_gcp.tif', delete=False)
            temp_geotiff_path = temp_geotiff.name
            temp_geotiff.close()
            self.temp_files.append(temp_geotiff_path)
            
            # Add GCPs to TIFF
            if not self.create_georeferenced_tiff(input_tiff, gcps, temp_geotiff_path, epsg):
                return False
            
            # Convert georeferenced TIFF to JPEG2000
            try:
                ds = gdal.Open(temp_geotiff_path, gdal.GA_ReadOnly)
                if ds is None:
                    print(f"Could not open georeferenced TIFF")
                    return False
                
                # Find JPEG2000 driver
                driver = gdal.GetDriverByName('JP2OpenJPEG')
                if driver is None:
                    for driver_name in ['JP2KAK', 'JP2ECW', 'JPEG2000']:
                        driver = gdal.GetDriverByName(driver_name)
                        if driver:
                            break
                
                if driver is None:
                    print("No JPEG2000 driver available")
                    return False
                
                # JPEG2000 creation options
                options = [
                    'QUALITY=100',
                    'REVERSIBLE=YES',
                    'YCBCR420=NO',
                    'GMLJP2=YES',      # Include GML for georeferencing
                    'GeoJP2=YES'       # Include GeoJP2 UUID box
                ]
                
                print(f"Creating georeferenced JPEG2000 with {len(gcps)} GCPs...")
                out_ds = driver.CreateCopy(output_path, ds, strict=0, options=options)
                
                if out_ds:
                    out_ds.FlushCache()
                    out_ds = None
                    ds = None
                    print(f"Created georeferenced JPEG2000: {output_path}")
                    return True
                else:
                    ds = None
                    return False
                    
            except Exception as e:
                print(f"Error creating JPEG2000: {e}")
                return False
                
        except Exception as e:
            print(f"Error creating georeferenced JPEG2000: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def warp_with_gcps(self, input_geotiff: str, output_path: str, 
                      resample_method: str = 'cubic') -> bool:
        """
        Warp (transform) a GeoTIFF with GCPs to create a properly georeferenced image
        
        Args:
            input_geotiff: Path to GeoTIFF with GCPs
            output_path: Path for warped output
            resample_method: Resampling method ('near', 'bilinear', 'cubic', 'lanczos')
            
        Returns:
            True on success, False on error
        """
        try:
            # Map resample method names
            resample_map = {
                'near': gdal.GRA_NearestNeighbour,
                'bilinear': gdal.GRA_Bilinear,
                'cubic': gdal.GRA_Cubic,
                'lanczos': gdal.GRA_Lanczos
            }
            
            resample_alg = resample_map.get(resample_method.lower(), gdal.GRA_Cubic)
            
            # Warp options
            warp_options = gdal.WarpOptions(
                format='GTiff',
                resampleAlg=resample_alg,
                creationOptions=['COMPRESS=LZW', 'TILED=YES'],
                multithread=True
            )
            
            # Perform the warp
            result = gdal.Warp(output_path, input_geotiff, options=warp_options)
            
            if result is None:
                print(f"Warp failed for {input_geotiff}")
                return False
            
            result = None  # Close dataset
            print(f"Warped GeoTIFF created: {output_path}")
            return True
            
        except Exception as e:
            print(f"Error warping GeoTIFF: {e}")
            return False
    
    def orthorectify_with_gcps(self, input_geotiff: str, output_path: str, 
                               transform_order: int = 1,
                               resample_method: str = 'cubic') -> bool:
        """
        Orthorectify a GeoTIFF using polynomial transformation with GCPs
        
        Args:
            input_geotiff: Path to GeoTIFF with GCPs
            output_path: Path for orthorectified output
            transform_order: Polynomial order (1=affine, 2=2nd order, 3=3rd order, -1=TPS)
            resample_method: Resampling method ('near', 'bilinear', 'cubic', 'lanczos')
            
        Returns:
            True on success, False on error
        """
        try:
            # Map resample method names
            resample_map = {
                'near': gdal.GRA_NearestNeighbour,
                'bilinear': gdal.GRA_Bilinear,
                'cubic': gdal.GRA_Cubic,
                'lanczos': gdal.GRA_Lanczos
            }
            
            resample_alg = resample_map.get(resample_method.lower(), gdal.GRA_Cubic)
            
            # Set transformation type based on order
            if transform_order == -1:
                # Thin Plate Spline - best for non-linear distortions
                transformer = 'tps'
                print(f"Using Thin Plate Spline (TPS) transformation")
            else:
                # Polynomial transformation
                transformer = f'polynomial:{transform_order}'
                print(f"Using {transform_order} order polynomial transformation")
            
            # Warp options with polynomial transformation
            warp_options = gdal.WarpOptions(
                format='GTiff',
                resampleAlg=resample_alg,
                transformerOptions=[f'METHOD={transformer.upper()}'],
                creationOptions=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER'],
                multithread=True,
                errorThreshold=0.125  # Maximum error in pixels
            )
            
            # Perform the orthorectification
            print(f"Orthorectifying with {transformer} transformation...")
            result = gdal.Warp(output_path, input_geotiff, options=warp_options)
            
            if result is None:
                print(f"Orthorectification failed for {input_geotiff}")
                return False
            
            # Get transformation statistics if available
            result_stats = result.GetMetadata()
            result = None  # Close dataset
            
            print(f"Orthorectified GeoTIFF created: {output_path}")
            if 'STATISTICS_MEAN' in result_stats:
                print(f"  Statistics: Mean={result_stats.get('STATISTICS_MEAN')}")
            
            return True
            
        except Exception as e:
            print(f"Error during orthorectification: {e}")
            return False
    
    def extract_georeference_from_tiff(self, tiff_path: str) -> Tuple[List, int, int]:
        """
        Extract georeferencing (GCPs or geotransform) from a TIFF file.
        This handles JPEG2000 HEIF files that may have embedded GMLJP2 georeferencing.
        
        Args:
            tiff_path: Path to TIFF file (converted from HEIF)
            
        Returns:
            Tuple of (gcps_list, width, height) where gcps_list is [(px, py, lon, lat), ...]
        """
        try:
            dataset = gdal.Open(tiff_path, gdal.GA_ReadOnly)
            if not dataset:
                return ([], 0, 0)
            
            width = dataset.RasterXSize
            height = dataset.RasterYSize
            gcps_list = []
            
            # Try to get GCPs first
            gcps = dataset.GetGCPs()
            if gcps and len(gcps) > 0:
                print(f"Found {len(gcps)} GCPs in converted image")
                for gcp in gcps:
                    gcps_list.append((gcp.GCPPixel, gcp.GCPLine, gcp.GCPX, gcp.GCPY))
                dataset = None
                return (gcps_list, width, height)
            
            # Try geotransform (for orthorectified images)
            geotransform = dataset.GetGeoTransform()
            if geotransform and geotransform != (0, 1, 0, 0, 0, 1):
                print(f"Found geotransform in converted image, creating corner GCPs")
                # Create GCPs from corners
                corners = [
                    (0, 0),  # Top-left
                    (width, 0),  # Top-right
                    (width, height),  # Bottom-right
                    (0, height)  # Bottom-left
                ]
                for px, py in corners:
                    lon = geotransform[0] + px * geotransform[1] + py * geotransform[2]
                    lat = geotransform[3] + px * geotransform[4] + py * geotransform[5]
                    gcps_list.append((px, py, lon, lat))
                dataset = None
                return (gcps_list, width, height)
            
            dataset = None
            print("No georeferencing found in converted image")
            return (gcps_list, width, height)
            
        except Exception as e:
            print(f"Error extracting georeference: {e}")
            return ([], 0, 0)
    
    def process_heif_with_ttl(self, heif_path: str, gcps: list, 
                             output_path: str, warp: bool = True,
                             orthorectify: bool = False, 
                             transform_order: int = 1,
                             resample_method: str = 'cubic',
                             original_uuid: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Complete workflow: HEIF -> TIFF -> GeoTIFF with GCPs -> Warped/Orthorectified GeoTIFF
        
        Args:
            heif_path: Path to input HEIF file
            gcps: List of GCPs as (pixel_x, pixel_y, lon, lat) tuples
            output_path: Path for final output GeoTIFF
            warp: Whether to warp the image (recommended for proper display)
            orthorectify: Whether to apply orthorectification with polynomial transformation
            transform_order: Polynomial order for orthorectification (1-3, or -1 for TPS)
            resample_method: Resampling method ('near', 'bilinear', 'cubic', 'lanczos')
            original_uuid: UUID of original HEIF image (if None, generates new one)
            
        Returns:
            Tuple of (success: bool, provenance: Dict)
        """
        # Generate UUIDs for provenance tracking
        if original_uuid is None:
            original_uuid = str(uuid.uuid4())
        
        derived_uuid = str(uuid.uuid4())
        algorithm_uuid = str(uuid.uuid4())
        processing_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Calculate BLAKE3 hash of input HEIF file
        input_hash, input_hash_algo = self.calculate_file_hash(heif_path)
        
        # Determine algorithm name
        if orthorectify:
            if transform_order == -1:
                algorithm_name = "TPS Orthorectification"
            else:
                algorithm_name = f"Polynomial Order {transform_order} Orthorectification"
        elif warp:
            algorithm_name = "GCP Warping"
        else:
            algorithm_name = "GCP Assignment"
        
        # Initialize provenance metadata
        provenance = {
            "original_uuid": original_uuid,
            "derived_uuid": derived_uuid,
            "algorithm_uuid": algorithm_uuid,
            "algorithm_name": algorithm_name,
            "processing_timestamp": processing_timestamp,
            "transform_order": transform_order if orthorectify else None,
            "resample_method": resample_method if (warp or orthorectify) else None,
            "gcp_count": len(gcps),
            "warp_enabled": warp,
            "orthorectify_enabled": orthorectify,
            "input_file": os.path.basename(heif_path),
            "input_hash": input_hash,
            "input_hash_algorithm": input_hash_algo,
            "output_file": os.path.basename(output_path)
        }
        try:
            # Step 1: Convert input raster to TIFF (HEIF via pillow_heif; others via GDAL Translate)
            print(f"Step 1: Converting {os.path.basename(heif_path)} to TIFF...")
            tiff_path = self.convert_any_to_tiff(heif_path)
            if not tiff_path:
                raise Exception(
                    "Could not convert input to TIFF.\n\n"
                    "For HEIF files: ensure pillow-heif or libheif tools are installed.\n"
                    "For other raster formats: ensure GDAL can open the file."
                )
            
            # Step 2: Add GCPs to create georeferenced TIFF
            print(f"Step 2: Adding {len(gcps)} GCPs to TIFF...")
            
            # Determine output format
            is_jp2_export = self.export_format == 'JP2' and output_path.endswith('.jp2')
            
            if warp or orthorectify:
                # Create intermediate file with GCPs
                temp_geo = tempfile.NamedTemporaryFile(suffix='_gcps.tif', delete=False)
                temp_geo_path = temp_geo.name
                temp_geo.close()
                self.temp_files.append(temp_geo_path)
                
                if is_jp2_export:
                    # For JP2 export, create georeferenced GeoTIFF first
                    if not self.create_georeferenced_tiff(tiff_path, gcps, temp_geo_path):
                        return False, provenance
                else:
                    if not self.create_georeferenced_tiff(tiff_path, gcps, temp_geo_path):
                        return False, provenance
                
                # Step 3: Apply transformation
                if orthorectify:
                    print(f"Step 3: Orthorectifying with {transform_order} order transformation...")
                    
                    if is_jp2_export:
                        # Create intermediate orthorectified TIFF
                        temp_ortho = tempfile.NamedTemporaryFile(suffix='_ortho.tif', delete=False)
                        temp_ortho_path = temp_ortho.name
                        temp_ortho.close()
                        self.temp_files.append(temp_ortho_path)
                        
                        if not self.orthorectify_with_gcps(temp_geo_path, temp_ortho_path, 
                                                           transform_order, resample_method):
                            return False, provenance
                        
                        # Convert orthorectified TIFF to JPEG2000
                        print("Step 4: Converting to JPEG2000...")
                        if not self.convert_tiff_to_jp2(temp_ortho_path, output_path):
                            return False, provenance
                    else:
                        if not self.orthorectify_with_gcps(temp_geo_path, output_path, 
                                                           transform_order, resample_method):
                            return False, provenance
                else:
                    print("Step 3: Warping to final output...")
                    
                    if is_jp2_export:
                        # Create intermediate warped TIFF
                        temp_warp = tempfile.NamedTemporaryFile(suffix='_warp.tif', delete=False)
                        temp_warp_path = temp_warp.name
                        temp_warp.close()
                        self.temp_files.append(temp_warp_path)
                        
                        if not self.warp_with_gcps(temp_geo_path, temp_warp_path, resample_method):
                            return False, provenance
                        
                        # Convert warped TIFF to JPEG2000
                        print("Step 4: Converting to JPEG2000...")
                        if not self.convert_tiff_to_jp2(temp_warp_path, output_path):
                            return False, provenance
                    else:
                        if not self.warp_with_gcps(temp_geo_path, output_path, resample_method):
                            return False, provenance
            else:
                # Direct output without warping/orthorectification
                if is_jp2_export:
                    # Create georeferenced JPEG2000
                    if not self.create_georeferenced_jp2(tiff_path, gcps, output_path):
                        return False, provenance
                else:
                    if not self.create_georeferenced_tiff(tiff_path, gcps, output_path):
                        return False, provenance
            
            # Calculate BLAKE3 hash of output GeoTIFF
            output_hash, output_hash_algo = self.calculate_file_hash(output_path)
            provenance['output_hash'] = output_hash
            provenance['output_hash_algorithm'] = output_hash_algo
            
            print(f"Input hash ({input_hash_algo}): {input_hash}")
            print(f"Output hash ({output_hash_algo}): {output_hash}")
            
            # Generate GDAL statistics (.aux.xml) for the output file
            self._compute_gdal_statistics(output_path)
            
            # Extract and add ISO 19115-4 imagery metadata
            if ISO19115_4_AVAILABLE:
                try:
                    print("Extracting ISO 19115-4 imagery metadata...")
                    extractor = ISO19115_4MetadataExtractor()
                    
                    # Open HEIF file to get image object
                    image_obj = None
                    try:
                        image_obj = Image.open(heif_path)
                    except:
                        pass
                    
                    # Extract metadata
                    iso_metadata = extractor.extract_from_heif(heif_path, image_obj)
                    
                    # Enrich provenance with ISO 19115-4 metadata
                    provenance = extractor.enrich_provenance(provenance, iso_metadata)
                    
                    print("✓ ISO 19115-4 metadata added to provenance")
                except Exception as e:
                    print(f"Warning: Could not extract ISO 19115-4 metadata: {e}")
            else:
                print("ISO 19115-4 metadata extractor not available")
            
            # Save provenance metadata as sidecar JSON
            file_ext = '.jp2' if output_path.endswith('.jp2') else '.tif'
            provenance_file = output_path.replace(file_ext, '_provenance.json')
            with open(provenance_file, 'w', encoding='utf-8') as f:
                json.dump(provenance, f, indent=2)
            
            provenance['provenance_file'] = provenance_file
            print(f"Successfully processed HEIF image: {output_path}")
            print(f"Provenance saved to: {provenance_file}")
            return True, provenance
            
        except Exception as e:
            print(f"Error processing HEIF with TTL: {e}")
            return False, provenance

    def _compute_gdal_statistics(self, output_path: str) -> None:
        """
        Compute per-band raster statistics and flush them to a GDAL .aux.xml sidecar file.

        Args:
            output_path: Path to the raster file (GeoTIFF or JP2)
        """
        try:
            from osgeo import gdal as _gdal
            dataset = _gdal.Open(output_path, _gdal.GA_Update)
            if dataset is None:
                print(f"Warning: Could not open {output_path} for statistics computation")
                return
            for band_idx in range(1, dataset.RasterCount + 1):
                band = dataset.GetRasterBand(band_idx)
                band.ComputeStatistics(False)
            dataset.FlushCache()
            dataset = None
            print(f"✓ GDAL statistics written to {output_path}.aux.xml")
        except Exception as e:
            print(f"Warning: Could not compute GDAL statistics: {e}")

    def generate_rdf_provenance(self, provenance: Dict, output_path: str) -> str:
        """
        Generate RDF Turtle file from provenance metadata using W3C PROV-O ontology.
        
        Args:
            provenance: Provenance metadata dictionary
            output_path: Path for output TTL file
            
        Returns:
            Path to generated TTL file
        """
        try:
            rdf_lines = []
            rdf_lines.append("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
            rdf_lines.append("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
            rdf_lines.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
            rdf_lines.append("@prefix prov: <http://www.w3.org/ns/prov#> .")
            rdf_lines.append("@prefix dct: <http://purl.org/dc/terms/> .")
            rdf_lines.append("@prefix geo: <http://www.opengis.net/ont/geosparql#> .")
            rdf_lines.append("@prefix crypto: <http://www.w3.org/2000/10/swap/crypto#> .")
            rdf_lines.append("")
            
            # Original Entity (HEIF file)
            original_uri = f"urn:uuid:{provenance['original_uuid']}"
            rdf_lines.append(f"<{original_uri}>")
            rdf_lines.append("    a prov:Entity ;")
            rdf_lines.append(f"    rdfs:label \"{provenance['input_file']}\" ;")
            rdf_lines.append("    dct:format \"image/heif\" ;")
            if provenance.get('input_hash'):
                rdf_lines.append(f"    crypto:hash \"{provenance['input_hash']}\" ;")
                rdf_lines.append(f"    crypto:hashAlgorithm \"{provenance['input_hash_algorithm']}\" ;")
            rdf_lines.append("    .")
            rdf_lines.append("")
            
            # Derived Entity (output file)
            is_jp2_output = provenance.get('output_file', '').endswith('.jp2')
            output_mime = "image/jp2" if is_jp2_output else "image/tiff"
            output_geometry_label = "JP2 with GCPs" if is_jp2_output else "GeoTIFF with GCPs"
            derived_uri = f"urn:uuid:{provenance['derived_uuid']}"
            rdf_lines.append(f"<{derived_uri}>")
            rdf_lines.append("    a prov:Entity, geo:Feature ;")
            rdf_lines.append(f"    rdfs:label \"{provenance['output_file']}\" ;")
            rdf_lines.append(f"    dct:format \"{output_mime}\" ;")
            rdf_lines.append(f"    geo:hasGeometry \"{output_geometry_label}\" ;")
            if provenance.get('output_hash'):
                rdf_lines.append(f"    crypto:hash \"{provenance['output_hash']}\" ;")
                rdf_lines.append(f"    crypto:hashAlgorithm \"{provenance['output_hash_algorithm']}\" ;")
            rdf_lines.append(f"    prov:wasDerivedFrom <{original_uri}> ;")
            rdf_lines.append(f"    prov:wasGeneratedBy <urn:uuid:{provenance['algorithm_uuid']}> ;")
            rdf_lines.append(f"    prov:generatedAtTime \"{provenance['processing_timestamp']}\"^^xsd:dateTime ;")
            rdf_lines.append("    .")
            rdf_lines.append("")
            
            # Activity (Processing Algorithm)
            activity_uri = f"urn:uuid:{provenance['algorithm_uuid']}"
            rdf_lines.append(f"<{activity_uri}>")
            rdf_lines.append("    a prov:Activity ;")
            rdf_lines.append(f"    rdfs:label \"{provenance['algorithm_name']}\" ;")
            rdf_lines.append(f"    prov:used <{original_uri}> ;")
            rdf_lines.append(f"    prov:startedAtTime \"{provenance['processing_timestamp']}\"^^xsd:dateTime ;")
            
            # Processing parameters
            if provenance.get('gcp_count') is not None:
                rdf_lines.append(f"    prov:qualifiedUsage [")
                rdf_lines.append(f"        a prov:Usage ;")
                rdf_lines.append(f"        rdfs:label \"Ground Control Points\" ;")
                rdf_lines.append(f"        prov:hadRole \"georeferencing\" ;")
                rdf_lines.append(f"        prov:value {provenance['gcp_count']} ;")
                rdf_lines.append(f"    ] ;")
            
            if provenance.get('transform_order') is not None:
                rdf_lines.append(f"    prov:qualifiedUsage [")
                rdf_lines.append(f"        a prov:Usage ;")
                rdf_lines.append(f"        rdfs:label \"Transformation Order\" ;")
                rdf_lines.append(f"        prov:value {provenance['transform_order']} ;")
                rdf_lines.append(f"    ] ;")
            
            if provenance.get('resample_method'):
                rdf_lines.append(f"    prov:qualifiedUsage [")
                rdf_lines.append(f"        a prov:Usage ;")
                rdf_lines.append(f"        rdfs:label \"Resampling Method\" ;")
                rdf_lines.append(f"        prov:value \"{provenance['resample_method']}\" ;")
                rdf_lines.append(f"    ] ;")
            
            rdf_lines.append("    .")
            rdf_lines.append("")
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(rdf_lines))
            
            print(f"RDF provenance saved to: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error generating RDF provenance: {e}")
            return None
    
    def generate_tb21_gimi_rdf(self, gcps: list, image_width: int, image_height: int, 
                                crs: str = "EPSG:4326") -> str:
        """
        Generate TB21 GIMI compliant Turtle RDF from GCPs.
        
        Args:
            gcps: List of GDAL GCP objects with pixel, line, X, Y, Z coordinates
            image_width: Image width in pixels
            image_height: Image height in pixels
            crs: Coordinate reference system (default: EPSG:4326)
            
        Returns:
            Turtle RDF string with embedded GCP metadata
        """
        from datetime import datetime, timezone
        
        # Generate UUID for this correspondence group
        group_uuid = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Start RDF document with TB21 GIMI namespaces
        rdf_lines = [
            "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix cco: <https://www.commoncoreontologies.org/> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix geo: <http://www.opengis.net/ont/geosparql#> .",
            "",
            "# TB21 GIMI Georeference Metadata",
            f"# Generated: {timestamp}",
            f"# CRS: {crs}",
            f"# Image dimensions: {image_width}x{image_height}",
            "",
            f"<urn:uuid:{group_uuid}> a cco:ImageToGroundCorrespondenceGroup ;",
            f'    rdfs:label "GeoTIFF Export Georeferencing" ;',
            f'    cco:designates_image_region <urn:uuid:{uuid.uuid4()}> ;',
            f'    cco:has_correspondence'
        ]
        
        # Generate UUIDs for all GCPs first (to reference them consistently)
        gcp_uuids = []
        for i, gcp in enumerate(gcps):
            gcp_uuids.append({
                'correspondence': str(uuid.uuid4()),
                'image_coord': str(uuid.uuid4()),
                'ground_coord': str(uuid.uuid4())
            })
        
        # Add correspondence URIs to the group
        correspondence_uris = [f"        <urn:uuid:{u['correspondence']}>" for u in gcp_uuids]
        rdf_lines.append(",\n".join(correspondence_uris) + " .")
        rdf_lines.append("")
        
        # Define each correspondence with its image and ground coordinates
        for i, gcp in enumerate(gcps):
            uuids = gcp_uuids[i]
            
            # Image coordinate (pixel, line)
            rdf_lines.extend([
                f"<urn:uuid:{uuids['correspondence']}> a cco:ImageToGroundCorrespondence ;",
                f'    rdfs:label "GCP {i+1}" ;',
                f"    cco:has_image_coordinate <urn:uuid:{uuids['image_coord']}> ;",
                f"    cco:has_ground_coordinate <urn:uuid:{uuids['ground_coord']}> .",
                "",
                f"<urn:uuid:{uuids['image_coord']}> a cco:ImageCoordinate ;",
                f'    cco:has_x_coordinate "{gcp.GCPPixel}"^^xsd:double ;',
                f'    cco:has_y_coordinate "{gcp.GCPLine}"^^xsd:double .',
                "",
                f"<urn:uuid:{uuids['ground_coord']}> a cco:GroundCoordinate ;",
                f'    cco:has_longitude "{gcp.GCPX}"^^xsd:double ;',
                f'    cco:has_latitude "{gcp.GCPY}"^^xsd:double ;',
                f'    cco:has_elevation "{gcp.GCPZ if hasattr(gcp, "GCPZ") else 0.0}"^^xsd:double ;',
                f'    geo:hasSRID """{crs}"""^^xsd:string .',
                ""
            ])
        
        return "\n".join(rdf_lines)
    
    def export_geotiff_to_tb21_heif(self, geotiff_path: str, output_heif_path: str,
                                     quality: int = 95, compression: str = "hevc",
                                     embed_rdf: bool = True) -> Tuple[bool, Dict]:
        """
        Export a GeoTIFF to TB21 GIMI compliant HEIF with embedded RDF metadata.
        
        This enables the reverse workflow: GeoTIFF → TB21 HEIF
        
        Args:
            geotiff_path: Path to input GeoTIFF file
            output_heif_path: Path to output HEIF file
            quality: Encoding quality (1-100, default: 95)
            compression: Compression codec ('hevc', 'av1', 'unci' for uncompressed)
            embed_rdf: If True, embeds RDF metadata using heif-enc (TB21 GIMI compliant)
            
        Returns:
            Tuple of (success: bool, metadata: dict with processing details)
        """
        from datetime import datetime, timezone
        from osgeo import gdal
        import os
        
        print("=" * 80)
        print("GeoTIFF to TB21 GIMI HEIF Export")
        print("=" * 80)
        print(f"Input:  {geotiff_path}")
        print(f"Output: {output_heif_path}")
        print(f"Quality: {quality}, Compression: {compression}")
        print(f"Embed RDF: {embed_rdf}")
        print()
        
        metadata = {
            "input_file": geotiff_path,
            "output_file": output_heif_path,
            "quality": quality,
            "compression": compression,
            "embed_rdf": embed_rdf,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Step 1: Extract GCPs from GeoTIFF
            print("Step 1: Extracting GCPs from GeoTIFF...")
            dataset = gdal.Open(geotiff_path, gdal.GA_ReadOnly)
            if not dataset:
                raise Exception(f"Failed to open GeoTIFF: {geotiff_path}")
            
            gcps = dataset.GetGCPs()
            gcp_projection = dataset.GetGCPProjection()
            geotransform = dataset.GetGeoTransform()
            
            # If no GCPs but has geotransform, create corner GCPs
            if not gcps and geotransform and geotransform != (0, 1, 0, 0, 0, 1):
                print("  → No GCPs found, generating from geotransform...")
                width = dataset.RasterXSize
                height = dataset.RasterYSize
                
                # Create GCPs for four corners
                gcps = []
                corners = [
                    (0, 0, "top-left"),
                    (width, 0, "top-right"),
                    (0, height, "bottom-left"),
                    (width, height, "bottom-right")
                ]
                
                for pixel, line, label in corners:
                    geo_x = geotransform[0] + pixel * geotransform[1] + line * geotransform[2]
                    geo_y = geotransform[3] + pixel * geotransform[4] + line * geotransform[5]
                    gcp = gdal.GCP(geo_x, geo_y, 0, pixel, line, label, "")
                    gcps.append(gcp)
                
                gcp_projection = dataset.GetProjection()
            
            if not gcps:
                raise Exception("No GCPs or geotransform found in GeoTIFF")
            
            print(f"  ✓ Extracted {len(gcps)} GCPs")
            metadata["gcp_count"] = len(gcps)
            metadata["gcp_projection"] = gcp_projection
            
            # Step 2: Generate TB21 GIMI RDF metadata with STAC liability-claims extensions
            rdf_content = None
            rdf_file = None
            if embed_rdf:
                print("Step 2: Generating TB21 GIMI RDF metadata with quality/provenance...")
                
                # Generate base TB21 GIMI RDF
                base_rdf = self.generate_tb21_gimi_rdf(
                    gcps,
                    dataset.RasterXSize,
                    dataset.RasterYSize,
                    gcp_projection or "EPSG:4326"
                )
                
                # Add STAC liability-claims metadata for quality and provenance
                stac_extensions = [
                    "",
                    "# STAC liability-claims extension metadata",
                    "@prefix stac: <http://stacspec.org/> .",
                    "@prefix liability: <https://stac-extensions.github.io/liability-claims/v1.0.0/> .",
                    "@prefix prov: <http://www.w3.org/ns/prov#> .",
                    "@prefix dqv: <http://www.w3.org/ns/dqv#> .",
                    "",
                    "# Data Quality Information (ISO 19115)",
                    "<urn:geotiff:quality> a dqv:QualityMeasurement ;",
                    '    dqv:isMeasurementOf "Geospatial data quality" ;',
                    f'    dqv:value "GeoTIFF with {len(gcps)} control points" ;',
                    f'    liability:scope "dataset" ;',
                    '    liability:conformance [',
                    '        liability:specification "TB21 GIMI Geospatial Metadata Standard" ;',
                    f'        liability:pass "true"^^xsd:boolean ;',
                    f'        liability:explanation "Compliant with TB21 GIMI v1.0 for military geospatial imagery"',
                    '    ] .',
                    "",
                    "# Provenance Information (W3C PROV)",
                    f'<urn:geotiff:source> a prov:Entity ;',
                    f'    prov:label "Source GeoTIFF" ;',
                    f'    prov:location "{os.path.basename(geotiff_path)}" ;',
                    f'    prov:generatedAtTime "{datetime.now(timezone.utc).isoformat()}"^^xsd:dateTime .',
                    "",
                    f'<urn:heif:output> a prov:Entity ;',
                    f'    prov:label "TB21 GIMI HEIF Output" ;',
                    f'    prov:location "{os.path.basename(output_heif_path)}" ;',
                    f'    prov:wasDerivedFrom <urn:geotiff:source> .',
                    "",
                    f'<urn:activity:conversion> a prov:Activity ;',
                    f'    prov:label "GeoTIFF to TB21 HEIF Conversion" ;',
                    f'    prov:used <urn:geotiff:source> ;',
                    f'    prov:startedAtTime "{datetime.now(timezone.utc).isoformat()}"^^xsd:dateTime ;',
                    f'    prov:wasAssociatedWith <urn:agent:qgis-plugin> .',
                    "",
                    '<urn:agent:qgis-plugin> a prov:SoftwareAgent ;',
                    '    prov:label "QGIS HEIF/TTL Importer Plugin" ;',
                    f'    prov:actedOnBehalfOf <urn:agent:user> .',
                    "",
                    '<urn:agent:user> a prov:Agent ;',
                    '    prov:label "QGIS User" .',
                    ""
                ]
                
                # Combine TB21 GIMI RDF with STAC metadata
                rdf_content = base_rdf + "\n".join(stac_extensions)
                
                print(f"  ✓ Generated {len(rdf_content)} bytes of RDF (TB21 GIMI + STAC quality/provenance)")
                print(f"  → Preview: {rdf_content[:200]}...")
                
                # Save RDF to temporary file for heif-enc
                rdf_file = tempfile.NamedTemporaryFile(mode='w', suffix='.ttl', delete=False)
                rdf_file.write(rdf_content)
                rdf_file.close()
                self.temp_files.append(rdf_file.name)
                metadata["rdf_size"] = len(rdf_content)
                metadata["includes_stac_metadata"] = True
            
            # Step 3: Convert to standard image format first (PNG/JPEG)
            print("Step 3: Converting GeoTIFF to intermediate format...")
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            temp_png.close()
            self.temp_files.append(temp_png.name)
            
            # Use GDAL to convert to PNG
            translate_options = gdal.TranslateOptions(
                format='PNG',
                outputType=gdal.GDT_Byte,
                scaleParams=[[0, 255]]
            )
            gdal.Translate(temp_png.name, dataset, options=translate_options)
            print(f"  ✓ Created intermediate PNG: {temp_png.name}")
            
            dataset = None  # Close dataset
            
            # Step 4: Encode to HEIF with heif-enc (supports all codecs including JPEG2000)
            if self.heif_enc_cmd and embed_rdf and rdf_file:
                print("Step 4: Encoding to TB21 GIMI HEIF with embedded RDF...")
                import subprocess
                
                # Build heif-enc command with SAI metadata
                cmd = [
                    self.heif_enc_cmd,
                    temp_png.name,
                    '-o', output_heif_path,
                    '-q', str(quality)
                ]
                
                # heif-enc does not support --plugin-directory on the command line.
                # Use the LIBHEIF_PLUGIN_PATH environment variable instead.
                plugin_dir = os.path.join(os.path.dirname(self.heif_enc_cmd), '..', 'libheif', 'plugins')
                enc_env = os.environ.copy()
                if os.path.exists(plugin_dir):
                    enc_env['LIBHEIF_PLUGIN_PATH'] = plugin_dir
                    print(f"  heif-enc: using plugin dir via LIBHEIF_PLUGIN_PATH: {plugin_dir}")
                
                # Add compression codec
                if compression == 'unci' or compression == 'uncompressed':
                    cmd.extend(['--uncompressed'])
                elif compression == 'av1':
                    cmd.extend(['-e', 'av1'])
                elif compression == 'jpeg2000':
                    cmd.extend(['--jpeg2000'])
                elif compression == 'htj2k':
                    cmd.extend(['--htj2k'])
                # hevc is default
                
                print(f"  → Command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                        env=enc_env)

                if result.returncode != 0:
                    error_msg = result.stderr.strip()
                    
                    # Provide helpful fallback suggestions for codec availability issues
                    if "No JPEG 2000 encoder available" in error_msg:
                        raise Exception(
                            f"JPEG2000 encoder not available in this libheif build.\n"
                            f"  → Try 'hevc' (default), 'av1', or 'uncompressed' instead.\n"
                            f"  → To enable JPEG2000: rebuild libheif with OpenJPEG support"
                        )
                    elif "encoder" in error_msg.lower() and "not available" in error_msg.lower():
                        raise Exception(
                            f"{compression} encoder not available.\n"
                            f"  → {error_msg}\n"
                            f"  → Try 'hevc' (default) or 'uncompressed' instead"
                        )
                    else:
                        raise Exception(f"heif-enc failed: {error_msg}")
                
                # Verify file was created
                if not os.path.exists(output_heif_path):
                    raise Exception(f"heif-enc completed but output file not found: {output_heif_path}")
                
                file_size = os.path.getsize(output_heif_path)
                print(f"  ✓ TB21 GIMI HEIF created ({file_size:,} bytes)")
                
                # Embed RDF using exiftool (heif-enc doesn't support XMP/SAI for single images)
                rdf_embedded = False
                if rdf_file:
                    try:
                        # Try to use exiftool to embed RDF as XMP
                        exiftool_result = subprocess.run(
                            ['exiftool', '-overwrite_original', f'-xmp<={rdf_file.name}', output_heif_path],
                            capture_output=True, text=True, timeout=30
                        )
                        if exiftool_result.returncode == 0:
                            print(f"  ✓ Embedded RDF metadata using exiftool")
                            metadata["encoding_method"] = "heif-enc + exiftool XMP"
                            rdf_embedded = True
                        else:
                            print(f"  ⚠ Could not embed RDF with exiftool: {exiftool_result.stderr}")
                    except FileNotFoundError:
                        print(f"  ⚠ exiftool not found")
                    
                    # If embedding failed or JPEG2000 (which may have issues), save external TTL
                    if not rdf_embedded or compression in ['jpeg2000', 'htj2k']:
                        external_ttl = output_heif_path.replace('.heif', '.ttl')
                        with open(external_ttl, 'w') as f:
                            f.write(rdf_content)
                        print(f"  ✓ Saved external TTL file: {os.path.basename(external_ttl)}")
                        metadata["external_ttl"] = external_ttl
                        if not rdf_embedded:
                            metadata["encoding_method"] = "heif-enc (RDF external)"
                
            else:
                # Fallback: Use pillow-heif without RDF embedding
                print("Step 4: Encoding to HEIF (no RDF embedding - heif-enc not available)...")
                if not HEIF_AVAILABLE:
                    raise Exception("pillow-heif not available and heif-enc not found")
                
                from PIL import Image
                img = Image.open(temp_png.name)
                img.save(output_heif_path, format='HEIF', quality=quality)
                print(f"  ⚠ HEIF created WITHOUT embedded RDF (heif-enc not available)")
                print(f"  → External TTL file saved alongside")
                
                # Save external TTL
                if rdf_content:
                    external_ttl = output_heif_path.replace('.heif', '.ttl')
                    with open(external_ttl, 'w') as f:
                        f.write(rdf_content)
                    metadata["external_ttl"] = external_ttl
                
                metadata["encoding_method"] = "pillow-heif (no SAI)"
            
            # Store actual output file path
            metadata["output_file"] = output_heif_path
            
            # Calculate hash if file was created
            if os.path.exists(output_heif_path):
                if BLAKE3_AVAILABLE:
                    hash_value, hash_algo = self.calculate_file_hash(output_heif_path)
                    metadata["output_hash"] = hash_value
                    metadata["hash_algorithm"] = hash_algo
                    print(f"  ✓ BLAKE3 hash: {hash_value[:16]}...")
            else:
                print(f"  ⚠ Output file not found (expected: {output_heif_path})")
                raise Exception(f"Output file was not created: {output_heif_path}")
            
            print()
            print("=" * 80)
            print("✓ SUCCESS: TB21 GIMI HEIF export complete")
            print("=" * 80)
            
            return True, metadata
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"\n✗ ERROR: {e}")
            print(error_traceback)
            metadata["error"] = str(e)
            metadata["traceback"] = error_traceback
            return False, metadata
    
    def cleanup(self):
        """Remove temporary files"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"Could not remove temp file {temp_file}: {e}")
        self.temp_files.clear()
    
    def __del__(self):
        """Cleanup on deletion"""
        self.cleanup()
