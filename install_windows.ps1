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
    [string]$QGISProfile  = 'default',
    [string]$QGISPythonExe = '',   # Override path to QGIS embedded python3.exe
    [switch]$SkipDeps,             # Skip Python dependency installation
    [switch]$InstallHeifEnc,       # Download & install pre-built heif-enc for TB21 HEIF export
    [string]$HeifEncRelease = ''   # Specific GitHub release tag, e.g. 'libheif-windows-v1.19.7'
                                   # Leave empty to use the latest release automatically
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
$GithubRepo    = 'luciocola/GIMI-imagery-workbench'   # used for heif-enc release download

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

# ── Install pre-built heif-enc (optional) ─────────────────────────────
if ($InstallHeifEnc) {
    Write-Host ""
    Write-Host "=== Installing pre-built heif-enc ===" -ForegroundColor White
    Write-Host "  Source: github.com/$GithubRepo releases" -ForegroundColor Cyan

    $HeifEncDir = Join-Path $env:LOCALAPPDATA 'GIMI_heif_enc'

    try {
        # ── Find the release asset URL ──────────────────────────────────
        $assetUrl = $null

        if ($HeifEncRelease) {
            # Explicit tag requested
            $apiUrl = "https://api.github.com/repos/$GithubRepo/releases/tags/$HeifEncRelease"
        } else {
            # Latest release
            $apiUrl = "https://api.github.com/repos/$GithubRepo/releases/latest"
        }

        Write-Info "Querying GitHub API: $apiUrl"
        $headers = @{ 'User-Agent' = 'GIMI-install_windows.ps1' }
        $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers -ErrorAction Stop

        foreach ($asset in $release.assets) {
            if ($asset.name -like 'heif-enc-windows-x64*.zip') {
                $assetUrl    = $asset.browser_download_url
                $assetName   = $asset.name
                $releaseTag  = $release.tag_name
                break
            }
        }

        if (-not $assetUrl) {
            Write-Warn "No 'heif-enc-windows-x64*.zip' asset found in release '$($release.tag_name)'."
            Write-Warn "Run the 'Build libheif (Windows x64)' GitHub Actions workflow first, then"
            Write-Warn "push a tag matching 'libheif-windows-*' to trigger a release."
            Write-Warn "Re-run this installer with -InstallHeifEnc once the release exists."
        } else {
            Write-Info "Found asset: $assetName  (release $releaseTag)"
            Write-Info "Downloading from: $assetUrl"

            # ── Download ZIP ────────────────────────────────────────────
            $tmpZip = Join-Path $env:TEMP 'heif-enc-windows-x64.zip'
            Invoke-WebRequest -Uri $assetUrl -OutFile $tmpZip -UseBasicParsing -ErrorAction Stop
            $zipSizeMB = [math]::Round((Get-Item $tmpZip).Length / 1MB, 1)
            Write-Ok "Downloaded $zipSizeMB MB → $tmpZip"

            # ── Extract ─────────────────────────────────────────────────
            if (Test-Path $HeifEncDir) {
                Remove-Item -Recurse -Force $HeifEncDir
            }
            New-Item -ItemType Directory -Path $HeifEncDir -Force | Out-Null
            Expand-Archive -Path $tmpZip -DestinationPath $HeifEncDir -Force
            Remove-Item $tmpZip -Force

            $heifExe = Join-Path $HeifEncDir 'heif-enc.exe'
            if (-not (Test-Path $heifExe)) {
                Write-Warn "heif-enc.exe not found after extraction in $HeifEncDir"
                Write-Warn "Contents: $(Get-ChildItem $HeifEncDir | Select-Object -ExpandProperty Name)"
            } else {
                Write-Ok "heif-enc installed to: $heifExe"

                # ── Write path into local_secrets.py ───────────────────
                $secretsFile = Join-Path $TargetDir 'local_secrets.py'
                if (Test-Path $secretsFile) {
                    $content = Get-Content $secretsFile -Raw

                    # Update or append HEIF_ENC_PATH
                    $escaped = $heifExe -replace '\\', '\\\\'
                    if ($content -match 'HEIF_ENC_PATH\s*=') {
                        $content = $content -replace "HEIF_ENC_PATH\s*=.*", "HEIF_ENC_PATH = r'$heifExe'"
                        Write-Info "Updated HEIF_ENC_PATH in local_secrets.py"
                    } else {
                        $content += "`n# Path to heif-enc.exe for TB21 GIMI HEIF export`n"
                        $content += "HEIF_ENC_PATH = r'$heifExe'`n"
                        Write-Info "Added HEIF_ENC_PATH to local_secrets.py"
                    }
                    $content | Out-File -Encoding UTF8 $secretsFile
                    Write-Ok "local_secrets.py updated with HEIF_ENC_PATH"
                } else {
                    Write-Warn "local_secrets.py not found at $secretsFile"
                    Write-Warn "Add manually:  HEIF_ENC_PATH = r'$heifExe'"
                }

                Write-Host ""
                Write-Host "  heif-enc is now available for TB21 GIMI HEIF export." -ForegroundColor Green
                Write-Host "  The GIMI plugin will detect it automatically at startup." -ForegroundColor Green

                # Show BUILD_INFO if present
                $buildInfo = Join-Path $HeifEncDir 'BUILD_INFO.json'
                if (Test-Path $buildInfo) {
                    Write-Host ""
                    Write-Host "  Build info:" -ForegroundColor Cyan
                    Get-Content $buildInfo | Write-Host
                }
            }
        }
    } catch {
        Write-Warn "heif-enc installation failed: $_"
        Write-Host ""
        Write-Host "  Manual alternative:" -ForegroundColor Yellow
        Write-Host "  1. Go to: https://github.com/$GithubRepo/releases"
        Write-Host "  2. Download 'heif-enc-windows-x64.zip' from the latest release"
        Write-Host "  3. Extract to a folder, e.g. C:\tools\heif-enc\"
        Write-Host "  4. Add that folder to your PATH, or set in the QGIS plugin's local_secrets.py:"
        Write-Host "       HEIF_ENC_PATH = r'C:\tools\heif-enc\heif-enc.exe'"
    }
} else {
    Write-Host ""
    Write-Info "Tip: run with -InstallHeifEnc to also download heif-enc.exe for TB21 GIMI export."
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
