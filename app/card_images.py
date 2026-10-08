"""Card image files: static/card_images/<lang>/<prefix>/<number>.jpg, all lowercase
(e.g. es/w/w-001.jpg).

Images are language dependent (printed text). A card shows the image in the request
language, falling back to English, then to any language that has one.
"""
import os

from app.i18n import DEFAULT_LANG, SUPPORTED_LANGS


def rel_path(lang, number):
    """'<lang>/<prefix>/<number>.jpg', lowercase."""
    n = number.lower()
    return f"{lang}/{n.split('-')[0]}/{n}.jpg"


def image_path(images_dir, lang, number):
    return os.path.join(images_dir, *rel_path(lang, number).split('/'))


def resolve_lang(images_dir, number, lang):
    """First language with an image for this card: lang → en → others; None if no image."""
    order = [lang, DEFAULT_LANG] + [l for l in SUPPORTED_LANGS if l not in (lang, DEFAULT_LANG)]
    for l in order:
        if os.path.isfile(image_path(images_dir, l, number)):
            return l
    return None
