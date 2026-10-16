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


def _is_xfa_fallback(text: str) -> bool:
    """XFA 전자 양식 PDF의 껍데기 글('Please wait...')인지 — 진짜 내용은 양식 데이터(XML)에 있다."""
    return "Please wait" in text[:300] and "Adobe" in text


def _xfa_datasets(pdf: Path) -> str | None:
    """XFA 전자 양식 PDF에서 입력 값이 든 datasets XML을 꺼낸다. 전자 양식이 아니면 None."""
    import pymupdf

    try:
        with pymupdf.open(str(pdf)) as doc:
            kind, val = doc.xref_get_key(doc.pdf_catalog(), "AcroForm")
            if kind != "xref":
                return None
            kind, val = doc.xref_get_key(int(val.split()[0]), "XFA")
            if kind == "array":  # [(preamble)1 0 R (datasets)56 0 R ...] 꼴
                m = re.search(r"\(datasets\)\s*(\d+)\s+0\s+R", val)
                xml = doc.xref_stream(int(m.group(1))).decode("utf-8", errors="replace") if m else ""
            elif kind == "xref":  # 통째로 한 스트림이면 datasets 부분만 오린다
                whole = doc.xref_stream(int(val.split()[0])).decode("utf-8", errors="replace")
                m = re.search(r"<xfa:datasets.*?</xfa:datasets>", whole, re.S)
                xml = m.group(0) if m else ""
            else:
                return None
    except Exception:  # noqa: BLE001 — 양식 구조가 다르면 일반 변환 결과를 그대로 쓴다
        return None
    return xml or None


def xfa_markdown(xml_text: str) -> str:
    """전자 양식 데이터(XML) → 읽기 좋은 마크다운.
    【라벨】은 같은 묶음(부모 요소) 안의 값만 거느리고, 값 없는 항목은 뺀다."""
    from xml.etree import ElementTree

    root = ElementTree.fromstring(xml_text)
    parent = {child: p for p in root.iter() for child in p}
    lines: list[str] = []
    label: str | None = None
    vals: list[str] = []
    scope = None  # 라벨의 부모 — 이 묶음을 벗어난 값은 라벨과 묶지 않는다
    prev_parent = None

    def in_scope(el) -> bool:
        while el is not None:
            if el is scope:
                return True
            el = parent.get(el)
        return False

    def flush() -> None:
        nonlocal label, vals, scope
        if label and vals:
            lines.append(f"**{label}** " + " ".join(vals))
        elif vals:
            lines.append(" ".join(vals))
        label, vals, scope = None, [], None

    for el in root.iter():
        if len(el) or el.text is None:
            continue  # 자식이 있는 칸은 묶음일 뿐
        text = el.text.strip()
        if not text:
            continue
        if el.tag.split("}")[-1] == "DOC_TITLE":
            flush()
            lines.append(f"# {text}")
            continue
        if text.startswith("【"):
            flush()
            label, scope = text, parent.get(el)
            continue
        if (label and not in_scope(el)) or (label is None and vals and parent.get(el) is not prev_parent):
            flush()  # 라벨 묶음을 벗어났거나, 라벨 없는 값이 다른 묶음으로 넘어감 → 줄을 끊는다
        vals.append(text)
        prev_parent = parent.get(el)
    flush()
    note = "> 전자 양식(XFA) PDF여서 입력된 값만 뽑았습니다. 원래 서식 모양은 Acrobat Reader로 보세요.\n"
    return note + "\n" + "\n\n".join(lines) + "\n"


def convert(pdf: Path, md: Path | None = None) -> str:
    """PDF 한 개를 마크다운 글로 바꾼다(쪽이 많으면 몇 초 걸린다 — 화면이 멈추지 않게 다른 스레드에서 부른다).
    md(쓸 마크다운 파일)를 주면 그림도 그 옆 '이름_images' 폴더에 꺼내고 글에서 상대 경로로 가리킨다
    (뷰어에서 보이고 [그림] 슬라이드로 볼 수 있음). 그림이 없으면 폴더를 남기지 않는다."""
    import pymupdf4llm  # 무거워서 쓸 때만 읽는다

    if md is None:
        text = pymupdf4llm.to_markdown(str(pdf), show_progress=False)
        text = text.replace("\r\n", "\n").strip() + "\n"
        if _is_xfa_fallback(text) and (xml := _xfa_datasets(pdf)):
            try:
                return xfa_markdown(xml)
            except Exception:  # noqa: BLE001 — 깨진 XML이면 껍데기 글이라도 돌려준다
                return text
        return text
    # 그림은 글 속 데이터(base64)로 받아 여기서 파일로 쓴다 — pymupdf4llm이 직접 쓰면 경로의 빈칸·한글에서 실패한다
    text = pymupdf4llm.to_markdown(str(pdf), show_progress=False, embed_images=True, image_format="png")
    if _is_xfa_fallback(text) and (xml := _xfa_datasets(pdf)):  # 전자 양식: 입력 값을 뽑는다
        try:
            return xfa_markdown(xml)
        except Exception:  # noqa: BLE001
            pass
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
    text = re.sub(r"<!-- (?:Start|End) of picture text -->\n?", "", text)  # 그림 속 글자 표시 주석은 잡음
    return text.replace("\r\n", "\n").strip() + "\n"
