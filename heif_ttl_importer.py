# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Main plugin class for GIMI Imagery Workbench
"""
import os
from pathlib import Path
from PyQt5.QtCore import QSettings, QTranslator, QCoreApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QMessageBox
from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsMessageLog,
    Qgis
)

from .heif_ttl_dialog import HEIFTTLImporterDialog
from .ttl_parser import TTLParser
from .heif_processor import HEIFProcessor


class HEIFTTLImporter:
    """QGIS Plugin for importing any GDAL-readable raster with optional TTL/RDF georeferencing"""

    def __init__(self, iface):
        """Constructor"""
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        
        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            f'heif_ttl_importer_{locale}.qm'
        )
        
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)
        
        # Plugin variables
        self.actions = []
        self.menu = '&GIMI Imagery Workbench'
        self.toolbar = None
        self.dialog = None
    
    def tr(self, message):
        """Get translation for a string"""
        return QCoreApplication.translate('HEIFTTLImporter', message)
    
    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None
    ):
        """Add a toolbar icon to the toolbar"""
        icon = QIcon(icon_path) if icon_path else QIcon()
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        
        if status_tip is not None:
            action.setStatusTip(status_tip)
        
        if whats_this is not None:
            action.setWhatsThis(whats_this)
        
        if add_to_toolbar:
            if self.toolbar is None:
                self.toolbar = self.iface.addToolBar('GIMI Imagery Workbench')
                self.toolbar.setObjectName('QGISRasterManagerToolbar')
            self.toolbar.addAction(action)
        
        if add_to_menu:
            self.iface.addPluginToRasterMenu(self.menu, action)
        
        self.actions.append(action)
        return action
    
    def initGui(self):
        """Create the menu entries and toolbar icons"""
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        if not os.path.exists(icon_path):
            icon_path = None
        
        self.add_action(
            icon_path,
            text=self.tr('GIMI Imagery Workbench'),
            callback=self.run,
            parent=self.iface.mainWindow(),
            status_tip=self.tr('Import any GDAL-readable raster with optional TTL/RDF georeferencing'),
            whats_this=self.tr('Import raster imagery using Ground Control Points from TTL/RDF metadata and export to any GDAL-writable format')
        )
    
    def unload(self):
        """Remove the plugin menu item and icon"""
        for action in self.actions:
            self.iface.removePluginRasterMenu(self.menu, action)
            if self.toolbar:
                self.toolbar.removeAction(action)
        
        if self.toolbar:
            del self.toolbar
    
    def log_message(self, message: str, level=Qgis.Info):
        """Log a message to QGIS message log"""
        QgsMessageLog.logMessage(message, 'GIMI Imagery Workbench', level)
    
    def run(self):
        """Run the plugin"""
        # Check if HEIF is supported
        processor = HEIFProcessor()
        if not processor.is_heif_supported():
            QMessageBox.critical(
                self.iface.mainWindow(),
                'Missing Dependency',
                'HEIF support is not available.\n\n'
                'Please install pillow-heif:\n'
                'pip install pillow-heif\n\n'
                'Then restart QGIS.'
            )
            return
        
        # Create dialog if not exists
        if self.dialog is None:
            try:
                self.dialog = HEIFTTLImporterDialog(self.iface.mainWindow(), iface=self.iface)
            except (AttributeError, Exception) as _dlg_err:
                # Catch AttributeError: _ARRAY_API not found if a dialog dependency
                # (hsi_adapter, dji_adapter, …) pulls in a C extension compiled for
                # a different NumPy ABI than QGIS's embedded Python.
                import traceback as _tb
                _tb.print_exc()
                QMessageBox.critical(
                    self.iface.mainWindow(), 'GIMI Workbench',
                    f'Could not create the dialog:\n{_dlg_err}\n\n'
                    'See the QGIS Python console for details.'
                )
                return
        
        # Set import callback to trigger processing
        self.dialog.import_callback = self.process_import
        
        # Show dialog (non-blocking, will stay open during import)
        self.dialog.show()
    
    def process_import(self):
        """Process the HEIF/TTL import"""
        success = False
        try:
            # Get parameters from dialog
            heif_path = self.dialog.txtHEIFPath.text()
            ttl_path = self.dialog.txtTTLPath.text()
            output_dir = self.dialog.txtOutputPath.text()
            warp = self.dialog.chkWarp.isChecked()
            add_to_map = self.dialog.chkAddToMap.isChecked()
            generate_rdf = self.dialog.chkGenerateRDF.isChecked()
            export_jp2 = self.dialog.chkExportJP2.isChecked() if hasattr(self.dialog, 'chkExportJP2') else False
            resample = self.dialog.get_resample_method()
            orthorectify = self.dialog.get_orthorectify_enabled()
            transform_order = self.dialog.get_transform_order()
            
            # Determine metadata source (external TTL or internal RDF)
            parser = self.dialog.ttl_parser
            has_internal_rdf = self.dialog.has_internal_rdf
            
            # Get GCPs based on metadata source
            if parser is not None:
                # Using external TTL file
                self.log_message(f"Starting HEIF import with external TTL: {Path(ttl_path).name}")
                gcps = parser.get_all_gcps()
                self.log_message(f"Extracted {len(gcps)} Ground Control Points from external TTL")
            elif has_internal_rdf:
                # Using internal RDF metadata
                self.log_message("Starting HEIF import with internal RDF metadata")
                
                # Parse internal RDF to extract GCPs
                internal_rdf = self.dialog.heif_processor.internal_rdf
                if not internal_rdf:
                    # Try to extract again if not already cached
                    self.log_message("Internal RDF not cached, attempting fresh extraction...")
                    internal_rdf = self.dialog.heif_processor.extract_internal_rdf(heif_path)
                    
                if not internal_rdf:
                    raise Exception("Could not extract internal RDF metadata from HEIF file")
                
                # Debug: Log RDF format and length
                rdf_format = self.dialog.heif_processor.internal_rdf_format or "unknown"
                self.log_message(f"Found internal {rdf_format.upper()} RDF ({len(internal_rdf)} characters)")
                
                # Create temporary TTL parser for internal RDF
                parser = TTLParser()
                parse_success = parser.parse_string(internal_rdf)
                
                if not parse_success:
                    raise Exception("Failed to parse internal RDF metadata")
                
                # Debug: Log parse results
                self.log_message(f"Parser found: {len(parser.image_coords)} image coords, "
                               f"{len(parser.ground_coords)} ground coords, "
                               f"{len(parser.correspondences)} correspondences")
                
                gcps = parser.get_all_gcps()
                self.log_message(f"Extracted {len(gcps)} Ground Control Points from internal RDF")
                
                if len(gcps) == 0:
                    raise Exception("No GCPs found in internal RDF metadata. The metadata may be incomplete.")
            else:
                # No TTL/RDF — check if the raster is already georeferenced or has
                # detectable geo metadata (worldfile, embedded geotransform, GCPs).
                processor = self.dialog.heif_processor if self.dialog.heif_processor else HEIFProcessor()
                probe = getattr(self.dialog, '_last_raster_probe', None) or \
                        processor.probe_raster_format(heif_path)

                if probe.get('is_geo_enabled') or probe.get('available_geo_sources'):
                    # GDAL Translate will bake any worldfile/embedded CRS into the temp TIFF;
                    # extract_georeference_from_tiff() will then synthesise corner GCPs.
                    geo_src_names = [s['source'] for s in probe.get('available_geo_sources', [])]
                    self.log_message(
                        f"No TTL/RDF provided — attempting to derive GCPs from the "
                        f"raster itself. Detected geo sources: "
                        f"{', '.join(geo_src_names) if geo_src_names else 'embedded geotransform'}"
                    )
                    temp_for_geo = processor.copy_raster_to_tiff(heif_path)
                    if temp_for_geo:
                        extracted_gcps, width, height = processor.extract_georeference_from_tiff(temp_for_geo)
                        if len(extracted_gcps) > 0:
                            gcps = extracted_gcps
                            self.log_message(
                                f"✓ Derived {len(gcps)} GCPs from embedded geotransform  "
                                f"({width}×{height} px)"
                            )
                        else:
                            sources_hint = '\n'.join(
                                f'  • {s["description"]}'
                                for s in probe.get('available_geo_sources', [])
                            )
                            raise Exception(
                                "Could not extract georeferencing from the raster.\n\n"
                                + (f"Detected potential sources:\n{sources_hint}\n\n"
                                   "Please provide a TTL sidecar file with GCPs."
                                   if sources_hint else
                                   "No georeferencing sources found. "
                                   "Please provide a TTL sidecar file with GCPs.")
                            )
                    else:
                        raise Exception("Could not open the raster with GDAL to extract geotransform.")
                else:
                    sources_hint = '\n'.join(
                        f'  • {s["description"]}'
                        for s in probe.get('available_geo_sources', [])
                    )
                    raise Exception(
                        "No metadata source available and the raster is not georeferenced.\n\n"
                        + (f"Detected potential sources:\n{sources_hint}\n\n"
                           "Please provide a TTL sidecar file with GCPs."
                           if sources_hint else
                           "Please provide a TTL sidecar file or ensure the raster has "
                           "an embedded geotransform, GCPs, or a world file (.tfw/.j2w).")
                    )
            
            # FALLBACK: If no GCPs found in TTL/RDF, try extracting from converted image
            if len(gcps) == 0:
                self.log_message("No GCPs in metadata, attempting to extract from converted image...")
                processor = self.dialog.heif_processor if self.dialog.heif_processor else HEIFProcessor()

                # Use convert_any_to_tiff so non-HEIF formats are handled via GDAL Translate
                tiff_path = processor.convert_any_to_tiff(heif_path)
                if tiff_path:
                    extracted_gcps, width, height = processor.extract_georeference_from_tiff(tiff_path)
                    if len(extracted_gcps) > 0:
                        gcps = extracted_gcps
                        self.log_message(f"✓ Extracted {len(gcps)} GCPs from image (GMLJP2 or geotransform)")
                        self.log_message(f"  Image dimensions: {width}x{height}")
                    else:
                        raise Exception("No georeferencing found in TTL or embedded in image")
                else:
                    raise Exception("Failed to convert HEIF for georeference extraction")
            
            # Check if sufficient GCPs for transformation order
            if orthorectify:
                min_gcps_required = {1: 3, 2: 6, 3: 10, -1: 3}  # -1 = TPS
                required = min_gcps_required.get(transform_order, 3)
                if len(gcps) < required:
                    raise Exception(f"Insufficient GCPs for transformation order {transform_order}. "
                                  f"Need at least {required}, have {len(gcps)}.")
                
                transform_name = "TPS" if transform_order == -1 else f"{transform_order} order polynomial"
                self.log_message(f"Using {transform_name} transformation for orthorectification")
            
            # Determine output filename
            heif_name = Path(heif_path).stem
            suffix = "_orthorectified" if orthorectify else "_georeferenced"
            
            # Choose file extension based on export format
            if export_jp2:
                output_ext = ".jp2"
                self.log_message("Export format: JPEG2000 (.jp2)")
            else:
                output_ext = ".tif"
                self.log_message("Export format: GeoTIFF (.tif)")
            
            output_filename = f"{heif_name}{suffix}{output_ext}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Update progress
            
            # Process HEIF with TTL - reuse processor from dialog to preserve internal RDF
            processor = self.dialog.heif_processor if self.dialog.heif_processor else HEIFProcessor()
            
            # Log processing mode
            if export_jp2:
                mode_text = "JPEG2000" + (" with orthorectification" if orthorectify else "")
            else:
                mode_text = "GeoTIFF" + (" with orthorectification" if orthorectify else "")
            self.log_message(f"Converting HEIF to {mode_text}...")
            
            # Set export format in processor
            if export_jp2:
                processor.export_format = 'JP2'
            
            success, provenance = processor.process_heif_with_ttl(
                heif_path, 
                gcps, 
                output_path, 
                warp=warp,
                orthorectify=orthorectify,
                transform_order=transform_order,
                resample_method=resample
            )
            
            if not success:
                err_detail = provenance.get('error', 'Check QGIS Python console for details.')
                raise Exception(f"Failed to process HEIF image. {err_detail}") from None
            
            # Log provenance information
            self.log_message(f"Original UUID: {provenance.get('original_uuid')}")
            self.log_message(f"Derived UUID: {provenance.get('derived_uuid')}")
            self.log_message(f"Algorithm UUID: {provenance.get('algorithm_uuid')}")
            self.log_message(f"Provenance saved: {provenance.get('provenance_file', 'N/A')}")
            
            # Generate RDF/TTL provenance if requested
            if generate_rdf:
                self.log_message("Generating RDF/TTL provenance file...")
                ttl_file = output_path.replace(output_ext, '_provenance.ttl')
                rdf_path = processor.generate_rdf_provenance(provenance, ttl_file)
                if rdf_path:
                    self.log_message(f"RDF provenance generated: {rdf_path}")
                else:
                    self.log_message("Warning: RDF provenance generation failed", level=Qgis.Warning)
            
            # Update progress
            
            # Add to map if requested
            if add_to_map:
                self.log_message(f"Adding layer to map: {output_path}")
                layer = QgsRasterLayer(output_path, heif_name)
                
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    self.iface.messageBar().pushMessage(
                        "Success",
                        f"Imported georeferenced imagery: {heif_name}",
                        level=Qgis.Success,
                        duration=5
                    )
                else:
                    raise Exception("Created GeoTIFF is not valid")
            
            # Update progress
            
            # Show success message
            processing_info = "Orthorectified" if orthorectify else ("Warped" if warp else "Georeferenced")
            transform_info = ""
            if orthorectify:
                transform_name = "TPS" if transform_order == -1 else f"{transform_order} order polynomial"
                transform_info = f'\nTransformation: {transform_name}'
            
            QMessageBox.information(
                self.iface.mainWindow(),
                'Import Successful',
                f'Successfully imported HEIF imagery:\n\n'
                f'Input: {Path(heif_path).name}\n'
                f'Output: {output_path}\n'
                f'GCPs: {len(gcps)}\n'
                f'Processing: {processing_info}'
                f'{transform_info}\n'
                f'Resampling: {resample}'
            )
            
            # Cleanup
            processor.cleanup()
            self.log_message("Import completed successfully")
            success = True
            
            # Store export info for package creation
            self.dialog.last_export_path = output_path
            self.dialog.last_provenance = provenance

            # Auto-load provenance into viewer
            provenance_file = provenance.get('provenance_file')
            if provenance_file and os.path.exists(provenance_file):
                try:
                    self.dialog.load_provenance_file(provenance_file)
                    self.log_message(f"Provenance loaded into viewer: {provenance_file}")
                except Exception as pv_err:
                    self.log_message(
                        f"Warning: Could not load provenance into viewer: {pv_err}",
                        level=Qgis.Warning
                    )
            
        except Exception as e:
            error_msg = f"Error importing HEIF/TTL: {str(e)}"
            self.log_message(error_msg, level=Qgis.Critical)
            QMessageBox.critical(
                self.iface.mainWindow(),
                'Import Failed',
                error_msg
            )
        
        finally:
            # Close dialog after import completes
            self.dialog.process_complete(success)
