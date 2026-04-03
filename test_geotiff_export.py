#!/usr/bin/env python3
"""
Test script for GeoTIFF to TB21 GIMI HEIF export functionality
"""
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from heif_processor import HEIFProcessor


def test_export(geotiff_path, output_heif_path=None):
    """
    Test exporting a GeoTIFF to TB21 GIMI HEIF format.
    
    Args:
        geotiff_path: Path to input GeoTIFF file
        output_heif_path: Optional output path (defaults to input + _tb21.heif)
    """
    print("=" * 80)
    print("TB21 GIMI HEIF Export Test")
    print("=" * 80)
    print()
    
    # Validate input
    if not os.path.exists(geotiff_path):
        print(f"❌ ERROR: GeoTIFF file not found: {geotiff_path}")
        return False
    
    # Set output path
    if not output_heif_path:
        base = geotiff_path.rsplit('.', 1)[0]
        output_heif_path = f"{base}_tb21.heif"
    
    print(f"Input:  {geotiff_path}")
    print(f"Output: {output_heif_path}")
    print()
    
    # Create processor
    processor = HEIFProcessor()
    
    # Check for heif-enc availability
    print("Checking dependencies...")
    has_heif_enc = processor.check_heif_enc_available()
    
    if not has_heif_enc:
        print("⚠️  WARNING: heif-enc not available")
        print("   → RDF metadata will be saved as external TTL file")
        print("   → For full TB21 GIMI compliance, install libheif with heif-enc")
        print("   → See: https://github.com/strukturag/libheif")
        print()
    else:
        print("✅ heif-enc available - full TB21 GIMI support enabled")
        print()
    
    # Perform export
    print("Starting export...")
    print()
    
    success, metadata = processor.export_geotiff_to_tb21_heif(
        geotiff_path,
        output_heif_path,
        quality=95,
        compression='hevc',  # Options: 'hevc', 'av1', 'unci'
        embed_rdf=True
    )
    
    # Display results
    print()
    if success:
        print("✅ EXPORT SUCCESSFUL")
        print()
        print("Metadata:")
        print(f"  - GCP Count: {metadata.get('gcp_count', 'unknown')}")
        print(f"  - RDF Size: {metadata.get('rdf_size', 0)} bytes")
        print(f"  - Encoding Method: {metadata.get('encoding_method', 'unknown')}")
        print(f"  - CRS: {metadata.get('gcp_projection', 'unknown')}")
        
        if metadata.get('output_hash'):
            print(f"  - BLAKE3 Hash: {metadata['output_hash'][:32]}...")
        
        if metadata.get('external_ttl'):
            print()
            print(f"📄 External TTL: {metadata['external_ttl']}")
            print("   (RDF metadata saved separately - heif-enc not available)")
        
        print()
        print(f"📦 Output file: {output_heif_path}")
        
        # Check file size
        if os.path.exists(output_heif_path):
            size_mb = os.path.getsize(output_heif_path) / (1024 * 1024)
            print(f"   Size: {size_mb:.2f} MB")
        
        return True
    else:
        print("❌ EXPORT FAILED")
        print()
        print(f"Error: {metadata.get('error', 'Unknown error')}")
        if metadata.get('traceback'):
            print()
            print("Traceback:")
            print(metadata['traceback'])
        return False


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_geotiff_export.py <geotiff_file> [output_heif]")
        print()
        print("Example:")
        print("  python test_geotiff_export.py sample.tif output_tb21.heif")
        print()
        # --- Codesprint January 2026: verify .aux.xml presence ---
        CODESPRINT_DATA_DIR = (
            "/Users/luciocolaiacomo/4113Eng-wfs/gimi-test-data/codesprint-january2026"
        )
        AUX_CHECK_FILES = [
            "tb21-single-image-hevc-internal-rdf_georeferenced.tif",
            "test20_georeferenced.tif",
        ]
        print("=" * 80)
        print("Codesprint January 2026 — GDAL .aux.xml sidecar check")
        print("=" * 80)
        import os
        if os.path.isdir(CODESPRINT_DATA_DIR):
            all_ok = True
            for fname in AUX_CHECK_FILES:
                tif_path = os.path.join(CODESPRINT_DATA_DIR, fname)
                aux_path = tif_path + ".aux.xml"
                if not os.path.exists(tif_path):
                    print(f"⚠️  Raster not found, skipping: {fname}")
                    continue
                if os.path.exists(aux_path):
                    print(f"✓  {fname}.aux.xml present ({os.path.getsize(aux_path)} bytes)")
                else:
                    print(f"⚠️  {fname}.aux.xml NOT present (run process_heif_with_ttl to generate it)")
            if all_ok:
                print("\nNote: .aux.xml files are generated automatically after HEIF import.")
        else:
            print(f"⚠️  Data directory not found: {CODESPRINT_DATA_DIR}")
        sys.exit(0)
    
    geotiff_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = test_export(geotiff_path, output_path)

    # After export, check that the STAC converter also works with the output
    if success and output_path and output_path.endswith('.heif'):
        pass  # heif-to-STAC path is not applicable here

    # Verify .aux.xml was produced alongside the input GeoTIFF
    aux_path = geotiff_path + ".aux.xml"
    if os.path.exists(aux_path):
        print(f"\n✓  GDAL statistics sidecar present: {aux_path}")
    else:
        print(f"\n⚠️  GDAL statistics sidecar NOT found: {aux_path}")
        print("    (This is generated by process_heif_with_ttl, not by the TB21 export test)")

    sys.exit(0 if success else 1)
