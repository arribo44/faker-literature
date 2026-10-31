"""Local web editor adding Wikidata books to ``literature.json``.

Run with:  python tools/literature_editor/server.py [--port 8765]

The server only listens on 127.0.0.1 and rejects requests coming from other
sites (Host / Origin checks), so no web page can write to the catalogue.
"""

import argparse
import json
import threading
import traceback
import urllib.error
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import editor


INDEX = Path(__file__).with_name("index.html")
MAX_BODY = 64 * 1024
WRITE_LOCK = threading.Lock()

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                               "style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class EditorHandler(BaseHTTPRequestHandler):
    server_version = "LiteratureEditor"

    def handle_one_request(self):
        # An unexpected error must answer the page instead of dropping the connection
        try:
            super().handle_one_request()
        except Exception:
            traceback.print_exc()
            try:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Erreur interne du serveur : voir le terminal où il tourne.")
            except OSError:
                pass

    def _allowed_hosts(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status, message):
        self._json(status, {"error": message})

    def _check_host(self):
        # Defeats DNS rebinding: only our own host names are served
        if self.headers.get("Host") not in self._allowed_hosts():
            self._error(HTTPStatus.FORBIDDEN, "Hôte non autorisé.")
            return False
        return True

    def do_GET(self):
        if not self._check_host():
            return
        url = urlsplit(self.path)
        if url.path == "/":
            self._send(HTTPStatus.OK, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/catalogue":
            self._json(HTTPStatus.OK, editor.catalogue_info(editor.load_catalogue()))
        elif url.path == "/api/author":
            self._get_author(parse_qs(url.query).get("id", [""])[0])
        else:
            self._error(HTTPStatus.NOT_FOUND, "Page introuvable.")

    def _get_author(self, text):
        try:
            author, works, total = editor.fetch_author(text)
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self._error(HTTPStatus.BAD_GATEWAY, f"Wikidata ne répond pas : {error}")
            return
        existing = editor.annotate(editor.load_catalogue(), author, works)
        self._json(HTTPStatus.OK, {"author": author, "existing": existing, "works": works, "total": total})

    def do_POST(self):
        if not self._check_host():
            return
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc not in self._allowed_hosts():
            self._error(HTTPStatus.FORBIDDEN, "Origine non autorisée.")
            return
        # A JSON content type forces a CORS preflight that this server never accepts
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON attendu.")
            return
        if urlsplit(self.path).path != "/api/books":
            self._error(HTTPStatus.NOT_FOUND, "Page introuvable.")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Requête vide ou trop volumineuse.")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("author"), dict) or not isinstance(payload.get("book"), dict):
                raise ValueError("Requête mal formée.")
            with WRITE_LOCK:
                data = editor.load_catalogue()
                message, created = editor.add_book(data, payload["author"], payload["book"])
                editor.save_catalogue(data)
        except (ValueError, UnicodeDecodeError) as error:
            print(f"  refusé : {error}", flush=True)
            self._error(HTTPStatus.BAD_REQUEST, str(error))
            return
        print(f"  enregistré : {message}", flush=True)
        self._json(HTTPStatus.CREATED, {
            "message": message,
            "created_author": created,
            "total_books": sum(len(entry["books"]) for entry in data["authors"]),
        })

    def log_message(self, format, *args):
        print(f"  {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the page automatically")
    parser.add_argument("--catalogue", type=Path, help="JSON file to edit (default: the bundled literature.json)")
    args = parser.parse_args()
    if args.catalogue:
        editor.CATALOGUE_PATH = args.catalogue.resolve()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), EditorHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Éditeur du catalogue : {url}  (Ctrl+C pour arrêter)", flush=True)
    print(f"Fichier modifié : {editor.CATALOGUE_PATH}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
