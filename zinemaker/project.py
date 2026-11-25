"""A portable issue contains immutable artwork copies and an atomic edit manifest."""

import copy
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from PIL.Image import DecompressionBombError
from filelock import FileLock
from .panels import analyze, bounds
from .cover import recipe
from .images import IMAGE_EXT, auto_crop, open_image

FOLDER = "Goosnav Zine"
TEXT_EXT = {".txt", ".md"}
ROLES = {"comic", "ad", "cover", "back", "essay"}
GROUPS = {
    "comics": "comic",
    "ads": "ad",
    "advertisements": "ad",
    "essays": "essay",
    "covers": "cover",
    "art": "comic",
    "all-book-prints": "comic",
}
DEFAULTS = {
    "width": 8.5,
    "height": 5.5,
    "style": "ornamental",
    "cover": True,
    "numbers": True,
}
MAX_FILE = 256 * 1024 * 1024


def natural(path):
    return [
        int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", str(path))
    ]


def number(value, low, high):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"Enter a number from {low} to {high}.")
    return value


def title(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValueError("Use a title between 1 and 160 characters.")
    return value.strip()


def text_body(value):
    if not isinstance(value, str) or len(value) > 150_000 or not value.strip():
        raise ValueError("Use between 1 and 150,000 characters of essay text.")
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise ValueError("Essay contains unsupported control characters.")
    return value.replace("\r\n", "\n").replace("\r", "\n")


def role_for(path, group=None):
    stem = path.stem.casefold()
    if path.suffix.lower() in TEXT_EXT:
        return "essay"
    if re.match(r"back[ _-]*cover\b", stem.replace("_", " ")):
        return "back"
    if re.match(r"(front[ _-]*)?cover(\b|_)", stem):
        return "cover"
    if re.match(r"(ad|advertisement)(\b|_|\d)", stem):
        return "ad"
    return group if group in {"ad", "cover", "back"} else "comic"


def arrange(items):
    covers = [i for i in items if i["role"] == "cover"]
    essays = [i for i in items if i["role"] == "essay"]
    comics = [i for i in items if i["role"] == "comic"]
    ads = [i for i in items if i["role"] == "ad"]
    middle = list(comics)
    for index, ad in reversed(list(enumerate(ads))):
        middle.insert(math.ceil((index + 1) * len(comics) / (len(ads) + 1)), ad)
    return covers + essays + middle + [i for i in items if i["role"] == "back"]


def insert_items(existing, added):
    if not existing:
        return arrange(added)
    result = existing[:]
    for item in arrange(added):
        role = item["role"]
        index = len(result)
        if role == "cover":
            index = next(
                (n for n, i in enumerate(result) if i["role"] != "cover"), index
            )
        elif role == "essay":
            index = next(
                (
                    n
                    for n, i in enumerate(result)
                    if i["role"] not in {"cover", "essay"}
                ),
                index,
            )
        elif role == "ad":
            comics = [n for n, i in enumerate(result) if i["role"] == "comic"]
            if comics:
                index = comics[(len(comics) - 1) // 2] + 1
            else:
                index = next(
                    (n for n, i in enumerate(result) if i["role"] == "back"), index
                )
        elif role == "comic":
            index = next(
                (n for n, i in enumerate(result) if i["role"] == "back"), index
            )
        result.insert(index, item)
    return result


class Conflict(ValueError):
    pass


class Project:
    def __init__(self, source, destination=None):
        self.source = Path(source).expanduser().resolve(strict=True)
        if not self.source.is_dir():
            raise ValueError("Choose a comics folder.")
        direct = (
            self.source.name == FOLDER
            and (self.source / "issue.json").is_file()
            and destination is None
        )
        base = Path(destination).expanduser().resolve() if destination else self.source
        self.root = self.source if direct else base / FOLDER
        self.assets = self.root / "assets"
        self.manifest = self.root / "issue.json"
        if (
            self.root.is_symlink()
            or self.assets.is_symlink()
            or self.manifest.is_symlink()
        ):
            raise ValueError("Choose a regular project folder.")
        if (
            self.root.exists()
            and not self.manifest.exists()
            and any(
                child.name not in {".DS_Store", ".issue.lock", "assets"}
                for child in self.root.iterdir()
            )
        ):
            raise ValueError(
                "This destination already contains a different Goosnav Zine folder. Choose another destination."
            )
        self.assets.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.root / ".issue.lock"), timeout=20)
        self.warnings = []
        with self.lock:
            if not self.manifest.exists():
                origin = ".." if self.source == self.root.parent else str(self.source)
                self.data = {
                    "origin": origin,
                    "version": 1,
                    "revision": 0,
                    "id": uuid.uuid4().hex,
                    "title": self.source.name[:160] or "Untitled issue",
                    **DEFAULTS,
                    "items": [],
                    "seen": [],
                }
                self.scan()
                self.save()
            else:
                self.reload()
                origin = (self.root / self.data.get("origin", "..")).resolve()
                if direct:
                    self.source = origin if origin.is_dir() else self.root
                elif origin != self.source:
                    raise ValueError(
                        "This destination holds another issue. Open its Goosnav Zine folder or choose a new destination."
                    )
                migration_warnings = []
                migrated = False
                for item in self.data["items"]:
                    if item["role"] == "comic" and "panels" not in item:
                        try:
                            item["panels"], item["auto"] = analyze(
                                open_image(self.asset(item))
                            )
                            migrated = True
                        except (ValueError, OSError, DecompressionBombError) as exc:
                            migration_warnings.append(str(exc))

                previous_seen = len(self.data["seen"])
                if not direct:
                    self.scan()
                self.warnings.extend(migration_warnings)
                if migrated or previous_seen != len(self.data["seen"]):
                    self.save()

    def reload(self):
        data = json.loads(self.manifest.read_text("utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("items"), list):
            raise ValueError("Unsupported issue manifest.")
        self.data = data

    def asset(self, item):
        name = item["asset"]
        if not re.fullmatch(r"[0-9a-f]{64}\.[a-z0-9]{2,5}", name):
            raise ValueError("Invalid artwork reference.")
        path = self.assets / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing artwork for {item['title']}.")
        return path

    def save(self):
        self.data["revision"] += 1
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.root, delete=False
        ) as out:
            tmp = Path(out.name)
            try:
                json.dump(self.data, out, ensure_ascii=False, indent=2)
                out.flush()
                os.fsync(out.fileno())
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        try:
            os.replace(tmp, self.manifest)
        finally:
            tmp.unlink(missing_ok=True)

    def store_image(self, path, suffix):
        if suffix not in IMAGE_EXT or path.stat().st_size > MAX_FILE:
            raise ValueError("Choose a supported image under 256 MiB.")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        target = self.assets / (digest + suffix)
        if target.is_symlink():
            raise ValueError("Invalid asset path.")
        if not target.exists():
            with tempfile.NamedTemporaryFile(dir=self.assets, delete=False) as out:
                tmp = Path(out.name)
            try:
                shutil.copyfile(path, tmp)
                image = open_image(tmp)
                tmp.replace(target)
            finally:
                tmp.unlink(missing_ok=True)
        else:
            image = open_image(target)
        return target, image

    def add(self, path, name, key, group=None):
        suffix = Path(name).suffix.lower()
        if suffix not in IMAGE_EXT | TEXT_EXT:
            raise ValueError("Choose an image or a UTF-8 text file.")
        if path.stat().st_size > MAX_FILE:
            raise ValueError("File exceeds 256 MiB.")
        name_path = Path(name)
        role = role_for(name_path, group)
        item = {
            "id": uuid.uuid4().hex,
            "title": name_path.stem[:160] or "Untitled",
            "role": role,
            "name": name_path.name,
        }
        if role == "essay":
            if path.stat().st_size > 600_004:
                raise ValueError("Essay is too large.")
            item["body"] = text_body(path.read_text("utf-8-sig"))
        else:
            target, image = self.store_image(path, suffix)
            if role == "comic":
                item["panels"], crop = analyze(image)
            else:
                crop = auto_crop(image)
            item.update(
                asset=target.name,
                auto=crop,
                crop=None,
                fit="contain",
                size=list(image.size),
                rotate=0,
            )
        self.data["items"].append(item)
        self.data["seen"].append(key)
        return item

    def scan(self):
        self.warnings = []
        candidates = []
        for path in self.source.iterdir():
            if path.is_symlink() or path.name.startswith("."):
                continue
            if path.is_file():
                candidates.append((path, None))
            elif path.name.casefold() in GROUPS and path.is_dir():
                candidates.extend(
                    (p, GROUPS[path.name.casefold()])
                    for p in path.iterdir()
                    if p.is_file() and not p.is_symlink() and not p.name.startswith(".")
                )
        added = []
        seen = set(self.data["seen"])
        # Comic Maker exports the same book crop as both PNG and TIFF.
        book_prints = {
            str(Path(key).with_suffix("")).casefold()
            for key in seen
            if Path(key).stem.casefold().endswith("--comic")
        }
        for path, group in sorted(candidates, key=lambda pair: natural(pair[0])):
            key = path.relative_to(self.source).as_posix()
            if key in seen or path.suffix.lower() not in IMAGE_EXT | TEXT_EXT:
                continue
            paired_print = (
                path.parent.name.casefold() == "all-book-prints"
                and path.stem.casefold().endswith("--comic")
                and path.suffix.lower() in {".png", ".tif", ".tiff"}
            )
            print_key = str(Path(key).with_suffix("")).casefold()
            if paired_print and print_key in book_prints:
                continue
            if path.suffix.lower() in TEXT_EXT and path.stem.lower() in {
                "readme",
                "agents",
                "license",
                "changelog",
                "requirements",
            }:
                continue
            try:
                item = self.add(path, path.name, key, group)
                if item["role"] == "essay" and self.same_essay(item):
                    self.data["items"].pop()
                    continue
                added.append(item)
                if paired_print:
                    book_prints.add(print_key)
            except (ValueError, OSError, DecompressionBombError) as exc:
                self.warnings.append(f"{key} — {exc}")
        if added:
            previous = self.data["items"][: -len(added)]
            self.data["items"] = insert_items(previous, added)
        return added

    def same_essay(self, item):
        body = " ".join(item["body"].split())
        return next(
            (
                old
                for old in self.data["items"]
                if old["id"] != item["id"]
                and old["role"] == "essay"
                and " ".join(old["body"].split()) == body
            ),
            None,
        )

    def essay_style(self, item, p):
        item["font_size"] = (
            number(p["font_size"], 7, 24) if p.get("font_size") else None
        )
        item["drop_cap"] = p.get("drop_cap", True) is True
        item["image_width"] = number(p.get("image_width", 100), 10, 100)
        item["image_side"] = p.get("image_side", "right")
        item["image_fit"] = p.get("image_fit", "contain")
        if item["image_side"] not in ("left", "right") or item["image_fit"] not in (
            "contain",
            "fill",
        ):
            raise ValueError("Choose an illustration position and framing.")
        item["image_height"] = number(p.get("image_height", 38), 10, 70)
        item["image_zoom"] = number(p.get("image_zoom", 100), 100, 250)
        item["image_x"] = number(p.get("image_x", 50), 0, 100)
        item["image_y"] = number(p.get("image_y", 50), 0, 100)
        if "illustration" in p:
            ref = p["illustration"]
            if ref:
                self.asset({"asset": ref, "title": "Essay illustration"})
            item["illustration"] = ref

    def update(self, action, payload):
        with self.lock:
            self.reload()
            if (
                payload.get("project") != self.data["id"]
                or payload.get("revision") != self.data["revision"]
            ):
                raise Conflict("This issue changed. Reload the editor before saving.")
            self.warnings = []
            result = self.edit(action, payload)
            self.save()
            return result

    def edit(self, action, p):
        items = self.data["items"]
        if action == "scan":
            self.scan()
        elif action == "settings":
            style = p["style"]
            if style not in {"ornamental", "ruled", "plain"} or any(
                type(p[k]) is not bool for k in ("cover", "numbers")
            ):
                raise ValueError("Invalid issue settings.")
            self.data.update(
                title=title(p["title"]),
                width=number(p["width"], 3, 24),
                height=number(p["height"], 3, 24),
                style=style,
                cover=p["cover"],
                numbers=p["numbers"],
            )
        elif action == "essay":
            essay = {
                "id": uuid.uuid4().hex,
                "role": "essay",
                "title": title(p["title"]),
                "name": "",
                "body": text_body(p["body"]),
            }
            if self.same_essay(essay):
                raise ValueError(
                    "This essay is already in the issue. Select it and choose Edit essay."
                )
            self.essay_style(essay, p)
            self.data["items"] = insert_items(items, [essay])
        elif action == "upload":
            if (
                p.get("role") == "cover"
                and Path(p["name"]).suffix.lower() not in IMAGE_EXT
            ):
                raise ValueError("Choose a cover image.")
            item = self.add(p["path"], p["name"], p["name"])
            if item["role"] == "essay" and (prior := self.same_essay(item)):
                items.pop()
                return prior["id"]
            if p.get("role") == "cover":
                # Reopen the same cover with its edits; interior pages keep their roles.
                prior = next(
                    (
                        old
                        for old in items[:-1]
                        if old["name"] == item["name"]
                        and old.get("asset") == item["asset"]
                        and old["role"] == "cover"
                    ),
                    None,
                )
                items.pop()
                if prior:
                    items.remove(prior)
                    self.data["seen"].pop()
                    item = prior
                item["role"] = "cover"
                items.insert(0, item)
            else:
                self.data["items"] = insert_items(items[:-1], [item])
            return item["id"]
        else:
            item = next((i for i in items if i["id"] == p.get("id")), None)
            if item is None:
                raise ValueError("Select an item in the page list.")
            if action == "cover-design":
                if item["role"] not in {"cover", "back"}:
                    raise ValueError("Select a front or back cover.")
                item["cover_design"] = recipe(p["design"])
            elif action == "move":
                old = items.index(item)
                new = p["index"]
                if type(new) is not int or not 0 <= new < len(items):
                    raise ValueError("Invalid position.")
                items.insert(new, items.pop(old))
            elif action == "remove":
                items.remove(item)
            elif action == "item":
                item["title"] = title(p["title"])
                if item["role"] == "essay":
                    item["body"] = text_body(p["body"])
                    self.essay_style(item, {**item, **p})
                    return
                role, fit, crop, rotate = p["role"], p["fit"], p["crop"], p["rotate"]
                if (
                    role not in ROLES - {"essay"}
                    or fit not in {"contain", "fill", "original"}
                    or rotate not in (0, 90, 180, 270)
                ):
                    raise ValueError("Invalid artwork settings.")
                if crop is not None:
                    if (
                        not isinstance(crop, list)
                        or len(crop) != 4
                        or not all(number(v, 0, 1) >= 0 for v in crop)
                    ):
                        raise ValueError("Select a crop inside the artwork.")
                    if crop[2] - crop[0] < 0.005 or crop[3] - crop[1] < 0.005:
                        raise ValueError("Draw a larger crop.")
                if role == "comic":
                    mode = p.get("layout", item.get("layout", "auto"))
                    if mode not in ("auto", "single", "2", "4", "10", "spread"):
                        raise ValueError("Choose a comic layout.")
                    item["layout"] = mode
                    if "panels" in p:
                        boxes = p["panels"]
                        if not isinstance(boxes, list) or len(boxes) > 10:
                            raise ValueError("Use up to ten panel rectangles.")
                        for box in boxes:
                            if (
                                len(box) != 4
                                or not all(number(v, 0, 1) >= 0 for v in box)
                                or min(box[2] - box[0], box[3] - box[1]) < 0.005
                            ):
                                raise ValueError("Draw each panel inside the image.")
                        if boxes != item.get("panels"):
                            item["auto"] = (
                                bounds(boxes)
                                if boxes
                                else auto_crop(open_image(self.asset(item)))
                            )
                        item["panels"] = boxes
                    if "panels" not in item:
                        item["panels"], item["auto"] = analyze(
                            open_image(self.asset(item))
                        )
                old_role = item["role"]
                item.update(role=role, fit=fit, crop=copy.copy(crop), rotate=rotate)
                if role != old_role:
                    self.data["items"] = insert_items(
                        [i for i in items if i != item], [item]
                    )
            else:
                raise ValueError("Unknown edit.")
