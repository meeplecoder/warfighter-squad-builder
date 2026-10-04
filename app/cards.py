from flask import Blueprint, request, jsonify
from sqlalchemy import or_
from app import db
from app.models import Card
from app.utils import nation_filter_clause

cards_bp = Blueprint('cards', __name__)

SORT_COLS = {
    'name': Card.name,
    'resource_cost': Card.resource_cost,
    'number': Card.number,
    'module': Card.module,
    'card_category': Card.card_category,
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

    if q:
        like = f'%{q}%'
        query = query.filter(or_(Card.name.ilike(like), Card.notes.ilike(like)))
    if category:
        query = query.filter(Card.card_category == category)
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
    primary = sort_col.desc() if order == 'desc' else sort_col.asc()
    if sort == 'number':
        query = query.order_by(primary)
    else:
        query = query.order_by(primary, Card.number.asc())

    total = query.count()
    cards = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        items=[c.to_card_object() for c in cards],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
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
        return jsonify(error='Card not found.'), 404

    detail = card.to_card_detail()
    if card.card_category == 'Soldier':
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
