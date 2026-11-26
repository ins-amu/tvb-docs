#!/usr/bin/env python3
"""Compute git-blame page attribution and generate the Contributors dashboard.

Reads `_toc.yml` and `contributors.yml`, computes surviving authorship per page
using `git blame -w -M -C` (respecting `.mailmap` and `.git-blame-ignore-revs`),
includes `Co-authored-by:` trailers from blamed commits, and filters `.ipynb`
blame to cell `source` lines only so notebook outputs/metadata never hijack
credit.

Outputs:
  - `_build/contributors/contributors.json`
  - `content/about/contributors.md` (written only when content changes)
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import unicodedata
from urllib.parse import urlparse
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON_OUT = Path("_build/contributors/contributors.json")
DEFAULT_MD_OUT = Path("content/about/contributors.md")
GENERATED_MD_REL = "content/about/contributors.md"
API_INDEX_REL = "content/reference/api/index.md"
API_PREFIX = "content/reference/api/"

DEFAULT_BOT_NAMES = {
    "copilot",
    "copilot-swe-agent",
    "copilot-swe-agent[bot]",
    "dependabot",
    "dependabot[bot]",
    "github-actions",
    "github-actions[bot]",
    "renovate",
    "renovate[bot]",
}

DEFAULT_BOT_EMAILS = {
    "action@github.com",
    "github-actions@github.com",
    "noreply@anthropic.com",
}

COAUTHOR_RE = re.compile(
    r"^co-authored-by:\s*(.+?)\s*<([^>\r\n]+)>\s*$",
    re.IGNORECASE | re.MULTILINE,
)

JSON_TOKEN_RE = re.compile(
    r'"(?:\\.|[^"\\])*"|[{}\[\]:,]|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
)

NOREPLY_GITHUB_RE = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.IGNORECASE)
HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def sort_key(name: str) -> tuple[str, str, str]:
    """Case- and diacritic-insensitive alphabetical sort key by last name."""
    parts = name.strip().split()
    if not parts:
        return ("", "", "")
    last = _strip_accents(parts[-1]).casefold()
    rest = _strip_accents(" ".join(parts[:-1])).casefold()
    return (last, rest, name.casefold())


def slugify_id(name: str) -> str:
    """Create a deterministic, lowercase ASCII slug for a contributor name."""
    ascii_ish = _strip_accents(name).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_ish).strip("-")
    return slug or "contributor"


def sanitize_website(url: str | None) -> str:
    """Allow only http:// or https:// URLs for contributor website links."""
    if not url or not isinstance(url, str):
        return ""
    cleaned = url.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return cleaned
    return ""


def _is_excluded_page(rel_path: str) -> bool:
    if rel_path == GENERATED_MD_REL:
        return True
    if rel_path.startswith(API_PREFIX) and rel_path != API_INDEX_REL:
        return True
    return False


def parse_toc_pages(repo_root: Path) -> list[tuple[str, str]]:
    """Return ordered, deduplicated `(rel_posix_path, section_label)` entries from `_toc.yml`."""
    toc_path = repo_root / "_toc.yml"
    if not toc_path.is_file():
        return []
    toc_cfg = yaml.safe_load(toc_path.read_text(encoding="utf-8")) or {}

    pages: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_page(raw_file: str | None, section: str) -> None:
        if not raw_file or not isinstance(raw_file, str):
            return
        rel = Path(raw_file.strip()).as_posix().lstrip("./")
        if not rel or _is_excluded_page(rel) or rel in seen:
            return
        if (repo_root / rel).is_file():
            seen.add(rel)
            pages.append((rel, section))

    def walk_entries(entries: list | None, section: str) -> None:
        if not isinstance(entries, list):
            return
        for item in entries:
            if not isinstance(item, dict):
                continue
            add_page(item.get("file"), section)
            walk_entries(item.get("sections"), section)
            walk_entries(item.get("chapters"), section)

    add_page(toc_cfg.get("root"), "Overview")
    for part in toc_cfg.get("parts") or []:
        if not isinstance(part, dict):
            continue
        section = str(part.get("caption") or "Documentation").strip()
        add_page(part.get("file"), section)
        walk_entries(part.get("chapters"), section)
        walk_entries(part.get("sections"), section)

    return pages


