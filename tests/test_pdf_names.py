from pathlib import Path
from types import SimpleNamespace

from mdeditor.app import pdf_names


def doc(path=None, name=""):
    return SimpleNamespace(path=Path(path) if path else None, name=name)


def test_pdf_named_after_file_and_dedup(tmp_path: Path):
    docs = [doc("a/보고서.md"), doc("b/보고서.md"), doc(name="새 문서 1"), doc("c/x:y.md")]
    names = [Path(p).name for p in pdf_names(docs, tmp_path)]
    assert names == ["보고서.pdf", "보고서 (2).pdf", "새 문서 1.pdf", "x_y.pdf"]
    assert all(Path(p).parent == tmp_path for p in pdf_names(docs, tmp_path))
