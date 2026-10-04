from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from sqlalchemy import or_
from app import db
from app.models import Card, Squad, SquadSoldier, SquadGear, SquadLike, SquadComment, CardAssociation
from app.models import now_utc
from app import rules as rules_module

squads_bp = Blueprint('squads', __name__)

SORT_COLS = {
    'created_at': 'squads.created_at',
    'name': 'squads.name',
    'rp_total': 'squads.rp_total',
    'likes_count': 'squads.likes_count',
}


def _build_soldiers_data(payload_soldiers):
    """Load Card objects for each soldier and their gear from DB."""
    soldiers_data = []
    for s in payload_soldiers:
        card = db.session.get(Card, s['card_id'])
        if not card:
            return None, f"Card {s['card_id']} not found."
        gear_data = []
        for g in s.get('gear', []):
            gc = db.session.get(Card, g['card_id'])
            if not gc:
                return None, f"Gear card {g['card_id']} not found."
            gear_data.append({'card': gc.to_card_detail(), 'quantity': g.get('quantity', 1)})
        soldiers_data.append({'card': card.to_card_detail(), 'gear': gear_data})
    return soldiers_data, None


def _squad_detail(squad, liked_by_me=False):
    base = squad.to_summary(liked_by_me=liked_by_me)
    situation = {'id': squad.situation_card.id, 'name': squad.situation_card.name} if squad.situation_card else None
    base['situation'] = situation
    base['notes'] = squad.notes

    soldiers_out = []
    for ss in squad.soldiers:
        sc = ss.card
        is_ps = sc.card_subtype == 'Player'
        lm = squad.mission_card.loadout_modifier or 0
        eff_loadout = (sc.loadout or 0) + lm if is_ps else None
        gear_loadout_used = 0
        gear_out = []
        for sg in ss.gear:
            gc = sg.card
            counts = is_ps
            lw = None
            if counts and gc.card_category in ('Weapon', 'Equipment'):
                w = gc.loadout if gc.loadout is not None else (gc.resource_cost or 0)
                gear_loadout_used += w * sg.quantity
                lw = w
            gear_out.append({
                'id': sg.id,
                'card': gc.to_card_object(),
                'quantity': sg.quantity,
                'loadout_weight': lw,
                'counts_in_budget': counts,
            })
        assocs = (CardAssociation.query
                  .filter_by(parent_card_id=sc.id)
                  .order_by(CardAssociation.id)
                  .all())
        default_gear = [
            {'card': a.child_card.to_card_object(), 'quantity': a.quantity}
            for a in assocs
        ]
        soldiers_out.append({
            'id': ss.id,
            'sort_order': ss.sort_order,
            'card': sc.to_card_object(),
            'effective_loadout': eff_loadout,
            'gear_loadout_used': gear_loadout_used if is_ps else None,
            'loadout_remaining': (eff_loadout - gear_loadout_used) if is_ps else None,
            'rp_cost': sc.resource_cost,
            'gear': gear_out,
            'default_gear': default_gear,
        })

    base['soldiers'] = soldiers_out
    base['computed'] = {
        'rp_total': squad.rp_total,
        'rp_remaining': (squad.mission_card.resources or 0) - squad.rp_total,
        'budget': squad.mission_card.resources,
    }
    return base


def _parse_and_validate(data):
    """Parse payload and run validation. Returns (mission_card, payload, soldiers_data, validation)."""
    mission_card_id = data.get('mission_card_id')
    if not mission_card_id:
        return None, None, None, None, 'mission_card_id is required.'

    mission_card = db.session.get(Card, mission_card_id)
    if not mission_card or mission_card.card_category != 'Mission':
        return None, None, None, None, 'Invalid mission card.'

    nation = (data.get('nation') or '').strip()
    if not nation:
        return None, None, None, None, 'nation is required.'

    soldiers_payload = data.get('soldiers', [])
    soldiers_data, err = _build_soldiers_data(soldiers_payload)
    if err:
        return None, None, None, None, err

    # Vehicle gear check
    for i, s in enumerate(soldiers_data):
        if s['card'].get('card_subtype') == 'Vehicle' and s.get('gear'):
            return None, None, None, None, 'Vehicle soldiers cannot carry gear.'

    validation = rules_module.validate_squad(data, mission_card.to_card_detail(), soldiers_data)
    return mission_card, data, soldiers_data, validation, None


def _save_squad(squad, data, soldiers_payload):
    """Write SquadSoldier + SquadGear rows from payload. Assumes squad is already persisted."""
    # Clear existing
    for ss in list(squad.soldiers):
        db.session.delete(ss)
    db.session.flush()

    for i, s in enumerate(soldiers_payload):
        ss = SquadSoldier(
            squad_id=squad.id,
            card_id=s['card_id'],
            sort_order=s.get('sort_order', i),
        )
        db.session.add(ss)
        db.session.flush()
        for g in s.get('gear', []):
            sg = SquadGear(
                squad_soldier_id=ss.id,
                card_id=g['card_id'],
                quantity=g.get('quantity', 1),
            )
            db.session.add(sg)


