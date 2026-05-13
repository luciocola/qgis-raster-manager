# GIMI Imagery Workbench

A QGIS 3.x plugin that imports HEIF (High Efficiency Image Format) imagery files and uses TTL (Turtle RDF) metadata to automatically georeference them using Ground Control Points (GCPs). Includes full **ISO 19115-4 imagery metadata** extraction and quality reporting. **NEW**: Export GeoTIFF to TB21 GIMI HEIF format with embedded RDF metadata.

> **⚠ PRE-RELEASE NOTICE — CONFORMANCE TESTING NOT YET PERFORMED.**  
> This release has **not** been checked against any formal conformance test suite (OGC, ISO, TB21 GIMI, or equivalent). Output files, metadata structures, and API behaviour may change in a subsequent release once conformance testing results are available. A new release will be issued following successful conformance validation. Use in production environments is at your own risk.

## Features

### Import Capabilities

- **HEIF Image Support**: Import modern HEIF/HEIC image files with full ISO/IEC 23008-12 compliance
- **HEIF Structure Analysis**: Display complete file structure including boxes, metadata, images, thumbnails, and embedded data
- **Internal RDF Support**: Process HEIF files with embedded RDF metadata (TB21 GIMI format)
- **TTL Metadata Parsing**: Extract Ground Control Points from external RDF/TTL metadata files or internal RDF
- **Automatic Georeferencing**: Use image-to-ground coordinate correspondences to georeference imagery
- **GeoTIFF Output**: Convert and export as georeferenced GeoTIFF files
- **JPEG2000 Output**: Optional export as JPEG2000 (.jp2) with better compression and native QGIS support
- **Image Warping**: Optional warping for proper display in geographic coordinates
- **Orthorectification**: Advanced polynomial transformation options (1st-3rd order, TPS)

### Export Capabilities (NEW)

- **TB21 GIMI Export**: Export GeoTIFF to TB21 GIMI compliant HEIF with embedded RDF metadata
- **GCP Extraction**: Automatically extract Ground Control Points from GeoTIFF geotransform or GCPs
- **RDF Generation**: Generate TB21 GIMI compliant Turtle RDF following Common Core Ontologies
- **RDF Embedding**: Use `heif-enc` with SAI (Sample Auxiliary Information) to embed metadata
- **Multiple Codecs**: Support for HEVC, AV1, and uncompressed formats
- **Fallback Mode**: Creates external TTL when `heif-enc` not available

### Quality & Metadata

- **ISO 19115-4 Metadata**: Automatic extraction of imagery-specific metadata quality elements
  - Radiometric accuracy
  - Sensor quality assessment
  - Cloud coverage reporting
  - Processing level documentation
  - Usability assessment for geospatial applications
  - Gridded data spatial representation
  - Acquisition information (platform, sensor, datetime)
