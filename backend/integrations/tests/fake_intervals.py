"""A local HTTP server that plays Intervals.icu, so the client is tested over real connections."""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeIntervals:
    def __init__(self) -> None:
        self.status = 200
        self.body: bytes = b'{"id": "i123"}'
        # Answers for single paths (without the query), e.g. "/api/v1/athlete/0/sport-settings".
        self.bodies: dict[str, bytes] = {}
        self.headers: dict[str, str] = {}
        self.delay = 0.0
        # Announce more bytes than are sent, then hang up: an answer that is cut off.
        self.missing_bytes = 0
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.requests.append(
                    {"method": "GET", "path": self.path, "headers": dict(self.headers.items())}
                )
                if outer.delay:
                    time.sleep(outer.delay)
                body = outer.bodies.get(self.path.split("?")[0], outer.body)
                self.send_response(outer.status)
                for name, value in outer.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body) + outer.missing_bytes))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/api/v1"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@contextmanager
def running() -> Iterator[FakeIntervals]:
    fake = FakeIntervals()
    fake.start()
    try:
        yield fake
    finally:
        fake.stop()
