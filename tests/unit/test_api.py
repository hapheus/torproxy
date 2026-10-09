import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import api
import pytest


@pytest.fixture(autouse=True)
def reset_ip_cache():
    api.clear_ip_cache()
    yield
    api.clear_ip_cache()


@pytest.mark.unit
class TestTorControlProtocol:
    @patch("socket.socket")
    def test_send_tor_command_success(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        bootstrap_reply = (
            b"250-status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=100 TAG=done "
            b'SUMMARY="Handshake"\r\n'
            b"250 OK\r\n"
        )
        mock_sock.recv.side_effect = [
            b"250 OK\r\n",
            bootstrap_reply,
        ]

        resp, err = api.send_tor_command("GETINFO status/bootstrap-phase")

        assert err is None
        assert "PROGRESS=100" in resp
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 9051))
        mock_sock.sendall.assert_any_call(b"AUTHENTICATE\r\n")

    @patch("socket.socket")
    def test_send_tor_command_auth_failure(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.recv.return_value = b"515 Authentication failed: wrong password\r\n"

        resp, err = api.send_tor_command("GETCONF DisableNetwork")

        assert resp is None
        assert err == "Tor control authentication failed"

    @patch("socket.socket")
    def test_send_tor_command_socket_timeout(self, mock_socket_class):
        mock_sock = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_sock
        mock_sock.connect.side_effect = socket.timeout("timed out")

        resp, err = api.send_tor_command("GETCONF DisableNetwork")

        assert resp is None
        assert "timed out" in err


@pytest.mark.unit
class TestTorBootstrapStatus:
    @patch("api.send_tor_command")
    def test_bootstrap_complete(self, mock_send):
        reply = (
            '250-status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=100 TAG=done SUMMARY="Done"\r\n'
            "250 OK"
        )
        mock_send.return_value = (reply, None)

        status, err = api.get_tor_bootstrap_status()

        assert err is None
        assert status == {
            "progress": 100,
            "tag": "done",
            "summary": "Done",
            "bootstrapped": True,
        }

    @patch("api.send_tor_command")
    def test_bootstrap_in_progress(self, mock_send):
        reply = (
            "250-status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=50 TAG=conn_dir "
            'SUMMARY="Connecting to directory mirror"\r\n250 OK'
        )
        mock_send.return_value = (reply, None)

        status, err = api.get_tor_bootstrap_status()

        assert err is None
        assert status == {
            "progress": 50,
            "tag": "conn_dir",
            "summary": "Connecting to directory mirror",
            "bootstrapped": False,
        }

    @patch("api.send_tor_command")
    def test_bootstrap_parse_failure(self, mock_send):
        mock_send.return_value = ("250 OK Unrecognized format", None)

        status, err = api.get_tor_bootstrap_status()

        assert status is None
        assert err == "Failed to parse bootstrap status"

    @patch("api.send_tor_command")
    def test_bootstrap_query_error(self, mock_send):
        mock_send.return_value = (None, "Socket closed")

        status, err = api.get_tor_bootstrap_status()

        assert status is None
        assert "Failed to query Tor control: Socket closed" in err


@pytest.mark.unit
class TestIPResolutionAndCaching:
    def test_clear_ip_cache(self):
        api._cached_ip = "192.0.2.1"
        api._cached_ip_time = time.time()

        api.clear_ip_cache()

        assert api._cached_ip is None
        assert api._cached_ip_time == 0

    def test_cached_ip_within_ttl(self):
        api._cached_ip = "198.51.100.42"
        api._cached_ip_time = time.time()

        with patch("urllib.request.build_opener") as mock_opener:
            ip, err = api.get_current_ip()
            assert ip == "198.51.100.42"
            assert err is None
            mock_opener.assert_not_called()

    @patch("urllib.request.build_opener")
    def test_get_current_ip_uppercase_key(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"IP": "203.0.113.10", "IsTor": true}'
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        ip, err = api.get_current_ip()

        assert ip == "203.0.113.10"
        assert err is None
        assert api._cached_ip == "203.0.113.10"

    @patch("urllib.request.build_opener")
    def test_get_current_ip_lowercase_key(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ip": "203.0.113.20"}'
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        ip, err = api.get_current_ip()

        assert ip == "203.0.113.20"
        assert err is None

    @patch("urllib.request.build_opener")
    def test_get_current_ip_missing_key(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        ip, err = api.get_current_ip()

        assert ip is None
        assert err == "No IP key in response"

    @patch("urllib.request.build_opener")
    def test_get_current_ip_network_error(self, mock_build_opener):
        mock_opener = MagicMock()
        mock_opener.open.side_effect = urllib.error.URLError("Connection refused")
        mock_build_opener.return_value = mock_opener

        ip, err = api.get_current_ip()

        assert ip is None
        assert "Connection refused" in err


@pytest.fixture(scope="module")
def api_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.APIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.mark.unit
class TestAPIEndpoints:
    def test_status_when_network_disabled(self, api_server):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 DisableNetwork=1", None)
            req = urllib.request.urlopen(f"{api_server}/status")
            assert req.status == 200
            data = json.loads(req.read().decode("utf-8"))
            assert data["status"] == "disconnected"
            assert data["ip"] is None

    def test_status_when_bootstrapping(self, api_server):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = (
                {"bootstrapped": False, "summary": "Connecting to guards"},
                None,
            )

            req = urllib.request.urlopen(f"{api_server}/status")
            assert req.status == 200
            data = json.loads(req.read().decode("utf-8"))
            assert data["status"] == "connecting"
            assert "Connecting to guards" in data["detail"]

    def test_status_when_connected(self, api_server):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
            patch("api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = ({"bootstrapped": True, "summary": "Done"}, None)
            mock_ip.return_value = ("185.220.101.5", None)

            req = urllib.request.urlopen(f"{api_server}/status")
            assert req.status == 200
            data = json.loads(req.read().decode("utf-8"))
            assert data["status"] == "connected"
            assert data["ip"] == "185.220.101.5"

    def test_ip_endpoint_success(self, api_server):
        with patch("api.get_current_ip") as mock_ip:
            mock_ip.return_value = ("192.0.2.100", None)
            req = urllib.request.urlopen(f"{api_server}/ip")
            assert req.status == 200
            data = json.loads(req.read().decode("utf-8"))
            assert data["ip"] == "192.0.2.100"

    def test_ip_endpoint_failure(self, api_server):
        with patch("api.get_current_ip") as mock_ip:
            mock_ip.return_value = (None, "Proxy offline")
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(f"{api_server}/ip")
            assert exc_info.value.code == 503

    def test_connect_endpoint(self, api_server):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)
            req = urllib.request.Request(f"{api_server}/connect", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == "connect"
                assert data["status"] == "success"
            mock_tor.assert_called_with("SETCONF DisableNetwork=0")

    def test_disconnect_endpoint(self, api_server):
        api._cached_ip = "1.2.3.4"
        api._cached_ip_time = time.time()

        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)
            req = urllib.request.Request(f"{api_server}/disconnect", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == "disconnect"
            assert api._cached_ip is None

    def test_reconnect_endpoint(self, api_server):
        api._cached_ip = "1.2.3.4"
        api._cached_ip_time = time.time()

        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)
            req = urllib.request.Request(f"{api_server}/reconnect", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == "reconnect"
            assert api._cached_ip is None
            mock_tor.assert_called_with("SIGNAL NEWNYM")

    def test_not_found_endpoint(self, api_server):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{api_server}/invalid-path")
        assert exc_info.value.code == 404
