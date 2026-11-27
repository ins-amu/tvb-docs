"""Convert NumPy docstrings and legacy Sphinx/rST fragments into valid MyST Markdown."""

from __future__ import annotations

import logging
import re
import textwrap
from collections.abc import Callable
from typing import Any

import griffe

_OUTER_MATH_ENV_RE = re.compile(
    r"^\\begin\{(?:aligned|align\*?|equation\*?|gather\*?|split|multline\*?|eqnarray\*?)\}"
)

XrefResolver = Callable[[str, str | None], str | None]

_SPHINX_XREF_RE = re.compile(
    r":(?:py:)?(class|meth|func|mod|attr|obj|exc|data|const):`([^`]+)`"
)
_INLINE_MATH_RE = re.compile(r":math:`([^`]+)`")
_CITE_REF_RE = re.compile(r"\[([A-Za-z0-9_.-]+)\]_")
_RST_DIRECTIVE_START_RE = re.compile(
    r"^([ \t]*)\.\.\s+(math|note|warning|deprecated|versionadded|versionchanged|rubric|moduleauthor|automethod|figure|image|NOTE)\s*::(.*)$"
)
_RST_TARGET_RE = re.compile(r"^\.\.\s+_[^:\s]+:\s*$")
_RST_FOOTNOTE_RE = re.compile(r"^([ \t]*)\.\.\s+\[([A-Za-z0-9_.-]+)\]\s*(.*)$")
_GRID_BORDER_RE = re.compile(r"^\s*\+[-=+:]+\+\s*$")
_GRID_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
_SPHINX_FIELD_RE = re.compile(
    r"^:(param|parameter|arg|argument|key|keyword|type|return|returns|rtype|raises|raise|ivar|cvar|var)\b([^:]*):(.*)$"
)


def _format_xref(kind: str, body: str, resolve_xref: XrefResolver | None) -> str:
    """Convert a Sphinx xref role body (`Title <target>` or `~pkg.Sym`) to a MyST link or inline code."""
    display: str | None = None
    target = body.strip()
    m = re.match(r"^(.+?)\s*<([^>]+)>$", target)
    if m:
        display = m.group(1).strip()
        target = m.group(2).strip()
    if target.startswith("~"):
        target = target[1:]
        if display is None:
            display = target.rsplit(".", 1)[-1]
    if display is None:
        display = target

    if resolve_xref is not None:
        resolved = resolve_xref(target, kind)
        if resolved:
            return f"[{display}]({resolved})"
    return f"`{display}`"


def _format_math_block(lines: list[str]) -> list[str]:
    """Emit a KaTeX/MyST display math block, wrapping multi-line `&` alignments cleanly."""
    dedented = textwrap.dedent("\n".join(lines)).strip("\n")
    if not dedented.strip():
        return []
    # Work around upstream tvb-library typo in BalloonModel.balloon_dfun (`v^{&/\alpha}`).
    dedented = dedented.replace("v^{&/\\alpha}", "v^{1/\\alpha}")
    has_outer_env = bool(_OUTER_MATH_ENV_RE.match(dedented.lstrip()))
    needs_aligned = ("&" in dedented or "\\\\" in dedented) and not has_outer_env
    if needs_aligned:
        dedented = dedented.replace("&=&", "&=")
        body = f"\\begin{{aligned}}\n{dedented}\n\\end{{aligned}}"
    else:
        body = dedented
    return ["", "$$", body, "$$", ""]


