"""'.md 파일을 mdEditor로 열기' 등록 — 지금 사용자(HKCU)의 레지스트리만 쓴다(관리자 권한 필요 없음).

Windows 10/11은 프로그램이 '기본 앱'을 직접 바꾸지 못하게 막아 두었다. 그래서 여기서는 mdEditor를
'연결 프로그램' 목록에 올리기만 하고, 마지막 '항상' 선택은 사용자가 한 번 고른다.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROG_ID = "mdEditor.md"
EXTENSIONS = (".md", ".markdown", ".mdown")
CLASSES = r"Software\Classes"


def registry_entries(exe: Path, icon: Path | None) -> list[tuple[str, str, str | None]]:
    """(키, 값 이름, 값) 목록. 값 이름 ''는 기본값, 값 None은 빈 표시(REG_NONE)."""
    open_cmd = f'"{exe}" "%1"'
    entries = [
        (rf"{PROG_ID}", "", "마크다운 문서"),
        (rf"{PROG_ID}\DefaultIcon", "", f"{icon or exe},0"),
        (rf"{PROG_ID}\shell\open\command", "", open_cmd),
        (rf"Applications\{exe.name}", "FriendlyAppName", "mdEditor"),
        (rf"Applications\{exe.name}\shell\open\command", "", open_cmd),
    ]
    for ext in EXTENSIONS:
        entries.append((rf"{ext}\OpenWithProgids", PROG_ID, None))
        entries.append((rf"Applications\{exe.name}\SupportedTypes", ext, ""))
    return entries


def _notify() -> None:
    """탐색기에 '연결이 바뀌었다'고 알린다(아이콘·연결 프로그램 목록을 새로 읽게)."""
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except (AttributeError, OSError):
        pass


def register(exe: Path, icon: Path | None = None, root: str = CLASSES) -> None:
    import winreg

    for key, name, value in registry_entries(exe, icon):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{root}\{key}") as k:
            if value is None:
                winreg.SetValueEx(k, name, 0, winreg.REG_NONE, b"")
            else:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
    _notify()


def _delete_tree(winreg, root, path: str) -> None:
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(winreg, root, rf"{path}\{sub}")
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def unregister(exe_name: str = "mdEditor.exe", root: str = CLASSES) -> None:
    """등록한 것만 지운다(.md 키 자체나 다른 프로그램 연결은 건드리지 않음)."""
    import winreg

    hk = winreg.HKEY_CURRENT_USER
    _delete_tree(winreg, hk, rf"{root}\{PROG_ID}")
    _delete_tree(winreg, hk, rf"{root}\Applications\{exe_name}")
    for ext in EXTENSIONS:
        try:
            with winreg.OpenKey(hk, rf"{root}\{ext}\OpenWithProgids", 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, PROG_ID)
        except FileNotFoundError:
            pass
    _notify()


def is_registered(root: str = CLASSES) -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{root}\{PROG_ID}\shell\open\command"):
            return True
    except FileNotFoundError:
        return False


def open_with_dialog(path: Path, hwnd: int = 0) -> bool:
    """Windows '이 파일을 어떻게 여시겠어요?' 창을 띄운다(정식 API SHOpenWithDialog).
    창이 떴으면 True(사용자가 취소해도 True), 못 띄웠으면 False.
    예전의 rundll32 OpenAs_RunDLL은 최신 Windows 11에서 조용히 무시되어 이 API를 쓴다."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class _OpenAsInfo(ctypes.Structure):
        _fields_ = [("pcszFile", wintypes.LPCWSTR), ("pcszClass", wintypes.LPCWSTR), ("oaifInFlags", ctypes.c_int)]

    # 등록 허용 | '항상' 선택을 확장자에 등록 | 고른 프로그램으로 바로 열기
    flags = 0x1 | 0x2 | 0x4
    try:
        res = ctypes.windll.shell32.SHOpenWithDialog(hwnd, ctypes.byref(_OpenAsInfo(str(path), None, flags)))
    except (AttributeError, OSError):
        return False
    return (res & 0xFFFFFFFF) in (0, 0x800704C7)  # S_OK 또는 사용자가 취소함(창은 떴음)


# ---------- 탐색기 폴더 오른쪽 클릭 메뉴 ('mdEditor로 열기') ----------
FOLDER_KEY = r"Directory\shell\mdEditor"
FOLDER_MENU = "mdEditor로 열기"


def folder_menu_entries(exe: Path, icon: Path | None) -> list[tuple[str, str, str]]:
    """(키, 값 이름, 값) — 폴더를 오른쪽 클릭하면 'mdEditor로 열기'가 나오고, 누르면 그 폴더가 넘어온다."""
    return [
        (FOLDER_KEY, "", FOLDER_MENU),
        (FOLDER_KEY, "Icon", f"{icon or exe},0"),
        (rf"{FOLDER_KEY}\command", "", f'"{exe}" "%1"'),
    ]


def register_folder_menu(exe: Path, icon: Path | None = None, root: str = CLASSES) -> None:
    import winreg

    for key, name, value in folder_menu_entries(exe, icon):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{root}\{key}") as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
    _notify()


def unregister_folder_menu(root: str = CLASSES) -> None:
    import winreg

    _delete_tree(winreg, winreg.HKEY_CURRENT_USER, rf"{root}\{FOLDER_KEY}")
    _notify()


def folder_menu_registered(root: str = CLASSES) -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{root}\{FOLDER_KEY}\command"):
            return True
    except FileNotFoundError:
        return False
