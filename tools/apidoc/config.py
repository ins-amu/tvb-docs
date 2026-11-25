"""Configuration, path discovery, git-source mapping, and collision-safe anchors."""

from __future__ import annotations

import hashlib
import json
import re
import sysconfig
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_SEGMENTS = frozenset({"tests", "equation_tests"})

# Kind prefixes keep module/class/function/method/trait/attribute anchors disjoint.
KIND_PREFIX = {
    "module": "mod",
    "class": "cls",
    "function": "fn",
    "method": "meth",
    "trait": "trait",
    "attribute": "attr",
}


@dataclass(frozen=True)
class GitSourceInfo:
    """Remote repository coordinates used to emit pinned `[View on Git]` URLs."""

    repo_url: str
    commit: str
    subdirectory: str = ""

    def blob_url(self, rel_path: str, lineno: int | None = None, endlineno: int | None = None) -> str:
        """Build a GitHub blob URL with optional `#L<start>-L<end>` anchor."""
        sub = f"{self.subdirectory.strip('/')}/" if self.subdirectory else ""
        base = f"{self.repo_url.rstrip('/')}/blob/{self.commit}/{sub}{rel_path.lstrip('/')}"
        if lineno is not None:
            if endlineno is not None and endlineno > lineno:
                return f"{base}#L{lineno}-L{endlineno}"
            return f"{base}#L{lineno}"
        return base


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root containing `myst.yml`."""
    cur = (start or Path(__file__)).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "myst.yml").is_file():
            return parent
    return Path.cwd().resolve()


def find_tvb_search_path(repo_root: Path) -> Path:
    """Locate the directory containing the installed `tvb` package."""
    candidates = [
        repo_root / ".venv" / "lib" / "python3.12" / "site-packages",
        Path(sysconfig.get_path("purelib")),
        Path(sysconfig.get_path("platlib")),
    ]
    for candidate in candidates:
        if (candidate / "tvb" / "__init__.py").is_file():
            return candidate
    # Fallback: search any python3.* under .venv/lib
    venv_lib = repo_root / ".venv" / "lib"
    if venv_lib.is_dir():
        for py_dir in sorted(venv_lib.glob("python*")):
            sp = py_dir / "site-packages"
            if (sp / "tvb" / "__init__.py").is_file():
                return sp
    raise FileNotFoundError("Could not locate installed 'tvb' package in .venv or active Python.")


def load_tvb_git_info(search_path: Path, repo_root: Path) -> GitSourceInfo | None:
    """Read upstream tvb-root commit metadata from dist-info `direct_url.json` or `requirements/base.txt`."""
    for dist_info in sorted(search_path.glob("tvb_library-*.dist-info")):
        direct_url = dist_info / "direct_url.json"
        if direct_url.is_file():
            data = json.loads(direct_url.read_text(encoding="utf-8"))
            url = data.get("url", "").removesuffix(".git")
            commit = data.get("vcs_info", {}).get("commit_id", "")
            subdir = data.get("subdirectory", "")
            if url and commit:
                return GitSourceInfo(repo_url=url, commit=commit, subdirectory=subdir)

    req = repo_root / "requirements" / "base.txt"
    if req.is_file():
        m = re.search(
            r"tvb-library\s*@\s*git\+(https://[^\s@]+)@([0-9a-f]+)(?:#subdirectory=([^\s]+))?",
            req.read_text(encoding="utf-8"),
        )
        if m:
            return GitSourceInfo(
                repo_url=m.group(1).removesuffix(".git"),
                commit=m.group(2),
                subdirectory=m.group(3) or "",
            )
    return None


def is_excluded_module(dotted_path: str) -> bool:
    """Return True for test packages and private/internal modules (e.g. `_numba`)."""
    parts = dotted_path.split(".")
    for part in parts[1:]:
        if part in EXCLUDED_SEGMENTS:
            return True
        if part.startswith("_") and part != "__init__":
            return True
    return False


class AnchorRegistry:
    """Allocate deterministic, MyST-lowercase-collision-free anchor IDs."""

    def __init__(self) -> None:
        self._lower_to_qualname: dict[str, str] = {}
        self._qualname_to_anchor: dict[tuple[str, str], str] = {}

    def anchor_for(self, kind: str, qualname: str) -> str:
        """Return a unique, lowercase-safe explicit MyST target anchor for `(kind, qualname)`."""
        key = (kind, qualname)
        if key in self._qualname_to_anchor:
            return self._qualname_to_anchor[key]

        prefix = KIND_PREFIX.get(kind, kind)
        slug_body = re.sub(r"[^a-zA-Z0-9]+", "-", qualname).strip("-").lower()
        base = f"{prefix}-{slug_body}"
        if len(base) > 64:
            digest = hashlib.sha1(f"{kind}:{qualname}".encode("utf-8")).hexdigest()[:6]
            base = f"{base[:57].rstrip('-')}-{digest}"

        existing = self._lower_to_qualname.get(base)
        if existing is not None and existing != f"{kind}:{qualname}":
            digest = hashlib.sha1(f"{kind}:{qualname}".encode("utf-8")).hexdigest()[:6]
            head = base[:57].rstrip("-")
            candidate = f"{head}-{digest}"
            while candidate in self._lower_to_qualname:
                digest = hashlib.sha1((digest + qualname).encode("utf-8")).hexdigest()[:6]
                candidate = f"{head}-{digest}"
            base = candidate

        self._lower_to_qualname[base] = f"{kind}:{qualname}"
        self._qualname_to_anchor[key] = base
        return base
