"""Build the self-contained macOS download for the current architecture."""

import hashlib
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Goosnav Zine Maker"


def notices(folder):
    folder.mkdir()
    shutil.copyfile(
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", folder / "Python.txt"
    )
    for name in (
        "pillow",
        "pypdfium2",
        "reportlab",
        "filelock",
        "charset-normalizer",
        "pyinstaller",
    ):
        dist = distribution(name)
        for file in dist.files:
            if "license" not in str(file).lower():
                continue
            target = folder / name / file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(dist.locate_file(file), target)


def main():
    if sys.platform != "darwin":
        raise SystemExit("Build this archive on macOS.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as work:
        work = Path(work)
        package = work / NAME
        package.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--onefile",
                "--console",
                "--name",
                NAME,
                "--workpath",
                str(work / "build"),
                "--specpath",
                str(work),
                "--distpath",
                str(package / "runtime"),
                "--add-data",
                f"{ROOT / 'zinemaker/static'}:zinemaker/static",
                "--add-data",
                f"{ROOT / 'zinemaker/art'}:zinemaker/art",
                "--collect-all",
                "pypdfium2_raw",
                "--collect-data",
                "reportlab",
                str(ROOT / "zine.py"),
            ],
            cwd=ROOT,
            check=True,
        )
        shutil.copy2(ROOT / "run.command", package / "run.command")
        (package / "Read me.txt").write_text(
            "Double-click run.command to open Goosnav Zine Maker in your browser.\n"
            "Choose Open folder in the editor, or choose Add essay to begin writing.\n"
            "Issue setup controls the title and page size. Export issue creates print and digital editions.\n"
            "Reopen the same comics folder to resume editing. Press Control-C in the launcher window to quit.\n"
            "This macOS build includes its runtime. It is ad-hoc signed and has not been notarized.\n"
        )
        notices(package / "Third-party notices")
        with (package / "checksums.sha256").open("w") as stream:
            for file in sorted(package.rglob("*")):
                if file.is_file() and file.name != "checksums.sha256":
                    with file.open("rb") as data:
                        digest = hashlib.file_digest(data, "sha256").hexdigest()
                    stream.write(f"{digest}  {file.relative_to(package)}\n")
        archive = (
            output / f"Goosnav-Zine-Maker-{version}-macOS-{platform.machine()}.zip"
        )
        result = work / "release.zip"
        subprocess.run(
            [
                "ditto",
                "-c",
                "-k",
                "--norsrc",
                "--keepParent",
                str(package),
                str(result),
            ],
            check=True,
        )
        result.replace(archive)
        print(archive)


if __name__ == "__main__":
    main()
