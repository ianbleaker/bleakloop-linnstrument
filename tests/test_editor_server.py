"""The editor's server over real sockets, polled as Live's display tick polls it."""

import json
import socket
import tomllib

import pytest

from BleakLoop.core import buttons, layout
from BleakLoop.editor import server


@pytest.fixture
def editor(tmp_path):
    user = tmp_path / "User Library" / "BleakLoop" / "buttons.toml"

    def reload():
        try:
            buttons.reload(buttons.PATH, user)
        except ValueError as error:
            return str(error)
        return None

    routes = server.Editor(0, reload, user_path=user)
    instance = server.Server(0, lambda request: routes.handle(request))
    routes.hosts = {f"127.0.0.1:{instance.port}", f"localhost:{instance.port}"}
    instance.user = user
    yield instance
    instance.close()
    buttons.reload(buttons.PATH)


def _exchange(instance, raw):
    client = socket.create_connection((server.HOST, instance.port))
    client.setblocking(False)
    try:
        client.sendall(raw)
    except OSError:
        pass
    received = b""
    for _ in range(20000):
        instance.poll()
        try:
            chunk = client.recv(65536)
        except BlockingIOError:
            continue
        except ConnectionResetError:
            break
        if not chunk:
            break
        received += chunk
    client.close()
    head, _, body = received.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    headers = dict(line.lower().split(": ", 1) for line in lines[1:])
    return int(lines[0].split()[1]), headers, body


def _request(instance, method, path, body=b"", host=None, **headers):
    host = host or f"127.0.0.1:{instance.port}"
    lines = [f"{method} {path} HTTP/1.1", f"Host: {host}", f"Content-Length: {len(body)}"]
    lines += [f"{name.replace('_', '-')}: {value}" for name, value in headers.items()]
    return _exchange(instance, ("\r\n".join(lines) + "\r\n\r\n").encode() + body)


def _save(instance, overlay, **headers):
    body = json.dumps({"overlay": overlay}).encode()
    headers.setdefault("Content_Type", "application/json")
    return _request(instance, "POST", "/api/save", body, **headers)


def test_get_routes_return_their_content_types(editor):
    status, headers, body = _request(editor, "GET", "/")
    assert status == 200 and headers["content-type"].startswith("text/html")
    assert headers["connection"] == "close"
    status, headers, body = _request(editor, "GET", "/api/layout")
    assert status == 200 and headers["content-type"].startswith("application/json")
    layout_data = json.loads(body)
    assert {"sections", "functions", "system", "overlay"} <= set(layout_data)
    assert _request(editor, "GET", "/nope")[0] == 404
    assert editor.connections == []


def test_a_foreign_host_is_refused(editor):
    assert _request(editor, "GET", "/api/layout", host=f"evil.example:{editor.port}")[0] == 403


def test_a_post_that_isnt_json_is_refused(editor):
    status, _, _ = _save(editor, {}, Content_Type="text/plain")
    assert status == 415
    assert not editor.user.exists()


def test_a_cross_site_origin_is_refused(editor):
    assert _save(editor, {}, Origin="http://evil.example")[0] == 403
    assert _save(editor, {}, Origin=f"http://127.0.0.1:{editor.port}")[0] == 200


def test_a_request_over_256_kb_is_refused(editor):
    body = b"x" * (server.MAX_REQUEST + 1)
    status, _, _ = _request(editor, "POST", "/api/save", body, Content_Type="application/json")
    assert status == 413


def test_a_valid_save_writes_the_file_and_moves_the_button(editor):
    overlay = {"global": {"metronome": {"pad": [1, 5]}, "fixed_length": {"pad": [1, 4]}}}
    status, _, body = _save(editor, overlay)
    assert status == 200
    assert tomllib.loads(editor.user.read_text(encoding="utf-8")) == {**overlay, "format": 2}
    assert layout.GLOBAL.metronome == (1, 5)
    assert json.loads(body)["overlay"] == {**overlay, "format": 2}


def test_an_invalid_save_returns_the_error_and_writes_nothing(editor):
    status, _, body = _save(editor, {"global": {"metronome": {"pad": [1, 1]}}})
    assert status == 400
    assert "taken by" in json.loads(body)["error"]
    assert not editor.user.exists()
    assert layout.GLOBAL.metronome == (1, 4)


def test_reset_deletes_the_user_file(editor):
    _save(editor, {"global": {"metronome": {"pad": [1, 5]}, "fixed_length": {"pad": [1, 4]}}})
    status, _, _ = _request(editor, "POST", "/api/reset", b"{}", Content_Type="application/json")
    assert status == 200
    assert not editor.user.exists()
    assert layout.GLOBAL.metronome == (1, 4)


def test_a_save_over_a_user_file_that_doesnt_load_keeps_a_backup(editor):
    editor.user.parent.mkdir(parents=True)
    editor.user.write_text('[global.metronome]\npad = [1, 1]\n', encoding="utf-8")
    status, _, body = _request(editor, "GET", "/api/layout")
    assert "taken by" in json.loads(body)["user_problem"]
    overlay = {"global": {"metronome": {"pad": [1, 5]}, "fixed_length": {"pad": [1, 4]}}}
    status, _, body = _save(editor, overlay)
    backup = editor.user.with_name("buttons.toml.bak")
    assert status == 200 and json.loads(body)["backup"] == str(backup)
    assert backup.read_text(encoding="utf-8") == '[global.metronome]\npad = [1, 1]\n'
    assert tomllib.loads(editor.user.read_text(encoding="utf-8")) == {**overlay, "format": 2}


def test_a_save_over_a_user_file_that_loads_makes_no_backup(editor):
    _save(editor, {"global": {"metronome": {"pad": [1, 5]}, "fixed_length": {"pad": [1, 4]}}})
    status, _, body = _save(editor, {})
    assert status == 200 and json.loads(body)["backup"] is None
    assert not editor.user.with_name("buttons.toml.bak").exists()


def test_a_reset_of_a_user_file_that_doesnt_load_keeps_a_backup(editor):
    editor.user.parent.mkdir(parents=True)
    editor.user.write_text("not toml [", encoding="utf-8")
    status, _, _ = _request(editor, "POST", "/api/reset", b"{}", Content_Type="application/json")
    assert status == 200 and not editor.user.exists()
    assert editor.user.with_name("buttons.toml.bak").read_text(encoding="utf-8") == "not toml ["


def test_a_response_bigger_than_one_send_arrives_whole(tmp_path):
    big = b"y" * (4 * 1024 * 1024)
    instance = server.Server(0, lambda request: server.response(200, "text/plain", big))
    try:
        status, headers, body = _exchange(instance, b"GET / HTTP/1.1\r\n\r\n")
    finally:
        instance.close()
    assert status == 200 and body == big


def test_a_request_in_pieces_is_buffered():
    assert server._parse(b"POST / HTTP/1.1\r\nContent-Length: 4\r\n\r\nab") is None
    request = server._parse(b"POST / HTTP/1.1\r\nContent-Length: 4\r\n\r\nabcd")
    assert (request.method, request.path, request.body) == ("POST", "/", b"abcd")


def test_the_atomic_write_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "deep" / "buttons.toml"
    server.write_atomic(path, "a = 1\n")
    assert path.read_text() == "a = 1\n"
    assert [p.name for p in path.parent.iterdir()] == ["buttons.toml"]


def test_a_failing_handler_answers_500():
    def broken(request):
        raise RuntimeError("bug")

    instance = server.Server(0, broken)
    try:
        assert _exchange(instance, b"GET / HTTP/1.1\r\n\r\n")[0] == 500
    finally:
        instance.close()
