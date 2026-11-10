"""Pure Python zero-dependency Model Context Protocol (MCP) handler."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from torproxy import __version__
from torproxy.queries import ProxyQueries
from torproxy.service import ControlFailure, InvalidInput, ProxyService

MCP_PROTOCOL_VERSION = "2024-11-05"
SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme not in ("http", "https"):
            raise urllib.error.URLError(
                f"Unsupported redirect URL scheme '{parsed.scheme}'. "
                "Only http and https are allowed."
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "torproxy_status",
        "description": (
            "Retrieve current Tor status, bootstrap progress, egress IP, and GeoIP metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "torproxy_get_ip",
        "description": "Query the current egress IP address routed through Tor.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "torproxy_reconnect",
        "description": (
            "Trigger a new Tor circuit/identity (SIGNAL NEWNYM), optionally switching "
            "exit country or strict nodes enforcement."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": (
                        "Optional 2-letter ISO country code or comma-separated list of country "
                        "codes (e.g. 'de' or 'de,at'). Pass 'any' or empty string to reset."
                    ),
                },
                "strict": {
                    "type": "boolean",
                    "description": (
                        "Optional boolean to strictly enforce exit nodes without fallback."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "torproxy_connect",
        "description": (
            "Enable the Tor network (SETCONF DisableNetwork=0), optionally updating "
            "country or strict nodes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": (
                        "Optional 2-letter ISO country code or comma-separated list of country "
                        "codes (e.g. 'de'). Pass 'any' or empty string to reset."
                    ),
                },
                "strict": {
                    "type": "boolean",
                    "description": (
                        "Optional boolean to strictly enforce exit nodes without fallback."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "torproxy_disconnect",
        "description": "Disable the Tor network (SETCONF DisableNetwork=1).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "torproxy_health",
        "description": "Check health status of Tor proxy, Privoxy HTTP, and SOCKS readiness.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "torproxy_diagnostics",
        "description": (
            "Detailed diagnostics including bootstrap state, circuit config, cache TTL age, "
            "reconnection metrics, and transparent gateway status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "torproxy_fetch",
        "description": (
            "Execute an HTTP/HTTPS or .onion request routed strictly through the Tor proxy."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL to fetch (HTTP, HTTPS, or .onion).",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, HEAD). Default: GET.",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers mapping string keys to string values.",
                },
                "body": {
                    "type": "string",
                    "description": "Optional string request body for POST/PUT requests.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Request timeout in seconds (default: 30).",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Max response body bytes to read (default: 1048576).",
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
]

RESOURCES_SCHEMA: list[dict[str, Any]] = [
    {
        "uri": "torproxy://status",
        "name": "Torproxy Status",
        "description": "Live JSON status of the proxy",
        "mimeType": "application/json",
    },
    {
        "uri": "torproxy://metrics",
        "name": "Torproxy Metrics",
        "description": "Prometheus telemetry metrics text",
        "mimeType": "text/plain",
    },
]


class McpHandler:
    def __init__(self, service: ProxyService, queries: ProxyQueries) -> None:
        self.service = service
        self.queries = queries

    def handle_jsonrpc(self, req: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": req.get("id") if isinstance(req, dict) else None,
                "error": {"code": -32600, "message": "Invalid Request: expected jsonrpc 2.0"},
            }

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        if "id" not in req:
            return None

        if method == "initialize":
            client_version = params.get("protocolVersion")
            negotiated_version = (
                client_version
                if isinstance(client_version, str) and client_version in SUPPORTED_PROTOCOL_VERSIONS
                else MCP_PROTOCOL_VERSION
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": negotiated_version,
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                    },
                    "serverInfo": {
                        "name": "torproxy",
                        "version": __version__,
                    },
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}

        if method == "resources/templates/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"resourceTemplates": []}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS_SCHEMA},
            }

        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            return self._call_tool(req_id, str(tool_name), args)

        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": RESOURCES_SCHEMA},
            }

        if method == "resources/read":
            uri = params.get("uri")
            return self._read_resource(req_id, str(uri))

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _call_tool(self, req_id: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "torproxy_status":
            resp = self.queries.status()
            text = json.dumps(resp.body) if isinstance(resp.body, dict) else str(resp.body)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": resp.status >= 400,
                },
            }

        if name == "torproxy_get_ip":
            resp = self.queries.ip()
            text = json.dumps(resp.body) if isinstance(resp.body, dict) else str(resp.body)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": resp.status >= 400,
                },
            }

        if name in ("torproxy_reconnect", "torproxy_connect"):
            action = "reconnect" if name == "torproxy_reconnect" else "connect"
            country = args.get("country")
            strict = args.get("strict") if "strict" in args else args.get("strict_nodes")
            try:
                res = self.service.mutate(action, country=country, strict=strict)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res)}],
                        "isError": False,
                    },
                }
            except (InvalidInput, ControlFailure) as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    },
                }

        if name == "torproxy_disconnect":
            try:
                res = self.service.mutate("disconnect")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res)}],
                        "isError": False,
                    },
                }
            except (InvalidInput, ControlFailure) as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    },
                }

        if name == "torproxy_health":
            resp = self.queries.health()
            text = json.dumps(resp.body) if isinstance(resp.body, dict) else str(resp.body)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": resp.status >= 400,
                },
            }

        if name == "torproxy_diagnostics":
            resp = self.queries.diagnostics()
            text = json.dumps(resp.body) if isinstance(resp.body, dict) else str(resp.body)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": resp.status >= 400,
                },
            }

        if name == "torproxy_fetch":
            return self._call_fetch(req_id, args)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True,
            },
        }

    def _call_fetch(self, req_id: Any, args: dict[str, Any]) -> dict[str, Any]:
        raw_url = args.get("url")
        if not raw_url or not isinstance(raw_url, str):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": "Error: Missing required 'url' parameter"}
                    ],
                    "isError": True,
                },
            }

        parsed = urllib.parse.urlparse(raw_url)
        if parsed.scheme not in ("http", "https"):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Error: Unsupported URL scheme '{parsed.scheme}'. "
                                "Only http and https are allowed."
                            ),
                        }
                    ],
                    "isError": True,
                },
            }

        method = str(args.get("method") or "GET").upper()
        headers = args.get("headers") or {}
        if not isinstance(headers, dict):
            headers = {}
        body = args.get("body")
        data = body.encode("utf-8") if isinstance(body, str) else None

        try:
            timeout = float(args.get("timeout", 30))
            if timeout <= 0:
                timeout = 30.0
        except (ValueError, TypeError):
            timeout = 30.0

        try:
            max_bytes = int(args.get("max_bytes", 1048576))
            if max_bytes <= 0:
                max_bytes = 1048576
        except (ValueError, TypeError):
            max_bytes = 1048576

        proxy_url = f"http://127.0.0.1:{self.service.settings.proxy_port}"
        proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(proxy_handler, _SafeRedirectHandler())

        req = urllib.request.Request(raw_url, data=data, headers=headers, method=method)

        try:
            with opener.open(req, timeout=timeout) as response:
                status = response.status
                resp_headers = dict(response.headers)
                raw_content = response.read(max_bytes)
                text = raw_content.decode("utf-8", errors="replace")
                result_payload = {
                    "status": status,
                    "headers": resp_headers,
                    "body": text,
                    "url": response.geturl(),
                }
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result_payload)}],
                        "isError": status >= 400,
                    },
                }
        except urllib.error.HTTPError as err:
            err_body = err.read(max_bytes).decode("utf-8", errors="replace") if err.fp else ""
            result_payload = {
                "status": err.code,
                "headers": dict(err.headers),
                "body": err_body,
                "url": raw_url,
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result_payload)}],
                    "isError": True,
                },
            }
        except Exception as err:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Fetch error: {err}"}],
                    "isError": True,
                },
            }

    def _read_resource(self, req_id: Any, uri: str) -> dict[str, Any]:
        if uri == "torproxy://status":
            resp = self.queries.status()
            text = (
                json.dumps(resp.body, indent=2) if isinstance(resp.body, dict) else str(resp.body)
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": text,
                        }
                    ]
                },
            }

        if uri == "torproxy://metrics":
            resp = self.queries.metrics()
            text = str(resp.body)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/plain",
                            "text": text,
                        }
                    ]
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": f"Unknown resource URI: {uri}"},
        }
