# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ido_annotator.py — Imagery Domain Ontology (IDO) integration for the
GIMI Imagery Workbench plugin.

Exposes processed raster outputs as IDO MediaObject individuals and attaches
an AnnotationLiabilityRecord drawn from the plugin's provenance dictionary.

IDO namespace:  http://ogc.secd.eu/ontology/imagery-domain#
IDO version:    1.1.0
Schema:         imagery_domain_ontology.ttl (companion repo)

The three public entry-points are:

    IDOAnnotator.build_media_object_ttl(prov, raster_path)
        → Turtle/TTL string to append to *_provenance.ttl sidecar.

    IDOAnnotator.build_stac_ido_properties(prov)
        → dict of IDO-specific STAC Item property values (ido: prefix).

    IDOAnnotator.estimate_niirs(gsd_metres)
        → float NIIRS estimate using a simplified GIQE approximation.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, Optional


# ── IDO namespace ─────────────────────────────────────────────────────────────
IDO_NS   = "http://ogc.secd.eu/ontology/imagery-domain#"
IDO_SCHEMA_URI = (
    "https://luciocola.github.io/"
    "stac-extension-liability-claims/v1.6.0/schema.json"
)

# Turtle prefix block shared by both TTL helpers
_TTL_PREFIXES = """\
@prefix :      <{ido}> .
@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix dct:   <http://purl.org/dc/terms/> .
@prefix prov:  <http://www.w3.org/ns/prov#> .
@prefix sosa:  <http://www.w3.org/ns/sosa/> .
@prefix time:  <http://www.w3.org/2006/time#> .
@prefix geo:   <http://www.opengis.net/ont/geosparql#> .
@prefix qudt:  <http://qudt.org/schema/qudt/> .
@prefix unit:  <http://qudt.org/vocab/unit/> .
""".format(ido=IDO_NS)


