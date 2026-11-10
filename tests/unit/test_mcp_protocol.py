import json

import pytest

from torproxy import __version__
from torproxy.bootstrap import create_services
from torproxy.configuration import Settings
from torproxy.queries import ProxyQueries


class FakeControl:
    def __init__(self):
        self.commands = []
        self.fail_on = None

    def send(self, command):
        self.commands.append(command)
        if command == self.fail_on:
            return None, "command failed"
        if command == "GETINFO status/bootstrap-phase":
            return '250-status/bootstrap-phase=PROGRESS=100 TAG=done SUMMARY="Done"\r\n250 OK', None
        if command == "GETCONF DisableNetwork":
            return "DisableNetwork=0", None
        return "250 OK", None


class FakeEgress:
    def resolve(self):
        return "198.51.100.42", None


class FakeSocks:
    def ready(self):
        return True


@pytest.fixture
def mcp_setup():
    from torproxy.mcp.protocol import McpHandler

    control = FakeControl()
    egress = FakeEgress()
    socks = FakeSocks()
    settings = Settings()
    service = create_services(settings, control=control, egress=egress, socks=socks)
    queries = ProxyQueries(service)
    handler = McpHandler(service, queries)
    return handler, service, control


@pytest.mark.unit
def test_mcp_initialize(mcp_setup):
    handler, _, _ = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = handler.handle_jsonrpc(req)
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "result" in resp
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    assert result["serverInfo"]["name"] == "torproxy"
    assert result["serverInfo"]["version"] == __version__


@pytest.mark.unit
def test_mcp_ping(mcp_setup):
    handler, _, _ = mcp_setup
    req = {"jsonrpc": "2.0", "id": "p-1", "method": "ping"}
    resp = handler.handle_jsonrpc(req)
    assert resp == {"jsonrpc": "2.0", "id": "p-1", "result": {}}


@pytest.mark.unit
def test_mcp_notification_returns_none(mcp_setup):
    handler, _, _ = mcp_setup
    req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    resp = handler.handle_jsonrpc(req)
    assert resp is None


@pytest.mark.unit
def test_mcp_tools_list(mcp_setup):
    handler, _, _ = mcp_setup
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    resp = handler.handle_jsonrpc(req)
    assert resp is not None
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    expected = {
        "torproxy_status",
        "torproxy_get_ip",
        "torproxy_reconnect",
        "torproxy_connect",
        "torproxy_disconnect",
        "torproxy_health",
        "torproxy_diagnostics",
    }
    assert expected.issubset(tool_names)
    for tool in tools:
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


@pytest.mark.unit
def test_mcp_tools_call_status(mcp_setup):
    handler, _, _ = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "torproxy_status", "arguments": {}},
    }
    resp = handler.handle_jsonrpc(req)
    assert resp is not None
    assert resp["id"] == 3
    result = resp["result"]
    assert result["isError"] is False
    assert len(result["content"]) == 1
    content = json.loads(result["content"][0]["text"])
    assert content["status"] == "connected"
    assert content["ip"] == "198.51.100.42"


@pytest.mark.unit
def test_mcp_tools_call_get_ip(mcp_setup):
    handler, _, _ = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "torproxy_get_ip", "arguments": {}},
    }
    resp = handler.handle_jsonrpc(req)
    result = resp["result"]
    assert result["isError"] is False
    content = json.loads(result["content"][0]["text"])
    assert content["ip"] == "198.51.100.42"


@pytest.mark.unit
def test_mcp_tools_call_reconnect(mcp_setup):
    handler, service, control = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "torproxy_reconnect",
            "arguments": {"country": "de", "strict": True},
        },
    }
    resp = handler.handle_jsonrpc(req)
    result = resp["result"]
    assert result["isError"] is False
    content = json.loads(result["content"][0]["text"])
    assert content["action"] == "reconnect"
    assert content["status"] == "success"
    assert content["exit_country"] == "DE"
    assert content["strict_nodes"] is True
    assert "SIGNAL NEWNYM" in control.commands


