import subprocess
import sys
import time
import uuid

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer

from mdeditor import single

# 두 번째로 실행된 mdEditor처럼 다른 프로세스에서 보낸다(Windows는 같은 프로그램 안 스레드끼리는 잘 안 됨)
SENDER = (
    "import sys, json; from PySide6.QtCore import QCoreApplication; from mdeditor import single; "
    "app = QCoreApplication([]); "
    "print(single.send_to_running(json.loads(sys.argv[2]), name=sys.argv[1], reply_ms=int(sys.argv[3])))"
)


def _send_from_other_process(app, name: str, paths: list[str], reply_ms: int = 3000) -> str:
    import json

    p = subprocess.Popen(
        [sys.executable, "-c", SENDER, name, json.dumps(paths), str(reply_ms)], stdout=subprocess.PIPE, text=True
    )
    end = time.time() + 15
    while p.poll() is None and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(5):
        app.processEvents()
        time.sleep(0.02)
    return p.stdout.read().strip()


def test_second_launch_hands_paths_to_running_one():
    app = QCoreApplication.instance() or QCoreApplication([])
    name = f"mdEditor-test-{uuid.uuid4().hex}"
    got: list = []
    assert not single.send_to_running(["x"], name=name, timeout_ms=200)  # 아직 아무것도 안 켜짐
    server = single.listen(got.append, name=name)
    assert server is not None
    try:
        assert _send_from_other_process(app, name, [r"C:\문서\가.md", "b.md"]) == "True"
    finally:
        server.close()
    assert got == [[r"C:\문서\가.md", "b.md"]]


def test_no_answer_means_start_own_window():
    """켜져 있는 쪽이 멈춰서 대답이 없으면 넘긴 것으로 치지 않는다(새 창을 띄우게)."""
    app = QCoreApplication.instance() or QCoreApplication([])
    name = f"mdEditor-test-{uuid.uuid4().hex}"
    mute = QLocalServer()
    assert mute.listen(name)  # 연결은 받지만 대답하지 않는다
    try:
        assert _send_from_other_process(app, name, ["a.md"], reply_ms=300) == "False"
    finally:
        mute.close()
