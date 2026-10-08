# Card images

    card_images/<lang>/<prefix>/<number>.jpg

- `<lang>`: `en`, `es` (see `SUPPORTED_LANGS` in `app/i18n.py`)
- `<prefix>`: card number before the dash (`W-001` → `W`)
- `.jpg` only

A card shows the image in the user's language, else English, else any language.
Re-run `scripts/import_cards.py` after adding images (sets `cards.has_image`).
