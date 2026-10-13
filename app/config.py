import os
from datetime import timedelta

# Absolute path to the project root (warfighter-squad-builder/)
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DEV_SECRET_KEY = 'dev-secret-key-CHANGE-ME'


def _flag(name, default):
    return os.environ.get(name, str(default)).lower() == 'true'


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', DEV_SECRET_KEY)
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

    # --- Auth (spec/01_system.md §Authentication) ---
    # Public origin used to build emailed links — never derived from the request Host header
    APP_BASE_URL = os.environ.get('APP_BASE_URL', '').rstrip('/')
    PASSWORD_MIN_LENGTH = int(os.environ.get('PASSWORD_MIN_LENGTH', '15'))   # NIST 800-63B-4, single factor
    PASSWORD_MAX_LENGTH = 128
    LOCAL_REGISTRATION_ENABLED = _flag('LOCAL_REGISTRATION_ENABLED', True)
    UNVERIFIED_ACCOUNT_DAYS = 7                         # unconfirmed sign-ups are deleted after this
    # Cookies: Secure everywhere except plain-http local development
    SESSION_COOKIE_SECURE = _flag('COOKIE_SECURE', not DEBUG)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    # Rate-limit counters live in process memory: run one process (threads are fine), see spec/01_system.md
    RATELIMIT_STORAGE_URI = 'memory://'
    # Number of reverse proxies in front of the app (for client IP + https scheme); 0 = none
    PROXY_FIX_HOPS = int(os.environ.get('PROXY_FIX_HOPS', '0'))

    # --- Outgoing mail (app/mailer.py) ---
    MAIL_BACKEND = os.environ.get('MAIL_BACKEND', 'console')   # console | resend | smtp | memory (tests)
    MAIL_FROM = os.environ.get('MAIL_FROM', 'Warfighter Squad Builder <no-reply@localhost>')
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')       # MAIL_BACKEND=resend
    MAIL_HOST = os.environ.get('MAIL_HOST', '')                 # MAIL_BACKEND=smtp
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_USE_SSL = _flag('MAIL_USE_SSL', False)         # implicit TLS (port 465); otherwise STARTTLS
