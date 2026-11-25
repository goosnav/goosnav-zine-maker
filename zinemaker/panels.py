"""Locate comic frames on a bounded proof and keep coordinates on the original scan."""

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import panel_detector
from .images import auto_crop


def bounds(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def split_gutters(gray, box):
    """Separate frames a few pixels apart inside one apparent outer rectangle."""
    x, y, w, h = box.x, box.y, box.w, box.h
    ink = gray[y : y + h, x : x + w] < 165
    for vertical, stripes in ((True, ink.T), (False, ink)):
        length, cross = stripes.shape
        if length < cross * 1.3 or min(length, cross) < 24:
            continue
        inset = max(2, round(cross * 0.05))
        coverage = stripes[:, inset:-inset].mean(axis=1)
        reach = max(4, round(cross * 0.055))
        clear = np.where(coverage < 0.025)[0]
        for run in np.split(clear, np.where(np.diff(clear) > 1)[0] + 1):
            if len(run) < 2:
                continue
            a, b = int(run[0]), int(run[-1]) + 1
            if min(a, length - b) < max(cross * 0.22, length * 0.12):
                continue
            if (
                min(
                    coverage[max(0, a - reach) : a].max(), coverage[b : b + reach].max()
                )
                < 0.84
            ):
                continue
            cut = (a + b) // 2
            parts = (
                ((x, y, cut, h), (x + cut, y, w - cut, h))
                if vertical
                else ((x, y, w, cut), (x, y + cut, w, h - cut))
            )
            return [
                child
                for part in parts
                for child in split_gutters(gray, panel_detector.Box(*part))
            ]
    return [box]


def gutter_boxes(gray):
    # Comic Maker's whitespace recovery for artwork without continuous borders.
    ink = (gray < 195).astype(np.uint8) * 255
    closed = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    joined = cv2.dilate(closed, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h > gray.size * 0.025 and 0.2 < w / h < 6:
            boxes.append(panel_detector.Box(x, y, w, h))
    return panel_detector.reading_order(panel_detector.prune(boxes))


def analyze(image, method="border"):
    sample = image.copy()
    sample.thumbnail((1500, 1500), Image.Resampling.LANCZOS)
    width, height = sample.size
    if min(sample.size) < 32 or max(sample.size) / min(sample.size) > 20:
        return [], auto_crop(sample)
    pad = max(8, round(max(sample.size) * 0.025))
    gray = np.asarray(ImageOps.expand(sample.convert("L"), border=pad, fill=255))
    if method == "gutter":
        height, width = sample.height, sample.width
        gutter = gutter_boxes(gray[pad : pad + height, pad : pad + width])
        boxes = [
            [b.x / width, b.y / height, (b.x + b.w) / width, (b.y + b.h) / height]
            for b in gutter
        ]
        if not 1 <= len(boxes) <= 10:
            return [], auto_crop(sample)
        return boxes, bounds(boxes)
    found = panel_detector.detect(gray)
    if not found.confident:
        # Normalize slow changes in paper tone independently of pencil borders.
        paper = cv2.morphologyEx(
            gray,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)),
        )
        paper = cv2.GaussianBlur(paper, (0, 0), 12)
        normalized = panel_detector.detect(
            cv2.divide(gray, np.maximum(paper, 80), scale=255)
        )
        if normalized.confident:
            found = normalized
    # Invert the analysis rotation. Crops and user edits always reference the
    # original orientation, and the full-resolution source stays untouched.
    matrix = cv2.getRotationMatrix2D(
        (gray.shape[1] / 2, gray.shape[0] / 2), -found.angle, 1
    )
    separated = [
        child
        for box in found.boxes
        for child in split_gutters(found.detection_image, box)
    ]
    boxes = []
    for box in panel_detector.reading_order(separated):
        x, y, r, b = box.x, box.y, box.x + box.w, box.y + box.h
        points = np.array([[x, y, 1], [r, y, 1], [r, b, 1], [x, b, 1]]) @ matrix.T
        lo = ((points.min(axis=0) - pad) / [width, height]).clip(0, 1)
        hi = ((points.max(axis=0) - pad) / [width, height]).clip(0, 1)
        boxes.append([*(float(p) for p in lo), *(float(p) for p in hi)])
    if not boxes or len(boxes) > 10 or any(b.coverage < 0.7 for b in found.boxes):
        return [], auto_crop(sample)
    crop = bounds(boxes)
    # A small isolated frame inside a larger illustration is unreliable.
    if (crop[2] - crop[0]) * (crop[3] - crop[1]) < 0.12:
        return [], auto_crop(sample)
    return boxes, crop


def comic_pages(issue, item):
    boxes = item.get("panels", [])
    mode = item.get("layout", "auto")
    if mode == "spread":
        return [
            {"kind": "comic", "item": item, "part": i + 1, "half": i} for i in range(2)
        ]
    if (
        not boxes
        or item["crop"]
        or item["fit"] != "contain"
        or item["rotate"]
        or mode == "single"
    ):
        return [{"kind": "comic", "item": item}]
    w, h = item["size"]
    crop = bounds(boxes)
    aspect = w * (crop[2] - crop[0]) / (h * (crop[3] - crop[1]))
    if mode == "auto":
        # Keep ordinary horizontal strips together. Rebuild square or tall
        # multi-row originals at a readable scale on landscape or portrait trim.
        if (
            len(boxes) < 2
            or aspect > 1.55
            and aspect < max(2.0, 2.8 * issue["width"] / issue["height"])
        ):
            return [{"kind": "comic", "item": item}]
        count = min(len(boxes), 4 if len(boxes) >= 4 and aspect < 1.45 else 2)
    else:
        count = min(len(boxes), int(mode))
    return [
        {
            "kind": "comic",
            "item": item,
            "part": i + 1,
            "group": boxes[i * len(boxes) // count : (i + 1) * len(boxes) // count],
        }
        for i in range(count)
    ]


def arrange_group(boxes, size, page_size):
    """Choose a row layout maximizing the smallest rendered panel scale."""
    w, h = page_size
    margin = min(w, h) * 0.035
    gap = margin * 0.55
    widths = [(box[2] - box[0]) * size[0] for box in boxes]
    heights = [(box[3] - box[1]) * size[1] for box in boxes]
    best_scale = 0
    for per_row in range(1, len(boxes) + 1):
        rows = [
            range(i, min(i + per_row, len(boxes)))
            for i in range(0, len(boxes), per_row)
        ]
        row_heights = [max(heights[i] for i in row) for row in rows]
        scale = min(
            (h - 2 * margin - gap * (len(rows) - 1)) / sum(row_heights),
            min(
                (w - 2 * margin - gap * (len(row) - 1)) / sum(widths[i] for i in row)
                for row in rows
            ),
        )
        if scale > best_scale:
            best_scale, best_rows, best_heights = scale, rows, row_heights
    top = (h + sum(best_heights) * best_scale + gap * (len(best_rows) - 1)) / 2
    for row, row_height in zip(best_rows, best_heights):
        x = (w - sum(widths[i] for i in row) * best_scale - gap * (len(row) - 1)) / 2
        for i in row:
            width, height = widths[i] * best_scale, heights[i] * best_scale
            yield (
                boxes[i],
                (x, top - (row_height * best_scale + height) / 2, width, height),
            )
            x += width + gap
        top -= row_height * best_scale + gap
