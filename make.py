#!/usr/bin/env python3
"""Cross-platform, incremental task runner for the TVB docs & JupyterLite build.

Equivalent to the Makefile, for contributors who do not have `make`
(notably on Windows):

    python make.py        # do the obvious next action (setup + live dev server)
    python make.py check
    py -3 make.py serve

Run `python make.py help` for the full task list.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "_build" / ".state.json"
DEV_SERVER_FILE = ROOT / "_build" / ".dev-server.json"
VENV_LOCK_STAMP = ROOT / ".venv" / ".uv-lock-sha256"
NO_ENSURE_UV_SYNC_FILE = ROOT / ".no-ensure-uv-sync"

DRY_RUN = False
FORCE = False
NO_EXECUTE = False
NO_ENSURE_UV_SYNC = False
STATIC_SERVE = False
PORT = 8000

TASKS = {
    "dev": "Ensure setup and start live incremental dev server on http://localhost:8000 (default)",
    "apidoc": "Generate native MyST API reference pages for tvb",
    "docs": "Build MyST HTML docs with API reference, glossary check, and downloadable notebooks",
    "slides": "Build the tutorial presentation as HTML, PDF, and PowerPoint",
    "lite": "Incrementally build JupyterLite into _build/lite (and sync to _build/html/lite)",
    "all": "Build complete unified static site (_build/html with MyST docs and JupyterLite)",
    "serve": "Serve unified site at http://localhost:8000 (live reload, or --static for _build/html)",
    "check": "Run the exact checks CI runs on PRs (refs + docs)",
    "refs": "Validate BibTeX citations against Crossref API",
    "test": "Run unit tests and reference checks",
    "setup": "Create .venv and install pinned dependencies from uv.lock",
    "lite-setup": "Create ~/.micromamba/envs/build-tvbl from build-environment.yml",
    "status": "Show build freshness, active dev server, and what would run next",
    "clean": "Remove generated HTML/site artifacts while preserving expensive caches",
    "clean-all": "Remove all build artifacts, caches, and WASM environments",
    "help": "Show this help message",
}

CLEAN_PATHS = (
    "_build/site",
    "_build/html",
    "_build/apidoc",
    "_build/lite_contents",
    "_build/notebooks",
    "_build/.state.json",
    ".myst.apidoc.yml",
    ".jupyterlite.doit.db",
)

CLEAN_ALL_PATHS = (
    "_build",
    ".jupyterlite.doit.db",
    "cockle_wasm_env",
    ".cockle_temp",
)

LITE_DIR = "_build/lite"
LITE_THEME_SRC = f"{LITE_DIR}/extensions/catppuccin_jupyterlab/themes/catppuccin_jupyterlab"
LITE_THEME_DST = f"{LITE_DIR}/build/themes"


def is_ci() -> bool:
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def python_cmd() -> str:
    """Interpreter for stdlib-only helper scripts."""
    if sys.platform == "win32":
        return sys.executable
    return shutil.which("python3") or sys.executable


def venv_python() -> str:
    """Return the project's .venv Python if present, else fall back to python_cmd()."""
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe", ".venv/Scripts/python"):
        candidate = ROOT / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return python_cmd()


def venv_bin(name: str) -> list[str]:
    """Return direct .venv binary command if present, else `uv run <name>`."""
    for rel in (f".venv/bin/{name}", f".venv/Scripts/{name}.exe", f".venv/Scripts/{name}"):
        candidate = ROOT / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate)]
    return ["uv", "run", name]


