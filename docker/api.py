#!/usr/bin/env python3
import json
import os
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tor_control

API_PORT = int(os.environ.get("TORPROXY_API_PORT", "8080"))
PROXY_PORT = int(os.environ.get("TORPROXY_LISTEN_PORT", "8118"))
SOCKS_PORT = int(os.environ.get("TORPROXY_SOCKS_PORT", "9050"))

# IP Caching configuration
IP_CACHE_TTL = 30  # seconds
_cache_lock = threading.Lock()
_cached_ip = None
_cached_ip_time = 0

# Runtime metrics tracking
_start_time = time.time()
_metrics_lock = threading.Lock()
_reconnect_count = 0
_last_reconnect_time = None

# Active country exit node tracking
_country_lock = threading.Lock()
_active_country = None
_active_strict_nodes = None
_country_state_initialized = False


def send_tor_command(command):
    return tor_control.send_command(command)


def clear_ip_cache():
    global _cached_ip, _cached_ip_time
    with _cache_lock:
        _cached_ip = None
        _cached_ip_time = 0


def record_reconnect():
    global _reconnect_count, _last_reconnect_time
    with _metrics_lock:
        _reconnect_count += 1
        _last_reconnect_time = time.time()


def reset_metrics():
    global _start_time, _reconnect_count, _last_reconnect_time
    with _metrics_lock:
        _start_time = time.time()
        _reconnect_count = 0
        _last_reconnect_time = None


def get_configured_country():
    val = os.environ.get("TORPROXY_COUNTRY") or os.environ.get("TORPROXY_EXIT_COUNTRY") or ""
    val = val.strip()
    return val.upper() if val else None


def get_strict_nodes():
    val = os.environ.get("TORPROXY_STRICT_NODES")
    if val is not None:
        return val.strip().lower() in ("1", "true", "yes")
    return bool(get_configured_country())


def get_current_country():
    global _country_state_initialized, _active_country, _active_strict_nodes
    with _country_lock:
        if not _country_state_initialized:
            _active_country = get_configured_country()
            _active_strict_nodes = get_strict_nodes()
            _country_state_initialized = True
        return _active_country


def get_current_strict_nodes():
    global _country_state_initialized, _active_country, _active_strict_nodes
    with _country_lock:
        if not _country_state_initialized:
            _active_country = get_configured_country()
            _active_strict_nodes = get_strict_nodes()
            _country_state_initialized = True
        return _active_strict_nodes


def set_current_country_state(country, strict_nodes=None):
    global _country_state_initialized, _active_country, _active_strict_nodes
    with _country_lock:
        _active_country = country
        if strict_nodes is not None:
            _active_strict_nodes = strict_nodes
        _country_state_initialized = True


def reset_country_state():
    global _country_state_initialized, _active_country, _active_strict_nodes
    with _country_lock:
        _active_country = None
        _active_strict_nodes = None
        _country_state_initialized = False


def validate_country_input(country_input):
    """Validates country input.

    Accepts:
      - string: "DE", "DE,AT", "de, at", "", "none", "any", "all", "*"
      - list: ["DE", "AT"]
      - None (unspecified)
    Returns:
      (tor_exit_nodes_param, normalized_country_string, error_message)
    """
    if country_input is None:
        return None, None, None

    if isinstance(country_input, list):
        parts = [str(item).strip() for item in country_input]
    elif isinstance(country_input, str):
        raw = country_input.strip()
        if raw.lower() in ("", "any", "all", "none", "*"):
            return "", None, None
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        return None, None, "Invalid country parameter format. Expected string or array of strings."

    if not parts:
        return "", None, None

    normalized = []
    tor_nodes = []
    for p in parts:
        if not re.match(r"^[a-zA-Z]{2}$", p):
            return None, None, f"Invalid ISO country code: '{p}'. Must be 2-letter alpha code."
        normalized.append(p.upper())
        tor_nodes.append(f"{{{p.lower()}}}")

    return ",".join(tor_nodes), ",".join(normalized), None


def validate_strict_nodes_input(strict_input):
    """Validates strict_nodes input.

    Accepts: bool, int (0, 1), or str ("1", "0", "true", "false", "yes", "no").
    Returns: (strict_bool, error_message)
    """
    if strict_input is None:
        return None, None
    if isinstance(strict_input, bool):
        return strict_input, None
    if isinstance(strict_input, int):
        if strict_input in (0, 1):
            return bool(strict_input), None
        return None, "strict_nodes integer must be 0 or 1"
    if isinstance(strict_input, str):
        s = strict_input.strip().lower()
        if s in ("1", "true", "yes"):
            return True, None
        if s in ("0", "false", "no"):
            return False, None
        return None, f"Invalid boolean value for strict_nodes: '{strict_input}'"
    return None, "strict_nodes must be boolean, integer (0/1), or boolean string"


