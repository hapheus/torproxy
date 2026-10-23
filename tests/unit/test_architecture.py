import ast
import os
import subprocess
import sys
from pathlib import Path


def test_core_does_not_import_concrete_adapters_or_http():
    root = Path("src/torproxy")
    for name in (
        "configuration.py",
        "models.py",
        "ports.py",
        "state.py",
        "service.py",
        "queries.py",
        "metrics.py",
    ):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            modules = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            assert not any(
                module.startswith(
                    (
                        "torproxy.adapters",
                        "torproxy.web",
                        "http.",
                        "urllib.",
                        "socket",
                        "os",
                        "time",
                    )
                )
                for module in modules
            ), name


def test_installed_package_import_has_no_io_or_background_work(tmp_path):
    script = """
import socket, threading, logging
def forbidden(*args, **kwargs):
    raise AssertionError('Import performed external work')
socket.socket.connect = forbidden
threading.Thread.start = forbidden
before = list(logging.getLogger().handlers)
import torproxy.bootstrap
import torproxy.runtime.cli
assert list(logging.getLogger().handlers) == before
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        check=True,
        capture_output=True,
        text=True,
    )
