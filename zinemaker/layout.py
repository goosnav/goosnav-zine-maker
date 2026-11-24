"""Pagination and drawing use physical points for the editor and both editions."""

import io
from contextlib import closing
import math
import threading
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import simpleSplit

from .images import open_image, region

ART = Path(__file__).with_name("art")
PDF_LOCK = threading.RLock()  # PDFium is process-global and not thread safe.
PAPER = (0.981, 0.969, 0.926)
INK = (0.105, 0.105, 0.093)
VERMILION = (0.68, 0.17, 0.10)


def dimensions(issue):
    return issue["width"] * 72, issue["height"] * 72


def wrap(text, face, size, width):
    lines = []
    for paragraph in text.expandtabs(4).split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        for line in simpleSplit(paragraph, face, size, width):
            if stringWidth(line, face, size) <= width:
                lines.append(line)
                continue
            part, length = "", 0
            for char in line:
                advance = stringWidth(char, face, size)
                if part and advance + length > width:
                    lines.append(part)
                    part, length = "", 0
                part += char
                length += advance
            lines.append(part)
    return lines


def essay_pages(issue, item):
    w, h = dimensions(issue)
    pad = max(17, min(w, h) * 0.085)
    cols = 2 if w >= 470 and w / h > 1.08 else 1
    gap = 18
    width = (w - 2 * pad - gap * (cols - 1)) / cols
    size = max(9, min(12, min(w, h) * 0.029))
    leading = size * 1.38
    heading = min(25, w * 0.06)
    titles = wrap(item["title"], "Times-Bold", heading, w - 2 * pad)
    # Keep even very long titles above the first column on small trim sizes.
    while len(titles) * heading * 1.12 > h * 0.33 and heading > 9:
        heading -= 1
        titles = wrap(item["title"], "Times-Bold", heading, w - 2 * pad)
    lines = wrap(item["body"], "Times-Roman", size, width)
    pages, offset = [], 0
    while offset < len(lines):
        header = titles if not pages else []
        top = h - pad - len(header) * heading * 1.12 - (14 if header else 0)
        rows = max(1, math.floor((top - pad) / leading))
        end = offset + rows * cols
        pages.append(
            dict(
                item=item,
                kind="essay",
                part=len(pages) + 1,
                heading=heading,
                header=header,
                top=top,
                pad=pad,
                size=size,
                leading=leading,
                gap=gap,
                width=width,
                rows=rows,
                lines=lines[offset:end],
            )
        )
        offset = end
    return pages


def paginate(issue):
    items = issue["items"]
    pages = []
    if items and issue["cover"] and not any(i["role"] == "cover" for i in items):
        art = next((i for i in items if i["role"] == "comic"), None)
        pages.append({"kind": "generated", "item": art})
    for item in items:
        if item["role"] == "essay":
            pages.extend(essay_pages(issue, item))
        else:
            pages.append({"kind": item["role"], "item": item})
    return pages


def draw_art(c, project, item, box, dpi, full=False):
    x, y, w, h = box
    im = open_image(project.asset(item))
    crop = item["crop"]
    if crop is None:
        crop = [0, 0, 1, 1] if full or item["fit"] == "original" else item["auto"]
    im = region(im, crop)
    if item["rotate"]:
        im = im.transpose(
            {
                90: Image.Transpose.ROTATE_270,
                180: Image.Transpose.ROTATE_180,
                270: Image.Transpose.ROTATE_90,
            }[item["rotate"]]
        )
    if item["fit"] == "fill":
        # Crop before resampling so small source images are never upscaled here.
        ratio = w / h
        cw, ch = (
            min(im.width, max(1, round(im.height * ratio))),
            min(im.height, max(1, round(im.width / ratio))),
        )
        left, top = (im.width - cw) // 2, (im.height - ch) // 2
        im = im.crop((left, top, left + cw, top + ch))
    scale = min(w / im.width, h / im.height)
    dw, dh = im.width * scale, im.height * scale
    im.thumbnail(
        (max(1, round(dw * dpi / 72)), max(1, round(dh * dpi / 72))),
        Image.Resampling.LANCZOS,
    )
    if dpi <= 160:
        encoded = io.BytesIO()
        im.save(encoded, "JPEG", quality=91, subsampling=0)
        encoded.seek(0)
        reader = ImageReader(encoded)
    else:
        reader = ImageReader(im)
    c.drawImage(reader, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh)


