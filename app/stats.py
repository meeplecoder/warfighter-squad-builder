"""Own, cookieless usage statistics: anonymous page-view counters and an admin-only report.

The browser reports each section change to POST /api/stats/hit; the admin report is GET /api/stats/report. Nothing personal is stored: only a per-day
counter per section, plus a daily salted hash of IP + user agent to count unique visitors (purged after 2 days).
Admin accounts and obvious bots are not counted.
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db, limiter, roles
from app.models import Campaign, Squad, StatHit, StatVisitor, User

stats_bp = Blueprint('stats', __name__)

ROUTES = ('cards', 'squads', 'builder', 'generator', 'campaigns', 'expansions', 'profile',
          'login', 'register', 'other')
BOT_RE = re.compile(r'bot|crawl|spider|slurp|curl|wget|python|httpclient|headless|preview|monitor|uptime', re.I)
MAX_DAYS = 365
VISITORS = '_visitors'          # pseudo-route holding the permanent unique-visitors count of each day


def _today():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _visitor_hash(day):
    ua = request.headers.get('User-Agent', '')
    raw = f"{current_app.config['SECRET_KEY']}|{day}|{request.remote_addr}|{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _bump(day, route):
    if StatHit.query.filter_by(day=day, route=route).update({StatHit.hits: StatHit.hits + 1}):
        return
    try:
        with db.session.begin_nested():
            db.session.add(StatHit(day=day, route=route, hits=1))
    except IntegrityError:                                            # lost a race: the row exists now
        StatHit.query.filter_by(day=day, route=route).update({StatHit.hits: StatHit.hits + 1})


@stats_bp.route('/hit', methods=['POST'])
@limiter.limit('300 per hour')
def hit():
    ua = request.headers.get('User-Agent', '')
    if not ua or BOT_RE.search(ua) or (current_user.is_authenticated and roles.is_admin(current_user)):
        return '', 204
    route = str((request.get_json(silent=True) or {}).get('route') or '')[:30]
    route = route if route in ROUTES else 'other'
    day = _today()
    try:
        _bump(day, route)
        try:
            with db.session.begin_nested():
                db.session.add(StatVisitor(day=day, vhash=_visitor_hash(day)))
            _bump(day, VISITORS)                                      # first hit of this visitor today
        except IntegrityError:
            pass                                                      # already counted today
        cutoff = (datetime.now(timezone.utc) - timedelta(days=2)).strftime('%Y-%m-%d')
        StatVisitor.query.filter(StatVisitor.day < cutoff).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()
    return '', 204


def _per_day(model, column, since):
    """Rows created per UTC day since `since` (the created_at columns are 'YYYY-MM-DDTHH:MM:SSZ' text),
    leaving out the admin account's own activity."""
    day = func.substr(column, 1, 10)
    q = db.session.query(day, func.count(model.id)).filter(day >= since)
    q = q.filter(model.username_lower != roles.ADMIN_USERNAME) if model is User else \
        q.filter(~model.user_id.in_(db.session.query(User.id).filter(User.username_lower == roles.ADMIN_USERNAME)))
    return dict(q.group_by(day).all())


@stats_bp.route('/report', methods=['GET'])
@roles.admin_required
def report():
    try:
        days = min(max(int(request.args.get('days', 30)), 1), MAX_DAYS)
    except ValueError:
        days = 30
    today = datetime.now(timezone.utc).date()
    labels = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    since = labels[0]
    per_day = {}
    for day, route, n in db.session.query(StatHit.day, StatHit.route, StatHit.hits).filter(StatHit.day >= since):
        d = per_day.setdefault(day, {'views': 0, 'visitors': 0})
        if route == VISITORS:
            d['visitors'] = n
        else:
            d['views'] += n
    signups = _per_day(User, User.created_at, since)
    squads = _per_day(Squad, Squad.created_at, since)
    series = [{'day': d, 'views': per_day.get(d, {}).get('views', 0), 'visitors': per_day.get(d, {}).get('visitors', 0),
               'signups': signups.get(d, 0), 'squads': squads.get(d, 0)} for d in labels]
    routes = [{'route': r, 'views': int(n)} for r, n in db.session.query(StatHit.route, func.sum(StatHit.hits))
              .filter(StatHit.day >= since, StatHit.route != VISITORS).group_by(StatHit.route)
              .order_by(func.sum(StatHit.hits).desc()).all()]
    return jsonify(days=days, series=series, routes=routes, totals={
        'users': User.query.filter(User.username_lower != roles.ADMIN_USERNAME).count(),
        'squads': sum(_per_day(Squad, Squad.created_at, '0000').values()),
        'campaigns': Campaign.query.filter(~Campaign.user_id.in_(
            db.session.query(User.id).filter(User.username_lower == roles.ADMIN_USERNAME))).count()})