def _convert_grid_table(lines: list[str]) -> list[str]:
    """Convert a simple rST `+---+---+` grid table into a Markdown pipe table."""
    rows: list[tuple[bool, list[str]]] = []
    cur_cells: list[str] | None = None
    is_header_next = True
    seen_header_sep = False

    for line in lines:
        stripped = line.strip()
        if _GRID_BORDER_RE.match(stripped):
            if cur_cells is not None:
                rows.append((False, cur_cells))
                cur_cells = None
            if "=" in stripped and rows and not seen_header_sep:
                # Mark the preceding row(s) as header
                rows[-1] = (True, rows[-1][1])
                seen_header_sep = True
            is_header_next = False
            continue
        m = _GRID_ROW_RE.match(stripped)
        if m:
            cells = [c.strip() for c in m.group(1).split("|")]
            if cur_cells is None:
                cur_cells = cells
            else:
                # Continuation row: join text with space
                for idx in range(min(len(cur_cells), len(cells))):
                    if cells[idx]:
                        cur_cells[idx] = (cur_cells[idx] + " " + cells[idx]).strip()
    if cur_cells is not None:
        rows.append((is_header_next, cur_cells))

    if not rows:
        return []

    ncols = max(len(r[1]) for r in rows)
    norm_rows = [(hdr, cells + [""] * (ncols - len(cells))) for hdr, cells in rows]

    header_idx = next((i for i, (hdr, _) in enumerate(norm_rows) if hdr), 0)
    out: list[str] = [""]

    # Grid tables with banner rows above the header (e.g. Table 1 / EXCITABLE CONFIGURATION)
    # cannot precede the Markdown table header row; emit them as a bold caption instead.
    if header_idx > 0:
        captions = [" ".join(c for c in cells if c).strip() for _, cells in norm_rows[:header_idx]]
        caption_text = " — ".join(c for c in captions if c)
        if caption_text:
            out.append(f"**{caption_text}**")
            out.append("")
        norm_rows = norm_rows[header_idx:]
        header_idx = 0

    for i, (_, cells) in enumerate(norm_rows):
        escaped = [c.replace("|", "\\|") for c in cells]
        out.append("| " + " | ".join(escaped) + " |")
        if i == header_idx:
            out.append("| " + " | ".join(["---"] * ncols) + " |")
    out.append("")
    return out


