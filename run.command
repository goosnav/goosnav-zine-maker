#!/bin/sh
set -eu
APP_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$APP_DIR/runtime/Goosnav Zine Maker" ]; then
    exec "$APP_DIR/runtime/Goosnav Zine Maker" "$@"
fi
exec "$APP_DIR/run.sh" "$@"
