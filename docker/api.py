#!/usr/bin/env python3
import json
import socket
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import os
import time
import re

API_PORT = int(os.environ.get("TORPROXY_API_PORT", 8080))
PROXY_PORT = int(os.environ.get("TORPROXY_LISTEN_PORT", 8118))

# IP Caching configuration
IP_CACHE_TTL = 30  # seconds
_cached_ip = None
_cached_ip_time = 0

def send_tor_command(command):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(('127.0.0.1', 9051))
            s.sendall(b'AUTHENTICATE\r\n')
            resp = s.recv(1024)
            if b'250' not in resp:
                return None, "Tor control authentication failed"
            
            s.sendall(command.encode('utf-8') + b'\r\n')
            resp = s.recv(1024)
            return resp.decode('utf-8'), None
    except Exception as e:
        return None, str(e)

def clear_ip_cache():
    global _cached_ip, _cached_ip_time
    _cached_ip = None
    _cached_ip_time = 0

def get_current_ip():
    global _cached_ip, _cached_ip_time
    now = time.time()
    if _cached_ip and (now - _cached_ip_time < IP_CACHE_TTL):
        return _cached_ip, None

    proxy_support = urllib.request.ProxyHandler({
        'http': f'http://127.0.0.1:{PROXY_PORT}',
        'https': f'http://127.0.0.1:{PROXY_PORT}'
    })
    opener = urllib.request.build_opener(proxy_support)
    try:
        # 3 seconds timeout to keep API responsive
        response = opener.open('https://check.torproject.org/api/ip', timeout=3)
        data = json.loads(response.read().decode('utf-8'))
        # check.torproject.org uses an uppercase "IP" key. Accept the
        # lowercase variant as well for compatibility with equivalent APIs.
        ip = data.get('IP') or data.get('ip')
        if ip:
            _cached_ip = ip
            _cached_ip_time = now
            return ip, None
        return None, "No IP key in response"
    except Exception as e:
        return None, str(e)

def get_tor_bootstrap_status():
    resp, err = send_tor_command('GETINFO status/bootstrap-phase')
    if err:
        return None, f"Failed to query Tor control: {err}"
    
    # Example format: 250-status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=100 TAG=done SUMMARY="Handshake..."
    match = re.search(r'PROGRESS=(\d+)\s+TAG=(\S+)\s+SUMMARY="([^"]+)"', resp)
    if match:
        progress = int(match.group(1))
        tag = match.group(2)
        summary = match.group(3)
        return {
            "progress": progress,
            "tag": tag,
            "summary": summary,
            "bootstrapped": progress == 100
        }, None
    return None, "Failed to parse bootstrap status"

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Print logs to stdout for Docker logging
        print(f"[API] {self.address_string()} - - {format%args}")

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def handle_request(self):
        path = self.path.strip('/')
        
        if path in ('status', ''):
            resp, err = send_tor_command('GETCONF DisableNetwork')
            if err:
                self.send_json(500, {"error": f"Failed to query Tor: {err}"})
                return
            
            network_enabled = "DisableNetwork=0" in resp
            
            if not network_enabled:
                self.send_json(200, {
                    "status": "disconnected",
                    "ip": None
                })
                return
            
            # Query Tor's internal bootstrap status
            bootstrap, b_err = get_tor_bootstrap_status()
            if not bootstrap or not bootstrap["bootstrapped"]:
                detail = bootstrap["summary"] if bootstrap else (b_err or "Unknown bootstrap status")
                self.send_json(200, {
                    "status": "connecting",
                    "ip": None,
                    "detail": f"Tor bootstrapping: {detail}"
                })
                return
            
            ip, err = get_current_ip()
            if ip:
                self.send_json(200, {
                    "status": "connected",
                    "ip": ip
                })
            else:
                self.send_json(200, {
                    "status": "connecting",
                    "ip": None,
                    "detail": f"Failed to route traffic (Tor bootstrapping?): {err}"
                })

        elif path == 'ip':
            ip, err = get_current_ip()
            if ip:
                self.send_json(200, {"ip": ip})
            else:
                self.send_json(503, {"error": "Could not retrieve IP. Proxy may be offline or connecting.", "detail": err})

        elif path == 'connect':
            _, err = send_tor_command('SETCONF DisableNetwork=0')
            if err:
                self.send_json(500, {"error": f"Failed to enable Tor network: {err}"})
            else:
                self.send_json(200, {"action": "connect", "status": "success"})

        elif path == 'disconnect':
            _, err = send_tor_command('SETCONF DisableNetwork=1')
            if err:
                self.send_json(500, {"error": f"Failed to disable Tor network: {err}"})
            else:
                clear_ip_cache()
                self.send_json(200, {"action": "disconnect", "status": "success"})

        elif path == 'reconnect':
            _, err = send_tor_command('SIGNAL NEWNYM')
            if err:
                self.send_json(500, {"error": f"Failed to trigger reconnect: {err}"})
            else:
                clear_ip_cache()
                self.send_json(200, {"action": "reconnect", "status": "success"})

        else:
            self.send_json(404, {"error": "Not Found", "supported_paths": ["/status", "/ip", "/connect", "/disconnect", "/reconnect"]})

def run():
    server_address = ('0.0.0.0', API_PORT)
    httpd = ThreadingHTTPServer(server_address, APIHandler)
    print(f"Starting API server on port {API_PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == '__main__':
    run()
