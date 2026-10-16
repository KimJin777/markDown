"""HWP·HWPX → 마크다운. 글·표는 syhwp로 뽑고, 그림은 파일 안(BinData)에서 직접 꺼낸다.

HWP(5.x)는 OLE 복합 파일이라 olefile로, HWPX는 ZIP이라 zipfile로 그림을 꺼낸다.
글 속 [그림] 자리에 꺼낸 그림을 문서에 넣은 순서대로 끼운다(순서가 어긋나면 남은 그림은 맨 뒤에 모음).
"""

from __future__ import annotations

import re
import zipfile
import zlib
from pathlib import Path

from mdeditor.pdf2md import images_dir_for

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}  # 브라우저가 보여 주는 그림만(wmf·emf는 못 보여 줘 뺌)
_PLACEHOLDER = re.compile(r"!?\[그림[^\]]*\]")  # syhwp가 그림 자리에 남기는 표시


def _bin_no(name: str) -> tuple:
    """BIN0001.jpg → 1, BIN000A.jpg → 10 — 번호는 16진수. 문서에 넣은 순서로 늘어놓기 위한 열쇠."""
    m = re.match(r"BIN([0-9A-Fa-f]+)", name, re.I)
    return (int(m.group(1), 16) if m else 0, name)


def _hwp_images(path: Path) -> list[tuple[str, bytes]]:
    """HWP 5.x(OLE)의 BinData 그림 [(이름, 바이트)]."""
    import olefile

    out = []
    with olefile.OleFileIO(str(path)) as ole:
        entries = [e for e in ole.listdir() if e[0] == "BinData" and Path(e[-1]).suffix.lower() in IMAGE_EXTS]
        for entry in sorted(entries, key=lambda e: _bin_no(e[-1])):
            data = ole.openstream(entry).read()
            try:
                data = zlib.decompress(data, -15)  # 본문 압축 문서(대부분)는 그림도 압축돼 있다
            except zlib.error:
                pass  # 압축하지 않은 문서는 그대로
            out.append((entry[-1], data))
    return out


def _hwpx_images(path: Path) -> list[tuple[str, bytes]]:
    """HWPX(ZIP)의 BinData 그림 [(이름, 바이트)]."""
    out = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.startswith("BinData/") and Path(n).suffix.lower() in IMAGE_EXTS]
        for n in sorted(names, key=lambda n: _bin_no(Path(n).name)):
            out.append((Path(n).name, z.read(n)))
    return out


def images_of(path: Path) -> list[tuple[str, bytes]]:
    return _hwpx_images(path) if path.suffix.lower() == ".hwpx" else _hwp_images(path)


def merge_images(text: str, links: list[str]) -> str:
    """글 속 [그림] 자리에 그림 링크를 순서대로 끼운다. 자리보다 그림이 많으면 맨 뒤에 모은다."""
    it = iter(links)
    text = _PLACEHOLDER.sub(lambda m: next(it, m.group(0)), text)
    rest = list(it)
    if rest:
        text += "\n## 문서에 든 나머지 그림\n\n" + "\n\n".join(rest) + "\n"
    return text


def convert(src: Path, md: Path | None = None) -> str:
    """HWP·HWPX 한 개를 마크다운 글로 바꾼다(암호 문서 등은 syhwp가 예외를 낸다).
    md(쓸 마크다운 파일)를 주면 그림도 그 옆 '이름_images' 폴더에 꺼내고 글에서 상대 경로로 가리킨다."""
    import syhwp  # 쓸 때만 읽는다

    text = syhwp.extract_markdown(str(src)).replace("\r\n", "\n").strip() + "\n"
    if md is None:
        return text
    images = images_of(src)
    if not images:
        return text
    img_dir = images_dir_for(md)
    img_dir.mkdir(exist_ok=True)
    links = []
    for name, data in images:
        (img_dir / name).write_bytes(data)
        links.append(f"![{name}]({img_dir.name}/{name})")
    return merge_images(text, links)
