"""Loopback-only editor. The native picker grants access to a folder."""

import copy
import functools
import io
import json
import mimetypes
import os
import shutil
import platform
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from filelock import Timeout
from .export import publish
from .images import open_image
from .layout import paginate, preview
from .project import Conflict, MAX_FILE, Project

STATIC = Path(__file__).with_name("static")


def choose_folder():
    if platform.system() == "Darwin":
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Choose a folder for Goosnav Zine Maker")',
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode and "-128" not in result.stderr:
            raise ValueError(
                "The folder picker could not open. Launch with a folder path in Terminal."
            )
        return result.stdout.strip()
    script = (
        "import tkinter as tk; from tkinter import filedialog; "
        "root=tk.Tk(); root.withdraw(); print(filedialog.askdirectory(parent=root)); root.destroy()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], text=True, capture_output=True
    )
    if result.returncode:
        raise ValueError(
            "The folder picker needs Tk. Launch with a folder path in the terminal."
        )
    return result.stdout.strip()


class Desk:
    def __init__(self, project):
        self.project = project
        self.token = secrets.token_urlsafe(32)
        self.folders = {}
        self.jobs = {}
        self.guard = threading.RLock()

    def snapshot(self):
        with self.guard, self.project.lock:
            self.project.reload()
            return self.project, copy.deepcopy(self.project.data)

    def state(self):
        project, issue = self.snapshot()
        pages = paginate(issue)
        summary = [
            {k: v for k, v in i.items() if k not in ("asset",)} for i in issue["items"]
        ]
        return {
            **{k: v for k, v in issue.items() if k not in ("items", "seen")},
            "items": summary,
            "pages": [
                {
                    "kind": p["kind"],
                    "id": p["item"]["id"] if p["item"] else None,
                    "part": p.get("part", 1),
                }
                for p in pages
            ],
            "source": str(project.source),
            "folder": str(project.root),
            "warnings": project.warnings,
        }

    @functools.lru_cache(maxsize=20)
    def page(self, project, revision, index):
        current, issue = self.snapshot()
        if current != project or issue["revision"] != revision:
            raise Conflict("Preview changed. Reload the editor.")
        pages = paginate(issue)
        if not 0 <= index < len(pages):
            raise ValueError("Unknown page.")
        return preview(project, issue, pages[index], index)

    @functools.lru_cache(maxsize=16)
    def source_image(self, project, asset):
        im = open_image(asset)
        im.thumbnail((1150, 1150))
        stream = io.BytesIO()
        im.save(stream, "JPEG", quality=90)
        return stream.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, content, mime="application/json", status=200):
        if mime == "application/json":
            content = json.dumps(content).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def dispatch(self, write):
        try:
            self.connection.settimeout(120)
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                return self.reply({"error": "Invalid host."}, status=403)
            path = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(path.query).items()}
            if write:
                if (
                    self.headers.get("Origin") != "http://" + host
                    or self.headers.get("X-Issue-Session") != self.server.desk.token
                ):
                    return self.reply(
                        {"error": "Reopen this local editor."}, status=403
                    )
                self.change(path.path, query)
            else:
                self.read(path.path, query)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            status = 409 if isinstance(exc, Conflict) else 400
            if isinstance(exc, Timeout):
                exc = ValueError("Another editor is saving this project. Try again.")
            self.reply({"error": str(exc) or HTTPStatus(status).phrase}, status=status)

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def file(self, path):
        self.reply(
            path.read_bytes(),
            mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )

    def read(self, path, q):
        desk = self.server.desk
        if path == "/api/state":
            self.reply({**desk.state(), "token": desk.token})
        elif path == "/api/export-progress":
            with desk.guard:
                job = desk.jobs.get(q.get("job"), {})
                self.reply({"status": job.get("status", "")})
        elif path == "/health/ready":
            self.reply({"ready": True})
        elif path in {"/api/page", "/api/art"}:
            project, issue = desk.snapshot()
            if q.get("project") != issue["id"]:
                raise Conflict("Reopen the current issue.")
            if path.endswith("page"):
                data = desk.page(project, int(q["revision"]), int(q["index"]))
            else:
                item = next((i for i in issue["items"] if i["id"] == q["id"]), None)
                if not item or "asset" not in item:
                    raise ValueError("Unknown artwork.")
                data = desk.source_image(project, project.asset(item))
            self.reply(data, "image/jpeg")
        elif re.fullmatch(
            r"/exports/[0-9_-]+[0-9a-f]{6}/(print\.pdf|digital\.pdf|website/(index\.html|page-\d+\.webp))",
            path,
        ):
            base = desk.project.root / "exports"
            target = base / path.removeprefix("/exports/")
            if target.resolve() != target or not target.is_file():
                raise ValueError("Export is unavailable.")
            # Stream large print editions without buffering a second copy.
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0])
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with target.open("rb") as f:
                shutil.copyfileobj(f, self.wfile)
        elif path in ("/", "/editor.css", "/editor.js", "/mark.svg"):
            self.file(STATIC / ("index.html" if path == "/" else path[1:]))
        elif path == "/favicon.ico":
            self.reply(b"", "image/x-icon", 204)
        else:
            self.reply({"error": "File not found."}, status=404)

    def change(self, path, q):
        desk = self.server.desk
        length = int(self.headers.get("Content-Length", "0"))
        if path == "/api/upload":
            if not 0 < length <= MAX_FILE:
                raise ValueError("Choose a nonempty file under 256 MiB.")
            name = q["name"]
            if name != Path(name).name or "/" in name or "\\" in name:
                raise ValueError("Invalid filename.")
            with tempfile.NamedTemporaryFile(
                dir=desk.project.root, delete=False
            ) as out:
                tmp = Path(out.name)
                try:
                    remaining = length
                    while remaining:
                        block = self.rfile.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError("Upload interrupted.")
                        out.write(block)
                        remaining -= len(block)
                except BaseException:
                    tmp.unlink(missing_ok=True)
                    raise
            try:
                with desk.guard:
                    desk.project.update(
                        "upload", {**q, "revision": int(q["revision"]), "path": tmp}
                    )
                    self.reply(desk.state())
            finally:
                tmp.unlink(missing_ok=True)
            return
        if (
            self.headers.get_content_type() != "application/json"
            or not 0 <= length <= 2_000_000
        ):
            raise ValueError("Invalid editor request.")
        p = json.loads(self.rfile.read(length))
        action = path.removeprefix("/api/")
        if action == "pick":
            picked = choose_folder()
            key = secrets.token_urlsafe(12)
            if picked:
                desk.folders[key] = Path(picked).resolve(strict=True)
            self.reply({"key": key if picked else None, "path": picked})
            return
        if action == "reveal":
            run = p.get("run", "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{6}-[a-f0-9]{6}", run):
                raise ValueError("Unknown export.")
            folder = desk.project.root / "exports" / run
            if folder.resolve() != folder or not (folder / "print.pdf").is_file():
                raise ValueError("The export folder is unavailable.")
            if platform.system() == "Windows":
                os.startfile(folder)
            else:
                subprocess.run(
                    [
                        "open" if platform.system() == "Darwin" else "xdg-open",
                        str(folder),
                    ],
                    check=True,
                )
            self.reply({"opened": True})
            return
        if action == "cancel-export":
            with desk.guard:
                job = desk.jobs.get(p.get("job"))
                if job:
                    job["cancelled"] = True
            self.reply({"received": bool(job)})
            return
        if action == "export":
            project, issue = desk.snapshot()
            if (
                p.get("project") != issue["id"]
                or p.get("revision") != issue["revision"]
            ):
                raise Conflict("Reload the latest issue before exporting.")
            key = p.get("job", "")
            if not re.fullmatch(r"[a-f0-9-]{36}", key):
                raise ValueError("Invalid export request.")
            with desk.guard:
                if desk.jobs:
                    raise ValueError("An export is already running.")
                desk.jobs[key] = {"cancelled": False, "status": "Preparing pages…"}

            def report(phase, current, total):
                with desk.guard:
                    if desk.jobs[key]["cancelled"]:
                        raise ValueError("Export cancelled.")
                    desk.jobs[key]["status"] = f"{phase} · page {current} of {total}"

            try:
                result = publish(project, issue, report)
            finally:
                with desk.guard:
                    del desk.jobs[key]
            self.reply({"path": str(result), "url": "/exports/" + result.name})
            return
        with desk.guard:
            if action == "open":
                source = desk.folders[p["source"]]
                dest = desk.folders[p["destination"]] if p.get("destination") else None
                desk.project = Project(source, dest)
                desk.page.cache_clear()
                desk.source_image.cache_clear()
            elif action in {"scan", "settings", "essay", "move", "remove", "item"}:
                desk.project.update(action, p)
            else:
                raise ValueError("Unknown command.")
            self.reply(desk.state())


def serve(project, port=0, browser=True):
    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        server.desk = Desk(project)
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"{url}\nIssue folder: {project.root}\nPress Ctrl+C to quit.", flush=True)
        if browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