def ipynb_source_line_numbers(raw_json: str) -> set[int] | None:
    """Return 1-based line numbers belonging to non-blank cell `source` fields.

    Returns `None` when `raw_json` is not valid nbformat JSON so callers can fall
    back to blaming non-blank lines.
    """
    try:
        parsed = json.loads(raw_json)
    except Exception:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("cells"), list):
        return None

    newlines = [idx for idx, ch in enumerate(raw_json) if ch == "\n"]

    def line_of(offset: int) -> int:
        return bisect_left(newlines, offset) + 1

    lines: set[int] = set()
    stack: list[dict] = []

    def mark_value_consumed() -> None:
        if not stack:
            return
        top = stack[-1]
        if top["kind"] == "object" and top["expect"] == "value":
            top["expect"] = "comma"
        elif top["kind"] == "array" and top["expect"] == "value":
            top["expect"] = "comma"

    def in_cell_source() -> bool:
        if len(stack) == 3:
            return (
                stack[0]["kind"] == "object"
                and stack[0].get("current_key") == "cells"
                and stack[1]["kind"] == "array"
                and stack[2]["kind"] == "object"
                and stack[2].get("current_key") == "source"
                and stack[2]["expect"] == "value"
            )
        if len(stack) == 4:
            return (
                stack[0]["kind"] == "object"
                and stack[0].get("current_key") == "cells"
                and stack[1]["kind"] == "array"
                and stack[2]["kind"] == "object"
                and stack[2].get("current_key") == "source"
                and stack[3]["kind"] == "array"
                and stack[3]["expect"] == "value"
            )
        return False

    for match in JSON_TOKEN_RE.finditer(raw_json):
        tok = match.group(0)
        if tok == "{":
            stack.append({"kind": "object", "expect": "key", "current_key": None})
        elif tok == "}":
            if stack:
                stack.pop()
            mark_value_consumed()
        elif tok == "[":
            stack.append({"kind": "array", "expect": "value"})
        elif tok == "]":
            if stack:
                stack.pop()
            mark_value_consumed()
        elif tok == ":":
            if stack and stack[-1]["kind"] == "object":
                stack[-1]["expect"] = "value"
        elif tok == ",":
            if stack:
                top = stack[-1]
                if top["kind"] == "object":
                    top["expect"] = "key"
                    top["current_key"] = None
                elif top["kind"] == "array":
                    top["expect"] = "value"
        elif tok.startswith('"'):
            if stack and stack[-1]["kind"] == "object" and stack[-1]["expect"] == "key":
                stack[-1]["current_key"] = json.loads(tok)
                stack[-1]["expect"] = "colon"
            else:
                if in_cell_source():
                    try:
                        decoded = json.loads(tok)
                    except Exception:
                        decoded = ""
                    if isinstance(decoded, str) and decoded.strip():
                        start_line = line_of(match.start())
                        end_line = line_of(max(match.start(), match.end() - 1))
                        lines.update(range(start_line, end_line + 1))
                mark_value_consumed()
        else:
            mark_value_consumed()

    return lines


def _has_active_ignore_revs(ignore_revs_file: Path | None) -> bool:
    if ignore_revs_file is None or not ignore_revs_file.is_file():
        return False
    for raw in ignore_revs_file.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            return True
    return False


