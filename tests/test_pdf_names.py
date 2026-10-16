from pathlib import Path
from types import SimpleNamespace

from mdeditor.app import pdf_jobs_each, pdf_names


def doc(path=None, name=""):
    return SimpleNamespace(path=Path(path) if path else None, name=name)


def test_pdf_named_after_file_and_dedup(tmp_path: Path):
    docs = [doc("a/보고서.md"), doc("b/보고서.md"), doc(name="새 문서 1"), doc("c/x:y.md")]
    names = [Path(p).name for p in pdf_names(docs, tmp_path)]
    assert names == ["보고서.pdf", "보고서 (2).pdf", "새 문서 1.pdf", "x_y.pdf"]
    assert all(Path(p).parent == tmp_path for p in pdf_names(docs, tmp_path))


def test_pdf_jobs_each_saves_next_to_source(tmp_path: Path):
    """각 파일의 폴더에 저장: 파일마다 그 파일이 있는 폴더, 같은 폴더 안에서는 이름이 겹치지 않게."""
    docs = [doc("a/보고서.md"), doc("a/메모.md"), doc("b/보고서.md"), doc(name="새 문서 1")]
    jobs = pdf_jobs_each(docs, tmp_path)
    assert len(jobs) == 4
    assert all(Path(p).parent == (d.path.parent if d.path else tmp_path) for d, p in jobs)  # 파일 옆에, 새 문서는 fallback
    assert [Path(p).name for d, p in jobs if d.path and d.path.parent == Path("a")] == ["보고서.pdf", "메모.pdf"]
    assert next(Path(p).name for d, p in jobs if d.path is None) == "새 문서 1.pdf"
