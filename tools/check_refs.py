#!/usr/bin/env python3
"""check_refs.py — validate every DOI in a BibTeX file against Crossref.

Purpose: catch fabricated / mismatched references (a DOI that resolves to a
different paper, a wrong author list, or an unresolvable DOI) before they ship.

Usage:
    uv run python tools/check_refs.py [path/to/references.bib]
    python3 tools/check_refs.py content/references.bib
    python3 tools/check_refs.py --refresh content/references.bib

Exit code 0 = all entries verified; 1 = at least one mismatch/unresolved DOI.
No third-party dependencies (stdlib only). Add a mailto for the Crossref
politeness pool via env CROSSREF_MAILTO.
"""
import argparse
import difflib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

MAILTO = os.environ.get("CROSSREF_MAILTO") or "tvb-docs-check-refs@users.noreply.github.com"
THRESHOLD = 0.80  # normalized-title similarity below this => mismatch


def norm(s: str) -> str:
    s = re.sub(r"\\[{}'\"^~v=][a-zA-Z]?|[{}]", " ", s or "")
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def field(body: str, name: str) -> str:
    m = re.search(rf"{name}\s*=\s*{{(.*?)}}", body, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""


def entries(text: str):
    # split on @type{key,
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+),", text):
        start = m.end()
        # crude brace-matched body
        depth = 1
        i = start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out.append((m.group(1), m.group(2).strip(), text[start:i - 1]))
    return out


def crossref_doi(doi: str, retries: int = 5):
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    if MAILTO:
        url += f"?mailto={urllib.parse.quote(MAILTO)}"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tvb-docs-check_refs/1.0 (mailto:%s)" % MAILTO})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r).get("message", {})
        except HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)  # 2,4,8,16s backoff
                continue
            raise
        except URLError as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
    raise last


def bib_author_families(body: str):
    m = re.search(r"author\s*=\s*{(.*?)}", body, re.IGNORECASE | re.DOTALL)
    if not m:
        return set()
    fams = set()
    for part in re.split(r"\band\b", m.group(1)):
        part = part.strip()
        if "," in part:
            fams.add(norm(part.split(",", 1)[0]))
    return {f for f in fams if f}


def bib_year(body: str):
    m = re.search(r"year\s*=\s*{?(\d{4})", body, re.IGNORECASE)
    return m.group(1) if m else ""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate DOIs in a BibTeX file against Crossref.")
    parser.add_argument("bib", nargs="?", default="content/references.bib", help="Path to references.bib")
    parser.add_argument("--refresh", action="store_true", help="Bypass cache and re-query Crossref for all DOIs")
    parser.add_argument("--cache", default=None, help="Path to cache JSON file (defaults to .refs-cache.json)")
    args = parser.parse_args(argv)

    bib_path = args.bib
    if not os.path.exists(bib_path):
        print(f"bib file not found: {bib_path}", file=sys.stderr)
        return 2

    cache_path = args.cache
    if not cache_path:
        cache_dir = os.path.dirname(bib_path) or "."
        cache_path = os.path.join(cache_dir, ".refs-cache.json")

    cache = {}
    if os.path.exists(cache_path) and not args.refresh:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception as e:
            print(f"Warning: could not read cache at {cache_path}: {e}", file=sys.stderr)
            cache = {}

    cache_dirty = False
    text = open(bib_path, encoding="utf-8").read()
    rows = entries(text)
    hard = 0      # fabrications / unresolved DOIs -> fail CI
    advisory = 0  # metadata slips -> warn only
    print(f"checking {len(rows)} entries in {bib_path}\n")

    for etype, key, body in rows:
        doi = field(body, "doi")
        title = field(body, "title")
        if not doi:
            print(f"[NO-DOI] {key}: no DOI field to verify")
            hard += 1
            continue

        cached = cache.get(doi) if not args.refresh else None
        if cached:
            ct = cached.get("title", "")
            cy = cached.get("year")
            ca = {norm(a) for a in cached.get("authors", []) if a}
        else:
            try:
                msg = crossref_doi(doi)
            except Exception as e:
                print(f"[UNRESOLVED] {key}: DOI {doi} -> {e}")
                hard += 1
                continue
            time.sleep(0.4)  # polite pacing for the Crossref polite pool
            ct = (msg.get("title") or [""])[0]
            cy = (msg.get("issued", {}).get("date-parts") or [[None]])[0][0]
            authors = sorted([a.get("family") for a in msg.get("author", []) if a.get("family")])
            ca = {norm(a) for a in authors if a}
            cache[doi] = {
                "title": ct,
                "year": cy,
                "authors": authors,
            }
            cache_dirty = True

        ratio = difflib.SequenceMatcher(None, norm(title), norm(ct)).ratio()
        if ratio < THRESHOLD:
            print(f"[MISMATCH] {key}: DOI {doi} resolves to:")
            print(f"           crossref: {ct}")
            print(f"           bib     : {title}   (similarity {ratio:.2f})")
            hard += 1
            continue

        # secondary metadata checks (advisory only)
        notes = []
        by = bib_year(body)
        if by and cy and str(by) != str(cy):
            notes.append(f"year bib={by} crossref={cy}")
        ba = bib_author_families(body)
        if ba and ca and not (ba & ca):
            notes.append(f"no author-family overlap (bib={sorted(ba)} crossref={sorted(ca)})")
        if notes:
            print(f"[CHECK] {key}: {doi} title OK but -> {'; '.join(notes)}")
            advisory += 1
        else:
            print(f"[OK] {key}: {doi}")

    if cache_dirty:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, sort_keys=True, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            print(f"Warning: could not write cache to {cache_path}: {e}", file=sys.stderr)

    print(f"\n{len(rows) - hard - advisory}/{len(rows)} clean, {advisory} advisory, {hard} hard problem(s).")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())

