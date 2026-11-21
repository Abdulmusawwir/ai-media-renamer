# Run `cargo test` on the MinGW (windows-gnu) toolchain.
#
# The GNU test harness needs two environment tweaks that the MSVC CI toolchain
# does not:
#   1. WebView2Loader.dll on PATH (from the webview2-com-sys build output).
#   2. A Microsoft.Windows.Common-Controls v6 manifest object passed via
#      RUSTFLAGS, because the GNU linker keeps MinGW's default manifest for
#      test harnesses and the app imports TaskDialogIndirect/SetWindowSubclass
#      from comctl32 v6.
#
# Usage:  pwsh scripts/cargo-test-gnu.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$srcTauri = Join-Path $root "src-tauri"
$mingw = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin"
$wv = Get-ChildItem (Join-Path $srcTauri "target\debug\build") -Recurse -Filter "WebView2Loader.dll" |
    Where-Object { $_.FullName -match '\\x64\\' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $wv) { throw "WebView2Loader.dll not found; run `cargo build` first" }
$manifestObj = Join-Path $env:TEMP "amr-manifest.o"
if (-not (Test-Path $manifestObj)) {
    $manifestDir = Join-Path $env:TEMP "amr-manifest"
    New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
    @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>
    </dependentAssembly>
  </dependency>
</assembly>
'@ | Set-Content -Path (Join-Path $manifestDir "app.manifest") -Encoding UTF8
'1 24 "app.manifest"' | Set-Content -Path (Join-Path $manifestDir "app.rc")
& (Join-Path $mingw "windres.exe") -i (Join-Path $manifestDir "app.rc") -o $manifestObj
if ($LASTEXITCODE -ne 0) { throw "windres failed" }
}
$env:PATH = "$env:USERPROFILE\.cargo\bin;$mingw;$($wv.DirectoryName);$env:PATH"
$env:RUSTFLAGS = "-C link-arg=$manifestObj"
Set-Location $srcTauri
cargo test
