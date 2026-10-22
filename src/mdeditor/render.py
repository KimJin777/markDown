"""마크다운 → HTML 변환. 뷰어와 인쇄가 같은 함수를 쓴다."""

from __future__ import annotations

import csv
import html
import io
import json
import re
from pathlib import Path
from urllib.parse import unquote

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_MERMAID_FLOWCHART_TB = re.compile(r"^\s*flowchart\s+TB(?:\s|$)", re.IGNORECASE)
MERMAID_JS = Path(__file__).with_name("vendor") / "mermaid.tiny.js"


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
    path, frag = (src.split("#", 1) + [""])[:2]
    # markdown-it이 한글·빈칸을 %EC..·%20으로 바꿔 두므로 풀어서 파일 경로로 만든다(안 풀면 %25EC로 두 번 바뀌어 그림이 안 보임)
    uri = (base_dir / unquote(path)).resolve().as_uri()
    return uri + ("#" + frag if frag else "")


def render_body(text: str, base_dir: Path | None = None) -> str:
    """본문 HTML. 블록마다 data-line(0부터 시작하는 원본 줄 번호)을 붙여 스크롤 동기화에 쓴다."""
    env: dict = {}
    tokens = _MD.parse(text, env)
    for tok in tokens:
        if tok.map and tok.nesting >= 0 and tok.block:
            tok.attrSet("data-line", str(tok.map[0]))
        # 기능 요청 #15: Mermaid 전체가 아니라 flowchart TB 코드 블록만 그래프로 표시한다.
        # html.escape로 원문을 넣어 Mermaid가 처리하기 전에도 임의 HTML이 실행되지 않게 한다.
        info = tok.info.strip().split(None, 1) if tok.type == "fence" else []
        if info and info[0].lower() == "mermaid" and _MERMAID_FLOWCHART_TB.match(tok.content):
            line = tok.attrGet("data-line")
            line_attr = f' data-line="{line}"' if line is not None else ""
            tok.type = "html_block"
            tok.tag = ""
            tok.nesting = 0
            tok.content = f'<pre class="mermaid"{line_attr}>{html.escape(tok.content)}</pre>\n'
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
pre.mermaid { background: #fff; padding: 12px 0; text-align: center; white-space: normal; }
pre.mermaid svg { display: block; max-width: 100%; height: auto; margin: 0 auto; }
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
@media print { body { padding: 0; } pre { white-space: pre-wrap; } pre.mermaid { break-inside: avoid; }
               a { color: inherit; } }
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


# 열마다 다른 글자색(어두운 색만 — 흰 바탕에서 읽기 좋게). 열이 많으면 처음부터 돌려 쓴다.
CSV_COLORS = ["#1f2328", "#0969da", "#bc4c00", "#1a7f37", "#8250df", "#cf222e", "#9a6700", "#1b7c83"]

CSV_CSS = """
table.csv { border-collapse: collapse; margin: 0 0 1em; font-size: 14px; }
table.csv th, table.csv td { border: 1px solid #d1d9e0; padding: 4px 10px; vertical-align: top; white-space: pre-wrap; }
table.csv thead th { position: sticky; top: 0; background: #eaeef2; z-index: 1; }
table.csv td.idx { color: #8c959f; text-align: right; }
table.csv td.num { text-align: right; font-variant-numeric: tabular-nums; }
.csv-info { color: #59636e; font-size: 13px; margin: 0 0 .6em; }
""" + "".join(f"table.csv .c{i} {{ color: {c}; }}\n" for i, c in enumerate(CSV_COLORS))
_NUM = re.compile(r"^[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?%?$")


def _csv_delimiter(text: str, tsv: bool) -> str:
    if tsv:
        return "\t"
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def render_csv(text: str, tsv: bool = False) -> str:
    """CSV·TSV → 표. 첫 줄은 머리글, 숫자 칸은 오른쪽 정렬. 줄마다 data-line을 붙여 동시보기가 된다."""
    if not text.strip():
        return "<p class='j-null'>(빈 CSV)</p>"
    sep = _csv_delimiter(text, tsv)
    reader = csv.reader(io.StringIO(text), delimiter=sep)
    rows: list[tuple[int, list[str]]] = []
    start = 0
    try:
        for row in reader:
            if row:
                rows.append((start, row))
            start = reader.line_num
    except csv.Error as e:
        return _data_err("CSV", f"{reader.line_num}번째 줄", str(e), text)
    if not rows:
        return "<p class='j-null'>(빈 CSV)</p>"
    width = max(len(r) for _, r in rows)
    (head_line, head), body = rows[0], rows[1:]
    head = head + [""] * (width - len(head))
    col = [f"c{i % len(CSV_COLORS)}" for i in range(width)]  # 열마다 글자색을 다르게(보기 편하게)

    def cells(r: list[str]) -> str:
        r = r + [""] * (width - len(r))
        return "".join(
            f"<td class='{col[i]}{' num' if _NUM.match(c.strip()) else ''}'>{html.escape(c)}</td>" for i, c in enumerate(r)
        )

    thead = (
        f"<tr data-line='{head_line}'><th>#</th>"
        + "".join(f"<th class='{col[i]}'>{html.escape(c)}</th>" for i, c in enumerate(head))
        + "</tr>"
    )
    tbody = "".join(f"<tr data-line='{ln}'><td class='idx'>{i}</td>{cells(r)}</tr>" for i, (ln, r) in enumerate(body, 1))
    name = {",": "쉼표", "\t": "탭", ";": "세미콜론", "|": "세로줄"}.get(sep, repr(sep))
    return (
        f"<style>{JSON_CSS}{CSV_CSS}</style><p class='csv-info'>{len(body)}줄 × {width}칸 · 구분: {name}</p>"
        f"<table class='csv'><thead>{thead}</thead><tbody>{tbody}</tbody></table>"
    )


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}


