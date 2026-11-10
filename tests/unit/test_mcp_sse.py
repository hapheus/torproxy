import json
import threading
import urllib.error
import urllib.request

import pytest

from torproxy.bootstrap import create_services
from torproxy.configuration import Settings
from torproxy.mcp.protocol import McpHandler
from torproxy.mcp.sse import McpSseServer
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
        return "198.51.100.42", None


class DummySocks:
    def ready(self):
        return True


@pytest.fixture
def running_sse_server():
    def _create(settings_override=None):
        settings_dict = {"TORPROXY_MCP_PORT": "2501", "TORPROXY_MCP_LISTEN_ADDRESS": "127.0.0.1"}
        if settings_override:
            settings_dict.update(settings_override)
        settings = Settings.from_mapping(settings_dict)
        service = create_services(
            settings, control=DummyControl(), egress=DummyEgress(), socks=DummySocks()
        )
        queries = ProxyQueries(service)
        handler = McpHandler(service, queries)
        server = McpSseServer(("127.0.0.1", 0), handler, settings)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"
        return server, base_url

    created_servers = []

    def factory(settings_override=None):
        srv, url = _create(settings_override)
        created_servers.append(srv)
        return srv, url

    yield factory

    for srv in created_servers:
        srv.shutdown()
        srv.server_close()


@pytest.mark.unit
def test_sse_options_cors(running_sse_server):
    _, base_url = running_sse_server()
    req = urllib.request.Request(f"{base_url}/sse", method="OPTIONS")
    with urllib.request.urlopen(req) as resp:
        assert resp.status in (200, 204)
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"
        assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")


@pytest.mark.unit
def test_sse_endpoint_and_message_flow(running_sse_server):
    _, base_url = running_sse_server()

    # 1. Connect to /sse stream
    req = urllib.request.Request(f"{base_url}/sse")
    resp = urllib.request.urlopen(req)
    assert resp.headers.get("Content-Type") == "text/event-stream"

    # Read until endpoint event is received
    line1 = resp.readline().decode().strip()
    line2 = resp.readline().decode().strip()
    resp.readline()  # empty separator line

    assert line1 == "event: endpoint"
    assert line2.startswith("data: /messages?sessionId=")
    endpoint_path = line2.split("data: ")[1].strip()

    # 2. Send JSON-RPC ping to /messages?sessionId=...
    post_url = f"{base_url}{endpoint_path}"
    body = json.dumps({"jsonrpc": "2.0", "id": "msg-1", "method": "ping"}).encode()
    post_req = urllib.request.Request(
        post_url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(post_req) as post_resp:
        assert post_resp.status in (200, 202)

    # 3. Read message response on SSE stream
    ev_line = resp.readline().decode().strip()
    data_line = resp.readline().decode().strip()
    resp.readline()  # separator line

    assert ev_line == "event: message"
    msg_data = json.loads(data_line.split("data: ")[1])
    assert msg_data["id"] == "msg-1"
    assert msg_data["result"] == {}

    resp.close()


@pytest.mark.unit
def test_sse_authentication(running_sse_server):
    _, base_url = running_sse_server({"TORPROXY_API_TOKEN": "topsecret"})

    # Missing token -> 401
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{base_url}/sse")
    assert exc_info.value.code == 401

    # Valid token via Bearer header -> 200
    req = urllib.request.Request(f"{base_url}/sse", headers={"Authorization": "Bearer topsecret"})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        resp.close()

    # Valid token via Query Parameter ?token=topsecret -> 200
    req_query = urllib.request.Request(f"{base_url}/sse?token=topsecret")
    with urllib.request.urlopen(req_query) as resp:
        assert resp.status == 200
        resp.close()


@pytest.mark.unit
def test_sse_unknown_session_returns_404(running_sse_server):
    _, base_url = running_sse_server()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    post_req = urllib.request.Request(
        f"{base_url}/messages?sessionId=non-existent-session",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(post_req)
    assert exc_info.value.code == 404


@pytest.mark.unit
def test_sse_invalid_paths_return_404(running_sse_server):
    _, base_url = running_sse_server()

    # GET invalid path
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{base_url}/unknown")
    assert exc_info.value.code == 404

    # POST invalid path
    post_req = urllib.request.Request(
        f"{base_url}/unknown",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(post_req)
    assert exc_info.value.code == 404


@pytest.mark.unit
def test_sse_post_missing_session_id(running_sse_server):
    _, base_url = running_sse_server()
    post_req = urllib.request.Request(
        f"{base_url}/messages",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(post_req)
    assert exc_info.value.code == 400


@pytest.mark.unit
def test_sse_post_invalid_json(running_sse_server):
    _, base_url = running_sse_server()

    # Get a valid session
    stream_resp = urllib.request.urlopen(f"{base_url}/sse")
    stream_resp.readline()
    line2 = stream_resp.readline().decode().strip()
    stream_resp.readline()
    endpoint = line2.split("data: ")[1].strip()

    post_req = urllib.request.Request(
        f"{base_url}{endpoint}",
        data=b"{not valid json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(post_req)
    assert exc_info.value.code == 400
    stream_resp.close()


@pytest.mark.unit
def test_sse_post_payload_too_large(running_sse_server):
    _, base_url = running_sse_server({"TORPROXY_MAX_BODY_BYTES": "100"})

    stream_resp = urllib.request.urlopen(f"{base_url}/sse")
    stream_resp.readline()
    line2 = stream_resp.readline().decode().strip()
    stream_resp.readline()
    endpoint = line2.split("data: ")[1].strip()

    large_body = json.dumps({"jsonrpc": "2.0", "data": "x" * 200}).encode()
    post_req = urllib.request.Request(
        f"{base_url}{endpoint}",
        data=large_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(post_req)
    assert exc_info.value.code == 413
    stream_resp.close()
