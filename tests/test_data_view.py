from pathlib import Path

from mdeditor.render import kind_of, print_document, render_json, render_yaml


def test_kind_of():
    assert kind_of(Path("a.json")) == "json" and kind_of(Path("a.YML")) == "yaml"
    assert kind_of(Path("a.txt")) == "txt" and kind_of(Path("a.md")) == "md" and kind_of(None) == "md"


def test_json_top_keys_become_headings_and_object_list_becomes_table():
    html = render_json('{"meta": {"coder": "A", "counts": {"I": 1}}, "items": [{"id": 1, "note": "x"}, {"id": 2, "cluster": null}]}')
    assert "<h2>meta" in html and "<h2>items<span class='j-count'>2개</span></h2>" in html
    assert "<table class='kv'>" in html and "<th>coder</th>" in html
    assert "<table class='rows'>" in html and "<th>cluster</th>" in html  # 열 = 모든 키의 합
    assert "j-null'>null" in html


def test_json_error_shows_position_and_raw():
    html = render_json('{"a": 1,,}')
    assert "JSON 형식 오류" in html and "1번째 줄" in html and "&quot;a&quot;" in html


def test_yaml_same_view_and_multi_documents():
    html = render_yaml("name: 테스트\nlist:\n  - a: 1\n  - a: 2\n")
    assert "<h2>name</h2>" in html and "<table class='rows'>" in html
    multi = render_yaml("a: 1\n---\nb: 2\n")
    assert "<h1>문서 1</h1>" in multi and "<h1>문서 2</h1>" in multi
    assert "YAML 형식 오류" in render_yaml("a: [1, 2\n")


def test_csv_table_header_numbers_and_lines():
    from mdeditor.render import render_any

    assert kind_of(Path("a.CSV")) == "csv" and kind_of(Path("a.tsv")) == "tsv"
    html = render_any('이름,점수,메모\n김,90,"쉼표, 있음"\n이,1,234.5,\n', None, "csv")
    assert "<th class='c0'>이름</th>" in html and "<td class='c2'>쉼표, 있음</td>" in html  # 열마다 글자색(c0, c1, ...)
    assert "<td class='c1 num'>90</td>" in html and "2줄 × 4칸" in html  # 칸 수가 다른 줄은 빈칸으로 채움
    assert "table.csv .c1 { color: #0969da; }" in html  # 열 색 CSS가 함께 나간다
    assert "data-line='0'" in html and "data-line='2'" in html  # 동시보기용 원본 줄 번호
    assert "구분: 세미콜론" in render_any("a;b\n1;2\n", None, "csv")
    assert "<td class='c1 num'>2</td>" in render_any("a\tb\n1\t2\n", None, "tsv")
    multi = render_any('a,b\n"줄\n바꿈",x\ny,z\n', None, "csv")
    assert "data-line='3'" in multi  # 따옴표 안 줄바꿈이 있어도 다음 줄 번호가 맞다
    assert "빈 CSV" in render_any("  \n", None, "csv")


def test_print_document_uses_kind():
    html = print_document([("d.json", '{"k": 1}', None, "json")])
    assert "<h2>k</h2>" in html


def test_image_kind_and_view(tmp_path: Path):
    from mdeditor.render import render_any, render_image

    assert kind_of(Path("사진.PNG")) == "image" and kind_of(Path("a.jpg")) == "image" and kind_of(Path("a.webp")) == "image"
    html = render_image("그림 1.png", tmp_path, stamp=123)
    assert "<img src='" in html and html.count("file:///") == 1 and "?r=123" in html  # 파일 주소 + 새로 읽기 표
    assert "alt='그림 1.png'" in html
    assert render_any("그림 1.png", tmp_path, "image").count("?r=") == 0  # 인쇄용은 새로 읽기 표 없음
