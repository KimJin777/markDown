import sys
from pathlib import Path

import pytest

from mdeditor import fileassoc

EXE = Path(r"C:\Users\u\.local\bin\mdEditor.exe")
TEST_ROOT = r"Software\mdEditorTest\Classes"  # 진짜 연결(Software\Classes)은 건드리지 않는다
TEST_SOFT = r"Software\mdEditorTest\Soft"  # 진짜 Software\mdEditor·RegisteredApplications도 건드리지 않는다


def test_entries_open_with_quoted_path():
    entries = {(k, n): v for k, n, v in fileassoc.registry_entries(EXE, Path(r"C:\x\icon.ico"))}
    assert entries[(r"mdEditor.md\shell\open\command", "")] == f'"{EXE}" "%1"'
    assert entries[(r"mdEditor.md\DefaultIcon", "")] == r"C:\x\icon.ico,0"
    for ext in (".md", ".markdown", ".mdown"):
        assert (rf"{ext}\OpenWithProgids", "mdEditor.md") in entries


def test_capability_entries_register_default_app_list():
    """Windows 설정 '기본 앱' 목록 등록(Windows 11에서 '항상'은 설정에서만 고를 수 있음)."""
    entries = {(k, n): v for k, n, v in fileassoc.capability_entries()}
    cap = r"Software\mdEditor\Capabilities"
    assert entries[(cap, "ApplicationName")] == "mdEditor"
    assert entries[(r"Software\RegisteredApplications", "mdEditor")] == cap
    for ext in (".md", ".markdown", ".mdown"):
        assert entries[(rf"{cap}\FileAssociations", ext)] == "mdEditor.md"


def test_folder_menu_entries_open_folder():
    entries = {(k, n): v for k, n, v in fileassoc.folder_menu_entries(EXE, Path(r"C:\x\icon.ico"))}
    assert entries[(r"Directory\shell\mdEditor", "")] == "mdEditor로 열기"
    assert entries[(r"Directory\shell\mdEditor", "Icon")] == r"C:\x\icon.ico,0"
    assert entries[(r"Directory\shell\mdEditor\command", "")] == f'"{EXE}" "%1"'


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 레지스트리")
def test_folder_menu_register_and_unregister_roundtrip():
    import winreg

    try:
        fileassoc.register_folder_menu(EXE, None, root=TEST_ROOT)
        assert fileassoc.folder_menu_registered(root=TEST_ROOT)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{TEST_ROOT}\Directory\shell\mdEditor\command") as k:
            assert winreg.QueryValueEx(k, "")[0] == f'"{EXE}" "%1"'
        fileassoc.unregister_folder_menu(root=TEST_ROOT)
        assert not fileassoc.folder_menu_registered(root=TEST_ROOT)
    finally:
        fileassoc._delete_tree(winreg, winreg.HKEY_CURRENT_USER, r"Software\mdEditorTest")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 레지스트리")
def test_register_and_unregister_roundtrip():
    import winreg

    try:
        fileassoc.register(EXE, None, root=TEST_ROOT, software=TEST_SOFT)
        assert fileassoc.is_registered(root=TEST_ROOT)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{TEST_ROOT}\.md\OpenWithProgids") as k:
            assert winreg.QueryValueEx(k, "mdEditor.md")[1] == winreg.REG_NONE
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{TEST_SOFT}\RegisteredApplications") as k:
            assert winreg.QueryValueEx(k, "mdEditor")[0] == rf"{TEST_SOFT}\mdEditor\Capabilities"
        fileassoc.unregister(root=TEST_ROOT, software=TEST_SOFT)
        assert not fileassoc.is_registered(root=TEST_ROOT)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{TEST_ROOT}\.md\OpenWithProgids") as k:
            with pytest.raises(FileNotFoundError):
                winreg.QueryValueEx(k, "mdEditor.md")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{TEST_SOFT}\RegisteredApplications") as k:
            with pytest.raises(FileNotFoundError):
                winreg.QueryValueEx(k, "mdEditor")
    finally:
        fileassoc._delete_tree(winreg, winreg.HKEY_CURRENT_USER, r"Software\mdEditorTest")
