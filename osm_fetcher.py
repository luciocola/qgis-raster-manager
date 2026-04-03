# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
osm_fetcher.py — Query OpenStreetMap features via the Overpass API for a
given WGS-84 bounding box and write the result as a GeoJSON FeatureCollection.

Usage::

    from .osm_fetcher import OSMContextFetcher
    fetcher = OSMContextFetcher()
    metadata = fetcher.fetch(
        bbox=[min_lon, min_lat, max_lon, max_lat],
        output_geojson_path='/path/to/image_osm_context.geojson',
        progress_callback=lambda msg: print(msg),   # optional
    )
    # metadata = {'query_time': '...', 'feature_counts': {...}, 'bbox': [...]}
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 60  # seconds

# Fallback mirrors tried in order when the primary endpoint times out or is unavailable
OVERPASS_FALLBACK_URLS: List[str] = [
    "https://overpass.karte.io/api/interpreter",
]

# Retry configuration for transient errors (502/503/504)
OVERPASS_MAX_RETRIES = 2
OVERPASS_RETRY_DELAY = 5  # seconds between retries (doubles each attempt)

# Maximum seconds to wait for a free Overpass slot before giving up
OVERPASS_MAX_SLOT_WAIT = 90  # seconds

# Feature categories we care about, keyed by the OSM tag to inspect
FEATURE_CATEGORIES: List[Tuple[str, str]] = [
    ("highway",  "road"),
    ("building", "building"),
    ("landuse",  "landuse"),
    ("waterway", "waterway"),
]

# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class OSMContextFetcher:
    """
    Fetch roads, buildings, landuse and waterways from the Overpass API for a
    WGS-84 bounding box and persist them as a GeoJSON FeatureCollection sidecar.

    The returned GeoJSON carries a ``feature_type`` property on each Feature
    (one of ``road``, ``building``, ``landuse``, ``waterway``) so that the
    QGIS layer-loading code can split features into separate layers.
    """

    def __init__(
        self,
        overpass_url: str = OVERPASS_URL,
        timeout: int = OVERPASS_TIMEOUT,
        max_retries: int = OVERPASS_MAX_RETRIES,
        retry_delay: float = OVERPASS_RETRY_DELAY,
        fallback_urls: Optional[List[str]] = None,
        max_slot_wait: float = OVERPASS_MAX_SLOT_WAIT,
    ):
        self._url = overpass_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._fallback_urls = fallback_urls if fallback_urls is not None else OVERPASS_FALLBACK_URLS
        self._max_slot_wait = max_slot_wait

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        bbox: List[float],
        output_geojson_path: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """
        Query Overpass for the supplied bounding box and write a GeoJSON file.

        Args:
            bbox:                 ``[min_lon, min_lat, max_lon, max_lat]`` in WGS-84.
            output_geojson_path:  Absolute path where the GeoJSON will be written.
            progress_callback:    Optional callable that receives progress strings.

        Returns:
            A metadata dict::

                {
                    "query_timestamp": "2026-01-15T12:34:56+00:00",
                    "bbox": [...],
                    "feature_counts": {"road": 12, "building": 45, ...},
                    "file": "<basename of output_geojson_path>",
                    "overpass_url": "...",
                }

        Raises:
            ValueError:       if bbox is invalid.
            RuntimeError:     if the Overpass request fails.
            OSError:          if the GeoJSON file cannot be written.
        """
        self._validate_bbox(bbox)
        min_lon, min_lat, max_lon, max_lat = bbox

        # Overpass bbox order: south, west, north, east
        south, west, north, east = min_lat, min_lon, max_lat, max_lon

        query = self._build_overpass_query(south, west, north, east)

        if progress_callback:
            progress_callback(
                "Checking Overpass API availability before querying…"
            )

        raw = self._http_post(query, progress_callback=progress_callback)

        if progress_callback:
            progress_callback("Converting Overpass response to GeoJSON…")

        geojson = self._overpass_to_geojson(raw, bbox)
        feature_counts = self._count_by_type(geojson["features"])

        import os
        os.makedirs(os.path.dirname(output_geojson_path) or ".", exist_ok=True)
        with open(output_geojson_path, "w", encoding="utf-8") as fh:
            json.dump(geojson, fh, indent=2)

        if progress_callback:
            total = sum(feature_counts.values())
            progress_callback(
                f"OSM context saved — {total} features "
                f"({', '.join(f'{v} {k}s' for k, v in feature_counts.items() if v)})"
            )

        import os as _os
        return {
            "query_timestamp": datetime.now(timezone.utc).isoformat(),
            "bbox": bbox,
            "feature_counts": feature_counts,
            "file": _os.path.basename(output_geojson_path),
            "overpass_url": self._url,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_bbox(self, bbox: List[float]) -> None:
        if len(bbox) != 4:
            raise ValueError("bbox must have exactly 4 elements: [min_lon, min_lat, max_lon, max_lat]")
        min_lon, min_lat, max_lon, max_lat = bbox
        if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
            raise ValueError(f"Longitude values out of range: {min_lon}, {max_lon}")
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            raise ValueError(f"Latitude values out of range: {min_lat}, {max_lat}")
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError("bbox min values must be less than max values")

    def _build_overpass_query(
        self, south: float, west: float, north: float, east: float
    ) -> str:
        """Build a compact Overpass QL query for the four feature categories."""
        bbox_str = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
        union_parts = "\n".join(
            f'  way["{tag}"]({bbox_str});'
            for tag, _ in FEATURE_CATEGORIES
        )
        # Add waterway relations (rivers, canals that are mapped as relations)
        union_parts += f'\n  relation["waterway"]({bbox_str});'
        return (
            f'[out:json][timeout:{self._timeout}];\n'
            f'(\n{union_parts}\n);\n'
            f'out body geom;'
        )

    # Transient HTTP status codes that warrant a retry
    _RETRYABLE_CODES = frozenset({429, 502, 503, 504})

    @staticmethod
    def _status_url_for(interpreter_url: str) -> str:
        """Derive the /api/status URL from an /api/interpreter URL."""
        return interpreter_url.rsplit("/interpreter", 1)[0] + "/status"

    def _seconds_until_free_slot(self, status_url: str) -> Optional[float]:
        """
        Query the Overpass /api/status endpoint and return how many seconds to
        wait before a slot will be free (0.0 means a slot is available right
        now).  Returns ``None`` if the status endpoint cannot be reached so the
        caller can proceed optimistically.
        """
        try:
            req = urllib.request.Request(status_url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None  # status unreachable — proceed optimistically

        # "2 slots available now."
        m = re.search(r"(\d+)\s+slots?\s+available\s+now", text, re.IGNORECASE)
        if m and int(m.group(1)) > 0:
            return 0.0

        # "Slot available after: 2026-03-31T12:00:34Z, in 34 seconds."
        m = re.search(r"in\s+(\d+)\s+seconds?", text, re.IGNORECASE)
        if m:
            return float(m.group(1))

        return 0.0  # unrecognised format — proceed optimistically

    def _http_post(
        self,
        query: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """
        Post *query* to Overpass and return the parsed JSON response.

        Before each endpoint attempt the /api/status endpoint is checked so
        the request is only sent when the server has a free query slot,
        eliminating the root cause of HTTP 504 Gateway Timeout.
        Falls back to mirror URLs on network/server errors.
        """
        encoded_data = urllib.parse.urlencode({"data": query}).encode("utf-8")
        endpoints = [self._url] + list(self._fallback_urls)
        last_exc: Optional[Exception] = None

        for url in endpoints:
            # --- 1. Wait for a free slot on this endpoint ---
            status_url = self._status_url_for(url)
            wait = self._seconds_until_free_slot(status_url)
            if wait is not None and wait > 0:
                if wait > self._max_slot_wait:
                    # Server too busy — skip to next mirror
                    last_exc = RuntimeError(
                        f"Overpass endpoint {url} has no free slots for "
                        f"{wait:.0f} s (max wait {self._max_slot_wait} s)"
                    )
                    continue
                if progress_callback:
                    progress_callback(
                        f"Overpass server busy — waiting {wait:.0f} s for a free slot…"
                    )
                time.sleep(wait + 1)  # +1 s safety margin
            elif wait is None:
                if progress_callback:
                    progress_callback(
                        f"Could not reach status endpoint for {url} — trying anyway…"
                    )

            if progress_callback:
                progress_callback("Querying Overpass API for OSM context data…")

            # --- 2. Send the query (with retries for transient errors) ---
            for attempt in range(self._max_retries):
                req = urllib.request.Request(
                    url,
                    data=encoded_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                        raw_bytes = resp.read()
                except urllib.error.HTTPError as exc:
                    last_exc = exc
                    if exc.code in self._RETRYABLE_CODES:
                        delay = self._retry_delay * (2 ** attempt)
                        if attempt < self._max_retries - 1:
                            if progress_callback:
                                progress_callback(
                                    f"HTTP {exc.code} — retrying in {delay:.0f} s "
                                    f"(attempt {attempt + 2}/{self._max_retries})…"
                                )
                            time.sleep(delay)
                            continue
                        break  # retries exhausted — try next mirror
                    raise RuntimeError(
                        f"Overpass API returned HTTP {exc.code}: {exc.reason}"
                    ) from exc
                except (urllib.error.URLError, OSError) as exc:
                    last_exc = exc
                    break  # network error — try next mirror
                else:
                    try:
                        return json.loads(raw_bytes.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            f"Overpass response was not valid JSON: {exc}"
                        ) from exc

        # All endpoints exhausted
        if isinstance(last_exc, urllib.error.HTTPError):
            raise RuntimeError(
                f"Overpass API returned HTTP {last_exc.code}: {last_exc.reason} "
                f"(tried {len(endpoints)} endpoint(s))"
            ) from last_exc
        raise RuntimeError(
            f"Could not reach any Overpass API endpoint: {last_exc}"
        ) from last_exc

    def _overpass_to_geojson(self, overpass_data: dict, bbox: List[float]) -> dict:
        """
        Convert an Overpass JSON response (``out body geom`` format) to a GeoJSON
        FeatureCollection.  Every feature gets a ``feature_type`` property.
        """
        features = []
        for element in overpass_data.get("elements", []):
            feature = self._element_to_feature(element)
            if feature is not None:
                features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features,
            "bbox": bbox,
            "metadata": {
                "source": "OpenStreetMap via Overpass API",
                "license": "ODbL 1.0 — © OpenStreetMap contributors",
                "query_time": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _element_to_feature(self, element: dict) -> Optional[dict]:
        """Convert a single Overpass element to a GeoJSON Feature or None."""
        elem_type = element.get("type")
        tags = element.get("tags", {})

        # Determine feature_type from tag priority
        feature_type = self._classify_tags(tags)
        if feature_type is None:
            return None

        geometry = None
        if elem_type == "way":
            geometry = self._way_to_geometry(element)
        elif elem_type == "relation":
            geometry = self._relation_to_geometry(element)
        elif elem_type == "node":
            lat = element.get("lat")
            lon = element.get("lon")
            if lat is not None and lon is not None:
                geometry = {"type": "Point", "coordinates": [lon, lat]}

        if geometry is None:
            return None

        properties = dict(tags)
        properties["feature_type"] = feature_type
        properties["osm_id"] = element.get("id")
        properties["osm_type"] = elem_type

        return {
            "type": "Feature",
            "id": f"{elem_type}/{element.get('id')}",
            "geometry": geometry,
            "properties": properties,
        }

    @staticmethod
    def _classify_tags(tags: dict) -> Optional[str]:
        """Return the first matching feature_type for this tag set, or None."""
        for osm_tag, feature_type in FEATURE_CATEGORIES:
            if osm_tag in tags:
                return feature_type
        return None

    @staticmethod
    def _way_to_geometry(element: dict) -> Optional[dict]:
        """Convert a way element (with geometry) to a GeoJSON LineString or Polygon."""
        geometry = element.get("geometry", [])
        if not geometry:
            return None
        coords = [[pt["lon"], pt["lat"]] for pt in geometry if "lon" in pt and "lat" in pt]
        if not coords:
            return None
        # Close ring if first/last nodes match → Polygon, else LineString
        if len(coords) >= 4 and coords[0] == coords[-1]:
            return {"type": "Polygon", "coordinates": [coords]}
        return {"type": "LineString", "coordinates": coords}

    @staticmethod
    def _relation_to_geometry(element: dict) -> Optional[dict]:
        """
        Convert a relation element to a MultiLineString (simplified).
        Full multipolygon reconstruction is intentionally out of scope.
        """
        members = element.get("members", [])
        rings = []
        for member in members:
            if member.get("type") == "way":
                geom = member.get("geometry", [])
                coords = [[pt["lon"], pt["lat"]] for pt in geom if "lon" in pt and "lat" in pt]
                if coords:
                    rings.append(coords)
        if not rings:
            return None
        return {"type": "MultiLineString", "coordinates": rings}

    @staticmethod
    def _count_by_type(features: List[dict]) -> Dict[str, int]:
        """Return per-category feature counts."""
        counts: Dict[str, int] = {ft: 0 for _, ft in FEATURE_CATEGORIES}
        for feat in features:
            ft = feat.get("properties", {}).get("feature_type")
            if ft in counts:
                counts[ft] += 1
        return counts
