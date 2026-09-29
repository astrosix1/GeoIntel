"""
Static file server for local frontend development — a drop-in replacement
for `python -m http.server` that adds a real Cache-Control header.

Why this exists: the plain stdlib http.server sends no Cache-Control at
all, so a browser reload can silently serve a stale app.js/app.css/
index.html after an edit without ever hitting the network — the exact
confusion that repeatedly required a disposable no-cache server to verify
changes during development. Every response here is explicitly no-cache.
"""
import http.server
import socketserver
import sys
import os

os.chdir(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, must-revalidate')
        super().end_headers()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    with socketserver.TCPServer(('', port), NoCacheHandler) as httpd:
        print(f'Serving frontend (no-cache) on port {port}')
        httpd.serve_forever()
