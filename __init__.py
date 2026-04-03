# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
General Raster Importer
A QGIS plugin for importing any GDAL-readable raster and exporting to any GDAL-writable format,
with optional TTL/RDF metadata georeferencing support.
"""


def classFactory(iface):
    from .heif_ttl_importer import HEIFTTLImporter
    return HEIFTTLImporter(iface)
