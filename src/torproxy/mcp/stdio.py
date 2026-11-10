"""Stdio transport for Model Context Protocol (MCP)."""

import json
import sys
from typing import TextIO

from torproxy.mcp.protocol import McpHandler


def run_stdio_server(
    handler: McpHandler,
    in_stream: TextIO | None = None,
    out_stream: TextIO | None = None,
    err_stream: TextIO | None = None,
) -> None:
    stdin = in_stream or sys.stdin
    stdout = out_stream or sys.stdout
    stderr = err_stream or sys.stderr

    for line in stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            req = json.loads(stripped)
        except json.JSONDecodeError as err:
            if stderr:
                stderr.write(f"[mcp-stdio] JSON parse error: {err}\n")
                stderr.flush()
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            stdout.write(json.dumps(err_resp) + "\n")
            stdout.flush()
            continue

        resp = handler.handle_jsonrpc(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
