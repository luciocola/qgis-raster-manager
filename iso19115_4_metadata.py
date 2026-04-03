# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ISO 19115-4 Imagery Metadata Extractor

This module extracts and generates ISO 19115-4 compliant metadata for imagery and gridded data.
ISO 19115-4 provides imagery-specific metadata quality elements including radiometric accuracy,
sensor quality, cloud coverage, processing level, and usability assessment.

References:
- ISO 19115-4:2014 - Geographic information - Metadata - Part 4: Imagery and gridded data
- ISO 19115-1:2014 - Geographic information - Metadata - Part 1: Fundamentals
"""

import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from PIL import Image
import json


class ISO19115_4MetadataExtractor:
    """
    Extract ISO 19115-4 metadata from HEIF imagery files.
    
    Provides imagery-specific quality metadata including:
    - Radiometric accuracy
    - Sensor quality
    - Cloud coverage
    - Snow coverage
    - Processing level
    - Usability assessment
    """
    
    def __init__(self):
        """Initialize the metadata extractor."""
        self.metadata = {}
        
    def extract_from_heif(self, heif_path: str, image_obj: Optional[Any] = None) -> Dict:
        """
        Extract ISO 19115-4 metadata from a HEIF file.
        
        Args:
            heif_path: Path to HEIF file
            image_obj: Optional pillow-heif image object
            
        Returns:
            Dictionary containing ISO 19115-4 metadata
        """
        metadata = {
            "standard": "ISO 19115-4:2014",
            "metadataIdentifier": self._generate_metadata_id(heif_path),
            "acquisitionInformation": {},
            "quality": []
        }
        
        # Extract basic file information
        file_info = self._extract_file_info(heif_path)
        metadata["fileInformation"] = file_info
        
        # Extract image dimensions and properties
        if image_obj:
            img_props = self._extract_image_properties(image_obj)
            metadata["imageProperties"] = img_props
            
            # Add gridded data extent
            metadata["gridSpatialRepresentation"] = {
                "numberOfDimensions": 2,
                "axisDimensionProperties": [
                    {
                        "dimensionName": "column",
                        "dimensionSize": img_props["width"]
                    },
                    {
                        "dimensionName": "row",
                        "dimensionSize": img_props["height"]
                    }
                ],
                "cellGeometry": "area"
            }
        
        # Extract EXIF metadata for acquisition information
        if image_obj and hasattr(image_obj, 'info'):
            exif_data = image_obj.info.get('exif', {})
            acq_info = self._extract_acquisition_info(exif_data)
            if acq_info:
                metadata["acquisitionInformation"] = acq_info
        
        # Generate quality reports
        quality_reports = self._generate_quality_reports(heif_path, image_obj)
        metadata["quality"] = quality_reports
        
        return metadata
    
    def _generate_metadata_id(self, heif_path: str) -> str:
        """Generate unique metadata identifier."""
        basename = os.path.splitext(os.path.basename(heif_path))[0]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"iso19115-4-{basename}-{timestamp}"
    
    def _extract_file_info(self, heif_path: str) -> Dict:
        """Extract basic file information."""
        stat = os.stat(heif_path)
        return {
            "fileName": os.path.basename(heif_path),
            "filePath": heif_path,
            "fileSize": stat.st_size,
            "fileType": "image/heif",
            "created": datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
        }
    
    def _extract_image_properties(self, image_obj: Any) -> Dict:
        """Extract image properties from pillow-heif image object."""
        props = {
            "width": image_obj.size[0],
            "height": image_obj.size[1],
            "mode": image_obj.mode,
            "hasAlpha": "A" in image_obj.mode
        }
        
        # Extract bit depth
        if hasattr(image_obj, 'info'):
            info = image_obj.info
            if 'bit_depth' in info:
                props["bitDepth"] = info['bit_depth']
            if 'icc_profile' in info:
                props["hasICCProfile"] = True
        
        return props
    
    def _extract_acquisition_info(self, exif_data: Dict) -> Dict:
        """Extract acquisition information from EXIF data."""
        acq_info = {}
        
        # Platform information (camera/sensor)
        if exif_data:
            # Camera make and model
            make = exif_data.get('Make', exif_data.get(271))  # IFD tag 271
            model = exif_data.get('Model', exif_data.get(272))  # IFD tag 272
            
            if make or model:
                acq_info["platform"] = {
                    "identifier": f"{make} {model}".strip() if make and model else (make or model),
                    "description": "Image acquisition platform"
                }
            
            # Sensor information
            if model:
                acq_info["instrument"] = {
                    "identifier": model,
                    "type": "optical sensor",
                    "description": "Image sensor"
                }
            
            # Acquisition date/time
            datetime_original = exif_data.get('DateTimeOriginal', exif_data.get(36867))
            if datetime_original:
                acq_info["acquisitionDate"] = datetime_original
        
        return acq_info
    
    def _generate_quality_reports(self, heif_path: str, image_obj: Optional[Any]) -> List[Dict]:
        """
        Generate ISO 19115-4 imagery quality reports.
        
        Quality elements specific to ISO 19115-4:
        - radiometricAccuracy
        - sensorQuality
        - cloudCoverage
        - snowCoverage
        - processingLevel
        - usabilityAssessment
        """
        reports = []
        
        # Processing Level (from HEIF format - typically raw/unprocessed)
        reports.append({
            "type": "processingLevel",
            "level": "L0",  # Raw sensor data
            "description": "HEIF imagery - unprocessed sensor data",
            "processingDate": datetime.now(timezone.utc).isoformat(),
            "measure": {
                "description": "Image stored in HEIF format without radiometric or geometric correction",
                "value": "L0",
                "valueType": "string"
            }
        })
        
        # Sensor Quality (based on HEIF format capabilities)
        reports.append({
            "type": "sensorQuality",
            "sensorType": "Image Sensor (HEIF capable)",
            "calibrationStatus": "unknown",
            "measure": {
                "description": "Sensor quality assessment based on HEIF metadata",
                "value": None,
                "valueType": "string",
                "method": "Metadata analysis"
            }
        })
        
        # Usability Assessment
        usability_score = self._assess_usability(image_obj)
        limitations = []
        
        if not image_obj:
            limitations.append("Image object not available for analysis")
            usability_score = 0.5
        elif image_obj.size[0] < 640 or image_obj.size[1] < 640:
            limitations.append("Low resolution imagery (< 640px)")
            
        reports.append({
            "type": "usabilityAssessment",
            "usabilityScore": usability_score,
            "limitations": limitations,
            "intendedUse": "Geospatial imagery analysis with georeferencing",
            "measure": {
                "description": "Fitness for use in geospatial applications",
                "value": usability_score,
                "valueType": "Real",
                "units": "probability",
                "method": "Expert assessment based on image properties"
            }
        })
        
        # Cloud Coverage (default unknown for ground-based imagery)
        reports.append({
            "type": "cloudCoverage",
            "coveragePercentage": None,
            "assessmentMethod": "Not applicable for ground-based imagery",
            "measure": {
                "description": "Cloud coverage assessment",
                "value": None,
                "valueType": "Real",
                "units": "percent"
            }
        })
        
        return reports
    
    def _assess_usability(self, image_obj: Optional[Any]) -> float:
        """
        Assess image usability for geospatial applications.
        
        Returns:
            Usability score between 0 and 1
        """
        if not image_obj:
            return 0.5  # Unknown
        
        score = 1.0
        
        # Reduce score for low resolution
        width, height = image_obj.size
        if width < 640 or height < 640:
            score -= 0.3
        elif width < 1024 or height < 1024:
            score -= 0.1
        
        # Reduce score if no ICC profile (color management)
        if hasattr(image_obj, 'info'):
            if 'icc_profile' not in image_obj.info:
                score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def generate_xml_metadata(self, metadata: Dict) -> str:
        """
        Generate ISO 19115-4 XML metadata (simplified).
        
        Args:
            metadata: Metadata dictionary from extract_from_heif()
            
        Returns:
            XML string
        """
        # Simplified XML generation
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<gmi:MI_Metadata xmlns:gmi="http://standards.iso.org/iso/19115/-4/gmi/1.0"')
        xml_parts.append('                xmlns:gco="http://standards.iso.org/iso/19115/-3/gco/1.0"')
        xml_parts.append('                xmlns:mdb="http://standards.iso.org/iso/19115/-3/mdb/2.0">')
        
        # Metadata identifier
        xml_parts.append(f'  <gmi:metadataIdentifier>')
        xml_parts.append(f'    <gco:CharacterString>{metadata["metadataIdentifier"]}</gco:CharacterString>')
        xml_parts.append(f'  </gmi:metadataIdentifier>')
        
        # Quality information
        if metadata.get("quality"):
            xml_parts.append('  <gmi:dataQualityInfo>')
            for report in metadata["quality"]:
                xml_parts.append(f'    <!-- {report["type"]} -->')
                xml_parts.append(f'    <description>{report.get("description", "")}</description>')
            xml_parts.append('  </gmi:dataQualityInfo>')
        
        xml_parts.append('</gmi:MI_Metadata>')
        
        return '\n'.join(xml_parts)
    
    def to_json(self, metadata: Dict, indent: int = 2) -> str:
        """
        Convert metadata to JSON string.
        
        Args:
            metadata: Metadata dictionary
            indent: JSON indentation level
            
        Returns:
            JSON string
        """
        return json.dumps(metadata, indent=indent, default=str)
    
    def enrich_provenance(self, provenance: Dict, metadata: Dict) -> Dict:
        """
        Enrich existing provenance data with ISO 19115-4 metadata.
        
        Args:
            provenance: Existing provenance dictionary
            metadata: ISO 19115-4 metadata dictionary
            
        Returns:
            Enriched provenance dictionary
        """
        enriched = provenance.copy()
        
        # Add ISO 19115-4 metadata section
        enriched["iso19115_4"] = {
            "metadataStandard": "ISO 19115-4:2014",
            "metadataIdentifier": metadata["metadataIdentifier"],
            "metadataDate": datetime.now(timezone.utc).isoformat()
        }
        
        # Add quality reports
        if metadata.get("quality"):
            enriched["iso19115_4"]["quality"] = metadata["quality"]
        
        # Add acquisition information
        if metadata.get("acquisitionInformation"):
            enriched["iso19115_4"]["acquisitionInformation"] = metadata["acquisitionInformation"]
        
        # Add gridded data information
        if metadata.get("gridSpatialRepresentation"):
            enriched["iso19115_4"]["gridSpatialRepresentation"] = metadata["gridSpatialRepresentation"]
        
        return enriched


def extract_iso19115_4_metadata(heif_path: str, image_obj: Optional[Any] = None) -> Dict:
    """
    Convenience function to extract ISO 19115-4 metadata from HEIF file.
    
    Args:
        heif_path: Path to HEIF file
        image_obj: Optional pillow-heif image object
        
    Returns:
        ISO 19115-4 metadata dictionary
    """
    extractor = ISO19115_4MetadataExtractor()
    return extractor.extract_from_heif(heif_path, image_obj)
