"""Local accounts: registration with email verification, login, logout, password reset.
Design and threat model: spec/01_system.md §Authentication; contracts: spec/05_api.md."""
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user

from app import db, limiter, mailer
from app.i18n import _, get_lang, normalize_lang
from app.models import AuthToken, User, now_utc
from app import security
from app.roles import is_reserved_username

auth_bp = Blueprint('auth', __name__)

USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{3,30}$')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _json():
    return request.get_json(silent=True) or {}


def _field_key(*fields):
    """Rate-limit key from a request-body field (per account / per address, whatever the client IP)."""
    def key():
        data = _json()
        value = next((data.get(f) for f in fields if data.get(f)), '')
        return f'{fields[0]}:' + str(value).strip().lower()
    return key


def _find_by_login(login):
    login = (login or '').strip().lower()
    if not login:
        return None
    if '@' in login:
        return User.query.filter_by(email=login).first()
    return User.query.filter_by(username_lower=login).first()


def _info(event, user=None, **extra):
    current_app.logger.info('auth event=%s user=%s ip=%s %s', event, user.id if user else '-',
                            request.remote_addr, ' '.join(f'{k}={v}' for k, v in extra.items()))


# ---------------------------------------------------------------------------
# Emails (sent in the recipient's language)
# ---------------------------------------------------------------------------
@contextmanager
def _lang(lang):
    target = normalize_lang(lang) or get_lang()
    had, prev = 'lang' in g, g.get('lang')
    g.lang = target
    try:
        yield
    finally:
        if had:
            g.lang = prev
        else:
            g.pop('lang', None)


def mail_verify(user):
    url = security.link('verify', security.issue_token(user, 'verify_email'))
    with _lang(user.language):
        mailer.send(user.email, _('Confirm your email address'), _(
            'Hi {username},\n\nConfirm your email address to activate your Warfighter WWII - Squad Builder account:\n\n'
            '{link}\n\nThe link expires in 24 hours. If you did not sign up, ignore this email.',
            username=user.username, link=url))


def mail_signup_attempt(user):
    with _lang(user.language):
        mailer.send(user.email, _('Sign-up attempt with your email'), _(
            'Hi {username},\n\nSomeone tried to create a new Warfighter WWII - Squad Builder account with this email '
            'address, which already has an account (username: {username}).\n\nIf it was you, log in instead. '
            'Forgot your password? Reset it here:\n\n{link}\n\nIf it was not you, you can ignore this email.',
            username=user.username, link=security.link('forgot')))


def mail_reset(user):
    url = security.link('reset', security.issue_token(user, 'reset_password'))
    with _lang(user.language):
        mailer.send(user.email, _('Reset your password'), _(
            'Hi {username},\n\nWe received a request to reset your Warfighter WWII - Squad Builder password. '
            'Choose a new one here:\n\n{link}\n\nThe link expires in 30 minutes and works once. If you did not '
            'ask for this, ignore this email — your password stays the same.',
            username=user.username, link=url))


def mail_password_changed(user):
    with _lang(user.language):
        mailer.send(user.email, _('Your password was changed'), _(
            'Hi {username},\n\nThe password of your Warfighter WWII - Squad Builder account was just changed and your '
            'other sessions were signed out.\n\nIf this was not you, reset your password now:\n\n{link}',
            username=user.username, link=security.link('forgot')))


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------
def purge_unverified():
    """Delete sign-ups never confirmed within UNVERIFIED_ACCOUNT_DAYS (they cannot log in, so own nothing).
    Accounts without a password (imported squad owners) are never touched."""
    days = current_app.config['UNVERIFIED_ACCOUNT_DAYS']
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    stale = User.query.filter(User.email_verified_at.is_(None), User.password_hash.isnot(None),
                              User.created_at < cutoff).all()
    for user in stale:
        db.session.delete(user)
    return len(stale)


# ---------------------------------------------------------------------------
# Registration + email verification
# ---------------------------------------------------------------------------
@auth_bp.route('/register', methods=['POST'])
@limiter.limit('10 per hour')
def register():
    if not current_app.config['LOCAL_REGISTRATION_ENABLED']:
        return jsonify(error=_('Registration is closed.')), 403
    data = _json()
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    full_name = (data.get('full_name') or '').strip()[:100] or None
    language = normalize_lang(data.get('language'))

    if not USERNAME_RE.match(username):
        return jsonify(error=_('Username must be 3–30 chars, letters/digits/underscore only.')), 400
    if is_reserved_username(username):
        return jsonify(error=_('This username is reserved.')), 400
    if len(email) > 254 or not EMAIL_RE.match(email):
        return jsonify(error=_('A valid email is required.')), 400
    problem = security.password_problem(password, username, email)
    if problem:
        return jsonify(error=problem), 400

    purge_unverified()  # frees usernames held by abandoned sign-ups
    # Usernames are public (shown on squads), so a clash may be reported
    if User.query.filter_by(username_lower=username.lower()).first():
        return jsonify(error=_('Username already taken.')), 409

    # Hash before branching so both paths below take the same time
    password_hash = security.hash_password(password)
    existing = User.query.filter_by(email=email).first()
    if existing:
        # Never reveal that the address is registered: same response, the owner gets an email instead
        if existing.password_hash and not existing.email_verified_at:
            mail_verify(existing)
        elif existing.password_hash:
            mail_signup_attempt(existing)
        _info('register_existing_email', existing)
    else:
        user = User(username=username, email=email, password_hash=password_hash,
                    password_changed_at=now_utc(), full_name=full_name, language=language)
        db.session.add(user)
        db.session.flush()
        mail_verify(user)
        _info('register', user)
    db.session.commit()
    return jsonify(ok=True, message=_('Check your email to confirm your address, then log in.')), 201


