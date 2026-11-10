"""HTTP/SSE transport for Model Context Protocol (MCP)."""

import json
import queue
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from torproxy.configuration import Settings
from torproxy.mcp.protocol import McpHandler


class McpSseServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: McpHandler,
        settings: Settings,
    ) -> None:
        self.handler = handler
        self.settings = settings
        self.sessions: dict[str, queue.Queue[str | None]] = {}
        self.sessions_lock = threading.Lock()
        self._is_shut_down = threading.Event()
        super().__init__(server_address, McpSseHandler)

    def create_session(self) -> tuple[str, queue.Queue[str | None]]:
        session_id = uuid.uuid4().hex
        q: queue.Queue[str | None] = queue.Queue()
        with self.sessions_lock:
            self.sessions[session_id] = q
        return session_id, q

    def get_session(self, session_id: str) -> queue.Queue[str | None] | None:
        with self.sessions_lock:
            return self.sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        with self.sessions_lock:
            self.sessions.pop(session_id, None)

    def server_close(self) -> None:
        self._is_shut_down.set()
        with self.sessions_lock:
            for q in self.sessions.values():
                q.put(None)
            self.sessions.clear()
        super().server_close()

    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys

        _, exc_value, _ = sys.exc_info()
        if isinstance(exc_value, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class McpSseHandler(BaseHTTPRequestHandler):
    server: McpSseServer

    def _check_auth(self, query_params: dict[str, list[str]]) -> bool:
        expected = self.server.settings.api_token
        if not expected:
            return True

        # 1. Bearer header
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == expected:
                return True

        # 2. X-API-Key header
        if self.headers.get("X-API-Key", "").strip() == expected:
            return True

        # 3. Query param ?token=...
        query_token = query_params.get("token", [""])[0].strip()
        if query_token == expected:
            return True

        return False

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-API-Key",
        )

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path != "/sse":
            self.send_response(404)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}\n')
            return

        if not self._check_auth(qs):
            self.send_response(401)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized"}\n')
            return

        session_id, q = self.server.create_session()
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        endpoint_url = f"/messages?sessionId={session_id}"
        self.wfile.write(f"event: endpoint\r\ndata: {endpoint_url}\r\n\r\n".encode("utf-8"))
        self.wfile.flush()

        try:
            while not self.server._is_shut_down.is_set():
                try:
                    msg = q.get(timeout=15.0)
                    if msg is None:
                        break
                    self.wfile.write(f"event: message\r\ndata: {msg}\r\n\r\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Keepalive comment
                    self.wfile.write(b": ping\r\n\r\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected or socket closed; terminate SSE stream gracefully
            pass
        finally:
            self.server.remove_session(session_id)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path != "/messages":
            self.send_response(404)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}\n')
            return

        if not self._check_auth(qs):
            self.send_response(401)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized"}\n')
            return

        session_id = qs.get("sessionId", [None])[0]
        if not session_id:
            self.send_response(400)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Missing sessionId query parameter"}\n')
            return

        q = self.server.get_session(session_id)
        if q is None:
            self.send_response(404)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Session not found"}\n')
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > self.server.settings.max_body_bytes:
            self.send_response(413)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Payload Too Large"}\n')
            return

        body_bytes = self.rfile.read(content_length)
        try:
            req = json.loads(body_bytes.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON body"}\n')
            return

        resp = self.server.handler.handle_jsonrpc(req)
        if resp is not None:
            q.put(json.dumps(resp))

        self.send_response(202)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "accepted"}\n')

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP access logs
        pass
