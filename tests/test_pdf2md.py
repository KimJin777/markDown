from pathlib import Path

import pymupdf

from mdeditor.pdf2md import _is_xfa_fallback, convert, images_dir_for, md_path_for, xfa_markdown


def test_xfa_fallback_detector():
    assert _is_xfa_fallback("# Please wait... \n\nIf this message is not replaced ... Adobe Reader ...")
    assert not _is_xfa_fallback("# 보통 문서\n\n본문입니다")


def test_xfa_markdown_labels_and_values():
    xml = (
        "<xfa:datasets xmlns:xfa='http://www.xfa.org/schema/xfa-data/1.0/'><xfa:data>"
        "<form1><Header><DOC_TITLE>특허출원서</DOC_TITLE></Header>"
        "<a><L_1>【구분항목】</L_1><D_1>특허출원</D_1><D_2>100010</D_2></a>"
        "<b><L_2>【빈항목】</L_2><D_3></D_3></b>"
        "<c><D_4>라벨 없는 값</D_4></c>"
        "</form1></xfa:data></xfa:datasets>"
    )
    md = xfa_markdown(xml)
    assert "# 특허출원서" in md
    assert "**【구분항목】** 특허출원 100010" in md
    assert "【빈항목】" not in md  # 값 없는 항목은 뺀다
    assert "라벨 없는 값" in md and md.startswith(">")  # 전자 양식 안내문으로 시작


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


def test_convert_writes_images_next_to_md(tmp_path: Path):
    folder = tmp_path / "빈칸 있는 폴더"
    folder.mkdir()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 120), False)
    pix.clear_with(180)
    png = tmp_path / "pic.png"
    pix.save(str(png))
    pdf = folder / "보고서 1.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Picture page", fontsize=20)
    page.insert_image(pymupdf.Rect(72, 120, 372, 300), filename=str(png))
    doc.save(pdf)
    doc.close()
    md = md_path_for(pdf)
    text = convert(pdf, md)
    img_dir = images_dir_for(md)
    files = list(img_dir.iterdir())
    assert files and all(f.suffix == ".png" for f in files)
    assert f"]({img_dir.name}/{files[0].name})" in text  # 상대 경로로 가리킨다
    assert ":/" not in text  # 절대 경로(C:/...)가 남지 않는다


def test_no_images_leaves_no_folder(tmp_path: Path):
    pdf = tmp_path / "text.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "only text", fontsize=12)
    doc.save(pdf)
    doc.close()
    md = md_path_for(pdf)
    assert "only text" in convert(pdf, md)
    assert not images_dir_for(md).exists()
