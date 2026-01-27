"""
TTL/RDF Parser for extracting Ground Control Points from metadata
"""
from typing import List, Dict, Tuple, Optional
import re


class ImageCoordinate:
    """Represents an image coordinate (pixel position)"""
    def __init__(self, uri: str, x: int, y: int):
        self.uri = uri
        self.x = x
        self.y = y
        
    def __repr__(self):
        return f"ImageCoord({self.x}, {self.y})"


class GroundCoordinate:
    """Represents a ground coordinate (geographic position)"""
    def __init__(self, uri: str, lon: float, lat: float):
        self.uri = uri
        self.lon = lon
        self.lat = lat
        
    def __repr__(self):
        return f"GroundCoord({self.lon}, {self.lat})"


class Correspondence:
    """Links an image coordinate to a ground coordinate (a GCP)"""
    def __init__(self, uri: str, img_coord: ImageCoordinate, ground_coord: GroundCoordinate):
        self.uri = uri
        self.img_coord = img_coord
        self.ground_coord = ground_coord
        
    def __repr__(self):
        return f"GCP: {self.img_coord} -> {self.ground_coord}"


class CorrespondenceGroup:
    """A group of correspondences that define a georeferenced tile"""
    def __init__(self, uri: str, tile_label: str, correspondences: List[Correspondence], wkt: Optional[str] = None):
        self.uri = uri
        self.tile_label = tile_label
        self.correspondences = correspondences
        self.wkt = wkt
        
    def __repr__(self):
        return f"Tile: {self.tile_label} with {len(self.correspondences)} GCPs"