def _run_git(repo_root: Path, args: list[str], *, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def blame_file(
    repo_root: Path,
    rel_path: str,
    *,
    ignore_revs_file: Path | None = None,
) -> tuple[set[str], list[tuple[str, str]], str]:
    """Run `git blame --line-porcelain -w -M -C` for `rel_path`.

    Returns `(commit_shas, author_identities, last_updated_iso_date)`.
    """
    cmd = ["blame", "--line-porcelain", "-w", "-M", "-C"]
    if _has_active_ignore_revs(ignore_revs_file):
        cmd.extend(["--ignore-revs-file", str(ignore_revs_file)])
    cmd.extend(["HEAD", "--", rel_path])

    res = _run_git(repo_root, cmd)
    if res.returncode != 0 or not res.stdout:
        return set(), [], ""

    allowed_lines: set[int] | None = None
    if rel_path.endswith(".ipynb"):
        show_res = _run_git(repo_root, ["show", f"HEAD:{rel_path}"])
        if show_res.returncode == 0 and show_res.stdout:
            allowed_lines = ipynb_source_line_numbers(show_res.stdout)

    entries: list[tuple[str, str, str, int, bool, int]] = []
    commit_meta: dict[str, dict[str, str | int]] = {}

    cur_sha = ""
    cur_final_line = 0
    cur_meta: dict[str, str | int] = {}

    for raw_line in res.stdout.splitlines():
        if raw_line.startswith("\t"):
            text_line = raw_line[1:]
            meta = commit_meta.get(cur_sha, {})
            author = str(cur_meta.get("author") or meta.get("author") or "").strip()
            email = str(cur_meta.get("author-mail") or meta.get("author-mail") or "").strip("<> ").strip()
            ts = int(cur_meta.get("committer-time") or meta.get("committer-time") or cur_meta.get("author-time") or meta.get("author-time") or 0)
            if cur_sha:
                commit_meta[cur_sha] = {
                    "author": author,
                    "author-mail": email,
                    "committer-time": ts,
                }
            entries.append((cur_sha, author, email, ts, bool(text_line.strip()), cur_final_line))
            cur_sha = ""
            cur_final_line = 0
            cur_meta = {}
            continue

        if not cur_sha:
            parts = raw_line.split()
            if len(parts) >= 3 and len(parts[0]) >= 7:
                cur_sha = parts[0]
                try:
                    cur_final_line = int(parts[2])
                except ValueError:
                    cur_final_line = 0
                cur_meta = {}
            continue

        if raw_line.startswith("author "):
            cur_meta["author"] = raw_line[len("author "):].strip()
        elif raw_line.startswith("author-mail "):
            cur_meta["author-mail"] = raw_line[len("author-mail "):].strip("<> ").strip()
        elif raw_line.startswith("author-time "):
            try:
                cur_meta["author-time"] = int(raw_line[len("author-time "):].strip())
            except ValueError:
                pass
        elif raw_line.startswith("committer-time "):
            try:
                cur_meta["committer-time"] = int(raw_line[len("committer-time "):].strip())
            except ValueError:
                pass

    if not entries:
        return set(), [], ""

    if allowed_lines is not None:
        kept = [e for e in entries if e[5] in allowed_lines]
    else:
        kept = [e for e in entries if e[4]]
        if not kept:
            kept = entries

    commits: set[str] = set()
    identities: list[tuple[str, str]] = []
    seen_identities: set[tuple[str, str]] = set()
    max_ts = 0

    for sha, author, email, ts, _, _ in kept:
        if sha and not sha.startswith("0" * 40):
            commits.add(sha)
        if author or email:
            ident = (author, email)
            if ident not in seen_identities:
                seen_identities.add(ident)
                identities.append(ident)
        if ts > max_ts:
            max_ts = ts

    last_updated = ""
    if max_ts > 0:
        last_updated = datetime.fromtimestamp(max_ts, tz=timezone.utc).strftime("%Y-%m-%d")

    return commits, identities, last_updated


def collect_coauthors(repo_root: Path, commits: set[str]) -> dict[str, list[tuple[str, str]]]:
    """Fetch `Co-authored-by:` trailers for the given commit SHAs."""
    coauthors: dict[str, list[tuple[str, str]]] = {}
    commit_list = sorted(commits)
    chunk_size = 200
    for idx in range(0, len(commit_list), chunk_size):
        chunk = commit_list[idx : idx + chunk_size]
        res = _run_git(repo_root, ["log", "--no-walk", "--format=%H%x1f%B%x1e", *chunk])
        if res.returncode != 0 or not res.stdout:
            continue
        for record in res.stdout.split("\x1e"):
            if "\x1f" not in record:
                continue
            sha, body = record.split("\x1f", 1)
            sha = sha.strip()
            found: list[tuple[str, str]] = []
            for m in COAUTHOR_RE.finditer(body):
                found.append((m.group(1).strip(), m.group(2).strip()))
            if found:
                coauthors[sha] = found
    return coauthors


def resolve_mailmap(
    repo_root: Path,
    identities: set[tuple[str, str]],
) -> dict[tuple[str, str], tuple[str, str]]:
    """Resolve `(name, email)` pairs through `.mailmap` using `git check-mailmap --stdin`."""
    ordered = sorted(identities)
    if not ordered:
        return {}

    stdin_lines = "".join(f"{name or email} <{email}>\n" for name, email in ordered)
    res = _run_git(repo_root, ["check-mailmap", "--stdin"], stdin_text=stdin_lines)
    if res.returncode != 0:
        return {ident: ident for ident in ordered}

    out_lines = [line for line in res.stdout.splitlines() if line.strip()]
    if len(out_lines) != len(ordered):
        return {ident: ident for ident in ordered}

    resolved: dict[tuple[str, str], tuple[str, str]] = {}
    for orig, mapped_line in zip(ordered, out_lines):
        m = re.match(r"^(.*?)\s*<([^>]+)>\s*$", mapped_line.strip())
        if m:
            resolved[orig] = (m.group(1).strip(), m.group(2).strip())
        else:
            resolved[orig] = orig
    return resolved


def load_contributors_config(repo_root: Path) -> dict:
    """Load `contributors.yml` if present."""
    cfg_path = repo_root / "contributors.yml"
    if not cfg_path.is_file():
        return {}
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}


