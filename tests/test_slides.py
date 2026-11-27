"""Integration checks for the tutorial slide exports."""

import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import make  # noqa: E402


@unittest.skipUnless(shutil.which("pandoc") and shutil.which("pdflatex"),
                     "Pandoc and pdflatex are required")
class TestSlideExports(unittest.TestCase):
    def test_formats_and_presenter_notes(self):
        source = (ROOT / "slides" / "tvb-tutorial.md").read_text(encoding="utf-8")
        notes = re.findall(r"::: notes\s*\n(.*?)\n:::", source, re.DOTALL)
        self.assertTrue(notes)
        self.assertEqual(len(notes), len(re.findall(r"^# ", source, re.MULTILINE)))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "slides").mkdir()
            (root / "slides" / "tvb-tutorial.md").write_text(source, encoding="utf-8")
            with mock.patch.object(make, "ROOT", root), mock.patch.object(make, "DRY_RUN", False):
                make.task_slides()

            output = root / "_build" / "slides"
            html = (output / "tvb-tutorial.html").read_text(encoding="utf-8")
            self.assertEqual(html.count('<aside class="notes">'), len(notes))
            self.assertIn("RevealNotes", html)
            self.assertTrue((output / "tvb-tutorial.pdf").read_bytes().startswith(b"%PDF-"))
            with zipfile.ZipFile(output / "tvb-tutorial.pptx") as pptx:
                note_files = [name for name in pptx.namelist()
                              if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", name)]
                self.assertEqual(len(note_files), len(notes))
                for index, note in enumerate(notes, 1):
                    name = f"ppt/notesSlides/notesSlide{index}.xml"
                    note_text = " ".join(ElementTree.fromstring(pptx.read(name)).itertext())
                    self.assertIn(" ".join(note.split()), note_text.replace("’", "'"))


if __name__ == "__main__":
    unittest.main()
