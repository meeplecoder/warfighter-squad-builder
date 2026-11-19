#!/bin/sh
# Upload the local card images (static/card_images) to the Fly volume at /data/card_images.
# Packs them into one archive, copies it with `fly ssh sftp`, unpacks it on the machine. Re-run after adding images.
#   usage: scripts/push_card_images.sh [fly app name]      (default: the app in fly.toml)
# The images are DVG's artwork: they stay out of git and out of the Docker image (see NOTICE.md).
set -eu
cd "$(dirname "$0")/.."
APP_ARG=""
[ $# -ge 1 ] && APP_ARG="-a $1"
SRC=static/card_images
[ -d "$SRC/en" ] || { echo "no images in $SRC" >&2; exit 1; }

ARCHIVE="$(mktemp /tmp/card_images.XXXXXX.tar.gz)"
trap 'rm -f "$ARCHIVE"' EXIT
tar -C "$SRC" --exclude=README.md -czf "$ARCHIVE" .
echo "archive: $(du -h "$ARCHIVE" | cut -f1)"

# shellcheck disable=SC2086
echo "put $ARCHIVE /data/card_images.tar.gz" | fly ssh sftp shell $APP_ARG
# shellcheck disable=SC2086
fly ssh console $APP_ARG -C "sh -c 'mkdir -p /data/card_images && tar -xzf /data/card_images.tar.gz -C /data/card_images && rm /data/card_images.tar.gz && chown -R app:app /data/card_images && du -sh /data/card_images'"
