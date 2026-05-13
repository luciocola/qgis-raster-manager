# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
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
        """Execute all parsing steps.

        Uses rdflib for robust order-independent parsing first; falls back to
        the legacy regex paths if rdflib is unavailable or returns nothing.
        """
        # Primary: rdflib — handles any predicate ordering
        self._parse_with_rdflib()

        # Secondary: CCO/TB21 GIMI regex (in case rdflib unavailable)
        if not self.correspondences:
            self._parse_cco_format()

        # Tertiary: old IMH regex format
        if not self.correspondences:
            self._parse_image_coordinates()
            self._parse_ground_coordinates()
            self._parse_correspondences()
            self._parse_tiles()
            self._parse_correspondence_groups()

    def _parse_with_rdflib(self):
        """Use rdflib to parse the TTL, robust to any predicate ordering."""
        try:
            from rdflib import Graph
            from rdflib.namespace import RDF
            from collections import defaultdict

            g = Graph()
            g.parse(data=self.content, format='turtle')

            # Index every subject by its predicate local-names and type local-names.
            # local name = fragment after '#' or last path segment after '/'.
            def local(uri):
                s = str(uri)
                return s.split('#')[-1].split('/')[-1]

            # {subject_str: {pred_local: [obj, ...]}}
            props = defaultdict(lambda: defaultdict(list))
            # {subject_str: {type_local}}
            types = defaultdict(set)

            for s, p, o in g:
                s_str = str(s)
                p_local = local(p)
                props[s_str][p_local].append(o)
                if p == RDF.type:
                    types[s_str].add(local(o))

            def first_val(prop_dict, *keys):
                """Return the first value found for any of the given keys."""
                for k in keys:
                    vals = prop_dict.get(k)
                    if vals:
                        return vals[0]
                return None

            # ---- image coordinates ----
            for subj, t in types.items():
                if 'ImageCoordinate' in t or '_0001664' in t:
                    p = props[subj]
                    x = first_val(p, 'has_x_coordinate', '_0001626')
                    y = first_val(p, 'has_y_coordinate', '_0001630')
                    if x is not None and y is not None:
                        self.image_coords[subj] = ImageCoordinate(
                            subj, int(float(str(x))), int(float(str(y))))

            # ---- ground coordinates ----
            for subj, t in types.items():
                if 'GroundCoordinate' in t or '_0001081' in t:
                    p = props[subj]
                    lon = first_val(p, 'has_longitude', 'ont00001764')
                    lat = first_val(p, 'has_latitude', 'ont00001766')
                    if lon is not None and lat is not None:
                        self.ground_coords[subj] = GroundCoordinate(
                            subj, float(str(lon)), float(str(lat)))

            # ---- correspondences ----
            for subj, t in types.items():
                if 'ImageToGroundCorrespondence' in t or '_0001657' in t:
                    p = props[subj]
                    img = first_val(p, 'has_image_coordinate', '_0001642')
                    gnd = first_val(p, 'has_ground_coordinate', '_0001667')
                    if img is not None and gnd is not None:
                        img_str = str(img)
                        gnd_str = str(gnd)
                        if img_str in self.image_coords and gnd_str in self.ground_coords:
                            self.correspondences[subj] = Correspondence(
                                subj,
                                self.image_coords[img_str],
                                self.ground_coords[gnd_str])

            # ---- tiles ----
            for subj, t in types.items():
                if 'ont00002004' in t or 'Tile' in t:
                    p = props[subj]
                    labels = p.get('label', [])
                    if labels:
                        self.tiles[subj] = str(labels[0])

            # ---- correspondence groups ----
            for subj, t in types.items():
                if '_0001634' in t or 'CorrespondenceGroup' in t or 'CorrespondenceSet' in t:
                    p = props[subj]
                    # Collect correspondence refs (_0001678)
                    corr_refs = p.get('_0001678', [])
                    wkt_vals = p.get('asWKT', [])
                    tile_refs = p.get('ont00001808', [])
                    wkt = str(wkt_vals[0]) if wkt_vals else None
                    tile_uri = str(tile_refs[0]) if tile_refs else None
                    tile_label = self.tiles.get(tile_uri, f"Tile {tile_uri}") if tile_uri else "Unknown Tile"
                    corrs = [self.correspondences[str(r)]
                             for r in corr_refs if str(r) in self.correspondences]
                    if corrs:
                        self.correspondence_groups[subj] = CorrespondenceGroup(
                            subj, tile_label, corrs, wkt)

        except Exception as e:
            print(f"TTLParser rdflib pass skipped ({type(e).__name__}: {e})")
    
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
    
    def get_image_dimensions(self) -> Tuple[int, int]:
        """Extract image dimensions from TTL comments or metadata"""
        # Look for comment like: # Image dimensions: 4394x3775
        pattern = r'#\s*Image dimensions:\s*(\d+)x(\d+)'
        match = re.search(pattern, self.content)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return (0, 0)
    
    def _parse_cco_format(self):
        """Parse CCO/TB21 GIMI format RDF"""
        # Parse ImageCoordinate entities
        # Pattern: <urn:uuid:...> a cco:ImageCoordinate ; cco:has_x_coordinate "123.45"^^xsd:double ; cco:has_y_coordinate "678.90"^^xsd:double
        img_coord_pattern = r'<(urn:uuid:[^>]+)>\s+a\s+cco:ImageCoordinate\s*;[^<]*cco:has_x_coordinate\s+"([\d\.\-]+)"[^<]*cco:has_y_coordinate\s+"([\d\.\-]+)"'
        for match in re.finditer(img_coord_pattern, self.content, re.MULTILINE | re.DOTALL):
            uri = match.group(1)
            x = float(match.group(2))
            y = float(match.group(3))
            self.image_coords[uri] = ImageCoordinate(uri, int(x), int(y))
        
        # Parse GroundCoordinate entities
        # Pattern: <urn:uuid:...> a cco:GroundCoordinate ; cco:has_longitude "138.49"^^xsd:double ; cco:has_latitude "-34.80"^^xsd:double
        ground_coord_pattern = r'<(urn:uuid:[^>]+)>\s+a\s+cco:GroundCoordinate\s*;[^<]*cco:has_longitude\s+"([\d\.\-]+)"[^<]*cco:has_latitude\s+"([\d\.\-]+)"'
        for match in re.finditer(ground_coord_pattern, self.content, re.MULTILINE | re.DOTALL):
            uri = match.group(1)
            lon = float(match.group(2))
            lat = float(match.group(3))
            self.ground_coords[uri] = GroundCoordinate(uri, lon, lat)
        
        # Parse ImageToGroundCorrespondence entities
        # Pattern: <urn:uuid:...> a cco:ImageToGroundCorrespondence ; ... cco:has_image_coordinate <urn:uuid:IMG> ; cco:has_ground_coordinate <urn:uuid:GROUND>
        corr_pattern = r'<(urn:uuid:[^>]+)>\s+a\s+cco:ImageToGroundCorrespondence\s*;[^<]*cco:has_image_coordinate\s+<(urn:uuid:[^>]+)>[^<]*cco:has_ground_coordinate\s+<(urn:uuid:[^>]+)>'
        for match in re.finditer(corr_pattern, self.content, re.MULTILINE | re.DOTALL):
            corr_uri = match.group(1)
            img_uri = match.group(2)
            ground_uri = match.group(3)
            
            if img_uri in self.image_coords and ground_uri in self.ground_coords:
                self.correspondences[corr_uri] = Correspondence(
                    corr_uri,
                    self.image_coords[img_uri],
                    self.ground_coords[ground_uri]
                )
    
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
