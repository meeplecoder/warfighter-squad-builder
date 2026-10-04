from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import Card, UserModule

profile_bp = Blueprint('profile', __name__)


def _all_modules_with_owned(user):
    all_modules = [
        r[0] for r in
        db.session.query(Card.module).distinct().order_by(Card.module).all()
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
    db.session.commit()
    return jsonify(user=current_user.to_dict())


@profile_bp.route('/password', methods=['PUT'])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')

    if not current_user.password_hash or not check_password_hash(current_user.password_hash, current_pw):
        return jsonify(error='Current password is incorrect.'), 400
    if len(new_pw) < 8:
        return jsonify(error='New password too short.'), 400

    current_user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    return jsonify(ok=True)


@profile_bp.route('/modules', methods=['PUT'])
@login_required
def update_modules():
    data = request.get_json(silent=True) or {}
    owned_list = data.get('owned_modules', [])

    all_modules = [
        r[0] for r in
        db.session.query(Card.module).distinct().all()
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
