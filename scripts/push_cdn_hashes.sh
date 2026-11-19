#!/bin/sh
# Load the card image CDN manifest into the production database (cards.cdn_hash) on the Fly machine.
# Copies the manifest to the volume with `fly ssh sftp`, runs scripts/load_cdn_hashes.py there, deletes the copy.
#   usage: scripts/push_cdn_hashes.sh /path/to/cards_cdn_manifest.json [fly app name]
# The manifest stays out of git and out of the Docker image.
set -eu
cd "$(dirname "$0")/.."
[ $# -ge 1 ] && [ -f "$1" ] || { echo "usage: $0 /path/to/cards_cdn_manifest.json [app]" >&2; exit 1; }
MANIFEST="$1"
APP_ARG=""
[ $# -ge 2 ] && APP_ARG="-a $2"

# shellcheck disable=SC2086
echo "put $MANIFEST /data/cards_cdn_manifest.json" | fly ssh sftp shell $APP_ARG
# shellcheck disable=SC2086
fly ssh console $APP_ARG -C "sh -c 'cd /app && python scripts/load_cdn_hashes.py /data/cards_cdn_manifest.json; rm -f /data/cards_cdn_manifest.json'"
