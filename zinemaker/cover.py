"""Editable cover color recipes, continuous page borders, and source-space paint."""

import json
import math
import numpy as np
import re
from PIL import Image, ImageChops, ImageEnhance, ImageOps, ImageDraw

from .images import open_image

DEFAULT = {
    "border": "none",
    "fit": "inherit",
    "width": 4,
    "keyline": 0,
    "zoom": 100,
    "focus_x": 50,
    "focus_y": 50,
    "filter": "original",
    "frame": "#F9C62D",
    "stripe": "#222020",
    "palette": ["#222020", "#B54035", "#F9C62D", "#FAF1DB"],
    "name": "Newsstand",
    "wash": 0,
    "saturation": 100,
    "contrast": 100,
    "fills": [],
}


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Select an RGB swatch.")
    return value.upper()


def bounded(value, lo, hi):
    if (
        type(value) not in (float, int)
        or not math.isfinite(value)
        or not lo <= value <= hi
    ):
        raise ValueError("Cover setting is outside the allowed range.")
    return value


def recipe(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid cover settings.")
    d = {**DEFAULT, **value}
    if d["fit"] not in ("inherit", "contain", "fill", "extend"):
        raise ValueError("Choose a cover fit.")
    if d["border"] not in ("none", "solid", "double"):
        raise ValueError("Choose a border style.")
    if not isinstance(d["palette"], list) or len(d["palette"]) != 4:
        raise ValueError("Choose a four-color palette.")
    if not isinstance(d["fills"], list) or len(d["fills"]) > 64:
        raise ValueError("A cover supports up to 64 paint edits.")
    if not isinstance(d["name"], str) or not 1 <= len(d["name"]) <= 80:
        raise ValueError("Invalid palette name.")
    if d["filter"] not in ("original", "grayscale", "ink", "palette", "dither"):
        raise ValueError("Choose an artwork filter.")
    fills = []
    for op in d["fills"]:
        if op["mode"] == "brush":
            points = op.get("points", [])
            if (
                not isinstance(points, list)
                or not 1 <= len(points) <= 4096
                or any(len(pt) != 2 for pt in points)
            ):
                raise ValueError("Invalid brush stroke.")
            fills.append(
                dict(
                    mode="brush",
                    color=color(op["color"]),
                    width=bounded(op["width"], 0.1, 10),
                    points=[[bounded(x, 0, 1), bounded(y, 0, 1)] for x, y in points],
                )
            )
            continue
        if op["mode"] not in ("bucket", "replace"):
            raise ValueError("Choose a paint tool.")
        fills.append(
            dict(
                x=bounded(op["x"], 0, 1),
                y=bounded(op["y"], 0, 1),
                color=color(op["color"]),
                tolerance=bounded(op["tolerance"], 0, 100),
                mode=op["mode"],
            )
        )
    return dict(
        name=d["name"],
        keyline=bounded(d["keyline"], 0, 6),
        zoom=bounded(d["zoom"], 100, 300),
        focus_x=bounded(d["focus_x"], 0, 100),
        focus_y=bounded(d["focus_y"], 0, 100),
        filter=d["filter"],
        fit=d["fit"],
        palette=[color(c) for c in d["palette"]],
        frame=color(d["frame"]),
        stripe=color(d["stripe"]),
        border=d["border"],
        width=bounded(d["width"], 1, 15),
        wash=bounded(d["wash"], 0, 100),
        saturation=bounded(d["saturation"], 0, 200),
        contrast=bounded(d["contrast"], 50, 160),
        fills=fills,
    )


def rgb(hexcolor):
    return tuple(bytes.fromhex(hexcolor[1:]))


def paint(im, op):
    if op["mode"] == "brush":
        draw = ImageDraw.Draw(im)
        width = max(1, round(min(im.size) * op["width"] / 100))
        points = [
            (
                min(im.width - 1, round(x * im.width)),
                min(im.height - 1, round(y * im.height)),
            )
            for x, y in op["points"]
        ]
        ink = rgb(op["color"])
        if len(points) > 1:
            draw.line(points, fill=ink, width=width, joint="curve")
        for x, y in points:
            start = width // 2
            draw.ellipse(
                (x - start, y - start, x - start + width - 1, y - start + width - 1),
                fill=ink,
            )
        return
    x = min(im.width - 1, int(op["x"] * im.width))
    y = min(im.height - 1, int(op["y"] * im.height))
    seed = im.getpixel((x, y))
    # Classify each channel in C. Flood-fill the binary mask only, so a similar
    # ink color elsewhere remains separate even if it matches the clicked pixel.
    threshold = round(op["tolerance"] * 2.55)
    bands = [
        band.point([255 if abs(v - base) <= threshold else 0 for v in range(256)])
        for band, base in zip(im.split(), seed)
    ]
    mask = ImageChops.darker(ImageChops.darker(bands[0], bands[1]), bands[2])
    if op["mode"] == "bucket":
        mask = connected(mask, x, y)
    im.paste(rgb(op["color"]), (0, 0, im.width, im.height), mask)


def connected(mask, x, y):
    """Mark horizontal runs connected above/below the seed (four neighbors)."""
    width, height = mask.size
    data = bytearray(mask.tobytes())
    stack = [(x, y)]
    runs = re.compile(b"\xff+")
    while stack:
        x, y = stack.pop()
        row = y * width
        if data[row + x] != 255:
            continue
        # Zero denotes a wall and 1 denotes an already visited entire run.
        left = data.rfind(b"\x00", row, row + x) + 1
        left = max(row, left)
        right = data.find(b"\x00", row + x, row + width)
        if right < 0:
            right = row + width
        data[left:right] = b"\x01" * (right - left)
        for dy in (-1, 1):
            if 0 <= y + dy < height:
                start = left + dy * width
                for match in runs.finditer(data, start, right + dy * width):
                    stack.append((match.start() - (row + dy * width), y + dy))
    return Image.frombytes("L", mask.size, bytes(data)).point([0, 255] + [0] * 254)


def edited_image(path, design):
    if not (
        design.get("filter", "original") != "original"
        or design["wash"]
        or design["fills"]
        or design["saturation"] != 100
        or design["contrast"] != 100
    ):
        return open_image(path)
    operations = tuple(json.dumps(op, sort_keys=True) for op in design["fills"])
    return paint_cache.render(
        path,
        tuple(design["palette"])
        if design["wash"] or design.get("filter") in ("palette", "dither")
        else (),
        design["wash"],
        design["saturation"],
        design["contrast"],
        operations,
        design.get("filter", "original"),
    )


class PaintCache:
    """Reuse the last full-size proof when the artist adds the next bucket fill."""

    def __init__(self):
        self.last = None

    def render(
        self, path, palette, wash, saturation, contrast, operations, filter_name
    ):
        base = (path, palette, wash, saturation, contrast, filter_name)
        previous = self.last
        start = 0
        if (
            previous
            and previous[0] == base
            and operations[: len(previous[1])] == previous[1]
        ):
            if operations == previous[1]:
                return previous[2]
            image = previous[2].copy()
            start = len(previous[1])
        else:
            image = adjust_colors(*base)
        for operation in operations[start:]:
            paint(image, json.loads(operation))
        self.last = (base, operations, image)
        return image


paint_cache = PaintCache()


def adjust_colors(path, palette, wash, saturation, contrast, filter_name="original"):
    image = open_image(path)
    if saturation != 100:
        image = ImageEnhance.Color(image).enhance(saturation / 100)
    if contrast != 100:
        image = ImageEnhance.Contrast(image).enhance(contrast / 100)
    if wash:
        stops = sorted(
            map(rgb, palette),
            key=lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2],
        )
        table = []
        for level in range(256):
            pos = level / 85
            i = min(2, int(pos))
            table.extend(
                round(a + (b - a) * (pos - i)) for a, b in zip(stops[i], stops[i + 1])
            )
        tones = ImageOps.grayscale(image)
        tones.putpalette(table)
        image = Image.blend(image, tones.convert("RGB"), wash / 100)
    if filter_name == "grayscale":
        return ImageOps.grayscale(image).convert("RGB")
    if filter_name == "ink":
        return (
            ImageOps.grayscale(image)
            .point(lambda p: 255 if p >= 150 else 0)
            .convert("RGB")
        )
    if filter_name == "dither":
        table = Image.new("P", (1, 1))
        table.putpalette(list(bytes.fromhex("".join(c[1:] for c in palette))) * 64)
        return image.quantize(
            palette=table, dither=Image.Dither.FLOYDSTEINBERG
        ).convert("RGB")
    if filter_name == "palette":
        # GSNV Paint's nearest squared-RGB rule. Chunk to bound working memory.
        colors = np.array([rgb(c) for c in palette], dtype=np.int32)
        for top in range(0, image.height, 64):
            box = (0, top, image.width, min(image.height, top + 64))
            pixels = np.asarray(image.crop(box), dtype=np.int32)
            distances = np.stack(
                [np.sum((pixels - c) ** 2, axis=2) for c in colors], axis=2
            )
            image.paste(
                Image.fromarray(colors[distances.argmin(axis=2)].astype(np.uint8)), box
            )
    return image


