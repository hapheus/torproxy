import json
import socket
import time
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import api
import pytest


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
        assert "Tor control authentication failed" in err

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
        mock_resp.read.return_value = b'{"ip": "203.0.113.20", "IsTor": true}'
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        ip, err = api.get_current_ip()

        assert ip == "203.0.113.20"
        assert err is None

    @patch("urllib.request.build_opener")
    def test_get_current_ip_rejects_is_tor_false(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"IP": "203.0.113.30", "IsTor": false}'
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        ip, err = api.get_current_ip()

        assert ip is None
        assert "IsTor=false" in err
        assert api._cached_ip is None

    @patch("urllib.request.build_opener")
    def test_get_current_ip_missing_is_tor_confirmation(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"IP": "203.0.113.40"}'
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        ip, err = api.get_current_ip()

        assert ip is None
        assert "missing IsTor" in err

    @patch("urllib.request.build_opener")
    def test_get_current_ip_missing_key(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok", "IsTor": true}'
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

    def test_reconnect_with_country_query_param(self, api_server):
        api.reset_country_state()
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)
            req = urllib.request.Request(f"{api_server}/reconnect?country=DE", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == "reconnect"
                assert data["status"] == "success"
                assert data["exit_country"] == "DE"
            mock_tor.assert_any_call("SETCONF ExitNodes={de}")
            mock_tor.assert_any_call("SIGNAL NEWNYM")
            assert api.get_current_country() == "DE"

    def test_connect_with_country_and_strict_json_body(self, api_server):
        api.reset_country_state()
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)
            payload = json.dumps({"country": "AT,CH", "strict_nodes": True}).encode("utf-8")
            req = urllib.request.Request(
                f"{api_server}/connect",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == "connect"
                assert data["status"] == "success"
                assert data["exit_country"] == "AT,CH"
                assert data["strict_nodes"] is True
            mock_tor.assert_any_call("SETCONF ExitNodes={at},{ch}")
            mock_tor.assert_any_call("SETCONF StrictNodes=1")
            mock_tor.assert_any_call("SETCONF DisableNetwork=0")
            assert api.get_current_country() == "AT,CH"
            assert api.get_current_strict_nodes() is True

    def test_reconnect_clear_country(self, api_server):
        api.set_current_country_state("DE", True)
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)
            req = urllib.request.Request(f"{api_server}/reconnect?country=any", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == "reconnect"
                assert data["status"] == "success"
                assert data.get("exit_country") is None
            mock_tor.assert_any_call("SETCONF ExitNodes=")
            mock_tor.assert_any_call("SIGNAL NEWNYM")
            assert api.get_current_country() is None

    def test_reconnect_invalid_country_returns_400(self, api_server):
        req = urllib.request.Request(f"{api_server}/reconnect?country=INVALID", method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400
        data = json.loads(exc_info.value.read().decode("utf-8"))
        assert "Invalid ISO country code" in data["error"]

    def test_reconnect_invalid_json_body_returns_400(self, api_server):
        req = urllib.request.Request(
            f"{api_server}/reconnect",
            data=b"invalid-json{",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400
        data = json.loads(exc_info.value.read().decode("utf-8"))
        assert "Malformed JSON request body" in data["error"]

    def test_reconnect_tor_error_setting_exit_nodes(self, api_server):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = (None, "Tor syntax error in ExitNodes")
            req = urllib.request.Request(f"{api_server}/reconnect?country=DE", method="POST")
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == 500
            data = json.loads(exc_info.value.read().decode("utf-8"))
            assert "Failed to configure ExitNodes in Tor" in data["error"]

    def test_reconnect_tor_error_setting_strict_nodes(self, api_server):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.side_effect = [
                ("250 OK", None),  # SETCONF ExitNodes
                (None, "Tor error setting strict nodes"),  # SETCONF StrictNodes
            ]
            req = urllib.request.Request(
                f"{api_server}/reconnect?country=DE&strict_nodes=1", method="POST"
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == 500
            data = json.loads(exc_info.value.read().decode("utf-8"))
            assert "Failed to configure StrictNodes in Tor" in data["error"]

    def test_reconnect_invalid_strict_nodes_returns_400(self, api_server):
        req = urllib.request.Request(f"{api_server}/reconnect?strict_nodes=maybe", method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400
        data = json.loads(exc_info.value.read().decode("utf-8"))
        assert "Invalid boolean value for strict_nodes" in data["error"]

    def test_legacy_get_reconnect_with_country(self, api_server):
        api.reset_country_state()
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)
            req = urllib.request.Request(f"{api_server}/reconnect?country=IT", method="GET")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == "reconnect"
                assert data["exit_country"] == "IT"
            mock_tor.assert_any_call("SETCONF ExitNodes={it}")
            assert api.get_current_country() == "IT"

    def test_reconnect_dynamic_switch_reflected_in_diagnostics(self, api_server):
        api.reset_country_state()
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
            patch("api.check_socks5_ready") as mock_socks,
            patch("api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 OK", None)
            mock_boot.return_value = ({"bootstrapped": True, "progress": 100}, None)
            mock_socks.return_value = True
            mock_ip.return_value = ("185.220.101.5", None)

            # Reconnect with country=ES
            req = urllib.request.Request(f"{api_server}/reconnect?country=ES", method="POST")
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 200

            # Query diagnostics
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            req_d = urllib.request.Request(f"{api_server}/diagnostics", method="GET")
            with urllib.request.urlopen(req_d) as resp_d:
                data_d = json.loads(resp_d.read().decode("utf-8"))
                assert data_d["tor"]["exit_country"] == "ES"

    def test_validation_helpers_direct(self):
        # Country validation
        assert api.validate_country_input(None) == (None, None, None)
        assert api.validate_country_input("") == ("", None, None)
        assert api.validate_country_input("any") == ("", None, None)
        assert api.validate_country_input("DE") == ("{de}", "DE", None)
        assert api.validate_country_input(["DE", "AT"]) == ("{de},{at}", "DE,AT", None)
        assert api.validate_country_input(123)[2] is not None
        assert api.validate_country_input(["DE", "INVALID"])[2] is not None

        # Strict nodes validation
        assert api.validate_strict_nodes_input(None) == (None, None)
        assert api.validate_strict_nodes_input(True) == (True, None)
        assert api.validate_strict_nodes_input(False) == (False, None)
        assert api.validate_strict_nodes_input(1) == (True, None)
        assert api.validate_strict_nodes_input(0) == (False, None)
        assert api.validate_strict_nodes_input("true") == (True, None)
        assert api.validate_strict_nodes_input("no") == (False, None)
        assert api.validate_strict_nodes_input(2)[1] is not None
        assert api.validate_strict_nodes_input("invalid")[1] is not None
        assert api.validate_strict_nodes_input({})[1] is not None

    def test_not_found_endpoint(self, api_server):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{api_server}/invalid-path")
        assert exc_info.value.code == 404

    def test_unsupported_http_method(self, api_server):
        req = urllib.request.Request(f"{api_server}/status", method="DELETE")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 501


@pytest.mark.unit
class TestApiServerRun:
    @patch("api.ThreadingHTTPServer")
    def test_run_server_handles_keyboard_interrupt(self, mock_server_class):
        mock_instance = MagicMock()
        mock_instance.serve_forever.side_effect = KeyboardInterrupt
        mock_server_class.return_value = mock_instance

        api.run()

        mock_server_class.assert_called_once_with(("0.0.0.0", 8080), api.APIHandler)
        mock_instance.serve_forever.assert_called_once()
        mock_instance.server_close.assert_called_once()
