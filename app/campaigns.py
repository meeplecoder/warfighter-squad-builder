"""Campaign designer API — spec/09_campaigns.md.

Saving replaces the whole campaign (missions + links), like squads. Missions carry a client
`key` so links can reference missions that don't have an id yet.
"""
import json

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, func

from app import db, i18n, mentions, campaign_yaml, roles
from app.i18n import _
from app.models import (Card, Squad, Campaign, CampaignMission, CampaignLink, now_utc,
                        CUSTOM_MODULE, CAMPAIGN_FLOW_TYPES, CAMPAIGN_LINK_CONDITIONS)
from app.required_modules import module_rank

campaigns_bp = Blueprint('campaigns', __name__)

TEXT_MAX = 5000
INTRO_MAX = 20000
PERSISTENCE_KEYS = ('xp', 'wounds', 'skills', 'gear', 'soldiers', 'casualties')
SORT_COLS = {'updated_at': Campaign.updated_at, 'created_at': Campaign.created_at, 'name': Campaign.name}
# override → (min, max)
OVERRIDES = {'rp_override': (1, 300), 'time_override': (1, 50), 'loadout_override': (-10, 10)}


def _text(v, limit=TEXT_MAX):
    v = (v if isinstance(v, str) else '').strip()
    return v[:limit] or None


def _can_view(c):
    return c.status == 'published' or roles.can_manage(c.user_id)     # owner and admin see drafts


def _squad_viewable(s):
    return s and (s.status == 'published' or roles.can_manage(s.user_id))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def _summary(c):
    return {
        'id': c.id, 'name': c.name, 'summary': c.summary, 'nation': c.nation, 'theater': c.theater,
        'flow_type': c.flow_type, 'language': c.language, 'status': c.status, 'mission_count': len(c.missions),
        'owner': {'id': c.owner.id, 'username': c.owner.username},
        'created_at': c.created_at, 'updated_at': c.updated_at,
    }


def _card(card_id):
    card = db.session.get(Card, card_id) if card_id else None
    return card.to_card_detail() if card else None


def _detail(c):
    d = _summary(c)
    settings = c.settings_dict()
    d.update(intro=c.intro, enemy=c.enemy, period=c.period, settings=settings)
    missions, modules, texts = [], set(), [c.intro, c.summary, settings.get('scoring')]
    texts += [r.get('body') for r in settings.get('rules', [])]
    texts += [o.get('epilogue') for o in settings.get('outcomes', [])]
    texts += [(settings.get('force') or {}).get(k) for k in ('restrictions', 'replacements')]
    for m in c.missions:
        mission = _card(m.mission_card_id)
        situation = _card(m.situation_card_id)
        objective = _card(m.objective_card_id)
        for card in [mission, situation, objective]:
            if card and card['module'] != CUSTOM_MODULE:
                modules.add(card['module'])
        squad = m.squad if _squad_viewable(m.squad) else None
        texts += [m.briefing, m.debrief, m.requirements, m.setup, m.victory, m.rewards]
        missions.append({
            'id': m.id, 'key': str(m.id), 'code': m.code, 'title': m.title,
            'briefing': m.briefing, 'debrief': m.debrief,
            'mission': mission, 'situation': situation, 'objective': objective,
            'squad': {'id': squad.id, 'name': squad.name, 'nation': squad.nation, 'rp_total': squad.rp_total}
                     if squad else None,
            'rp_override': m.rp_override, 'time_override': m.time_override,
            'loadout_override': m.loadout_override, 'is_entry': bool(m.is_entry),
            'requirements': m.requirements, 'setup': m.setup, 'victory': m.victory, 'rewards': m.rewards,
        })
    d['missions'] = missions
    d['links'] = [{'id': l.id, 'from': str(l.from_mission_id), 'to': str(l.to_mission_id),
                   'condition': l.condition, 'label': l.label} for l in c.links]
    d['modules'] = sorted(modules, key=module_rank)
    d['mentions'] = mentions.resolve(*texts)
    return d


