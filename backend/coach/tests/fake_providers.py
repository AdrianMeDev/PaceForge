"""A local HTTP server that plays an AI provider, for tests over real connections."""

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeProvider:
    def __init__(self) -> None:
        self.status = 200
        self.body: bytes = b"{}"
        self.headers: dict[str, str] = {}
        self.delay = 0.0
        # Announce more bytes than are sent, then hang up: an answer that is cut off.
        self.missing_bytes = 0
        # Answer with a redirect to another path of this server (``status`` 3xx).
        self.location = "/elsewhere"
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    parsed: Any = json.loads(raw)
                except ValueError:
                    parsed = None
                outer.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        # The server tidies "//x" into "/x" in ``path``; this is what was sent.
                        "raw_path": self.requestline.split()[1],
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "json": parsed,
                    }
                )
                if outer.delay:
                    time.sleep(outer.delay)
                self.send_response(outer.status)
                if 300 <= outer.status < 400:
                    self.send_header("Location", outer.location)
                for name, value in outer.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(outer.body) + outer.missing_bytes))
                self.end_headers()
                self.wfile.write(outer.body)

            def do_GET(self) -> None:
                outer.requests.append({"method": "GET", "path": self.path})
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

    def reply(self, data: object, status: int = 200) -> None:
        self.status = status
        self.body = json.dumps(data).encode("utf-8")

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@contextmanager
def running() -> Iterator[FakeProvider]:
    fake = FakeProvider()
    fake.start()
    try:
        yield fake
    finally:
        fake.stop()
