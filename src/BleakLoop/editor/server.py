"""A small HTTP server on 127.0.0.1, polled from Live's display tick: no threads, as
http.server blocks. Each connection reads into a buffer until its request is complete, and its
response goes out over the following ticks. Every response closes the connection."""

import json
import logging
import os
import shutil
import socket
import time
import tomllib
from pathlib import Path

from ..core import buttons, userfile

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
MAX_REQUEST = 256 * 1024
IDLE_SECONDS = 10  # a connection that stalls this long is dropped
ACCEPTS_PER_POLL = 8
CHUNK = 65536

REASONS = {
    200: "OK",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    500: "Internal Server Error",
}


class Request:
    def __init__(self, method, path, headers, body):
        self.method, self.path, self.headers, self.body = method, path, headers, body


def response(status, content_type, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    head = (
        f"HTTP/1.1 {status} {REASONS.get(status, '')}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n\r\n"
    )
    return head.encode("ascii") + body


def _parse(data):
    # The complete request, an error status, or None while more is to come.
    end = data.find(b"\r\n\r\n")
    if end < 0:
        return 413 if len(data) > MAX_REQUEST else None
    try:
        lines = data[:end].decode("iso-8859-1").split("\r\n")
        method, path, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
    except ValueError:
        return 400
    if length < 0:
        return 400
    if end + 4 + length > MAX_REQUEST:
        return 413
    body = data[end + 4 : end + 4 + length]
    if len(body) < length:
        return None
    return Request(method, path, headers, body)


class _Connection:
    def __init__(self, sock):
        self.sock = sock
        self.incoming = b""
        self.outgoing = None  # bytes still to send, once answered
        self.seen = time.monotonic()


class Server:
    """Answers each request with handle(request) -> response bytes."""

    def __init__(self, port, handle, host=HOST):
        self.handle = handle
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((host, port))
            self.sock.listen(8)
            self.sock.setblocking(False)
        except OSError:
            self.sock.close()
            raise
        self.port = self.sock.getsockname()[1]
        self.connections = []

    def poll(self):
        for _ in range(ACCEPTS_PER_POLL):
            try:
                sock, _ = self.sock.accept()
            except (BlockingIOError, InterruptedError):
                break
            sock.setblocking(False)
            self.connections.append(_Connection(sock))
        now = time.monotonic()
        for connection in list(self.connections):
            try:
                done = self._step(connection, now)
            except OSError:
                done = True
            if done:
                self._drop(connection)

    def _step(self, connection, now):
        # True once the connection is finished with.
        if connection.outgoing is None:
            while True:
                try:
                    data = connection.sock.recv(CHUNK)
                except (BlockingIOError, InterruptedError):
                    break
                if not data:
                    return True
                connection.incoming += data
                connection.seen = now
                if len(connection.incoming) > MAX_REQUEST:
                    break
            request = _parse(connection.incoming)
            if request is None:
                return now - connection.seen > IDLE_SECONDS
            if isinstance(request, int):
                connection.outgoing = response(request, "text/plain; charset=utf-8", REASONS[request])
            else:
                # A bug here must never reach Live's display tick.
                try:
                    connection.outgoing = self.handle(request)
                except Exception:
                    logger.exception("BleakLoop editor: %s %s failed", request.method, request.path)
                    connection.outgoing = response(500, "text/plain; charset=utf-8", REASONS[500])
        if connection.outgoing:
            try:
                sent = connection.sock.send(connection.outgoing)
            except (BlockingIOError, InterruptedError):
                sent = 0
            if sent:
                connection.outgoing = connection.outgoing[sent:]
                connection.seen = now
        return not connection.outgoing or now - connection.seen > IDLE_SECONDS

    def _drop(self, connection):
        self.connections.remove(connection)
        try:
            connection.sock.close()
        except OSError:
            pass

    def close(self):
        for connection in list(self.connections):
            self._drop(connection)
        self.sock.close()


PAGE = Path(__file__).parent / "index.html"
TEXT = "text/plain; charset=utf-8"


def _json(status, data):
    return response(status, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False))


