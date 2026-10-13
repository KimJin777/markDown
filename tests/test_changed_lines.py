from mdeditor.app import changed_lines


def test_changed_and_inserted_lines_in_new_text():
    old = "a\nb\nc\nd"
    new = "a\nB\nc\nnew\nd"
    assert changed_lines(old, new) == [1, 3]


def test_deleted_only_and_same_text():
    assert changed_lines("a\nb\nc", "a\nc") == []
    assert changed_lines("x\ny", "x\ny") == []
