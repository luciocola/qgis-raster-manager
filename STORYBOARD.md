# GIMI Imagery Workbench — Storyboard

**Plugin version:** 2.0.0  
**Author:** 4113 Engineering  
**QGIS minimum:** 3.0  
**Date:** 30 April 2026

---

## Overview

This storyboard describes the end-to-end user experience of the **GIMI Imagery Workbench** plugin.  
Each scene corresponds to one screen state or interaction moment in the plugin dialog.

---

## Scene 01 — Launch

| | |
|---|---|
| **Trigger** | User clicks the *GIMI Imagery Workbench* toolbar button or selects **Raster → GIMI Imagery Workbench** from the menu |
| **Screen state** | Main plugin dialog opens. All tabs visible: **Import**, **Export**, **STAC / Provenance**, **IDO Annotation**, **Query STAC** |
| **User goal** | Load a raster (any GDAL-readable format) and optionally georeference it |
| **Key UI elements** | File picker (Input Raster), Output format dropdown, Export path, tabs for metadata and annotation |

```
┌────────────────────────────────────────────────────────────────┐
│  GIMI Imagery Workbench  v2.1.0            [?] [×]             │
├────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │  Import  │ │  Export  │ │ STAC/Prov.   │ │ IDO Annot.   │ │
│  └──────────┘ └──────────┘ └──────────────┘ └──────────────┘ │
│                                                                │
│  Input raster: [                              ] [Browse...]   │
│  Input TTL/RDF: [                             ] [Browse...]   │
│  Output path:  [                              ] [Browse...]   │
│  Output format: [ GeoTIFF (GTiff)        ▼ ]                  │
│                                                                │
│                          [Import & Georeference]              │
└────────────────────────────────────────────────────────────────┘
```

---

## Scene 02 — Input Raster Selection

| | |
|---|---|
| **Trigger** | User clicks **Browse…** next to *Input raster* |
| **Screen state** | OS file picker opens, filter shows all GDAL-readable formats (HEIF, GeoTIFF, JP2, ECW, PNG, JPEG, NITF, HDF5, NetCDF, Zarr, ENVI, HFA, VRT, GeoPackage, MrSID …) |
| **Happy path** | User selects `flight_area.tif`; path populates the field |
| **Edge case** | File is a HEIF — plugin auto-detects it and enables the *Show HEIF Structure* button |
| **Edge case** | File is already georeferenced GeoTIFF — TTL/RDF field becomes optional, warp step is skipped |

---

## Scene 03 — TTL / RDF Metadata (Optional)

| | |
|---|---|
| **Trigger** | User clicks **Browse…** next to *Input TTL/RDF* |
| **Screen state** | OS file picker opens, filter: `*.ttl *.rdf *.n3 *.turtle` |
| **Happy path** | User selects `flight_area_gcps.ttl`; plugin parses it and shows GCP count in status bar: `✓ 12 GCPs loaded from TTL` |
| **Alternative** | HEIF file contains embedded RDF (TB21 GIMI format) — plugin auto-detects and pre-fills the GCP list without needing an external TTL |
| **Edge case** | Malformed TTL — error shown inline: `⚠ Could not parse TTL: unexpected token at line 7` |

---

## Scene 04 — Output Format Selection

| | |
|---|---|
| **Trigger** | User clicks the **Output format** dropdown |
| **Screen state** | Dropdown expands showing all supported formats grouped by type |
| **Formats available** | GeoTIFF (default), COG, JPEG2000/JP2, PNG, JPEG, HFA/Erdas, ECW, NITF, GeoPackage Raster, ENVI, VRT, NetCDF, HDF5, Zarr, MrSID, TB21 GIMI HEIF |
| **User action** | Selects *JPEG2000 (JP2OpenJPEG)* |
| **Side effect** | Output path field auto-updates extension from `.tif` to `.jp2`; a note appears: `ℹ JPEG2000 exports include native CRS embedding` |

---

## Scene 05 — Warping / Orthorectification Options

| | |
|---|---|
| **Trigger** | User expands the *Georeferencing Options* collapsible group |
| **Screen state** | Three options visible |
| **Option A** | *GCP Assignment only* — embeds GCPs in header, no pixel warp |
| **Option B** | *GCP Warp* (default) — full pixel-level warp to WGS-84 |
| **Option C** | *Orthorectification* — polynomial order 1/2/3 or TPS; enables *Polynomial Order* spinner |
| **Resampling** | Combo: Nearest / Bilinear / **Cubic** (default) / Lanczos |
| **User action** | Leaves default *GCP Warp, Cubic* |

