"""마크다운 → HTML 변환. 뷰어와 인쇄가 같은 함수를 쓴다."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _highlight(code: str, lang: str, _attrs: str) -> str:
    try:
        lexer = get_lexer_by_name(lang.strip()) if lang.strip() else None
    except ClassNotFound:
        lexer = None
    if lexer is None:
        return ""  # 빈 문자열이면 markdown-it이 이스케이프해서 그대로 출력
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


def _make_md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "highlight": _highlight})
    md.enable(["table", "strikethrough"])
    md.use(tasklists_plugin)
    return md


_MD = _make_md()


def _absolute(src: str, base_dir: Path | None) -> str:
    """상대 경로 이미지·링크를 파일 위치 기준 file:// 주소로 바꾼다(인쇄 때 여러 파일을 합치므로)."""
    if base_dir is None or not src or src.startswith("#") or _URL_SCHEME.match(src):
        return src
    return (base_dir / src).resolve().as_uri()


def render_body(text: str, base_dir: Path | None = None) -> str:
    """본문 HTML. 블록마다 data-line(0부터 시작하는 원본 줄 번호)을 붙여 스크롤 동기화에 쓴다."""
    env: dict = {}
    tokens = _MD.parse(text, env)
    for tok in tokens:
        if tok.map and tok.nesting >= 0 and tok.block:
            tok.attrSet("data-line", str(tok.map[0]))
        for child in tok.children or []:
            if child.type == "image":
                child.attrSet("src", _absolute(str(child.attrGet("src") or ""), base_dir))
            elif child.type == "link_open":
                child.attrSet("href", _absolute(str(child.attrGet("href") or ""), base_dir))
    return _MD.renderer.render(tokens, _MD.options, env)


CSS = """
:root { color-scheme: light; }
body { font-family: "Malgun Gothic", "Segoe UI", sans-serif; font-size: 15px; line-height: 1.7;
       color: #1f2328; background: #fff; margin: 0; padding: 20px 28px; word-wrap: break-word; }
h1, h2 { border-bottom: 1px solid #d8dee4; padding-bottom: .3em; }
h1, h2, h3, h4, h5, h6 { margin: 1.4em 0 .6em; line-height: 1.3; }
p, ul, ol, table, pre, blockquote { margin: 0 0 1em; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
code { font-family: Consolas, "D2Coding", monospace; font-size: 90%;
       background: #eff1f3; padding: .15em .35em; border-radius: 4px; }
pre { background: #f6f8fa; padding: 12px 16px; border-radius: 6px; overflow-x: auto; line-height: 1.45; }
pre code { background: none; padding: 0; font-size: 88%; }
blockquote { color: #59636e; border-left: 4px solid #d1d9e0; padding: 0 1em; margin-left: 0; }
table { border-collapse: collapse; }
th, td { border: 1px solid #d1d9e0; padding: 6px 13px; }
th { background: #f6f8fa; }
img { max-width: 100%; }
hr { border: 0; border-top: 1px solid #d1d9e0; margin: 1.5em 0; }
li.task-list-item { list-style: none; }
li.task-list-item input { margin: 0 .4em 0 -1.3em; }
.file-title { font-size: 12px; color: #59636e; border-bottom: 1px solid #d8dee4; margin-bottom: 1em; }
.doc + .doc { break-before: page; page-break-before: always; }
@media print { body { padding: 0; } pre { white-space: pre-wrap; } a { color: inherit; } }
""" + HtmlFormatter(style="default").get_style_defs("pre code")


JSON_CSS = """
.json-err { color: #cf222e; background: #ffebe9; border: 1px solid #ffcecb; padding: 8px 12px; border-radius: 6px; }
table.kv { border-collapse: collapse; margin: 0 0 1em; }
table.kv > tbody > tr > th { text-align: left; vertical-align: top; background: #f6f8fa; white-space: nowrap; font-weight: 600; }
table.kv td, table.kv th, table.rows td, table.rows th { border: 1px solid #d1d9e0; padding: 4px 10px; vertical-align: top; }
table.rows { border-collapse: collapse; margin: 0 0 1em; font-size: 14px; }
table.rows thead th { position: sticky; top: 0; background: #eaeef2; z-index: 1; }
table.rows td.idx { color: #8c959f; text-align: right; }
.j-str { white-space: pre-wrap; } .j-num { color: #0550ae; } .j-bool { color: #8250df; } .j-null { color: #8c959f; font-style: italic; }
.j-count { color: #59636e; font-weight: normal; font-size: 13px; margin-left: .4em; }
ul.j-list { margin: 0; padding-left: 1.2em; }
"""


