"""Identify imported page proofs by their typeset heading and opening words."""

import io
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageOps
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from .images import open_image
from .layout import raster


@lru_cache(maxsize=128)
def text_sample(words, face):
    width = stringWidth(words, face, 24) + 8
    stream = io.BytesIO()
    c = Canvas(stream, pagesize=(width, 36))
    c.setFont(face, 24)
    c.drawString(4, 9, words)
    c.showPage()
    c.save()
    ink = ImageOps.invert(
        raster(stream.getvalue(), round(max(width, 36) * 2)).convert("L")
    )
    return np.asarray(ink.crop(ink.getbbox()))


def find_line(image, sample, heights):
    best, rect = 0, (0, 0, 0, 0)
    for height in heights:
        width = max(1, round(height * sample.shape[1] / sample.shape[0]))
        if width >= image.shape[1] or height >= image.shape[0]:
            continue
        pattern = cv2.resize(sample, (width, height), interpolation=cv2.INTER_AREA)
        scores = cv2.matchTemplate(image, pattern, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        if score > best:
            best, rect = score, (x, y, width, height)
    return best, rect


@lru_cache(maxsize=256)
def resembles_essay(path, title, opening):
    image = open_image(path)
    image.thumbnail((800, 800), Image.Resampling.LANCZOS)
    width, height = image.size
    if width < 150 or height < 100 or len(title) < 3 or len(opening) < 8:
        return False
    ink = np.asarray(ImageOps.invert(image.convert("L")))
    heading = ink[: max(20, height // 3), : 3 * width // 4]
    score, (_, y, _, h) = find_line(
        heading, text_sample(title, "Times-Bold"), range(9, 48)
    )
    if score < 0.76:
        return False
    bottom = y + h
    body = ink[bottom : bottom + max(20, height // 5), : 3 * width // 4]
    words = [word for word in opening.split() if len(word) >= 3][:2]
    if len(words) < 2:
        return False
    score, (x, y, w, h) = find_line(
        body, text_sample(words[0], "Times-Roman"), range(6, 30)
    )
    if score < 0.78:
        return False
    # Confirm the next word on the same baseline, close to the first word.
    sample = text_sample(words[1], "Times-Roman")
    region = body[
        max(0, y - h // 2) : y + 2 * h,
        x + w - 1 : x + w + round(h * (5 + 2 * sample.shape[1] / sample.shape[0])),
    ]
    score, _ = find_line(region, sample, range(max(4, h // 2), 2 * h + 1))
    return score >= 0.78


def possible_proofs(project, items):
    essays = [
        (i["title"], " ".join(i["body"].split()[:3]))
        for i in items
        if i["role"] == "essay"
    ]
    matches = {}
    for item in items:
        if item["role"] == "comic" and not item.get("panels"):
            for title, opening in essays:
                try:
                    match = resembles_essay(
                        project.asset(item), title[:50], opening[:60]
                    )
                except (OSError, ValueError):
                    continue
                if match:
                    matches[item["id"]] = title
                    break
    return matches
