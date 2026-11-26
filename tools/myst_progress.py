#!/usr/bin/env python3
"""Terminal progress bar and spinner for MyST builds and watch-mode rebuilds.

Stdlib-only and Python 3.9+ compatible so it can be imported by both
``make.py`` (invoked with system python3) and ``tools/dev_server.py``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, TextIO

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

RE_BUILT_PAGE = re.compile(r"📖\s*Built\s+(.+?)\s+in\s+(.+?)\.\s*$")
RE_BUILT_TOTAL = re.compile(r"📚\s*Built\s+(\d+)\s+page(?:s|\(s\))?\s+for\s+(.+?)\s+in\s+(.+?)\.\s*$")
RE_EXECUTING = re.compile(r"💿\s*Executing notebook\s+\((.+?)\)")
RE_FULL_REBUILD = re.compile(r"💥\s*Triggered full (?:project load and )?site rebuild")
RE_UPDATING_DEPS = re.compile(r"🔄\s*Updating dependent pages for\s+(.+?)(?:\s+\[|$)")

_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_NOISE_PREFIXES = (
    "💾 Adding cached notebook outputs",
    "🪄",
    "Starting WebSocket:",
    "Exception opening new comm",
    "🪐 Jupyter server started",
)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _format_elapsed(seconds: float) -> str:
    secs = max(0, int(seconds))
    mins, rem = divmod(secs, 60)
    return f"{mins:02d}:{rem:02d}"


def _short_name(path_str: str) -> str:
    name = os.path.basename(path_str.rstrip("/"))
    return name or path_str


def estimate_page_count(root: Path, state_file: Path | None = None) -> int:
    """Return last recorded MyST page count or estimate from repository files."""
    sf = state_file or (root / "_build" / ".state.json")
    if sf.is_file():
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            count = data.get("myst_page_count")
            if isinstance(count, int) and count > 0:
                return count
        except (OSError, json.JSONDecodeError):
            pass

    total = 0
    content_dir = root / "content"
    skip_dirs = {"_templates", "_static", "_code"}
    if content_dir.is_dir():
        for dirpath, dirnames, filenames in os.walk(content_dir):
            dirnames[:] = [
                d for d in dirnames if not d.startswith(".") and d not in skip_dirs
            ]
            for fname in filenames:
                if fname.endswith((".md", ".ipynb")):
                    total += 1
    if (root / "README.md").is_file():
        total += 1
    return max(1, total)


def save_page_count(state_file: Path, count: int) -> None:
    """Atomically store ``myst_page_count`` in ``state_file``."""
    if count <= 0:
        return
    try:
        data: dict = {}
        if state_file.is_file():
            try:
                loaded = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        data["myst_page_count"] = int(count)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, state_file)
    except OSError:
        pass


class MystProgressTracker:
    """Parse ``myst`` output lines and render a live progress bar / spinner."""

    def __init__(
        self,
        total_pages: int,
        mode: str = "build",
        stream: TextIO | None = None,
        is_tty: bool | None = None,
        verbose: bool | None = None,
        on_build_complete: Callable[[int, str], None] | None = None,
        on_state_change: Callable[[dict], None] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._stream = stream if stream is not None else sys.stdout
        if is_tty is None:
            ci_env = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
            try:
                tty = bool(self._stream.isatty()) and not ci_env
            except Exception:
                tty = False
            self._is_tty = tty
        else:
            self._is_tty = is_tty
        if verbose is None:
            self._verbose = os.environ.get("MYST_VERBOSE", "").lower() in ("1", "true", "yes")
        else:
            self._verbose = verbose
        self._mode = mode
        self._on_build_complete = on_build_complete
        self._on_state_change = on_state_change

        self.phase = "initial"
        self.built_pages = 0
        self.total_pages = max(1, int(total_pages))
        self.executing: list[str] = []
        self.watch_target = ""
        self.last_built = ""
        self.started_at = time.monotonic()

        self._frame_idx = 0
        self._status_active = False
        self._skip_next_jupyter_url = False
        self._ticker_stop = threading.Event()
        self._ticker_thread: threading.Thread | None = None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "phase": self.phase,
                "built": self.built_pages,
                "total": self.total_pages,
                "executing": list(self.executing),
                "watch_target": self.watch_target,
                "last_built": self.last_built,
                "elapsed_s": max(0.0, time.monotonic() - self.started_at),
            }

    def _clear_status_locked(self) -> None:
        if self._is_tty and self._status_active:
            self._stream.write("\r\x1b[2K")
            self._stream.flush()
            self._status_active = False

    def _render_locked(self) -> None:
        if not self._is_tty or self.phase == "idle":
            return
        frame = _SPINNER_FRAMES[self._frame_idx % len(_SPINNER_FRAMES)]
        elapsed = _format_elapsed(time.monotonic() - self.started_at)

        if self.executing:
            detail = f"exec: {_short_name(self.executing[0])}"
            if len(self.executing) > 1:
                detail += f" (+{len(self.executing) - 1})"
        elif self.watch_target and self.phase == "watch_file":
            detail = _short_name(self.watch_target)
        elif self.last_built:
            detail = f"built: {_short_name(self.last_built)}"
        else:
            detail = "preparing..."

        if self.phase in ("initial", "full_rebuild"):
            total = max(1, self.total_pages)
            built = min(self.built_pages, total)
            pct = int(built * 100 / total)
            bar_w = 22
            filled = int(bar_w * built / total)
            bar = "█" * filled + "░" * (bar_w - filled)
            line = f"{frame} [{bar}] {self.built_pages}/{total} ({pct:3d}%) · {elapsed} · {detail}"
        else:
            line = f"{frame} Rebuilding {detail} · {elapsed}"

        try:
            cols = shutil.get_terminal_size((100, 24)).columns
        except Exception:
            cols = 100
        max_len = max(20, cols - 1)
        if len(line) > max_len:
            line = line[: max_len - 1] + "…"

        self._stream.write(f"\r\x1b[2K{line}")
        self._stream.flush()
        self._status_active = True

    def _print_locked(self, text: str) -> None:
        self._clear_status_locked()
        self._stream.write(text + "\n")
        self._stream.flush()
        if self._is_tty and self.phase != "idle":
            self._render_locked()

    def print_line(self, text: str) -> None:
        """Print a log line cleanly above any active progress bar."""
        with self._lock:
            self._print_locked(text)

    def _notify_state(self) -> None:
        if self._on_state_change is not None:
            self._on_state_change(self.snapshot())

    def _remove_executing_locked(self, built_path: str) -> None:
        if not self.executing:
            return
        if built_path in self.executing:
            self.executing.remove(built_path)
            return
        built_base = _short_name(built_path)
        for idx, item in enumerate(self.executing):
            if item.endswith(built_path) or built_path.endswith(item) or _short_name(item) == built_base:
                self.executing.pop(idx)
                return

    def _is_noise_line(self, clean: str) -> bool:
        if not clean:
            return True
        if self._skip_next_jupyter_url:
            self._skip_next_jupyter_url = False
            if clean.startswith("http://") and "token=" in clean:
                return True
        if clean.startswith("🪐 Jupyter server started"):
            self._skip_next_jupyter_url = True
            return True
        return any(clean.startswith(prefix) for prefix in _NOISE_PREFIXES)

    def feed_line(self, raw_line: str) -> None:
        """Process one stdout/stderr line from ``myst``."""
        raw_stripped = raw_line.rstrip("\r\n")
        clean = strip_ansi(raw_stripped).strip()

        complete_args: tuple[int, str] | None = None
        state_changed = False

        with self._lock:
            if self._verbose and raw_stripped:
                self._print_locked(raw_stripped)

            if RE_FULL_REBUILD.search(clean):
                self.phase = "full_rebuild"
                self.built_pages = 0
                self.executing.clear()
                self.watch_target = ""
                self.last_built = ""
                self.started_at = time.monotonic()
                state_changed = True
                if not self._verbose:
                    self._print_locked("↻ Full site rebuild triggered...")
                self._render_locked()

            elif m_exec := RE_EXECUTING.search(clean):
                nb_path = m_exec.group(1).strip()
                if nb_path not in self.executing:
                    self.executing.append(nb_path)
                if self.phase == "idle":
                    self.phase = "watch_file"
                    self.watch_target = nb_path
                    self.started_at = time.monotonic()
                state_changed = True
                if not self._is_tty and not self._verbose:
                    self._print_locked(f"💿 Executing notebook ({nb_path})")
                self._render_locked()

            elif m_deps := RE_UPDATING_DEPS.search(clean):
                dep_path = m_deps.group(1).strip()
                if self.phase == "idle":
                    self.phase = "watch_file"
                    self.watch_target = dep_path
                    self.started_at = time.monotonic()
                state_changed = True
                self._render_locked()

            elif m_built := RE_BUILT_PAGE.search(clean):
                built_path = m_built.group(1).strip()
                dur = m_built.group(2).strip()
                self._remove_executing_locked(built_path)
                self.last_built = built_path
                state_changed = True

                if self.phase in ("initial", "full_rebuild"):
                    self.built_pages += 1
                    if self.built_pages > self.total_pages:
                        self.total_pages = self.built_pages
                    if not self._is_tty and not self._verbose and self.built_pages % 50 == 0:
                        self._print_locked(
                            f"Built {self.built_pages}/{self.total_pages} pages "
                            f"({_format_elapsed(time.monotonic() - self.started_at)})"
                        )
                    self._render_locked()
                elif self.phase == "idle":
                    if not self._verbose:
                        self._print_locked(f"✓ Rebuilt {built_path} in {dur}.")
                    complete_args = (1, built_path)
                elif self.phase == "watch_file":
                    if not self.executing:
                        self.phase = "idle"
                        self.watch_target = ""
                        self._clear_status_locked()
                        if not self._verbose:
                            self._print_locked(f"✓ Rebuilt {built_path} in {dur}.")
                        complete_args = (1, built_path)
                    else:
                        self._render_locked()

            elif m_total := RE_BUILT_TOTAL.search(clean):
                count = int(m_total.group(1))
                dur = m_total.group(3).strip()
                self.total_pages = max(1, count)
                self.built_pages = count
                self.executing.clear()
                self.watch_target = ""
                self.phase = "idle"
                state_changed = True
                self._clear_status_locked()
                if not self._verbose:
                    self._print_locked(f"✓ Built {count} pages in {dur}.")
                complete_args = (count, "")

            elif not self._verbose and not self._is_noise_line(clean):
                self._print_locked(raw_stripped)

        if state_changed:
            self._notify_state()
        if complete_args is not None and self._on_build_complete is not None:
            self._on_build_complete(*complete_args)

    def start_ticker(self, interval_s: float = 0.2) -> None:
        if not self._is_tty or self._ticker_thread is not None:
            return
        self._ticker_stop.clear()

        def _tick() -> None:
            while not self._ticker_stop.wait(interval_s):
                with self._lock:
                    if self.phase != "idle":
                        self._frame_idx += 1
                        self._render_locked()

        self._ticker_thread = threading.Thread(target=_tick, name="myst-progress-ticker", daemon=True)
        self._ticker_thread.start()

    def stop_ticker(self) -> None:
        self._ticker_stop.set()
        if self._ticker_thread is not None:
            self._ticker_thread.join(timeout=1.0)
            self._ticker_thread = None

    def finish(self) -> None:
        self.stop_ticker()
        with self._lock:
            self._clear_status_locked()


def run_myst_with_progress(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    total_pages: int,
    state_file: Path | None = None,
) -> int:
    """Run ``myst build`` streaming output through ``MystProgressTracker``."""
    print("+ " + " ".join(cmd), flush=True)
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    prev_term = signal.getsignal(signal.SIGTERM)
    terminated = False

    def _forward_term(signum, frame):
        nonlocal terminated
        terminated = True
        if proc.returncode is None:
            try:
                proc.terminate()
            except OSError:
                pass

    signal.signal(signal.SIGTERM, _forward_term)

    def _on_complete(count: int, _path: str) -> None:
        if state_file is not None and count > 1:
            save_page_count(state_file, count)

    tracker = MystProgressTracker(
        total_pages=total_pages,
        mode="build",
        on_build_complete=_on_complete,
    )
    tracker.start_ticker()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            tracker.feed_line(line)
        rc = proc.wait()
    except KeyboardInterrupt:
        if proc.poll() is None:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        raise
    finally:
        tracker.finish()
        signal.signal(signal.SIGTERM, prev_term)

    if terminated:
        raise SystemExit(143)
    return rc