def build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    path_prefix: list[str] = []
    if (ROOT / ".venv").is_dir():
        env["VIRTUAL_ENV"] = str(ROOT / ".venv")
    for rel in (".venv/bin", ".venv/Scripts"):
        venv_dir = ROOT / rel
        if venv_dir.is_dir():
            path_prefix.append(str(venv_dir))
    if sys.platform != "win32":
        path_prefix.extend([str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin"])
    if path_prefix:
        env["PATH"] = os.pathsep.join([*path_prefix, env.get("PATH", "")])
    if is_ci():
        for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
            env.setdefault(var, "1")
    if extra:
        env.update(extra)
    return env


def lite_env() -> str:
    if os.environ.get("LITE_ENV"):
        return os.environ["LITE_ENV"]
    return "environment.ci.yml" if (ROOT / "environment.ci.yml").is_file() else "environment.yml"


def _micromamba_env_dir() -> Path:
    return Path.home() / ".micromamba" / "envs" / "build-tvbl"


def jupyter_cmd() -> str:
    if os.environ.get("JUPYTER_CMD"):
        return os.environ["JUPYTER_CMD"]
    env_dir = _micromamba_env_dir()
    for rel in ("bin/jupyter", "Scripts/jupyter.exe", "Scripts/jupyter"):
        candidate = env_dir / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "jupyter"


def lite_python() -> str:
    jcmd = jupyter_cmd()
    jresolved = jcmd if jcmd != "jupyter" else shutil.which("jupyter")
    if jresolved:
        jpath = Path(jresolved)
        for name in ("python", "python3", "python.exe"):
            candidate = jpath.parent / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    env_dir = _micromamba_env_dir()
    for rel in ("bin/python", "Scripts/python.exe", "python.exe"):
        candidate = env_dir / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return python_cmd()


def tvbl_test_dir() -> str:
    if os.environ.get("TVBL_TEST_DIR"):
        return os.environ["TVBL_TEST_DIR"]
    local = Path("/Users/duke/src/tvbl/content/tvbl")
    return str(local) if local.is_dir() else "content/_code"


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    if DRY_RUN:
        return
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env or build_env())
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
    try:
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
        signal.signal(signal.SIGTERM, prev_term)
    if terminated:
        raise SystemExit(143)
    if rc:
        raise subprocess.CalledProcessError(rc, cmd)


def run_capture(cmd: list[str], env: dict[str, str] | None = None) -> str:
    print("+ " + " ".join(cmd), flush=True)
    if DRY_RUN:
        return ""
    res = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env or build_env(),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return res.stdout.strip()


def copy(src: str, dst: str) -> None:
    print(f"+ cp {src} {dst}", flush=True)
    if DRY_RUN:
        return
    source = ROOT / src
    target = ROOT / dst
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_file() and not target.is_symlink():
            s_st, t_st = source.stat(), target.stat()
            if s_st.st_size == t_st.st_size and s_st.st_mtime_ns == t_st.st_mtime_ns:
                return
        target.unlink()
    shutil.copy2(source, target)


def copy_tree(src: str, dst: str) -> None:
    print(f"+ cp -r {src} {dst}", flush=True)
    if DRY_RUN:
        return
    source = ROOT / src
    target = ROOT / dst / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)


