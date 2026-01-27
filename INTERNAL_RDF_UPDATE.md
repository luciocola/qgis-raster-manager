# HEIF/TTL Importer - Internal RDF Support Update

## Overview
Updated the HEIF/TTL Importer plugin to support HEIF files with embedded RDF metadata (TB21 GIMI format), making external TTL files optional when internal RDF is present.

## Changes Made

### 1. heif_processor.py
Added detection and extraction of internal RDF metadata from HEIF files:

- **`has_internal_rdf(heif_path)`**: Detects if HEIF file contains embedded RDF
  - Supports XML/RDF format (`<rdf:RDF`)
  - Supports Turtle format (`@prefix rdf:`, `@prefix rdfs:`)
  - Supports XMP format (`<?xpacket`)
  
- **`extract_internal_rdf(heif_path)`**: Extracts embedded RDF content
  - Returns Turtle format (up to 200 lines)
  - Returns full XML/RDF blocks
  - Stores in `self.internal_rdf` and `self.internal_rdf_format`

### 2. heif_ttl_dialog.py
Updated UI to handle internal RDF and make TTL optional:

- **`check_heif_metadata()`**: Checks HEIF for internal RDF on file selection
- **`display_internal_rdf_preview()`**: Shows internal RDF in preview pane
- **Updated `browse_heif()`**: Detects internal RDF and shows info message
- **Updated `validate()`**: Makes TTL optional when internal RDF exists
  - Validates either external TTL OR internal RDF
  - Shows clear error messages about metadata requirements
  - Validates GCPs from either source

### 3. ttl_parser.py
Added support for parsing RDF from strings (not just files):

- **Updated `__init__()`**: Made `ttl_file_path` parameter optional
- **`parse_string(ttl_content)`**: Parses RDF/TTL content from string
- **`_parse_all()`**: Refactored parsing logic to avoid duplication

### 4. heif_ttl_importer.py
Updated import processing to use either external TTL or internal RDF:

- **Updated `process_import()`**: 
  - Checks for TTL parser first
  - Falls back to internal RDF if available
  - Parses internal RDF using `TTLParser.parse_string()`
  - Extracts GCPs from either source
  - Logs metadata source being used

### 5. test_internal_rdf.py
Created test script to verify internal RDF detection:

- Tests HEIF support availability
- Detects internal RDF format
- Extracts and displays RDF preview
- Parses RDF and shows GCP count
- Displays first 5 GCPs

## Usage

### With External TTL File (Original Workflow)
1. Select HEIF file
2. Select TTL file
3. Configure output options
4. Import

### With Internal RDF (New Workflow)
1. Select HEIF file with internal RDF (e.g., TB21 GIMI)
2. TTL field remains empty - plugin detects internal RDF
3. Info message shows: "Internal RDF metadata detected..."
4. Preview shows internal RDF content
5. Configure output options
6. Import

## Validation Logic

The plugin now validates metadata with this logic:

```
IF has_external_ttl:
    Use external TTL for GCPs
ELSE IF has_internal_rdf:
    Extract and parse internal RDF for GCPs
ELSE:
    Show error: Need either external TTL OR internal RDF
```

## Supported RDF Formats

1. **Turtle Format** (TB21 GIMI standard)
   ```turtle
   @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
   @prefix imh: <http://ontology.commonsemantics.com/imh#> .
   ...
   ```

2. **XML/RDF Format**
   ```xml
   <rdf:RDF xmlns:rdf="..." xmlns:imh="...">
   ...
   </rdf:RDF>
   ```

3. **XMP Format**
   ```xml
   <?xpacket begin="..." id="..."?>
   <x:xmpmeta xmlns:x="adobe:ns:meta/">
   ...
   ```

## Testing

Run the test script:
```bash
cd /path/to/heif_ttl_importer
/Applications/QGIS-LTR.app/Contents/MacOS/bin/python3 test_internal_rdf.py
```

Provide a TB21 GIMI HEIF file at:
```
/Users/luciocolaiacomo/4113Eng-wfs/gimi-test-data/test.heif
```

## Deployment

```bash
cd /path/to/heif_ttl_importer
./deploy.sh
```

Then restart QGIS and enable the plugin.

## Dependencies

- Python 3.9+
- QGIS 3.x
- pillow-heif (HEIF image support)
- GDAL (georeferencing)

Install via QGIS Python:
```bash
/Applications/QGIS-LTR.app/Contents/MacOS/bin/python3 -m pip install pillow-heif
```

## Error Handling

The plugin now provides clear error messages:

- ✓ "Internal RDF metadata detected" - when HEIF has embedded RDF
- ⚠️ "No RDF metadata found. Please provide either external TTL OR HEIF with internal RDF" - when neither source available
- ❌ "Could not extract internal RDF metadata" - when extraction fails
- ❌ "No ground control points found" - when RDF has no GCPs

## Technical Details

### Binary RDF Detection
Searches HEIF binary data for:
- `b'<rdf:RDF'` (XML/RDF)
- `b'@prefix rdf:'` (Turtle)
- `b'@prefix rdfs:'` (Turtle)
- `b'<?xpacket'` (XMP)

### RDF Extraction
- Turtle: Extracts from start marker to 200 lines
- XML/RDF: Extracts complete `<rdf:RDF>...</rdf:RDF>` block
- XMP: Extracts complete `<?xpacket>...</xpacket>` block

### GCP Parsing
Uses same TTL/RDF parser for both sources:
- Image coordinates: `imh:_0001626` (x), `imh:_0001630` (y)
- Ground coordinates: `cco:ont00001764` (lon), `cco:ont00001766` (lat)
- Correspondences: `imh:_0001642` (image), `imh:_0001667` (ground)

## Future Enhancements

Potential improvements:
- [ ] Add rdflib for more robust RDF parsing
- [ ] Support additional RDF formats (JSON-LD, N-Triples)
- [ ] Validate RDF schema compliance
- [ ] Extract additional metadata (timestamps, sensors, etc.)
- [ ] Cache internal RDF to avoid re-extraction
- [ ] Support multiple correspondence groups
- [ ] Add RDF editing capabilities

## Changelog

### 2024-01-XX - v1.1.0
- Added internal RDF detection and extraction
- Made external TTL files optional
- Added support for TB21 GIMI HEIF format
- Added TTLParser.parse_string() method
- Updated validation logic for dual metadata sources
- Added test script for internal RDF
- Improved error messages and user feedback

## License

Same as parent plugin.
