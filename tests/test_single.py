import threading
import uuid

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from mdeditor import single


def test_second_launch_hands_paths_to_running_one():
    app = QCoreApplication.instance() or QCoreApplication([])
    name = f"mdEditor-test-{uuid.uuid4().hex}"
    got: list = []
    loop = QEventLoop()

    def on_paths(paths):
        got.append(paths)
        loop.quit()

    assert not single.send_to_running(["x"], name=name, timeout_ms=200)  # 아직 아무것도 안 켜짐
    server = single.listen(on_paths, name=name)
    assert server is not None
    sent = []
    t = threading.Thread(target=lambda: sent.append(single.send_to_running([r"C:\문서\가.md", "b.md"], name=name)))
    t.start()
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    t.join(5)
    server.close()
    assert sent == [True]
    assert got == [[r"C:\문서\가.md", "b.md"]]
    assert app is not None