def _error(status, message):
    return _json(status, {"error": message})


def write_atomic(path, text):
    # A temporary file in the same folder, then a rename: a reader sees the old file or the
    # new one, never half of one.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class Editor:
    """The editor's routes. Writes only to the user file it was given, never to a path from a
    request. on_change reloads the layout after a save or reset."""

    def __init__(self, port, on_change, shipped_path=None, user_path=None):
        self.port = port
        self.on_change = on_change
        self.shipped_path = shipped_path or buttons.PATH
        self.user_path = user_path or buttons.USER_PATH
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    def handle(self, request):
        # Another web page in the browser can reach 127.0.0.1 too: a foreign Host (DNS
        # rebinding) or Origin is refused, and a POST must be JSON, which a page on another
        # origin can't send without a preflight this server never grants.
        host = request.headers.get("host", "")
        if host not in self.hosts:
            return response(403, TEXT, "Forbidden")
        origin = request.headers.get("origin")
        if origin is not None and origin != f"http://{host}":
            return response(403, TEXT, "Forbidden")
        path = request.path.split("?", 1)[0]
        if request.method == "GET":
            if path == "/":
                return response(200, "text/html; charset=utf-8", PAGE.read_bytes())
            if path == "/api/layout":
                data = buttons.describe()
                data["user_problem"] = self._user_problem()
                return _json(200, data)
            return response(404, TEXT, "Not Found")
        if request.method != "POST":
            return response(405, TEXT, "Method Not Allowed")
        kind = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if kind != "application/json":
            return response(415, TEXT, "Unsupported Media Type")
        if path == "/api/save":
            return self._save(request.body)
        if path == "/api/reset":
            return self._reset()
        return response(404, TEXT, "Not Found")

    def _save(self, body):
        if self.user_path is None:
            return _error(400, "BleakLoop isn't installed in a Remote Scripts folder: no user file")
        try:
            overlay = json.loads(body.decode("utf-8"))["overlay"]
            if not isinstance(overlay, dict):
                raise ValueError("overlay: not an object")
            overlay = userfile.prune(overlay)
            text = userfile.to_toml(overlay)
            if tomllib.loads(text) != overlay:
                raise ValueError("the overlay doesn't survive being written as TOML")
            with open(self.shipped_path, "rb") as file:
                shipped = tomllib.load(file)
            merged, _ = userfile.merge(shipped, overlay, str(self.user_path))
            buttons.Registry(merged)
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) as error:
            message = str(error) if not isinstance(error, KeyError) else f"missing {error}"
            return _error(400, message)
        try:
            backup = self._back_up()
            write_atomic(self.user_path, text)
        except OSError as error:
            return _error(400, f"couldn't write {self.user_path}: {error.strerror}")
        return self._changed(backup)

    def _reset(self):
        backup = None
        if self.user_path is not None:
            try:
                backup = self._back_up()
                Path(self.user_path).unlink(missing_ok=True)
            except OSError as error:
                return _error(400, f"couldn't delete {self.user_path}: {error.strerror}")
        return self._changed(backup)

    def _user_problem(self):
        # Why the user file on disk doesn't load, or None. The editor then shows the layout
        # BleakLoop fell back to, without the file's changes.
        if self.user_path is None or not Path(self.user_path).exists():
            return None
        try:
            buttons.load(self.shipped_path, self.user_path)
        except (ValueError, OSError) as error:
            return str(error)
        return None

    def _back_up(self):
        # A user file that doesn't load isn't in the editor, so a save or reset would lose
        # it: it's copied to buttons.toml.bak first. Returns the copy's path, or None.
        if self._user_problem() is None:
            return None
        backup = Path(self.user_path).with_name(Path(self.user_path).name + ".bak")
        shutil.copyfile(self.user_path, backup)
        return str(backup)

    def _changed(self, backup=None):
        problem = self.on_change()
        if problem:
            return _error(400, problem)
        # The files as saved, even while the reload waits for a held pad.
        data = buttons.describe(buttons.load(self.shipped_path, self.user_path))
        data["user_problem"], data["backup"] = None, backup
        return _json(200, data)
