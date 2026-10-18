import os
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest

# Ensure docker/ directory is on sys.path for api module import
docker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docker"))
if docker_dir not in sys.path:
    sys.path.insert(0, docker_dir)

import api  # noqa: E402


@pytest.fixture(autouse=True)
def reset_ip_cache():
    api.clear_ip_cache()
    yield
    api.clear_ip_cache()


@pytest.fixture(scope="module")
def api_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.APIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
