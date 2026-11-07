"""Bounded HTTP transport; no application state is shared across servers."""

import hmac
import json
import re
import socket
import threading
import time
import urllib.parse
import uuid
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

    MUTATION_PATHS = ("connect", "disconnect", "reconnect")
    LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
    SAFE_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-.]{1,64}\Z")

    def _is_same_origin(self) -> bool:
        """CSRF guard for mutations: browser cross-origin requests carry Origin/Referer.

        Non-browser clients (curl, scripts, Docker healthchecks) send neither
        header and remain allowed, preserving the legacy GET-mutation contract.
        """
        origin = self.headers.get("Origin", "").strip()
        referer = self.headers.get("Referer", "").strip()
        candidate = origin or referer
        if not candidate:
            return True
        if candidate == "null":
            return False
        host = self.headers.get("Host", "").strip()
        try:
            candidate_host = urllib.parse.urlsplit(candidate).hostname
            request_host = urllib.parse.urlsplit(f"http://{host}").hostname
        except ValueError:
            return False
        if not candidate_host or not request_host:
            return False
        if candidate_host == request_host:
            return True
        return candidate_host in self.LOOPBACK_HOSTS and request_host in self.LOOPBACK_HOSTS

    def setup(self) -> None:
        self.request.settimeout(self.server.settings.request_timeout)
        super().setup()

    def log_message(self, format: str, *args: object) -> None:
        # Never log a client-supplied path, query, header, or body.
        code = args[1] if len(args) > 1 and str(args[1]).isdigit() else "-"
        request_id = getattr(self, "request_id", "-")
        print(f"[API] status={code} req={request_id} ?REDACTED", flush=True)

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

    def _is_authorized(self, path: str) -> bool:
        expected = self.server.settings.api_token
        if not expected:
            return True
        if self.server.settings.api_allow_anonymous_health and path in ("health", "v1/health"):
            return True

        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
                return True

        api_key_header = self.headers.get("X-API-Key", "")
        if api_key_header:
            token = api_key_header.strip()
            if hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
                return True

        return False

    def _handle(self) -> None:
        started = time.monotonic()
        # ISSUE-14: correlation id echoed on every response and in logs.
        # Sanitize incoming header to safe characters to prevent HTTP response splitting.
        candidate_rid = self.headers.get("X-Request-ID", "").strip()
        if candidate_rid and self.SAFE_REQUEST_ID_PATTERN.fullmatch(candidate_rid):
            self.request_id = candidate_rid
        else:
            self.request_id = str(uuid.uuid4())
        try:
            parsed = urllib.parse.urlsplit(self.path)
            clean_path = parsed.path.strip("/")
            if not self._is_authorized(clean_path):
                response = Response(
                    401,
                    {"error": "Unauthorized", "detail": "Valid Bearer token or X-API-Key required"},
                )
            elif clean_path in self.MUTATION_PATHS and not self._is_same_origin():
                response = Response(
                    403,
                    {"error": "Forbidden", "detail": "Cross-origin mutations are not allowed"},
                )
            else:
                params = urllib.parse.parse_qs(parsed.query, max_num_fields=32)
                country = params.get("country", [None])[0]
                strict = params.get("strict_nodes", params.get("strict", [None]))[0]
                if self.command == "POST":
                    body = self._body()
                    country = body.get("country", country)
                    strict = body.get("strict_nodes", body.get("strict", strict))
                response = self.server.router.dispatch(clean_path, country, strict)
                # ISSUE-14: anonymous /health returns a minimal body —
                # details (country, ports, bootstrap) are auth-only.
                if (
                    self.server.settings.api_token
                    and self.server.settings.api_allow_anonymous_health
                    and clean_path in ("health", "v1/health")
                    and isinstance(response.body, dict)
                ):
                    response = Response(response.status, {"status": response.body.get("status")})
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
        self.send_header("X-Request-ID", self.request_id)
        # Wildcard CORS only on successful, non-mutating responses (ISSUE-01):
        # never on errors and never on mutations, so foreign origins cannot read
        # or trigger state changes through a browser.
        if response.status < 400 and clean_path not in self.MUTATION_PATHS:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if response.status == 401:
            self.send_header("WWW-Authenticate", 'Bearer realm="torproxy"')
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # Client disconnected before the full response could be delivered
            pass
        # ISSUE-14: latency + status-class counters for /metrics.
        try:
            state = self.server.router.service.state
            with state.lock:
                state.requests_total += 1
                state.request_latency_seconds_total += time.monotonic() - started
                if 400 <= response.status < 500:
                    state.http_4xx_total += 1
                elif response.status >= 500:
                    state.http_5xx_total += 1
        except Exception:  # noqa: BLE001
            pass

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        clean_path = urllib.parse.urlsplit(self.path).path.strip("/")
        self.send_response(204)
        if clean_path not in self.MUTATION_PATHS:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, X-API-Key, X-Request-ID, Content-Type, Accept",
        )
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()


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
            # ISSUE-11: never reset silently — answer 503 with Retry-After
            # and count the rejection for /metrics.
            try:
                state = self.router.service.state
                with state.lock:
                    state.requests_rejected_total += 1
            except Exception:  # noqa: BLE001
                pass
            self._send_service_unavailable(request)
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    @staticmethod
    def _send_service_unavailable(
        request: socket.socket | tuple[bytes, socket.socket],
    ) -> None:
        body = json.dumps({"error": "Service Unavailable", "detail": "Server busy, retry"}).encode()
        raw = (
            b"HTTP/1.1 503 Service Unavailable\r\n"
            b"Content-Type: application/json\r\n"
            b"Retry-After: 1\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Connection: close\r\n\r\n"
            + body
        )
        try:
            sock = request[1] if isinstance(request, tuple) else request  # type: ignore[assignment]
            sock.sendall(raw)
        except OSError:
            # Client disconnected before 503 response could be sent
            pass

    def process_request_thread(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: tuple
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()