# ---------------------------------------------------------------------------
# Parsing & validation
# ---------------------------------------------------------------------------
def _parse(data, owner_id=None):
    """Payload → (fields, settings, missions, links, errors). Errors block any save."""
    errors = []
    fields = {
        'name': _text(data.get('name'), 120) or '',
        'summary': _text(data.get('summary'), 500),
        'intro': _text(data.get('intro'), INTRO_MAX),
        'nation': _text(data.get('nation'), 60),
        'theater': _text(data.get('theater'), 120),
        'enemy': _text(data.get('enemy'), 120),
        'period': _text(data.get('period'), 120),
        'flow_type': data.get('flow_type') if data.get('flow_type') in CAMPAIGN_FLOW_TYPES else 'linear',
        'language': i18n.normalize_lang(str(data.get('language') or '')),
    }
    s = data.get('settings') or {}
    force = s.get('force') or {}
    try:
        size = int(force['squad_size']) if force.get('squad_size') not in (None, '') else None
    except (TypeError, ValueError):
        size = None
    settings = {
        'force': {'squad_size': size if size and 1 <= size <= 30 else None,
                  'restrictions': _text(force.get('restrictions')), 'replacements': _text(force.get('replacements'))},
        'persistence': {k: bool((s.get('persistence') or {}).get(k)) for k in PERSISTENCE_KEYS},
        'rules': [{'title': _text(r.get('title'), 120), 'body': _text(r.get('body'))}
                  for r in (s.get('rules') or [])[:30] if isinstance(r, dict) and (r.get('title') or r.get('body'))],
        'scoring': _text(s.get('scoring')),
        'outcomes': [{'label': _text(o.get('label'), 120), 'condition': _text(o.get('condition'), 300),
                      'epilogue': _text(o.get('epilogue'))}
                     for o in (s.get('outcomes') or [])[:20] if isinstance(o, dict) and (o.get('label') or o.get('epilogue'))],
    }

    missions, keys = [], set()
    for i, m in enumerate((data.get('missions') or [])[:60]):
        key = str(m.get('key') or f'n{i}')
        if key in keys:
            errors.append(_('Duplicate mission key {key}.', key=key))
            continue
        keys.add(key)
        label = m.get('title') or f'#{i + 1}'
        row = {'key': key, 'code': _text(m.get('code'), 20), 'title': _text(m.get('title'), 120),
               'is_entry': 1 if m.get('is_entry') else 0}
        for f in ('briefing', 'debrief', 'requirements', 'setup', 'victory', 'rewards'):
            row[f] = _text(m.get(f))
        # Cards
        mc_id = m.get('mission_card_id')
        mc = db.session.get(Card, int(mc_id)) if mc_id else None
        if mc_id and (not mc or mc.card_type != 'Mission'
                      or (mc.module == CUSTOM_MODULE and mc.owner_user_id != (owner_id or current_user.id))):
            errors.append(_('{mission}: invalid mission card.', mission=label))
            mc = None
        row['mission_card_id'] = mc.id if mc else None
        sc_id = m.get('situation_card_id')
        sc = db.session.get(Card, int(sc_id)) if sc_id else None
        row['situation_card_id'] = sc.id if sc and sc.card_type == 'Situation' else None
        oc_id = m.get('objective_card_id')
        oc = db.session.get(Card, int(oc_id)) if oc_id else None
        row['objective_card_id'] = oc.id if oc and oc.card_type == 'Objective' else None
        sq_id = m.get('squad_id')
        sq = db.session.get(Squad, int(sq_id)) if sq_id else None
        row['squad_id'] = sq.id if _squad_viewable(sq) else None
        for f, (lo, hi) in OVERRIDES.items():
            v = m.get(f)
            if v in (None, ''):
                row[f] = None
                continue
            try:
                v = int(v)
            except (TypeError, ValueError):
                errors.append(_('{mission}: overrides must be numbers.', mission=label))
                continue
            if not lo <= v <= hi:
                errors.append(_('{mission}: override out of range ({lo} to {hi}).', mission=label, lo=lo, hi=hi))
            row[f] = v
        missions.append(row)

    links = []
    for l in (data.get('links') or [])[:300]:
        frm, to = str(l.get('from')), str(l.get('to'))
        cond = l.get('condition') if l.get('condition') in CAMPAIGN_LINK_CONDITIONS else 'success'
        if frm in keys and to in keys:
            links.append({'from': frm, 'to': to, 'condition': cond, 'label': _text(l.get('label'), 120)})
    return fields, settings, missions, links, errors


