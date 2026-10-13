from mdeditor.changelog import changes_since, read_changelog, sections, version_key

TEXT = """# 변경 이력

설명

## v0.7.0 — 2026-10-13

- 그림 슬라이드

## v0.6.0 — 2026-10-13

- 트리

## v0.5.0 — 2026-10-05

- PDF 보기
"""


def test_sections_in_file_order():
    assert [v for v, _ in sections(TEXT)] == ["0.7.0", "0.6.0", "0.5.0"]
    assert sections(TEXT)[1][1] == "## v0.6.0 — 2026-10-13\n\n- 트리"


def test_changes_since_last_seen():
    assert "그림 슬라이드" in changes_since(TEXT, "0.5.0", "0.7.0")
    assert "트리" in changes_since(TEXT, "0.5.0", "0.7.0")
    assert "PDF 보기" not in changes_since(TEXT, "0.5.0", "0.7.0")
    # 처음 실행(본 적 없음)이면 지금 버전만
    assert changes_since(TEXT, None, "0.6.0") == "## v0.6.0 — 2026-10-13\n\n- 트리"
    assert changes_since(TEXT, "0.7.0", "0.7.0") == ""


def test_version_key_numeric():
    assert version_key("0.10.0") > version_key("0.9.1")


def test_real_changelog_is_found():
    assert sections(read_changelog())  # 개발 실행에서도 저장소의 CHANGELOG.md를 찾는다
