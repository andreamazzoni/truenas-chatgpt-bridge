"""TEST ONLY: loopback NAS TLS/WebSocket and empty control-plane fixture.

Never installed in the production image. No real network or credentials.
"""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socketserver
import ssl
import struct
import threading
import time


def exact(stream, size):
    data = b""
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise EOFError
        data += part
    return data


def receive(stream):
    first, second = exact(stream, 2)
    size = second & 127
    if size == 126:
        size, = struct.unpack("!H", exact(stream, 2))
    elif size == 127:
        size, = struct.unpack("!Q", exact(stream, 8))
    if size > 1048576 or first & 15 == 8:
        raise EOFError
    mask = exact(stream, 4) if second & 128 else b""
    body = exact(stream, size)
    if mask:
        body = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
    return json.loads(body)


def send(stream, value):
    body = json.dumps(value).encode()
    header = bytes([129, len(body)]) if len(body) < 126 else bytes([129, 126]) + struct.pack("!H", len(body))
    stream.write(header + body)
    stream.flush()


class NAS(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            request_path = self.rfile.readline().decode().split()[1]
            legacy = request_path == "/websocket"
            if request_path not in ("/websocket", "/api/current"):
                self.wfile.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
                return
            headers = {}
            while line := self.rfile.readline().strip():
                key, value = line.decode().split(":", 1)
                headers[key.lower()] = value.strip()
            accept = base64.b64encode(hashlib.sha1((headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + "\r\n\r\n").encode())
            self.wfile.flush()
            authenticated = False
            while True:
                req = receive(self.rfile)
                if legacy and req.get("msg") == "connect":
                    send(self.wfile, {"msg": "connected", "session": "fixture"})
                    continue
                method = req.get("method")
                if legacy and method == "auth.login_with_api_key":
                    expected = Path("/run/secrets/truenas_api_key").read_text().strip()
                    authenticated = req.get("params") == [expected]
                    result = authenticated
                elif not legacy and method == "auth.login_ex":
                    expected = Path("/run/secrets/truenas_api_key").read_text().strip()
                    authenticated = req.get("params") == [{"mechanism": "API_KEY_PLAIN", "username": "fixture-user", "api_key": expected}]
                    result = {"response_type": "SUCCESS" if authenticated else "AUTH_ERR"}
                elif method == "system.info" and authenticated:
                    result = {"version": "FIXTURE", "hostname": "fixture"}
                else:
                    send(self.wfile, {"id": req.get("id"), **({"msg": "result"} if legacy else {"jsonrpc": "2.0"}), "error": {"code": -32000, "message": "fixture rejected method"}})
                    continue
                send(self.wfile, {"id": req["id"], **({"msg": "result"} if legacy else {"jsonrpc": "2.0"}), "result": result})
        except (EOFError, OSError, ValueError, KeyError):
            pass  # Includes no-credential TLS preflight connecting and closing.


class NASServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ControlPlane(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if "/poll?" in self.path:
            time.sleep(1)
            self.send_response(204)
            self.end_headers()
        else:
            body = json.dumps({"id": "tunnel_" + "a" * 32, "name": "offline-fixture"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


if __name__ == "__main__":
    nas = NASServer(("127.0.0.1", 9443), NAS)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/etc/bridge/truenas-ca.pem", "/tests/server.key")
    nas.socket = context.wrap_socket(nas.socket, server_side=True)
    threading.Thread(target=nas.serve_forever, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", 9080), ControlPlane).serve_forever()
