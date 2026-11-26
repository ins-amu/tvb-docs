#!/usr/bin/env python3
"""Build or reuse a persistent cached emscripten-wasm32 conda+pip prefix for JupyterLite.

Intended to be executed by the `build-tvbl` micromamba environment's Python
(which has `jupyterlite_xeus` and `pyyaml` installed).
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def compute_env_hash(env_file: Path, yaml_content: dict) -> str:
    h = hashlib.sha256()
    h.update(env_file.read_bytes())

    # If a local-channel is referenced in channels (e.g., CI wasm recipes), hash its packages by content
    # so restored caches across CI runners match reliably regardless of file mtimes.
    for channel in yaml_content.get("channels") or []:
        if isinstance(channel, str) and "local-channel" in channel:
            local_dir = Path(channel.removeprefix("file://"))
            if local_dir.is_dir():
                for item in sorted(local_dir.rglob("*")):
                    if item.is_file():
                        h.update(f"{item.relative_to(local_dir).as_posix()}:{_sha256_file(item)}\n".encode())
    return h.hexdigest()


def build_or_reuse_prefix(env_file: Path, cache_dir: Path, *, force: bool = False) -> Path:
    import yaml
    from jupyterlite_xeus.create_conda_env import create_conda_env_from_env_file

    yaml_content = yaml.safe_load(env_file.read_text(encoding="utf-8"))
    env_name = yaml_content["name"]
    prefix_dir = cache_dir / "envs" / env_name
    stamp_file = cache_dir / ".env-hash"
    env_hash = compute_env_hash(env_file, yaml_content)

    if (
        not force
        and stamp_file.is_file()
        and stamp_file.read_text(encoding="utf-8").strip() == env_hash
        and (prefix_dir / "conda-meta" / "history").is_file()
    ):
        print(f"Reusing cached xeus WASM prefix: {prefix_dir}", file=sys.stderr)
        return prefix_dir

    print(f"Building xeus WASM prefix in {prefix_dir} from {env_file}...", file=sys.stderr)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Redirect OS fd 1 -> 2 while building so subprocesses (rattler/pip)
    # stream to stderr and stdout emits only the resulting prefix path.
    sys.stdout.flush()
    saved_stdout_fd = os.dup(1)
    try:
        os.dup2(2, 1)
        create_conda_env_from_env_file(
            cache_dir,
            yaml_content,
            env_file.parent.resolve(),
        )
    finally:
        sys.stdout.flush()
        os.dup2(saved_stdout_fd, 1)
        os.close(saved_stdout_fd)

    if not (prefix_dir / "conda-meta" / "history").is_file():
        raise RuntimeError(f"Expected conda-meta/history missing in {prefix_dir}")

    stamp_file.write_text(env_hash + "\n", encoding="utf-8")
    return prefix_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or reuse cached xeus WASM prefix.")
    parser.add_argument("--env-file", type=Path, required=True, help="Path to environment.yml")
    parser.add_argument("--cache-dir", type=Path, default=Path("_build/xeus-prefix"),
                        help="Root prefix cache directory")
    parser.add_argument("--force", action="store_true", help="Force full prefix rebuild")
    args = parser.parse_args()

    prefix = build_or_reuse_prefix(args.env_file.resolve(), args.cache_dir.resolve(), force=args.force)
    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
