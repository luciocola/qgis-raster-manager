# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Dialog for GIMI Imagery Workbench
"""
import os
from pathlib import Path
from PyQt5 import uic
from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt, QSettings, QTimer, QThread, pyqtSignal, QObject

from .ttl_parser import TTLParser

# Load UI file
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'heif_ttl_dialog_base.ui'))

# ── GDAL output-format registry ──────────────────────────────────────
# Maps the combo-box label to (gdal_driver_name, file_extension, default_creation_options)
GDAL_OUTPUT_FORMATS = {
    "GeoTIFF (.tif)":                         ("GTiff",       ".tif",  "COMPRESS=DEFLATE TILED=YES"),
    "Cloud-Optimised GeoTIFF (.tif)":         ("COG",         ".tif",  "COMPRESS=DEFLATE OVERVIEW_RESAMPLING=NEAREST"),
    # JP2GROK is the recommended JPEG-2000 driver since GDAL 3.13 (Grok library).
    # Requires GDAL ≥ 3.13 built with -DGDAL_USE_GROK=ON  and  Grok ≥ 20.3 installed.
    # Install on macOS: brew install grok  (https://github.com/GrokImageCompression/grok)
    "JPEG2000 – Grok JP2GROK (.jp2) ★":      ("JP2GROK",     ".jp2",  "REVERSIBLE=YES PLT=YES TLM=YES PROG=RLCP"),
    "JPEG2000 – OpenJPEG (.jp2)":             ("JP2OpenJPEG", ".jp2",  ""),
    "PNG (.png)":                              ("PNG",         ".png",  ""),
    "JPEG (.jpg)":                             ("JPEG",        ".jpg",  "QUALITY=95"),
    "HFA / ERDAS Imagine (.img)":             ("HFA",         ".img",  ""),
    "ECW (.ecw)":                              ("ECW",         ".ecw",  "TARGET=10"),
    "NITF (.ntf)":                             ("NITF",        ".ntf",  ""),
    "GeoPackage Raster (.gpkg)":              ("GPKG",        ".gpkg", ""),
    "ENVI (.img / .hdr)":                     ("ENVI",        ".img",  ""),
    "VRT (.vrt)":                              ("VRT",         ".vrt",  ""),
    "NetCDF (.nc)":                            ("netCDF",      ".nc",   ""),
    "HDF5 (.h5)":                              ("HDF5",        ".h5",   ""),
    "Zarr (.zarr)":                            ("Zarr",        ".zarr", ""),
    "MrSID (.sid)":                            ("MrSID",       ".sid",  ""),
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
# OGC Connected Systems API dialog
# ─────────────────────────────────────────────────────────────────────

class CSAPIDialog(QDialog):
    """
    Dialog for the OGC Connected Systems API (https://cs.ogc.secd.eu/api/1.0).

    Three tabs:
      1. Systems     – list / register drones
      2. Deployments – list / create missions
      3. Spatial     – load flight paths and observations into QGIS
    """

    DEFAULT_URL = "https://cs.ogc.secd.eu/api/1.0"

    def __init__(self, parent=None, prefill_dji_data: dict = None):
        super().__init__(parent)
        self._prefill = prefill_dji_data or {}
        self.setWindowTitle("OGC Connected Systems API")
        self.setMinimumSize(760, 540)
        self.resize(860, 620)
        self._build_ui()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
            QPushButton, QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
            QHeaderView, QTextEdit, QSizePolicy, QAbstractItemView,
            QFormLayout, QComboBox, QSplitter,
        )
        from PyQt5.QtCore import QSettings

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Config bar ────────────────────────────────────────────────
        cfg = QGroupBox("CS API Connection")
        cfg_form = QFormLayout(cfg)

        self._cs_le_url = QLineEdit(self.DEFAULT_URL)
        self._cs_le_url.setPlaceholderText("https://cs.ogc.secd.eu/api/1.0")
        cfg_form.addRow("Base URL:", self._cs_le_url)

        self._cs_le_token = QLineEdit()
        self._cs_le_token.setEchoMode(QLineEdit.Password)
        self._cs_le_token.setPlaceholderText("Bearer token (optional)")
        cfg_form.addRow("Token:", self._cs_le_token)

        ping_row = QHBoxLayout()
        self._cs_btn_ping = QPushButton("Test Connection")
        self._cs_btn_ping.setMaximumWidth(140)
        self._cs_btn_ping.clicked.connect(self._cs_test_connection)
        self._cs_lbl_ping = QLabel("")
        self._cs_lbl_ping.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        ping_row.addWidget(self._cs_btn_ping)
        ping_row.addWidget(self._cs_lbl_ping)
        cfg_form.addRow("", ping_row)
        root.addWidget(cfg)

        # ── Tabs ──────────────────────────────────────────────────────
        self._cs_tabs = QTabWidget()
        root.addWidget(self._cs_tabs, 1)

        self._build_systems_tab()
        self._build_deployments_tab()
        self._build_spatial_tab()

        # ── Bottom buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── Systems tab ───────────────────────────────────────────────────

    def _build_systems_tab(self):
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
            QHeaderView, QAbstractItemView, QFormLayout, QComboBox,
        )

        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # List section
        grp_list = QGroupBox("Registered Systems")
        vl = QVBoxLayout(grp_list)

        filter_row = QHBoxLayout()
        self._cs_sys_filter = QLineEdit()
        self._cs_sys_filter.setPlaceholderText("Filter by UID (optional)…")
        self._cs_btn_list_sys = QPushButton("Refresh")
        self._cs_btn_list_sys.clicked.connect(self._cs_list_systems)
        filter_row.addWidget(QLabel("UID:"))
        filter_row.addWidget(self._cs_sys_filter)
        filter_row.addWidget(self._cs_btn_list_sys)
        vl.addLayout(filter_row)

        self._cs_tbl_systems = QTableWidget(0, 5)
        self._cs_tbl_systems.setHorizontalHeaderLabels(
            ["CS ID", "UID", "Name", "Type", "Status"])
        hdr = self._cs_tbl_systems.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._cs_tbl_systems.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cs_tbl_systems.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._cs_tbl_systems.setAlternatingRowColors(True)
        self._cs_tbl_systems.setMaximumHeight(150)
        vl.addWidget(self._cs_tbl_systems)

        self._cs_lbl_systems_status = QLabel("")
        vl.addWidget(self._cs_lbl_systems_status)
        vbox.addWidget(grp_list)

        # Register section
        grp_reg = QGroupBox("Register New System (Drone)")
        form = QFormLayout(grp_reg)

        self._cs_sys_uid = QLineEdit()
        self._cs_sys_uid.setPlaceholderText("urn:drone:dji:mavic3-001")
        if self._prefill.get("drone_uid"):
            self._cs_sys_uid.setText(self._prefill["drone_uid"])
        form.addRow("UID *:", self._cs_sys_uid)

        self._cs_sys_name = QLineEdit()
        self._cs_sys_name.setPlaceholderText("DJI Mavic 3 – Unit 001")
        if self._prefill.get("drone_name"):
            self._cs_sys_name.setText(self._prefill["drone_name"])
        form.addRow("Name *:", self._cs_sys_name)

        self._cs_sys_make = QLineEdit("DJI")
        form.addRow("Make:", self._cs_sys_make)

        self._cs_sys_model = QLineEdit()
        self._cs_sys_model.setPlaceholderText("Mavic 3")
        if self._prefill.get("drone_model"):
            self._cs_sys_model.setText(self._prefill["drone_model"])
        form.addRow("Model:", self._cs_sys_model)

        self._cs_sys_serial = QLineEdit()
        self._cs_sys_serial.setPlaceholderText("Serial number")
        if self._prefill.get("drone_serial"):
            self._cs_sys_serial.setText(self._prefill["drone_serial"])
        form.addRow("Serial:", self._cs_sys_serial)

        reg_row = QHBoxLayout()
        self._cs_btn_register = QPushButton("Register System")
        self._cs_btn_register.setMinimumWidth(140)
        self._cs_btn_register.clicked.connect(self._cs_register_system)
        self._cs_lbl_reg_status = QLabel("")
        reg_row.addWidget(self._cs_btn_register)
        reg_row.addWidget(self._cs_lbl_reg_status)
        reg_row.addStretch()
        form.addRow("", reg_row)
        vbox.addWidget(grp_reg)
        vbox.addStretch()

        self._cs_tabs.addTab(tab, "Systems")

    # ── Deployments tab ───────────────────────────────────────────────

    def _build_deployments_tab(self):
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
            QHeaderView, QAbstractItemView, QFormLayout, QDateTimeEdit,
        )
        from PyQt5.QtCore import QDateTime

        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # List section
        grp_list = QGroupBox("Existing Deployments")
        vl = QVBoxLayout(grp_list)

        filter_row = QHBoxLayout()
        self._cs_dep_filter = QLineEdit()
        self._cs_dep_filter.setPlaceholderText("CS system ID (optional)…")
        self._cs_btn_list_dep = QPushButton("Refresh")
        self._cs_btn_list_dep.clicked.connect(self._cs_list_deployments)
        filter_row.addWidget(QLabel("System ID:"))
        filter_row.addWidget(self._cs_dep_filter)
        filter_row.addWidget(self._cs_btn_list_dep)
        vl.addLayout(filter_row)

        self._cs_tbl_dep = QTableWidget(0, 5)
        self._cs_tbl_dep.setHorizontalHeaderLabels(
            ["CS ID", "Name", "System ID", "Start", "End"])
        hdr = self._cs_tbl_dep.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._cs_tbl_dep.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cs_tbl_dep.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._cs_tbl_dep.setAlternatingRowColors(True)
        self._cs_tbl_dep.setMaximumHeight(140)
        vl.addWidget(self._cs_tbl_dep)
        self._cs_lbl_dep_list_status = QLabel("")
        vl.addWidget(self._cs_lbl_dep_list_status)
        vbox.addWidget(grp_list)

        # Create section
        grp_create = QGroupBox("Create Deployment")
        form = QFormLayout(grp_create)

        self._cs_dep_name = QLineEdit()
        self._cs_dep_name.setPlaceholderText("Survey Mission 01")
        if self._prefill.get("mission_name"):
            self._cs_dep_name.setText(self._prefill["mission_name"])
        form.addRow("Name *:", self._cs_dep_name)

        self._cs_dep_system_id = QLineEdit()
        self._cs_dep_system_id.setPlaceholderText(
            "CS system UUID (from Systems tab)")
        form.addRow("System ID *:", self._cs_dep_system_id)

        self._cs_dep_start = QDateTimeEdit(
            QDateTime.fromString(
                self._prefill.get("time_start", QDateTime.currentDateTimeUtc().toString("yyyy-MM-ddThh:mm:ssZ")),
                "yyyy-MM-ddThh:mm:ssZ"
            )
        )
        self._cs_dep_start.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._cs_dep_start.setCalendarPopup(True)
        form.addRow("Time Start:", self._cs_dep_start)

        self._cs_dep_end = QDateTimeEdit(
            QDateTime.fromString(
                self._prefill.get("time_end", QDateTime.currentDateTimeUtc().toString("yyyy-MM-ddThh:mm:ssZ")),
                "yyyy-MM-ddThh:mm:ssZ"
            )
        )
        self._cs_dep_end.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._cs_dep_end.setCalendarPopup(True)
        form.addRow("Time End:", self._cs_dep_end)

        create_row = QHBoxLayout()
        self._cs_btn_create_dep = QPushButton("Create Deployment")
        self._cs_btn_create_dep.setMinimumWidth(150)
        self._cs_btn_create_dep.clicked.connect(self._cs_create_deployment)
        self._cs_lbl_dep_status = QLabel("")
        create_row.addWidget(self._cs_btn_create_dep)
        create_row.addWidget(self._cs_lbl_dep_status)
        create_row.addStretch()
        form.addRow("", create_row)
        vbox.addWidget(grp_create)
        vbox.addStretch()

        self._cs_tabs.addTab(tab, "Deployments")

    # ── Spatial tab ───────────────────────────────────────────────────

    def _build_spatial_tab(self):
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
            QHeaderView, QAbstractItemView, QFormLayout, QSizePolicy,
        )

        tab = QWidget()
        vbox = QVBoxLayout(tab)

        # Flight path
        grp_fp = QGroupBox("Flight Path (reconstruct from telemetry)")
        fl = QFormLayout(grp_fp)

        self._cs_fp_system_id = QLineEdit()
        self._cs_fp_system_id.setPlaceholderText("CS system UUID")
        fl.addRow("System ID:", self._cs_fp_system_id)

        fp_row = QHBoxLayout()
        self._cs_btn_get_fp = QPushButton("Get Flight Path")
        self._cs_btn_get_fp.clicked.connect(self._cs_get_flight_path)
        self._cs_btn_load_fp = QPushButton("Load in QGIS")
        self._cs_btn_load_fp.setEnabled(False)
        self._cs_btn_load_fp.clicked.connect(self._cs_load_flight_path)
        fp_row.addWidget(self._cs_btn_get_fp)
        fp_row.addWidget(self._cs_btn_load_fp)
        fp_row.addStretch()
        fl.addRow("", fp_row)

        self._cs_lbl_fp_status = QLabel("")
        fl.addRow("", self._cs_lbl_fp_status)
        self._cs_flight_path_geojson = None
        vbox.addWidget(grp_fp)

        # Observations within area
        grp_obs = QGroupBox("Observations (spatial query)")
        obs_form = QFormLayout(grp_obs)

        bbox_row = QHBoxLayout()
        for attr, placeholder, lbl in [
            ("_cs_obs_west",  "-180", "W"),
            ("_cs_obs_south", "-90",  "S"),
            ("_cs_obs_east",  "180",  "E"),
            ("_cs_obs_north", "90",   "N"),
        ]:
            l = QLabel(lbl)
            l.setMaximumWidth(16)
            le = QLineEdit(placeholder)
            le.setMaximumWidth(80)
            setattr(self, attr, le)
            bbox_row.addWidget(l)
            bbox_row.addWidget(le)
        obs_form.addRow("BBox (W S E N):", bbox_row)

        obs_row = QHBoxLayout()
        self._cs_btn_get_obs = QPushButton("Query Observations")
        self._cs_btn_get_obs.clicked.connect(self._cs_query_observations)
        self._cs_btn_load_obs = QPushButton("Load in QGIS")
        self._cs_btn_load_obs.setEnabled(False)
        self._cs_btn_load_obs.clicked.connect(self._cs_load_observations)
        obs_row.addWidget(self._cs_btn_get_obs)
        obs_row.addWidget(self._cs_btn_load_obs)
        obs_row.addStretch()
        obs_form.addRow("", obs_row)

        self._cs_lbl_obs_status = QLabel("")
        obs_form.addRow("", self._cs_lbl_obs_status)
        self._cs_obs_data = None
        vbox.addWidget(grp_obs)

        # Active drones
        grp_active = QGroupBox("Active Drones (live positions)")
        active_vl = QVBoxLayout(grp_active)
        active_row = QHBoxLayout()
        self._cs_btn_active = QPushButton("Refresh Active Drones")
        self._cs_btn_active.clicked.connect(self._cs_get_active_drones)
        self._cs_btn_load_active = QPushButton("Load in QGIS")
        self._cs_btn_load_active.setEnabled(False)
        self._cs_btn_load_active.clicked.connect(self._cs_load_active_drones)
        active_row.addWidget(self._cs_btn_active)
        active_row.addWidget(self._cs_btn_load_active)
        active_row.addStretch()
        active_vl.addLayout(active_row)
        self._cs_lbl_active_status = QLabel("")
        active_vl.addWidget(self._cs_lbl_active_status)
        self._cs_active_drones = None
        vbox.addWidget(grp_active)

        vbox.addStretch()
        self._cs_tabs.addTab(tab, "Spatial / Observations")

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self):
        from PyQt5.QtCore import QSettings
        s = QSettings("4113Eng", "GeneralRasterImporter")
        url = s.value("csapi/base_url", self.DEFAULT_URL)
        token = s.value("csapi/token", "")
        self._cs_le_url.setText(url)
        self._cs_le_token.setText(token)

    def _save_settings(self):
        from PyQt5.QtCore import QSettings
        s = QSettings("4113Eng", "GeneralRasterImporter")
        s.setValue("csapi/base_url", self._cs_le_url.text().strip())
        s.setValue("csapi/token", self._cs_le_token.text().strip())

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------

    def _client(self):
        try:
            from .cs_api_client import CSAPIClient
        except ImportError:
            from cs_api_client import CSAPIClient
        # _cs_le_url may not exist when called from the DJI tab before the CS
        # tab has been fully initialised (or in a dialog subclass without a CS tab).
        url = getattr(self, '_cs_le_url', None)
        url = url.text().strip() if url is not None else ''
        url = url or self.DEFAULT_URL
        tok = getattr(self, '_cs_le_token', None)
        token = (tok.text().strip() or None) if tok is not None else None
        return CSAPIClient(url, token=token)

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def _cs_test_connection(self):
        from PyQt5.QtWidgets import QApplication
        self._cs_lbl_ping.setText("Testing…")
        QApplication.processEvents()
        try:
            client = self._client()
            resp = client.get("/")
            title = resp.get("title", "OK")
            self._cs_lbl_ping.setText(f"✓ Connected: {title}")
        except Exception as exc:
            self._cs_lbl_ping.setText(f"✗ {exc}")

    # ------------------------------------------------------------------
    # Systems
    # ------------------------------------------------------------------

    def _cs_list_systems(self):
        from PyQt5.QtWidgets import QApplication, QTableWidgetItem
        uid_filter = self._cs_sys_filter.text().strip() or None
        self._cs_lbl_systems_status.setText("Loading…")
        QApplication.processEvents()
        try:
            items = self._client().list_systems(uid=uid_filter, limit=100)
            self._cs_tbl_systems.setRowCount(0)
            for item in items:
                props = item.get("properties", {})
                row = self._cs_tbl_systems.rowCount()
                self._cs_tbl_systems.insertRow(row)
                vals = [
                    str(item.get("id", "")),
                    str(props.get("uid", item.get("uid", ""))),
                    str(props.get("name", item.get("name", ""))),
                    str(props.get("type", item.get("type", ""))),
                    str(props.get("status", item.get("status", ""))),
                ]
                for col, v in enumerate(vals):
                    self._cs_tbl_systems.setItem(row, col, QTableWidgetItem(v))
            self._cs_lbl_systems_status.setText(f"{len(items)} system(s)")
        except Exception as exc:
            self._cs_lbl_systems_status.setText(f"Error: {exc}")

    def _cs_register_system(self):
        from PyQt5.QtWidgets import QApplication
        uid = self._cs_sys_uid.text().strip()
        name = self._cs_sys_name.text().strip()
        if not uid or not name:
            self._cs_lbl_reg_status.setText("⚠ UID and Name are required.")
            return
        self._cs_lbl_reg_status.setText("Registering…")
        QApplication.processEvents()
        body = {
            "uid": uid,
            "name": name,
            "type": "drone",
            "status": "inactive",
            "properties": {
                "make": self._cs_sys_make.text().strip() or "DJI",
                "model": self._cs_sys_model.text().strip(),
                "serial": self._cs_sys_serial.text().strip(),
            },
        }
        try:
            result = self._client().register_system(body)
            cs_id = result.get("id", result.get("properties", {}).get("id", "?"))
            self._cs_lbl_reg_status.setText(f"✓ Created — CS ID: {cs_id}")
            self._cs_dep_system_id.setText(str(cs_id))
            self._cs_list_systems()
        except Exception as exc:
            self._cs_lbl_reg_status.setText(f"✗ {exc}")

    # ------------------------------------------------------------------
    # Deployments
    # ------------------------------------------------------------------

    def _cs_list_deployments(self):
        from PyQt5.QtWidgets import QApplication, QTableWidgetItem
        sys_filter = self._cs_dep_filter.text().strip() or None
        self._cs_lbl_dep_list_status.setText("Loading…")
        QApplication.processEvents()
        try:
            items = self._client().list_deployments(system_id=sys_filter, limit=100)
            self._cs_tbl_dep.setRowCount(0)
            for item in items:
                props = item.get("properties", {})
                row = self._cs_tbl_dep.rowCount()
                self._cs_tbl_dep.insertRow(row)
                vals = [
                    str(item.get("id", "")),
                    str(props.get("name", item.get("name", ""))),
                    str(props.get("systemId", item.get("systemId", ""))),
                    str(item.get("timeStart", props.get("timeStart", ""))[:19]
                        if item.get("timeStart") or props.get("timeStart") else ""),
                    str(item.get("timeEnd", props.get("timeEnd", ""))[:19]
                        if item.get("timeEnd") or props.get("timeEnd") else ""),
                ]
                for col, v in enumerate(vals):
                    self._cs_tbl_dep.setItem(row, col, QTableWidgetItem(v))
            self._cs_lbl_dep_list_status.setText(f"{len(items)} deployment(s)")
        except Exception as exc:
            self._cs_lbl_dep_list_status.setText(f"Error: {exc}")

    def _cs_create_deployment(self):
        from PyQt5.QtWidgets import QApplication
        name = self._cs_dep_name.text().strip()
        system_id = self._cs_dep_system_id.text().strip()
        if not name or not system_id:
            self._cs_lbl_dep_status.setText("⚠ Name and System ID are required.")
            return
        import uuid as _uuid
        time_start = self._cs_dep_start.dateTime().toUTC().toString("yyyy-MM-ddThh:mm:ssZ")
        time_end   = self._cs_dep_end.dateTime().toUTC().toString("yyyy-MM-ddThh:mm:ssZ")
        dep_uid = f"urn:deployment:{system_id[:8]}:{_uuid.uuid4().hex[:8]}"
        body: dict = {
            "uid": dep_uid,
            "name": name,
            "systemId": system_id,
            "timeStart": time_start,
            "timeEnd": time_end,
            "properties": dict(self._prefill.get("extra_properties", {})),
        }
        if self._prefill.get("flight_path_geojson"):
            body["properties"]["flightPath"] = self._prefill["flight_path_geojson"]
        self._cs_lbl_dep_status.setText("Creating…")
        QApplication.processEvents()
        try:
            result = self._client().create_deployment(body)
            dep_id = result.get("id", result.get("properties", {}).get("id", "?"))
            self._cs_lbl_dep_status.setText(f"✓ Created — CS ID: {dep_id}")
            self._cs_list_deployments()
        except Exception as exc:
            self._cs_lbl_dep_status.setText(f"✗ {exc}")

    # ------------------------------------------------------------------
    # Spatial
    # ------------------------------------------------------------------

    def _cs_get_flight_path(self):
        from PyQt5.QtWidgets import QApplication
        system_id = self._cs_fp_system_id.text().strip()
        if not system_id:
            self._cs_lbl_fp_status.setText("⚠ Enter a system ID.")
            return
        self._cs_lbl_fp_status.setText("Fetching…")
        QApplication.processEvents()
        try:
            result = self._client().get_flight_path(system_id)
            if not result:
                self._cs_lbl_fp_status.setText("No flight path data returned.")
                return
            coords = (
                result.get("coordinates")
                or result.get("geometry", {}).get("coordinates")
                or []
            )
            self._cs_flight_path_geojson = result
            self._cs_lbl_fp_status.setText(f"✓ {len(coords)} points")
            self._cs_btn_load_fp.setEnabled(True)
        except Exception as exc:
            self._cs_lbl_fp_status.setText(f"✗ {exc}")

    def _cs_load_flight_path(self):
        if not self._cs_flight_path_geojson:
            return
        self._load_geojson_to_qgis(
            self._cs_flight_path_geojson,
            f"flight_path_{self._cs_fp_system_id.text().strip()[:8]}",
        )

    def _cs_query_observations(self):
        from PyQt5.QtWidgets import QApplication
        try:
            bbox = [
                float(self._cs_obs_west.text()),
                float(self._cs_obs_south.text()),
                float(self._cs_obs_east.text()),
                float(self._cs_obs_north.text()),
            ]
        except ValueError:
            self._cs_lbl_obs_status.setText("⚠ Invalid bounding box values.")
            return
        self._cs_lbl_obs_status.setText("Querying…")
        QApplication.processEvents()
        try:
            items = self._client().get_observations_within(bbox=bbox, limit=500)
            self._cs_obs_data = items
            self._cs_lbl_obs_status.setText(f"✓ {len(items)} observation(s)")
            self._cs_btn_load_obs.setEnabled(bool(items))
        except Exception as exc:
            self._cs_lbl_obs_status.setText(f"✗ {exc}")

    def _cs_load_observations(self):
        if not self._cs_obs_data:
            return
        # Convert observations list to GeoJSON FeatureCollection
        features = []
        for obs in self._cs_obs_data:
            lat = obs.get("latitude") or obs.get("lat")
            lon = obs.get("longitude") or obs.get("lon")
            if lat is None or lon is None:
                geom = obs.get("geometry")
                if geom:
                    coords = geom.get("coordinates", [])
                    if len(coords) >= 2:
                        lon, lat = coords[0], coords[1]
            if lat is None or lon is None:
                continue
            props = {k: v for k, v in obs.items()
                     if k not in ("geometry", "latitude", "longitude", "lat", "lon")}
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            })
        fc = {"type": "FeatureCollection", "features": features}
        self._load_geojson_to_qgis(fc, "cs_observations")

    def _cs_get_active_drones(self):
        from PyQt5.QtWidgets import QApplication
        self._cs_lbl_active_status.setText("Fetching…")
        QApplication.processEvents()
        try:
            drones = self._client().get_active_drones()
            self._cs_active_drones = drones
            self._cs_lbl_active_status.setText(f"✓ {len(drones)} active drone(s)")
            self._cs_btn_load_active.setEnabled(bool(drones))
        except Exception as exc:
            self._cs_lbl_active_status.setText(f"✗ {exc}")

    def _cs_load_active_drones(self):
        if not self._cs_active_drones:
            return
        features = []
        for item in self._cs_active_drones:
            geom = item.get("geometry")
            if not geom:
                props_inner = item.get("properties", {})
                lat = props_inner.get("latitude") or props_inner.get("lat")
                lon = props_inner.get("longitude") or props_inner.get("lon")
                if lat and lon:
                    geom = {"type": "Point", "coordinates": [lon, lat]}
            if not geom:
                continue
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": item.get("properties", {}),
            })
        fc = {"type": "FeatureCollection", "features": features}
        self._load_geojson_to_qgis(fc, "cs_active_drones")

    # ------------------------------------------------------------------
    # Helper – load GeoJSON into QGIS map
    # ------------------------------------------------------------------

    def _load_geojson_to_qgis(self, geojson: dict, layer_name: str):
        import json
        import tempfile
        import os
        try:
            from qgis.core import QgsProject, QgsVectorLayer
        except ImportError:
            QMessageBox.critical(self, "QGIS Not Available",
                                 "Cannot load layer: QGIS not running.")
            return
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False, encoding="utf-8")
        try:
            json.dump(geojson, tmp)
            tmp.close()
            lyr = QgsVectorLayer(tmp.name, layer_name, "ogr")
            if not lyr.isValid():
                QMessageBox.warning(self, "Layer Error", "Could not create QGIS layer.")
                return
            QgsProject.instance().addMapLayer(lyr)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────
# DJI processing worker (background thread)
# ─────────────────────────────────────────────────────────────────────

class _DJIWorker(QObject):
    """Runs GDALSimpleProcessor or NodeODMProcessor in a background thread."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)

    def __init__(self, processor):
        super().__init__()
        self._proc = processor

    def run(self):
        self._proc.progress_cb = lambda pct, msg: self.progress.emit(pct, msg)
        result = self._proc.run()
        self.finished.emit(result)

    def cancel(self):
        self._proc.cancelled = True
        if hasattr(self._proc, 'cancel'):
            self._proc.cancel()


# ─────────────────────────────────────────────────────────────────────

class HEIFTTLImporterDialog(QDialog, FORM_CLASS):
    """Dialog for importing HEIF imagery with TTL metadata"""

    DEFAULT_URL = "https://cs.ogc.secd.eu/api/1.0"

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
        self.btnClose.clicked.connect(self.close_dialog)
        
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
        if hasattr(self, 'btnStartImport'):
            self.btnStartImport.clicked.connect(self._on_start_import)
        if hasattr(self, 'btnSTACExportAction'):
            self.btnSTACExportAction.clicked.connect(self.open_ipfs_upload_dialog)
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

        # ── DJI Drone tab (added programmatically) ────────────────────
        self._dji_images = []
        self._dji_result = None
        self._dji_worker = None
        self._dji_thread = None
        self._dji_track_stac_path = None   # path to last exported STAC Item JSON
        self._dji_track_hash = None        # SHA-256 of last exported STAC Item
        self._setup_dji_tab()

        # ── HSI Hyperspectral tab (added programmatically) ─────────────
        self._setup_hsi_tab()

        # ── Sentinel-1 SAR tab (added programmatically) ────────────────
        self._sar_safe_path = None          # path to loaded .SAFE folder
        self._sar_meta = {}                 # parsed metadata dict
        self._sar_worker = None
        self._sar_thread = None
        self._setup_sar_tab()

        # ── Register / Settings tab (added programmatically) ────────────
        self._setup_register_settings_tab()

        # Ensure all tabs are visible without scroll arrows at startup
        self.setMinimumWidth(980)
        if self.width() < 1060:
            self.resize(1060, self.height())

    # ------------------------------------------------------------------
    # CS API client factory
    # ------------------------------------------------------------------

    def _client(self):
        """Return a CSAPIClient using the URL/token from the CS tab (if present)."""
        try:
            from .cs_api_client import CSAPIClient
        except ImportError:
            from cs_api_client import CSAPIClient
        url = getattr(self, '_cs_le_url', None)
        url = url.text().strip() if url is not None else ''
        url = url or self.DEFAULT_URL
        tok = getattr(self, '_cs_le_token', None)
        token = (tok.text().strip() or None) if tok is not None else None
        return CSAPIClient(url, token=token)

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
                    elif codec in ('jpeg2000', 'jp2 grok') and not has_jpeg2000:
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
                        if codec in ['jpeg2000', 'jp2 grok', 'htj2k'] and openjpeg_available:
                            tooltip += "\nOpenJPEG is installed - rebuild libheif with: cmake -DWITH_OpenJPEG=ON"
                        
                        item.setToolTip(tooltip)
                    
        except Exception as e:
            print(f"Could not check codec availability: {e}")

        # ── JP2 driver probe (GDAL) ────────────────────────────────────────
        # Detect which JPEG-2000 drivers are compiled into the running GDAL,
        # log the result, and annotate / disable the JP2GROK combo item if the
        # driver is absent (requires GDAL ≥ 3.13 + Grok ≥ 20.3).
        self._probe_jp2_drivers()
    
    def _probe_jp2_drivers(self):
        """Detect available GDAL JP2 drivers; annotate the JP2GROK combo item.

        * If JP2GROK is present  → tooltip confirms it is active and shows GDAL version.
        * If JP2GROK is absent   → item is grayed out with an install hint.
        * Reports GDAL version tuple to the Python console at startup.
        """
        try:
            from osgeo import gdal as _gdal
        except ImportError:
            return

        try:
            from .heif_processor import gdal_version_tuple, _gdal_has_driver
        except ImportError:
            try:
                from heif_processor import gdal_version_tuple, _gdal_has_driver  # type: ignore[no-redef]
            except ImportError:
                return

        ver = gdal_version_tuple()
        ver_str = f"{ver[0]}.{ver[1]}.{ver[2]}"
        print(f"[GIMI Imagery Workbench] GDAL version: {ver_str}")

        jp2_drivers = [d for d in ('JP2GROK', 'JP2KAK', 'JP2ECW', 'JP2OpenJPEG', 'JPEG2000')
                       if _gdal_has_driver(d)]
        print(f"[GIMI Imagery Workbench] Available JP2 drivers: {jp2_drivers or ['none']}")

        grok_ok = 'JP2GROK' in jp2_drivers
        grok_label = "JPEG2000 – Grok JP2GROK (.jp2) ★"

        # Update the cmbOutputFormat item (main import tab)
        if hasattr(self, 'cmbOutputFormat'):
            mdl = self.cmbOutputFormat.model()
            for i in range(self.cmbOutputFormat.count()):
                if self.cmbOutputFormat.itemText(i) == grok_label:
                    item = mdl.item(i)
                    if grok_ok:
                        item.setEnabled(True)
                        item.setToolTip(
                            f"Grok JP2GROK driver active  (GDAL {ver_str})\n"
                            "High-Throughput JPEG 2000 with TLM+PLT random-access markers.\n"
                            "Default creation options: REVERSIBLE=YES PLT=YES TLM=YES PROG=RLCP"
                        )
                    else:
                        item.setEnabled(False)
                        tip = (
                            f"JP2GROK driver not compiled into this GDAL build (GDAL {ver_str}).\n"
                            "To enable:\n"
                            "  1. Install Grok ≥ 20.3:\n"
                            "       macOS:  brew install grok\n"
                            "       Linux:  see https://github.com/GrokImageCompression/grok\n"
                            "  2. Obtain GDAL ≥ 3.13 built with -DGDAL_USE_GROK=ON\n"
                            "       macOS:  brew install gdal  (formula includes Grok since 3.13)\n"
                            "  3. Restart QGIS."
                        )
                        item.setToolTip(tip)
                    break

        # If Grok is available and GDAL < 3.13, warn in console
        if grok_ok and ver < (3, 13, 0):
            print(
                f"[GIMI Imagery Workbench] WARNING: JP2GROK found but GDAL {ver_str} < 3.13.0. "
                "Some JP2GROK creation options may not be supported. Upgrade to GDAL ≥ 3.13."
            )

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
            QMessageBox.warning(self, "GIMI Imagery Workbench", "Please select a valid source raster file.")
            return
        if not dst:
            QMessageBox.warning(self, "GIMI Imagery Workbench", "Please specify an output directory.")
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

        try:
            self.heif_processor.export_gdal(src, dst, driver, creation_opts)
            QMessageBox.information(self, "GIMI Imagery Workbench",
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
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _on_start_import(self):
        """Trigger the import process via the callback set by the plugin."""
        if callable(self.import_callback):
            self.import_callback()
        else:
            QMessageBox.information(
                self, 'Start Import',
                'No import callback is registered.\n\n'
                'Open this dialog through the GIMI Imagery Workbench toolbar button '
                'to activate the import function.')

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
    # IPFS Upload
    # ------------------------------------------------------------------

    def open_ipfs_upload_dialog(self):
        """Open the IPFS Upload dialog."""
        dlg = _IPFSUploadDialog(self)
        dlg.exec_()

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
        """Open the blockchain registration dialog."""
        dlg = _BlockchainRegisterDialog(self)
        dlg.exec_()

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
                    f'Successfully exported to GIMI HEIF:\n',
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
        self.btnClose.setEnabled(True)
        if success:
            # Close dialog on success
            self.accept()
        # If not success, keep dialog open so user can try again

    # ==================================================================
    # DJI DRONE TAB
    # ==================================================================

    def _setup_dji_tab(self):
        """Build the DJI Drone tab and append it to the existing tabWidget."""
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
            QHeaderView, QRadioButton, QProgressBar, QTextEdit,
            QButtonGroup, QSizePolicy, QAbstractItemView, QSpinBox,
            QScrollArea,
        )

        # Outer tab widget — just holds the scroll area
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        # Scroll area so all groups are accessible even at small window sizes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        # Inner content widget
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

        # ── 0. DJI Developer App Key ───────────────────────────────────
        grp_key = QGroupBox('DJI Developer App Key')
        gl_key = QVBoxLayout(grp_key)

        key_info = QLabel(
            '<b>A DJI Developer App Key is required to process DJI drone imagery.</b>'
            '<br/>Register at <a href="https://developer.dji.com/user/apps">'
            'https://developer.dji.com/user/apps</a> to obtain your key, then '
            'paste it below or add it to <tt>local_secrets.py</tt>.'
        )
        key_info.setWordWrap(True)
        key_info.setOpenExternalLinks(True)
        gl_key.addWidget(key_info)

        key_row = QHBoxLayout()
        self._dji_le_app_key = QLineEdit()
        self._dji_le_app_key.setPlaceholderText('Paste your DJI App Key here…')
        self._dji_le_app_key.setEchoMode(QLineEdit.Password)
        self._dji_btn_key_show = QPushButton('Show')
        self._dji_btn_key_show.setMaximumWidth(55)
        self._dji_btn_key_show.setCheckable(True)
        self._dji_btn_key_show.toggled.connect(
            lambda on: self._dji_le_app_key.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password)
        )
        self._dji_btn_key_save = QPushButton('Save to local_secrets.py')
        self._dji_btn_key_save.setMaximumWidth(180)
        self._dji_btn_key_save.clicked.connect(self._dji_save_app_key)
        key_row.addWidget(QLabel('App Key:'))
        key_row.addWidget(self._dji_le_app_key)
        key_row.addWidget(self._dji_btn_key_show)
        key_row.addWidget(self._dji_btn_key_save)
        gl_key.addLayout(key_row)

        self._dji_lbl_key_status = QLabel('')
        gl_key.addWidget(self._dji_lbl_key_status)

        root.addWidget(grp_key)

        # ── 1. Folder & mission ────────────────────────────────────────
        grp_folder = QGroupBox('DJI Image Folder')
        gl = QVBoxLayout(grp_folder)

        folder_row = QHBoxLayout()
        self._dji_le_folder = QLineEdit()
        self._dji_le_folder.setPlaceholderText('Select folder containing DJI JPEG images…')
        self._dji_btn_browse = QPushButton('Browse…')
        self._dji_btn_browse.setMaximumWidth(90)
        self._dji_btn_browse.setAutoDefault(False)
        self._dji_btn_browse.clicked.connect(self._dji_browse_folder)
        folder_row.addWidget(QLabel('Folder:'))
        folder_row.addWidget(self._dji_le_folder)
        folder_row.addWidget(self._dji_btn_browse)
        gl.addLayout(folder_row)

        mission_row = QHBoxLayout()
        self._dji_le_mission = QLineEdit()
        self._dji_le_mission.setPlaceholderText('mission_name  (used as output sub-folder)')
        self._dji_le_mission.setText('drone_mission_01')
        self._dji_btn_scan = QPushButton('Scan Images')
        self._dji_btn_scan.setMinimumWidth(110)
        self._dji_btn_scan.clicked.connect(self._dji_scan_images)
        mission_row.addWidget(QLabel('Mission:'))
        mission_row.addWidget(self._dji_le_mission)
        mission_row.addWidget(self._dji_btn_scan)
        gl.addLayout(mission_row)

        # ── Video scan row ─────────────────────────────────────────────
        video_row = QHBoxLayout()
        self._dji_le_video = QLineEdit()
        self._dji_le_video.setPlaceholderText('Optional: select DJI MP4 video to scan for GPS metadata…')
        self._dji_btn_browse_video = QPushButton('Browse…')
        self._dji_btn_browse_video.setMaximumWidth(90)
        self._dji_btn_browse_video.setAutoDefault(False)
        self._dji_btn_browse_video.clicked.connect(self._dji_browse_video)
        self._dji_btn_scan_video = QPushButton('Scan Video')
        self._dji_btn_scan_video.setMinimumWidth(100)
        self._dji_btn_scan_video.clicked.connect(self._dji_scan_video)
        self._dji_btn_center_gps = QPushButton('📍 Center GPS')
        self._dji_btn_center_gps.setToolTip(
            'Quickly extract a single GPS coordinate from the centre of the video\n'
            '(midpoint of the GPS track, or the centre video frame if no track found).')
        self._dji_btn_center_gps.setMinimumWidth(110)
        self._dji_btn_center_gps.clicked.connect(self._dji_get_center_gps)
        video_row.addWidget(QLabel('Video:'))
        video_row.addWidget(self._dji_le_video)
        video_row.addWidget(self._dji_btn_browse_video)
        video_row.addWidget(self._dji_btn_scan_video)
        video_row.addWidget(self._dji_btn_center_gps)
        gl.addLayout(video_row)

        # ── Sidecar GPS file row ───────────────────────────────────────
        sidecar_row = QHBoxLayout()
        self._dji_le_sidecar = QLineEdit()
        self._dji_le_sidecar.setPlaceholderText(
            'Optional: GPS sidecar (.SRT / .txt) — auto-detected if left blank')
        self._dji_btn_browse_sidecar = QPushButton('Browse…')
        self._dji_btn_browse_sidecar.setMaximumWidth(90)
        self._dji_btn_browse_sidecar.setAutoDefault(False)
        self._dji_btn_browse_sidecar.clicked.connect(self._dji_browse_sidecar)
        sidecar_row.addWidget(QLabel('Sidecar:'))
        sidecar_row.addWidget(self._dji_le_sidecar)
        sidecar_row.addWidget(self._dji_btn_browse_sidecar)
        gl.addLayout(sidecar_row)

        self._dji_lbl_scan_status = QLabel('No images scanned.')
        gl.addWidget(self._dji_lbl_scan_status)

        root.addWidget(grp_folder)

        # ── 2. Image table ─────────────────────────────────────────────
        grp_images = QGroupBox('Scanned DJI Images')
        grp_images.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        gl2 = QVBoxLayout(grp_images)
        self._dji_table = QTableWidget(0, 7)
        self._dji_table.setHorizontalHeaderLabels(
            ['Filename', 'Lat', 'Lon', 'Alt (m)', 'GSD (cm)', 'Datetime', 'Model'])
        hdr = self._dji_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 7):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._dji_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._dji_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._dji_table.setAlternatingRowColors(True)
        self._dji_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._dji_table.setMinimumHeight(80)
        gl2.addWidget(self._dji_table)
        root.addWidget(grp_images)

        # ── 3. Processing options ──────────────────────────────────────
        grp_proc = QGroupBox('Processing')
        gl3 = QVBoxLayout(grp_proc)

        self._dji_bg = QButtonGroup(grp_proc)
        self._dji_rb_gdal = QRadioButton('GDAL Simple (built-in, fast — GPS footprint georeferencing)')
        self._dji_rb_nodeodm = QRadioButton('NodeODM / WebODM (photogrammetric — requires running NodeODM server)')
        self._dji_rb_gdal.setChecked(True)
        self._dji_bg.addButton(self._dji_rb_gdal, 0)
        self._dji_bg.addButton(self._dji_rb_nodeodm, 1)
        gl3.addWidget(self._dji_rb_gdal)

        nodeodm_row = QHBoxLayout()
        nodeodm_row.addWidget(self._dji_rb_nodeodm)
        self._dji_le_nodeodm_url = QLineEdit('http://localhost:3000')
        self._dji_le_nodeodm_url.setMaximumWidth(240)
        self._dji_le_nodeodm_url.setEnabled(False)
        nodeodm_row.addWidget(QLabel('URL:'))
        nodeodm_row.addWidget(self._dji_le_nodeodm_url)
        nodeodm_row.addStretch()
        gl3.addLayout(nodeodm_row)
        self._dji_rb_nodeodm.toggled.connect(
            lambda on: self._dji_le_nodeodm_url.setEnabled(on))

        out_row = QHBoxLayout()
        self._dji_le_outdir = QLineEdit()
        self._dji_le_outdir.setPlaceholderText('Output directory (cesium dashboard drone_output_dir)…')
        import tempfile
        self._dji_le_outdir.setText(tempfile.gettempdir())
        self._dji_btn_outdir = QPushButton('Browse…')
        self._dji_btn_outdir.setMaximumWidth(90)
        self._dji_btn_outdir.clicked.connect(self._dji_browse_outdir)
        out_row.addWidget(QLabel('Output Directory:'))
        out_row.addWidget(self._dji_le_outdir)
        out_row.addWidget(self._dji_btn_outdir)
        gl3.addLayout(out_row)

        root.addWidget(grp_proc)

        # ── 4. Action row ─────────────────────────────────────────────
        act_row = QHBoxLayout()
        self._dji_btn_process = QPushButton('Process Drone Images/Video')
        self._dji_btn_process.setMinimumHeight(30)
        self._dji_btn_process.clicked.connect(self._dji_start_processing)
        self._dji_btn_cancel = QPushButton('Cancel')
        self._dji_btn_cancel.setEnabled(False)
        self._dji_btn_cancel.clicked.connect(self._dji_cancel_processing)
        act_row.addWidget(self._dji_btn_process)
        act_row.addWidget(self._dji_btn_cancel)
        act_row.addStretch()
        root.addLayout(act_row)

        self._dji_progress = QProgressBar()
        self._dji_progress.setRange(0, 100)
        self._dji_progress.setValue(0)
        self._dji_progress.setVisible(False)
        root.addWidget(self._dji_progress)

        # ── 5. Log ────────────────────────────────────────────────────
        grp_log = QGroupBox('Processing Log')
        grp_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        gl_log = QVBoxLayout(grp_log)
        self._dji_log = QTextEdit()
        self._dji_log.setReadOnly(True)
        self._dji_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._dji_log.setMinimumHeight(60)
        self._dji_log.setPlaceholderText('Processing log…')
        gl_log.addWidget(self._dji_log)
        root.addWidget(grp_log)

        # ── 6. Results ────────────────────────────────────────────────
        grp_res = QGroupBox('Results')
        gl_res = QHBoxLayout(grp_res)
        self._dji_btn_load_ortho = QPushButton('Load Orthophoto in QGIS')
        self._dji_btn_load_ortho.clicked.connect(self._dji_load_orthophoto)
        self._dji_btn_load_fp = QPushButton('Load Footprints in QGIS')
        self._dji_btn_load_fp.clicked.connect(self._dji_load_footprints)
        self._dji_btn_stac = QPushButton('Export STAC Item')
        self._dji_btn_stac.clicked.connect(self._dji_export_stac)
        self._dji_btn_csapi = QPushButton('Open CS API …')
        self._dji_btn_csapi.clicked.connect(self._open_cs_api_dialog)
        gl_res.addWidget(self._dji_btn_load_ortho)
        gl_res.addWidget(self._dji_btn_load_fp)
        gl_res.addWidget(self._dji_btn_stac)
        gl_res.addWidget(self._dji_btn_csapi)
        gl_res.addStretch()
        root.addWidget(grp_res)

        # ── Flight Track Registration (GeoJSON + STAC + Blockchain) ──
        grp_track = QGroupBox('Flight Track Registration')
        gl_track = QVBoxLayout(grp_track)

        # Row 1: export button + hash display
        track_row1 = QHBoxLayout()
        self._dji_btn_export_track = QPushButton('📋 Export Track GeoJSON + STAC')
        self._dji_btn_export_track.setToolTip(
            'Build a GeoJSON LineString and STAC Item from the scanned GPS points,\n'
            'compute a SHA-256 integrity hash, and save both files to the output directory.')
        self._dji_btn_export_track.clicked.connect(self._dji_export_flight_track)
        self._dji_lbl_track_hash = QLabel('BLAKE3: —')
        self._dji_lbl_track_hash.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._dji_lbl_track_hash.setWordWrap(True)
        track_row1.addWidget(self._dji_btn_export_track)
        track_row1.addWidget(self._dji_lbl_track_hash, 1)
        gl_track.addLayout(track_row1)

        # Row 2: blockchain API URL + anchor button
        track_row2 = QHBoxLayout()
        track_row2.addWidget(QLabel('Blockchain API:'))
        self._dji_le_blockchain_api = QLineEdit('http://localhost:8000')
        self._dji_le_blockchain_api.setPlaceholderText(
            'stac_imagery_api base URL  (http://localhost:8000)')
        track_row2.addWidget(self._dji_le_blockchain_api)
        gl_track.addLayout(track_row2)

        track_row3 = QHBoxLayout()
        self._dji_btn_anchor = QPushButton('⛓ Anchor on Blockchain')
        self._dji_btn_anchor.setToolTip(
            'POST the STAC item and SHA-256 hash to the blockchain anchor API.\n'
            'If the API is unavailable a local provenance record is saved instead.')
        self._dji_btn_anchor.clicked.connect(self._dji_anchor_blockchain)
        self._dji_lbl_anchor_result = QLabel('Tx: —')
        self._dji_lbl_anchor_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._dji_lbl_anchor_result.setWordWrap(True)
        track_row3.addWidget(self._dji_btn_anchor)
        track_row3.addWidget(self._dji_lbl_anchor_result, 1)
        gl_track.addLayout(track_row3)

        # Row 4: GIMI HEIF key-frame extraction (TB21 Option B)
        track_row4 = QHBoxLayout()
        self._dji_spin_gimi_frames = QSpinBox()
        self._dji_spin_gimi_frames.setRange(1, 60)
        self._dji_spin_gimi_frames.setValue(5)
        self._dji_spin_gimi_frames.setToolTip('Number of evenly-spaced key frames to extract')
        self._dji_spin_gimi_frames.setMaximumWidth(60)
        self._dji_btn_extract_gimi = QPushButton('🖼 Extract Frames → GIMI HEIF')
        self._dji_btn_extract_gimi.setToolTip(
            'Extract key frames from the DJI video and encode each as a\n'
            'TB21 GIMI HEIF file with embedded GPS-derived RDF/Turtle metadata.\n'
            'Requires ffmpeg, heif-enc and exiftool (Homebrew).')
        self._dji_btn_extract_gimi.clicked.connect(self._dji_extract_gimi_frames)
        self._dji_lbl_gimi_result = QLabel('GIMI: —')
        self._dji_lbl_gimi_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._dji_lbl_gimi_result.setWordWrap(True)
        track_row4.addWidget(QLabel('Frames:'))
        track_row4.addWidget(self._dji_spin_gimi_frames)
        track_row4.addWidget(self._dji_btn_extract_gimi)
        track_row4.addWidget(self._dji_lbl_gimi_result, 1)
        gl_track.addLayout(track_row4)

        root.addWidget(grp_track)

        # ── Stream imagery / video to CS deployment via MQTT ─────────
        grp_stream = QGroupBox('Stream to CS Deployment (MQTT)')
        gl_stream = QVBoxLayout(grp_stream)

        dep_row = QHBoxLayout()
        self._dji_stream_le_dep = QLineEdit()
        self._dji_stream_le_dep.setPlaceholderText(
            'Deployment UID  (e.g. urn:deployment:mission-01)')
        self._dji_stream_btn_dep = QPushButton('Pick …')
        self._dji_stream_btn_dep.setMaximumWidth(70)
        self._dji_stream_btn_dep.clicked.connect(self._dji_stream_pick_deployment)
        dep_row.addWidget(QLabel('Deployment:'))
        dep_row.addWidget(self._dji_stream_le_dep)
        dep_row.addWidget(self._dji_stream_btn_dep)

        broker_row = QHBoxLayout()
        self._dji_stream_le_broker = QLineEdit('localhost')
        self._dji_stream_le_port = QSpinBox()
        self._dji_stream_le_port.setRange(1, 65535)
        self._dji_stream_le_port.setValue(1883)
        self._dji_stream_le_port.setMaximumWidth(80)
        broker_row.addWidget(QLabel('MQTT broker:'))
        broker_row.addWidget(self._dji_stream_le_broker)
        broker_row.addWidget(QLabel('Port:'))
        broker_row.addWidget(self._dji_stream_le_port)

        topic_row = QHBoxLayout()
        self._dji_stream_le_topic = QLineEdit()
        self._dji_stream_le_topic.setPlaceholderText(
            'cs/deployments/{uid}/imagery  (auto-filled from deployment)')
        topic_row.addWidget(QLabel('Topic:'))
        topic_row.addWidget(self._dji_stream_le_topic)

        media_row = QHBoxLayout()
        self._dji_stream_le_media = QLineEdit()
        self._dji_stream_le_media.setPlaceholderText(
            'Image folder or video file to stream')
        self._dji_stream_btn_media = QPushButton('Browse…')
        self._dji_stream_btn_media.setMaximumWidth(90)
        self._dji_stream_btn_media.clicked.connect(self._dji_stream_browse_media)
        media_row.addWidget(self._dji_stream_le_media)
        media_row.addWidget(self._dji_stream_btn_media)

        fps_row = QHBoxLayout()
        self._dji_stream_spin_fps = QSpinBox()
        self._dji_stream_spin_fps.setRange(1, 30)
        self._dji_stream_spin_fps.setValue(5)
        self._dji_stream_spin_fps.setMaximumWidth(60)
        fps_row.addWidget(QLabel('Frame rate (img/s):'))
        fps_row.addWidget(self._dji_stream_spin_fps)
        fps_row.addStretch()

        stream_btn_row = QHBoxLayout()
        self._dji_btn_stream_start = QPushButton('▶ Start Streaming')
        self._dji_btn_stream_start.setMinimumHeight(28)
        self._dji_btn_stream_start.clicked.connect(self._dji_stream_start)
        self._dji_btn_stream_stop = QPushButton('■ Stop')
        self._dji_btn_stream_stop.setEnabled(False)
        self._dji_btn_stream_stop.clicked.connect(self._dji_stream_stop)
        stream_btn_row.addWidget(self._dji_btn_stream_start)
        stream_btn_row.addWidget(self._dji_btn_stream_stop)

        self._dji_lbl_stream_status = QLabel('Stream: idle')
        self._dji_lbl_stream_status.setTextInteractionFlags(Qt.TextSelectableByMouse)

        gl_stream.addLayout(dep_row)
        gl_stream.addLayout(broker_row)
        gl_stream.addLayout(topic_row)
        gl_stream.addLayout(media_row)
        gl_stream.addLayout(fps_row)
        gl_stream.addLayout(stream_btn_row)
        gl_stream.addWidget(self._dji_lbl_stream_status)
        root.addWidget(grp_stream)

        # internal streaming state
        self._dji_stream_timer = None
        self._dji_stream_files = []
        self._dji_stream_index = 0
        self._dji_mqtt_client = None

        # ── Monitor Stream (MQTT Subscriber) ──────────────────────────
        grp_monitor = QGroupBox('Monitor Stream (MQTT Subscriber)')
        gl_monitor = QVBoxLayout(grp_monitor)

        mon_broker_row = QHBoxLayout()
        self._dji_mon_le_broker = QLineEdit('localhost')
        self._dji_mon_le_port = QSpinBox()
        self._dji_mon_le_port.setRange(1, 65535)
        self._dji_mon_le_port.setValue(1883)
        self._dji_mon_le_port.setMaximumWidth(80)
        mon_broker_row.addWidget(QLabel('MQTT broker:'))
        mon_broker_row.addWidget(self._dji_mon_le_broker)
        mon_broker_row.addWidget(QLabel('Port:'))
        mon_broker_row.addWidget(self._dji_mon_le_port)

        mon_topic_row = QHBoxLayout()
        self._dji_mon_le_topic = QLineEdit()
        self._dji_mon_le_topic.setPlaceholderText('dji/stream/# — topic to subscribe to')
        mon_topic_row.addWidget(QLabel('Topic:'))
        mon_topic_row.addWidget(self._dji_mon_le_topic)

        mon_btn_row = QHBoxLayout()
        self._dji_btn_mon_start = QPushButton('▶ Start Monitoring')
        self._dji_btn_mon_start.setMinimumHeight(28)
        self._dji_btn_mon_start.clicked.connect(self._dji_monitor_start)
        self._dji_btn_mon_stop = QPushButton('■ Stop')
        self._dji_btn_mon_stop.setEnabled(False)
        self._dji_btn_mon_stop.clicked.connect(self._dji_monitor_stop)
        mon_btn_row.addWidget(self._dji_btn_mon_start)
        mon_btn_row.addWidget(self._dji_btn_mon_stop)

        self._dji_mon_lbl_frame = QLabel('No frame yet')
        self._dji_mon_lbl_frame.setAlignment(Qt.AlignCenter)
        self._dji_mon_lbl_frame.setMinimumHeight(200)
        self._dji_mon_lbl_frame.setMaximumHeight(400)
        self._dji_mon_lbl_frame.setStyleSheet(
            'background:#1a1a1a; border:1px solid #444; color:#aaa;')

        self._dji_lbl_mon_status = QLabel('Monitor: idle')
        self._dji_lbl_mon_status.setTextInteractionFlags(Qt.TextSelectableByMouse)

        gl_monitor.addLayout(mon_broker_row)
        gl_monitor.addLayout(mon_topic_row)
        gl_monitor.addLayout(mon_btn_row)
        gl_monitor.addWidget(self._dji_mon_lbl_frame)
        gl_monitor.addWidget(self._dji_lbl_mon_status)

        # internal monitor state
        self._dji_mon_client = None
        self._dji_mon_queue = None
        self._dji_mon_timer = None
        self._dji_mon_frame_count = 0

        # ── Pre-populate from local_secrets.py (gitignored) ───────────
        _s = None
        try:
            # Force a fresh import each time the dialog is opened so that an
            # updated file is picked up without restarting QGIS.
            import importlib as _il
            import sys as _sys
            _mod_name = 'local_secrets'
            _mod_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_secrets.py')
            if os.path.exists(_mod_path):
                import importlib.util as _ilu
                _spec = _ilu.spec_from_file_location(_mod_name, _mod_path)
                _s = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_s)
        except Exception:
            pass
        if _s is not None:
            v = getattr(_s, 'DJI_APP_KEY', None)
            if v:
                self._dji_le_app_key.setText(v)
                self._dji_lbl_key_status.setText('✓ App Key loaded from local_secrets.py')
            else:
                # Fallback: check QSettings (written by Save button in previous sessions)
                _qs = QSettings('4113Eng', 'GIMIWorkbench')
                _qk = _qs.value('dji/app_key', '')
                if _qk:
                    self._dji_le_app_key.setText(_qk)
                    self._dji_lbl_key_status.setText('✓ App Key loaded from saved settings')
            v = getattr(_s, 'NODEODM_URL', None)
            if v:
                self._dji_le_nodeodm_url.setText(v)
            v = getattr(_s, 'MQTT_BROKER', None)
            if v:
                self._dji_stream_le_broker.setText(v)
            v = getattr(_s, 'MQTT_PORT', None)
            if v:
                self._dji_stream_le_port.setValue(int(v))
            v = getattr(_s, 'MQTT_TOPIC', None)
            if v:
                self._dji_stream_le_topic.setText(v)
            # mirror MQTT settings to monitor widget
            self._dji_mon_le_broker.setText(self._dji_stream_le_broker.text())
            self._dji_mon_le_port.setValue(self._dji_stream_le_port.value())
            self._dji_mon_le_topic.setText(self._dji_stream_le_topic.text())

        root.addWidget(grp_monitor)
        root.addStretch()
        self.tabWidget.addTab(tab, 'DJI Drone')

    # ------------------------------------------------------------------
    # DJI – App Key management
    # ------------------------------------------------------------------

    def _dji_save_app_key(self):
        """Persist DJI_APP_KEY into local_secrets.py (creating it from the example if absent)."""
        key = self._dji_le_app_key.text().strip()
        if not key:
            QMessageBox.warning(self, 'Empty Key', 'Please enter a DJI App Key before saving.')
            return

        secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_secrets.py')
        example_path = os.path.join(os.path.dirname(secrets_path), 'local_secrets.example.py')

        # Seed from example if local_secrets.py does not exist yet
        if not os.path.exists(secrets_path):
            if os.path.exists(example_path):
                import shutil
                shutil.copy(example_path, secrets_path)
            else:
                with open(secrets_path, 'w', encoding='utf-8') as _f:
                    _f.write('# local_secrets.py — auto-created by GIMI Imagery Workbench\n')
                    _f.write("DJI_APP_KEY = ''\n")

        with open(secrets_path, 'r', encoding='utf-8') as _f:
            src = _f.read()

        import re as _re
        if _re.search(r'^DJI_APP_KEY\s*=', src, _re.MULTILINE):
            src = _re.sub(
                r"^(DJI_APP_KEY\s*=\s*)['\"].*?['\"]\s*$",
                lambda m: f"DJI_APP_KEY = '{key}'",
                src, flags=_re.MULTILINE,
            )
        else:
            src = src.rstrip() + f"\nDJI_APP_KEY = '{key}'\n"

        with open(secrets_path, 'w', encoding='utf-8') as _f:
            _f.write(src)

        # Also persist to QSettings so it survives even if local_secrets.py
        # is overwritten by a future deploy.
        QSettings('4113Eng', 'GIMIWorkbench').setValue('dji/app_key', key)

        self._dji_lbl_key_status.setText('✓ App Key saved to local_secrets.py')

    def _dji_check_app_key(self) -> bool:
        """Return True if an App Key is configured; otherwise show an informational
        dialog explaining how to obtain one and return False."""
        key = self._dji_le_app_key.text().strip()
        if key:
            return True

        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout as _VBL
        dlg = QDialog(self)
        dlg.setWindowTitle('DJI App Key Required')
        dlg.setMinimumWidth(480)
        vb = _VBL(dlg)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setHtml(
            '<h3>DJI Developer App Key not configured</h3>'
            '<p>Processing DJI drone imagery requires a valid <b>DJI Developer App Key</b>.</p>'
            '<ol>'
            '<li>Register a free developer account at '
            '<a href="https://developer.dji.com">https://developer.dji.com</a>.</li>'
            '<li>Create a new application and copy the <b>App Key</b>.</li>'
            '<li>Paste the key in the <b>App Key</b> field at the top of this tab, '
            'then click <i>Save to local_secrets.py</i>.</li>'
            '</ol>'
            '<p><i>Note: the App Key is stored only in the gitignored '
            '<tt>local_secrets.py</tt> file and is never transmitted by this plugin.</i></p>'
            '<p style="font-size:9px;color:#888;">'
            'DJI, the DJI logo and DJI Mobile SDK are trademarks or registered trademarks '
            'of SZ DJI Technology Co., Ltd. Use of the DJI SDK is subject to the '
            '<a href="https://developer.dji.com/en/mobile-sdk/documentation/introduction/sdk_overview.html">'
            'DJI SDK Developer License Agreement</a>.</p>'
        )
        tb.setMinimumHeight(240)
        vb.addWidget(tb)
        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        vb.addWidget(btns)
        dlg.exec_()
        return False

    # ------------------------------------------------------------------
    # DJI – folder browsing & scanning
    # ------------------------------------------------------------------

    def _dji_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Select DJI Image Folder', os.path.expanduser('~'),
            QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog)
        if folder:
            self._dji_le_folder.setText(folder)
            # Auto-derive mission name from folder base name
            base = os.path.basename(folder.rstrip('/\\'))
            if base:
                import re
                slug = re.sub(r'[^a-z0-9_\-]', '_', base.lower())[:40]
                self._dji_le_mission.setText(slug)

    def _dji_browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select DJI Video File', os.path.expanduser('~'),
            'Video Files (*.mp4 *.MP4 *.mov *.MOV *.avi *.AVI)')
        if path:
            self._dji_le_video.setText(path)

    def _dji_browse_sidecar(self):
        """Let the user manually pick a GPS sidecar file."""
        start_dir = os.path.dirname(self._dji_le_video.text().strip()) or os.path.expanduser('~')
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select GPS Sidecar File', start_dir,
            'GPS / Flight Log Files (*.SRT *.srt *.txt *.TXT *.csv *.CSV *.kmz *.KMZ *.kml *.KML);;All files (*)')
        if path:
            self._dji_le_sidecar.setText(path)

    def _dji_get_center_gps(self):
        """Extract a single GPS fix from the centre of the selected video."""
        try:
            from .dji_adapter import DJI_AVAILABLE, DJI_ERROR
        except ImportError:
            from dji_adapter import DJI_AVAILABLE, DJI_ERROR
        if not DJI_AVAILABLE:
            QMessageBox.critical(self, 'DJI Module Not Found',
                f'Cannot import dji_drone_processor:\n{DJI_ERROR}')
            return
        try:
            from .dji_adapter import extract_center_frame_gps
        except (ImportError, AttributeError):
            try:
                from dji_adapter import extract_center_frame_gps
            except (ImportError, AttributeError):
                QMessageBox.critical(self, 'Not available',
                    'extract_center_frame_gps not found in dji_adapter.\n'
                    'Ensure the dji_drone_processor plugin is up to date.')
                return

        video = self._dji_le_video.text().strip()
        if not video or not os.path.isfile(video):
            QMessageBox.warning(self, 'No Video', 'Please select a valid video file first.')
            return

        self._dji_lbl_scan_status.setText('Extracting center GPS…')
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        sidecar = self._dji_le_sidecar.text().strip() or None
        try:
            meta = extract_center_frame_gps(video, sidecar_path=sidecar)
        except Exception as exc:
            QMessageBox.critical(self, 'Center GPS Error', str(exc))
            self._dji_lbl_scan_status.setText('Center GPS: failed.')
            return

        if meta is None or not meta.is_valid():
            QMessageBox.information(self, 'Center GPS',
                'No GPS coordinate found at the video centre.\n\n'
                'Try loading a .csv or .kmz sidecar via the Sidecar Browse… button\n'
                'to provide the flight GPS track.')
            self._dji_lbl_scan_status.setText('Center GPS: no coordinate found.')
            return

        # Show result in a copyable dialog
        lat = meta.latitude
        lon = meta.longitude
        alt = meta.gps_altitude
        rel = meta.relative_altitude
        alt_str = f'{alt:.1f} m MSL' if alt is not None else '—'
        rel_str = f'{rel:.1f} m AGL' if rel is not None else '—'

        msg_lines = [
            f'<b>Video centre GPS coordinate</b><br/>',
            f'Latitude:  <tt>{lat:.8f}</tt>',
            f'Longitude: <tt>{lon:.8f}</tt>',
            f'Altitude:  {alt_str}  /  {rel_str}',
        ]
        if meta.model:
            msg_lines.append(f'Model: {meta.model}')
        if meta.serial_number:
            msg_lines.append(f'Serial: {meta.serial_number}')
        msg_lines.append(f'<br/><i>Source: {os.path.basename(sidecar or video)}</i>')

        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle('Center GPS Result')
        dlg.setMinimumWidth(380)
        vb = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setHtml('<br/>'.join(msg_lines))
        # Also put plain text on clipboard for easy copy
        clipboard_text = f'{lat:.8f}, {lon:.8f}'
        vb.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        copy_btn = bb.addButton('Copy Lat, Lon', QDialogButtonBox.ActionRole)
        def _copy():
            from PyQt5.QtWidgets import QApplication as _QApp
            _QApp.clipboard().setText(clipboard_text)
        copy_btn.clicked.connect(_copy)
        bb.accepted.connect(dlg.accept)
        vb.addWidget(bb)
        dlg.exec_()

        self._dji_lbl_scan_status.setText(
            f'Center GPS: {lat:.6f}, {lon:.6f}  alt {alt_str}')

    def _dji_scan_video(self):
        """Scan a DJI video for GPS metadata and merge into the image table."""
        try:
            from .dji_adapter import DJI_AVAILABLE, DJI_ERROR
        except ImportError:
            from dji_adapter import DJI_AVAILABLE, DJI_ERROR
        if not DJI_AVAILABLE:
            QMessageBox.critical(self, 'DJI Module Not Found',
                f'Cannot import dji_drone_processor:\n{DJI_ERROR}')
            return
        try:
            from .dji_adapter import scan_video_metadata
        except (ImportError, AttributeError):
            try:
                from dji_adapter import scan_video_metadata
            except (ImportError, AttributeError):
                QMessageBox.critical(self, 'Not available',
                    'scan_video_metadata not found in dji_adapter.\n'
                    'Ensure the dji_drone_processor plugin is up to date.')
                return

        video = self._dji_le_video.text().strip()
        if not video or not os.path.isfile(video):
            QMessageBox.warning(self, 'No Video', 'Please select a valid video file.')
            return

        self._dji_lbl_scan_status.setText('Scanning video…')
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        sidecar = self._dji_le_sidecar.text().strip() or None
        try:
            new_metas = scan_video_metadata(video, sample_interval_s=1.0,
                                            sidecar_path=sidecar)
        except Exception as exc:
            QMessageBox.critical(self, 'Video Scan Error', str(exc))
            self._dji_lbl_scan_status.setText('Video scan failed.')
            return

        # ── Direct exiftool fallback (bypasses any stale module cache) ──────
        # This handles the case where the cached exif_utils.py in the running
        # QGIS session predates the exiftool NRT-track tier.
        if not new_metas:
            new_metas = self._dji_exiftool_fallback(video)

        if not new_metas:
            sidecar_txt = self._dji_le_sidecar.text().strip()
            QMessageBox.information(self, 'Video Scan',
                'No GPS metadata found in the video.\n\n'
                'Supported GPS sources (use the Sidecar field to select one):\n'
                '  \u2022 .SRT / .txt \u2014 DJI subtitle sidecar (auto-generated by drone)\n'
                '  \u2022 .csv \u2014 DJI flight log CSV (exported from DJI Fly app)\n'
                '  \u2022 .kmz / .kml \u2014 DJI KMZ/KML flight record\n\n'
                + (f'Sidecar tried: {sidecar_txt}\n' if sidecar_txt else
                   'Tip: select a .csv or .kmz file from DJI Fly via the Sidecar Browse\u2026 button.'))
            self._dji_lbl_scan_status.setText('Video scan: no GPS data found.')
            return

        # Merge with any existing image scan results
        existing = self._dji_images or []
        merged = existing + new_metas
        self._dji_images = sorted(merged, key=lambda m: (0 if m.is_valid() else 1, m.filename))

        # Append new rows to table
        for meta in new_metas:
            row = self._dji_table.rowCount()
            self._dji_table.insertRow(row)
            vals = [
                meta.filename,
                f'{meta.latitude:.6f}' if meta.latitude is not None else '—',
                f'{meta.longitude:.6f}' if meta.longitude is not None else '—',
                f'{meta.gps_altitude:.1f}' if meta.gps_altitude is not None else '—',
                f'{meta.gsd_cm:.2f}' if meta.gsd_cm is not None else '—',
                meta.datetime_taken.isoformat()[:19] if meta.datetime_taken else '—',
                meta.model or '—',
            ]
            for col, v in enumerate(vals):
                from PyQt5.QtWidgets import QTableWidgetItem
                self._dji_table.setItem(row, col, QTableWidgetItem(v))

        valid = sum(1 for m in new_metas if m.is_valid())
        self._dji_lbl_scan_status.setText(
            f'Video: {len(new_metas)} points found — {valid} with GPS  '
            f'(total in table: {len(self._dji_images)})')
        self._dji_btn_process.setEnabled(bool(self._dji_images))

    def _dji_browse_outdir(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Select Output Directory', self._dji_le_outdir.text())
        if folder:
            self._dji_le_outdir.setText(folder)

    def _dji_exiftool_fallback(self, video_path: str):
        """
        Call exiftool directly (bypassing any cached exif_utils module) to
        extract GPS from a DJI NRT metadata track.  Returns a list of
        DJIImageMetadata-like SimpleNamespace objects compatible with the table.
        """
        import subprocess
        import re as _re
        from types import SimpleNamespace

        # Locate exiftool — try PATH first, then known Homebrew locations
        import shutil
        _et = shutil.which('exiftool')
        if not _et:
            for _p in ('/opt/homebrew/bin/exiftool',
                       '/usr/local/bin/exiftool',
                       '/usr/bin/exiftool'):
                if os.path.isfile(_p):
                    _et = _p
                    break
        if not _et:
            return []

        try:
            proc = subprocess.run(
                [_et, '-ee', '-n',
                 '-GPSLatitude', '-GPSLongitude', '-GPSAltitude', '-GPSDateTime',
                 '-VideoFrameRate', video_path],
                capture_output=True, text=True, timeout=180,
            )
        except (subprocess.TimeoutExpired, OSError):
            return []

        lats, lons, alts, times = [], [], [], []
        fps = 25.0
        for line in proc.stdout.splitlines():
            if ':' not in line:
                continue
            key, _, val = line.partition(':')
            key, val = key.strip(), val.strip()
            if key == 'GPS Latitude':
                try: lats.append(float(val))
                except ValueError: pass
            elif key == 'GPS Longitude':
                try: lons.append(float(val))
                except ValueError: pass
            elif key == 'GPS Altitude':
                try: alts.append(float(val))
                except ValueError: alts.append(None)
            elif key == 'GPS Date/Time':
                m = _re.match(r'\d{4}:\d{2}:\d{2}\s+(\d+):(\d+):([\d.]+)', val)
                times.append(int(m.group(1)) * 3600 + int(m.group(2)) * 60 +
                             float(m.group(3)) if m else None)
            elif key == 'Video Frame Rate':
                try: fps = float(val)
                except ValueError: pass

        if not lats or not lons or len(lats) != len(lons):
            return []

        video_name = os.path.basename(video_path)
        results = []
        last_t = None
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                continue
            t = times[i] if i < len(times) else (i / fps)
            if last_t is not None and t is not None and (t - last_t) < 1.0:
                continue
            last_t = t
            alt = alts[i] if i < len(alts) else None
            meta = SimpleNamespace(
                path=video_path,
                filename=f'{video_name}@{t:.1f}s' if t is not None else video_name,
                latitude=lat,
                longitude=lon,
                gps_altitude=alt,
                relative_altitude=None,
                gsd_cm=None,
                datetime_taken=None,
                model='DJI',
                serial_number=None,
                make='DJI',
            )
            meta.is_valid = lambda m=meta: (m.latitude is not None and m.longitude is not None)
            results.append(meta)
        return results

    def _dji_scan_images(self):
        if not self._dji_check_app_key():
            return

        try:
            from .dji_adapter import scan_image_folder, DJI_AVAILABLE, DJI_ERROR
        except ImportError:
            from dji_adapter import scan_image_folder, DJI_AVAILABLE, DJI_ERROR

        if not DJI_AVAILABLE:
            QMessageBox.critical(self, 'DJI Module Not Found',
                                 f'Cannot import dji_drone_processor:\n{DJI_ERROR}\n\n'
                                 'Ensure the dji_drone_processor plugin is in the sibling '
                                 'directory of this plugin.')
            return

        folder = self._dji_le_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, 'No Folder', 'Please select a valid image folder.')
            return

        self._dji_lbl_scan_status.setText('Scanning…')
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            images = scan_image_folder(folder)
        except PermissionError as e:
            QMessageBox.critical(self, 'Permission Denied', str(e))
            self._dji_lbl_scan_status.setText('Scan failed — permission denied.')
            return
        except Exception as e:
            QMessageBox.critical(self, 'Scan Error', f'Error scanning folder:\n{e}')
            self._dji_lbl_scan_status.setText('Scan failed.')
            return
        self._dji_images = images

        self._dji_table.setRowCount(0)
        for meta in images:
            row = self._dji_table.rowCount()
            self._dji_table.insertRow(row)
            vals = [
                meta.filename,
                f'{meta.latitude:.6f}' if meta.latitude is not None else '—',
                f'{meta.longitude:.6f}' if meta.longitude is not None else '—',
                f'{meta.gps_altitude:.1f}' if meta.gps_altitude is not None else '—',
                f'{meta.gsd_cm:.2f}' if meta.gsd_cm is not None else '—',
                meta.datetime_taken.isoformat()[:19] if meta.datetime_taken else '—',
                meta.model or '—',
            ]
            for col, v in enumerate(vals):
                from PyQt5.QtWidgets import QTableWidgetItem
                self._dji_table.setItem(row, col, QTableWidgetItem(v))

        valid = sum(1 for m in images if m.is_valid())
        if not images:
            self._dji_lbl_scan_status.setText(
                'No JPEG images found. Check the folder contains .jpg/.jpeg files '
                '(subdirectories are scanned automatically).')
        else:
            self._dji_lbl_scan_status.setText(
                f'{len(images)} image(s) found — {valid} with valid GPS')
        self._dji_btn_process.setEnabled(bool(images))

    # ------------------------------------------------------------------
    # DJI – processing
    # ------------------------------------------------------------------

    def _dji_start_processing(self):
        if not self._dji_check_app_key():
            return

        try:
            from .dji_adapter import (
                GDALSimpleProcessor, NodeODMProcessor,
                create_footprints_geojson, DJI_AVAILABLE, DJI_ERROR,
            )
        except ImportError:
            from dji_adapter import (
                GDALSimpleProcessor, NodeODMProcessor,
                create_footprints_geojson, DJI_AVAILABLE, DJI_ERROR,
            )

        if not DJI_AVAILABLE:
            QMessageBox.critical(self, 'DJI Module Not Found', DJI_ERROR)
            return

        if not self._dji_images:
            QMessageBox.warning(self, 'No Images', 'Please scan a DJI image folder first.')
            return

        mission = self._dji_le_mission.text().strip() or 'drone_mission'
        base_out = self._dji_le_outdir.text().strip()
        if not base_out:
            QMessageBox.warning(self, 'No Output Dir', 'Please select an output directory.')
            return

        # Output structure matches cesium dashboard drones.py expectations:
        # {base_out}/{mission}/footprints.geojson + orthophoto.tif
        mission_dir = os.path.join(base_out, mission)
        os.makedirs(mission_dir, exist_ok=True)

        # Save footprints GeoJSON immediately (before ortho processing)
        fp_path = os.path.join(mission_dir, 'footprints.geojson')
        create_footprints_geojson(self._dji_images, fp_path)

        # Build processor
        if self._dji_rb_nodeodm.isChecked():
            url = self._dji_le_nodeodm_url.text().strip() or 'http://localhost:3000'
            processor = NodeODMProcessor(
                images=self._dji_images,
                output_dir=mission_dir,
                nodeodm_url=url,
            )
        else:
            processor = GDALSimpleProcessor(
                images=self._dji_images,
                output_dir=mission_dir,
            )

        # Start worker thread
        self._dji_log.clear()
        n_imgs = getattr(processor, 'images', [])
        n_vid  = getattr(processor, 'video_frame_count', 0)
        if n_vid and not n_imgs:
            self._dji_log.append(
                f'Video-only mission: {n_vid} GPS track points → writing footprints.geojson\n'
                '(No raster images found — orthophoto mosaic will not be produced.)')
        elif n_vid:
            self._dji_log.append(
                f'{len(n_imgs)} still image(s) + {n_vid} video GPS points to process…')
        self._dji_progress.setVisible(True)
        self._dji_progress.setValue(0)
        self._dji_btn_process.setEnabled(False)
        self._dji_btn_cancel.setEnabled(True)
        # Create fresh worker + thread for each run
        self._dji_worker = _DJIWorker(processor)
        self._dji_thread = QThread()
        self._dji_worker.moveToThread(self._dji_thread)
        self._dji_thread.started.connect(self._dji_worker.run)
        self._dji_worker.progress.connect(self._dji_on_progress)
        self._dji_worker.finished.connect(self._dji_on_finished)
        self._dji_worker.finished.connect(self._dji_thread.quit)
        self._dji_thread.start()

    def _dji_cancel_processing(self):
        if self._dji_worker:
            self._dji_worker.cancel()
        self._dji_log.append('Cancellation requested…')

    def _dji_on_progress(self, pct: int, msg: str):
        self._dji_progress.setValue(pct)
        self._dji_log.append(f'[{pct:3d}%] {msg}')

    def _dji_on_finished(self, result):
        self._dji_btn_process.setEnabled(True)
        self._dji_btn_cancel.setEnabled(False)
        self._dji_result = result

        # Clean up thread/worker so they can be recreated on the next run
        if self._dji_thread is not None:
            self._dji_thread.quit()
            self._dji_thread.wait()
        self._dji_worker = None
        self._dji_thread = None

        mission = self._dji_le_mission.text().strip() or 'drone_mission'
        base_out = self._dji_le_outdir.text().strip()
        mission_dir = os.path.join(base_out, mission)

        if result.success:
            self._dji_progress.setValue(100)
            self._dji_log.append('✓ Processing complete.')

            # Write metadata.json for cesium dashboard
            import json
            from datetime import datetime, timezone
            meta = {
                'mission': mission,
                'processed_at': datetime.now(timezone.utc).isoformat(),
                'image_count': len(self._dji_images),
                'orthophoto': result.orthophoto_path,
                'point_cloud': result.point_cloud_path,
                'dsm': result.dsm_path,
            }
            try:
                with open(os.path.join(mission_dir, 'metadata.json'), 'w') as fh:
                    json.dump(meta, fh, indent=2)
            except OSError:
                pass

            # If GDAL mode, rename/copy mosaic to orthophoto.tif
            if result.orthophoto_path and os.path.exists(result.orthophoto_path):
                ortho_dest = os.path.join(mission_dir, 'orthophoto.tif')
                if result.orthophoto_path != ortho_dest:
                    import shutil
                    try:
                        shutil.copy2(result.orthophoto_path, ortho_dest)
                        self._dji_result.orthophoto_path = ortho_dest
                    except OSError:
                        pass

            self._dji_log.append(f'Output → {mission_dir}')
        else:
            self._dji_progress.setValue(0)
            self._dji_log.append(f'✗ Processing failed: {result.error}')
            QMessageBox.critical(self, 'DJI Processing Error', result.error or 'Unknown error')

    # ------------------------------------------------------------------
    # DJI – QGIS layer loading
    # ------------------------------------------------------------------

    def _dji_load_orthophoto(self):
        if not self._dji_result or not self._dji_result.orthophoto_path:
            return
        path = self._dji_result.orthophoto_path
        if not os.path.exists(path):
            QMessageBox.warning(self, 'Not Found', f'Orthophoto not found:\n{path}')
            return
        try:
            from qgis.core import QgsProject, QgsRasterLayer
            mission = self._dji_le_mission.text().strip() or 'orthophoto'
            lyr = QgsRasterLayer(path, f'{mission} — orthophoto')
            if not lyr.isValid():
                raise RuntimeError('Layer not valid')
            QgsProject.instance().addMapLayer(lyr)
            self._dji_log.append(f'Loaded orthophoto layer: {os.path.basename(path)}')
        except Exception as exc:
            QMessageBox.critical(self, 'Load Error', str(exc))

    def _dji_load_footprints(self):
        mission = self._dji_le_mission.text().strip() or 'drone_mission'
        base_out = self._dji_le_outdir.text().strip()
        fp_path = os.path.join(base_out, mission, 'footprints.geojson')
        if not os.path.exists(fp_path):
            QMessageBox.warning(self, 'Not Found', f'Footprints not found:\n{fp_path}')
            return
        try:
            from qgis.core import QgsProject, QgsVectorLayer
            lyr = QgsVectorLayer(fp_path, f'{mission} — footprints', 'ogr')
            if not lyr.isValid():
                raise RuntimeError('Layer not valid')
            QgsProject.instance().addMapLayer(lyr)
            self._dji_log.append(f'Loaded footprints layer: {mission}/footprints.geojson')
        except Exception as exc:
            QMessageBox.critical(self, 'Load Error', str(exc))

    # ------------------------------------------------------------------
    # DJI – STAC export
    # ------------------------------------------------------------------

    def _dji_export_stac(self):
        """Export the DJI orthophoto as a STAC 1.0 Item with liability fields."""
        if not self._dji_result or not self._dji_result.orthophoto_path:
            QMessageBox.warning(self, 'No Result',
                                'Process the images first to generate an orthophoto.')
            return

        ortho_path = self._dji_result.orthophoto_path
        if not os.path.exists(ortho_path):
            QMessageBox.warning(self, 'Not Found', f'Orthophoto not found:\n{ortho_path}')
            return

        from PyQt5.QtWidgets import QFileDialog
        out_dir = QFileDialog.getExistingDirectory(
            self, 'Select Output Directory for STAC Item',
            os.path.dirname(ortho_path))
        if not out_dir:
            return

        mission = self._dji_le_mission.text().strip() or 'drone_mission'
        base_out = self._dji_le_outdir.text().strip()

        # Build a minimal _provenance.json sidecar in memory
        import json
        from datetime import datetime, timezone

        valid_images = [m for m in self._dji_images if m.is_valid()]
        timestamps = [
            m.datetime_taken.isoformat()
            for m in valid_images if m.datetime_taken
        ]
        avg_gsd_cm = None
        gsds = [m.gsd_cm for m in valid_images if m.gsd_cm]
        if gsds:
            avg_gsd_cm = sum(gsds) / len(gsds)

        prov = {
            'derived_uuid': f'{mission}_stac',
            'output_file': os.path.basename(ortho_path),
            'input_file': self._dji_le_folder.text().strip(),
            'algorithm_name': 'DJI Drone Processor (QGIS Plugin)',
            'processing_timestamp': datetime.now(timezone.utc).isoformat(),
            'ido_annotation': {
                'responsible_party': '4113 Engineering',
                'data_classification': 'unclassified',
            },
            'iso19115_4': {
                'quality': [
                    {
                        'type': 'processingLevel',
                        'level': 'L2 — Georeferenced Orthophoto',
                    },
                    {
                        'type': 'cloudCoverage',
                        'coveragePercentage': 0,
                    },
                ]
                + ([{
                    'type': 'usabilityAssessment',
                    'usabilityScore': min(1.0, round(8.0 / max(avg_gsd_cm, 0.5), 2)),
                    'intendedUse': 'Drone orthophoto — DJI imagery',
                }] if avg_gsd_cm else []),
            },
        }
        if timestamps:
            prov['processing_timestamp'] = timestamps[0]

        # Write temp provenance file
        import tempfile
        tmp_dir = tempfile.mkdtemp()
        prov_path = os.path.join(tmp_dir, f'{mission}_provenance.json')
        try:
            with open(prov_path, 'w') as fh:
                json.dump(prov, fh, indent=2)

            from .stac_converter import ProvenanceToSTACConverter
            stac_path = ProvenanceToSTACConverter().convert(prov_path, ortho_path, out_dir)
            self._dji_log.append(f'STAC Item → {stac_path}')
            QMessageBox.information(self, 'STAC Item Exported',
                                    f'STAC Item written to:\n{stac_path}')
        except Exception as exc:
            QMessageBox.critical(self, 'STAC Export Error', str(exc))
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Flight track export + blockchain registration
    # ------------------------------------------------------------------

    def _dji_export_flight_track(self):
        """Export GPS track as GeoJSON + STAC Item, compute SHA-256 hash."""
        from PyQt5.QtWidgets import QFileDialog, QMessageBox

        valid_pts = [m for m in (self._dji_images or []) if m.is_valid()]
        if not valid_pts:
            QMessageBox.warning(self, 'No GPS Points',
                'No valid GPS points available.\n'
                'Please scan a video (or image folder) with GPS data first.')
            return

        video = self._dji_le_video.text().strip()
        if not video:
            video = 'flight.mp4'

        out_dir = self._dji_le_outdir.text().strip()
        if not out_dir:
            out_dir = QFileDialog.getExistingDirectory(
                self, 'Select output directory for track files')
            if not out_dir:
                return
            self._dji_le_outdir.setText(out_dir)

        # COP metadata from the mission / classification fields if present
        cop_meta: dict = {}
        for attr, key in [
            ('_dji_le_mission', 'mission'),
            ('_dji_le_classification', 'classification'),
            ('_dji_le_releasability', 'releasability'),
        ]:
            widget = getattr(self, attr, None)
            if widget:
                val = widget.text().strip() if hasattr(widget, 'text') else widget.currentText().strip()
                if val:
                    cop_meta[key] = val

        try:
            try:
                from .dji_adapter import save_flight_track
            except ImportError:
                from dji_adapter import save_flight_track

            geojson_path, stac_path, sha256 = save_flight_track(
                valid_pts, video, out_dir, cop_meta=cop_meta or None
            )
        except Exception as exc:
            QMessageBox.critical(self, 'Export Error', str(exc))
            return

        self._dji_track_stac_path = stac_path
        self._dji_track_hash = sha256

        short_hash = sha256[:16] + '…'
        self._dji_lbl_track_hash.setText(f'BLAKE3: {short_hash}')
        self._dji_lbl_anchor_result.setText('Tx: — (not yet anchored)')

        # Log output
        self._dji_log.append(f'Track GeoJSON  → {geojson_path}')
        self._dji_log.append(f'STAC Item      → {stac_path}')
        self._dji_log.append(f'BLAKE3         → {sha256}')

        QMessageBox.information(
            self, 'Flight Track Exported',
            f'GeoJSON track:\n{geojson_path}\n\n'
            f'STAC Item:\n{stac_path}\n\n'
            f'SHA-256 hash:\n{sha256}\n\n'
            'Use "⛓ Anchor on Blockchain" to register this hash.')

    def _dji_anchor_blockchain(self):
        """POST the STAC item + SHA-256 to the blockchain anchor API."""
        from PyQt5.QtWidgets import QMessageBox

        if not self._dji_track_stac_path or not self._dji_track_hash:
            QMessageBox.warning(self, 'Nothing to Anchor',
                'Export the flight track first using "📋 Export Track GeoJSON + STAC".')
            return

        api_url = self._dji_le_blockchain_api.text().strip() or 'http://localhost:8000'

        ipfs_cid = None

        self._dji_lbl_anchor_result.setText('Anchoring…')
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            try:
                from .dji_adapter import anchor_via_api
            except ImportError:
                from dji_adapter import anchor_via_api

            result = anchor_via_api(
                self._dji_track_stac_path,
                self._dji_track_hash,
                ipfs_cid=ipfs_cid,
                api_url=api_url,
            )
        except Exception as exc:
            QMessageBox.critical(self, 'Anchor Error', str(exc))
            self._dji_lbl_anchor_result.setText('Tx: ERROR')
            return

        status = result.get('status', 'unknown')

        if status == 'anchored':
            tx = result.get('tx_hash') or '—'
            self._dji_lbl_anchor_result.setText(f'Tx: {tx[:20]}…')
            self._dji_log.append(f'Blockchain anchor → tx {tx}')
            QMessageBox.information(
                self, 'Anchored on Blockchain',
                f'Transaction hash:\n{tx}\n\n'
                f'IPFS CID: {result.get("ipfs_cid") or "—"}')

        elif status == 'local_only':
            record_path = result.get('record_path', '')
            self._dji_lbl_anchor_result.setText('Tx: local provenance record saved')
            self._dji_log.append(
                f'Blockchain API unavailable → provenance record: {record_path}')
            QMessageBox.information(
                self, 'Local Provenance Record Saved',
                f'The blockchain anchor API at\n{api_url}\nwas not reachable.\n\n'
                f'A tamper-evident provenance record with the SHA-256 hash has been\n'
                f'saved locally:\n{record_path}\n\n'
                'Start stac_imagery_api and retry to anchor on-chain.')

        else:
            err = result.get('error', 'unknown error')
            self._dji_lbl_anchor_result.setText(f'Tx: error — {err[:40]}')
            QMessageBox.warning(self, 'Anchor Failed', str(err))

    # ------------------------------------------------------------------
    # TB21 GIMI key-frame extraction (Option B)
    # ------------------------------------------------------------------

    def _dji_extract_gimi_frames(self):
        """
        Extract key frames from the DJI video and encode each as a TB21
        GIMI HEIF file with embedded GPS-derived RDF metadata.
        """
        from PyQt5.QtWidgets import QMessageBox, QFileDialog, QApplication

        video_path = getattr(self, '_dji_video_path', None) or self._dji_le_video.text().strip()
        if not video_path or not os.path.isfile(video_path):
            QMessageBox.warning(self, 'No Video',
                'Select a DJI video file first (use the Video field).')
            return

        gps_points = getattr(self, '_dji_images', [])
        valid_gps = [p for p in gps_points
                     if getattr(p, 'latitude', None) is not None
                     and getattr(p, 'longitude', None) is not None]
        if not valid_gps:
            QMessageBox.warning(self, 'No GPS Data',
                'Scan the video for GPS data first ("🔍 Scan GPS from Video").')
            return

        # Output directory: same folder as video, sub-folder gimi_frames/
        default_out = os.path.join(os.path.dirname(video_path), 'gimi_frames')
        out_dir = QFileDialog.getExistingDirectory(
            self, 'Select Output Directory for GIMI HEIF Frames', default_out)
        if not out_dir:
            out_dir = default_out

        n_frames = self._dji_spin_gimi_frames.value()

        # Gather COP metadata
        cop_meta = {
            'mission': (getattr(self, '_dji_le_mission', None)
                        and self._dji_le_mission.text().strip()) or '',
            'classification': (getattr(self, '_dji_cb_classification', None)
                               and self._dji_cb_classification.currentText()) or 'public release',
        }

        self._dji_lbl_gimi_result.setText('Extracting…')
        self._dji_btn_extract_gimi.setEnabled(False)
        QApplication.processEvents()

        try:
            try:
                from .dji_adapter import extract_frames_as_gimi
            except ImportError:
                from dji_adapter import extract_frames_as_gimi

            results = extract_frames_as_gimi(
                video_path=video_path,
                gps_points=valid_gps,
                output_dir=out_dir,
                cop_meta=cop_meta,
                n_frames=n_frames,
                quality=90,
                sample_interval_s=1.0,
                progress_cb=lambda cur, tot: (
                    self._dji_lbl_gimi_result.setText(f'Frame {cur}/{tot}…'),
                    QApplication.processEvents()
                ),
            )
        except Exception as exc:
            self._dji_btn_extract_gimi.setEnabled(True)
            self._dji_lbl_gimi_result.setText('Error')
            QMessageBox.critical(self, 'GIMI Extraction Error', str(exc))
            return

        self._dji_btn_extract_gimi.setEnabled(True)

        ok = [r for r in results if r.get('ok')]
        failed = [r for r in results if not r.get('ok')]

        self._dji_lbl_gimi_result.setText(
            f'{len(ok)}/{len(results)} frames → {os.path.basename(out_dir)}/')
        self._dji_log.append(
            f'GIMI extraction: {len(ok)} OK, {len(failed)} failed → {out_dir}')

        if failed:
            errs = '\n'.join(f"  Frame {r['frame_index']}: {r.get('error')}" for r in failed[:5])
            QMessageBox.warning(
                self, 'Some Frames Failed',
                f'{len(failed)} frame(s) failed:\n{errs}')
        else:
            heif_paths = [r['heif_path'] for r in ok if r.get('heif_path')]
            msg = (
                f'{len(ok)} TB21 GIMI HEIF files written to:\n{out_dir}\n\n'
                + '\n'.join(os.path.basename(p) for p in heif_paths[:10])
                + ('\n…' if len(heif_paths) > 10 else '')
            )
            QMessageBox.information(self, 'GIMI Frames Extracted', msg)

    # ------------------------------------------------------------------
    # IPFS upload
    # ------------------------------------------------------------------
    # Stream imagery / video to CS deployment via MQTT
    # ------------------------------------------------------------------

    def _dji_stream_browse_media(self):
        """Browse for image folder or video file to stream."""
        from PyQt5.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, 'Select Image Folder to Stream')
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, 'Select Video File to Stream', '',
                'Video files (*.mp4 *.avi *.mov *.mkv *.m4v);;All files (*.*)')
        if path:
            self._dji_stream_le_media.setText(path)
            # Auto-fill topic from deployment UID
            dep = self._dji_stream_le_dep.text().strip()
            if dep and not self._dji_stream_le_topic.text().strip():
                self._dji_stream_le_topic.setText(
                    f'cs/deployments/{dep}/imagery')

    def _dji_stream_pick_deployment(self):
        """Query the CS API and let the user pick a deployment from a list."""
        from PyQt5.QtWidgets import QDialog, QListWidget, QVBoxLayout, QPushButton, QMessageBox
        try:
            client = self._client()
            deps = client.list_deployments(limit=100)
        except Exception as exc:
            QMessageBox.warning(self, 'CS API', f'Could not list deployments:\n{exc}')
            return

        if not deps:
            QMessageBox.information(self, 'CS API', 'No deployments found.')
            return

        dlg = QDialog(self)
        dlg.setWindowTitle('Select Deployment')
        layout = QVBoxLayout(dlg)
        lst = QListWidget()
        for d in deps:
            uid = d.get('uid') or d.get('id', '')
            name = d.get('name', uid)
            lst.addItem(f'{name}  [{uid}]')
        layout.addWidget(lst)
        btn_ok = QPushButton('Select')
        btn_ok.clicked.connect(dlg.accept)
        layout.addWidget(btn_ok)
        dlg.resize(500, 300)

        if dlg.exec_() and lst.currentRow() >= 0:
            chosen = deps[lst.currentRow()]
            uid = chosen.get('uid') or chosen.get('id', '')
            self._dji_stream_le_dep.setText(uid)
            if not self._dji_stream_le_topic.text().strip():
                self._dji_stream_le_topic.setText(
                    f'cs/deployments/{uid}/imagery')

    def _dji_stream_start(self):
        """Start streaming imagery frames or video to the CS deployment via MQTT."""
        import os, glob

        broker = self._dji_stream_le_broker.text().strip()
        port   = self._dji_stream_le_port.value()
        topic  = self._dji_stream_le_topic.text().strip()
        dep    = self._dji_stream_le_dep.text().strip()
        media  = self._dji_stream_le_media.text().strip()
        fps    = self._dji_stream_spin_fps.value()

        if not broker or not topic:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Stream', 'Set MQTT broker and topic before streaming.')
            return

        if not media or not os.path.exists(media):
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Stream', 'Select a valid image folder or video file.')
            return

        # Try to import paho-mqtt; offer install if missing
        try:
            import paho.mqtt.client as mqtt_client  # type: ignore
        except ImportError:
            from PyQt5.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 'paho-mqtt not found',
                'The paho-mqtt library is required for MQTT streaming.\n'
                'Install it now? (pip install paho-mqtt)',
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                import subprocess, sys
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', 'paho-mqtt', '-q'],
                    check=False)
                try:
                    import paho.mqtt.client as mqtt_client  # type: ignore
                except ImportError:
                    QMessageBox.critical(self, 'Stream',
                        'paho-mqtt installation failed. '
                        'Install manually: pip install paho-mqtt')
                    return
            else:
                return

        # Build frame list from image folder or extract video frames
        if os.path.isdir(media):
            exts = ('*.jpg', '*.jpeg', '*.png', '*.tif', '*.tiff', '*.heic', '*.heif')
            files = []
            for ext in exts:
                files.extend(glob.glob(os.path.join(media, ext)))
                files.extend(glob.glob(os.path.join(media, ext.upper())))
            self._dji_stream_files = sorted(set(files))
        elif os.path.isfile(media) and media.lower().split('.')[-1] in (
                'jpg', 'jpeg', 'png', 'tif', 'tiff', 'heic', 'heif'):
            # Single image file — wrap in a one-item list
            self._dji_stream_files = [media]
        else:
            # Video: extract frames via OpenCV if available, else error
            try:
                # The bundled QGIS opencv_contrib egg is broken (missing libprotobuf.22.dylib).
                # Remove it from sys.path so the pip-installed cv2 is found instead.
                import sys as _sys
                _sys.path = [p for p in _sys.path if 'opencv_contrib_python' not in p]
                if 'cv2' in _sys.modules:
                    del _sys.modules['cv2']
                import cv2  # type: ignore
                import tempfile
                cap = cv2.VideoCapture(media)
                tmp_dir = tempfile.mkdtemp(prefix='dji_stream_frames_')
                frame_idx = 0
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                skip = max(1, int(cap.get(cv2.CAP_PROP_FPS) / fps))
                self._dji_stream_files = []
                self._dji_log.append(
                    f'Extracting frames from video ({total_frames} total, 1/{skip})…')
                from PyQt5.QtWidgets import QApplication
                QApplication.processEvents()
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    if frame_idx % skip == 0:
                        p = os.path.join(tmp_dir, f'frame_{frame_idx:06d}.jpg')
                        cv2.imwrite(p, frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        self._dji_stream_files.append(p)
                    frame_idx += 1
                cap.release()
            except (ImportError, AttributeError, Exception):
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(self, 'Stream',
                    'OpenCV (cv2) is required to extract video frames.\n'
                    'Install: pip install opencv-python')
                return

        if not self._dji_stream_files:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Stream', 'No image files found in the selected path.')
            return

        # Connect MQTT
        self._dji_mqtt_client = mqtt_client.Client(
            client_id=f'qgis-dji-stream-{dep[:20]}',
            protocol=mqtt_client.MQTTv5
            if hasattr(mqtt_client, 'MQTTv5') else mqtt_client.MQTTv311,
        )

        cs_token = ''
        if hasattr(self, '_cs_le_token'):
            cs_token = self._cs_le_token.text().strip()
        if cs_token:
            self._dji_mqtt_client.username_pw_set(cs_token, '')

        def _on_connect(client, userdata, flags, rc, *args):
            if rc == 0:
                self._dji_lbl_stream_status.setText(
                    f'Stream: connected to {broker}:{port} → {topic}')
            else:
                self._dji_lbl_stream_status.setText(f'Stream: MQTT connect error rc={rc}')

        self._dji_mqtt_client.on_connect = _on_connect

        try:
            self._dji_mqtt_client.connect(broker, port, keepalive=60)
            self._dji_mqtt_client.loop_start()
        except Exception as exc:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, 'Stream', f'MQTT connect failed:\n{exc}')
            return

        # Fire a timer to publish frames at the requested fps
        from PyQt5.QtCore import QTimer
        self._dji_stream_index = 0
        self._dji_stream_timer = QTimer(self)
        interval_ms = max(100, 1000 // fps)
        self._dji_stream_timer.setInterval(interval_ms)
        self._dji_stream_timer.timeout.connect(self._dji_stream_tick)
        self._dji_stream_timer.start()

        self._dji_btn_stream_start.setEnabled(False)
        self._dji_btn_stream_stop.setEnabled(True)
        self._dji_lbl_stream_status.setText(
            f'Stream: publishing {len(self._dji_stream_files)} frames '
            f'@ {fps} fps → {topic}')
        self._dji_log.append(
            f'▶ Stream started: {len(self._dji_stream_files)} frames '
            f'→ mqtt://{broker}:{port}/{topic}')

        # ── Publish flight path to CS API in background ───────────────
        import threading
        threading.Thread(
            target=self._dji_publish_flight_path,
            args=(dep,),
            daemon=True,
        ).start()

    def _dji_publish_flight_path(self, deployment_uid: str):
        """
        Build a GeoJSON LineString from scanned DJI image GPS positions and
        POST it to the OGC Connected Systems API as an Observation on the
        drone's flight-path datastream.  Runs in a daemon thread.

        The observation result is a GeoJSON Feature conformant with:
          - MGCP extension code MO001 (Unmanned Aerial System) for the
            moving-object feature type
          - AIS ITU-R M.1371 field naming conventions (with altitude extension)
          - Imagery Interpretation Ontology :UAS / :FlightTrajectory classes
            (http://ogc.secd.eu/ontology/imagery-interpretation#)

        AIS field mapping used in result properties:
          mmsi         → uas:serialNumber  (drone_uid)
          sog (knots)  → uas:groundSpeed_ms (converted)
          cog (deg)    → uas:headingYaw_deg
          nav_status   → uas:flightStatus
          [AIS extension]
          altitude_msl_m, altitude_agl_m, vertical_rate_ms,
          gimbal_pitch_deg, gimbal_roll_deg, gimbal_yaw_deg
        """
        import json
        from datetime import datetime, timezone

        # ── Harmonized vocab namespaces (AIS + ADS-B) ───────────────────────
        _IIO     = 'http://ogc.secd.eu/ontology/imagery-interpretation#'
        _AIS     = 'http://secd.eu/vocab/ais-field#'
        _ADSB    = 'http://secd.eu/vocab/adsb-field#'
        _MGCP_MO = 'http://secd.eu/vocab/mgcp-moving-object#'

        images = self._dji_images or []
        geolocated = [m for m in images if m.is_geolocated() and m.longitude is not None]
        if not geolocated:
            self._dji_log.append('CS API: no GPS positions in scanned images — flight path not published')
            return

        try:
            client = self._client()
        except Exception as exc:
            self._dji_log.append(f'CS API: could not build client — {exc}')
            return

        # ── Resolve drone identity ───────────────────────────────────────────
        drone_uid = ''
        drone_model = 'unknown'
        drone_serial = ''
        if geolocated:
            first = geolocated[0]
            drone_model = (getattr(first, 'model', '') or 'unknown').strip()
            drone_serial = (getattr(first, 'serial_number', '') or '').strip()
            # URN follows MO001 harmonized schema: urn:uas:dji:{model}:{serial}
            drone_uid = f'urn:uas:dji:{drone_model.lower().replace(" ", "-")}'
            if drone_serial:
                drone_uid += f':{drone_serial.lower()}'

        # ── Timestamps ───────────────────────────────────────────────────────
        now_iso = datetime.now(timezone.utc).isoformat()
        t_start = (
            geolocated[0].timestamp.isoformat()
            if getattr(geolocated[0], 'timestamp', None)
            else now_iso
        )
        t_end = (
            geolocated[-1].timestamp.isoformat()
            if getattr(geolocated[-1], 'timestamp', None)
            else now_iso
        )

        # ── 3-D LineString coordinates [lon, lat, alt_msl] ──────────────────
        pts = [
            [m.longitude, m.latitude, m.gps_altitude or 0.0]
            for m in geolocated
        ]

        # ── Per-point harmonized position reports ─────────────────────────────
        # Each entry carries both AIS-native and ADS-B-native field names,
        # plus UAS attitude extension fields (not in either standard).
        # Speed conversion: 1 knot (AIS SOG) = 0.5144 m/s (ADS-B velocity)
        position_reports = []
        for i, m in enumerate(geolocated):
            # Ground speed — prefer explicit field, else compute from GNSS deltas
            gs_ms = None
            if getattr(m, 'ground_speed', None) is not None:
                gs_ms = float(m.ground_speed)
            elif i > 0:
                prev = geolocated[i - 1]
                if (getattr(prev, 'timestamp', None) and getattr(m, 'timestamp', None)
                        and prev.timestamp != m.timestamp):
                    from math import radians, cos, sin, asin, sqrt
                    lat1, lon1 = radians(prev.latitude), radians(prev.longitude)
                    lat2, lon2 = radians(m.latitude), radians(m.longitude)
                    dlat, dlon = lat2 - lat1, lon2 - lon1
                    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
                    dist_m = 2 * 6_371_000 * asin(sqrt(a))
                    dt_s = abs((m.timestamp - prev.timestamp).total_seconds())
                    if dt_s > 0:
                        gs_ms = dist_m / dt_s

            # Vertical rate (m/s) — ADS-B: vertical_rate; no AIS equivalent
            vr_ms = None
            if i > 0:
                prev = geolocated[i - 1]
                if (getattr(prev, 'timestamp', None) and getattr(m, 'timestamp', None)
                        and prev.timestamp != m.timestamp):
                    da = (m.gps_altitude or 0.0) - (prev.gps_altitude or 0.0)
                    dt_s = abs((m.timestamp - prev.timestamp).total_seconds())
                    if dt_s > 0:
                        vr_ms = da / dt_s

            yaw = getattr(m, 'flight_yaw', None)
            report = {
                # ── Harmonized identity ─────────────────────────────────────
                'uid':              drone_uid,
                # ── Position (both standards) ───────────────────────────────
                'latitude':         m.latitude,          # AIS: latitude; ADS-B: latitude
                'longitude':        m.longitude,         # AIS: longitude; ADS-B: longitude
                'altitude_msl_m':   m.gps_altitude,      # ADS-B: baro_altitude/geo_altitude; absent from AIS
                'altitude_agl_m':   getattr(m, 'relative_altitude', None),  # UAS extension only
                # ── Speed ───────────────────────────────────────────────────
                'speed_ms':         gs_ms,               # ADS-B: velocity (m/s, canonical)
                'speed_knots':      (gs_ms / 0.5144) if gs_ms is not None else None,  # AIS: SOG
                'vertical_rate_ms': vr_ms,               # ADS-B: vertical_rate; no AIS equivalent
                # ── Course / heading ────────────────────────────────────────
                'course_deg':       yaw,                 # AIS: COG; ADS-B: true_track
                'heading_deg':      yaw,                 # AIS: heading; ADS-B: heading
                # ── Operational status ──────────────────────────────────────
                'operational_status': 'airborne',        # AIS: nav_status→0; ADS-B: on_ground=false
                # ── AIS-native aliases ──────────────────────────────────────
                'ais:mmsi':         drone_uid,
                'ais:sog_knots':    (gs_ms / 0.5144) if gs_ms is not None else None,
                'ais:cog':          yaw,
                'ais:heading':      yaw,
                'ais:nav_status':   0,                   # 0 = under way
                # ── ADS-B-native aliases ────────────────────────────────────
                'adsb:icao24':      drone_serial or drone_uid,
                'adsb:velocity_ms': gs_ms,
                'adsb:true_track':  yaw,
                'adsb:baro_altitude_m': m.gps_altitude,
                'adsb:vertical_rate_ms': vr_ms,
                'adsb:on_ground':   False,
                # ── UAS attitude extension (not in AIS or ADS-B) ───────────
                'uas:gimbalPitch_deg':  getattr(m, 'gimbal_pitch', None),
                'uas:gimbalRoll_deg':   getattr(m, 'gimbal_roll', None),
                'uas:gimbalYaw_deg':    getattr(m, 'gimbal_yaw', None),
                'uas:flightPitch_deg':  getattr(m, 'flight_pitch', None),
                'uas:flightRoll_deg':   getattr(m, 'flight_roll', None),
            }
            # Drop None values to keep payload lean
            position_reports.append({k: v for k, v in report.items() if v is not None})

        # ── Observation payload ───────────────────────────────────────────────
        obs_body = {
            # JSON-LD context linking short prefixes to ontology URIs
            '@context': {
                'iio':     _IIO,
                'ais':     _AIS,
                'adsb':    _ADSB,
                'uas':     _IIO,
                'mgcp-mo': _MGCP_MO,
            },
            'datastream': {'@id': deployment_uid},
            'phenomenonTime': f'{t_start}/{t_end}',
            'resultTime': now_iso,
            'result': {
                'type': 'Feature',
                # Harmonized type: :FlightTrajectory (subclass of :MovingObjectTrack)
                '@type': f'{_IIO}FlightTrajectory',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': pts,        # [lon, lat, altitude_msl_m]
                },
                'properties': {
                    # ── Moving-object classification (MGCP MO001) ──────────
                    'mgcp:fcode':       'MO001',
                    'mgcp:fcode_name':  'Unmanned Aerial System',
                    'iio:class':        f'{_IIO}UAS',
                    # ── Harmonized identity ────────────────────────────────
                    'uid':              drone_uid,
                    'ais:mmsi':         drone_uid,          # AIS MMSI analogue
                    'adsb:icao24':      drone_serial or drone_uid,  # ADS-B ICAO24 analogue
                    'uas:serialNumber': drone_serial or None,
                    'uas:model':        drone_model,
                    'callsign':         drone_model,        # AIS: ship_name / ADS-B: callsign
                    # ── Track summary ──────────────────────────────────────
                    'frame_count':      len(pts),
                    'deployment':       deployment_uid,
                    # ── Harmonization declaration ──────────────────────────
                    'harmonized_standards': {
                        'ais':  {
                            'standard': 'ITU-R M.1371-5',
                            'native_fields': ['ais:mmsi', 'ais:sog_knots', 'ais:cog',
                                              'ais:heading', 'ais:nav_status',
                                              'latitude', 'longitude'],
                            'extension_fields': ['altitude_msl_m', 'altitude_agl_m',
                                                 'vertical_rate_ms', 'uas:gimbal*_deg',
                                                 'uas:flightPitch_deg', 'uas:flightRoll_deg'],
                            'gap_note': 'AIS is 2-D (no altitude). Extension fields from ADS-B and DJI XMP.',
                        },
                        'adsb': {
                            'standard': 'ICAO Doc 9684 / RTCA DO-260B',
                            'native_fields': ['adsb:icao24', 'adsb:velocity_ms',
                                              'adsb:true_track', 'adsb:baro_altitude_m',
                                              'adsb:vertical_rate_ms', 'adsb:on_ground',
                                              'latitude', 'longitude'],
                            'extension_fields': ['ais:sog_knots', 'ais:nav_status',
                                                 'uas:gimbal*_deg', 'uas:flightPitch_deg'],
                            'gap_note': 'ADS-B lacks attitude (gimbal/body angles). Extension from DJI XMP.',
                        },
                    },
                    # ── Per-point kinematic data ───────────────────────────
                    'position_reports': position_reports,
                },
            },
        }

        try:
            client.post_observation(obs_body)
            self._dji_log.append(
                f'CS API: flight path published ({len(pts)} pts, MO001/UAS, AIS+ADS-B harmonized) '
                f'uid="{drone_uid}" deployment="{deployment_uid}"')
        except Exception as exc:
            self._dji_log.append(f'CS API: flight path publish failed — {exc}')

    def _dji_stream_tick(self):
        """Publish the next frame to the MQTT broker."""
        import os, json, base64
        from datetime import datetime, timezone

        if self._dji_stream_index >= len(self._dji_stream_files):
            self._dji_stream_stop()
            self._dji_lbl_stream_status.setText('Stream: finished (all frames sent)')
            return

        path = self._dji_stream_files[self._dji_stream_index]
        self._dji_stream_index += 1

        # Read image and encode as base64 (compact MQTT payload)
        try:
            with open(path, 'rb') as fh:
                img_bytes = fh.read()
        except OSError:
            return

        payload = json.dumps({
            'deployment': self._dji_stream_le_dep.text().strip(),
            'frame_index': self._dji_stream_index,
            'total_frames': len(self._dji_stream_files),
            'filename': os.path.basename(path),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'encoding': 'base64/jpeg',
            'data': base64.b64encode(img_bytes).decode(),
        })

        try:
            self._dji_mqtt_client.publish(
                self._dji_stream_le_topic.text().strip(),
                payload=payload,
                qos=0,
                retain=False,
            )
        except Exception:
            pass

        self._dji_lbl_stream_status.setText(
            f'Stream: frame {self._dji_stream_index}/{len(self._dji_stream_files)} '
            f'({os.path.basename(path)})')

    def _dji_stream_stop(self):
        """Stop the MQTT stream and disconnect."""
        if self._dji_stream_timer:
            self._dji_stream_timer.stop()
            self._dji_stream_timer = None
        if self._dji_mqtt_client:
            try:
                self._dji_mqtt_client.loop_stop()
                self._dji_mqtt_client.disconnect()
            except Exception:
                pass
            self._dji_mqtt_client = None

        self._dji_btn_stream_start.setEnabled(True)
        self._dji_btn_stream_stop.setEnabled(False)
        self._dji_lbl_stream_status.setText('Stream: stopped')
        self._dji_log.append('■ Stream stopped')

    # ------------------------------------------------------------------
    # DJI – MQTT Stream Monitor (subscriber / viewer)
    # ------------------------------------------------------------------

    def _dji_monitor_start(self):
        """Subscribe to an MQTT topic and display incoming image frames."""
        import queue
        try:
            import paho.mqtt.client as mqtt_client  # type: ignore
        except ImportError:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, 'Monitor',
                'paho-mqtt is not installed.\n'
                'Run: pip install paho-mqtt  (in the QGIS Python environment)')
            return

        broker = self._dji_mon_le_broker.text().strip()
        port   = self._dji_mon_le_port.value()
        topic  = self._dji_mon_le_topic.text().strip()
        if not broker or not topic:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Monitor',
                'Set MQTT broker and topic before monitoring.')
            return

        self._dji_mon_queue = queue.Queue(maxsize=30)
        self._dji_mon_frame_count = 0

        def _on_connect(client, userdata, flags, rc, *args):
            if rc == 0:
                client.subscribe(userdata['topic'])
                self._dji_lbl_mon_status.setText(
                    f'Monitor: connected → {userdata["topic"]}')
            else:
                self._dji_lbl_mon_status.setText(
                    f'Monitor: connect error rc={rc}')

        def _on_message(client, userdata, msg):
            try:
                import json as _json, base64 as _b64
                data = _json.loads(msg.payload.decode('utf-8', errors='replace'))
                img_b64 = data.get('data', '')
                if img_b64:
                    img_bytes = _b64.b64decode(img_b64)
                    try:
                        userdata['q'].put_nowait(img_bytes)
                    except Exception:
                        pass  # queue full — drop frame
            except Exception:
                pass

        self._dji_mon_client = mqtt_client.Client(
            client_id='qgis-dji-monitor',
            userdata={'q': self._dji_mon_queue, 'topic': topic},
            protocol=(mqtt_client.MQTTv5
                      if hasattr(mqtt_client, 'MQTTv5')
                      else mqtt_client.MQTTv311),
        )
        self._dji_mon_client.on_connect = _on_connect
        self._dji_mon_client.on_message = _on_message

        try:
            self._dji_mon_client.connect(broker, port, keepalive=60)
            self._dji_mon_client.loop_start()
        except Exception as exc:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, 'Monitor', f'MQTT connect failed:\n{exc}')
            self._dji_mon_client = None
            return

        from PyQt5.QtCore import QTimer
        self._dji_mon_timer = QTimer(self)
        self._dji_mon_timer.setInterval(100)
        self._dji_mon_timer.timeout.connect(self._dji_monitor_poll)
        self._dji_mon_timer.start()

        self._dji_btn_mon_start.setEnabled(False)
        self._dji_btn_mon_stop.setEnabled(True)
        self._dji_lbl_mon_status.setText(
            f'Monitor: connecting to {broker}:{port} → {topic}…')

    def _dji_monitor_poll(self):
        """Drain the frame queue and refresh the preview (runs on Qt main thread)."""
        from PyQt5.QtGui import QPixmap
        from PyQt5.QtCore import Qt as _Qt
        if self._dji_mon_queue is None:
            return
        try:
            while not self._dji_mon_queue.empty():
                img_bytes = self._dji_mon_queue.get_nowait()
                self._dji_mon_frame_count += 1
                pix = QPixmap()
                pix.loadFromData(img_bytes)
                if not pix.isNull():
                    scaled = pix.scaled(
                        self._dji_mon_lbl_frame.width(),
                        self._dji_mon_lbl_frame.height(),
                        _Qt.KeepAspectRatio,
                        _Qt.SmoothTransformation,
                    )
                    self._dji_mon_lbl_frame.setPixmap(scaled)
                self._dji_lbl_mon_status.setText(
                    f'Monitor: frame #{self._dji_mon_frame_count} received')
        except Exception:
            pass

    def _dji_monitor_stop(self):
        """Stop the MQTT monitor and disconnect."""
        if self._dji_mon_timer:
            self._dji_mon_timer.stop()
            self._dji_mon_timer = None
        if self._dji_mon_client:
            try:
                self._dji_mon_client.loop_stop()
                self._dji_mon_client.disconnect()
            except Exception:
                pass
            self._dji_mon_client = None
        self._dji_mon_queue = None
        self._dji_btn_mon_start.setEnabled(True)
        self._dji_btn_mon_stop.setEnabled(False)
        self._dji_lbl_mon_status.setText('Monitor: stopped')

    # ------------------------------------------------------------------
    # OGC Connected Systems API dialog
    # ------------------------------------------------------------------

    def _open_cs_api_dialog(self):
        """Open the CS API dialog pre-filled with data from the DJI tab."""
        import json

        prefill: dict = {}

        # ── Drone identity ────────────────────────────────────────────
        valid_images = [m for m in (self._dji_images or []) if m.is_valid()]
        if valid_images:
            first = valid_images[0]
            model_slug = (first.model or 'unknown').lower().replace(' ', '-')
            serial_slug = (getattr(first, 'serial_number', '') or '').lower().replace(' ', '-')
            uid = f"urn:drone:dji:{model_slug}"
            if serial_slug:
                uid += f":{serial_slug}"
            prefill['drone_uid'] = uid
            prefill['drone_name'] = f"DJI {first.model or 'Drone'}"
            prefill['drone_model'] = first.model or ''
            prefill['drone_serial'] = getattr(first, 'serial_number', '') or ''

        # ── Mission timing ────────────────────────────────────────────
        timestamps = sorted([
            m.datetime_taken.isoformat() + 'Z'
            for m in valid_images
            if m.datetime_taken
        ])
        if timestamps:
            prefill['time_start'] = timestamps[0]
            prefill['time_end'] = timestamps[-1]

        mission = self._dji_le_mission.text().strip() or 'DJI Mission'
        prefill['mission_name'] = mission

        # ── Flight path from footprints.geojson ───────────────────────
        base_out = self._dji_le_outdir.text().strip()
        if base_out and mission:
            fp_path = os.path.join(base_out, mission, 'footprints.geojson')
            if os.path.exists(fp_path):
                try:
                    with open(fp_path) as fh:
                        footprints = json.load(fh)
                    # Derive a LineString from footprint centroids
                    coords = []
                    for feat in footprints.get('features', []):
                        geom = feat.get('geometry', {})
                        if geom.get('type') == 'Point':
                            coords.append(geom['coordinates'])
                        elif geom.get('type') == 'Polygon':
                            pts = geom['coordinates'][0]
                            cx = sum(p[0] for p in pts) / len(pts)
                            cy = sum(p[1] for p in pts) / len(pts)
                            coords.append([cx, cy])
                    if coords:
                        prefill['flight_path_geojson'] = {
                            'type': 'LineString',
                            'coordinates': coords,
                        }
                except Exception:
                    pass

        # ── Extra deployment properties from processed result ─────────
        if self._dji_result:
            extra: dict = {}
            if valid_images:
                first = valid_images[0]
                extra['make'] = 'DJI'
                extra['model'] = first.model or ''
                extra['serial'] = first.serial_number or ''
                gsds = [m.gsd_cm for m in valid_images if m.gsd_cm]
                if gsds:
                    extra['avg_gsd_cm'] = round(sum(gsds) / len(gsds), 3)
            prefill['extra_properties'] = extra

        dlg = CSAPIDialog(self, prefill_dji_data=prefill)
        dlg.exec_()

    # ==================================================================
    # HSI HYPERSPECTRAL TAB
    # ==================================================================

    def _setup_hsi_tab(self):
        """Build the HSI Hyperspectral tab and append it to tabWidget."""
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QProgressBar, QTextEdit,
            QComboBox, QFileDialog, QSizePolicy, QScrollArea,
            QCheckBox, QListWidget, QAbstractItemView,
        )

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

        # ── Status banner ─────────────────────────────────────────────
        try:
            from .hsi_adapter import HSI_AVAILABLE as _hav, HSI_ERROR as _herr
        except (ImportError, AttributeError, Exception):
            try:
                from hsi_adapter import HSI_AVAILABLE as _hav, HSI_ERROR as _herr  # type: ignore[no-redef]
            except (ImportError, AttributeError, Exception):
                _hav, _herr = False, 'hsi_adapter.py not found'

        # ── Input HSI files / directory ───────────────────────────────
        grp_in = QGroupBox('Input HSI Files')
        gl_in = QVBoxLayout(grp_in)

        # File list (multi-select for remove; single-item probe on current row)
        self._hsi_lw_input = QListWidget()
        self._hsi_lw_input.setMinimumHeight(90)
        self._hsi_lw_input.setMaximumHeight(160)
        self._hsi_lw_input.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._hsi_lw_input.setToolTip(
            'Add individual files or click "Browse Directory…" to load all HSI '
            'files in a folder at once.  Each file produces a <stem>_browse.heif '
            'and (optionally) a <stem>_cube.<ext> in the output directory.'
        )
        gl_in.addWidget(self._hsi_lw_input)

        # Button row
        hl_btns = QHBoxLayout()
        btn_add_files = QPushButton('Add File(s)…')
        btn_add_files.setToolTip('Add one or more HSI files to the list')
        btn_add_files.clicked.connect(self._hsi_add_files)
        hl_btns.addWidget(btn_add_files)
        btn_browse_dir = QPushButton('Browse Directory…')
        btn_browse_dir.setToolTip('Scan a directory and add all recognised HSI files')
        btn_browse_dir.clicked.connect(self._hsi_browse_dir)
        hl_btns.addWidget(btn_browse_dir)
        btn_remove = QPushButton('Remove Selected')
        btn_remove.clicked.connect(self._hsi_remove_selected)
        hl_btns.addWidget(btn_remove)
        hl_btns.addStretch(1)
        gl_in.addLayout(hl_btns)

        self._hsi_lbl_probe = QLabel('')
        self._hsi_lbl_probe.setWordWrap(True)
        gl_in.addWidget(self._hsi_lbl_probe)

        self._hsi_lw_input.currentRowChanged.connect(self._hsi_probe_selected)
        root.addWidget(grp_in)

        # ── Output options ────────────────────────────────────────────
        grp_fc = QGroupBox('Output Options')
        gl_fc = QVBoxLayout(grp_fc)

        # Output directory (optional – defaults to same directory as each input)
        hl_outdir = QHBoxLayout()
        hl_outdir.addWidget(QLabel('Output directory:'))
        self._hsi_le_outdir = QLineEdit()
        self._hsi_le_outdir.setPlaceholderText(
            'Leave blank to write next to each input file'
        )
        hl_outdir.addWidget(self._hsi_le_outdir)
        btn_browse_outdir = QPushButton('Browse…')
        btn_browse_outdir.clicked.connect(self._hsi_browse_outdir)
        hl_outdir.addWidget(btn_browse_outdir)
        gl_fc.addLayout(hl_outdir)

        # False-colour method
        hl_method = QHBoxLayout()
        hl_method.addWidget(QLabel('False-colour method:'))
        self._hsi_cmb_method = QComboBox()
        self._hsi_cmb_method.addItems([
            'pca — Principal Component Analysis (recommended)',
            'band_select — Nearest visible-wavelength bands (requires wavelengths)',
        ])
        hl_method.addWidget(self._hsi_cmb_method, 1)
        gl_fc.addLayout(hl_method)

        root.addWidget(grp_fc)

        # ── Full spectral cube export (optional) ──────────────────────
        grp_cube = QGroupBox('Full Spectral Cube Export (optional)')
        grp_cube.setCheckable(True)
        grp_cube.setChecked(False)
        gl_cube = QVBoxLayout(grp_cube)
        self._hsi_grp_cube = grp_cube

        # Output cube path is auto-generated as <out_dir>/<stem>_cube.<ext>
        gl_cube.addWidget(QLabel(
            'Cube files are named  <em>&lt;stem&gt;_cube.&lt;ext&gt;</em>  '
            'and written to the output directory above.'
        ))

        hl_cube_drv = QHBoxLayout()
        hl_cube_drv.addWidget(QLabel('Driver:'))
        self._hsi_cmb_driver = QComboBox()
        self._hsi_cmb_driver.addItems([
            'GTiff — GeoTIFF (multi-band)',
            'JP2GROK — JPEG-2000 via Grok (GDAL ≥ 3.13) ★',
            'JP2OpenJPEG — JPEG-2000 via OpenJPEG',
            'HFA — ERDAS Imagine (.img)',
        ])
        hl_cube_drv.addWidget(self._hsi_cmb_driver, 1)
        gl_cube.addLayout(hl_cube_drv)

        root.addWidget(grp_cube)

        # ── Run / progress ────────────────────────────────────────────
        grp_run = QGroupBox('Convert')
        gl_run = QVBoxLayout(grp_run)

        hl_run = QHBoxLayout()
        self._hsi_btn_run = QPushButton('Convert HSI → GIMI')
        self._hsi_btn_run.setStyleSheet('font-weight:bold;')
        self._hsi_btn_run.clicked.connect(self._hsi_run)
        hl_run.addWidget(self._hsi_btn_run, 1)
        gl_run.addLayout(hl_run)

        self._hsi_progress = QProgressBar()
        self._hsi_progress.setRange(0, 100)
        self._hsi_progress.setFormat('%v / %m files')
        self._hsi_progress.setVisible(False)
        gl_run.addWidget(self._hsi_progress)

        # Update button label whenever the file list changes
        self._hsi_lw_input.model().rowsInserted.connect(self._hsi_update_run_btn)
        self._hsi_lw_input.model().rowsRemoved.connect(self._hsi_update_run_btn)

        self._hsi_log = QTextEdit()
        self._hsi_log.setReadOnly(True)
        self._hsi_log.setMinimumHeight(120)
        self._hsi_log.setMaximumHeight(200)
        self._hsi_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        gl_run.addWidget(self._hsi_log)

        root.addWidget(grp_run)
        root.addStretch(1)

        self.tabWidget.addTab(tab, 'HSI Hyperspectral')

    # ── HSI helpers ───────────────────────────────────────────────────

    # Recognised HSI extensions for directory scanning
    _HSI_EXTENSIONS = frozenset({
        '.tif', '.tiff', '.hdr', '.h5', '.hdf5',
        '.img', '.bil', '.bip', '.bsq', '.nc', '.he4', '.he5',
    })

    def _hsi_update_run_btn(self):
        n = self._hsi_lw_input.count()
        if n == 0:
            self._hsi_btn_run.setText('Convert HSI → GIMI')
        elif n == 1:
            self._hsi_btn_run.setText('Convert 1 file → GIMI')
        else:
            self._hsi_btn_run.setText(f'Convert {n} files → GIMI')

    def _hsi_add_files(self):
        """Open a multi-file picker and add selected files to the list."""
        from PyQt5.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Select HSI file(s)', '',
            'HSI files (*.tif *.tiff *.hdr *.h5 *.hdf5 *.img *.bil *.bip *.bsq *.nc);;'
            'All files (*)',
        )
        self._hsi_add_paths(paths)

    def _hsi_browse_dir(self):
        """Scan a directory and add all recognised HSI files to the list."""
        from PyQt5.QtWidgets import QFileDialog
        directory = QFileDialog.getExistingDirectory(
            self, 'Select HSI directory', '',
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not directory:
            return
        found = []
        for entry in sorted(os.listdir(directory)):
            ext = os.path.splitext(entry)[1].lower()
            if ext in self._HSI_EXTENSIONS:
                found.append(os.path.join(directory, entry))
        if not found:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self, 'GIMI Imagery Workbench',
                f'No recognised HSI files found in:\n{directory}\n\n'
                f'Supported extensions: {", ".join(sorted(self._HSI_EXTENSIONS))}'
            )
            return
        self._hsi_add_paths(found)
        # Auto-fill output directory to the scanned directory
        if not self._hsi_le_outdir.text():
            self._hsi_le_outdir.setText(directory)

    def _hsi_add_paths(self, paths):
        """Add paths to the list, skipping duplicates."""
        existing = {self._hsi_lw_input.item(i).text()
                    for i in range(self._hsi_lw_input.count())}
        for p in paths:
            if p and p not in existing:
                self._hsi_lw_input.addItem(p)
                existing.add(p)

    def _hsi_remove_selected(self):
        """Remove all currently selected items from the file list."""
        for item in self._hsi_lw_input.selectedItems():
            self._hsi_lw_input.takeItem(self._hsi_lw_input.row(item))

    def _hsi_browse_outdir(self):
        """Browse for the output directory."""
        from PyQt5.QtWidgets import QFileDialog
        directory = QFileDialog.getExistingDirectory(
            self, 'Select output directory', '',
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if directory:
            self._hsi_le_outdir.setText(directory)

    def _hsi_probe_selected(self, row: int):
        """Update the probe label for the currently highlighted list item."""
        if row < 0:
            self._hsi_lbl_probe.setText('')
            return
        item = self._hsi_lw_input.item(row)
        if item is None:
            self._hsi_lbl_probe.setText('')
            return
        self._hsi_probe_file(item.text())

    def _hsi_probe_file(self, filepath: str):
        """Show band/size/wavelength info for a file path."""
        if not filepath or not os.path.exists(filepath):
            self._hsi_lbl_probe.setText('')
            return
        try:
            from .hsi_adapter import probe_hsi_file as _phf
        except (ImportError, AttributeError, Exception):
            try:
                from hsi_adapter import probe_hsi_file as _phf  # type: ignore[no-redef]
            except (ImportError, AttributeError, Exception):
                self._hsi_lbl_probe.setText('<i>hsi_adapter not available</i>')
                return
        try:
            info = _phf(filepath)
        except Exception as exc:
            self._hsi_lbl_probe.setText(f'<i>Probe error: {exc}</i>')
            return
        parts = [
            f"Format: <b>{info['format']}</b>",
            f"Bands: <b>{info['bands']}</b>",
            f"Size: <b>{info['width']} × {info['height']}</b> px",
        ]
        if info['has_wavelengths']:
            parts.append(
                f"Wavelengths: <b>{info['wavelength_min']:.1f} – {info['wavelength_max']:.1f} nm</b>"
            )
        self._hsi_lbl_probe.setText('  |  '.join(parts))

    def _hsi_run(self):
        """Validate inputs and start batch HSI → GIMI conversion in a worker thread."""
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import QThread

        # Collect all files from the list widget
        file_paths = [
            self._hsi_lw_input.item(i).text()
            for i in range(self._hsi_lw_input.count())
        ]
        # Filter to existing paths only
        missing = [p for p in file_paths if not os.path.exists(p)]
        file_paths = [p for p in file_paths if os.path.exists(p)]

        if not file_paths:
            QMessageBox.warning(
                self, 'GIMI Imagery Workbench',
                'Please add at least one valid HSI file to the list.'
                + (f'\n\nMissing files:\n' + '\n'.join(missing) if missing else '')
            )
            return

        if missing:
            QMessageBox.warning(
                self, 'GIMI Imagery Workbench',
                f'{len(missing)} file(s) not found and will be skipped:\n' + '\n'.join(missing)
            )

        out_dir = self._hsi_le_outdir.text().strip() or None
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                QMessageBox.critical(
                    self, 'GIMI Imagery Workbench',
                    f'Cannot create output directory:\n{out_dir}\n\n{e}'
                )
                return

        method_text = self._hsi_cmb_method.currentText()
        method = 'pca' if method_text.startswith('pca') else 'band_select'

        export_cube = self._hsi_grp_cube.isChecked()
        drv_text = self._hsi_cmb_driver.currentText()
        if drv_text.startswith('JP2GROK'):
            cube_driver = 'JP2GROK'
        elif drv_text.startswith('JP2OpenJPEG'):
            cube_driver = 'JP2OpenJPEG'
        elif drv_text.startswith('HFA'):
            cube_driver = 'HFA'
        else:
            cube_driver = 'GTiff'

        self._hsi_log.clear()
        n = len(file_paths)
        self._hsi_log.append(f'Starting batch conversion: {n} file(s) …')
        self._hsi_progress.setRange(0, n)
        self._hsi_progress.setValue(0)
        self._hsi_progress.setVisible(True)
        self._hsi_btn_run.setEnabled(False)

        try:
            from .heif_processor import HEIFProcessor
        except (ImportError, AttributeError, Exception):
            from heif_processor import HEIFProcessor  # type: ignore[no-redef]

        self._hsi_processor_inst = HEIFProcessor()

        self._hsi_thread = QThread()
        self._hsi_worker = _HSIBatchWorker(
            self._hsi_processor_inst, file_paths, out_dir,
            method, cube_driver, export_cube
        )
        self._hsi_worker.moveToThread(self._hsi_thread)
        self._hsi_thread.started.connect(self._hsi_worker.run)
        self._hsi_worker.file_done.connect(self._hsi_on_file_done)
        self._hsi_worker.all_done.connect(self._hsi_on_all_done)
        self._hsi_worker.all_done.connect(self._hsi_thread.quit)
        self._hsi_thread.start()

    def _hsi_on_file_done(self, path: str, success: bool, provenance: dict):
        """Called after each file in the batch completes."""
        done = self._hsi_progress.value() + 1
        self._hsi_progress.setValue(done)
        stem = os.path.basename(path)
        if success:
            hsi_meta = provenance.get('hsi', {})
            bands = hsi_meta.get('band_count', '?')
            w = hsi_meta.get('width', '?')
            h = hsi_meta.get('height', '?')
            self._hsi_log.append(
                f'<span style="color:green;">✓</span> <b>{stem}</b> — '
                f'{bands} bands, {w}×{h} px'
            )
        else:
            err = provenance.get('error', 'unknown error')
            self._hsi_log.append(
                f'<span style="color:red;">✗</span> <b>{stem}</b> — {err}'
            )

    def _hsi_on_all_done(self, succeeded: int, total: int):
        """Called when the entire batch finishes."""
        from PyQt5.QtWidgets import QMessageBox
        self._hsi_btn_run.setEnabled(True)
        if succeeded == total:
            self._hsi_log.append(
                f'<span style="color:green;font-weight:bold;">'
                f'✓ All {total} file(s) converted successfully.</span>'
            )
        else:
            failed = total - succeeded
            self._hsi_log.append(
                f'<span style="color:orange;font-weight:bold;">'
                f'⚠ {succeeded}/{total} succeeded, {failed} failed.</span>'
            )
            QMessageBox.warning(
                self, 'GIMI Imagery Workbench',
                f'Batch conversion finished with {failed} failure(s).\n'
                f'See the log for details.'
            )

    # ==================================================================
    # SENTINEL-1 SAR TAB
    # ==================================================================

    def _setup_sar_tab(self):
        """Build the Sentinel-1 SAR tab and append it to tabWidget."""
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QProgressBar, QTextEdit,
            QComboBox, QFileDialog, QSizePolicy, QScrollArea,
            QFormLayout,
        )

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

        # ── 1. Input ──────────────────────────────────────────────────
        grp_in = QGroupBox('Sentinel-1 SAFE Folder')
        gl_in = QHBoxLayout(grp_in)
        self._sar_le_safe = QLineEdit()
        self._sar_le_safe.setPlaceholderText(
            'Select .SAFE folder (e.g. S1A_IW_SLC__1SSH_…_081F1B_61A7.SAFE)')
        self._sar_btn_browse = QPushButton('Browse…')
        self._sar_btn_browse.setAutoDefault(False)
        self._sar_btn_browse.setMaximumWidth(90)
        self._sar_btn_browse.clicked.connect(self._sar_browse_safe)
        self._sar_btn_load = QPushButton('Load Metadata')
        self._sar_btn_load.setAutoDefault(False)
        self._sar_btn_load.setMinimumWidth(120)
        self._sar_btn_load.clicked.connect(self._sar_load_metadata)
        gl_in.addWidget(self._sar_le_safe, 1)
        gl_in.addWidget(self._sar_btn_browse)
        gl_in.addWidget(self._sar_btn_load)
        root.addWidget(grp_in)

        # ── 2. Metadata display ───────────────────────────────────────
        grp_meta = QGroupBox('SAR Product Metadata')
        fl_meta = QFormLayout(grp_meta)
        fl_meta.setLabelAlignment(Qt.AlignRight)

        def _ro(placeholder=''):
            w = QLineEdit()
            w.setReadOnly(True)
            w.setPlaceholderText(placeholder)
            return w

        self._sar_le_mission    = _ro('mission')
        self._sar_le_mode       = _ro('mode')
        self._sar_le_pol        = _ro('polarisation')
        self._sar_le_orbit      = _ro('orbit')
        self._sar_le_pass       = _ro('pass direction')
        self._sar_le_start      = _ro('start time')
        self._sar_le_stop       = _ro('stop time')
        self._sar_le_bbox       = _ro('bounding box (min_lon,min_lat,max_lon,max_lat)')
        self._sar_le_freq       = _ro('radar frequency (GHz)')
        self._sar_le_prf        = _ro('PRF (Hz)')
        self._sar_le_subswaths  = _ro('sub-swath TIFFs found')

        fl_meta.addRow('Mission:',      self._sar_le_mission)
        fl_meta.addRow('Mode:',         self._sar_le_mode)
        fl_meta.addRow('Polarisation:', self._sar_le_pol)
        fl_meta.addRow('Orbit #:',      self._sar_le_orbit)
        fl_meta.addRow('Pass:',         self._sar_le_pass)
        fl_meta.addRow('Start:',        self._sar_le_start)
        fl_meta.addRow('Stop:',         self._sar_le_stop)
        fl_meta.addRow('Bbox:',         self._sar_le_bbox)
        fl_meta.addRow('Radar freq:',   self._sar_le_freq)
        fl_meta.addRow('PRF:',          self._sar_le_prf)
        fl_meta.addRow('Sub-swaths:',   self._sar_le_subswaths)
        root.addWidget(grp_meta)

        # ── 3. Liability & Claims fields ──────────────────────────────
        grp_lia = QGroupBox('Liability & Claims (STAC extension)')
        fl_lia = QFormLayout(grp_lia)
        fl_lia.setLabelAlignment(Qt.AlignRight)

        self._sar_le_resp_party     = QLineEdit()
        self._sar_le_resp_party.setPlaceholderText('e.g. ESA / Copernicus')
        self._sar_le_claim_status   = QComboBox()
        self._sar_le_claim_status.addItems([
            'pending', 'under_review', 'resolved', 'rejected', 'withdrawn'])
        self._sar_le_claim_type     = QLineEdit()
        self._sar_le_claim_type.setText('satellite_data_provision')
        self._sar_le_jurisdiction   = QLineEdit()
        self._sar_le_jurisdiction.setPlaceholderText('e.g. EU, AU, US')
        self._sar_le_insurer        = QLineEdit()
        self._sar_le_insurer.setPlaceholderText('Insurance provider (optional)')
        self._sar_le_policy         = QLineEdit()
        self._sar_le_policy.setPlaceholderText('Policy number (optional)')

        fl_lia.addRow('Responsible party:', self._sar_le_resp_party)
        fl_lia.addRow('Claim status:',      self._sar_le_claim_status)
        fl_lia.addRow('Claim type:',        self._sar_le_claim_type)
        fl_lia.addRow('Jurisdiction:',      self._sar_le_jurisdiction)
        fl_lia.addRow('Insurer:',           self._sar_le_insurer)
        fl_lia.addRow('Policy #:',          self._sar_le_policy)
        root.addWidget(grp_lia)

        # ── 4. Output ─────────────────────────────────────────────────
        grp_out = QGroupBox('Output')
        hl_out = QHBoxLayout(grp_out)
        hl_out.addWidget(QLabel('Output directory:'))
        self._sar_le_outdir = QLineEdit()
        self._sar_le_outdir.setPlaceholderText('Folder where HEIF, STAC JSON and TTL files will be written')
        btn_out = QPushButton('Browse…')
        btn_out.setAutoDefault(False)
        btn_out.setMaximumWidth(90)
        btn_out.clicked.connect(self._sar_browse_outdir)
        hl_out.addWidget(self._sar_le_outdir, 1)
        hl_out.addWidget(btn_out)
        root.addWidget(grp_out)

        # ── 5. Process / cancel ───────────────────────────────────────
        grp_proc = QGroupBox('Processing')
        gl_proc = QVBoxLayout(grp_proc)

        hl_btns = QHBoxLayout()
        self._sar_btn_process = QPushButton(
            'Convert SAR → Amplitude HEIF + STAC + TTL')
        self._sar_btn_process.setStyleSheet('font-weight:bold;')
        self._sar_btn_process.setEnabled(False)
        self._sar_btn_process.clicked.connect(self._sar_start_processing)
        hl_btns.addWidget(self._sar_btn_process, 1)
        self._sar_btn_cancel = QPushButton('Cancel')
        self._sar_btn_cancel.setEnabled(False)
        self._sar_btn_cancel.clicked.connect(self._sar_cancel)
        hl_btns.addWidget(self._sar_btn_cancel)
        gl_proc.addLayout(hl_btns)

        self._sar_progress = QProgressBar()
        self._sar_progress.setRange(0, 100)
        self._sar_progress.setVisible(False)
        gl_proc.addWidget(self._sar_progress)

        self._sar_log = QTextEdit()
        self._sar_log.setReadOnly(True)
        self._sar_log.setMinimumHeight(140)
        self._sar_log.setMaximumHeight(240)
        self._sar_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        gl_proc.addWidget(self._sar_log)

        root.addWidget(grp_proc)
        root.addStretch(1)

        self.tabWidget.addTab(tab, 'Sentinel-1 SAR')

    # ── SAR helpers ───────────────────────────────────────────────────

    def _sar_browse_safe(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Select Sentinel-1 .SAFE Folder',
            os.path.expanduser('~'),
            QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog)
        if folder:
            self._sar_le_safe.setText(folder)

    def _sar_browse_outdir(self):
        folder = QFileDialog.getExistingDirectory(
            self, 'Select Output Directory',
            self._sar_le_outdir.text() or os.path.expanduser('~'),
            QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog)
        if folder:
            self._sar_le_outdir.setText(folder)

    def _sar_load_metadata(self):
        """Parse the SAFE annotation XMLs and populate the metadata fields."""
        safe = self._sar_le_safe.text().strip()
        if not safe or not os.path.isdir(safe):
            QMessageBox.warning(self, 'Sentinel-1 SAR',
                                'Please select a valid .SAFE folder first.')
            return
        try:
            meta = _parse_safe_metadata(safe)
        except Exception as exc:
            QMessageBox.critical(self, 'Metadata Error', str(exc))
            return

        self._sar_meta = meta
        self._sar_safe_path = safe

        # Populate read-only fields
        self._sar_le_mission.setText(meta.get('mission_id', ''))
        self._sar_le_mode.setText(
            f"{meta.get('mode','')} – {meta.get('product_type','')} – "
            f"slice {meta.get('slice_number','?')}")
        self._sar_le_pol.setText(meta.get('polarisation', ''))
        self._sar_le_orbit.setText(str(meta.get('absolute_orbit', '')))
        self._sar_le_pass.setText(meta.get('pass', ''))
        self._sar_le_start.setText(meta.get('start_time', ''))
        self._sar_le_stop.setText(meta.get('stop_time', ''))
        bbox = meta.get('bbox', [])
        self._sar_le_bbox.setText(
            f'{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}'
            if len(bbox) == 4 else '')
        rf = meta.get('radar_frequency', 0)
        self._sar_le_freq.setText(f'{rf/1e9:.6f} GHz' if rf else '')
        prf = meta.get('prf', 0)
        self._sar_le_prf.setText(f'{prf:.3f} Hz' if prf else '')
        sw_names = [sw['swath'] for sw in meta.get('subswaths', [])]
        self._sar_le_subswaths.setText(', '.join(sw_names) or 'none found')

        # Set default output dir next to SAFE folder
        if not self._sar_le_outdir.text():
            self._sar_le_outdir.setText(
                os.path.join(os.path.dirname(safe),
                             os.path.basename(safe).replace('.SAFE', '_gimi')))

        self._sar_btn_process.setEnabled(bool(meta.get('subswaths')))
        self._sar_log.append(
            f'✓ Loaded metadata: {len(meta.get("subswaths",[]))} sub-swath(s), '
            f'orbit {meta.get("absolute_orbit")}, '
            f'{meta.get("pass")} pass.')

    def _sar_start_processing(self):
        if not self._sar_meta or not self._sar_meta.get('subswaths'):
            QMessageBox.warning(self, 'No Metadata',
                                'Load SAFE metadata first.')
            return
        out_dir = self._sar_le_outdir.text().strip()
        if not out_dir:
            QMessageBox.warning(self, 'No Output',
                                'Please select an output directory.')
            return

        liability_fields = {
            'responsible_party': self._sar_le_resp_party.text().strip(),
            'claim_status':      self._sar_le_claim_status.currentText(),
            'claim_type':        self._sar_le_claim_type.text().strip(),
            'jurisdiction':      self._sar_le_jurisdiction.text().strip(),
            'insurance_provider': self._sar_le_insurer.text().strip(),
            'policy_number':     self._sar_le_policy.text().strip(),
        }

        self._sar_log.clear()
        self._sar_progress.setVisible(True)
        self._sar_progress.setValue(0)
        self._sar_btn_process.setEnabled(False)
        self._sar_btn_cancel.setEnabled(True)

        self._sar_worker = _SARWorker(
            safe_path=self._sar_safe_path,
            meta=self._sar_meta,
            out_dir=out_dir,
            liability_fields=liability_fields,
        )
        self._sar_thread = QThread()
        self._sar_worker.moveToThread(self._sar_thread)
        self._sar_thread.started.connect(self._sar_worker.run)
        self._sar_worker.progress.connect(self._sar_on_progress)
        self._sar_worker.finished.connect(self._sar_on_finished)
        self._sar_worker.finished.connect(self._sar_thread.quit)
        self._sar_thread.start()

    def _sar_cancel(self):
        if self._sar_worker:
            self._sar_worker.cancelled = True
        self._sar_log.append('Cancellation requested…')

    def _sar_on_progress(self, pct: int, msg: str):
        self._sar_progress.setValue(pct)
        self._sar_log.append(f'[{pct:3d}%] {msg}')

    def _sar_on_finished(self, result: dict):
        self._sar_btn_process.setEnabled(True)
        self._sar_btn_cancel.setEnabled(False)
        if self._sar_thread:
            self._sar_thread.quit()
            self._sar_thread.wait()
        self._sar_worker = None
        self._sar_thread = None

        if result.get('success'):
            self._sar_progress.setValue(100)
            files = result.get('files', [])
            ok_count = sum(1 for f in files if f.get('heif_ok'))
            self._sar_log.append(
                f'<span style="color:green;font-weight:bold;">'
                f'✓ Done. {len(files)} sub-swath(s) processed, '
                f'{ok_count} HEIF file(s) created.</span>')
            if result.get('collection'):
                self._sar_log.append(
                    f'  STAC Collection → {result["collection"]}')
            if result.get('combined_ttl'):
                self._sar_log.append(
                    f'  Combined TTL    → {result["combined_ttl"]}')
            for f in files:
                status = '✓' if f.get('heif_ok') else '⚠ (PNG fallback)'
                self._sar_log.append(
                    f'  {f["swath"]}: HEIF {status} | STAC {f["stac"]} | TTL {f["ttl"]}')
        else:
            self._sar_progress.setValue(0)
            self._sar_log.append(
                f'<span style="color:red;font-weight:bold;">'
                f'✗ {result.get("error","Unknown error")}</span>')


