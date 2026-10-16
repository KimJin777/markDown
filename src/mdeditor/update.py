"""업데이트 확인·자동 업데이트(도움말 → 업데이트 확인).

GitHub 저장소 main의 pyproject.toml 버전과 지금 버전을 비교한다. 새 버전이 있으면
mdEditor를 닫은 뒤 별도 창(명령 창)에서 `uv tool upgrade markdown-editor`를 돌리고 다시 켠다
(켜져 있는 동안에는 파일이 잠겨 업그레이드가 실패하므로).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from mdeditor import changelog

REPO = "KimJin777/markDown"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
GIT_URL = f"git+https://github.com/{REPO}"
PACKAGE = "markdown-editor"


def _get(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "mdEditor", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — 고정된 https 주소
        return r.read().decode("utf-8")


def parse_version(pyproject: str) -> str | None:
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    return m.group(1) if m else None


def is_newer(remote: str, current: str) -> bool:
    return changelog.version_key(remote) > changelog.version_key(current)


def check(current: str, timeout: float = 6) -> tuple[str, str]:
    """(최신 버전, 지금 버전 다음부터 바뀐 내용). 인터넷이 안 되면 OSError."""
    import time

    bust = f"?nocache={int(time.time())}"  # raw 주소는 CDN이 5분쯤 캐시해, 방금 나온 버전을 못 볼 수 있다
    latest = parse_version(_get(f"{RAW}/pyproject.toml{bust}", timeout))
    if not latest:
        raise OSError("저장소에서 버전을 읽지 못했습니다")
    notes = ""
    if is_newer(latest, current):
        try:
            notes = changelog.changes_since(_get(f"{RAW}/CHANGELOG.md{bust}", timeout), current, latest)
        except OSError:
            pass
    return latest, notes


def install_kind() -> str:
    """'uv'(uv tool로 설치 — 자동 업데이트 가능), 'exe'(실행 파일 배포본), 'dev'(개발용 실행)."""
    if getattr(sys, "frozen", False):
        return "exe"
    prefix = Path(sys.prefix)
    if prefix.parent.name.lower() == "tools" and (prefix / "uv-receipt.toml").exists():
        return "uv"
    return "dev"


def find_uv() -> Path | None:
    found = shutil.which("uv")
    if found:
        return Path(found)
    for p in (Path.home() / ".local" / "bin" / "uv.exe", Path.home() / ".cargo" / "bin" / "uv.exe"):
        if p.exists():
            return p
    return None


def updater_script(uv: Path, pid: int, relaunch: Path | None) -> str:
    """mdEditor(pid)가 끝나길 기다렸다가 업그레이드하고 다시 켜는 명령 창 스크립트(.cmd)."""
    again = f'start "" "{relaunch}"\r\n' if relaunch else ""
    return (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "title mdEditor 업데이트\r\n"
        "echo mdEditor가 닫히기를 기다리는 중...\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
        "timeout /t 2 /nobreak >nul\r\n"
        "echo.\r\n"
        "echo 새 버전을 받는 중... (잠시 걸릴 수 있습니다)\r\n"
        f'call "{uv}" tool upgrade {PACKAGE}\r\n'
        "if errorlevel 1 (\r\n"
        "  echo 업그레이드가 안 되어 다시 설치합니다...\r\n"
        f'  call "{uv}" tool install --force {GIT_URL}\r\n'
        ")\r\n"
        "if errorlevel 1 (\r\n"
        "  echo.\r\n"
        "  echo 업데이트하지 못했습니다. 위 메시지를 확인하세요.\r\n"
        "  pause\r\n"
        "  exit /b 1\r\n"
        ")\r\n"
        "echo.\r\n"
        "echo 업데이트를 마쳤습니다. mdEditor를 다시 켭니다.\r\n"
        f"{again}"
        "timeout /t 3 >nul\r\n"
        'del "%~f0"\r\n'
    )


def start_updater(uv: Path, relaunch: Path | None) -> None:
    """업데이트 명령 창을 띄운다(이 프로그램이 끝난 뒤 일을 시작한다)."""
    fd, path = tempfile.mkstemp(prefix="mdEditor-update-", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(updater_script(uv, os.getpid(), relaunch))
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["cmd.exe", "/c", path], creationflags=flags, close_fds=True, cwd=str(Path.home()))
