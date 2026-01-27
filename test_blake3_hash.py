#!/usr/bin/env python3
"""
Test script for BLAKE3 hash calculation in HEIF processor
"""
import os
import sys
import tempfile
from pathlib import Path

# Add plugin directory to path
plugin_dir = Path(__file__).parent
sys.path.insert(0, str(plugin_dir))

from heif_processor import HEIFProcessor

try:
    import blake3
    BLAKE3_AVAILABLE = True
except ImportError:
    BLAKE3_AVAILABLE = False


def test_blake3_hash():
    """Test BLAKE3 hash calculation"""
    print("=" * 80)
    print("BLAKE3 Hash Calculation Test")
    print("=" * 80)
    
    # Check BLAKE3 availability
    if BLAKE3_AVAILABLE:
        print("✓ BLAKE3 module available")
    else:
        print("⚠️  BLAKE3 module NOT available - will use SHA256 fallback")
    
    # Create test file
    print("\nCreating test file...")
    test_data = b"This is a test file for BLAKE3 hash calculation\n" * 100
    
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.test') as f:
        test_file = f.name
        f.write(test_data)
    
    print(f"Test file: {test_file}")
    print(f"Test file size: {len(test_data)} bytes")
    
    try:
        # Calculate hash using HEIFProcessor
        print("\nCalculating hash using HEIFProcessor...")
        processor = HEIFProcessor()
        hash_value, hash_algo = processor.calculate_file_hash(test_file)
        
        if hash_value:
            print(f"✓ Hash calculated successfully!")
            print(f"  Algorithm: {hash_algo}")
            print(f"  Hash value: {hash_value}")
            print(f"  Hash length: {len(hash_value)} characters")
            
            # Verify multihash prefix
            if hash_algo == "blake3":
                expected_prefix = "1e20"
                if hash_value.startswith(expected_prefix):
                    print(f"  ✓ Correct multihash prefix: {expected_prefix} (BLAKE3)")
                else:
                    print(f"  ❌ Wrong prefix: expected {expected_prefix}, got {hash_value[:4]}")
                    return False
            elif hash_algo == "sha256":
                expected_prefix = "1220"
                if hash_value.startswith(expected_prefix):
                    print(f"  ✓ Correct multihash prefix: {expected_prefix} (SHA256)")
                else:
                    print(f"  ❌ Wrong prefix: expected {expected_prefix}, got {hash_value[:4]}")
                    return False
            
            # Verify hash independently
            if BLAKE3_AVAILABLE:
                print("\nVerifying hash independently with BLAKE3...")
                hasher = blake3.blake3()
                with open(test_file, 'rb') as f:
                    hasher.update(f.read())
                expected_hash = "1e20" + hasher.hexdigest()
                
                if hash_value == expected_hash:
                    print("  ✓ Hash matches independent calculation!")
                else:
                    print(f"  ❌ Hash mismatch!")
                    print(f"  Expected: {expected_hash}")
                    print(f"  Got:      {hash_value}")
                    return False
            else:
                import hashlib
                print("\nVerifying hash independently with SHA256...")
                hasher = hashlib.sha256()
                with open(test_file, 'rb') as f:
                    hasher.update(f.read())
                expected_hash = "1220" + hasher.hexdigest()
                
                if hash_value == expected_hash:
                    print("  ✓ Hash matches independent calculation!")
                else:
                    print(f"  ❌ Hash mismatch!")
                    print(f"  Expected: {expected_hash}")
                    print(f"  Got:      {hash_value}")
                    return False
            
            return True
        else:
            print("❌ Failed to calculate hash")
            return False
            
    finally:
        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"\nCleaned up test file: {test_file}")


def main():
    """Main test runner"""
    success = test_blake3_hash()
    
    print("\n" + "=" * 80)
    if success:
        print("✅ TEST PASSED: BLAKE3 hash calculation working!")
    else:
        print("❌ TEST FAILED: Check errors above")
    print("=" * 80)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
