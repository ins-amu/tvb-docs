"""Tests for git-blame page attribution and Contributors dashboard generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.build_contributors import (  # noqa: E402
    blame_file,
    build_contributors,
    ipynb_source_line_numbers,
    sanitize_website,
    sort_key,
)


def _git(repo: Path, *args: str, author_name: str = "Setup", author_email: str = "setup@example.org") -> str:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
    )
    res = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


class TestContributors(unittest.TestCase):
    def test_ipynb_source_line_numbers_excludes_outputs_and_metadata(self) -> None:
        nb = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {"tags": ["intro"]},
                    "source": ["# Title\n", "   \n", "Body line"],
                },
                {
                    "cell_type": "code",
                    "execution_count": 7,
                    "metadata": {"collapsed": False},
                    "outputs": [
                        {
                            "output_type": "display_data",
                            "data": {"image/png": "AAAA\nBBBB"},
                        }
                    ],
                    "source": "x = 1 + 1",
                },
            ],
            "metadata": {"kernelspec": {"name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        raw = json.dumps(nb, indent=2)
        allowed = ipynb_source_line_numbers(raw)
        self.assertIsNotNone(allowed)
        lines = raw.splitlines()
        allowed_texts = [lines[ln - 1] for ln in sorted(allowed)]

        self.assertTrue(any("# Title" in t for t in allowed_texts))
        self.assertTrue(any("Body line" in t for t in allowed_texts))
        self.assertTrue(any("x = 1 + 1" in t for t in allowed_texts))
        self.assertFalse(any("AAAA" in t for t in allowed_texts))
        self.assertFalse(any("execution_count" in t for t in allowed_texts))
        self.assertFalse(any("intro" in t for t in allowed_texts))
        # Whitespace-only source line should not be included
        self.assertFalse(any(t.strip().strip('",') == "" for t in allowed_texts))

    def test_ipynb_source_line_numbers_malformed_json_returns_none(self) -> None:
        self.assertIsNone(ipynb_source_line_numbers("{not valid json"))

    def test_sanitize_website(self) -> None:
        self.assertEqual(sanitize_website("https://ins-amu.fr"), "https://ins-amu.fr")
        self.assertEqual(sanitize_website("http://example.org/lab"), "http://example.org/lab")
        self.assertEqual(sanitize_website("javascript:alert(1)"), "")
        self.assertEqual(sanitize_website(""), "")

    def test_sort_key_orders_by_last_name(self) -> None:
        names = [
            "Alice Zimmerman",
            "Zoe Adams",
            "Amirhossein Esmaeili",
            "Matthew Bassat",
            "Marmaduke Woodman",
            "Ján Repka",
        ]
        self.assertEqual(
            sorted(names, key=sort_key),
            [
                "Zoe Adams",
                "Matthew Bassat",
                "Amirhossein Esmaeili",
                "Ján Repka",
                "Marmaduke Woodman",
                "Alice Zimmerman",
            ],
        )

    def test_end_to_end_git_repo_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _git(repo, "init")

            (repo / ".mailmap").write_text(
                "Alice Anderson <alice@example.org> alice <alice@example.org>\n",
                encoding="utf-8",
            )
            (repo / ".git-blame-ignore-revs").write_text(
                "# Empty ignore list\n",
                encoding="utf-8",
            )
            (repo / "contributors.yml").write_text(
                """
contributors:
  alice-anderson:
    name: Alice Anderson
    email: alice@example.org
    github: alicegh
    affiliation: Institute of Neuroscience
    website: https://ins.example.org
  bob-brown:
    name: Bob Brown
    email: bob@example.org
    github: bobgh
""",
                encoding="utf-8",
            )
            (repo / "_toc.yml").write_text(
                """
format: jb-book
root: README.md
parts:
  - caption: Guides
    chapters:
      - file: content/guide.md
      - file: content/overwritten.md
      - file: content/notebook.ipynb
  - caption: About
    chapters:
      - file: content/about/contributors.md