class IDOAnnotator:
    """
    Generates IDO-conformant RDF triples and STAC properties for a processed
    raster sidecar produced by the GIMI Imagery Workbench.

    Instantiate once per conversion run:

        anno = IDOAnnotator(responsible_party="4113 Engineering Pty Ltd")
        ttl_snippet  = anno.build_media_object_ttl(prov, output_path)
        stac_props   = anno.build_stac_ido_properties(prov)
    """

    IDO_EXTENSION_URI = (
        "https://stac-extensions.github.io/ido/v1.0.0/schema.json"
    )
    IDO_ONTOLOGY_URI  = "http://ogc.secd.eu/ontology/imagery-domain"

    def __init__(
        self,
        responsible_party: str = "4113 Engineering",
        legal_jurisdiction: str = "",
        ownership_did: str = "",
        data_classification: str = "unclassified",
        retention_days: int = 3650,
    ):
        self.responsible_party   = responsible_party
        self.legal_jurisdiction  = legal_jurisdiction
        self.ownership_did       = ownership_did
        self.data_classification = data_classification
        self.retention_days      = retention_days

    # ── Public API ────────────────────────────────────────────────────────────

    def build_media_object_ttl(
        self,
        prov: Dict[str, Any],
        raster_path: str,
    ) -> str:
        """
        Return a Turtle/TTL string (including prefix declarations) that
        represents the processed raster as an IDO MediaObject together with:

          - an AnnotationLiabilityRecord capturing quality, NIIRS and
            sovereignty constraints
          - links to W3C PROV entities already present in the sidecar TTL

        Intended to be appended verbatim to the ``*_provenance.ttl`` sidecar
        produced by ``heif_processor.generate_rdf_provenance()``.
        """
        derived_uri = f"urn:uuid:{prov.get('derived_uuid', 'unknown')}"
        original_uri = f"urn:uuid:{prov.get('original_uuid', 'unknown')}"
        lr_uri = f"urn:uuid:{prov.get('derived_uuid', 'unknown')}-ido-lr"
        dq_uri = f"urn:uuid:{prov.get('derived_uuid', 'unknown')}-ido-dq"
        niirs_uri = f"urn:uuid:{prov.get('derived_uuid', 'unknown')}-ido-niirs"
        policy_uri = f"urn:uuid:{prov.get('derived_uuid', 'unknown')}-ido-policy"
        sov_uri = f"urn:uuid:{prov.get('derived_uuid', 'unknown')}-ido-sov"

        gsd = self._gsd_from_prov(prov, raster_path)
        niirs_val = self.estimate_niirs(gsd) if gsd else None
        ts = prov.get("processing_timestamp", "")
        output_file = prov.get("output_file", os.path.basename(raster_path))

        lines: list[str] = [
            "###############################################################",
            "##  IDO — Imagery Domain Ontology  (ido_annotator.py  v1.1.0)",
            "##  Ontology: <http://ogc.secd.eu/ontology/imagery-domain>",
            "###############################################################",
            "",
            _TTL_PREFIXES,
        ]

        # ── MediaObject ───────────────────────────────────────────────────────
        lines += [
            f"### Processed raster as IDO MediaObject",
            f"<{derived_uri}>",
            f"    a :MediaObject, prov:Entity ;",
            f"    rdfs:label \"{output_file}\"@en ;",
        ]
        if gsd:
            lines.append(f"    :hasSpatialResolution \"{gsd:.4f}\"^^xsd:decimal ;")
            lines.append(f"    qudt:unit unit:M ;")
        if ts:
            lines += [
                f"    :hasAcquisitionTime [",
                f"        rdf:type time:Instant ;",
                f"        time:inXSDDateTimeStamp \"{ts}\"^^xsd:dateTimeStamp",
                f"    ] ;",
            ]
        # Link to the source file as the parent PROV entity
        lines.append(f"    prov:wasDerivedFrom <{original_uri}> ;")
        lines.append(f"    :hasLiabilityRecord <{lr_uri}> ;")
        lines.append(f"    .")
        lines.append("")

        # ── AnnotationLiabilityRecord ─────────────────────────────────────────
        lines += [
            f"### AnnotationLiabilityRecord — quality, NIIRS, usage policy, sovereignty",
            f"<{lr_uri}>",
            f"    a :AnnotationLiabilityRecord ;",
            f"    rdfs:label \"Liability record for {output_file}\"@en ;",
            f"    :hasResponsibleParty \"{self.responsible_party}\" ;",
            f"    :hasAnnotationOrigin \"{self.responsible_party}\" ;",
        ]
        if self.ownership_did:
            lines.append(f"    :hasOwnershipDID \"{self.ownership_did}\"^^xsd:anyURI ;")
        if self.legal_jurisdiction:
            lines.append(f"    :hasLegalJurisdiction \"{self.legal_jurisdiction}\" ;")
        lines.append(f"    :hasAnnotationQuality <{dq_uri}> ;")
        if niirs_val is not None:
            lines.append(f"    :hasNIIRSRating <{niirs_uri}> ;")
        lines.append(f"    :hasUsagePolicy <{policy_uri}> ;")
        lines.append(f"    :hasSovereigntyConstraint <{sov_uri}> ;")
        lines.append(f"    .")
        lines.append("")

        # ── DQ report (ISO 19157 thematic lineage) ────────────────────────────
        dq_type = "DQ_Completeness_Commission"
        dq_measure = "processing completeness"
        dq_result = "100"
        # Use quality data from ISO 19115-4 if available
        iso_quality = prov.get("iso19115_4", {}).get("quality", [])
        for qr in iso_quality:
            if qr.get("type") == "processingLevel":
                dq_type = "DQ_CompletenessOmission"
                dq_measure = "processing level"
                dq_result = str(qr.get("level", "L1"))
                break

        lines += [
            f"<{dq_uri}>",
            f"    a :AnnotationQualityReport ;",
            f"    rdfs:label \"Quality report — {output_file}\"@en ;",
            f"    :dqElementType \"{dq_type}\" ;",
            f"    :dqMeasureName \"{dq_measure}\" ;",
            f"    :dqResult \"{dq_result}\"^^xsd:string ;",
            f"    :dqEvaluationMethod \"automated_plugin_processing\" ;",
            f"    .",
            "",
        ]

        # Also embed ISO 19157 cloud cover if present
        for qr in iso_quality:
            if qr.get("type") == "cloudCoverage":
                pct = qr.get("coveragePercentage")
                if pct is not None:
                    lines += [
                        f"<{dq_uri}>",
                        f"    :dqElementType \"DQ_ThematicClassificationCorrectness\" ;",
                        f"    :dqMeasureName \"cloud coverage percentage\" ;",
                        f"    :dqResult \"{pct}\"^^xsd:decimal ;",
                        f"    :dqResultUnit \"percent\" ;",
                        f"    .",
                        "",
                    ]
                break

        # ── NIIRS ─────────────────────────────────────────────────────────────
        if niirs_val is not None:
            lines += [
                f"<{niirs_uri}>",
                f"    a :NIIRSRating ;",
                f"    rdfs:label \"NIIRS estimate for {output_file}\"@en ;",
                f"    :niirs_overall \"{niirs_val:.1f}\"^^xsd:decimal ;",
                f"    rdfs:comment \"GSD-based GIQE approximation; GSD={gsd:.4f} m/px\" ;",
                f"    .",
                "",
            ]

        # ── Usage policy ──────────────────────────────────────────────────────
        lines += [
            f"<{policy_uri}>",
            f"    a :UsagePolicy ;",
            f"    rdfs:label \"Default usage policy for {output_file}\"@en ;",
            f"    :policyType \"Offer\" ;",
            f"    :policyAssigner \"{self.ownership_did or self.responsible_party}\"^^xsd:string ;",
            f"    :policyPermittedActions \"[\\\"use\\\",\\\"reproduce\\\"]\" ;",
            f"    :policyProhibitedActions \"[\\\"commercialize\\\",\\\"sublicense\\\"]\" ;",
            f"    .",
            "",
        ]

        # ── Sovereignty ───────────────────────────────────────────────────────
        lines += [
            f"<{sov_uri}>",
            f"    a :SovereigntyConstraint ;",
            f"    rdfs:label \"Sovereignty constraints for {output_file}\"@en ;",
            f"    :retentionDays \"{self.retention_days}\"^^xsd:integer ;",
            f"    :redistributionAllowed \"false\"^^xsd:boolean ;",
            f"    :dataClassification \"{self.data_classification}\" ;",
            f"    .",
            "",
        ]

        return "\n".join(lines)

    def build_stac_ido_properties(
        self, prov: Dict[str, Any], raster_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Return a dict of IDO-related key/value pairs to be merged into the
        STAC Item ``properties`` dict.

        All keys use the ``ido:`` prefix (namespace aliased here to the full URI).
        The caller must add the IDO extension schema URI to ``stac_extensions``.
        """
        props: Dict[str, Any] = {
            "ido:ontology_uri": self.IDO_ONTOLOGY_URI,
            "ido:media_object_uri": f"urn:uuid:{prov.get('derived_uuid', '')}",
            "ido:responsible_party": self.responsible_party,
            "ido:annotation_method": prov.get("algorithm_name", ""),
            "ido:data_classification": self.data_classification,
        }

        if self.ownership_did:
            props["ido:ownership_did"] = self.ownership_did
        if self.legal_jurisdiction:
            props["ido:legal_jurisdiction"] = self.legal_jurisdiction

        # NIIRS from GSD if grid info is available
        gsd = self._gsd_from_prov(prov, raster_path)
        if gsd:
            niirs = self.estimate_niirs(gsd)
            props["ido:niirs_estimated"] = round(niirs, 1)
            props["ido:gsd_metres"] = round(gsd, 4)

        # ISO 19115-4 quality passthrough
        iso_quality = prov.get("iso19115_4", {}).get("quality", [])
        for qr in iso_quality:
            if qr.get("type") == "cloudCoverage":
                props["ido:cloud_cover_pct"] = qr.get("coveragePercentage")
            if qr.get("type") == "processingLevel":
                props["ido:processing_level"] = qr.get("level")

        return {k: v for k, v in props.items() if v not in (None, "", [])}

    @staticmethod
    def estimate_niirs(gsd_metres: float) -> float:
        """
        Return a simplified GIQE-based NIIRS estimate from ground sampling
        distance (GSD) in metres/pixel.

        Formula (visible imagery, no SNR factor):
            NIIRS ≈ 10.251 – 3.32 * log10(GSD_inches)
        where GSD_inches = gsd_metres * 39.3701.

        Clamped to [0.5, 9.0].
        """
        if gsd_metres <= 0:
            return 0.5
        gsd_inches = gsd_metres * 39.3701
        niirs = 10.251 - 3.32 * math.log10(gsd_inches)
        return max(0.5, min(9.0, round(niirs, 1)))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _gsd_from_prov(
        self, prov: Dict[str, Any], raster_path: Optional[str]
    ) -> Optional[float]:
        """
        Extract or estimate the GSD (metres/pixel) from the provenance dict.

        Priority order:
          1. ``prov["iso19115_4"]["imageProperties"]["resolution_metres"]``
          2. GDAL GeoTransform of *raster_path* (pixel size from GT[1])
          3. ``prov["iso19115_4"]["gridSpatialRepresentation"]`` — not a GSD;
             skipped.
        """
        # 1. Explicit resolution from ISO 19115-4 extraction
        res = (
            prov.get("iso19115_4", {})
                .get("imageProperties", {})
                .get("resolution_metres")
        )
        if res and float(res) > 0:
            return float(res)

        # 2. Derive from GDAL GeoTransform
        if raster_path and os.path.exists(raster_path):
            try:
                from osgeo import gdal
                ds = gdal.Open(raster_path, gdal.GA_ReadOnly)
                if ds:
                    gt = ds.GetGeoTransform()
                    ds = None
                    if gt and gt[1] > 0:
                        return abs(gt[1])  # x-pixel size (approximate for projected CRS)
            except Exception:
                pass

        return None
