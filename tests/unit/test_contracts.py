import json
import os
import re
import urllib.error
import urllib.request
from unittest.mock import patch

import api
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKER_DIR = os.path.join(REPO_ROOT, "docker")


@pytest.mark.unit
class TestAPIContract:
    """Verifies that all API endpoints adhere to the frozen backward-compatible schema."""

    @pytest.mark.parametrize("method", ["GET", "POST"])
    @pytest.mark.parametrize("path", ["/status", "/"])
    def test_status_connected_schema(self, api_server, method, path):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
            patch("api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = ({"bootstrapped": True, "summary": "Done"}, None)
            mock_ip.return_value = ("198.51.100.42", None)

            req = urllib.request.Request(f"{api_server}{path}", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                assert resp.headers.get("Content-Type") == "application/json"
                assert resp.headers.get("Access-Control-Allow-Origin") == "*"
                body = json.loads(resp.read().decode("utf-8"))
                assert body["status"] == "connected"
                assert isinstance(body["ip"], str)
                assert body["ip"] == "198.51.100.42"

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_status_connecting_schema(self, api_server, method):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = (
                {"bootstrapped": False, "summary": "Handshake"},
                None,
            )

            req = urllib.request.Request(f"{api_server}/status", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body["status"] == "connecting"
                assert body["ip"] is None
                assert "detail" in body
                assert "Handshake" in body["detail"]

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_status_bootstrapped_but_ip_check_fails_schema(self, api_server, method):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
            patch("api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = ({"bootstrapped": True, "summary": "Done"}, None)
            mock_ip.return_value = (None, "Egress check timeout")

            req = urllib.request.Request(f"{api_server}/status", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body["status"] == "connecting"
                assert body["ip"] is None
                assert "detail" in body
                assert "Egress check timeout" in body["detail"]

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_status_disconnected_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 DisableNetwork=1", None)

            req = urllib.request.Request(f"{api_server}/status", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body["status"] == "disconnected"
                assert body["ip"] is None

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_status_error_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = (None, "ControlPort connection refused")

            req = urllib.request.Request(f"{api_server}/status", method=method)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)

            assert exc_info.value.code == 500
            body = json.loads(exc_info.value.read().decode("utf-8"))
            assert "error" in body
            assert "Failed to query Tor: ControlPort connection refused" in body["error"]

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_ip_success_schema(self, api_server, method):
        with patch("api.get_current_ip") as mock_ip:
            mock_ip.return_value = ("203.0.113.1", None)

            req = urllib.request.Request(f"{api_server}/ip", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert "ip" in body
                assert body["ip"] == "203.0.113.1"

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_ip_unavailable_schema(self, api_server, method):
        with patch("api.get_current_ip") as mock_ip:
            mock_ip.return_value = (None, "Socket timeout")

            req = urllib.request.Request(f"{api_server}/ip", method=method)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)

            assert exc_info.value.code == 503
            body = json.loads(exc_info.value.read().decode("utf-8"))
            assert "error" in body
            assert "detail" in body
            assert body["detail"] == "Socket timeout"

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_connect_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)

            req = urllib.request.Request(f"{api_server}/connect", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body["action"] == "connect"
                assert body["status"] == "success"

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_connect_error_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = (None, "Tor daemon down")

            req = urllib.request.Request(f"{api_server}/connect", method=method)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)

            assert exc_info.value.code == 500
            body = json.loads(exc_info.value.read().decode("utf-8"))
            assert "error" in body
            assert "Failed to enable Tor network: Tor daemon down" in body["error"]

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_disconnect_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)

            req = urllib.request.Request(f"{api_server}/disconnect", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body["action"] == "disconnect"
                assert body["status"] == "success"

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_disconnect_error_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = (None, "Tor daemon down")

            req = urllib.request.Request(f"{api_server}/disconnect", method=method)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)

            assert exc_info.value.code == 500
            body = json.loads(exc_info.value.read().decode("utf-8"))
            assert "error" in body
            assert "Failed to disable Tor network: Tor daemon down" in body["error"]

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_reconnect_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)

            req = urllib.request.Request(f"{api_server}/reconnect", method=method)
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                body = json.loads(resp.read().decode("utf-8"))
                assert body["action"] == "reconnect"
                assert body["status"] == "success"

    @pytest.mark.parametrize("method", ["GET", "POST"])
    def test_reconnect_error_schema(self, api_server, method):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = (None, "Rate limited")

            req = urllib.request.Request(f"{api_server}/reconnect", method=method)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)

            assert exc_info.value.code == 500
            body = json.loads(exc_info.value.read().decode("utf-8"))
            assert "error" in body
            assert "Failed to trigger reconnect: Rate limited" in body["error"]

    def test_404_not_found_schema(self, api_server):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{api_server}/non-existent")

        assert exc_info.value.code == 404
        body = json.loads(exc_info.value.read().decode("utf-8"))
        assert body["error"] == "Not Found"
        assert sorted(body["supported_paths"]) == sorted([
            "/status",
            "/ip",
            "/connect",
            "/disconnect",
            "/reconnect",
        ])


@pytest.mark.unit
class TestEnvironmentAndDefaultsContract:
    """Verifies that default configuration values and Dockerfile declarations remain compatible."""

    def test_python_api_defaults(self):
        assert api.API_PORT == 8080
        assert api.PROXY_PORT == 8118
        assert api.IP_CACHE_TTL == 30

    def test_dockerfile_defaults_and_instructions(self):
        dockerfile_path = os.path.join(DOCKER_DIR, "Dockerfile")
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            dockerfile = f.read()

        # Check default environment variables in Dockerfile
        assert "TORPROXY_LISTEN_ADDRESS=0.0.0.0" in dockerfile
        assert "TORPROXY_LISTEN_PORT=8118" in dockerfile
        assert "TORPROXY_API_PORT=8080" in dockerfile
        assert "TORPROXY_SOCKS_PORT=9050" in dockerfile

        # Check exposed ports
        assert re.search(r"EXPOSE\s+.*8118.*8080.*9050", dockerfile)

        # Check non-root user
        assert re.search(r"USER\s+torproxy", dockerfile)

        # Check healthcheck parameters
        assert "--interval=30s" in dockerfile
        assert "--timeout=15s" in dockerfile
        assert "--start-period=180s" in dockerfile
        assert "--retries=3" in dockerfile
        assert 'CMD ["/usr/local/bin/healthcheck.sh"]' in dockerfile

        # Check tini entrypoint
        assert 'ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/start.sh"]' in dockerfile

    def test_env_example_matches_contract(self):
        env_example_path = os.path.join(REPO_ROOT, ".env.example")
        with open(env_example_path, "r", encoding="utf-8") as f:
            env_example = f.read()

        assert "TORPROXY_HOST_PORT=8118" in env_example
        assert "TORPROXY_LISTEN_ADDRESS=0.0.0.0" in env_example
        assert "TORPROXY_LISTEN_PORT=8118" in env_example
        assert "TORPROXY_API_PORT=8080" in env_example
        assert "TORPROXY_SOCKS_PORT=9050" in env_example

    def test_docker_compose_loopback_bindings(self):
        compose_path = os.path.join(REPO_ROOT, "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as f:
            compose = f.read()

        # Host ports must explicitly bind to 127.0.0.1 by default
        assert '127.0.0.1:${TORPROXY_HOST_PORT:-8118}:${TORPROXY_LISTEN_PORT:-8118}' in compose
        assert '127.0.0.1:${TORPROXY_API_PORT:-8080}:${TORPROXY_API_PORT:-8080}' in compose
        assert '127.0.0.1:${TORPROXY_SOCKS_PORT:-9050}:${TORPROXY_SOCKS_PORT:-9050}' in compose


@pytest.mark.unit
class TestComposeExamplesContract:
    """Verifies that all shipped examples define torproxy with expected contracts."""

    EXAMPLES = [
        "browserless-chromium-via-tor",
        "crw-web-scraper-via-tor",
        "searxng-via-tor",
    ]

    def test_examples_torproxy_service(self):
        for example in self.EXAMPLES:
            compose_path = os.path.join(REPO_ROOT, "examples", example, "docker-compose.yml")
            assert os.path.exists(compose_path), f"Missing compose file for {example}"
            with open(compose_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "image: hapheus/torproxy:latest" in content
            assert "TORPROXY_LISTEN_PORT: 8118" in content
            assert "TORPROXY_API_PORT: 8080" in content
            assert "TORPROXY_SOCKS_PORT: 9050" in content

    def test_no_example_exposes_management_api_to_wildcard_host(self):
        for example in self.EXAMPLES:
            compose_path = os.path.join(REPO_ROOT, "examples", example, "docker-compose.yml")
            with open(compose_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Wildcard publication like "8080:8080" or "0.0.0.0:8080:8080" is forbidden in examples
            assert '"8080:8080"' not in content, (
                f"{example} publishes 8080 without host restriction"
            )
            assert "0.0.0.0:8080" not in content, f"{example} publishes 8080 to 0.0.0.0"



@pytest.mark.unit
class TestServerLifecycle:
    """Tests the server startup and shutdown loop in api.py."""

    @patch("api.ThreadingHTTPServer")
    def test_run_server_handles_keyboard_interrupt(self, mock_server_cls):
        mock_instance = mock_server_cls.return_value
        mock_instance.serve_forever.side_effect = KeyboardInterrupt

        api.run()

        mock_server_cls.assert_called_once_with(("0.0.0.0", api.API_PORT), api.APIHandler)
        mock_instance.serve_forever.assert_called_once()
        mock_instance.server_close.assert_called_once()
