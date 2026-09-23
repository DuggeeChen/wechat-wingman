@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title WeChat Wingman

rem ---- 1. Locate Python: env override > PATH > py launcher ----
set "PY=%WECHAT_WINGMAN_PYTHON%"
if not defined PY set "PY=%WX_HELPER_PYTHON%"
if not defined PY for %%P in (python.exe) do if not "%%~$PATH:P"=="" set "PY=%%~$PATH:P"
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"

if not defined PY (
  echo.
  echo [X] Python not found.
  echo     Install Python 3.9+ from https://www.python.org/downloads/
  echo     and tick "Add python.exe to PATH" during setup.
  echo     Or set WECHAT_WINGMAN_PYTHON to your python.exe path.
  echo.
  if /i not "%~1"=="/quiet" pause
  exit /b 1
)

rem ---- 2. Check dependencies ----
"%PY%" -c "import PIL, requests, tkinter" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [X] Missing dependency. Run:
  echo     "%PY%" -m pip install -r requirements.txt
  echo.
  if /i not "%~1"=="/quiet" pause
  exit /b 1
)

rem ---- 3. Launch via pythonw (no console window) ----
for %%F in ("%PY%") do set "PYW=%%~dpFpythonw.exe"
if not exist "!PYW!" set "PYW=%PY%"

start "" "!PYW!" "%~dp0wx_helper.py"
exit /b 0
