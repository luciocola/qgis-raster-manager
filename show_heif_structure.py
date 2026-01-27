#!/usr/bin/env python3
"""
Standalone utility to display HEIF/HEVC file structure.

Usage:
    python show_heif_structure.py <path_to_heif_file>
    
This will display detailed information about the HEIF file including:
- File metadata and brand information
- All images contained in the file
- Thumbnails and their dimensions
- Color profiles, EXIF, and XMP data
- Embedded RDF metadata (if present)
- HDR information
- Encoding and compression details
"""

import sys
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python show_heif_structure.py <path_to_heif_file>")
        print()
        print("Example:")
        print("  python show_heif_structure.py image.heic")
        sys.exit(1)
    
    heif_path = sys.argv[1]
    
    if not os.path.exists(heif_path):
        print(f"ERROR: File not found: {heif_path}")
        sys.exit(1)
    
    # Import the processor
    try:
        from heif_processor import HEIFProcessor
    except ImportError:
        print("ERROR: Could not import HEIFProcessor")
        print("Make sure you're running this script from the heif_ttl_importer directory")
        sys.exit(1)
    
    # Check if HEIF is supported
    processor = HEIFProcessor()
    if not processor.is_heif_supported():
        print("ERROR: HEIF support not available")
        print("Install required dependencies:")
        print("  pip install pillow pillow-heif")
        sys.exit(1)
    
    # Display the structure
    print()
    structure = processor.display_heif_structure(heif_path)
    print(structure)
    print()
    
    # Option to save to file
    if len(sys.argv) > 2 and sys.argv[2] == '--save':
        output_file = heif_path + "_structure.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(structure)
        print(f"Structure saved to: {output_file}")

if __name__ == "__main__":
    main()
