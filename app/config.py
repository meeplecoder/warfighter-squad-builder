import os

# Absolute path to the project root (warfighter-squad-builder/)
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-CHANGE-ME')
    _raw_db = os.environ.get('DATABASE_URL', '')
    SQLALCHEMY_DATABASE_URI = (
        _raw_db if _raw_db and not _raw_db.startswith('sqlite:///data/')
        else f"sqlite:///{os.path.join(_BASE, 'data', 'warfighter.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CARDS_CSV = os.environ.get('CARDS_CSV', os.path.join(_BASE, '..', 'cards2.csv'))
    CARD_IMAGES_DIR = os.path.join(_BASE, 'static', 'card_images')
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
    # Card images: CARD_IMAGES_DIR/<lang>/<prefix>/<number>.<jpg|png|webp>, lowercase (see app/card_images.py)
    # Tabletop Simulator export: public base URL holding card images as <lang>/<prefix>/<number>.jpg
    # (same layout as static/card_images). TTS cannot log in, so the app's own image route won't work.
    TTS_IMAGE_BASE_URL = os.environ.get('TTS_IMAGE_BASE_URL', '')
    TTS_CARD_BACK_URL = os.environ.get('TTS_CARD_BACK_URL', '')
