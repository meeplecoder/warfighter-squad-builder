#!/bin/sh
# Container start-up: prepare /data, load the cards when needed, then run gunicorn.
#   SKIP_CARD_IMPORT=1   never import the cards automatically
#   CARDS_CSV=path       CSV to import (default cards/warfighter_cards.csv); re-imported on start when it or the importer changed
#   CARD_IMAGES_DIR      where the card images are served from (set it to /data/card_images to keep them on the volume)
#   PORT                 listen port (default 8080)
set -e

# Started as root (the usual case): fix the volume's ownership, then re-run this script as the 'app' user
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data && chown -R app:app /data
    exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

CSV="${CARDS_CSV:-cards/warfighter_cards.csv}"
STAMP="/data/.cards_csv.sha256"

if [ -z "$SKIP_CARD_IMPORT" ] && [ -f "$CSV" ]; then
    # Fingerprint = the CSV + the importer code, so a deploy re-imports when either changed (e.g. a new card type is loaded)
    SUM="$(cat "$CSV" scripts/import_cards.py scripts/parse_associations.py app/utils.py | sha256sum | cut -d' ' -f1)"
    if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$SUM" ]; then
        echo "entrypoint: importing cards from $CSV"
        python scripts/import_cards.py --csv "$CSV"
        echo "$SUM" > "$STAMP"
    fi
fi

# One process, several threads: rate-limit counters and SQLite both assume a single instance
exec gunicorn -w 1 --threads 4 -b "0.0.0.0:${PORT:-8080}" --access-logfile - run:app
