"""Admin-only user management: list, view, edit, enable/disable and delete accounts.

Passwords are never returned — the admin can only set a new one. The `admin` account itself cannot be renamed,
disabled or deleted here. All routes are guarded by roles.admin_required.
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import func

from app import db, mailer, roles, security
from app.auth import EMAIL_RE, USERNAME_RE, _info, mail_password_changed
from app.i18n import _, normalize_lang
from app.models import (Campaign, CampaignMission, Card, CardTranslation, Squad, SquadComment, SquadLike, User,
                        now_utc)

admin_users_bp = Blueprint('admin_users', __name__)

STATUSES = ('pending', 'enabled', 'disabled')


def _counts(model, user_ids):
    rows = db.session.query(model.user_id, func.count(model.id)).filter(model.user_id.in_(user_ids)) \
        .group_by(model.user_id).all()
    return dict(rows)


def _row(user, squads=0, campaigns=0):
    return {
        'id': user.id, 'username': user.username, 'full_name': user.full_name, 'email': user.email,
        'status': user.status, 'role': user.role, 'created_at': user.created_at,
        'squads': squads, 'campaigns': campaigns,
    }


def _detail(user):
    d = _row(user, Squad.query.filter_by(user_id=user.id).count(), Campaign.query.filter_by(user_id=user.id).count())
    d.update(avatar_url=user.avatar_url, language=user.language, email_verified_at=user.email_verified_at,
             disabled_at=user.disabled_at, password_changed_at=user.password_changed_at,
             has_password=bool(user.password_hash))           # never the hash itself
    return d


@admin_users_bp.route('', methods=['GET'])
@admin_users_bp.route('/', methods=['GET'])
@roles.admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc(), User.id.desc()).all()
    ids = [u.id for u in users]
    squads, campaigns = _counts(Squad, ids), _counts(Campaign, ids)
    return jsonify(users=[_row(u, squads.get(u.id, 0), campaigns.get(u.id, 0)) for u in users])


@admin_users_bp.route('/<int:user_id>', methods=['GET'])
@roles.admin_required
def get_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error=_('User not found.')), 404
    return jsonify(user=_detail(user))


def _apply_status(user, status):
    if status == 'disabled':
        if not user.disabled_at:
            user.disabled_at = now_utc()
        security.revoke_sessions(user)                    # signs the user out everywhere
    elif status == 'enabled':
        user.disabled_at = None
        user.email_verified_at = user.email_verified_at or now_utc()      # enabling a pending account approves it
    elif status == 'pending':
        user.disabled_at = None
        user.email_verified_at = None


@admin_users_bp.route('/<int:user_id>', methods=['PUT', 'PATCH'])
@roles.admin_required
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error=_('User not found.')), 404
    data = request.get_json(silent=True) or {}
    is_admin_account = roles.role_of(user) == roles.ROLE_ADMIN

    if 'username' in data:
        username = (data['username'] or '').strip()
        if username != user.username:
            if is_admin_account:
                return jsonify(error=_('The admin account cannot be renamed.')), 400
            if not USERNAME_RE.match(username):
                return jsonify(error=_('Username must be 3–30 chars, letters/digits/underscore only.')), 400
            if roles.is_reserved_username(username):
                return jsonify(error=_('This username is reserved.')), 400
            if User.query.filter(User.username_lower == username.lower(), User.id != user.id).first():
                return jsonify(error=_('Username already taken.')), 409
            user.username = username
    if 'email' in data:
        email = (data['email'] or '').strip().lower()
        if email != user.email:
            if len(email) > 254 or not EMAIL_RE.match(email):
                return jsonify(error=_('A valid email is required.')), 400
            if User.query.filter(User.email == email, User.id != user.id).first():
                return jsonify(error=_('That email is already in use.')), 409
            user.email = email
    if 'full_name' in data:
        user.full_name = (data['full_name'] or '').strip()[:100] or None
    if 'avatar_url' in data:
        user.avatar_url = (data['avatar_url'] or '').strip()[:500] or None
    if 'language' in data:
        if data['language'] and not normalize_lang(data['language']):
            return jsonify(error=_('Unsupported language.')), 400
        user.language = normalize_lang(data['language'])
    if 'status' in data and data['status'] != user.status:
        if data['status'] not in STATUSES:
            return jsonify(error=_('Invalid status.')), 400
        if is_admin_account:
            return jsonify(error=_('The admin account cannot be disabled.')), 400
        _apply_status(user, data['status'])

    password = data.get('password')
    if password:
        problem = security.password_problem(password, user.username, user.email)
        if problem:
            return jsonify(error=problem), 400
        security.set_password(user, password)
        security.revoke_sessions(user)
        if user.id != current_user.id and user.email_verified_at:
            mail_password_changed(user)

    db.session.commit()
    _info('admin_user_updated', user, by=current_user.id, password=bool(password))
    return jsonify(user=_detail(user))


@admin_users_bp.route('/<int:user_id>', methods=['DELETE'])
@roles.admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify(error=_('User not found.')), 404
    if roles.role_of(user) == roles.ROLE_ADMIN:
        return jsonify(error=_('The admin account cannot be deleted.')), 400

    # SQLite foreign-key enforcement is off, so unlink and clean up by hand (same as deleting a squad/campaign)
    squad_ids = [s.id for s in Squad.query.filter_by(user_id=user.id).all()]
    mission_ids = [s.mission_card_id for s in Squad.query.filter_by(user_id=user.id).all()]
    for c in Campaign.query.filter_by(user_id=user.id).all():
        mission_ids += [m.mission_card_id for m in c.missions]
        db.session.delete(c)
    if squad_ids:
        Squad.query.filter(Squad.parent_squad_id.in_(squad_ids)).update({Squad.parent_squad_id: None}, synchronize_session=False)
        CampaignMission.query.filter(CampaignMission.squad_id.in_(squad_ids)).update(
            {CampaignMission.squad_id: None}, synchronize_session=False)
    # Likes the user gave to other people's squads: keep the counters right
    liked = [l.squad_id for l in SquadLike.query.filter_by(user_id=user.id).all()]
    CardTranslation.query.filter_by(updated_by=user.id).update({CardTranslation.updated_by: None})
    Card.query.filter_by(owner_user_id=user.id).update({Card.owner_user_id: None})
    username = user.username
    db.session.delete(user)                    # squads, likes, comments, modules, tokens cascade via the ORM
    db.session.flush()
    from app import custom_missions
    custom_missions.purge(mission_ids)
    for sid in set(liked) - set(squad_ids):
        squad = db.session.get(Squad, sid)
        if squad:
            squad.likes_count = SquadLike.query.filter_by(squad_id=sid).count()
    db.session.commit()
    _info('admin_user_deleted', None, by=current_user.id, deleted=username)
    return jsonify(ok=True)
