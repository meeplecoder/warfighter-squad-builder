import os
from flask import Flask, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__, static_folder='../static', static_url_path='/static')
    app.config.from_object('app.config.Config')

    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(_base, 'data'), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = None  # API-only; return 401 instead of redirect

    from app.models import User, CardAssociation  # noqa: F401 — ensure table is registered

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify(error='Not authenticated.'), 401

    from app.auth import auth_bp
    from app.cards import cards_bp
    from app.squads import squads_bp
    from app.profile import profile_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(cards_bp, url_prefix='/api/cards')
    app.register_blueprint(squads_bp, url_prefix='/api/squads')
    app.register_blueprint(profile_bp, url_prefix='/api/profile')

    @app.route('/api/modules')
    def get_modules():
        from app.models import Card
        modules = [
            r[0] for r in
            db.session.query(Card.module).distinct().order_by(Card.module).all()
            if r[0]
        ]
        return jsonify(modules=modules)

    @app.route('/api/nations')
    def get_nations():
        from app.models import Card
        from app.utils import normalize_nation
        raw = [r[0] for r in db.session.query(Card.nation).distinct().all() if r[0]]
        base_set = sorted({normalize_nation(n) for n in raw})
        return jsonify(nations=base_set)

    with app.app_context():
        db.create_all()
        # Safe migration: add status column if it doesn't exist yet
        with db.engine.connect() as conn:
            try:
                conn.execute(db.text(
                    "ALTER TABLE squads ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'"
                ))
                conn.commit()
            except Exception:
                pass  # Column already exists

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_spa(path):
        if path.startswith('api/') or path.startswith('static/'):
            from flask import abort
            abort(404)
        return send_from_directory('../static', 'index.html')

    return app