---

## Scene 06 — Import & Georeference Execution

| | |
|---|---|
| **Trigger** | User clicks **Import & Georeference** |
| **Screen state** | Progress bar appears; log panel streams step-by-step output |

```
Processing log
──────────────────────────────────────────────────────
Step 1: Converting flight_area.heic to TIFF ...      ✓
Step 2: Adding 12 GCPs to TIFF ...                   ✓
Step 3: Warping to final output (cubic) ...           ✓
✓ GDAL statistics written to flight_area.tif.aux.xml
Extracting ISO 19115-4 imagery metadata ...          ✓
✓ ISO 19115-4 metadata added to provenance
Input  hash (blake3): a3f7c8...
Output hash (blake3): 9d2b01...
Provenance saved to: flight_area_provenance.json
✓ IDO MediaObject + AnnotationLiabilityRecord appended to TTL
──────────────────────────────────────────────────────
✅  Done — flight_area.tif added to QGIS layers
```

| **On completion** | Output raster is auto-loaded as a QGIS raster layer; layer name = `flight_area` |
| **On error** | Red banner: `✗ Import failed: <reason>` — log retained for inspection |

---

## Scene 07 — STAC / Provenance Tab

| | |
|---|---|
| **Trigger** | User clicks the **STAC / Provenance** tab |
| **Screen state** | Panel shows two sub-sections: *Provenance Summary* and *Export to STAC* |

### 07-A  Provenance Summary

| Field | Value (example) |
|---|---|
| Original UUID | `a1b2c3d4-…` |
| Derived UUID | `e5f6a7b8-…` |
| Algorithm | GCP Warping |
| Input hash (BLAKE3) | `a3f7c8…` |
| Output hash (BLAKE3) | `9d2b01…` |
| Processing timestamp | `2026-04-30T09:14:23Z` |
| GCP count | 12 |
| ISO 19115-4 | Cloud cover 2 %, Processing level L1A |

### 07-B  Export to STAC

```
STAC output dir: [                              ] [Browse...]
                 [  Export STAC Item  ]
```

- Writes `<derived_uuid>.json` (STAC 1.0 Item) to chosen directory
- Extensions declared: `checksum`, `processing`, `eo`, **`ido`** (Imagery Domain Ontology v1.1.0)
- `ido:niirs_estimated`, `ido:gsd_metres`, `ido:responsible_party`, `ido:data_classification` are populated automatically from provenance

---

## Scene 08 — IDO Annotation Tab

| | |
|---|---|
| **Trigger** | User clicks the **IDO Annotation** tab |
| **Purpose** | Supply Imagery Domain Ontology governance metadata: responsible party, quality, NIIRS, usage policy, sovereignty |

```
┌──────────────────────────────────────────────────────────────┐
│  IDO Annotation (Imagery Domain Ontology v1.1.0)            │
├──────────────────────────────────────────────────────────────┤
│  Responsible party:  [4113 Engineering          ]            │
│  Legal jurisdiction: [Australia                 ]            │
│  Ownership DID:      [did:web:4113eng.com.au     ]           │
│  Data classification:[ Unclassified        ▼ ]              │
│  Retention (days):   [ 3650 ↑↓ ]                            │
├──────────────────────────────────────────────────────────────┤
│  NIIRS estimate (auto from GSD):  [ 5.8 ]  (read-only)      │
│  GSD (m/px):                      [ 0.25 ] (auto from GDAL) │
├──────────────────────────────────────────────────────────────┤
│  Annotation method:  [ Manual photo interpretation ▼ ]       │
│  Feature class (MGCP): [ AA010 — Extraction Mine      ▼ ]   │
│  Confidence:         [ 0.92 ↑↓ ]                            │
└──────────────────────────────────────────────────────────────┘
```

| | |
|---|---|
| **Auto fields** | NIIRS and GSD are estimated automatically from the raster's GDAL GeoTransform |
| **Saved to** | `prov["ido_annotation"]` dict → written into `_provenance.json` and appended as OWL individuals in `_provenance.ttl` |

---

## Scene 09 — Query STAC Tab

| | |
|---|---|
| **Trigger** | User clicks the **Query STAC** tab |
| **Purpose** | Search an external STAC catalogue for related imagery |

