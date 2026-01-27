# Uncompressed HEIF (unci) Support - Solution Summary

## Problem
The HEIF/TTL Imagery Importer plugin was failing to process TB21 GIMI defense imagery files because they use the **unci (uncompressed)** codec, which is not supported by the standard homebrew libheif installation.

### Error Symptoms
- Files showed "File contains 1 image" but conversion failed
- Error: `Unsupported image type: Image item of type 'unci' is not supported`
- pillow-heif could detect file structure but not decode image data
- All standard libheif tools (heif-convert, heif-dec from homebrew) failed

## Root Cause
The homebrew libheif package (1.21.2) is compiled **without** the uncompressed codec enabled (`WITH_UNCOMPRESSED_CODEC=OFF`). While the source code includes full unci support in `libheif/codecs/uncompressed/`, the binary distributed via homebrew does not include this functionality.

## Solution
Built libheif from source with full uncompressed codec support enabled.

### Build Steps (Completed)
```bash
# 1. Install build dependencies
brew install cmake

# 2. Clone libheif source
cd ~/Downloads
git clone --depth 1 https://github.com/strukturag/libheif.git

# 3. Configure with uncompressed codec enabled
cd libheif
mkdir build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DWITH_UNCOMPRESSED_CODEC=ON \
  -DCMAKE_INSTALL_PREFIX=$HOME/local-libheif \
  -DWITH_EXAMPLES=OFF

# 4. Build
make -j4

# 5. Install (optional - we're using from build directory)
make install
```

### Build Verification
The cmake output confirmed:
```
=== Supported formats ===
format        decoding   encoding
Uncompressed    YES        YES
```

### Test Results
Successfully decoded the TB21 uncompressed HEIF file:
```bash
~/Downloads/libheif/build/examples/heif-dec \
  tb21-single-image-uncompressed-internal-rdf.heif \
  test_unci_output.png
```

Output: **25MB PNG, 4096x4096 RGB, 8-bit** ✓

## Plugin Integration
The HEIF/TTL Importer plugin has been updated to automatically detect and use the custom-built heif-dec decoder:

### Priority Search Order
1. `~/Downloads/libheif/build/examples/heif-dec` - Custom build with unci support (HIGHEST PRIORITY)
2. `~/local-libheif/bin/heif-dec` - Installed custom build
3. `/opt/homebrew/bin/heif-dec` - Homebrew (may not support unci)
4. `/usr/local/bin/heif-dec` - Homebrew Intel Mac
5. `/usr/bin/heif-dec` - System installation

### Code Changes
- Updated `check_heif_convert_available()` to prioritize custom build
- Updated `convert_heif_with_libheif()` to use heif-dec syntax (not heif-convert)
- Updated error messages in `display_heif_structure()` to indicate unci is now supported
- Changed detection to return code 0 or 1 (heif-dec returns 1 for --version)

## Usage
When processing a TB21 GIMI HEIF file:

1. **Load file in QGIS**: Plugins → HEIF/TTL Imagery Importer
2. **Browse to HEIF file**: Select your tb21-*.heif file
3. **Click "Show HEIF Structure"** to analyze the file
   - Will show "Uncompressed - May NOT be supported" in codec detection
   - But conversion will succeed with custom heif-dec
4. **Import normally**: The plugin will automatically use custom heif-dec decoder
   - Conversion to PNG happens transparently
   - PNG is then converted to GeoTIFF with GCPs from RDF metadata

## Technical Details

### Codec Identifier: unci
- Defined in ISO/IEC 23001-17 (Uncompressed Image File Format)
- 4-character code: `unci` (0x756E6369)
- File brand: `mif1` (Media Image File format)
- Used by TB21 GIMI for lossless defense imagery
- Contains raw pixel data without compression

### libheif Architecture
- **Built-in decoder**: Uncompressed codec is compiled into libheif core (not a plugin)
- **CMake flag**: `WITH_UNCOMPRESSED_CODEC` must be ON at compile time
- **Source location**: `libheif/codecs/uncompressed/` directory
- **Decoders included**: 
  - ComponentInterleaveDecoder
  - RowInterleaveDecoder
  - PixelInterleaveDecoder
  - TileComponentInterleaveDecoder
  - MixedInterleaveDecoder

### Supported Uncompressed Formats
The custom build supports various uncompressed interleave modes:
- Component interleave
- Row interleave
- Pixel interleave
- Tile component interleave
- Mixed interleave

## Known Limitations
1. **Homebrew libheif**: Does NOT support unci - must use custom build
2. **pillow-heif**: Uses bundled libheif without unci support - cannot be used directly
3. **File size**: Uncompressed HEIF files are very large (50MB for 4096x4096 image)
4. **Performance**: Decoding is slower than compressed formats (no compression overhead)

## Future Improvements
Consider submitting a homebrew formula patch to enable `WITH_UNCOMPRESSED_CODEC=ON` by default.

## References
- libheif GitHub: https://github.com/strukturag/libheif
- ISO 23001-17: Uncompressed Image File Format
- TB21 GIMI Specification: Defense imagery metadata standard
- heif-dec documentation: https://github.com/strukturag/libheif/wiki

## Verification Commands
Test if your libheif supports unci:
```bash
# Check available decoders
/opt/homebrew/bin/heif-dec --list-decoders
# Should show "uncompressed:" line (may be empty for homebrew)

# Test with custom build
~/Downloads/libheif/build/examples/heif-dec --list-decoders
# Should show decoders for uncompressed format

# Convert test file
~/Downloads/libheif/build/examples/heif-dec \
  input.heif output.png
```

## Status
✅ **RESOLVED**: Uncompressed HEIF files can now be processed by the HEIF/TTL Importer plugin using the custom-built libheif decoder.
