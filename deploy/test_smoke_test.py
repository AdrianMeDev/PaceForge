"""Regression checks for the smoke test itself; no Docker daemon is required."""

import unittest
from unittest.mock import Mock, patch

import smoke_test


class SmokeTestTests(unittest.TestCase):
    def test_proxy_trust_is_absent_by_default_and_explicit_when_enabled(self):
        self.assertNotIn("DJANGO_TRUST_PROXY_HEADERS", smoke_test.backend_env(False))
        self.assertEqual(smoke_test.backend_env(True)["DJANGO_TRUST_PROXY_HEADERS"], "true")

    def test_every_asset_is_requested_and_a_missing_asset_fails(self):
        html = """<app-root></app-root>
            <script src="double.js"></script>
            <script src='single.js'></script>
            <SCRIPT SRC = unquoted.js></SCRIPT>
            <link rel="stylesheet" href="double.css">
            <link href='single.css' rel='stylesheet'>
            <LINK HREF = unquoted.css REL = STYLESHEET>
        """
        headers = {
            "Cache-Control": "no-cache",
            "Content-Security-Policy": "script-src 'self'; object-src 'none'",
        }
        page = Mock(status=200)
        page.getheader.side_effect = headers.get
        requested = []

        def fetch(_connection, path):
            requested.append(path)
            if path == "/settings/security":
                return page, html
            return Mock(status=404 if path == "/single.css" else 200), ""

        with (
            patch.object(smoke_test, "SniConnection"),
            patch.object(smoke_test, "fetch", side_effect=fetch),
            patch.object(smoke_test, "failures", []) as failures,
            patch("builtins.print"),
        ):
            smoke_test.test_spa_through_caddy(443)
            self.assertEqual(
                requested,
                [
                    "/settings/security",
                    "/double.js",
                    "/single.js",
                    "/unquoted.js",
                    "/double.css",
                    "/single.css",
                    "/unquoted.css",
                ],
            )
            self.assertEqual(failures, ["asset /single.css -> 200 (got 404)"])


if __name__ == "__main__":
    unittest.main()
