from mdeditor.fmt import blank, find_all, insert_text, next_match
from mdeditor.render import render_body
from mdeditor.symbols import GROUPS


def test_find_all_case_and_word():
    t = "Cat cat category CAT"
    assert find_all(t, "cat") == [(0, 3), (4, 7), (8, 11), (17, 20)]
    assert find_all(t, "cat", case=True) == [(4, 7), (8, 11)]
    assert find_all(t, "cat", word=True) == [(0, 3), (4, 7), (17, 20)]
    assert find_all(t, "") == []
    assert find_all("a.b axb", ".") == [(1, 2)]  # 정규식 글자도 글자 그대로


def test_find_korean_word():
    assert find_all("사과 사과나무 사과", "사과", word=True) == [(0, 2), (8, 10)]


def test_next_match_wraps():
    spans = [(0, 3), (4, 7), (17, 20)]
    assert next_match(spans, 3) == 1
    assert next_match(spans, 18) == 0  # 끝에서 처음으로
    assert next_match(spans, 4, back=True) == 0
    assert next_match(spans, 0, back=True) == 2  # 처음에서 끝으로
    assert next_match([], 0) is None


def test_insert_replaces_selection_and_moves_cursor():
    assert insert_text("가나다", 1, 2, "※") == (1, 2, "※", 2, 2)
    assert insert_text("가나다", 3, 3, "①") == (3, 3, "①", 4, 4)


def test_blank_renders_as_underlined_space():
    assert blank(3) == "<u>&emsp;&emsp;&emsp;</u>"
    assert blank(2, under=False) == "&emsp;&emsp;"
    html = render_body(f"답: {blank(4)} 입니다")
    assert "<u>    </u>" in html  # 빈칸이 줄지 않고 그대로 남는다


def test_symbol_groups_are_single_characters():
    assert len(GROUPS) >= 5
    for name, chars in GROUPS:
        assert name and chars and len(set(chars)) == len(chars), name
