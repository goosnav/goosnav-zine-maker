#!/bin/sh
set -eu
APP_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
export PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin"
if command -v uv >/dev/null 2>&1; then
    exec uv run --frozen --project "$APP_DIR" python "$APP_DIR/zine.py" "$@"
fi
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi
if ! "$APP_DIR/.venv/bin/python" -c 'import pypdfium2, reportlab, PIL, filelock, cv2, numpy' 2>/dev/null; then
    "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
fi
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/zine.py" "$@"
