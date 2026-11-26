"""Tests for MyST terminal progress tracking and dev_server immediate-bind handling."""

from __future__ import annotations

import http.server
import io
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.dev_server import DevServerState, UnifiedDevHandler  # noqa: E402
from tools.myst_progress import (  # noqa: E402
    MystProgressTracker,
    estimate_page_count,
    save_page_count,
)


class TestMystProgressTracker(unittest.TestCase):
    def test_initial_build_tty_and_callbacks(self) -> None:
        buf = io.StringIO()
        completed: list[tuple[int, str]] = []
        states: list[str] = []

        tracker = MystProgressTracker(
            total_pages=3,
            mode="build",
            stream=buf,
            is_tty=True,
            verbose=False,
            on_build_complete=lambda c, p: completed.append((c, p)),
            on_state_change=lambda s: states.append(s["phase"]),
        )
        tracker.feed_line("\x1b[32m💾 Adding cached notebook outputs (content/a.md)\x1b[0m\n")
        tracker.feed_line("\x1b[36m💿 Executing notebook (content/tutorials/first.md) [no execution cache found]\x1b[0m\n")
        tracker.feed_line("⚠️  content/a.md:10 Minor warning\n")
        tracker.feed_line("📖 Built content/tutorials/first.md in 1.2 s.\n")
        tracker.feed_line("📖 Built content/a.md in 0.1 s.\n")
        tracker.feed_line("📚 Built 2 pages for project in 1.5 s.\n")
        tracker.finish()

        out = buf.getvalue()
        self.assertIn("exec: first.md", out)
        self.assertIn("⚠️  content/a.md:10 Minor warning", out)
        self.assertIn("✓ Built 2 pages in 1.5 s.", out)
        self.assertNotIn("Adding cached notebook outputs", out)
        self.assertEqual(completed, [(2, "")])
        self.assertEqual(states[-1], "idle")

    def test_watch_single_file_and_full_rebuild(self) -> None:
        buf = io.StringIO()
        completed: list[tuple[int, str]] = []

        tracker = MystProgressTracker(
            total_pages=2,
            mode="dev",
            stream=buf,
            is_tty=False,
            verbose=False,
            on_build_complete=lambda c, p: completed.append((c, p)),
        )
        tracker.feed_line("📚 Built 2 pages for project in 1.0 s.\n")
        self.assertEqual(tracker.phase, "idle")

        # Fast markdown rebuild while idle
        tracker.feed_line("📖 Built content/user-guide/bb-coupling.md in 120 ms.\n")
        self.assertEqual(tracker.phase, "idle")
        self.assertIn("✓ Rebuilt content/user-guide/bb-coupling.md in 120 ms.", buf.getvalue())

        # Notebook watch rebuild
        tracker.feed_line("💿 Executing notebook (content/tutorials/first.md) [no execution cache found]\n")
        self.assertEqual(tracker.phase, "watch_file")
        tracker.feed_line("📖 Built content/tutorials/first.md in 2.5 s.\n")
        self.assertEqual(tracker.phase, "idle")
        self.assertIn("✓ Rebuilt content/tutorials/first.md in 2.5 s.", buf.getvalue())

        # Full site rebuild triggered in watch mode
        tracker.feed_line("💥 Triggered full site rebuild\n")
        self.assertEqual(tracker.phase, "full_rebuild")
        self.assertEqual(tracker.built_pages, 0)
        tracker.feed_line("📖 Built content/a.md in 0.1 s.\n")
        tracker.feed_line("📚 Built 1 page for project in 0.2 s.\n")
        self.assertEqual(tracker.phase, "idle")
        self.assertEqual(
            completed,
            [
                (2, ""),
                (1, "content/user-guide/bb-coupling.md"),
                (1, "content/tutorials/first.md"),
                (1, ""),
            ],
        )

    def test_estimate_and_save_page_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "content" / "tutorials").mkdir(parents=True)
            (root / "content" / "_templates").mkdir(parents=True)
            (root / "content" / "tutorials" / "a.md").write_text("# A\n", encoding="utf-8")
            (root / "content" / "_templates" / "skip.md").write_text("# Skip\n", encoding="utf-8")
            (root / "README.md").write_text("# Home\n", encoding="utf-8")

            state_file = root / "_build" / ".state.json"
            self.assertEqual(estimate_page_count(root, state_file), 2)

            save_page_count(state_file, 297)
            self.assertEqual(estimate_page_count(root, state_file), 297)


class _DummyUpstreamHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<html><body>upstream ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass


class TestDevServerImmediateBind(unittest.TestCase):
    def test_503_while_building_then_proxies_when_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_build" / "lite").mkdir(parents=True)
            (root / "_build" / "notebooks").mkdir(parents=True)

            upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _DummyUpstreamHandler)
            upstream_port = upstream.server_address[1]
            upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            upstream_thread.start()

            state = DevServerState()
            state.update_progress(
                {
                    "phase": "initial",
                    "built": 12,
                    "total": 100,
                    "executing": ["content/tutorials/first.md"],
                    "elapsed_s": 5.0,
                }
            )
            handler_cls = partial(
                UnifiedDevHandler,
                root=root,
                myst_port=upstream_port,
                lite_dir=root / "_build" / "lite",
                notebooks_dir=root / "_build" / "notebooks",
                server_state=state,
            )
            proxy = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
            proxy_port = proxy.server_address[1]
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()

            try:
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(f"http://127.0.0.1:{proxy_port}/", timeout=3)
                err = ctx.exception
                self.assertEqual(err.code, 503)
                self.assertEqual(err.headers.get("Retry-After"), "3")
                html_body = err.read().decode("utf-8")
                self.assertIn("12 / 100", html_body)
                self.assertIn("first.md", html_body)

                state.mark_ready("127.0.0.1")
                with urllib.request.urlopen(f"http://127.0.0.1:{proxy_port}/", timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertIn(b"upstream ok", resp.read())
            finally:
                proxy.shutdown()
                proxy.server_close()
                upstream.shutdown()
                upstream.server_close()


if __name__ == "__main__":
    unittest.main()