def sync_tree(src_rel: str, dst_rel: str) -> None:
    """Incrementally mirror src_rel -> dst_rel using hardlinks (copy2 fallback)."""
    src = ROOT / src_rel
    dst = ROOT / dst_rel
    if DRY_RUN:
        print(f"+ sync {src_rel} -> {dst_rel}", flush=True)
        return
    if not src.exists():
        return

    dst.mkdir(parents=True, exist_ok=True)
    expected: set[Path] = set()
    updated = 0

    for item in sorted(src.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        expected.add(target.resolve())

        if target.exists() and not target.is_symlink():
            try:
                if os.path.samefile(item, target):
                    continue
            except OSError:
                pass
            s_st, t_st = item.stat(), target.stat()
            if s_st.st_size == t_st.st_size and s_st.st_mtime_ns == t_st.st_mtime_ns:
                continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        try:
            os.link(item, target)
        except OSError:
            shutil.copy2(item, target)
        updated += 1

    pruned = 0
    for existing in sorted(dst.rglob("*"), reverse=True):
        if existing.is_file() or existing.is_symlink():
            if existing.resolve() not in expected:
                existing.unlink()
                pruned += 1
        elif existing.is_dir():
            try:
                if not any(existing.iterdir()):
                    existing.rmdir()
            except OSError:
                pass

    if updated or pruned:
        print(f"+ sync {src_rel} -> {dst_rel} (updated={updated}, pruned={pruned})", flush=True)


# ---------------------------------------------------------------------------
# Incremental state & fingerprinting
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(updates: dict) -> None:
    if DRY_RUN:
        return
    state = load_state()
    state.update(updates)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while chunk := fp.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(
    paths: list[str],
    *,
    exclude_content_generated: bool = False,
    exclude_content_dirs: tuple[str, ...] = (),
    extra_tokens: list[str] | None = None,
    content_hash: bool | None = None,
) -> str:
    use_content_hash = is_ci() if content_hash is None else content_hash
    h = hashlib.sha256()
    if extra_tokens:
        for tok in extra_tokens:
            h.update(f"tok:{tok}\n".encode("utf-8"))

    files: list[Path] = []
    for rel in paths:
        p = ROOT / rel
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            for child in p.rglob("*"):
                if child.is_file():
                    files.append(child)

    for f in sorted(set(files)):
        rel_posix = f.relative_to(ROOT).as_posix()
        parts = rel_posix.split("/")
        if any(part.startswith(".") or part == "__pycache__" for part in parts):
            continue
        if parts[0] == "content" and len(parts) > 1:
            if parts[1] in exclude_content_dirs:
                continue
            if exclude_content_generated:
                if rel_posix.startswith("content/demos/") and (
                    f.suffix == ".png" or "_widget_assets" in parts
                ):
                    continue
                if rel_posix.startswith("content/reference/api/") and rel_posix != "content/reference/api/index.md":
                    continue
        try:
            if use_content_hash:
                h.update(f"{rel_posix}:{_sha256_file(f)}\n".encode("utf-8"))
            else:
                st = f.stat()
                h.update(f"{rel_posix}:{st.st_size}:{st.st_mtime_ns}\n".encode("utf-8"))
        except OSError:
            pass
    return h.hexdigest()


def fp_refs() -> str:
    return _hash_tree(["content/references.bib", "content/.refs-cache.json", "tools/check_refs.py"])


def fp_apidoc() -> str:
    return _hash_tree(
        [
            "tools/apidoc",
            "content",
            "myst.yml",
            "_toc.yml",
            "requirements/uv.lock",
            "requirements/base.txt",
        ],
        exclude_content_generated=True,
    )


def fp_docs() -> str:
    return _hash_tree(
        [
            "content",
            "_static",
            "plugins",
            "_toc.yml",
            "myst.yml",
            "README.md",
            "tools/build_glossary.mjs",
            "tools/build_site_search.mjs",
            "tools/stage_lite.py",
        ],
        exclude_content_generated=True,
        extra_tokens=[
            f"BASE_URL={os.environ.get('BASE_URL', '')}",
            f"apidoc={fp_apidoc()}",
        ],
    )


def fp_lite_env() -> str:
    paths = [
        lite_env(),
        "build-environment.yml",
        "jupyter_lite_config.json",
        "jupyter-lite.json",
        "overrides.json",
        "cockle-config.json",
        "extensions",
        "tools/build_xeus_prefix.py",
    ]
    if (ROOT / "local-channel").is_dir():
        paths.append("local-channel")
    return _hash_tree(paths)


def fp_lite_tvbl() -> str:
    return _hash_tree(
        [
            "content/_code/tvbl",
            "content/_code/tvbl_docs.py",
            "tools/patch_lite_runtime.py",
        ]
    )


def fp_lite_contents_non_tvbl() -> str:
    return _hash_tree(
        ["content", "README.md", "tools/stage_lite.py"],
        exclude_content_generated=True,
        exclude_content_dirs=("_code", "_static", "_templates"),
    )


def fp_lite_contents() -> str:
    h = hashlib.sha256()
    h.update(fp_lite_contents_non_tvbl().encode("utf-8"))
    h.update(fp_lite_tvbl().encode("utf-8"))
    return h.hexdigest()


def venv_ready() -> bool:
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe", ".venv/Scripts/python"):
        candidate = ROOT / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return True
    return False


def lite_env_ready() -> bool:
    if os.environ.get("JUPYTER_CMD"):
        return True
    env_dir = _micromamba_env_dir()
    for rel in ("bin/jupyter", "Scripts/jupyter.exe", "Scripts/jupyter"):
        candidate = env_dir / rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return True
    return shutil.which("jupyter") is not None


def _uv_lock_sha256() -> str:
    lock_file = ROOT / "requirements" / "uv.lock"
    if not lock_file.is_file():
        return ""
    return hashlib.sha256(lock_file.read_bytes()).hexdigest()


def venv_in_sync() -> bool:
    """Return True if .venv exists and matches requirements/uv.lock."""
    if not venv_ready():
        return False
    lock_hash = _uv_lock_sha256()
    stamp_matches = (
        bool(lock_hash)
        and VENV_LOCK_STAMP.is_file()
        and VENV_LOCK_STAMP.read_text(encoding="utf-8").strip() == lock_hash
    )
    if is_ci() and stamp_matches:
        return True
    res = subprocess.run(
        ["uv", "pip", "sync", "--offline", "--dry-run", "requirements/uv.lock"],
        cwd=ROOT,
        env=build_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    out = res.stderr + res.stdout
    if res.returncode == 0 and "Would make no changes" in out:
        return True
    if res.returncode != 0 and stamp_matches and "offline" in out.lower():
        return True
    return False


def skip_uv_sync() -> bool:
    return NO_ENSURE_UV_SYNC or NO_ENSURE_UV_SYNC_FILE.exists()


def ensure_venv() -> None:
    if skip_uv_sync():
        if not venv_ready() and not DRY_RUN:
            raise RuntimeError(
                ".venv not found and uv sync is disabled (--no-ensure-uv-sync / .no-ensure-uv-sync). "
                "Run `python make.py setup` once to create .venv."
            )
        return
    if venv_in_sync():
        return
    task_setup()


def ensure_lite_env() -> None:
    if lite_env_ready():
        return
    if shutil.which("micromamba") is None and not DRY_RUN:
        raise RuntimeError(
            "JupyterLite build env not found (~/.micromamba/envs/build-tvbl) and "
            "`micromamba` is not on PATH. Install micromamba or set JUPYTER_CMD."
        )
    task_lite_setup()


def dev_server_info() -> dict | None:
    if not DEV_SERVER_FILE.is_file():
        return None
    try:
        info = json.loads(DEV_SERVER_FILE.read_text(encoding="utf-8"))
        pid = int(info["pid"])
        os.kill(pid, 0)
        return info
    except Exception:
        return None


def port_in_use(port: int) -> bool:
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.3)
                if sock.connect_ex((addr, port)) == 0:
                    return True
        except OSError:
            pass
    return False


def find_free_port(start: int = 8000, max_tries: int = 100) -> int:
    """Return `start` if available, otherwise the first free port after it."""
    for port in range(start, start + max_tries):
        if port_in_use(port):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}..{start + max_tries - 1}")


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def task_help() -> None:
    cyan, reset = ("\033[36m", "\033[0m") if sys.stdout.isatty() else ("", "")
    print("TVB Docs & JupyterLite Build Commands:")
    print()
    for name, description in TASKS.items():
        print(f"  {cyan}{name:<14}{reset} {description}")
    print()
    print("Options: -n/--dry-run, -f/--force, --no-execute, --no-ensure-uv-sync, --static, --port PORT")


