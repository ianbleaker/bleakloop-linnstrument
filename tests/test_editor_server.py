"""The editor's server answers over real sockets, polled as Live's display tick polls it."""

import socket

import pytest

from BleakLoop.editor import server


@pytest.fixture
def running():
    instance = server.Server(0, server.placeholder)
    yield instance
    instance.close()


def _exchange(instance, raw):
    client = socket.create_connection((server.HOST, instance.port))
    client.setblocking(False)
    client.sendall(raw)
    received = b""
    for _ in range(2000):
        instance.poll()
        try:
            chunk = client.recv(65536)
        except BlockingIOError:
            continue
        if not chunk:
            break
        received += chunk
    client.close()
    return received


def test_get_root_answers_and_closes(running):
    reply = _exchange(running, b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
    assert reply.startswith(b"HTTP/1.1 200 OK\r\n")
    assert b"Connection: close" in reply
    assert reply.endswith(b"BleakLoop editor OK")
    assert running.connections == []


def test_an_unknown_path_is_404(running):
    assert _exchange(running, b"GET /nope HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 404")


def test_a_request_in_pieces_is_buffered():
    assert server._parse(b"POST / HTTP/1.1\r\nContent-Length: 4\r\n\r\nab") is None
    request = server._parse(b"POST / HTTP/1.1\r\nContent-Length: 4\r\n\r\nabcd")
    assert (request.method, request.path, request.body) == ("POST", "/", b"abcd")
