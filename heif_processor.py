"""
HEIF Image Processor - Converts HEIF images to GeoTIFF format
"""
import os
import tempfile
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict
from pathlib import Path

try:
    from PIL import Image
    from pillow_heif import register_heif_opener
    import pillow_heif
    # Register HEIF format with PIL
    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False
    pillow_heif = None

try:
    import blake3
    BLAKE3_AVAILABLE = True
except ImportError:
    BLAKE3_AVAILABLE = False
    import hashlib

from osgeo import gdal, osr


class HEIFProcessor:
    """Processes HEIF images and converts them to GeoTIFF with GCPs"""
    
    def __init__(self):
        self.temp_files = []
        self.internal_rdf = None
        self.internal_rdf_format = None
        self.heif_convert_cmd = None  # Will be set by check_heif_convert_available()
        self.heif_enc_cmd = None  # heif-enc for encoding
        self.tiling_mode = None  # 'grid', 'tili', or 'unci'
        self.supports_signed_int = False  # ISO/IEC 23001-17 signed integers (PR #1644)
        self.supports_sai = False  # Sample Auxiliary Information for GIMI
        self.export_format = 'GTIFF'  # 'GTIFF' or 'JP2'
        
    def is_heif_supported(self) -> bool:
        """Check if HEIF format is supported"""
        return HEIF_AVAILABLE
    
    def check_heif_enc_available(self) -> bool:
        """
        Check if heif-enc command-line tool is available.
        
        heif-enc provides advanced encoding features:
        - Tiled image encoding (grid, tili, unci modes)
        - Uncompressed codec with signed integer support
        - SAI (Sample Auxiliary Information) for GIMI content IDs
        - Multi-resolution pyramids
        - Image sequences with metadata tracks
        
        See: https://github.com/strukturag/libheif/wiki/heif%E2%80%90enc-Command-Line-Tool
        
        Returns:
            True if heif-enc is available, False otherwise
        """
        import subprocess
        
        for cmd in ['heif-enc', '/usr/local/bin/heif-enc', os.path.expanduser('~/Downloads/libheif/build/examples/heif-enc')]:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0 or 'heif-enc' in result.stdout or 'heif-enc' in result.stderr:
                    self.heif_enc_cmd = cmd
                    print(f"Found heif-enc at: {cmd}")
                    
                    # Check for advanced features in help output
                    help_result = subprocess.run([cmd, '--help'], 
                                                capture_output=True, 
                                                text=True, 
                                                timeout=5)
                    help_text = help_result.stdout + help_result.stderr
                    
                    # Check for tiling support
                    if '--tiled-input' in help_text:
                        print("  ✓ Tiled image encoding supported")
                    if '--unci' in help_text or '--uncompressed' in help_text:
                        print("  ✓ Uncompressed codec supported")
                        self.supports_signed_int = True  # PR #1644 feature
                    if '--sai-data-file' in help_text:
                        print("  ✓ SAI metadata supported (GIMI content IDs)")
                        self.supports_sai = True
                    
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        
        print("heif-enc not found. Advanced encoding features unavailable.")
        print("Install libheif and build with: cmake .. && make")
        print("See: https://github.com/strukturag/libheif")
        return False
    
    def check_heif_convert_available(self) -> bool:
        """
        Check if heif-convert command-line tool is available.
        
        Returns:
            True if heif-convert is available, False otherwise
        """
        import subprocess
        
        for cmd in ['heif-convert', '/usr/local/bin/heif-convert', os.path.expanduser('~/Downloads/libheif/build/examples/heif-convert')]:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0 or 'heif-convert' in result.stdout or 'heif-convert' in result.stderr:
                    self.heif_convert_cmd = cmd
                    print(f"Found heif-convert at: {cmd}")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        
        return False
    
    def calculate_file_hash(self, file_path: str) -> Tuple[str, str]:
        """
        Calculate cryptographic hash of file using BLAKE3 (preferred) or SHA256 (fallback).
        
        Args:
            file_path: Path to file to hash
            
        Returns:
            Tuple of (hash_value, hash_algorithm)
            hash_value includes multihash prefix (0x1e for BLAKE3, 0x12 for SHA256)
        """
        try:
            if BLAKE3_AVAILABLE:
                hasher = blake3.blake3()
                hash_algo = "blake3"
                # Multihash prefix for BLAKE3: 0x1e
                prefix = "1e20"  # 0x1e (blake3) + 0x20 (32 bytes)
            else:
                hasher = hashlib.sha256()
                hash_algo = "sha256"
                # Multihash prefix for SHA256: 0x12
                prefix = "1220"  # 0x12 (sha256) + 0x20 (32 bytes)
            
            # Read file in chunks
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            
            hash_value = prefix + hasher.hexdigest()
            return hash_value, hash_algo
            
        except Exception as e:
            print(f"Error calculating file hash: {e}")
            return "", "unknown"
    
    def detect_tiling_mode(self, heif_path: str) -> Optional[str]:
        """
        Detect the tiling mode used in a HEIF file.
        
        Tiling modes from libheif:
        - 'grid': Default method with best decoder compatibility (max 65535 tiles)
        - 'tili': Efficient tiling with little overhead (unlimited tiles, libheif only)
        - 'unci': ISO 23001-17 uncompressed codec internal tiling
        
        See: https://github.com/strukturag/libheif/wiki/heif%E2%80%90enc-Command-Line-Tool#tiling-modes
        
        Args:
            heif_path: Path to HEIF file
            
        Returns:
            Tiling mode string ('grid', 'tili', 'unci') or None if not tiled
        """
        try:
            with open(heif_path, 'rb') as f:
                data = f.read(16384)  # Read first 16KB for box detection
                
                # Check for grid box (iref 'dimg' reference)
                if b'grid' in data:
                    self.tiling_mode = 'grid'
                    return 'grid'
                
                # Check for tili box (libheif-specific)
                if b'tili' in data:
                    self.tiling_mode = 'tili'
                    return 'tili'
                
                # Check for unci box (uncompressed codec)
                if b'unci' in data:
                    self.tiling_mode = 'unci'
                    return 'unci'
                
                return None
        except Exception as e:
            print(f"Error detecting tiling mode: {e}")
            return None
    
    def has_internal_rdf(self, heif_path: str) -> bool:
        """
        Check if HEIF file has internal RDF/XMP metadata.
        
        Supports both XML/RDF and Turtle formats (TB21 GIMI).
        
        Args:
            heif_path: Path to HEIF file
            
        Returns:
            True if internal RDF metadata found, False otherwise
        """
        try:
            with open(heif_path, 'rb') as f:
                data = f.read()
                # Check for XML/RDF format or XMP
                if b'<rdf:RDF' in data or b'<?xpacket' in data:
                    self.internal_rdf_format = 'xml'
                    return True
                # Check for Turtle format RDF (TB21 GIMI files)
                if b'@prefix rdf:' in data or b'@prefix rdfs:' in data:
                    self.internal_rdf_format = 'turtle'
                    return True
                return False
        except Exception as e:
            print(f"Error checking for internal RDF: {e}")
            return False
    
    def extract_internal_rdf(self, heif_path: str) -> Optional[str]:
        """
        Extract internal RDF metadata from HEIF file.
        
        Args:
            heif_path: Path to HEIF file
            
        Returns:
            RDF content as string, or None if not found
        """
        try:
            with open(heif_path, 'rb') as f:
                data = f.read()
                
                # Extract XML/RDF format
                if b'<rdf:RDF' in data:
                    idx = data.find(b'<rdf:RDF')
                    end_idx = data.find(b'</rdf:RDF>', idx)
                    if end_idx > 0:
                        rdf_data = data[idx:end_idx + 10]
                        self.internal_rdf = rdf_data.decode('utf-8', errors='ignore')
                        self.internal_rdf_format = 'xml'
                        return self.internal_rdf
                
                # Extract Turtle format RDF (TB21 GIMI files)
                elif b'@prefix rdf:' in data or b'@prefix rdfs:' in data:
                    idx = data.find(b'@prefix')
                    # Extract up to 100KB to ensure all GCP data is captured
                    end_idx = min(idx + 100000, len(data))
                    chunk = data[idx:end_idx]
                    
                    try:
                        turtle_text = chunk.decode('utf-8', errors='ignore')
                        # For TB21 GIMI files, we need ALL the RDF content to extract GCPs
                        # Don't truncate prematurely - GCPs can be scattered throughout
                        self.internal_rdf = turtle_text
                        self.internal_rdf_format = 'turtle'
                        print(f"Extracted {len(self.internal_rdf)} characters of Turtle RDF")
                        return self.internal_rdf
                    except Exception as e:
                        print(f"Error decoding Turtle RDF: {e}")
                        return None
                
                # Check for XMP packet if RDF not found
                if b'<?xpacket' in data:
                    idx = data.find(b'<?xpacket')
                    end_idx = data.find(b'<?xpacket end', idx)
                    if end_idx > 0:
                        xmp_data = data[idx:end_idx + 50]
                        self.internal_rdf = xmp_data.decode('utf-8', errors='ignore')
                        self.internal_rdf_format = 'xmp'
                        return self.internal_rdf
                
                return None
                
        except Exception as e:
            print(f"Error extracting internal RDF: {e}")
            return None
    
    def display_heif_structure(self, heif_path: str) -> str:
        """
        Display the complete HEIF/HEVC file structure including boxes, metadata, and images.
        
        Args:
            heif_path: Path to HEIF file
            
        Returns:
            String containing formatted file structure information
        """
        if not HEIF_AVAILABLE:
            return "ERROR: pillow-heif not installed. Install with: pip install pillow-heif"
        
        structure = []
        structure.append("=" * 80)
        structure.append(f"HEIF/HEVC FILE STRUCTURE: {os.path.basename(heif_path)}")
        structure.append("=" * 80)
        structure.append("")
        
        try:
            import pillow_heif
            
            # Get file size
            file_size = os.path.getsize(heif_path)
            structure.append(f"File Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
            structure.append("")
            
            # Open HEIF file with pillow_heif
            heif_file = pillow_heif.open_heif(heif_path)
            
            # File-level information
            structure.append("FILE INFORMATION:")
            structure.append("-" * 80)
            
            # Check if container has images
            num_images = len(heif_file)
            
            # Brand (may not exist in all versions)
            try:
                structure.append(f"  Brand: {heif_file.brand}")
            except AttributeError:
                structure.append(f"  Brand: HEIF (unknown)")
            
            structure.append(f"  Number of Images: {num_images}")
            
            if num_images == 0:
                structure.append("  Type: Metadata-only container (no image data)")
                structure.append("")
                structure.append("⚠️  This HEIF file contains no actual image data detected by pillow_heif.")
                structure.append("    It may only contain embedded metadata (RDF, XMP, etc.)")
                structure.append("    OR the image encoding may not be supported by the current pillow_heif version.")
                structure.append("")
                
                # Try to get more info about the file structure
                with open(heif_path, 'rb') as f:
                    # Read more data to analyze structure
                    data = f.read(8192)  # Read first 8KB
                    
                    # Parse ftyp box to get compatible brands
                    ftyp_idx = data.find(b'ftyp')
                    if ftyp_idx > 0:
                        # ftyp box contains major brand and compatible brands
                        ftyp_start = ftyp_idx + 4
                        if ftyp_start + 8 < len(data):
                            major_brand = data[ftyp_start:ftyp_start+4].decode('ascii', errors='ignore')
                            minor_version = int.from_bytes(data[ftyp_start+4:ftyp_start+8], 'big')
                            structure.append(f"  File Type Box (ftyp):")
                            structure.append(f"    Major brand: {major_brand}")
                            
                            # Check compatible brands
                            compat_brands = []
                            offset = ftyp_start + 8
                            while offset + 4 < min(ftyp_start + 100, len(data)):
                                brand = data[offset:offset+4]
                                if brand.isalnum() or b'\x00' in brand:
                                    brand_str = brand.decode('ascii', errors='ignore').strip('\x00')
                                    if brand_str and len(brand_str) >= 3:
                                        compat_brands.append(brand_str)
                                offset += 4
                            
                            if compat_brands:
                                structure.append(f"    Compatible brands: {', '.join(compat_brands[:10])}")
                        structure.append("")
                    
                    # Look for item type information (infe boxes contain 'item_type')
                    # Common types: 'hvc1' (HEVC), 'jpeg' (JPEG), 'unci' (uncompressed), 'av01' (AV1)
                    encoding_types = []
                    
                    # Search for common codec identifiers
                    if b'hvc1' in data or b'hevc' in data.lower():
                        encoding_types.append('HEVC (H.265) - NOT supported by pillow_heif')
                    if b'hev1' in data:
                        encoding_types.append('HEVC variant - NOT supported')
                    if b'unci' in data:
                        encoding_types.append('Uncompressed - May NOT be supported by pillow_heif')
                    if b'jpeg' in data.lower() and b'Exif' in data:
                        encoding_types.append('JPEG')
                    if b'av01' in data or b'AV1' in data:
                        encoding_types.append('AV1 - NOT supported by pillow_heif')
                    if b'avc1' in data or b'h264' in data.lower():
                        encoding_types.append('H.264/AVC - May NOT be supported')
                    
                    # Look for HEIF boxes
                    box_types = []
                    if b'ftyp' in data:
                        box_types.append('ftyp (file type)')
                    if b'meta' in data:
                        box_types.append('meta (metadata)')
                    if b'mdat' in data:
                        box_types.append('mdat (media data) ✓')
                    if b'idat' in data:
                        box_types.append('idat (item data) ✓')
                    if b'iref' in data:
                        box_types.append('iref (item references)')
                    if b'iprp' in data:
                        box_types.append('iprp (item properties)')
                    if b'pitm' in data:
                        box_types.append('pitm (primary item) ✓')
                    if b'iinf' in data:
                        box_types.append('iinf (item information)')
                    if b'iloc' in data:
                        box_types.append('iloc (item location)')
                    
                    if box_types:
                        structure.append("  Detected HEIF boxes:")
                        for bt in box_types:
                            structure.append(f"    - {bt}")
                        structure.append("")
                    
                    if encoding_types:
                        structure.append("  🔍 Detected image encoding(s):")
                        for et in encoding_types:
                            structure.append(f"    - {et}")
                        structure.append("")
                        
                        # Check if it's the uncompressed unci format
                        if any('Uncompressed' in et or 'unci' in et for et in encoding_types):
                            structure.append("  ⚠️  UNCOMPRESSED HEIF (unci) DETECTED:")
                            structure.append("      Uncompressed HEIF is supported by custom-built libheif.")
                            structure.append("      Your system uses custom libheif with unci decoder enabled.")
                            structure.append("")
                            structure.append("  ✓ SOLUTION:")
                            structure.append("      This plugin will automatically use the custom heif-dec decoder")
                            structure.append("      located at: ~/Downloads/libheif/build/examples/heif-dec")
                            structure.append("      The conversion will proceed automatically.")
                            structure.append("")
                            structure.append("  📝 Note: If conversion fails, homebrew libheif does NOT support unci.")
                            structure.append("      The custom-built version is required for uncompressed files.")
                        else:
                            structure.append("  ⚠️  SOLUTION:")
                            structure.append("      This file uses an image codec not supported by pillow_heif.")
                            structure.append("      Supported codecs: HEIC (libheif with HEVC decoder)")
                            structure.append("      Try:")
                            structure.append("      1. Convert the image with: heif-dec input.heif output.png")
                            structure.append("      2. Or use libheif tools to extract the image")
                            structure.append("      3. Check if libheif-dev is installed with HEVC support")
                        structure.append("")
                    elif 'mdat' in str(box_types) or 'idat' in str(box_types):
                        structure.append("  ℹ️  File contains media/item data boxes - image may be present")
                        structure.append("      but encoded in a format not supported by pillow_heif.")
                        structure.append("      Common unsupported formats: Uncompressed, HEVC without decoder")
                        structure.append("")
                        structure.append("  Try: heif-dec input.heif output.png")
            else:
                # Only access info if there are images
                try:
                    file_format = heif_file.info.get('format', 'HEIF')
                    structure.append(f"  Format: {file_format}")
                except (IndexError, AttributeError):
                    structure.append(f"  Format: HEIF (container)")
                
                # Check for HDR
                try:
                    has_hdr = any(img.info.get('hdr_to_8bit') is not None for img in heif_file)
                    structure.append(f"  HDR Content: {'Yes' if has_hdr else 'No'}")
                except:
                    pass
                
                # Color profiles - only if there are images
                try:
                    if heif_file.info.get('icc_profile'):
                        structure.append(f"  ICC Profile: Present ({len(heif_file.info['icc_profile'])} bytes)")
                    if heif_file.info.get('exif'):
                        structure.append(f"  EXIF Data: Present ({len(heif_file.info['exif'])} bytes)")
                    if heif_file.info.get('xmp'):
                        structure.append(f"  XMP Data: Present ({len(heif_file.info['xmp'])} bytes)")
                except (IndexError, AttributeError):
                    pass
            
            structure.append("")
            
            # Iterate through all images in the container
            for idx, img in enumerate(heif_file):
                structure.append(f"IMAGE #{idx + 1}:")
                structure.append("-" * 80)
                
                # Image properties
                structure.append(f"  Size: {img.size[0]} x {img.size[1]} pixels")
                structure.append(f"  Mode: {img.mode}")
                structure.append(f"  Bit Depth: {img.info.get('bits_per_pixel', 'N/A')} bits per pixel")
                
                # Check if this is primary image
                if hasattr(img, 'primary') and img.primary:
                    structure.append(f"  Primary Image: Yes")
                
                # Thumbnails
                if hasattr(img, 'thumbnails') and img.thumbnails:
                    structure.append(f"  Thumbnails: {len(img.thumbnails)}")
                    for tidx, thumb in enumerate(img.thumbnails):
                        structure.append(f"    Thumbnail {tidx + 1}: {thumb.size[0]}x{thumb.size[1]}")
                
                # Encoding information
                if 'encoder' in img.info:
                    structure.append(f"  Encoder: {img.info['encoder']}")
                
                # Compression
                if 'compression' in img.info:
                    structure.append(f"  Compression: {img.info['compression']}")
                
                # Color information
                if 'color_primaries' in img.info:
                    structure.append(f"  Color Primaries: {img.info['color_primaries']}")
                if 'color_matrix' in img.info:
                    structure.append(f"  Color Matrix: {img.info['color_matrix']}")
                if 'color_transfer' in img.info:
                    structure.append(f"  Transfer Function: {img.info['color_transfer']}")
                
                # HDR metadata
                if 'hdr_to_8bit' in img.info:
                    structure.append(f"  HDR: Yes")
                    structure.append(f"    HDR to 8-bit conversion: {img.info['hdr_to_8bit']}")
                
                # Orientation
                if 'orientation' in img.info:
                    structure.append(f"  Orientation: {img.info['orientation']}")
                
                # Stride (for planar formats)
                if hasattr(img, 'stride'):
                    structure.append(f"  Stride: {img.stride}")
                
                # Image-specific metadata
                if 'exif' in img.info and img.info['exif']:
                    structure.append(f"  EXIF: Present")
                    # Try to parse EXIF
                    try:
                        from PIL import ExifTags
                        pil_img = img.to_pillow()
                        exif_data = pil_img.getexif()
                        if exif_data:
                            structure.append("    EXIF Tags:")
                            for tag_id, value in list(exif_data.items())[:10]:  # Show first 10
                                tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                                # Truncate long values
                                value_str = str(value)[:50]
                                if len(str(value)) > 50:
                                    value_str += "..."
                                structure.append(f"      {tag_name}: {value_str}")
                            if len(exif_data) > 10:
                                structure.append(f"      ... and {len(exif_data) - 10} more tags")
                    except Exception as e:
                        structure.append(f"    (Could not parse EXIF: {e})")
                
                if 'xmp' in img.info and img.info['xmp']:
                    xmp_data = img.info['xmp']
                    structure.append(f"  XMP: Present ({len(xmp_data)} bytes)")
                    # Show preview of XMP
                    try:
                        xmp_str = xmp_data.decode('utf-8', errors='ignore')[:200]
                        structure.append(f"    Preview: {xmp_str}...")
                    except:
                        pass
                
                if 'icc_profile' in img.info and img.info['icc_profile']:
                    structure.append(f"  ICC Profile: Present ({len(img.info['icc_profile'])} bytes)")
                
                structure.append("")
            
            # Check for internal RDF
            structure.append("EMBEDDED RDF METADATA:")
            structure.append("-" * 80)
            has_rdf = self.has_internal_rdf(heif_path)
            if has_rdf:
                rdf_content = self.extract_internal_rdf(heif_path)
                structure.append(f"  Format: {self.internal_rdf_format.upper()}")
                structure.append(f"  Size: {len(rdf_content)} bytes")
                structure.append("  Content:")
                structure.append("")
                # Show ALL RDF content (no truncation)
                for line in rdf_content.split('\n'):
                    structure.append(f"    {line}")
            else:
                structure.append("  No internal RDF metadata found")
            
            structure.append("")
            structure.append("=" * 80)
            
        except Exception as e:
            structure.append(f"ERROR analyzing HEIF structure: {e}")
            import traceback
            structure.append(traceback.format_exc())
        
        return '\n'.join(structure)
    
    def check_heif_convert_available(self) -> bool:
        """
        Check if heif-dec command-line tool is available.
        Prioritizes custom-built version with uncompressed (unci) codec support.
        
        Returns:
            True if heif-dec is available, False otherwise
        """
        import subprocess
        import os
        
        # Possible locations for heif-dec (decoder) - heif-convert was renamed to heif-dec in newer versions
        # PRIORITIZE custom-built version with unci support first
        possible_paths = [
            os.path.expanduser('~/Downloads/libheif/build/examples/heif-dec'),  # Custom build with unci support
            os.path.expanduser('~/local-libheif/bin/heif-dec'),  # Installed custom build
            '/opt/homebrew/bin/heif-dec',  # Homebrew on Apple Silicon (may not have unci)
            '/usr/local/bin/heif-dec',  # Homebrew on Intel Mac
            '/usr/bin/heif-dec',  # System installation
            # Fallback to older heif-convert name if it exists
            '/opt/homebrew/bin/heif-convert',
            '/usr/local/bin/heif-convert',
        ]
        
        for cmd in possible_paths:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, 
                                      text=True, 
                                      timeout=5)
                if result.returncode == 0 or result.returncode == 1:  # Some versions return 1 for --version
                    self.heif_convert_cmd = cmd
                    # Log which version we're using
                    print(f"✓ Using HEIF decoder from: {cmd}")
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        self.heif_convert_cmd = None
        return False
    
    def convert_heif_with_libheif(self, heif_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert HEIF to PNG using heif-dec command-line tool.
        This is a fallback for formats not supported by pillow_heif (e.g., uncompressed unci).
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path. If None, creates temp file
            
        Returns:
            Path to output PNG file or None on error
        """
        import subprocess
        
        # Ensure we have the command path
        if not hasattr(self, 'heif_convert_cmd') or self.heif_convert_cmd is None:
            if not self.check_heif_convert_available():
                print("heif-dec not found. Install libheif with: brew install libheif")
                print("Or build from source with uncompressed codec support.")
                return None
        
        try:
            # Determine output path
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                output_path = temp_file.name
                temp_file.close()
                self.temp_files.append(output_path)
            
            # Use heif-dec to extract image
            # Syntax: heif-dec <input.heif> <output.png>
            print(f"Converting HEIF with custom libheif decoder (unci support)...")
            print(f"Command: {self.heif_convert_cmd}")
            result = subprocess.run(
                [self.heif_convert_cmd, heif_path, output_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # heif-dec may return 0 on success or 1 with warnings
            if result.returncode != 0 and not os.path.exists(output_path):
                print(f"heif-dec failed with return code {result.returncode}")
                print(f"stderr: {result.stderr}")
                print(f"stdout: {result.stdout}")
                
                # Check for specific unsupported codec errors
                if 'unci' in result.stderr.lower() or 'uncompressed' in result.stderr.lower():
                    print("\n" + "=" * 80)
                    print("UNSUPPORTED CODEC: Uncompressed HEIF (unci)")
                    print("=" * 80)
                    print("This HEIF file uses uncompressed encoding which is not supported by this libheif build.")
                    print("The image data IS present but cannot be decoded with this version.")
                    print("\nRECOMMENDED SOLUTIONS:")
                    print("1. Use custom-built libheif with WITH_UNCOMPRESSED_CODEC=ON")
                    print("2. Ask the data provider for a HEVC-compressed version")
                    print("3. Try the custom build at: ~/Downloads/libheif/build/examples/heif-dec")
                    print("=" * 80 + "\n")
                
                return None
            
            if not os.path.exists(output_path):
                print(f"heif-dec did not create output file: {output_path}")
                return None
            
            print(f"Successfully converted HEIF using heif-convert: {output_path}")
            return output_path
            
        except subprocess.TimeoutExpired:
            print("heif-convert timed out")
            return None
        except Exception as e:
            print(f"Error using heif-convert: {e}")
            import traceback
            traceback.print_exc()
            return None

    def convert_heif_to_tiff(self, heif_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert HEIF image to TIFF format
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path. If None, creates temp file
            
        Returns:
            Path to output TIFF file or None on error
        """
        if not HEIF_AVAILABLE:
            print("ERROR: pillow-heif not installed. Install with: pip install pillow-heif")
            # Try heif-convert as fallback
            if self.check_heif_convert_available():
                print("Attempting conversion with heif-convert...")
                png_path = self.convert_heif_with_libheif(heif_path)
                if png_path:
                    # Convert PNG to TIFF
                    try:
                        img = Image.open(png_path)
                        if output_path is None:
                            temp_file = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
                            output_path = temp_file.name
                            temp_file.close()
                            self.temp_files.append(output_path)
                        img.save(output_path, 'TIFF', compression='lzw')
                        return output_path
                    except Exception as e:
                        print(f"Error converting PNG to TIFF: {e}")
            return None
            
        try:
            # Ensure HEIF opener is registered
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except Exception as e:
                print(f"Warning: Could not register HEIF opener: {e}")
            
            # Try to open HEIF image with PIL
            img = None
            try:
                img = Image.open(heif_path)
            except Exception as img_error:
                # Try with pillow_heif directly as fallback
                print(f"PIL Image.open failed: {img_error}")
                print("Trying pillow_heif direct method...")
                try:
                    import pillow_heif
                    heif_file = pillow_heif.open_heif(heif_path)
                    
                    # Check if file contains any images
                    if len(heif_file) == 0:
                        print("WARNING: HEIF file contains 0 images detected by pillow_heif")
                        print("Attempting conversion with heif-convert...")
                        
                        # Try heif-convert as final fallback
                        if self.check_heif_convert_available():
                            png_path = self.convert_heif_with_libheif(heif_path)
                            if png_path:
                                # Convert PNG to TIFF
                                img = Image.open(png_path)
                                # Continue with normal flow below
                            else:
                                error_msg = (
                                    "Cannot decode HEIF image. The file contains image data but uses "
                                    "an unsupported codec (likely uncompressed 'unci' format).\n\n"
                                    "This is a limitation of the available HEIF libraries. "
                                    "Please request a HEVC-compressed version of this image from your data provider."
                                )
                                raise Exception(error_msg)
                        else:
                            print("heif-convert not available. Install with: brew install libheif")
                            error_msg = (
                                "Cannot decode HEIF image. Install libheif tools: brew install libheif"
                            )
                            raise Exception(error_msg)
                    else:
                        # Get first image
                        img = heif_file[0].to_pillow()
                except Exception as heif_error:
                    print(f"pillow_heif direct method also failed: {heif_error}")
                    
                    # Try heif-convert as final fallback
                    if self.check_heif_convert_available():
                        print("Attempting conversion with heif-convert as final fallback...")
                        png_path = self.convert_heif_with_libheif(heif_path)
                        if png_path:
                            img = Image.open(png_path)
                        else:
                            raise heif_error
                    else:
                        raise
            
            if img is None:
                print("ERROR: Could not load image from HEIF file")
                return None
            
            # Convert to RGB if needed
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            
            # Determine output path
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.tif', delete=False)
                output_path = temp_file.name
                temp_file.close()
                self.temp_files.append(output_path)
            
            # Save as TIFF
            img.save(output_path, 'TIFF', compression='lzw')
            
            print(f"Converted HEIF to TIFF: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error converting HEIF to TIFF: {e}")
            return None
    
    def convert_heif_to_jp2(self, heif_path: str, output_path: Optional[str] = None, 
                           lossless: bool = True) -> Optional[str]:
        """
        Convert HEIF to JPEG2000 using heif-enc (experimental).
        
        JPEG2000 advantages:
        - Better compression than TIFF (20-30% smaller)
        - Native QGIS/GDAL support
        - Multi-resolution pyramids
        - Lossless and lossy modes
        - Excellent for large imagery
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path. If None, creates temp file
            lossless: If True, use lossless compression (default)
            
        Returns:
            Path to output JP2 file or None on error
        """
        if not self.heif_enc_cmd:
            if not self.check_heif_enc_available():
                print("heif-enc not available. Cannot convert to JPEG2000.")
                print("Install libheif: https://github.com/strukturag/libheif")
                return None
        
        # Determine output path
        if output_path is None:
            temp_file = tempfile.NamedTemporaryFile(suffix='.jp2', delete=False)
            output_path = temp_file.name
            temp_file.close()
            self.temp_files.append(output_path)
        
        # Build command
        cmd = [
            self.heif_enc_cmd,
            '--jpeg2000',
            heif_path,
            '-o', output_path
        ]
        
        if lossless:
            cmd.insert(2, '-L')  # Lossless mode
        
        try:
            print(f"Converting HEIF to JPEG2000: {os.path.basename(heif_path)}")
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=60)
            
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"Successfully converted to JPEG2000: {output_path}")
                return output_path
            else:
                print(f"JPEG2000 conversion failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print("JPEG2000 conversion timed out")
            return None
        except Exception as e:
            print(f"Error converting to JPEG2000: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def convert_heif_to_jp2_via_gdal(self, heif_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        Convert HEIF to JPEG2000 via TIFF intermediate (fallback method).
        
        Uses: HEIF → TIFF → JPEG2000
        
        Args:
            heif_path: Path to input HEIF file
            output_path: Optional output path for JP2 file
            
        Returns:
            Path to output JP2 file or None on error
        """
        try:
            # Step 1: Convert HEIF to TIFF
            tiff_path = self.convert_heif_to_tiff(heif_path)
            if not tiff_path:
                return None
            
            # Determine output path
            if output_path is None:
                temp_file = tempfile.NamedTemporaryFile(suffix='.jp2', delete=False)
                output_path = temp_file.name
                temp_file.close()
                self.temp_files.append(output_path)
            
            # Step 2: Convert TIFF to JPEG2000 using GDAL
            ds = gdal.Open(tiff_path, gdal.GA_ReadOnly)
            if ds is None:
                print(f"Could not open TIFF: {tiff_path}")
                return None
            
            # Try JP2OpenJPEG driver (most common)
            driver = gdal.GetDriverByName('JP2OpenJPEG')
            if driver is None:
                # Try other JP2 drivers
                for driver_name in ['JP2KAK', 'JP2ECW', 'JPEG2000']:
                    driver = gdal.GetDriverByName(driver_name)
                    if driver:
                        break
            
            if driver is None:
                print("No JPEG2000 driver available in GDAL")
                return None
            
            # Create JPEG2000 with options
            options = [
                'QUALITY=100',      # Lossless quality
                'REVERSIBLE=YES',   # Lossless compression
                'YCBCR420=NO',      # Preserve full color
                'GMLJP2=NO'         # Skip GML boxes for now
            ]
            
            print(f"Converting TIFF to JPEG2000 using {driver.ShortName}...")
            out_ds = driver.CreateCopy(output_path, ds, strict=0, options=options)
            
            if out_ds:
                out_ds.FlushCache()
                out_ds = None
                ds = None
                print(f"Successfully converted to JPEG2000: {output_path}")
                return output_path
            else:
                ds = None
                print("JPEG2000 creation failed")
                return None
                
        except Exception as e:
            print(f"Error in GDAL JPEG2000 conversion: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def convert_tiff_to_jp2(self, tiff_path: str, output_path: str) -> bool:
        """
        Convert a GeoTIFF to JPEG2000, preserving georeferencing.
        
        Args:
            tiff_path: Path to input GeoTIFF
            output_path: Path for output JP2 file
            
        Returns:
            True on success, False on error
        """
        try:
            ds = gdal.Open(tiff_path, gdal.GA_ReadOnly)
            if ds is None:
                print(f"Could not open TIFF: {tiff_path}")
                return False
            
            # Find JPEG2000 driver
            driver = gdal.GetDriverByName('JP2OpenJPEG')
            if driver is None:
                for driver_name in ['JP2KAK', 'JP2ECW', 'JPEG2000']:
                    driver = gdal.GetDriverByName(driver_name)
                    if driver:
                        break
            
            if driver is None:
                print("No JPEG2000 driver available in GDAL")
                return False
            
            # JPEG2000 creation options
            options = [
                'QUALITY=100',
                'REVERSIBLE=YES',
                'YCBCR420=NO',
                'GMLJP2=YES',
                'GeoJP2=YES'
            ]
            
            print(f"Converting to JPEG2000 using {driver.ShortName}...")
            out_ds = driver.CreateCopy(output_path, ds, strict=0, options=options)
            
            if out_ds:
                out_ds.FlushCache()
                out_ds = None
                ds = None
                print(f"Successfully converted to JPEG2000: {output_path}")
                return True
            else:
                ds = None
                print("JPEG2000 conversion failed")
                return False
                
        except Exception as e:
            print(f"Error converting TIFF to JPEG2000: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_georeferenced_tiff(self, input_tiff: str, gcps: list, output_path: str, 
                                  epsg: int = 4326) -> bool:
        """
        Create a georeferenced GeoTIFF using Ground Control Points
        
        Args:
            input_tiff: Path to input TIFF file
            gcps: List of GCPs as (pixel_x, pixel_y, lon, lat) tuples
            output_path: Path for output GeoTIFF
            epsg: EPSG code for coordinate system (default 4326 = WGS84)
            
        Returns:
            True on success, False on error
        """
        try:
            # Open input dataset
            src_ds = gdal.Open(input_tiff, gdal.GA_ReadOnly)
            if src_ds is None:
                print(f"Could not open {input_tiff}")
                return False
            
            # Get raster dimensions
            width = src_ds.RasterXSize
            height = src_ds.RasterYSize
            bands = src_ds.RasterCount
            
            # Create GCP list for GDAL
            gdal_gcps = []
            for i, (px, py, lon, lat) in enumerate(gcps):
                gcp = gdal.GCP(lon, lat, 0, px, py, f"GCP_{i}", str(i))
                gdal_gcps.append(gcp)
            
            # Create spatial reference
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(epsg)
            
            # Create output dataset
            driver = gdal.GetDriverByName('GTiff')
            dst_ds = driver.Create(output_path, width, height, bands, gdal.GDT_Byte,
                                  options=['COMPRESS=LZW', 'TILED=YES'])
            
            if dst_ds is None:
                print(f"Could not create {output_path}")
                return False
            
            # Copy raster data
            for band_idx in range(1, bands + 1):
                src_band = src_ds.GetRasterBand(band_idx)
                dst_band = dst_ds.GetRasterBand(band_idx)
                data = src_band.ReadAsArray()
                dst_band.WriteArray(data)
                
                # Copy color interpretation
                dst_band.SetColorInterpretation(src_band.GetColorInterpretation())
            
            # Set GCPs and projection
            dst_ds.SetGCPs(gdal_gcps, srs.ExportToWkt())
            
            # Flush to disk
            dst_ds.FlushCache()
            dst_ds = None
            src_ds = None
            
            print(f"Created georeferenced GeoTIFF with {len(gcps)} GCPs: {output_path}")
            return True
            
        except Exception as e:
            print(f"Error creating georeferenced TIFF: {e}")
            return False
    
    def create_georeferenced_jp2(self, input_tiff: str, gcps: list, output_path: str, 
                                 epsg: int = 4326) -> bool:
        """
        Create a georeferenced JPEG2000 file using Ground Control Points.
        
        Args:
            input_tiff: Path to input TIFF file
            gcps: List of GCPs as (pixel_x, pixel_y, lon, lat) tuples
            output_path: Path for output JP2 file
            epsg: EPSG code for coordinate system (default 4326 = WGS84)
            
        Returns:
            True on success, False on error
        """
        try:
            # First create georeferenced GeoTIFF
            temp_geotiff = tempfile.NamedTemporaryFile(suffix='_gcp.tif', delete=False)
            temp_geotiff_path = temp_geotiff.name
            temp_geotiff.close()
            self.temp_files.append(temp_geotiff_path)
            
            # Add GCPs to TIFF
            if not self.create_georeferenced_tiff(input_tiff, gcps, temp_geotiff_path, epsg):
                return False
            
            # Convert georeferenced TIFF to JPEG2000
            try:
                ds = gdal.Open(temp_geotiff_path, gdal.GA_ReadOnly)
                if ds is None:
                    print(f"Could not open georeferenced TIFF")
                    return False
                
                # Find JPEG2000 driver
                driver = gdal.GetDriverByName('JP2OpenJPEG')
                if driver is None:
                    for driver_name in ['JP2KAK', 'JP2ECW', 'JPEG2000']:
                        driver = gdal.GetDriverByName(driver_name)
                        if driver:
                            break
                
                if driver is None:
                    print("No JPEG2000 driver available")
                    return False
                
                # JPEG2000 creation options
                options = [
                    'QUALITY=100',
                    'REVERSIBLE=YES',
                    'YCBCR420=NO',
                    'GMLJP2=YES',      # Include GML for georeferencing
                    'GeoJP2=YES'       # Include GeoJP2 UUID box
                ]
                
                print(f"Creating georeferenced JPEG2000 with {len(gcps)} GCPs...")
                out_ds = driver.CreateCopy(output_path, ds, strict=0, options=options)
                
                if out_ds:
                    out_ds.FlushCache()
                    out_ds = None
                    ds = None
                    print(f"Created georeferenced JPEG2000: {output_path}")
                    return True
                else:
                    ds = None
                    return False
                    
            except Exception as e:
                print(f"Error creating JPEG2000: {e}")
                return False
                
        except Exception as e:
            print(f"Error creating georeferenced JPEG2000: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def warp_with_gcps(self, input_geotiff: str, output_path: str, 
                      resample_method: str = 'cubic') -> bool:
        """
        Warp (transform) a GeoTIFF with GCPs to create a properly georeferenced image
        
        Args:
            input_geotiff: Path to GeoTIFF with GCPs
            output_path: Path for warped output
            resample_method: Resampling method ('near', 'bilinear', 'cubic', 'lanczos')
            
        Returns:
            True on success, False on error
        """
        try:
            # Map resample method names
            resample_map = {
                'near': gdal.GRA_NearestNeighbour,
                'bilinear': gdal.GRA_Bilinear,
                'cubic': gdal.GRA_Cubic,
                'lanczos': gdal.GRA_Lanczos
            }
            
            resample_alg = resample_map.get(resample_method.lower(), gdal.GRA_Cubic)
            
            # Warp options
            warp_options = gdal.WarpOptions(
                format='GTiff',
                resampleAlg=resample_alg,
                creationOptions=['COMPRESS=LZW', 'TILED=YES'],
                multithread=True
            )
            
            # Perform the warp
            result = gdal.Warp(output_path, input_geotiff, options=warp_options)
            
            if result is None:
                print(f"Warp failed for {input_geotiff}")
                return False
            
            result = None  # Close dataset
            print(f"Warped GeoTIFF created: {output_path}")
            return True
            
        except Exception as e:
            print(f"Error warping GeoTIFF: {e}")
            return False
    
    def orthorectify_with_gcps(self, input_geotiff: str, output_path: str, 
                               transform_order: int = 1,
                               resample_method: str = 'cubic') -> bool:
        """
        Orthorectify a GeoTIFF using polynomial transformation with GCPs
        
        Args:
            input_geotiff: Path to GeoTIFF with GCPs
            output_path: Path for orthorectified output
            transform_order: Polynomial order (1=affine, 2=2nd order, 3=3rd order, -1=TPS)
            resample_method: Resampling method ('near', 'bilinear', 'cubic', 'lanczos')
            
        Returns:
            True on success, False on error
        """
        try:
            # Map resample method names
            resample_map = {
                'near': gdal.GRA_NearestNeighbour,
                'bilinear': gdal.GRA_Bilinear,
                'cubic': gdal.GRA_Cubic,
                'lanczos': gdal.GRA_Lanczos
            }
            
            resample_alg = resample_map.get(resample_method.lower(), gdal.GRA_Cubic)
            
            # Set transformation type based on order
            if transform_order == -1:
                # Thin Plate Spline - best for non-linear distortions
                transformer = 'tps'
                print(f"Using Thin Plate Spline (TPS) transformation")
            else:
                # Polynomial transformation
                transformer = f'polynomial:{transform_order}'
                print(f"Using {transform_order} order polynomial transformation")
            
            # Warp options with polynomial transformation
            warp_options = gdal.WarpOptions(
                format='GTiff',
                resampleAlg=resample_alg,
                transformerOptions=[f'METHOD={transformer.upper()}'],
                creationOptions=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER'],
                multithread=True,
                errorThreshold=0.125  # Maximum error in pixels
            )
            
            # Perform the orthorectification
            print(f"Orthorectifying with {transformer} transformation...")
            result = gdal.Warp(output_path, input_geotiff, options=warp_options)
            
            if result is None:
                print(f"Orthorectification failed for {input_geotiff}")
                return False
            
            # Get transformation statistics if available
            result_stats = result.GetMetadata()
            result = None  # Close dataset
            
            print(f"Orthorectified GeoTIFF created: {output_path}")
            if 'STATISTICS_MEAN' in result_stats:
                print(f"  Statistics: Mean={result_stats.get('STATISTICS_MEAN')}")
            
            return True
            
        except Exception as e:
            print(f"Error during orthorectification: {e}")
            return False
    
    def process_heif_with_ttl(self, heif_path: str, gcps: list, 
                             output_path: str, warp: bool = True,
                             orthorectify: bool = False, 
                             transform_order: int = 1,
                             resample_method: str = 'cubic',
                             original_uuid: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Complete workflow: HEIF -> TIFF -> GeoTIFF with GCPs -> Warped/Orthorectified GeoTIFF
        
        Args:
            heif_path: Path to input HEIF file
            gcps: List of GCPs as (pixel_x, pixel_y, lon, lat) tuples
            output_path: Path for final output GeoTIFF
            warp: Whether to warp the image (recommended for proper display)
            orthorectify: Whether to apply orthorectification with polynomial transformation
            transform_order: Polynomial order for orthorectification (1-3, or -1 for TPS)
            resample_method: Resampling method ('near', 'bilinear', 'cubic', 'lanczos')
            original_uuid: UUID of original HEIF image (if None, generates new one)
            
        Returns:
            Tuple of (success: bool, provenance: Dict)
        """
        # Generate UUIDs for provenance tracking
        if original_uuid is None:
            original_uuid = str(uuid.uuid4())
        
        derived_uuid = str(uuid.uuid4())
        algorithm_uuid = str(uuid.uuid4())
        processing_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Calculate BLAKE3 hash of input HEIF file
        input_hash, input_hash_algo = self.calculate_file_hash(heif_path)
        
        # Determine algorithm name
        if orthorectify:
            if transform_order == -1:
                algorithm_name = "TPS Orthorectification"
            else:
                algorithm_name = f"Polynomial Order {transform_order} Orthorectification"
        elif warp:
            algorithm_name = "GCP Warping"
        else:
            algorithm_name = "GCP Assignment"
        
        # Initialize provenance metadata
        provenance = {
            "original_uuid": original_uuid,
            "derived_uuid": derived_uuid,
            "algorithm_uuid": algorithm_uuid,
            "algorithm_name": algorithm_name,
            "processing_timestamp": processing_timestamp,
            "transform_order": transform_order if orthorectify else None,
            "resample_method": resample_method if (warp or orthorectify) else None,
            "gcp_count": len(gcps),
            "warp_enabled": warp,
            "orthorectify_enabled": orthorectify,
            "input_file": os.path.basename(heif_path),
            "input_hash": input_hash,
            "input_hash_algorithm": input_hash_algo,
            "output_file": os.path.basename(output_path)
        }
        try:
            # Step 1: Convert HEIF to TIFF
            print("Step 1: Converting HEIF to TIFF...")
            tiff_path = self.convert_heif_to_tiff(heif_path)
            if not tiff_path:
                raise Exception(
                    "HEIF file contains no image data (metadata-only container).\n\n"
                    "The plugin requires an actual image for georeferencing. "
                    "This HEIF appears to only contain RDF metadata without pixel data."
                )
            
            # Step 2: Add GCPs to create georeferenced TIFF
            print(f"Step 2: Adding {len(gcps)} GCPs to TIFF...")
            
            # Determine output format
            is_jp2_export = self.export_format == 'JP2' and output_path.endswith('.jp2')
            
            if warp or orthorectify:
                # Create intermediate file with GCPs
                temp_geo = tempfile.NamedTemporaryFile(suffix='_gcps.tif', delete=False)
                temp_geo_path = temp_geo.name
                temp_geo.close()
                self.temp_files.append(temp_geo_path)
                
                if is_jp2_export:
                    # For JP2 export, create georeferenced GeoTIFF first
                    if not self.create_georeferenced_tiff(tiff_path, gcps, temp_geo_path):
                        return False, provenance
                else:
                    if not self.create_georeferenced_tiff(tiff_path, gcps, temp_geo_path):
                        return False, provenance
                
                # Step 3: Apply transformation
                if orthorectify:
                    print(f"Step 3: Orthorectifying with {transform_order} order transformation...")
                    
                    if is_jp2_export:
                        # Create intermediate orthorectified TIFF
                        temp_ortho = tempfile.NamedTemporaryFile(suffix='_ortho.tif', delete=False)
                        temp_ortho_path = temp_ortho.name
                        temp_ortho.close()
                        self.temp_files.append(temp_ortho_path)
                        
                        if not self.orthorectify_with_gcps(temp_geo_path, temp_ortho_path, 
                                                           transform_order, resample_method):
                            return False, provenance
                        
                        # Convert orthorectified TIFF to JPEG2000
                        print("Step 4: Converting to JPEG2000...")
                        if not self.convert_tiff_to_jp2(temp_ortho_path, output_path):
                            return False, provenance
                    else:
                        if not self.orthorectify_with_gcps(temp_geo_path, output_path, 
                                                           transform_order, resample_method):
                            return False, provenance
                else:
                    print("Step 3: Warping to final output...")
                    
                    if is_jp2_export:
                        # Create intermediate warped TIFF
                        temp_warp = tempfile.NamedTemporaryFile(suffix='_warp.tif', delete=False)
                        temp_warp_path = temp_warp.name
                        temp_warp.close()
                        self.temp_files.append(temp_warp_path)
                        
                        if not self.warp_with_gcps(temp_geo_path, temp_warp_path, resample_method):
                            return False, provenance
                        
                        # Convert warped TIFF to JPEG2000
                        print("Step 4: Converting to JPEG2000...")
                        if not self.convert_tiff_to_jp2(temp_warp_path, output_path):
                            return False, provenance
                    else:
                        if not self.warp_with_gcps(temp_geo_path, output_path, resample_method):
                            return False, provenance
            else:
                # Direct output without warping/orthorectification
                if is_jp2_export:
                    # Create georeferenced JPEG2000
                    if not self.create_georeferenced_jp2(tiff_path, gcps, output_path):
                        return False, provenance
                else:
                    if not self.create_georeferenced_tiff(tiff_path, gcps, output_path):
                        return False, provenance
            
            # Calculate BLAKE3 hash of output GeoTIFF
            output_hash, output_hash_algo = self.calculate_file_hash(output_path)
            provenance['output_hash'] = output_hash
            provenance['output_hash_algorithm'] = output_hash_algo
            
            print(f"Input hash ({input_hash_algo}): {input_hash}")
            print(f"Output hash ({output_hash_algo}): {output_hash}")
            
            # Save provenance metadata as sidecar JSON
            file_ext = '.jp2' if output_path.endswith('.jp2') else '.tif'
            provenance_file = output_path.replace(file_ext, '_provenance.json')
            with open(provenance_file, 'w', encoding='utf-8') as f:
                json.dump(provenance, f, indent=2)
            
            provenance['provenance_file'] = provenance_file
            print(f"Successfully processed HEIF image: {output_path}")
            print(f"Provenance saved to: {provenance_file}")
            return True, provenance
            
        except Exception as e:
            print(f"Error processing HEIF with TTL: {e}")
            return False, provenance
    
    def generate_rdf_provenance(self, provenance: Dict, output_path: str) -> str:
        """
        Generate RDF Turtle file from provenance metadata using W3C PROV-O ontology.
        
        Args:
            provenance: Provenance metadata dictionary
            output_path: Path for output TTL file
            
        Returns:
            Path to generated TTL file
        """
        try:
            rdf_lines = []
            rdf_lines.append("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
            rdf_lines.append("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .")
            rdf_lines.append("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .")
            rdf_lines.append("@prefix prov: <http://www.w3.org/ns/prov#> .")
            rdf_lines.append("@prefix dct: <http://purl.org/dc/terms/> .")
            rdf_lines.append("@prefix geo: <http://www.opengis.net/ont/geosparql#> .")
            rdf_lines.append("@prefix crypto: <http://www.w3.org/2000/10/swap/crypto#> .")
            rdf_lines.append("")
            
            # Original Entity (HEIF file)
            original_uri = f"urn:uuid:{provenance['original_uuid']}"
            rdf_lines.append(f"<{original_uri}>")
            rdf_lines.append("    a prov:Entity ;")
            rdf_lines.append(f"    rdfs:label \"{provenance['input_file']}\" ;")
            rdf_lines.append("    dct:format \"image/heif\" ;")
            if provenance.get('input_hash'):
                rdf_lines.append(f"    crypto:hash \"{provenance['input_hash']}\" ;")
                rdf_lines.append(f"    crypto:hashAlgorithm \"{provenance['input_hash_algorithm']}\" ;")
            rdf_lines.append("    .")
            rdf_lines.append("")
            
            # Derived Entity (GeoTIFF output)
            derived_uri = f"urn:uuid:{provenance['derived_uuid']}"
            rdf_lines.append(f"<{derived_uri}>")
            rdf_lines.append("    a prov:Entity, geo:Feature ;")
            rdf_lines.append(f"    rdfs:label \"{provenance['output_file']}\" ;")
            rdf_lines.append("    dct:format \"image/tiff\" ;")
            rdf_lines.append("    geo:hasGeometry \"GeoTIFF with GCPs\" ;")
            if provenance.get('output_hash'):
                rdf_lines.append(f"    crypto:hash \"{provenance['output_hash']}\" ;")
                rdf_lines.append(f"    crypto:hashAlgorithm \"{provenance['output_hash_algorithm']}\" ;")
            rdf_lines.append(f"    prov:wasDerivedFrom <{original_uri}> ;")
            rdf_lines.append(f"    prov:wasGeneratedBy <urn:uuid:{provenance['algorithm_uuid']}> ;")
            rdf_lines.append(f"    prov:generatedAtTime \"{provenance['processing_timestamp']}\"^^xsd:dateTime ;")
            rdf_lines.append("    .")
            rdf_lines.append("")
            
            # Activity (Processing Algorithm)
            activity_uri = f"urn:uuid:{provenance['algorithm_uuid']}"
            rdf_lines.append(f"<{activity_uri}>")
            rdf_lines.append("    a prov:Activity ;")
            rdf_lines.append(f"    rdfs:label \"{provenance['algorithm_name']}\" ;")
            rdf_lines.append(f"    prov:used <{original_uri}> ;")
            rdf_lines.append(f"    prov:startedAtTime \"{provenance['processing_timestamp']}\"^^xsd:dateTime ;")
            
            # Processing parameters
            if provenance.get('gcp_count') is not None:
                rdf_lines.append(f"    prov:qualifiedUsage [")
                rdf_lines.append(f"        a prov:Usage ;")
                rdf_lines.append(f"        rdfs:label \"Ground Control Points\" ;")
                rdf_lines.append(f"        prov:hadRole \"georeferencing\" ;")
                rdf_lines.append(f"        prov:value {provenance['gcp_count']} ;")
                rdf_lines.append(f"    ] ;")
            
            if provenance.get('transform_order') is not None:
                rdf_lines.append(f"    prov:qualifiedUsage [")
                rdf_lines.append(f"        a prov:Usage ;")
                rdf_lines.append(f"        rdfs:label \"Transformation Order\" ;")
                rdf_lines.append(f"        prov:value {provenance['transform_order']} ;")
                rdf_lines.append(f"    ] ;")
            
            if provenance.get('resample_method'):
                rdf_lines.append(f"    prov:qualifiedUsage [")
                rdf_lines.append(f"        a prov:Usage ;")
                rdf_lines.append(f"        rdfs:label \"Resampling Method\" ;")
                rdf_lines.append(f"        prov:value \"{provenance['resample_method']}\" ;")
                rdf_lines.append(f"    ] ;")
            
            rdf_lines.append("    .")
            rdf_lines.append("")
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(rdf_lines))
            
            print(f"RDF provenance saved to: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"Error generating RDF provenance: {e}")
            return None
    
    def cleanup(self):
        """Remove temporary files"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"Could not remove temp file {temp_file}: {e}")
        self.temp_files.clear()
    
    def __del__(self):
        """Cleanup on deletion"""
        self.cleanup()
