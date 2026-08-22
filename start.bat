@echo off
REM ===========================================================================
REM AI Media Renamer v2 - quick launcher for Windows
REM Starts the FastAPI backend (which serves the built React frontend) and opens
REM the app in your default browser at http://localhost:8000
REM ===========================================================================

setlocal

REM --- Locate or bootstrap Python via winget ---------------------------------
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python not found. Installing via winget...
    where winget >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo winget is not available. Please install Python 3.10+ manually from https://python.org
        pause
        exit /b 1
    )
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    REM Refresh PATH for this session
    set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"
)

REM --- Install / refresh the package (editable) ------------------------------
echo Installing AI Media Renamer (editable)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e .

REM --- Launch the server -----------------------------------------------------
echo Starting server on http://localhost:8000 ...
start "" python -m uvicorn server.main:app --host 127.0.0.1 --port 8000

REM Give the server a moment to boot, then open the browser
timeout /t 3 >nul
start "" http://localhost:8000

echo Done. Press any key to exit this window (the server keeps running in the background).
pause
endlocal
