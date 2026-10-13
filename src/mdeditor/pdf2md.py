"""PDF → 마크다운(pymupdf4llm). 글자·제목·목록·표를 뽑는다. 그림과 스캔본(글자가 그림인 PDF)의 글자는 빠진다."""

from __future__ import annotations

from pathlib import Path


def md_path_for(pdf: Path, taken: set[Path] = frozenset()) -> Path:
    """PDF 옆에 '원래 이름.md'. 이미 있거나(taken 포함) 겹치면 ' (2)'를 붙인다 — 있던 파일은 덮어쓰지 않는다."""
    stem, n = pdf.stem, 2
    path = pdf.with_name(f"{stem}.md")
    while path.exists() or path in taken:
        path, n = pdf.with_name(f"{stem} ({n}).md"), n + 1
    return path


def convert(pdf: Path) -> str:
    """PDF 한 개를 마크다운 글로 바꾼다(쪽이 많으면 몇 초 걸린다 — 화면이 멈추지 않게 다른 스레드에서 부른다)."""
    import pymupdf4llm  # 무거워서 쓸 때만 읽는다

    text = pymupdf4llm.to_markdown(str(pdf), show_progress=False)
    return text.replace("\r\n", "\n").strip() + "\n"
