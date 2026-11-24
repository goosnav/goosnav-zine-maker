"""Inspect scans once. Store crop rectangles in oriented source coordinates."""

from PIL import Image, ImageFilter, ImageOps, ImageStat

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp", ".gif"}
Image.MAX_IMAGE_PIXELS = 100_000_000


def open_image(path):
    with Image.open(path) as source:
        if source.width * source.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds the 100 megapixel limit.")
        image = ImageOps.exif_transpose(source)
        if image.mode in ("RGBA", "LA", "P") or "transparency" in image.info:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
        if image.mode.startswith("I;16"):
            return image.point(lambda x: x / 256).convert("RGB")
        return image.convert("RGB")


def panel_band(rows):
    """Find framed strip rows separated from marginal notes by clear paper."""
    height = len(rows)
    groups = []
    gap = max(5, round(height * 0.035))
    for y, coverage in enumerate(rows):
        if coverage < 8:
            continue
        if not groups or y - groups[-1][1] > gap:
            groups.append([y, y])
        else:
            groups[-1][1] = y
    bands = []
    for top, bottom in groups:
        span = bottom - top + 1
        edge = max(3, round(span * 0.16))
        if (
            span > height * 0.075
            and max(rows[top : top + edge]) >= 65
            and max(rows[bottom - edge + 1 : bottom + 1]) >= 65
        ):
            bands.append((top, bottom))
        elif max(rows[top : bottom + 1]) > 50:
            # A substantial illustration outside the frames may belong to the comic.
            return None
    if bands:
        return bands[0][0], bands[-1][1] + 1
    return None


def auto_crop(image):
    sample = image.copy()
    sample.thumbnail((1100, 1100))
    gray = ImageOps.grayscale(sample)
    w, h = gray.size
    whole = [0, 0, 1, 1]
    if min(w, h) < 24:
        return whole
    corners = [gray.crop((x, y, x + 4, y + 4)) for x in (0, w - 4) for y in (0, h - 4)]
    paper = sorted(ImageStat.Stat(c).median[0] for c in corners)[2]
    if paper < 186:  # Full-bleed photos and dark stock
        return whole
    mask = gray.filter(ImageFilter.MedianFilter(3)).point(
        lambda p: 255 if p < paper - 43 else 0
    )

    # Add a paper margin around the detected ink.
    def extent(projection, length):
        points = [i for i, value in enumerate(projection) if value > 1.3]
        if not points:
            return (0, length)
        return (
            max(0, points[0] - round(length * 0.014) - 1),
            min(length, points[-1] + round(length * 0.014) + 2),
        )

    rows = mask.resize((1, h), Image.Resampling.BOX).tobytes()
    band = panel_band(rows)
    if band:
        pad = max(2, round(h * 0.018))
        y0, y1 = max(0, band[0] - pad), min(h, band[1] + pad)
    else:
        y0, y1 = extent(rows, h)
    strip = mask.crop((0, y0, w, y1))
    x0, x1 = extent(strip.resize((w, 1), Image.Resampling.BOX).tobytes(), w)
    if x1 - x0 < w * 0.08 or y1 - y0 < h * 0.04:
        return whole
    return [x0 / w, y0 / h, x1 / w, y1 / h]


def region(image, crop):
    w, h = image.size
    left, top, right, bottom = crop
    x, y = min(w - 1, round(left * w)), min(h - 1, round(top * h))
    return image.crop(
        (x, y, max(x + 1, round(right * w)), max(y + 1, round(bottom * h)))
    )
