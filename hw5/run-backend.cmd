@echo off
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000
