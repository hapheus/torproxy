import threading

import pytest

from tests.support import api
from torproxy.adapters.tor_control import TorControlClient
from torproxy.configuration import Settings
from torproxy.state import RuntimeState
from torproxy.web.router import Router
from torproxy.web.server import ProxyHTTPServer


@pytest.fixture(autouse=True)
def reset_api_state(tmp_path):
    cookie = tmp_path / "control_auth_cookie"
    cookie.write_bytes(b"\x01" * 32)
    api.settings = Settings(cookie_path=str(cookie))
    api.control = TorControlClient(9051, str(cookie))
    api.state = RuntimeState(None, False, api.state.clock)
    yield


@pytest.fixture(scope="module")
def api_server():
    server = ProxyHTTPServer(("127.0.0.1", 0), Router(api), Settings())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
