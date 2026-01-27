# Installation Guide - HEIF/TTL Imagery Importer

## Quick Start

### 1. Install Python Dependencies

The plugin requires `pillow-heif` to read HEIF images:

```bash
pip install pillow pillow-heif
```

**Important**: You may need to install these packages in QGIS's Python environment:

#### macOS/Linux:
```bash
# Find QGIS Python
/Applications/QGIS.app/Contents/MacOS/bin/pip3 install pillow-heif
```

#### Windows:
```bash
# Open OSGeo4W Shell as Administrator, then:
py3_env
python -m pip install pillow-heif
```

### 2. Deploy the Plugin

#### Option A: Automatic Deployment (macOS/Linux)

```bash
cd heif_ttl_importer
chmod +x deploy.sh
./deploy.sh
```

#### Option B: Manual Deployment

Copy the entire `heif_ttl_importer` folder to your QGIS plugins directory:

**macOS**:
```bash
cp -r heif_ttl_importer ~/Library/Application\ Support/QGIS/QGIS3/profiles/default/python/plugins/
```

**Linux**:
```bash
cp -r heif_ttl_importer ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
```

**Windows**:
```
Copy to: %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\
```

### 3. Enable in QGIS

1. **Restart QGIS** (important!)
2. Go to **Plugins → Manage and Install Plugins**
3. Click the **Installed** tab
4. Find **HEIF/TTL Imagery Importer**
5. Check the box to enable it

### 4. Verify Installation

1. Look for the plugin icon in the toolbar
2. Or go to **Raster → HEIF/TTL Importer**
3. Click to open the import dialog

If you see an error about missing HEIF support, return to step 1.

## Testing the Plugin

### Using the Example Data

1. Download or locate a HEIF image file (`.heif` or `.heic`)
2. Ensure you have the corresponding TTL metadata file
3. Open QGIS and launch the plugin
4. Select your HEIF and TTL files
5. Choose an output directory
6. Click OK to import

### Expected Results

- A georeferenced GeoTIFF will be created
- The image will be automatically added to the map (if enabled)
- The image will display in the correct geographic location
- Ground Control Points from the TTL file will be applied

## Troubleshooting

### "HEIF support is not available"

This means `pillow-heif` is not installed or not in the correct Python environment.

**Solution**:
```bash
# For QGIS Python on macOS
/Applications/QGIS.app/Contents/MacOS/bin/pip3 install pillow-heif

# For QGIS Python on Windows (in OSGeo4W Shell)
python -m pip install pillow-heif

# For Linux
pip3 install pillow-heif
```

Then **restart QGIS**.

### Plugin doesn't appear in menu

1. Check that the plugin folder is in the correct location
2. Look for errors in: **Plugins → Python Console**, then:
   ```python
   import qgis.utils
   qgis.utils.showPluginHelp()
   ```
3. Try reinstalling the plugin

### Import fails with "Invalid TTL file"

- Ensure your TTL file contains the required RDF predicates:
  - `imh:_0001664` (image coordinates)
  - `imh:_0001081` (ground coordinates)
  - `imh:_0001657` (correspondences)
- Check the metadata preview in the dialog for parsing status

### Output image is black or corrupted

- Verify the HEIF file is valid (open it in an image viewer)
- Try a different resampling method
- Check the QGIS message log for GDAL errors

## Advanced Configuration

### Custom EPSG Codes

By default, the plugin uses EPSG:4326 (WGS84). To use a different CRS, modify `heif_processor.py`:

```python
def create_georeferenced_tiff(self, input_tiff: str, gcps: list, output_path: str, 
                              epsg: int = 4326):  # Change this value
```

### Performance Tuning

For large images, adjust GDAL options in `heif_processor.py`:

```python
driver = gdal.GetDriverByName('GTiff')
dst_ds = driver.Create(output_path, width, height, bands, gdal.GDT_Byte,
                      options=[
                          'COMPRESS=LZW',     # Use JPEG for photos
                          'TILED=YES',         # Keep for large images
                          'BIGTIFF=YES'        # Add for >4GB files
                      ])
```

## Uninstallation

1. Disable the plugin in QGIS: **Plugins → Manage and Install Plugins**
2. Delete the plugin folder:
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/heif_ttl_importer`
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/heif_ttl_importer`
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\heif_ttl_importer`
3. Restart QGIS

## Getting Help

- Check the [README.md](README.md) for usage instructions
- Review QGIS message logs: **View → Panels → Log Messages**
- Enable Python debugging in QGIS settings for detailed error output

## System Requirements

- **QGIS**: 3.0 or higher
- **Python**: 3.6 or higher (included with QGIS)
- **RAM**: 4GB minimum (8GB+ recommended for large images)
- **Disk Space**: Enough for input HEIF + output GeoTIFF (typically 2-3x the HEIF size)

## Dependencies Summary

| Package | Purpose | Installation |
|---------|---------|--------------|
| pillow | Image processing | Usually included with QGIS |
| pillow-heif | HEIF format support | `pip install pillow-heif` |
| GDAL | Geospatial operations | Included with QGIS |
| PyQt5 | User interface | Included with QGIS |
