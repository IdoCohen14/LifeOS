@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup.py with Python 3.11 or newer first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run.py
pause
