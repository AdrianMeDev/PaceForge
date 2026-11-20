#!/usr/bin/env python3
"""Smoke test for the production images and the production Caddyfile.

Build the images first (``docker compose -f compose.prod.yaml build``), then run
``python3 deploy/smoke_test.py``. The test starts the frontend, the backend and Caddy on an
ephemeral Docker network and publishes their ports on dynamic loopback ports only, so it never
uses host ports 80 or 443 and does not touch ``compose.dev.yaml``. Everything it creates is
removed on exit. It needs only the Python standard library and the Docker CLI.
"""

from __future__ import annotations

import base64
import http.client
import os
import re
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CADDYFILE = REPO / "deploy" / "Caddyfile"

FRONTEND_IMAGE = os.environ.get("FRONTEND_IMAGE", "paceforge-frontend:local")
BACKEND_IMAGE = os.environ.get("BACKEND_IMAGE", "paceforge-backend:local")
CADDY_IMAGE = "caddy:2.10-alpine"
DOMAIN = "localhost"

RUN_ID = uuid.uuid4().hex[:8]
NETWORK = f"paceforge-smoke-{RUN_ID}"
ECHO_NETWORK = f"{NETWORK}-echo"
LABEL = f"paceforge-smoke={RUN_ID}"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def docker(*args: str, check_rc: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check_rc and result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def start(name: str, image: str, *args: str, alias: str | None = None, env=None, **kw) -> str:
    """Start a detached container on a smoke network. Ports go to 127.0.0.1 only."""
    network = kw.get("network", NETWORK)
    cmd = ["run", "-d", "--name", f"{NETWORK}-{name}", "--label", LABEL, "--network", network]
    if alias:
        cmd += ["--network-alias", alias]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    for port in kw.get("publish", []):
        cmd += ["-p", f"127.0.0.1::{port}"]
    for volume in kw.get("volumes", []):
        cmd += ["-v", volume]
    cmd.append(image)
    cmd += args
    docker(*cmd)
    return f"{NETWORK}-{name}"


def host_port(container: str, port: int) -> int:
    out = docker("port", container, f"{port}/tcp").stdout.splitlines()[0]
    return int(out.rsplit(":", 1)[1])


class SniConnection(http.client.HTTPSConnection):
    """HTTPS to 127.0.0.1 that sends SNI ``localhost`` and accepts Caddy's local certificate."""

    def __init__(self, port: int) -> None:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__("127.0.0.1", port, timeout=10, context=context)

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=DOMAIN)


def fetch(conn: http.client.HTTPConnection, path: str, headers=None):
    conn.request("GET", path, headers={"Host": DOMAIN, **(headers or {})})
    response = conn.getresponse()
    body = response.read().decode("utf-8", errors="replace")
    conn.close()
    return response, body


def plain(port: int) -> http.client.HTTPConnection:
    return http.client.HTTPConnection("127.0.0.1", port, timeout=10)


