import json
import urllib.request
from unittest.mock import patch

import api
import pytest


@pytest.fixture(autouse=True)
def reset_metrics():
    api.reset_metrics()
    yield
    api.reset_metrics()


@pytest.mark.unit
class TestDiagnosticsEndpoint:
    def test_diagnostics_endpoint_contract(self, api_server):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
            patch("api.check_socks5_ready") as mock_socks,
            patch("api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = (
                {"bootstrapped": True, "progress": 100, "summary": "Done"},
                None,
            )
            mock_socks.return_value = True
            mock_ip.return_value = ("185.220.101.5", None)

            for path in ("/diagnostics", "/v1/diagnostics"):
                req = urllib.request.Request(f"{api_server}{path}", method="GET")
                with urllib.request.urlopen(req) as resp:
                    assert resp.status == 200
                    assert resp.headers.get("Content-Type") == "application/json"
                    data = json.loads(resp.read().decode("utf-8"))

                    assert "uptime_seconds" in data
                    assert isinstance(data["uptime_seconds"], (int, float))
                    assert "started_at" in data
                    assert "reconnect_count" in data
                    assert data["reconnect_count"] == 0

                    assert "tor" in data
                    assert data["tor"]["network_enabled"] is True
                    assert data["tor"]["bootstrapped"] is True
                    assert data["tor"]["progress"] == 100

                    assert "proxies" in data
                    assert data["proxies"]["socks5_ready"] is True
                    assert data["proxies"]["socks_port"] == 9050
                    assert data["proxies"]["http_port"] == 8118

                    assert "egress" in data
                    assert data["egress"]["verified"] is True
                    assert data["egress"]["ip"] == "185.220.101.5"

    def test_diagnostics_no_privacy_leaks(self, api_server):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
            patch("api.check_socks5_ready") as mock_socks,
            patch("api.get_current_ip") as mock_ip,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = (
                {"bootstrapped": True, "progress": 100, "summary": "Done"},
                None,
            )
            mock_socks.return_value = True
            mock_ip.return_value = ("185.220.101.5", None)

            req = urllib.request.Request(f"{api_server}/v1/diagnostics", method="GET")
            with urllib.request.urlopen(req) as resp:
                raw_body = resp.read().decode("utf-8")
                data = json.loads(raw_body)

                # Ensure sensitive terms are never present as keys or content
                for forbidden in ("cookie", "password", "token", "secret", "client_ip", "history"):
                    assert forbidden not in raw_body.lower()

                # Walk all keys
                def assert_no_forbidden_keys(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            assert "cookie" not in k.lower()
                            assert "secret" not in k.lower()
                            assert "client" not in k.lower()
                            assert_no_forbidden_keys(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            assert_no_forbidden_keys(item)

                assert_no_forbidden_keys(data)

    def test_reconnect_increments_counter_and_timestamp(self, api_server):
        with patch("api.send_tor_command") as mock_tor:
            mock_tor.return_value = ("250 OK", None)

            # Trigger reconnect
            reconn_req = urllib.request.Request(f"{api_server}/reconnect", method="POST")
            with urllib.request.urlopen(reconn_req) as resp:
                assert resp.status == 200

            # Verify in diagnostics
            diag_req = urllib.request.Request(f"{api_server}/diagnostics", method="GET")
            with urllib.request.urlopen(diag_req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                assert data["reconnect_count"] == 1
                assert data["last_reconnect_at"] is not None


@pytest.mark.unit
class TestMetricsEndpoint:
    def test_metrics_prometheus_exposition(self, api_server):
        with (
            patch("api.send_tor_command") as mock_tor,
            patch("api.get_tor_bootstrap_status") as mock_boot,
            patch("api.check_socks5_ready") as mock_socks,
        ):
            mock_tor.return_value = ("250 DisableNetwork=0", None)
            mock_boot.return_value = (
                {"bootstrapped": True, "progress": 100, "summary": "Done"},
                None,
            )
            mock_socks.return_value = True

            for path in ("/metrics", "/v1/metrics"):
                req = urllib.request.Request(f"{api_server}{path}", method="GET")
                with urllib.request.urlopen(req) as resp:
                    assert resp.status == 200
                    content_type = resp.headers.get("Content-Type", "")
                    assert "text/plain" in content_type

                    body = resp.read().decode("utf-8")
                    assert "torproxy_uptime_seconds" in body
                    assert "torproxy_reconnect_total 0" in body
                    assert "torproxy_tor_bootstrapped 1" in body
                    assert "torproxy_tor_bootstrap_progress 100" in body
                    assert "torproxy_socks5_ready 1" in body


@pytest.mark.unit
class TestOperationalLogging:
    def test_log_message_masks_sensitive_query_strings(self, capsys):
        handler = api.APIHandler.__new__(api.APIHandler)
        handler.client_address = ("127.0.0.1", 12345)
        log_format = '"%s" %s %s'
        log_args = ("GET /status?token=secret123&pass=abc HTTP/1.1", "200", "-")
        handler.log_message(log_format, *log_args)

        captured = capsys.readouterr().out
        assert "[API]" in captured
        assert "secret123" not in captured
        assert "pass=abc" not in captured
        assert "?REDACTED" in captured
