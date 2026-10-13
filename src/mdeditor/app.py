"""markDown 편집기 — [파일 탐색기 | 편집기 | 뷰어] 세 칸, 칸 사이 기둥으로 크기 조절."""

from __future__ import annotations

import difflib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QMarginsF, QPoint, QSettings, QStandardPaths, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPageLayout,
    QPageSize,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextDocumentLayout,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTextEdit,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdeditor import __version__
from mdeditor.fmt import locate_in_source, py_to_q, q_to_py, set_heading, set_size, toggle_wrap
from mdeditor import changelog, fileassoc, pdf2md, shortcut, single
from mdeditor.render import kind_of, page, print_document, render_any

MD_SUFFIXES = {".md", ".markdown", ".mdown", ".txt", ".json", ".yaml", ".yml", ".pdf"}
MD_FILTER = "읽을 수 있는 파일 (*.md *.markdown *.mdown *.txt *.json *.yaml *.yml *.pdf);;마크다운 (*.md *.markdown *.mdown);;텍스트 (*.txt);;JSON (*.json);;YAML (*.yaml *.yml);;PDF (*.pdf);;모든 파일 (*)"
SAVE_FILTER = "마크다운 (*.md *.markdown *.mdown);;텍스트 (*.txt);;JSON (*.json);;YAML (*.yaml *.yml);;모든 파일 (*)"
ICON = Path(__file__).with_name("icon.ico")

# 파일 목록 정렬: (설정값, 메뉴 글자)
SORT_MODES = [("added", "올린 순서"), ("name", "이름"), ("kind", "종류(확장자)"), ("folder", "폴더(경로)"), ("mtime", "고친 시각(최근 먼저)")]

# 뷰어 껍데기 페이지: 본문만 갈아 끼워 깜박임·스크롤 튐을 막는다
PREVIEW_JS = """
<style>
#toc { display: none; position: fixed; top: 0; left: 0; bottom: 0; width: 240px; overflow-y: auto;
       padding: 14px 10px 30px 14px; box-sizing: border-box; background: #f6f8fa; border-right: 4px solid #d0d7de;
       font-size: 14px; line-height: 1.45; }
#toc .toc-title { font-weight: 600; color: #59636e; font-size: 12px; margin-bottom: 8px; }
#toc a { display: block; color: #0969da; padding: 4px 4px; border-radius: 4px; text-decoration: none; cursor: pointer; }
#toc a:hover { background: #e7ecf0; }
#toc a.on { background: #ddf4ff; font-weight: 600; }
#toc .lv1 { font-weight: 600; } #toc .lv2 { padding-left: 14px; } #toc .lv3 { padding-left: 28px; }
#toc .lv4, #toc .lv5, #toc .lv6 { padding-left: 42px; font-size: 13px; }
#toc .empty { color: #8c959f; }
body.toc-on #toc { display: block; }
body.toc-on #content { margin-left: 250px; }
#content img { cursor: zoom-in; }
#content .md-changed { color: #0550ae; background: #ddf4ff; box-shadow: -8px 0 0 #ddf4ff, -11px 0 0 #0969da; }
#content .md-changed .md-changed { box-shadow: none; }
#slides { display: none; position: fixed; inset: 0; z-index: 1000; background: #111; color: #e6edf3;
          flex-direction: column; user-select: none; }
body.slides-on #slides { display: flex; }
body.slides-on { overflow: hidden; }
#slides .s-stage { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 16px; position: relative; }
#slides .s-stage img { max-width: 100%; max-height: 100%; object-fit: contain; background: #fff; box-shadow: 0 2px 16px #000a; }
#slides .s-nav { position: absolute; top: 0; bottom: 0; width: 30%; cursor: pointer; display: flex; align-items: center;
                 font-size: 44px; color: #fff0; transition: color .15s; }
#slides .s-nav:hover { color: #fffa; }
#slides .s-prev { left: 0; padding-left: 18px; } #slides .s-next { right: 0; justify-content: flex-end; padding-right: 18px; }
#slides .s-bar { display: flex; gap: 14px; align-items: baseline; padding: 8px 16px 10px; background: #000; font-size: 14px; }
#slides .s-count { font-weight: 600; white-space: nowrap; }
#slides .s-cap { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#slides .s-sec { color: #9198a1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 35%; }
#slides .s-help { color: #6e7681; white-space: nowrap; font-size: 12px; }
#slides .s-close { cursor: pointer; padding: 0 4px; font-size: 18px; } #slides .s-close:hover { color: #fff; }
</style>
<nav id="toc"></nav>
<div id="slides">
  <div class="s-stage"><img alt=""><div class="s-nav s-prev">‹</div><div class="s-nav s-next">›</div></div>
  <div class="s-bar"><span class="s-count"></span><span class="s-cap"></span><span class="s-sec"></span>
    <span class="s-help">← → 넘기기 · Esc 닫기 · F11 전체 화면</span><span class="s-close" title="닫기 (Esc)">✕</span></div>
</div>
<script>
let quietUntil = 0;  // 프로그램이 움직인 스크롤은 편집기로 되돌려 보내지 않는다(서로 밀고 당기기 방지)
const hush = () => { quietUntil = Date.now() + 200; };
const blocks = () => Array.from(document.querySelectorAll('#content [data-line]'))
  .map(el => ({ n: +el.dataset.line, y: el.getBoundingClientRect().top + window.scrollY }));
let totalLines = 1;  // 원본 줄 수(줄 표시가 없는 보기에서 비율 스크롤에 씀)
function setContent(html, lines, changed) {
  hush(); totalLines = lines || 1; document.getElementById('content').innerHTML = html; buildToc(); markChanged(changed || []);
  if (slidesOn()) { slides = contentImages(); if (slides.length) showSlide(Math.min(si, slides.length - 1)); else closeSlides(); }
}
// 새로 불러와 바뀐 줄이 든 블록을 파란색으로(그 줄을 품은 가장 안쪽 블록 = 줄 번호가 그 줄 이하인 마지막 블록)
function markChanged(changed) {
  if (!changed.length) return;
  const els = Array.from(document.querySelectorAll('#content [data-line]'));
  for (const c of changed) {
    let hit = null;
    for (const el of els) if (+el.dataset.line <= c) hit = el;
    if (hit) hit.classList.add('md-changed');
  }
}
// 그림 슬라이드: 본문의 그림만 모아 한 장씩 크게 본다(그림을 누르면 그 그림부터)
let slides = [], si = 0, wheelAt = 0;
const S = document.getElementById('slides');
const contentImages = () => Array.from(document.querySelectorAll('#content img'));
const slidesOn = () => document.body.classList.contains('slides-on');
function openSlides(start) {  // 그림 개수를 돌려준다(0이면 열지 않음)
  slides = contentImages();
  if (!slides.length) return 0;
  document.body.classList.add('slides-on');
  showSlide(Math.max(0, Math.min(start || 0, slides.length - 1)));
  return slides.length;
}
function closeSlides() { document.body.classList.remove('slides-on'); }
function showSlide(i) {
  si = (i + slides.length) % slides.length;  // 끝에서 넘기면 처음으로
  const im = slides[si];
  S.querySelector('.s-stage img').src = im.currentSrc || im.src;
  S.querySelector('.s-count').textContent = (si + 1) + ' / ' + slides.length;
  S.querySelector('.s-cap').textContent = im.alt || im.title || '';
  let sec = '';  // 그림이 들어 있는 절 제목
  heads.forEach(h => { if (h.compareDocumentPosition(im) & Node.DOCUMENT_POSITION_FOLLOWING) sec = h.textContent; });
  S.querySelector('.s-sec').textContent = sec ? '§ ' + sec : '';
}
S.querySelector('.s-prev').onclick = () => showSlide(si - 1);
S.querySelector('.s-next').onclick = () => showSlide(si + 1);
S.querySelector('.s-close').onclick = closeSlides;
S.addEventListener('wheel', e => {
  e.preventDefault();
  if (Date.now() - wheelAt < 250) return;  // 휠 한 번에 한 장
  wheelAt = Date.now();
  showSlide(si + (e.deltaY > 0 ? 1 : -1));
}, { passive: false });
document.addEventListener('click', e => {
  const im = e.target.closest && e.target.closest('#content img');
  if (!im) return;
  e.preventDefault();  // 그림에 걸린 링크로 가지 않는다
  openSlides(contentImages().indexOf(im));
}, true);
document.addEventListener('keydown', e => {
  if (!slidesOn()) {
    if (e.key === 'Escape') console.log('__mdesc__');  // 전체 화면이면 끈다
    return;
  }
  const go = { ArrowRight: 1, ArrowDown: 1, PageDown: 1, ' ': 1, ArrowLeft: -1, ArrowUp: -1, PageUp: -1 }[e.key];
  if (go) showSlide(si + go);
  else if (e.key === 'Home') showSlide(0);
  else if (e.key === 'End') showSlide(slides.length - 1);
  else if (e.key === 'Escape') closeSlides();
  else return;
  e.preventDefault();
});
// 목차: 본문 제목(h1~h6)으로 왼쪽 목록을 만들고, 누르면 그 제목으로 이동(동시보기면 원본도 따라감)
let heads = [];
function buildToc() {
  heads = Array.from(document.querySelectorAll('#content h1, #content h2, #content h3, #content h4, #content h5, #content h6'));
  const toc = document.getElementById('toc');
  const top = Math.min(...heads.map(h => +h.tagName[1]), 6);
  toc.innerHTML = '<div class="toc-title">목차</div>' + (heads.length ? '' : '<div class="empty">제목(#)이 없습니다</div>');
  heads.forEach(h => {
    const a = document.createElement('a');
    a.className = 'lv' + (+h.tagName[1] - top + 1);
    a.textContent = h.textContent;
    a.title = h.textContent;
    a.onclick = () => window.scrollTo(0, h.getBoundingClientRect().top + window.scrollY - 8);
    toc.appendChild(a);
  });
  markToc();
}
function markToc() {  // 지금 보고 있는 절을 목차에서 표시
  const links = document.querySelectorAll('#toc a');
  let cur = -1;
  heads.forEach((h, i) => { if (h.getBoundingClientRect().top <= 40) cur = i; });
  links.forEach((a, i) => a.classList.toggle('on', i === cur));
  if (cur >= 0 && document.body.classList.contains('toc-on')) links[cur].scrollIntoView({ block: 'nearest' });
}
function setToc(on) { document.body.classList.toggle('toc-on', on); }
window.addEventListener('scroll', markToc);
function scrollToLine(line, atEnd) {
  hush();
  if (atEnd) { window.scrollTo(0, document.body.scrollHeight); return; }
  const bs = blocks();
  if (!bs.length) {  // JSON·YAML처럼 줄 표시가 없는 보기: 문서 길이 비율로 맞춘다
    const room = document.body.scrollHeight - window.innerHeight;
    window.scrollTo(0, totalLines > 1 ? room * line / (totalLines - 1) : 0);
    return;
  }
  if (line <= 0) { window.scrollTo(0, 0); return; }
  let prev = null, next = null;
  for (const b of bs) { if (b.n <= line) prev = b; else { next = b; break; } }
  let y = prev ? prev.y : 0;
  if (prev && next && next.n > prev.n) y += (next.y - prev.y) * (line - prev.n) / (next.n - prev.n);
  window.scrollTo(0, Math.max(0, y - 8));
}
function topLine() {
  const bs = blocks(), y = window.scrollY + 8;
  if (!bs.length) {
    const room = document.body.scrollHeight - window.innerHeight;
    return room > 0 ? (totalLines - 1) * window.scrollY / room : 0;
  }
  let prev = null, next = null;
  for (const b of bs) { if (b.y <= y) prev = b; else { next = b; break; } }
  if (!prev) return 0;
  if (next && next.y > prev.y) return prev.n + (next.n - prev.n) * (y - prev.y) / (next.y - prev.y);
  return prev.n;
}
// 뷰어에서 선택한 글자 → 원본을 찾을 단서(블록 시작 줄, 다음 블록 줄, 선택 글자, 블록 안에서 앞쪽 글자)
function selectionInfo() {
  const s = window.getSelection();
  if (!s || s.isCollapsed || !s.rangeCount) return '';
  const r = s.getRangeAt(0);
  let el = r.startContainer.nodeType === 1 ? r.startContainer : r.startContainer.parentElement;
  const blk = el && el.closest('#content [data-line]');
  if (!blk) return '';
  const n = +blk.dataset.line;
  const later = blocks().map(b => b.n).filter(m => m > n);
  const pre = document.createRange();
  pre.selectNodeContents(blk);
  pre.setEnd(r.startContainer, r.startOffset);
  return JSON.stringify({ line: n, end: later.length ? Math.min(...later) : -1, text: s.toString(), before: pre.toString() });
}
let pending = false;
window.addEventListener('scroll', () => {
  if (Date.now() < quietUntil || pending) return;
  pending = true;
  requestAnimationFrame(() => {
    pending = false;
    const atEnd = window.scrollY > 0 && window.innerHeight + window.scrollY >= document.body.scrollHeight - 2;
    console.log('__mdscroll__ ' + topLine() + ' ' + atEnd);
  });
});
</script>
"""