def _j_scalar(v) -> str:
    if v is None:
        return "<span class='j-null'>null</span>"
    if isinstance(v, bool):
        return f"<span class='j-bool'>{'true' if v else 'false'}</span>"
    if isinstance(v, (int, float)):
        return f"<span class='j-num'>{v}</span>"
    return f"<span class='j-str'>{html.escape(str(v))}</span>"


def _j_value(v, depth: int = 0) -> str:
    if isinstance(v, dict):
        if not v:
            return "<span class='j-null'>{}</span>"
        rows = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{_j_value(x, depth + 1)}</td></tr>" for k, x in v.items())
        return f"<table class='kv'><tbody>{rows}</tbody></table>"
    if isinstance(v, list):
        if not v:
            return "<span class='j-null'>[]</span>"
        if len(v) >= 2 and all(isinstance(x, dict) for x in v):
            return _j_rows(v, depth)
        if all(not isinstance(x, (dict, list)) for x in v) and len(v) <= 8 and sum(len(str(x)) for x in v) < 120:
            return ", ".join(_j_scalar(x) for x in v)  # 짧은 값 목록은 한 줄로
        return "<ul class='j-list'>" + "".join(f"<li>{_j_value(x, depth + 1)}</li>" for x in v) + "</ul>"
    return _j_scalar(v)


def _j_rows(items: list[dict], depth: int) -> str:
    """같은 모양의 객체 목록 → 표(열 = 키). 397개 같은 긴 목록을 한눈에."""
    cols: list[str] = []
    for it in items:
        for k in it:
            if k not in cols:
                cols.append(k)
    head = "<th>#</th>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    body = "".join(
        f"<tr><td class='idx'>{i}</td>" + "".join(f"<td>{_j_value(it[c], depth + 1) if c in it else ''}</td>" for c in cols) + "</tr>"
        for i, it in enumerate(items, 1)
    )
    return f"<table class='rows'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _data_err(kind: str, where: str, msg: str, text: str) -> str:
    return (
        f"<style>{JSON_CSS}</style><div class='json-err'>{kind} 형식 오류 — {where}: {html.escape(msg)}</div>"
        f"<pre><code>{html.escape(text)}</code></pre>"
    )


def render_data(data, title: str | None = None) -> str:
    """구조 데이터 보기: 맨 위 키는 제목(목차에 나옴), 객체는 '키 | 값' 표, 같은 모양 객체 목록은 열 표."""
    out = [f"<h1>{html.escape(title)}</h1>"] if title else []
    if isinstance(data, dict) and data:
        for k, v in data.items():
            count = f"<span class='j-count'>{len(v)}개</span>" if isinstance(v, (list, dict)) else ""
            out.append(f"<h2>{html.escape(str(k))}{count}</h2>{_j_value(v)}")
    else:
        out.append(_j_value(data))
    return "".join(out)


def render_json(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return _data_err("JSON", f"{e.lineno}번째 줄 {e.colno}번째 칸", e.msg, text)
    return f"<style>{JSON_CSS}</style>" + render_data(data)


def render_yaml(text: str) -> str:
    """YAML도 JSON과 같은 모양으로. '---'로 나뉜 여러 문서는 문서마다 따로."""
    try:
        docs = [d for d in yaml.safe_load_all(text)]
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"{mark.line + 1}번째 줄 {mark.column + 1}번째 칸" if mark else "위치 모름"
        return _data_err("YAML", where, str(getattr(e, "problem", None) or e), text)
    docs = [d for d in docs if d is not None]
    if not docs:
        return "<p class='j-null'>(빈 YAML)</p>"
    parts = [f"<style>{JSON_CSS}</style>"]
    for i, d in enumerate(docs, 1):
        parts.append(render_data(d, title=f"문서 {i}" if len(docs) > 1 else None))
    return "".join(parts)


def kind_of(path: Path | None) -> str:
    """파일 종류: 'md' | 'txt' | 'json' | 'yaml' | 'pdf'."""
    suffix = path.suffix.lower() if path else ".md"
    return {".txt": "txt", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".pdf": "pdf"}.get(suffix, "md")


def render_any(text: str, base_dir: Path | None, kind: str = "md") -> str:
    """파일 종류별 본문 HTML."""
    if kind == "json":
        return render_json(text)
    if kind == "yaml":
        return render_yaml(text)
    return render_body(text, base_dir)


def page(body: str, title: str = "", script: str = "") -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>{body}{script}</body></html>"
    )


def print_document(docs: list[tuple]) -> str:
    """인쇄용 HTML 하나. docs = [(제목, 원본, 기준 폴더[, 종류])], 파일마다 새 쪽에서 시작."""
    parts = [
        f"<section class='doc'><div class='file-title'>{html.escape(d[0])}</div>"
        f"{render_any(d[1], d[2], d[3] if len(d) > 3 else 'md')}</section>"
        for d in docs
    ]
    return page("".join(parts), title="인쇄")
