#!/usr/bin/env python3
"""Unified local development server for TVB docs + JupyterLite + downloadable notebooks.

Runs `myst start` on an internal port for fast incremental MDAST/page reload, and
exposes a single unified endpoint (default http://localhost:8000) that:
  - serves `/lite/*` statically from `_build/lite/` (if built)
  - serves `/notebooks/*` statically from `_build/notebooks/` (kept fresh via a light watcher)
  - serves `/glossary-search.js` from `content/_static/glossary-search.js`
  - reverse-proxies all documentation routes to `myst start`, injecting the
    glossary search script into HTML responses
"""

from __future__ import annotations

import argparse
from functools import partial
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

SITE_SEARCH_TAG = b'<script id="tvb-site-search-script" type="module" src="/site-search.mjs"></script>'


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_http(
    port: int,
    proc: subprocess.Popen,
    stop_event: threading.Event,
    timeout_s: float = 90.0,
) -> str | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if stop_event.is_set():
            return None
        if proc.poll() is not None:
            raise RuntimeError(f"myst start exited early with code {proc.returncode}")
        for host in ("localhost", "127.0.0.1"):
            url = f"http://{host}:{port}/"
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if resp.status < 500:
                        return host
            except Exception:
                pass
        stop_event.wait(0.25)
    raise TimeoutError(f"Timed out waiting for myst start on port {port}")


def terminate_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError:
            proc.terminate()
    else:
        proc.terminate()
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                proc.kill()
        else:
            proc.kill()
        proc.wait()


def md_mtime_snapshot(content_dir: Path) -> dict[Path, int]:
    snap: dict[Path, int] = {}
    for p in content_dir.rglob("*.md"):
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(content_dir).parts):
            try:
                snap[p] = p.stat().st_mtime_ns
            except OSError:
                pass
    return snap


def start_notebooks_watcher(
    root: Path,
    python_exe: str,
    notebooks_dir: Path,
    stop_event: threading.Event,
    poll_s: float = 2.0,
) -> threading.Thread:
    content_dir = root / "content"

    def run() -> None:
        prev = md_mtime_snapshot(content_dir)
        while not stop_event.wait(poll_s):
            curr = md_mtime_snapshot(content_dir)
            if curr == prev:
                continue
            prev = curr
            try:
                subprocess.run(
                    [
                        python_exe,
                        str(root / "tools" / "stage_lite.py"),
                        "--notebooks-only",
                        "--notebooks-dir",
                        str(notebooks_dir),
                    ],
                    cwd=root,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"! notebook sync failed (exit {exc.returncode})", flush=True)

    t = threading.Thread(target=run, name="notebooks-watcher", daemon=True)
    t.start()
    return t


class UnifiedDevHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(
        self,
        *args,
        root: Path,
        myst_host: str,
        myst_port: int,
        lite_dir: Path,
        notebooks_dir: Path,
        **kwargs,
    ):
        self.root = root
        self.myst_host = myst_host
        self.myst_port = myst_port
        self.lite_dir = lite_dir
        self.notebooks_dir = notebooks_dir
        super().__init__(*args, directory=str(root), **kwargs)

    def log_message(self, format: str, *args) -> None:
        # Keep terminal output quiet for routine static/asset fetches; errors still print.
        pass

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_static_under(self, base_dir: Path, rel_path: str) -> None:
        rel_clean = rel_path.lstrip("/").split("?", 1)[0]
        target = (base_dir / rel_clean).resolve()
        try:
            target.relative_to(base_dir.resolve())
        except ValueError:
            self._send_bytes(403, "text/plain; charset=utf-8", b"Forbidden")
            return

        if target.is_dir():
            index = target / "index.html"
            if index.is_file():
                target = index
            else:
                self._send_bytes(404, "text/plain; charset=utf-8", b"Not found")
                return

        if not target.is_file():
            self._send_bytes(404, "text/plain; charset=utf-8", b"Not found")
            return

        if target.suffix == ".mjs":
            ctype = "application/javascript; charset=utf-8"
        else:
            ctype, _ = mimetypes.guess_type(str(target))
            if not ctype:
                ctype = "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _handle_request(self) -> None:
        path_only = self.path.split("?", 1)[0]

        if path_only in ("/lite", "/lite/"):
            self.send_response(302)
            self.send_header("Location", "/lite/lab/index.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path_only.startswith("/lite/"):
            if not self.lite_dir.is_dir():
                msg = (
                    "<html><body style='font-family:sans-serif;padding:2rem'>"
                    "<h2>JupyterLite is not built yet</h2>"
                    "<p>Run <code>python3 make.py lite</code> (or <code>make lite</code>) "
                    "to build <code>_build/lite</code>, then refresh this page.</p>"
                    "</body></html>"
                ).encode("utf-8")
                self._send_bytes(503, "text/html; charset=utf-8", msg)
                return
            self._serve_static_under(self.lite_dir, path_only[len("/lite/"):])
            return

        if path_only.startswith("/notebooks/"):
            self._serve_static_under(self.notebooks_dir, path_only[len("/notebooks/"):])
            return

        if path_only == "/site-search.mjs":
            js_path = self.root / "content" / "_static" / "site-search.mjs"
            if js_path.is_file():
                self._send_bytes(200, "application/javascript; charset=utf-8", js_path.read_bytes())
                return

        if path_only.startswith("/vendor/"):
            self._serve_static_under(
                self.root / "content" / "_static" / "vendor",
                path_only[len("/vendor/"):],
            )
            return

        if path_only in (
            "/site-search-manifest.json",
            "/search-docs.json",
            "/search-glossary.json",
            "/api-symbols.json",
        ):
            json_path = self.root / "_build" / "html" / path_only.lstrip("/")
            if not json_path.is_file() and path_only == "/api-symbols.json":
                json_path = self.root / "_build" / "apidoc" / "api-symbols.json"
            if json_path.is_file():
                self._send_bytes(200, "application/json; charset=utf-8", json_path.read_bytes())
                return

        self._proxy_to_myst()

    def _proxy_to_myst(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        req_body = self.rfile.read(length) if length > 0 else None

        headers = {}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl in HOP_BY_HOP or kl in ("host", "accept-encoding"):
                continue
            headers[k] = v
        headers["Host"] = f"{self.myst_host}:{self.myst_port}"
        headers["Accept-Encoding"] = "identity"

        conn = http.client.HTTPConnection(self.myst_host, self.myst_port, timeout=30)
        try:
            conn.request(self.command, self.path, body=req_body, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            ctype = resp.getheader("Content-Type", "")

            if (
                "text/html" in ctype
                and b"</body>" in body
                and b'id="tvb-site-search-script"' not in body
                and (self.root / "_build" / "html" / "site-search-manifest.json").is_file()
            ):
                body = body.replace(b"</body>", SITE_SEARCH_TAG + b"</body>", 1)

            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                kl = k.lower()
                if kl in HOP_BY_HOP or kl in ("content-length", "content-encoding"):
                    continue
                if kl == "location":
                    v = v.replace(f"http://127.0.0.1:{self.myst_port}", "")
                    v = v.replace(f"http://localhost:{self.myst_port}", "")
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except Exception as exc:
            self._send_bytes(502, "text/plain; charset=utf-8", f"Proxy error: {exc}\n".encode("utf-8"))
        finally:
            conn.close()

    def do_GET(self) -> None:
        self._handle_request()

    def do_HEAD(self) -> None:
        self._handle_request()

    def do_POST(self) -> None:
        self._handle_request()

    def do_OPTIONS(self) -> None:
        self._handle_request()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live MyST dev server with unified routing.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--myst-bin", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--execute", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--lite-dir", type=Path, default=Path("_build/lite"))
    parser.add_argument("--notebooks-dir", type=Path, default=Path("_build/notebooks"))
    parser.add_argument("--state-file", type=Path, default=Path("_build/.dev-server.json"))
    args = parser.parse_args()

    root = args.root.resolve()
    lite_dir = (root / args.lite_dir if not args.lite_dir.is_absolute() else args.lite_dir).resolve()
    notebooks_dir = (root / args.notebooks_dir if not args.notebooks_dir.is_absolute() else args.notebooks_dir).resolve()
    state_file = (root / args.state_file if not args.state_file.is_absolute() else args.state_file).resolve()

    config_args: list[str] = []
    if args.config is not None:
        cfg_path = (root / args.config if not args.config.is_absolute() else args.config).resolve()
        if cfg_path.is_file():
            try:
                cfg_arg = cfg_path.relative_to(root).as_posix()
            except ValueError:
                cfg_arg = str(cfg_path)
            config_args = ["--config", cfg_arg]

    myst_port = find_free_port()
    cdn_port = find_free_port()
    myst_cmd = [
        args.myst_bin,
        "start",
        *config_args,
        "--port",
        str(myst_port),
        "--server-port",
        str(cdn_port),
        *(["--execute"] if args.execute else []),
    ]

    print(f"+ {' '.join(myst_cmd)}", flush=True)
    popen_kwargs: dict = {"cwd": root}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    myst_proc = subprocess.Popen(myst_cmd, **popen_kwargs)

    stop_event = threading.Event()
    server: ThreadingHTTPServer | None = None

    def handle_sig(*_):
        stop_event.set()
        if server is not None:
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    try:
        myst_host = wait_for_http(myst_port, myst_proc, stop_event)
        if myst_host is None:
            return 0

        handler_cls = partial(
            UnifiedDevHandler,
            root=root,
            myst_host=myst_host,
            myst_port=myst_port,
            lite_dir=lite_dir,
            notebooks_dir=notebooks_dir,
        )
        ThreadingHTTPServer.allow_reuse_address = True
        ThreadingHTTPServer.daemon_threads = True
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_cls)

        start_notebooks_watcher(root, args.python, notebooks_dir, stop_event)

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "port": args.port,
                    "myst_port": myst_port,
                    "cdn_port": cdn_port,
                    "url": f"http://localhost:{args.port}",
                    "execute": args.execute,
                    "started_at": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        lite_note = "ready" if lite_dir.is_dir() else "not built yet (run `python make.py lite`)"
        print(
            f"\nTVB dev server running at http://localhost:{args.port}\n"
            f"  - Docs (live reload, execute={args.execute}): http://localhost:{args.port}/\n"
            f"  - JupyterLite ({lite_note}): http://localhost:{args.port}/lite/lab/index.html\n"
            f"  - Downloadable notebooks: http://localhost:{args.port}/notebooks/\n"
            f"Press Ctrl+C to stop.\n",
            flush=True,
        )

        # Monitor myst_proc while serving
        def watch_myst() -> None:
            while not stop_event.is_set():
                if myst_proc.poll() is not None:
                    print(f"! myst start exited unexpectedly (code {myst_proc.returncode})", file=sys.stderr, flush=True)
                    stop_event.set()
                    if server is not None:
                        server.shutdown()
                    return
                time.sleep(0.5)

        threading.Thread(target=watch_myst, daemon=True).start()
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_event.set()
        if server is not None:
            server.server_close()
        if state_file.exists():
            try:
                state_file.unlink()
            except OSError:
                pass
        terminate_process_tree(myst_proc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
