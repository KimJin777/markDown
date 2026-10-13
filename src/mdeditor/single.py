"""한 번만 실행: 이미 켜져 있으면 새 창을 띄우지 않고 그 창에 파일을 넘긴다(.md 더블클릭 등)."""

from __future__ import annotations

import getpass
import json
from typing import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name() -> str:
    return f"mdEditor-{getpass.getuser()}"  # 사용자마다 따로


def send_to_running(paths: list[str], name: str | None = None, timeout_ms: int = 1000) -> bool:
    """켜져 있는 mdEditor에 파일 경로를 넘긴다. 넘겼으면 True(이 프로그램은 끝내면 된다)."""
    sock = QLocalSocket()
    sock.connectToServer(name or server_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    try:  # 켜져 있는 창이 앞으로 나올 수 있게 허락한다(Windows는 배경 프로그램이 앞으로 나오는 것을 막는다)
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except (AttributeError, OSError):
        pass
    sock.write(json.dumps(paths).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        sock.waitForDisconnected(timeout_ms)
    return True


def listen(on_paths: Callable[[list[str]], None], name: str | None = None, parent=None) -> QLocalServer | None:
    """다른 mdEditor가 넘기는 파일을 받는다. 받으면 on_paths(경로 목록)."""
    server = QLocalServer(parent)
    name = name or server_name()
    if not server.listen(name):
        QLocalServer.removeServer(name)  # 비정상 종료로 남은 이름 정리 후 한 번 더
        if not server.listen(name):
            return None

    def on_connection() -> None:
        while (sock := server.nextPendingConnection()) is not None:
            buf = bytearray()

            def read(s=sock, b=buf) -> None:
                b.extend(bytes(s.readAll()))

            def done(s=sock, b=buf) -> None:
                read(s, b)
                s.deleteLater()
                try:
                    paths = json.loads(b.decode("utf-8") or "[]")
                except ValueError:
                    return
                on_paths([p for p in paths if isinstance(p, str)])

            sock.readyRead.connect(read)
            sock.disconnected.connect(done)

    server.newConnection.connect(on_connection)
    return server
