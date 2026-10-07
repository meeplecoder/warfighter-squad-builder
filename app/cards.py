import os
import re
from flask import Blueprint, request, jsonify, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from flask_limiter.util import get_remote_address
from sqlalchemy import or_, and_, case, func
from sqlalchemy.orm import aliased
from app import db, limiter, i18n
from app.i18n import _
from app.models import Card, CardTranslation
from app import smart_filter
from app.utils import nation_filter_clause


def _image_rate_key():
    if current_user.is_authenticated:
        return f'uid:{current_user.id}'
    return get_remote_address()

# Put 'Core Europe' first when sorting by module
_MODULE_PRIORITY = case((Card.module == 'Core Europe', 0), else_=1)

cards_bp = Blueprint('cards', __name__)

SORT_COLS = {
    'name': Card.name,
    'resource_cost': Card.resource_cost,
    'number': Card.number,
    'module': Card.module,
    'card_type': Card.card_type,
    'nation': Card.nation,
}


@cards_bp.route('', methods=['GET'])
@cards_bp.route('/', methods=['GET'])
def list_cards():
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    subtype = request.args.get('subtype', '').strip()
    nation = request.args.get('nation', '').strip()
    nation_strict = request.args.get('nation_strict', 'false').lower() == 'true'
    modules = request.args.getlist('module')
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(200, max(1, int(request.args.get('per_page', 50))))
    sort = request.args.get('sort', 'module')
    order = request.args.get('order', 'asc')

    query = Card.query
    lang = i18n.get_lang()

    filter_errors = []
    if q:
        # Smart syntax (t:weapon rp<5 …) + free words; accent-insensitive, EN + translation
        query, filter_errors = smart_filter.apply(query, q, lang)
    if category:
        query = query.filter(Card.card_type == category)
    if subtype:
        query = query.filter(Card.card_subtype == subtype)
    if nation:
        if nation_strict:
            clause = nation_filter_clause(nation, Card.nation)
            if clause is not None:
                query = query.filter(or_(clause, Card.nation.is_(None)))
        else:
            clause = nation_filter_clause(nation, Card.nation)
            if clause is not None:
                query = query.filter(clause)
    if modules:
        query = query.filter(Card.module.in_(modules))

    sort_col = SORT_COLS.get(sort, Card.module)
    if sort == 'name':
        # Sort by the displayed (translated) name, accent-insensitive
        name_col = Card.name
        if lang != i18n.DEFAULT_LANG:
            tr = aliased(CardTranslation)
            query = query.outerjoin(tr, and_(tr.card_number == Card.number, tr.lang == lang, tr.field == 'name'))
            name_col = func.coalesce(tr.value, Card.name)
        sort_col = func.fold(name_col)
    primary = sort_col.desc() if order == 'desc' else sort_col.asc()
    if sort == 'number':
        query = query.order_by(primary)
    elif sort == 'module':
        query = query.order_by(_MODULE_PRIORITY, primary, Card.number.asc())
    else:
        query = query.order_by(primary, _MODULE_PRIORITY, Card.module.asc(), Card.number.asc())

    # Full ordered ID list (no paging) — used for prev/next in card detail
    if request.args.get('ids_only', 'false').lower() == 'true':
        return jsonify(ids=[cid for (cid,) in query.with_entities(Card.id).all()])

    total = query.count()
    cards = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        items=[c.to_card_object() for c in cards],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
        filter_errors=filter_errors,
    )


@cards_bp.route('/<id_or_number>', methods=['GET'])
def get_card(id_or_number):
    card = None
    try:
        card_id = int(id_or_number)
        card = db.session.get(Card, card_id)
    except ValueError:
        card = Card.query.filter_by(number=id_or_number).first()

    if not card:
        return jsonify(error=_('Card not found.')), 404

    detail = card.to_card_detail()
    if card.card_type == 'Soldier':
        from app.models import CardAssociation
        assocs = (CardAssociation.query
                  .filter_by(parent_card_id=card.id)
                  .order_by(CardAssociation.id)
                  .all())
        detail['associations'] = [
            {'card': a.child_card.to_card_object(), 'quantity': a.quantity}
            for a in assocs
        ]
    else:
        detail['associations'] = []
    return jsonify(card=detail)


_PREFIX_RE = re.compile(r'^[A-Za-z0-9]+$')
_FILENAME_RE = re.compile(r'^[A-Za-z0-9]+-\d+\.jpg$', re.IGNORECASE)


@cards_bp.route('/images/<prefix>/<filename>')
@login_required
@limiter.limit('120 per minute; 500 per hour', key_func=_image_rate_key)
def card_image(prefix, filename):
    if not _PREFIX_RE.match(prefix) or not _FILENAME_RE.match(filename):
        abort(400)
    response = send_from_directory(
        os.path.join(current_app.config['CARD_IMAGES_DIR'], prefix),
        filename,
    )
    response.headers['Cache-Control'] = 'private, max-age=604800'
    return response
