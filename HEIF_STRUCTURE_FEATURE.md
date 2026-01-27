# HEIF Structure Display Feature - Implementation Summary

## Overview
Added comprehensive HEIF/HEVC file structure display functionality to the heif_ttl_importer plugin.

## Changes Made

### 1. Enhanced `heif_processor.py`

#### New Method: `display_heif_structure(heif_path: str) -> str`
- Displays complete HEIF/HEVC file structure
- Returns formatted string with detailed analysis
- Includes:
  - File metadata (size, format, brand)
  - All images in container with dimensions and properties
  - Thumbnails and their sizes
  - Color information (primaries, matrices, transfer functions)
  - EXIF data preview (first 10 tags)
  - XMP metadata
  - ICC color profiles
  - HDR metadata (if present)
  - Embedded RDF/Turtle metadata
  - Encoding and compression details

#### Import Fix
- Added explicit import of `pillow_heif` module
- Properly handles missing pillow_heif dependency

### 2. Enhanced `heif_ttl_dialog.py`

#### New Method: `show_heif_structure()`
- UI integration for structure display
- Shows structure in metadata preview area
- Also displays in popup message box for easier viewing
- Includes error handling and user feedback

#### Updated Constructor
- Added signal connection for `btnShowStructure` button (if present in UI)
- Gracefully handles missing UI button

### 3. New Standalone Tool: `show_heif_structure.py`

Command-line utility for analyzing HEIF files:
```bash
python show_heif_structure.py image.heic
python show_heif_structure.py image.heic --save  # Save to file
```

Features:
- Works independently of QGIS
- Validates dependencies before running
- Optional save to text file
- Clear usage instructions

### 4. New Test Script: `test_heif_structure.py`

Testing utility that:
- Verifies all dependencies are installed
- Tests the structure display function
- Provides diagnostic output
- Can test with real HEIF files

Usage:
```bash
python test_heif_structure.py  # Check dependencies
python test_heif_structure.py image.heic  # Test with file
```

### 5. Updated Documentation: `README.md`

Added new sections:
- **Analyzing HEIF File Structure** with two usage methods
- Example output showing what information is displayed
- Command-line usage examples
- Updated file structure listing

## Usage Examples

### Method 1: Within QGIS Plugin
1. Open HEIF/TTL Importer dialog
2. Select a HEIF file
3. Click "Show Structure" button (if UI updated)
4. View structure in metadata preview area

### Method 2: Command Line
```bash
cd heif_ttl_importer
python show_heif_structure.py /path/to/image.heic
```

### Method 3: Programmatic
```python
from heif_processor import HEIFProcessor

processor = HEIFProcessor()
structure = processor.display_heif_structure('image.heic')
print(structure)
```

## Information Displayed

### File Level
- File size in bytes and MB
- Container format and brand
- Number of images
- HDR capability
- Presence of ICC, EXIF, XMP data

### Per Image
- Dimensions (width x height)
- Color mode (RGB, etc.)
- Bit depth
- Primary image indicator
- Thumbnail count and dimensions
- Encoder information
- Compression type
- Color space details
- HDR metadata
- Orientation
- EXIF tags (preview)
- XMP data (preview)
- ICC profile size

### Embedded Metadata
- RDF/Turtle metadata detection
- Format type (XML/Turtle)
- Size in bytes
- Content preview

## Technical Notes

### Dependencies
Requires:
- `pillow_heif` - For HEIF file parsing
- `PIL/Pillow` - For image processing
- `os`, `sys` - Standard library

### Error Handling
- Graceful degradation if dependencies missing
- Clear error messages
- Detailed stack traces for debugging
- Catches and reports exceptions at each level

### Performance
- Reads file metadata efficiently
- Limits preview lengths to avoid overwhelming output
- Shows first N items for large collections

## Future Enhancements

Potential additions:
- [ ] Add UI button to Qt Designer `.ui` file
- [ ] Export structure to JSON format
- [ ] Add box-level analysis (ISOBMFF boxes)
- [ ] Compare multiple HEIF files
- [ ] Validate HEIF compliance
- [ ] Extract and save embedded images/thumbnails

## Testing

To test the implementation:

1. Check dependencies:
   ```bash
   python test_heif_structure.py
   ```

2. Test with a HEIF file:
   ```bash
   python show_heif_structure.py sample.heic
   ```

3. Verify in QGIS plugin (after adding UI button)

## Compatibility

- Works with HEIF/HEIC files from any source
- Supports HEVC-encoded images
- Handles single and multi-image containers
- Compatible with Apple HEIC photos
- Works with defense/GIMI HEIF files containing RDF
