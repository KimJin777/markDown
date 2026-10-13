"""한 번만 실행: 이미 켜져 있으면 새 창을 띄우지 않고 그 창에 파일을 넘긴다(.md 더블클릭 등).

넘기는 쪽은 경로 목록(JSON)과 줄바꿈을 보내고, 받는 쪽이 'ok'라고 대답해야 넘긴 것으로 친다.
켜져 있는 mdEditor가 멈춰 있어 대답이 없으면 넘기지 않고 새 창을 띄운다(창이 안 뜨는 일 방지).
"""

from __future__ import annotations

import getpass
import json
from typing import Callable

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

ACK = b"ok\n"


def server_name() -> str:
    return f"mdEditor-{getpass.getuser()}"  # 사용자마다 따로


def send_to_running(paths: list[str], name: str | None = None, timeout_ms: int = 1000, reply_ms: int = 3000) -> bool:
    """켜져 있는 mdEditor에 파일 경로를 넘긴다. 받았다는 대답이 오면 True(이 프로그램은 끝내면 된다)."""
    sock = QLocalSocket()
    sock.connectToServer(name or server_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    try:  # 켜져 있는 창이 앞으로 나올 수 있게 허락한다(Windows는 배경 프로그램이 앞으로 나오는 것을 막는다)
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except (AttributeError, OSError):
        pass
    sock.write(json.dumps(paths).encode("utf-8") + b"\n")
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    reply = bytearray()
    while not reply.endswith(b"\n") and sock.waitForReadyRead(reply_ms):
        reply.extend(bytes(sock.readAll()))
    sock.disconnectFromServer()
    if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        sock.waitForDisconnected(timeout_ms)
    return bytes(reply) == ACK


def listen(on_paths: Callable[[list[str]], None], name: str | None = None, parent=None) -> QLocalServer | None:
    """다른 mdEditor가 넘기는 파일을 받는다. 받으면 대답하고 on_paths(경로 목록)."""
    server = QLocalServer(parent)
    name = name or server_name()
    if not server.listen(name):
        QLocalServer.removeServer(name)  # 비정상 종료로 남은 이름 정리 후 한 번 더
        if not server.listen(name):
            return None

    def on_connection() -> None:
        while (sock := server.nextPendingConnection()) is not None:
            buf = bytearray()
            sock.disconnected.connect(sock.deleteLater)

            def read(s=sock, b=buf) -> None:
                b.extend(bytes(s.readAll()))
                if not b.endswith(b"\n"):
                    return  # 아직 다 안 옴
                try:
                    paths = json.loads(b.decode("utf-8") or "[]")
                except ValueError:
                    paths = None
                b.clear()
                if not isinstance(paths, list):
                    return
                s.write(ACK)  # 먼저 대답하고(넘기는 쪽이 오래 기다리지 않게) 파일은 다음 차례에 연다
                s.flush()
                s.waitForBytesWritten(1000)
                QTimer.singleShot(0, lambda p=[x for x in paths if isinstance(x, str)]: on_paths(p))

            sock.readyRead.connect(read)
            if sock.bytesAvailable():  # 연결과 함께 벌써 와 있던 것(readyRead가 다시 오지 않음)
                read()

    server.newConnection.connect(on_connection)
    return server