class TTLParser:
    """Parser for TTL/RDF files containing imagery metadata"""
    
    def __init__(self, ttl_file_path: str = None):
        self.ttl_file_path = ttl_file_path
        self.content = ""
        self.image_coords: Dict[str, ImageCoordinate] = {}
        self.ground_coords: Dict[str, GroundCoordinate] = {}
        self.correspondences: Dict[str, Correspondence] = {}
        self.correspondence_groups: Dict[str, CorrespondenceGroup] = {}
        self.tiles: Dict[str, str] = {}
    
    def parse(self) -> bool:
        """Parse the TTL file and extract all metadata"""
        try:
            if not self.ttl_file_path:
                raise ValueError("No TTL file path provided")
                
            with open(self.ttl_file_path, 'r', encoding='utf-8') as f:
                self.content = f.read()
                
            self._parse_all()
            return True
        except Exception as e:
            print(f"Error parsing TTL file: {e}")
            return False
    
    def parse_string(self, ttl_content: str) -> bool:
        """Parse TTL/RDF content from a string (e.g., internal HEIF metadata)"""
        try:
            self.content = ttl_content
            self._parse_all()
            return True
        except Exception as e:
            print(f"Error parsing TTL string: {e}")
            return False
    
    def _parse_all(self):
        """Execute all parsing steps"""
        self._parse_image_coordinates()
        self._parse_ground_coordinates()
        self._parse_correspondences()
        self._parse_tiles()
        self._parse_correspondence_groups()
    
    def _parse_image_coordinates(self):
        """Extract all image coordinates from TTL"""
        # Pattern: <urn:uuid:...> imh:_0001626 2048 ; imh:_0001630 4096 ; a imh:_0001664
        pattern = r'<(urn:uuid:[^>]+)>\s+imh:_0001626\s+(\d+)\s*;\s*imh:_0001630\s+(\d+)\s*;[^<]*a\s+imh:_0001664'
        
        matches = re.finditer(pattern, self.content, re.MULTILINE | re.DOTALL)
        for match in matches:
            uri = match.group(1)
            x = int(match.group(2))
            y = int(match.group(3))
            self.image_coords[uri] = ImageCoordinate(uri, x, y)
    
    def _parse_ground_coordinates(self):
        """Extract all ground coordinates from TTL"""
        # Pattern: <urn:uuid:...> a imh:_0001081 ; ... cco:ont00001764 138.665473 ; cco:ont00001766 -34.813112
        pattern = r'<(urn:uuid:[^>]+)>\s+a\s+imh:_0001081\s*;[^<]*cco:ont00001764\s+([\d\.\-]+)\s*;[^<]*cco:ont00001766\s+([\d\.\-]+)'
        
        matches = re.finditer(pattern, self.content, re.MULTILINE | re.DOTALL)
        for match in matches:
            uri = match.group(1)
            lon = float(match.group(2))
            lat = float(match.group(3))
            self.ground_coords[uri] = GroundCoordinate(uri, lon, lat)
    
    def _parse_correspondences(self):
        """Extract correspondences linking image coords to ground coords"""
        # Pattern: <urn:uuid:...> imh:_0001642 <urn:uuid:IMG> ; imh:_0001667 <urn:uuid:GROUND> ; a imh:_0001657
        pattern = r'<(urn:uuid:[^>]+)>\s+imh:_0001642\s+<(urn:uuid:[^>]+)>\s*;\s*imh:_0001667\s+<(urn:uuid:[^>]+)>\s*;[^<]*a\s+imh:_0001657'
        
        matches = re.finditer(pattern, self.content, re.MULTILINE | re.DOTALL)
        for match in matches:
            corr_uri = match.group(1)
            img_uri = match.group(2)
            ground_uri = match.group(3)
            
            if img_uri in self.image_coords and ground_uri in self.ground_coords:
                self.correspondences[corr_uri] = Correspondence(
                    corr_uri,
                    self.image_coords[img_uri],
                    self.ground_coords[ground_uri]
                )
    
    def _parse_tiles(self):
        """Extract tile labels"""
        # Pattern: <urn:uuid:...> a cco:ont00002004 ; rdfs:label "tile: (1,0)"
        pattern = r'<(urn:uuid:[^>]+)>\s+a\s+cco:ont00002004\s*;[^<]*rdfs:label\s+"([^"]+)"'
        
        matches = re.finditer(pattern, self.content, re.MULTILINE | re.DOTALL)
        for match in matches:
            uri = match.group(1)
            label = match.group(2)
            self.tiles[uri] = label
    
    def _parse_correspondence_groups(self):
        """Extract correspondence groups (tiles with their GCPs)"""
        # Pattern: <urn:uuid:...> imh:_0001678 <urn:uuid:...>, <urn:uuid:...> ; geosparql:asWKT "..." ; a imh:_0001634 ; ... cco:ont00001808 <urn:uuid:TILE>
        pattern = r'<(urn:uuid:[^>]+)>\s+imh:_0001678\s+([^;]+);\s*geosparql:asWKT\s+"([^"]+)"[^<]*a\s+imh:_0001634[^<]*cco:ont00001808\s+<(urn:uuid:[^>]+)>'
        
        matches = re.finditer(pattern, self.content, re.MULTILINE | re.DOTALL)
        for match in matches:
            group_uri = match.group(1)
            corr_refs = match.group(2)
            wkt = match.group(3)
            tile_uri = match.group(4)
            
            # Extract correspondence URIs
            corr_uris = re.findall(r'<(urn:uuid:[^>]+)>', corr_refs)
            
            # Get correspondences
            corrs = []
            for corr_uri in corr_uris:
                if corr_uri in self.correspondences:
                    corrs.append(self.correspondences[corr_uri])
            
            # Get tile label
            tile_label = self.tiles.get(tile_uri, f"Unknown Tile {tile_uri}")
            
            if corrs:
                self.correspondence_groups[group_uri] = CorrespondenceGroup(
                    group_uri, tile_label, corrs, wkt
                )
    
    def get_all_gcps(self) -> List[Tuple[int, int, float, float]]:
        """Get all GCPs as (pixel_x, pixel_y, lon, lat) tuples"""
        gcps = []
        for corr in self.correspondences.values():
            gcps.append((
                corr.img_coord.x,
                corr.img_coord.y,
                corr.ground_coord.lon,
                corr.ground_coord.lat
            ))
        return gcps
    
    def get_gcps_for_tile(self, tile_label: str) -> List[Tuple[int, int, float, float]]:
        """Get GCPs for a specific tile"""
        for group in self.correspondence_groups.values():
            if group.tile_label == tile_label:
                gcps = []
                for corr in group.correspondences:
                    gcps.append((
                        corr.img_coord.x,
                        corr.img_coord.y,
                        corr.ground_coord.lon,
                        corr.ground_coord.lat
                    ))
                return gcps
        return []
    
    def get_tile_labels(self) -> List[str]:
        """Get all tile labels"""
        return [group.tile_label for group in self.correspondence_groups.values()]
    
    def get_image_dimensions(self) -> Tuple[int, int]:
        """Estimate image dimensions from max coordinates"""
        if not self.image_coords:
            return (0, 0)
        
        max_x = max(coord.x for coord in self.image_coords.values())
        max_y = max(coord.y for coord in self.image_coords.values())
        return (max_x, max_y)
