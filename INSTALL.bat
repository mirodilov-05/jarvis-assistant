@echo off
rem Jarvis: double-click to analyse this laptop and install what is missing.
cd /d "%~dp0"
if not exist "%~dp0install.ps1" (
  echo Extract the whole ZIP to a folder first, for example C:\Jarvis, then run INSTALL.bat there.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
