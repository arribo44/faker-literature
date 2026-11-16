"""HTTP checks of the local catalogue editor: hosts, origins and session cookie."""

import http.client
import json
import sys
import threading
from http.server import ThreadingHTTPServer

import editor
import pytest
import server

BOOK = {
    "author": {"wikidata_id": "Q999999", "name": {"fr_FR": "Murasaki Shikibu", "en_US": "Murasaki Shikibu"},
               "nationality": {"fr_FR": "japonais", "en_US": "Japanese"}},
    "book": {"wikidata_id": "Q193375", "title": {"fr_FR": "Le Dit du Genji", "en_US": "The Tale of Genji"},
             "year": "1008", "genre": {"fr_FR": "roman", "en_US": "novel"}, "pages": {}, "publisher": {}},
}


@pytest.fixture
def running(tmp_path, monkeypatch):
    catalogue = tmp_path / "literature.json"
    catalogue.write_bytes(editor.CATALOGUE_PATH.read_bytes())
    catalogue.chmod(0o644)
    monkeypatch.setattr(editor, "CATALOGUE_PATH", catalogue)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.EditorHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1], catalogue
    httpd.shutdown()
    httpd.server_close()


def _request(port, method, path, body=None, headers=None):
    headers = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response, data


def _session(port):
    response, _ = _request(port, "GET", "/")
    cookie = response.getheader("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    return cookie.split(";")[0]


def _post_book(port, cookie=None, **headers):
    headers = {"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {}), **headers}
    return _request(port, "POST", "/api/books", json.dumps(BOOK), headers)


def test_page_sets_the_session_cookie_and_api_requires_it(running):
    port, _ = running

    response, data = _request(port, "GET", "/api/catalogue")
    assert response.status == 403 and "rechargez la page" in json.loads(data)["error"]

    response, _ = _request(port, "GET", "/api/catalogue", headers={"Cookie": "editor_session=forged"})
    assert response.status == 403

    response, data = _request(port, "GET", "/api/catalogue", headers={"Cookie": _session(port)})
    assert response.status == 200 and json.loads(data)["books"] > 500


def test_write_requires_the_session_cookie(running):
    port, catalogue = running
    before = catalogue.read_bytes()

    response, _ = _post_book(port)

    assert response.status == 403
    assert catalogue.read_bytes() == before


def test_write_with_the_session_keeps_the_file_permissions(running):
    port, catalogue = running

    response, data = _post_book(port, _session(port))

    assert response.status == 201, data
    assert "Le Dit du Genji" in catalogue.read_text(encoding="utf-8")
    if sys.platform != "win32":  # POSIX permissions
        assert catalogue.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize("headers", [{"Host": "evil.example:80"}, {"Origin": "http://evil.example"}])
def test_other_hosts_and_origins_are_refused(running, headers):
    port, catalogue = running
    before = catalogue.read_bytes()

    response, _ = _post_book(port, _session(port), **headers)

    assert response.status == 403
    assert catalogue.read_bytes() == before


def test_unknown_page_is_not_found(running):
    port, _ = running

    response, _ = _request(port, "GET", "/nope")

    assert response.status == 404
