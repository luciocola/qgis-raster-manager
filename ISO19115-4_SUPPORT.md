# ISO 19115-4 Imagery Metadata Support

This document describes the ISO 19115-4 metadata extraction and generation capabilities of the HEIF/TTL Importer plugin.

## Overview

**ISO 19115-4:2014** - "Geographic information - Metadata - Part 4: Imagery and gridded data" - is the international standard that extends ISO 19115 with imagery-specific metadata elements. This plugin automatically extracts and generates ISO 19115-4 compliant metadata for all processed HEIF imagery.

## Why ISO 19115-4?

ISO 19115-4 provides essential quality metadata for:

- **Remote Sensing**: Satellite and aerial imagery metadata
- **Defense Applications**: NATO DGIWG compliant imagery metadata
- **Emergency Response**: Standardized quality reporting for disaster response
- **Scientific Research**: Documented sensor characteristics and processing levels
- **Data Interoperability**: International standard for imagery exchange

## Metadata Elements Extracted

### 1. Processing Level

Documents the level of radiometric and geometric correction applied to the imagery.

**Levels:**
- `L0`: Raw sensor data (HEIF format default)
- `L1A`: Radiometrically corrected
- `L1B`: Geometrically corrected
- `L2A`: Orthorectified
- `L2B`: Atmospherically corrected

**Example:**
```json
{
  "type": "processingLevel",
  "level": "L0",
  "description": "HEIF imagery - unprocessed sensor data",
  "processingDate": "2026-01-28T14:30:00Z",
  "measure": {
    "description": "Image stored in HEIF format without radiometric or geometric correction",
    "value": "L0",
    "valueType": "string"
  }
}
```

### 2. Sensor Quality

Assessment of sensor calibration status and health.

**Calibration Status:**
- `calibrated`: Sensor fully calibrated
- `uncalibrated`: No calibration applied
- `partial`: Partial calibration
- `unknown`: Calibration status unknown

**Example:**
```json
{
  "type": "sensorQuality",
  "sensorType": "Image Sensor (HEIF capable)",
  "calibrationStatus": "unknown",
  "measure": {
    "description": "Sensor quality assessment based on HEIF metadata",
    "method": "Metadata analysis"
  }
}
```

### 3. Radiometric Accuracy

Quality of radiometric measurements in the imagery (when available from EXIF/metadata).

**Example:**
```json
{
  "type": "radiometricAccuracy",
  "calibrationAccuracy": 0.05,
  "units": "reflectance",
  "method": "Laboratory calibration certificate"
}
```

### 4. Cloud Coverage

Percentage of imagery obscured by clouds (typically N/A for ground-based HEIF).

**Example:**
```json
{
  "type": "cloudCoverage",
  "coveragePercentage": null,
  "assessmentMethod": "Not applicable for ground-based imagery"
}
```

### 5. Usability Assessment

Fitness for use in geospatial applications.

**Scoring Criteria:**
- Resolution: Higher scores for larger images (>1024px)
- Color Management: Presence of ICC profile
- Metadata Completeness: EXIF data availability

**Score Range:** 0.0 (unusable) to 1.0 (excellent)

**Example:**
```json
{
  "type": "usabilityAssessment",
  "usabilityScore": 0.9,
  "limitations": [],
  "intendedUse": "Geospatial imagery analysis with georeferencing",
  "measure": {
    "description": "Fitness for use in geospatial applications",
    "value": 0.9,
    "valueType": "Real",
    "units": "probability",
    "method": "Expert assessment based on image properties"
  }
}
```

### 6. Acquisition Information

Platform and sensor details extracted from EXIF metadata.

**Components:**
- **Platform**: Camera make/model
- **Instrument**: Sensor identifier
- **Acquisition Date**: Image capture datetime

**Example:**
```json
{
  "acquisitionInformation": {
    "platform": {
      "identifier": "Apple iPhone 12 Pro",
      "description": "Image acquisition platform"
    },
    "instrument": {
      "identifier": "iPhone 12 Pro",
      "type": "optical sensor",
      "description": "Image sensor"
    },
    "acquisitionDate": "2025:05:15 14:32:10"
  }
}
```

