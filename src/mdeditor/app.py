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

from PySide6.QtCore import QMarginsF, QPoint, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QFont,
    QKeySequence,
    QPageLayout,
    QPageSize,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWebEngineCore import QWebEnginePage
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
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mdeditor import __version__
from mdeditor.fmt import locate_in_source, py_to_q, q_to_py, set_heading, set_size, toggle_wrap
from mdeditor.render import page, print_document, render_body

MD_SUFFIXES = {".md", ".markdown", ".mdown", ".txt"}
MD_FILTER = "마크다운 (*.md *.markdown *.mdown *.txt);;모든 파일 (*)"

# 뷰어 껍데기 페이지: 본문만 갈아 끼워 깜박임·스크롤 튐을 막는다
PREVIEW_JS = """
<script>
let quietUntil = 0;  // 프로그램이 움직인 스크롤은 편집기로 되돌려 보내지 않는다(서로 밀고 당기기 방지)
const hush = () => { quietUntil = Date.now() + 200; };
const blocks = () => Array.from(document.querySelectorAll('#content [data-line]'))
  .map(el => ({ n: +el.dataset.line, y: el.getBoundingClientRect().top + window.scrollY }));
function setContent(html) { hush(); document.getElementById('content').innerHTML = html; }
function scrollToLine(line, atEnd) {
  hush();
  if (atEnd) { window.scrollTo(0, document.body.scrollHeight); return; }
  const bs = blocks();
  if (!bs.length || line <= 0) { window.scrollTo(0, 0); return; }
  let prev = null, next = null;
  for (const b of bs) { if (b.n <= line) prev = b; else { next = b; break; } }
  let y = prev ? prev.y : 0;
  if (prev && next && next.n > prev.n) y += (next.y - prev.y) * (line - prev.n) / (next.n - prev.n);
  window.scrollTo(0, Math.max(0, y - 8));
}
function topLine() {
  const bs = blocks(), y = window.scrollY + 8;
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

    @property
    def name(self) -> str:
        return self.path.name if self.path else f"새 문서 {self.untitled_no}"

    @property
    def is_text(self) -> bool:
        """일반 텍스트 파일(.txt): 원본 창에만 보이고, 저장하면 같은 이름의 .md가 된다."""
        return bool(self.path) and self.path.suffix.lower() == ".txt"

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

        self.files = FileList()
        self.editor = Editor()
        self.preview = QWebEngineView()
        self.preview_page = PreviewPage(self.preview)
        self.preview.setPage(self.preview_page)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setStyleSheet("QSplitter::handle { background: #d0d7de; } QSplitter::handle:hover { background: #8c959f; }")
        right = QWidget()  # 오른쪽: 서식 버튼 줄 + 뷰어
        right_box = QVBoxLayout(right)
        right_box.setContentsMargins(0, 0, 0, 0)
        right_box.setSpacing(0)
        right_box.addWidget(self._build_format_bar())
        right_box.addWidget(self.preview)
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
        f.addSeparator()
        a_print = act(f, "체크한 파일 인쇄...", self.print_checked, QKeySequence.StandardKey.Print)
        a_pdf = act(f, "체크한 파일 PDF로 저장...", self.save_pdf, "Ctrl+Shift+P")
        f.addSeparator()
        act(f, "끝내기", self.close, "Ctrl+Q")

        v = self.menuBar().addMenu("보기(&V)")
        v.addAction(self.sync_action)

        s = self.menuBar().addMenu("선택(&S)")
        act(s, "모두 체크", lambda: self._check_all(True), "Ctrl+Shift+A")
        act(s, "모두 체크 해제", lambda: self._check_all(False))

        bar = self.addToolBar("도구")
        bar.setObjectName("toolbar")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for a, label in (
            (a_new, "새 파일"),
            (a_open, "파일 올리기"),
            (a_save, "저장"),
            (None, None),
            (a_print, "인쇄"),
            (a_pdf, "PDF로 저장"),
        ):
            if a is None:
                bar.addSeparator()
            else:
                bar.addAction(a)
                bar.widgetForAction(a).setText(label)

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
        if self.current is None:
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
            self.setWindowTitle(f"{doc.name}{' *' if doc.dirty else ''} — markDown v{__version__}")

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
        self._refresh_item(doc)
        self.files.setCurrentItem(item)

    def _on_item_changed(self, item: QListWidgetItem | None, _prev) -> None:
        if item is None:
            return
        doc: Doc = item.data(Qt.ItemDataRole.UserRole)
        self.current = doc
        self.editor.setDocument(doc.qdoc)
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
        self.st_kind.setText("텍스트(.txt) → 저장 시 .md" if d.is_text else "마크다운")
        self.st_enc.setText(f"{d.encoding} · {'CRLF' if d.newline == chr(13) + chr(10) else 'LF'}")
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
                text, enc, newline = read_text(f)
            except OSError as e:
                QMessageBox.warning(self, "열기 실패", f"{f}\n{e}")
                continue
            doc = Doc(path=f, saved_text=text, encoding=enc, newline=newline)
            doc.qdoc.setPlainText(text)
            doc.qdoc.setModified(False)
            self._add_doc(doc)
            last = doc
        if last and (item := self._item_of(last)):
            self.files.setCurrentItem(item)
        self.statusBar().showMessage(f"{len(files)}개 파일을 올렸습니다.", 4000)

    # ---------- 저장·닫기 ----------
    def _write(self, doc: Doc, path: Path) -> bool:
        text = doc.qdoc.toPlainText()
        try:
            path.write_text(text, encoding="utf-8", newline=doc.newline)
        except OSError as e:
            QMessageBox.warning(self, "저장 실패", f"{path}\n{e}")
            return False
        doc.path, doc.saved_text, doc.encoding = path.resolve(), text, "UTF-8"
        self.settings.setValue("lastDir", str(path.parent))
        self._refresh_item(doc)
        if doc is self.current:
            self.render_preview()  # 기준 폴더·종류(.txt→.md)가 바뀌었을 수 있다
            self._update_status()
        self.statusBar().showMessage(f"저장했습니다: {path}", 4000)
        return True

    def save(self, doc: Doc) -> bool:
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
        if doc.path:
            start = str(doc.path.with_suffix(".md") if doc.is_text else doc.path)
        else:
            start = str(Path(self._last_dir()) / f"{doc.name}.md")
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", start, MD_FILTER)
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
        item = self._item_of(doc)
        if item:
            self.files.takeItem(self.files.row(item))
        self.docs.remove(doc)

    def close_current(self) -> None:
        """목록에서 닫기: 체크한 파일을 모두 닫는다. 체크한 것이 없으면 지금 보는 파일만."""
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
        self.render_preview()

    def _on_text_changed(self) -> None:
        self.render_timer.start()

    def render_preview(self) -> None:
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
            body = render_body(self.current.qdoc.toPlainText(), self.current.base_dir)
        self.preview_page.runJavaScript(f"setContent({json.dumps(body)});")
        self.sync_scroll()

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
        if checked or self.current is None:
            return checked
        r = QMessageBox.question(
            self, what, f"체크한 파일이 없습니다.\n지금 보고 있는 문서만 {what}할까요?"
        )
        return [self.current] if r == QMessageBox.StandardButton.Yes else []

    def _load_offscreen(self, docs: list[Doc], on_loaded) -> QWebEngineView:
        """화면에 띄우지 않는 뷰에 인쇄용 HTML을 올리고, 다 읽으면 on_loaded(view, ok)."""
        view = QWebEngineView()
        self._print_jobs.append(view)
        html = print_document([(d.name, d.qdoc.toPlainText(), d.base_dir) for d in docs])
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


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("markDown")
    app.setApplicationVersion(__version__)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:  # 탐색기에서 파일을 끌어다 실행 파일에 놓은 경우
        win.open_paths(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