- **BLAKE3 Hashing**: Cryptographic signatures for data integrity and interoperability
- **Provenance Tracking**: Full lineage metadata with UUIDs, processing history, and ISO 19115-4 quality reports
- **Multiple Tiles**: Support for tiled imagery with separate GCP sets
- **Advanced Tiling Support**: Automatic detection of grid, tili, and unci tiling modes (see [libheif tiling modes](https://github.com/strukturag/libheif/wiki/heif%E2%80%90enc-Command-Line-Tool#tiling-modes))
- **Uncompressed Format**: Support for ISO 23001-17 uncompressed codec including signed integer data ([PR #1644](https://github.com/strukturag/libheif/pull/1644))
- **SAI Metadata**: Extract Sample Auxiliary Information including GIMI content IDs and TAI timestamps
- **heif-enc Integration**: Optional integration with heif-enc command-line tool for advanced encoding features

## Installation

### Prerequisites

1. **QGIS 3.0+** installed
2. **Python dependencies**:
   ```bash
   pip install pillow pillow-heif gdal blake3
   ```

3. **Optional: libheif command-line tools** (for TB21 GIMI export with embedded RDF):
   - Download from: https://github.com/strukturag/libheif
   - Includes `heif-enc` for creating TB21 GIMI compliant HEIF files
   - Build instructions:
     ```bash
     git clone https://github.com/strukturag/libheif.git
     cd libheif
     mkdir build && cd build
     cmake .. -DCMAKE_BUILD_TYPE=Release -DENABLE_EXPERIMENTAL_FEATURES=on
     make
     sudo make install
     ```
   > **Note:** `-DENABLE_EXPERIMENTAL_FEATURES=on` is required to enable `tili` tiling mode
   > and the `heif-enc` RDF sidecar feature. Without it these features are compiled out.
   - Provides `heif-enc` and `heif-convert` tools for:
     - Advanced tiling modes (grid, tili, unci)
     - Uncompressed codec with signed integer support
     - SAI metadata for GIMI content IDs and timestamps
     - Multi-resolution pyramids
     - Image sequences with metadata tracks

**Note**: BLAKE3 is used for cryptographic hashing to ensure data integrity and interoperability with other defense and emergency response systems. The plugin generates BLAKE3 hashes (with multihash format) for both input and output files, providing verifiable file fingerprints for secure data exchange and provenance tracking.

### Plugin Installation

#### Method 1: Manual Installation
1. Copy the `QGIS imagery workbench` folder to your QGIS plugins directory:
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/`

> **⚠ WARNING: WINDOWS OS INSTALLATION NOT TESTED.**  
> The plugin has been developed and tested on macOS and Linux only. Windows installation is provided on a best-effort basis via `install_windows.ps1` and the QGIS "Install from ZIP" method, but has not been validated. Functionality, dependency installation, and path handling on Windows may require additional steps.

2. Restart QGIS

3. Enable the plugin:
   - Go to **Plugins → Manage and Install Plugins**
   - Find "HEIF/TTL Imagery Importer" in the **Installed** tab
   - Check the box to enable it

#### Method 2: Using pb_tool (for development)
```bash
cd QGIS imagery workbench
pb_tool deploy
```

## Usage

### Analyzing HEIF File Structure

You can analyze the complete structure of a HEIF/HEVC file in two ways:

#### Method 1: Using the Plugin (QGIS)

1. Open the HEIF/TTL Importer dialog
2. Select a HEIF file
3. Click the "Show Structure" button (if available in UI)
4. The complete file structure will be displayed in the metadata preview area

#### Method 2: Standalone Command-Line Tool

Use the included `show_heif_structure.py` utility:

```bash
cd QGIS imagery workbench
python show_heif_structure.py path/to/image.heic
```

This will display:
- **File Information**: Format, brand, size, number of images
- **Image Details**: Dimensions, bit depth, color mode for each image
- **Thumbnails**: All embedded thumbnail images with sizes
- **Metadata**: EXIF, XMP, ICC profiles
- **Color Information**: Color primaries, transfer functions, matrices
- **HDR Data**: HDR metadata if present
- **Encoding**: Compression and encoding details
- **Embedded RDF**: Internal RDF/Turtle metadata (if present)

To save the structure to a text file:
```bash
python show_heif_structure.py path/to/image.heic --save
```

This creates `image.heic_structure.txt` with the complete analysis.

### Example Output

```
================================================================================
HEIF/HEVC FILE STRUCTURE: example.heic
================================================================================

File Size: 4,523,891 bytes (4.31 MB)

FILE INFORMATION:
--------------------------------------------------------------------------------
  Format: HEIF
  Brand: heic
  Number of Images: 1
  HDR Content: No
  ICC Profile: Present (548 bytes)
  EXIF Data: Present (1,234 bytes)

IMAGE #1:
--------------------------------------------------------------------------------
  Size: 4032 x 3024 pixels
  Mode: RGB
  Bit Depth: 24 bits per pixel
  Primary Image: Yes
  Thumbnails: 1
    Thumbnail 1: 320x240
  Compression: HEVC
  Color Primaries: bt709
  
  EXIF: Present
    EXIF Tags:
      Make: Apple
      Model: iPhone 12 Pro
      DateTime: 2024:01:15 14:32:10
      ... and 25 more tags

EMBEDDED RDF METADATA:
--------------------------------------------------------------------------------
  Format: TURTLE
  Size: 2,456 bytes
  Preview:
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix imh: <http://ontology.mil/foundry/IMH#> .
    ...
```

### Basic Workflow

1. **Open the Plugin**:
   - Click the toolbar icon or
   - Go to **Raster → HEIF/TTL Importer → Import HEIF/TTL Imagery**

2. **Select Input Files**:
   - **HEIF Image**: Browse to your `.heif` or `.heic` file
   - **TTL Metadata**: Browse to the corresponding `.ttl` file containing GCPs
   - The plugin will auto-suggest the TTL file if it's in the same directory

3. **Configure Options**:
   - **Output Directory**: Where to save the georeferenced output
   - **Output Format**: Choose between GeoTIFF (.tif) or JPEG2000 (.jp2)
   - **Warp Image**: Enable for proper display (recommended)
   - **Resampling Method**: Choose quality vs. speed tradeoff
     - Cubic: Best quality (default)
     - Lanczos: High quality
     - Bilinear: Good balance
     - Nearest Neighbor: Fastest
   - **Add to Map**: Automatically add result to map canvas

4. **Review Metadata**: The dialog shows a preview of:
   - Number of Ground Control Points found
   - Image dimensions
   - Tile information
   - Available correspondences

5. **Import**: Click **OK** to process

## Exporting GeoTIFF to TB21 GIMI HEIF

### Overview

The plugin now supports **bidirectional workflow** for TB21 GIMI format:

- **Import**: TB21 HEIF (with internal RDF) → GeoTIFF ✅
- **Export**: GeoTIFF → TB21 HEIF (with internal RDF) ✅ **NEW**

### Using the Python API

```python
from heif_processor import HEIFProcessor

processor = HEIFProcessor()

# Export GeoTIFF to TB21 HEIF with embedded RDF
success, metadata = processor.export_geotiff_to_tb21_heif(
    geotiff_path='input.tif',
    output_heif_path='output_tb21.heif',
    quality=95,
    compression='hevc',  # Options: 'hevc', 'av1', 'unci'
    embed_rdf=True
)

if success:
    print(f"✅ Exported {metadata['gcp_count']} GCPs")
    print(f"RDF: {metadata['rdf_size']} bytes")
```

### Using the Test Script

```bash
python test_geotiff_export.py input.tif output_tb21.heif
```

### Export Options

- **quality**: 1-100 (default: 95)
- **compression**: `hevc` (default), `av1`, `unci` (uncompressed)
- **embed_rdf**: `True` (requires `heif-enc` for TB21 GIMI compliance)

### Requirements

**For full TB21 GIMI compliance** (embedded RDF), install `heif-enc`:

```bash
brew install libheif  # macOS
```

Without `heif-enc`, RDF is saved as external `.ttl` file.

See [TB21_EXPORT_FEATURE.md](TB21_EXPORT_FEATURE.md) for complete documentation.

### TTL Metadata Format

The plugin expects TTL files with the following RDF structure:

```turtle
# Image coordinates (pixel positions)
<urn:uuid:img-coord-1>
    imh:_0001626 2048 ;  # X coordinate
    imh:_0001630 1024 ;  # Y coordinate
    a imh:_0001664 ;
    rdfs:label "Image Coordinate" .

# Ground coordinates (geographic positions)
<urn:uuid:ground-coord-1>
    a imh:_0001081 ;
    rdfs:label "Ground Coordinate" ;
    cco:ont00001764 138.665473 ;  # Longitude
    cco:ont00001766 -34.813112 .  # Latitude

# Correspondence (linking image to ground)
<urn:uuid:correspondence-1>
    imh:_0001642 <urn:uuid:img-coord-1> ;
    imh:_0001667 <urn:uuid:ground-coord-1> ;
    a imh:_0001657 ;
    rdfs:label "Correspondence" .
```

### Example

See the included example: `tb21-4x4-grid-hevc.ttl`

This demonstrates:
- 4x4 grid of image tiles
- Multiple GCPs per tile
- Complete image-to-ground correspondences
- WKT polygon boundaries for each tile

## How It Works

### Processing Pipeline

1. **Parse TTL Metadata**:
   - Extract image coordinates (pixel positions)
   - Extract ground coordinates (lat/lon)
   - Link them via correspondences to create GCPs

2. **Convert HEIF to TIFF**:
   - Uses `pillow-heif` to decode HEIF format
   - Converts to uncompressed TIFF

3. **Add GCPs**:
   - Attaches Ground Control Points to TIFF
   - Sets coordinate reference system (EPSG:4326 by default)

4. **Warp Image** (if enabled):
   - Transforms image using GCPs
   - Resamples to geographic coordinates
   - Creates properly georeferenced GeoTIFF

5. **Load in QGIS**:
   - Adds result as raster layer
   - Displays with correct geographic positioning

6. **Generate Provenance**:
   - Calculates BLAKE3 hash of input HEIF file
   - Calculates BLAKE3 hash of output GeoTIFF
   - Creates provenance JSON with full processing metadata
   - Enables verification and interoperability with other systems

### BLAKE3 Hash Format

The plugin uses BLAKE3 hashing with multihash format for interoperability:

- **Format**: `1e20` + 64-character BLAKE3 hexdigest
  - `1e` = Multihash code for BLAKE3
  - `20` = 32 bytes (256 bits) length indicator
  - Hash provides unique file fingerprint for integrity verification

- **Purpose**: 
  - Data integrity verification across systems
  - Interoperability with IPFS and content-addressed storage
  - Provenance tracking for defense and emergency operations
  - Secure data exchange between organizations

- **Fallback**: If BLAKE3 is unavailable, falls back to SHA256 with `1220` prefix

Example provenance output:
```json
{
  "input_hash": "1e202ec513944598549b41a52cb4cbd600c2ee56e8a8c48cdba08ed2fce8d30b8145",
  "input_hash_algorithm": "blake3",
  "output_hash": "1e20a7f3d8e9c2b4f6a1e5d8c7b9f2e4d6a8c5b3f1e9d7c2a4f6e8b1d3c5a7f9",
  "output_hash_algorithm": "blake3",
  "original_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "derived_uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "algorithm_uuid": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}
```

### Coordinate Systems

- **Input**: HEIF image in pixel coordinates
- **GCPs**: Geographic coordinates (WGS84, EPSG:4326)
- **Output**: GeoTIFF in WGS84 projection

## Advanced Features

### Tiled Image Support

The plugin automatically detects and handles three tiling modes defined in the HEIF specification:

1. **Grid Mode** (default):
   - Best decoder compatibility
   - Maximum 65,535 tiles
   - Uses `grid` item reference
   - Supported by all HEIF decoders

2. **Tili Mode** (experimental — requires `-DENABLE_EXPERIMENTAL_FEATURES=on`):
   - Efficient tiling with minimal overhead
   - Practically unlimited tiles
   - Requires libheif decoder built with experimental features
   - Optimized for very large images
   - `tili` has been proposed to MPEG and is expected to be included in **ISO 23008-12, Amd-2** (approval expected end of April 2026). The box syntax has changed during the standardization process. libheif currently implements the **old pre-standard format**; it will switch to the new official syntax once the amendment is approved. That file-format change will be **incompatible** — files encoded with the current experimental `tili` will not be readable by future decoders using the standard syntax. For this reason `tili` remains behind the `EXPERIMENTAL` flag until the standard is finalized.

3. **Unci Mode** (ISO 23001-17):
   - Uses uncompressed codec internal tiling
   - Part of ISO 23001-17 standard
   - Supports signed integer data ([PR #1644](https://github.com/strukturag/libheif/pull/1644))
   - Low overhead, large image support

The plugin automatically detects the tiling mode when analyzing HEIF structure and adjusts processing accordingly.

### SAI Metadata (GIMI Support)

Sample Auxiliary Information (SAI) provides frame-level metadata for:

- **Content IDs**: UUID-based GIMI content identifiers
- **TAI Timestamps**: ISO 23001-17 TAI (International Atomic Time) timestamps
- **Synchronization State**: Frame timing and sync flags

SAI data is automatically extracted when present in HEIF files and included in provenance metadata.

### Uncompressed Format with Signed Integers

The plugin supports the ISO 23001-17 uncompressed codec including the latest signed integer enumeration ([PR #1644](https://github.com/strukturag/libheif/pull/1644)). This enables:

- Lossless imagery with precise numeric values
- Signed integer data for elevation/bathymetry
- Optional compression (deflate, zlib, brotli)
- High-precision scientific data preservation

### heif-enc Integration

When `heif-enc` command-line tool is available, the plugin can leverage advanced encoding features:

```bash
# Check if heif-enc is available
which heif-enc

# Or use custom build location
export HEIF_ENC_PATH=~/Downloads/libheif/build/examples/heif-enc
```

Features enabled with heif-enc:
- Multi-resolution pyramid encoding
- Image sequence encoding with metadata tracks
- Advanced compression options
- Tiling mode selection
- SAI metadata injection

### JPEG2000 Export

The plugin supports exporting georeferenced imagery as JPEG2000 format:

**Advantages of JPEG2000:**
- **Better Compression**: 20-30% smaller than GeoTIFF at same quality
- **Native QGIS Support**: GDAL has built-in JPEG2000 drivers
- **Lossless Mode**: Reversible compression preserves all data
- **Multi-resolution**: Built-in pyramids for efficient zoom
- **Large Images**: Handles very large imagery efficiently
- **Georeferencing**: Supports GML and GeoJP2 UUID boxes

**How to Use:**
1. Open the HEIF/TTL Importer dialog
2. Check "Export as JPEG2000 (.jp2) instead of GeoTIFF"
3. Process your HEIF imagery as normal
4. Output will be georeferenced JPEG2000 file

**Requirements:**
- GDAL with JPEG2000 driver (JP2OpenJPEG, JP2KAK, or JP2ECW)
- Included in standard QGIS installation

**When to Use JPEG2000:**
- Large imagery archives (satellites, aerial photos)
- Web service delivery (WMS/WCS)
- Long-term preservation
- When file size matters
- Scientific data requiring lossless compression

### ISO 19115-4 Imagery Metadata

The plugin automatically extracts and generates **ISO 19115-4** compliant metadata for all imagery:

**What is ISO 19115-4?**

ISO 19115-4:2014 is the international standard for "Geographic information - Metadata - Part 4: Imagery and gridded data". It extends ISO 19115 with imagery-specific quality elements essential for remote sensing and geospatial imagery applications.

**Metadata Elements Extracted:**

1. **Radiometric Accuracy**: Quality of radiometric measurements
2. **Sensor Quality**: Camera/sensor calibration status and health
3. **Cloud Coverage**: Percentage of imagery obscured by clouds
4. **Processing Level**: Level of radiometric and geometric correction (L0, L1A, L1B, L2A, etc.)
5. **Usability Assessment**: Fitness for use in geospatial applications
6. **Acquisition Information**: 
   - Platform (camera make/model)
   - Sensor/instrument details
   - Acquisition datetime
7. **Gridded Data Representation**:
   - Image dimensions (rows/columns)
   - Cell geometry
   - Number of dimensions

**Output Format:**

ISO 19115-4 metadata is embedded in the provenance JSON file created alongside your georeferenced output:

```json
{
  "original_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "derived_uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "iso19115_4": {
    "metadataStandard": "ISO 19115-4:2014",
    "metadataIdentifier": "iso19115-4-my_image-20260128123045",
    "quality": [
      {
        "type": "processingLevel",
        "level": "L0",
        "description": "HEIF imagery - unprocessed sensor data"
      },
      {
        "type": "sensorQuality",
        "sensorType": "Image Sensor (HEIF capable)",
        "calibrationStatus": "unknown"
      },
      {
        "type": "usabilityAssessment",
        "usabilityScore": 0.9,
        "intendedUse": "Geospatial imagery analysis with georeferencing"
      }
    ],
    "acquisitionInformation": {
      "platform": {
        "identifier": "Apple iPhone 12 Pro",
        "description": "Image acquisition platform"
      },
      "instrument": {
        "identifier": "iPhone 12 Pro",
        "type": "optical sensor"
      }
    },
    "gridSpatialRepresentation": {
      "numberOfDimensions": 2,
      "axisDimensionProperties": [
        {"dimensionName": "column", "dimensionSize": 4032},
        {"dimensionName": "row", "dimensionSize": 3024}
      ]
    }
  }
}
```

**Benefits:**

- **Standardized Metadata**: ISO-compliant metadata for interoperability with defense and emergency response systems
- **Quality Assurance**: Documented quality metrics for decision making
- **Lineage Tracking**: Complete provenance from sensor to georeferenced output
- **STAC Integration**: Compatible with STAC (SpatioTemporal Asset Catalog) extensions
- **International Compliance**: Meets NATO, UN, and international geospatial standards

**Compatibility:**

The ISO 19115-4 implementation is compatible with:
- **ISO 19115-1:2014**: Core metadata standard
- **ISO 19157-1:2023**: Data quality measures
- **STAC Liability & Claims Extension**: For quality reporting
- **NATO DGIWG**: Defence Geospatial Information Working Group standards
- **OGC Standards**: OGC SensorThings API, OGC API - Features

For more technical details, see [ISO 19115-4 vs ISO 19157-3 Compatibility](https://github.com/stac-extensions/liability-claims/blob/main/ISO19115-4-vs-ISO19157-3-COMPATIBILITY.md)

## Troubleshooting

### "HEIF support is not available"

Install the required Python package:
```bash
pip install pillow-heif
```

Then restart QGIS.

### "No ground control points found in TTL file"

Check that your TTL file contains:
- Image coordinates (`imh:_0001664`)
- Ground coordinates (`imh:_0001081`)
- Correspondences (`imh:_0001657`)

### "Created GeoTIFF is not valid"

Possible causes:
- Insufficient GCPs (need at least 3)
- Invalid coordinate values
- Corrupted HEIF file

Check the QGIS message log (View → Panels → Log Messages) for detailed error information.

### Image appears distorted

Try different resampling methods:
- Use "Cubic" or "Lanczos" for better quality
- Ensure "Warp image" is enabled
- Check that GCPs are accurate

## Technical Details

### Dependencies

- **QGIS 3.x**: Core GIS functionality
- **PyQt5**: User interface
- **PIL/Pillow**: Image processing
- **pillow-heif**: HEIF format support
- **GDAL/OGR**: Geospatial transformations
- **blake3**: Cryptographic hashing for interoperability (falls back to hashlib.sha256 if unavailable)

### pillow-heif Tile Access API

The [pillow-heif](https://github.com/bigcat88/pillow_heif) maintainer is currently working on adding support for the **libheif tile access API**. Once available, the plugin will use this path for more reliable tiled-image decoding (grid, tili, unci modes) and will replace the current pillow-based workarounds with direct tile-level access.

### Python Bindings for libheif — SWIG Implementation

The current implementation uses a mixture of **pillow-heif**, **libheif command-line tools** (`heif-enc`, `heif-dec`, `heif-info`), **GDAL**, and **ad-hoc byte/string scanning**. pillow-heif only exposes a small subset of the full libheif feature set, CLI tools introduce subprocess overhead, and byte/string scanning is fragile (false positives/negatives — see implementation notes in `heif_processor.py`).

The clean path is to call the **libheif C API directly** via a [SWIG](https://www.swig.org/)-generated Python binding.  The binding lives in `libheif_binding/` and is already wired into `heif_processor.py`.

#### What the binding provides

| C API function | Python surface | Used for |
|---|---|---|
| `heif_context_alloc/free/read_from_file` | `HeifContext.from_file()` | Open any HEIF/AVIF/HEIC file |
| `heif_context_get_list_of_top_level_image_IDs` | `ctx.top_level_image_ids()` | Enumerate images |
| `heif_context_get_image_handle` | `ctx.get_image_handle(id)` | Per-image inspection |
| `heif_image_handle_get_number_of_metadata_blocks` + `get_list_of_metadata_block_IDs` | `handle.metadata_blocks()` | Iterate embedded items |
| `heif_image_handle_get_metadata_content_type` | `block.content_type` | MIME type of each item |
| `heif_image_handle_get_metadata` | `block.read()` | Read raw bytes of any item |
| `heif_image_handle_get_number_of_tiles` | `handle.tile_count` | Confirm tiling (libheif ≥ 1.17) |

`has_internal_rdf()` and `extract_internal_rdf()` now use `HeifContext.find_rdf_metadata()` which inspects metadata block MIME content-types (`text/turtle`, `application/rdf+xml`) — no byte scanning.  The byte-scan path is retained only as a last-resort fallback when the binding has not been compiled.

`detect_tiling_mode()` uses `HeifContext.detect_tiling_mode()`.  Full tiling-type resolution (grid / tili / unci) still falls back to heuristics because `heif_image_handle_get_item_type()` is not yet in libheif's stable public header.  A TODO is recorded in both the SWIG interface and `__init__.py` to wire it in once it is available.

#### Build the binding

```bash
# Prerequisites
brew install swig libheif       # macOS
# apt install swig libheif-dev  # Debian/Ubuntu

cd libheif_binding
./build.sh                      # runs: python setup.py build_ext --inplace
```

After a successful build, `libheif_core.py` and `_libheif_core*.so` appear in `libheif_binding/` and are picked up automatically by `heif_processor.py`.  If the build has not been run, the plugin degrades gracefully to the byte-scan fallback.

#### Future work

- Expose `heif_image_handle_get_item_type()` once libheif adds it to the public header → allows unambiguous grid / tili / unci detection without any heuristics
- `display_heif_structure()`: rewrite using C API box traversal; currently uses ad-hoc parsing (see `show_heif_structure.py`)
- Consider publishing the binding as a standalone `pyheif-native` package for the broader libheif ecosystem

### File Structure

```
QGIS imagery workbench/
├── __init__.py                    # Plugin entry point
├── metadata.txt                   # Plugin metadata
├── heif_ttl_importer.py          # Main plugin class
├── heif_ttl_dialog.py            # Dialog implementation
├── heif_ttl_dialog_base.ui       # Qt Designer UI file
├── ttl_parser.py                 # TTL/RDF parser
├── heif_processor.py             # HEIF to GeoTIFF converter
├── iso19115_4_metadata.py        # ISO 19115-4 metadata extractor
├── show_heif_structure.py        # Standalone HEIF structure analyzer
├── stac_converter.py             # STAC item/collection generation
├── osm_fetcher.py                # OpenStreetMap feature fetcher
├── icon.png                      # Plugin toolbar icon
├── pb_tool.cfg                   # pb_tool deployment configuration
├── deploy.sh                     # Deployment helper script
├── QUICK_REFERENCE.py            # Quick-reference code snippets
├── libheif_binding/              # SWIG-generated libheif C API binding
│   ├── __init__.py               #   Pythonic HeifContext / ImageHandle / MetadataBlock
│   ├── libheif_core.i            #   SWIG interface file (hand-written)
│   ├── setup.py                  #   setuptools build script
│   └── build.sh                  #   One-shot build helper
├── test_heif_structure.py        # Tests for HEIF structure analysis
├── test_geotiff_export.py        # Tests for GeoTIFF → TB21 HEIF export
├── test_internal_rdf.py          # Tests for internal RDF extraction
├── test_rdf_parsing.py           # Tests for TTL/RDF parsing
├── test_unci_support.py          # Tests for uncompressed HEIF codec
├── test_heif_to_jp2.py           # Tests for HEIF → JPEG2000 export
├── test_blake3_hash.py           # Tests for BLAKE3 hashing
└── README.md                     # This file
```

### Key Classes

- **TTLParser**: Parses RDF/TTL files to extract GCPs
- **HEIFProcessor**: Handles HEIF conversion and georeferencing
- **ISO19115_4MetadataExtractor**: Extracts ISO 19115-4 imagery metadata
- **HEIFTTLImporterDialog**: User interface
- **HEIFTTLImporter**: Main plugin integration with QGIS

## License

Copyright (C) 2026 4113Eng-wfs

This plugin is released under the **GNU General Public License v3.0 or later** (GPL-3.0-or-later).

You are free to use, study, modify and distribute it under GPL-3.0-or-later terms.
See the [LICENSE](LICENSE) file or <https://www.gnu.org/licenses/gpl-3.0.html> for the full text.

> **Why GPL-3.0 and not Creative Commons?**  
> Creative Commons licenses are designed for creative works (text, art, media) — the CC organisation
> explicitly recommends against using them for software. This plugin uses PyQt5 (GPL-3.0) and
> libheif (LGPL-3.0), which legally require a GPL-3.0-compatible license for distribution.

## Contributing

Contributions are welcome! Please submit issues and pull requests.

## Credits

Developed by 4113Eng-wfs for defense and emergency response applications.

## Support

For issues and questions, please use the issue tracker or contact [your contact info].
