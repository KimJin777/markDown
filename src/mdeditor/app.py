"""markDown 편집기 — [파일 탐색기 | 편집기 | 뷰어] 세 칸, 칸 사이 기둥으로 크기 조절."""

from __future__ import annotations

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
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextDocumentLayout,
    QPlainTextEdit,
    QSplitter,
    QWidget,
)

from mdeditor.render import page, print_document, render_body

MD_SUFFIXES = {".md", ".markdown", ".mdown", ".txt"}
MD_FILTER = "마크다운 (*.md *.markdown *.mdown *.txt);;모든 파일 (*)"

# 뷰어 껍데기 페이지: 본문만 갈아 끼워 깜박임·스크롤 튐을 막는다
PREVIEW_JS = """
<script>
function setContent(html) { document.getElementById('content').innerHTML = html; }
function scrollToLine(line, atEnd) {
  if (atEnd) { window.scrollTo(0, document.body.scrollHeight); return; }
  const els = Array.from(document.querySelectorAll('#content [data-line]'));
  if (!els.length || line <= 0) { window.scrollTo(0, 0); return; }
  let prev = null, next = null;
  for (const el of els) {
    const n = +el.dataset.line;
    if (n <= line) prev = { n, el }; else { next = { n, el }; break; }
  }
  const top = e => e.el.getBoundingClientRect().top + window.scrollY;
  let y = prev ? top(prev) : 0;
  if (prev && next && next.n > prev.n) y += (top(next) - top(prev)) * (line - prev.n) / (next.n - prev.n);
  window.scrollTo(0, Math.max(0, y - 8));
}
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


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp949", errors="replace")  # 예전 한글 메모장 파일


@dataclass
class Doc:
    path: Path | None
    untitled_no: int = 0
    qdoc: QTextDocument = field(default_factory=QTextDocument)
    saved_text: str = ""

    @property
    def name(self) -> str:
        return self.path.name if self.path else f"새 문서 {self.untitled_no}"

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

        self.files = FileList()
        self.editor = Editor()
        self.preview = QWebEngineView()
        self.preview_page = PreviewPage(self.preview)
        self.preview.setPage(self.preview_page)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setStyleSheet("QSplitter::handle { background: #d0d7de; } QSplitter::handle:hover { background: #8c959f; }")
        for w in (self.files, self.editor, self.preview):
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
        self.preview.loadFinished.connect(self._on_preview_loaded)

        self._build_menu()
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
        act(f, "목록에서 닫기", self.close_current, "Ctrl+W")
        f.addSeparator()
        a_print = act(f, "체크한 파일 인쇄...", self.print_checked, QKeySequence.StandardKey.Print)
        a_pdf = act(f, "체크한 파일 PDF로 저장...", self.save_pdf, "Ctrl+Shift+P")
        f.addSeparator()
        act(f, "끝내기", self.close, "Ctrl+Q")

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
            self.setWindowTitle(f"{doc.name}{' *' if doc.dirty else ''} — markDown")

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
                files += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in MD_SUFFIXES - {".txt"})
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
                text = read_text(f)
            except OSError as e:
                QMessageBox.warning(self, "열기 실패", f"{f}\n{e}")
                continue
            doc = Doc(path=f, saved_text=text)
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
            path.write_text(text, encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "저장 실패", f"{path}\n{e}")
            return False
        doc.path, doc.saved_text = path.resolve(), text
        self.settings.setValue("lastDir", str(path.parent))
        self._refresh_item(doc)
        if doc is self.current:
            self.render_preview()  # 기준 폴더가 바뀌었을 수 있다(그림 경로)
        self.statusBar().showMessage(f"저장했습니다: {path}", 4000)
        return True

    def save(self, doc: Doc) -> bool:
        return self._write(doc, doc.path) if doc.path else self.save_as(doc)

    def save_as(self, doc: Doc) -> bool:
        start = str(doc.path) if doc.path else str(Path(self._last_dir()) / f"{doc.name}.md")
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
        doc = self.current
        if doc is None or not self._confirm_discard([doc] if doc.dirty else []):
            return
        self.current = None
        self._remove_doc(doc)
        if not self.docs:
            self.new_file()

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
        body = render_body(self.current.qdoc.toPlainText(), self.current.base_dir)
        self.preview_page.runJavaScript(f"setContent({json.dumps(body)});")
        self.sync_scroll()

    def sync_scroll(self) -> None:
        if self._preview_ready:
            at_end = "true" if self.editor.at_end() else "false"
            self.preview_page.runJavaScript(f"scrollToLine({self.editor.top_line()}, {at_end});")

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
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1:  # 탐색기에서 파일을 끌어다 실행 파일에 놓은 경우
        win.open_paths(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
