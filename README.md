# HEIF/TTL Imagery Importer for QGIS

A QGIS 3.x plugin that imports HEIF (High Efficiency Image Format) imagery files and uses TTL (Turtle RDF) metadata to automatically georeference them using Ground Control Points (GCPs).

## Features

- **HEIF Image Support**: Import modern HEIF/HEIC image files with full ISO/IEC 23008-12 compliance
- **HEIF Structure Analysis**: Display complete file structure including boxes, metadata, images, thumbnails, and embedded data
- **Internal RDF Support**: Process HEIF files with embedded RDF metadata (TB21 GIMI format)
- **TTL Metadata Parsing**: Extract Ground Control Points from external RDF/TTL metadata files or internal RDF
- **Automatic Georeferencing**: Use image-to-ground coordinate correspondences to georeference imagery
- **GeoTIFF Output**: Convert and export as georeferenced GeoTIFF files
- **JPEG2000 Output**: Optional export as JPEG2000 (.jp2) with better compression and native QGIS support
- **Image Warping**: Optional warping for proper display in geographic coordinates
- **Orthorectification**: Advanced polynomial transformation options (1st-3rd order, TPS)
- **BLAKE3 Hashing**: Cryptographic signatures for data integrity and interoperability
- **Provenance Tracking**: Full lineage metadata with UUIDs and processing history
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

3. **Optional: libheif command-line tools** (for advanced features):
   - Download from: https://github.com/strukturag/libheif
   - Build instructions:
     ```bash
     git clone https://github.com/strukturag/libheif.git
     cd libheif
     mkdir build && cd build
     cmake .. -DCMAKE_BUILD_TYPE=Release
     make
     sudo make install
     ```
   - Provides `heif-enc` and `heif-convert` tools for:
     - Advanced tiling modes (grid, tili, unci)
     - Uncompressed codec with signed integer support
     - SAI metadata for GIMI content IDs and timestamps
     - Multi-resolution pyramids
     - Image sequences with metadata tracks

**Note**: BLAKE3 is used for cryptographic hashing to ensure data integrity and interoperability with other defense and emergency response systems. The plugin generates BLAKE3 hashes (with multihash format) for both input and output files, providing verifiable file fingerprints for secure data exchange and provenance tracking.

### Plugin Installation

#### Method 1: Manual Installation
1. Copy the `heif_ttl_importer` folder to your QGIS plugins directory:
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/`

2. Restart QGIS

3. Enable the plugin:
   - Go to **Plugins → Manage and Install Plugins**
   - Find "HEIF/TTL Imagery Importer" in the **Installed** tab
   - Check the box to enable it

#### Method 2: Using pb_tool (for development)
```bash
cd heif_ttl_importer
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
cd heif_ttl_importer
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

2. **Tili Mode** (libheif-specific):
   - Efficient tiling with minimal overhead
   - Practically unlimited tiles
   - Requires libheif decoder
   - Optimized for very large images

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

### File Structure

```
heif_ttl_importer/
├── __init__.py                    # Plugin entry point
├── metadata.txt                   # Plugin metadata
├── heif_ttl_importer.py          # Main plugin class
├── heif_ttl_dialog.py            # Dialog implementation
├── heif_ttl_dialog_base.ui       # Qt Designer UI file
├── ttl_parser.py                 # TTL/RDF parser
├── heif_processor.py             # HEIF to GeoTIFF converter
├── show_heif_structure.py        # Standalone HEIF structure analyzer
└── README.md                     # This file
```

### Key Classes

- **TTLParser**: Parses RDF/TTL files to extract GCPs
- **HEIFProcessor**: Handles HEIF conversion and georeferencing
- **HEIFTTLImporterDialog**: User interface
- **HEIFTTLImporter**: Main plugin integration with QGIS

## License

[Add your license here]

## Contributing

Contributions are welcome! Please submit issues and pull requests.

## Credits

Developed by 4113Eng-wfs for defense and emergency response applications.

## Support

For issues and questions, please use the issue tracker or contact [your contact info].
