"""Launch from any working directory, optionally with explicit source and output."""

import argparse
import sys
from pathlib import Path

from zinemaker.export import publish
from zinemaker.project import Project
from zinemaker.server import serve


def main():
    parser = argparse.ArgumentParser(
        description="Build a print and digital magazine from a comics folder."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        type=Path,
        help="folder to open immediately (default: choose in the editor)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="parent folder for Goosnav Zine and all generated work",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="scan new files and export the issue without opening the editor",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="print the editor URL without opening it",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="local port (default: automatically selected)",
    )
    args = parser.parse_args()
    project = None
    if args.folder or args.export or args.output:
        project = Project(args.folder or Path.cwd(), args.output)
    if args.export:
        for warning in project.warnings:
            print(warning, file=sys.stderr)
        print(publish(project, project.data))
    else:
        serve(project, args.port, not args.no_browser)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as e:
        sys.exit(f"Goosnav Zine Maker: {e}")
