# Start the complete local dev stack in one command:
#   1. llama-server on 127.0.0.1:8080 (if not already answering)
#   2. FastAPI backend on 127.0.0.1:8000
#   3. Vite dev server on 127.0.0.1:5173 (proxies /api and /health to 8000)
#
# Run with: pwsh scripts/dev-all.ps1
# Press Ctrl+C to stop only the processes this script started.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$dataDir = Join-Path $env:APPDATA "ai-media-renamer"
$env:AMR_DATA_DIR = $dataDir
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$started = @()

function Test-Port([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Start-Component([string]$name, [string]$exe, [string[]]$arguments, [string]$workDir) {
    $out = Join-Path $logDir "$name.out.log"
    $err = Join-Path $logDir "$name.err.log"
    $proc = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $workDir `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    $script:started += $proc.Id
    Write-Host "$name started (pid $($proc.Id)); logs: $out / $err"
    return $proc
}

function Wait-ForPort([int]$port, [string]$name, [int]$seconds = 60) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (Test-Port $port) { Write-Host "$name is ready on $port"; return }
        Start-Sleep -Seconds 1
    }
    throw "$name did not start on port $port within ${seconds}s (see logs/)"
}

try {
    if (-not (Test-Port 8080)) {
        $configPath = Join-Path $dataDir "config.json"
        if (-not (Test-Path $configPath)) { throw "No config at $configPath --- run the setup wizard first." }
        $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
        $gguf = $cfg.model.llamacpp.gguf_path
        if (-not $gguf -or -not (Test-Path $gguf)) { throw "No GGUF configured --- run the setup wizard first." }
        $serverExe = Join-Path $dataDir "bin\llama-server.exe"
        if (-not (Test-Path $serverExe)) { throw "Missing $serverExe --- run the setup wizard first." }
        $llamaArgs = @("--model", $gguf, "--host", "127.0.0.1", "--port", "8080", "-c", "4096")
        $mmproj = $cfg.model.llamacpp.mmproj_path
        if ($mmproj -and (Test-Path $mmproj)) { $llamaArgs += @("--mmproj", $mmproj) }
        Start-Component "llama-server" $serverExe $llamaArgs (Split-Path $serverExe)
        Wait-ForPort 8080 "llama-server" 90
    } else {
        Write-Host "llama-server already listening on 8080; reusing it."
    }

    if (-not (Test-Port 8000)) {
        Start-Component "backend" "python" @(
            "desktop_backend.py", "--host", "127.0.0.1", "--port", "8000",
            "--no-launch", "--no-update-check"
        ) $root
        Wait-ForPort 8000 "backend"
    } else {
        Write-Host "Backend already listening on 8000; reusing it."
    }

    if (-not (Test-Port 5173)) {
        Start-Component "vite" "npm" @("--prefix", "frontend", "run", "dev") $root
        Wait-ForPort 5173 "Vite"
    } else {
        Write-Host "Vite already listening on 5173; reusing it."
    }

    Write-Host "`nDev stack ready: SPA http://127.0.0.1:5173  API http://127.0.0.1:8000  AI http://127.0.0.1:8080/v1"
    Write-Host "Press Ctrl+C to stop the processes started by this script."
    while ($true) { Start-Sleep -Seconds 2 }
}
finally {
    foreach ($id in $started) {
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($p) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped pid $id"
        }
    }
}
