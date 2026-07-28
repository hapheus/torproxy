#!/usr/bin/env python3
import json
import socket
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import os

API_PORT = int(os.environ.get("TORPROXY_API_PORT", 8080))
PROXY_PORT = int(os.environ.get("TORPROXY_LISTEN_PORT", 8118))

def send_tor_command(command):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(('127.0.0.1', 9051))
        s.sendall(b'AUTHENTICATE \r\n')
        resp = s.recv(1024)
        if b'250' not in resp:
            return None, "Tor control authentication failed"
        
        s.sendall(command.encode('utf-8') + b'\r\n')
        resp = s.recv(1024)
        return resp.decode('utf-8'), None
    except Exception as e:
        return None, str(e)
    finally:
        try:
            s.close()
        except NameError:
            pass

def get_current_ip():
    proxy_support = urllib.request.ProxyHandler({
        'http': f'http://127.0.0.1:{PROXY_PORT}',
        'https': f'http://127.0.0.1:{PROXY_PORT}'
    })
    opener = urllib.request.build_opener(proxy_support)
    try:
        # 3 seconds timeout to keep API responsive
        response = opener.open('https://check.torproject.org/api/ip', timeout=3)
        data = json.loads(response.read().decode('utf-8'))
        return data.get('ip'), None
    except Exception as e:
        return None, str(e)

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
                    "ip": None,
                    "network": "disabled"
                })
                return
            
            ip, err = get_current_ip()
            if ip:
                self.send_json(200, {
                    "status": "connected",
                    "ip": ip,
                    "network": "enabled"
                })
            else:
                self.send_json(200, {
                    "status": "connecting",
                    "ip": None,
                    "network": "enabled",
                    "detail": "Failed to route traffic (Tor bootstrapping?)"
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
                self.send_json(200, {"action": "disconnect", "status": "success"})

        elif path == 'reconnect':
            _, err = send_tor_command('SIGNAL NEWNYM')
            if err:
                self.send_json(500, {"error": f"Failed to trigger reconnect: {err}"})
            else:
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
