from pathlib import Path

from mdeditor.render import MERMAID_JS, page, print_document, render_body


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


def test_all_mermaid_diagram_types_become_diagram_blocks():
    sources = [
        "flowchart TB\n  A[시작] --> B[끝]",
        "sequenceDiagram\n  사용자->>앱: 열기",
        "classDiagram\n  class 문서",
        "pie title 종류\n  \"마크다운\" : 3",
    ]
    for source in sources:
        html = render_body(f"앞\n\n```mermaid\n{source}\n```\n")
        assert '<pre class="mermaid" data-line="2">' in html
        assert 'class="language-mermaid"' not in html


def test_mermaid_source_is_html_escaped():
    html = render_body("```mermaid\nsequenceDiagram\n  A->>B: <script>alert(1)</script>\n```\n")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_mermaid_page_uses_bundled_library():
    html = page("<p>본문</p>", with_mermaid=True)
    assert MERMAID_JS.is_file()
    assert MERMAID_JS.resolve().as_uri() in html
    assert "securityLevel:'strict'" in html


def test_relative_image_becomes_absolute(tmp_path: Path):
    html = render_body("![그림](img/a.png) [링크](https://example.com) [앵커](#x)", tmp_path)
    assert (tmp_path / "img" / "a.png").resolve().as_uri() in html
    assert 'href="https://example.com"' in html
    assert 'href="#x"' in html


def test_korean_image_name_not_encoded_twice(tmp_path: Path):
    html = render_body("![](그림_images/한글-001.png) ![](<빈칸 폴더/a b.png>)", tmp_path)
    assert (tmp_path / "그림_images" / "한글-001.png").resolve().as_uri() in html
    assert (tmp_path / "빈칸 폴더" / "a b.png").resolve().as_uri() in html
    assert "%25" not in html


def test_print_document_breaks_page_per_file():
    html = print_document([("a.md", "# A", None), ("b.md", "# B", None)])
    assert html.count("<section class='doc'>") == 2
    assert ".doc + .doc" in html and "a.md" in html and "b.md" in html


def test_print_document_waits_for_mermaid_rendering():
    html = print_document([("sequence.md", "```mermaid\nsequenceDiagram\nA->>B: 요청\n```", None)])
    assert "window.__mdMermaidReady = false" in html
    assert "await mermaid.run" in html
    assert MERMAID_JS.resolve().as_uri() in html
