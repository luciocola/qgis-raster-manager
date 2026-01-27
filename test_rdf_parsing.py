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