MIN_COMPLETE_MISSIONS = 2
# A mission is complete when it has these (field → label for the error message)
MISSION_REQUIRED = (('title', 'title'), ('mission_card_id', 'mission card'), ('objective_card_id', 'objective'),
                    ('briefing', 'briefing'))


def _publish_errors(fields, settings, missions):
    """Basic campaign validation (Validate button + required to publish). To be extended."""
    errs = []
    name = fields['name'].strip()
    if not name or name in ('Unnamed campaign', _('Unnamed campaign')):
        errs.append(_('Campaign name is required.'))
    elif len(name) < 3:
        errs.append(_('Campaign name must be at least 3 characters.'))
    if not fields['summary']:
        errs.append(_('Add a summary.'))
    if not fields['intro']:
        errs.append(_('Add an introduction.'))

    incomplete = []
    for i, m in enumerate(missions):
        missing = [_(label) for f, label in MISSION_REQUIRED if not m[f]]
        if missing:
            incomplete.append(_('{mission}: missing {fields}.', mission=m['title'] or f'#{i + 1}',
                                fields=', '.join(missing)))
    complete = len(missions) - len(incomplete)
    if complete < MIN_COMPLETE_MISSIONS:
        errs.append(_('At least {n} complete missions are needed ({done} so far).',
                      n=MIN_COMPLETE_MISSIONS, done=complete))
        errs.extend(incomplete)

    if fields['flow_type'] == 'branching' and missions and not any(m['is_entry'] for m in missions):
        errs.append(_('Branching campaigns need at least one starting mission.'))
    if not any(o['label'] and o['epilogue'] for o in settings['outcomes']):
        errs.append(_('Resolution: add at least one outcome with a label and an epilogue.'))
    return errs


def _save(c, fields, settings, missions, links):
    for k, v in fields.items():
        setattr(c, k, v)
    if not c.name:
        c.name = _('Unnamed campaign')
    c.settings = json.dumps(settings, ensure_ascii=False)
    c.updated_at = now_utc()
    for l in list(c.links):
        db.session.delete(l)
    for m in list(c.missions):
        db.session.delete(m)
    db.session.flush()
    by_key = {}
    for i, row in enumerate(missions):
        key = row.pop('key')
        m = CampaignMission(campaign_id=c.id, sort_order=i, **row)
        db.session.add(m)
        by_key[key] = m
    db.session.flush()
    for l in links:
        db.session.add(CampaignLink(campaign_id=c.id, from_mission_id=by_key[l['from']].id,
                                    to_mission_id=by_key[l['to']].id, condition=l['condition'], label=l['label']))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@campaigns_bp.route('', methods=['GET'])
