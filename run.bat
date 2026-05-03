@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo VoiceDoc AI - Starting...
echo ==========================================
echo.

REM =========================================================
REM Default local paths
REM =========================================================
set "APP_ROOT=%USERPROFILE%\VoiceDoc_env"
set "VENV_PATH=%APP_ROOT%\venv"
set "MODEL_ROOT=%APP_ROOT%\whisper_models"

REM =========================================================
REM Optional custom venv path via venv_path.txt
REM =========================================================
if exist "%~dp0venv_path.txt" (
    set /p _RAW=< "%~dp0venv_path.txt"
    set "_RAW=%_RAW: =%"
    if /i not "%_RAW%"=="DEFAULT" if not "%_RAW%"=="" (
        set "VENV_PATH=%_RAW%"
        echo INFO: Custom venv path loaded from venv_path.txt
    )
)

echo INFO: venv path   = %VENV_PATH%
echo INFO: model path  = %MODEL_ROOT%
echo.

if not exist "%VENV_PATH%\Scripts\activate.bat" (
    echo ERROR: venv not found at:
    echo %VENV_PATH%
    echo.
    echo Please run setup.bat on this computer first.
    pause
    exit /b 1
)

if not exist "%~dp0Home.py" (
    echo ERROR: Home.py not found.
    echo Please check the project folder.
    pause
    exit /b 1
)

if not exist "%APP_ROOT%" mkdir "%APP_ROOT%"
if not exist "%MODEL_ROOT%" mkdir "%MODEL_ROOT%"

REM =========================================================
REM Default model/cache environment variables
REM =========================================================
set "VOICEDOC_MODEL_DIR=%MODEL_ROOT%"
set "WHISPER_MODEL_DIR=%MODEL_ROOT%"
set "HF_HOME=%MODEL_ROOT%"
set "XDG_CACHE_HOME=%MODEL_ROOT%"
set "TRANSFORMERS_CACHE=%MODEL_ROOT%"
set "VOICEDOC_FORCE_CPU=true"

REM =========================================================
REM Load .env if exists (can override defaults)
REM =========================================================
if exist "%~dp0.env" (
    echo INFO: Loading .env ...
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0.env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

REM Ensure model dir still exists after env override
if not exist "%VOICEDOC_MODEL_DIR%" mkdir "%VOICEDOC_MODEL_DIR%" 2>nul

REM =========================================================
REM Activate venv
REM =========================================================
call "%VENV_PATH%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate venv.
    pause
    exit /b 1
)

echo OK: venv activated
echo INFO: Whisper model cache = %VOICEDOC_MODEL_DIR%
echo.

REM =========================================================
REM Launch app
REM =========================================================
cd /d "%~dp0"
echo OK: Launching VoiceDoc AI...
echo Browser : http://localhost:8501
echo Stop    : Ctrl+C in this window
echo ==========================================
echo.

streamlit run Home.py --server.headless false --browser.gatherUsageStats false

echo.
echo Stopped.
pause
endlocal