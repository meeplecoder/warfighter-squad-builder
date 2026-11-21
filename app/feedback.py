"""Bug reports / feature requests sent from the header button (logged-in users only). They are stored in the
bug_reports table (admin list at GET /api/feedback) and also mailed to BUG_REPORT_EMAIL when that is set."""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app import db, limiter, mailer, roles
from app.i18n import _
from app.models import BugReport

feedback_bp = Blueprint('feedback', __name__)

KINDS = ('bug', 'ui', 'data', 'translation', 'performance', 'feature', 'other')
MAX_LEN = 4000


@feedback_bp.route('', methods=['POST'])
@limiter.limit('5 per hour')
@login_required
def submit():
    data = request.get_json(silent=True) or {}
    kind = data.get('kind')
    text = (data.get('text') or '').strip()
    if kind not in KINDS:
        return jsonify(error=_('Invalid report type.')), 400
    if len(text) < 10:
        return jsonify(error=_('Please describe the problem in a few words.')), 400
    if data.get('website'):                       # honeypot field: bots fill it, humans never see it
        return jsonify(ok=True)
    who = current_user.username
    body = (f"Type: {kind}\nUser: {who}\nLanguage: {request.headers.get('X-Lang', '')}\n"
            f"Page: {str(data.get('page') or '')[:300]}\nUser-Agent: {request.headers.get('User-Agent', '')[:200]}\n\n"
            f"{text[:MAX_LEN]}")
    db.session.add(BugReport(user_id=current_user.id, username=who, kind=kind, text=text[:MAX_LEN],
                             page=str(data.get('page') or '')[:300], language=request.headers.get('X-Lang', '')[:10],
                             user_agent=request.headers.get('User-Agent', '')[:200]))
    db.session.commit()
    to = current_app.config.get('BUG_REPORT_EMAIL')
    subject = f'[Squad Builder] {kind}: {text[:60]!r}'.replace('\n', ' ')
    if to:
        mailer.send(to, subject, body)
    return jsonify(ok=True)


@feedback_bp.route('', methods=['GET'])
@roles.admin_required
def list_reports():
    rows = BugReport.query.order_by(BugReport.created_at.desc(), BugReport.id.desc()).all()
    return jsonify(reports=[{'id': r.id, 'user_id': r.user_id, 'username': r.username, 'kind': r.kind, 'text': r.text,
                             'page': r.page, 'language': r.language, 'created_at': r.created_at} for r in rows])
