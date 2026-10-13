from flask import Blueprint, current_app, request, jsonify
from flask_login import current_user, login_required, login_user
from app import db, limiter, mailer, security
from app.auth import EMAIL_RE, _info, _lang, mail_password_changed
from app.models import Card, User, UserModule, now_utc
from app.i18n import _, normalize_lang

profile_bp = Blueprint('profile', __name__)


def _all_modules_with_owned(user):
    all_modules = [
        r[0] for r in
        Card.catalog().with_entities(Card.module).distinct().order_by(Card.module).all()
        if r[0]
    ]
    owned_set = {um.module for um in user.modules if um.owned}
    # Default is owned=True for modules with no row
    explicit_excluded = {um.module for um in user.modules if not um.owned}
    result = []
    for m in all_modules:
        if m in explicit_excluded:
            result.append({'module': m, 'owned': False})
        else:
            result.append({'module': m, 'owned': True})
    return result


@profile_bp.route('', methods=['GET'])
@profile_bp.route('/', methods=['GET'])
@login_required
def get_profile():
    return jsonify(
        user=current_user.to_dict(),
        modules=_all_modules_with_owned(current_user),
    )


@profile_bp.route('', methods=['PUT'])
@profile_bp.route('/', methods=['PUT'])
@login_required
def update_profile():
    data = request.get_json(silent=True) or {}
    if 'full_name' in data:
        current_user.full_name = (data['full_name'] or '').strip() or None
    if 'avatar_url' in data:
        current_user.avatar_url = (data['avatar_url'] or '').strip() or None
    if 'language' in data:
        if data['language'] and not normalize_lang(data['language']):
            return jsonify(error=_('Unsupported language.')), 400
        current_user.language = normalize_lang(data['language'])
    db.session.commit()
    return jsonify(user=current_user.to_dict())


@profile_bp.route('/password', methods=['PUT'])
@login_required
@limiter.limit('10 per hour', key_func=lambda: f'user:{current_user.id}')
def change_password():
    data = request.get_json(silent=True) or {}
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')
    user = current_user._get_current_object()

    if not security.verify_password(user, current_pw):
        return jsonify(error=_('Current password is incorrect.')), 400
    problem = security.password_problem(new_pw, user.username, user.email)
    if problem:
        return jsonify(error=problem), 400

    security.set_password(user, new_pw)
    security.revoke_sessions(user)          # signs out every other device …
    db.session.commit()
    remember = current_app.config.get('REMEMBER_COOKIE_NAME', 'remember_token') in request.cookies
    login_user(user, remember=remember)     # … and re-issues this one's cookies
    mail_password_changed(user)
    _info('password_changed', user)
    return jsonify(ok=True)


@profile_bp.route('/email', methods=['PUT'])
@login_required
@limiter.limit('5 per hour', key_func=lambda: f'user:{current_user.id}')
def change_email():
    """Takes effect only once the new address confirms (POST /email/confirm); the old one is told."""
    data = request.get_json(silent=True) or {}
    new_email = (data.get('new_email') or '').strip().lower()
    user = current_user._get_current_object()

    if not security.verify_password(user, data.get('current_password', '')):
        return jsonify(error=_('Current password is incorrect.')), 400
    if len(new_email) > 254 or not EMAIL_RE.match(new_email):
        return jsonify(error=_('A valid email is required.')), 400
    if new_email == user.email:
        return jsonify(error=_('That is already your email.')), 400

    with _lang(user.language):
        if User.query.filter_by(email=new_email).first():
            # Same response as success; only the owner of that address learns it is taken
            mailer.send(new_email, _('Email change attempt'), _(
                'Hello,\n\nSomeone asked to move a Warfighter Squad Builder account to this address, but it '
                'already belongs to an account. No change was made. If it was you, log in with this address instead.'))
        else:
            url = security.link('confirm-email', security.issue_token(user, 'change_email', new_email=new_email))
            mailer.send(new_email, _('Confirm your new email address'), _(
                'Hi {username},\n\nConfirm that this address should become the email of your Warfighter Squad '
                'Builder account:\n\n{link}\n\nThe link expires in 24 hours. If you did not ask for this, ignore '
                'this email.', username=user.username, link=url))
            mailer.send(user.email, _('Email change requested'), _(
                'Hi {username},\n\nSomeone asked to change the email of your Warfighter Squad Builder account to '
                '{new_email}. Nothing changes until the new address is confirmed.\n\nIf this was not you, reset '
                'your password now:\n\n{link}',
                username=user.username, new_email=new_email, link=security.link('forgot')))
    db.session.commit()
    _info('email_change_requested', user)
    return jsonify(ok=True, message=_('Check the new inbox to confirm the change.'))


@profile_bp.route('/email/confirm', methods=['POST'])
@limiter.limit('20 per hour')
def confirm_email_change():
    tok = security.valid_token((request.get_json(silent=True) or {}).get('token'), 'change_email')
    if not tok:
        return jsonify(error=_('This link is invalid or has expired.'), code='token_invalid'), 400
    user = tok.user
    if User.query.filter(User.email == tok.new_email, User.id != user.id).first():
        return jsonify(error=_('That email is already in use.')), 409
    security.use_token(tok)
    old_email, user.email = user.email, tok.new_email
    user.email_verified_at = now_utc()
    db.session.commit()
    with _lang(user.language):
        mailer.send(old_email, _('Your email was changed'), _(
            'Hi {username},\n\nThe email of your Warfighter Squad Builder account was changed to {new_email}.'
            '\n\nIf this was not you, contact the site administrator.',
            username=user.username, new_email=user.email))
    _info('email_changed', user)
    return jsonify(ok=True, email=user.email)


@profile_bp.route('/modules', methods=['PUT'])
@login_required
def update_modules():
    data = request.get_json(silent=True) or {}
    owned_list = data.get('owned_modules', [])

    all_modules = [
        r[0] for r in
        Card.catalog().with_entities(Card.module).distinct().all()
        if r[0]
    ]
    owned_set = set(owned_list)

    # Delete all existing module rows for this user
    UserModule.query.filter_by(user_id=current_user.id).delete()

    # Insert rows only for modules explicitly excluded
    for m in all_modules:
        if m not in owned_set:
            db.session.add(UserModule(user_id=current_user.id, module=m, owned=0))

    db.session.commit()
    return jsonify(ok=True, owned_count=len(owned_set))