def wait_for(description: str, probe, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    last: object = None
    while time.monotonic() < deadline:
        try:
            if probe():
                return
        except (OSError, http.client.HTTPException, RuntimeError, ValueError) as exc:
            last = exc
        time.sleep(1)
    raise RuntimeError(f"{description} not ready after {timeout:.0f}s (last error: {last})")


def status_is_200(conn_factory, path: str):
    def probe() -> bool:
        response, _ = fetch(conn_factory(), path)
        return response.status == 200

    return probe


def backend_env(trust_proxy: bool) -> dict[str, str]:
    env = {
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "DJANGO_ALLOWED_HOSTS": DOMAIN,
        "APP_DOMAIN": DOMAIN,
        # The health endpoint never touches the database, and nothing sends mail. The deploy
        # check only needs a database password and a non-console mail backend to be set.
        "DATABASE_URL": f"postgres://smoke:{secrets.token_hex(8)}@db.invalid:5432/smoke",
        "SMTP_HOST": "smtp.invalid",
        "AUTO_MIGRATE": "false",
    }
    # Leave the variable absent on the untrusted backend to exercise the default.
    if trust_proxy:
        env["DJANGO_TRUST_PROXY_HEADERS"] = "true"
    return env


class AssetParser(HTMLParser):
    """Collect script and stylesheet URLs using HTML attribute parsing rules."""

    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script":
            url = attributes.get("src")
        elif tag == "link" and "stylesheet" in (attributes.get("rel") or "").lower().split():
            url = attributes.get("href")
        else:
            return
        if url:
            self.assets.append(url)


def test_static_server_user_and_routes(frontend: str, frontend_port: int) -> None:
    print("static frontend container")
    script = (
        "id -un; "
        "touch /srv/new-file 2>/dev/null && echo dir-writable || echo dir-readonly; "
        "echo x >> /srv/index.html 2>/dev/null && echo file-writable || echo file-readonly"
    )
    out = docker("exec", frontend, "sh", "-c", script).stdout.split()
    check(out[:1] == ["paceforge"], f"runs as paceforge (got {out[:1]})")
    check("dir-readonly" in out, "paceforge cannot write to /srv")
    check("file-readonly" in out, "paceforge cannot write to /srv/index.html")

    for path in ("/api/health/", "/api"):
        response, body = fetch(plain(frontend_port), path)
        check(
            response.status == 404 and "<app-root>" not in body,
            f"direct GET {path} -> 404 without <app-root> (got {response.status})",
        )
    response, body = fetch(plain(frontend_port), "/settings/security")
    check(
        response.status == 200 and "<app-root>" in body,
        f"direct GET /settings/security -> 200 with <app-root> (got {response.status})",
    )


# Stands in for the backend behind Caddy and answers with the X-Forwarded-Proto it received.
ECHO_SERVER = (
    "import http.server as h\n"
    "class H(h.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        body = self.headers.get('X-Forwarded-Proto', '').encode()\n"
    "        self.send_response(200)\n"
    "        self.send_header('Content-Length', str(len(body)))\n"
    "        self.end_headers()\n"
    "        self.wfile.write(body)\n"
    "h.HTTPServer(('0.0.0.0', 8000), H).serve_forever()\n"
)


def test_scheme_forwarding(echo_caddy_port: int, trusted_port: int, untrusted_port: int) -> None:
    print("scheme forwarding")
    response, body = fetch(
        SniConnection(echo_caddy_port), "/api/echo/", {"X-Forwarded-Proto": "http"}
    )
    check(
        body == "https",
        f"Caddy overwrites a spoofed X-Forwarded-Proto: http with https (backend saw {body!r})",
    )

    response, _ = fetch(plain(untrusted_port), "/api/health/", {"X-Forwarded-Proto": "https"})
    check(
        response.status == 200 and response.getheader("Strict-Transport-Security") is None,
        "backend without DJANGO_TRUST_PROXY_HEADERS ignores X-Forwarded-Proto: https (no HSTS)",
    )

    response, _ = fetch(plain(trusted_port), "/api/health/", {"X-Forwarded-Proto": "https"})
    check(
        response.getheader("Strict-Transport-Security") is not None,
        "backend with DJANGO_TRUST_PROXY_HEADERS honors X-Forwarded-Proto: https (HSTS set)",
    )


def test_api_through_caddy(caddy_port: int) -> None:
    print("API through Caddy")
    response, body = fetch(SniConnection(caddy_port), "/api/health/")
    check(
        response.status == 200 and body.replace(" ", "") == '{"status":"ok"}',
        f"GET /api/health/ -> 200 {{'status': 'ok'}} (got {response.status} {body[:60]!r})",
    )
    for path in ("/api/does-not-exist/", "/api"):
        response, body = fetch(SniConnection(caddy_port), path)
        check(
            response.status == 404 and "<app-root>" not in body,
            f"GET {path} -> 404 without <app-root> (got {response.status})",
        )


def test_spa_through_caddy(caddy_port: int) -> None:
    print("SPA through Caddy")
    response, html = fetch(SniConnection(caddy_port), "/settings/security")
    check(
        response.status == 200 and "<app-root>" in html,
        f"deep link /settings/security -> 200 with <app-root> (got {response.status})",
    )
    check(
        response.getheader("Cache-Control") == "no-cache",
        f"Cache-Control: no-cache (got {response.getheader('Cache-Control')!r})",
    )
    csp = response.getheader("Content-Security-Policy") or ""
    directives = {part.strip().split(" ", 1)[0]: part.strip() for part in csp.split(";")}
    check(
        directives.get("script-src") == "script-src 'self'",
        f"CSP restricts script-src to 'self' (got {directives.get('script-src')!r})",
    )
    check(
        directives.get("object-src") == "object-src 'none'",
        f"CSP sets object-src 'none' (got {directives.get('object-src')!r})",
    )

    inline_script = re.search(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>", html, re.I)
    check(inline_script is None, "no inline <script> in the served HTML")
    check(
        re.search(r"<[^>]+\son[a-z]+\s*=", html, re.I) is None,
        "no inline on*= event handlers in the served HTML",
    )
    check(
        re.search(r"<(object|embed)\b", html, re.I) is None,
        "no <object> or <embed> in the served HTML",
    )

    parser = AssetParser()
    parser.feed(html)
    assets = parser.assets
    check(
        any(a.endswith(".js") for a in assets) and any(a.endswith(".css") for a in assets),
        f"HTML references JS and CSS assets (found {assets})",
    )
    for asset in assets:
        path = asset if asset.startswith("/") else f"/{asset}"
        response, _ = fetch(SniConnection(caddy_port), path)
        check(response.status == 200, f"asset {path} -> 200 (got {response.status})")


def cleanup() -> None:
    names = docker("ps", "-aq", "--filter", f"label={LABEL}", check_rc=False).stdout.split()
    if names:
        docker("rm", "-f", "-v", *names, check_rc=False)
    for network in (NETWORK, ECHO_NETWORK):
        docker("network", "rm", network, check_rc=False)


def main() -> int:
    for image in (FRONTEND_IMAGE, BACKEND_IMAGE):
        if docker("image", "inspect", image, check_rc=False).returncode != 0:
            print(f"Image {image} not found. Run: docker compose -f compose.prod.yaml build")
            return 2

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        for network in (NETWORK, ECHO_NETWORK):
            docker("network", "create", "--label", LABEL, network)

        frontend = start("frontend", FRONTEND_IMAGE, alias="frontend", publish=[8080])
        trusted = start(
            "backend", BACKEND_IMAGE, alias="backend", env=backend_env(True), publish=[8000]
        )
        untrusted = start(
            "backend-untrusted", BACKEND_IMAGE, env=backend_env(False), publish=[8000]
        )
        caddy = start(
            "caddy",
            CADDY_IMAGE,
            env={"APP_DOMAIN": DOMAIN},
            volumes=[f"{CADDYFILE}:/etc/caddy/Caddyfile:ro"],
            publish=[443],
        )

        # The same Caddyfile in front of an echo server, on its own network so that the alias
        # "backend" stays unique.
        start(
            "echo",
            BACKEND_IMAGE,
            "python",
            "-c",
            ECHO_SERVER,
            alias="backend",
            network=ECHO_NETWORK,
        )
        echo_caddy = start(
            "echo-caddy",
            CADDY_IMAGE,
            env={"APP_DOMAIN": DOMAIN},
            volumes=[f"{CADDYFILE}:/etc/caddy/Caddyfile:ro"],
            publish=[443],
            network=ECHO_NETWORK,
        )

        frontend_port = host_port(frontend, 8080)
        echo_caddy_port = host_port(echo_caddy, 443)
        trusted_port = host_port(trusted, 8000)
        untrusted_port = host_port(untrusted, 8000)
        caddy_port = host_port(caddy, 443)

        wait_for("frontend", status_is_200(lambda: plain(frontend_port), "/healthz"))
        wait_for("backend", status_is_200(lambda: plain(trusted_port), "/api/health/"))
        wait_for(
            "backend (untrusted)", status_is_200(lambda: plain(untrusted_port), "/api/health/")
        )
        wait_for("caddy", status_is_200(lambda: SniConnection(caddy_port), "/api/health/"))
        wait_for("echo", status_is_200(lambda: SniConnection(echo_caddy_port), "/api/echo/"))

        test_static_server_user_and_routes(frontend, frontend_port)
        test_scheme_forwarding(echo_caddy_port, trusted_port, untrusted_port)
        test_api_through_caddy(caddy_port)
        test_spa_through_caddy(caddy_port)
    except Exception as exc:
        print(f"ERROR: {exc}")
        failures.append(str(exc))
    finally:
        cleanup()

    if failures:
        print(f"\n{len(failures)} check(s) failed")
        return 1
    print("\nAll smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