def task_setup() -> None:
    if not venv_ready() or FORCE:
        cmd = ["uv", "venv", "--python", "3.12"]
        if venv_ready():
            cmd.append("--clear")
        run(cmd)
    run(["uv", "pip", "sync", "requirements/uv.lock"])
    if (ROOT / "trajecturtle" / "pyproject.toml").is_file():
        run(["uv", "pip", "install", "--no-deps", "-e", "./trajecturtle"])
    if not DRY_RUN and (ROOT / ".venv").is_dir():
        VENV_LOCK_STAMP.write_text(_uv_lock_sha256() + "\n", encoding="utf-8")


def _apidoc_outputs_ready() -> bool:
    return (
        (ROOT / ".myst.apidoc.yml").is_file()
        and (ROOT / "_build" / "apidoc" / "api-symbols.json").is_file()
        and (ROOT / "content" / "reference" / "api" / "api-xref-map.json").is_file()
    )


def task_apidoc() -> None:
    ensure_venv()
    state = load_state()
    cur = fp_apidoc()
    if not FORCE and not is_ci() and _apidoc_outputs_ready() and state.get("apidoc") == cur:
        print("apidoc up to date.", flush=True)
        return
    run([venv_python(), "-m", "tools.apidoc", *(["--no-cache"] if FORCE else [])])
    save_state({"apidoc": fp_apidoc()})


