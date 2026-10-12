"""Campaign YAML files (format warfighter-campaign/1) — docs/campaign_yaml.md, spec/09_campaigns.md §6.

`load(text)` turns a YAML file into the same payload the campaign editor sends to the API
(card numbers/names resolved to card ids) plus a list of warnings. Problems that the user can fix in
the editor (unknown card, bad flow, stray key) are warnings; only unreadable files raise.
`to_editor(payload)` shapes that payload like a campaign detail so the editor can be prefilled.
"""
import yaml
from sqlalchemy import func

from app import db, i18n
from app.i18n import _
from app.models import Card, CardTranslation, CAMPAIGN_FLOW_TYPES, CAMPAIGN_LINK_CONDITIONS
from app.required_modules import module_rank

FORMAT = 'warfighter-campaign/1'
MAX_SIZE = 200_000
PERSISTENCE_DEFAULTS = {'xp': True, 'wounds': True, 'skills': True, 'soldiers': True, 'casualties': True,
                        'gear': False}
TOP_KEYS = {'format', 'author', 'language', 'name', 'summary', 'intro', 'nation', 'theater', 'enemy', 'period',
            'flow', 'force', 'persistence', 'rules', 'scoring', 'outcomes', 'missions'}
MISSION_TEXTS = ('briefing', 'debrief', 'requirements', 'setup', 'victory', 'rewards')
MISSION_KEYS = {'id', 'code', 'title', 'mission', 'objective', 'situation', 'entry', 'rp', 'time', 'loadout',
                'next', *MISSION_TEXTS}
OVERRIDES = {'rp': 'rp_override', 'time': 'time_override', 'loadout': 'loadout_override'}


class CampaignYamlError(ValueError):
    pass


def _str(v):
    if v is None or isinstance(v, (dict, list)):
        return ''
    if isinstance(v, bool):
        return 'yes' if v else 'no'
    return str(v).strip()


def _list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def find_card(ref, card_type, warnings, where):
    """Card number ('W-018') or name (English, or a translated name) → catalog card of that type."""
    ref = _str(ref)
    if not ref:
        return None
    by_number = Card.catalog().filter(func.upper(Card.number) == ref.upper()).first()
    if by_number:
        if by_number.card_type == card_type:
            return by_number
        warnings.append(_('{where}: {ref} is a {type} card; expected a {expected} card.', where=where, ref=ref,
                          type=by_number.card_type, expected=card_type))
        return None
    folded = i18n.fold(ref)
    cards = Card.catalog().filter(Card.card_type == card_type, func.fold(Card.name) == folded).all()
    if not cards:
        numbers = [t.card_number for t in CardTranslation.query.filter(
            CardTranslation.field == 'name', func.fold(CardTranslation.value) == folded)]
        if numbers:
            cards = Card.catalog().filter(Card.card_type == card_type, Card.number.in_(numbers)).all()
    if not cards:
        warnings.append(_('{where}: {type} card "{ref}" not found.', where=where, type=card_type, ref=ref))
        return None
    cards.sort(key=lambda c: (module_rank(c.module), c.number))
    if len(cards) > 1:
        warnings.append(_('{where}: "{ref}" matches several cards; using {number}. Use the card number to choose.',
                          where=where, ref=ref, number=cards[0].number))
    return cards[0]