@campaigns_bp.route('/', methods=['GET'])
def list_campaigns():
    user_id = request.args.get('user_id', type=int)
    q = request.args.get('q', '').strip()
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(100, max(1, request.args.get('per_page', 25, type=int)))
    # One list (like squads): everyone's published campaigns plus the user's own drafts.
    # user_id narrows it to one author; drafts only show to their owner.
    query = Campaign.query
    if user_id:
        query = query.filter(Campaign.user_id == user_id)
    if user_id and current_user.is_authenticated and current_user.id == user_id:
        pass
    elif roles.is_admin():
        pass        # the admin sees every campaign, drafts included
    elif current_user.is_authenticated:
        query = query.filter(or_(Campaign.status == 'published', Campaign.user_id == current_user.id))
    else:
        query = query.filter(Campaign.status == 'published')
    lang = i18n.normalize_lang(request.args.get('lang'))
    if lang:    # campaigns in that language plus those without one
        query = query.filter(or_(Campaign.language == lang, Campaign.language.is_(None)))
    if q:
        like = f'%{i18n.fold(q)}%'
        query = query.filter(or_(func.fold(Campaign.name).like(like), func.fold(Campaign.summary).like(like),
                                 func.fold(Campaign.theater).like(like)))
    col = SORT_COLS.get(request.args.get('sort'), Campaign.updated_at)
    query = query.order_by(col.asc() if request.args.get('order') == 'asc' else col.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify(items=[_summary(c) for c in items], total=total, page=page,
                   pages=(total + per_page - 1) // per_page)


@campaigns_bp.route('/<int:campaign_id>', methods=['GET'])
def get_campaign(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if not c or not _can_view(c):
        return jsonify(error=_('Campaign not found.')), 404
    return jsonify(campaign=_detail(c))


def _write(c, data, is_new):
    target = data.get('status', 'draft' if is_new else c.status)
    if target not in ('draft', 'published'):
        target = 'draft'
    fields, settings, missions, links, errors = _parse(data, None if is_new else c.user_id)
    if errors:
        return jsonify(error=' '.join(errors), errors=errors), 400
    if target == 'published':
        perrs = _publish_errors(fields, settings, missions)
        if perrs:
            return jsonify(error=_('Campaign cannot be published yet.'), errors=perrs), 422
    if is_new:
        c = Campaign(user_id=current_user.id, name=fields['name'] or _('Unnamed campaign'))
        db.session.add(c)
        db.session.flush()
    c.status = target
    _save(c, fields, settings, missions, links)
    db.session.commit()
    return jsonify(campaign=_detail(c)), 201 if is_new else 200


@campaigns_bp.route('/import', methods=['POST'])
@login_required
def import_campaign():
    """Campaign YAML file → unsaved campaign for the editor + warnings (spec 09 §6). Nothing is saved."""
    content = (request.get_json(silent=True) or {}).get('content') or ''
    if not content.strip():
        return jsonify(error=_('Nothing to import.')), 400
    try:
        payload, warnings = campaign_yaml.load(content)
    except campaign_yaml.CampaignYamlError as e:
        return jsonify(error=str(e)), 400
    return jsonify(campaign=campaign_yaml.to_editor(payload), warnings=warnings)


@campaigns_bp.route('/validate', methods=['POST'])
@login_required
def validate_campaign():
    """Check the editor payload without saving: {valid, errors}."""
    fields, settings, missions, links, errors = _parse(request.get_json(silent=True) or {})
    errors = errors + _publish_errors(fields, settings, missions)
    return jsonify(valid=not errors, errors=errors)


@campaigns_bp.route('', methods=['POST'])
@campaigns_bp.route('/', methods=['POST'])
@login_required
def create_campaign():
    return _write(None, request.get_json(silent=True) or {}, True)


@campaigns_bp.route('/<int:campaign_id>', methods=['PUT'])
@login_required
def update_campaign(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if not c:
        return jsonify(error=_('Campaign not found.')), 404
    if not roles.can_manage(c.user_id):              # owner or admin
        return jsonify(error=_('Not authorized.')), 403
    old_cards = {m.mission_card_id for m in c.missions}
    resp = _write(c, request.get_json(silent=True) or {}, False)
    if resp[1] == 200:
        from app import custom_missions
        if custom_missions.purge(list(old_cards)):
            db.session.commit()
    return resp


@campaigns_bp.route('/<int:campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    c = db.session.get(Campaign, campaign_id)
    if not c:
        return jsonify(error=_('Campaign not found.')), 404
    if not roles.can_manage(c.user_id):              # owner or admin
        return jsonify(error=_('Not authorized.')), 403
    old_cards = [m.mission_card_id for m in c.missions]
    db.session.delete(c)
    db.session.flush()
    from app import custom_missions
    custom_missions.purge(old_cards)
    db.session.commit()
    return jsonify(ok=True)
