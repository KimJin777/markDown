"""서식 버튼이 원본에 할 일. 모두 (바꿀 시작, 끝, 새 글, 새 선택 시작, 끝)을 돌려준다(위치는 파이썬 글자 단위)."""

from __future__ import annotations

import re

Edit = tuple[int, int, str, int, int]

_SPAN = r'<span style="font-size:\d+px">'
_SPAN_FULL = re.compile(_SPAN + r"(.*)</span>", re.S)
_SPAN_BEFORE = re.compile(_SPAN + r"$")
_HEADING = re.compile(r"^#{1,6}\s+")


def _star_ok(run_before: str, run_after: str, left: str) -> bool:
    """'*' 기울임을 '**' 굵게와 헷갈리지 않게: 마커 바깥에 별이 더 붙어 있으면 다른 서식이다."""
    if left != "*":
        return True
    return not (run_before.endswith("*") or run_after.startswith("*"))


def toggle_wrap(text: str, s: int, e: int, left: str, right: str | None = None) -> Edit:
    """선택한 글자를 left…right로 감싸거나, 이미 감싸져 있으면 벗긴다."""
    right = left if right is None else right
    sel = text[s:e]
    # 1) 선택 안에 마커까지 들어 있는 경우: **글자**
    if (
        len(sel) >= len(left) + len(right)
        and sel.startswith(left)
        and sel.endswith(right)
        and _star_ok(sel[len(left) : len(left) + 1], sel[len(sel) - len(right) - 1 : len(sel) - len(right)], left)
    ):
        inner = sel[len(left) : len(sel) - len(right)]
        return s, e, inner, s, s + len(inner)
    # 2) 선택 바로 바깥에 마커가 있는 경우: **[글자]**
    if (
        text[max(0, s - len(left)) : s] == left
        and text[e : e + len(right)] == right
        and _star_ok(text[max(0, s - len(left) - 1) : s - len(left)], text[e + len(right) : e + len(right) + 1], left)
    ):
        ns = s - len(left)
        return ns, e + len(right), sel, ns, ns + len(sel)
    # 3) 감싸기 (선택이 없으면 마커 사이에 커서)
    return s, e, left + sel + right, s + len(left), s + len(left) + len(sel)


def set_size(text: str, s: int, e: int, px: int | None) -> Edit:
    """글자 크기: <span style="font-size:Npx">로 감싼다. px=None이면 크기 지정을 없앤다(기본 크기)."""
    sel = text[s:e]
    open_tag = f'<span style="font-size:{px}px">' if px else ""
    close_tag = "</span>" if px else ""
    if m := _SPAN_FULL.fullmatch(sel):
        inner = m.group(1)
        rs, re_ = s, e
    elif (m := _SPAN_BEFORE.search(text, 0, s)) and text[e : e + 7] == "</span>":
        inner = sel
        rs, re_ = m.start(), e + 7
    else:
        if not px:
            return s, e, sel, s, e
        inner, rs, re_ = sel, s, e
    start = rs + len(open_tag)
    return rs, re_, open_tag + inner + close_tag, start, start + len(inner)


def set_heading(text: str, s: int, e: int, level: int) -> Edit:
    """선택이 걸친 줄마다 제목 단계(#×level)를 붙인다. level=0이면 본문으로 되돌린다."""
    ls = text.rfind("\n", 0, s) + 1
    end_ref = e - 1 if e > s and text[e - 1] == "\n" else e  # 다음 줄 맨 앞까지 잡힌 선택은 그 줄 제외
    le = text.find("\n", end_ref)
    le = len(text) if le == -1 else le
    lines = text[ls:le].split("\n")
    prefix = "#" * level + " " if level else ""
    new = "\n".join((prefix + _HEADING.sub("", ln)) if ln.strip() else ln for ln in lines)
    return ls, le, new, ls, ls + len(new)


def locate_in_source(text: str, line: int, end: int, sel: str, before: str) -> tuple[int, int] | None:
    """뷰어에서 선택한 글자를 원본에서 찾는다. line~end(다음 블록 시작 줄, -1이면 끝) 범위에서,
    블록 안 앞쪽에 같은 글자가 몇 번 나왔는지(before)로 몇 번째 것인지 고른다. 못 찾으면 None."""
    sel = sel.strip()
    if not sel:
        return None
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    if line >= len(starts):
        return None
    lo = starts[line]
    hi = starts[end] if 0 <= end < len(starts) else len(text)
    found, i = [], text.find(sel, lo, hi)
    while i != -1:
        found.append(i)
        i = text.find(sel, i + len(sel), hi)
    if not found:
        return None
    k = before.count(sel)
    s = found[k] if k < len(found) else found[0]
    return s, s + len(sel)


# Qt 문서 위치는 UTF-16 단위라 이모지 같은 글자에서 파이썬 위치와 어긋난다
def q_to_py(text: str, q: int) -> int:
    n = 0
    for i, ch in enumerate(text):
        if n >= q:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def py_to_q(text: str, i: int) -> int:
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in text[:i])
