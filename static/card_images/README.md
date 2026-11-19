# Card images

    card_images/<lang>/<prefix>/<number>.jpg      e.g. es/w/w-001.jpg

All folder and file names lowercase.

- `<lang>`: `en`, `es` (see `SUPPORTED_LANGS` in `app/i18n.py`)
- `<prefix>`: card number before the dash (`W-001` → `w`)
- `<number>`: card number, lowercase (`w-001.jpg`); `.jpg` only

A card shows the image in the user's language, else English, else any language.
Re-run `scripts/import_cards.py` after adding images (sets `cards.has_image`).

Set the `CARD_IMAGES_DIR` environment variable to serve the images from another folder (same layout). In production
they live on the data volume (`/data/card_images`) and are uploaded with `scripts/push_card_images.sh`.
They are served by `/api/cards/images/...` to logged-in users only, and are never committed to git.
