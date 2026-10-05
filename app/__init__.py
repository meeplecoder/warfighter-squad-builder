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

    from app.models import User, CardAssociation, SquadObjective  # noqa: F401 — ensure tables are registered

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
        all_mods = [
            r[0] for r in
            db.session.query(Card.module).distinct().order_by(Card.module).all()
            if r[0]
        ]
        # Core Europe always first
        pinned = [m for m in all_mods if m == 'Core Europe']
        rest = [m for m in all_mods if m != 'Core Europe']
        return jsonify(modules=pinned + rest)

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

            try:
                conn.execute(db.text(
                    "ALTER TABLE cards ADD COLUMN hostile_spawn_table TEXT"
                ))
                conn.commit()
            except Exception:
                pass  # Column already exists

            try:
                conn.execute(db.text(
                    "ALTER TABLE cards ADD COLUMN health_actions_table TEXT"
                ))
                conn.commit()
            except Exception:
                pass  # Column already exists

            try:
                conn.execute(db.text(
                    "ALTER TABLE cards ADD COLUMN hardy_markers TEXT"
                ))
                conn.commit()
            except Exception:
                pass  # Column already exists

            try:
                conn.execute(db.text(
                    "ALTER TABLE cards ADD COLUMN weapon_range_table TEXT"
                ))
                conn.commit()
            except Exception:
                pass  # Column already exists

            try:
                conn.execute(db.text(
                    "ALTER TABLE cards ADD COLUMN weapon_mode_table TEXT"
                ))
                conn.commit()
            except Exception:
                pass  # Column already exists

            # Migrate single objective_card_id → squad_objectives junction table
            try:
                conn.execute(db.text("""
                    CREATE TABLE IF NOT EXISTS squad_objectives (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        squad_id INTEGER NOT NULL REFERENCES squads(id) ON DELETE CASCADE,
                        card_id INTEGER NOT NULL REFERENCES cards(id),
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        UNIQUE (squad_id, card_id)
                    )
                """))
                conn.commit()
                # Populate from existing objective_card_id where not already migrated
                squads_with_obj = conn.execute(db.text(
                    "SELECT id, objective_card_id FROM squads WHERE objective_card_id IS NOT NULL"
                )).fetchall()
                for row in squads_with_obj:
                    try:
                        conn.execute(db.text(
                            "INSERT OR IGNORE INTO squad_objectives (squad_id, card_id, sort_order) VALUES (:sid, :cid, 0)"
                        ), {'sid': row[0], 'cid': row[1]})
                    except Exception:
                        pass
                conn.commit()
            except Exception:
                pass

            # Add soldier_xp column and populate from notes (XP lines)
            try:
                conn.execute(db.text(
                    "ALTER TABLE cards ADD COLUMN soldier_xp INTEGER NOT NULL DEFAULT 0"
                ))
                conn.commit()
                import re as _re2
                rows2 = conn.execute(db.text(
                    "SELECT id, notes FROM cards WHERE card_type='Soldier' AND notes IS NOT NULL"
                )).fetchall()
                updates2 = []
                for row in rows2:
                    for line in (row[1] or '').split('\n'):
                        m = _re2.match(r'^(\d+)\s+XP\.?$', line.strip(), _re2.IGNORECASE)
                        if m:
                            updates2.append({'xp': int(m.group(1)), 'id': row[0]})
                            break
                for upd in updates2:
                    conn.execute(db.text(
                        "UPDATE cards SET soldier_xp = :xp WHERE id = :id"
                    ), upd)
                conn.commit()
            except Exception:
                pass  # Column already exists

            # Add combat_xp column and populate it from notes (CX lines)
            try:
                conn.execute(db.text(
                    "ALTER TABLE cards ADD COLUMN combat_xp INTEGER NOT NULL DEFAULT 0"
                ))
                conn.commit()
                import re as _re
                rows = conn.execute(db.text(
                    "SELECT id, notes FROM cards WHERE card_type='Soldier' AND notes IS NOT NULL"
                )).fetchall()
                updates = []
                for row in rows:
                    for line in (row[1] or '').split('\n'):
                        m = _re.match(r'^(\d+)\s+CX\.?$', line.strip(), _re.IGNORECASE)
                        if m:
                            updates.append({'cx': int(m.group(1)), 'id': row[0]})
                            break
                if updates:
                    for upd in updates:
                        conn.execute(db.text(
                            "UPDATE cards SET combat_xp = :cx WHERE id = :id"
                        ), upd)
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
