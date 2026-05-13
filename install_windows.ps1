#Requires -Version 5.1
<#
.SYNOPSIS
    Install GIMI Imagery Workbench QGIS plugin on Windows.

.DESCRIPTION
    Copies plugin files to the QGIS plugins directory and installs
    Python dependencies into QGIS's embedded Python environment.

    Run from the plugin source folder:
        powershell -ExecutionPolicy Bypass -File install_windows.ps1

    Or from a downloaded ZIP — extract first, then run this script
    from inside the extracted folder.

.NOTES
    Tested on QGIS 3.x (OSGeo4W and standalone installer).
    Requires QGIS to be closed before running.
#>

[CmdletBinding(SupportsShouldProcess)]
param (
    [string]$QGISProfile = 'default',
    [string]$QGISPythonExe = '',   # Override path to QGIS embedded python3.exe
    [switch]$SkipDeps              # Skip Python dependency installation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Colour helpers ─────────────────────────────────────────────────────
function Write-Ok   { param([string]$msg) Write-Host "  [ ok ] $msg" -ForegroundColor Green  }
function Write-Info { param([string]$msg) Write-Host "  [info] $msg" -ForegroundColor Cyan   }
function Write-Warn { param([string]$msg) Write-Host "  [warn] $msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$msg) Write-Host "  [FAIL] $msg" -ForegroundColor Red    }

# ── Plugin identity ────────────────────────────────────────────────────
$PluginId      = 'heif_ttl_importer'
$PluginName    = 'GIMI Imagery Workbench'

# Files to copy (relative to this script's directory)
$PluginFiles = @(
    '__init__.py',
    'heif_ttl_importer.py',
    'heif_ttl_dialog.py',
    'heif_ttl_dialog_base.ui',
    'ttl_parser.py',
    'heif_processor.py',
    'iso19115_4_metadata.py',
    'stac_converter.py',
    'osm_fetcher.py',
    'ido_annotator.py',
    'dji_adapter.py',
    'drone_mf_attributes.py',
    'hsi_adapter.py',
    'cs_api_client.py',
    'metadata.txt',
    'README.md',
    'LICENSE',
    'icon.png'
)

# Python packages required at runtime
$PipPackages = @(
    'pillow',
    'pillow-heif',
    'blake3'
)

# ── Resolve source directory ───────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = $PWD.Path }
Write-Host ""
Write-Host "=== $PluginName — Windows Installer ===" -ForegroundColor White
Write-Info "Source : $ScriptDir"

# ── Resolve QGIS plugins directory ────────────────────────────────────
$AppData = [System.Environment]::GetFolderPath('ApplicationData')
$PluginRoot = Join-Path $AppData "QGIS\QGIS3\profiles\$QGISProfile\python\plugins"
$TargetDir  = Join-Path $PluginRoot $PluginId

Write-Info "Target : $TargetDir"

if (-not (Test-Path $PluginRoot)) {
    Write-Warn "QGIS profile folder not found: $PluginRoot"
    Write-Warn "Make sure QGIS has been run at least once before installing plugins."
    $create = Read-Host "Create the directory anyway? [y/N]"
    if ($create -notmatch '^[yY]') { Write-Fail "Aborted."; exit 1 }
    New-Item -ItemType Directory -Path $PluginRoot -Force | Out-Null
}

# ── Clear stale bytecode ───────────────────────────────────────────────
if (Test-Path $TargetDir) {
    Write-Info "Removing stale bytecode from previous install…"
    Get-ChildItem -Path $TargetDir -Filter '*.pyc' -Recurse | Remove-Item -Force
    Get-ChildItem -Path $TargetDir -Filter '__pycache__' -Recurse -Directory | Remove-Item -Recurse -Force
}

# ── Create target directory ────────────────────────────────────────────
New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null

# ── Copy plugin files ──────────────────────────────────────────────────
Write-Host ""
Write-Host "Copying plugin files…" -ForegroundColor White

$Copied = 0; $Skipped = 0
foreach ($f in $PluginFiles) {
    $src = Join-Path $ScriptDir $f
    $dst = Join-Path $TargetDir $f
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dst -Force
        Write-Host "    $f" -ForegroundColor DarkGray
        $Copied++
    } else {
        Write-Warn "$f not found in source — skipped"
        $Skipped++
    }
}

# ── Copy libheif_binding package ───────────────────────────────────────
$BindingSrc = Join-Path $ScriptDir 'libheif_binding'
if (Test-Path $BindingSrc) {
    $BindingDst = Join-Path $TargetDir 'libheif_binding'
    New-Item -ItemType Directory -Path $BindingDst -Force | Out-Null
    Copy-Item -Path (Join-Path $BindingSrc '__init__.py') -Destination $BindingDst -Force
    Write-Host "    libheif_binding/__init__.py" -ForegroundColor DarkGray

    # Copy compiled Windows extension (.pyd) if present
    $pyds = Get-ChildItem -Path $BindingSrc -Filter '*.pyd' -ErrorAction SilentlyContinue
    foreach ($pyd in $pyds) {
        Copy-Item -Path $pyd.FullName -Destination $BindingDst -Force
        Write-Host "    libheif_binding/$($pyd.Name)  [compiled extension]" -ForegroundColor DarkGray
    }

    # Also copy libheif_core.py wrapper if present
    $wrapper = Join-Path $BindingSrc 'libheif_core.py'
    if (Test-Path $wrapper) {
        Copy-Item -Path $wrapper -Destination $BindingDst -Force
    }
}

# ── local_secrets.py ───────────────────────────────────────────────────
$SecretsSrc  = Join-Path $ScriptDir 'local_secrets.example.py'
$SecretsDst  = Join-Path $TargetDir 'local_secrets.py'
if (-not (Test-Path $SecretsDst)) {
    if (Test-Path $SecretsSrc) {
        Copy-Item -Path $SecretsSrc -Destination $SecretsDst -Force
        Write-Host "    local_secrets.py  [seeded from example]" -ForegroundColor DarkGray
        $Copied++
    }
} else {
    Write-Info "local_secrets.py already present — not overwritten"
}

Write-Ok "Copied $Copied file(s)$(if ($Skipped -gt 0) { ", $Skipped skipped" })."

# ── Install Python dependencies ────────────────────────────────────────
if (-not $SkipDeps) {
    Write-Host ""
    Write-Host "Installing Python dependencies…" -ForegroundColor White

    # Locate QGIS embedded Python
    if (-not $QGISPythonExe) {
        # Common OSGeo4W paths
        $Candidates = @(
            'C:\Program Files\QGIS 3.40\apps\Python312\python3.exe',
            'C:\Program Files\QGIS 3.38\apps\Python312\python3.exe',
            'C:\Program Files\QGIS 3.36\apps\Python39\python3.exe',
            'C:\OSGeo4W\apps\Python312\python3.exe',
            'C:\OSGeo4W\apps\Python39\python3.exe'
        )
        foreach ($c in $Candidates) {
            if (Test-Path $c) { $QGISPythonExe = $c; break }
        }
    }

    if ($QGISPythonExe -and (Test-Path $QGISPythonExe)) {
        Write-Info "Using QGIS Python: $QGISPythonExe"
        foreach ($pkg in $PipPackages) {
            Write-Info "pip install $pkg …"
            try {
                & $QGISPythonExe -m pip install $pkg --quiet 2>&1 | ForEach-Object {
                    if ($_ -match 'error|Error') { Write-Warn $_ } else { Write-Host "    $_" -ForegroundColor DarkGray }
                }
                Write-Ok "$pkg installed."
            } catch {
                Write-Warn "Could not install ${pkg}: $_"
                Write-Warn "Install manually inside QGIS Python Console:"
                Write-Warn "  import subprocess, sys; subprocess.run([sys.executable, '-m', 'pip', 'install', '$pkg'])"
            }
        }
    } else {
        Write-Warn "QGIS embedded Python not found. Install dependencies manually."
        Write-Host ""
        Write-Host "  Option 1 — OSGeo4W Shell:" -ForegroundColor Yellow
        Write-Host "    py3_env && python -m pip install pillow pillow-heif blake3"
        Write-Host ""
        Write-Host "  Option 2 — QGIS Python Console (Plugins → Python Console):" -ForegroundColor Yellow
        Write-Host "    import subprocess, sys"
        Write-Host "    subprocess.run([sys.executable, '-m', 'pip', 'install', 'pillow', 'pillow-heif', 'blake3'])"
        Write-Host ""
    }
} else {
    Write-Info "Skipping dependency installation (-SkipDeps)."
    Write-Host ""
    Write-Host "  Install manually in QGIS Python Console:" -ForegroundColor Yellow
    Write-Host "    import subprocess, sys"
    Write-Host "    subprocess.run([sys.executable,'-m','pip','install','pillow','pillow-heif','blake3'])"
}

# ── Summary ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Installation complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Start QGIS"
Write-Host "  2. Plugins → Manage and Install Plugins → Installed"
Write-Host "  3. Find '$PluginName' and enable it"
Write-Host ""
Write-Host "If the plugin does not appear, check:" -ForegroundColor Yellow
Write-Host "  - Plugin directory: $TargetDir"
Write-Host "  - Python dependencies installed in QGIS Python"
Write-Host "  - QGIS message log for errors (View → Panels → Log Messages)"
Write-Host ""