@pytest.mark.unit
def test_mcp_tools_call_reconnect_invalid_country(mcp_setup):
    handler, _, _ = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "torproxy_reconnect",
            "arguments": {"country": "INVALID_CODE"},
        },
    }
    resp = handler.handle_jsonrpc(req)
    result = resp["result"]
    assert result["isError"] is True
    assert "Invalid ISO country code" in result["content"][0]["text"]


@pytest.mark.unit
def test_mcp_tools_call_connect_and_disconnect(mcp_setup):
    handler, _, control = mcp_setup
    req_disc = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "torproxy_disconnect", "arguments": {}},
    }
    resp_disc = handler.handle_jsonrpc(req_disc)
    assert resp_disc["result"]["isError"] is False
    assert "SETCONF DisableNetwork=1" in control.commands

    req_conn = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {"name": "torproxy_connect", "arguments": {}},
    }
    resp_conn = handler.handle_jsonrpc(req_conn)
    assert resp_conn["result"]["isError"] is False
    assert "SETCONF DisableNetwork=0" in control.commands


@pytest.mark.unit
def test_mcp_tools_call_health_and_diagnostics(mcp_setup):
    handler, _, _ = mcp_setup
    for tool_name in ("torproxy_health", "torproxy_diagnostics"):
        req = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": {}},
        }
        resp = handler.handle_jsonrpc(req)
        assert resp["result"]["isError"] is False
        assert len(resp["result"]["content"]) == 1


@pytest.mark.unit
def test_mcp_tools_call_unknown_tool(mcp_setup):
    handler, _, _ = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {"name": "non_existent_tool", "arguments": {}},
    }
    resp = handler.handle_jsonrpc(req)
    assert resp["result"]["isError"] is True
    assert "Unknown tool" in resp["result"]["content"][0]["text"]


@pytest.mark.unit
def test_mcp_resources_list_and_read(mcp_setup):
    handler, _, _ = mcp_setup
    list_req = {"jsonrpc": "2.0", "id": 11, "method": "resources/list"}
    list_resp = handler.handle_jsonrpc(list_req)
    resources = list_resp["result"]["resources"]
    uris = {r["uri"] for r in resources}
    assert "torproxy://status" in uris
    assert "torproxy://metrics" in uris

    # Read torproxy://status
    read_req = {
        "jsonrpc": "2.0",
        "id": 12,
        "method": "resources/read",
        "params": {"uri": "torproxy://status"},
    }
    read_resp = handler.handle_jsonrpc(read_req)
    contents = read_resp["result"]["contents"]
    assert contents[0]["uri"] == "torproxy://status"
    assert contents[0]["mimeType"] == "application/json"
    status_data = json.loads(contents[0]["text"])
    assert "status" in status_data

    # Read torproxy://metrics
    read_metrics = {
        "jsonrpc": "2.0",
        "id": 13,
        "method": "resources/read",
        "params": {"uri": "torproxy://metrics"},
    }
    metrics_resp = handler.handle_jsonrpc(read_metrics)
    assert metrics_resp["result"]["contents"][0]["mimeType"] == "text/plain"

    # Read unknown resource
    unknown_req = {
        "jsonrpc": "2.0",
        "id": 14,
        "method": "resources/read",
        "params": {"uri": "torproxy://invalid"},
    }
    unknown_resp = handler.handle_jsonrpc(unknown_req)
    assert "error" in unknown_resp
    assert unknown_resp["error"]["code"] == -32602


@pytest.mark.unit
def test_mcp_unknown_method_error(mcp_setup):
    handler, _, _ = mcp_setup
    req = {"jsonrpc": "2.0", "id": 99, "method": "unknown_rpc_method"}
    resp = handler.handle_jsonrpc(req)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


