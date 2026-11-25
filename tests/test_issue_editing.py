import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw

from zinemaker.archive import open_project, save_project
from zinemaker.cover import edited_image, recipe
from zinemaker.layout import essay_pages, paginate, pdf
from zinemaker.panels import analyze, arrange_group, comic_pages
from zinemaker.project import Project


def frames(count):
    cols = min(5, count)
    rows = (count + cols - 1) // cols
    image = Image.new("RGB", (cols * 135 + 72, rows * 118 + 112), "white")
    pen = ImageDraw.Draw(image)
    for i in range(count):
        x, y = 36 + i % cols * 135, 56 + i // cols * 118
        pen.rectangle((x, y, x + 120, y + 100), outline="black", width=3)
        pen.ellipse((x + 31, y + 20, x + 60, y + 65), outline="black", width=2)
    pen.line((10, 15, 22, 15), fill="black", width=2)
    return image


class EditingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_one_to_ten_frames_and_group_order(self):
        for count in range(1, 11):
            with self.subTest(count=count):
                image = frames(count)
                boxes, crop = analyze(image)
                self.assertEqual(len(boxes), count)
                self.assertGreater(crop[1] * image.height, 15)
                item = dict(
                    panels=boxes,
                    size=image.size,
                    layout="4",
                    crop=None,
                    fit="contain",
                    rotate=0,
                )
                pages = comic_pages({"width": 9, "height": 6}, item)
                self.assertEqual([box for p in pages for box in p["group"]], boxes)
                for page in pages:
                    for _, (x, y, w, h) in arrange_group(
                        page["group"], image.size, (648, 432)
                    ):
                        self.assertTrue(0 <= x < x + w <= 648 and 0 <= y < y + h <= 432)

    def test_legacy_issue_manual_crop_and_spread_alignment(self):
        image = Image.new("RGB", (600, 200), "#cf2831")
        ImageDraw.Draw(image).rectangle((300, 0, 599, 199), fill="#146AC0")
        image.save(self.root / "strip.png")
        p = Project(self.root)
        item = p.data["items"][0]
        del item["panels"]
        item["crop"] = [0, 0, 1, 1]
        p.data["cover"] = False
        p.save()
        p = Project(p.root)
        item = p.data["items"][0]
        self.assertEqual(item["crop"], [0, 0, 1, 1])
        item["layout"] = "spread"
        pages = paginate(p.data)
        self.assertEqual([p["kind"] for p in pages], ["alignment", "comic", "comic"])
        out = io.BytesIO()
        pdf(out, p, p.data, pages, 145)
        with pdfium.PdfDocument(out.getvalue()) as doc:
            for i, color in [(1, (207, 40, 49)), (2, (20, 106, 192))]:
                im = doc[i].render().to_pil().convert("RGB")
                actual = im.getpixel((im.width // 2, im.height // 2))
                self.assertLess(max(abs(a - b) for a, b in zip(actual, color)), 5)

    def test_essay_reflow_preserves_words_and_image_clearance(self):
        body = ("A    story for the first line.\n\nThe editor returns. " * 80).strip()
        item = dict(
            title="An Update",
            role="essay",
            body=body,
            illustration="drawing",
            image_height=45,
        )
        for size in (8, 12, 18, 24):
            for side in ("left", "right"):
                pages = essay_pages(
                    {"width": 9, "height": 6},
                    {**item, "font_size": size, "image_side": side},
                )
                self.assertEqual(
                    " ".join(line for p in pages for line in p["lines"]).split(),
                    body.split(),
                )
                first = pages[0]
                x, y, w, h = first["illustration"]
                for left, base in first["positions"]:
                    if x <= left < x + w:
                        self.assertGreater(base, y + h)
                self.assertTrue(
                    all(
                        p["illustration"] is None and not p["initial"]
                        for p in pages[1:]
                    )
                )

    def test_palette_distance_dither_and_brush(self):
        path = self.root / "art.png"
        art = Image.new("RGB", (51, 30), "#A93343")
        art.save(path)
        palette = ["#AA3044", "#151515", "#EFE0DB", "#EECCAA"]
        for name in ("palette", "dither"):
            out = edited_image(path, recipe({"filter": name, "palette": palette}))
            colors = {
                out.getpixel((x, y))
                for x in range(out.width)
                for y in range(out.height)
            }
            self.assertTrue(colors <= set(tuple(bytes.fromhex(c[1:])) for c in palette))
            if name == "palette":
                self.assertEqual(colors, {(170, 48, 68)})
        op = {
            "mode": "brush",
            "width": 8,
            "points": [[0.1, 0.5], [0.9, 0.5]],
            "color": "#00FFFF",
        }
        out = edited_image(path, recipe({"fills": [op]}))
        self.assertEqual(out.getpixel((25, 15)), (0, 255, 255))
        self.assertEqual(out.getpixel((25, 3)), (169, 51, 67))

    def test_archive_recovery_and_duplicate_text_import(self):
        (self.root / "essay.txt").write_text("A letter to the reader.")
        (self.root / "essay-copy.md").write_text("A letter to the reader.\n")
        p = Project(self.root)
        self.assertEqual(len(p.data["items"]), 1)
        path = self.root / "drawing.png"
        frames(3).save(path)
        ref, _ = p.store_image(path, ".png")
        essay = p.data["items"][0]
        p.edit("item", {**essay, "illustration": ref.name, "font_size": 14})
        p.save()
        archive = save_project(p, p.data)
        before = p.manifest.read_bytes()
        restored = open_project(archive)
        self.assertNotEqual(restored.root, p.root)
        self.assertEqual(restored.data["items"], p.data["items"])
        self.assertEqual(
            restored.asset({"asset": ref.name}).read_bytes(), path.read_bytes()
        )
        bad = self.root / "broken.gsnvzine"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(bad, "w") as dest:
            for name in source.namelist():
                dest.writestr(
                    name, b"broken" if name.startswith("assets/") else source.read(name)
                )
        with self.assertRaisesRegex(ValueError, "damaged"):
            open_project(bad)
        self.assertEqual(p.manifest.read_bytes(), before)
        self.assertFalse(list(self.root.glob("broken - *")))
