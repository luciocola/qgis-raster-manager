# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Third-party notice
# ------------------
# This module interfaces with the DJI Mobile SDK and DJI Windows SDK.
# DJI, the DJI logo, DJI Mobile SDK, and all related product names are
# trademarks or registered trademarks of SZ DJI Technology Co., Ltd.
# Use of the DJI SDK is subject to the DJI SDK Developer License Agreement:
# https://developer.dji.com/policies/sdk-developer-license-agreement/
# A valid DJI Developer App Key is required; register at:
# https://developer.dji.com/user/apps
"""
dji_adapter.py – thin bridge to the dji_drone_processor sibling plugin.

Both QGIS-general-raster-importer and dji_drone_processor live inside the
same parent directory.  This module adds that parent to sys.path at import
time so that ``dji_drone_processor.exif_utils`` and
``dji_drone_processor.processor`` can be imported without requiring the
plugin to be separately installed.

Usage::

    from .dji_adapter import (
        DJIImageMetadata, scan_image_folder, footprint_bbox,
        GDALSimpleProcessor, NodeODMProcessor,
        create_footprints_geojson, ProcessingResult,
        DJI_AVAILABLE, DJI_ERROR,
    )
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Locate dji_drone_processor relative to this file
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)  # parent of both sibling plugins

if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

# ---------------------------------------------------------------------------
# Attempt import – graceful degradation if plugin is absent
# ---------------------------------------------------------------------------
DJI_AVAILABLE: bool = False
DJI_ERROR: str = ""

try:
    from dji_drone_processor.exif_utils import (  # type: ignore[import]
        DJIImageMetadata,
        scan_image_folder,
        scan_video_metadata,
        extract_center_frame_gps,
        footprint_bbox,
    )
    from dji_drone_processor.processor import (  # type: ignore[import]
        ProcessingResult,
        GDALSimpleProcessor,
        NodeODMProcessor,
        create_footprints_geojson,
    )
    from dji_drone_processor.flight_stac import (  # type: ignore[import]
        flight_track_to_geojson,
        create_video_stac_item,
        hash_stac_item,
        save_flight_track,
        anchor_via_api,
        extract_frames_as_gimi,
    )
    DJI_AVAILABLE = True
except ImportError as _e:
    DJI_ERROR = str(_e)

    # ── Stubs so the rest of the module can still be imported ────────
    class DJIImageMetadata:  # type: ignore[no-redef]
        pass

    class ProcessingResult:  # type: ignore[no-redef]
        pass

    class GDALSimpleProcessor:  # type: ignore[no-redef]
        pass

    class NodeODMProcessor:  # type: ignore[no-redef]
        pass

    def scan_image_folder(folder: str):  # type: ignore[misc]
        return []

    def scan_video_metadata(video_path: str, sample_interval_s: float = 1.0, progress_cb=None):  # type: ignore[misc]
        return []

    def extract_center_frame_gps(video_path: str, sidecar_path=None):  # type: ignore[misc]
        return None

    def footprint_bbox(meta):  # type: ignore[misc]
        return None

    def create_footprints_geojson(images, output_path: str) -> bool:  # type: ignore[misc]
        return False

    def flight_track_to_geojson(gps_points, video_path=None):  # type: ignore[misc]
        return {"type": "FeatureCollection", "features": []}

    def create_video_stac_item(video_path, gps_points, cop_meta=None, item_id=None):  # type: ignore[misc]
        return {}

    def hash_stac_item(stac_item) -> str:  # type: ignore[misc]
        return ""

    def save_flight_track(gps_points, video_path, output_dir, cop_meta=None, item_id=None):  # type: ignore[misc]
        return ("", "", "")

    def anchor_via_api(stac_item_path, sha256_hash, ipfs_cid=None, api_url="http://localhost:8000", timeout=30):  # type: ignore[misc]
        return {"status": "error", "sha256": sha256_hash}

    def extract_frames_as_gimi(video_path, gps_points, output_dir, cop_meta=None,  # type: ignore[misc]
                                n_frames=5, quality=90, sample_interval_s=1.0,
                                progress_cb=None):
        return []
