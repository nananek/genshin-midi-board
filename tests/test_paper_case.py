from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GENERATOR = ROOT / "hardware" / "rp2040_frisk" / "scripts" / "gen_paper_case.py"
PDF = ROOT / "docs" / "paper_case_a4.pdf"
SVG = ROOT / "docs" / "paper_case_a4.svg"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_paper_case", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the class module through sys.modules
    sys.modules["gen_paper_case"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gen = _load_generator()
DESIGN = yaml.safe_load(
    (ROOT / "hardware" / "rp2040_frisk" / "design.yaml").read_text(encoding="utf-8"))
CASE = gen.build_case(gen.read_design())


class BoundsCanvas:
    """Record the drawing extents and text boxes without writing a file."""

    def __init__(self) -> None:
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.texts: list[tuple[str, float, float, float, float]] = []

    def _point(self, x: float, y: float) -> None:
        self.xs.append(x)
        self.ys.append(y)

    def line(self, x1, y1, x2, y2, *a, **k) -> None:
        self._point(x1, y1)
        self._point(x2, y2)

    def rect(self, x, y, w, h, *a, **k) -> None:
        self._point(x, y)
        self._point(x + w, y + h)

    def polyline(self, pts, *a, **k) -> None:
        for x, y in pts:
            self._point(x, y)

    def polygon(self, pts, *a, **k) -> None:
        self.polyline(pts)

    def circle(self, cx, cy, r, *a, **k) -> None:
        self._point(cx - r, cy - r)
        self._point(cx + r, cy + r)

    def fill(self, pts, *a, **k) -> None:
        self.polyline(pts)

    def text(self, s, x, y, size=3.0, angle=0.0) -> None:
        width = gen.text_width(s, size)
        if angle:
            self.texts.append((s, x - 0.75 * size, y, 0.75 * size, width))
            self._point(x - 0.75 * size, y)
            self._point(x, y + width)
        else:
            self.texts.append((s, x, y - 0.75 * size, width, 1.0 * size))
            self._point(x, y - 0.75 * size)
            self._point(x + width, y + 0.25 * size)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return min(self.xs), min(self.ys), max(self.xs), max(self.ys)


def _overlap(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    return max(0.0, w) * max(0.0, h)


class CaseGeometryTests(unittest.TestCase):
    def test_stdlib_yaml_reader_matches_pyyaml(self) -> None:
        self.assertEqual(gen.read_design(), DESIGN)

    def test_inner_size_follows_the_board(self) -> None:
        self.assertAlmostEqual(CASE.w, 63.0, places=6)
        self.assertAlmostEqual(CASE.d, 36.0, places=6)
        self.assertAlmostEqual(CASE.h, 9.0, places=6)
        self.assertAlmostEqual(CASE.board_w, 62.0, places=6)
        self.assertAlmostEqual(CASE.board_h, 35.0, places=6)
        self.assertAlmostEqual(CASE.spec.clearance, 0.5, places=6)

    def test_geometry_has_no_errors(self) -> None:
        self.assertEqual(gen.validate(CASE), [])

    def test_connectors_are_on_the_long_walls(self) -> None:
        openings = {o.ref: o for o in CASE.openings}
        self.assertEqual(openings["J1"].wall, "back")
        self.assertEqual(openings["J3"].wall, "back")
        self.assertEqual(openings["J2"].wall, "front")
        # board x -> net x is a 0.5 mm shift, never a mirror
        self.assertAlmostEqual(openings["J1"].along, 17.0, places=6)
        self.assertAlmostEqual(openings["J3"].along, 46.0, places=6)
        self.assertAlmostEqual(openings["J2"].along, 31.5, places=6)
        for ref in ("J1", "J3"):
            self.assertGreaterEqual(openings[ref].length, 14.0)
            self.assertGreaterEqual(openings[ref].height, 4.5)

    def test_switches_sit_on_the_wall_their_lever_faces(self) -> None:
        openings = {o.ref: o for o in CASE.openings}
        self.assertEqual(openings["SW1"].wall, "left")
        self.assertEqual(openings["SW2"].wall, "left")
        self.assertEqual(openings["SW3"].wall, "right")
        self.assertEqual(openings["SW4"].wall, "front")
        self.assertEqual(openings["SW6"].wall, "back")
        # left/right walls run back to front: net y = 35.5 - board y
        self.assertAlmostEqual(openings["SW1"].along, 26.5, places=6)
        self.assertAlmostEqual(openings["SW2"].along, 11.0, places=6)
        self.assertAlmostEqual(openings["SW3"].along, 23.0, places=6)
        self.assertAlmostEqual(openings["SW4"].along, 15.5, places=6)

    def test_led_and_reset_press_through_the_lid(self) -> None:
        holes = {h.ref: h for h in CASE.holes}
        self.assertEqual(holes["LED1"].diameter, 3.0)
        self.assertEqual(holes["SW6"].diameter, 5.0)
        led = next(p for p in DESIGN["placements"] if p["ref"] == "LED1")
        self.assertAlmostEqual(holes["LED1"].center[0], led["x_mm"] + 0.5, places=6)
        self.assertAlmostEqual(holes["SW6"].center[0], 31.5, places=6)
        hinge = CASE.d + CASE.h
        for hole in CASE.holes:
            self.assertGreater(hole.center[1], hinge + 2.0,
                               "lid hole must clear the hinge")

    def test_openings_stay_clear_of_the_glue_tabs(self) -> None:
        # The four corner tabs are 7 mm deep and glue to the inside of the
        # front/back walls; an opening at x<7 or x>56 would be covered.
        for opening in CASE.openings:
            if opening.wall not in ("front", "back"):
                continue
            x, _, w, _ = opening.rect
            if opening.wall == "front" and opening.ref in ("J2", "SW4"):
                continue
            self.assertGreaterEqual(x, 7.0, opening.ref)
            self.assertLessEqual(x + w, CASE.w - 7.0, opening.ref)

    def test_tuck_hardware_is_consistent(self) -> None:
        s = CASE.spec
        self.assertGreater(s.tuck_d, s.slit_drop + s.slit_h / 2.0)
        self.assertGreaterEqual(s.lip_d, s.tuck_d)
        self.assertGreater(s.tuck_w, s.slit_len)
        self.assertLessEqual(s.tuck_w - s.slit_len, 3.0)
        self.assertGreaterEqual(s.lip_w, s.slit_len + 2.0)
        self.assertGreaterEqual(s.lip_x, s.tab_d + 0.5)
        self.assertLessEqual(s.lip_x + s.lip_w, CASE.w - s.tab_d - 0.5)
        # tongue and slit share a centre line
        self.assertAlmostEqual(s.tuck_x + s.tuck_w / 2.0,
                               s.slit_x + s.slit_len / 2.0, places=6)

    def test_lid_holes_do_not_overlap(self) -> None:
        a, b = CASE.holes
        gap = ((a.center[0] - b.center[0]) ** 2
               + (a.center[1] - b.center[1]) ** 2) ** 0.5
        self.assertGreaterEqual(gap, (a.diameter + b.diameter) / 2.0 + 1.0)


class SheetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.canvas = BoundsCanvas()
        gen.draw_sheet(self.canvas, CASE)

    def test_everything_fits_on_a4(self) -> None:
        x0, y0, x1, y1 = self.canvas.bbox
        self.assertGreaterEqual(x0, 6.0)
        self.assertGreaterEqual(y0, 6.0)
        self.assertLessEqual(x1, gen.A4_W - 6.0)
        self.assertLessEqual(y1, gen.A4_H - 6.0)

    def test_text_does_not_collide(self) -> None:
        for i, a in enumerate(self.canvas.texts):
            for b in self.canvas.texts[i + 1:]:
                self.assertLess(_overlap(a[1:], b[1:]), 1.0,
                                "%r overlaps %r" % (a[0], b[0]))

    def test_scale_bar_is_100_mm(self) -> None:
        svg = gen.render_svg(CASE)
        ops = "\n".join(svg.ops)
        self.assertIn('x1="15.000" y1="189.000" x2="115.000" y2="189.000"', ops)
        self.assertIn(">100<", ops)


class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "case.pdf"
        gen.render_pdf(CASE).save(cls.path)
        cls.data = cls.path.read_bytes()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_page_is_a4_landscape(self) -> None:
        box = self.data.split(b"/MediaBox [0 0 ")[1].split(b"]")[0].split()
        width, height = float(box[0]), float(box[1])
        self.assertAlmostEqual(width, 297.0 * gen.MM, delta=0.01)
        self.assertAlmostEqual(height, 210.0 * gen.MM, delta=0.01)
        self.assertIn(b"/Count 1", self.data)

    def test_user_space_is_one_millimetre(self) -> None:
        self.assertIn(("%s 0 0 %s 0 0 cm" % (gen._num(gen.MM), gen._num(gen.MM)))
                      .encode("ascii"), self.data)

    def test_scale_bar_line_is_in_the_stream(self) -> None:
        self.assertIn(b"15 21 m 115 21 l S", self.data)
        # 1 mm ticks at both ends
        self.assertIn(b"15 21 m 15 24.2 l", self.data)
        self.assertIn(b"115 21 m 115 24.2 l", self.data)
        self.assertIn(b"100", self.data)

    def test_committed_pdf_is_current(self) -> None:
        self.assertTrue(PDF.exists(), "docs/paper_case_a4.pdf is missing")
        self.assertEqual(PDF.read_bytes(), self.data,
                         "docs/paper_case_a4.pdf is stale; run the generator")

    def test_svg_preview_is_one_to_one(self) -> None:
        self.assertTrue(SVG.exists(), "docs/paper_case_a4.svg is missing")
        head = SVG.read_text(encoding="utf-8")[:400]
        self.assertIn('width="297mm"', head)
        self.assertIn('height="210mm"', head)
        self.assertIn('viewBox="0 0 297 210"', head)


if __name__ == "__main__":
    unittest.main()
