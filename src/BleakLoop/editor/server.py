"""A small HTTP server on 127.0.0.1, polled from Live's display tick: no threads, as
http.server blocks. Each connection reads into a buffer until its request is complete, and its
response goes out over the following ticks. Every response closes the connection."""

import socket
import time

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
                connection.outgoing = self.handle(request)
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


def placeholder(request):
    # Item 4's go/no-go answer, until the editor's routes replace it.
    if request.method == "GET" and request.path == "/":
        return response(200, "text/plain; charset=utf-8", "BleakLoop editor OK")
    return response(404, "text/plain; charset=utf-8", "Not Found")