def comic_frame(c, w, h, style, index):
    m = min(w, h) * 0.035
    if style == "plain":
        return
    c.setLineWidth(0.65)
    c.rect(m, m, w - 2 * m, h - 2 * m)
    if style != "ornamental":
        return
    side = min(w, h) * 0.15
    filename = ART / f"corner-{(1, 3, 5)[index % 3]}.png"
    with Image.open(filename) as corner:
        for flipx, flipy in [
            (False, False),
            (True, False),
            (True, True),
            (False, True),
        ]:
            tile = ImageOps.mirror(corner) if flipx else corner
            tile = ImageOps.flip(tile) if flipy else tile
            c.drawImage(
                ImageReader(tile),
                w - m - side - 2 if flipx else m + 2,
                m + 2 if flipy else h - m - side - 2,
                side,
                side,
            )


def draw(c, project, issue, page, index, dpi):
    w, h = dimensions(issue)
    m = min(w, h) * 0.08
    kind, item = page["kind"], page["item"]
    c.setFillColorRGB(*INK)
    if kind == "generated":
        c.setFillColorRGB(*PAPER)
        c.rect(0, 0, w, h, fill=1, stroke=0)
        c.setFillColorRGB(*INK)
        c.setFont("Helvetica-Bold", min(11, w * 0.023))
        c.drawString(m, h - m, "GOOSNAV   /   ZINE")
        size = min(55, w * 0.093, h * 0.135)
        lines = wrap(issue["title"], "Times-Bold", size, w - 2 * m)
        while len(lines) * size > h * 0.34 and size > 9:
            size -= 1
            lines = wrap(issue["title"], "Times-Bold", size, w - 2 * m)
        top = h - m - 8
        for line in lines:
            top -= size
            c.setFont("Times-Bold", size)
            c.drawString(m, top, line)
        top -= m * 0.45
        c.setStrokeColorRGB(*VERMILION)
        c.setLineWidth(2)
        c.line(m, top, w - m, top)
        if item:
            draw_art(c, project, item, (m, m * 1.45, w - 2 * m, top - m * 1.95), dpi)
        c.setLineWidth(0.6)
        c.line(m, m, w - m, m)
    elif kind == "essay":
        p = page
        y = h - p["pad"]
        c.setFont("Times-Bold", p["heading"])
        for line in p["header"]:
            y -= p["heading"] * 1.12
            c.drawString(p["pad"], y, line)
        if p["header"]:
            c.setLineWidth(0.55)
            c.line(p["pad"], y - 5, w - p["pad"], y - 5)
        c.setFont("Times-Roman", p["size"])
        for n, line in enumerate(p["lines"]):
            column, row = divmod(n, p["rows"])
            c.drawString(
                p["pad"] + column * (p["width"] + p["gap"]),
                p["top"] - (row + 1) * p["leading"],
                line,
            )
    elif kind == "comic":
        comic_frame(c, w, h, issue["style"], index)
        side = min(w, h) * (0.11 if issue["style"] == "ornamental" else 0.065)
        vertical = min(w, h) * (0.195 if issue["style"] == "ornamental" else 0.09)
        draw_art(
            c, project, item, (side, vertical, w - 2 * side, h - 2 * vertical), dpi
        )
    else:
        draw_art(c, project, item, (0, 0, w, h), dpi, full=True)
    if kind in {"comic", "essay"} and issue["numbers"]:
        c.setFillColorRGB(*INK)
        c.setFont("Times-Roman", max(8, min(13, min(w, h) * 0.034)))
        c.drawCentredString(w / 2, min(w, h) * 0.047, str(index + 1))
    c.showPage()


def pdf(target, project, issue, pages, dpi, first=0, on_page=None):
    c = Canvas(target, pagesize=dimensions(issue), pageCompression=1)
    c.setTitle(issue["title"])
    c.setCreator("Goosnav Zine Maker")
    for index, page in enumerate(pages, first):
        if on_page:
            on_page(index)
        draw(c, project, issue, page, index, dpi)
    c.save()


def raster(data, edge):
    with PDF_LOCK, pdfium.PdfDocument(data) as doc, closing(doc[0]) as page:
        return raster_page(page, edge)


def raster_page(page, edge):
    with closing(page.render(scale=edge / max(page.get_size()))) as bitmap:
        return bitmap.to_pil().convert("RGB")


def preview(project, issue, page, index):
    stream = io.BytesIO()
    with PDF_LOCK:
        pdf(stream, project, issue, [page], 145, first=index)
        im = raster(stream.getvalue(), 1200)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=91)
    return out.getvalue()