def task_refs() -> None:
    state = load_state()
    cur = fp_refs()
    if not FORCE and not is_ci() and state.get("refs") == cur:
        print("refs up to date (content/references.bib unchanged).", flush=True)
        return
    run([python_cmd(), "tools/check_refs.py", "content/references.bib"])
    save_state({"refs": fp_refs()})


def task_slides() -> None:
    output = ROOT / "_build" / "slides"
    if not DRY_RUN:
        output.mkdir(parents=True, exist_ok=True)
    common = ["pandoc", "slides/tvb-tutorial.md", "--standalone", "--slide-level=1"]
    run([*common, "-t", "revealjs", "-V",
         "revealjs-url=https://cdn.jsdelivr.net/npm/reveal.js@4.6.1",
         "-o", str(output / "tvb-tutorial.html")])
    run([*common, "-t", "pptx", "-o", str(output / "tvb-tutorial.pptx")])
    run([*common, "-t", "beamer", "-o", str(output / "tvb-tutorial.pdf")])


def task_docs() -> None:
    ensure_venv()
    task_apidoc()
    execute = not NO_EXECUTE
    state = load_state()
    cur_docs = fp_docs()
    html_index = ROOT / "_build" / "html" / "index.html"

    if (
        not FORCE
        and not is_ci()
        and html_index.is_file()
        and (ROOT / "_build" / "html" / "site-search-manifest.json").is_file()
        and state.get("docs") == cur_docs
        and state.get("docs_execute") == execute
    ):
        print("docs up to date.", flush=True)
        if (ROOT / LITE_DIR).is_dir():
            sync_tree(LITE_DIR, "_build/html/lite")
            copy(".nojekyll", "_build/html/.nojekyll")
        return

    myst_cmd = [*venv_bin("myst"), "build", "--config", ".myst.apidoc.yml"]
    if execute:
        myst_cmd.append("--execute")
        if is_ci():
            myst_cmd.extend(["--execute-parallel", "2"])
    myst_cmd.append("--html")

    run(myst_cmd)
    run(["node", "tools/build_glossary.mjs"])
    run(["node", "tools/build_site_search.mjs"])
    run(
        [
            venv_python(),
            "-c",
            "from tvb_card_widgets import export_static_assets; export_static_assets('_build/html/trajecturtle')",
        ],
        env=build_env({"PYTHONPATH": "content/_code"}),
    )
    run(["node", "tools/stage_phaseplane.mjs"])
    run(
        [
            venv_python(),
            "tools/stage_lite.py",
            "--notebooks-only",
            "--notebooks-dir",
            "_build/notebooks",
            *(["--force"] if FORCE else []),
        ]
    )
    sync_tree("_build/notebooks", "_build/html/notebooks")
    if (ROOT / LITE_DIR).is_dir():
        sync_tree(LITE_DIR, "_build/html/lite")
        copy(".nojekyll", "_build/html/.nojekyll")
    save_state({"docs": fp_docs(), "docs_execute": execute})


