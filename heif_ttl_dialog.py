# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Dialog for General Raster Importer
"""
import os
from pathlib import Path
from PyQt5 import uic
from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt, QSettings, QTimer

from .ttl_parser import TTLParser

# Load UI file
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'heif_ttl_dialog_base.ui'))

# ── GDAL output-format registry ──────────────────────────────────────
# Maps the combo-box label to (gdal_driver_name, file_extension, default_creation_options)
GDAL_OUTPUT_FORMATS = {
    "GeoTIFF (.tif)":                 ("GTiff",       ".tif",  "COMPRESS=DEFLATE TILED=YES"),
    "Cloud-Optimised GeoTIFF (.tif)": ("COG",         ".tif",  "COMPRESS=DEFLATE OVERVIEW_RESAMPLING=NEAREST"),
    "JPEG2000 – OpenJPEG (.jp2)":     ("JP2OpenJPEG", ".jp2",  ""),
    "PNG (.png)":                      ("PNG",         ".png",  ""),
    "JPEG (.jpg)":                     ("JPEG",        ".jpg",  "QUALITY=95"),
    "HFA / ERDAS Imagine (.img)":     ("HFA",         ".img",  ""),
    "ECW (.ecw)":                      ("ECW",         ".ecw",  "TARGET=10"),
    "NITF (.ntf)":                     ("NITF",        ".ntf",  ""),
    "GeoPackage Raster (.gpkg)":      ("GPKG",        ".gpkg", ""),
    "ENVI (.img / .hdr)":             ("ENVI",        ".img",  ""),
    "VRT (.vrt)":                      ("VRT",         ".vrt",  ""),
    "NetCDF (.nc)":                    ("netCDF",      ".nc",   ""),
    "HDF5 (.h5)":                      ("HDF5",        ".h5",   ""),
    "Zarr (.zarr)":                    ("Zarr",        ".zarr", ""),
    "MrSID (.sid)":                    ("MrSID",       ".sid",  ""),
}

# ── Known public STAC service endpoints ──────────────────────────────
STAC_SERVICES = {
    "Element84 Earth Search v1":        "https://earth-search.aws.element84.com/v1",
    "Microsoft Planetary Computer":      "https://planetarycomputer.microsoft.com/api/stac/v1",
    "Copernicus Data Space Ecosystem":   "https://catalogue.dataspace.copernicus.eu/stac",
    "USGS LandsatLook":                  "https://landsatlook.usgs.gov/stac-server",
    "NASA CMR – LPCLOUD":               "https://cmr.earthdata.nasa.gov/stac/LPCLOUD",
    "AWS Open Data STAC":               "https://stacindex.org/api/stacs",  # meta-index
    "Custom…":                           "",
}


# ── STAC Query sub-dialog ─────────────────────────────────────────────

class STACQueryDialog(QDialog):
    """Standalone dialog for querying any STAC API service."""

    def __init__(self, parent=None, initial_bbox=None):
        super().__init__(parent)
        self.setWindowTitle('STAC Query')
        self.setMinimumWidth(760)
        self.setMinimumHeight(560)
        self.resize(820, 660)
        self._results = []
        self._build_ui(initial_bbox or (-180.0, -90.0, 180.0, 90.0))

    # ----------------------------------------------------------------
    def _build_ui(self, bbox):
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox,
            QDateEdit, QPushButton, QTableWidget, QTableWidgetItem,
            QHeaderView, QLabel, QSizePolicy,
        )
        from PyQt5.QtCore import QDate

        main = QVBoxLayout(self)

        # ── Service selector ──────────────────────────────────────────
        svc_group = QGroupBox('STAC Service')
        svc_row = QHBoxLayout(svc_group)
        svc_row.addWidget(QLabel('Service:'))
        self.cmbService = QComboBox()
        for name in STAC_SERVICES:
            self.cmbService.addItem(name)
        self.cmbService.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        svc_row.addWidget(self.cmbService)
        self.txtCustomURL = QLineEdit()
        self.txtCustomURL.setPlaceholderText('https://your-stac-api.example.com/v1')
        self.txtCustomURL.setVisible(False)
        svc_row.addWidget(self.txtCustomURL)
        self.cmbService.currentTextChanged.connect(self._on_service_changed)
        main.addWidget(svc_group)

        # ── Query parameters ──────────────────────────────────────────
        qp_group = QGroupBox('Query Parameters')
        qp_grid = QGridLayout(qp_group)

        qp_grid.addWidget(QLabel('Collections\n(comma-sep):'), 0, 0)
        self.txtCollections = QLineEdit()
        self.txtCollections.setPlaceholderText(
            'e.g. sentinel-2-l2a, landsat-c2-l2  (leave blank for all)')
        qp_grid.addWidget(self.txtCollections, 0, 1, 1, 5)

        qp_grid.addWidget(QLabel('Date from:'), 1, 0)
        self.dtFrom = QDateEdit(QDate.currentDate().addYears(-1))
        self.dtFrom.setDisplayFormat('yyyy-MM-dd')
        self.dtFrom.setCalendarPopup(True)
        qp_grid.addWidget(self.dtFrom, 1, 1)

        qp_grid.addWidget(QLabel('to:'), 1, 2, Qt.AlignRight)
        self.dtTo = QDateEdit(QDate.currentDate())
        self.dtTo.setDisplayFormat('yyyy-MM-dd')
        self.dtTo.setCalendarPopup(True)
        qp_grid.addWidget(self.dtTo, 1, 3)

        qp_grid.addWidget(QLabel('Max results:'), 1, 4, Qt.AlignRight)
        self.spnLimit = QSpinBox()
        self.spnLimit.setRange(1, 500)
        self.spnLimit.setValue(20)
        self.spnLimit.setMaximumWidth(70)
        qp_grid.addWidget(self.spnLimit, 1, 5)

        qp_grid.addWidget(QLabel('Bounding box\n(W S E N):'), 2, 0)
        bbox_row = QHBoxLayout()
        west, south, east, north = bbox
        for label, lo, hi, val in [('W', -180, 180, west), ('S', -90, 90, south),
                                    ('E', -180, 180, east), ('N', -90, 90, north)]:
            lbl = QLabel(label)
            lbl.setMaximumWidth(14)
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setDecimals(6)
            spin.setValue(val)
            spin.setMaximumWidth(110)
            bbox_row.addWidget(lbl)
            bbox_row.addWidget(spin)
            setattr(self, f'spn{label}', spin)
        qp_grid.addLayout(bbox_row, 2, 1, 1, 5)

        main.addWidget(qp_group)

        # ── Search action row ─────────────────────────────────────────
        action_row = QHBoxLayout()
        self.btnSearch = QPushButton('Search')
        self.btnSearch.setMinimumHeight(32)
        self.btnSearch.setMinimumWidth(120)
        self.btnSearch.clicked.connect(self._run_query)
        self.lblStatus = QLabel('')
        self.lblStatus.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        action_row.addWidget(self.btnSearch)
        action_row.addWidget(self.lblStatus)
        main.addLayout(action_row)

        # ── Results table ─────────────────────────────────────────────
        res_group = QGroupBox('Results')
        res_layout = QVBoxLayout(res_group)

        self.tblResults = QTableWidget(0, 5)
        self.tblResults.setHorizontalHeaderLabels(
            ['Item ID', 'Collection', 'Date', 'Bounding Box', 'Assets'])
        hdr = self.tblResults.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tblResults.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tblResults.setSelectionBehavior(QTableWidget.SelectRows)
        self.tblResults.setAlternatingRowColors(True)
        res_layout.addWidget(self.tblResults)

        res_btn_row = QHBoxLayout()
        self.btnOpenBrowser = QPushButton('Open Item in Browser')
        self.btnOpenBrowser.setEnabled(False)
        self.btnOpenBrowser.clicked.connect(self._open_in_browser)
        res_btn_row.addWidget(self.btnOpenBrowser)
        res_btn_row.addStretch()
        btn_close = QPushButton('Close')
        btn_close.clicked.connect(self.reject)
        res_btn_row.addWidget(btn_close)
        res_layout.addLayout(res_btn_row)

        main.addWidget(res_group)

        self.tblResults.itemSelectionChanged.connect(
            lambda: self.btnOpenBrowser.setEnabled(
                bool(self.tblResults.selectedItems())))

    # ----------------------------------------------------------------
    def _on_service_changed(self, name):
        self.txtCustomURL.setVisible(name == 'Custom…')

    def _get_base_url(self):
        name = self.cmbService.currentText()
        if name == 'Custom…':
            return self.txtCustomURL.text().rstrip('/')
        return STAC_SERVICES.get(name, '').rstrip('/')

    # ----------------------------------------------------------------
    def _run_query(self):
        import json
        import urllib.request
        import urllib.error
        from PyQt5.QtWidgets import QApplication, QTableWidgetItem

        base_url = self._get_base_url()
        if not base_url:
            self.lblStatus.setText('⚠ Please enter a service URL.')
            return

        payload = {
            'bbox': [
                self.spnW.value(), self.spnS.value(),
                self.spnE.value(), self.spnN.value(),
            ],
            'datetime': (
                f'{self.dtFrom.date().toString("yyyy-MM-dd")}T00:00:00Z'
                f'/{self.dtTo.date().toString("yyyy-MM-dd")}T23:59:59Z'
            ),
            'limit': self.spnLimit.value(),
        }
        cols = [c.strip() for c in self.txtCollections.text().split(',') if c.strip()]
        if cols:
            payload['collections'] = cols

        self.btnSearch.setEnabled(False)
        self.lblStatus.setText('Querying…')
        QApplication.processEvents()

        try:
            body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                f'{base_url}/search',
                data=body,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': 'GeneralRasterImporter/2.0',
                },
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            self.lblStatus.setText(f'HTTP {exc.code}: {exc.reason}')
            self.btnSearch.setEnabled(True)
            return
        except Exception as exc:
            self.lblStatus.setText(f'Error: {exc}')
            self.btnSearch.setEnabled(True)
            return

        features = result.get('features', [])
        self._results = features
        self.tblResults.setRowCount(0)

        for feat in features:
            row = self.tblResults.rowCount()
            self.tblResults.insertRow(row)
            fid  = feat.get('id', '')
            coll = feat.get('collection',
                            feat.get('properties', {}).get('collection', ''))
            dt   = (feat.get('properties') or {}).get('datetime', '')
            if dt and len(dt) > 10:
                dt = dt[:10]
            raw_bbox = feat.get('bbox', [])
            bbox_str = ', '.join(f'{v:.4f}' for v in raw_bbox) if raw_bbox else ''
            assets   = ', '.join(feat.get('assets', {}).keys())
            for col, val in enumerate([fid, coll, dt, bbox_str, assets]):
                self.tblResults.setItem(row, col, QTableWidgetItem(str(val)))

        matched = (result.get('numberMatched')
                   or result.get('context', {}).get('matched')
                   or len(features))
        self.lblStatus.setText(
            f'{len(features)} item(s) returned  ·  matched: {matched}')
        self.btnSearch.setEnabled(True)

    # ----------------------------------------------------------------
    def _open_in_browser(self):
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl

        rows = {idx.row() for idx in self.tblResults.selectedIndexes()}
        if not rows:
            return
        row = sorted(rows)[0]
        if row >= len(self._results):
            return
        feat = self._results[row]
        # Prefer self link, fall back to first asset href
        url = next(
            (lnk['href'] for lnk in feat.get('links', [])
             if lnk.get('rel') == 'self'),
            None
        )
        if not url:
            url = next(
                (a.get('href', '') for a in feat.get('assets', {}).values()),
                None
            )
        if url:
            QDesktopServices.openUrl(QUrl(url))


# ─────────────────────────────────────────────────────────────────────

class HEIFTTLImporterDialog(QDialog, FORM_CLASS):
    """Dialog for importing HEIF imagery with TTL metadata"""
    
    def __init__(self, parent=None, iface=None):
        super(HEIFTTLImporterDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        # Allow the dialog to be freely resized (needed on macOS)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )
        
        self.ttl_parser = None
        self.heif_processor = None
        self.has_internal_rdf = False
        self.ready_to_process = False
        
        # Connect signals
        self.btnBrowseHEIF.clicked.connect(self.browse_heif)
        self.btnBrowseTTL.clicked.connect(self.browse_ttl)
        self.btnBrowseOutput.clicked.connect(self.browse_output)
        self.txtHEIFPath.textChanged.connect(self.check_heif_metadata)
        self.txtTTLPath.textChanged.connect(self.parse_ttl_metadata)
        self.chkOrthorectify.toggled.connect(self.toggle_orthorectify_options)
        
        # Connect Import and Close buttons
        self.btnImport.clicked.connect(self.start_import)
        self.btnClose.clicked.connect(self.close_dialog)
        self.btnCreatePackage.clicked.connect(self.create_package)
        
        # Connect Export buttons (if they exist in UI)
        if hasattr(self, 'btnBrowseGeoTIFF'):
            self.btnBrowseGeoTIFF.clicked.connect(self.browse_geotiff_export)
        if hasattr(self, 'btnBrowseGeoTIFFSource'):
            self.btnBrowseGeoTIFFSource.clicked.connect(self.browse_geotiff_for_source)
        if hasattr(self, 'btnBrowseHEIFOutput'):
            self.btnBrowseHEIFOutput.clicked.connect(self.browse_heif_output)
        if hasattr(self, 'btnExportToHEIF'):
            self.btnExportToHEIF.clicked.connect(self.export_to_tb21_heif)
        if hasattr(self, 'comboGeoTIFFSource'):
            self.comboGeoTIFFSource.currentIndexChanged.connect(self.on_geotiff_source_changed)
        if hasattr(self, 'btnRefreshLayers'):
            self.btnRefreshLayers.clicked.connect(self.refresh_raster_layers)
        
        # Add button for displaying HEIF structure if it exists in UI
        if hasattr(self, 'btnShowStructure'):
            self.btnShowStructure.clicked.connect(self.show_heif_structure)
        
        # Connect Provenance viewer buttons
        if hasattr(self, 'btnLoadProvenance'):
            self.btnLoadProvenance.clicked.connect(self.browse_provenance_file)
        if hasattr(self, 'btnExportSTAC'):
            self.btnExportSTAC.clicked.connect(self.export_provenance_to_stac)
        if hasattr(self, 'btnQueryOSM'):
            self.btnQueryOSM.clicked.connect(self.query_osm_context)
        if hasattr(self, 'btnLoadOSMLayers'):
            self.btnLoadOSMLayers.clicked.connect(self.load_osm_layers_to_map)

        # Publishing buttons (new standalone group)
        if hasattr(self, 'btnSTACExportAction'):
            self.btnSTACExportAction.clicked.connect(self.open_stac_query)
        if hasattr(self, 'btnImmutablePublish'):
            self.btnImmutablePublish.clicked.connect(self.publish_immutable_catalogue)

        # ── GDAL Export group (Tab 3) ──────────────────────────────────
        if hasattr(self, 'btnBrowseGDALSource'):
            self.btnBrowseGDALSource.clicked.connect(self.browse_gdal_source)
        if hasattr(self, 'btnRefreshGDALLayers'):
            self.btnRefreshGDALLayers.clicked.connect(self.refresh_gdal_export_layers)
        if hasattr(self, 'btnBrowseGDALOutput'):
            self.btnBrowseGDALOutput.clicked.connect(self.browse_gdal_output)
        if hasattr(self, 'btnExportGDAL'):
            self.btnExportGDAL.clicked.connect(self.export_gdal)
        if hasattr(self, 'comboGDALExportSource'):
            self.comboGDALExportSource.currentIndexChanged.connect(self.on_gdal_source_changed)
        if hasattr(self, 'cmbGDALOutputFormat'):
            self.cmbGDALOutputFormat.currentIndexChanged.connect(self._on_gdal_format_changed)
        if hasattr(self, 'cmbOutputFormat'):
            self.cmbOutputFormat.currentIndexChanged.connect(self._on_import_format_changed)

        # Initialise provenance viewer state
        self.loaded_provenance_path = None
        self.loaded_provenance_data = None

        # Cached raster probe result (set by check_heif_metadata)
        self._last_raster_probe = None

        # Store last export path for package creation
        self.last_export_path = None
        self.last_provenance = None
        
        # Callback for import trigger
        self.import_callback = None
        
        # Load saved settings
        self.load_settings()
        
        # Set default output to temp directory
        if not self.txtOutputPath.text():
            import tempfile
            self.txtOutputPath.setText(tempfile.gettempdir())
        
        # Populate raster layers for export - use QTimer to ensure QGIS is ready
        QTimer.singleShot(100, self.refresh_raster_layers)
        QTimer.singleShot(150, self.refresh_gdal_export_layers)
        
        # Check available codecs and disable unsupported ones
        QTimer.singleShot(200, self.check_available_codecs)
    
    def check_available_codecs(self):
        """Check which heif-enc codecs are available and disable unsupported ones in UI"""
        if not hasattr(self, 'comboCompression'):
            return
        
        try:
            from .heif_processor import HEIFProcessor
            if self.heif_processor is None:
                self.heif_processor = HEIFProcessor()
            
            if not self.heif_processor.heif_enc_cmd:
                return  # heif-enc not available
            
            import subprocess
            result = subprocess.run(
                [self.heif_processor.heif_enc_cmd, '--list-encoders'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout
                
                # Parse available encoders
                has_hevc = 'HEIC encoders:' in output and 'x265' in output
                has_av1 = 'AVIF encoders:' in output and 'aom' in output
                
                # Check for JPEG2000 encoders (openjpeg or other)
                j2k_section = output.split('JPEG 2000 encoders:')[1].split('\n')[1].strip() if 'JPEG 2000 encoders:' in output else ''
                has_jpeg2000 = 'openjpeg' in j2k_section.lower() or len(j2k_section) > 0
                
                htj2k_section = output.split('JPEG 2000 (HT) encoders:')[1].split('\n')[1].strip() if 'JPEG 2000 (HT) encoders:' in output else ''
                has_htj2k = len(htj2k_section) > 0
                
                has_uncompressed = 'Uncompressed encoders:' in output
                
                # Check if OpenJPEG is available on system (for helpful message)
                try:
                    openjpeg_check = subprocess.run(['which', 'opj_compress'], capture_output=True, text=True, timeout=2)
                    openjpeg_available = openjpeg_check.returncode == 0
                except:
                    openjpeg_available = False
                
                # Disable unavailable codecs
                for i in range(self.comboCompression.count()):
                    codec = self.comboCompression.itemText(i)
                    available = True
                    
                    if codec == 'hevc' and not has_hevc:
                        available = False
                    elif codec == 'av1' and not has_av1:
                        available = False
                    elif codec == 'jpeg2000' and not has_jpeg2000:
                        available = False
                    elif codec == 'htj2k' and not has_htj2k:
                        available = False
                    elif codec == 'uncompressed' and not has_uncompressed:
                        available = False
                    
                    # Disable/gray out unavailable options
                    model = self.comboCompression.model()
                    item = model.item(i)
                    if not available:
                        item.setEnabled(False)
                        tooltip = f"{codec} encoder not available in this libheif build"
                        
                        # Add helpful message for JPEG2000 if OpenJPEG is installed
                        if codec in ['jpeg2000', 'htj2k'] and openjpeg_available:
                            tooltip += "\nOpenJPEG is installed - rebuild libheif with: cmake -DWITH_OpenJPEG=ON"
                        
                        item.setToolTip(tooltip)
                    
        except Exception as e:
            print(f"Could not check codec availability: {e}")
    
    def check_heif_metadata(self):
        """
        Probe the selected raster input: detect format, dimensions, georeferencing
        status, and available metadata sources.  Updates lblRasterStatus and
        (if HEIF with internal RDF) pre-fills the metadata preview.
        """
        input_path = self.txtHEIFPath.text()

        self.has_internal_rdf = False

        # Clear status when nothing is selected
        if hasattr(self, 'lblRasterStatus'):
            self.lblRasterStatus.setText('No file selected.')
            self.lblRasterStatus.setStyleSheet('')

        if not input_path or not os.path.exists(input_path):
            return

        try:
            from .heif_processor import HEIFProcessor
        except ImportError:
            from heif_processor import HEIFProcessor

        if self.heif_processor is None:
            self.heif_processor = HEIFProcessor()

        # ---- Probe format ----
        probe = self.heif_processor.probe_raster_format(input_path)

        # Store probe on dialog for use by process_import
        self._last_raster_probe = probe

        # ---- Build status text ----
        dim_str = ''
        if probe['width'] and probe['height']:
            dim_str = f'  {probe["width"]}×{probe["height"]}'
            if probe['band_count']:
                dim_str += f'  {probe["band_count"]} band(s)'

        fmt_line = f'Format: {probe["format_name"]}{dim_str}'

        if probe['is_geo_enabled']:
            crs_hint = ''
            if probe['crs_epsg']:
                crs_hint = f'  CRS: EPSG:{probe["crs_epsg"]}'
            elif probe['crs_wkt']:
                crs_hint = '  CRS: (custom projection)'
            if probe['has_gcps']:
                geo_line = f'✓ Georeferenced  {probe["gcp_count"]} GCPs{crs_hint}'
            else:
                geo_line = f'✓ Georeferenced  (geotransform){crs_hint}'
            status_color = 'green'
        else:
            geo_line = '⚠ Not georeferenced'
            status_color = 'orange'

        # -- Geo sources --
        sources = probe.get('available_geo_sources', [])
        source_lines = []
        for s in sources:
            source_lines.append(f'  • {s["description"]}')

        status_parts = [fmt_line, geo_line]
        if source_lines:
            geo_line += '  |  Available georef sources:'
            status_parts = [fmt_line, geo_line] + source_lines

        full_status = '\n'.join(status_parts)

        if hasattr(self, 'lblRasterStatus'):
            self.lblRasterStatus.setText(full_status)
            self.lblRasterStatus.setStyleSheet(
                f'color: {status_color}; font-weight: bold;'
            )

        # ---- Legacy lblTTLStatus compatibility ----
        if probe['is_heif']:
            self.has_internal_rdf = probe.get('available_geo_sources') and any(
                s['source'] == 'embedded_rdf' for s in sources
            )
            if self.has_internal_rdf:
                rdf_content = self.heif_processor.extract_internal_rdf(input_path)
                if rdf_content:
                    self.display_internal_rdf_preview(rdf_content)
                if hasattr(self, 'lblTTLStatus'):
                    fmt = (self.heif_processor.internal_rdf_format or 'RDF').upper()
                    self.lblTTLStatus.setText(
                        f'✓ Internal {fmt} RDF detected — external TTL optional'
                    )
                    self.lblTTLStatus.setStyleSheet('color: green; font-weight: bold;')
            else:
                if hasattr(self, 'lblTTLStatus'):
                    self.lblTTLStatus.setText('⚠ No internal RDF — external TTL file required')
                    self.lblTTLStatus.setStyleSheet('color: orange; font-weight: bold;')

        # -- Auto-suggest sidecar TTL or JSON if found --
        if not self.txtTTLPath.text():
            for s in sources:
                if s['source'] in ('sidecar_ttl', 'sidecar_json') and s.get('path'):
                    self.txtTTLPath.setText(s['path'])
                    break

    def show_heif_structure(self):
        """Display the complete file structure (HEIF) or GDAL metadata summary"""
        heif_path = self.txtHEIFPath.text()

        if not heif_path or not os.path.exists(heif_path):
            QMessageBox.warning(self, "No File Selected",
                                "Please select a raster input file first.")
            return

        try:
            from .heif_processor import HEIFProcessor
        except ImportError:
            from heif_processor import HEIFProcessor

        if self.heif_processor is None:
            self.heif_processor = HEIFProcessor()

        probe = getattr(self, '_last_raster_probe', None) or \
                self.heif_processor.probe_raster_format(heif_path)

        if probe['is_heif']:
            # Full HEIF structure dump
            structure = self.heif_processor.display_heif_structure(heif_path)
        else:
            # GDAL metadata summary for non-HEIF rasters
            structure = self._build_gdal_info_text(heif_path, probe)

        self.txtMetadataPreview.setPlainText(structure)

        msg = QMessageBox(self)
        msg.setWindowTitle("Raster File Info")
        msg.setText("File analysis complete — see details in the metadata preview area.")
        msg.setDetailedText(structure)
        msg.setIcon(QMessageBox.Information)
        msg.exec_()

    def _build_gdal_info_text(self, path: str, probe: dict) -> str:
        """Build a human-readable summary of a non-HEIF raster's GDAL metadata."""
        lines = [
            '=' * 60,
            f'RASTER FILE: {os.path.basename(path)}',
            '=' * 60,
            f'Format:     {probe["format_name"]} ({probe["driver_name"]})',
            f'Dimensions: {probe["width"]} × {probe["height"]} px',
            f'Bands:      {probe["band_count"]}',
        ]
        if probe['crs_epsg']:
            lines.append(f'CRS:        EPSG:{probe["crs_epsg"]}')
        elif probe['crs_wkt']:
            lines.append(f'CRS:        {probe["crs_wkt"][:80]}…')
        if probe['geotransform_valid']:
            lines.append('Geotransform: valid (raster is georeferenced)')
        if probe['has_gcps']:
            lines.append(f'GCPs:       {probe["gcp_count"]} control points embedded')
        lines.append('')
        sources = probe.get('available_geo_sources', [])
        if sources:
            lines.append('Available Georeferencing Sources:')
            for s in sources:
                lines.append(f'  [{s["source"]}]  {s["description"]}')
        else:
            lines.append('No external georeferencing sources detected.')
        return '\n'.join(lines)

    def display_internal_rdf_preview(self, rdf_content: str):
        """Display preview of internal RDF metadata"""
        preview = []
        preview.append("=" * 60)
        preview.append("INTERNAL RDF METADATA (from HEIF file)")
        preview.append("=" * 60)
        preview.append("")
        preview.append(f"Format: {self.heif_processor.internal_rdf_format.upper()}")
        preview.append(f"Size: {len(rdf_content)} bytes")
        preview.append("")
        preview.append("Preview:")
        preview.append("-" * 60)
        preview.append(rdf_content[:1000])  # First 1000 chars
        if len(rdf_content) > 1000:
            preview.append(f"\n... ({len(rdf_content) - 1000} more bytes)")
        preview.append("-" * 60)
        preview.append("")
        preview.append("ℹ️  External TTL file is OPTIONAL - internal RDF will be used if no TTL provided")
        
        self.txtMetadataPreview.setText('\n'.join(preview))
    
    def toggle_orthorectify_options(self, checked):
        """Enable/disable orthorectification options"""
        self.labelTransform.setEnabled(checked)
        self.cmbTransformOrder.setEnabled(checked)
        if checked:
            # Ensure warping is enabled when orthorectifying
            self.chkWarp.setChecked(True)
            self.chkWarp.setEnabled(False)
        else:
            self.chkWarp.setEnabled(True)
    
    def load_settings(self):
        """Load previously saved settings"""
        settings = QSettings()
        self.txtHEIFPath.setText(settings.value("heif_ttl_importer/last_heif_path", ""))
        self.txtTTLPath.setText(settings.value("heif_ttl_importer/last_ttl_path", ""))
        self.txtOutputPath.setText(settings.value("heif_ttl_importer/last_output_path", ""))
    
    def save_settings(self):
        """Save current settings"""
        settings = QSettings()
        settings.setValue("heif_ttl_importer/last_heif_path", self.txtHEIFPath.text())
        settings.setValue("heif_ttl_importer/last_ttl_path", self.txtTTLPath.text())
        settings.setValue("heif_ttl_importer/last_output_path", self.txtOutputPath.text())

    # ── Output-format combo helpers (Import tab) ──────────────────────

    def _on_import_format_changed(self, index: int):
        """Auto-fill creation options hint when output format changes (import tab)."""
        if not hasattr(self, 'cmbOutputFormat') or not hasattr(self, 'txtCreationOpts'):
            return
        label = self.cmbOutputFormat.currentText()
        entry = GDAL_OUTPUT_FORMATS.get(label)
        if entry and not self.txtCreationOpts.text():
            self.txtCreationOpts.setPlaceholderText(
                entry[2] if entry[2] else "e.g. COMPRESS=DEFLATE TILED=YES")

    def get_import_output_format(self):
        """Return (gdal_driver, extension, creation_opts_list) for the selected import output format."""
        if not hasattr(self, 'cmbOutputFormat'):
            return "GTiff", ".tif", []
        label = self.cmbOutputFormat.currentText()
        driver, ext, _ = GDAL_OUTPUT_FORMATS.get(label, ("GTiff", ".tif", ""))
        raw_opts = self.txtCreationOpts.text().strip() if hasattr(self, 'txtCreationOpts') else ""
        opts = [o for o in raw_opts.split() if "=" in o]
        return driver, ext, opts

    # ── GDAL Export group helpers (Export tab) ────────────────────────

    def _on_gdal_format_changed(self, index: int):
        """Auto-fill creation options hint when the GDAL export format changes."""
        if not hasattr(self, 'cmbGDALOutputFormat') or not hasattr(self, 'txtGDALExportOpts'):
            return
        label = self.cmbGDALOutputFormat.currentText()
        entry = GDAL_OUTPUT_FORMATS.get(label)
        if entry and not self.txtGDALExportOpts.text():
            self.txtGDALExportOpts.setPlaceholderText(
                entry[2] if entry[2] else "e.g. COMPRESS=DEFLATE TILED=YES")
        # Update output path extension suggestion
        self._suggest_gdal_output_path()

    def _suggest_gdal_output_path(self):
        """Auto-suggest output path extension based on selected GDAL format."""
        if not hasattr(self, 'txtGDALOutputPath') or not hasattr(self, 'cmbGDALOutputFormat'):
            return
        current = self.txtGDALOutputPath.text()
        if not current:
            return
        label = self.cmbGDALOutputFormat.currentText()
        entry = GDAL_OUTPUT_FORMATS.get(label)
        if not entry:
            return
        new_ext = entry[1]
        p = Path(current)
        if p.suffix.lower() != new_ext:
            self.txtGDALOutputPath.setText(str(p.with_suffix(new_ext)))

    def refresh_gdal_export_layers(self):
        """Populate comboGDALExportSource with loaded raster layers."""
        if not hasattr(self, 'comboGDALExportSource'):
            return
        try:
            from qgis.core import QgsProject, QgsRasterLayer
            self.comboGDALExportSource.clear()
            self.comboGDALExportSource.addItem("Browse for file...")
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsRasterLayer):
                    self.comboGDALExportSource.addItem(layer.name(), layer.id())
        except Exception as e:
            print(f"refresh_gdal_export_layers: {e}")

    def on_gdal_source_changed(self, index: int):
        """Fill txtGDALSourcePath when a layer is selected in comboGDALExportSource."""
        if not hasattr(self, 'comboGDALExportSource') or not hasattr(self, 'txtGDALSourcePath'):
            return
        if index == 0:
            return  # "Browse for file..." — handled by button
        try:
            from qgis.core import QgsProject
            layer_id = self.comboGDALExportSource.currentData()
            if layer_id:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    self.txtGDALSourcePath.setText(layer.source())
                    self._suggest_gdal_output_path()
        except Exception as e:
            print(f"on_gdal_source_changed: {e}")

    def browse_gdal_source(self):
        """Browse for a source raster file for GDAL export."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Source Raster",
            self.txtGDALSourcePath.text() if hasattr(self, 'txtGDALSourcePath') else os.path.expanduser("~"),
            "All Raster Files (*.tif *.tiff *.jp2 *.img *.ecw *.png *.jpg *.ntf *.gpkg *.heif *.heic *.nc *.h5 *.vrt);;"
            "GeoTIFF (*.tif *.tiff);;"
            "JPEG2000 (*.jp2);;"
            "HEIF/HEIC (*.heif *.heic);;"
            "All Files (*.*)"
        )
        if file_path and hasattr(self, 'txtGDALSourcePath'):
            self.txtGDALSourcePath.setText(file_path)
            # Suggest output path beside source
            if hasattr(self, 'txtGDALOutputPath') and not self.txtGDALOutputPath.text():
                label = self.cmbGDALOutputFormat.currentText() if hasattr(self, 'cmbGDALOutputFormat') else ""
                ext = GDAL_OUTPUT_FORMATS.get(label, ("GTiff", ".tif", ""))[1]
                self.txtGDALOutputPath.setText(str(Path(file_path).with_suffix(ext)))

    def browse_gdal_output(self):
        """Browse for a target path for GDAL export."""
        if not hasattr(self, 'cmbGDALOutputFormat'):
            return
        label = self.cmbGDALOutputFormat.currentText()
        ext = GDAL_OUTPUT_FORMATS.get(label, ("GTiff", ".tif", ""))[1]
        start = self.txtGDALOutputPath.text() if hasattr(self, 'txtGDALOutputPath') else os.path.expanduser("~")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Raster As",
            start,
            f"Selected format (*{ext});;All Files (*.*)"
        )
        if file_path and hasattr(self, 'txtGDALOutputPath'):
            if not file_path.lower().endswith(ext):
                file_path += ext
            self.txtGDALOutputPath.setText(file_path)

    def export_gdal(self):
        """Export the selected source raster using GDAL translate to the chosen format."""
        if not hasattr(self, 'txtGDALSourcePath') or not hasattr(self, 'txtGDALOutputPath'):
            return
        src = self.txtGDALSourcePath.text().strip()
        dst = self.txtGDALOutputPath.text().strip()
        if not src or not os.path.exists(src):
            QMessageBox.warning(self, "General Raster Importer", "Please select a valid source raster file.")
            return
        if not dst:
            QMessageBox.warning(self, "General Raster Importer", "Please specify an output path.")
            return

        label = self.cmbGDALOutputFormat.currentText() if hasattr(self, 'cmbGDALOutputFormat') else "GeoTIFF (.tif)"
        driver, ext, default_opts = GDAL_OUTPUT_FORMATS.get(label, ("GTiff", ".tif", ""))

        raw_opts = self.txtGDALExportOpts.text().strip() if hasattr(self, 'txtGDALExportOpts') else ""
        creation_opts = [o for o in (raw_opts or default_opts).split() if "=" in o]

        try:
            from .heif_processor import HEIFProcessor
        except ImportError:
            from heif_processor import HEIFProcessor

        if self.heif_processor is None:
            self.heif_processor = HEIFProcessor()

        if not dst.lower().endswith(ext):
            dst += ext
            if hasattr(self, 'txtGDALOutputPath'):
                self.txtGDALOutputPath.setText(dst)

        self.progressBar.setValue(0)
        try:
            self.heif_processor.export_gdal(src, dst, driver, creation_opts)
            self.progressBar.setValue(100)
            QMessageBox.information(self, "General Raster Importer",
                                    f"Exported successfully:\n{dst}")
            add_to_map = self.chkGDALAddToMap.isChecked() if hasattr(self, 'chkGDALAddToMap') else False
            if add_to_map:
                try:
                    from qgis.core import QgsProject, QgsRasterLayer
                    layer = QgsRasterLayer(dst, Path(dst).stem)
                    if layer.isValid():
                        QgsProject.instance().addMapLayer(layer)
                except Exception:
                    pass
        except Exception as exc:
            self.progressBar.setValue(0)
            QMessageBox.critical(self, "Export Failed", str(exc))

    def browse_heif(self):
        """Browse for a raster input file (HEIF, GeoTIFF, JP2, PNG, JPEG, or any GDAL-readable raster)"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Raster Input",
            self.txtHEIFPath.text() or os.path.expanduser("~"),
            "Raster Images (*.heif *.heic *.HEIF *.HEIC "
            "*.tif *.tiff *.TIF *.TIFF "
            "*.jp2 *.JP2 "
            "*.png *.PNG "
            "*.jpg *.jpeg *.JPG *.JPEG "
            "*.img *.ecw *.sid);;"
            "HEIF/HEIC (*.heif *.heic);;"
            "GeoTIFF (*.tif *.tiff);;"
            "JPEG2000 (*.jp2);;"
            "PNG (*.png);;"
            "JPEG (*.jpg *.jpeg);;"
            "All Files (*.*)"
        )
        
        if file_path:
            self.txtHEIFPath.setText(file_path)
            
            # Check for internal RDF metadata
            self.check_heif_metadata()
            
            # Auto-suggest TTL file if in same directory (but not required if has internal RDF)
            ttl_candidate = Path(file_path).with_suffix('.ttl')
            if ttl_candidate.exists() and not self.txtTTLPath.text():
                self.txtTTLPath.setText(str(ttl_candidate))
            elif not ttl_candidate.exists() and self.has_internal_rdf:
                # Show message that TTL is optional
                QMessageBox.information(
                    self,
                    "Internal RDF Detected",
                    f"This HEIF file contains internal {self.heif_processor.internal_rdf_format.upper()} RDF metadata.\n\n"
                    "External TTL file is OPTIONAL - you can proceed without it.\n"
                    "The internal RDF will be used for georeferencing."
                )
    
    def browse_ttl(self):
        """Browse for metadata file (TTL/RDF, XML, or JSON provenance)"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Metadata File",
            self.txtTTLPath.text() or os.path.expanduser("~"),
            "Metadata Files (*.ttl *.TTL *.rdf *.RDF *.xml *.XML *.json *.JSON);;"
            "TTL/RDF (*.ttl *.rdf);;"
            "XML/RDF (*.xml);;"
            "JSON Provenance (*_provenance.json *.json);;"
            "All Files (*.*)"
        )

        if file_path:
            self.txtTTLPath.setText(file_path)
    
    def browse_output(self):
        """Browse for output directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self.txtOutputPath.text() or os.path.expanduser("~")
        )
        
        if dir_path:
            self.txtOutputPath.setText(dir_path)
    
    def parse_ttl_metadata(self):
        """Parse metadata file and display preview — supports TTL, XML/RDF, and JSON formats."""
        ttl_path = self.txtTTLPath.text()

        if not ttl_path or not os.path.exists(ttl_path):
            self.txtMetadataPreview.clear()
            self.ttl_parser = None
            return

        ext = os.path.splitext(ttl_path)[1].lower()

        # ---- JSON provenance sidecar ----
        if ext == '.json':
            self._parse_json_metadata_preview(ttl_path)
            return

        # ---- XML / RDF ----
        if ext in ('.xml', '.rdf') and ext != '.ttl':
            # Check for Turtle-style content inside the file before deciding
            try:
                with open(ttl_path, 'rb') as fh:
                    head = fh.read(256)
                is_turtle = (b'@prefix' in head or b'@base' in head)
            except OSError:
                is_turtle = False
            if not is_turtle:
                self._parse_xml_metadata_preview(ttl_path)
                return

        try:
            # Parse TTL with custom parser (for GCPs extraction)
            parser = TTLParser(ttl_path)
            if parser.parse():
                self.ttl_parser = parser
            else:
                self.ttl_parser = None
            
            # Parse with rdflib for rich metadata display
            try:
                from rdflib import Graph, Namespace, URIRef
                from rdflib.namespace import RDF, RDFS
                
                g = Graph()
                g.parse(ttl_path, format='turtle')
                
                # Define namespaces
                IMH = Namespace("http://ontology.mil/foundry/IMH#")
                CCO = Namespace("https://www.commoncoreontologies.org/")
                GEOSPARQL = Namespace("http://www.opengis.net/ont/geosparql#")
                OBI = Namespace("http://purl.obolibrary.org/obo/")
                
                preview = []
                preview.append("=" * 60)
                preview.append("RDF METADATA PREVIEW")
                preview.append("=" * 60)
                preview.append("")
                
                # Get basic statistics
                total_triples = len(g)
                preview.append(f"📊 Total RDF Triples: {total_triples}")
                preview.append("")
                
                # Count entities by type
                preview.append("🔍 Entity Types:")
                type_counts = {}
                for s, p, o in g.triples((None, RDF.type, None)):
                    type_name = str(o).split('#')[-1].split('/')[-1]
                    type_counts[type_name] = type_counts.get(type_name, 0) + 1
                
                for type_name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                    preview.append(f"  • {type_name}: {count}")
                preview.append("")
                
                # Image Coordinates
                img_coords = list(g.subjects(RDF.type, URIRef(str(IMH) + "_0001664")))
                if img_coords:
                    preview.append(f"📍 Image Coordinates: {len(img_coords)}")
                    for coord in img_coords[:3]:
                        x = g.value(coord, URIRef(str(IMH) + "_0001626"))
                        y = g.value(coord, URIRef(str(IMH) + "_0001630"))
                        label = g.value(coord, RDFS.label)
                        if x and y:
                            preview.append(f"  • {label or 'Coordinate'}: ({x}, {y})")
                    if len(img_coords) > 3:
                        preview.append(f"  ... and {len(img_coords) - 3} more")
                    preview.append("")
                
                # Ground Coordinates
                ground_coords = list(g.subjects(RDF.type, URIRef(str(IMH) + "_0001081")))
                if ground_coords:
                    preview.append(f"🌍 Ground Coordinates (WGS84): {len(ground_coords)}")
                    for coord in ground_coords[:3]:
                        lon = g.value(coord, URIRef(str(CCO) + "ont00001764"))
                        lat = g.value(coord, URIRef(str(CCO) + "ont00001766"))
                        label = g.value(coord, RDFS.label)
                        if lon and lat:
                            preview.append(f"  • {label or 'Coordinate'}: ({float(lon):.6f}, {float(lat):.6f})")
                    if len(ground_coords) > 3:
                        preview.append(f"  ... and {len(ground_coords) - 3} more")
                    preview.append("")
                
                # Correspondences (GCPs)
                correspondences = list(g.subjects(RDF.type, URIRef(str(IMH) + "_0001657")))
                if correspondences:
                    preview.append(f"🎯 Ground Control Points: {len(correspondences)}")
                    preview.append("")
                
                # Tiles
                tiles = list(g.subjects(RDF.type, URIRef(str(CCO) + "ont00002004")))
                if tiles:
                    preview.append(f"🗺️  Tiles: {len(tiles)}")
                    for tile in tiles[:10]:
                        label = g.value(tile, RDFS.label)
                        if label:
                            preview.append(f"  • {label}")
                    if len(tiles) > 10:
                        preview.append(f"  ... and {len(tiles) - 10} more")
                    preview.append("")
                
                # Correspondence Groups
                groups = list(g.subjects(RDF.type, URIRef(str(IMH) + "_0001634")))
                if groups:
                    preview.append(f"📦 Correspondence Groups: {len(groups)}")
                    for group in groups[:5]:
                        wkt = g.value(group, URIRef(str(GEOSPARQL) + "asWKT"))
                        tile_ref = g.value(group, URIRef(str(CCO) + "ont00001808"))
                        if tile_ref:
                            tile_label = g.value(tile_ref, RDFS.label)
                            # Count correspondences in this group
                            corr_refs = list(g.objects(group, URIRef(str(IMH) + "_0001678")))
                            preview.append(f"  • {tile_label or 'Group'}: {len(corr_refs)} GCPs")
                    if len(groups) > 5:
                        preview.append(f"  ... and {len(groups) - 5} more")
                    preview.append("")
                
                # Timestamps
                timestamps = list(g.subjects(RDF.type, URIRef(str(IMH) + "_0001416")))
                if timestamps:
                    preview.append(f"⏰ Timestamps: {len(timestamps)}")
                    for ts in timestamps[:3]:
                        label = g.value(ts, RDFS.label)
                        time_val = g.value(ts, URIRef(str(OBI) + "OBI_0002135"))
                        if label:
                            preview.append(f"  • {label}")
                    preview.append("")
                
                # File/Sample references
                samples = list(g.subjects(RDF.type, URIRef(str(CCO) + "ont00002004")))
                for sample in samples[:1]:
                    label = g.value(sample, RDFS.label)
                    if label and "Sample File" in str(label):
                        preview.append(f"📄 {label}")
                        preview.append("")
                
                # Summary from custom parser
                if self.ttl_parser:
                    dims = self.ttl_parser.get_image_dimensions()
                    preview.append(f"📐 Estimated Image Dimensions: {dims[0]} x {dims[1]} pixels")
                    gcps = self.ttl_parser.get_all_gcps()
                    if gcps:
                        lons = [gcp[2] for gcp in gcps]
                        lats = [gcp[3] for gcp in gcps]
                        preview.append(f"📍 Geographic Extent:")
                        preview.append(f"  Longitude: {min(lons):.6f} to {max(lons):.6f}")
                        preview.append(f"  Latitude: {min(lats):.6f} to {max(lats):.6f}")
                
                preview.append("")
                preview.append("=" * 60)
                preview.append("✓ Ready for georeferencing")
                preview.append("=" * 60)
                
                self.txtMetadataPreview.setPlainText("\n".join(preview))
                
            except ImportError:
                # Fallback to simple preview if rdflib not available
                if self.ttl_parser:
                    preview = []
                    preview.append(f"Image Coordinates: {len(self.ttl_parser.image_coords)}")
                    preview.append(f"Ground Coordinates: {len(self.ttl_parser.ground_coords)}")
                    preview.append(f"Correspondences (GCPs): {len(self.ttl_parser.correspondences)}")
                    preview.append(f"Tiles: {len(self.ttl_parser.correspondence_groups)}")
                    
                    dims = self.ttl_parser.get_image_dimensions()
                    preview.append(f"Estimated Image Size: {dims[0]} x {dims[1]} pixels")
                    
                    if self.ttl_parser.correspondence_groups:
                        preview.append("\nTiles found:")
                        for group in list(self.ttl_parser.correspondence_groups.values())[:5]:
                            preview.append(f"  - {group.tile_label}: {len(group.correspondences)} GCPs")
                        if len(self.ttl_parser.correspondence_groups) > 5:
                            preview.append(f"  ... and {len(self.ttl_parser.correspondence_groups) - 5} more")
                    
                    preview.append("\nNote: Install rdflib for detailed RDF preview")
                    self.txtMetadataPreview.setPlainText("\n".join(preview))
                else:
                    self.txtMetadataPreview.setPlainText("Error: Could not parse TTL file")
                
        except Exception as e:
            self.txtMetadataPreview.setPlainText(f"Error parsing TTL: {str(e)}\n\nTry installing rdflib: pip install rdflib")
            self.ttl_parser = None

    # ------------------------------------------------------------------
    # Private metadata-format helpers
    # ------------------------------------------------------------------

    def _parse_json_metadata_preview(self, path: str):
        """Handle a JSON metadata file loaded into the Metadata field.

        If the file looks like a *_provenance.json (has 'original_uuid' or
        'derived_uuid'), delegate to load_provenance_file() which populates
        the full Provenance tab.  Otherwise display a pretty-printed JSON
        summary in the metadata preview area.
        """
        import json
        self.ttl_parser = None  # JSON files carry no GCPs

        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as exc:
            self.txtMetadataPreview.setPlainText(f"Error reading JSON: {exc}")
            return

        is_provenance = 'original_uuid' in data or 'derived_uuid' in data
        if is_provenance:
            # Populate the Provenance tab and show a short note here
            self.load_provenance_file(path)
            self.txtMetadataPreview.setPlainText(
                "JSON provenance file loaded.\n"
                "See the Provenance tab for full details."
            )
            return

        # Generic JSON — pretty-print top-level keys in the preview
        lines = ["=" * 60, "JSON METADATA PREVIEW", "=" * 60, ""]
        for key, val in list(data.items())[:40]:
            if isinstance(val, dict):
                lines.append(f"{key}:")
                for k2, v2 in list(val.items())[:8]:
                    lines.append(f"  {k2}: {v2}")
            elif isinstance(val, list):
                lines.append(f"{key}: [{len(val)} item(s)]")
            else:
                lines.append(f"{key}: {val}")
        if len(data) > 40:
            lines.append(f"... and {len(data) - 40} more keys")
        self.txtMetadataPreview.setPlainText("\n".join(lines))

    def _parse_xml_metadata_preview(self, path: str):
        """Display an XML/RDF metadata file as a key/value summary.

        No GCPs are extracted from XML — ttl_parser stays None.
        """
        import xml.etree.ElementTree as ET
        self.ttl_parser = None

        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            self.txtMetadataPreview.setPlainText(f"Error parsing XML: {exc}")
            return

        root = tree.getroot()
        lines = ["=" * 60, "XML METADATA PREVIEW", "=" * 60, ""]
        lines.append(f"Root element: {root.tag}")
        lines.append(f"Attributes: {root.attrib or '(none)'}")
        lines.append("")

        # Collect up to 50 text-bearing leaf elements
        count = 0
        for elem in root.iter():
            if count >= 50:
                lines.append("... (output truncated)")
                break
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            text = (elem.text or '').strip()
            if text:
                lines.append(f"{tag}: {text}")
                count += 1

        self.txtMetadataPreview.setPlainText("\n".join(lines))

    def get_resample_method(self) -> str:
        """Get selected resampling method"""
        text = self.cmbResample.currentText()
        if 'Cubic' in text:
            return 'cubic'
        elif 'Lanczos' in text:
            return 'lanczos'
        elif 'Bilinear' in text:
            return 'bilinear'
        else:
            return 'near'
    
    def get_transform_order(self) -> int:
        """Get polynomial transformation order for orthorectification"""
        index = self.cmbTransformOrder.currentIndex()
        # 0=1st order, 1=2nd order, 2=3rd order, 3=TPS
        if index == 0:
            return 1
        elif index == 1:
            return 2
        elif index == 2:
            return 3
        else:
            return -1  # TPS (Thin Plate Spline)
    
    def get_orthorectify_enabled(self) -> bool:
        """Check if orthorectification is enabled"""
        return self.chkOrthorectify.isChecked()
    
    def validate(self) -> bool:
        """Validate user inputs"""
        if not self.txtHEIFPath.text():
            QMessageBox.warning(self, "Missing Input", "Please select a raster input file.")
            return False

        if not os.path.exists(self.txtHEIFPath.text()):
            QMessageBox.warning(self, "File Not Found", "Raster input file does not exist.")
            return False

        probe = getattr(self, '_last_raster_probe', None)
        is_geo_enabled = bool(probe and probe.get('is_geo_enabled', False))

        has_metadata = (
            (self.txtTTLPath.text() and os.path.exists(self.txtTTLPath.text()))
            or self.has_internal_rdf
        )

        # Metadata is required only when the raster has no embedded georeferencing
        if not has_metadata and not is_geo_enabled:
            QMessageBox.warning(
                self,
                "Missing Georeferencing",
                "No georeferencing information found.\n\n"
                "Please provide one of:\n"
                "• External TTL file with GCPs\n"
                "• JSON provenance sidecar\n"
                "• XML metadata file\n"
                "• A raster that already contains an embedded geotransform (e.g. GeoTIFF)"
            )
            return False

        has_ttl = self.txtTTLPath.text() and os.path.exists(self.txtTTLPath.text())

        if not self.txtOutputPath.text():
            QMessageBox.warning(self, "Missing Output", "Please select an output directory.")
            return False

        if not os.path.exists(self.txtOutputPath.text()):
            try:
                os.makedirs(self.txtOutputPath.text(), exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Invalid Directory",
                                    f"Could not create output directory: {str(e)}")
                return False

        # If using external TTL for GCPs, validate it has correspondences
        # (skip this check when the raster already has an embedded geotransform)
        if has_ttl and self.ttl_parser is not None:
            if len(self.ttl_parser.correspondences) == 0 and not is_geo_enabled:
                QMessageBox.warning(self, "No GCPs Found",
                                    "No ground control points found in TTL file.\n\n"
                                    "The raster also has no embedded geotransform.\n"
                                    "Import cannot proceed without georeferencing.")
                return False
        elif has_ttl and self.ttl_parser is None and not is_geo_enabled:
            # JSON/XML metadata loaded but raster is not already geo-enabled — no GCPs
            QMessageBox.warning(self, "No Georeferencing",
                                "The selected metadata file does not contain GCPs and\n"
                                "the raster has no embedded geotransform.\n\n"
                                "Please provide a TTL file with ground control points.")
            return False
        elif not has_ttl and self.has_internal_rdf:
            # Using internal RDF — validate it can be parsed
            if not self.heif_processor or not self.heif_processor.internal_rdf:
                QMessageBox.warning(
                    self,
                    "Internal RDF Error",
                    "Could not extract internal RDF metadata from the file."
                )
                return False

        return True
    
    def start_import(self):
        """Triggered when Import button is clicked"""
        if self.validate():
            self.save_settings()
            # Disable Import button during processing
            self.btnImport.setEnabled(False)
            self.btnImport.setText("Importing...")
            self.btnClose.setEnabled(False)
            
            # Trigger import process via callback (allows progress bar to update)
            if self.import_callback:
                # Use QTimer.singleShot to defer execution and allow UI to update
                QTimer.singleShot(100, self.import_callback)
            else:
                # Fallback: just mark as ready
                self.ready_to_process = True
    
    def close_dialog(self):
        """Close the dialog"""
        if self.ready_to_process:
            # Import is in progress - confirm cancellation
            reply = QMessageBox.question(
                self,
                'Import in Progress',
                'Import is currently running. Are you sure you want to close?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.reject()
        else:
            self.reject()
    
    # ------------------------------------------------------------------
    # Provenance viewer / STAC export
    # ------------------------------------------------------------------

    def browse_provenance_file(self):
        """Open file dialog to choose a _provenance.json file."""
        start_dir = (
            os.path.dirname(self.last_export_path)
            if self.last_export_path
            else os.path.expanduser('~')
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Select Provenance JSON',
            start_dir,
            'Provenance JSON (*_provenance.json *.json);;All Files (*.*)'
        )
        if file_path:
            self.load_provenance_file(file_path)

    def load_provenance_file(self, json_path: str):
        """Load and display a _provenance.json file in the viewer widgets."""
        import json
        try:
            with open(json_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as exc:
            QMessageBox.critical(self, 'Load Error',
                                 f'Could not read provenance file:\n{exc}')
            return

        self.loaded_provenance_path = json_path
        self.loaded_provenance_data = data

        if hasattr(self, 'txtProvenance'):
            self.txtProvenance.setText(json_path)

        # --- Populate the summary table ---
        if hasattr(self, 'tblProvenance'):
            from PyQt5.QtWidgets import QTableWidgetItem
            FLAT_FIELDS = [
                'original_uuid', 'derived_uuid', 'algorithm_uuid',
                'algorithm_name', 'processing_timestamp',
                'gcp_count', 'warp_enabled', 'orthorectify_enabled',
                'resample_method', 'transform_order',
                'input_file', 'input_hash', 'input_hash_algorithm',
                'output_file', 'output_hash', 'output_hash_algorithm',
            ]
            rows = [(k, str(data.get(k, '—'))) for k in FLAT_FIELDS]
            tbl = self.tblProvenance
            tbl.setRowCount(len(rows))
            tbl.setColumnCount(2)
            tbl.setHorizontalHeaderLabels(['Field', 'Value'])
            for row_idx, (field, value) in enumerate(rows):
                tbl.setItem(row_idx, 0, QTableWidgetItem(field))
                tbl.setItem(row_idx, 1, QTableWidgetItem(value))
            tbl.resizeColumnsToContents()
            tbl.horizontalHeader().setStretchLastSection(True)

        # --- Format ISO 19115-4 quality block ---
        if hasattr(self, 'txtISOQuality'):
            iso = data.get('iso19115_4', {})
            if iso:
                lines = [
                    f"Standard: {iso.get('metadataStandard', 'N/A')}",
                    f"Identifier: {iso.get('metadataIdentifier', 'N/A')}",
                    f"Date: {iso.get('metadataDate', 'N/A')}",
                    '',
                ]
                for q in iso.get('quality', []):
                    q_type = q.get('type', 'unknown')
                    if q_type == 'processingLevel':
                        lines.append(f"Processing Level: {q.get('level', 'N/A')} — {q.get('description', '')}")
                    elif q_type == 'sensorQuality':
                        lines.append(f"Sensor Type: {q.get('sensorType', 'N/A')} | Calibration: {q.get('calibrationStatus', 'N/A')}")
                    elif q_type == 'usabilityAssessment':
                        score = q.get('usabilityScore', 'N/A')
                        lims = '; '.join(q.get('limitations', [])) or 'None'
                        lines.append(f"Usability Score: {score} | Limitations: {lims}")
                    elif q_type == 'cloudCoverage':
                        pct = q.get('coveragePercentage')
                        lines.append(f"Cloud Coverage: {pct if pct is not None else 'N/A'}")
                grid = iso.get('gridSpatialRepresentation', {})
                if grid:
                    dims = grid.get('axisDimensionProperties', [])
                    dim_str = ' × '.join(
                        str(d.get('dimensionSize', '?')) for d in dims
                    )
                    lines.append(f"Grid Dimensions: {dim_str} px")
                self.txtISOQuality.setPlainText('\n'.join(lines))
            else:
                self.txtISOQuality.setPlainText('No ISO 19115-4 metadata present.')

        # Update status label
        alg = data.get('algorithm_name', 'unknown')
        ts = data.get('processing_timestamp', 'unknown')
        if hasattr(self, 'lblProvenanceStatus'):
            self.lblProvenanceStatus.setText(
                f"Loaded: {os.path.basename(json_path)} | "
                f"Algorithm: {alg} | Processed: {ts}"
            )

        # Enable STAC export now that provenance is loaded
        if hasattr(self, 'btnExportSTAC') or hasattr(self, 'btnSTACExportAction'):
            # STAC export also needs the sibling GeoTIFF/JP2
            output_file = data.get('output_file', '')
            sibling = os.path.join(os.path.dirname(json_path), output_file)
            can_export = bool(output_file and os.path.exists(sibling))
            if hasattr(self, 'btnExportSTAC'):
                self.btnExportSTAC.setEnabled(can_export)
            # btnSTACExportAction is always enabled (STAC Query, not export)

        # Enable OSM query if there is a sibling raster to derive the bbox from
        if hasattr(self, 'btnQueryOSM'):
            output_file = data.get('output_file', '')
            sibling = os.path.join(os.path.dirname(json_path), output_file)
            self.btnQueryOSM.setEnabled(bool(output_file and os.path.exists(sibling)))

        # Enable OSM layer loader if the sidecar already exists OR osm_context key present
        if hasattr(self, 'btnLoadOSMLayers'):
            osm_sidecar = self._osm_sidecar_path(json_path)
            has_osm_key = bool(data.get('osm_context'))
            has_osm_file = bool(osm_sidecar and os.path.exists(osm_sidecar))
            self.btnLoadOSMLayers.setEnabled(has_osm_key or has_osm_file)

        # Auto-offer TTL preview in metadata pane
        if hasattr(self, 'txtMetadataPreview'):
            ttl_sibling = json_path.replace('_provenance.json', '_provenance.ttl')
            if os.path.exists(ttl_sibling):
                try:
                    with open(ttl_sibling, 'r', encoding='utf-8') as fh:
                        self.txtMetadataPreview.setPlainText(fh.read())
                except Exception:
                    pass

    def export_provenance_to_stac(self):
        """Export the currently loaded provenance as a STAC 1.0 Item JSON file."""
        if not self.loaded_provenance_data or not self.loaded_provenance_path:
            QMessageBox.warning(self, 'No Provenance Loaded',
                                'Please load a provenance file first.')
            return

        data = self.loaded_provenance_data
        output_file = data.get('output_file', '')
        geotiff_path = os.path.join(
            os.path.dirname(self.loaded_provenance_path), output_file
        )
        if not os.path.exists(geotiff_path):
            QMessageBox.warning(
                self, 'Raster Not Found',
                f'The raster file referenced in provenance was not found:\n{geotiff_path}'
            )
            return

        output_dir = QFileDialog.getExistingDirectory(
            self, 'Select Output Directory for STAC Item',
            os.path.dirname(self.loaded_provenance_path)
        )
        if not output_dir:
            return

        try:
            from .stac_converter import ProvenanceToSTACConverter
            converter = ProvenanceToSTACConverter()
            stac_path = converter.convert(
                self.loaded_provenance_path,
                geotiff_path,
                output_dir
            )
            QMessageBox.information(
                self, 'STAC Item Exported',
                f'STAC Item written to:\n{stac_path}'
            )
        except Exception as exc:
            QMessageBox.critical(self, 'STAC Export Error',
                                 f'Could not export STAC Item:\n{exc}')

    # ------------------------------------------------------------------
    # STAC Query
    # ------------------------------------------------------------------

    def open_stac_query(self):
        """Open the STAC Query dialog.

        If provenance data is loaded and contains a bounding box, the dialog is
        pre-filled with that bbox so the user can immediately search for related
        imagery in any STAC catalogue.
        """
        bbox = None
        if self.loaded_provenance_data:
            bb = (self.loaded_provenance_data.get('bounding_box')
                  or self.loaded_provenance_data.get('bbox'))
            if bb and len(bb) >= 4:
                try:
                    bbox = (float(bb[0]), float(bb[1]),
                            float(bb[2]), float(bb[3]))
                except (TypeError, ValueError):
                    bbox = None
        dlg = STACQueryDialog(parent=self, initial_bbox=bbox)
        dlg.exec_()

    # ------------------------------------------------------------------
    # Immutable Catalogue Publish
    # ------------------------------------------------------------------

    def publish_immutable_catalogue(self):
        """Open the Satellite STAC Importer plugin for immutable catalogue publishing.

        Looks for the plugin in QGIS plugin registry.  If it is loaded, calls
        its ``run()`` method to open the dialog.  If it is not installed, shows
        a message box with the download / repository link.
        """
        _PLUGIN_KEY = 'satellite_stac_importer'
        _PLUGIN_NAME = 'Satellite STAC Importer'
        _PLUGIN_URL = 'https://github.com/luciocola/satellite_stac_importer'

        try:
            import qgis.utils as _qu
            plugin_instance = _qu.plugins.get(_PLUGIN_KEY)
        except Exception:
            plugin_instance = None

        if plugin_instance is not None:
            try:
                plugin_instance.run()
            except Exception as exc:
                QMessageBox.warning(
                    self, f'{_PLUGIN_NAME} Error',
                    f'Could not open {_PLUGIN_NAME}:\n{exc}'
                )
            return

        # Plugin not available — offer download
        msg = QMessageBox(self)
        msg.setWindowTitle('Satellite STAC Importer Not Found')
        msg.setIcon(QMessageBox.Question)
        msg.setText(
            f'<b>{_PLUGIN_NAME}</b> is not installed or not enabled in QGIS.<br><br>'
            'This plugin is required to publish to an immutable STAC catalogue '
            '(IPFS + blockchain provenance).'
        )
        msg.setInformativeText(
            f'Repository: <a href="{_PLUGIN_URL}">{_PLUGIN_URL}</a><br><br>'
            'To install it:<br>'
            '1. Download the ZIP from the repository<br>'
            '2. In QGIS: <i>Plugins → Manage and Install Plugins → '
            'Install from ZIP</i><br>'
            '3. Restart QGIS and enable the plugin'
        )
        btn_open = msg.addButton('Open Repository…', QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Close)
        msg.exec_()
        if msg.clickedButton() == btn_open:
            try:
                from PyQt5.QtGui import QDesktopServices
                from PyQt5.QtCore import QUrl
                QDesktopServices.openUrl(QUrl(_PLUGIN_URL))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # OSM context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _osm_sidecar_path(provenance_json_path: str) -> str:
        """Return the expected ``_osm_context.geojson`` path next to *provenance_json_path*."""
        stem = provenance_json_path.replace('_provenance.json', '')
        return stem + '_osm_context.geojson'

    def query_osm_context(self):
        """
        Query Overpass for the image bounding box and save an OSM context
        GeoJSON sidecar.  Updates ``_provenance.json`` with an ``osm_context``
        key and enables the *Load OSM Layers* button.
        """
        import json as _json

        if not self.loaded_provenance_data or not self.loaded_provenance_path:
            QMessageBox.warning(self, 'No Provenance Loaded',
                                'Please load a provenance file first.')
            return

        data = self.loaded_provenance_data
        output_file = data.get('output_file', '')
        provenance_dir = os.path.dirname(self.loaded_provenance_path)
        raster_path = os.path.join(provenance_dir, output_file)

        if not os.path.exists(raster_path):
            QMessageBox.warning(self, 'Raster Not Found',
                                f'Cannot derive bounding box — raster not found:\n{raster_path}')
            return

        # Extract bbox from the raster via the STAC converter helper
        try:
            from .stac_converter import ProvenanceToSTACConverter
            bbox, _ = ProvenanceToSTACConverter()._extract_bbox_and_geometry(raster_path)
        except Exception as exc:
            QMessageBox.critical(self, 'Bbox Extraction Failed',
                                 f'Could not extract bounding box from raster:\n{exc}')
            return

        osm_path = self._osm_sidecar_path(self.loaded_provenance_path)

        # Provide feedback via the status label during the blocking HTTP call
        if hasattr(self, 'lblProvenanceStatus'):
            self.lblProvenanceStatus.setText('Querying Overpass API…  (may take up to 45 s)')

        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from .osm_fetcher import OSMContextFetcher
            fetcher = OSMContextFetcher()
            osm_meta = fetcher.fetch(
                bbox=bbox,
                output_geojson_path=osm_path,
                progress_callback=lambda msg: (
                    hasattr(self, 'lblProvenanceStatus') and
                    self.lblProvenanceStatus.setText(msg)
                ) or None,
            )
        except Exception as exc:
            if hasattr(self, 'lblProvenanceStatus'):
                self.lblProvenanceStatus.setText('OSM query failed — see error dialog.')
            QMessageBox.critical(self, 'OSM Query Failed',
                                 f'Could not fetch OSM context data:\n{exc}')
            return

        # Persist osm_context reference into the _provenance.json sidecar
        data['osm_context'] = osm_meta
        self.loaded_provenance_data = data
        try:
            with open(self.loaded_provenance_path, 'w', encoding='utf-8') as fh:
                _json.dump(data, fh, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, 'Provenance Update Failed',
                                f'OSM metadata fetched but could not update provenance JSON:\n{exc}')

        # Update UI
        counts = osm_meta.get('feature_counts', {})
        total = sum(counts.values())
        count_str = ', '.join(f'{v} {k}s' for k, v in counts.items() if v)
        if hasattr(self, 'lblProvenanceStatus'):
            self.lblProvenanceStatus.setText(
                f'OSM context saved — {total} features ({count_str})'
            )
        if hasattr(self, 'btnLoadOSMLayers'):
            self.btnLoadOSMLayers.setEnabled(True)

        QMessageBox.information(
            self, 'OSM Context Fetched',
            f'OSM context saved to:\n{osm_path}\n\n'
            f'Total features: {total}\n{count_str}\n\n'
            f'Click "Load OSM Layers in Map" to add them to the QGIS canvas.'
        )

    def load_osm_layers_to_map(self):
        """
        Load the OSM context GeoJSON sidecar into the QGIS map canvas as separate
        vector layers per feature type, grouped under an *OSM Context* layer group.
        """
        if not self.loaded_provenance_path:
            QMessageBox.warning(self, 'No Provenance Loaded',
                                'Please load a provenance file first.')
            return

        osm_path = self._osm_sidecar_path(self.loaded_provenance_path)

        # Fall back: check osm_context.file key in loaded data
        if not os.path.exists(osm_path) and self.loaded_provenance_data:
            ctx = self.loaded_provenance_data.get('osm_context', {})
            alt = os.path.join(os.path.dirname(self.loaded_provenance_path),
                               ctx.get('file', ''))
            if os.path.exists(alt):
                osm_path = alt

        if not os.path.exists(osm_path):
            QMessageBox.warning(self, 'OSM Sidecar Not Found',
                                f'No OSM context file found at:\n{osm_path}\n\n'
                                'Run "Query OSM Context..." first.')
            return

        # Import QGIS classes (only available inside QGIS)
        try:
            from qgis.core import QgsVectorLayer, QgsProject
        except ImportError:
            QMessageBox.critical(self, 'QGIS Not Available',
                                 'QGIS core libraries are not available.')
            return

        # Feature types to split into individual layers
        LAYER_SPECS = [
            ('road',     'Roads (highway)'),
            ('building', 'Buildings'),
            ('landuse',  'Land Use'),
            ('waterway', 'Waterways'),
        ]

        # Read and split the GeoJSON by feature_type in Python so that each
        # sub-layer gets its own filtered file — avoids the unreliable OGR
        # setSubsetString behaviour on GeoJSON providers.
        import json as _json_osm
        with open(osm_path, encoding='utf-8') as _fh:
            osm_data = _json_osm.load(_fh)

        all_features = osm_data.get('features', [])
        osm_dir = os.path.dirname(osm_path)
        osm_stem = os.path.splitext(os.path.basename(osm_path))[0]

        # Create a layer tree group for OSM context
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group_name = f'OSM Context — {osm_stem}'

        # Remove any existing group with the same name to avoid duplicates
        existing = root.findGroup(group_name)
        if existing:
            root.removeChildNode(existing)

        group = root.insertGroup(0, group_name)
        loaded_count = 0

        for feature_type, layer_label in LAYER_SPECS:
            typed_features = [
                f for f in all_features
                if f.get('properties', {}).get('feature_type') == feature_type
            ]
            if not typed_features:
                continue

            # Normalise geometries to a single type per layer so QGIS OGR
            # can determine the layer geometry type correctly.
            # Roads/waterways → LineString; buildings/landuse → Polygon.
            # Closed-way roads (roundabouts) come back as Polygon in the OSM
            # response; we extract their exterior ring as a LineString so the
            # whole layer stays homogeneous and QGIS renders it as lines.
            line_types = {'road', 'waterway'}
            normalised = []
            for feat in typed_features:
                geom = feat.get('geometry') or {}
                gtype = geom.get('type', '')
                coords = geom.get('coordinates')
                if feature_type in line_types:
                    # Ensure geometry is LineString or MultiLineString
                    if gtype == 'Polygon' and coords:
                        # Extract exterior ring as LineString
                        ring = coords[0]
                        if len(ring) >= 2:
                            feat = dict(feat)
                            feat['geometry'] = {'type': 'LineString', 'coordinates': ring}
                        else:
                            continue  # degenerate, skip
                    elif gtype == 'MultiLineString':
                        pass  # fine as-is
                    elif gtype == 'LineString':
                        if not coords or len(coords) < 2:
                            continue  # degenerate, skip
                    elif gtype not in ('LineString', 'MultiLineString'):
                        continue  # skip Points / unknown
                else:
                    # Polygon types — skip non-polygon geometries
                    if gtype not in ('Polygon', 'MultiPolygon'):
                        continue
                normalised.append(feat)

            if not normalised:
                continue

            # Write a small filtered GeoJSON file alongside the main sidecar
            typed_path = os.path.join(osm_dir, f'{osm_stem}_{feature_type}.geojson')
            typed_fc = {'type': 'FeatureCollection', 'features': normalised}
            with open(typed_path, 'w', encoding='utf-8') as _fh:
                _json_osm.dump(typed_fc, _fh)

            layer = QgsVectorLayer(typed_path, layer_label, 'ogr')
            if not layer.isValid():
                continue

            project.addMapLayer(layer, False)  # register without adding to root
            group.addLayer(layer)
            loaded_count += 1

        if loaded_count == 0:
            root.removeChildNode(group)
            QMessageBox.warning(self, 'No Layers Loaded',
                                'The OSM context file was found but no features could be loaded.\n'
                                'The file may be empty for this bounding box.')
            return

        # Refresh the canvas so the new layers render immediately
        try:
            from qgis.utils import iface
            if iface:
                iface.mapCanvas().refresh()
        except Exception:
            pass

        if hasattr(self, 'lblProvenanceStatus'):
            self.lblProvenanceStatus.setText(
                f'OSM context loaded — {loaded_count} layer(s) added to map.'
            )

        QMessageBox.information(
            self, 'OSM Layers Loaded',
            f'{loaded_count} layer(s) added to the map canvas under the group:\n"{group_name}"'
        )

    # ------------------------------------------------------------------

    def create_package(self):
        """Create a ZIP package with GeoTIFF, JSON, RDF, and original HEIF"""
        if not self.last_export_path or not os.path.exists(self.last_export_path):
            QMessageBox.warning(
                self,
                'No Export Available',
                'Please run the import process first to generate files.'
            )
            return
        
        try:
            import zipfile
            
            # Get base name and directory
            base_path = self.last_export_path.replace('.tif', '')
            output_dir = os.path.dirname(self.last_export_path)
            base_name = os.path.basename(base_path)
            
            # Suggest ZIP file name
            from PyQt5.QtWidgets import QFileDialog
            zip_path, _ = QFileDialog.getSaveFileName(
                self,
                'Save Package As',
                os.path.join(output_dir, f"{base_name}_package.zip"),
                'ZIP Files (*.zip)'
            )
            
            if not zip_path:
                return
            
            # Collect files to include
            files_to_zip = []
            
            # 1. GeoTIFF output
            if os.path.exists(self.last_export_path):
                files_to_zip.append((self.last_export_path, os.path.basename(self.last_export_path)))
            
            # 2. JSON provenance
            json_file = base_path + '_provenance.json'
            if os.path.exists(json_file):
                files_to_zip.append((json_file, os.path.basename(json_file)))
            
            # 3. RDF/TTL provenance
            ttl_file = base_path + '_provenance.ttl'
            if os.path.exists(ttl_file):
                files_to_zip.append((ttl_file, os.path.basename(ttl_file)))
            
            # 4. Original HEIF file
            heif_path = self.txtHEIFPath.text()
            if heif_path and os.path.exists(heif_path):
                files_to_zip.append((heif_path, 'original_' + os.path.basename(heif_path)))
            
            # 5. External TTL metadata (if used)
            ttl_path = self.txtTTLPath.text()
            if ttl_path and os.path.exists(ttl_path):
                files_to_zip.append((ttl_path, 'metadata_' + os.path.basename(ttl_path)))
            
            # Create ZIP archive
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path, arcname in files_to_zip:
                    zipf.write(file_path, arcname)
            
            # Calculate ZIP size
            zip_size = os.path.getsize(zip_path)
            zip_size_mb = zip_size / (1024 * 1024)
            
            QMessageBox.information(
                self,
                'Package Created',
                f'Successfully created package:\n\n'
                f'File: {os.path.basename(zip_path)}\n'
                f'Size: {zip_size_mb:.2f} MB\n'
                f'Files included: {len(files_to_zip)}\n\n'
                f'Location: {zip_path}'
            )
        
        except Exception as e:
            QMessageBox.critical(
                self,
                'Package Error',
                f'Error creating package:\n{str(e)}'
            )
    
    def refresh_raster_layers(self):
        """Refresh the list of loaded raster layers"""
        if not hasattr(self, 'comboGeoTIFFSource'):
            print("DEBUG: comboGeoTIFFSource not found in dialog")
            return
        
        try:
            from qgis.core import QgsProject, QgsRasterLayer
            
            print("DEBUG: Starting to refresh raster layers")
            
            # Store current selection
            current_text = self.comboGeoTIFFSource.currentText()
            
            # Clear and repopulate
            self.comboGeoTIFFSource.clear()
            self.comboGeoTIFFSource.addItem('Browse for file...')
            
            # Add loaded raster layers
            project = QgsProject.instance()
            all_layers = project.mapLayers()
            print(f"DEBUG: Total layers in project: {len(all_layers)}")
            
            raster_count = 0
            for layer_id, layer in all_layers.items():
                print(f"DEBUG: Checking layer: {layer.name()}, Type: {type(layer).__name__}, Valid: {layer.isValid()}")
                if isinstance(layer, QgsRasterLayer) and layer.isValid():
                    # Store layer ID in user data
                    self.comboGeoTIFFSource.addItem(layer.name(), layer_id)
                    raster_count += 1
                    print(f"DEBUG: Added raster layer: {layer.name()}")
            
            print(f"DEBUG: Found {raster_count} raster layers")
            
            # Restore selection if possible
            index = self.comboGeoTIFFSource.findText(current_text)
            if index >= 0:
                self.comboGeoTIFFSource.setCurrentIndex(index)
            
            # Update status
            if raster_count > 0 and hasattr(self, 'txtGeoTIFFPath'):
                self.txtGeoTIFFPath.setPlaceholderText(f'{raster_count} raster layer(s) available in project')
            elif hasattr(self, 'txtGeoTIFFPath'):
                self.txtGeoTIFFPath.setPlaceholderText('No raster layers loaded in QGIS project')
        
        except ImportError as e:
            print(f"Error importing QGIS modules: {e}")
            if hasattr(self, 'txtGeoTIFFPath'):
                self.txtGeoTIFFPath.setPlaceholderText('QGIS not available - use Browse button')
        except Exception as e:
            print(f"Error refreshing raster layers: {e}")
            import traceback
            traceback.print_exc()
    
    def on_geotiff_source_changed(self, index):
        """Handle GeoTIFF source selection change"""
        if not hasattr(self, 'comboGeoTIFFSource'):
            return
        
        try:
            if index == 0:
                # "Browse for file..." selected
                self.txtGeoTIFFPath.setText('')
                self.txtGeoTIFFPath.setReadOnly(False)
                return
            
            from qgis.core import QgsProject
            
            # Get layer from stored ID
            layer_id = self.comboGeoTIFFSource.currentData()
            if layer_id:
                project = QgsProject.instance()
                layer = project.mapLayer(layer_id)
                
                if layer and layer.isValid():
                    # Get the layer's source file path
                    source_path = layer.source()
                    
                    # Handle provider-specific paths (e.g., GDAL virtual datasets)
                    if '|' in source_path:
                        source_path = source_path.split('|')[0]
                    
                    self.txtGeoTIFFPath.setText(source_path)
                    self.txtGeoTIFFPath.setReadOnly(True)
                    
                    # Auto-suggest output path
                    if os.path.exists(source_path):
                        suggested_output = source_path.rsplit('.', 1)[0] + '_tb21.heif'
                        if hasattr(self, 'txtHEIFOutputPath'):
                            self.txtHEIFOutputPath.setText(suggested_output)
                else:
                    QMessageBox.warning(self, 'Layer Error', 
                                      'Selected layer is no longer valid. Please refresh the layer list.')
        
        except Exception as e:
            print(f"Error handling source change: {e}")
            import traceback
            traceback.print_exc()
    
    def browse_geotiff_for_source(self):
        """Browse for GeoTIFF file when browse button clicked in source row"""
        settings = QSettings()
        last_dir = settings.value('heif_ttl_importer/last_geotiff_dir', os.path.expanduser('~'))
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Select GeoTIFF File',
            last_dir,
            'GeoTIFF Files (*.tif *.tiff);;All Files (*.*)'
        )
        
        if file_path:
            # Set combo box to "Browse for file..." mode
            if hasattr(self, 'comboGeoTIFFSource'):
                self.comboGeoTIFFSource.setCurrentIndex(0)
            
            # Update the file path text field
            if hasattr(self, 'txtGeoTIFFPath'):
                self.txtGeoTIFFPath.setText(file_path)
                self.txtGeoTIFFPath.setReadOnly(False)
            
            settings.setValue('heif_ttl_importer/last_geotiff_dir', os.path.dirname(file_path))
            
            # Auto-suggest output path
            suggested_output = file_path.rsplit('.', 1)[0] + '_tb21.heif'
            if hasattr(self, 'txtHEIFOutputPath'):
                self.txtHEIFOutputPath.setText(suggested_output)
    
    def browse_geotiff_export(self):
        """Browse for GeoTIFF file to export to TB21 HEIF"""
        settings = QSettings()
        last_dir = settings.value('heif_ttl_importer/last_geotiff_dir', os.path.expanduser('~'))
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Select GeoTIFF to Export',
            last_dir,
            'GeoTIFF Files (*.tif *.tiff);;All Files (*.*)'
        )
        
        if file_path:
            # Set to "Browse for file..." mode
            if hasattr(self, 'comboGeoTIFFSource'):
                self.comboGeoTIFFSource.setCurrentIndex(0)
            
            self.txtGeoTIFFPath.setText(file_path)
            self.txtGeoTIFFPath.setReadOnly(False)
            settings.setValue('heif_ttl_importer/last_geotiff_dir', os.path.dirname(file_path))
            
            # Auto-suggest output path
            suggested_output = file_path.rsplit('.', 1)[0] + '_tb21.heif'
            if hasattr(self, 'txtHEIFOutputPath'):
                self.txtHEIFOutputPath.setText(suggested_output)
    
    def browse_heif_output(self):
        """Browse for output HEIF file location"""
        settings = QSettings()
        last_dir = settings.value('heif_ttl_importer/last_export_dir', os.path.expanduser('~'))
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            'Save TB21 HEIF As',
            last_dir,
            'HEIF Files (*.heif *.heic);;All Files (*.*)'
        )
        
        if file_path:
            if not file_path.lower().endswith(('.heif', '.heic')):
                file_path += '.heif'
            self.txtHEIFOutputPath.setText(file_path)
            settings.setValue('heif_ttl_importer/last_export_dir', os.path.dirname(file_path))
    
    def export_to_tb21_heif(self):
        """Export GeoTIFF to TB21 GIMI compliant HEIF"""
        from .heif_processor import HEIFProcessor
        
        # Get paths
        geotiff_path = self.txtGeoTIFFPath.text().strip()
        heif_output = self.txtHEIFOutputPath.text().strip()
        
        if not geotiff_path or not os.path.exists(geotiff_path):
            QMessageBox.warning(
                self,
                'Input Required',
                'Please select a valid GeoTIFF file to export.'
            )
            return
        
        if not heif_output:
            QMessageBox.warning(
                self,
                'Output Required',
                'Please specify an output HEIF file path.'
            )
            return
        
        # Get export settings
        quality = self.spinQuality.value() if hasattr(self, 'spinQuality') else 95
        compression = self.comboCompression.currentText() if hasattr(self, 'comboCompression') else 'hevc'
        embed_rdf = self.chkEmbedRDF.isChecked() if hasattr(self, 'chkEmbedRDF') else True
        
        # Disable export button during processing
        if hasattr(self, 'btnExportToHEIF'):
            self.btnExportToHEIF.setEnabled(False)
            self.btnExportToHEIF.setText('Exporting...')
        
        try:
            # Create processor and export
            processor = HEIFProcessor()
            
            # Check if heif-enc is available for RDF embedding
            if embed_rdf and not processor.check_heif_enc_available():
                reply = QMessageBox.question(
                    self,
                    'heif-enc Not Available',
                    'heif-enc command-line tool is not available. '
                    'The HEIF will be created WITHOUT embedded RDF metadata.\n\n'
                    'An external TTL file will be saved instead.\n\n'
                    'Continue anyway?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            
            # Perform export
            success, metadata = processor.export_geotiff_to_tb21_heif(
                geotiff_path,
                heif_output,
                quality=quality,
                compression=compression,
                embed_rdf=embed_rdf
            )
            
            if success:
                msg_parts = [
                    f'Successfully exported to TB21 GIMI HEIF:\n',
                    f'Output: {heif_output}',
                    f'GCPs: {metadata.get("gcp_count", "unknown")}',
                    f'RDF Size: {metadata.get("rdf_size", 0)} bytes',
                    f'Encoding: {metadata.get("encoding_method", "unknown")}'
                ]
                
                if metadata.get("external_ttl"):
                    msg_parts.append(f'\n⚠ External TTL: {os.path.basename(metadata["external_ttl"])}')
                
                if metadata.get("output_hash"):
                    msg_parts.append(f'BLAKE3: {metadata["output_hash"][:16]}...')
                
                QMessageBox.information(
                    self,
                    'Export Successful',
                    '\n'.join(msg_parts)
                )
            else:
                error_msg = metadata.get('error', 'Unknown error')
                QMessageBox.critical(
                    self,
                    'Export Failed',
                    f'Failed to export TB21 HEIF:\n\n{error_msg}'
                )
        
        except Exception as e:
            import traceback
            QMessageBox.critical(
                self,
                'Export Error',
                f'An error occurred during export:\n\n{str(e)}\n\n{traceback.format_exc()}'
            )
        
        finally:
            # Re-enable export button
            if hasattr(self, 'btnExportToHEIF'):
                self.btnExportToHEIF.setEnabled(True)
                self.btnExportToHEIF.setText('Export to TB21 HEIF')
            
    def process_complete(self, success=True):
        """Called when import process is complete"""
        self.ready_to_process = False
        # Re-enable Import button
        self.btnImport.setEnabled(True)
        self.btnImport.setText("Start Import")
        self.btnClose.setEnabled(True)
        if success:
            # Close dialog on success
            self.accept()
        # If not success, keep dialog open so user can try again
