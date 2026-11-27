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
from dataclasses import dataclass, field
from functools import partial
import html
import http.client
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Callable
import urllib.request

_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from myst_progress import MystProgressTracker, estimate_page_count, save_page_count  # noqa: E402

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


@dataclass
class DevServerState:
    """Thread-safe readiness and build progress state shared with HTTP handlers."""

    myst_host: str | None = None
    myst_ready: bool = False
    myst_exited: int | None = None
    last_activity: float = field(default_factory=time.monotonic)
    progress: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def touch(self) -> None:
        with self._lock:
            self.last_activity = time.monotonic()

    def update_progress(self, snap: dict) -> None:
        with self._lock:
            self.progress = dict(snap)
            self.last_activity = time.monotonic()

    def mark_ready(self, host: str) -> None:
        with self._lock:
            self.myst_host = host
            self.myst_ready = True
            self.last_activity = time.monotonic()

    def mark_exited(self, code: int) -> None:
        with self._lock:
            self.myst_exited = code

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "myst_host": self.myst_host,
                "myst_ready": self.myst_ready,
                "myst_exited": self.myst_exited,
                "last_activity": self.last_activity,
                "progress": dict(self.progress),
            }


def sync_exec_cache(src_dir: Path, dst_dir: Path) -> int:
    """Copy or hardlink ``*.ipynb`` execution cache files from ``src_dir`` to ``dst_dir``."""
    if not src_dir.is_dir():
        return 0
    synced = 0
    try:
        dst_dir.mkdir(parents=True, exist_ok=True)
        for item in src_dir.iterdir():
            if item.suffix != ".ipynb" or not item.is_file():
                continue
            target = dst_dir / item.name
            try:
                if target.is_file():
                    try:
                        if os.path.samefile(item, target):
                            continue
                    except OSError:
                        pass
                    if target.stat().st_size == item.stat().st_size:
                        continue
                    target.unlink()
                try:
                    os.link(item, target)
                except OSError:
                    shutil.copy2(item, target)
                synced += 1
            except OSError:
                continue
    except OSError:
        return synced
    return synced


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
    deadline = time.monotonic() + timeout_s if timeout_s > 0 else None
    while deadline is None or time.monotonic() < deadline:
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
    raise TimeoutError(f"Timed out after {timeout_s:.0f}s waiting for myst start on port {port}")


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
    log_fn: Callable[[str], None] = print,
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
                res = subprocess.run(
                    [
                        python_exe,
                        str(root / "tools" / "stage_lite.py"),
                        "--notebooks-only",
                        "--notebooks-dir",
                        str(notebooks_dir),
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                for line in (res.stdout or "").splitlines():
                    if line.strip():
                        log_fn(line)
            except subprocess.CalledProcessError as exc:
                msg = (exc.stderr or exc.stdout or "").strip()
                detail = f": {msg}" if msg else ""
                log_fn(f"! notebook sync failed (exit {exc.returncode}){detail}")

    t = threading.Thread(target=run, name="notebooks-watcher", daemon=True)
    t.start()
    return t


def _render_building_html(snap: dict) -> bytes:
    prog = snap.get("progress") or {}
    built = int(prog.get("built", 0) or 0)
    total = max(1, int(prog.get("total", 1) or 1))
    pct = min(100, int(built * 100 / total))
    elapsed_s = int(prog.get("elapsed_s", 0) or 0)
    mins, secs = divmod(max(0, elapsed_s), 60)
    executing = prog.get("executing") or []
    exec_html = ""
    if executing:
        names = ", ".join(html.escape(os.path.basename(str(p))) for p in executing[:3])
        if len(executing) > 3:
            names += f" (+{len(executing) - 3} more)"
        exec_html = f"<p><strong>Executing:</strong> <code>{names}</code></p>"
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta http-equiv='refresh' content='3'>"
        "<title>TVB Docs — Building…</title>"
        "<style>body{font-family:system-ui,-apple-system,sans-serif;max-width:600px;"
        "margin:4rem auto;padding:0 1.5rem;color:#1f2937;line-height:1.5}"
        ".bar{background:#e5e7eb;border-radius:6px;height:14px;overflow:hidden;margin:1rem 0}"
        ".fill{background:#2563eb;height:100%;transition:width .3s}</style></head>"
        "<body><h2>Building TVB Documentation…</h2>"
        f"<p>Built <strong>{built} / {total}</strong> pages ({pct}%) &middot; {mins:02d}:{secs:02d} elapsed.</p>"
        f"<div class='bar'><div class='fill' style='width:{pct}%'></div></div>"
        f"{exec_html}"
        "<p style='color:#6b7280;font-size:0.9rem'>This page refreshes automatically. "
        "For prose-only edits without notebook execution, run "
        "<code>python3 make.py dev --no-execute</code>.</p></body></html>"
    )
    return body.encode("utf-8")


class UnifiedDevHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(
        self,
        *args,
        root: Path,
        myst_host: str = "127.0.0.1",
        myst_port: int,
        lite_dir: Path,
        notebooks_dir: Path,
        server_state: DevServerState | None = None,
        **kwargs,
    ):
        self.root = root
        self.myst_host = myst_host
        self.myst_port = myst_port
        self.lite_dir = lite_dir
        self.notebooks_dir = notebooks_dir
        self.server_state = server_state
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

        if path_only in ("/the-hillside.jpg", "/the-goat.jpg"):
            img_path = self.root / "_static" / path_only.lstrip("/")
            if img_path.is_file():
                self._serve_static_under(self.root / "_static", path_only.lstrip("/"))
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

        if self.server_state is not None:
            snap = self.server_state.snapshot()
            if not snap["myst_ready"]:
                body = _render_building_html(snap)
                self.send_response(503, "Service Unavailable")
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Retry-After", "3")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
                return

        self._proxy_to_myst()

    def _proxy_to_myst(self) -> None:
        myst_host = self.myst_host
        if self.server_state is not None:
            myst_host = self.server_state.snapshot()["myst_host"] or myst_host

        length = int(self.headers.get("Content-Length") or "0")
        req_body = self.rfile.read(length) if length > 0 else None

        headers = {}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl in HOP_BY_HOP or kl in ("host", "accept-encoding"):
                continue
            headers[k] = v
        headers["Host"] = f"{myst_host}:{self.myst_port}"
        headers["Accept-Encoding"] = "identity"

        conn = http.client.HTTPConnection(myst_host, self.myst_port, timeout=30)
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
    parser.add_argument(
        "--exec-cache-dir",
        type=Path,
        default=None,
        help="Optional shared directory to persist _build/execute/*.ipynb files",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=None,
        help="Inactivity timeout in seconds while waiting for myst start (default: 600 with --execute, 120 without)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    lite_dir = (root / args.lite_dir if not args.lite_dir.is_absolute() else args.lite_dir).resolve()
    notebooks_dir = (root / args.notebooks_dir if not args.notebooks_dir.is_absolute() else args.notebooks_dir).resolve()
    state_file = (root / args.state_file if not args.state_file.is_absolute() else args.state_file).resolve()
    exec_cache_dir = (
        (root / args.exec_cache_dir if not args.exec_cache_dir.is_absolute() else args.exec_cache_dir).resolve()
        if args.exec_cache_dir is not None
        else None
    )
    build_state_file = root / "_build" / ".state.json"

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

    stop_event = threading.Event()
    server_state = DevServerState()
    total_pages = estimate_page_count(root, build_state_file)
    server_state.update_progress({"phase": "initial", "built": 0, "total": total_pages, "executing": [], "elapsed_s": 0.0})

    def on_build_complete(count: int, _path: str) -> None:
        if count > 1:
            save_page_count(build_state_file, count)
        if exec_cache_dir is not None and args.execute:
            sync_exec_cache(root / "_build" / "execute", exec_cache_dir)

    tracker = MystProgressTracker(
        total_pages=total_pages,
        mode="dev",
        on_build_complete=on_build_complete,
        on_state_change=server_state.update_progress,
    )

    handler_cls = partial(
        UnifiedDevHandler,
        root=root,
        myst_port=myst_port,
        lite_dir=lite_dir,
        notebooks_dir=notebooks_dir,
        server_state=server_state,
    )
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer.daemon_threads = True
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_cls)

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

    tracker.print_line(f"+ {' '.join(myst_cmd)}")
    tracker.print_line(f"TVB dev server listening at http://localhost:{args.port} (building docs...)")
    exec_dir = root / "_build" / "execute"
    if args.execute and (not exec_dir.is_dir() or not any(exec_dir.glob("*.ipynb"))):
        tracker.print_line(
            "Note: _build/execute is empty; initial notebook execution can take a few minutes "
            "(use `python3 make.py dev --no-execute` for prose-only edits)."
        )

    myst_env = os.environ.copy()
    if "JUPYTER_CONFIG_DIR" not in myst_env:
        jupyter_cfg = root / "_build" / "jupyter_config"
        jupyter_cfg.mkdir(parents=True, exist_ok=True)
        myst_env["JUPYTER_CONFIG_DIR"] = str(jupyter_cfg)
    popen_kwargs: dict = {
        "cwd": root,
        "env": myst_env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    myst_proc = subprocess.Popen(myst_cmd, **popen_kwargs)

    def handle_sig(*_):
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    startup_timeout = args.startup_timeout
    if startup_timeout is None:
        # `myst start --execute` runs uncached notebooks before opening its HTTP port.
        startup_timeout = 600.0 if args.execute else 120.0

    exit_code = 0
    exit_lock = threading.Lock()

    def set_error_exit(code: int = 1) -> None:
        nonlocal exit_code
        with exit_lock:
            if exit_code == 0:
                exit_code = code

    def myst_output_reader() -> None:
        assert myst_proc.stdout is not None
        try:
            for line in myst_proc.stdout:
                server_state.touch()
                tracker.feed_line(line)
        except ValueError:
            pass

    def probe_myst_ready() -> None:
        lite_note = "ready" if lite_dir.is_dir() else "not built yet (run `python make.py lite`)"
        while not stop_event.is_set():
            rc = myst_proc.poll()
            if rc is not None:
                server_state.mark_exited(rc)
                tracker.print_line(f"! myst start exited early with code {rc}")
                set_error_exit(rc or 1)
                stop_event.set()
                server.shutdown()
                return
            if startup_timeout > 0:
                idle_for = time.monotonic() - server_state.snapshot()["last_activity"]
                if idle_for > startup_timeout:
                    tracker.print_line(
                        f"! Timed out after {startup_timeout:.0f}s with no myst start activity on port {myst_port}"
                    )
                    set_error_exit(1)
                    stop_event.set()
                    server.shutdown()
                    return
            for host in ("localhost", "127.0.0.1"):
                url = f"http://{host}:{myst_port}/"
                try:
                    with urllib.request.urlopen(url, timeout=1.0) as resp:
                        if resp.status < 500:
                            server_state.mark_ready(host)
                            tracker.print_line(
                                f"\nTVB dev server ready at http://localhost:{args.port}\n"
                                f"  - Docs (live reload, execute={args.execute}): http://localhost:{args.port}/\n"
                                f"  - JupyterLite ({lite_note}): http://localhost:{args.port}/lite/lab/index.html\n"
                                f"  - Downloadable notebooks: http://localhost:{args.port}/notebooks/\n"
                                "Press Ctrl+C to stop.\n"
                            )
                            return
                except Exception:
                    pass
            stop_event.wait(0.25)

    def watch_myst() -> None:
        while not stop_event.is_set():
            if server_state.snapshot()["myst_ready"]:
                rc = myst_proc.poll()
                if rc is not None:
                    server_state.mark_exited(rc)
                    tracker.print_line(f"! myst start exited unexpectedly (code {rc})")
                    set_error_exit(rc or 1)
                    stop_event.set()
                    server.shutdown()
                    return
            stop_event.wait(0.5)

    reader_thread = threading.Thread(target=myst_output_reader, name="myst-output-reader", daemon=True)
    reader_thread.start()
    threading.Thread(target=probe_myst_ready, name="myst-ready-probe", daemon=True).start()
    threading.Thread(target=watch_myst, name="myst-watcher", daemon=True).start()

    tracker.start_ticker()
    start_notebooks_watcher(root, args.python, notebooks_dir, stop_event, log_fn=tracker.print_line)

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_event.set()
        tracker.finish()
        server.server_close()
        if state_file.exists():
            try:
                state_file.unlink()
            except OSError:
                pass
        terminate_process_tree(myst_proc)
        reader_thread.join(timeout=1.0)
        if exec_cache_dir is not None and args.execute:
            sync_exec_cache(root / "_build" / "execute", exec_cache_dir)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
