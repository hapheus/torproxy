import io
import json

import pytest

from torproxy.bootstrap import create_services
from torproxy.configuration import Settings
from torproxy.mcp.protocol import McpHandler
from torproxy.mcp.stdio import run_stdio_server
from torproxy.queries import ProxyQueries


class DummyControl:
    def send(self, command):
        if command == "GETINFO status/bootstrap-phase":
            return '250-status/bootstrap-phase=PROGRESS=100 TAG=done SUMMARY="Done"\r\n250 OK', None
        if command == "GETCONF DisableNetwork":
            return "DisableNetwork=0", None
        return "250 OK", None


class DummyEgress:
    def resolve(self):
        return "198.51.100.99", None


class DummySocks:
    def ready(self):
        return True


@pytest.fixture
def stdio_handler():
    settings = Settings()
    service = create_services(
        settings, control=DummyControl(), egress=DummyEgress(), socks=DummySocks()
    )
    queries = ProxyQueries(service)
    return McpHandler(service, queries)


@pytest.mark.unit
def test_stdio_server_single_request(stdio_handler):
    in_buf = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n")
    out_buf = io.StringIO()
    err_buf = io.StringIO()

    run_stdio_server(stdio_handler, in_stream=in_buf, out_stream=out_buf, err_stream=err_buf)

    lines = [line.strip() for line in out_buf.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    resp = json.loads(lines[0])
    assert resp == {"jsonrpc": "2.0", "id": 1, "result": {}}


@pytest.mark.unit
def test_stdio_server_ignores_notification_output(stdio_handler):
    in_buf = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
    )
    out_buf = io.StringIO()
    err_buf = io.StringIO()

    run_stdio_server(stdio_handler, in_stream=in_buf, out_stream=out_buf, err_stream=err_buf)

    assert out_buf.getvalue().strip() == ""


@pytest.mark.unit
def test_stdio_server_malformed_json(stdio_handler):
    in_buf = io.StringIO("{not valid json\n")
    out_buf = io.StringIO()
    err_buf = io.StringIO()

    run_stdio_server(stdio_handler, in_stream=in_buf, out_stream=out_buf, err_stream=err_buf)

    lines = [line.strip() for line in out_buf.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    resp = json.loads(lines[0])
    assert resp["error"]["code"] == -32700  # Parse error