def task_test() -> None:
    ensure_venv()
    run(["node", "--test", "tests/test_site_search.mjs"])
    run(
        ["uv", "run", "--with", "pytest", "pytest", "-q", "tests", tvbl_test_dir()],
        env=build_env({"PYTHONPATH": f".{os.pathsep}content/_code"}),
    )
    task_refs()


def task_check() -> None:
    task_refs()
    task_docs()


def task_lite_setup() -> None:
    target = _micromamba_env_dir()
    run(["micromamba", "create", "-y", "-p", str(target), "-f", "build-environment.yml"])


def _run_full_lite_build() -> None:
    prefix_out = run_capture(
        [
            lite_python(),
            "tools/build_xeus_prefix.py",
            "--env-file",
            lite_env(),
            "--cache-dir",
            "_build/xeus-prefix",
            *(["--force"] if FORCE else []),
        ]
    )
    prefix_arg = (prefix_out.splitlines()[-1].strip() if prefix_out else "") or "_build/xeus-prefix/envs/xeus-kernel"
    run(
        [
            jupyter_cmd(),
            "lite",
            "build",
            "--contents",
            "_build/lite_contents",
            "--output-dir",
            LITE_DIR,
            f"--XeusAddon.prefix={prefix_arg}",
        ]
    )
    if (ROOT / LITE_THEME_SRC).is_dir():
        copy_tree(LITE_THEME_SRC, LITE_THEME_DST)
    run([python_cmd(), "tools/patch_lite_runtime.py", LITE_DIR])


def _lite_has_xeus_config() -> bool:
    jl_json = ROOT / LITE_DIR / "jupyter-lite.json"
    if not jl_json.is_file():
        return False
    try:
        text = jl_json.read_text(encoding="utf-8")
        return "xeus" in text
    except OSError:
        return False


def _python_has_module(py: str, module: str) -> bool:
    if DRY_RUN:
        return True
    res = subprocess.run([py, "-c", f"import {module}"], capture_output=True, check=False)
    return res.returncode == 0


def _stage_lite_python() -> str:
    if venv_ready():
        if not skip_uv_sync():
            ensure_venv()
        return venv_python()
    lite_py = lite_python()
    if _python_has_module(lite_py, "jupytext"):
        return lite_py
    ensure_venv()
    return venv_python()


def task_lite() -> None:
    ensure_lite_env()

    state = load_state()
    cur_env = fp_lite_env()
    cur_tvbl = fp_lite_tvbl()
    cur_non_tvbl = fp_lite_contents_non_tvbl()
    cur_contents = fp_lite_contents()

    lite_root = ROOT / LITE_DIR
    xeus_ready = (lite_root / "xeus" / "kernels.json").is_file()
    doit_ready = (ROOT / ".jupyterlite.doit.db").is_file()

    if (
        not FORCE
        and xeus_ready
        and _lite_has_xeus_config()
        and state.get("lite_env") == cur_env
        and state.get("lite_tvbl") == cur_tvbl
        and state.get("lite_contents") == cur_contents
    ):
        print("JupyterLite up to date.", flush=True)
        copy(".nojekyll", "_build/html/.nojekyll")
        sync_tree(LITE_DIR, "_build/html/lite")
        return

    run(
        [
            _stage_lite_python(),
            "tools/stage_lite.py",
            "--output",
            "_build/lite_contents",
            "--notebooks-dir",
            "_build/notebooks",
            *(["--force"] if FORCE else []),
        ]
    )

    if (
        not FORCE
        and xeus_ready
        and _lite_has_xeus_config()
        and state.get("lite_env") == cur_env
        and state.get("lite_contents_non_tvbl") == cur_non_tvbl
    ):
        print("JupyterLite fast path: only tvbl code changed (re-patching runtime).", flush=True)
        sync_tree("_build/lite_contents/tvbl", f"{LITE_DIR}/files/tvbl")
        copy("_build/lite_contents/tvbl_docs.py", f"{LITE_DIR}/files/tvbl_docs.py")
        run([python_cmd(), "tools/patch_lite_runtime.py", LITE_DIR])
    elif (
        not FORCE
        and xeus_ready
        and doit_ready
        and _lite_has_xeus_config()
        and state.get("lite_env") == cur_env
    ):
        print("JupyterLite incremental path: contents changed (skipping Xeus/Terminal addons).", flush=True)
        run(
            [
                jupyter_cmd(),
                "lite",
                "build",
                "--disable-addons=jupyterlite-xeus",
                "--disable-addons=jupyterlite-terminal",
                "--contents",
                "_build/lite_contents",
                "--output-dir",
                LITE_DIR,
            ]
        )
        if not DRY_RUN and not _lite_has_xeus_config():
            print("Warning: incremental Lite build dropped xeus config; running full Lite build.", flush=True)
            _run_full_lite_build()
        else:
            if (ROOT / LITE_THEME_SRC).is_dir():
                copy_tree(LITE_THEME_SRC, LITE_THEME_DST)
            if state.get("lite_tvbl") != cur_tvbl or is_ci():
                run([python_cmd(), "tools/patch_lite_runtime.py", LITE_DIR])
    else:
        _run_full_lite_build()

    copy(".nojekyll", "_build/html/.nojekyll")
    sync_tree(LITE_DIR, "_build/html/lite")
    save_state(
        {
            "lite_env": cur_env,
            "lite_tvbl": cur_tvbl,
            "lite_contents_non_tvbl": cur_non_tvbl,
            "lite_contents": cur_contents,
        }
    )


