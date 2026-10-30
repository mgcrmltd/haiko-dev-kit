"""diagram.py writes a valid draw.io file: a tab per diagram, every edge joined to shapes that exist, the same every time."""

import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import diagram  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent.parent / "examples" / "empirical-college"


def draw(folder: Path = EXAMPLE) -> tuple[str, ET.Element]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "app.drawio"
        diagram.main(["--app", str(folder), "--metadata", str(Path(tmp) / "none"), "--out", str(out)])
        text = out.read_text(encoding="utf-8")
    return text, ET.fromstring(text)


class DrawioFile(unittest.TestCase):
    def test_valid_drawio_with_a_tab_per_diagram(self):
        _, root = draw()
        self.assertEqual(root.tag, "mxfile")
        pages = root.findall("diagram")
        self.assertGreaterEqual(len(pages), 1)
        self.assertEqual(pages[0].get("name"), "Overview")
        self.assertEqual(len({p.get("name") for p in pages}), len(pages), "tab names are unique")

    def test_every_edge_joins_two_shapes_and_ids_are_unique(self):
        _, root = draw()
        for page in root.findall("diagram"):
            cells = page.findall("./mxGraphModel/root/mxCell")
            ids = [c.get("id") for c in cells]
            self.assertEqual(len(ids), len(set(ids)), page.get("name"))
            vertices = {c.get("id") for c in cells if c.get("vertex") == "1"}
            for e in (c for c in cells if c.get("edge") == "1"):
                self.assertIn(e.get("source"), vertices, f"{page.get('name')}: {e.get('id')}")
                self.assertIn(e.get("target"), vertices, f"{page.get('name')}: {e.get('id')}")

    def test_the_same_app_draws_the_same_file(self):
        self.assertEqual(draw()[0], draw()[0])

    def test_a_snapshot_draws_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snap.json"
            snap.write_text(json.dumps({"haikoSnapshot": True, "definition": json.loads((EXAMPLE / "app-definition.json").read_text()),
                                        "securityManifest": json.loads((EXAMPLE / "security-manifest.json").read_text())}))
            out = Path(tmp) / "s.drawio"
            diagram.main(["--snapshot", str(snap), "--out", str(out)])
            self.assertEqual(ET.parse(out).getroot().find("diagram").get("name"), "Overview")


if __name__ == "__main__":
    unittest.main()
