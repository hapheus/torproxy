"""Environment access and process lifetime belong at the executable boundary."""

import argparse
import os
import sys

from torproxy import __version__
from torproxy.bootstrap import create_server
from torproxy.configuration import Settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="torproxy",
        description="Tor HTTP and SOCKS5 proxy runtime and control REST API.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)

    server = create_server(Settings.from_mapping(os.environ))
    try:
        print(f"Starting API server on port {server.server_port}...", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        # Graceful shutdown initiated by user interrupt (Ctrl+C) or termination signal
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