def placement(item, design, page_size):
    """Return the page-space art rectangle (top-down) and its original pixels."""
    w, h = page_size
    margin = min(w, h) * design["width"] / 100 if design["border"] != "none" else 0
    width, height = item["size"]
    xmin, ymin, xmax, ymax = item["crop"] or (0, 0, 1, 1)
    left, top = (
        min(width - 1, round(xmin * width)),
        min(height - 1, round(ymin * height)),
    )
    right, bottom = (
        max(left + 1, round(xmax * width)),
        max(top + 1, round(ymax * height)),
    )
    sw, sh = right - left, bottom - top
    quarter = item["rotate"] in (90, 270)
    fit = design.get("fit", "inherit")
    if fit == "inherit":
        fit = item["fit"]
    cw, ch = sw, sh
    if fit == "fill":
        ratio = (w - 2 * margin) / (h - 2 * margin)
        if quarter:
            ratio = 1 / ratio
        cw, ch = min(sw, max(1, round(sh * ratio))), min(sh, max(1, round(sw / ratio)))
    zoom = design.get("zoom", 100) / 100
    cw, ch = max(1, round(cw / zoom)), max(1, round(ch / zoom))
    left += round((sw - cw) * design.get("focus_x", 50) / 100)
    top += round((sh - ch) * design.get("focus_y", 50) / 100)
    right, bottom = left + cw, top + ch
    sw, sh = cw, ch
    if quarter:
        sw, sh = sh, sw
    scale = min((w - 2 * margin) / sw, (h - 2 * margin) / sh)
    dw, dh = sw * scale, sh * scale
    return ((w - dw) / 2, (h - dh) / 2, dw, dh), (left, top, right, bottom), margin


