"""
HEIF/TTL Imagery Importer
A QGIS plugin for importing HEIF imagery with TTL metadata georeferencing
"""


def classFactory(iface):
    from .heif_ttl_importer import HEIFTTLImporter
    return HEIFTTLImporter(iface)
