#!/usr/bin/env python3
"""Atheris-compatible Fuzz Harness for torproxy configuration and control parsing.

Can be executed with: python scripts/fuzz_tor_control.py
Or integrated into OSS-Fuzz / ClusterFuzzLite / CI fuzzing workflows.
"""

import io
import sys

try:
    import atheris
except ImportError:
    atheris = None

from torproxy.adapters.tor_control import TorControlError, read_reply
from torproxy.configuration import Settings


class FakeSocket:
    def __init__(self, data: bytes) -> None:
        self.stream = io.BytesIO(data)

    def recv(self, bufsize: int) -> bytes:
        return self.stream.read(bufsize)


def TestOneInput(data: bytes) -> None:
    """Fuzz harness entry point: parses raw fuzzed byte strings into Tor responses and config."""
    fdp = atheris.FuzzedDataProvider(data) if atheris else None
    if fdp:
        control_stream_bytes = fdp.ConsumeBytes(128)
        country_str = fdp.ConsumeUnicodeNoSurrogates(32)
        port_str = fdp.ConsumeUnicodeNoSurrogates(16)
        strict_str = fdp.ConsumeUnicodeNoSurrogates(8)
    else:
        control_stream_bytes = data[:128]
        try:
            decoded = data.decode("utf-8", errors="replace")
        except Exception:
            return
        parts = decoded.split("\x00")
        country_str = parts[0] if len(parts) > 0 else ""
        port_str = parts[1] if len(parts) > 1 else ""
        strict_str = parts[2] if len(parts) > 2 else ""

    # Fuzz Tor Control Protocol reply parser
    fake_sock = FakeSocket(control_stream_bytes)
    try:
        read_reply(fake_sock)  # type: ignore[arg-type]
    except (TorControlError, UnicodeDecodeError, ValueError):
        # Expected parsing rejections during fuzzing
        pass

    # Fuzz Settings environment mapping parser
    env_mapping = {
        "TORPROXY_COUNTRY": country_str,
        "TORPROXY_LISTEN_PORT": port_str,
        "TORPROXY_STRICT_NODES": strict_str,
    }
    try:
        Settings.from_mapping(env_mapping)
    except ValueError:
        # Expected invalid configuration inputs during fuzzing
        pass


def main() -> None:
    if atheris:
        atheris.instrument_all()
        atheris.Setup(sys.argv, TestOneInput)
        atheris.Fuzz()
    else:
        # Hermetic regression corpus for CI / non-Atheris environments
        corpus = [
            b"",
            b"\x00",
            b"250 OK\r\n",
            b"250-STATUS/CIRCUIT=ESTABLISHED\r\n250 OK\r\n",
            b"250+INFO=\nsomething\n.\r\n250 OK\r\n",
            b"510 Unrecognized command\r\n",
            b"999 Malformed line without proper CRLF",
            b"\xff" * 128,
            b"250\x00DE\x008080\x00true",
            b"250 OK\r\n\x00US,CA\x009050\x001",
        ]
        for sample in corpus:
            TestOneInput(sample)
        print("Fuzz harness smoke verification passed successfully.")


if __name__ == "__main__":
    main()
