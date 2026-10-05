"""markDown 편집기 — [파일 탐색기 | 편집기 | 뷰어] 세 칸, 칸 사이 기둥으로 크기 조절."""

from __future__ import annotations

import html
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QMarginsF, QPoint, QSettings, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPageLayout,
    QPageSize,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextDocumentLayout,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mdeditor import __version__
from mdeditor.fmt import locate_in_source, py_to_q, q_to_py, set_heading, set_size, toggle_wrap
from mdeditor import shortcut
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
</style>
<nav id="toc"></nav>
<script>
let quietUntil = 0;  // 프로그램이 움직인 스크롤은 편집기로 되돌려 보내지 않는다(서로 밀고 당기기 방지)
const hush = () => { quietUntil = Date.now() + 200; };
const blocks = () => Array.from(document.querySelectorAll('#content [data-line]'))
  .map(el => ({ n: +el.dataset.line, y: el.getBoundingClientRect().top + window.scrollY }));
let totalLines = 1;  // 원본 줄 수(줄 표시가 없는 보기에서 비율 스크롤에 씀)
function setContent(html, lines) { hush(); totalLines = lines || 1; document.getElementById('content').innerHTML = html; buildToc(); }
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


class FileList(QListWidget):
    """올린 파일 목록. 체크한 파일을 한꺼번에 인쇄한다. 파일·폴더를 끌어다 놓을 수 있다."""

    filesDropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)
        self.setToolTip("파일·폴더를 여기로 끌어다 놓으면 올라갑니다.\n체크한 파일은 한꺼번에 인쇄됩니다.")

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

    def javaScriptConsoleMessage(self, level, message: str, line: int, source: str) -> None:  # noqa: N802
        if message.startswith("__mdscroll__ "):
            _, ln, at_end = message.split()
            self.scrolled.emit(float(ln), at_end == "true")

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

        self.sort_mode = str(self.settings.value("sortMode", "added"))
        self.sort_reverse = self.settings.value("sortReverse", False, type=bool)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setStyleSheet("QSplitter::handle { background: #d0d7de; } QSplitter::handle:hover { background: #8c959f; }")
        right = QWidget()  # 오른쪽: 서식 버튼 줄 + 뷰어
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(0)
        right_box.addWidget(self._build_format_bar())
        right_box.addWidget(self.viewer_stack)
        for w in (self.files, self.editor, right):
            self.splitter.addWidget(w)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setSizes([200, 600, 600])
        self.setCentralWidget(self.splitter)

        self.render_timer = QTimer(self, singleShot=True, interval=150)
        self.render_timer.timeout.connect(self.render_preview)

        self.files.currentItemChanged.connect(self._on_item_changed)
        self.files.filesDropped.connect(self.open_paths)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.verticalScrollBar().valueChanged.connect(self.sync_scroll)
        self.preview_page.openMarkdown.connect(lambda p: self.open_paths([p]))
        self.preview_page.scrolled.connect(self._on_preview_scrolled)
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
        f.addSeparator()
        act(f, "바탕화면에 바로가기 만들기", lambda: self.make_shortcut())
        f.addSeparator()
        act(f, "끝내기", self.close, "Ctrl+Q")

        v = self.menuBar().addMenu("보기(&V)")
        v.addAction(self.source_action)
        v.addAction(self.toc_action)
        v.addAction(self.sync_action)

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

        bar = self.addToolBar("도구")
        bar.setObjectName("toolbar")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for a, label in (
            (a_new, "새 파일"),
            (a_open, "파일 올리기"),
            (self.select_all_action, "모두선택"),
            (self.close_checked_action, "선택닫기"),
            ("sort", None),
            (a_save, "저장"),
            (None, None),
            (a_print, "인쇄"),
            (a_pdf, "PDF로 저장"),
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
    def _item_of(self, doc: Doc) -> QListWidgetItem | None:
        for i in range(self.files.count()):
            item = self.files.item(i)
            if item.data(Qt.ItemDataRole.UserRole) is doc:
                return item
        return None

    def _refresh_item(self, doc: Doc) -> None:
        item = self._item_of(doc)
        if item:
            item.setText(("● " if doc.dirty else "") + doc.name)
            item.setToolTip(str(doc.path) if doc.path else "저장하지 않은 새 문서")
        if doc is self.current:
            self.setWindowTitle(f"{doc.name}{' *' if doc.dirty else ''} — mdEditor v{__version__}")

    def _add_doc(self, doc: Doc) -> None:
        doc.qdoc.setParent(self)  # 목록에서 닫아도 편집기가 잠시 쥐고 있을 수 있어 창이 소유
        doc.qdoc.setDocumentLayout(QPlainTextDocumentLayout(doc.qdoc))
        doc.qdoc.setDefaultFont(self.editor.font())
        doc.qdoc.contentsChanged.connect(lambda d=doc: self._refresh_item(d))
        self.docs.append(doc)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, doc)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.files.addItem(item)
        self._watch(doc)
        self._refresh_item(doc)
        self._apply_sort()
        self.files.setCurrentItem(item)

    def _on_item_changed(self, item: QListWidgetItem | None, _prev) -> None:
        if item is None:
            return
        doc: Doc = item.data(Qt.ItemDataRole.UserRole)
        self.current = doc
        self.editor.setDocument(doc.qdoc)
        self.editor.setReadOnly(doc.is_pdf)
        self.editor.setPlaceholderText(
            "PDF 파일은 오른쪽 뷰어에서 보기만 합니다(원본 편집 없음)." if doc.is_pdf else ""
        )
        self.editor.setFocus()
        self._refresh_item(doc)
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
        for i in range(self.files.count()):
            self.files.item(i).setCheckState(state)
        self._sync_select_all()

    def _all_checked(self) -> bool:
        n = self.files.count()
        return n > 0 and all(self.files.item(i).checkState() == Qt.CheckState.Checked for i in range(n))

    def _toggle_check_all(self) -> None:
        on = not self._all_checked()
        self._check_all(on)
        self.statusBar().showMessage(f"{self.files.count()}개 파일을 모두 체크했습니다." if on else "체크를 모두 풀었습니다.", 3000)

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
        """목록 칸을 정렬 기준대로 다시 늘어놓는다(체크·지금 보는 파일은 그대로)."""
        order = sort_docs(self.docs, self.sort_mode, self.sort_reverse)
        if [self.files.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.files.count())] == order:
            return
        cur = self.files.currentItem()
        self.files.blockSignals(True)
        try:
            taken = [self.files.takeItem(0) for _ in range(self.files.count())]
            by_doc = {id(it.data(Qt.ItemDataRole.UserRole)): it for it in taken}
            for d in order:
                self.files.addItem(by_doc[id(d)])
            if cur is not None:
                self.files.setCurrentItem(cur)
        finally:
            self.files.blockSignals(False)

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
        for p in map(Path, paths):
            if p.is_dir():
                files += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in MD_SUFFIXES)
            elif p.is_file():
                files.append(p)
        if not files:
            return
        self.settings.setValue("lastDir", str(files[-1].parent))
        # 아무것도 쓰지 않은 첫 새 문서는 자리만 차지하므로 치운다
        if len(self.docs) == 1 and self.docs[0].path is None and not self.docs[0].qdoc.toPlainText():
            self._remove_doc(self.docs[0])
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
        stamp = file_stamp(doc.path)
        if stamp is None:  # 지워졌거나 옮겨졌다(목록에는 남겨 둔다 — 저장하면 다시 생긴다)
            self.statusBar().showMessage(f"파일이 지워졌거나 옮겨졌습니다: {doc.path}", 8000)
            return
        self._watch(doc)  # 지우고 새로 쓰는 방식으로 저장하는 프로그램이 있어 다시 건다
        if stamp == doc.stamp:
            return
        doc.stamp = stamp
        if doc.is_pdf:
            if doc is self.current:
                self._show_pdf(doc.path, reload=True)
            self.statusBar().showMessage(f"바뀐 PDF를 다시 읽었습니다: {doc.name}", 5000)
            return
        try:
            text, enc, newline = read_text(doc.path)
        except OSError:
            return
        if text == doc.saved_text:  # 시각만 바뀜(내용 같음)
            return
        if doc.dirty:
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
                return
        self._replace_text(doc, text, enc, newline)
        self._apply_sort()  # '고친 시각' 정렬이면 자리가 바뀐다
        self.statusBar().showMessage(f"바뀐 파일을 다시 읽었습니다: {doc.name}", 5000)

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
        item = self._item_of(doc)
        if item:
            self.files.takeItem(self.files.row(item))
        self.docs.remove(doc)
        self._sync_select_all()

    def close_checked(self) -> None:
        """[선택닫기] 버튼: 체크한 파일만 닫는다. 체크한 것이 없으면 아무것도 닫지 않고 알려 준다."""
        if not any(self.files.item(i).checkState() == Qt.CheckState.Checked for i in range(self.files.count())):
            self.statusBar().showMessage("닫을 파일을 목록에서 체크하세요.", 4000)
            return
        self.close_current()

    def close_current(self) -> None:
        """목록에서 닫기(Ctrl+W): 체크한 파일을 모두 닫는다. 체크한 것이 없으면 지금 보는 파일만."""
        targets = [
            self.files.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.files.count())
            if self.files.item(i).checkState() == Qt.CheckState.Checked
        ] or ([self.current] if self.current else [])
        if not targets or not self._confirm_discard([d for d in targets if d.dirty]):
            return
        if self.current in targets:
            self.current = None
        for doc in targets:
            self._remove_doc(doc)
        if not self.docs:
            self.new_file()
        elif self.current is None:
            self.files.setCurrentRow(0)
        if len(targets) > 1:
            self.statusBar().showMessage(f"{len(targets)}개 파일을 목록에서 닫았습니다.", 4000)

    def closeEvent(self, e: QCloseEvent) -> None:  # noqa: N802
        if not self._confirm_discard([d for d in self.docs if d.dirty]):
            e.ignore()
            return
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
        self.preview_page.runJavaScript(f"setContent({json.dumps(body)}, {lines});")
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

    # ---------- 인쇄·PDF ----------
    def _checked_docs(self, what: str) -> list[Doc]:
        """체크한 문서. 없으면 지금 보는 문서만 할지 묻는다."""
        checked = [
            self.files.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.files.count())
            if self.files.item(i).checkState() == Qt.CheckState.Checked
        ]
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
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:  # 탐색기에서 파일을 끌어다 실행 파일에 놓은 경우
        win.open_paths(sys.argv[1:])
    QTimer.singleShot(1500, lambda: win.make_shortcut(first_run=True))  # 창이 뜬 뒤에
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
