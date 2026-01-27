"""
Dialog for HEIF/TTL Importer
"""
import os
from pathlib import Path
from PyQt5 import uic
from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox
from PyQt5.QtCore import QSettings, QTimer

from .ttl_parser import TTLParser

# Load UI file
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'heif_ttl_dialog_base.ui'))


class HEIFTTLImporterDialog(QDialog, FORM_CLASS):
    """Dialog for importing HEIF imagery with TTL metadata"""
    
    def __init__(self, parent=None):
        super(HEIFTTLImporterDialog, self).__init__(parent)
        self.setupUi(self)
        
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
        
        # Add button for displaying HEIF structure if it exists in UI
        if hasattr(self, 'btnShowStructure'):
            self.btnShowStructure.clicked.connect(self.show_heif_structure)
        
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
    
    def check_heif_metadata(self):
        """Check if HEIF file has internal RDF metadata"""
        heif_path = self.txtHEIFPath.text()
        
        if not heif_path or not os.path.exists(heif_path):
            self.has_internal_rdf = False
            return
        
        try:
            from .heif_processor import HEIFProcessor
            
            if self.heif_processor is None:
                self.heif_processor = HEIFProcessor()
            
            # Check for internal RDF
            self.has_internal_rdf = self.heif_processor.has_internal_rdf(heif_path)
            
            # Check if heif-convert is available for unsupported formats
            has_heif_convert = self.heif_processor.check_heif_convert_available()
            
            if self.has_internal_rdf:
                # Extract and preview internal RDF
                rdf_content = self.heif_processor.extract_internal_rdf(heif_path)
                if rdf_content:
                    self.display_internal_rdf_preview(rdf_content)
                    # Show info message
                    if hasattr(self, 'lblTTLStatus'):
                        status_msg = f"✓ Internal {self.heif_processor.internal_rdf_format.upper()} RDF detected - external TTL optional"
                        if has_heif_convert:
                            status_msg += " | heif-convert available for unsupported formats"
                        self.lblTTLStatus.setText(status_msg)
                        self.lblTTLStatus.setStyleSheet("color: green; font-weight: bold;")
            else:
                if hasattr(self, 'lblTTLStatus'):
                    status_msg = "⚠ No internal RDF - external TTL file required"
                    if has_heif_convert:
                        status_msg += " | heif-convert available"
                    self.lblTTLStatus.setText(status_msg)
                    self.lblTTLStatus.setStyleSheet("color: orange; font-weight: bold;")
                    
        except Exception as e:
            print(f"Error checking HEIF metadata: {e}")
            self.has_internal_rdf = False
    
    def show_heif_structure(self):
        """Display the complete HEIF/HEVC file structure"""
        heif_path = self.txtHEIFPath.text()
        
        if not heif_path or not os.path.exists(heif_path):
            QMessageBox.warning(self, "No HEIF File", 
                              "Please select a HEIF image file first.")
            return
        
        try:
            from .heif_processor import HEIFProcessor
            
            if self.heif_processor is None:
                self.heif_processor = HEIFProcessor()
            
            # Get the structure
            structure = self.heif_processor.display_heif_structure(heif_path)
            
            # Display in metadata preview area
            self.txtMetadataPreview.setPlainText(structure)
            
            # Also show in a message box for easier reading
            msg = QMessageBox(self)
            msg.setWindowTitle("HEIF File Structure")
            msg.setText("File structure analysis complete. See details in the metadata preview area.")
            msg.setDetailedText(structure)
            msg.setIcon(QMessageBox.Information)
            msg.exec_()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", 
                               f"Failed to analyze HEIF structure:\n{str(e)}")
            import traceback
            print(traceback.format_exc())
    
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
    
    def browse_heif(self):
        """Browse for HEIF image file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select HEIF Image",
            self.txtHEIFPath.text() or os.path.expanduser("~"),
            "HEIF Images (*.heif *.heic *.HEIF *.HEIC);;All Files (*.*)"
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
        """Browse for TTL metadata file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TTL Metadata File",
            self.txtTTLPath.text() or os.path.expanduser("~"),
            "TTL Files (*.ttl *.TTL);;RDF Files (*.rdf *.RDF);;All Files (*.*)"
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
        """Parse TTL file and display preview using rdflib"""
        ttl_path = self.txtTTLPath.text()
        
        if not ttl_path or not os.path.exists(ttl_path):
            self.txtMetadataPreview.clear()
            self.ttl_parser = None
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
            QMessageBox.warning(self, "Missing Input", "Please select a HEIF image file.")
            return False
        
        if not os.path.exists(self.txtHEIFPath.text()):
            QMessageBox.warning(self, "File Not Found", "HEIF image file does not exist.")
            return False
        
        # TTL is optional if HEIF has internal RDF metadata
        has_ttl = self.txtTTLPath.text() and os.path.exists(self.txtTTLPath.text())
        
        if not has_ttl and not self.has_internal_rdf:
            QMessageBox.warning(
                self, 
                "Missing Metadata", 
                "No RDF metadata found.\n\n"
                "Please provide either:\n"
                "• External TTL file, OR\n"
                "• HEIF file with internal RDF metadata"
            )
            return False
        
        if not self.txtOutputPath.text():
            QMessageBox.warning(self, "Missing Output", "Please select an output directory.")
            return False
        
        if not os.path.exists(self.txtOutputPath.text()):
            # Try to create the directory
            try:
                os.makedirs(self.txtOutputPath.text(), exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Invalid Directory", 
                                  f"Could not create output directory: {str(e)}")
                return False
        
        # If using external TTL, validate it has GCPs
        if has_ttl:
            if self.ttl_parser is None:
                QMessageBox.warning(self, "Invalid Metadata", 
                                  "Could not parse TTL metadata file.")
                return False
            
            if len(self.ttl_parser.correspondences) == 0:
                QMessageBox.warning(self, "No GCPs Found", 
                                  "No ground control points found in TTL file.")
                return False
        else:
            # Using internal RDF - validate it can be parsed
            if not self.heif_processor or not self.heif_processor.internal_rdf:
                QMessageBox.warning(
                    self,
                    "Internal RDF Error",
                    "Could not extract internal RDF metadata from HEIF file."
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
                f'Failed to create package:\n\n{str(e)}'
            )
            
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
