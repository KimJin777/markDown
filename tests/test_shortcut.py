import sys
from pathlib import Path

import pytest

from mdeditor import shortcut


def test_dev_run_makes_no_shortcut():
    # 개발용(.venv 안) 실행에서는 바로가기를 만들지 않는다
    assert shortcut.launcher_path() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 바로가기")
def test_create_shortcut(tmp_path: Path):
    lnk = shortcut.create(tmp_path, Path(r"C:\Windows\notepad.exe"))
    assert lnk == tmp_path / "mdEditor.lnk" and lnk.stat().st_size > 0
