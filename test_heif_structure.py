#!/usr/bin/env python3
"""
Test script for HEIF structure display functionality.

This script tests the display_heif_structure() method by creating a simple
test case or using an existing HEIF file.
"""

import sys
import os

def test_heif_structure_display():
    """Test the HEIF structure display function"""
    
    print("Testing HEIF Structure Display Functionality")
    print("=" * 60)
    
    # Import the processor
    try:
        from heif_processor import HEIFProcessor
        print("✓ HEIFProcessor imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import HEIFProcessor: {e}")
        return False
    
    # Check dependencies
    processor = HEIFProcessor()
    
    if not processor.is_heif_supported():
        print("✗ HEIF support not available")
        print("  Install dependencies: pip install pillow pillow-heif")
        return False
    
    print("✓ HEIF support available")
    
    # Check if pillow_heif module is accessible
    try:
        import pillow_heif
        print(f"✓ pillow_heif version: {pillow_heif.__version__ if hasattr(pillow_heif, '__version__') else 'unknown'}")
    except ImportError:
        print("✗ pillow_heif not available")
        return False
    
    # Check if PIL is available
    try:
        from PIL import Image
        print(f"✓ PIL/Pillow version: {Image.__version__ if hasattr(Image, '__version__') else 'unknown'}")
    except ImportError:
        print("✗ PIL/Pillow not available")
        return False
    
    # Test with a real file if provided
    if len(sys.argv) > 1:
        heif_path = sys.argv[1]
        if os.path.exists(heif_path):
            print(f"\n✓ Testing with file: {heif_path}")
            print("-" * 60)
            
            try:
                structure = processor.display_heif_structure(heif_path)
                print(structure)
                print("\n✓ Structure display successful")
                return True
            except Exception as e:
                print(f"\n✗ Error displaying structure: {e}")
                import traceback
                traceback.print_exc()
                return False
        else:
            print(f"\n✗ File not found: {heif_path}")
            return False
    else:
        print("\n⚠ No test file provided")
        print("\nUsage:")
        print("  python test_heif_structure.py <path_to_heif_file>")
        print("\nThe display_heif_structure() method is ready to use.")
        print("Provide a HEIF file to see the full structure analysis.")
        return True

if __name__ == "__main__":
    success = test_heif_structure_display()
    sys.exit(0 if success else 1)