@squads_bp.route('', methods=['GET'])
@squads_bp.route('/', methods=['GET'])
def list_squads():
    user_id = request.args.get('user_id', type=int)
    nation = request.args.get('nation', '').strip()
    mission_id = request.args.get('mission_id', type=int)
    liked = request.args.get('liked', 'false').lower() == 'true'
    status_filter = request.args.get('status', '').strip()
    sort = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 20))))

    query = Squad.query

    # Visibility: only published squads are public, except the owner sees their own drafts too
    is_own_squads = current_user.is_authenticated and user_id == current_user.id
    if is_own_squads:
        # Owner sees all their squads; honour optional status filter
        if status_filter in ('draft', 'published'):
            query = query.filter(Squad.status == status_filter)
    else:
        # Everyone else only sees published squads
        query = query.filter(Squad.status == 'published')

    if user_id:
        query = query.filter(Squad.user_id == user_id)
    if nation:
        query = query.filter(Squad.nation == nation)
    if mission_id:
        query = query.filter(Squad.mission_card_id == mission_id)
    if liked and current_user.is_authenticated:
        liked_ids = [l.squad_id for l in SquadLike.query.filter_by(user_id=current_user.id).all()]
        query = query.filter(Squad.id.in_(liked_ids))

    sort_attr = {
        'created_at': Squad.created_at,
        'name': Squad.name,
        'rp_total': Squad.rp_total,
        'likes_count': Squad.likes_count,
    }.get(sort, Squad.created_at)
    query = query.order_by(sort_attr.desc() if order == 'desc' else sort_attr.asc())

    total = query.count()
    squads = query.offset((page - 1) * per_page).limit(per_page).all()

    liked_ids_set = set()
    if current_user.is_authenticated:
        ids = [s.id for s in squads]
        liked_ids_set = {
            l.squad_id for l in
            SquadLike.query.filter(SquadLike.squad_id.in_(ids), SquadLike.user_id == current_user.id).all()
        }

    return jsonify(
        items=[s.to_summary(liked_by_me=s.id in liked_ids_set) for s in squads],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@squads_bp.route('/<int:squad_id>', methods=['GET'])
def get_squad(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    liked_by_me = False
    if current_user.is_authenticated:
        liked_by_me = SquadLike.query.filter_by(squad_id=squad_id, user_id=current_user.id).first() is not None
    return jsonify(squad=_squad_detail(squad, liked_by_me=liked_by_me))


@squads_bp.route('/validate', methods=['POST'])
def validate_squad():
    data = request.get_json(silent=True) or {}
    mission_card, payload, soldiers_data, validation, err = _parse_and_validate(data)
    if err:
        return jsonify(error=err), 400
    return jsonify(validation)


@squads_bp.route('', methods=['POST'])
@squads_bp.route('/', methods=['POST'])
@login_required
def create_squad():
    data = request.get_json(silent=True) or {}
    target_status = data.get('status', 'draft')
    if target_status not in ('draft', 'published'):
        target_status = 'draft'

    mission_card, payload, soldiers_data, validation, err = _parse_and_validate(data)
    if err:
        return jsonify(error=err), 400

    if target_status == 'published' and not validation['valid']:
        return jsonify(error='Squad has validation errors.', validation=validation), 422

    squad = Squad(
        user_id=current_user.id,
        name=(data.get('name') or '').strip() or 'Unnamed Squad',
        mission_card_id=data['mission_card_id'],
        objective_card_id=data.get('objective_card_id'),
        situation_card_id=data.get('situation_card_id'),
        nation=data['nation'],
        notes=data.get('notes') or '',
        rp_total=validation['computed']['rp_total'],
        is_valid=1 if validation['valid'] else 0,
        status=target_status,
    )
    db.session.add(squad)
    db.session.flush()
    _save_squad(squad, data, data.get('soldiers', []))
    db.session.commit()
    return jsonify(squad=_squad_detail(squad)), 201


@squads_bp.route('/<int:squad_id>', methods=['PUT'])
@login_required
def update_squad(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    if squad.user_id != current_user.id:
        return jsonify(error='Not authorized.'), 403

    data = request.get_json(silent=True) or {}
    target_status = data.get('status', squad.status)
    if target_status not in ('draft', 'published'):
        target_status = squad.status

    mission_card, payload, soldiers_data, validation, err = _parse_and_validate(data)
    if err:
        return jsonify(error=err), 400

    if target_status == 'published' and not validation['valid']:
        return jsonify(error='Squad has validation errors.', validation=validation), 422

    squad.name = (data.get('name') or '').strip() or squad.name
    squad.mission_card_id = data['mission_card_id']
    squad.objective_card_id = data.get('objective_card_id')
    squad.situation_card_id = data.get('situation_card_id')
    squad.nation = data['nation']
    squad.notes = data.get('notes') or ''
    squad.rp_total = validation['computed']['rp_total']
    squad.is_valid = 1 if validation['valid'] else 0
    squad.status = target_status
    squad.updated_at = now_utc()

    _save_squad(squad, data, data.get('soldiers', []))
    db.session.commit()
    return jsonify(squad=_squad_detail(squad))


@squads_bp.route('/<int:squad_id>/publish', methods=['POST'])
@login_required
def publish_squad(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    if squad.user_id != current_user.id:
        return jsonify(error='Not authorized.'), 403

    # Re-validate against current saved state
    soldiers_payload = [
        {
            'card_id': ss.card_id,
            'sort_order': ss.sort_order,
            'gear': [{'card_id': sg.card_id, 'quantity': sg.quantity} for sg in ss.gear],
        }
        for ss in squad.soldiers
    ]
    squad_data = {
        'mission_card_id': squad.mission_card_id,
        'objective_card_id': squad.objective_card_id,
        'situation_card_id': squad.situation_card_id,
        'nation': squad.nation,
        'soldiers': soldiers_payload,
    }
    _, _, soldiers_data, validation, err = _parse_and_validate(squad_data)
    if err:
        return jsonify(error=err), 400
    if not validation['valid']:
        return jsonify(error='Squad has validation errors.', validation=validation), 422

    squad.status = 'published'
    squad.is_valid = 1
    squad.updated_at = now_utc()
    db.session.commit()
    return jsonify(squad=_squad_detail(squad))


@squads_bp.route('/<int:squad_id>', methods=['DELETE'])
@login_required
def delete_squad(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    if squad.user_id != current_user.id:
        return jsonify(error='Not authorized.'), 403
    db.session.delete(squad)
    db.session.commit()
    return jsonify(ok=True)


# --- Likes ---

@squads_bp.route('/<int:squad_id>/like', methods=['POST'])
@login_required
def like_squad(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    existing = SquadLike.query.filter_by(squad_id=squad_id, user_id=current_user.id).first()
    if not existing:
        like = SquadLike(squad_id=squad_id, user_id=current_user.id)
        db.session.add(like)
        squad.likes_count = (squad.likes_count or 0) + 1
        db.session.commit()
    return jsonify(likes_count=squad.likes_count, liked_by_me=True)


@squads_bp.route('/<int:squad_id>/like', methods=['DELETE'])
@login_required
def unlike_squad(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    existing = SquadLike.query.filter_by(squad_id=squad_id, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        squad.likes_count = max(0, (squad.likes_count or 1) - 1)
        db.session.commit()
    return jsonify(likes_count=squad.likes_count, liked_by_me=False)


# --- Comments ---

@squads_bp.route('/<int:squad_id>/comments', methods=['GET'])
def list_comments(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    query = SquadComment.query.filter_by(squad_id=squad_id).order_by(SquadComment.created_at.asc())
    total = query.count()
    comments = query.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify(
        items=[c.to_dict() for c in comments],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@squads_bp.route('/<int:squad_id>/comments', methods=['POST'])
@login_required
def add_comment(squad_id):
    squad = db.session.get(Squad, squad_id)
    if not squad:
        return jsonify(error='Squad not found.'), 404
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify(error='Comment body is required.'), 400
    if len(body) > 2000:
        return jsonify(error='Comment too long (max 2000 chars).'), 400
    comment = SquadComment(squad_id=squad_id, user_id=current_user.id, body=body)
    db.session.add(comment)
    db.session.commit()
    return jsonify(comment=comment.to_dict()), 201


@squads_bp.route('/<int:squad_id>/comments/<int:comment_id>', methods=['PUT'])
@login_required
def edit_comment(squad_id, comment_id):
    comment = db.session.get(SquadComment, comment_id)
    if not comment or comment.squad_id != squad_id:
        return jsonify(error='Comment not found.'), 404
    squad = db.session.get(Squad, squad_id)
    if comment.user_id != current_user.id and squad.user_id != current_user.id:
        return jsonify(error='Not authorized.'), 403
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify(error='Comment body is required.'), 400
    comment.body = body
    comment.updated_at = now_utc()
    db.session.commit()
    return jsonify(comment=comment.to_dict())


@squads_bp.route('/<int:squad_id>/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(squad_id, comment_id):
    comment = db.session.get(SquadComment, comment_id)
    if not comment or comment.squad_id != squad_id:
        return jsonify(error='Comment not found.'), 404
    squad = db.session.get(Squad, squad_id)
    if comment.user_id != current_user.id and squad.user_id != current_user.id:
        return jsonify(error='Not authorized.'), 403
    db.session.delete(comment)
    db.session.commit()
    return jsonify(ok=True)
