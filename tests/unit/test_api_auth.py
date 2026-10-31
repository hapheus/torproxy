import json
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest

from tests.support import api
from torproxy.configuration import Settings
from torproxy.web.router import Router
from torproxy.web.server import ProxyHTTPServer


@pytest.fixture
def auth_api_server():
    settings = Settings(api_token="super-secret-token", api_allow_anonymous_health=False)
    server = ProxyHTTPServer(("127.0.0.1", 0), Router(api), settings)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.fixture
def anon_health_api_server():
    settings = Settings(api_token="super-secret-token", api_allow_anonymous_health=True)
    server = ProxyHTTPServer(("127.0.0.1", 0), Router(api), settings)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


@pytest.mark.unit
class TestAPIAuthentication:
    def test_unauthenticated_request_rejected_with_401(self, auth_api_server):
        req = urllib.request.Request(f"{auth_api_server}/status")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 401
        assert "Bearer" in exc_info.value.headers.get("WWW-Authenticate", "")
        body = json.loads(exc_info.value.read().decode("utf-8"))
        assert body["error"] == "Unauthorized"

    def test_invalid_token_rejected_with_401(self, auth_api_server):
        req = urllib.request.Request(
            f"{auth_api_server}/status",
            headers={"Authorization": "Bearer wrong-token"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 401
        body = json.loads(exc_info.value.read().decode("utf-8"))
        assert body["error"] == "Unauthorized"

    def test_bearer_token_authorization_header_success(self, auth_api_server):
        with (
            patch("tests.support.api.send_tor_command") as mock_tor,
            patch("tests.support.api.get_tor_bootstrap_status") as mock_boot,
            patch("tests.support.api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = ({"bootstrapped": True, "summary": "Done"}, None)
            mock_ip.return_value = ("198.51.100.42", None)

            req = urllib.request.Request(
                f"{auth_api_server}/status",
                headers={"Authorization": "Bearer super-secret-token"},
            )
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "connected"

    def test_x_api_key_header_success(self, auth_api_server):
        with (
            patch("tests.support.api.send_tor_command") as mock_tor,
            patch("tests.support.api.get_tor_bootstrap_status") as mock_boot,
            patch("tests.support.api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = ({"bootstrapped": True, "summary": "Done"}, None)
            mock_ip.return_value = ("198.51.100.42", None)

            req = urllib.request.Request(
                f"{auth_api_server}/status",
                headers={"X-API-Key": "super-secret-token"},
            )
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "connected"

    def test_mutating_endpoint_requires_auth(self, auth_api_server):
        req = urllib.request.Request(
            f"{auth_api_server}/reconnect",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 401

    def test_cors_options_preflight_bypasses_auth(self, auth_api_server):
        req = urllib.request.Request(f"{auth_api_server}/status", method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 204
            assert resp.headers.get("Access-Control-Allow-Origin") == "*"
            assert "Authorization" in resp.headers.get("Access-Control-Allow-Headers", "")
            assert "X-API-Key" in resp.headers.get("Access-Control-Allow-Headers", "")

    def test_anonymous_health_allowed_when_enabled(self, anon_health_api_server):
        with patch("tests.support.api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 DisableNetwork=1", None)
            req = urllib.request.Request(f"{anon_health_api_server}/health")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "disconnected"

            # Meanwhile, /status still requires auth on the same server
            req_status = urllib.request.Request(f"{anon_health_api_server}/status")
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req_status)
            assert exc_info.value.code == 401
