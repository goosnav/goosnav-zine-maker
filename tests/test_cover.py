import tempfile
import unittest
from pathlib import Path
from contextlib import closing

import pypdfium2 as pdfium
from PIL import Image, ImageDraw

from zinemaker.cover import edited_image, paint, placement, recipe, source_swatches
from zinemaker.export import publish
from zinemaker.project import Project


class CoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "cover.png"
        image = Image.new("RGB", (300, 200), "white")
        ImageDraw.Draw(image).rectangle((145, 0, 155, 199), fill="#181818")
        image.save(self.source)

    def fill(self, mode="bucket"):
        return dict(mode=mode, x=0.2, y=0.5, tolerance=0, color="#D33244")

    def test_bucket_is_connected_and_replace_is_global(self):
        for mode in ("bucket", "replace"):
            with Image.open(self.source) as image:
                paint(image, self.fill(mode))
                self.assertEqual(image.getpixel((50, 100)), (211, 50, 68))
                self.assertEqual(image.getpixel((150, 100)), (24, 24, 24))
                self.assertEqual(
                    image.getpixel((250, 100)),
                    (255, 255, 255) if mode == "bucket" else (211, 50, 68),
                )

    def test_tolerance_diagonal_and_wash(self):
        image = Image.new("RGB", (4, 2), "black")
        for xy, c in [((0, 0), 200), ((1, 0), 205), ((2, 1), 202)]:
            image.putpixel(xy, (c, c, c))
        paint(image, {**self.fill(), "x": 0, "y": 0, "tolerance": 3})
        self.assertEqual(image.getpixel((1, 0)), (211, 50, 68))
        self.assertEqual(image.getpixel((2, 1)), (202, 202, 202))
        design = recipe({"wash": 100})
        self.assertEqual(
            edited_image(self.source, design).getpixel((12, 100)), (250, 241, 219)
        )
        self.assertIn("#FFFFFF", source_swatches(self.source))

    def test_rotation_crop_geometry(self):
        item = {
            "size": [300, 200],
            "crop": [0.1, 0, 0.9, 1],
            "fit": "fill",
            "rotate": 90,
        }
        rect, box, margin = placement(
            item, recipe({"border": "solid", "width": 10}), (200, 100)
        )
        self.assertEqual(margin, 10)
        self.assertLess(abs(rect[0] - 10), 1)
        self.assertLess(abs(rect[1] - 10), 1)
        self.assertTrue(30 <= box[0] < box[2] <= 270)
        self.assertEqual((box[1], box[3]), (0, 200))

    def test_reopen_and_export_pdf_and_web_colors(self):
        before = self.source.read_bytes()
        p = Project(self.folder)
        item = p.data["items"][0]
        design = recipe(
            {
                "border": "double",
                "width": 10,
                "frame": "#00BB77",
                "stripe": "#111155",
                "fills": [self.fill()],
            }
        )
        p.update(
            "cover-design",
            {
                "id": item["id"],
                "project": p.data["id"],
                "revision": p.data["revision"],
                "design": design,
            },
        )
        p = Project(self.folder)
        self.assertEqual(p.data["items"][0]["cover_design"], design)
        out = publish(p, p.data)
        for name in ("print.pdf", "digital.pdf", "website/page-001.webp"):
            if name.endswith(".pdf"):
                with (
                    pdfium.PdfDocument(out / name) as doc,
                    closing(doc[0]) as page,
                    closing(page.render(scale=2)) as bm,
                ):
                    im = bm.to_pil().convert("RGB")
            else:
                with Image.open(out / name) as original:
                    im = original.convert("RGB")
            for x, y, wanted in [
                (0.5, 0.03, (0, 187, 119)),
                (0.5, 0.086, (17, 17, 85)),
                (0.3, 0.5, (211, 50, 68)),
                (0.7, 0.5, (255, 255, 255)),
            ]:
                actual = im.getpixel((int(im.width * x), int(im.height * y)))
                self.assertLess(
                    max(abs(a - b) for a, b in zip(actual, wanted)),
                    12,
                    (name, actual, wanted),
                )
        self.assertEqual(self.source.read_bytes(), before)

    def test_upload_reuses_front_cover_and_preserves_interior_page(self):
        source = self.source.rename(self.folder / "Winter.png")
        p = Project(self.folder)
        original = p.data["items"][0]["id"]

        def upload():
            return p.update(
                "upload",
                {
                    "project": p.data["id"],
                    "revision": p.data["revision"],
                    "name": source.name,
                    "path": source,
                    "role": "cover",
                },
            )

        cover = upload()
        self.assertEqual(cover, upload())
        self.assertNotEqual(cover, original)
        self.assertEqual(
            [(i["id"], i["role"]) for i in p.data["items"]],
            [(cover, "cover"), (original, "comic")],
        )

    def test_invalid_settings_do_not_save(self):
        p = Project(self.folder)
        before = p.manifest.read_bytes()
        with self.assertRaises(ValueError):
            p.update(
                "cover-design",
                {
                    "project": p.data["id"],
                    "revision": p.data["revision"],
                    "id": p.data["items"][0]["id"],
                    "design": {"frame": "bad"},
                },
            )
        self.assertEqual(p.manifest.read_bytes(), before)
