#!/usr/bin/env python3
"""Cross-platform task runner for the TVB docs build.

Equivalent to the Makefile, for contributors who do not have `make`
(notably on Windows):

    python make.py check
    py -3 make.py serve

Run `python make.py` or `python make.py help` for the task list.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRY_RUN = False

TASKS = {
    "setup": "Create .venv and install pinned dependencies from uv.lock",
    "refs": "Validate BibTeX citations against Crossref API",
    "docs": "Build MyST HTML docs with execution and stage JupyterLite contents",
    "test": "Run unit tests and reference checks",
    "check": "Run the exact checks CI runs on PRs (refs + docs)",
    "lite-setup": "Create ~/.micromamba/envs/build-tvbl from build-environment.yml",
    "lite": "Build JupyterLite site into _build/html/lite and apply runtime patches",
    "all": "Build complete unified static site (_build/html with MyST docs and JupyterLite)",
    "serve": "Serve unified static site at http://localhost:8000, rebuilding docs on changes",
    "clean": "Remove build artifacts and temporary databases",
}

CLEAN_PATHS = (
    "_build/site",
    "_build/html",
    "_build/execute",
    "_build/lite_contents",
    ".jupyterlite.doit.db",
    "cockle_wasm_env",
)

THEME_SRC = "_build/html/lite/extensions/catppuccin_jupyterlab/themes/catppuccin_jupyterlab"
THEME_DST = "_build/html/lite/build/themes"

# Sources watched by `serve`; docs rebuild when one of these changes. Images are
# left out on purpose: `myst build --execute` writes its own figures back into
# content/, and watching them would trigger a pointless second rebuild.
WATCH_PATHS = ("content", "_static", "plugins", "_toc.yml", "myst.yml", "README.md")
WATCH_SUFFIXES = {".md", ".ipynb", ".py", ".yml", ".bib", ".js", ".mjs", ".css"}
WATCH_POLL_S = 1.0


def python_cmd() -> str:
    """Interpreter for the stdlib-only helper scripts."""
    if sys.platform == "win32":
        return sys.executable
    return shutil.which("python3") or sys.executable


def build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if sys.platform != "win32":
        env["PATH"] = os.pathsep.join(
            [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", env.get("PATH", "")]
        )
    if extra:
        env.update(extra)
    return env


def lite_env() -> str:
    if os.environ.get("LITE_ENV"):
        return os.environ["LITE_ENV"]
    return "environment.ci.yml" if (ROOT / "environment.ci.yml").is_file() else "environment.yml"


def jupyter_cmd() -> str:
    if os.environ.get("JUPYTER_CMD"):
        return os.environ["JUPYTER_CMD"]
    env_dir = Path.home() / ".micromamba" / "envs" / "build-tvbl"
    for rel in ("bin/jupyter", "Scripts/jupyter.exe", "Scripts/jupyter"):
        candidate = env_dir / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "jupyter"


def tvbl_test_dir() -> str:
    if os.environ.get("TVBL_TEST_DIR"):
        return os.environ["TVBL_TEST_DIR"]
    local = Path("/Users/duke/src/tvbl/content/tvbl")
    return str(local) if local.is_dir() else "content/_code"


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    if DRY_RUN:
        return
    subprocess.run(cmd, cwd=ROOT, env=env or build_env(), check=True)


def copy(src: str, dst: str) -> None:
    print(f"+ cp {src} {dst}", flush=True)
    if DRY_RUN:
        return
    target = ROOT / dst
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / src, target)


def copy_tree(src: str, dst: str) -> None:
    print(f"+ cp -r {src} {dst}", flush=True)
    if DRY_RUN:
        return
    source = ROOT / src
    target = ROOT / dst / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)


def task_help() -> None:
    cyan, reset = ("\033[36m", "\033[0m") if sys.stdout.isatty() else ("", "")
    print("TVB Docs & JupyterLite Build Commands:")
    print()
    for name, description in TASKS.items():
        print(f"  {cyan}{name:<14}{reset} {description}")
    print()


def task_setup() -> None:
    run(["uv", "venv", "--python", "3.12"])
    run(["uv", "pip", "sync", "requirements/uv.lock"])


def task_refs() -> None:
    run([python_cmd(), "tools/check_refs.py", "content/references.bib"])


def task_docs() -> None:
    run(["uv", "run", "myst", "build", "--execute", "--html"])
    run(["node", "tools/build_glossary.mjs"])
    run(["uv", "run", "python", "tools/stage_lite.py"])


def task_test() -> None:
    run(
        ["uv", "run", "--with", "pytest", "pytest", "-q", tvbl_test_dir()],
        env=build_env({"PYTHONPATH": "content/_code"}),
    )
    task_refs()


def task_check() -> None:
    task_refs()
    task_docs()


def task_lite_setup() -> None:
    target = Path.home() / ".micromamba" / "envs" / "build-tvbl"
    run(["micromamba", "create", "-y", "-p", str(target), "-f", "build-environment.yml"])


def task_lite() -> None:
    run(["uv", "run", "python", "tools/stage_lite.py"])
    run(
        [
            jupyter_cmd(),
            "lite",
            "build",
            "--contents",
            "_build/lite_contents",
            "--output-dir",
            "_build/html/lite",
            f"--XeusAddon.environment_file={lite_env()}",
        ]
    )
    if (ROOT / THEME_SRC).is_dir():
        copy_tree(THEME_SRC, THEME_DST)
    copy(".nojekyll", "_build/html/.nojekyll")
    run([python_cmd(), "tools/patch_lite_runtime.py", "_build/html/lite"])


def task_all() -> None:
    task_docs()
    task_lite()


def watch_state() -> dict[Path, int]:
    """Snapshot {path: mtime_ns} of the source files `serve` watches."""
    state: dict[Path, int] = {}
    for rel in WATCH_PATHS:
        root = ROOT / rel
        for file in root.rglob("*") if root.is_dir() else [root]:
            if file.suffix not in WATCH_SUFFIXES or not file.is_file():
                continue
            # Skips .ipynb_checkpoints and other editor droppings.
            if any(p.startswith(".") for p in file.relative_to(root).parts):
                continue
            state[file] = file.stat().st_mtime_ns
    return state


def task_serve() -> None:
    """Serve the built site, rebuilding the docs whenever a source changes."""
    if DRY_RUN:
        print("+ serve http://localhost:8000 (watching sources for docs rebuilds)")
        return
    if not any((ROOT / "_build/html").glob("*.html")):
        sys.exit("_build/html holds no pages yet - run `python make.py all` first")

    server = subprocess.Popen(
        [python_cmd(), "-m", "http.server", "8000", "--directory", "_build/html"],
        cwd=ROOT,
        env=build_env(),
    )
    # Without this, `kill <pid>` would skip the cleanup below and leave
    # http.server orphaned on port 8000. Ctrl+C is handled by main().
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    print("Serving http://localhost:8000 - watching sources (Ctrl+C to stop)", flush=True)
    try:
        state = watch_state()
        while server.poll() is None:
            time.sleep(WATCH_POLL_S)
            latest = watch_state()
            if latest == state:
                continue
            # No debounce needed: the rebuild blocks, so save bursts coalesce.
            state = latest
            print("+ source changed - rebuilding docs (reload the browser when done)", flush=True)
            try:
                task_docs()
            except subprocess.CalledProcessError as exc:
                print(f"! rebuild failed (exit {exc.returncode}); still watching", flush=True)
    finally:
        server.terminate()
        server.wait()
    print(f"! http.server exited (code {server.returncode})", flush=True)


def task_clean() -> None:
    for rel in CLEAN_PATHS:
        print(f"+ rm -rf {rel}", flush=True)
        if DRY_RUN:
            continue
        path = ROOT / rel
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()


def main(argv: list[str] | None = None) -> int:
    global DRY_RUN
    parser = argparse.ArgumentParser(
        prog="make.py",
        description="Cross-platform task runner for the TVB docs build.",
        add_help=False,
    )
    parser.add_argument("task", nargs="?", default="help", choices=[*TASKS, "help"])
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="print commands without running them"
    )
    parser.add_argument("-h", "--help", action="store_true", help="show this help message")
    args = parser.parse_args(argv)

    if args.help:
        task_help()
        return 0

    DRY_RUN = args.dry_run
    task = globals()[f"task_{args.task.replace('-', '_')}"]
    try:
        task()
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
