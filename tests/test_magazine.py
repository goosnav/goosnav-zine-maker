import tempfile
import unittest
from pathlib import Path
from contextlib import closing

from PIL import Image, ImageDraw
import pypdfium2 as pdfium

from zinemaker.export import publish
from zinemaker.images import auto_crop
from zinemaker.layout import paginate, preview
from zinemaker.project import Conflict, FOLDER, Project


class MagazineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.source = self.base / "Comics"
        self.source.mkdir()

    def art(self, name):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        im = Image.new("RGB", (800, 550), "white")
        draw = ImageDraw.Draw(im)
        for x in (75, 300, 525):
            draw.rectangle((x, 175, x + 200, 365), outline="black", width=4)
            draw.ellipse((x + 45, 205, x + 125, 310), outline="black", width=3)
        draw.line((387, 55, 415, 55), fill="black", width=4)
        draw.line((400, 42, 400, 68), fill="black", width=4)
        im.save(path)
        return path

    def edit(self, p, action, **values):
        p.update(
            action, {"revision": p.data["revision"], "project": p.data["id"], **values}
        )

    def test_empty_and_art_only(self):
        p = Project(self.source)
        self.assertEqual(paginate(p.data), [])
        with self.assertRaisesRegex(ValueError, "Add artwork"):
            publish(p, p.data)
        self.art("comic10.png")
        self.art("comic2.png")
        self.edit(p, "scan")
        self.assertEqual(
            [i["name"] for i in p.data["items"]], ["comic2.png", "comic10.png"]
        )
        self.assertEqual(
            [pg["kind"] for pg in paginate(p.data)], ["generated", "comic", "comic"]
        )
        self.edit(p, "remove", id=p.data["items"][0]["id"])
        self.edit(p, "scan")
        self.assertEqual(len(p.data["items"]), 1)
        self.assertTrue((self.source / "comic2.png").exists())

    def test_trim_leaves_panels_and_excludes_registration(self):
        with Image.open(self.art("scan.png")) as im:
            x, y, r, b = auto_crop(im)
        self.assertLess(x, 75 / 800)
        self.assertGreater(r, 725 / 800)
        self.assertGreater(y, 0.16)
        self.assertLess(y, 175 / 550)
        self.assertGreater(b, 365 / 550)
        self.assertEqual(auto_crop(Image.new("RGB", (80, 60), "black")), [0, 0, 1, 1])

    def test_destination_reopen_conflict_and_frozen_art(self):
        original = self.art("comic.png")
        out = self.base / "Delivery"
        p = Project(self.source, out)
        i = p.data["items"][0]
        revision = p.data["revision"]
        self.edit(
            p,
            "item",
            id=i["id"],
            role="comic",
            title="Retitled",
            fit="fill",
            crop=[0.1, 0.2, 0.9, 0.8],
            rotate=90,
        )
        with self.assertRaises(Conflict):
            p.update("scan", {"revision": revision, "project": p.data["id"]})
        self.assertFalse((self.source / FOLDER).exists())
        p = Project(out / FOLDER)
        self.assertEqual(p.source, self.source)
        self.assertEqual(p.data["items"][0]["rotate"], 90)
        original.unlink()
        self.assertGreater(len(preview(p, p.data, paginate(p.data)[1], 1)), 500)
        elsewhere = self.base / "Other"
        elsewhere.mkdir()
        with self.assertRaisesRegex(ValueError, "another issue"):
            Project(elsewhere, out)

    def test_optional_roles_pagination_and_print_size(self):
        for name in [
            "comics/10.png",
            "comics/2.png",
            "ads/spread.png",
            "cover.png",
            "back-cover.png",
        ]:
            self.art(name)
        body = "\n\n".join("A comic essay about paper and ink. " * 6 for _ in range(24))
        (self.source / "Editorial.txt").write_text(body)
        (self.source / "damaged.png").write_bytes(b"broken")
        p = Project(self.source)
        self.assertTrue(p.warnings)
        self.assertEqual(
            [i["role"] for i in p.data["items"]],
            ["cover", "essay", "comic", "ad", "comic", "back"],
        )
        self.edit(
            p,
            "settings",
            width=6,
            height=9,
            title="New & bright",
            cover=True,
            numbers=False,
            style="ruled",
        )
        pages = paginate(p.data)
        essays = [pg for pg in pages if pg["kind"] == "essay"]
        self.assertGreater(len(essays), 1)
        self.assertEqual(
            " ".join(" ".join(pg["lines"]) for pg in essays).split(), body.split()
        )
        export = publish(p, p.data)
        for filename in ("print.pdf", "digital.pdf"):
            with pdfium.PdfDocument(export / filename) as doc, closing(doc[0]) as first:
                self.assertEqual(len(doc), len(pages))
                self.assertEqual(first.get_size(), (432, 648))
        site = export / "website"
        self.assertEqual(len(list(site.glob("page-*.webp"))), len(pages))
        self.assertIn("New &amp; bright", (site / "index.html").read_text())
        self.assertNotIn(str(self.source), (site / "index.html").read_text())
        self.assertNotIn("generated", [pg["kind"] for pg in pages])

    def test_comic_maker_pairs_and_incremental_reopen(self):
        self.art("all-book-prints/Morning--comic.png")
        self.art("all-book-prints/Morning--comic.tif")
        p = Project(self.source)
        self.assertEqual(len(p.data["items"]), 1)
        self.art("all-book-prints/Evening--comic.tif")
        self.assertEqual(len(Project(self.source).data["items"]), 2)
        self.assertEqual(len(Project(self.source).data["items"]), 2)

    def test_cancelled_export_leaves_no_partial_edition(self):
        self.art("First.png")
        p = Project(self.source)

        def stop(phase, current, total):
            if phase == "Digital PDF":
                raise ValueError("Cancelled")

        with self.assertRaisesRegex(ValueError, "Cancelled"):
            publish(p, p.data, stop)
        self.assertEqual(list((p.root / "exports").iterdir()), [])
        self.assertTrue(p.manifest.is_file())

    def test_rejected_edit_preserves_saved_issue(self):
        self.art("comic.jpg")
        p = Project(self.source)
        i = p.data["items"][0]
        saved = p.manifest.read_bytes()
        with self.assertRaises(ValueError):
            self.edit(
                p,
                "item",
                id=i["id"],
                title="New title",
                role="comic",
                fit="fill",
                crop=[2, 0, 1, 1],
                rotate=0,
            )
        self.assertEqual(saved, p.manifest.read_bytes())
        with self.assertRaises(ValueError):
            self.edit(
                p,
                "settings",
                width=0,
                height=11,
                title="Other",
                cover=True,
                numbers=False,
                style="plain",
            )
        self.assertEqual(saved, p.manifest.read_bytes())


if __name__ == "__main__":
    unittest.main()