def check_socks5_ready(port=None, timeout=1.5):
    """Verifies that Tor's SOCKS5 proxy accepts connections and completes a handshake."""
    target_port = port or SOCKS_PORT
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(("127.0.0.1", target_port))
            # SOCKS5 greeting: version 5, 1 auth method (0x00 = No authentication)
            s.sendall(b"\x05\x01\x00")
            resp = s.recv(2)
            return resp == b"\x05\x00"
    except Exception:  # noqa: BLE001
        return False


def get_current_ip():
    global _cached_ip, _cached_ip_time
    now = time.time()
    with _cache_lock:
        if _cached_ip and (now - _cached_ip_time < IP_CACHE_TTL):
            return _cached_ip, None

    proxy_support = urllib.request.ProxyHandler({
        "http": f"http://127.0.0.1:{PROXY_PORT}",
        "https": f"http://127.0.0.1:{PROXY_PORT}",
    })
    opener = urllib.request.build_opener(proxy_support)
    try:
        # 3 seconds timeout to keep API responsive
        response = opener.open("https://check.torproject.org/api/ip", timeout=3)
        data = json.loads(response.read().decode("utf-8"))

        is_tor = data.get("IsTor")
        if is_tor is None:
            is_tor = data.get("is_tor")

        if is_tor is False:
            return None, "Tor check service reported traffic NOT routed through Tor (IsTor=false)"
        if is_tor is not True:
            return None, "Tor check service response missing IsTor confirmation"

        # check.torproject.org uses an uppercase "IP" key. Accept the
        # lowercase variant as well for compatibility with equivalent APIs.
        ip = data.get("IP") or data.get("ip")
        if ip:
            with _cache_lock:
                _cached_ip = ip
                _cached_ip_time = now
            return ip, None
        return None, "No IP key in response"
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def get_tor_bootstrap_status():
    resp, err = send_tor_command("GETINFO status/bootstrap-phase")
    if err:
        return None, f"Failed to query Tor control: {err}"

    # Format: 250-status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=100 TAG=done SUMMARY="..."
    match = re.search(r'PROGRESS=(\d+)\s+TAG=(\S+)\s+SUMMARY="([^"]+)"', resp)
    if match:
        progress = int(match.group(1))
        tag = match.group(2)
        summary = match.group(3)
        return {
            "progress": progress,
            "tag": tag,
            "summary": summary,
            "bootstrapped": progress == 100,
        }, None
    return None, "Failed to parse bootstrap status"


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Print logs to stdout for Docker logging without leaking query params or sensitive details
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        msg = format % args
        # Mask query strings to ensure URLs / sensitive tokens are never printed
        msg = re.sub(r'(\s/[^?\s]*)\?[^\s]*(\s)', r'\1?REDACTED\2', msg)
        print(f"[API] {timestamp} - {msg}")

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def send_text(self, status_code, text, content_type="text/plain; charset=utf-8"):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.strip("/")
        query_params = urllib.parse.parse_qs(parsed.query)

        req_country = query_params.get("country", [None])[0]
        req_strict = query_params.get("strict_nodes", query_params.get("strict", [None]))[0]

        if self.command == "POST":
            content_length_str = self.headers.get("Content-Length")
            if content_length_str:
                try:
                    content_length = int(content_length_str)
                    if content_length > 0:
                        body_bytes = self.rfile.read(content_length)
                        body_data = json.loads(body_bytes.decode("utf-8"))
                        if isinstance(body_data, dict):
                            if "country" in body_data:
                                req_country = body_data["country"]
                            if "strict_nodes" in body_data:
                                req_strict = body_data["strict_nodes"]
                            elif "strict" in body_data:
                                req_strict = body_data["strict"]
                except Exception as e:
                    self.send_json(400, {"error": f"Malformed JSON request body: {e}"})
                    return

        if path in ("status", ""):
            resp, err = send_tor_command("GETCONF DisableNetwork")
            if err:
                self.send_json(500, {"error": f"Failed to query Tor: {err}"})
                return

            network_enabled = "DisableNetwork=0" in resp

            if not network_enabled:
                self.send_json(200, {
                    "status": "disconnected",
                    "ip": None,
                })
                return

            # Query Tor's internal bootstrap status
            bootstrap, b_err = get_tor_bootstrap_status()
            if not bootstrap or not bootstrap["bootstrapped"]:
                detail = (
                    bootstrap["summary"]
                    if bootstrap
                    else (b_err or "Unknown bootstrap status")
                )
                self.send_json(200, {
                    "status": "connecting",
                    "ip": None,
                    "detail": f"Tor bootstrapping: {detail}",
                })
                return

            ip, err = get_current_ip()
            if ip:
                self.send_json(200, {
                    "status": "connected",
                    "ip": ip,
                })
            else:
                self.send_json(200, {
                    "status": "connecting",
                    "ip": None,
                    "detail": f"Failed to route traffic (Tor bootstrapping?): {err}",
                })

        elif path == "ip":
            ip, err = get_current_ip()
            if ip:
                self.send_json(200, {"ip": ip})
            else:
                self.send_json(503, {
                    "error": "Could not retrieve IP. Proxy may be offline or connecting.",
                    "detail": err,
                })

        elif path in ("connect", "reconnect"):
            tor_nodes, norm_country, c_err = validate_country_input(req_country)
            if c_err:
                self.send_json(400, {"error": c_err})
                return

            strict_bool, s_err = validate_strict_nodes_input(req_strict)
            if s_err:
                self.send_json(400, {"error": s_err})
                return

            if req_country is not None:
                cmd = f"SETCONF ExitNodes={tor_nodes}" if tor_nodes else "SETCONF ExitNodes="
                _, err = send_tor_command(cmd)
                if err:
                    self.send_json(500, {"error": f"Failed to configure ExitNodes in Tor: {err}"})
                    return

            if strict_bool is not None:
                val = 1 if strict_bool else 0
                _, err = send_tor_command(f"SETCONF StrictNodes={val}")
                if err:
                    self.send_json(500, {"error": f"Failed to configure StrictNodes in Tor: {err}"})
                    return

            if req_country is not None or strict_bool is not None:
                new_country = norm_country if req_country is not None else get_current_country()
                new_strict = (
                    strict_bool if strict_bool is not None else get_current_strict_nodes()
                )
                set_current_country_state(new_country, new_strict)

            if path == "connect":
                _, err = send_tor_command("SETCONF DisableNetwork=0")
                if err:
                    self.send_json(500, {"error": f"Failed to enable Tor network: {err}"})
                else:
                    clear_ip_cache()
                    resp_data = {"action": "connect", "status": "success"}
                    curr_c = get_current_country()
                    if curr_c:
                        resp_data["exit_country"] = curr_c
                        resp_data["strict_nodes"] = get_current_strict_nodes()
                    self.send_json(200, resp_data)
            else:
                _, err = send_tor_command("SIGNAL NEWNYM")
                if err:
                    self.send_json(500, {"error": f"Failed to trigger reconnect: {err}"})
                else:
                    clear_ip_cache()
                    record_reconnect()
                    resp_data = {"action": "reconnect", "status": "success"}
                    curr_c = get_current_country()
                    if curr_c:
                        resp_data["exit_country"] = curr_c
                        resp_data["strict_nodes"] = get_current_strict_nodes()
                    self.send_json(200, resp_data)

        elif path == "disconnect":
            _, err = send_tor_command("SETCONF DisableNetwork=1")
            if err:
                self.send_json(500, {"error": f"Failed to disable Tor network: {err}"})
            else:
                clear_ip_cache()
                self.send_json(200, {"action": "disconnect", "status": "success"})

        elif path in ("health", "v1/health"):
            resp, err = send_tor_command("GETCONF DisableNetwork")
            if err:
                self.send_json(503, {
                    "status": "unhealthy",
                    "error": f"Failed to query Tor control: {err}",
                })
                return

            network_enabled = "DisableNetwork=0" in resp
            country = get_current_country()
            strict_nodes = get_current_strict_nodes()

            if not network_enabled:
                self.send_json(200, {
                    "status": "disconnected",
                    "tor": {
                        "network_enabled": False,
                        "bootstrapped": False,
                        "progress": 0,
                        "exit_country": country,
                        "strict_nodes": strict_nodes,
                    },
                    "proxies": {
                        "socks5": False,
                    },
                    "egress": {
                        "verified": False,
                        "ip": None,
                    },
                })
                return

            bootstrap, b_err = get_tor_bootstrap_status()
            bootstrapped = bool(bootstrap and bootstrap.get("bootstrapped"))
            socks_ready = check_socks5_ready()

            if not bootstrapped:
                progress = bootstrap.get("progress", 0) if bootstrap else 0
                summary = (
                    bootstrap.get("summary", b_err or "Bootstrapping")
                    if bootstrap
                    else (b_err or "Unknown")
                )
                self.send_json(200, {
                    "status": "bootstrapping",
                    "tor": {
                        "network_enabled": True,
                        "bootstrapped": False,
                        "progress": progress,
                        "summary": summary,
                        "exit_country": country,
                        "strict_nodes": strict_nodes,
                    },
                    "proxies": {
                        "socks5": socks_ready,
                    },
                    "egress": {
                        "verified": False,
                        "ip": None,
                    },
                })
                return

            ip, ip_err = get_current_ip()
            overall_status = "healthy" if ip and socks_ready else "degraded"

            self.send_json(200, {
                "status": overall_status,
                "tor": {
                    "network_enabled": True,
                    "bootstrapped": True,
                    "progress": 100,
                    "summary": "Done",
                    "exit_country": country,
                    "strict_nodes": strict_nodes,
                },
                "proxies": {
                    "socks5": socks_ready,
                },
                "egress": {
                    "verified": bool(ip),
                    "ip": ip,
                    "error": ip_err if not ip else None,
                },
            })

        elif path in ("diagnostics", "v1/diagnostics"):
            now = time.time()
            uptime = round(now - _start_time, 2)
            started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_start_time))
            last_reconnect_iso = (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_last_reconnect_time))
                if _last_reconnect_time
                else None
            )

            bootstrap, b_err = get_tor_bootstrap_status()
            socks_ready = check_socks5_ready()
            ip, ip_err = get_current_ip()

            resp, _ = send_tor_command("GETCONF DisableNetwork")
            network_enabled = "DisableNetwork=0" in (resp or "")

            with _metrics_lock:
                rec_count = _reconnect_count

            self.send_json(200, {
                "uptime_seconds": uptime,
                "started_at": started_at,
                "last_reconnect_at": last_reconnect_iso,
                "reconnect_count": rec_count,
                "tor": {
                    "network_enabled": network_enabled,
                    "bootstrapped": bool(bootstrap and bootstrap.get("bootstrapped")),
                    "progress": bootstrap.get("progress", 0) if bootstrap else 0,
                    "summary": (
                        bootstrap.get("summary", b_err or "Unknown")
                        if bootstrap
                        else (b_err or "Unknown")
                    ),
                    "exit_country": get_current_country(),
                    "strict_nodes": get_current_strict_nodes(),
                },
                "proxies": {
                    "socks5_ready": socks_ready,
                    "socks_port": SOCKS_PORT,
                    "http_port": PROXY_PORT,
                },
                "egress": {
                    "verified": bool(ip),
                    "ip": ip,
                    "error": ip_err if not ip else None,
                },
            })

        elif path in ("metrics", "v1/metrics"):
            now = time.time()
            uptime = round(now - _start_time, 2)
            bootstrap, _ = get_tor_bootstrap_status()
            progress = bootstrap.get("progress", 0) if bootstrap else 0
            bootstrapped = 1 if (bootstrap and bootstrap.get("bootstrapped")) else 0
            socks_ready = 1 if check_socks5_ready() else 0
            country_str = get_current_country() or ""
            strict_val = 1 if get_current_strict_nodes() else 0

            with _metrics_lock:
                rec_count = _reconnect_count

            metrics_lines = [
                "# HELP torproxy_uptime_seconds Total container API uptime in seconds",
                "# TYPE torproxy_uptime_seconds gauge",
                f"torproxy_uptime_seconds {uptime}",
                "",
                "# HELP torproxy_reconnect_total Total circuit reconnect requests triggered",
                "# TYPE torproxy_reconnect_total counter",
                f"torproxy_reconnect_total {rec_count}",
                "",
                "# HELP torproxy_tor_bootstrapped Tor bootstrap status (1=done, 0=in progress)",
                "# TYPE torproxy_tor_bootstrapped gauge",
                f"torproxy_tor_bootstrapped {bootstrapped}",
                "",
                "# HELP torproxy_tor_bootstrap_progress Tor bootstrap progress percentage",
                "# TYPE torproxy_tor_bootstrap_progress gauge",
                f"torproxy_tor_bootstrap_progress {progress}",
                "",
                "# HELP torproxy_socks5_ready SOCKS5 listener probe (1=ready, 0=down)",
                "# TYPE torproxy_socks5_ready gauge",
                f"torproxy_socks5_ready {socks_ready}",
                "",
                "# HELP torproxy_strict_nodes Tor StrictNodes setting (1=strict, 0=flexible)",
                "# TYPE torproxy_strict_nodes gauge",
                f"torproxy_strict_nodes {strict_val}",
                "",
                "# HELP torproxy_exit_country_info Configured exit country code",
                "# TYPE torproxy_exit_country_info gauge",
                f'torproxy_exit_country_info{{country="{country_str}"}} 1',
                "",
            ]
            self.send_text(
                200,
                "\n".join(metrics_lines),
                content_type="text/plain; version=0.0.4; charset=utf-8",
            )

        else:
            self.send_json(404, {
                "error": "Not Found",
                "supported_paths": [
                    "/status",
                    "/ip",
                    "/connect",
                    "/disconnect",
                    "/reconnect",
                    "/health",
                    "/diagnostics",
                    "/metrics",
                ],
            })


def run():
    server_address = ("0.0.0.0", API_PORT)
    httpd = ThreadingHTTPServer(server_address, APIHandler)
    print(f"Starting API server on port {API_PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()
