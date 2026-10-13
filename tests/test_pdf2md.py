from pathlib import Path

import pymupdf

from mdeditor.pdf2md import convert, md_path_for


def test_md_named_after_pdf_without_overwrite(tmp_path: Path):
    pdf = tmp_path / "보고서.pdf"
    assert md_path_for(pdf) == tmp_path / "보고서.md"
    (tmp_path / "보고서.md").write_text("있던 파일", encoding="utf-8")
    assert md_path_for(pdf) == tmp_path / "보고서 (2).md"
    # 같은 묶음에서 이미 쓰기로 한 이름도 피한다
    assert md_path_for(pdf, {tmp_path / "보고서 (2).md"}) == tmp_path / "보고서 (3).md"


def test_convert_extracts_text(tmp_path: Path):
    pdf = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello PDF", fontsize=24)
    page.insert_text((72, 120), "second line of body text", fontsize=11)
    doc.save(pdf)
    doc.close()
    md = convert(pdf)
    assert "Hello PDF" in md
    assert "second line of body text" in md
    assert md.endswith("\n")
