"""저장하지 않은 내용 자동 백업 — 프로그램이 갑자기 꺼져도 다음 실행 때 되살린다.

30초마다 저장 안 된 문서를 백업 폴더에 통째로 적어 두고, 정상 종료 때 지운다.
다음 실행 때 백업이 남아 있으면 '제대로 닫히지 않았다'는 뜻이므로 복구할지 묻는다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

INDEX = "index.json"


def backup_dir(base: Path) -> Path:
    return base / "backup"


def write_snapshot(folder: Path, docs: list[tuple[str | None, str, str]]) -> None:
    """docs = [(원본 경로 또는 None, 이름, 본문)]. 지난 백업을 지우고 새로 쓴다."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("bak-*.md"):
        old.unlink(missing_ok=True)
    entries = []
    for i, (path, name, text) in enumerate(docs):
        fn = f"bak-{i:03d}.md"
        (folder / fn).write_text(text, encoding="utf-8")
        entries.append({"file": fn, "path": path, "name": name})
    (folder / INDEX).write_text(
        json.dumps({"savedAt": time.time(), "docs": entries}, ensure_ascii=False), encoding="utf-8"
    )


def read_snapshot(folder: Path) -> list[dict]:
    """[{'path': 원본 경로 또는 None, 'name': 이름, 'text': 본문}] — 백업이 없으면 빈 목록."""
    try:
        data = json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for e in data.get("docs", []):
        try:
            text = (folder / str(e.get("file"))).read_text(encoding="utf-8")
        except OSError:
            continue  # 백업 파일 하나가 깨져도 나머지는 살린다
        out.append({"path": e.get("path"), "name": str(e.get("name", "")), "text": text})
    return out


def clear(folder: Path) -> None:
    """정상 종료·복구 뒤: 백업을 지운다."""
    for f in folder.glob("bak-*.md"):
        f.unlink(missing_ok=True)
    (folder / INDEX).unlink(missing_ok=True)
