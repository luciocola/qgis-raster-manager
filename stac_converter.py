# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
stac_converter.py — Convert a _provenance.json sidecar to a STAC 1.0 Item.

Usage (standalone or from dialog):
    from .stac_converter import ProvenanceToSTACConverter
    path = ProvenanceToSTACConverter().convert(
        '/path/to/image_provenance.json',
        '/path/to/image_georeferenced.tif',
        '/path/to/output_dir'
    )
"""
from __future__ import annotations

import json
import os
from typing import Optional


class ProvenanceToSTACConverter:
    """
    Converts a _provenance.json produced by the HEIF TTL Importer into a
    STAC 1.0 Item JSON file.

    The converter reads the raster file with GDAL to extract a WGS-84 bounding
    box, then maps provenance fields onto the standard STAC Item schema with the
    following extensions:
      - checksum  (https://stac-extensions.github.io/checksum/v1.0.0/schema.json)
      - processing (https://stac-extensions.github.io/processing/v1.1.0/schema.json)
      - eo         (https://stac-extensions.github.io/eo/v1.1.0/schema.json)
    """

    STAC_EXTENSIONS = [
        "https://stac-extensions.github.io/checksum/v1.0.0/schema.json",
        "https://stac-extensions.github.io/processing/v1.1.0/schema.json",
        "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
    ]

    # Map _provenance.json quality report types → STAC property names
    _QUALITY_STAC_MAP = {
        "processingLevel": "processing:level",
        "usabilityAssessment": "quality:usability_score",
        "cloudCoverage": "eo:cloud_cover",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(
        self,
        provenance_json_path: str,
        raster_path: str,
        output_dir: str,
    ) -> str:
        """
        Convert *provenance_json_path* + *raster_path* into a STAC Item JSON file.

        Args:
            provenance_json_path: Absolute path to the ``_provenance.json`` sidecar.
            raster_path:          Absolute path to the corresponding GeoTIFF / JP2.
            output_dir:           Directory where the STAC Item file will be written.

        Returns:
            Absolute path to the written STAC Item JSON file.

        Raises:
            FileNotFoundError: if *provenance_json_path* or *raster_path* are missing.
            RuntimeError:      if GDAL cannot open *raster_path*.
        """
        if not os.path.exists(provenance_json_path):
            raise FileNotFoundError(f"Provenance file not found: {provenance_json_path}")
        if not os.path.exists(raster_path):
            raise FileNotFoundError(f"Raster file not found: {raster_path}")

        with open(provenance_json_path, "r", encoding="utf-8") as fh:
            prov = json.load(fh)

        bbox, geometry = self._extract_bbox_and_geometry(raster_path)
        properties = self._build_properties(prov)
        assets = self._build_assets(prov, provenance_json_path, raster_path)

        item_id = prov.get("derived_uuid", os.path.splitext(os.path.basename(raster_path))[0])
        item = {
            "type": "Feature",
            "stac_version": "1.0.0",
            "stac_extensions": self.STAC_EXTENSIONS,
            "id": item_id,
            "geometry": geometry,
            "bbox": bbox,
            "properties": properties,
            "links": [],
            "assets": assets,
        }

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{item_id}.json")
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(item, fh, indent=2)

        return output_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_bbox_and_geometry(self, raster_path: str):
        """Open *raster_path* with GDAL and return (bbox, GeoJSON geometry) in WGS-84."""
        try:
            from osgeo import gdal, osr
        except ImportError as exc:
            raise RuntimeError("GDAL/osgeo is required for STAC conversion") from exc

        ds = gdal.Open(raster_path, gdal.GA_ReadOnly)
        if ds is None:
            raise RuntimeError(f"GDAL could not open raster: {raster_path}")

        gt = ds.GetGeoTransform()
        width = ds.RasterXSize
        height = ds.RasterYSize
        proj_wkt = ds.GetProjection()
        ds = None  # close

        # Corner coordinates in the native CRS
        corners_native = [
            (gt[0], gt[3]),
            (gt[0] + width * gt[1], gt[3] + width * gt[4]),
            (gt[0] + width * gt[1] + height * gt[2], gt[3] + width * gt[4] + height * gt[5]),
            (gt[0] + height * gt[2], gt[3] + height * gt[5]),
        ]

        # Transform to WGS-84
        src_srs = osr.SpatialReference()
        if proj_wkt:
            src_srs.ImportFromWkt(proj_wkt)
        else:
            src_srs.ImportFromEPSG(4326)

        wgs84 = osr.SpatialReference()
        wgs84.ImportFromEPSG(4326)
        # Ensure lon/lat axis order
        wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

        transform_fn = osr.CoordinateTransformation(src_srs, wgs84)

        wgs_corners = []
        for x_native, y_native in corners_native:
            lon, lat, _ = transform_fn.TransformPoint(x_native, y_native)
            wgs_corners.append([lon, lat])
        # Close ring
        wgs_corners.append(wgs_corners[0])

        lons = [c[0] for c in wgs_corners[:-1]]
        lats = [c[1] for c in wgs_corners[:-1]]
        bbox = [min(lons), min(lats), max(lons), max(lats)]

        geometry = {
            "type": "Polygon",
            "coordinates": [wgs_corners],
        }
        return bbox, geometry

    def _build_properties(self, prov: dict) -> dict:
        """Map provenance fields to STAC Item properties."""
        props: dict = {
            "datetime": prov.get("processing_timestamp"),
            "title": prov.get("output_file"),
            "processing:lineage": prov.get("algorithm_name"),
            "processing:software": {"heif_ttl_importer": "QGIS Plugin"},
        }

        iso = prov.get("iso19115_4", {})
        for quality_report in iso.get("quality", []):
            q_type = quality_report.get("type")
            if q_type == "processingLevel":
                props["processing:level"] = quality_report.get("level")
            elif q_type == "usabilityAssessment":
                score = quality_report.get("usabilityScore")
                if score is not None:
                    props["quality:usability_score"] = score
                lims = quality_report.get("limitations", [])
                if lims:
                    props["quality:limitations"] = lims
            elif q_type == "cloudCoverage":
                pct = quality_report.get("coveragePercentage")
                if pct is not None:
                    props["eo:cloud_cover"] = pct

        grid = iso.get("gridSpatialRepresentation")
        if grid:
            props["grid_spatial_representation"] = grid

        return props

    def _build_assets(
        self,
        prov: dict,
        provenance_json_path: str,
        raster_path: str,
    ) -> dict:
        """Build the STAC Item assets dict."""
        prov_dir = os.path.dirname(provenance_json_path)

        # Determine MIME type from output file extension
        output_file = prov.get("output_file", "")
        if output_file.endswith(".jp2"):
            data_media_type = "image/jp2"
        else:
            data_media_type = "image/tiff; application=geotiff"

        assets: dict = {
            "data": {
                "href": os.path.relpath(raster_path, prov_dir),
                "type": data_media_type,
                "roles": ["data"],
                "title": prov.get("output_file"),
            },
            "provenance_json": {
                "href": os.path.basename(provenance_json_path),
                "type": "application/json",
                "roles": ["metadata"],
                "title": "Processing provenance (JSON)",
            },
        }

        # Add BLAKE3 multihash checksum to the data asset
        output_hash = prov.get("output_hash")
        output_hash_algo = prov.get("output_hash_algorithm", "blake3")
        if output_hash:
            assets["data"]["checksum:multihash"] = output_hash
            assets["data"]["checksum:algorithm"] = output_hash_algo

        # Include sibling TTL if present
        ttl_sibling = provenance_json_path.replace("_provenance.json", "_provenance.ttl")
        if os.path.exists(ttl_sibling):
            assets["provenance_ttl"] = {
                "href": os.path.basename(ttl_sibling),
                "type": "text/turtle",
                "roles": ["metadata"],
                "title": "Processing provenance (RDF/Turtle)",
            }

        # Include GDAL AUX.XML if present
        aux_path = raster_path + ".aux.xml"
        if os.path.exists(aux_path):
            assets["gdal_statistics"] = {
                "href": os.path.relpath(aux_path, prov_dir),
                "type": "application/xml",
                "roles": ["metadata"],
                "title": "GDAL raster statistics",
            }

        # Include OSM context GeoJSON sidecar if present
        osm_path = provenance_json_path.replace("_provenance.json", "_osm_context.geojson")
        if not os.path.exists(osm_path):
            # Also check for path stored in provenance under osm_context.file
            osm_ctx = prov.get("osm_context", {})
            if osm_ctx.get("file"):
                candidate = os.path.join(prov_dir, osm_ctx["file"])
                if os.path.exists(candidate):
                    osm_path = candidate
                else:
                    osm_path = None
            else:
                osm_path = None
        if osm_path and os.path.exists(osm_path):
            osm_meta = prov.get("osm_context", {})
            assets["osm_context"] = {
                "href": os.path.relpath(osm_path, prov_dir),
                "type": "application/geo+json",
                "roles": ["context", "metadata"],
                "title": "OSM context features (roads, buildings, landuse, waterways)",
                "osm:bbox": osm_meta.get("bbox"),
                "osm:query_timestamp": osm_meta.get("query_timestamp"),
                "osm:feature_counts": osm_meta.get("feature_counts"),
            }

        return assets
