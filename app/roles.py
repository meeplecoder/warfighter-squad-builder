"""
Roles and access control.

Two roles exist:
  * admin — the single account whose username is `admin` (case-insensitive). Can edit/publish/delete any squad and
            campaign, see every draft, and use the admin-only views (today: the card-translation editor).
  * user  — everybody else: manages only their own squads and campaigns.

The role is DERIVED from the username, never from a stored flag, so it cannot be granted by editing data or by
signing up: the name `admin` is reserved at registration (RESERVED_USERNAMES) and the account is created from the
command line (scripts/create_admin.py). No other module should compare usernames itself — use the helpers here.
"""
from functools import wraps

from flask import jsonify
from flask_login import current_user

from app.i18n import _

ADMIN_USERNAME = 'admin'
ROLE_ADMIN, ROLE_USER = 'admin', 'user'
RESERVED_USERNAMES = frozenset({ADMIN_USERNAME})        # lower-case; refused by /api/auth/register


def role_of(user):
    """'admin' for the admin account, 'user' for everybody else (and for anonymous visitors)."""
    if user is not None and getattr(user, 'is_authenticated', True) and \
            (getattr(user, 'username_lower', None) or '').lower() == ADMIN_USERNAME:
        return ROLE_ADMIN
    return ROLE_USER


def is_admin(user=None):
    """True when `user` (default: the current request's user) is the admin account."""
    user = current_user if user is None else user
    return bool(user is not None and getattr(user, 'is_authenticated', False) and role_of(user) == ROLE_ADMIN)


def can_manage(owner_id, user=None):
    """May `user` edit / publish / delete something owned by `owner_id`? The owner and the admin may."""
    user = current_user if user is None else user
    return bool(user is not None and getattr(user, 'is_authenticated', False)
                and (user.id == owner_id or is_admin(user)))


def is_reserved_username(username):
    return (username or '').strip().lower() in RESERVED_USERNAMES


def resolve_owner(data):
    """Owner of a squad / campaign being created: (user, None) or (None, (json response, status)).

    The request body may carry `owner` (a username). Without it, or naming the caller, the owner is the session
    user. Naming anybody else is for the admin only (everyone else gets 403). The admin may name an account that
    does not exist yet: it is created without a password ('reserved': nobody can log in as it, like the owners of
    imported squads), so the name is held for its real author."""
    from app import db
    from app.auth import USERNAME_RE
    from app.models import User
    name = data.get('owner')
    name = name.strip() if isinstance(name, str) else ''
    if not name or name.lower() == (current_user.username_lower or '').lower():
        return current_user._get_current_object(), None
    if not is_admin():
        return None, (jsonify(error=_('Only the admin can create content for another owner.')), 403)
    user = User.query.filter_by(username_lower=name.lower()).first()
    if not user:
        if not USERNAME_RE.match(name):
            return None, (jsonify(error=_('Username must be 3–30 chars, letters/digits/underscore only.')), 400)
        user = User(username=name, email=f'{name.lower()}@community.local', password_hash=None, full_name=name)
        db.session.add(user)
        db.session.flush()
    return user, None


def admin_required(fn):
    """Route guard: 401 when not logged in, 403 for any non-admin account."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error=_('Not authenticated.')), 401
        if not is_admin(current_user):
            return jsonify(error=_('Admin only.')), 403
        return fn(*args, **kwargs)
    return wrapper