def _convert_doctests(lines: list[str]) -> list[str]:
    """Wrap contiguous `>>>` / `...` doctest blocks into fenced ```python blocks."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if re.match(r"^\s*>>>\s?", lines[i]):
            block: list[str] = []
            while i < len(lines) and (
                lines[i].strip() != ""
                or (i + 1 < len(lines) and re.match(r"^\s*(?:>>>|\.\.\.)\s?", lines[i + 1]))
            ):
                block.append(lines[i])
                i += 1
            dedented = textwrap.dedent("\n".join(block)).splitlines()
            out.extend(["", "```python", *dedented, "```", ""])
        else:
            out.append(lines[i])
            i += 1
    return out


def sanitize_inline_rst(text: str, resolve_xref: XrefResolver | None = None) -> str:
    """Normalize inline rST roles (`:math:`, `:class:`, ```` `` ````, `[REF]_`) to MyST."""
    if not text:
        return ""
    out = _INLINE_MATH_RE.sub(lambda m: f"${m.group(1).strip()}$", text)
    out = _SPHINX_XREF_RE.sub(
        lambda m: _format_xref(m.group(1), m.group(2), resolve_xref),
        out,
    )
    out = _CITE_REF_RE.sub(lambda m: f"[{m.group(1)}]", out)
    # rST double backticks -> single Markdown backticks (only when not inside fenced code)
    out = re.sub(r"``([^`\n]+?)``", lambda m: f"`{m.group(1)}`", out)
    # Standalone Python decorators / handles like `@cuda.jit` are parsed as citations by MyST
    out = re.sub(r"(?<![A-Za-z0-9_`\\\[])(@[A-Za-z_][A-Za-z0-9_.]*)", r"`\1`", out)
    return out


def rst_to_myst(text: str, resolve_xref: XrefResolver | None = None) -> str:
    """Convert raw rST / Sphinx docstring prose into clean MyST Markdown."""
    if not text or not text.strip():
        return ""

    lines = textwrap.dedent(text).splitlines()
    out: list[str] = []
    i = 0
    in_fence = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue

        if _RST_TARGET_RE.match(stripped):
            i += 1
            continue

        # Legacy Sphinx `.. note::`, `.. warning::`, `.. math::`, etc.
        m_dir = _RST_DIRECTIVE_START_RE.match(line)
        if m_dir:
            base_indent = len(m_dir.group(1))
            kind = m_dir.group(2).lower()
            arg = m_dir.group(3).strip()
            i += 1
            body: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() == "":
                    body.append("")
                    i += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" \t"))
                if nxt_indent > base_indent:
                    body.append(nxt)
                    i += 1
                else:
                    break

            if kind in ("moduleauthor", "automethod", "figure", "image"):
                continue
            if kind == "math":
                math_lines = ([arg] if arg else []) + body
                out.extend(_format_math_block(math_lines))
            elif kind == "rubric":
                heading = sanitize_inline_rst(arg, resolve_xref)
                out.extend(["", f"**{heading}**", ""])
            else:
                admonition_name = {
                    "note": "note",
                    "warning": "warning",
                    "deprecated": "warning",
                    "versionadded": "note",
                    "versionchanged": "note",
                }.get(kind, "note")
                body_text = textwrap.dedent("\n".join(body)).strip()
                if kind in ("deprecated", "versionadded", "versionchanged"):
                    prefix = f"*{kind.title()}{f' {arg}' if arg else ''}:* "
                    body_text = prefix + body_text
                elif arg and not body_text:
                    body_text = arg
                body_text = sanitize_inline_rst(body_text, resolve_xref)
                out.extend(["", f":::{{{admonition_name}}}", body_text, ":::", ""])
            continue

        # Inline `.. NOTE: ...` comment-style note in TVB docstrings
        m_inline_note = re.match(r"^\s*\.\.\s+NOTE:\s*(.*)$", line)
        if m_inline_note:
            note_lines = [m_inline_note.group(1).strip()]
            base_indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(lines) and lines[i].strip() and (len(lines[i]) - len(lines[i].lstrip())) > base_indent:
                note_lines.append(lines[i].strip())
                i += 1
            out.extend(["", ":::{note}", sanitize_inline_rst(" ".join(note_lines), resolve_xref), ":::", ""])
            continue

        # Reference definitions `.. [KEY] citation text`
        m_ref = _RST_FOOTNOTE_RE.match(line)
        if m_ref:
            base_indent = len(m_ref.group(1))
            key = m_ref.group(2)
            parts = [m_ref.group(3).strip()]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    break
                nxt_indent = len(nxt) - len(nxt.lstrip(" \t"))
                if nxt_indent > base_indent:
                    parts.append(nxt.strip())
                    i += 1
                else:
                    break
            citation = sanitize_inline_rst(" ".join(p for p in parts if p), resolve_xref)
            out.append(f"- **[{key}]** {citation}")
            continue

        # Grid tables `+---+---+`
        if _GRID_BORDER_RE.match(stripped):
            tbl_lines: list[str] = []
            while i < len(lines) and (
                _GRID_BORDER_RE.match(lines[i].strip()) or _GRID_ROW_RE.match(lines[i].strip())
            ):
                tbl_lines.append(lines[i])
                i += 1
            out.extend(_convert_grid_table(tbl_lines))
            continue

        # Strip Sphinx `:param:` / `:return:` / `:type:` lines only if handled separately
        out.append(sanitize_inline_rst(line, resolve_xref))
        i += 1

    out = _convert_doctests(out)
    # Collapse >2 consecutive blank lines
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return collapsed


def _extract_sphinx_fields(text: str) -> tuple[str, list[tuple[str, str, str]], str]:
    """Split legacy `:param name:` / `:type name:` / `:return:` fields out of plain text."""
    prose: list[str] = []
    params: dict[str, dict[str, str]] = {}
    returns: list[str] = []
    lines = textwrap.dedent(text).splitlines()
    i = 0
    while i < len(lines):
        m = _SPHINX_FIELD_RE.match(lines[i].strip())
        if not m:
            prose.append(lines[i])
            i += 1
            continue
        field_kind = m.group(1)
        arg_name = m.group(2).strip()
        desc_parts = [m.group(3).strip()]
        base_indent = len(lines[i]) - len(lines[i].lstrip())
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                break
            nxt_stripped = nxt.strip()
            if _SPHINX_FIELD_RE.match(nxt_stripped):
                break
            if (len(nxt) - len(nxt.lstrip())) > base_indent:
                desc_parts.append(nxt_stripped)
                i += 1
            else:
                break
        desc = " ".join(p for p in desc_parts if p)
        if field_kind in ("param", "parameter", "arg", "argument", "key", "keyword"):
            entry = params.setdefault(arg_name, {"type": "", "desc": ""})
            entry["desc"] = desc
        elif field_kind == "type":
            entry = params.setdefault(arg_name, {"type": "", "desc": ""})
            entry["type"] = desc
        elif field_kind in ("return", "returns"):
            returns.append(desc)
    param_rows = [(name, info["type"], info["desc"]) for name, info in params.items()]
    return "\n".join(prose), param_rows, " ".join(returns)


def _render_param_table(
    items: list[tuple[str, str, str]],
    resolve_xref: XrefResolver | None = None,
) -> str:
    lines = ["| Name | Type | Description |", "| --- | --- | --- |"]
    for name, ann, desc in items:
        clean_ann = f"`{ann}`" if ann else "—"
        clean_desc = sanitize_inline_rst(" ".join(desc.split()), resolve_xref).replace("|", "\\|")
        lines.append(f"| `{name}` | {clean_ann} | {clean_desc or '—'} |")
    return "\n".join(lines)


def render_docstring(
    docstring: griffe.Docstring | None,
    resolve_xref: XrefResolver | None = None,
    *,
    heading_level: int = 3,
) -> str:
    """Render a `griffe.Docstring` (NumPy + Sphinx sections) into structured MyST Markdown."""
    if docstring is None or not docstring.value.strip():
        return ""

    h = "#" * heading_level
    chunks: list[str] = []
    # Griffe parses docstrings lazily on `.parsed`; silence parameter-mismatch warnings from upstream docstrings.
    griffe_logger = logging.getLogger("griffe")
    griffelib_logger = logging.getLogger("griffelib")
    prev_levels = (griffe_logger.level, griffelib_logger.level)
    griffe_logger.setLevel(logging.ERROR)
    griffelib_logger.setLevel(logging.ERROR)
    try:
        parsed: list[Any] = docstring.parsed
    finally:
        griffe_logger.setLevel(prev_levels[0])
        griffelib_logger.setLevel(prev_levels[1])

    for section in parsed:
        kind = section.kind
        val = section.value

        if kind == griffe.DocstringSectionKind.text:
            prose, sphinx_params, sphinx_ret = _extract_sphinx_fields(str(val))
            rendered = rst_to_myst(prose, resolve_xref)
            if rendered:
                chunks.append(rendered)
            if sphinx_params:
                chunks.append(f"{h} Parameters\n\n{_render_param_table(sphinx_params, resolve_xref)}")
            if sphinx_ret:
                chunks.append(f"{h} Returns\n\n{rst_to_myst(sphinx_ret, resolve_xref)}")

        elif kind in (
            griffe.DocstringSectionKind.parameters,
            griffe.DocstringSectionKind.other_parameters,
            griffe.DocstringSectionKind.attributes,
        ):
            title = {
                griffe.DocstringSectionKind.parameters: "Parameters",
                griffe.DocstringSectionKind.other_parameters: "Other Parameters",
                griffe.DocstringSectionKind.attributes: "Attributes",
            }[kind]
            rows = [
                (
                    p.name,
                    str(p.annotation) if p.annotation else "",
                    p.description or "",
                )
                for p in val
            ]
            if rows:
                chunks.append(f"{h} {title}\n\n{_render_param_table(rows, resolve_xref)}")

        elif kind in (griffe.DocstringSectionKind.returns, griffe.DocstringSectionKind.yields):
            title = "Returns" if kind == griffe.DocstringSectionKind.returns else "Yields"
            items = []
            for r in val:
                name_part = f"`{r.name}` " if getattr(r, "name", None) else ""
                type_part = f"(`{r.annotation}`) " if getattr(r, "annotation", None) else ""
                desc = rst_to_myst(r.description or "", resolve_xref)
                items.append(f"- {name_part}{type_part}{desc}".strip())
            if items:
                chunks.append(f"{h} {title}\n\n" + "\n".join(items))

        elif kind in (griffe.DocstringSectionKind.raises, griffe.DocstringSectionKind.warns):
            title = "Raises" if kind == griffe.DocstringSectionKind.raises else "Warns"
            items = []
            for r in val:
                ann = f"`{r.annotation}`" if getattr(r, "annotation", None) else "`Exception`"
                desc = rst_to_myst(r.description or "", resolve_xref)
                items.append(f"- {ann}: {desc}".strip())
            if items:
                chunks.append(f"{h} {title}\n\n" + "\n".join(items))

        elif kind == griffe.DocstringSectionKind.examples:
            ex_parts: list[str] = []
            for sub_kind, sub_val in val:
                sub_str = str(sub_val)
                if sub_kind == griffe.DocstringSectionKind.examples:
                    cleaned = sub_str.strip()
                    if not cleaned.startswith("```"):
                        ex_parts.append(f"```python\n{cleaned}\n```")
                    else:
                        ex_parts.append(cleaned)
                else:
                    ex_parts.append(rst_to_myst(sub_str, resolve_xref))
            if ex_parts:
                chunks.append(f"{h} Examples\n\n" + "\n\n".join(p for p in ex_parts if p))

        elif kind == griffe.DocstringSectionKind.admonition:
            title = getattr(section, "title", None) or "Note"
            desc = getattr(val, "description", None) or str(val)
            low = title.lower()
            if low in ("note", "warning", "tip", "important", "caution"):
                chunks.append(f":::{{{low}}}\n{rst_to_myst(desc, resolve_xref)}\n:::")
            elif low == "see also":
                # Auto-link symbol names in See Also lines
                sa_lines = []
                for line in str(desc).splitlines():
                    s = line.strip()
                    if not s:
                        continue
                    head_sym = s.split(":")[0].split(",")[0].strip().strip("`")
                    resolved = resolve_xref(head_sym, None) if resolve_xref else None
                    if resolved and head_sym:
                        sa_lines.append(f"- [{head_sym}]({resolved})" + s[len(head_sym):])
                    else:
                        sa_lines.append(f"- {sanitize_inline_rst(s, resolve_xref)}")
                if sa_lines:
                    chunks.append(f"{h} See Also\n\n" + "\n".join(sa_lines))
            else:
                chunks.append(f"{h} {title}\n\n{rst_to_myst(desc, resolve_xref)}")

        elif kind == griffe.DocstringSectionKind.deprecated:
            desc = getattr(val, "description", None) or str(val)
            ver = getattr(val, "version", "")
            chunks.append(f":::{{warning}}\n**Deprecated{f' ({ver})' if ver else ''}:** {rst_to_myst(desc, resolve_xref)}\n:::")

    return "\n\n".join(c for c in chunks if c.strip())


def first_sentence(docstring: griffe.Docstring | None) -> str:
    """Return a compact one-line summary for tables and `api-symbols.json`."""
    if docstring is None or not docstring.value.strip():
        return ""
    for line in textwrap.dedent(docstring.value).splitlines():
        s = line.strip()
        if not s or s.startswith(".."):
            continue
        if s.startswith(":"):
            continue
        # Strip inline rST formatting for compact summaries
        s = re.sub(r":math:`([^`]+)`", r"\1", s)
        s = re.sub(r":(?:py:)?(?:class|meth|func|mod|attr|obj):`(?:~)?([^`<>]+)(?:<[^>]+>)?`", r"\1", s)
        s = s.replace("``", "`")
        m = re.match(r"^(.+?[.!?])(?:\s|$)", s)
        return (m.group(1) if m else s)[:180]
    return ""
