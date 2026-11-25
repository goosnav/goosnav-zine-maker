"""Editable cover color recipes, continuous page borders, and source-space paint."""

import math
import re
from PIL import Image, ImageChops, ImageEnhance, ImageOps

from .images import open_image

DEFAULT = {
    "border": "none",
    "fit": "inherit",
    "width": 4,
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
    if d["fit"] not in ("inherit", "contain", "fill"):
        raise ValueError("Choose a cover fit.")
    if d["border"] not in ("none", "solid", "double"):
        raise ValueError("Choose a border style.")
    if not isinstance(d["palette"], list) or len(d["palette"]) != 4:
        raise ValueError("Choose a four-color palette.")
    if not isinstance(d["fills"], list) or len(d["fills"]) > 64:
        raise ValueError("A cover supports up to 64 paint edits.")
    if not isinstance(d["name"], str) or not 1 <= len(d["name"]) <= 80:
        raise ValueError("Invalid palette name.")
    fills = []
    for op in d["fills"]:
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
        design["wash"]
        or design["fills"]
        or design["saturation"] != 100
        or design["contrast"] != 100
    ):
        return open_image(path)
    operations = tuple(
        tuple(op[k] for k in ("x", "y", "color", "tolerance", "mode"))
        for op in design["fills"]
    )
    return paint_cache.render(
        path,
        tuple(design["palette"]) if design["wash"] else (),
        design["wash"],
        design["saturation"],
        design["contrast"],
        operations,
    )


class PaintCache:
    """Reuse the last full-size proof when the artist adds the next bucket fill."""

    def __init__(self):
        self.last = None

    def render(self, path, palette, wash, saturation, contrast, operations):
        base = (path, palette, wash, saturation, contrast)
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
            paint(image, dict(zip(("x", "y", "color", "tolerance", "mode"), operation)))
        self.last = (base, operations, image)
        return image


paint_cache = PaintCache()


def adjust_colors(path, palette, wash, saturation, contrast):
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
    if fit == "fill":
        ratio = (w - 2 * margin) / (h - 2 * margin)
        if quarter:
            ratio = 1 / ratio
        cw, ch = min(sw, max(1, round(sh * ratio))), min(sh, max(1, round(sw / ratio)))
        left += (sw - cw) // 2
        top += (sh - ch) // 2
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
    draw_image(canvas, img, (x, h - y - dh, dw, dh), dpi)


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
