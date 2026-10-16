from pathlib import Path

from mdeditor import autosave
from mdeditor.app import render_delay


def test_snapshot_roundtrip(tmp_path: Path):
    folder = autosave.backup_dir(tmp_path)
    docs = [(r"C:\문서\보고서.md", "보고서.md", "# 고치던 내용\n한글도 그대로"), (None, "새 문서 1", "저장 안 한 글")]
    autosave.write_snapshot(folder, docs)
    got = autosave.read_snapshot(folder)
    assert [(e["path"], e["name"], e["text"]) for e in got] == docs
    # 다시 쓰면 지난 백업 파일은 치워지고 새 내용만 남는다
    autosave.write_snapshot(folder, [(None, "새 문서 2", "둘째")])
    got = autosave.read_snapshot(folder)
    assert len(got) == 1 and got[0]["text"] == "둘째"
    assert len(list(folder.glob("bak-*.md"))) == 1
    autosave.clear(folder)
    assert autosave.read_snapshot(folder) == [] and not list(folder.glob("bak-*.md"))


def test_read_snapshot_missing_or_broken(tmp_path: Path):
    folder = autosave.backup_dir(tmp_path)
    assert autosave.read_snapshot(folder) == []  # 백업 폴더가 없음
    folder.mkdir(parents=True)
    (folder / autosave.INDEX).write_text("{깨진 json", encoding="utf-8")
    assert autosave.read_snapshot(folder) == []


def test_render_delay_grows_with_size():
    assert render_delay(1_000) == 150
    assert render_delay(100_000) == 300
    assert render_delay(500_000) == 600
