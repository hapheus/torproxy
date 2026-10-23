import json
import socket
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from torproxy.adapters import tor_control


def test_compose_passes_country_configuration():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text())
    environment = compose["services"]["torproxy"]["environment"]
    for name in ("TORPROXY_COUNTRY", "TORPROXY_STRICT_NODES", "TORPROXY_EXIT_COUNTRY"):
        assert name in environment


@pytest.mark.parametrize("body", [b"[]", b"null", b"123", b'"DE"'])
def test_mutations_reject_non_object_json(api_server, body):
    request = urllib.request.Request(f"{api_server}/reconnect", data=body, method="POST")
    with patch("tests.support.api.send_tor_command") as command:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=3)
        assert error.value.code == 400
        command.assert_not_called()


def test_oversized_body_rejected_before_commands(api_server):
    request = urllib.request.Request(
        f"{api_server}/reconnect",
        data=json.dumps({"padding": "x" * 17000}).encode(),
        method="POST",
    )
    with patch("tests.support.api.send_tor_command") as command:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=3)
        assert error.value.code == 413
        command.assert_not_called()


def test_control_cookie_failure_never_attempts_empty_authentication():
    sock = MagicMock()
    sock.recv.return_value = b"250 OK\r\n"
    ok, error = tor_control.authenticate(sock, cookie_path="/nonexistent/cookie")
    assert ok is False
    assert error
    sock.sendall.assert_not_called()


def test_control_rejects_command_injection_before_connecting():
    with patch("socket.socket") as constructor:
        response, error = tor_control.send_command("SIGNAL NEWNYM\r\nSETCONF DisableNetwork=0")
    assert response is None
    assert error
    constructor.assert_not_called()


def test_incomplete_http_body_cannot_hold_worker_forever(api_server):
    port = int(api_server.rsplit(":", 1)[1])
    with socket.create_connection(("127.0.0.1", port), timeout=7) as client:
        client.sendall(b"POST /reconnect HTTP/1.0\r\nContent-Length: 10\r\n\r\n{")
        assert b"408" in client.recv(4096)