def load(text):
    """YAML text → (payload for the campaigns API, warnings). Raises CampaignYamlError if unreadable."""
    if len(text) > MAX_SIZE:
        raise CampaignYamlError(_('Import too large.'))
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, 'problem_mark', None)
        raise CampaignYamlError(_('Invalid YAML at line {line}: {problem}', line=mark.line + 1 if mark else '?',
                                  problem=getattr(e, 'problem', None) or str(e)))
    if not isinstance(data, dict):
        raise CampaignYamlError(_('A campaign file must be a YAML mapping (name:, missions:, …).'))

    warnings = []
    fmt = _str(data.get('format'))
    if fmt and fmt != FORMAT:
        warnings.append(_('Unknown format "{fmt}" (expected {expected}); importing anyway.', fmt=fmt, expected=FORMAT))
    unknown = sorted(str(k) for k in data if k not in TOP_KEYS)
    if unknown:
        warnings.append(_('Ignored keys: {keys}.', keys=', '.join(unknown)))

    flow = _str(data.get('flow')) or 'linear'
    if flow not in CAMPAIGN_FLOW_TYPES:
        warnings.append(_('Unknown flow "{flow}"; using linear.', flow=flow))
        flow = 'linear'

    force = data.get('force') if isinstance(data.get('force'), dict) else {}
    persistence = dict(PERSISTENCE_DEFAULTS)
    for k, v in (data.get('persistence') or {}).items() if isinstance(data.get('persistence'), dict) else ():
        if k in persistence:
            persistence[k] = bool(v)
        else:
            warnings.append(_('Ignored persistence key: {key}.', key=k))

    rules = []
    for r in _list(data.get('rules')):
        if isinstance(r, dict):
            rules.append({'title': _str(r.get('title')), 'body': _str(r.get('body'))})
        else:
            rules.append({'title': '', 'body': _str(r)})
    outcomes = [{'label': _str(o.get('label')), 'condition': _str(o.get('condition')),
                 'epilogue': _str(o.get('epilogue'))} for o in _list(data.get('outcomes')) if isinstance(o, dict)]

    missions, links, refs = [], [], {}
    raw_missions = [m for m in _list(data.get('missions')) if isinstance(m, dict)]
    if not raw_missions:
        warnings.append(_('The file has no missions.'))
    for i, m in enumerate(raw_missions, 1):
        key = _str(m.get('id')) or f'm{i}'
        if key in refs:
            warnings.append(_('Mission {n}: duplicate id "{id}"; renamed to m{n}.', n=i, id=key))
            key = f'm{i}'
        code = _str(m.get('code'))
        title = _str(m.get('title'))
        where = _('Mission {label}', label=code or title or i)
        stray = sorted(str(k) for k in m if k not in MISSION_KEYS)
        if stray:
            warnings.append(_('{where}: ignored keys: {keys}.', where=where, keys=', '.join(stray)))
        mc = find_card(m.get('mission'), 'Mission', warnings, where)
        oc = find_card(m.get('objective'), 'Objective', warnings, where)
        sc = find_card(m.get('situation'), 'Situation', warnings, where)
        row = {'key': key, 'code': code, 'title': title, 'is_entry': bool(m.get('entry')),
               'mission_card_id': mc.id if mc else None, 'objective_card_id': oc.id if oc else None,
               'situation_card_id': sc.id if sc else None, 'squad_id': None}
        for yk, field in OVERRIDES.items():
            v = m.get(yk)
            if v in (None, ''):
                row[field] = None
            elif isinstance(v, int) and not isinstance(v, bool):
                row[field] = v
            else:
                warnings.append(_('{where}: {key} must be a whole number.', where=where, key=yk))
                row[field] = None
        for f in MISSION_TEXTS:
            row[f] = _str(m.get(f))
        missions.append(row)
        refs[key] = key
        if code and code not in refs:
            refs[code] = key
        for n in _list(m.get('next')):
            n = n if isinstance(n, dict) else {'to': n}
            links.append((where, key, n))

    resolved = []
    for where, frm, n in links:
        to = refs.get(_str(n.get('to')))
        cond = _str(n.get('when')) or 'success'
        if not to:
            warnings.append(_('{where}: next mission "{to}" not found.', where=where, to=_str(n.get('to'))))
            continue
        if cond not in CAMPAIGN_LINK_CONDITIONS:
            warnings.append(_('{where}: unknown condition "{cond}"; using success.', where=where, cond=cond))
            cond = 'success'
        resolved.append({'from': frm, 'to': to, 'condition': cond, 'label': _str(n.get('label'))})
    if resolved and flow != 'branching':
        warnings.append(_('"next" links are only used by branching campaigns; ignored.'))
        resolved = []
    if flow == 'branching' and missions and not any(m['is_entry'] for m in missions):
        missions[0]['is_entry'] = True

    try:
        squad_size = int(force['squad_size']) if force.get('squad_size') not in (None, '') else None
    except (TypeError, ValueError):
        warnings.append(_('force.squad_size must be a whole number.'))
        squad_size = None
    payload = {
        'name': _str(data.get('name')), 'summary': _str(data.get('summary')), 'intro': _str(data.get('intro')),
        'nation': _str(data.get('nation')), 'theater': _str(data.get('theater')), 'enemy': _str(data.get('enemy')),
        'period': _str(data.get('period')), 'flow_type': flow,
        'settings': {
            'force': {'squad_size': squad_size, 'restrictions': _str(force.get('restrictions')),
                      'replacements': _str(force.get('replacements'))},
            'persistence': persistence, 'rules': rules, 'scoring': _str(data.get('scoring')), 'outcomes': outcomes,
        },
        'missions': missions, 'links': resolved,
        'author': _str(data.get('author')),
    }
    return payload, warnings


def to_editor(payload):
    """Payload from load() → campaign-detail shape (card objects instead of ids) for the editor."""
    def card(card_id):
        c = db.session.get(Card, card_id) if card_id else None
        return c.to_card_detail() if c else None

    missions = []
    for m in payload['missions']:
        missions.append({
            'key': m['key'], 'code': m['code'], 'title': m['title'], 'is_entry': m['is_entry'],
            'mission': card(m['mission_card_id']), 'objective': card(m['objective_card_id']),
            'situation': card(m['situation_card_id']), 'squad': None,
            **{f: m[f] for f in ('rp_override', 'time_override', 'loadout_override', *MISSION_TEXTS)},
        })
    return {k: payload[k] for k in ('name', 'summary', 'intro', 'nation', 'theater', 'enemy', 'period',
                                     'flow_type', 'settings', 'links', 'author')} | {'missions': missions}
