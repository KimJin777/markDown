"""PDF → 마크다운(pymupdf4llm). 글자·제목·목록·표를 뽑고 그림은 옆 폴더에 꺼낸다. 스캔본(글자가 그림인 PDF)의 글자는 빠진다."""

from __future__ import annotations

import base64
import re
from pathlib import Path


def md_path_for(pdf: Path, taken: set[Path] = frozenset()) -> Path:
    """PDF 옆에 '원래 이름.md'. 이미 있거나(taken 포함) 겹치면 ' (2)'를 붙인다 — 있던 파일은 덮어쓰지 않는다."""
    stem, n = pdf.stem, 2
    path = pdf.with_name(f"{stem}.md")
    while path.exists() or path in taken:
        path, n = pdf.with_name(f"{stem} ({n}).md"), n + 1
    return path


def _safe(name: str) -> str:
    """그림 폴더·파일 이름용(빈칸·특수 문자 → _). 마크다운 링크가 깨지지 않게."""
    return re.sub(r"[^\w.-]+", "_", name).strip("_") or "pdf"


def images_dir_for(md: Path) -> Path:
    """마크다운 옆 그림 폴더: '이름_images'."""
    return md.with_name(f"{_safe(md.stem)}_images")


def convert(pdf: Path, md: Path | None = None) -> str:
    """PDF 한 개를 마크다운 글로 바꾼다(쪽이 많으면 몇 초 걸린다 — 화면이 멈추지 않게 다른 스레드에서 부른다).
    md(쓸 마크다운 파일)를 주면 그림도 그 옆 '이름_images' 폴더에 꺼내고 글에서 상대 경로로 가리킨다
    (뷰어에서 보이고 [그림] 슬라이드로 볼 수 있음). 그림이 없으면 폴더를 남기지 않는다."""
    import pymupdf4llm  # 무거워서 쓸 때만 읽는다

    if md is None:
        text = pymupdf4llm.to_markdown(str(pdf), show_progress=False)
        return text.replace("\r\n", "\n").strip() + "\n"
    # 그림은 글 속 데이터(base64)로 받아 여기서 파일로 쓴다 — pymupdf4llm이 직접 쓰면 경로의 빈칸·한글에서 실패한다
    text = pymupdf4llm.to_markdown(str(pdf), show_progress=False, embed_images=True, image_format="png")
    img_dir = images_dir_for(md)
    stem = _safe(md.stem)
    n = 0

    def save(m: re.Match) -> str:
        nonlocal n
        n += 1
        img_dir.mkdir(exist_ok=True)
        name = f"{stem}-{n:03d}.{m.group(1)}"
        (img_dir / name).write_bytes(base64.b64decode(m.group(2)))
        return f"]({img_dir.name}/{name})"

    text = re.sub(r"\]\(data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)\)", save, text)
    return text.replace("\r\n", "\n").strip() + "\n"
