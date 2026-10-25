@echo off
chcp 65001 >nul
echo ==========================================
echo VoiceDoc AI - Setup (First Time Install)
echo ==========================================
echo.

set "VENV_ROOT=%USERPROFILE%\VoiceDoc_env"
set "VENV_PATH=%VENV_ROOT%\venv"

echo Windows user folder : %USERPROFILE%
echo venv will be at     : %VENV_PATH%
echo Code folder         : %~dp0
echo.
echo NOTE: venv is local to this PC and will NOT sync to OneDrive.
echo Each computer must run setup.bat once.
echo.
pause

REM -- Check Python --
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
python --version
echo.

REM --------------------------------------------------
REM  Step 1/6 : Create venv
REM --------------------------------------------------
if not exist "%VENV_PATH%\Scripts\activate.bat" (
    echo [1/6] Creating venv at %VENV_PATH% ...
    if not exist "%VENV_ROOT%" mkdir "%VENV_ROOT%"
    python -m venv "%VENV_PATH%"
    if errorlevel 1 (
        echo ERROR: venv creation failed.
        pause
        exit /b 1
    )
    echo OK: venv created.
) else (
    echo [1/6] venv already exists, skipping.
)
echo.

REM --------------------------------------------------
REM  Step 2/6 : Activate venv
REM --------------------------------------------------
call "%VENV_PATH%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Cannot activate venv.
    pause
    exit /b 1
)
echo OK: venv activated.
echo.

REM --------------------------------------------------
REM  Step 3/6 : Upgrade pip
REM --------------------------------------------------
echo [2/6] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo OK: pip upgraded.
echo.

REM --------------------------------------------------
REM  Step 4/6 : Install packages
REM --------------------------------------------------
echo [3/6] Installing packages from requirements.txt ...
echo (First run may take 5-15 minutes)
if not exist "%~dp0requirements.txt" (
    echo ERROR: requirements.txt not found at %~dp0
    pause
    exit /b 1
)
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo ERROR: Package install failed. Check the error above.
    pause
    exit /b 1
)
echo OK: All packages installed.
echo.

REM --------------------------------------------------
REM  Step 5/6 : Verify critical packages
REM --------------------------------------------------
echo [4/6] Verifying critical packages...
python -c "import faster_whisper; import streamlit; import pydub; import soundfile; import scipy; import docx; import pypdf; from dotenv import load_dotenv; print('OK: All critical packages verified.')"
if errorlevel 1 (
    echo WARNING: Some packages may not be installed correctly.
    echo Run: pip install -r requirements.txt
)
echo.

REM --------------------------------------------------
REM  Step 5/6 : Check FFmpeg
REM --------------------------------------------------
echo [5/6] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo WARNING: FFmpeg not found in PATH.
    echo.
    echo HOW TO INSTALL FFMPEG:
    echo   1. Go to https://www.gyan.dev/ffmpeg/builds/
    echo   2. Download ffmpeg-release-essentials.zip
    echo   3. Extract to C:\ffmpeg\
    echo   4. Add C:\ffmpeg\bin to system PATH:
    echo      - Press Win+S, search "Environment Variables"
    echo      - Under System Variables, select Path, click Edit
    echo      - Click New, enter: C:\ffmpeg\bin
    echo      - Click OK to close all windows
    echo   5. Verify: open a new cmd window and run "ffmpeg -version"
    echo.
) else (
    echo OK: FFmpeg found.
)
echo.

REM --------------------------------------------------
REM  Step 6/6 : Create config files
REM --------------------------------------------------
echo [6/6] Creating config files...

REM -- .env --
if not exist "%~dp0.env" (
    echo INFO: Creating .env template...
    echo DEEPSEEK_API_KEY=sk-put-your-key-here>"%~dp0.env"
    echo XAI_API_KEY=>>"%~dp0.env"
    echo OPENAI_API_KEY=>>"%~dp0.env"
    echo VOICEDOC_LOW_MEMORY=false>>"%~dp0.env"
    echo DEFAULT_WHISPER_MODEL=medium>>"%~dp0.env"
    echo DEFAULT_LANGUAGE=yue>>"%~dp0.env"
    echo OK: .env created. Open with Notepad and fill in your API Keys.
) else (
    echo OK: .env already exists.
)
echo.

echo HF_HUB_DISABLE_SYMLINKS_WARNING=1>>"%~dp0.env"
echo PYTHONIOENCODING=utf-8>>"%~dp0.env"

REM -- .streamlit\config.toml --
REM toolbarMode=minimal stops Streamlit from intercepting Ctrl+C
REM and removes the Clear Cache popup when user tries to copy text.
if not exist "%~dp0.streamlit" mkdir "%~dp0.streamlit"
if not exist "%~dp0.streamlit\config.toml" (
    echo INFO: Creating .streamlit\config.toml ...
    echo [global]>"%~dp0.streamlit\config.toml"
    echo toolbarMode = "minimal">>"%~dp0.streamlit\config.toml"
    echo.>>"%~dp0.streamlit\config.toml"
    echo [server]>>"%~dp0.streamlit\config.toml"
    echo headless = true>>"%~dp0.streamlit\config.toml"
    echo port = 8501>>"%~dp0.streamlit\config.toml"
    echo.>>"%~dp0.streamlit\config.toml"
    echo [browser]>>"%~dp0.streamlit\config.toml"
    echo gatherUsageStats = false>>"%~dp0.streamlit\config.toml"
    echo OK: config.toml created.
) else (
    echo OK: .streamlit\config.toml already exists.
)
echo.

REM -- venv marker for run.bat --
echo DEFAULT>"%~dp0venv_path.txt"
echo OK: venv_path.txt updated.
echo.

echo ==========================================
echo Setup COMPLETE!
echo.
echo venv   : %VENV_PATH%
echo config : %~dp0.streamlit\config.toml
echo.
echo Next steps:
echo   1. Open .env with Notepad and fill in API Key(s)
echo   2. Double-click run.bat to start VoiceDoc AI
echo   3. Open browser at http://localhost:8501
echo   4. Check page 5 (System Health Check)
echo.
echo New computer? Just run setup.bat again.
echo ==========================================
echo.
pause