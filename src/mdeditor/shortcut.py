"""바탕화면 바로가기(.lnk) 만들기 — Windows 기본 기능(WScript.Shell)만 쓴다."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "mdEditor.lnk"

_PS = r"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MD_LNK)
$s.TargetPath = $env:MD_TARGET
$s.WorkingDirectory = $env:MD_WORKDIR
$s.Description = 'mdEditor — 마크다운 편집기'
$s.IconLocation = $env:MD_ICON + ',0'
$s.Save()
"""


def launcher_path() -> Path | None:
    """바로가기가 가리킬 실행 파일. 개발용(.venv 안)이면 None — 개발·시험 중에는 만들지 않는다."""
    if getattr(sys, "frozen", False):  # PyInstaller 실행 파일
        candidates = [Path(sys.executable)]
    else:  # uv tool / pip 설치: 실행 명령(mdEditor.exe)
        candidates = [Path(sys.argv[0]), Path(sys.prefix) / "Scripts" / "mdEditor.exe"]
    for exe in candidates:
        exe = exe.resolve()
        if exe.suffix.lower() == ".exe" and exe.exists() and ".venv" not in exe.parts:
            return exe
    return None


def create(desktop: Path, target: Path, icon: Path | None = None) -> Path:
    """desktop에 바로가기를 만들고 그 경로를 돌려준다(이미 있으면 새로 덮어씀). 실패하면 예외.
    icon이 없으면 실행 파일의 아이콘을 쓴다."""
    lnk = desktop / SHORTCUT_NAME
    env = {
        **os.environ,
        "MD_LNK": str(lnk),
        "MD_TARGET": str(target),
        "MD_ICON": str(icon or target),
        "MD_WORKDIR": str(Path.home()),
    }
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _PS],
        env=env,
        check=True,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=30,
    )
    if not lnk.exists():
        raise OSError(f"바로가기가 만들어지지 않았습니다: {lnk}")
    return lnk
