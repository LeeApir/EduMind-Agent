"""Serve only the local review artifact on loopback; no API, signing or directory listing."""

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "local-materials/catalog-course-review-20261003.html"


class ReviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/catalog-course-review-20261003.html"):
            self.send_error(404)
            return
        content = PREVIEW.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    print("Local review: http://127.0.0.1:4187/", flush=True)
    HTTPServer(("127.0.0.1", 4187), ReviewHandler).serve_forever()
