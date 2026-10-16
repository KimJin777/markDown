"""도구 줄 아이콘 — Windows 내장 아이콘 글꼴(Segoe Fluent Icons, 없으면 Segoe MDL2 Assets)로 그린다.

그림 파일 없이 글꼴의 아이콘 글자를 그려 만들므로 Windows 기본 앱들과 같은 모양이 난다.
PDF·MD·A4처럼 글꼴에 없는 것은 글자 배지로 그린다. get("이름")으로 얻고,
QApplication이 만들어진 뒤에 불러야 한다(QPixmap 때문).
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPen, QPixmap

INK = "#444c56"  # 아이콘 기본색(진한 회색)
ACCENT = "#0969da"  # 강조(파랑)

# Segoe Fluent Icons·MDL2 Assets 공통 코드(이름: (코드, 색)) — https://learn.microsoft.com/windows/apps/design/style/segoe-fluent-icons-font
_FLUENT = {
    "new": (0xE7C3, INK),  # Page
    "open": (0xE8E5, INK),  # OpenFile
    "reload": (0xE72C, INK),  # Refresh
    "reviewed": (0xE73E, ACCENT),  # CheckMark
    "select_all": (0xE8B3, INK),  # SelectAll
    "close": (0xE8BB, INK),  # ChromeClose(✕) — 휴지통 모양은 '지우기'로 오해될 수 있어 쓰지 않는다
    "sort": (0xE8CB, INK),  # Sort
    "save": (0xE74E, INK),  # Save
    "print": (0xE749, INK),  # Print
    "size": (0xE8E9, INK),  # FontSize
    "bold": (0xE8DD, INK),  # Bold
    "italic": (0xE8DB, INK),  # Italic
    "underline": (0xE8DC, INK),  # Underline
    "strike": (0xEDE0, INK),  # Strikethrough
    "symbol": (0xE8C1, INK),  # Characters
    "source": (0xE943, INK),  # Code
    "toc": (0xE8FD, INK),  # BulletedList
    "sync": (0xE895, INK),  # Sync
    "image": (0xE8B9, INK),  # Picture
    "fullscreen": (0xE740, INK),  # FullScreen
}

# 아이콘 글꼴에 없는 것: 글자로 그린다. (글자, 색, 상자 배지 여부)
_GLYPH = {
    "blank": ("␣", INK, False),
    "pdf": ("PDF", "#cf222e", True),
    "pdf2md": ("MD", ACCENT, True),
    "a4": ("A4", INK, True),
}

_cache: dict[str, QIcon] = {}
_family: str | None = None


def _icon_family() -> str:
    """설치된 아이콘 글꼴 이름. Windows 11은 Fluent, Windows 10은 MDL2."""
    global _family
    if _family is None:
        families = set(QFontDatabase.families())
        _family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), "")
    return _family


def _paint(draw) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(p)
    p.end()
    return QIcon(pm)


def _fluent(code: int, color: str) -> QIcon | None:
    family = _icon_family()
    if not family:
        return None
    font = QFont(family)
    font.setPixelSize(46)
    if not QFontMetrics(font).inFontUcs4(code):  # 이 Windows의 글꼴에 없는 아이콘이면 글자 배지로 넘어간다
        return None

    def draw(p: QPainter) -> None:
        p.setPen(QColor(color))
        p.setFont(font)
        p.drawText(QRect(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, chr(code))

    return _paint(draw)


def _glyph(text: str, color: str, boxed: bool) -> QIcon:
    font = QFont("Segoe UI Symbol")
    font.setBold(True)

    def draw(p: QPainter) -> None:
        if boxed:  # 작은 상자 안에 글자(PDF·MD·A4 배지)
            pen = QPen(QColor(color))
            pen.setWidth(4)
            p.setPen(pen)
            p.drawRoundedRect(QRectF(3, 10, 58, 44), 9, 9)
            font.setPixelSize(22 if len(text) >= 3 else 26)
            p.setFont(font)
            p.drawText(QRect(0, 10, 64, 44), Qt.AlignmentFlag.AlignCenter, text)
        else:
            p.setPen(QColor(color))
            font.setPixelSize(30 if len(text) >= 3 else 44)
            p.setFont(font)
            p.drawText(QRect(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, text)

    return _paint(draw)


def get(name: str) -> QIcon:
    """이름으로 아이콘을 얻는다(한 번 만들면 다시 씀). 모르는 이름이면 빈 아이콘."""
    if name in _cache:
        return _cache[name]
    icon = None
    if name in _FLUENT:
        icon = _fluent(*_FLUENT[name])
    if icon is None and name in _GLYPH:
        icon = _glyph(*_GLYPH[name])
    if icon is None:  # 아이콘 글꼴이 없는 환경: 이름 첫 글자라도 그린다
        icon = _glyph(name[:1].upper(), INK, False) if name else QIcon()
    _cache[name] = icon
    return icon
