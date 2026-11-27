"""Tests for CI-safe content hashing and incremental build helpers."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import make  # noqa: E402
from tools.build_xeus_prefix import compute_env_hash  # noqa: E402


class TestBuildCacheHashing(unittest.TestCase):
    def test_build_xeus_prefix_hash_ignores_local_channel_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "local-channel" / "emscripten-wasm32"
            local_dir.mkdir(parents=True)
            pkg = local_dir / "tvb-gdist-2.9.2-0.conda"
            pkg.write_bytes(b"package-bytes-v1")

            env_file = tmp_path / "environment.ci.yml"
            env_file.write_text(
                f"name: xeus-kernel\nchannels:\n  - file://{tmp_path / 'local-channel'}\ndependencies:\n  - tvb-gdist\n",
                encoding="utf-8",
            )
            yaml_content = {
                "name": "xeus-kernel",
                "channels": [f"file://{tmp_path / 'local-channel'}"],
                "dependencies": ["tvb-gdist"],
            }

            h1 = compute_env_hash(env_file, yaml_content)
            os.utime(pkg, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
            h2 = compute_env_hash(env_file, yaml_content)
            self.assertEqual(h1, h2)

            pkg.write_bytes(b"package-bytes-v2")
            h3 = compute_env_hash(env_file, yaml_content)
            self.assertNotEqual(h1, h3)

    def test_make_hash_tree_uses_content_in_ci(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "sample.txt"
            target.write_text("hello", encoding="utf-8")

            with mock.patch.object(make, "ROOT", tmp_path), mock.patch.dict(os.environ, {"CI": "true"}):
                h1 = make._hash_tree(["sample.txt"])
                os.utime(target, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
                h2 = make._hash_tree(["sample.txt"])
                self.assertEqual(h1, h2)

                target.write_text("world", encoding="utf-8")
                h3 = make._hash_tree(["sample.txt"])
                self.assertNotEqual(h1, h3)

    def test_stage_lite_python_prefers_lite_python_when_no_venv(self) -> None:
        with (
            mock.patch.object(make, "venv_ready", return_value=False),
            mock.patch.object(make, "lite_python", return_value="/mock/build-env/bin/python"),
            mock.patch.object(make, "_python_has_module", return_value=True),
            mock.patch.object(make, "ensure_venv") as mock_ensure_venv,
        ):
            self.assertEqual(make._stage_lite_python(), "/mock/build-env/bin/python")
            mock_ensure_venv.assert_not_called()

    def test_lite_python_resolves_jupyter_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            jup = bin_dir / "jupyter"
            py = bin_dir / "python"
            jup.write_text("#!/bin/sh\n", encoding="utf-8")
            py.write_text("#!/bin/sh\n", encoding="utf-8")
            jup.chmod(0o755)
            py.chmod(0o755)

            with (
                mock.patch.object(make, "jupyter_cmd", return_value="jupyter"),
                mock.patch("shutil.which", return_value=str(jup)),
            ):
                self.assertEqual(make.lite_python(), str(py))

    def test_fp_exec_env_ignores_mtime_and_tracks_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "requirements").mkdir()
            (tmp_path / "content" / "_code").mkdir(parents=True)
            lock = tmp_path / "requirements" / "uv.lock"
            helper = tmp_path / "content" / "_code" / "helper.py"
            lock.write_text("pkg==1.0\n", encoding="utf-8")
            helper.write_text("x = 1\n", encoding="utf-8")

            with mock.patch.object(make, "ROOT", tmp_path):
                h1 = make.fp_exec_env()
                os.utime(helper, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
                self.assertEqual(h1, make.fp_exec_env())

                helper.write_text("x = 2\n", encoding="utf-8")
                self.assertNotEqual(h1, make.fp_exec_env())

    def test_exec_cache_hydrate_persist_and_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / "repo"
            cache_base = tmp_path / "shared-cache"
            (repo / "requirements").mkdir(parents=True)
            (repo / "content" / "_code").mkdir(parents=True)
            (repo / "requirements" / "uv.lock").write_text("pkg==1.0\n", encoding="utf-8")
            (repo / "content" / "_code" / "helper.py").write_text("x = 1\n", encoding="utf-8")
            exec_dir = repo / "_build" / "execute"
            exec_dir.mkdir(parents=True)
            nb = exec_dir / "abc123.ipynb"
            nb.write_text('{"cells": []}', encoding="utf-8")

            with (
                mock.patch.object(make, "ROOT", repo),
                mock.patch.object(make, "DRY_RUN", False),
                mock.patch.dict(os.environ, {"TVB_DOCS_EXEC_CACHE": str(cache_base)}),
            ):
                self.assertEqual(make.persist_exec_cache(), 1)
                nb.unlink()
                self.assertFalse(nb.exists())
                self.assertEqual(make.hydrate_exec_cache(), 1)
                self.assertTrue(nb.is_file())

            with (
                mock.patch.object(make, "ROOT", repo),
                mock.patch.dict(os.environ, {"TVB_DOCS_EXEC_CACHE": "off"}),
            ):
                self.assertIsNone(make.exec_cache_dir())

    def test_trajecturtle_installed_editable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "trajecturtle").mkdir()
            dist_info = repo / ".venv" / "lib" / "python3.12" / "site-packages" / "tvb_phaseplane-0.1.0.dist-info"
            dist_info.mkdir(parents=True)

            with mock.patch.object(make, "ROOT", repo):
                self.assertFalse(make._trajecturtle_installed_editable())

                direct_url = dist_info / "direct_url.json"
                direct_url.write_text(
                    json.dumps({"url": (repo / "trajecturtle").resolve().as_uri(), "dir_info": {"editable": True}}),
                    encoding="utf-8",
                )
                self.assertTrue(make._trajecturtle_installed_editable())

    def test_hash_tree_excludes_generated_contributors_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            about_dir = tmp_path / "content" / "about"
            about_dir.mkdir(parents=True)
            (about_dir / "about-this-site.md").write_text("# About\n", encoding="utf-8")
            gen = about_dir / "contributors.md"
            gen.write_text("# Contributors v1\n", encoding="utf-8")

            with mock.patch.object(make, "ROOT", tmp_path), mock.patch.dict(os.environ, {"CI": "true"}):
                h1 = make._hash_tree(["content"], exclude_content_generated=True)
                gen.write_text("# Contributors v2 with extra text\n", encoding="utf-8")
                h2 = make._hash_tree(["content"], exclude_content_generated=True)
                self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
