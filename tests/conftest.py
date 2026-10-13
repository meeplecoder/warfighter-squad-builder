"""Test setup: a throw-away SQLite database filled from the fictional demo card set (examples/cards.sample.csv).

The environment is set BEFORE the app is imported (app.config reads it at import time).
"""
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_TMP = tempfile.mkdtemp(prefix='wf-test-')
os.environ.update({
    'DATABASE_URL': f'sqlite:///{_TMP}/test.db',
    'DEBUG': 'true',
    'MAIL_BACKEND': 'memory',
    'SECRET_KEY': 'test-secret-key-test-secret-key-12345',
})
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope='session')
def app():
    subprocess.run([sys.executable, 'scripts/import_cards.py', '--csv', 'examples/cards.sample.csv'],
                   cwd=ROOT, check=True, capture_output=True, env=os.environ.copy())
    from app import create_app, limiter
    application = create_app()
    limiter.enabled = False
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def login(app):
    """Return a function that logs a (new) verified user into a test client."""
    from app import db
    from app.models import User, now_utc
    from app.security import hash_password

    def _login(client, username='tester'):
        with app.app_context():
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username, email=f'{username}@example.com', password_hash=hash_password('x' * 20),
                            email_verified_at=now_utc())
                db.session.add(user)
                db.session.commit()
            uid = f'{user.id}:{user.session_version or 1}'
        with client.session_transaction() as sess:
            sess['_user_id'] = uid
            sess['_fresh'] = True
        return uid
    return _login


def card_id(app, number):
    from app.models import Card
    with app.app_context():
        return Card.query.filter_by(number=number).one().id
