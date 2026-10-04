import re
from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User

auth_bp = Blueprint('auth', __name__)

USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]{3,30}$')


def user_obj(user):
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': user.full_name,
        'avatar_url': user.avatar_url,
        'created_at': user.created_at,
    }


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    full_name = (data.get('full_name') or '').strip() or None

    if not USERNAME_RE.match(username):
        return jsonify(error='Username must be 3–30 chars, letters/digits/underscore only.'), 400
    if not email or '@' not in email:
        return jsonify(error='A valid email is required.'), 400
    if len(password) < 8:
        return jsonify(error='Password must be at least 8 characters.'), 400

    if User.query.filter_by(username=username).first():
        return jsonify(error='Username already taken.'), 409
    if User.query.filter_by(email=email).first():
        return jsonify(error='Email already registered.'), 409

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        full_name=full_name,
    )
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify(user=user_obj(user)), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    user = User.query.filter_by(username=username).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify(error='Invalid credentials.'), 401

    login_user(user, remember=True)
    return jsonify(user=user_obj(user)), 200


@auth_bp.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return jsonify(ok=True), 200


@auth_bp.route('/me', methods=['GET'])
def me():
    if not current_user.is_authenticated:
        return jsonify(error='Not authenticated.'), 401
    return jsonify(user=user_obj(current_user)), 200