@auth_bp.route('/verify', methods=['POST'])
@limiter.limit('20 per hour')
def verify_email():
    tok = security.valid_token(_json().get('token'), 'verify_email')
    if not tok:
        return jsonify(error=_('This link is invalid or has expired.'), code='token_invalid'), 400
    security.use_token(tok)
    if not tok.user.email_verified_at:
        tok.user.email_verified_at = now_utc()
    db.session.commit()
    _info('email_verified', tok.user)
    return jsonify(ok=True)


@auth_bp.route('/verify/resend', methods=['POST'])
@limiter.limit('5 per hour')
@limiter.limit('3 per hour', key_func=_field_key('login', 'email'))
def resend_verification():
    data = _json()
    user = _find_by_login(data.get('login') or data.get('email'))
    if user and user.password_hash and not user.email_verified_at:
        mail_verify(user)
        db.session.commit()
    return jsonify(ok=True, message=_('If that account is waiting for confirmation, we sent a new link.'))


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
_FAILED = dict(deduct_when=lambda response: response.status_code == 401)


@auth_bp.route('/login', methods=['POST'])
@limiter.limit('10 per minute; 50 per hour', **_FAILED)
@limiter.limit('10 per 15 minutes', key_func=_field_key('login', 'username'), **_FAILED)
def login():
    data = _json()
    user = _find_by_login(data.get('login') or data.get('username'))
    password = data.get('password') or ''

    if not security.verify_password(user, password):
        _info('login_failed', user)
        return jsonify(error=_('Invalid credentials.')), 401
    if user.disabled_at:
        _info('login_disabled', user)
        return jsonify(error=_('This account has been disabled. Contact the administrator.'), code='account_disabled'), 403
    if not user.email_verified_at:
        return jsonify(error=_('Please confirm your email address first. Check your inbox.'),
                       code='email_unverified'), 403

    if security.needs_rehash(user):
        user.password_hash = security.hash_password(password)
        db.session.commit()
    session.clear()  # no pre-login session data survives (fixation)
    login_user(user, remember=bool(data.get('remember')))
    _info('login', user)
    return jsonify(user=user.to_dict()), 200


@auth_bp.route('/logout', methods=['POST'])
def logout():
    logout_user()
    session.clear()
    return jsonify(ok=True), 200


@auth_bp.route('/logout-all', methods=['POST'])
@login_required
def logout_all():
    user = current_user._get_current_object()
    security.revoke_sessions(user)
    db.session.commit()
    logout_user()
    session.clear()
    _info('logout_all', user)
    return jsonify(ok=True), 200


@auth_bp.route('/me', methods=['GET'])
def me():
    if not current_user.is_authenticated:
        return jsonify(error=_('Not authenticated.')), 401
    return jsonify(user=current_user.to_dict()), 200


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------
@auth_bp.route('/password/forgot', methods=['POST'])
@limiter.limit('5 per hour')
@limiter.limit('3 per hour', key_func=_field_key('email'))
def forgot_password():
    email = (_json().get('email') or '').strip().lower()
    user = User.query.filter_by(email=email).first() if email else None
    if user and user.password_hash:  # imported owners (no password) cannot be claimed this way
        mail_reset(user)
        db.session.commit()
        _info('reset_requested', user)
    return jsonify(ok=True, message=_('If an account uses that address, we sent a reset link.'))


@auth_bp.route('/password/reset', methods=['POST'])
@limiter.limit('20 per hour')
def reset_password():
    data = _json()
    tok = security.valid_token(data.get('token'), 'reset_password')
    if not tok:
        return jsonify(error=_('This link is invalid or has expired.'), code='token_invalid'), 400
    user = tok.user
    password = data.get('password') or ''
    problem = security.password_problem(password, user.username, user.email)
    if problem:
        return jsonify(error=problem), 400  # token stays usable for another try

    security.use_token(tok)
    AuthToken.query.filter(AuthToken.user_id == user.id, AuthToken.purpose == 'reset_password',
                           AuthToken.used_at.is_(None)).delete()
    security.set_password(user, password)
    security.revoke_sessions(user)
    if not user.email_verified_at:
        user.email_verified_at = now_utc()  # the reset proved control of the address
    db.session.commit()
    mail_password_changed(user)
    _info('password_reset', user)
    return jsonify(ok=True, message=_('Password changed. You can now log in.'))