# ---------------------------------------------------------------------------
# SAFE metadata parser
# ---------------------------------------------------------------------------

def _parse_safe_metadata(safe_path: str) -> dict:
    """Parse a Sentinel-1 .SAFE folder and return a metadata dict."""
    import os, glob
    from xml.etree import ElementTree as ET

    ann_dir = os.path.join(safe_path, 'annotation')
    meas_dir = os.path.join(safe_path, 'measurement')

    # Find annotation XMLs (not calibration/noise/rfi)
    xml_files = sorted(
        f for f in glob.glob(os.path.join(ann_dir, 's1a-*.xml'))
        if os.path.basename(f).startswith('s1a-')
    )
    if not xml_files:
        raise ValueError('No annotation XML files found in SAFE/annotation/')

    meta = {}
    all_lats, all_lons = [], []
    subswaths = []

    for xml_path in xml_files:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        ads = root.find('.//adsHeader')
        if ads is not None and not meta:
            meta['mission_id']    = _xt(ads, 'missionId', 'S1A')
            meta['product_type']  = _xt(ads, 'productType', 'SLC')
            meta['polarisation']  = _xt(ads, 'polarisation', 'HH')
            meta['mode']          = _xt(ads, 'mode', 'IW')
            meta['absolute_orbit'] = int(_xt(ads, 'absoluteOrbitNumber', '0'))
            meta['relative_orbit'] = meta['absolute_orbit'] % 175  # S1A repeat

        # Timing from imageInformation
        ii = root.find('.//imageInformation')
        if ii is not None and not meta.get('start_time'):
            meta['start_time'] = _xt(ii, 'productFirstLineUtcTime')
            meta['stop_time']  = _xt(ii, 'productLastLineUtcTime')
            meta['ascending_node_time'] = _xt(ii, 'ascendingNodeTime')
            meta['slice_number'] = _xt(ii, 'sliceNumber', '?')

        # Radar frequency & PRF (first XML wins)
        if not meta.get('radar_frequency'):
            rf = root.find('.//radarFrequency')
            if rf is not None:
                meta['radar_frequency'] = float(rf.text)
            af = root.find('.//azimuthFrequency')
            if af is not None:
                meta['prf'] = float(af.text)

        # Orbit direction
        if not meta.get('pass'):
            p = root.find('.//pass')
            if p is not None:
                meta['pass'] = p.text

        # Geolocation points for this sub-swath
        pts = root.findall('.//geolocationGridPoint')
        lats = [float(p.find('latitude').text) for p in pts]
        lons = [float(p.find('longitude').text) for p in pts]
        all_lats.extend(lats)
        all_lons.extend(lons)

        # Pixel spacing
        rps = root.find('.//rangePixelSpacing')
        aps = root.find('.//azimuthPixelSpacing')

        # Quality index
        qi = root.find('.//productQualityIndex')

        # Incidence angle mid-swath
        iam = root.find('.//incidenceAngleMidSwath')

        # Find corresponding TIFF
        sw_tag = _xt(ads, 'swath', '') if ads is not None else ''
        pol    = meta.get('polarisation', 'hh').lower()
        tiff_pat = os.path.join(
            meas_dir,
            f's1a-{sw_tag.lower()}-slc-{pol}-*.tiff')
        tiff_files = glob.glob(tiff_pat)
        tiff_path = tiff_files[0] if tiff_files else ''

        # Fallback: any TIFF matching swath
        if not tiff_path:
            for tf in glob.glob(os.path.join(meas_dir, '*.tiff')):
                if sw_tag.lower() in os.path.basename(tf):
                    tiff_path = tf
                    break

        subswaths.append({
            'swath':               sw_tag or f'IW{len(subswaths)+1}',
            'tiff':                tiff_path,
            'annotation_xml':      xml_path,
            'range_pixel_spacing': float(rps.text) if rps is not None else None,
            'azimuth_pixel_spacing': float(aps.text) if aps is not None else None,
            'incidence_angle_mid': float(iam.text) if iam is not None else None,
            'quality_index':       float(qi.text) if qi is not None else None,
        })

    meta['bbox'] = [
        min(all_lons), min(all_lats),
        max(all_lons), max(all_lats),
    ] if all_lats else []
    meta['subswaths'] = [sw for sw in subswaths if sw['tiff']]

    return meta


