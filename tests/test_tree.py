from pathlib import Path

from mdeditor.app import Doc, add_root, tree_of

R = Path("C:/proj")


def shape(nodes: list) -> list:
    return [(n[1].name, shape(n[2])) if n[0] == "dir" else n[1].name for n in nodes]


def test_add_root_merges_nested_folders():
    roots = add_root([], R / "docs")
    assert add_root(roots, R / "docs" / "sub") == [R / "docs"]  # 이미 올린 폴더 안
    assert add_root(roots + [Path("D:/x")], R) == [Path("D:/x"), R]  # 새 폴더가 기존 폴더를 품음


def test_tree_keeps_subfolders_and_loose_files_on_top():
    docs = [
        Doc(path=Path("D:/loose/메모.md")),
        Doc(path=R / "b.md"),
        Doc(path=R / "sub2" / "문서10.md"),
        Doc(path=R / "sub2" / "문서2.md"),
        Doc(path=R / "sub1" / "deep" / "x.json"),
        Doc(path=None, untitled_no=1),
    ]
    tree = tree_of(docs, [R], "name")
    # 폴더가 먼저(이름순), 그다음 낱개 파일(정렬 기준대로). 빈 폴더 단계도 하위 폴더 모양 그대로
    assert shape(tree) == [
        ("proj", [("sub1", [("deep", ["x.json"])]), ("sub2", ["문서2.md", "문서10.md"]), "b.md"]),
        "메모.md",
        "새 문서 1",
    ]


def test_tree_without_roots_is_flat_list_in_sort_order():
    docs = [Doc(path=R / "b.md"), Doc(path=R / "a.md")]
    assert shape(tree_of(docs, [], "added")) == ["b.md", "a.md"]
    assert shape(tree_of(docs, [], "name", reverse=True)) == ["b.md", "a.md"]
