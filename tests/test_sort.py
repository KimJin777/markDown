from pathlib import Path

from mdeditor.app import Doc, sort_docs
from mdeditor.render import kind_of


def _docs(*names: str) -> list[Doc]:
    return [Doc(path=Path(n)) for n in names]


def test_sort_by_name_is_natural_and_case_insensitive():
    docs = _docs("b/문서10.md", "a/문서2.md", "c/Alpha.md")
    assert [d.name for d in sort_docs(docs, "name")] == ["Alpha.md", "문서2.md", "문서10.md"]
    assert [d.name for d in sort_docs(docs, "name", reverse=True)] == ["문서10.md", "문서2.md", "Alpha.md"]


def test_sort_by_kind_then_folder_and_added_order():
    docs = _docs("z/b.md", "y/a.json", "x/c.md")
    assert [d.name for d in sort_docs(docs, "kind")] == ["a.json", "b.md", "c.md"]
    assert [d.name for d in sort_docs(docs, "folder")] == ["c.md", "a.json", "b.md"]
    assert sort_docs(docs, "added") == docs and sort_docs(docs, "added", True) == docs[::-1]


def test_pdf_kind():
    assert kind_of(Path("a.PDF")) == "pdf" and Doc(path=Path("a.pdf")).is_pdf
