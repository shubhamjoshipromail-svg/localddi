"""The server must answer without touching the network."""

import socket

import pytest


@pytest.fixture()
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the server tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_queries_work_with_the_network_blocked(client, no_network):
    assert client.get("/").status_code == 200
    body = client.get("/v1/interactions", params={"drugs": "warfarin,aspirin"}).json()
    assert body["summary"]["interactions_found"] == 1
    assert client.get("/v1/drugs/resolve", params={"name": "warfarine"}).status_code == 200
    assert "fullInteractionTypeGroup" in client.get("/REST/interaction/list.json?rxcuis=11289+1191").json()
    assert client.get("/REST/interaction/interaction.json?rxcui=11289").status_code == 200
    assert client.get("/v1/status").status_code == 200


def test_no_model_or_http_client_dependencies():
    """The package depends on FastAPI and uvicorn only: no LLM SDK, no HTTP client."""
    from importlib.metadata import PackageNotFoundError, requires

    try:
        requires("localddi")
    except PackageNotFoundError:
        pytest.skip("localddi is not installed (run pip install -e .)")
    declared = " ".join(req for req in requires("localddi") or [] if "extra ==" not in req).lower()
    for forbidden in ("anthropic", "openai", "requests", "httpx"):
        assert forbidden not in declared


def test_app_module_has_no_network_imports():
    from pathlib import Path

    import localddi

    package = Path(localddi.__file__).parent
    for name in ("app.py", "engine.py", "nlm.py", "db.py", "textnorm.py"):
        source = (package / name).read_text(encoding="utf-8")
        for needle in ("urllib", "httpx", "requests", "socket", "anthropic", "openai", "download"):
            assert needle not in source, f"{name} mentions {needle}"
