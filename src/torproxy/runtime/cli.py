"""Environment access and process lifetime belong at the executable boundary."""

import argparse
import os
import sys
import threading

from torproxy import __version__
from torproxy.bootstrap import create_mcp_handler, create_mcp_server, create_server
from torproxy.configuration import Settings
from torproxy.mcp.stdio import run_stdio_server


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
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "mcp",
        help="Run Model Context Protocol (MCP) server over stdio",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_mapping(os.environ)

    if args.command == "mcp":
        handler = create_mcp_handler(settings)
        run_stdio_server(handler)
        return 0

    server = create_server(settings)
    mcp_server = None
    if settings.mcp_enabled:
        service = getattr(getattr(server, "router", None), "service", None)
        handler = create_mcp_handler(settings, service=service)
        mcp_server = create_mcp_server(settings, handler=handler)
        threading.Thread(target=mcp_server.serve_forever, daemon=True).start()
        print(f"Starting MCP SSE server on port {mcp_server.server_address[1]}...", flush=True)

    try:
        print(f"Starting API server on port {server.server_port}...", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        # Graceful shutdown initiated by user interrupt (Ctrl+C) or termination signal
        pass
    finally:
        if mcp_server is not None:
            mcp_server.shutdown()
            mcp_server.server_close()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
