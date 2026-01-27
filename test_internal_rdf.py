#!/usr/bin/env python3
"""
Test script for HEIF files with internal RDF metadata
"""
import os
import sys
from pathlib import Path

# Add plugin directory to path
plugin_dir = Path(__file__).parent
sys.path.insert(0, str(plugin_dir))

from heif_processor import HEIFProcessor
from ttl_parser import TTLParser


def test_internal_rdf_detection():
    """Test detection of internal RDF in HEIF files"""
    print("=" * 80)
    print("HEIF Internal RDF Detection Test")
    print("=" * 80)
    
    # Test with TB21 GIMI test file (if exists)
    test_file = "/Users/luciocolaiacomo/4113Eng-wfs/gimi-test-data/test.heif"
    
    if not os.path.exists(test_file):
        print(f"\n⚠️  Test file not found: {test_file}")
        print("Please provide a TB21 GIMI HEIF file with internal RDF metadata")
        return False
    
    print(f"\nTesting file: {test_file}")
    print("-" * 80)
    
    # Create processor
    processor = HEIFProcessor()
    
    # Check HEIF support
    if not processor.is_heif_supported():
        print("❌ HEIF support not available - install pillow-heif")
        return False
    
    print("✓ HEIF support available")
    
    # Check for internal RDF
    print("\nChecking for internal RDF metadata...")
    has_rdf = processor.has_internal_rdf(test_file)
    
    if has_rdf:
        print(f"✓ Internal RDF detected! Format: {processor.internal_rdf_format}")
        
        # Extract RDF
        print("\nExtracting internal RDF...")
        rdf_content = processor.extract_internal_rdf(test_file)
        
        if rdf_content:
            print(f"✓ Extracted {len(rdf_content)} characters of RDF")
            
            # Show preview
            lines = rdf_content.split('\n')[:20]
            print("\nRDF Preview (first 20 lines):")
            print("-" * 80)
            for line in lines:
                print(line)
            print("-" * 80)
            
            # Try to parse RDF
            print("\nParsing RDF with TTLParser...")
            parser = TTLParser()
            success = parser.parse_string(rdf_content)
            
            if success:
                print(f"✓ RDF parsed successfully!")
                print(f"  - Image coordinates: {len(parser.image_coords)}")
                print(f"  - Ground coordinates: {len(parser.ground_coords)}")
                print(f"  - Correspondences: {len(parser.correspondences)}")
                
                if parser.correspondences:
                    print("\nExtractable Ground Control Points:")
                    gcps = parser.get_all_gcps()
                    for i, gcp in enumerate(gcps[:5], 1):  # Show first 5
                        img_x, img_y, geo_lon, geo_lat = gcp
                        print(f"  GCP {i}: img({img_x},{img_y}) -> "
                              f"geo({geo_lon:.6f},{geo_lat:.6f})")
                    if len(gcps) > 5:
                        print(f"  ... and {len(gcps) - 5} more")
                    
                    return True
                else:
                    print("⚠️  No correspondences found in RDF")
                    return False
            else:
                print("❌ Failed to parse RDF")
                return False
        else:
            print("❌ Failed to extract RDF")
            return False
    else:
        print("❌ No internal RDF metadata detected")
        print("\nSearched for:")
        print("  - XML/RDF format: <rdf:RDF")
        print("  - Turtle format: @prefix rdf:")
        print("  - XMP format: <?xpacket")
        return False


def main():
    """Main test runner"""
    success = test_internal_rdf_detection()
    
    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED: Internal RDF detection working!")
    else:
        print("❌ TEST FAILED: Check errors above")
    print("=" * 80)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