### 7. Gridded Data Representation

Spatial structure of the raster image.

**Example:**
```json
{
  "gridSpatialRepresentation": {
    "numberOfDimensions": 2,
    "axisDimensionProperties": [
      {
        "dimensionName": "column",
        "dimensionSize": 4032
      },
      {
        "dimensionName": "row",
        "dimensionSize": 3024
      }
    ],
    "cellGeometry": "area"
  }
}
```

## Complete Provenance Example

When you process a HEIF file, the plugin generates a `_provenance.json` file with full ISO 19115-4 metadata:

```json
{
  "original_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "derived_uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "algorithm_uuid": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "algorithm_name": "GCP Warping",
  "processing_timestamp": "2026-01-28T14:30:00.000000+00:00",
  "gcp_count": 12,
  "warp_enabled": true,
  "input_file": "imagery.heic",
  "input_hash": "1e202ec513944598549b41a52cb4cbd600c2ee56e8a8c48cdba08ed2fce8d30b8145",
  "input_hash_algorithm": "blake3",
  "output_file": "imagery_georef.tif",
  "output_hash": "1e20a7f3d8e9c2b4f6a1e5d8c7b9f2e4d6a8c5b3f1e9d7c2a4f6e8b1d3c5a7f9",
  "output_hash_algorithm": "blake3",
  
  "iso19115_4": {
    "metadataStandard": "ISO 19115-4:2014",
    "metadataIdentifier": "iso19115-4-imagery-20260128143000",
    "metadataDate": "2026-01-28T14:30:00.000000+00:00",
    
    "fileInformation": {
      "fileName": "imagery.heic",
      "filePath": "/path/to/imagery.heic",
      "fileSize": 4523891,
      "fileType": "image/heif",
      "created": "2025-05-15T10:15:30+00:00",
      "modified": "2025-05-15T10:15:30+00:00"
    },
    
    "imageProperties": {
      "width": 4032,
      "height": 3024,
      "mode": "RGB",
      "hasAlpha": false,
      "bitDepth": 24,
      "hasICCProfile": true
    },
    
    "quality": [
      {
        "type": "processingLevel",
        "level": "L0",
        "description": "HEIF imagery - unprocessed sensor data",
        "processingDate": "2026-01-28T14:30:00.000000+00:00",
        "measure": {
          "description": "Image stored in HEIF format without radiometric or geometric correction",
          "value": "L0",
          "valueType": "string"
        }
      },
      {
        "type": "sensorQuality",
        "sensorType": "Image Sensor (HEIF capable)",
        "calibrationStatus": "unknown",
        "measure": {
          "description": "Sensor quality assessment based on HEIF metadata",
          "value": null,
          "valueType": "string",
          "method": "Metadata analysis"
        }
      },
      {
        "type": "usabilityAssessment",
        "usabilityScore": 0.9,
        "limitations": [],
        "intendedUse": "Geospatial imagery analysis with georeferencing",
        "measure": {
          "description": "Fitness for use in geospatial applications",
          "value": 0.9,
          "valueType": "Real",
          "units": "probability",
          "method": "Expert assessment based on image properties"
        }
      },
      {
        "type": "cloudCoverage",
        "coveragePercentage": null,
        "assessmentMethod": "Not applicable for ground-based imagery",
        "measure": {
          "description": "Cloud coverage assessment",
          "value": null,
          "valueType": "Real",
          "units": "percent"
        }
      }
    ],
    
    "acquisitionInformation": {
      "platform": {
        "identifier": "Apple iPhone 12 Pro",
        "description": "Image acquisition platform"
      },
      "instrument": {
        "identifier": "iPhone 12 Pro",
        "type": "optical sensor",
        "description": "Image sensor"
      },
      "acquisitionDate": "2025:05:15 14:32:10"
    },
    
    "gridSpatialRepresentation": {
      "numberOfDimensions": 2,
      "axisDimensionProperties": [
        {"dimensionName": "column", "dimensionSize": 4032},
        {"dimensionName": "row", "dimensionSize": 3024}
      ],
      "cellGeometry": "area"
    }
  }
}
```

