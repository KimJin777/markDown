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


def test_print_document_uses_kind():
    html = print_document([("d.json", '{"k": 1}', None, "json")])
    assert "<h2>k</h2>" in html
