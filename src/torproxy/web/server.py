"""Bounded HTTP transport; no application state is shared across servers."""

import json
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from torproxy.configuration import Settings
from torproxy.models import Response
from torproxy.web.router import Router


class RequestError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class APIHandler(BaseHTTPRequestHandler):
    server: "ProxyHTTPServer"

    def setup(self) -> None:
        self.request.settimeout(self.server.settings.request_timeout)
        super().setup()

    def log_message(self, format: str, *args: object) -> None:
        # Never log a client-supplied path, query, header, or body.
        code = args[1] if len(args) > 1 and str(args[1]).isdigit() else "-"
        print(f"[API] status={code} ?REDACTED", flush=True)

    def _body(self) -> dict:
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding"):
            raise RequestError(400, "Transfer-Encoding is not supported")
        if len(lengths) > 1:
            raise RequestError(400, "Duplicate Content-Length")
        length = lengths[0] if lengths else "0"
        if not length.isascii() or not length.isdecimal():
            raise RequestError(400, "Invalid Content-Length")
        size = int(length)
        if size > self.server.settings.max_body_bytes:
            raise RequestError(413, "Request body too large")
        if not size:
            return {}
        try:
            raw = self.rfile.read(size)
        except TimeoutError:
            raise RequestError(408, "Request body timed out") from None
        if len(raw) != size:
            raise RequestError(400, "Incomplete request body")
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise RequestError(400, "Malformed JSON request body") from None
        if not isinstance(body, dict):
            raise RequestError(400, "JSON request body must be an object")
        return body

    def _handle(self) -> None:
        try:
            parsed = urllib.parse.urlsplit(self.path)
            params = urllib.parse.parse_qs(parsed.query, max_num_fields=32)
            country = params.get("country", [None])[0]
            strict = params.get("strict_nodes", params.get("strict", [None]))[0]
            if self.command == "POST":
                body = self._body()
                country = body.get("country", country)
                strict = body.get("strict_nodes", body.get("strict", strict))
            response = self.server.router.dispatch(parsed.path.strip("/"), country, strict)
        except RequestError as error:
            response = Response(error.status, {"error": str(error)})
        except ValueError:
            response = Response(400, {"error": "Invalid request target"})
        payload = (
            response.body if isinstance(response.body, str) else json.dumps(response.body)
        ).encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()


class ProxyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address: tuple[str, int], router: Router, settings: Settings) -> None:
        self.router = router
        self.settings = settings
        self.slots = threading.BoundedSemaphore(settings.max_workers)
        super().__init__(address, APIHandler)

    def process_request(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: tuple
    ) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: tuple
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()
