"""마크다운 → HTML 변환. 뷰어와 인쇄가 같은 함수를 쓴다."""

from __future__ import annotations

import html
import re
from pathlib import Path

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


def page(body: str, title: str = "", script: str = "") -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>{body}{script}</body></html>"
    )


def print_document(docs: list[tuple[str, str, Path | None]]) -> str:
    """인쇄용 HTML 하나. docs = [(제목, 원본, 기준 폴더)], 파일마다 새 쪽에서 시작."""
    parts = [
        f"<section class='doc'><div class='file-title'>{html.escape(title)}</div>"
        f"{render_body(text, base)}</section>"
        for title, text, base in docs
    ]
    return page("".join(parts), title="인쇄")
