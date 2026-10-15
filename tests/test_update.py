import subprocess
import sys
from pathlib import Path

import pytest

from mdeditor import update


def test_parse_and_compare_versions():
    assert update.parse_version('[project]\nname = "x"\nversion = "0.13.0"\n') == "0.13.0"
    assert update.parse_version("no version") is None
    assert update.is_newer("0.10.0", "0.9.2")
    assert not update.is_newer("0.12.0", "0.12.0")


def test_dev_run_is_not_auto_updated():
    assert update.install_kind() == "dev"  # 테스트는 .venv에서 돈다


def _fake_uv(tmp_path: Path, fail_upgrade: bool) -> tuple[Path, Path]:
    log = tmp_path / "uv.log"
    uv = tmp_path / "uv.cmd"
    fail = 'if "%2"=="upgrade" exit /b 1\r\n' if fail_upgrade else ""
    uv.write_text(f'@echo off\r\necho %*>>"{log}"\r\n{fail}exit /b 0\r\n', encoding="utf-8")
    return uv, log


def _run_script(tmp_path: Path, uv: Path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()  # 이미 끝난 mdEditor 대신
    script = tmp_path / "up.cmd"
    script.write_text(update.updater_script(uv, dead.pid, None), encoding="utf-8", newline="")
    subprocess.run(["cmd.exe", "/c", str(script)], stdin=subprocess.DEVNULL, capture_output=True, timeout=60)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 명령 창")
def test_updater_script_upgrades(tmp_path: Path):
    uv, log = _fake_uv(tmp_path, fail_upgrade=False)
    _run_script(tmp_path, uv)
    lines = log.read_text(encoding="utf-8").split("\n")
    assert lines[0].strip() == "tool upgrade markdown-editor"
    assert "install" not in log.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 명령 창")
def test_updater_script_reinstalls_when_upgrade_fails(tmp_path: Path):
    uv, log = _fake_uv(tmp_path, fail_upgrade=True)
    _run_script(tmp_path, uv)
    text = log.read_text(encoding="utf-8")
    assert "tool upgrade markdown-editor" in text
    assert "tool install --force git+https://github.com/KimJin777/markDown" in text
