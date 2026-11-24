import html
from contextlib import closing
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pypdfium2 as pdfium
from .layout import PDF_LOCK, paginate, pdf, raster_page


def publish(project, issue, report=None):
    pages = paginate(issue)
    if not pages:
        raise ValueError("Add artwork or an essay before exporting.")

    def progress(phase, index):
        if report:
            report(phase, index + 1, len(pages))

    exports = project.root / "exports"
    if exports.is_symlink():
        raise ValueError("Choose a regular export folder.")
    exports.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".building-", dir=exports))
    try:
        with PDF_LOCK:
            pdf(
                str(stage / "print.pdf"),
                project,
                issue,
                pages,
                300,
                on_page=lambda index: progress("Print PDF", index),
            )
            pdf(
                str(stage / "digital.pdf"),
                project,
                issue,
                pages,
                145,
                on_page=lambda index: progress("Digital PDF", index),
            )
        web = stage / "website"
        web.mkdir()
        figures = []
        with PDF_LOCK, pdfium.PdfDocument(stage / "digital.pdf") as doc:
            for idx, info in enumerate(pages):
                progress("Web edition", idx)
                with closing(doc[idx]) as page:
                    im = raster_page(
                        page,
                        min(2200, round(max(issue["width"], issue["height"]) * 145)),
                    )
                name = f"page-{idx + 1:03}.webp"
                im.save(web / name, quality=90, method=4)
                label = (
                    issue["title"]
                    if info["kind"] == "generated"
                    else info["item"]["title"]
                )
                alt = html.escape(f"Page {idx + 1} — {label}", quote=True)
                text = ""
                if info["kind"] == "essay":
                    text = (
                        "<details><summary>Read text</summary><p>"
                        + html.escape(" ".join(info["header"] + info["lines"]))
                        + "</p></details>"
                    )
                figures.append(
                    f'<figure id="p{idx + 1}"><img width="{im.width}" height="{im.height}" src="{name}" alt="{alt}" loading="{"eager" if idx == 0 else "lazy"}">{text}<figcaption>{idx + 1} / {len(pages)}</figcaption></figure>'
                )
        name = html.escape(issue["title"])
        (web / "index.html").write_text(
            f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{name}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#eeece6;color:#282924;font:16px system-ui}}header,main{{max-width:1040px;margin:auto;padding:16px}}h1{{font: bold clamp(22px,4vw,40px) Georgia;margin:.3em 0}}figure{{margin:0 0 28px}}img{{display:block;width:100%;height:auto;box-shadow:0 1px 5px #0004}}figcaption{{text-align:center;font-size:13px;margin:.5em}}p{{line-height:1.6;max-width:65ch}}summary{{cursor:pointer}}</style>
<header><h1>{name}</h1></header><main>{"".join(figures)}</main></html>""",
            encoding="utf-8",
        )
        run = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "-" + uuid.uuid4().hex[:6]
        result = exports / run
        progress("Finishing", len(pages) - 1)
        stage.rename(result)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)
