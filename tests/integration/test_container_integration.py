import json
import os
import socket
import urllib.error
import urllib.request

import pytest

API_PORT = int(os.environ.get("TORPROXY_API_PORT", 8080))
HTTP_PORT = int(os.environ.get("TORPROXY_HTTP_PORT", 8118))
SOCKS_PORT = int(os.environ.get("TORPROXY_SOCKS_PORT", 9050))
HOST = os.environ.get("TORPROXY_HOST", "127.0.0.1")


def is_port_open(host, port, timeout=2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


# Skip the entire module if the container ports are not listening
container_listening = is_port_open(HOST, API_PORT) and is_port_open(HOST, SOCKS_PORT)
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not container_listening,
        reason=f"torproxy container is not listening on {HOST}:{API_PORT} and {SOCKS_PORT}",
    ),
]


class TestContainerRestApi:
    def test_status_endpoint(self):
        url = f"http://{HOST}:{API_PORT}/status"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "status" in data
            assert data["status"] in ("connected", "bootstrapping")
            assert "detail" in data
            assert "ip" in data

    def test_health_endpoint(self):
        url = f"http://{HOST}:{API_PORT}/health"
        with urllib.request.urlopen(url, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] in ("healthy", "bootstrapping", "disconnected")
            assert "tor" in data
            assert "proxies" in data
            assert "egress" in data

    def test_reconnect_endpoint_post(self):
        url = f"http://{HOST}:{API_PORT}/reconnect"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["action"] == "reconnect"
            assert data["status"] == "success"

    def test_legacy_get_endpoints_compatible(self):
        for endpoint in ("connect", "reconnect"):
            url = f"http://{HOST}:{API_PORT}/{endpoint}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200
                data = json.loads(resp.read().decode("utf-8"))
                assert data["action"] == endpoint
                assert data["status"] == "success"


class TestContainerSocks5Handshake:
    def test_socks5_initial_greeting_no_auth(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5.0)
            sock.connect((HOST, SOCKS_PORT))
            # Greeting: SOCKS version 5, 1 auth method, method 0x00 (NO AUTHENTICATION REQUIRED)
            sock.sendall(b"\x05\x01\x00")
            reply = sock.recv(2)
            assert reply == b"\x05\x00", f"Unexpected SOCKS5 handshake reply: {reply!r}"


class TestFailClosedAndLeakPrevention:
    def test_disconnect_and_fail_closed(self):
        # 1. Trigger Disconnect via REST API
        disc_url = f"http://{HOST}:{API_PORT}/disconnect"
        disc_req = urllib.request.Request(disc_url, method="POST")
        with urllib.request.urlopen(disc_req, timeout=5) as resp:
            assert resp.status == 200

        # 2. Verify /health reflects disconnected state
        health_url = f"http://{HOST}:{API_PORT}/health"
        with urllib.request.urlopen(health_url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "disconnected"
            assert data["tor"]["network_enabled"] is False

        # 3. Privoxy HTTP Proxy MUST fail-closed (return error / 500 / 503, NEVER clearnet)
        proxy_handler = urllib.request.ProxyHandler({"http": f"http://{HOST}:{HTTP_PORT}"})
        opener = urllib.request.build_opener(proxy_handler)
        fail_closed = False
        try:
            with opener.open("http://example.com", timeout=3) as r:
                # If Privoxy returns an error page, status might be 500 or 503
                content = r.read().decode("utf-8", errors="replace")
                if "500" in content or "503" in content or "Privoxy" in content:
                    fail_closed = True
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            fail_closed = True
        assert fail_closed is True, "Privoxy did not fail-closed when Tor was disconnected!"

        # 4. Reconnect Tor to restore service
        conn_url = f"http://{HOST}:{API_PORT}/connect"
        conn_req = urllib.request.Request(conn_url, method="POST")
        with urllib.request.urlopen(conn_req, timeout=5) as resp:
            assert resp.status == 200

        # 5. Verify /health restored
        with urllib.request.urlopen(health_url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["tor"]["network_enabled"] is True
