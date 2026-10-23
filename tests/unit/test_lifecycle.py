import concurrent.futures
import json
import os
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from tests.support import api

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKER_DIR = os.path.join(REPO_ROOT, "docker")


@pytest.mark.unit
class TestConcurrencySafeCache:
    def test_concurrent_ip_resolution(self):
        call_count = 0

        def fake_urlopen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"IP": "198.51.100.99", "IsTor": true}'
            return mock_resp

        api.state.invalidate()

        with patch("urllib.request.build_opener") as mock_builder:
            mock_opener = MagicMock()
            mock_opener.open.side_effect = fake_urlopen
            mock_builder.return_value = mock_opener

            # Launch 20 concurrent threads attempting to resolve IP
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(api.get_current_ip) for _ in range(20)]
                results = [f.result() for f in futures]

            for ip, err in results:
                assert ip == "198.51.100.99"
                assert err is None

        # Cache was populated and reused across threads
        assert api.state.cached_ip == "198.51.100.99"

    def test_cache_cleared_during_reconnect_and_disconnect(self, api_server):
        api.state.cached_ip = "192.0.2.55"
        api.state.cached_at = 1000

        with patch("tests.support.api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)

            # Reconnect clears cache
            req = urllib.request.Request(f"{api_server}/reconnect", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
            assert api.state.cached_ip is None

            # Set again and test disconnect
            api.state.cached_ip = "192.0.2.66"
            req = urllib.request.Request(f"{api_server}/disconnect", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
            assert api.state.cached_ip is None


@pytest.mark.unit
class TestSocks5ReadinessProbe:
    @patch("socket.socket")
    def test_socks5_ready_success(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.recv.return_value = b"\x05\x00"

        ready = api.check_socks5_ready()
        assert ready is True
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 9050))
        mock_sock.sendall.assert_called_once_with(b"\x05\x01\x00")

    @patch("socket.socket")
    def test_socks5_ready_failure_handshake(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.recv.return_value = b"\x05\xff"  # No acceptable auth methods

        ready = api.check_socks5_ready()
        assert ready is False

    @patch("socket.socket")
    def test_socks5_ready_connection_refused(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.connect.side_effect = ConnectionRefusedError("Connection refused")

        ready = api.check_socks5_ready()
        assert ready is False


@pytest.mark.unit
class TestHealthDiagnosticEndpoint:
    def test_health_endpoint_healthy(self, api_server):
        with (
            patch("tests.support.api.send_tor_command") as mock_tor,
            patch("tests.support.api.get_tor_bootstrap_status") as mock_boot,
            patch("tests.support.api.check_socks5_ready") as mock_socks,
            patch("tests.support.api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = (
                {"bootstrapped": True, "progress": 100, "summary": "Done"},
                None,
            )
            mock_socks.return_value = True
            mock_ip.return_value = ("185.220.101.5", None)

            req = urllib.request.Request(f"{api_server}/health", method="GET")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "healthy"
                assert data["tor"]["bootstrapped"] is True
                assert data["proxies"]["socks5"] is True
                assert data["egress"]["verified"] is True
                assert data["egress"]["ip"] == "185.220.101.5"

    def test_health_endpoint_bootstrapping(self, api_server):
        with (
            patch("tests.support.api.send_tor_command") as mock_tor,
            patch("tests.support.api.get_tor_bootstrap_status") as mock_boot,
            patch("tests.support.api.check_socks5_ready") as mock_socks,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = (
                {"bootstrapped": False, "progress": 40, "summary": "Loading keys"},
                None,
            )
            mock_socks.return_value = False

            req = urllib.request.Request(f"{api_server}/health", method="GET")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "bootstrapping"
                assert data["tor"]["progress"] == 40
                assert data["proxies"]["socks5"] is False

    def test_health_endpoint_control_error(self, api_server):
        with patch("tests.support.api.send_tor_command") as mock_tor:
            mock_tor.return_value = (None, "Socket connection failed")

            req = urllib.request.Request(f"{api_server}/health", method="GET")
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == 503
            data = json.loads(exc_info.value.read().decode("utf-8"))
            assert data["status"] == "unhealthy"
            assert "Socket connection failed" in data["error"]

    def test_health_endpoint_network_disabled(self, api_server):
        with patch("tests.support.api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 DisableNetwork=1", None)

            req = urllib.request.Request(f"{api_server}/health", method="GET")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["status"] == "disconnected"
                assert data["tor"]["network_enabled"] is False
                assert data["proxies"]["socks5"] is False


@pytest.mark.unit
class TestProcessSupervisionTrap:
    def test_start_script_traps_sigterm_and_sigint(self):
        start_script = os.path.join(DOCKER_DIR, "start.sh")
        with open(start_script, "r", encoding="utf-8") as f:
            content = f.read()

        assert "trap shutdown" in content
        assert "SIGTERM" in content
        assert "SIGINT" in content
        assert "EXIT" in content