```
┌──────────────────────────────────────────────────────────────┐
│  Query STAC                                                  │
├──────────────────────────────────────────────────────────────┤
│  STAC service: [ Element 84 Earth Search ▼ ]                 │
│  Bounding box: [ use current map extent ]  [Set from Layer]  │
│  Date range:   [ 2025-01-01 ] to [ 2026-04-30 ]             │
│  Collections:  [ sentinel-2-l2a          ]                   │
│                                  [Search] [Clear]            │
├──────────────────────────────────────────────────────────────┤
│  Results (0 of 0)                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  No results yet — run a search                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                          [Load Selected]     │
└──────────────────────────────────────────────────────────────┘
```

---

## Scene 10 — Export to TB21 GIMI HEIF

| | |
|---|---|
| **Trigger** | User selects **Output format → TB21 GIMI HEIF** on the Import tab, then runs Export |
| **Pre-condition** | `heif-enc` CLI tool is on `$PATH`; if not, plugin falls back to external TTL |
| **Process** | 1. Extract GCPs from GeoTIFF GeoTransform → 2. Generate TB21 GIMI Turtle RDF → 3. Call `heif-enc` with SAI flag to embed RDF |
| **Outputs** | `flight_area_gimi.heif` + `flight_area_gimi_provenance.ttl` |
| **Log** | `✓ TB21 GIMI HEIF written (embedded RDF, 12 GCPs)` |

---

## Scene 11 — HEIF Structure Viewer

| | |
|---|---|
| **Trigger** | User clicks **Show HEIF Structure** (visible when input is HEIF/HEIC) |
| **Screen state** | Expandable tree view showing ISOBMFF boxes |
| **Info shown** | Format, brand, image dimensions, thumbnails, EXIF/XMP/ICC profiles, HDR metadata, embedded RDF/Turtle (TB21 GIMI), SAI content IDs and TAI timestamps |

---

## Scene 12 — BLAKE3 Integrity Verification

| | |
|---|---|
| **Trigger** | User clicks **Verify Hashes** in the Provenance Summary |
| **Process** | Plugin re-computes BLAKE3 hash of input and output files on disk, compares against stored values |
| **Pass** | `✓ Input hash matches — file unmodified`, `✓ Output hash matches` |
| **Fail** | `✗ Output hash mismatch — file may have been altered after processing` |

---

## Scene 13 — Closing & Cleanup

| | |
|---|---|
| **Trigger** | User clicks ✕ or **Close** |
| **Behaviour** | Dialog closes; temp files cleaned; toolbar button remains available |
| **Persist** | Last-used paths remembered in QSettings for next session |

---

## Data Flow Summary

```
User Input
   │
   ├─ Raster file (HEIF / GeoTIFF / JP2 / any GDAL)
   └─ TTL/RDF GCPs (external or embedded)
         │
         ▼
   HEIFProcessor.process_heif_with_ttl()
         │
         ├─ convert_any_to_tiff()          → temp TIFF
         ├─ create_georeferenced_tiff()     → TIFF + GCPs
         ├─ warp_with_gcps()               → output raster
         ├─ ISO19115_4MetadataExtractor     → iso19115_4 dict
         ├─ generate_rdf_provenance()       → _provenance.ttl
         │       └─ IDOAnnotator            → IDO triples appended
         └─ _provenance.json               → provenance sidecar
               │
               ▼
   ProvenanceToSTACConverter.convert()
         │
         ├─ GDAL bbox extraction
         ├─ IDOAnnotator.build_stac_ido_properties()
         └─ STAC Item JSON (checksum + processing + eo + ido)
```

---

## Output Artefacts

| File | Format | Contents |
|---|---|---|
| `<name>.(tif\|jp2\|…)` | Raster | Georeferenced output in chosen GDAL format |
| `<name>_provenance.json` | JSON | Full processing provenance (UUIDs, hashes, ISO 19115-4, IDO fields) |
| `<name>_provenance.ttl` | Turtle/RDF | PROV-O lineage + IDO `MediaObject` + `AnnotationLiabilityRecord` |
| `<name>.(tif\|jp2).aux.xml` | GDAL XML | Per-band statistics |
| `<derived_uuid>.json` | STAC 1.0 Item | Machine-readable catalogue item with IDO extension |
| `<name>_osm_context.geojson` | GeoJSON | Optional OSM context features (roads, buildings, land use) |
