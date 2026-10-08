"""Card image files: static/card_images/<lang>/<prefix>/<number>.jpg

Images are language dependent (printed text). A card shows the image in the request
language, falling back to English, then to any language that has one.
"""
import os

from app.i18n import DEFAULT_LANG, SUPPORTED_LANGS


def prefix_of(number):
    return number.split('-')[0]


def image_path(images_dir, lang, number):
    return os.path.join(images_dir, lang, prefix_of(number), f'{number}.jpg')


def resolve_lang(images_dir, number, lang):
    """First language with an image for this card: lang → en → others; None if no image."""
    order = [lang, DEFAULT_LANG] + [l for l in SUPPORTED_LANGS if l not in (lang, DEFAULT_LANG)]
    for l in order:
        if os.path.isfile(image_path(images_dir, l, number)):
            return l
    return None
