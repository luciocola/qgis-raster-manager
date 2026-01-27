# Dialog Progress Bar Fix

## Issue
When clicking OK to start the HEIF import process, the dialog closes immediately instead of staying open to show the progress bar. Users cannot see the import progress and the dialog disappears before completion.

## Root Cause
The dialog's `accept()` method was calling `super().accept()` which closes the dialog immediately after validation. The import process (`process_import()`) then tries to update the progress bar on a closed dialog.

**Original flow:**
1. User clicks OK
2. `accept()` validates inputs
3. `accept()` calls `super().accept()` → **dialog closes**
4. `exec_()` returns to plugin
5. `process_import()` runs but dialog is already closed
6. Progress bar updates fail (dialog not visible)

## Solution
Modified the dialog to stay open during processing and only close when import completes.

### Changes Made

#### 1. Modified Dialog Accept Method ([heif_ttl_dialog.py](heif_ttl_dialog.py#L483-L493))

**Before:**
```python
def accept(self):
    """Override accept to validate and save settings"""
    if self.validate():
        self.save_settings()
        super().accept()  # Closes dialog immediately!
```

**After:**
```python
def accept(self):
    """Override accept to validate without closing dialog"""
    if self.validate():
        self.save_settings()
        # Don't call super().accept() yet - keep dialog open for progress
        # The import process will close it when complete
        self.ready_to_process = True
        
def process_complete(self, success=True):
    """Called when import process is complete to close dialog"""
    self.ready_to_process = False
    if success:
        super().accept()  # Close with accepted status
    # If not success, keep dialog open so user can try again
```

#### 2. Added State Flag ([heif_ttl_dialog.py](heif_ttl_dialog.py#L24))

```python
self.ready_to_process = False  # Flag to indicate user clicked OK
```

#### 3. Updated Plugin Run Method ([heif_ttl_importer.py](heif_ttl_importer.py#L136-L141))

**Before:**
```python
result = self.dialog.exec_()

if result:  # result is False because dialog never accepted
    self.process_import()
```

**After:**
```python
self.dialog.exec_()

# Check if user validated and clicked OK (dialog may still be open)
if self.dialog.ready_to_process:
    self.process_import()
```

#### 4. Disable OK Button During Processing ([heif_ttl_importer.py](heif_ttl_importer.py#L145-L151))

Prevents user from clicking OK multiple times while import is running:

```python
def process_import(self):
    """Process the HEIF/TTL import"""
    # Disable OK button to prevent multiple imports
    if hasattr(self.dialog, 'buttonBox'):
        ok_button = self.dialog.buttonBox.button(self.dialog.buttonBox.Ok)
        if ok_button:
            ok_button.setEnabled(False)
```

#### 5. Close Dialog After Completion ([heif_ttl_importer.py](heif_ttl_importer.py#L299-L309))

```python
finally:
    # Reset progress bar
    self.dialog.progressBar.setValue(0)
    
    # Re-enable OK button
    if hasattr(self.dialog, 'buttonBox'):
        ok_button = self.dialog.buttonBox.button(self.dialog.buttonBox.Ok)
        if ok_button:
            ok_button.setEnabled(True)
    
    # Close dialog after import completes
    self.dialog.process_complete(success)
```

## New Workflow

**Fixed flow:**
1. User clicks OK
2. `accept()` validates inputs and sets `ready_to_process = True`
3. Dialog remains open (no `super().accept()` called)
4. `exec_()` continues running (dialog still visible)
5. Plugin checks `ready_to_process` flag
6. `process_import()` runs with dialog still open
7. Progress bar updates are visible
8. After completion, `process_complete()` closes dialog

## User Experience

### Before Fix
- Click OK → dialog disappears
- No progress feedback
- User doesn't know if import is running
- Import happens in background

### After Fix
- Click OK → dialog stays open
- OK button becomes disabled (visual feedback)
- Progress bar fills from 0% to 100%
- User sees each processing step
- Dialog closes automatically when complete
- On error, dialog stays open for retry

## Testing

**Test successful import:**
1. Open plugin
2. Select HEIF file with internal RDF or external TTL
3. Click OK
4. **Expected:** 
   - Dialog remains open
   - OK button grays out
   - Progress bar advances: 10% → 30% → 90% → 100%
   - Success message appears
   - Dialog closes after clicking OK on success message

**Test failed import:**
1. Open plugin
2. Select invalid HEIF file
3. Click OK
4. **Expected:**
   - Dialog remains open
   - Progress bar starts
   - Error message appears
   - Dialog stays open (can fix inputs and retry)
   - OK button re-enabled

**Test cancellation:**
1. Open plugin
2. Click Cancel button
3. **Expected:**
   - Dialog closes immediately
   - No import process runs

## Technical Details

### Dialog States
- **Initial:** `ready_to_process = False`, OK button enabled
- **After OK click:** `ready_to_process = True`, OK button disabled, dialog open
- **During import:** Progress bar updating, dialog visible
- **After success:** `process_complete(True)` → dialog closes via `super().accept()`
- **After error:** `process_complete(False)` → dialog stays open, OK button re-enabled

### Progress Bar Updates
The progress bar now updates correctly at:
- 10% - After extracting GCPs
- 30% - After determining output path  
- 90% - After HEIF processing complete
- 100% - After adding to map (if enabled)

## Files Modified
1. `heif_ttl_dialog.py` (lines 24, 483-493)
2. `heif_ttl_importer.py` (lines 136-141, 145-151, 299-309)

## Deployment
```bash
cd /Users/luciocolaiacomo/4113Eng-wfs/cop_defence_stac/heif_ttl_importer
./deploy.sh
```

Then **restart QGIS** to reload the plugin.
