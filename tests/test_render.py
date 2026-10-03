from pathlib import Path

from mdeditor.render import print_document, render_body


def test_blocks_carry_source_line():
    html = render_body("# 제목\n\n본문\n\n- 하나\n")
    assert '<h1 data-line="0">' in html
    assert '<p data-line="2">' in html
    assert 'data-line="4"' in html


def test_table_and_strikethrough():
    html = render_body("| a | b |\n|---|---|\n| 1 | 2 |\n\n~~지움~~")
    assert "<table" in html and "<td>1</td>" in html
    assert "<s>지움</s>" in html


def test_task_list():
    html = render_body("- [x] 완료\n- [ ] 할 일\n")
    assert "task-list-item" in html
    assert 'checked="checked"' in html


def test_code_block_highlighted_and_unknown_lang_escaped():
    html = render_body("```python\nprint('x')\n```\n\n```zzz\n<b>\n```")
    assert 'class="language-python"' in html and "<span" in html
    assert "&lt;b&gt;" in html


def test_relative_image_becomes_absolute(tmp_path: Path):
    html = render_body("![그림](img/a.png) [링크](https://example.com) [앵커](#x)", tmp_path)
    assert (tmp_path / "img" / "a.png").resolve().as_uri() in html
    assert 'href="https://example.com"' in html
    assert 'href="#x"' in html


def test_print_document_breaks_page_per_file():
    html = print_document([("a.md", "# A", None), ("b.md", "# B", None)])
    assert html.count("<section class='doc'>") == 2
    assert ".doc + .doc" in html and "a.md" in html and "b.md" in html
