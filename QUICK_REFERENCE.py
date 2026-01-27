#!/usr/bin/env python3
"""
Quick Reference - HEIF Structure Display

This file provides code snippets for using the HEIF structure display functionality.
"""

# ============================================================================
# METHOD 1: Standalone Command Line
# ============================================================================

# Basic usage:
# python show_heif_structure.py image.heic

# Save to file:
# python show_heif_structure.py image.heic --save


# ============================================================================
# METHOD 2: Programmatic Usage in Python
# ============================================================================

from heif_processor import HEIFProcessor

# Create processor instance
processor = HEIFProcessor()

# Check if HEIF is supported
if processor.is_heif_supported():
    # Display structure
    structure = processor.display_heif_structure('path/to/image.heic')
    print(structure)
    
    # Save to file
    with open('structure_output.txt', 'w', encoding='utf-8') as f:
        f.write(structure)
else:
    print("HEIF support not available. Install: pip install pillow pillow-heif")


# ============================================================================
# METHOD 3: In QGIS Plugin Dialog
# ============================================================================

# In heif_ttl_dialog.py, the method is already integrated:
# self.btnShowStructure.clicked.connect(self.show_heif_structure)

# The show_heif_structure() method:
# - Gets HEIF path from UI
# - Calls processor.display_heif_structure()
# - Displays result in metadata preview area
# - Shows popup dialog for easier viewing


# ============================================================================
# METHOD 4: Batch Processing Multiple Files
# ============================================================================

import os
from heif_processor import HEIFProcessor

def batch_analyze_heif_files(directory):
    """Analyze all HEIF files in a directory"""
    processor = HEIFProcessor()
    
    if not processor.is_heif_supported():
        print("ERROR: HEIF support not available")
        return
    
    # Find all HEIF files
    heif_extensions = ['.heif', '.heic', '.hif']
    heif_files = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.lower().endswith(ext) for ext in heif_extensions):
                heif_files.append(os.path.join(root, file))
    
    print(f"Found {len(heif_files)} HEIF files")
    
    # Analyze each file
    for heif_path in heif_files:
        print(f"\nAnalyzing: {heif_path}")
        print("=" * 80)
        
        try:
            structure = processor.display_heif_structure(heif_path)
            
            # Save to file next to original
            output_path = heif_path + "_structure.txt"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(structure)
            
            print(f"Saved structure to: {output_path}")
            
        except Exception as e:
            print(f"ERROR: {e}")

# Usage:
# batch_analyze_heif_files('/path/to/heif/files')


# ============================================================================
# METHOD 5: Extract Specific Information
# ============================================================================

import pillow_heif

def get_heif_summary(heif_path):
    """Get quick summary of HEIF file"""
    heif_file = pillow_heif.open_heif(heif_path)
    
    summary = {
        'brand': heif_file.brand,
        'num_images': len(heif_file),
        'file_size': os.path.getsize(heif_path),
        'images': []
    }
    
    for img in heif_file:
        img_info = {
            'size': img.size,
            'mode': img.mode,
            'has_exif': 'exif' in img.info and img.info['exif'] is not None,
            'has_xmp': 'xmp' in img.info and img.info['xmp'] is not None,
            'thumbnail_count': len(img.thumbnails) if hasattr(img, 'thumbnails') else 0
        }
        summary['images'].append(img_info)
    
    return summary

# Usage:
# summary = get_heif_summary('image.heic')
# print(f"Images: {summary['num_images']}")
# print(f"Primary size: {summary['images'][0]['size']}")


# ============================================================================
# METHOD 6: Check for Embedded RDF
# ============================================================================

def check_embedded_rdf(heif_path):
    """Check if HEIF contains embedded RDF metadata"""
    processor = HEIFProcessor()
    
    has_rdf = processor.has_internal_rdf(heif_path)
    
    if has_rdf:
        rdf_content = processor.extract_internal_rdf(heif_path)
        rdf_format = processor.internal_rdf_format
        
        print(f"RDF Format: {rdf_format}")
        print(f"RDF Size: {len(rdf_content)} bytes")
        print("\nPreview:")
        print(rdf_content[:500])
        
        return True
    else:
        print("No embedded RDF found")
        return False

# Usage:
# check_embedded_rdf('tb21_gimi_image.heic')


# ============================================================================
# EXAMPLE OUTPUT
# ============================================================================

"""
Sample output from display_heif_structure():

================================================================================
HEIF/HEVC FILE STRUCTURE: sample.heic
================================================================================

File Size: 2,456,789 bytes (2.34 MB)

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
  Transfer Function: bt709
  
  EXIF: Present
    EXIF Tags:
      Make: Apple
      Model: iPhone 13 Pro
      DateTime: 2024:01:15 14:32:10
      FNumber: 1.5
      ExposureTime: 1/120
      ISOSpeedRatings: 100
      ... and 18 more tags
  
  ICC Profile: Present (548 bytes)

EMBEDDED RDF METADATA:
--------------------------------------------------------------------------------
  Format: TURTLE
  Size: 3,456 bytes
  Preview:
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix imh: <http://ontology.mil/foundry/IMH#> .
    ... (3,456 more bytes)

================================================================================
"""
