@echo off
rem mdEditor 실행 파일 만들기 → dist\mdEditor\mdEditor.exe (폴더째 복사해서 쓴다)
cd /d "%~dp0"
uv sync -q
uv run --no-sync pyinstaller --noconfirm --clean --windowed --name mdEditor ^
  --distpath dist --workpath build --specpath build ^
  --copy-metadata markdown-editor ^
  --collect-submodules pygments.lexers --collect-submodules pygments.styles ^
  packaging\launch.py