## Standards Compatibility

### ISO 19115-1:2014
Core metadata standard - all ISO 19115-4 elements are compatible with and extend ISO 19115-1.

### ISO 19157-1:2023
Data quality measures - ISO 19115-4 quality elements map to ISO 19157-1:
- `radiometricAccuracy` → `thematicQuality.thematicClassificationCorrectness`
- `sensorQuality` → `metaquality.confidence`
- `processingLevel` → `lineage.processStep`
- `usabilityAssessment` → `usability`

See [ISO19115-4 vs ISO19157-3 Compatibility](https://github.com/stac-extensions/liability-claims/blob/main/ISO19115-4-vs-ISO19157-3-COMPATIBILITY.md) for detailed mapping.

### STAC Extensions
The ISO 19115-4 metadata is compatible with:
- **STAC Liability & Claims Extension**: Maps quality reports to STAC items
- **STAC Processing Extension**: Documents processing levels
- **STAC Sentinel Extension**: Compatible with satellite imagery metadata

### NATO DGIWG
Defence Geospatial Information Working Group standards recognize ISO 19115-4 for defense imagery applications.

## Usage in Python

You can use the metadata extractor independently:

```python
from iso19115_4_metadata import ISO19115_4MetadataExtractor
from PIL import Image

# Initialize extractor
extractor = ISO19115_4MetadataExtractor()

# Extract metadata
metadata = extractor.extract_from_heif(
    heif_path="/path/to/image.heic",
    image_obj=Image.open("/path/to/image.heic")
)

# Get JSON
json_output = extractor.to_json(metadata, indent=2)
print(json_output)

# Get XML (simplified)
xml_output = extractor.generate_xml_metadata(metadata)
print(xml_output)

# Enrich existing provenance
provenance = {"original_uuid": "...", "derived_uuid": "..."}
enriched = extractor.enrich_provenance(provenance, metadata)
```

## XML Output

The plugin can generate simplified ISO 19115-4 XML metadata:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<gmi:MI_Metadata xmlns:gmi="http://standards.iso.org/iso/19115/-4/gmi/1.0"
                xmlns:gco="http://standards.iso.org/iso/19115/-3/gco/1.0"
                xmlns:mdb="http://standards.iso.org/iso/19115/-3/mdb/2.0">
  <gmi:metadataIdentifier>
    <gco:CharacterString>iso19115-4-imagery-20260128143000</gco:CharacterString>
  </gmi:metadataIdentifier>
  <gmi:dataQualityInfo>
    <!-- processingLevel -->
    <description>HEIF imagery - unprocessed sensor data</description>
    <!-- sensorQuality -->
    <description>Sensor quality assessment based on HEIF metadata</description>
    <!-- usabilityAssessment -->
    <description>Fitness for use in geospatial applications</description>
  </gmi:dataQualityInfo>
</gmi:MI_Metadata>
```

## References

- [ISO 19115-4:2014](https://www.iso.org/standard/39229.html) - Official standard
- [ISO 19115-1:2014](https://www.iso.org/standard/53798.html) - Core metadata standard
- [ISO 19157-1:2023](https://www.iso.org/standard/78900.html) - Data quality measures
- [ISO TC 211](https://www.isotc211.org/) - Geographic information standards
- [STAC Liability & Claims Extension](https://github.com/stac-extensions/liability-claims)
- [NATO DGIWG](https://www.dgiwg.org/) - Defence geospatial standards

## Future Enhancements

Planned improvements:

1. **Enhanced EXIF Parsing**: Extract more sensor parameters
2. **Radiometric Calibration**: Support for external calibration files
3. **Cloud Detection**: Automatic cloud coverage analysis
4. **Processing Chains**: Track multi-step processing lineage
5. **XML Validation**: Full schema validation against ISO 19115-4 XSD
6. **INSPIRE Compliance**: European INSPIRE directive metadata support

---

**Version**: 1.0  
**Date**: 2026-01-28  
**Author**: 4113Eng-wfs
