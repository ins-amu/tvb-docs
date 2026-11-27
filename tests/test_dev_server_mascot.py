"""Tests for About-page goat mascot asset serving and script injection in dev_server."""

from __future__ import annotations

from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import sys
import tempfile
import threading
import unittest
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import dev_server  # noqa: E402


class _MockMystHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:
        body = (
            b"<!doctype html><html><body>"
            b'<div class="tvb-about-mascot"></div>'
            b"</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestDevServerMascot(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmp.name)

        self.upstream = HTTPServer(("127.0.0.1", 0), _MockMystHandler)
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever, daemon=True)
        self.upstream_thread.start()

        handler = partial(
            dev_server.UnifiedDevHandler,
            root=ROOT,
            myst_host="127.0.0.1",
            myst_port=self.upstream.server_port,
            lite_dir=tmp_path / "lite",
            notebooks_dir=tmp_path / "notebooks",
            server_state=None,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()
        self._tmp.cleanup()

    def test_serves_goat_opus_and_about_mascot_mjs(self) -> None:
        with urllib.request.urlopen(f"{self.base_url}/goat.opus") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "audio/ogg")
            self.assertEqual(resp.read(), (ROOT / "_static" / "goat.opus").read_bytes())

        with urllib.request.urlopen(f"{self.base_url}/about-mascot.mjs") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "application/javascript; charset=utf-8")
            self.assertEqual(
                resp.read(),
                (ROOT / "content" / "_static" / "about-mascot.mjs").read_bytes(),
            )

    def test_injects_about_mascot_script_into_proxied_html(self) -> None:
        with urllib.request.urlopen(f"{self.base_url}/about-this-site") as resp:
            self.assertEqual(resp.status, 200)
            html_bytes = resp.read()
        expected_tag = dev_server.ABOUT_MASCOT_TAG
        self.assertIn(expected_tag + b"</body>", html_bytes)
        self.assertEqual(html_bytes.count(b'id="tvb-about-mascot-script"'), 1)


if __name__ == "__main__":
    unittest.main()
