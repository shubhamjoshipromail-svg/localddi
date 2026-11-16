"""The downloader, exercised against a local HTTP server (loopback only)."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from localddi import download

PAYLOAD = bytes(range(256)) * 400  # 102,400 bytes


class FlakyHandler(BaseHTTPRequestHandler):
    """Sends half the file and drops the connection on the first request, then honours Range."""

    requests: list[str | None] = []

    def do_GET(self):  # noqa: N802
        if self.path == "/missing":
            self.send_error(404)
            return
        range_header = self.headers.get("Range")
        type(self).requests.append(range_header)
        if range_header:
            start = int(range_header.removeprefix("bytes=").rstrip("-"))
            body = PAYLOAD[start:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        else:
            body = PAYLOAD
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if len(type(self).requests) == 1:
            self.wfile.write(body[: len(body) // 2])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def server(monkeypatch):
    monkeypatch.setattr(download.time, "sleep", lambda _: None)
    FlakyHandler.requests = []
    httpd = HTTPServer(("127.0.0.1", 0), FlakyHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_fetch_resumes_after_a_dropped_connection(server, tmp_path):
    dest = download.fetch(f"{server}/file.zip", tmp_path / "file.zip")
    assert dest.read_bytes() == PAYLOAD
    assert not (tmp_path / "file.zip.part").exists()
    assert FlakyHandler.requests[0] is None
    assert FlakyHandler.requests[1] == f"bytes={len(PAYLOAD) // 2}-"


def test_fetch_gives_up_with_a_clear_error(server, tmp_path):
    with pytest.raises(RuntimeError, match="could not download"):
        download.fetch(f"{server}/missing", tmp_path / "x", retries=2)
    assert not (tmp_path / "x").exists()


def test_cached_files_are_not_downloaded_again(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("should have used the cache")

    monkeypatch.setattr(download, "fetch", refuse)
    (tmp_path / "RxNorm_full_prescribe_current.zip").write_bytes(b"cached")
    assert download.fetch_rxnorm(tmp_path).read_bytes() == b"cached"
    (tmp_path / "ddinter").mkdir()
    for name in download.DDINTER_FILES:
        (tmp_path / "ddinter" / name).write_text("cached")
    assert download.fetch_ddinter(tmp_path) == tmp_path / "ddinter"
    assert len(download.DDINTER_FILES) == 14


def test_unlinked_ddinter_files_are_optional(tmp_path, monkeypatch):
    def fake_fetch(url, dest, **kwargs):
        if dest.name in download.DDINTER_UNLINKED:
            raise RuntimeError("404")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("x")
        return dest

    monkeypatch.setattr(download, "fetch", fake_fetch)
    target = download.fetch_ddinter(tmp_path)
    assert sorted(p.name for p in target.iterdir()) == sorted(download.DDINTER_LINKED)


def test_linked_ddinter_files_are_required(tmp_path, monkeypatch):
    def fake_fetch(url, dest, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(download, "fetch", fake_fetch)
    with pytest.raises(RuntimeError):
        download.fetch_ddinter(tmp_path)


def test_linked_only_removes_cached_unlinked_files(tmp_path, monkeypatch):
    (tmp_path / "ddinter").mkdir()
    for name in download.DDINTER_FILES:
        (tmp_path / "ddinter" / name).write_text("cached")
    monkeypatch.setattr(download, "fetch", lambda *a, **k: None)
    target = download.fetch_ddinter(tmp_path, linked_only=True)
    assert sorted(p.name for p in target.iterdir()) == sorted(download.DDINTER_LINKED)