def task_all() -> None:
    task_docs()
    task_lite()


def task_dev() -> None:
    ensure_venv()
    info = dev_server_info()
    if info is not None:
        print(
            f"TVB dev server is already running (PID {info['pid']}) at {info['url']}.",
            flush=True,
        )
        run(
            [
                venv_python(),
                "tools/stage_lite.py",
                "--notebooks-only",
                "--notebooks-dir",
                "_build/notebooks",
            ]
        )
        return

    port = find_free_port(PORT)
    if port != PORT:
        print(f"Port {PORT} is in use; starting dev server at http://localhost:{port}.", flush=True)

    task_apidoc()
    run(
        [
            venv_python(),
            "tools/stage_lite.py",
            "--notebooks-only",
            "--notebooks-dir",
            "_build/notebooks",
            *(["--force"] if FORCE else []),
        ]
    )
    myst_cmd = venv_bin("myst")
    if len(myst_cmd) != 1:
        raise RuntimeError("myst binary not found in .venv; run `python make.py setup` first.")

    cmd = [
        venv_python(),
        "tools/dev_server.py",
        "--port",
        str(port),
        "--myst-bin",
        myst_cmd[0],
        "--python",
        venv_python(),
        "--config",
        ".myst.apidoc.yml",
        "--lite-dir",
        LITE_DIR,
        "--notebooks-dir",
        "_build/notebooks",
        "--execute" if not NO_EXECUTE else "--no-execute",
    ]
    run(cmd)


def task_serve() -> None:
    """Serve the unified site (live reload by default, or static _build/html with --static)."""
    if STATIC_SERVE:
        task_docs()
        port = find_free_port(PORT)
        if port != PORT:
            print(f"Port {PORT} is in use; serving _build/html at http://localhost:{port}.", flush=True)
        else:
            print(f"+ serving _build/html at http://localhost:{port}", flush=True)
        run([python_cmd(), "-m", "http.server", str(port), "--directory", "_build/html"])
        return
    task_dev()


