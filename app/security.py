"""Password policy/hashing and single-use emailed tokens (spec/01_system.md §Authentication)."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, has_request_context, request
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.i18n import _
from app.models import AuthToken, now_utc

TOKEN_TTL = {
    'verify_email': timedelta(hours=24),
    'reset_password': timedelta(minutes=30),
    'change_email': timedelta(hours=24),
}

# Hash of a random string: checked when the account does not exist so timing does not reveal it,
# and its method prefix ("scrypt:32768:8:1") tells whether a stored hash needs upgrading.
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))
_CURRENT_METHOD = _DUMMY_HASH.split('$', 1)[0]


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def password_problem(password, username='', email=''):
    """Error message if `password` violates the policy, else None. Length over composition rules:
    NIST SP 800-63B-4 requires 15+ characters when the password is the only factor."""
    cfg = current_app.config
    if len(password) < cfg['PASSWORD_MIN_LENGTH']:
        return _('Password must be at least {n} characters.', n=cfg['PASSWORD_MIN_LENGTH'])
    if len(password) > cfg['PASSWORD_MAX_LENGTH']:
        return _('Password must be at most {n} characters.', n=cfg['PASSWORD_MAX_LENGTH'])
    low = password.lower()
    personal = [w for w in (username.lower(), email.lower().split('@')[0]) if len(w) >= 4]
    if any(w in low for w in personal):
        return _('Password must not contain your username or email.')
    return None


def hash_password(password):
    return generate_password_hash(password)


def verify_password(user, password):
    """Constant-work check: hashes against a dummy when the user/hash is missing."""
    stored = user.password_hash if user and user.password_hash else None
    if len(password) > 1024:  # never feed huge inputs to the KDF
        check_password_hash(_DUMMY_HASH, '')
        return False
    ok = check_password_hash(stored or _DUMMY_HASH, password)
    return bool(stored) and ok


def needs_rehash(user):
    return not (user.password_hash or '').startswith(_CURRENT_METHOD + '$')


def set_password(user, password):
    user.password_hash = hash_password(password)
    user.password_changed_at = now_utc()


def revoke_sessions(user):
    """Invalidate every session and remember-me cookie of `user` (they embed session_version)."""
    user.session_version = (user.session_version or 1) + 1


# ---------------------------------------------------------------------------
# Single-use tokens
# ---------------------------------------------------------------------------
def _hash_token(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _ts(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def issue_token(user, purpose, new_email=None):
    """New token for `purpose`; any unused older one for the same user + purpose stops working."""
    AuthToken.query.filter_by(user_id=user.id, purpose=purpose, used_at=None).delete()
    raw = secrets.token_urlsafe(32)
    db.session.add(AuthToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=_hash_token(raw),
        new_email=new_email,
        expires_at=_ts(datetime.now(timezone.utc) + TOKEN_TTL[purpose]),
        request_ip=request.remote_addr if has_request_context() else None,
    ))
    return raw


def valid_token(raw, purpose):
    """The unused, unexpired AuthToken matching `raw` for `purpose`, else None. Call use_token() to spend it."""
    if not raw or not isinstance(raw, str) or len(raw) > 128:
        return None
    tok = AuthToken.query.filter_by(token_hash=_hash_token(raw)).first()
    if not tok or tok.purpose != purpose or tok.used_at or tok.expires_at < now_utc():
        return None
    return tok


def use_token(tok):
    tok.used_at = now_utc()


def link(path, raw_token=None):
    """Emailed link. Tokens sit after '#' so they never reach server logs or Referer headers."""
    url = f"{current_app.config['APP_BASE_URL']}/#/{path}"
    return f'{url}/{raw_token}' if raw_token else url
