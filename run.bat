@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\mdeditor.exe" uv sync
start "" ".venv\Scripts\mdeditor.exe" %*
