"""The try-it page is public, self-contained and available before importing data."""

import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from localddi import DISCLAIMER, REPO_URL
from localddi.app import create_app


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_home_is_html_with_disclaimer_and_offline_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert DISCLAIMER in response.text
    page = PageParser()
    page.feed(response.text)
    anchors = {attrs.get("href") for tag, attrs in page.tags if tag == "a"}
    assert {"/docs", REPO_URL} <= anchors
    for tag, attrs in page.tags:
        if tag != "a":
            for value in attrs.values():
                assert not re.search(r"https?://|^//", value or "")
        if tag == "script":
            assert "src" not in attrs
        if tag == "link":
            assert attrs.get("rel") not in {"stylesheet", "preload", "preconnect", "dns-prefetch"}
    styles = re.findall(r"<style>(.*?)</style>", response.text, re.DOTALL)
    assert styles
    assert not re.search(r"https?://|@import|url\s*\(", "\n".join(styles))


@pytest.mark.parametrize("key", [None, "private-key-never-in-html"])
def test_home_without_database_is_public(tmp_path, monkeypatch, key):
    if key:
        monkeypatch.setenv("LOCALDDI_API_KEY", key)
    else:
        monkeypatch.delenv("LOCALDDI_API_KEY", raising=False)
    database = tmp_path / "missing.sqlite"
    with TestClient(create_app(database)) as empty:
        response = empty.get("/")
        assert response.status_code == 200
        assert DISCLAIMER in response.text
        assert "localddi import --demo" in response.text
        assert "<code>localddi import</code>" in response.text
        assert empty.get("/v1/status").status_code == (401 if key else 503)
        if key:
            assert key not in response.text
    assert not database.exists()
