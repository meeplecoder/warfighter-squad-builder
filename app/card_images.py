"""Card image files: static/card_images/<lang>/<prefix>/<number>.<ext>, all lowercase
(e.g. es/w/w-001.jpg). Supported extensions: jpg, png, webp (first found wins).

Images are language dependent (printed text). A card shows the image in the request
language, falling back to English, then to any language that has one.
"""
import os

from app.i18n import DEFAULT_LANG, SUPPORTED_LANGS

EXTENSIONS = ('jpg', 'png', 'webp')


def rel_path(lang, number, ext='jpg'):
    """'<lang>/<prefix>/<number>.<ext>', lowercase."""
    n = number.lower()
    return f"{lang}/{n.split('-')[0]}/{n}.{ext}"


def image_path(images_dir, lang, number, ext='jpg'):
    return os.path.join(images_dir, *rel_path(lang, number, ext).split('/'))


def resolve(images_dir, number, lang):
    """rel_path of the first existing image: lang → en → others, each jpg → png → webp;
    None if no image."""
    order = [lang, DEFAULT_LANG] + [l for l in SUPPORTED_LANGS if l not in (lang, DEFAULT_LANG)]
    for l in order:
        for ext in EXTENSIONS:
            if os.path.isfile(image_path(images_dir, l, number, ext)):
                return rel_path(l, number, ext)
    return None
