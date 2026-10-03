@echo off
cd /d "%~dp0"
rem 버전이 바뀌었으면 다시 설치(최신이면 바로 넘어감)
uv sync -q
start "" ".venv\Scripts\mdEditor.exe" %*
