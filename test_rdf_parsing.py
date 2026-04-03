#!/usr/bin/env python3
"""Test TTL parser with actual RDF from HEIF file"""
import sys
import os
sys.path.insert(0, '/Users/luciocolaiacomo/4113Eng-wfs/cop_defence_stac/heif_ttl_importer')

# Read RDF from HEIF file
heif_path = '/Users/luciocolaiacomo/4113Eng-wfs/gimi-test-data/T21-GIMI-main-data-NGA_Sample_Data-2025-12-tb21-data-v2/data/NGA_Sample_Data/2025-12-tb21-data-v2/tb21-single-image-uncompressed-internal-rdf.heif'

with open(heif_path, 'rb') as f:
    data = f.read()
    idx = data.find(b'@prefix')
    if idx >= 0:
        # Extract up to 10KB of RDF
        rdf_bytes = data[idx:idx+10000]
        rdf_content = rdf_bytes.decode('utf-8', errors='ignore')
        
        # Find logical end (after some complete triples)
        lines = rdf_content.split('\n')
        limited_rdf = '\n'.join(lines[:50])  # First 50 lines
        
        print("=== Extracted RDF (first 50 lines) ===")
        print(limited_rdf)
        print("\n=== Testing TTL Parser ===")
        
        # Test with TTL parser
        from ttl_parser import TTLParser
        
        parser = TTLParser()
        success = parser.parse_string(rdf_content)
        
        print(f"Parse success: {success}")
        print(f"Image coordinates found: {len(parser.image_coords)}")
        print(f"Ground coordinates found: {len(parser.ground_coords)}")
        print(f"Correspondences found: {len(parser.correspondences)}")
        
        gcps = parser.get_all_gcps()
        print(f"\nTotal GCPs extracted: {len(gcps)}")
        
        if gcps:
            print("\nFirst 3 GCPs:")
            for i, gcp in enumerate(gcps[:3]):
                print(f"  GCP {i}: pixel=({gcp[0]}, {gcp[1]}), geo=({gcp[2]}, {gcp[3]})")
    else:
        print("No RDF found in file")


# ---------------------------------------------------------------------------
# Codesprint January 2026 — provenance TTL readability check
# ---------------------------------------------------------------------------

def test_provenance_ttl_files():
    """
    Verify that the _provenance.ttl files produced by the plugin can be parsed
    by rdflib and contain the expected W3C PROV entities.

    These files are W3C PROV records, NOT GIMI GCP metadata, so they are not
    fed into TTLParser — we just confirm they are well-formed RDF.
    """
    CODESPRINT_DATA_DIR = (
        "/Users/luciocolaiacomo/4113Eng-wfs/gimi-test-data/codesprint-january2026"
    )

    TTL_FILES = [
        "tb21-single-image-hevc-internal-rdf_georeferenced_provenance.ttl",
        "test20_georeferenced_provenance.ttl",
    ]

    print("\n" + "=" * 80)
    print("Codesprint January 2026 — provenance TTL readability")
    print("=" * 80)

    import os
    if not os.path.isdir(CODESPRINT_DATA_DIR):
        print(f"⚠️  Data directory not found, skipping: {CODESPRINT_DATA_DIR}")
        return

    try:
        import rdflib
    except ImportError:
        print("⚠️  rdflib not available — skipping RDF parse check")
        return

    all_ok = True
    for filename in TTL_FILES:
        fpath = os.path.join(CODESPRINT_DATA_DIR, filename)
        if not os.path.exists(fpath):
            print(f"⚠️  Skipped (file not found): {filename}")
            continue
        try:
            g = rdflib.Graph()
            g.parse(fpath, format="turtle")
            triple_count = len(g)
            # Check for prov:Entity subjects
            PROV = rdflib.Namespace("http://www.w3.org/ns/prov#")
            entities = list(g.subjects(rdflib.RDF.type, PROV.Entity))
            activities = list(g.subjects(rdflib.RDF.type, PROV.Activity))
            print(f"✓  {filename}")
            print(f"    Triples: {triple_count}  |  prov:Entity: {len(entities)}  |  prov:Activity: {len(activities)}")
            if len(entities) < 2 or len(activities) < 1:
                print("    ⚠️  Expected ≥2 prov:Entity and ≥1 prov:Activity")
                all_ok = False
        except Exception as exc:
            print(f"❌  {filename}: parse error — {exc}")
            all_ok = False

    if all_ok:
        print("\n✅ All provenance TTL files are well-formed and contain expected PROV structure")
    else:
        print("\n❌ One or more provenance TTL files had issues — check output above")


if __name__ == "__main__":
    test_provenance_ttl_files()