""",
                encoding="utf-8",
            )
            (repo / "content" / "about").mkdir(parents=True)
            (repo / "README.md").write_text("# Home\n\nWelcome.\n", encoding="utf-8")
            (repo / "content" / "guide.md").write_text(
                "# User Guide\n\nOriginal paragraph.\n", encoding="utf-8"
            )
            (repo / "content" / "overwritten.md").write_text(
                "# Overwritten Page\n\nBob's temporary line.\n", encoding="utf-8"
            )
            nb_v1 = {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": ["# Notebook Title\n"]},
                    {
                        "cell_type": "code",
                        "execution_count": 1,
                        "metadata": {},
                        "outputs": [{"output_type": "stream", "text": ["old output\n"]}],
                        "source": ["print('hello')\n"],
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            (repo / "content" / "notebook.ipynb").write_text(
                json.dumps(nb_v1, indent=2) + "\n", encoding="utf-8"
            )
            _git(repo, "add", ".")
            _git(
                repo,
                "commit",
                "-m",
                "Initial docs",
                author_name="alice",
                author_email="alice@example.org",
            )

            # Bob edits guide.md (keeping Alice's line) and owns overwritten.md for now.
            (repo / "content" / "guide.md").write_text(
                "# User Guide\n\nOriginal paragraph.\n\nBob's section.\n", encoding="utf-8"
            )
            (repo / "content" / "overwritten.md").write_text(
                "# Overwritten Page\n\nBob edited line.\n", encoding="utf-8"
            )
            _git(repo, "add", "content/guide.md", "content/overwritten.md")
            _git(
                repo,
                "commit",
                "-m",
                "Bob updates",
                author_name="Bob Brown",
                author_email="bob@example.org",
            )

            # Carol replaces all lines of overwritten.md with a human Co-authored-by and a bot Co-authored-by.
            (repo / "content" / "overwritten.md").write_text(
                "# Fresh Title\n\nCompletely rewritten by Carol.\n", encoding="utf-8"
            )
            _git(repo, "add", "content/overwritten.md")
            _git(
                repo,
                "commit",
                "-m",
                "Rewrite page\n\nCo-authored-by: Reviewer Zoe <zoe@example.org>\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>",
                author_name="Carol Clark",
                author_email="carol@example.org",
            )

            # Runner re-executes notebook.ipynb changing only outputs & execution_count.
            nb_v2 = {
                "cells": [
                    {"cell_type": "markdown", "metadata": {}, "source": ["# Notebook Title\n"]},
                    {
                        "cell_type": "code",
                        "execution_count": 2,
                        "metadata": {},
                        "outputs": [{"output_type": "stream", "text": ["new output\n", "more\n"]}],
                        "source": ["print('hello')\n"],
                    },
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            (repo / "content" / "notebook.ipynb").write_text(
                json.dumps(nb_v2, indent=2) + "\n", encoding="utf-8"
            )
            _git(repo, "add", "content/notebook.ipynb")
            _git(
                repo,
                "commit",
                "-m",
                "Re-execute notebook",
                author_name="Notebook Runner",
                author_email="runner@example.org",
            )

            data = build_contributors(repo)

            # Alphabetical on guide.md and mailmap canonicalized
            guide_names = [c["name"] for c in data["pages"]["content/guide.md"]["contributors"]]
            self.assertEqual(guide_names, ["Alice Anderson", "Bob Brown"])

            # Overwritten page: Bob has 0 surviving lines; Carol + human co-author Zoe appear; Copilot bot excluded
            overwritten_names = [
                c["name"] for c in data["pages"]["content/overwritten.md"]["contributors"]
            ]
            self.assertEqual(overwritten_names, ["Carol Clark", "Reviewer Zoe"])

            # Notebook: Runner changed only outputs/execution_count, so only Alice is credited
            nb_names = [c["name"] for c in data["pages"]["content/notebook.ipynb"]["contributors"]]
            self.assertEqual(nb_names, ["Alice Anderson"])

            # Dashboard ordering and profile links
            self.assertEqual(
                list(data["contributors"].keys()),
                ["alice-anderson", "bob-brown", "carol-clark", "reviewer-zoe"],
            )

            md_path = repo / "content" / "about" / "contributors.md"
            md_text = md_path.read_text(encoding="utf-8")
            self.assertIn("(contributor-alice-anderson)=", md_text)
            self.assertIn("[@alicegh](https://github.com/alicegh)", md_text)
            self.assertIn("[Institute of Neuroscience](https://ins.example.org)", md_text)
            self.assertIn("[User Guide](../guide.md)", md_text)
            self.assertIn("[Home](../../README.md)", md_text)

            # Calling again should be a no-op write (preserving mtime)
            os.utime(md_path, (1_700_000_000, 1_700_000_000))
            build_contributors(repo)
            self.assertEqual(int(md_path.stat().st_mtime), 1_700_000_000)

    def test_non_git_dir_degrades_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "_toc.yml").write_text("format: jb-book\nroot: README.md\n", encoding="utf-8")
            (tmp_path / "README.md").write_text("# Doc\n", encoding="utf-8")
            commits, idents, updated = blame_file(tmp_path, "README.md")
            self.assertEqual(commits, set())
            self.assertEqual(idents, [])
            self.assertEqual(updated, "")

            data = build_contributors(tmp_path)
            self.assertEqual(data["pages"], {})
            self.assertEqual(data["contributors"], {})
            self.assertTrue((tmp_path / "content" / "about" / "contributors.md").is_file())


if __name__ == "__main__":
    unittest.main()
