@echo off
REM Windows helper: creates a virtual environment (first run), installs packages, starts the app.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Package installation failed. Check your internet connection and try again.
  pause
  exit /b 1
)
streamlit run app.py
pause