def task_status() -> None:
    state = load_state()
    skip_sync = skip_uv_sync()
    v_ready = venv_ready()
    v_ok = v_ready if skip_sync else venv_in_sync()
    a_ok = _apidoc_outputs_ready() and state.get("apidoc") == fp_apidoc()
    r_ok = state.get("refs") == fp_refs()
    d_ok = (ROOT / "_build" / "html" / "index.html").is_file() and state.get("docs") == fp_docs()
    l_ok = (
        (ROOT / LITE_DIR / "xeus" / "kernels.json").is_file()
        and state.get("lite_env") == fp_lite_env()
        and state.get("lite_contents") == fp_lite_contents()
    )
    l_env_ok = lite_env_ready()
    srv = dev_server_info()

    def fmt(ok: bool, yes: str = "up-to-date", no: str = "stale/missing") -> str:
        return yes if ok else no

    if skip_sync and v_ready:
        v_label = "ready (uv sync skipped)"
    elif v_ok:
        v_label = "ready"
    elif v_ready:
        v_label = "out of date (needs uv pip sync)"
    else:
        v_label = "needs setup"
    print("TVB Docs Build Status:")
    print(f"  venv (.venv):      {v_label}")
    print(f"  apidoc:            {fmt(a_ok)}")
    print(f"  refs:              {fmt(r_ok)}")
    print(f"  docs (_build/html):{fmt(d_ok)}")
    print(f"  lite-setup:        {fmt(l_env_ok, 'ready', 'missing (~/.micromamba/envs/build-tvbl)')}")
    print(f"  lite (_build/lite):{fmt(l_ok)}")
    if srv:
        print(f"  dev server:        running at {srv['url']} (PID {srv['pid']})")
    elif port_in_use(PORT):
        next_port = find_free_port(PORT)
        print(f"  dev server:        port {PORT} occupied (will use http://localhost:{next_port})")
    else:
        print("  dev server:        stopped")

    sync_prefix = "" if v_ok else ("sync .venv + " if v_ready else "setup + ")
    next_hint = "report running server" if srv else f"{sync_prefix}start live dev server"
    print(f"  default `make`:    will {next_hint}")


def _remove_paths(paths: tuple[str, ...]) -> None:
    for rel in paths:
        print(f"+ rm -rf {rel}", flush=True)
        if DRY_RUN:
            continue
        path = ROOT / rel
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    api_dir = ROOT / "content" / "reference" / "api"
    if api_dir.is_dir():
        for item in api_dir.iterdir():
            if item.name != "index.md":
                print(f"+ rm -f content/reference/api/{item.name}", flush=True)
                if not DRY_RUN:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()


def task_clean() -> None:
    _remove_paths(CLEAN_PATHS)


def task_clean_all() -> None:
    _remove_paths(CLEAN_ALL_PATHS)


def main(argv: list[str] | None = None) -> int:
    global DRY_RUN, FORCE, NO_EXECUTE, NO_ENSURE_UV_SYNC, STATIC_SERVE, PORT
    parser = argparse.ArgumentParser(
        prog="make.py",
        description="Cross-platform, incremental task runner for the TVB docs build.",
        add_help=False,
    )
    parser.add_argument("task", nargs="?", default="dev", choices=list(TASKS))
    parser.add_argument("-n", "--dry-run", action="store_true", help="print commands without running them")
    parser.add_argument("-f", "--force", action="store_true", help="ignore freshness checks and rebuild")
    parser.add_argument("--no-execute", action="store_true", help="skip notebook/cell execution")
    parser.add_argument(
        "--no-ensure-uv-sync",
        action="store_true",
        help="skip automatic uv sync checks when .venv exists (or create ./.no-ensure-uv-sync)",
    )
    parser.add_argument("--static", action="store_true", help="serve static _build/html instead of live myst start")
    parser.add_argument("--port", type=int, default=8000, help="port for dev/serve HTTP server (default: 8000)")
    parser.add_argument("-h", "--help", action="store_true", help="show this help message")
    args = parser.parse_args(argv)

    if args.help:
        task_help()
        return 0

    DRY_RUN = args.dry_run
    FORCE = args.force
    NO_EXECUTE = args.no_execute
    NO_ENSURE_UV_SYNC = args.no_ensure_uv_sync
    STATIC_SERVE = args.static
    PORT = args.port

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
