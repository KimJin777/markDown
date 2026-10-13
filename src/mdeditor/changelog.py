"""변경 이력(CHANGELOG.md)을 프로그램 안에서 보여 주기 위한 읽기·나누기."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HEAD = re.compile(r"^## v(\d+(?:\.\d+)*)\b.*$", re.M)


def changelog_path() -> Path | None:
    """설치본·실행 파일은 패키지 안의 사본, 개발용(소스 그대로 실행)은 저장소 맨 위의 원본."""
    here = Path(__file__).resolve().parent
    candidates = [here / "CHANGELOG.md", here.parents[1] / "CHANGELOG.md"]
    if getattr(sys, "_MEIPASS", None):  # PyInstaller 실행 파일
        candidates.insert(0, Path(sys._MEIPASS) / "mdeditor" / "CHANGELOG.md")
    return next((p for p in candidates if p.is_file()), None)


def read_changelog() -> str:
    p = changelog_path()
    return p.read_text(encoding="utf-8") if p else ""


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def sections(text: str) -> list[tuple[str, str]]:
    """[(버전, '## v… 제목부터 다음 버전 앞까지의 글')] — 파일에 적힌 순서(최신이 위)."""
    heads = list(_HEAD.finditer(text))
    return [(m.group(1), text[m.start() : heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()) for i, m in enumerate(heads)]


def changes_since(text: str, last_seen: str | None, current: str) -> str:
    """지난번에 본 버전(last_seen)보다 새롭고 지금 버전(current) 이하인 부분. 처음이면 지금 버전만."""
    cur = version_key(current)
    low = version_key(last_seen) if last_seen else None
    picked = [
        body for v, body in sections(text) if version_key(v) <= cur and (version_key(v) == cur if low is None else version_key(v) > low)
    ]
    return "\n\n".join(picked)
