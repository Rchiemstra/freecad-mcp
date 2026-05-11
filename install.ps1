#Requires -Version 5.1
<#
.SYNOPSIS
    Install the FreeCADMCP addon into a FreeCAD Mod directory.

.DESCRIPTION
    Copies addon/FreeCADMCP/ to the target FreeCAD Mod directory.
    Defaults to the standard FreeCAD 1.x user Mod path but accepts
    an override via -ModDir.

.PARAMETER ModDir
    Full path to the FreeCAD Mod directory.
    Default: %APPDATA%\FreeCAD\v1-2\Mod

.PARAMETER FreeCADVersion
    Convenience alias for the FreeCAD config folder name inside %APPDATA%\FreeCAD\.
    Used only when -ModDir is not specified.
    Default: v1-2

.PARAMETER Force
    Overwrite files without prompting when the addon folder already exists.

.EXAMPLE
    .\install.ps1
    # Installs to %APPDATA%\FreeCAD\v1-2\Mod\FreeCADMCP (default)

.EXAMPLE
    .\install.ps1 -ModDir "C:\MyFreeCAD\Mod"
    # Installs to C:\MyFreeCAD\Mod\FreeCADMCP

.EXAMPLE
    .\install.ps1 -FreeCADVersion "v1-0" -Force
    # Installs to %APPDATA%\FreeCAD\v1-0\Mod\FreeCADMCP, no prompt

.EXAMPLE
    .\install.ps1 -ModDir "C:\Program Files\FreeCAD 1.0\Mod" -Force
#>
[CmdletBinding()]
param(
    [string] $ModDir       = "",
    [string] $FreeCADVersion = "v1-2",
    [switch] $Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$AddonSrc  = Join-Path $ScriptDir "addon\FreeCADMCP"

if (-not (Test-Path $AddonSrc)) {
    Write-Error "Addon source not found: $AddonSrc`nRun this script from the freecad-mcp repository root."
    exit 1
}

if ($ModDir -eq "") {
    $ModDir = Join-Path $env:APPDATA "FreeCAD\$FreeCADVersion\Mod"
}

$AddonDst = Join-Path $ModDir "FreeCADMCP"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "FreeCADMCP Addon Installer" -ForegroundColor Cyan
Write-Host "--------------------------" -ForegroundColor Cyan
Write-Host "  Source  : $AddonSrc"
Write-Host "  Target  : $AddonDst"
Write-Host ""

if (-not (Test-Path $ModDir)) {
    Write-Host "Mod directory does not exist: $ModDir" -ForegroundColor Yellow
    $create = Read-Host "Create it? [Y/n]"
    if ($create -eq "" -or $create -match "^[Yy]") {
        New-Item -ItemType Directory -Path $ModDir -Force | Out-Null
        Write-Host "Created: $ModDir" -ForegroundColor Green
    } else {
        Write-Host "Aborted." -ForegroundColor Red
        exit 1
    }
}

if ((Test-Path $AddonDst) -and -not $Force) {
    Write-Host "Addon already installed at: $AddonDst" -ForegroundColor Yellow
    $overwrite = Read-Host "Update / overwrite? [Y/n]"
    if ($overwrite -ne "" -and $overwrite -notmatch "^[Yy]") {
        Write-Host "Aborted." -ForegroundColor Red
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Copy addon
# ---------------------------------------------------------------------------

Write-Host "Copying addon files..." -ForegroundColor Cyan

Copy-Item -Path $AddonSrc -Destination $ModDir -Recurse -Force

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

$CopiedFiles = Get-ChildItem -Path $AddonDst -Recurse -File
$FileCount   = $CopiedFiles.Count

Write-Host ""
Write-Host "Done. $FileCount file(s) installed to:" -ForegroundColor Green
Write-Host "  $AddonDst" -ForegroundColor Green
Write-Host ""
Write-Host "Restart FreeCAD for the addon to take effect." -ForegroundColor Yellow
Write-Host ""
