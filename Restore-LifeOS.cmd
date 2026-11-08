@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.py first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\recovery_ui.py %*
pause
