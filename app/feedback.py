"""Bug reports / feature requests sent from the header button (logged-in users only). They are stored in the
bug_reports table (admin list at GET /api/feedback) and also mailed to BUG_REPORT_EMAIL when that is set."""
import json
import urllib.parse
import urllib.request

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from app import db, limiter, mailer, roles
from app.i18n import _
from app.models import BUG_STATUSES, BugReport

feedback_bp = Blueprint('feedback', __name__)

KINDS = ('bug', 'ui', 'data', 'translation', 'performance', 'feature', 'other')
MAX_LEN = 4000
TURNSTILE_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def _turnstile_ok(token):
    """Verify a Turnstile token server-side. No secret configured = captcha disabled."""
    secret = current_app.config.get('TURNSTILE_SECRET_KEY')
    if not secret:
        return True
    if not token:
        return False
    data = urllib.parse.urlencode({'secret': secret, 'response': token, 'remoteip': request.remote_addr or ''}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TURNSTILE_URL, data=data), timeout=5) as r:
            return bool(json.load(r).get('success'))
    except Exception:
        current_app.logger.exception('Turnstile verification failed')
        return False


@feedback_bp.route('/captcha', methods=['GET'])
def captcha_config():
    return jsonify(site_key=current_app.config.get('TURNSTILE_SITE_KEY') or '')


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
    if not _turnstile_ok(data.get('captcha')):
        return jsonify(error=_('Captcha check failed. Please try again.')), 400
    if data.get('website'):                       # honeypot field: bots fill it, humans never see it
        return jsonify(ok=True)
    who = current_user.username
    body = (f"Type: {kind}\nUser: {who}\nLanguage: {request.headers.get('X-Lang', '')}\n"
            f"Page: {str(data.get('page') or '')[:300]}\nUser-Agent: {request.headers.get('User-Agent', '')[:200]}\n\n"
            f"{text[:MAX_LEN]}")
    report = BugReport(user_id=current_user.id, username=who, kind=kind, text=text[:MAX_LEN],
                             page=str(data.get('page') or '')[:300], language=request.headers.get('X-Lang', '')[:10],
                             user_agent=request.headers.get('User-Agent', '')[:200])
    db.session.add(report)
    db.session.commit()
    to = current_app.config.get('BUG_REPORT_EMAIL')
    subject = f'[Squad Builder] #{report.id} {kind}: {text[:60]!r}'.replace('\n', ' ')
    if to:
        mailer.send(to, subject, f'Report: #{report.id}\n' + body)
    return jsonify(ok=True, id=report.id)


@feedback_bp.route('', methods=['GET'])
@roles.admin_required
def list_reports():
    rows = BugReport.query.order_by(BugReport.created_at.desc(), BugReport.id.desc()).all()
    return jsonify(reports=[{'id': r.id, 'user_id': r.user_id, 'username': r.username, 'kind': r.kind, 'text': r.text,
                             'page': r.page, 'language': r.language, 'status': r.status, 'created_at': r.created_at}
                            for r in rows])


@feedback_bp.route('/<int:report_id>', methods=['PUT'])
@roles.admin_required
def set_status(report_id):
    report = db.session.get(BugReport, report_id)
    if report is None:
        return jsonify(error=_('Report not found.')), 404
    status = (request.get_json(silent=True) or {}).get('status')
    if status not in BUG_STATUSES:
        return jsonify(error=_('Invalid status.')), 400
    report.status = status
    db.session.commit()
    return jsonify(ok=True, id=report.id, status=report.status)
