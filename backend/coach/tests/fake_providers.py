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
        # A request that asks for a stream gets these events if set; else the JSON answer of
        # ``reply`` turned into the events the Anthropic API would send for it.
        self.events: list[object] | None = None
        # The wait before each event of a stream.
        self.event_delay = 0.0
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
                streamed = outer.stream_for(parsed)
                if streamed is not None:
                    self.send_stream(streamed)
                    return
                self.send_response(outer.status)
                if 300 <= outer.status < 400:
                    self.send_header("Location", outer.location)
                for name, value in outer.headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(outer.body) + outer.missing_bytes))
                self.end_headers()
                self.wfile.write(outer.body)

            def send_stream(self, events: list[bytes]) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                total = sum(len(event) for event in events) + outer.missing_bytes
                self.send_header("Content-Length", str(total))
                self.end_headers()
                for event in events:
                    if outer.event_delay:
                        time.sleep(outer.event_delay)
                    self.wfile.write(event)

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

    def stream_for(self, request: object) -> list[bytes] | None:
        """The events for a request that asks for a stream and gets a 200, else ``None``: an
        error status, or a body that is not JSON, is sent as it is."""
        if not isinstance(request, dict) or request.get("stream") is not True:
            return None
        if self.status != 200:
            return None
        if self.events is not None:
            return [sse(event) for event in self.events]
        try:
            message = json.loads(self.body)
        except ValueError:
            return None
        return [sse(event) for event in message_events(message)]

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


def sse(data: object) -> bytes:
    """One server-sent event, named after its type as the Anthropic API does."""
    kind = data.get("type") if isinstance(data, dict) else None
    name = f"event: {kind}\n" if isinstance(kind, str) else ""
    return f"{name}data: {json.dumps(data)}\n\n".encode()


def sse_body(message: object) -> bytes:
    """The bytes of the stream that ``message_events`` gives for ``message``."""
    return b"".join(sse(event) for event in message_events(message))


def message_events(message: object) -> list[object]:
    """The events the Anthropic API streams for ``message``, an answer as it looks without
    streaming. Text blocks arrive empty and then as a delta, other blocks as they are; the stop
    reason comes with ``message_delta``. A message of the wrong shape is passed on as it is, so
    that the checks of the reader see it."""
    if not isinstance(message, dict):
        return [{"type": "message_start", "message": message}, {"type": "message_stop"}]
    start = {k: v for k, v in message.items() if k != "stop_reason"}
    content = message.get("content")
    blocks: list[object] = []
    if isinstance(content, list):
        start["content"] = []
        for index, block in enumerate(content):
            text = block.get("text") if isinstance(block, dict) else None
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(text, str):
                blocks.append(
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {**block, "text": ""},
                    }
                )
                blocks.append(
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "text_delta", "text": text},
                    }
                )
            else:
                blocks.append(
                    {"type": "content_block_start", "index": index, "content_block": block}
                )
            blocks.append({"type": "content_block_stop", "index": index})
    end: dict[str, object] = {"type": "message_delta", "delta": {}}
    if "stop_reason" in message:
        end["delta"] = {"stop_reason": message["stop_reason"]}
    return [
        {"type": "message_start", "message": start},
        {"type": "ping"},
        *blocks,
        end,
        {"type": "message_stop"},
    ]
