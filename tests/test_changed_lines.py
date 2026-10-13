from mdeditor.app import changed_lines


def test_changed_and_inserted_lines_in_new_text():
    old = "a\nb\nc\nd"
    new = "a\nB\nc\nnew\nd"
    assert changed_lines(old, new) == [1, 3]


def test_deleted_only_and_same_text():
    assert changed_lines("a\nb\nc", "a\nc") == []
    assert changed_lines("x\ny", "x\ny") == []


def test_feature_request_url_prefills_issue():
    from urllib.parse import parse_qs, urlparse

    from mdeditor.app import feature_request_url

    u = urlparse(feature_request_url("9.9.9"))
    assert u.netloc == "github.com" and u.path.endswith("/issues/new")
    q = parse_qs(u.query)
    assert q["title"] == ["[기능 요청] "]
    assert "mdEditor v9.9.9" in q["body"][0]