_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def pdf_names(docs: list, folder: Path) -> list[str]:
    """문서마다 '원래 파일 이름.pdf'. 이름이 겹치면 ' (2)'를 붙인다."""
    used: set[str] = set()
    out = []
    for d in docs:
        stem = _BAD_CHARS.sub("_", d.path.stem if d.path else d.name).strip() or "문서"
        name, n = f"{stem}.pdf", 2
        while name.lower() in used:
            name, n = f"{stem} ({n}).pdf", n + 1
        used.add(name.lower())
        out.append(str(folder / name))
    return out


def _natural(text: str) -> list:
    """'문서2'가 '문서10'보다 앞에 오도록 숫자는 수로 비교한다."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", text.casefold()) if t]


def _mtime(doc) -> float:
    try:
        return doc.path.stat().st_mtime if doc.path else float("inf")  # 새 문서는 '가장 최근'
    except OSError:
        return 0.0


def sort_docs(docs: list, mode: str, reverse: bool = False) -> list:
    """파일 목록 정렬 순서. docs는 올린 순서. 같은 값끼리는 올린 순서를 지킨다."""
    keys = {
        "name": lambda d: _natural(d.name),
        "kind": lambda d: (_natural(d.path.suffix if d.path else ".md"), _natural(d.name)),
        "folder": lambda d: (_natural(str(d.path.parent)) if d.path else [], _natural(d.name)),
        "mtime": lambda d: -_mtime(d),
    }
    if mode not in keys:
        return list(reversed(docs)) if reverse else list(docs)
    return sorted(docs, key=keys[mode], reverse=reverse)


def changed_lines(old: str, new: str) -> list[int]:
    """새로 불러온 글에서 바뀌거나 새로 생긴 줄 번호(0부터). 지워지기만 한 줄은 보이지 않으니 빠진다."""
    ops = difflib.SequenceMatcher(None, old.split("\n"), new.split("\n"), autojunk=False).get_opcodes()
    return [j for tag, _i1, _i2, j1, j2 in ops if tag in ("replace", "insert") for j in range(j1, j2)]


REPO_URL = "https://github.com/KimJin777/markDown"


def feature_request_url(version: str) -> str:
    """GitHub '새 이슈' 쓰기 화면 주소(제목·본문 틀·버전을 미리 채움)."""
    from urllib.parse import urlencode

    body = (
        "## 원하는 기능\n\n\n## 어떤 때 쓰려고 하나요\n\n\n"
        f"---\nmdEditor v{version} · Windows {sys.getwindowsversion().build if sys.platform == 'win32' else ''}\n"
    )
    return f"{REPO_URL}/issues/new?" + urlencode({"title": "[기능 요청] ", "body": body, "labels": "enhancement"})


def add_root(roots: list[Path], folder: Path) -> list[Path]:
    """폴더 올리기로 생긴 트리 뿌리 목록. 이미 올린 폴더 안이면 그대로, 새 폴더가 올린 폴더들을 품으면 하나로 합친다."""
    if any(folder.is_relative_to(r) for r in roots):
        return roots
    return [r for r in roots if not r.is_relative_to(folder)] + [folder]


def tree_of(docs: list, roots: list[Path], mode: str, reverse: bool = False) -> list:
    """파일 목록 트리. 항목은 ('dir', 폴더 경로, [자식...]) 또는 ('doc', 문서).
    올린 폴더(roots) 안의 파일은 하위 폴더 모양 그대로, 낱개로 올린 파일은 맨 위 칸에 둔다.
    한 칸 안에서는 폴더가 먼저(이름순), 파일은 정렬 기준대로."""
    top: list = []
    dirs: dict[Path, list] = {}

    def children_of(path: Path, root: Path) -> list:
        if path not in dirs:
            dirs[path] = []
            (top if path == root else children_of(path.parent, root)).append(("dir", path, dirs[path]))
        return dirs[path]

    for d in sort_docs(docs, mode, reverse):
        root = next((r for r in roots if d.path and d.path.is_relative_to(r)), None)
        (children_of(d.path.parent, root) if root else top).append(("doc", d))

    def arrange(items: list) -> None:
        folders = sorted((i for i in items if i[0] == "dir"), key=lambda i: _natural(i[1].name or str(i[1])))
        for f in folders:
            arrange(f[2])
        items[:] = folders + [i for i in items if i[0] == "doc"]

    arrange(top)
    return top


def file_stamp(path: Path | None) -> tuple[float, int] | None:
    """(고친 시각, 크기) — 다른 프로그램이 파일을 바꿨는지 알아보는 데 쓴다."""
    try:
        st = path.stat()
        return st.st_mtime, st.st_size
    except (OSError, AttributeError):
        return None


def read_text(path: Path) -> tuple[str, str, str]:
    """(본문, 인코딩, 줄바꿈). 본문의 줄바꿈은 \\n으로 통일한다 — 편집기가 \\n만 쓰므로,
    그대로 두면 Windows(CRLF) 파일이 열자마자 '수정됨'으로 잡힌다. 저장할 때 원래 줄바꿈으로 되돌린다."""
    raw = path.read_bytes()
    try:
        text, enc = raw.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        text, enc = raw.decode("cp949", errors="replace"), "CP949"  # 예전 한글 메모장 파일
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n").replace("\r", "\n"), enc, newline


@dataclass
class Doc:
    path: Path | None
    untitled_no: int = 0
    qdoc: QTextDocument = field(default_factory=QTextDocument)
    saved_text: str = ""
    encoding: str = "UTF-8"  # 읽은 인코딩(표시용). 저장은 항상 UTF-8
    newline: str = "\n"
    stamp: tuple[float, int] | None = None  # 마지막으로 읽거나 쓴 때의 (고친 시각, 크기)
    changed_outside: bool = False  # 다른 프로그램이 파일을 바꿈 → [새로 불러오기](F5)를 기다리는 중
    changed_lines: list[int] = field(default_factory=list)  # 새로 불러와서 바뀐 줄(파란색) — 여기서 고치면 지운다
    reloaded: bool = False  # 바뀐 파일을 새로 불러왔고 아직 [검토완료] 전 → 목록에 ↻(파란색)

    @property
    def name(self) -> str:
        return self.path.name if self.path else f"새 문서 {self.untitled_no}"

    @property
    def kind(self) -> str:
        """'md' | 'txt' | 'json' | 'yaml' | 'pdf' — 뷰어가 어떻게 보여 줄지."""
        return kind_of(self.path)

    @property
    def is_pdf(self) -> bool:
        """PDF: 뷰어에서 보기만 한다(원본 편집·저장 없음)."""
        return self.kind == "pdf"

    @property
    def is_text(self) -> bool:
        """일반 텍스트 파일(.txt): 원본 창에만 보이고, 저장하면 같은 이름의 .md가 된다."""
        return self.kind == "txt"

    @property
    def base_dir(self) -> Path | None:
        return self.path.parent if self.path else None

    @property
    def dirty(self) -> bool:
        return self.qdoc.toPlainText() != self.saved_text


class PdfToMdWorker(QThread):
    """PDF를 마크다운으로 바꾸는 일을 화면 밖 스레드에서 한다(쪽이 많으면 몇 초 걸림)."""

    converted = Signal(object, object)  # (PDF 경로, 마크다운 글 또는 오류)

    def __init__(self, pdfs: list[Path], parent=None) -> None:
        super().__init__(parent)
        self.pdfs = pdfs

    def run(self) -> None:
        for pdf in self.pdfs:
            try:
                self.converted.emit(pdf, pdf2md.convert(pdf))
            except Exception as e:  # noqa: BLE001 — 깨진 PDF 등: 그 파일만 건너뛰고 알려 준다
                self.converted.emit(pdf, e)


class FileList(QTreeWidget):
    """올린 파일 목록(트리). 폴더로 올리면 하위 폴더 모양 그대로 보인다. 체크한 파일을 한꺼번에 인쇄한다.
    파일·폴더를 끌어다 놓을 수 있다. 폴더를 체크하면 그 안의 파일이 모두 체크된다."""

    filesDropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setIndentation(14)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.DropOnly)
        self.setToolTip(
            "파일·폴더를 여기로 끌어다 놓으면 올라갑니다(폴더는 하위 폴더까지 트리로).\n"
            "체크한 파일은 한꺼번에 인쇄됩니다. 폴더를 체크하면 안의 파일이 모두 체크됩니다."
        )

    def leaves(self) -> list[QTreeWidgetItem]:
        """파일 칸(폴더 칸 빼고)을 보이는 순서대로."""
        out: list[QTreeWidgetItem] = []

        def walk(item: QTreeWidgetItem) -> None:
            if item.data(0, Qt.ItemDataRole.UserRole) is not None:
                out.append(item)
            for i in range(item.childCount()):
                walk(item.child(i))

        walk(self.invisibleRootItem())
        return out

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            self.filesDropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


class Editor(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

    def top_line(self) -> int:
        return self.cursorForPosition(QPoint(0, 0)).blockNumber()

    def at_end(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.maximum() > 0 and bar.value() >= bar.maximum()


class PreviewPage(QWebEnginePage):
    """뷰어 안 링크: 마크다운 파일이면 편집기로 열고, 그 밖은 기본 브라우저로 연다."""

    openMarkdown = Signal(str)
    scrolled = Signal(float, bool)  # 뷰어를 사람이 스크롤함: (원본 줄 번호, 맨 끝인지)
    escPressed = Signal()  # 그림 슬라이드가 닫혀 있을 때 뷰어에서 Esc

    def javaScriptConsoleMessage(self, level, message: str, line: int, source: str) -> None:  # noqa: N802
        if message.startswith("__mdscroll__ "):
            _, ln, at_end = message.split()
            self.scrolled.emit(float(ln), at_end == "true")
        elif message == "__mdesc__":
            self.escPressed.emit()

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # noqa: N802
        if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            return True
        if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in MD_SUFFIXES:
            self.openMarkdown.emit(url.toLocalFile())
        elif url.hasFragment() and url.adjusted(QUrl.UrlFormattingOption.RemoveFragment) == self.url().adjusted(
            QUrl.UrlFormattingOption.RemoveFragment
        ):
            self.runJavaScript(
                f"var e=document.getElementById({json.dumps(url.fragment())});if(e)e.scrollIntoView();"
            )
        else:
            QDesktopServices.openUrl(url)
        return False


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("markDown", "mdeditor")
        self.docs: list[Doc] = []
        self.current: Doc | None = None
        self.untitled_count = 0
        self._preview_ready = False
        self._pdf2md: PdfToMdWorker | None = None  # PDF→마크다운 바꾸는 중인 일
        self._print_jobs: list[QWebEngineView] = []  # 인쇄·PDF가 끝날 때까지 살려 둘 화면 밖 뷰
        self._from_preview = False  # 뷰어 스크롤을 편집기에 옮기는 중(되돌려 보내지 않음)
        self._last_pane = "editor"  # 서식 버튼이 쓸 선택: 마지막으로 누른 칸(편집기/뷰어)
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # 동시보기: 켜면 편집기·뷰어 어느 쪽을 스크롤해도 다른 쪽이 같은 위치로 따라온다
        self.sync_action = QAction("동시보기", self, checkable=True)
        self.sync_action.setToolTip("켜면 원본과 뷰어가 함께 스크롤됩니다 (Ctrl+Shift+L)")
        self.sync_action.setShortcut("Ctrl+Shift+L")
        self.sync_action.setChecked(self.settings.value("syncScroll", True, type=bool))
        self.sync_action.toggled.connect(self._on_sync_toggled)

        # 목차: 뷰어 왼쪽에 제목 목록(누르면 그 절로 이동)
        self.toc_action = QAction("목차", self, checkable=True)
        self.toc_action.setToolTip("뷰어 왼쪽에 목차를 보이거나 숨깁니다 (Ctrl+Shift+T)")
        self.toc_action.setShortcut("Ctrl+Shift+T")
        self.toc_action.setChecked(self.settings.value("toc", True, type=bool))
        self.toc_action.toggled.connect(self._on_toc_toggled)

        # 그림 슬라이드: 본문의 그림만 모아 한 장씩 크게 본다
        self.slides_action = QAction("그림", self)
        self.slides_action.setToolTip("문서의 그림만 슬라이드로 봅니다 — ← → 넘기기, Esc 닫기 (Ctrl+Shift+G)\n뷰어에서 그림을 눌러도 그 그림부터 열립니다")
        self.slides_action.setShortcut("Ctrl+Shift+G")
        self.slides_action.triggered.connect(self.show_slides)
        self.addAction(self.slides_action)  # 전체 화면에서 서식 줄이 숨어도 단축키가 듣게

        # 전체 화면: 뷰어만 화면 가득(F11 또는 Esc로 돌아옴)
        self.fullscreen_action = QAction("전체 화면 보기", self, checkable=True)
        self.fullscreen_action.setToolTip("뷰어만 화면 가득 봅니다 — 돌아오려면 F11 또는 Esc (F11)")
        self.fullscreen_action.setShortcut("F11")
        self.fullscreen_action.toggled.connect(self._on_fullscreen_toggled)
        self.addAction(self.fullscreen_action)  # 메뉴 줄을 숨겨도 F11이 듣게

        # 소스: 끄면 원본 편집기를 숨기고 뷰어만 본다
        self.source_action = QAction("소스", self, checkable=True)
        self.source_action.setToolTip("원본(소스) 창을 보이거나 숨깁니다 — 끄면 뷰어만 보입니다 (Ctrl+Shift+E)")
        self.source_action.setShortcut("Ctrl+Shift+E")
        self.source_action.setChecked(self.settings.value("showSource", True, type=bool))
        self.source_action.toggled.connect(self._on_source_toggled)

        self.files = FileList()
        self.editor = Editor()
        self.preview = QWebEngineView()
        self.preview_page = PreviewPage(self.preview)
        self.preview.setPage(self.preview_page)
        # PDF는 Chromium 내장 PDF 보기로 띄운다(뷰어 자리를 PDF일 때만 이 뷰로 바꿔 끼움)
        self.pdf_view = QWebEngineView()
        for attr in (QWebEngineSettings.WebAttribute.PluginsEnabled, QWebEngineSettings.WebAttribute.PdfViewerEnabled):
            self.pdf_view.settings().setAttribute(attr, True)
        self.viewer_stack = QStackedWidget()
        self.viewer_stack.addWidget(self.preview)
        self.viewer_stack.addWidget(self.pdf_view)
        self._pdf_shown: Path | None = None  # pdf_view에 올라 있는 파일

        # 다른 프로그램이 파일을 바꾸면 알아채서 다시 읽는다
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)
        self._changed: set[Path] = set()
        self.reload_timer = QTimer(self, singleShot=True, interval=300)  # 저장이 끝날 때까지 잠깐 기다린다
        self.reload_timer.timeout.connect(self._reload_changed)
        self._asking_reload = False
        self._reloading = False  # 새로 불러와 본문을 바꾸는 중(내가 고친 것으로 치지 않음)

        self.roots: list[Path] = []  # 폴더 올리기로 올린 폴더(트리 뿌리)
        self._items: dict[int, QTreeWidgetItem] = {}  # id(문서) → 목록 칸
        self._collapsed: set[str] = set()  # 접어 둔 폴더
        self._tree_sig: tuple | None = None  # 지금 그려진 트리 모양
        self.sort_mode = str(self.settings.value("sortMode", "added"))
        self.sort_reverse = self.settings.value("sortReverse", False, type=bool)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setStyleSheet("QSplitter::handle { background: #d0d7de; } QSplitter::handle:hover { background: #8c959f; }")
        right = QWidget()  # 오른쪽: 서식 버튼 줄 + 뷰어
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(0)
        self.format_bar = self._build_format_bar()
        right_box.addWidget(self.format_bar)
        right_box.addWidget(self.viewer_stack)
        for w in (self.files, self.editor, right):
            self.splitter.addWidget(w)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([200, 600, 600])
        self.setCentralWidget(self.splitter)

        self.render_timer = QTimer(self, singleShot=True, interval=150)
        self.render_timer.timeout.connect(self.render_preview)

        self.files.currentItemChanged.connect(self._on_item_changed)
        self.files.itemExpanded.connect(lambda it: self._on_folder_toggled(it, True))
        self.files.itemCollapsed.connect(lambda it: self._on_folder_toggled(it, False))
        self.files.filesDropped.connect(self.open_paths)
        self.files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._files_menu)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.verticalScrollBar().valueChanged.connect(self.sync_scroll)
        self.preview_page.openMarkdown.connect(lambda p: self.open_paths([p]))
        self.preview_page.scrolled.connect(self._on_preview_scrolled)
        self.preview_page.escPressed.connect(lambda: self.fullscreen_action.setChecked(False))
        self.preview.loadFinished.connect(self._on_preview_loaded)

        self._build_menu()
        self._build_status()
        self.preview.setHtml(page("<div id='content'></div>", script=PREVIEW_JS), QUrl.fromLocalFile(str(Path.home()) + "/"))
        self._restore()
        self.editor.setVisible(self.source_action.isChecked())  # 소스 켬/끔 상태 복원
        self.new_file()

    # ---------- 메뉴 ----------
    def _build_menu(self) -> None:
        def act(menu, text, slot, shortcut=None) -> QAction:
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        f = self.menuBar().addMenu("파일(&F)")
        a_new = act(f, "새 파일", self.new_file, QKeySequence.StandardKey.New)
        a_open = act(f, "파일 올리기(여러 개)...", self.open_files_dialog, QKeySequence.StandardKey.Open)
        act(f, "폴더 올리기...", self.open_folder_dialog, "Ctrl+Shift+O")
        self.reload_action = act(f, "새로 불러오기", self.reload_current, "F5")
        self.reload_action.setToolTip("다른 프로그램에서 바뀐 파일(목록에 ↻)을 파일에서 다시 읽습니다 (F5)")
        self.reload_action.setEnabled(False)
        self.reviewed_action = act(f, "비교 검토 완료", self.mark_reviewed, "Ctrl+F5")
        self.reviewed_action.setToolTip("새로 불러와 바뀐 부분(파란색)을 다 봤으면 눌러 보통 색으로 돌립니다 (Ctrl+F5)")
        self.reviewed_action.setEnabled(False)
        f.addSeparator()
        a_save = act(f, "저장", self.save_current, QKeySequence.StandardKey.Save)
        act(f, "다른 이름으로 저장...", self.save_current_as, "Ctrl+Shift+S")
        act(f, "모두 저장", self.save_all, "Ctrl+Alt+S")
        f.addSeparator()
        act(f, "목록에서 닫기(체크한 파일 모두)", self.close_current, "Ctrl+W")
        self.close_checked_action = QAction("선택닫기", self)
        self.close_checked_action.setToolTip("목록에서 체크한 파일을 모두 닫습니다(저장 안 된 파일은 물어봄)")
        self.close_checked_action.triggered.connect(self.close_checked)
        f.addSeparator()
        a_print = act(f, "체크한 파일 인쇄...", self.print_checked, QKeySequence.StandardKey.Print)
        a_pdf = act(f, "체크한 파일 PDF로 저장...", self.save_pdf, "Ctrl+Shift+P")
        self.pdf2md_action = act(f, "PDF를 마크다운으로 바꾸기", self.convert_pdfs, "Ctrl+Shift+M")
        self.pdf2md_action.setToolTip(
            "체크한 PDF(없으면 지금 보는 PDF)를 같은 폴더에 '이름.md'로 바꿔 목록에 올립니다 — 글자·표만, 그림은 빠짐"
        )
        f.addSeparator()
        act(f, "바탕화면에 바로가기 만들기", lambda: self.make_shortcut())
        act(f, ".md 파일을 mdEditor로 열기 등록...", self.register_file_assoc)
        act(f, ".md 파일 연결 등록 해제", self.unregister_file_assoc)
        f.addSeparator()
        act(f, "끝내기", self.close, "Ctrl+Q")

        v = self.menuBar().addMenu("보기(&V)")
        v.addAction(self.source_action)
        v.addAction(self.toc_action)
        v.addAction(self.sync_action)
        v.addSeparator()
        v.addAction(self.slides_action)
        v.addAction(self.fullscreen_action)
        v.addSeparator()
        self.auto_reload_action = QAction("바뀐 파일 자동으로 다시 읽기", self, checkable=True)
        self.auto_reload_action.setToolTip("켜면 다른 프로그램이 바꾼 파일을 F5 없이 바로 다시 읽습니다")
        self.auto_reload_action.setChecked(self.settings.value("autoReload", False, type=bool))
        self.auto_reload_action.toggled.connect(self._on_auto_reload_toggled)
        v.addAction(self.auto_reload_action)
        v.addSeparator()
        act(v, "폴더 모두 펼치기", lambda: self.expand_folders(True))  # 목록에서 누른 폴더(없으면 모든 폴더)
        act(v, "폴더 모두 접기", lambda: self.expand_folders(False))

        # 모두선택: 누를 때마다 목록 전체 체크 ↔ 전체 해제(토글). 버튼은 '모두 체크됨'일 때 눌린 모양
        self.select_all_action = QAction("모두선택", self, checkable=True)
        self.select_all_action.setShortcut("Ctrl+Shift+A")
        self.select_all_action.setToolTip("목록의 파일을 모두 체크하거나, 모두 체크돼 있으면 모두 해제합니다 (Ctrl+Shift+A)")
        self.select_all_action.triggered.connect(self._toggle_check_all)
        self.files.itemChanged.connect(lambda _item: self._sync_select_all())

        s = self.menuBar().addMenu("선택(&S)")
        s.addAction(self.select_all_action)
        act(s, "모두 체크 해제", lambda: self._check_all(False))

        # 정렬: 목록 순서 기준(고르면 바로 다시 늘어놓고, 새로 올린 파일도 그 기준을 따른다)
        self.sort_menu = QMenu("목록 정렬", self)
        group = QActionGroup(self)
        for mode, label in SORT_MODES:
            a = QAction(label, self, checkable=True)
            a.setChecked(mode == self.sort_mode)
            a.triggered.connect(lambda _c=False, m=mode: self.set_sort(m, self.sort_reverse))
            group.addAction(a)
            self.sort_menu.addAction(a)
        self.sort_menu.addSeparator()
        self.sort_reverse_action = QAction("거꾸로", self, checkable=True)
        self.sort_reverse_action.setChecked(self.sort_reverse)
        self.sort_reverse_action.toggled.connect(lambda on: self.set_sort(self.sort_mode, on))
        self.sort_menu.addAction(self.sort_reverse_action)
        v.addSeparator()
        v.addMenu(self.sort_menu)
        sort_btn = QToolButton()
        sort_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        sort_btn.setMenu(self.sort_menu)
        sort_btn.setToolTip("파일 목록 정렬 기준")

        h = self.menuBar().addMenu("도움말(&H)")
        act(h, "새 기능·변경 이력...", lambda: self.show_changelog())
        act(h, "기능 추가 요청...", self.request_feature)
        act(h, "mdEditor 정보...", self.show_about)

        bar = self.addToolBar("도구")
        bar.setObjectName("toolbar")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for a, label in (
            (a_new, "새 파일"),
            (a_open, "파일 올리기"),
            (self.reload_action, "새로 불러오기"),
            (self.reviewed_action, "검토완료"),
            (self.select_all_action, "모두선택"),
            (self.close_checked_action, "선택닫기"),
            ("sort", None),
            (a_save, "저장"),
            (None, None),
            (a_print, "인쇄"),
            (a_pdf, "PDF로 저장"),
            (self.pdf2md_action, "PDF→MD"),
        ):
            if a is None:
                bar.addSeparator()
            elif a == "sort":
                bar.addWidget(sort_btn)
            else:
                bar.addAction(a)
                bar.widgetForAction(a).setText(label)
                sc = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                if sc and sc not in a.toolTip():  # 단축키를 풍선 도움말에 보인다(예: 저장 (Ctrl+S))
                    a.setToolTip(f"{label} ({sc})")
        self.sort_button = sort_btn
        self._update_sort_button()

    # ---------- 서식 버튼(오른쪽 위) — 왼쪽 원본에서 선택한 글자에 적용 ----------
    def _build_format_bar(self) -> QToolBar:
        bar = QToolBar("서식")
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        bar.setStyleSheet("QToolBar { border-bottom: 1px solid #d0d7de; spacing: 2px; }")

        size_btn = QToolButton()
        size_btn.setText("글자 크기")
        size_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(size_btn)
        for level in (1, 2, 3):
            menu.addAction(f"제목 {level}  ({'#' * level})", lambda lv=level: self.apply_format(lambda t, s, e: set_heading(t, s, e, lv)))
        menu.addAction("본문(제목 해제)", lambda: self.apply_format(lambda t, s, e: set_heading(t, s, e, 0)))
        menu.addSeparator()
        for label, px in (("아주 크게 (32px)", 32), ("크게 (24px)", 24), ("조금 크게 (18px)", 18), ("작게 (12px)", 12)):
            menu.addAction(label, lambda p=px: self.apply_format(lambda t, s, e: set_size(t, s, e, p)))
        menu.addAction("기본 크기(크기 지정 해제)", lambda: self.apply_format(lambda t, s, e: set_size(t, s, e, None)))
        size_btn.setMenu(menu)
        size_btn.setToolTip("제목 단계(#) 또는 글자 크기 지정(HTML)")
        bar.addWidget(size_btn)
        bar.addSeparator()

        def fmt_action(text: str, tip: str, left: str, right: str | None, shortcut: str | None, bold=False, italic=False, under=False, strike=False):
            a = QAction(text, self)
            f = a.font()
            f.setBold(bold)
            f.setItalic(italic)
            f.setUnderline(under)
            f.setStrikeOut(strike)
            a.setFont(f)
            a.setToolTip(f"{tip}{f' ({shortcut})' if shortcut else ''} — 원본: {left}글자{right or left}")
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(lambda: self.apply_format(lambda t, s, e: toggle_wrap(t, s, e, left, right)))
            bar.addAction(a)

        fmt_action("굵게", "굵게", "**", None, "Ctrl+B", bold=True)
        fmt_action("기울임", "기울임", "*", None, "Ctrl+I", italic=True)
        fmt_action("밑줄", "밑줄", "<u>", "</u>", "Ctrl+U", under=True)
        fmt_action("취소선", "취소선", "~~", None, None, strike=True)
        bar.addSeparator()
        bar.addAction(self.source_action)
        bar.addAction(self.toc_action)
        bar.addAction(self.sync_action)
        bar.addSeparator()
        bar.addAction(self.slides_action)
        bar.addAction(self.fullscreen_action)
        bar.widgetForAction(self.fullscreen_action).setText("전체 화면")
        return bar

    def _on_focus_changed(self, _old, new) -> None:
        if new is self.editor:
            self._last_pane = "editor"
        elif new is not None and (new is self.preview or self.preview.isAncestorOf(new)):
            self._last_pane = "preview"

    def apply_format(self, fn) -> None:
        """선택한 글자(없으면 커서 위치)에 서식을 적용. 같은 버튼을 다시 누르면 해제된다. 되돌리기 한 번에 취소.
        마지막으로 뷰어를 눌렀으면 뷰어에서 선택한 글자를 원본에서 찾아 적용한다."""
        if self.current is None or self.current.is_pdf:
            return
        if self._last_pane == "preview":
            self.preview_page.runJavaScript("selectionInfo()", 0, lambda info: self._apply_from_preview(fn, info))
        else:
            self._apply_in_editor(fn)

    def _apply_from_preview(self, fn, info: str) -> None:
        if not info:  # 뷰어에 선택이 없으면 원본 커서 위치에
            self._apply_in_editor(fn)
            return
        d = json.loads(info)
        text = self.current.qdoc.toPlainText()
        hit = locate_in_source(text, d["line"], d["end"], d["text"], d["before"])
        if hit is None:
            QMessageBox.information(
                self, "서식", "뷰어에서 고른 글자를 원본에서 찾지 못했습니다.\n왼쪽 원본에서 글자를 선택한 뒤 다시 눌러 주세요."
            )
            return
        cur = self.editor.textCursor()
        cur.setPosition(py_to_q(text, hit[0]))
        cur.setPosition(py_to_q(text, hit[1]), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cur)
        self._apply_in_editor(fn, keep_view=True)

    def _apply_in_editor(self, fn, keep_view: bool = False) -> None:
        text = self.current.qdoc.toPlainText()
        cur = self.editor.textCursor()
        s, e = q_to_py(text, cur.selectionStart()), q_to_py(text, cur.selectionEnd())
        bar = self.editor.verticalScrollBar()
        top = bar.value()
        rs, re_, new, ns, ne = fn(text, s, e)
        cur.beginEditBlock()
        cur.setPosition(py_to_q(text, rs))
        cur.setPosition(py_to_q(text, re_), QTextCursor.MoveMode.KeepAnchor)
        cur.insertText(new)
        cur.endEditBlock()
        after = text[:rs] + new + text[re_:]
        cur.setPosition(py_to_q(after, ns))
        cur.setPosition(py_to_q(after, ne), QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cur)
        if keep_view:  # 뷰어에서 작업 중이면 화면이 튀지 않게 원래 위치 유지
            self._from_preview = True
            bar.setValue(top)
            self._from_preview = False
        else:
            self.editor.setFocus()

    # ---------- 파일 목록 ----------
    def _item_of(self, doc: Doc) -> QTreeWidgetItem | None:
        return self._items.get(id(doc))

    def _checked(self) -> list[Doc]:
        """체크한 파일(보이는 순서대로)."""
        return [
            it.data(0, Qt.ItemDataRole.UserRole) for it in self.files.leaves() if it.checkState(0) == Qt.CheckState.Checked
        ]

    def _refresh_item(self, doc: Doc) -> None:
        item = self._item_of(doc)
        if item:
            mark = ("● " if doc.dirty else "") + ("↻ " if doc.changed_outside or doc.reloaded else "")
            item.setText(0, mark + doc.name)
            tip = str(doc.path) if doc.path else "저장하지 않은 새 문서"
            if doc.changed_outside:
                tip += "\n다른 프로그램에서 바뀌었습니다 — 새로 불러오기(F5)"
            elif doc.reloaded:
                tip += "\n바뀐 내용을 새로 불러왔습니다(바뀐 부분은 파란색) — 다 봤으면 [검토완료](Ctrl+F5)"
            item.setToolTip(0, tip)
            color = "#bc4c00" if doc.changed_outside else "#0969da" if doc.reloaded else None  # 주황: 읽기 전, 파랑: 읽음·검토 전
            item.setForeground(0, QColor(color) if color else self.files.palette().text())
        if doc is self.current:
            self.setWindowTitle(f"{doc.name}{' *' if doc.dirty else ''} — mdEditor v{__version__}")
            self.reload_action.setEnabled(doc.changed_outside)

    def _add_doc(self, doc: Doc) -> None:
        doc.qdoc.setParent(self)  # 목록에서 닫아도 편집기가 잠시 쥐고 있을 수 있어 창이 소유
        doc.qdoc.setDocumentLayout(QPlainTextDocumentLayout(doc.qdoc))
        doc.qdoc.setDefaultFont(self.editor.font())
        doc.qdoc.contentsChanged.connect(lambda d=doc: self._refresh_item(d))
        doc.qdoc.contentsChanged.connect(lambda d=doc: self._on_doc_edited(d))
        self.docs.append(doc)
        self._watch(doc)
        self._apply_sort()
        self.files.setCurrentItem(self._item_of(doc))

    def _rebuild_list(self) -> None:
        """파일 목록 트리를 문서·올린 폴더·정렬 기준대로 새로 그린다(체크·펼침·지금 보는 파일·스크롤은 그대로)."""
        checked = {id(d) for d in self._checked()}
        collapsed = set(self._collapsed)
        bar = self.files.verticalScrollBar()
        top = bar.value()
        folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.files.blockSignals(True)
        try:
            self.files.clear()
            self._items = {}

            def add(parent: QTreeWidgetItem, nodes: list) -> None:
                for node in nodes:
                    item = QTreeWidgetItem(parent)
                    if node[0] == "dir":
                        path = node[1]
                        item.setText(0, path.name or str(path))
                        item.setToolTip(0, str(path))
                        item.setIcon(0, folder_icon)
                        item.setData(0, Qt.ItemDataRole.UserRole + 1, str(path))
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
                        item.setCheckState(0, Qt.CheckState.Unchecked)
                        add(item, node[2])  # 안의 파일 체크에 따라 폴더 체크(일부만이면 '반쯤')가 정해진다
                        item.setExpanded(str(path) not in collapsed)
                    else:
                        doc = node[1]
                        item.setData(0, Qt.ItemDataRole.UserRole, doc)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(0, Qt.CheckState.Checked if id(doc) in checked else Qt.CheckState.Unchecked)
                        self._items[id(doc)] = item
                        self._refresh_item(doc)

            add(self.files.invisibleRootItem(), tree_of(self.docs, self.roots, self.sort_mode, self.sort_reverse))
            if self.current is not None and (cur := self._item_of(self.current)):
                self.files.setCurrentItem(cur)
        finally:
            self.files.blockSignals(False)
        bar.setValue(top)
        self._sync_select_all()

    def _on_folder_toggled(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if path := item.data(0, Qt.ItemDataRole.UserRole + 1):  # 접은 폴더는 다시 그려도 접힌 채로
            (self._collapsed.discard if expanded else self._collapsed.add)(path)

    @staticmethod
    def _is_folder(item: QTreeWidgetItem | None) -> bool:
        return item is not None and bool(item.data(0, Qt.ItemDataRole.UserRole + 1))

    def _set_expanded_tree(self, item: QTreeWidgetItem, on: bool) -> None:
        """폴더 칸과 그 안의 하위 폴더를 모두 펼치거나 접는다(접은 상태는 _collapsed에 기억됨)."""
        if self._is_folder(item):
            item.setExpanded(on)
        for i in range(item.childCount()):
            self._set_expanded_tree(item.child(i), on)

    def expand_folders(self, on: bool, item: QTreeWidgetItem | None = None) -> None:
        """고른 폴더(목록에서 누른 폴더)를 하위 폴더까지 모두 펼치기/접기. 폴더를 고르지 않았으면 모든 폴더."""
        if item is None:
            cur = self.files.currentItem()
            item = cur if self._is_folder(cur) else self.files.invisibleRootItem()
        self._set_expanded_tree(item, on)

    def _files_menu(self, pos: QPoint) -> None:
        """파일 목록 오른쪽 클릭: 폴더 펼치기·접기."""
        item = self.files.itemAt(pos)
        menu = QMenu(self)
        if self._is_folder(item):
            menu.addAction("이 폴더 모두 펼치기(하위 폴더까지)", lambda: self.expand_folders(True, item))
            menu.addAction("이 폴더 모두 접기(하위 폴더까지)", lambda: self.expand_folders(False, item))
            menu.addSeparator()
        root = self.files.invisibleRootItem()
        menu.addAction("모든 폴더 펼치기", lambda: self.expand_folders(True, root))
        menu.addAction("모든 폴더 접기", lambda: self.expand_folders(False, root))
        menu.exec(self.files.viewport().mapToGlobal(pos))

    def _on_item_changed(self, item: QTreeWidgetItem | None, _prev) -> None:
        if item is None:
            return
        doc: Doc | None = item.data(0, Qt.ItemDataRole.UserRole)
        if doc is None:  # 폴더 칸: 보던 파일을 그대로 둔다
            return
        self.current = doc
        self.editor.setDocument(doc.qdoc)
        self.editor.setReadOnly(doc.is_pdf)
        self.editor.setPlaceholderText(
            "PDF 파일은 오른쪽 뷰어에서 보기만 합니다(원본 편집 없음).\n"
            "마크다운으로 고치려면 위쪽 [PDF→MD](Ctrl+Shift+M)로 바꾸세요." if doc.is_pdf else ""
        )
        self.editor.setFocus()
        self._refresh_item(doc)
        self._show_changes()
        self.render_preview()
        self._update_status()

    # ---------- 상태 표시줄(맨 아래) ----------
    def _build_status(self) -> None:
        sb = self.statusBar()
        sb.setStyleSheet("QStatusBar { border-top: 1px solid #d0d7de; } QStatusBar QLabel { padding: 0 8px; }")
        self.st_path = QLabel()
        self.st_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)  # 경로를 끌어 복사 가능
        self.st_kind = QLabel()
        self.st_pos = QLabel()
        self.st_enc = QLabel()
        self.st_sync = QLabel()
        sb.addWidget(self.st_path, 1)  # 왼쪽: 파일 경로(남는 폭 전부)
        for w in (self.st_kind, self.st_pos, self.st_enc, self.st_sync):
            sb.addPermanentWidget(w)
        ver = QToolButton()  # 맨 오른쪽 버전 — 누르면 변경 이력
        ver.setText(f"v{__version__}")
        ver.setAutoRaise(True)
        ver.setToolTip("새 기능·변경 이력 보기")
        ver.clicked.connect(lambda: self.show_changelog())
        sb.addPermanentWidget(ver)
        self.editor.cursorPositionChanged.connect(self._update_pos)
        self.sync_action.toggled.connect(lambda _on: self._update_status())

    def _update_status(self) -> None:
        d = self.current
        if d is None:
            return
        self.st_path.setText(str(d.path) if d.path else "(저장하지 않은 새 문서)")
        self.st_path.setToolTip(str(d.path) if d.path else "")
        self.st_kind.setText(
            {"txt": "텍스트(.txt) → 저장 시 .md", "json": "JSON", "yaml": "YAML", "pdf": "PDF(보기만)"}.get(d.kind, "마크다운")
        )
        self.st_enc.setText("" if d.is_pdf else f"{d.encoding} · {'CRLF' if d.newline == chr(13) + chr(10) else 'LF'}")
        self.st_sync.setText("동시보기 켬" if self.sync_action.isChecked() else "동시보기 끔")
        self._update_pos()

    def _update_pos(self) -> None:
        c = self.editor.textCursor()
        sel = abs(c.selectionEnd() - c.selectionStart())
        lines = self.editor.document().blockCount()
        text = f"줄 {c.blockNumber() + 1}/{lines}, 칸 {c.positionInBlock() + 1}"
        self.st_pos.setText(text + (f" · {sel}자 선택" if sel else ""))

    def _check_all(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        self.files.blockSignals(True)
        try:
            for item in self.files.leaves():  # 폴더 칸은 안의 파일을 따라 저절로 바뀐다
                item.setCheckState(0, state)
        finally:
            self.files.blockSignals(False)
        self._sync_select_all()

    def _all_checked(self) -> bool:
        leaves = self.files.leaves()
        return bool(leaves) and all(it.checkState(0) == Qt.CheckState.Checked for it in leaves)

    def _toggle_check_all(self) -> None:
        on = not self._all_checked()
        self._check_all(on)
        self.statusBar().showMessage(f"{len(self.docs)}개 파일을 모두 체크했습니다." if on else "체크를 모두 풀었습니다.", 3000)

    def _sync_select_all(self) -> None:
        """하나씩 체크를 바꿔도 버튼 모양이 실제 상태(모두 체크됨 여부)를 따라가게."""
        self.select_all_action.setChecked(self._all_checked())

    # ---------- 목록 정렬 ----------
    def set_sort(self, mode: str, reverse: bool) -> None:
        self.sort_mode, self.sort_reverse = mode, reverse
        self.settings.setValue("sortMode", mode)
        self.settings.setValue("sortReverse", reverse)
        self._update_sort_button()
        self._apply_sort()
        label = dict(SORT_MODES).get(mode, mode)
        self.statusBar().showMessage(f"목록을 '{label}'{' 거꾸로' if reverse else ''} 정렬했습니다.", 3000)

    def _update_sort_button(self) -> None:
        label = dict(SORT_MODES).get(self.sort_mode, "올린 순서")
        self.sort_button.setText(f"정렬: {label.split('(')[0]}{' ↑' if self.sort_reverse else ''}")

    def _apply_sort(self) -> None:
        """목록을 정렬 기준대로 다시 늘어놓는다. 모양(폴더·순서)이 그대로면 다시 그리지 않는다."""
        self.roots = [r for r in self.roots if any(d.path and d.path.is_relative_to(r) for d in self.docs)]
        tree = tree_of(self.docs, self.roots, self.sort_mode, self.sort_reverse)

        def sig(nodes: list) -> tuple:
            return tuple((n[0], str(n[1]), sig(n[2])) if n[0] == "dir" else ("doc", id(n[1])) for n in nodes)

        if (s := sig(tree)) != self._tree_sig:
            self._tree_sig = s
            self._rebuild_list()

    # ---------- 열기 ----------
    def new_file(self) -> None:
        self.untitled_count += 1
        self._add_doc(Doc(path=None, untitled_no=self.untitled_count))

    def open_files_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "마크다운 파일 올리기", self._last_dir(), MD_FILTER)
        self.open_paths(paths)

    def open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "폴더 올리기", self._last_dir())
        if folder:
            self.open_paths([folder])

    def open_paths(self, paths: list[str]) -> None:
        files: list[Path] = []
        folders: list[Path] = []
        for p in map(Path, paths):
            if p.is_dir():
                folders.append(p.resolve())
                files += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in MD_SUFFIXES)
            elif p.is_file():
                files.append(p)
        if not files:
            return
        self.settings.setValue("lastDir", str(files[-1].parent))
        # 아무것도 쓰지 않은 첫 새 문서는 자리만 차지하므로 치운다
        if len(self.docs) == 1 and self.docs[0].path is None and not self.docs[0].qdoc.toPlainText():
            self._remove_doc(self.docs[0])
        for folder in folders:  # 올린 폴더는 하위 폴더까지 트리로 보인다
            self.roots = add_root(self.roots, folder)
        last = None
        for f in files:
            f = f.resolve()
            existing = next((d for d in self.docs if d.path == f), None)
            if existing:
                last = existing
                continue
            try:
                text, enc, newline = ("", "PDF", "\n") if kind_of(f) == "pdf" else read_text(f)
            except OSError as e:
                QMessageBox.warning(self, "열기 실패", f"{f}\n{e}")
                continue
            doc = Doc(path=f, saved_text=text, encoding=enc, newline=newline, stamp=file_stamp(f))
            doc.qdoc.setPlainText(text)
            doc.qdoc.setModified(False)
            self._add_doc(doc)
            last = doc
        self._apply_sort()  # 올린 폴더가 기존 폴더를 품으면 트리 모양이 바뀐다
        if last and (item := self._item_of(last)):
            self.files.setCurrentItem(item)
        self.statusBar().showMessage(f"{len(files)}개 파일을 올렸습니다.", 4000)

    # ---------- 바뀐 파일 다시 읽기(감지) ----------
    def _watch(self, doc: Doc) -> None:
        if doc.path and str(doc.path) not in self.watcher.files() and doc.path.exists():
            self.watcher.addPath(str(doc.path))

    def _unwatch(self, doc: Doc) -> None:
        if doc.path and str(doc.path) in self.watcher.files():
            if not any(d is not doc and d.path == doc.path for d in self.docs):
                self.watcher.removePath(str(doc.path))

    def _on_file_changed(self, path: str) -> None:
        self._changed.add(Path(path))
        self.reload_timer.start()  # 여러 번 연달아 와도 한 번만 처리

    def _reload_changed(self) -> None:
        if self._asking_reload:  # 묻는 창이 떠 있는 동안 온 변경은 창을 닫은 뒤 처리
            self.reload_timer.start()
            return
        changed, self._changed = self._changed, set()
        for path in changed:
            for doc in [d for d in self.docs if d.path == path]:
                self._check_reload(doc)

    def _check_reload(self, doc: Doc) -> None:
        """파일이 정말 바뀌었으면 목록에 ↻ 표시를 하고 [새로 불러오기](F5)를 켠다(자동으로 다시 읽기가 켜져 있으면 바로 읽음)."""
        stamp = file_stamp(doc.path)
        if stamp is None:  # 지워졌거나 옮겨졌다(목록에는 남겨 둔다 — 저장하면 다시 생긴다)
            self.statusBar().showMessage(f"파일이 지워졌거나 옮겨졌습니다: {doc.path}", 8000)
            return
        self._watch(doc)  # 지우고 새로 쓰는 방식으로 저장하는 프로그램이 있어 다시 건다
        if stamp == doc.stamp:
            return
        doc.stamp = stamp
        if not doc.is_pdf:
            try:
                text, _enc, _newline = read_text(doc.path)
            except OSError:
                return
            if text == doc.saved_text:  # 시각만 바뀜(내용 같음)
                return
        if self.auto_reload_action.isChecked():
            self._reload_doc(doc)
            return
        doc.changed_outside = True
        self._refresh_item(doc)
        self.statusBar().showMessage(f"다른 프로그램에서 바뀌었습니다: {doc.name} — 새로 불러오기(F5)", 8000)

    def reload_current(self) -> None:
        """[새로 불러오기](F5): 지금 보는 파일이 밖에서 바뀌었으면 파일에서 다시 읽는다."""
        if self.current is not None and self.current.changed_outside:
            self._reload_doc(self.current)

    def _on_auto_reload_toggled(self, on: bool) -> None:
        self.settings.setValue("autoReload", on)
        if on:  # 켜는 순간 기다리던 파일도 다시 읽는다
            for doc in [d for d in self.docs if d.changed_outside]:
                self._reload_doc(doc)

    def _reload_doc(self, doc: Doc) -> None:
        """파일에서 다시 읽는다. 여기서 고치고 저장하지 않은 내용이 있으면 먼저 묻는다."""
        if doc.is_pdf:
            doc.changed_outside = False
            if doc is self.current:
                self._show_pdf(doc.path, reload=True)
            self._refresh_item(doc)
            self.statusBar().showMessage(f"PDF를 새로 불러왔습니다: {doc.name}", 5000)
            return
        try:
            text, enc, newline = read_text(doc.path)
        except OSError as e:
            QMessageBox.warning(self, "새로 불러오기", f"{doc.path}\n{e}")
            return
        if doc.dirty and text != doc.qdoc.toPlainText():
            self._asking_reload = True
            try:
                r = QMessageBox.question(
                    self,
                    "파일이 바뀜",
                    f"{doc.name}\n다른 프로그램에서 파일이 바뀌었습니다.\n\n"
                    "다시 읽을까요? (여기서 고치고 저장하지 않은 내용은 사라집니다 — Ctrl+Z로 되돌릴 수 있음)",
                )
            finally:
                self._asking_reload = False
            if r != QMessageBox.StandardButton.Yes:
                return  # ↻ 표시는 남겨 둔다(나중에 F5로 다시 읽을 수 있게)
        doc.changed_outside = False
        doc.stamp = file_stamp(doc.path)
        old = doc.qdoc.toPlainText()
        self._reloading = True
        try:
            self._replace_text(doc, text, enc, newline)
        finally:
            self._reloading = False
        doc.changed_lines = changed_lines(old, text)
        doc.reloaded = doc.reloaded or text != old  # 자동으로 다시 읽어도 목록에 ↻가 남아 바뀐 파일임을 안다
        self._refresh_item(doc)
        if doc is self.current:
            self._show_changes()
            self.render_preview()
        self._apply_sort()  # '고친 시각' 정렬이면 자리가 바뀐다
        n = len(doc.changed_lines)
        self.statusBar().showMessage(
            f"파일을 새로 불러왔습니다: {doc.name}" + (f" — 바뀐 줄 {n}개를 파란색으로 표시" if n else ""), 8000
        )

    def _on_doc_edited(self, doc: Doc) -> None:
        """여기서 고치기 시작하면(되돌리기 포함) 새로 불러온 표시(파란색)를 지운다 — 줄 번호가 어긋나므로."""
        if self._reloading or not doc.changed_lines:
            return
        doc.changed_lines = []
        if doc is self.current:
            self._show_changes()

    def _show_changes(self) -> None:
        """편집기에서 새로 불러와 바뀐 줄을 파란색으로 칠한다(뷰어는 render_preview가 칠함)."""
        sels = []
        doc = self.current
        if doc is not None and doc.changed_lines and not doc.is_pdf:
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#ddf4ff"))
            fmt.setForeground(QColor("#0550ae"))
            fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            for n in doc.changed_lines:
                block = doc.qdoc.findBlockByNumber(n)
                if not block.isValid():
                    continue
                sel = QTextEdit.ExtraSelection()
                sel.format = fmt
                sel.cursor = QTextCursor(block)
                sels.append(sel)
        self.editor.setExtraSelections(sels)
        self.reviewed_action.setEnabled(bool(sels) or (doc is not None and doc.reloaded))

    def mark_reviewed(self) -> None:
        """[검토완료]: 새로 불러와 바뀐 부분(파란색)을 다 봤다 — 편집기·뷰어 모두 보통 색으로."""
        doc = self.current
        if doc is None or not (doc.changed_lines or doc.reloaded):
            return
        doc.changed_lines = []
        doc.reloaded = False
        self._refresh_item(doc)
        self._show_changes()
        self.render_preview()
        self.statusBar().showMessage(f"비교 검토 완료: {doc.name}", 3000)

    def _replace_text(self, doc: Doc, text: str, enc: str, newline: str) -> None:
        """본문을 새 내용으로 갈아 끼운다. 되돌리기(Ctrl+Z)가 되고, 보던 위치·커서는 그대로."""
        is_cur = doc is self.current
        bar = self.editor.verticalScrollBar()
        top, pos = bar.value(), self.editor.textCursor().position()
        cur = QTextCursor(doc.qdoc)
        cur.select(QTextCursor.SelectionType.Document)
        cur.insertText(text)
        doc.saved_text, doc.encoding, doc.newline = text, enc, newline
        self._refresh_item(doc)
        if is_cur:
            c = self.editor.textCursor()
            c.setPosition(min(pos, doc.qdoc.characterCount() - 1))
            self.editor.setTextCursor(c)
            bar.setValue(top)
            self._update_status()

    # ---------- 저장·닫기 ----------
    def _write(self, doc: Doc, path: Path) -> bool:
        text = doc.qdoc.toPlainText()
        self._unwatch(doc)  # 내가 쓰는 것을 '다른 프로그램이 바꿈'으로 잡지 않게
        try:
            path.write_text(text, encoding="utf-8", newline=doc.newline)
        except OSError as e:
            self._watch(doc)
            QMessageBox.warning(self, "저장 실패", f"{path}\n{e}")
            return False
        doc.path, doc.saved_text, doc.encoding = path.resolve(), text, "UTF-8"
        doc.stamp = file_stamp(doc.path)
        self._watch(doc)
        self._apply_sort()  # 이름·고친 시각이 바뀌었을 수 있다
        self.settings.setValue("lastDir", str(path.parent))
        self._refresh_item(doc)
        if doc is self.current:
            self.render_preview()  # 기준 폴더·종류(.txt→.md)가 바뀌었을 수 있다
            self._update_status()
        self.statusBar().showMessage(f"저장했습니다: {path}", 4000)
        return True

    def save(self, doc: Doc) -> bool:
        if doc.is_pdf:
            self.statusBar().showMessage("PDF는 보기만 하므로 저장할 것이 없습니다.", 4000)
            return True
        if doc.path and doc.is_text:
            # 텍스트 파일은 같은 이름의 .md로 저장하고, 그 뒤로는 .md가 원본이 된다(원래 .txt는 그대로 둔다)
            md = doc.path.with_suffix(".md")
            if md.exists() and not any(d is not doc and d.path == md.resolve() for d in self.docs):
                r = QMessageBox.question(self, "저장", f"{md.name} 파일이 이미 있습니다.\n덮어쓸까요?")
                if r != QMessageBox.StandardButton.Yes:
                    return False
            elif any(d is not doc and d.path == md.resolve() for d in self.docs):
                QMessageBox.warning(self, "저장", f"{md.name}이(가) 이미 목록에 열려 있습니다.\n'다른 이름으로 저장'을 쓰세요.")
                return False
            return self._write(doc, md)
        return self._write(doc, doc.path) if doc.path else self.save_as(doc)

    def save_as(self, doc: Doc) -> bool:
        if doc.is_pdf:
            self.statusBar().showMessage("PDF는 다른 이름으로 저장할 수 없습니다(보기만).", 4000)
            return False
        if doc.path:
            start = str(doc.path.with_suffix(".md") if doc.is_text else doc.path)
        else:
            start = str(Path(self._last_dir()) / f"{doc.name}.md")
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", start, SAVE_FILTER)
        return self._write(doc, Path(path)) if path else False

    def save_current(self) -> None:
        if self.current:
            self.save(self.current)

    def save_current_as(self) -> None:
        if self.current:
            self.save_as(self.current)

    def save_all(self) -> None:
        for d in [d for d in self.docs if d.dirty]:
            if not self.save(d):
                return

    def _confirm_discard(self, dirty: list[Doc]) -> bool:
        """저장 안 된 문서가 있으면 묻는다. 계속해도 되면 True."""
        if not dirty:
            return True
        names = "\n".join(f"  • {d.name}" for d in dirty)
        r = QMessageBox.question(
            self,
            "저장하지 않은 변경",
            f"저장하지 않은 문서가 있습니다.\n{names}\n\n저장할까요?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Save:
            return all(self.save(d) for d in dirty)
        return True

    def _remove_doc(self, doc: Doc) -> None:
        self._unwatch(doc)
        self.docs.remove(doc)
        self._apply_sort()  # 빈 폴더 칸도 함께 치운다

    def close_checked(self) -> None:
        """[선택닫기] 버튼: 체크한 파일만 닫는다. 체크한 것이 없으면 아무것도 닫지 않고 알려 준다."""
        if not self._checked():
            self.statusBar().showMessage("닫을 파일을 목록에서 체크하세요.", 4000)
            return
        self.close_current()

    def close_current(self) -> None:
        """목록에서 닫기(Ctrl+W): 체크한 파일을 모두 닫는다. 체크한 것이 없으면 지금 보는 파일만."""
        targets = self._checked() or ([self.current] if self.current else [])
        if not targets or not self._confirm_discard([d for d in targets if d.dirty]):
            return
        if self.current in targets:
            self.current = None
        for doc in targets:
            self._remove_doc(doc)
        if not self.docs:
            self.new_file()
        elif self.current is None:
            self.files.setCurrentItem(self.files.leaves()[0])
        if len(targets) > 1:
            self.statusBar().showMessage(f"{len(targets)}개 파일을 목록에서 닫았습니다.", 4000)

    def closeEvent(self, e: QCloseEvent) -> None:  # noqa: N802
        if not self._confirm_discard([d for d in self.docs if d.dirty]):
            e.ignore()
            return
        if self._pdf2md is not None:  # 바꾸는 중인 스레드를 두고 닫으면 프로그램이 죽는다
            self._pdf2md.wait()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        e.accept()

    # ---------- 뷰어 ----------
    def _on_preview_loaded(self, ok: bool) -> None:
        self._preview_ready = ok
        self._on_toc_toggled(self.toc_action.isChecked(), save=False)
        self.render_preview()

    def _on_source_toggled(self, on: bool) -> None:
        self.settings.setValue("showSource", on)
        if not on:
            sizes = self.splitter.sizes()
            if sizes[1] > 0:
                self._sizes_with_source = sizes  # 다시 켤 때 폭을 되돌리려고 기억
            self.editor.setVisible(False)
            self._last_pane = "preview"  # 원본이 숨으면 서식 버튼은 뷰어 선택을 쓴다
            self.preview.setFocus()
        else:
            self.editor.setVisible(True)
            sizes = getattr(self, "_sizes_with_source", None)
            if not sizes:  # 기억이 없으면 원본·뷰어 반반
                total = sum(self.splitter.sizes())
                left = self.splitter.sizes()[0]
                sizes = [left, (total - left) // 2, (total - left) // 2]
            self.splitter.setSizes(sizes)
            self.sync_scroll()
        self.statusBar().showMessage("소스 켬" if on else "소스 끔 — 뷰어만 봅니다 (다시 켜려면 '소스' 버튼)", 3000)

    # ---------- 그림 슬라이드·전체 화면 ----------
    def show_slides(self) -> None:
        d = self.current
        if d is None or not self._preview_ready or d.is_pdf or d.is_text:
            self.statusBar().showMessage("그림 슬라이드는 마크다운 문서에서 볼 수 있습니다.", 4000)
            return

        def opened(n) -> None:
            if n:
                self.preview.setFocus()  # 화살표·Esc가 슬라이드로 가게
                self.statusBar().showMessage(f"그림 {n}장 — ← → 넘기기, Esc 닫기, F11 전체 화면", 5000)
            else:
                self.statusBar().showMessage("이 문서에는 그림이 없습니다.", 4000)

        self.preview_page.runJavaScript("openSlides(0)", 0, opened)

    def _on_fullscreen_toggled(self, on: bool) -> None:
        """뷰어만 화면 가득. 숨긴 칸·창 크기는 끌 때 그대로 돌아온다."""
        panes = (self.menuBar(), self.statusBar(), self.format_bar, self.files, *self.findChildren(QToolBar, "toolbar"))
        if on:
            self._before_full = (self.isMaximized(), self.splitter.saveState(), self.editor.isVisible())
            for w in (*panes, self.editor):
                w.setVisible(False)
            self.showFullScreen()
            self.preview.setFocus()
        else:
            maximized, state, editor_on = getattr(self, "_before_full", (False, None, True))
            for w in panes:
                w.setVisible(True)
            self.editor.setVisible(editor_on)
            self.showMaximized() if maximized else self.showNormal()
            if state is not None:
                self.splitter.restoreState(state)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape and self.fullscreen_action.isChecked():
            self.fullscreen_action.setChecked(False)
            return
        super().keyPressEvent(e)

    def _on_toc_toggled(self, on: bool, save: bool = True) -> None:
        if save:
            self.settings.setValue("toc", on)
        if self._preview_ready:
            self.preview_page.runJavaScript(f"setToc({'true' if on else 'false'});")

    def _on_text_changed(self) -> None:
        self.render_timer.start()

    def render_preview(self) -> None:
        if self.current is not None and self.current.is_pdf:
            self._show_pdf(self.current.path)
            return
        self.viewer_stack.setCurrentWidget(self.preview)
        if not self._preview_ready or self.current is None:
            return
        if self.current.is_text:  # 텍스트 파일은 원본 창에만 — 저장하면 .md가 되어 뷰어에 나온다
            md_name = self.current.path.with_suffix(".md").name
            body = (
                "<div style='color:#59636e;margin-top:40px;text-align:center'>"
                "<p>텍스트 파일(.txt)은 왼쪽 원본 창에만 보입니다.</p>"
                f"<p><b>저장</b>(Ctrl+S)하면 같은 이름의 <b>{html.escape(md_name)}</b>로 저장되고,<br>"
                "그때부터 그 .md 파일이 원본이 되어 이 뷰어에 나타납니다.</p></div>"
            )
        else:
            body = render_any(self.current.qdoc.toPlainText(), self.current.base_dir, self.current.kind)
        lines = self.current.qdoc.blockCount()
        changed = json.dumps(self.current.changed_lines)
        self.preview_page.runJavaScript(f"setContent({json.dumps(body)}, {lines}, {changed});")
        self.sync_scroll()

    def _show_pdf(self, path: Path, reload: bool = False) -> None:
        """뷰어 자리에 PDF 보기를 띄운다. 같은 파일이면 다시 읽지 않는다(보던 쪽 유지)."""
        self.viewer_stack.setCurrentWidget(self.pdf_view)
        if reload or self._pdf_shown != path:
            self._pdf_shown = path
            url = QUrl.fromLocalFile(str(path))
            if reload:  # 같은 주소는 캐시를 쓸 수 있어 뒤에 표를 붙여 새로 읽힌다
                url.setQuery(f"r={int((file_stamp(path) or (0, 0))[0] * 1000)}")
            self.pdf_view.load(url)

    def sync_scroll(self) -> None:
        """편집기 → 뷰어 (동시보기가 켜져 있을 때만)."""
        if self._preview_ready and self.sync_action.isChecked() and not self._from_preview:
            at_end = "true" if self.editor.at_end() else "false"
            self.preview_page.runJavaScript(f"scrollToLine({self.editor.top_line()}, {at_end});")

    def _on_preview_scrolled(self, line: float, at_end: bool) -> None:
        """뷰어 → 편집기 (동시보기가 켜져 있을 때만)."""
        if not self.sync_action.isChecked() or self.current is None:
            return
        bar = self.editor.verticalScrollBar()
        self._from_preview = True
        try:
            if at_end:
                bar.setValue(bar.maximum())
            else:
                block = self.current.qdoc.findBlockByNumber(int(line))
                if block.isValid():
                    bar.setValue(block.firstLineNumber())  # 편집기 스크롤 값은 화면 줄 단위
        finally:
            self._from_preview = False

    def _on_sync_toggled(self, on: bool) -> None:
        self.settings.setValue("syncScroll", on)
        self.statusBar().showMessage("동시보기 켬 — 원본과 뷰어가 함께 움직입니다." if on else "동시보기 끔", 3000)
        if on:
            self.sync_scroll()  # 켜는 순간 뷰어를 편집기 위치로 맞춘다

    # ---------- PDF → 마크다운 ----------
    def convert_pdfs(self) -> None:
        """체크한 PDF(없으면 지금 보는 PDF)를 PDF 옆에 '이름.md'로 바꿔 쓰고 목록에 올린다."""
        if self._pdf2md is not None:
            self.statusBar().showMessage("PDF를 마크다운으로 바꾸는 중입니다. 끝난 뒤 다시 하세요.", 4000)
            return
        checked = self._checked()
        pdfs = [d.path for d in checked if d.is_pdf] or (
            [self.current.path] if self.current is not None and self.current.is_pdf else []
        )
        if not pdfs:
            QMessageBox.information(
                self, "PDF→MD", "바꿀 PDF가 없습니다.\nPDF 파일을 목록에 올려 체크하거나, PDF를 연 채로 다시 누르세요."
            )
            return
        self._pdf2md_total, self._pdf2md_out, self._pdf2md_fail = len(pdfs), [], []
        self.pdf2md_action.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        self.statusBar().showMessage(f"PDF를 마크다운으로 바꾸는 중... (0/{len(pdfs)})")
        worker = PdfToMdWorker(pdfs, self)
        worker.converted.connect(self._on_pdf_converted)
        worker.finished.connect(self._on_pdf2md_finished)
        self._pdf2md = worker
        worker.start()

    def _on_pdf_converted(self, pdf: Path, result) -> None:
        if isinstance(result, Exception):
            self._pdf2md_fail.append(f"{pdf.name}: {result}")
        elif not result.strip():  # 글자를 하나도 못 뽑음(스캔본 등)
            self._pdf2md_fail.append(f"{pdf.name}: 뽑을 글자가 없습니다(스캔한 그림 PDF일 수 있음)")
        else:
            out = pdf2md.md_path_for(pdf, set(self._pdf2md_out))
            try:
                out.write_text(result, encoding="utf-8")
                self._pdf2md_out.append(out)
            except OSError as e:
                self._pdf2md_fail.append(f"{pdf.name}: {e}")
        done = len(self._pdf2md_out) + len(self._pdf2md_fail)
        self.statusBar().showMessage(f"PDF를 마크다운으로 바꾸는 중... ({done}/{self._pdf2md_total})")

    def _on_pdf2md_finished(self) -> None:
        self._pdf2md.deleteLater()
        self._pdf2md = None
        QApplication.restoreOverrideCursor()
        self.pdf2md_action.setEnabled(True)
        if self._pdf2md_out:
            self.open_paths([str(p) for p in self._pdf2md_out])
            names = ", ".join(p.name for p in self._pdf2md_out[:3]) + (" ..." if len(self._pdf2md_out) > 3 else "")
            self.statusBar().showMessage(f"PDF {len(self._pdf2md_out)}개를 마크다운으로 바꿨습니다: {names}", 8000)
        else:
            self.statusBar().clearMessage()
        if self._pdf2md_fail:
            QMessageBox.warning(self, "PDF→MD", "바꾸지 못한 PDF가 있습니다.\n\n" + "\n".join(self._pdf2md_fail))

    # ---------- 인쇄·PDF ----------
    def _checked_docs(self, what: str) -> list[Doc]:
        """체크한 문서. 없으면 지금 보는 문서만 할지 묻는다."""
        checked = self._checked()
        if not checked and self.current is not None:
            r = QMessageBox.question(
                self, what, f"체크한 파일이 없습니다.\n지금 보고 있는 문서만 {what}할까요?"
            )
            checked = [self.current] if r == QMessageBox.StandardButton.Yes else []
        pdfs = [d for d in checked if d.is_pdf]
        if pdfs:  # PDF는 이미 인쇄용 문서라 여기서 다시 만들지 않는다
            names = "\n".join(f"  • {d.name}" for d in pdfs[:10]) + ("\n  ..." if len(pdfs) > 10 else "")
            QMessageBox.information(
                self, what, f"PDF 파일은 {what}에서 뺍니다(PDF 보기 프로그램에서 인쇄하세요).\n{names}"
            )
        return [d for d in checked if not d.is_pdf]

    def _load_offscreen(self, docs: list[Doc], on_loaded) -> QWebEngineView:
        """화면에 띄우지 않는 뷰에 인쇄용 HTML을 올리고, 다 읽으면 on_loaded(view, ok)."""
        view = QWebEngineView()
        self._print_jobs.append(view)
        html = print_document([(d.name, d.qdoc.toPlainText(), d.base_dir, d.kind) for d in docs])
        # setHtml은 2MB를 넘으면 조용히 실패하므로 임시 파일로 써서 읽힌다
        fd, tmp = tempfile.mkstemp(prefix="mdeditor-", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(html)
        view.setProperty("tmpfile", tmp)
        view.loadFinished.connect(lambda ok: on_loaded(view, ok))
        view.load(QUrl.fromLocalFile(tmp))
        return view

    def _done_offscreen(self, view: QWebEngineView, msg: str | None = None) -> None:
        if view in self._print_jobs:
            self._print_jobs.remove(view)
        if tmp := view.property("tmpfile"):
            Path(tmp).unlink(missing_ok=True)
        view.deleteLater()
        if msg:
            self.statusBar().showMessage(msg, 8000)

    def save_pdf(self) -> None:
        docs = self._checked_docs("PDF로 저장")
        if not docs:
            return
        if len(docs) == 1:
            stem = docs[0].path.stem if docs[0].path else docs[0].name
            path, _ = QFileDialog.getSaveFileName(
                self, "PDF로 저장", str(Path(self._last_dir()) / f"{stem}.pdf"), "PDF (*.pdf)"
            )
            if not path:
                return
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self.export_pdfs([(docs[0], path)])
            return

        # 여러 개: 저장할 폴더만 고르면 파일마다 '원래 파일 이름.pdf'로 따로 저장
        folder = QFileDialog.getExistingDirectory(self, f"PDF {len(docs)}개를 저장할 폴더", self._last_dir())
        if not folder:
            return
        jobs = list(zip(docs, pdf_names(docs, Path(folder))))
        exists = [p for _, p in jobs if Path(p).exists()]
        if exists:
            names = "\n".join(f"  • {Path(p).name}" for p in exists[:10]) + ("\n  ..." if len(exists) > 10 else "")
            r = QMessageBox.question(self, "PDF로 저장", f"같은 이름의 PDF가 이미 있습니다.\n{names}\n\n덮어쓸까요?")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.export_pdfs(jobs)

    def export_pdfs(self, jobs: list[tuple[Doc, str]]) -> None:
        """문서마다 PDF 하나씩, 차례로 저장. 글자가 살아 있는 PDF라 검색·복사가 된다."""
        layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(15, 15, 15, 15),
            QPageLayout.Unit.Millimeter,
        )
        total, failed = len(jobs), []
        queue = list(jobs)
        self.settings.setValue("lastDir", str(Path(jobs[0][1]).parent))

        def next_job() -> None:
            if not queue:
                done = total - len(failed)
                where = jobs[0][1] if total == 1 else str(Path(jobs[0][1]).parent)
                self.statusBar().showMessage(f"PDF {done}/{total}개를 저장했습니다: {where}", 10000)
                if failed:
                    QMessageBox.warning(
                        self,
                        "PDF 저장 실패",
                        "다음 파일을 저장하지 못했습니다.\n"
                        + "\n".join(f"  • {p}" for p in failed)
                        + "\n\n같은 PDF가 다른 프로그램에서 열려 있지 않은지 확인하세요.",
                    )
                return
            doc, path = queue.pop(0)
            self.statusBar().showMessage(f"PDF로 저장하는 중... ({total - len(queue)}/{total}) {doc.name}")

            def loaded(view: QWebEngineView, ok: bool) -> None:
                if not ok:
                    failed.append(path)
                    self._done_offscreen(view)
                    next_job()
                    return

                def finished(file_path: str, success: bool) -> None:
                    if not success:
                        failed.append(file_path)
                    self._done_offscreen(view)
                    next_job()

                view.page().pdfPrintingFinished.connect(finished)
                view.page().printToPdf(path, layout)

            self._load_offscreen([doc], loaded)

        next_job()

    def print_checked(self) -> None:
        checked = self._checked_docs("인쇄")
        if not checked:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle(f"인쇄 — {len(checked)}개 파일")
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        self.print_docs(checked, printer)

    def print_docs(self, checked: list[Doc], printer: QPrinter) -> None:
        self._printer = printer  # 인쇄가 끝날 때까지 살려 둔다
        self.statusBar().showMessage(f"{len(checked)}개 파일을 인쇄하는 중...")

        def loaded(view: QWebEngineView, ok: bool) -> None:
            if not ok:
                self._done_offscreen(view, "인쇄에 실패했습니다.")
                return
            view.printFinished.connect(
                lambda success: self._done_offscreen(
                    view, f"{len(checked)}개 파일을 인쇄했습니다." if success else "인쇄에 실패했습니다."
                )
            )
            view.print(printer)

        self._load_offscreen(checked, loaded)

    # ---------- 설정 ----------
    def _last_dir(self) -> str:
        return str(self.settings.value("lastDir", str(Path.home() / "Documents")))

    def _restore(self) -> None:
        if g := self.settings.value("geometry"):
            self.restoreGeometry(g)
        else:
            self.resize(1400, 850)
        if s := self.settings.value("splitter"):
            self.splitter.restoreState(s)

    # ---------- 버전·변경 이력 ----------
    def show_changelog(self, text: str | None = None, title: str = "새 기능·변경 이력") -> None:
        """변경 이력을 뷰어와 같은 모양으로 보여 준다(최근 두 버전까지). text를 주면 그 부분만."""
        text = changelog.latest(changelog.read_changelog(), __version__) if text is None else text
        if not text.strip():
            QMessageBox.information(self, title, f"mdEditor v{__version__}\n변경 이력 파일을 찾지 못했습니다.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} — mdEditor v{__version__}")
        dlg.resize(780, 640)
        box = QVBoxLayout(dlg)
        view = QWebEngineView(dlg)
        view.setPage(PreviewPage(view))  # 이력 속 링크는 기본 브라우저로
        view.setHtml(page(render_any(text, None, "md"), title=title), QUrl("about:blank"))
        box.addWidget(view)
        buttons = QDialogButtonBox()
        buttons.addButton("닫기", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.rejected.connect(dlg.reject)
        box.addWidget(buttons)
        dlg.exec()

    def show_whats_new(self) -> None:
        """새 버전으로 처음 켰을 때 한 번: 지난번에 쓰던 버전 다음부터 바뀐 내용."""
        last = self.settings.value("lastSeenVersion", None)
        if last == __version__:
            return
        self.settings.setValue("lastSeenVersion", __version__)
        text = changelog.changes_since(changelog.read_changelog(), last, __version__)
        if text:
            self.show_changelog(text, "새 버전에서 바뀐 내용")

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "mdEditor 정보",
            f"<h3>mdEditor v{__version__}</h3>"
            "<p>Windows용 마크다운 편집기 — [파일 목록 | 원본 | 뷰어]</p>"
            "<p><a href='https://github.com/KimJin777/markDown'>github.com/KimJin777/markDown</a></p>"
            "<p>업데이트: <code>uv tool upgrade markdown-editor</code></p>"
            "<p>라이선스: GNU AGPL v3.0 이상</p>",
        )

    # ---------- 바탕화면 바로가기 ----------
    def make_shortcut(self, first_run: bool = False) -> None:
        """처음 실행할 때 한 번 자동으로, 또는 메뉴에서 직접 바탕화면에 mdEditor 바로가기를 만든다."""
        if first_run and self.settings.value("shortcutDone", False, type=bool):
            return
        target = shortcut.launcher_path()
        if target is None:  # 개발용 실행(.venv)이면 만들지 않는다
            if not first_run:
                QMessageBox.information(self, "바로가기", "개발용 실행에서는 바로가기를 만들지 않습니다.\n설치한 mdEditor(또는 실행 파일)로 실행해 주세요.")
            return
        desktop = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation))
        if first_run and (desktop / shortcut.SHORTCUT_NAME).exists():
            self.settings.setValue("shortcutDone", True)
            return
        try:
            lnk = shortcut.create(desktop, target, ICON if ICON.exists() else None)
        except Exception as e:  # noqa: BLE001 — 바로가기 실패로 프로그램이 멈추면 안 된다
            self.settings.setValue("shortcutDone", True)  # 매번 다시 시도하지 않는다(메뉴로 다시 만들 수 있음)
            self.statusBar().showMessage(f"바탕화면 바로가기를 만들지 못했습니다: {e}", 8000)
            return
        self.settings.setValue("shortcutDone", True)
        self.statusBar().showMessage(f"바탕화면에 바로가기를 만들었습니다: {lnk}", 8000)

    # ---------- .md 파일 연결·한 번만 실행 ----------
    def register_file_assoc(self) -> None:
        """mdEditor를 .md 파일의 '연결 프로그램'에 올리고, Windows의 '항상 이 앱으로 열기' 고르는 창을 띄운다."""
        title = ".md 파일 연결"
        exe = shortcut.launcher_path()
        if exe is None:
            QMessageBox.information(self, title, "개발용 실행에서는 등록하지 않습니다.\n설치한 mdEditor(또는 실행 파일)로 실행해 주세요.")
            return
        try:
            fileassoc.register(exe, ICON if ICON.exists() else None)
        except OSError as e:
            QMessageBox.warning(self, title, f"등록하지 못했습니다.\n{e}")
            return
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "mdEditor를 .md 파일의 '연결 프로그램'에 올렸습니다.\n\n"
            "마지막으로 Windows에서 한 번만 고르면 됩니다(Windows가 프로그램이 직접 바꾸는 것을 막아 둠).\n"
            "[지금 고르기]를 누르면 나오는 창에서 mdEditor를 고르고 '항상'을 누르세요."
        )
        pick = box.addButton("지금 고르기", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is pick:
            self._pick_default_app()

    def _pick_default_app(self) -> None:
        """'이 파일을 어떻게 여시겠어요?' 창. .md 파일이 하나 있어야 해서, 보던 .md가 없으면 임시 파일을 쓴다."""
        d = self.current
        if d is not None and d.path and d.path.suffix.lower() == ".md" and d.path.exists():
            sample = d.path
        else:
            sample = Path(tempfile.gettempdir()) / "mdEditor 연결 고르기.md"
            sample.write_text("# mdEditor\n", encoding="utf-8")
        try:
            subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", str(sample)])
        except OSError:
            QDesktopServices.openUrl(QUrl("ms-settings:defaultapps"))  # 설정 → 앱 → 기본 앱

    def unregister_file_assoc(self) -> None:
        try:
            fileassoc.unregister((shortcut.launcher_path() or Path("mdEditor.exe")).name)
        except OSError as e:
            QMessageBox.warning(self, ".md 파일 연결", f"해제하지 못했습니다.\n{e}")
            return
        QMessageBox.information(
            self,
            ".md 파일 연결",
            "mdEditor를 .md 파일의 '연결 프로그램'에서 뺐습니다.\n"
            "기본 앱으로 골라 두었다면 Windows 설정 → 앱 → 기본 앱에서 다른 프로그램을 고르세요.",
        )

    def request_feature(self) -> None:
        """도움말 → 기능 추가 요청: 저장소의 GitHub 이슈 쓰기 화면을 연다(따로 DB 없이 요청이 한곳에 모임)."""
        r = QMessageBox.information(
            self,
            "기능 추가 요청",
            "웹 브라우저에서 mdEditor 저장소(GitHub)의 '새 이슈' 쓰기 화면을 엽니다.\n"
            "제목과 내용을 적고 [Submit new issue]를 누르면 요청이 접수됩니다.\n"
            "(GitHub 계정으로 로그인해야 합니다. 버전 정보는 미리 채워 둡니다.)",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )
        if r == QMessageBox.StandardButton.Ok:
            QDesktopServices.openUrl(QUrl(feature_request_url(__version__)))

    def receive_paths(self, paths: list[str]) -> None:
        """다른 곳에서 mdEditor를 또 실행함(.md 더블클릭 등): 새 창 대신 이 창에 올리고 앞으로 나온다."""
        if paths:
            self.open_paths(paths)
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("mdEditor")
    app.setApplicationVersion(__version__)
    if sys.platform == "win32":  # 작업 표시줄에 파이썬 아이콘 대신 mdEditor 아이콘이 보이게
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KimJin777.mdEditor")
        except (AttributeError, OSError):
            pass
    app.setWindowIcon(QIcon(str(ICON)))
    paths = [str(Path(a).resolve()) for a in sys.argv[1:]]  # .md 더블클릭·실행 파일에 끌어다 놓기
    if single.send_to_running(paths):  # 이미 켜져 있으면 그 창에 넘기고 끝낸다
        sys.exit(0)
    win = MainWindow()
    win.show()
    win._single = single.listen(win.receive_paths, parent=win)  # 다음에 실행되는 mdEditor가 넘기는 파일을 받는다
    if paths:
        win.open_paths(paths)
    QTimer.singleShot(1500, lambda: win.make_shortcut(first_run=True))  # 창이 뜬 뒤에
    QTimer.singleShot(2500, win.show_whats_new)  # 새 버전으로 처음 켰으면 바뀐 내용을 보여 준다
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
