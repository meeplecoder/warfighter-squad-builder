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
    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