@pytest.mark.unit
def test_mcp_tools_call_fetch_missing_or_invalid_url(mcp_setup):
    handler, _, _ = mcp_setup
    # Missing url
    req1 = {
        "jsonrpc": "2.0",
        "id": 20,
        "method": "tools/call",
        "params": {"name": "torproxy_fetch", "arguments": {}},
    }
    resp1 = handler.handle_jsonrpc(req1)
    assert resp1["result"]["isError"] is True
    assert "Missing required 'url'" in resp1["result"]["content"][0]["text"]

    # Invalid scheme
    req2 = {
        "jsonrpc": "2.0",
        "id": 21,
        "method": "tools/call",
        "params": {"name": "torproxy_fetch", "arguments": {"url": "file:///etc/passwd"}},
    }
    resp2 = handler.handle_jsonrpc(req2)
    assert resp2["result"]["isError"] is True
    assert "Unsupported URL scheme" in resp2["result"]["content"][0]["text"]


@pytest.mark.unit
def test_mcp_tools_call_fetch_success(mcp_setup, monkeypatch):
    from unittest.mock import MagicMock

    handler, _, _ = mcp_setup

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.read.return_value = b'{"origin": "198.51.100.1"}'
    mock_resp.geturl.return_value = "https://example.com/api"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    mock_opener = MagicMock()
    mock_opener.open.return_value = mock_resp

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: mock_opener)

    req = {
        "jsonrpc": "2.0",
        "id": 22,
        "method": "tools/call",
        "params": {
            "name": "torproxy_fetch",
            "arguments": {
                "url": "https://example.com/api",
                "method": "GET",
                "headers": {"User-Agent": "agent/1.0"},
            },
        },
    }
    resp = handler.handle_jsonrpc(req)
    assert resp["result"]["isError"] is False
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["status"] == 200
    assert "198.51.100.1" in content["body"]
    assert content["url"] == "https://example.com/api"


@pytest.mark.unit
def test_mcp_tools_call_fetch_http_error(mcp_setup, monkeypatch):
    import io
    import urllib.error
    from unittest.mock import MagicMock

    handler, _, _ = mcp_setup

    fp = io.BytesIO(b"Not Found")
    http_err = urllib.error.HTTPError(
        "https://example.com/404", 404, "Not Found", {"Content-Type": "text/plain"}, fp
    )

    mock_opener = MagicMock()
    mock_opener.open.side_effect = http_err
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: mock_opener)

    req = {
        "jsonrpc": "2.0",
        "id": 23,
        "method": "tools/call",
        "params": {"name": "torproxy_fetch", "arguments": {"url": "https://example.com/404"}},
    }
    resp = handler.handle_jsonrpc(req)
    assert resp["result"]["isError"] is True
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["status"] == 404
    assert content["body"] == "Not Found"


@pytest.mark.unit
def test_mcp_initialize_version_negotiation_and_optional_lists(mcp_setup):
    handler, _, _ = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 30,
        "method": "initialize",
        "params": {"protocolVersion": "2025-03-26"},
    }
    resp = handler.handle_jsonrpc(req)
    assert resp["result"]["protocolVersion"] == "2025-03-26"

    prompts_resp = handler.handle_jsonrpc({"jsonrpc": "2.0", "id": 31, "method": "prompts/list"})
    assert prompts_resp["result"] == {"prompts": []}

    templates_resp = handler.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 32, "method": "resources/templates/list"}
    )
    assert templates_resp["result"] == {"resourceTemplates": []}


@pytest.mark.unit
def test_mcp_reconnect_accepts_strict_nodes_alias(mcp_setup):
    handler, _, _ = mcp_setup
    req = {
        "jsonrpc": "2.0",
        "id": 33,
        "method": "tools/call",
        "params": {
            "name": "torproxy_reconnect",
            "arguments": {"country": "at", "strict_nodes": True},
        },
    }
    resp = handler.handle_jsonrpc(req)
    assert resp["result"]["isError"] is False
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["exit_country"] == "AT"
    assert content["strict_nodes"] is True


@pytest.mark.unit
def test_mcp_fetch_rejects_redirect_to_disallowed_scheme(mcp_setup):
    import urllib.request
    from email.message import Message

    from torproxy.mcp.protocol import _SafeRedirectHandler

    redirect_handler = _SafeRedirectHandler()
    req = urllib.request.Request("https://example.com/start")
    with pytest.raises(urllib.error.URLError, match="Unsupported redirect URL scheme"):
        redirect_handler.redirect_request(req, None, 302, "Found", Message(), "file:///etc/passwd")