def draw_cover(canvas, project, item, design, page_size, dpi, draw_image):
    w, h = page_size
    (x, y, dw, dh), box, margin = placement(item, design, page_size)
    if margin:

        def rect(inset, ink):
            canvas.setFillColor(ink)
            canvas.rect(inset, inset, w - 2 * inset, h - 2 * inset, fill=1, stroke=0)

        rect(0, design["frame"])
        if design["border"] == "double":
            rect(margin * 0.72, design["stripe"])
        rect(margin, "#FFFFFF")
    img = edited_image(project.asset(item), design).crop(box)
    if item["rotate"]:
        img = img.transpose(
            {
                90: Image.Transpose.ROTATE_270,
                180: Image.Transpose.ROTATE_180,
                270: Image.Transpose.ROTATE_90,
            }[item["rotate"]]
        )
    if design.get("fit") == "extend":
        # Mirror the edge color at each scanline to preserve edge lettering.
        from reportlab.lib.utils import ImageReader

        if x - margin > 0.01:
            for start, col in ((margin, 0), (x + dw, img.width - 1)):
                canvas.drawImage(
                    ImageReader(img.crop((col, 0, col + 1, img.height))),
                    start,
                    h - y - dh,
                    x - margin,
                    dh,
                )
        if y - margin > 0.01:
            for start, row in ((margin, img.height - 1), (h - y, 0)):
                canvas.drawImage(
                    ImageReader(img.crop((0, row, img.width, row + 1))),
                    x,
                    start,
                    dw,
                    y - margin,
                )
    draw_image(canvas, img, (x, h - y - dh, dw, dh), dpi)
    if margin and design.get("keyline", 0):
        canvas.setLineWidth(design["keyline"])
        canvas.setStrokeColorRGB(0, 0, 0)
        canvas.rect(margin, margin, w - 2 * margin, h - 2 * margin, fill=0, stroke=1)


def source_swatches(path):
    image = open_image(path)
    image.thumbnail((160, 160))
    sample = image.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    table = sample.getpalette()
    colors = []
    for _, index in sorted(sample.getcolors(), reverse=True):
        candidate = tuple(table[index * 3 : index * 3 + 3])
        if all(
            sum((a - b) ** 2 for a, b in zip(old, candidate)) > 45**2 for old in colors
        ):
            colors.append(candidate)
    return ["#%02X%02X%02X" % c for c in colors[:6]]