def _xt(element, tag: str, default: str = '') -> str:
    """Extract text from a child tag, return default if not found."""
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else default


# ---------------------------------------------------------------------------
# Worker thread for batch HSI → GIMI conversion
# ---------------------------------------------------------------------------

class _HSIBatchWorker(QObject):
    """Runs HEIFProcessor.convert_hsi_to_gimi() for each file in a background thread.

    Signals
    -------
    file_done(path, success, provenance)
        Emitted after each file completes.
    all_done(succeeded, total)
        Emitted once when all files have been processed.
    """

    file_done = pyqtSignal(str, bool, dict)
    all_done = pyqtSignal(int, int)

    # Extension → output extension map for cube files
    _CUBE_EXT = {
        'GTiff': '.tif',
        'JP2GROK': '.jp2',
        'JP2OpenJPEG': '.jp2',
        'HFA': '.img',
    }

    def __init__(self, processor, file_paths, out_dir,
                 false_colour_method, cube_driver, export_cube,
                 parent=None):
        super().__init__(parent)
        self._proc = processor
        self._paths = list(file_paths)
        self._out_dir = out_dir          # None → same dir as each input file
        self._method = false_colour_method
        self._cube_driver = cube_driver
        self._export_cube = export_cube

    def run(self):
        import os as _os
        total = len(self._paths)
        succeeded = 0
        cube_ext = self._CUBE_EXT.get(self._cube_driver, '.tif')

        for path in self._paths:
            stem = _os.path.splitext(_os.path.basename(path))[0]
            dest_dir = self._out_dir or _os.path.dirname(path) or '.'

            heif_out = _os.path.join(dest_dir, stem + '_browse.heif')
            cube_out = (
                _os.path.join(dest_dir, stem + '_cube' + cube_ext)
                if self._export_cube else None
            )

            try:
                ok, prov = self._proc.convert_hsi_to_gimi(
                    hsi_path=path,
                    output_heif=heif_out,
                    output_cube=cube_out,
                    false_colour_method=self._method,
                    cube_driver=self._cube_driver,
                )
                if ok:
                    succeeded += 1
                self.file_done.emit(path, ok, prov)
            except Exception as exc:
                self.file_done.emit(path, False, {'error': str(exc)})

        self.all_done.emit(succeeded, total)


