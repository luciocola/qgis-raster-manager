#!/usr/bin/env python3
"""
Test HEIF to JPEG2000 conversion and QGIS compatibility
"""
import subprocess
import sys
import os
from pathlib import Path

def test_heif_to_jp2_conversion():
    """Test if we can convert HEIF to JPEG2000 and if GDAL/QGIS can read it"""
    
    print("=" * 80)
    print("HEIF to JPEG2000 Conversion Test")
    print("=" * 80)
    print()
    
    # Check if heif-enc is available
    heif_enc_paths = [
        'heif-enc',
        '/usr/local/bin/heif-enc',
        os.path.expanduser('~/Downloads/libheif/build/examples/heif-enc')
    ]
    
    heif_enc = None
    for path in heif_enc_paths:
        try:
            result = subprocess.run([path, '--version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0 or 'heif-enc' in result.stdout or 'heif-enc' in result.stderr:
                heif_enc = path
                print(f"✓ Found heif-enc at: {path}")
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    if not heif_enc:
        print("✗ heif-enc not found. Install libheif:")
        print("  git clone https://github.com/strukturag/libheif.git")
        print("  cd libheif && mkdir build && cd build")
        print("  cmake .. && make")
        return False
    
    # Check for JPEG2000 support
    result = subprocess.run([heif_enc, '--help'], 
                          capture_output=True, 
                          text=True, 
                          timeout=5)
    help_text = result.stdout + result.stderr
    
    if '--jpeg2000' not in help_text:
        print("✗ heif-enc does not support JPEG2000")
        return False
    
    print("✓ heif-enc supports JPEG2000 (experimental)")
    print()
    
    # Test GDAL JPEG2000 support
    print("Checking GDAL JPEG2000 support...")
    try:
        from osgeo import gdal
        
        jp2_drivers = []
        for i in range(gdal.GetDriverCount()):
            driver = gdal.GetDriver(i)
            short_name = driver.ShortName
            long_name = driver.LongName
            
            if 'JP2' in short_name or 'JPEG2000' in long_name or 'jpeg2000' in long_name.lower():
                jp2_drivers.append(f"{short_name} ({long_name})")
        
        if jp2_drivers:
            print(f"✓ GDAL has {len(jp2_drivers)} JPEG2000 driver(s):")
            for driver in jp2_drivers:
                print(f"  - {driver}")
        else:
            print("✗ No JPEG2000 drivers found in GDAL")
            print("  You may need to install GDAL with OpenJPEG support:")
            print("  brew install gdal")
            return False
        
        print()
        
        # Test reading a simple JPEG2000 file
        print("Testing GDAL JPEG2000 read capability...")
        
        # Create a test JP2 file using heif-enc (if we have a test HEIF file)
        test_heif = None
        test_dirs = [
            os.getcwd(),
            os.path.expanduser('~/Downloads'),
            os.path.expanduser('~/Desktop')
        ]
        
        for dir_path in test_dirs:
            for ext in ['.heif', '.heic', '.HEIF', '.HEIC']:
                test_files = list(Path(dir_path).glob(f'*{ext}'))
                if test_files:
                    test_heif = str(test_files[0])
                    break
            if test_heif:
                break
        
        if test_heif:
            print(f"Found test HEIF file: {test_heif}")
            
            # Convert to JPEG2000
            output_jp2 = '/tmp/test_conversion.jp2'
            print(f"Converting to JPEG2000: {output_jp2}")
            
            cmd = [heif_enc, '--jpeg2000', test_heif, '-o', output_jp2]
            print(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=30)
            
            if result.returncode == 0 and os.path.exists(output_jp2):
                print(f"✓ Successfully created JPEG2000 file")
                
                # Try to open with GDAL
                ds = gdal.Open(output_jp2, gdal.GA_ReadOnly)
                if ds:
                    print("✓ GDAL can read the JPEG2000 file!")
                    print(f"  Size: {ds.RasterXSize} x {ds.RasterYSize}")
                    print(f"  Bands: {ds.RasterCount}")
                    print(f"  Driver: {ds.GetDriver().ShortName}")
                    ds = None
                    
                    print()
                    print("=" * 80)
                    print("RESULT: HEIF → JPEG2000 → QGIS workflow is SUPPORTED!")
                    print("=" * 80)
                    print()
                    print("You can use JPEG2000 as an intermediate or output format.")
                    print("QGIS will be able to display JPEG2000 files created from HEIF.")
                    print()
                    
                    # Clean up
                    os.remove(output_jp2)
                    return True
                else:
                    print("✗ GDAL could not open the JPEG2000 file")
                    if os.path.exists(output_jp2):
                        print(f"  File exists: {output_jp2}")
                        print(f"  File size: {os.path.getsize(output_jp2)} bytes")
            else:
                print("✗ JPEG2000 conversion failed")
                if result.stderr:
                    print(f"  Error: {result.stderr}")
        else:
            print("No test HEIF file found. Skipping conversion test.")
            print()
            print("CONCLUSION:")
            print("- heif-enc supports JPEG2000 encoding (experimental)")
            print("- GDAL has JPEG2000 drivers available")
            print("- Conversion should work, but needs testing with actual HEIF file")
            
    except ImportError as e:
        print(f"✗ Could not import GDAL: {e}")
        print("  Make sure GDAL Python bindings are installed")
        return False
    except Exception as e:
        print(f"✗ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == '__main__':
    success = test_heif_to_jp2_conversion()
    sys.exit(0 if success else 1)
