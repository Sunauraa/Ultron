"""Serve the fixture pages and log what they send: POST /submit (an application) and GET /leak (a hidden field read),
and each load of the framed form wide_gem.html.
Usage: python server.py PORT LOG"""

import http.server
import sys
from pathlib import Path

LOG = Path(sys.argv[2])


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_GET(self):
        if self.path.startswith("/leak"):
            with LOG.open("a") as f:
                f.write(f"LEAK {self.path}\n")
            self.send_response(204)
            self.end_headers()
            return
        if self.path.startswith("/wide_gem.html"):  # the framed form: loaded once means it was filled in its frame
            with LOG.open("a") as f:
                f.write(f"GET {self.path}\n")
        super().do_GET()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        with LOG.open("a") as f:
            f.write(f"POST {self.path} {body}\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
