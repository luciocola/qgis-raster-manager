#!/usr/bin/env python3
"""
Test script to verify uncompressed HEIF (unci) support
Demonstrates the complete workflow from unci HEIF to GeoTIFF
"""

import sys
import os

# Test file path
TEST_FILE = "/Users/luciocolaiacomo/4113Eng-wfs/gimi-test-data/T21-GIMI-main-data-NGA_Sample_Data-2025-12-tb21-data-v2/data/NGA_Sample_Data/2025-12-tb21-data-v2/tb21-single-image-uncompressed-internal-rdf.heif"

def test_heif_structure_detection():
    """Test 1: Verify HEIF structure can be analyzed"""
    print("=" * 80)
    print("TEST 1: HEIF Structure Detection")
    print("=" * 80)
    
    from heif_processor import HEIFProcessor
    
    processor = HEIFProcessor()
    structure = processor.display_heif_structure(TEST_FILE)
    
    if structure:
        print("✓ Structure detection successful")
        print("\nStructure preview:")
        print("\n".join(structure[:20]))
        return True
    else:
        print("✗ Structure detection failed")
        return False

def test_heif_dec_availability():
    """Test 2: Verify custom heif-dec is available"""
    print("\n" + "=" * 80)
    print("TEST 2: Custom heif-dec Availability")
    print("=" * 80)
    
    from heif_processor import HEIFProcessor
    
    processor = HEIFProcessor()
    available = processor.check_heif_convert_available()
    
    if available:
        print(f"✓ heif-dec available at: {processor.heif_convert_cmd}")
        return True
    else:
        print("✗ heif-dec not found")
        return False

def test_unci_conversion():
    """Test 3: Verify unci file can be converted to PNG"""
    print("\n" + "=" * 80)
    print("TEST 3: Uncompressed HEIF Conversion")
    print("=" * 80)
    
    from heif_processor import HEIFProcessor
    import tempfile
    
    processor = HEIFProcessor()
    
    # Create temp output
    output_png = os.path.join(tempfile.gettempdir(), 'test_unci_conversion.png')
    
    result = processor.convert_heif_with_libheif(TEST_FILE, output_png)
    
    if result and os.path.exists(output_png):
        size_mb = os.path.getsize(output_png) / (1024 * 1024)
        print(f"✓ Conversion successful")
        print(f"  Output: {output_png}")
        print(f"  Size: {size_mb:.2f} MB")
        
        # Verify it's a valid PNG
        try:
            from PIL import Image
            img = Image.open(output_png)
            print(f"  Dimensions: {img.size[0]} x {img.size[1]}")
            print(f"  Mode: {img.mode}")
            img.close()
        except Exception as e:
            print(f"  Warning: Could not verify PNG: {e}")
        
        # Cleanup
        os.remove(output_png)
        return True
    else:
        print("✗ Conversion failed")
        return False

def test_rdf_extraction():
    """Test 4: Verify internal RDF metadata can be extracted"""
    print("\n" + "=" * 80)
    print("TEST 4: Internal RDF Metadata Extraction")
    print("=" * 80)
    
    from heif_processor import HEIFProcessor
    
    processor = HEIFProcessor()
    rdf_content = processor.extract_internal_rdf(TEST_FILE)
    
    if rdf_content:
        print("✓ RDF extraction successful")
        print(f"  Format: {processor.internal_rdf_format}")
        print(f"  Length: {len(rdf_content)} characters")
        print("\nRDF preview:")
        print(rdf_content[:500] + "...")
        return True
    else:
        print("✗ No RDF metadata found")
        return False

def main():
    """Run all tests"""
    print("\n" + "#" * 80)
    print("# UNCOMPRESSED HEIF (unci) SUPPORT VERIFICATION")
    print("#" * 80)
    print(f"\nTest File: {os.path.basename(TEST_FILE)}")
    
    if not os.path.exists(TEST_FILE):
        print(f"\n✗ ERROR: Test file not found: {TEST_FILE}")
        print("Please update TEST_FILE path in this script.")
        return 1
    
    file_size = os.path.getsize(TEST_FILE) / (1024 * 1024)
    print(f"File Size: {file_size:.2f} MB\n")
    
    # Run tests
    tests = [
        test_heif_structure_detection,
        test_heif_dec_availability,
        test_unci_conversion,
        test_rdf_extraction,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED - Uncompressed HEIF support is working!")
        return 0
    else:
        print(f"\n✗ {total - passed} TEST(S) FAILED")
        return 1

if __name__ == '__main__':
    sys.exit(main())
