import zipfile
from pathlib import Path

from mdeditor.hwp2md import _bin_no, _hwpx_images, merge_images
from mdeditor.render import kind_of


def test_kind_of_hwp():
    assert kind_of(Path("문서.hwp")) == "hwp" and kind_of(Path("문서.HWPX")) == "hwp"


def test_bin_no_is_hex():
    """BinData 번호는 16진수 — BIN0009 다음이 BIN000A."""
    names = ["BIN000A.jpg", "BIN0002.jpg", "BIN0009.bmp", "BIN0010.png"]
    assert sorted(names, key=_bin_no) == ["BIN0002.jpg", "BIN0009.bmp", "BIN000A.jpg", "BIN0010.png"]


def test_merge_images_fills_placeholders_in_order():
    text = "앞글\n\n[그림]\n\n| 칸 | [그림] |\n"
    links = ["![a](x/a.jpg)", "![b](x/b.jpg)"]
    out = merge_images(text, links)
    assert "![a](x/a.jpg)" in out.splitlines()[2] and "| 칸 | ![b](x/b.jpg) |" in out
    # 자리보다 그림이 많으면 맨 뒤에 모은다
    out = merge_images("[그림]\n", ["![a](a)", "![b](b)", "![c](c)"])
    assert out.startswith("![a](a)") and "나머지 그림" in out and "![c](c)" in out
    # 그림이 모자라면 남은 자리는 그대로 둔다
    assert "[그림]" in merge_images("[그림] [그림]\n", ["![a](a)"])


def test_hwpx_images_from_zip(tmp_path: Path):
    """HWPX는 ZIP — BinData 안의 그림만, 번호 순서로."""
    p = tmp_path / "견본.hwpx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Contents/section0.xml", "<xml/>")
        z.writestr("BinData/image2.png", b"PNG2")
        z.writestr("BinData/image1.jpg", b"JPG1")
        z.writestr("BinData/skip.wmf", b"WMF")  # 브라우저가 못 보여 주는 형식은 뺀다
    imgs = _hwpx_images(p)
    assert [(n, d) for n, d in imgs] == [("image1.jpg", b"JPG1"), ("image2.png", b"PNG2")]