def is_bot(name: str, email: str, config: dict) -> bool:
    """Return True if the identity represents an automated bot or ignored account."""
    name_l = name.strip().casefold()
    email_l = email.strip().casefold()

    if "[bot]" in name_l or "[bot]" in email_l:
        return True
    if name_l in DEFAULT_BOT_NAMES or email_l in DEFAULT_BOT_EMAILS:
        return True
    if email_l.startswith("copilot@") or "+copilot@" in email_l:
        return True

    cfg_names = {str(n).strip().casefold() for n in (config.get("ignore_names") or [])}
    cfg_emails = {str(e).strip().casefold() for e in (config.get("ignore_emails") or [])}
    return name_l in cfg_names or email_l in cfg_emails


def _build_profile_lookup(config: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    by_email: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    raw_profiles = config.get("contributors") or {}
    if not isinstance(raw_profiles, dict):
        return by_email, by_name

    for cid, entry in raw_profiles.items():
        if not isinstance(entry, dict):
            continue
        profile = {
            "id": str(cid).strip(),
            "name": str(entry.get("name") or cid).strip(),
            "github": str(entry.get("github") or "").strip().lstrip("@"),
            "affiliation": str(entry.get("affiliation") or "").strip(),
            "website": sanitize_website(entry.get("website")),
        }
        emails: list[str] = []
        if entry.get("email"):
            emails.append(str(entry["email"]))
        for extra in entry.get("emails") or []:
            if extra:
                emails.append(str(extra))
        for em in emails:
            by_email[em.strip().casefold()] = profile
        by_name[profile["name"].casefold()] = profile
        by_name[_strip_accents(profile["name"]).casefold()] = profile
    return by_email, by_name


def match_contributor(
    name: str,
    email: str,
    config: dict,
    lookups: tuple[dict[str, dict], dict[str, dict]] | None = None,
) -> dict:
    """Match a canonical `(name, email)` against `contributors.yml` or derive metadata."""
    by_email, by_name = lookups if lookups is not None else _build_profile_lookup(config)

    email_key = email.strip().casefold()
    name_key = name.strip().casefold()
    ascii_name_key = _strip_accents(name.strip()).casefold()

    matched = by_email.get(email_key) or by_name.get(name_key) or by_name.get(ascii_name_key)
    if matched:
        return dict(matched)

    github = ""
    if email:
        m = NOREPLY_GITHUB_RE.match(email.strip())
        if m:
            github = m.group(1)

    display_name = name.strip() or github or email.split("@", 1)[0]
    return {
        "id": slugify_id(display_name),
        "name": display_name,
        "github": github,
        "affiliation": "",
        "website": "",
    }


def extract_page_title(repo_root: Path, rel_path: str) -> str:
    """Extract the H1 page title from a `.md` or `.ipynb` file."""
    path = repo_root / rel_path
    if not path.is_file():
        return Path(rel_path).stem.replace("-", " ").replace("_", " ").title()

    if rel_path.endswith(".ipynb"):
        try:
            nb = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            nb = {}
        for cell in nb.get("cells") or []:
            if not isinstance(cell, dict) or cell.get("cell_type") != "markdown":
                continue
            src = cell.get("source") or ""
            text = "".join(src) if isinstance(src, list) else str(src)
            for line in text.splitlines():
                m = HEADING_RE.match(line)
                if m:
                    return m.group(1).strip()
        return Path(rel_path).stem.replace("-", " ").replace("_", " ").title()

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    idx = 0
    if lines and lines[0].strip() == "---":
        idx = 1
        while idx < len(lines) and lines[idx].strip() not in {"---", "..."}:
            idx += 1
        idx += 1

    in_fence = False
    fence_char = ""
    for line in lines[idx:]:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_char = marker
            elif marker == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            return m.group(1).strip()

    return Path(rel_path).stem.replace("-", " ").replace("_", " ").title()


def compute_attribution(repo_root: Path) -> dict:
    """Compute per-page and per-contributor attribution data for `repo_root`."""
    config = load_contributors_config(repo_root)
    lookups = _build_profile_lookup(config)
    ignore_revs = repo_root / ".git-blame-ignore-revs"
    toc_pages = parse_toc_pages(repo_root)

    raw_pages: list[dict] = []
    all_commits: set[str] = set()
    all_identities: set[tuple[str, str]] = set()

    for rel_path, section in toc_pages:
        commits, identities, last_updated = blame_file(
            repo_root, rel_path, ignore_revs_file=ignore_revs
        )
        all_commits.update(commits)
        all_identities.update(identities)
        raw_pages.append(
            {
                "path": rel_path,
                "section": section,
                "title": extract_page_title(repo_root, rel_path),
                "commits": commits,
                "identities": identities,
                "last_updated": last_updated,
            }
        )

    coauthors_by_commit = collect_coauthors(repo_root, all_commits)
    for co_list in coauthors_by_commit.values():
        all_identities.update(co_list)

    mailmap_cache = resolve_mailmap(repo_root, all_identities)

    pages_out: dict[str, dict] = {}
    contributors_agg: dict[str, dict] = {}
    used_ids: dict[str, str] = {}

    for entry in raw_pages:
        page_identities = list(entry["identities"])
        for sha in entry["commits"]:
            page_identities.extend(coauthors_by_commit.get(sha, ()))

        page_profiles: dict[str, dict] = {}
        for raw_ident in page_identities:
            canon_name, canon_email = mailmap_cache.get(raw_ident, raw_ident)
            if is_bot(canon_name, canon_email, config) or is_bot(raw_ident[0], raw_ident[1], config):
                continue
            profile = match_contributor(canon_name, canon_email, config, lookups)
            cid = profile["id"]
            if cid in used_ids and used_ids[cid] != profile["name"].casefold():
                # Avoid accidental slug collision across genuinely distinct contributors.
                digest = hashlib.sha1(f"{canon_name}:{canon_email}".encode("utf-8")).hexdigest()[:4]
                cid = f"{cid}-{digest}"
                profile["id"] = cid
            used_ids[cid] = profile["name"].casefold()
            page_profiles[cid] = profile

        sorted_profiles = sorted(page_profiles.values(), key=lambda p: sort_key(p["name"]))
        if not sorted_profiles:
            continue

        pages_out[entry["path"]] = {
            "title": entry["title"],
            "section": entry["section"],
            "last_updated": entry["last_updated"],
            "contributors": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    **({"github": p["github"]} if p["github"] else {}),
                    **({"affiliation": p["affiliation"]} if p["affiliation"] else {}),
                    **({"website": p["website"]} if p["website"] else {}),
                }
                for p in sorted_profiles
            ],
        }

        for p in sorted_profiles:
            cid = p["id"]
            agg = contributors_agg.setdefault(
                cid,
                {
                    "id": cid,
                    "name": p["name"],
                    "github": p["github"],
                    "affiliation": p["affiliation"],
                    "website": p["website"],
                    "sections": {},
                    "pages": [],
                },
            )
            sec = entry["section"]
            agg["sections"][sec] = agg["sections"].get(sec, 0) + 1
            agg["pages"].append(
                {
                    "path": entry["path"],
                    "title": entry["title"],
                    "section": sec,
                    "last_updated": entry["last_updated"],
                }
            )

    sorted_contributors: dict[str, dict] = {}
    for cid, agg in sorted(contributors_agg.items(), key=lambda kv: sort_key(kv[1]["name"])):
        agg["page_count"] = len(agg["pages"])
        sorted_contributors[cid] = agg

    return {
        "pages": pages_out,
        "contributors": sorted_contributors,
    }


