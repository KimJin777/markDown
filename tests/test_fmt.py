from mdeditor.fmt import py_to_q, q_to_py, set_heading, set_size, toggle_wrap


def apply(text, edit):
    s, e, new, ns, ne = edit
    out = text[:s] + new + text[e:]
    return out, out[ns:ne]


def test_wrap_and_unwrap_selection():
    t = "가 나다 라"
    out, sel = apply(t, toggle_wrap(t, 2, 4, "**"))
    assert out == "가 **나다** 라" and sel == "나다"
    # 바깥에 마커가 있으면 벗긴다(같은 버튼 다시 누르기)
    back, sel = apply(out, toggle_wrap(out, 4, 6, "**"))
    assert back == t and sel == "나다"
    # 마커까지 선택해도 벗긴다
    back, _ = apply(out, toggle_wrap(out, 2, 8, "**"))
    assert back == t


def test_italic_does_not_eat_bold():
    t = "**굵게**"
    out, _ = apply(t, toggle_wrap(t, 2, 4, "*"))
    assert out == "***굵게***"
    out, _ = apply(t, toggle_wrap(t, 0, 6, "*"))
    assert out == "***굵게***"


def test_no_selection_puts_cursor_between_markers():
    s, e, new, ns, ne = toggle_wrap("abc", 1, 1, "<u>", "</u>")
    assert new == "<u></u>" and ns == ne == 4


def test_underline_html():
    t = "밑줄"
    out, _ = apply(t, toggle_wrap(t, 0, 2, "<u>", "</u>"))
    assert out == "<u>밑줄</u>"
    back, _ = apply(out, toggle_wrap(out, 3, 5, "<u>", "</u>"))
    assert back == t


def test_size_wrap_change_and_remove():
    t = "크게"
    out, sel = apply(t, set_size(t, 0, 2, 24))
    assert out == '<span style="font-size:24px">크게</span>' and sel == "크게"
    i = out.index("크게")
    out2, _ = apply(out, set_size(out, i, i + 2, 14))  # 안쪽만 선택해도 크기만 바뀜
    assert out2 == '<span style="font-size:14px">크게</span>'
    back, _ = apply(out2, set_size(out2, 0, len(out2), None))  # 태그째 선택 후 기본 크기
    assert back == t


def test_heading_lines():
    t = "첫 줄\n## 둘째\n\n셋째"
    out, _ = apply(t, set_heading(t, 1, 8, 1))
    assert out == "# 첫 줄\n# 둘째\n\n셋째"
    back, _ = apply(out, set_heading(out, 0, 0, 0))
    assert back == "첫 줄\n# 둘째\n\n셋째"


def test_utf16_positions():
    t = "a😀b"
    assert py_to_q(t, 2) == 3 and q_to_py(t, 3) == 2


def test_locate_preview_selection_in_source():
    from mdeditor.fmt import locate_in_source

    t = "# 제목\n\n가나 **다라** 가나\n\n가나 끝"
    # 셋째 줄(2) 블록, 블록 안 두 번째 '가나'(앞쪽 글자에 '가나'가 한 번 있음)
    s, e = locate_in_source(t, 2, 4, "가나", "가나 다라 ")
    assert t[s:e] == "가나" and t[:s].count("가나") == 1
    # 굵게 안의 글자도 찾는다
    s, e = locate_in_source(t, 2, 4, "다라", "가나 ")
    assert t[s - 2 : e + 2] == "**다라**"
    # 범위 밖·없는 글자는 None
    assert locate_in_source(t, 2, 4, "끝", "") is None
    assert locate_in_source(t, 2, 4, "  ", "") is None
