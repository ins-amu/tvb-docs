"""Tests for CI-safe content hashing and incremental build helpers."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