def _escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _format_links_cell(contrib: dict) -> str:
    parts: list[str] = []
    if contrib.get("github"):
        gh = contrib["github"]
        parts.append(f"[@{gh}](https://github.com/{gh})")
    aff = contrib.get("affiliation", "")
    web = contrib.get("website", "")
    if aff and web:
        parts.append(f"[{_escape_table_cell(aff)}]({web})")
    elif web:
        host = urlparse(web).netloc or web
        parts.append(f"[{_escape_table_cell(host)}]({web})")
    elif aff:
        parts.append(_escape_table_cell(aff))
    return " · ".join(parts) if parts else "—"


def render_contributors_markdown(data: dict) -> str:
    """Render `content/about/contributors.md` from attribution `data`."""
    lines: list[str] = [
        "# Contributors",
        "",
        "Every contribution to the TVB documentation — from tutorials and model cards to small fixes and review suggestions — is credited automatically.",
        "",
        "Page attribution is computed at build time from surviving lines in `git blame` (including `Co-authored-by:` review trailers, and excluding generated API pages and notebook output cells). To add or update your GitHub profile, affiliation, or institute website, edit [`contributors.yml`](https://github.com/ins-amu/tvb-docs/blob/main/contributors.yml) (and [`.mailmap`](https://github.com/ins-amu/tvb-docs/blob/main/.mailmap) if needed).",
        "",
    ]

    contributors = list((data.get("contributors") or {}).values())
    if not contributors:
        lines.extend(
            [
                "No contributor metadata was found (for example in a build without git history).",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Summary",
            "",
            "| Contributor | Links | Sections | Pages |",
            "| --- | --- | --- | --- |",
        ]
    )

    for contrib in contributors:
        cid = contrib["id"]
        name = _escape_table_cell(contrib["name"])
        links_cell = _format_links_cell(contrib)
        sections_cell = _escape_table_cell(", ".join(contrib["sections"].keys()))
        lines.append(
            f"| [{name}](#contributor-{cid}) | {links_cell} | {sections_cell} | {contrib['page_count']} |"
        )

    lines.extend(["", "## Pages by contributor", ""])

    for contrib in contributors:
        cid = contrib["id"]
        name = contrib["name"]
        lines.append(f"(contributor-{cid})=")
        lines.append(f"### {name}")
        lines.append("")

        meta_bits: list[str] = []
        if contrib.get("github"):
            gh = contrib["github"]
            meta_bits.append(f"**GitHub:** [@{gh}](https://github.com/{gh})")
        aff = contrib.get("affiliation", "")
        web = contrib.get("website", "")
        if aff and web:
            meta_bits.append(f"**Affiliation:** [{aff}]({web})")
        elif web:
            host = urlparse(web).netloc or web
            meta_bits.append(f"**Website:** [{host}]({web})")
        elif aff:
            meta_bits.append(f"**Affiliation:** {aff}")
        if meta_bits:
            lines.append("- " + " · ".join(meta_bits))
            lines.append("")

        pages_by_section: dict[str, list[dict]] = {}
        for page in contrib["pages"]:
            pages_by_section.setdefault(page["section"], []).append(page)

        for section, sec_pages in pages_by_section.items():
            lines.append(f"- **{section}**")
            for page in sec_pages:
                rel_link = posixpath.relpath(page["path"], "content/about")
                lines.append(f"  - [{page['title']}]({rel_link})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing == text:
            return False
    path.write_text(text, encoding="utf-8")
    return True


def build_contributors(
    repo_root: Path = REPO_ROOT,
    *,
    json_out: Path | None = None,
    md_out: Path | None = None,
) -> dict:
    """Compute attribution and write JSON + Markdown outputs."""
    data = compute_attribution(repo_root)
    json_path = json_out if json_out is not None else (repo_root / DEFAULT_JSON_OUT)
    md_path = md_out if md_out is not None else (repo_root / DEFAULT_MD_OUT)

    json_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    _write_if_changed(json_path, json_text)
    md_text = render_contributors_markdown(data)
    _write_if_changed(md_path, md_text)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools/build_contributors.py",
        description="Generate git-blame page attribution and Contributors dashboard.",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--json-out", type=Path, default=None, help="Output JSON path")
    parser.add_argument("--md-out", type=Path, default=None, help="Output Markdown dashboard path")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    data = build_contributors(repo_root, json_out=args.json_out, md_out=args.md_out)
    print(
        f"Built contributors: {len(data['contributors'])} contributors across {len(data['pages'])} pages.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
