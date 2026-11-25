"""Portable project snapshots. Restore into a fresh folder next to the selected file."""

import copy
import hashlib
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from .cover import recipe
from .images import open_image
from .project import FOLDER, MAX_FILE, Project, ROLES


def references(issue):
    return {
        item[key]
        for item in issue["items"]
        for key in ("asset", "illustration")
        if item.get(key)
    }


def save_project(project, issue):
    title = re.sub(r"[^\w .-]", "_", issue["title"]).strip(" .")[:80] or "Issue"
    name = f"{title} - {datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.gsnvzine"
    target = project.root / name
    with tempfile.NamedTemporaryFile(dir=project.root, delete=False) as temp:
        stage = Path(temp.name)
    try:
        with zipfile.ZipFile(stage, "w", allowZip64=True) as archive:
            archive.writestr(
                "issue.json", json.dumps({**issue, "origin": ".."}, ensure_ascii=False)
            )
            for asset in sorted(references(issue)):
                archive.write(
                    project.asset({"asset": asset, "title": asset}), "assets/" + asset
                )
        stage.replace(target)
    finally:
        stage.unlink(missing_ok=True)
    return target


def open_project(path, destination=None):
    path = Path(path).resolve(strict=True)
    parent = Path(destination or path.parent)
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 20000 or len({e.filename for e in entries}) != len(entries):
            raise ValueError("Invalid project file list.")
        if archive.getinfo("issue.json").file_size > 24 * 1024**2:
            raise ValueError("Issue manifest is too large.")
        data = json.loads(archive.read("issue.json"))
        if data.get("version") != 1 or not isinstance(data.get("items"), list):
            raise ValueError("Unsupported project version.")
        if not isinstance(data.get("seen"), list) or not all(
            isinstance(v, str) for v in data["seen"]
        ):
            raise ValueError("Invalid source file list.")
        ids = [item.get("id") for item in data["items"]]
        if any(
            not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{32}", v) for v in ids
        ) or len(ids) != len(set(ids)):
            raise ValueError("Invalid page identifiers.")
        refs = references(data)
        if {e.filename for e in entries} != {
            "issue.json",
            *("assets/" + name for name in refs),
        }:
            raise ValueError("Project artwork list is incomplete or invalid.")
        if sum(entry.file_size for entry in entries) > shutil.disk_usage(parent).free:
            raise ValueError(
                "The chosen disk does not have space to open this project."
            )
        directory = Path(tempfile.mkdtemp(prefix=path.stem[:64] + " - ", dir=parent))
        try:
            root = directory / FOLDER
            assets = root / "assets"
            assets.mkdir(parents=True)
            sizes = {}
            for name in refs:
                if not re.fullmatch(
                    r"[a-f0-9]{64}\.(?:png|jpeg|jpg|webp|bmp|gif|tiff?)", name
                ):
                    raise ValueError("Invalid artwork reference.")
                entry = archive.getinfo("assets/" + name)
                if entry.file_size > MAX_FILE:
                    raise ValueError("Artwork exceeds the project size limit.")
                with archive.open(entry) as src, (assets / name).open("wb") as out:
                    shutil.copyfileobj(src, out)
                with (assets / name).open("rb") as src:
                    if (
                        hashlib.file_digest(src, "sha256").hexdigest()
                        != name.split(".")[0]
                    ):
                        raise ValueError("Project contains damaged artwork.")
                sizes[name] = list(open_image(assets / name).size)
            if any(item["role"] not in ROLES for item in data["items"]):
                raise ValueError("Unknown issue page type.")
            data.update(origin="..", id=uuid.uuid4().hex, revision=0)
            (root / "issue.json").write_text(json.dumps(data), "utf-8")
            project = Project(root)
            original = copy.deepcopy(project.data)
            project.edit("settings", data)
            for item in project.data["items"]:
                if item["role"] != "essay":
                    if sizes.get(item.get("asset")) != item.get("size"):
                        raise ValueError("Artwork dimensions do not match the project.")
                    auto = item.get("auto")
                    if (
                        not isinstance(auto, list)
                        or len(auto) != 4
                        or not (
                            0 <= auto[0] < auto[2] <= 1 and 0 <= auto[1] < auto[3] <= 1
                        )
                    ):
                        raise ValueError("Invalid automatic crop.")
                project.edit("item", item)
                if item.get("cover_design"):
                    recipe(item["cover_design"])
            project.data = original
            project.save()
            return project
        except BaseException:
            shutil.rmtree(directory)
            raise