# =============================================================================
# Sentinel-1 SAR worker
# =============================================================================


# =============================================================================
# IPFS Upload dialog  (mirrors "Upload to IPFS" tab in Asbestos HSI Manager)
# =============================================================================

class _IPFSUploadDialog(QDialog):
    """Standalone dialog replicating the 'Upload to IPFS' tab from the
    Asbestos HSI Manager.  Accepts any local file for upload."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Upload to IPFS')
        self.setMinimumWidth(640)
        self.setMinimumHeight(560)
        self._file_to_upload = None   # path selected by user
        self._last_ipfs_url = None
        self._last_cid = None
        self._init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
            QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
            QSlider, QSpinBox, QTextEdit, QDialogButtonBox, QFileDialog,
        )
        from PyQt5.QtCore import Qt

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── File selection ──────────────────────────────────────────────
        grp_file = QGroupBox('File to Upload')
        hl_file = QHBoxLayout(grp_file)
        self._le_file = QLineEdit()
        self._le_file.setPlaceholderText('Select a file to upload to IPFS…')
        self._le_file.setReadOnly(True)
        btn_browse = QPushButton('Browse…')
        btn_browse.setMaximumWidth(90)
        btn_browse.clicked.connect(self._browse_file)
        hl_file.addWidget(self._le_file)
        hl_file.addWidget(btn_browse)
        root.addWidget(grp_file)

        # ── Compression options ─────────────────────────────────────────
        grp_comp = QGroupBox('Compression Options')
        gl_comp = QGridLayout(grp_comp)

        gl_comp.addWidget(QLabel('Enable Lossy Compression:'), 0, 0)
        self._chk_compress = QCheckBox('Reduce file size before upload')
        self._chk_compress.setChecked(False)
        gl_comp.addWidget(self._chk_compress, 0, 1)

        gl_comp.addWidget(QLabel('Compression Type:'), 1, 0)
        self._cmb_compress_type = QComboBox()
        self._cmb_compress_type.addItems(['JPEG', 'JPEG2000', 'LZW'])
        self._cmb_compress_type.setCurrentText('JPEG')
        gl_comp.addWidget(self._cmb_compress_type, 1, 1)

        gl_comp.addWidget(QLabel('Compression Quality:'), 2, 0)
        self._slider_quality = QSlider(Qt.Horizontal)
        self._slider_quality.setMinimum(1)
        self._slider_quality.setMaximum(100)
        self._slider_quality.setValue(75)
        self._slider_quality.setTickPosition(QSlider.TicksBelow)
        self._slider_quality.setTickInterval(10)
        self._lbl_quality = QLabel('75%  (Good quality, smaller size)')
        self._slider_quality.valueChanged.connect(self._update_quality_label)
        gl_comp.addWidget(self._slider_quality, 2, 1)
        gl_comp.addWidget(self._lbl_quality, 2, 2)

        gl_comp.addWidget(QLabel('Max File Size:'), 3, 0)
        gl_comp.addWidget(QLabel('10 MB  (IPFS upload limit)'), 3, 1)
        root.addWidget(grp_comp)

        # ── Upload status ───────────────────────────────────────────────
        grp_status = QGroupBox('Upload Status')
        vl_status = QVBoxLayout(grp_status)
        self._txt_status = QTextEdit()
        self._txt_status.setReadOnly(True)
        self._txt_status.setMaximumHeight(160)
        vl_status.addWidget(self._txt_status)
        root.addWidget(grp_status)

        # ── Result ──────────────────────────────────────────────────────
        grp_result = QGroupBox('Result')
        gl_res = QGridLayout(grp_result)
        gl_res.addWidget(QLabel('IPFS URL:'), 0, 0)
        self._le_ipfs_url = QLineEdit()
        self._le_ipfs_url.setReadOnly(True)
        gl_res.addWidget(self._le_ipfs_url, 0, 1)
        gl_res.addWidget(QLabel('CID:'), 1, 0)
        self._le_cid = QLineEdit()
        self._le_cid.setReadOnly(True)
        gl_res.addWidget(self._le_cid, 1, 1)
        root.addWidget(grp_result)

        # ── Buttons ─────────────────────────────────────────────────────
        hl_btns = QHBoxLayout()
        self._btn_upload = QPushButton('⬆  Upload to IPFS')
        self._btn_upload.setMinimumHeight(36)
        self._btn_upload.setStyleSheet(
            'QPushButton { background-color: #9C27B0; color: white; font-weight: bold; }'
            'QPushButton:disabled { background-color: #cccccc; color: #888888; }')
        self._btn_upload.clicked.connect(self._do_upload)
        hl_btns.addWidget(self._btn_upload)
        hl_btns.addStretch()

        btn_close = QPushButton('Close')
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(self.accept)
        hl_btns.addWidget(btn_close)
        root.addLayout(hl_btns)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _update_quality_label(self, value: int):
        if value >= 90:
            desc = 'Excellent quality, larger size'
        elif value >= 75:
            desc = 'Good quality, smaller size'
        elif value >= 50:
            desc = 'Medium quality, small size'
        else:
            desc = 'Low quality, very small size'
        self._lbl_quality.setText(f'{value}%  ({desc})')

    def _browse_file(self):
        from PyQt5.QtWidgets import QFileDialog
        import os
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select File to Upload', os.path.expanduser('~'),
            'All Files (*)')
        if path:
            self._le_file.setText(path)
            self._file_to_upload = path

    def _status(self, msg: str):
        self._txt_status.append(msg)
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

    def _do_upload(self):
        import os, importlib.util as _ilu
        from PyQt5.QtWidgets import QMessageBox, QProgressDialog
        from PyQt5.QtCore import Qt

        file_path = self._le_file.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, 'No File', 'Please select a file to upload.')
            return

        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 10:
            QMessageBox.warning(
                self, 'File Too Large',
                f'The file ({file_size_mb:.2f} MB) exceeds the 10 MB limit.\n\n'
                'Please compress or resize the file before uploading.')
            return

        # Load IPFSUploader from the asbestos_hsi_manager plugin
        _asbestos_dir = '/Users/luciocolaiacomo/4113Eng-wfs/cop_defence_stac/asbestos_hsi_manager'
        try:
            # Load oidc_auth first (dependency)
            _oidc_spec = _ilu.spec_from_file_location(
                '_oidc_auth_gimi', f'{_asbestos_dir}/oidc_auth.py')
            _oidc_mod = _ilu.module_from_spec(_oidc_spec)
            _oidc_spec.loader.exec_module(_oidc_mod)

            # Load ipfs_uploader
            _up_spec = _ilu.spec_from_file_location(
                '_ipfs_uploader_gimi', f'{_asbestos_dir}/ipfs_uploader.py')
            _up_mod = _ilu.module_from_spec(_up_spec)
            # Inject oidc_auth into the module's namespace so relative import works
            import sys as _sys
            _up_mod.OIDCAuthenticator = _oidc_mod.OIDCAuthenticator
            _up_spec.loader.exec_module(_up_mod)
            IPFSUploader = _up_mod.IPFSUploader
        except Exception as exc:
            QMessageBox.critical(
                self, 'Module Error',
                f'Could not load IPFSUploader:\n{exc}')
            return

        self._txt_status.clear()
        self._le_ipfs_url.clear()
        self._le_cid.clear()
        self._btn_upload.setEnabled(False)

        progress = QProgressDialog('Uploading to IPFS…', 'Cancel', 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        try:
            uploader = IPFSUploader()
            result = uploader.upload(file_path, status_callback=self._status)
            progress.close()

            if not result.get('success'):
                QMessageBox.warning(self, 'Upload Failed', 'IPFS upload failed.')
                return

            ipfs_url = result.get('location', '')
            cid = result.get('cid', result.get('ipfs_hash', ''))
            if not ipfs_url and cid:
                ipfs_url = f'https://ipfs.demo.secd.eu/files/{cid}'
            elif ipfs_url and not ipfs_url.startswith('http'):
                ipfs_url = f'https://ipfs.demo.secd.eu/files/{ipfs_url}'

            self._last_ipfs_url = ipfs_url
            self._last_cid = cid
            self._le_ipfs_url.setText(ipfs_url)
            self._le_cid.setText(cid)
            self._status(f'✓ Upload successful!')
            self._status(f'   IPFS URL: {ipfs_url}')
            self._status(f'   CID: {cid}')
            QMessageBox.information(
                self, 'Upload Successful',
                f'File uploaded to IPFS!\n\n'
                f'URL: {ipfs_url}\n'
                f'CID: {cid}')

        except Exception as exc:
            progress.close()
            self._status(f'✗ Error: {exc}')
            QMessageBox.critical(self, 'Upload Error', str(exc))
        finally:
            self._btn_upload.setEnabled(True)


# =============================================================================
# Blockchain Register dialog  (mirrors "Register on Blockchain" in Asbestos HSI)
# =============================================================================

class _BlockchainRegisterDialog(QDialog):
    """Standalone dialog for registering an asset on the Fabric blockchain.

    Mirrors the 'Register on Blockchain' functionality from the Asbestos HSI
    Manager.  The user provides:
      - Asset ID   (or auto-generates one)
      - IPFS URL   (from a previous upload, or entered manually)
      - SHA-256 / BLAKE3 hash of the asset
      - P12 certificate path + password
      - Gateway URL, channel and chaincode (pre-filled with sensible defaults)
    """

    _DEFAULT_GATEWAY  = 'https://api.demo.secd.eu'
    _DEFAULT_CHANNEL  = 'demo'
    _DEFAULT_CHAINCODE = 'archaeology'
    _ASBESTOS_DIR     = '/Users/luciocolaiacomo/4113Eng-wfs/cop_defence_stac/asbestos_hsi_manager'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Register on Blockchain')
        self.setMinimumWidth(660)
        self.setMinimumHeight(600)
        self._init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout,
            QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog,
        )
        from PyQt5.QtCore import QSettings

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Asset info ──────────────────────────────────────────────────
        grp_asset = QGroupBox('Asset Details')
        gl_asset = QGridLayout(grp_asset)

        gl_asset.addWidget(QLabel('Asset ID:'), 0, 0)
        self._le_asset_id = QLineEdit()
        self._le_asset_id.setPlaceholderText('Unique asset identifier (auto-generated if empty)')
        gl_asset.addWidget(self._le_asset_id, 0, 1)

        gl_asset.addWidget(QLabel('IPFS URL:'), 1, 0)
        self._le_ipfs_url = QLineEdit()
        self._le_ipfs_url.setPlaceholderText('https://ipfs.demo.secd.eu/files/<CID>')
        gl_asset.addWidget(self._le_ipfs_url, 1, 1)

        gl_asset.addWidget(QLabel('File Hash (SHA-256):'), 2, 0)
        self._le_hash = QLineEdit()
        self._le_hash.setPlaceholderText('SHA-256 hex string of the uploaded file')
        gl_asset.addWidget(self._le_hash, 2, 1)

        root.addWidget(grp_asset)

        # ── Certificate ─────────────────────────────────────────────────
        grp_cert = QGroupBox('P12 Certificate Authentication')
        gl_cert = QGridLayout(grp_cert)

        gl_cert.addWidget(QLabel('P12 Certificate:'), 0, 0)
        self._le_p12 = QLineEdit()
        qs = QSettings()
        stored_p12 = qs.value('ipfs_imagery_uploader/p12_path', '')
        if not stored_p12:
            import os
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(plugin_dir, 'Certificati.p12')
            stored_p12 = candidate if os.path.exists(candidate) else ''
        self._le_p12.setText(stored_p12)
        self._le_p12.setPlaceholderText('/path/to/certificate.p12')
        btn_browse_p12 = QPushButton('Browse…')
        btn_browse_p12.setMaximumWidth(90)
        btn_browse_p12.clicked.connect(self._browse_p12)
        hl_p12 = QHBoxLayout()
        hl_p12.addWidget(self._le_p12)
        hl_p12.addWidget(btn_browse_p12)
        gl_cert.addWidget(QLabel('P12 Certificate:'), 0, 0)
        gl_cert.addLayout(hl_p12, 0, 1)

        gl_cert.addWidget(QLabel('P12 Password:'), 1, 0)
        self._le_pwd = QLineEdit()
        self._le_pwd.setEchoMode(QLineEdit.Password)
        self._le_pwd.setPlaceholderText('Passphrase for the P12 certificate')
        self._le_pwd.setText(qs.value('ipfs_imagery_uploader/p12_password', ''))
        gl_cert.addWidget(self._le_pwd, 1, 1)

        root.addWidget(grp_cert)

        # ── Blockchain config ───────────────────────────────────────────
        grp_bc = QGroupBox('Blockchain Configuration')
        gl_bc = QGridLayout(grp_bc)

        gl_bc.addWidget(QLabel('Gateway URL:'), 0, 0)
        self._le_gateway = QLineEdit(self._DEFAULT_GATEWAY)
        gl_bc.addWidget(self._le_gateway, 0, 1)

        gl_bc.addWidget(QLabel('Channel:'), 1, 0)
        self._le_channel = QLineEdit(self._DEFAULT_CHANNEL)
        gl_bc.addWidget(self._le_channel, 1, 1)

        gl_bc.addWidget(QLabel('Chaincode:'), 2, 0)
        self._le_chaincode = QLineEdit(self._DEFAULT_CHAINCODE)
        gl_bc.addWidget(self._le_chaincode, 2, 1)

        root.addWidget(grp_bc)

        # ── Status log ──────────────────────────────────────────────────
        grp_log = QGroupBox('Registration Log')
        vl_log = QVBoxLayout(grp_log)
        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMinimumHeight(140)
        vl_log.addWidget(self._txt_log)
        root.addWidget(grp_log)

        # ── Buttons ─────────────────────────────────────────────────────
        hl_btns = QHBoxLayout()
        self._btn_register = QPushButton('⛓  Register on Blockchain')
        self._btn_register.setMinimumHeight(36)
        self._btn_register.setStyleSheet(
            'QPushButton { background-color: #3F51B5; color: white; font-weight: bold; }'
            'QPushButton:disabled { background-color: #cccccc; color: #888888; }')
        self._btn_register.clicked.connect(self._do_register)
        hl_btns.addWidget(self._btn_register)
        hl_btns.addStretch()
        btn_close = QPushButton('Close')
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(self.accept)
        hl_btns.addWidget(btn_close)
        root.addLayout(hl_btns)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse_p12(self):
        import os
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select P12 Certificate',
            os.path.expanduser('~'),
            'P12 / PFX Certificates (*.p12 *.pfx);;All Files (*)')
        if path:
            self._le_p12.setText(path)

    def _log(self, msg: str):
        self._txt_log.append(msg)
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

    def _do_register(self):
        import os, importlib.util as _ilu, hashlib, uuid
        from datetime import datetime, timezone
        from PyQt5.QtWidgets import QMessageBox, QProgressDialog
        from PyQt5.QtCore import Qt, QSettings

        ipfs_url   = self._le_ipfs_url.text().strip()
        file_hash  = self._le_hash.text().strip()
        asset_id   = self._le_asset_id.text().strip() or str(uuid.uuid4())
        p12_path   = self._le_p12.text().strip()
        p12_pwd    = self._le_pwd.text()
        gateway    = self._le_gateway.text().strip() or self._DEFAULT_GATEWAY
        channel    = self._le_channel.text().strip()  or self._DEFAULT_CHANNEL
        chaincode  = self._le_chaincode.text().strip() or self._DEFAULT_CHAINCODE

        if not ipfs_url:
            QMessageBox.warning(self, 'Missing IPFS URL',
                'Please enter the IPFS URL of the uploaded asset.')
            return
        if not p12_path or not os.path.exists(p12_path):
            QMessageBox.warning(self, 'Certificate Not Found',
                f'P12 certificate not found:\n{p12_path}\n\n'
                'Please select a valid certificate file.')
            return

        # Load BlockchainRegister from asbestos_hsi_manager
        try:
            # cryptography dependency — load oidc_auth too (it's required by ipfs_uploader
            # but blockchain_register only needs cryptography which is installed system-wide)
            _spec = _ilu.spec_from_file_location(
                '_blockchain_register_gimi',
                f'{self._ASBESTOS_DIR}/blockchain_register.py')
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            BlockchainRegister = _mod.BlockchainRegister
        except Exception as exc:
            QMessageBox.critical(self, 'Module Error',
                f'Could not load BlockchainRegister:\n{exc}')
            return

        self._txt_log.clear()
        self._btn_register.setEnabled(False)

        progress = QProgressDialog('Registering on blockchain…', 'Cancel', 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        self._log('=== Blockchain Registration ===')
        self._log(f'Channel:   {channel}')
        self._log(f'Chaincode: {chaincode}')
        self._log(f'Asset ID:  {asset_id}')
        self._log(f'IPFS URL:  {ipfs_url}')
        if file_hash:
            self._log(f'Hash:      {file_hash[:32]}…')

        # Build minimal STAC metadata for the payload
        now = datetime.now(timezone.utc).isoformat()
        stac_meta = {
            'type': 'Feature',
            'id': asset_id,
            'bbox': [0, 0, 0, 0],
            'properties': {
                'datetime': now,
                'start_datetime': now,
                'end_datetime': now,
            },
            'assets': {
                'PRODUCT': {
                    'title': 'GIMI Imagery Asset',
                    'href': ipfs_url,
                    'type': 'application/octet-stream',
                }
            }
        }

        try:
            br = BlockchainRegister(
                gateway_url=gateway,
                p12_path=p12_path,
                p12_password=p12_pwd,
                channel=channel,
                chaincode=chaincode,
            )
            result = br.register_asset(
                asset_id=asset_id,
                metadata=stac_meta,
                sha256_hash=file_hash,
                ipfs_cid=ipfs_url,
                status_callback=self._log,
            )
            progress.close()

            if result.get('registered') or result.get('status') == 'success':
                tx_id    = result.get('transaction_id', result.get('job_id', 'N/A'))
                bc_url   = result.get('blockchain_url', '')
                self._log(f'\n✓ Blockchain registration successful!')
                self._log(f'  Transaction ID: {tx_id}')
                if bc_url:
                    self._log(f'  URL: {bc_url}')
                # Persist P12 path for future use
                qs = QSettings()
                qs.setValue('ipfs_imagery_uploader/p12_path', p12_path)
                if p12_pwd:
                    qs.setValue('ipfs_imagery_uploader/p12_password', p12_pwd)
                qs.sync()
                QMessageBox.information(
                    self, 'Registration Successful',
                    f'Asset registered on blockchain!\n\n'
                    f'Channel:        {channel}\n'
                    f'Chaincode:      {chaincode}\n'
                    f'Transaction ID: {tx_id}\n'
                    f'Asset ID:       {asset_id}\n\n'
                    f'IPFS URL: {ipfs_url}')
            else:
                err = result.get('message', result.get('error', 'Unknown error'))
                self._log(f'\n✗ Registration failed: {err}')
                QMessageBox.warning(self, 'Registration Failed',
                    f'Blockchain registration failed:\n{err}')

        except Exception as exc:
            progress.close()
            self._log(f'\n✗ Error: {exc}')
            QMessageBox.critical(self, 'Registration Error', str(exc))
        finally:
            self._btn_register.setEnabled(True)


# =============================================================================
# Register / Settings tab  (IPFS Authenix OAuth2 + P12 certificate management)
# =============================================================================


class _RegisterSettingsTabMixin:
    """
    Mixin that provides _setup_register_settings_tab() and all its helper
    methods.  Kept as a separate class purely for organisation — it is mixed
    into HEIFTTLImporterDialog at class definition.
    """

    # ------------------------------------------------------------------
    # Tab builder
    # ------------------------------------------------------------------

    def _setup_register_settings_tab(self):
        """Build the Register / Settings tab and append it to tabWidget."""
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QCheckBox, QTextEdit, QScrollArea,
            QSizePolicy,
        )
        from PyQt5.QtCore import Qt, QTimer, QUrl
        from PyQt5.QtGui import QDesktopServices

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

        # ── IPFS Uploader Authentication (OAuth2 / Authenix) ───────────────
        grp_ipfs = QGroupBox('IPFS Uploader Authentication (OAuth2 — Authenix)')
        gl_ipfs = QVBoxLayout(grp_ipfs)

        reg_info = QLabel(
            'New user? Register for an IPFS account to receive your Client ID:'
        )
        reg_info.setWordWrap(True)
        gl_ipfs.addWidget(reg_info)

        reg_row = QHBoxLayout()
        self._reg_btn_open_ipfs = QPushButton(
            'Register  →  https://ipfs.ogc.secd.eu/')
        self._reg_btn_open_ipfs.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl('https://ipfs.ogc.secd.eu/')))
        reg_row.addWidget(self._reg_btn_open_ipfs)
        reg_row.addStretch()
        gl_ipfs.addLayout(reg_row)

        cid_row = QHBoxLayout()
        cid_row.addWidget(QLabel('IPFS Client ID:'))
        self._reg_le_client_id = QLineEdit()
        self._reg_le_client_id.setPlaceholderText(
            'Paste Client ID received after registration …')
        # pre-fill from QSettings
        from qgis.PyQt.QtCore import QSettings as _QS
        _qs = _QS()
        self._reg_le_client_id.setText(_qs.value('ipfs_imagery_uploader/ipfs_client_id', ''))
        cid_row.addWidget(self._reg_le_client_id)
        gl_ipfs.addLayout(cid_row)

        info_lbl = QLabel(
            'Enter your Client ID above, then click Authenticate to start the '
            'OAuth2 device flow (RFC 8628).')
        info_lbl.setStyleSheet('QLabel { color: #666; }')
        info_lbl.setWordWrap(True)
        gl_ipfs.addWidget(info_lbl)

        self._reg_btn_auth = QPushButton('🔐 Authenticate with IPFS Uploader')
        self._reg_btn_auth.setMinimumHeight(36)
        self._reg_btn_auth.clicked.connect(self._reg_start_device_flow)
        gl_ipfs.addWidget(self._reg_btn_auth)

        # Device-flow verification group (hidden until flow starts)
        self._reg_grp_verify = QGroupBox('Device Verification')
        gl_verify = QVBoxLayout(self._reg_grp_verify)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel('Verification URL:'))
        self._reg_le_verify_url = QLineEdit()
        self._reg_le_verify_url.setReadOnly(True)
        self._reg_btn_copy_url = QPushButton('Copy URL')
        self._reg_btn_copy_url.clicked.connect(
            lambda: self._reg_copy_to_clipboard(self._reg_le_verify_url.text(),
                                                'Verification URL copied'))
        self._reg_btn_open_url = QPushButton('Open in Browser')
        self._reg_btn_open_url.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self._reg_le_verify_url.text()))
        )
        url_row.addWidget(self._reg_le_verify_url)
        url_row.addWidget(self._reg_btn_copy_url)
        url_row.addWidget(self._reg_btn_open_url)
        gl_verify.addLayout(url_row)

        code_row = QHBoxLayout()
        code_row.addWidget(QLabel('User Code:'))
        self._reg_le_user_code = QLineEdit()
        self._reg_le_user_code.setReadOnly(True)
        self._reg_le_user_code.setStyleSheet(
            'QLineEdit { font-size: 16px; font-weight: bold; }')
        self._reg_btn_copy_code = QPushButton('Copy Code')
        self._reg_btn_copy_code.clicked.connect(
            lambda: self._reg_copy_to_clipboard(self._reg_le_user_code.text(),
                                                'User code copied'))
        code_row.addWidget(self._reg_le_user_code)
        code_row.addWidget(self._reg_btn_copy_code)
        gl_verify.addLayout(code_row)

        self._reg_lbl_auth_status = QLabel(
            '⏳ Waiting for authorization — complete verification in your browser.')
        self._reg_lbl_auth_status.setStyleSheet('QLabel { color: #0066cc; }')
        self._reg_lbl_auth_status.setWordWrap(True)
        gl_verify.addWidget(self._reg_lbl_auth_status)

        self._reg_grp_verify.setLayout(gl_verify)
        self._reg_grp_verify.setVisible(False)
        gl_ipfs.addWidget(self._reg_grp_verify)

        self._reg_txt_auth_log = QTextEdit()
        self._reg_txt_auth_log.setReadOnly(True)
        self._reg_txt_auth_log.setMaximumHeight(110)
        self._reg_txt_auth_log.setPlaceholderText('Authentication log…')
        gl_ipfs.addWidget(self._reg_txt_auth_log)

        # OAuth2 polling state
        self._reg_oidc = None
        self._reg_device_code = None
        self._reg_polling_timer = None
        self._reg_poll_count = 0
        self._reg_access_token = None

        root.addWidget(grp_ipfs)

        # ── Blockchain Certificate Registration ─────────────────────────────
        grp_bc = QGroupBox('Blockchain Certificate Registration')
        gl_bc = QVBoxLayout(grp_bc)

        bc_info = QLabel(
            'Register for blockchain access and obtain a P12 certificate. '
            'This certificate is required for storing metadata on the blockchain.'
        )
        bc_info.setWordWrap(True)
        bc_info.setStyleSheet('QLabel { color: #666; }')
        gl_bc.addWidget(bc_info)

        self._reg_btn_register_bc = QPushButton(
            '📜 Register for Blockchain Certificate')
        self._reg_btn_register_bc.setMinimumHeight(36)
        self._reg_btn_register_bc.clicked.connect(self._reg_open_bc_registration)
        gl_bc.addWidget(self._reg_btn_register_bc)

        reg_url_row = QHBoxLayout()
        reg_url_row.addWidget(QLabel('Registration URL:'))
        self._reg_le_reg_url = QLineEdit('https://user.ogc.secd.eu/')
        self._reg_le_reg_url.setReadOnly(True)
        self._reg_btn_copy_reg_url = QPushButton('Copy URL')
        self._reg_btn_copy_reg_url.clicked.connect(
            lambda: self._reg_copy_to_clipboard(
                self._reg_le_reg_url.text(), 'Registration URL copied'))
        reg_url_row.addWidget(self._reg_le_reg_url)
        reg_url_row.addWidget(self._reg_btn_copy_reg_url)
        gl_bc.addLayout(reg_url_row)

        # P12 Certificate Management sub-group
        grp_cert = QGroupBox('P12 Certificate Management')
        gl_cert = QVBoxLayout(grp_cert)

        cur_cert_row = QHBoxLayout()
        cur_cert_row.addWidget(QLabel('Current Certificate:'))
        self._reg_le_current_cert = QLineEdit()
        self._reg_le_current_cert.setReadOnly(True)
        self._reg_le_current_cert.setPlaceholderText('No certificate loaded')
        cur_cert_row.addWidget(self._reg_le_current_cert)
        gl_cert.addLayout(cur_cert_row)

        pwd_row = QHBoxLayout()
        pwd_row.addWidget(QLabel('P12 Password:'))
        self._reg_le_p12_pwd = QLineEdit()
        self._reg_le_p12_pwd.setEchoMode(QLineEdit.Password)
        self._reg_le_p12_pwd.setPlaceholderText(
            'Passphrase from your registration email …')
        self._reg_le_p12_pwd.setText(
            _qs.value('ipfs_imagery_uploader/p12_password', ''))
        pwd_row.addWidget(self._reg_le_p12_pwd)
        gl_cert.addLayout(pwd_row)

        cert_btn_row = QHBoxLayout()
        self._reg_btn_upload_cert = QPushButton('📁 Upload P12 Certificate')
        self._reg_btn_upload_cert.setMinimumHeight(32)
        self._reg_btn_upload_cert.clicked.connect(self._reg_upload_p12)
        self._reg_btn_show_cert_loc = QPushButton('📍 Show Certificate Location')
        self._reg_btn_show_cert_loc.setMinimumHeight(32)
        self._reg_btn_show_cert_loc.clicked.connect(self._reg_show_cert_location)
        cert_btn_row.addWidget(self._reg_btn_upload_cert)
        cert_btn_row.addWidget(self._reg_btn_show_cert_loc)
        gl_cert.addLayout(cert_btn_row)

        cert_hint = QLabel(
            'Upload the P12 certificate you received by email after registering '
            'at https://user.ogc.secd.eu/ — it will be stored in your user '
            'profile, not in the plugin source files.'
        )
        cert_hint.setWordWrap(True)
        cert_hint.setStyleSheet('QLabel { color: #666; font-style: italic; }')
        gl_cert.addWidget(cert_hint)

        grp_cert.setLayout(gl_cert)
        gl_bc.addWidget(grp_cert)
        grp_bc.setLayout(gl_bc)
        root.addWidget(grp_bc)

        # ── Fabric Gateway Configuration ─────────────────────────────────
        grp_fabric = QGroupBox('Fabric Gateway Configuration')
        gl_fabric = QVBoxLayout(grp_fabric)

        self._reg_chk_bc_enable = QCheckBox('Enable Blockchain Storage')
        gl_fabric.addWidget(self._reg_chk_bc_enable)

        gw_info = QLabel(
            'Fabric Gateway should be configured to connect to:\n'
            '  • Peer: 49.13.87.234:7051\n'
            '  • Channel: test\n'
            '  • Chaincode: dq4ipt\n'
            '  • Organisation: org1.example.com'
        )
        gw_info.setStyleSheet('QLabel { color: #666; padding: 6px; }')
        gl_fabric.addWidget(gw_info)

        gw_row = QHBoxLayout()
        gw_row.addWidget(QLabel('Gateway URL:'))
        self._reg_le_gateway_url = QLineEdit('http://localhost:3000')
        self._reg_le_gateway_url.setPlaceholderText('http://gateway-host:3000')
        gw_row.addWidget(self._reg_le_gateway_url)
        gl_fabric.addLayout(gw_row)

        self._reg_btn_save = QPushButton('Save Settings')
        self._reg_btn_save.setMinimumHeight(32)
        self._reg_btn_save.clicked.connect(self._reg_save_settings)
        gl_fabric.addWidget(self._reg_btn_save)

        root.addWidget(grp_fabric)
        root.addStretch()

        # Populate current cert status
        self._reg_update_cert_status()

        self.tabWidget.addTab(tab, 'Register / Settings')

    # ------------------------------------------------------------------
    # OAuth2 helpers
    # ------------------------------------------------------------------

    def _reg_start_device_flow(self):
        """Start Authenix OAuth2 Device Flow (RFC 8628)."""
        from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import QTimer

        client_id = self._reg_le_client_id.text().strip()
        if not client_id:
            QMessageBox.warning(
                self, 'Client ID Required',
                'Please enter your IPFS Client ID.\n\n'
                'Register at https://ipfs.ogc.secd.eu/ to receive your Client ID.')
            return

        # Persist client_id
        from qgis.PyQt.QtCore import QSettings as _QS
        _QS().setValue('ipfs_imagery_uploader/ipfs_client_id', client_id)

        self._reg_txt_auth_log.append('Initiating OAuth2 device flow…')

        try:
            import sys, importlib.util as _ilu
            _ipfs_dir = '/Users/luciocolaiacomo/4113Eng-wfs/cop_defence_stac/ipfs_imagery_uploader'
            _spec = _ilu.spec_from_file_location(
                'oidc_auth_ext',
                f'{_ipfs_dir}/oidc_auth.py')
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            OIDCAuthenticator = _mod.OIDCAuthenticator
        except Exception as exc:
            QMessageBox.critical(self, 'OIDC Module Not Found',
                f'Could not load oidc_auth from ipfs_imagery_uploader:\n{exc}')
            return

        self._reg_oidc = OIDCAuthenticator(
            client_id=client_id,
            client_secret=None,
            auth_url='https://www.authenix.eu/oauth/authorize',
            token_url='https://www.authenix.eu/oauth/token',
            device_url='https://www.authenix.eu/oauth/device_authorize',
        )

        try:
            device_resp = self._reg_oidc.start_device_flow()
        except Exception as exc:
            self._reg_txt_auth_log.append(f'❌ Error: {exc}')
            QMessageBox.warning(self, 'Authentication Error',
                f'Failed to start device flow:\n{exc}')
            return

        self._reg_device_code = device_resp.get('device_code', '')
        verify_uri = device_resp.get('verification_uri', '')
        user_code = device_resp.get('user_code', '')
        poll_interval = int(device_resp.get('interval', 5)) * 1000

        self._reg_le_verify_url.setText(verify_uri)
        self._reg_le_user_code.setText(user_code)
        self._reg_grp_verify.setVisible(True)

        self._reg_txt_auth_log.append(f'✓ Device code obtained')
        self._reg_txt_auth_log.append(f'  Verification URL: {verify_uri}')
        self._reg_txt_auth_log.append(f'  User Code: {user_code}')
        self._reg_txt_auth_log.append('Waiting for user authorization…')

        self._reg_btn_auth.setEnabled(False)
        self._reg_lbl_auth_status.setText(
            '⏳ Waiting for authorization — complete verification in your browser.')

        self._reg_poll_count = 0
        self._reg_polling_timer = QTimer(self)
        self._reg_polling_timer.timeout.connect(self._reg_poll_for_token)
        self._reg_polling_timer.start(poll_interval)

    def _reg_poll_for_token(self):
        """Poll Authenix token endpoint for access token."""
        from PyQt5.QtWidgets import QMessageBox
        self._reg_poll_count += 1
        if self._reg_poll_count > 120:
            self._reg_stop_polling()
            self._reg_txt_auth_log.append('❌ Authentication timeout.')
            self._reg_lbl_auth_status.setText('❌ Authentication timeout')
            QMessageBox.warning(self, 'Timeout',
                'Authentication timed out. Please try again.')
            return
        try:
            self._reg_oidc.poll_for_token(self._reg_device_code, interval=5)
            if self._reg_oidc.access_token:
                self._reg_access_token = self._reg_oidc.access_token
                self._reg_stop_polling()
                self._reg_txt_auth_log.append('✓ Authentication successful!')
                self._reg_lbl_auth_status.setText('✓ Authenticated successfully!')
                self._reg_lbl_auth_status.setStyleSheet(
                    'QLabel { color: green; font-weight: bold; }')
                QMessageBox.information(
                    self, 'Authentication Successful',
                    'You are now authenticated with the IPFS uploader!')
        except Exception as exc:
            if 'authorization_pending' not in str(exc).lower():
                self._reg_stop_polling()
                self._reg_txt_auth_log.append(f'❌ Error: {exc}')
                QMessageBox.warning(self, 'Authentication Error', str(exc))

    def _reg_stop_polling(self):
        if self._reg_polling_timer:
            self._reg_polling_timer.stop()
            self._reg_polling_timer = None
        self._reg_btn_auth.setEnabled(True)
        self._reg_grp_verify.setVisible(False)

    def _reg_copy_to_clipboard(self, text: str, msg: str):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self._reg_txt_auth_log.append(f'📋 {msg}')

    # ------------------------------------------------------------------
    # Blockchain / certificate helpers
    # ------------------------------------------------------------------

    def _reg_open_bc_registration(self):
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtWidgets import QMessageBox
        QDesktopServices.openUrl(QUrl('https://user.ogc.secd.eu/'))
        self._reg_txt_auth_log.append('🌐 Opened blockchain registration page.')
        QMessageBox.information(
            self, 'Blockchain Registration',
            'Opening registration page in your browser.\n\n'
            'Steps:\n'
            '1. Complete the registration form\n'
            '2. A P12 certificate will be sent to your email\n'
            '3. Come back here and click “Upload P12 Certificate”\n'
            '4. Enter the passphrase from the email in the P12 Password field')

    def _reg_update_cert_status(self):
        import os
        from datetime import datetime
        from qgis.PyQt.QtCore import QSettings as _QS
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        stored = _QS().value('ipfs_imagery_uploader/p12_path', '')
        candidates = [p for p in [
            stored,
            os.path.join(plugin_dir, 'Certificati.p12'),
        ] if p]
        found = next((p for p in candidates if os.path.exists(p)), None)
        if found:
            sz = os.path.getsize(found) / 1024
            mt = datetime.fromtimestamp(os.path.getmtime(found)).strftime('%Y-%m-%d %H:%M')
            self._reg_le_current_cert.setText(f'{os.path.basename(found)}  ({sz:.1f} KB, {mt})')
            self._reg_le_current_cert.setStyleSheet('QLineEdit { color: green; }')
        else:
            self._reg_le_current_cert.setText('')

    def _reg_upload_p12(self):
        import os, shutil
        from datetime import datetime
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        from qgis.PyQt.QtCore import QSettings as _QS

        src, _ = QFileDialog.getOpenFileName(
            self, 'Select P12 Certificate', os.path.expanduser('~'),
            'P12 Certificates (*.p12 *.pfx);;All Files (*)')
        if not src:
            return
        if not os.path.exists(src) or os.path.getsize(src) == 0:
            QMessageBox.warning(self, 'Invalid File',
                'The selected file is missing or empty.')
            return

        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        dest = os.path.join(plugin_dir, 'Certificati.p12')

        if os.path.exists(dest):
            reply = QMessageBox.question(
                self, 'Certificate Already Exists',
                'A certificate is already installed.\nReplace it with the new one?',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if reply != QMessageBox.Yes:
                return
            try:
                shutil.copy2(dest, dest + '.backup')
            except OSError:
                pass

        try:
            shutil.copy2(src, dest)
            os.chmod(dest, 0o600)
        except Exception as exc:
            QMessageBox.critical(self, 'Upload Error', str(exc))
            return

        _QS().setValue('ipfs_imagery_uploader/p12_path', dest)

        # Persist P12 password if filled in
        pwd = self._reg_le_p12_pwd.text()
        if pwd:
            _QS().setValue('ipfs_imagery_uploader/p12_password', pwd)

        self._reg_update_cert_status()
        sz = os.path.getsize(dest) / 1024
        self._reg_txt_auth_log.append(
            f'✓ Certificate installed: {os.path.basename(dest)}  ({sz:.1f} KB)')
        QMessageBox.information(
            self, 'Certificate Uploaded',
            f'P12 certificate installed successfully.\n'
            f'Location: {dest}\nSize: {sz:.1f} KB\n\n'
            'Restart QGIS for the new certificate to take effect.')

    def _reg_show_cert_location(self):
        import os, subprocess, platform
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        cert = os.path.join(plugin_dir, 'Certificati.p12')
        try:
            if platform.system() == 'Darwin':
                subprocess.run(['open', '-R', cert] if os.path.exists(cert)
                               else ['open', plugin_dir])
            elif platform.system() == 'Linux':
                subprocess.run(['xdg-open', plugin_dir])
            elif platform.system() == 'Windows':
                subprocess.run(['explorer', '/select,', cert]
                               if os.path.exists(cert) else ['explorer', plugin_dir])
        except Exception:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Certificate Location',
                f'Certificate directory:\n{plugin_dir}')

    def _reg_save_settings(self):
        from PyQt5.QtWidgets import QMessageBox
        from qgis.PyQt.QtCore import QSettings as _QS
        qs = _QS()
        cid = self._reg_le_client_id.text().strip()
        if cid:
            qs.setValue('ipfs_imagery_uploader/ipfs_client_id', cid)
        pwd = self._reg_le_p12_pwd.text()
        if pwd:
            qs.setValue('ipfs_imagery_uploader/p12_password', pwd)
        qs.setValue('ipfs_imagery_uploader/gateway_url',
                    self._reg_le_gateway_url.text().strip())
        qs.setValue('ipfs_imagery_uploader/bc_enabled',
                    self._reg_chk_bc_enable.isChecked())
        qs.sync()
        QMessageBox.information(self, 'Saved', 'Settings saved successfully.')


# Inject Register/Settings methods into HEIFTTLImporterDialog
for _mixin_method_name in dir(_RegisterSettingsTabMixin):
    if _mixin_method_name.startswith('_reg_') or _mixin_method_name == '_setup_register_settings_tab':
        setattr(HEIFTTLImporterDialog,
                _mixin_method_name,
                getattr(_RegisterSettingsTabMixin, _mixin_method_name))


class _SARWorker(QObject):
    """Background worker: converts one Sentinel-1 SAFE sub-swath to amplitude
    HEIF + writes STAC Item JSON + TTL/RDF sidecar."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)   # result dict

    def __init__(self, safe_path: str, meta: dict, out_dir: str,
                 liability_fields: dict):
        super().__init__()
        self._safe = safe_path
        self._meta = meta
        self._out_dir = out_dir
        self._liability = liability_fields
        self.cancelled = False

    # ------------------------------------------------------------------
    def run(self):
        import os, json, hashlib, math
        from datetime import timezone

        result = {'success': False, 'error': '', 'files': []}
        os.makedirs(self._out_dir, exist_ok=True)

        subswaths = self._meta.get('subswaths', [])
        total = len(subswaths)
        if total == 0:
            result['error'] = 'No sub-swath TIFF files found in SAFE folder.'
            self.finished.emit(result)
            return

        stac_items = []
        ttl_graphs = []

        for idx, sw in enumerate(subswaths):
            if self.cancelled:
                result['error'] = 'Cancelled by user.'
                self.finished.emit(result)
                return

            pct_start = int(idx / total * 90)
            self.progress.emit(pct_start, f'Processing sub-swath {sw["swath"]} …')

            tiff_path = sw['tiff']
            stem = os.path.splitext(os.path.basename(tiff_path))[0]
            heif_out = os.path.join(self._out_dir, stem + '_amplitude.heif')
            stac_out = os.path.join(self._out_dir, stem + '_stac.json')
            ttl_out  = os.path.join(self._out_dir, stem + '.ttl')

            # ── 1. SAR amplitude conversion → HEIF ────────────────────
            self.progress.emit(pct_start + 2,
                               f'{sw["swath"]}: converting complex→amplitude…')
            heif_ok, heif_err = self._convert_sar_to_heif(tiff_path, heif_out, sw)
            if not heif_ok:
                self.progress.emit(pct_start + 3,
                                   f'  ⚠ HEIF conversion failed: {heif_err}')

            # ── 2. STAC Item ───────────────────────────────────────────
            self.progress.emit(pct_start + 5,
                               f'{sw["swath"]}: building STAC item…')
            stac_item = self._build_stac_item(sw, heif_out if heif_ok else None,
                                              tiff_path, stac_out)
            with open(stac_out, 'w', encoding='utf-8') as fh:
                json.dump(stac_item, fh, indent=2)

            # ── 3. TTL / RDF sidecar ───────────────────────────────────
            self.progress.emit(pct_start + 7,
                               f'{sw["swath"]}: writing TTL/RDF…')
            ttl_content = self._build_ttl(stac_item, sw,
                                          heif_out if heif_ok else None,
                                          tiff_path)
            with open(ttl_out, 'w', encoding='utf-8') as fh:
                fh.write(ttl_content)

            result['files'].append({
                'swath':    sw['swath'],
                'heif':     heif_out if heif_ok else None,
                'stac':     stac_out,
                'ttl':      ttl_out,
                'heif_ok':  heif_ok,
            })
            stac_items.append(stac_item)
            ttl_graphs.append(ttl_content)

        # ── 4. STAC Collection ─────────────────────────────────────────
        self.progress.emit(92, 'Writing STAC Collection…')
        coll_path = os.path.join(self._out_dir, 'collection.json')
        collection = self._build_collection(stac_items)
        with open(coll_path, 'w', encoding='utf-8') as fh:
            json.dump(collection, fh, indent=2)
        result['collection'] = coll_path

        # ── 5. Combined TTL graph ──────────────────────────────────────
        combined_ttl = os.path.join(self._out_dir, 'sentinel1_metadata.ttl')
        with open(combined_ttl, 'w', encoding='utf-8') as fh:
            fh.write(_SAR_TTL_PREFIXES)
            for g in ttl_graphs:
                # strip per-file prefix lines (already written above)
                body = '\n'.join(
                    l for l in g.splitlines()
                    if not l.startswith('@prefix'))
                fh.write(body + '\n')
        result['combined_ttl'] = combined_ttl

        self.progress.emit(100, 'Done.')
        result['success'] = True
        self.finished.emit(result)

    # ------------------------------------------------------------------
    def _convert_sar_to_heif(self, tiff_path: str, heif_out: str,
                              sw: dict) -> tuple:
        """
        Convert Sentinel-1 SLC complex TIFF to 8-bit amplitude HEIF.

        SLC pixels are 16-bit signed I/Q pairs (CInt16).
        Pipeline:
          1. Read a downsampled tile via GDAL ReadRaster (avoid RAM explosion)
          2. Compute amplitude:  A = sqrt(I² + Q²)
          3. Apply log-scale stretch:  dB = 20·log10(A + 1)
          4. Percentile normalise to [0, 255] uint8
          5. Encode as HEIF (via pillow-heif)
        """
        try:
            import numpy as np
            from osgeo import gdal
            gdal.UseExceptions()

            ds = gdal.Open(tiff_path, gdal.GA_ReadOnly)
            if ds is None:
                return False, 'GDAL could not open TIFF'

            full_w = ds.RasterXSize
            full_h = ds.RasterYSize

            # Downsample to max 2048 px on longest side to keep RAM manageable
            scale = min(1.0, 2048 / max(full_w, full_h))
            out_w = max(1, int(full_w * scale))
            out_h = max(1, int(full_h * scale))

            # SLC has 2 bands per sub-swath: band 1 = I (real), band 2 = Q (imag)
            # For Sentinel-1 SAFE TIFFs the single band stores complex CInt16;
            # GDAL exposes it as one band. We read raw bytes and reshape.
            band = ds.GetRasterBand(1)
            # Read as Float32 (GDAL auto-converts CInt16 → Float32 magnitude
            # when using gdal.GDT_Float32 with a complex source type)
            raw = band.ReadRaster(0, 0, full_w, full_h,
                                  out_w, out_h,
                                  buf_type=gdal.GDT_CFloat32)
            if raw is None:
                return False, 'GDAL ReadRaster returned None'

            arr = np.frombuffer(raw, dtype=np.complex64).reshape(out_h, out_w)
            amplitude = np.abs(arr).astype(np.float32)

            # log10 stretch to dB scale
            db = 20.0 * np.log10(amplitude + 1.0)

            # Percentile normalise (2–98%) → [0, 255] uint8
            lo, hi = np.percentile(db, 2), np.percentile(db, 98)
            if hi <= lo:
                hi = lo + 1.0
            db_clip = np.clip(db, lo, hi)
            img8 = ((db_clip - lo) / (hi - lo) * 255).astype(np.uint8)

            ds = None  # close GDAL dataset

            # Save as HEIF via pillow-heif
            try:
                import pillow_heif
                from PIL import Image
                pillow_heif.register_heif_opener()
                pil_img = Image.fromarray(img8, mode='L')
                pil_img.save(heif_out, format='HEIF',
                             quality=85,
                             chroma=444)
            except Exception as he:
                # Fallback: save as PNG if pillow-heif not available
                heif_out_png = heif_out.replace('.heif', '.png')
                from PIL import Image
                Image.fromarray(img8, mode='L').save(heif_out_png)
                # update path in place (caller checks heif_ok, not the path)
                import os
                os.rename(heif_out_png, heif_out.replace('.heif', '.png'))
                return False, f'pillow-heif unavailable ({he}); saved PNG instead'

            return True, ''

        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    def _build_stac_item(self, sw: dict, heif_path, tiff_path: str,
                         stac_out: str) -> dict:
        import os
        from datetime import datetime, timezone

        m = self._meta
        lf = self._liability

        bbox = m.get('bbox', [-180, -90, 180, 90])
        polygon_coords = [
            [bbox[0], bbox[1]], [bbox[2], bbox[1]],
            [bbox[2], bbox[3]], [bbox[0], bbox[3]],
            [bbox[0], bbox[1]],
        ]

        item_id = (f"S1A_{m.get('mode','IW')}_{sw['swath']}_"
                   f"{m.get('polarisation','HH')}_"
                   f"{m.get('start_time','').replace(':','').replace('-','')[:15]}")

        assets = {
            'data': {
                'href': os.path.relpath(tiff_path, os.path.dirname(stac_out)),
                'type': 'image/tiff; application=geotiff',
                'title': f'SLC TIFF – {sw["swath"]}',
                'roles': ['data'],
                'sar:polarizations': [m.get('polarisation', 'HH')],
            }
        }
        if heif_path and os.path.exists(heif_path):
            assets['browse'] = {
                'href': os.path.relpath(heif_path, os.path.dirname(stac_out)),
                'type': 'image/heif',
                'title': 'Amplitude browse (HEIF)',
                'roles': ['overview'],
            }

        props = {
            'datetime':    m.get('start_time'),
            'start_datetime': m.get('start_time'),
            'end_datetime':   m.get('stop_time'),
            'platform':    'sentinel-1a',
            'mission':     'sentinel-1',
            'instruments': ['c-sar'],
            'constellation': 'sentinel-1',
            'gsd':         sw.get('range_pixel_spacing'),
            # ── SAR extension ───────────────────────────────────────
            'sar:instrument_mode':    m.get('mode', 'IW'),
            'sar:frequency_band':     'C',
            'sar:center_frequency':   round(m.get('radar_frequency', 5.405e9) / 1e9, 4),
            'sar:polarizations':      [m.get('polarisation', 'HH')],
            'sar:product_type':       m.get('product_type', 'SLC'),
            'sar:looks_range':        1,
            'sar:looks_azimuth':      1,
            'sar:pixel_spacing_range': sw.get('range_pixel_spacing'),
            'sar:pixel_spacing_azimuth': sw.get('azimuth_pixel_spacing'),
            'sar:observation_direction': 'right',
            # ── SAT / orbit extension ────────────────────────────────
            'sat:orbit_state':         m.get('pass', 'ascending').lower(),
            'sat:absolute_orbit':      m.get('absolute_orbit'),
            'sat:relative_orbit':      m.get('relative_orbit'),
            'sat:anx_datetime':        m.get('ascending_node_time'),
            # ── EO (incidence angle) ─────────────────────────────────
            'view:incidence_angle':    sw.get('incidence_angle_mid'),
            # ── Liability & Claims extension ─────────────────────────
            'liability:responsible_party': lf.get('responsible_party', ''),
            'liability:claim_status':      lf.get('claim_status', 'pending'),
            'liability:claim_type':        lf.get('claim_type', 'satellite_data_provision'),
            'liability:jurisdiction':      lf.get('jurisdiction', ''),
            'liability:incident_datetime': m.get('start_time'),
            'liability:data_quality_index': sw.get('quality_index'),
            'liability:evidence_references': [
                os.path.basename(tiff_path),
            ],
            'liability:notes': (
                f"Sentinel-1A IW SLC – sub-swath {sw['swath']} – "
                f"polarisation {m.get('polarisation','HH')} – "
                f"orbit {m.get('absolute_orbit')} – "
                f"slice {m.get('slice_number')}"
            ),
        }
        # remove None values
        props = {k: v for k, v in props.items() if v is not None}

        stac_item = {
            'type':        'Feature',
            'stac_version': '1.0.0',
            'stac_extensions': [
                'https://stac-extensions.github.io/sar/v1.0.0/schema.json',
                'https://stac-extensions.github.io/sat/v1.0.0/schema.json',
                'https://stac-extensions.github.io/eo/v1.0.0/schema.json',
                'https://stac-extensions.github.io/view/v1.0.0/schema.json',
                'https://luciocola.github.io/stac-extension-liability-claims/v1.6.0/schema.json',
            ],
            'id':       item_id,
            'geometry': {
                'type': 'Polygon',
                'coordinates': [polygon_coords],
            },
            'bbox':       bbox,
            'properties': props,
            'assets':     assets,
            'links':      [],
        }
        return stac_item

    # ------------------------------------------------------------------
    def _build_collection(self, items: list) -> dict:
        from datetime import datetime, timezone
        m = self._meta
        all_bboxes = [it['bbox'] for it in items]
        min_lon = min(b[0] for b in all_bboxes)
        min_lat = min(b[1] for b in all_bboxes)
        max_lon = max(b[2] for b in all_bboxes)
        max_lat = max(b[3] for b in all_bboxes)

        start_times = [it['properties'].get('start_datetime') for it in items
                       if it['properties'].get('start_datetime')]
        end_times   = [it['properties'].get('end_datetime') for it in items
                       if it['properties'].get('end_datetime')]

        return {
            'type':          'Collection',
            'id':            f"S1A_{m.get('mode','IW')}_SLC_{m.get('absolute_orbit','')}",
            'stac_version':  '1.0.0',
            'stac_extensions': [
                'https://stac-extensions.github.io/sar/v1.0.0/schema.json',
                'https://stac-extensions.github.io/sat/v1.0.0/schema.json',
                'https://luciocola.github.io/stac-extension-liability-claims/v1.6.0/schema.json',
            ],
            'title':       f"Sentinel-1A IW SLC – Orbit {m.get('absolute_orbit','')}",
            'description': (
                f"Sentinel-1A IW SLC product acquired "
                f"{m.get('start_time','')[:10]}. "
                f"Polarisation: {m.get('polarisation','HH')}. "
                f"Orbit: {m.get('pass','Ascending')} #{m.get('absolute_orbit','')}."
            ),
            'license':     'proprietary',
            'extent': {
                'spatial':  {'bbox': [[min_lon, min_lat, max_lon, max_lat]]},
                'temporal': {'interval': [[
                    min(start_times) if start_times else None,
                    max(end_times)   if end_times   else None,
                ]]},
            },
            'links': [
                {'rel': 'item', 'href': f'./{it["id"]}_stac.json',
                 'type': 'application/geo+json'}
                for it in items
            ],
        }

    # ------------------------------------------------------------------
    def _build_ttl(self, stac_item: dict, sw: dict,
                   heif_path, tiff_path: str) -> str:
        import os
        from urllib.parse import quote

        m   = self._meta
        lf  = self._liability
        pid = stac_item['id']
        props = stac_item['properties']

        # Safe URI slug
        slug = quote(pid, safe='')
        base_uri = f'https://example.org/sar/{slug}'

        lines = [_SAR_TTL_PREFIXES]
        lines.append(f'# Sentinel-1 SAR metadata – {pid}')
        lines.append('')

        # ── Dataset description ──────────────────────────────────────
        lines.append(f'<{base_uri}>')
        lines.append('    a dcat:Dataset, prov:Entity ;')
        lines.append(f'    dcterms:title "Sentinel-1A {sw["swath"]} SLC – {m.get("polarisation","HH")}" ;')
        lines.append(f'    dcterms:identifier "{pid}" ;')
        lines.append(f'    dcterms:created "{props.get("datetime","")}"^^xsd:dateTime ;')
        lines.append(f'    dcterms:temporal [ a dcterms:PeriodOfTime ;')
        lines.append(f'        time:hasBeginning [ time:inXSDDateTimeStamp "{props.get("start_datetime","")}"^^xsd:dateTimeStamp ] ;')
        lines.append(f'        time:hasEnd      [ time:inXSDDateTimeStamp "{props.get("end_datetime","")}"^^xsd:dateTimeStamp ] ] ;')
        lines.append(f'    dcterms:spatial [ a dcterms:Location ;')
        bbox = stac_item['bbox']
        lines.append(f'        locn:geometry "POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, {bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))"^^geo:wktLiteral ] ;')
        lines.append(f'    dcat:keyword "SAR", "Sentinel-1", "SLC", "IW", "{m.get("polarisation","HH")}", "{sw["swath"]}" ;')
        lines.append(f'    dcat:distribution <{base_uri}/tiff>, <{base_uri}/stac> ;')
        if heif_path and os.path.exists(heif_path):
            lines.append(f'    dcat:distribution <{base_uri}/heif> ;')
        lines.append('    .')
        lines.append('')

        # ── SAR-specific properties ──────────────────────────────────
        lines.append(f'<{base_uri}>')
        lines.append(f'    sar:instrumentMode "{props.get("sar:instrument_mode","IW")}" ;')
        lines.append(f'    sar:frequencyBand  "C" ;')
        lines.append(f'    sar:centerFrequencyGHz {props.get("sar:center_frequency", 5.405)} ;')
        lines.append(f'    sar:polarization   "{m.get("polarisation","HH")}" ;')
        lines.append(f'    sar:productType    "{props.get("sar:product_type","SLC")}" ;')
        lines.append(f'    sar:pixelSpacingRange  {sw.get("range_pixel_spacing", "null")} ;')
        lines.append(f'    sar:pixelSpacingAzimuth {sw.get("azimuth_pixel_spacing", "null")} ;')
        lines.append(f'    sar:absoluteOrbit  {m.get("absolute_orbit", 0)} ;')
        lines.append(f'    sar:orbitDirection "{m.get("pass","Ascending")}" ;')
        if sw.get('incidence_angle_mid') is not None:
            lines.append(f'    sar:incidenceAngleMid {sw["incidence_angle_mid"]:.4f} ;')
        lines.append('    .')
        lines.append('')

        # ── Liability & claims ────────────────────────────────────────
        claim_uri = f'{base_uri}/claim'
        lines.append(f'<{claim_uri}>')
        lines.append('    a liability:Claim ;')
        lines.append(f'    liability:responsibleParty "{lf.get("responsible_party","")}" ;')
        lines.append(f'    liability:claimStatus      "{lf.get("claim_status","pending")}" ;')
        lines.append(f'    liability:claimType        "{lf.get("claim_type","satellite_data_provision")}" ;')
        if lf.get('jurisdiction'):
            lines.append(f'    liability:jurisdiction     "{lf["jurisdiction"]}" ;')
        if lf.get('insurance_provider'):
            lines.append(f'    liability:insuranceProvider "{lf["insurance_provider"]}" ;')
        if lf.get('policy_number'):
            lines.append(f'    liability:policyNumber     "{lf["policy_number"]}" ;')
        lines.append(f'    liability:relatesTo        <{base_uri}> ;')
        lines.append('    .')
        lines.append('')

        # ── Distributions ─────────────────────────────────────────────
        lines.append(f'<{base_uri}/tiff>')
        lines.append('    a dcat:Distribution ;')
        lines.append(f'    dcterms:title "SLC TIFF – {sw["swath"]}" ;')
        lines.append(f'    dcat:mediaType "image/tiff" ;')
        lines.append(f'    dcat:downloadURL <file://{quote(tiff_path, safe="/:")}> ;')
        lines.append('    .')
        lines.append('')
        if heif_path and os.path.exists(heif_path):
            lines.append(f'<{base_uri}/heif>')
            lines.append('    a dcat:Distribution ;')
            lines.append(f'    dcterms:title "Amplitude browse (HEIF)" ;')
            lines.append(f'    dcat:mediaType "image/heif" ;')
            lines.append(f'    dcat:downloadURL <file://{quote(heif_path, safe="/:")}> ;')
            lines.append('    .')
            lines.append('')
        lines.append(f'<{base_uri}/stac>')
        lines.append('    a dcat:Distribution ;')
        lines.append(f'    dcterms:title "STAC Item JSON" ;')
        lines.append(f'    dcat:mediaType "application/geo+json" ;')
        lines.append('    .')
        lines.append('')

        return '\n'.join(lines)


_SAR_TTL_PREFIXES = """\
@prefix rdf:         <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:        <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:         <http://www.w3.org/2001/XMLSchema#> .
@prefix dcterms:     <http://purl.org/dc/terms/> .
@prefix dcat:        <http://www.w3.org/ns/dcat#> .
@prefix prov:        <http://www.w3.org/ns/prov#> .
@prefix time:        <http://www.w3.org/2006/time#> .
@prefix locn:        <http://www.w3.org/ns/locn#> .
@prefix geo:         <http://www.opengis.net/ont/geosparql#> .
@prefix sar:         <https://stac-extensions.github.io/sar/v1.0.0/> .
@prefix liability:   <https://luciocola.github.io/stac-extension-liability-claims/v1.6.0/> .
"""