def kind_of(path: Path | None) -> str:
    """파일 종류: 'md' | 'txt' | 'json' | 'yaml' | 'csv' | 'tsv' | 'pdf' | 'image' | 'hwp'."""
    suffix = path.suffix.lower() if path else ".md"
    kinds = {
        ".txt": "txt", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".csv": "csv", ".tsv": "tsv", ".pdf": "pdf", ".hwp": "hwp", ".hwpx": "hwp",
    }
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return kinds.get(suffix, "md")


def render_image(name: str, base_dir: Path | None, stamp: int = 0) -> str:
    """그림 파일 보기: 그림 하나가 본문. stamp(고친 시각)를 주소 뒤에 붙여 밖에서 바뀐 그림이 새로 읽히게 한다."""
    src = _absolute(name, base_dir)
    if stamp:
        src += f"?r={stamp}"
    return f"<img src='{html.escape(src, quote=True)}' alt='{html.escape(name)}'>"


def render_any(text: str, base_dir: Path | None, kind: str = "md") -> str:
    """파일 종류별 본문 HTML. 그림(kind='image')은 text 자리에 파일 이름을 받는다."""
    if kind == "json":
        return render_json(text)
    if kind == "yaml":
        return render_yaml(text)
    if kind in ("csv", "tsv"):
        return render_csv(text, tsv=kind == "tsv")
    if kind == "image":
        return render_image(text, base_dir)
    return render_body(text, base_dir)


def _mermaid_head() -> str:
    """앱에 함께 넣은 Mermaid를 불러온다. 외부 CDN을 쓰지 않아 오프라인에서도 동작한다."""
    src = html.escape(MERMAID_JS.resolve().as_uri(), quote=True)
    return (
        f"<script src='{src}'></script>"
        "<script>mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'default',"
        "flowchart:{useMaxWidth:true}});</script>"
    )


def page(body: str, title: str = "", script: str = "", with_mermaid: bool = False) -> str:
    extra_head = _mermaid_head() if with_mermaid else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{CSS}</style>{extra_head}</head>"
        f"<body>{body}{script}</body></html>"
    )


def print_document(docs: list[tuple]) -> str:
    """인쇄용 HTML 하나. docs = [(제목, 원본, 기준 폴더[, 종류])], 파일마다 새 쪽에서 시작."""
    parts = [
        f"<section class='doc'><div class='file-title'>{html.escape(d[0])}</div>"
        f"{render_any(d[1], d[2], d[3] if len(d) > 3 else 'md')}</section>"
        for d in docs
    ]
    body = "".join(parts)
    has_mermaid = 'class="mermaid"' in body
    script = ""
    if has_mermaid:
        script = """
<script>
window.__mdMermaidReady = false;
(async () => {
  try { await mermaid.run({querySelector: '.mermaid', suppressErrors: true}); }
  catch (e) { console.error(e); }
  finally { window.__mdMermaidReady = true; }
})();
</script>
"""
    return page(body, title="인쇄", script=script, with_mermaid=has_mermaid)
