#!/bin/sh
set -eu
APP_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -eq 0 ]; then
    SOURCE=$(osascript -e 'POSIX path of (choose folder with prompt "Choose the comics folder for your magazine")') || exit 0
    exec "$APP_DIR/run.sh" "$SOURCE"
fi
exec "$APP_DIR/run.sh" "$@"
