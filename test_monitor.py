"""Integration tests use only short-lived servers started by this test module."""

import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace

from loopglass.monitor import Scanner, discover_listeners, is_web_app, stop_listener

HTTP_SERVER = r'''
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(('127.0.0.1', 0), Handler)
print(server.server_address[1], flush=True)
server.serve_forever()
'''


HTTPS_SERVER = r'''
import ssl
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(204)
        self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(('127.0.0.1', 0), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(sys.argv[1], sys.argv[2])
server.socket = context.wrap_socket(server.socket, server_side=True)
print(server.server_address[1], flush=True)
server.serve_forever()
'''

RAW_SERVER = r'''
import socket
s = socket.socket()
s.bind(('127.0.0.1', 0))
s.listen()
print(s.getsockname()[1], flush=True)
while True:
    client, _ = s.accept()
    client.sendall(b'NOT HTTP\n')
    client.close()
'''

STUBBORN_SERVER = r'''
import socket
import signal
signal.signal(signal.SIGTERM, signal.SIG_IGN)
s = socket.socket()
s.bind(('127.0.0.1', 0))
s.listen()
print(s.getsockname()[1], flush=True)
while True:
    client, _ = s.accept()
    client.recv(1024)
    client.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 0\r\n\r\n')
    client.close()
'''


class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
            child.stdout.close()
            child.stderr.close()

    def start_server(self, code, *args, cwd=None):
        child = subprocess.Popen([sys.executable, "-u", "-c", code, *args],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, cwd=cwd)
        self.children.append(child)
        line = child.stdout.readline().strip()
        if not line:
            self.fail(f"test server exited before listening: {child.stderr.read()}")
        return child, int(line)

    def find(self, child, port):
        for _ in range(30):
            matches = [item for item in discover_listeners()
                       if item.pid == child.pid and item.port == port]
            if matches:
                return matches[0]
            time.sleep(0.05)
        self.fail(f"test listener {child.pid}:{port} was not discovered")

    def test_http_classification_and_graceful_stop(self):
        child, port = self.start_server(HTTP_SERVER)
        item = self.find(child, port)
        scanner = Scanner()
        classified = next(x for x in scanner.scan() if x.key == item.key)
        self.assertEqual(classified.protocol, "http")
        self.assertEqual(classified.url, f"http://127.0.0.1:{port}/")
        self.assertEqual(classified.scope, "Loopback only")
        self.assertTrue(is_web_app(classified))
        self.assertFalse(is_web_app(replace(classified, cwd="/usr/bin")))
        self.assertTrue(is_web_app(replace(classified, cwd="/tmp")))
        self.assertTrue(is_web_app(replace(classified, cwd="/mnt/my-project")))
        self.assertTrue(stop_listener(classified).closed)
        child.wait(timeout=3)

    def test_http_server_outside_home_is_in_main_view(self):
        child, port = self.start_server(HTTP_SERVER, cwd="/tmp")
        item = self.find(child, port)
        classified = next(x for x in Scanner().scan() if x.key == item.key)
        self.assertEqual(classified.cwd, "/tmp")
        self.assertEqual(classified.protocol, "http")
        self.assertTrue(is_web_app(classified))
        self.assertTrue(stop_listener(classified).closed)
        child.wait(timeout=3)

    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL is needed to create a test certificate")
    def test_https_classification(self):
        with tempfile.TemporaryDirectory() as folder:
            cert, key = f"{folder}/cert.pem", f"{folder}/key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048",
                            "-nodes", "-keyout", key, "-out", cert,
                            "-subj", "/CN=localhost", "-days", "1"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            child, port = self.start_server(HTTPS_SERVER, cert, key)
            item = self.find(child, port)
            classified = next(x for x in Scanner().scan() if x.key == item.key)
            self.assertEqual(classified.protocol, "https")
            self.assertEqual(classified.url, f"https://127.0.0.1:{port}/")
            self.assertTrue(stop_listener(classified).closed)
            child.wait(timeout=3)

    def test_non_http_stays_in_other_ports(self):
        child, port = self.start_server(RAW_SERVER)
        item = self.find(child, port)
        classified = next(x for x in Scanner().scan() if x.key == item.key)
        self.assertIsNone(classified.protocol)
        self.assertFalse(stop_listener(classified).closed)
        self.assertIsNone(child.poll())

    def test_identity_and_socket_guard(self):
        child, port = self.start_server(HTTP_SERVER)
        item = replace(self.find(child, port), protocol="http")
        self.assertFalse(stop_listener(replace(item, started=item.started + 10)).closed)
        self.assertFalse(stop_listener(replace(item, port=port + 1)).closed)
        self.assertIsNone(child.poll())

    def test_force_only_after_graceful_failure(self):
        child, port = self.start_server(STUBBORN_SERVER)
        item = replace(self.find(child, port), protocol="http")
        result = stop_listener(item, wait_seconds=0.3)
        self.assertFalse(result.closed)
        self.assertTrue(result.can_force)
        self.assertIsNone(child.poll())
        self.assertTrue(stop_listener(item, force=True).closed)
        child.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
