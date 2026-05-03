@echo off
chcp 65001 >nul
setlocal

echo ==========================================
echo VoiceDoc AI - Setup (First Time Install)
echo ==========================================
echo.

REM =========================================================
REM Local folders under user profile (NOT inside sync folder)
REM =========================================================
set "APP_ROOT=%USERPROFILE%\VoiceDoc_env"
set "VENV_ROOT=%APP_ROOT%"
set "VENV_PATH=%VENV_ROOT%\venv"
set "MODEL_ROOT=%APP_ROOT%\whisper_models"

echo Windows user folder : %USERPROFILE%
echo Local app root      : %APP_ROOT%
echo venv path           : %VENV_PATH%
echo Whisper model path  : %MODEL_ROOT%
echo Code folder         : %~dp0
echo.
echo NOTE:
echo - venv and Whisper models will stay on this PC only
echo - they will NOT be stored inside OneDrive / synced project folder
echo - each computer must run setup.bat once
echo.
pause

REM =========================================================
REM Check Python
REM =========================================================
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Please install Python 3.10 or 3.11 first:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Python detected:
python --version
echo.

REM =========================================================
REM Ensure local folders exist
REM =========================================================
if not exist "%APP_ROOT%" mkdir "%APP_ROOT%"
if not exist "%MODEL_ROOT%" mkdir "%MODEL_ROOT%"

REM =========================================================
REM Step 1 - Create venv
REM =========================================================
if not exist "%VENV_PATH%\Scripts\activate.bat" (
    echo [1/6] Creating virtual environment...
    python -m venv "%VENV_PATH%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo OK: venv created.
) else (
    echo [1/6] venv already exists, skipping.
)
echo.

REM =========================================================
REM Step 2 - Activate venv
REM =========================================================
echo [2/6] Activating virtual environment...
call "%VENV_PATH%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Cannot activate venv.
    pause
    exit /b 1
)
echo OK: venv activated.
echo.

REM =========================================================
REM Step 3 - Upgrade pip
REM =========================================================
echo [3/6] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo WARNING: pip upgrade may not have completed successfully.
)
echo.

REM =========================================================
REM Step 4 - Install requirements
REM =========================================================
echo [4/6] Installing packages from requirements.txt ...
echo First run may take 5-15 minutes.
if not exist "%~dp0requirements.txt" (
    echo ERROR: requirements.txt not found at:
    echo %~dp0requirements.txt
    pause
    exit /b 1
)

pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ERROR: Package installation failed.
    echo Please review the error messages above.
    pause
    exit /b 1
)
echo OK: Packages installed.
echo.

REM =========================================================
REM Step 5 - Verify critical packages
REM =========================================================
echo [5/6] Verifying critical packages...
python -c "import faster_whisper, streamlit, pydub, soundfile, scipy, docx, pypdf; from dotenv import load_dotenv; print('OK: critical packages verified.')"
if errorlevel 1 (
    echo WARNING: Some critical packages may be missing.
    echo Try: pip install -r requirements.txt
)
echo.

REM =========================================================
REM Step 6 - Check FFmpeg
REM =========================================================
echo [6/6] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo WARNING: FFmpeg not found.
    echo Download from: https://ffmpeg.org/download.html
    echo Then add ffmpeg\bin to PATH.
) else (
    echo OK: FFmpeg found.
)
echo.

REM =========================================================
REM Create / update .env
REM =========================================================
if not exist "%~dp0.env" (
    echo INFO: Creating .env template...
    (
        echo DEEPSEEK_API_KEY=sk-put-your-key-here
        echo XAI_API_KEY=
        echo OPENAI_API_KEY=
        echo VOICEDOC_LOW_MEMORY=false
        echo DEFAULT_WHISPER_MODEL=medium
        echo DEFAULT_LANGUAGE=yue
        echo VOICEDOC_MODEL_DIR=%MODEL_ROOT%
        echo WHISPER_MODEL_DIR=%MODEL_ROOT%
        echo HF_HOME=%MODEL_ROOT%
        echo XDG_CACHE_HOME=%MODEL_ROOT%
        echo TRANSFORMERS_CACHE=%MODEL_ROOT%
        echo VOICEDOC_FORCE_CPU=true
    ) > "%~dp0.env"
    echo OK: .env created.
) else (
    echo INFO: .env already exists.
    echo INFO: Existing .env kept unchanged.
    echo.
    echo Please confirm these values exist in .env:
    echo VOICEDOC_MODEL_DIR=%MODEL_ROOT%
    echo WHISPER_MODEL_DIR=%MODEL_ROOT%
    echo HF_HOME=%MODEL_ROOT%
    echo XDG_CACHE_HOME=%MODEL_ROOT%
    echo TRANSFORMERS_CACHE=%MODEL_ROOT%
    echo VOICEDOC_FORCE_CPU=true
)
echo.

REM =========================================================
REM Save default venv marker for run.bat
REM =========================================================
echo DEFAULT>"%~dp0venv_path.txt"
echo OK: venv_path.txt updated.
echo.

echo ==========================================
echo Setup COMPLETE!
echo.
echo venv path          : %VENV_PATH%
echo Whisper model path : %MODEL_ROOT%
echo.
echo Next steps:
echo 1. Open .env and fill in API key if needed
echo 2. Double-click run.bat
echo 3. Open browser at http://localhost:8501
echo.
echo First model download will happen when Whisper runs for the first time.
echo After that, models stay in:
echo %MODEL_ROOT%
echo ==========================================
echo.
pause
endlocal