# Build the AI Media Renamer desktop app end-to-end on Windows.
# Steps:
#   1. npm ci + npm run build in frontend/
#   2. pyinstaller build_desktop.spec --noconfirm
#   3. npm ci at repo root
#   4. npm run tauri build
#   5. Assert outputs: nsis *.exe and *.sig
#
# This is the ONLY supported desktop build command. Running `npm run tauri build`
# on its own can package a stale bundled backend. Use `npm run build:desktop`.
#
# Note: building with the local MinGW toolchain prints a harmless GNU ld warning
# (".rsrc merge failure: multiple non-default manifests"). The installer is still
# produced and runs correctly; CI uses MSVC and does not print it.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root
Set-Location $root

# Native commands do not honour $ErrorActionPreference on Windows PowerShell.
# Add the Cargo bin folder and check every exit code explicitly.
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
function Invoke-BuildStep([string]$name, [scriptblock]$command) {
    & $command
    if ($LASTEXITCODE -ne 0) { throw "$name failed with exit code $LASTEXITCODE" }
}

Write-Host "=== 1. Frontend build ==="
Push-Location (Join-Path $root "frontend")
Invoke-BuildStep "frontend install" { npm ci }
Invoke-BuildStep "frontend build" { npm run build }
Pop-Location

Write-Host "=== 2. Backend (PyInstaller onedir) ==="
# Remove the previous bundle first. PyInstaller copies frontend/dist into it,
# so keeping an old folder would silently package a stale UI.
if (Test-Path "dist/AIMediaRenamerBackend") {
    Remove-Item "dist/AIMediaRenamerBackend" -Recurse -Force
}
Invoke-BuildStep "python dependencies" { pip install -r requirements.txt pyinstaller }
Invoke-BuildStep "backend bundle" { pyinstaller build_desktop.spec --noconfirm }
if (-not (Test-Path "dist/AIMediaRenamerBackend/AIMediaRenamerBackend.exe")) {
    throw "Backend exe missing after PyInstaller build"
}

Write-Host "=== 3. Root npm install ==="
Invoke-BuildStep "root npm install" { npm ci }

Write-Host "=== 4. Tauri build ==="
Invoke-BuildStep "Tauri build" { npm run tauri build }

Write-Host "=== 5. Assert outputs ==="
$version = (Get-Content VERSION -Raw).Trim()
$bundle = "src-tauri/target/release/bundle/nsis"
$exe = Get-ChildItem "$bundle/*$version*.exe" -ErrorAction SilentlyContinue
$sig = Get-ChildItem "$bundle/*$version*.sig" -ErrorAction SilentlyContinue
if (-not $exe) { throw "NSIS installer for v$version not found in $bundle" }
if (-not $sig) { throw "Signature for v$version not found in $bundle" }
if ($exe.Count -ne $sig.Count) { throw "Installer/signature count mismatch in $bundle" }
Write-Host "Build complete: $($exe[0].FullName)"
