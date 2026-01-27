# HEIF to JPEG2000 Conversion Support

## Summary

**YES**, it is possible to convert HEIF to JPEG2000 and display it in QGIS!

## Technical Details

### Conversion Tools

1. **heif-enc** (from libheif) supports JPEG2000 encoding:
   ```bash
   heif-enc --jpeg2000 input.heif -o output.jp2
   ```
   - Status: Experimental in libheif
   - Format: Creates standard JPEG2000 files (.jp2, .j2k)
   - Compression: Supports both lossy and lossless modes

2. **heif-enc** also supports HT-JPEG2000 (High Throughput):
   ```bash
   heif-enc --htj2k input.heif -o output.jhc
   ```
   - Faster encoding/decoding than standard JPEG2000
   - Suitable for high-resolution imagery

### QGIS Support

QGIS includes GDAL which has multiple JPEG2000 drivers:

- **JP2OpenJPEG**: OpenJPEG-based driver (most common)
- **JP2KAK**: Kakadu driver (commercial, high performance)
- **JP2ECW**: ECW/JPEG2000 driver
- **JPEG2000**: Generic driver

QGIS can read and display JPEG2000 files natively through GDAL.

## Why Use JPEG2000?

### Advantages

1. **Better Compression**: 
   - 20-30% better than JPEG at same quality
   - Supports both lossy and lossless compression

2. **Large Images**:
   - Handles very large images efficiently
   - Progressive decoding (can view while loading)
   - Region of interest (ROI) decoding

3. **Metadata**:
   - Extensive metadata support
   - GeoTIFF-like georeferencing via GML boxes
   - Can embed XML metadata

4. **Quality Scalability**:
   - Multiple quality layers in single file
   - Progressive quality improvement

5. **Multi-resolution**:
   - Built-in pyramids/overviews
   - Efficient zoom operations

### Use Cases for HEIF → JPEG2000

1. **Archive Format**: Long-term preservation of imagery
2. **Web Services**: OGC WMS/WCS delivery
3. **Large Imagery**: Satellite/aerial imagery > 10k x 10k
4. **Quality Requirements**: When lossless compression needed
5. **Interoperability**: Better support than HEIF in GIS tools

## Implementation in Plugin

The plugin can add JPEG2000 as an output option:

### Option 1: Direct Conversion (heif-enc)

```python
def convert_heif_to_jp2(self, heif_path: str, output_path: str, 
                        lossless: bool = True) -> Optional[str]:
    """
    Convert HEIF to JPEG2000 using heif-enc
    
    Args:
        heif_path: Path to input HEIF file
        output_path: Path for output JP2 file
        lossless: If True, use lossless compression
        
    Returns:
        Path to output file or None on error
    """
    if not self.heif_enc_cmd:
        if not self.check_heif_enc_available():
            return None
    
    cmd = [
        self.heif_enc_cmd,
        '--jpeg2000',
        heif_path,
        '-o', output_path
    ]
    
    if lossless:
        cmd.insert(2, '-L')  # Lossless mode
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return output_path
        else:
            print(f"JPEG2000 conversion failed: {result.stderr}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None
```

### Option 2: Two-step (HEIF → TIFF → JP2)

For cases where heif-enc is not available:

```python
def convert_heif_to_jp2_via_tiff(self, heif_path: str, output_path: str) -> Optional[str]:
    """Convert HEIF → TIFF → JPEG2000 using GDAL"""
    # 1. Convert HEIF to TIFF (existing method)
    tiff_path = self.convert_heif_to_tiff(heif_path)
    if not tiff_path:
        return None
    
    # 2. Convert TIFF to JPEG2000 using GDAL
    try:
        ds = gdal.Open(tiff_path)
        driver = gdal.GetDriverByName('JP2OpenJPEG')
        
        options = [
            'QUALITY=100',  # Lossless
            'REVERSIBLE=YES',
            'YCBCR420=NO'  # Preserve full color
        ]
        
        out_ds = driver.CreateCopy(output_path, ds, options=options)
        out_ds = None
        ds = None
        
        return output_path
    except Exception as e:
        print(f"GDAL JP2 conversion failed: {e}")
        return None
```

## Recommended Workflow

For the HEIF/TTL Importer plugin:

1. **Primary**: Keep GeoTIFF as default (best QGIS compatibility)
2. **Option**: Add JPEG2000 as alternative output format
3. **Use heif-enc** when available (faster, direct)
4. **Fallback to GDAL** when heif-enc not available
5. **Add to dialog**: Checkbox "Export as JPEG2000 (.jp2)"

## Testing

To test HEIF → JPEG2000 → QGIS workflow:

```bash
# 1. Convert HEIF to JPEG2000
heif-enc --jpeg2000 input.heif -o output.jp2

# 2. Check file info
gdalinfo output.jp2

# 3. Open in QGIS
# Load the .jp2 file via Layer → Add Raster Layer
# or drag and drop into QGIS
```

## Performance Comparison

| Format | Size | Load Time | Quality | QGIS Support |
|--------|------|-----------|---------|--------------|
| HEIF | Smallest | Fast* | Excellent | Limited** |
| JPEG2000 | Medium | Medium | Excellent | Native |
| GeoTIFF (LZW) | Larger | Fast | Lossless | Native |
| GeoTIFF (uncompressed) | Largest | Fastest | Lossless | Native |

\* When codec is supported  
\** Requires pillow-heif, not all codecs supported

## Conclusion

JPEG2000 is a viable intermediate/output format for HEIF imagery:

✓ **Supported** by heif-enc (libheif)  
✓ **Natively readable** by QGIS/GDAL  
✓ **Better compression** than TIFF  
✓ **Lossless mode** available  
✓ **Georeferencing** supported via GML boxes  

Recommended for:
- Large imagery archives
- Web service delivery
- When HEIF codec compatibility is uncertain
- Long-term preservation requirements
