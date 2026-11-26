# Build the AI Media Renamer desktop app end-to-end on Windows.
# Steps:
#   1. npm ci + npm run build in frontend/
#   2. pyinstaller build_desktop.spec --noconfirm
#   3. npm ci at repo root
#   4. npm run tauri build
#   5. Assert outputs: nsis *.exe, *.sig, latest.json
#
# Note: building with the local MinGW toolchain prints a harmless GNU ld warning
# (".rsrc merge failure: multiple non-default manifests"). The installer is still
# produced and runs correctly; CI uses MSVC and does not print it.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root
Set-Location $root

Write-Host "=== 1. Frontend build ==="
Push-Location (Join-Path $root "frontend")
npm ci
npm run build
Pop-Location

Write-Host "=== 2. Backend (PyInstaller onedir) ==="
pip install -r requirements.txt pyinstaller
pyinstaller build_desktop.spec --noconfirm
if (-not (Test-Path "dist/AIMediaRenamerBackend/AIMediaRenamerBackend.exe")) {
    throw "Backend exe missing after PyInstaller build"
}

Write-Host "=== 3. Root npm install ==="
npm ci

Write-Host "=== 4. Tauri build ==="
npm run tauri build

Write-Host "=== 5. Assert outputs ==="
$bundle = "src-tauri/target/release/bundle/nsis"
$exe = Get-ChildItem "$bundle/*.exe" -ErrorAction SilentlyContinue
$sig = Get-ChildItem "$bundle/*.sig" -ErrorAction SilentlyContinue
if (-not $exe) { throw "NSIS installer (.exe) not found in $bundle" }
if (-not $sig) { throw "Signature (.sig) not found in $bundle" }
Write-Host "Build complete: $($exe[0].FullName)"
