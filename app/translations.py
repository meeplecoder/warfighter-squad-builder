"""Owner-only translation editor API (users.is_admin). See spec/07_i18n.md §4.3."""
from functools import wraps

from flask import Blueprint, request, jsonify
from flask_login import current_user
from sqlalchemy import or_, func

from app import db, i18n
from app.i18n import _
from app.models import Card, CardTranslation
from app import translation_io

translations_bp = Blueprint('translations', __name__)

STATUS_FILTERS = ('missing', 'stale', 'draft', 'reviewed')


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error=_('Not authenticated.')), 401
        if not current_user.is_admin:
            return jsonify(error=_('Admin only.')), 403
        return fn(*args, **kwargs)
    return wrapper


def _target_lang():
    lang = i18n.normalize_lang(request.args.get('lang') or (request.get_json(silent=True) or {}).get('lang'))
    if not lang or lang == i18n.DEFAULT_LANG:
        return None
    return lang


def _card_status(card, rows):
    """missing > stale > draft > reviewed. Notes only required when the card has notes."""
    needed = ['name'] + (['notes'] if card.notes else [])
    if any(f not in rows for f in needed):
        return 'missing'
    if any(r.stale for r in rows.values()):
        return 'stale'
    if any(r.status != 'reviewed' for r in rows.values()):
        return 'draft'
    return 'reviewed'


def _rows_by_card(lang, numbers=None):
    q = CardTranslation.query.filter_by(lang=lang)
    if numbers is not None:
        q = q.filter(CardTranslation.card_number.in_(numbers))
    out = {}
    for r in q.all():
        out.setdefault(r.card_number, {})[r.field] = r
    return out


def _row_dict(r):
    if not r:
        return None
    return {'value': r.value, 'status': r.status, 'stale': bool(r.stale), 'updated_at': r.updated_at}


def _item(card, rows):
    obj = card.to_card_object()
    return {
        'id': card.id,
        'number': card.number,
        'card_type': card.card_type,
        'card_subtype': card.card_subtype,
        'module': card.module,
        'image_url': obj['image_url'],
        'name_en': card.name,
        'notes_en': card.notes,
        'status': _card_status(card, rows),
        'translations': {f: _row_dict(rows.get(f)) for f in i18n.CARD_FIELDS},
    }


@translations_bp.route('', methods=['GET'])
@admin_required
def list_translations():
    lang = _target_lang()
    if not lang:
        return jsonify(error=_('Unsupported language.')), 400
    card_type = request.args.get('type', '').strip()
    module = request.args.get('module', '').strip()
    status = request.args.get('status', '').strip()
    q = request.args.get('q', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 25))))

    query = Card.query
    if request.args.get('number'):
        query = query.filter(Card.number == request.args['number'])
    if card_type:
        query = query.filter(Card.card_type == card_type)
    if module:
        query = query.filter(Card.module == module)
    if q:
        like = f'%{i18n.fold(q)}%'
        translated = (db.session.query(CardTranslation.card_number)
                      .filter(CardTranslation.lang == lang, func.fold(CardTranslation.value).like(like)))
        query = query.filter(or_(func.fold(Card.name).like(like), func.fold(Card.notes).like(like),
                                 Card.number.ilike(f'%{q}%'), Card.number.in_(translated)))
    cards = query.order_by(Card.number).all()
    rows = _rows_by_card(lang)
    items = [(c, rows.get(c.number, {})) for c in cards]
    if status in STATUS_FILTERS:
        items = [(c, r) for c, r in items if _card_status(c, r) == status]

    total = len(items)
    page_items = items[(page - 1) * per_page: page * per_page]
    return jsonify(
        items=[_item(c, r) for c, r in page_items],
        total=total, page=page, per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@translations_bp.route('/stats', methods=['GET'])
@admin_required
def stats():
    lang = _target_lang()
    if not lang:
        return jsonify(error=_('Unsupported language.')), 400
    rows = _rows_by_card(lang)
    total = {s: 0 for s in STATUS_FILTERS}
    by_type = {}
    for c in Card.query.all():
        st = _card_status(c, rows.get(c.number, {}))
        total[st] += 1
        by_type.setdefault(c.card_type, {s: 0 for s in STATUS_FILTERS})[st] += 1
    return jsonify(lang=lang, total=total, by_type=by_type)


@translations_bp.route('/<number>', methods=['PUT'])
@admin_required
def save_translation(number):
    data = request.get_json(silent=True) or {}
    lang = _target_lang()
    if not lang:
        return jsonify(error=_('Unsupported language.')), 400
    card = Card.query.filter_by(number=number).first()
    if not card:
        return jsonify(error=_('Card not found.')), 404
    status = data.get('status', 'reviewed')
    if status not in translation_io.STATUSES:
        return jsonify(error=_('Invalid status.')), 400
    for field in i18n.CARD_FIELDS:
        if field in data:
            translation_io.upsert(card, lang, field, data[field], status, user_id=current_user.id)
    db.session.commit()
    i18n.invalidate_cache()
    return jsonify(item=_item(card, _rows_by_card(lang, [card.number]).get(card.number, {})))


@translations_bp.route('/export', methods=['GET'])
@admin_required
def export():
    lang = _target_lang()
    if not lang:
        return jsonify(error=_('Unsupported language.')), 400
    resp = jsonify(translation_io.export_entries(lang, request.args.get('status')))
    resp.headers['Content-Disposition'] = f'attachment; filename=card_translations.{lang}.json'
    return resp


@translations_bp.route('/import', methods=['POST'])
@admin_required
def import_():
    entries = request.get_json(silent=True)
    if not isinstance(entries, list):
        return jsonify(error=_('Expected a JSON array of translation entries.')), 400
    report = translation_io.import_entries(
        entries,
        overwrite_reviewed=request.args.get('overwrite_reviewed', 'false').lower() == 'true',
        dry_run=request.args.get('dry_run', 'false').lower() == 'true',
        user_id=current_user.id,
    )
    return jsonify(report=report)


@translations_bp.route('/rehash', methods=['POST'])
@admin_required
def rehash():
    return jsonify(report=translation_io.rehash())
