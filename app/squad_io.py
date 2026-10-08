"""Squad export (text / CSV / Tabletop Simulator) and import (text / CSV).

Formats are documented in spec/08_squad_tools.md §2. Export uses the request
language for names and labels; import relies on card numbers in [brackets]
(text) or the `number` column (CSV), so it works regardless of language.
Lines without a number fall back to an exact (accent-insensitive) name match.
"""
import csv
import io
import re
import uuid

from flask import current_app
from flask_login import current_user
from sqlalchemy import or_

from app import i18n, card_images
from app.i18n import _
from app.models import Card, CardAssociation, CardTranslation, CUSTOM_MODULE
from app.utils import normalize_nation

CSV_COLUMNS = ['section', 'soldier_number', 'number', 'name', 'type', 'quantity', 'rp_each']


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _assocs(card):
    return (CardAssociation.query.filter_by(parent_card_id=card.id)
            .order_by(CardAssociation.id).all())


def _rp(card):
    return card.resource_cost if card.resource_cost is not None else 0


def export_text(squad):
    mc = squad.mission_card
    lines = [f"{_('Squad')}: {squad.name}",
             f"{_('Nation')}: {i18n.enum_label('nation', squad.nation)}",
             f"{_('Mission')}: {mc.display_name()} [{mc.number}] — {squad.rp_total}/{mc.resources or 0} RP"]
    for so in squad.objectives:
        lines.append(f"{_('Objective')}: {so.card.display_name()} [{so.card.number}]")
    if squad.situation_card:
        sc = squad.situation_card
        lines.append(f"{_('Situation')}: {sc.display_name()} [{sc.number}]")
    for ss in squad.soldiers:
        c = ss.card
        tag = '' if c.card_subtype == 'Player' else f" ({i18n.enum_label('card_subtype', c.card_subtype)})"
        lines.append('')
        lines.append(f"{c.display_name()} [{c.number}]{tag} — {_rp(c)} RP")
        for sg in ss.gear:
            g = sg.card
            lines.append(f"  {sg.quantity}× {g.display_name()} [{g.number}] — {_rp(g)} RP")
        included = _assocs(c)
        if included:
            names = ', '.join((f'{a.quantity}× ' if a.quantity > 1 else '') + a.child_card.display_name()
                              for a in included)
            lines.append(f"  ({_('Included')}: {names})")
    if squad.notes:
        lines += ['', f"{_('Strategy Notes')}:", squad.notes.strip()]
    lines += ['', f"— Warfighter Squad Builder"]
    return '\n'.join(lines) + '\n'


def export_csv(squad):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    w.writerow(['squad', '', '', squad.name, squad.nation, '', ''])
    mc = squad.mission_card
    w.writerow(['mission', '', mc.number, mc.display_name(), mc.card_type, 1, mc.resources or 0])
    for so in squad.objectives:
        w.writerow(['objective', '', so.card.number, so.card.display_name(), so.card.card_type, 1, ''])
    if squad.situation_card:
        sc = squad.situation_card
        w.writerow(['situation', '', sc.number, sc.display_name(), sc.card_type, 1, ''])
    for ss in squad.soldiers:
        c = ss.card
        w.writerow(['soldier', '', c.number, c.display_name(), c.card_subtype or c.card_type, 1, _rp(c)])
        for sg in ss.gear:
            g = sg.card
            w.writerow(['gear', c.number, g.number, g.display_name(), g.card_type, sg.quantity, _rp(g)])
        for a in _assocs(c):
            g = a.child_card
            w.writerow(['included', c.number, g.number, g.display_name(), g.card_type, a.quantity, 0])
    return buf.getvalue()


def _tts_image_url(card):
    base = (current_app.config.get('TTS_IMAGE_BASE_URL') or '').rstrip('/')
    if not base:
        return ''
    rel = (card_images.resolve(current_app.config['CARD_IMAGES_DIR'], card.number, i18n.get_lang())
           or card_images.rel_path(i18n.DEFAULT_LANG, card.number))
    return f'{base}/{rel}'


def _tts_card(card, deck_id, x, z):
    return {
        'GUID': uuid.uuid4().hex[:6],
        'Name': 'Card',
        'Transform': {'posX': x, 'posY': 1.0, 'posZ': z, 'rotX': 0, 'rotY': 180, 'rotZ': 0,
                      'scaleX': 1.0, 'scaleY': 1.0, 'scaleZ': 1.0},
        'Nickname': card.display_name(),
        'Description': f'{card.number} · {i18n.enum_label("card_type", card.card_type)}',
        'CardID': deck_id * 100,
        'CustomDeck': {str(deck_id): {
            'FaceURL': _tts_image_url(card),
            'BackURL': current_app.config.get('TTS_CARD_BACK_URL') or '',
            'NumWidth': 1, 'NumHeight': 1, 'BackIsHidden': True, 'UniqueBack': False, 'Type': 0,
        }},
    }


def _tts_stack(cards_with_qty, nickname, x, z, next_id):
    """One TTS object: a single Card, or a Deck when there are several. Returns (obj, next_id)."""
    cards = []
    for card, qty in cards_with_qty:
        for _i in range(qty):
            cards.append(_tts_card(card, next_id, x, z))
            next_id += 1
    if len(cards) == 1:
        return cards[0], next_id
    deck = {
        'GUID': uuid.uuid4().hex[:6],
        'Name': 'Deck',
        'Transform': dict(cards[0]['Transform']),
        'Nickname': nickname,
        'DeckIDs': [c['CardID'] for c in cards],
        'CustomDeck': {k: v for c in cards for k, v in c['CustomDeck'].items()},
        'ContainedObjects': cards,
    }
    return deck, next_id


def export_tts(squad):
    """Tabletop Simulator saved object: mission/objectives/situation in a row,
    then one deck per soldier (soldier card first, then gear and included cards)."""
    objects, next_id = [], 1
    top = [(squad.mission_card, 1)] + [(so.card, 1) for so in squad.objectives]
    if squad.situation_card:
        top.append((squad.situation_card, 1))
    for i, (card, qty) in enumerate(top):
        obj, next_id = _tts_stack([(card, qty)], card.display_name(), i * 2.6, 4.0, next_id)
        objects.append(obj)
    for i, ss in enumerate(squad.soldiers):
        stack = [(ss.card, 1)] + [(sg.card, sg.quantity) for sg in ss.gear] \
            + [(a.child_card, a.quantity) for a in _assocs(ss.card)]
        obj, next_id = _tts_stack(stack, ss.card.display_name(), i * 2.6, 0.0, next_id)
        objects.append(obj)
    return {
        'SaveName': squad.name,
        'GameMode': '', 'Gravity': 0.5, 'Date': '', 'Table': '', 'Sky': '', 'Note': '',
        'Rules': '', 'XmlUI': '', 'LuaScript': '', 'LuaScriptState': '',
        'ObjectStates': objects,
        'TabStates': {}, 'VersionNumber': '',
    }


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
NUMBER_RE = re.compile(r'\[([A-Za-z0-9]+-[A-Za-z0-9]+)\]')
QTY_RE = re.compile(r'^\s*(\d+)\s*[×xX]\s*')


class _Resolver:
    def __init__(self):
        # Printed cards + the importing user's own custom missions
        query = Card.catalog()
        if current_user.is_authenticated:
            query = Card.query.filter(or_(Card.module != CUSTOM_MODULE, Card.owner_user_id == current_user.id))
        self.by_number = {c.number: c for c in query.all()}
        self.by_name = {}
        for c in self.by_number.values():
            self.by_name.setdefault(i18n.fold(c.name), c)
        for r in CardTranslation.query.filter_by(field='name'):
            c = self.by_number.get(r.card_number)
            if c:
                self.by_name.setdefault(i18n.fold(r.value), c)

    def number(self, n):
        return self.by_number.get((n or '').strip())

    def name(self, text):
        return self.by_name.get(i18n.fold(text.strip()))


def _empty_draft():
    return {'name': '', 'nation': '', 'mission': None, 'objectives': [], 'situation': None, 'soldiers': []}


def _place(draft, card, qty, indented, warnings, line_no):
    """Put a resolved card where it belongs, by card type."""
    if card.card_type == 'Mission':
        draft['mission'] = card
    elif card.card_type == 'Objective':
        draft['objectives'].append(card)
    elif card.card_type == 'Situation':
        draft['situation'] = card
    elif card.card_type == 'Soldier' and not indented:
        draft['soldiers'].append({'card': card, 'gear': []})
    elif draft['soldiers']:
        gear = draft['soldiers'][-1]['gear']
        for g in gear:
            if g['card'].id == card.id:
                g['quantity'] += qty
                break
        else:
            gear.append({'card': card, 'quantity': qty})
    else:
        warnings.append(_('Line {n}: {name} has no soldier to attach to.', n=line_no, name=card.display_name()))


def import_text(content):
    res, draft, warnings = _Resolver(), _empty_draft(), []
    for line_no, raw in enumerate(content.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith('(') or stripped.startswith('—'):
            continue  # "(Included: …)" — pre-printed, derived from the soldier card
        indented = line[:1] in (' ', '\t', '-', '*', '+')
        m_qty = QTY_RE.match(stripped.lstrip('-*+ '))
        qty = int(m_qty.group(1)) if m_qty else 1
        m_num = NUMBER_RE.search(line)
        if m_num:
            card = res.number(m_num.group(1))
            if not card:
                warnings.append(_('Line {n}: unknown card number {number}.', n=line_no, number=m_num.group(1)))
                continue
            _place(draft, card, qty, indented, warnings, line_no)
            continue
        # No number: "Label: value" or a bare name ("2x Mk2 Grenade", "Hernandez — 27 RP")
        has_label = ':' in stripped
        value = stripped.split(':', 1)[1] if has_label else stripped
        name = QTY_RE.sub('', value.strip().lstrip('-*+ '))
        name = re.split(r'\s+[—–-]\s+|\s+\(', name)[0]
        card = res.name(name)
        if card:
            _place(draft, card, qty, indented, warnings, line_no)
        elif not draft['name'] and not draft['soldiers'] and not draft['mission']:
            draft['name'] = value.strip()       # first unresolved line = squad name
        elif not has_label:
            warnings.append(_('Line {n}: card not found: {text}', n=line_no, text=stripped[:60]))
    return draft, warnings


def import_csv(content):
    res, draft, warnings = _Resolver(), _empty_draft(), []
    reader = csv.DictReader(io.StringIO(content.lstrip('﻿')))
    if not reader.fieldnames or 'number' not in reader.fieldnames:
        return draft, [_('CSV must have a header row with at least: section, number.')]
    soldiers_by_number = {}
    for line_no, row in enumerate(reader, 2):
        section = (row.get('section') or '').strip().lower()
        if section == 'squad':
            draft['name'] = (row.get('name') or '').strip()
            draft['nation'] = (row.get('type') or '').strip()
            continue
        if section == 'included':
            continue
        card = res.number(row.get('number')) or (res.name(row['name']) if row.get('name') else None)
        if not card:
            warnings.append(_('Line {n}: card not found: {text}', n=line_no,
                              text=(row.get('number') or row.get('name') or '')[:60]))
            continue
        try:
            qty = max(1, int(row.get('quantity') or 1))
        except ValueError:
            qty = 1
        if section == 'gear':
            owner = soldiers_by_number.get((row.get('soldier_number') or '').strip())
            if owner is None and draft['soldiers']:
                owner = draft['soldiers'][-1]
            if owner is None:
                warnings.append(_('Line {n}: {name} has no soldier to attach to.', n=line_no, name=card.display_name()))
                continue
            owner['gear'].append({'card': card, 'quantity': qty})
        else:
            _place(draft, card, qty, False, warnings, line_no)
            if card.card_type == 'Soldier':
                soldiers_by_number[card.number] = draft['soldiers'][-1]
    return draft, warnings


def detect_format(content):
    first = content.lstrip('﻿').split('\n', 1)[0].lower()
    return 'csv' if first.startswith('section,') or ('number' in first and ',' in first) else 'text'


def draft_to_json(draft, warnings):
    """Serialize for the builder: cards as detail objects (soldiers carry associations)."""
    if not draft['nation']:
        for s in draft['soldiers']:
            if s['card'].nation:
                draft['nation'] = normalize_nation(s['card'].nation)
                break
    if not draft['mission']:
        warnings.append(_('No mission found — pick one in the builder.'))

    def soldier_json(s):
        detail = s['card'].to_card_detail()
        detail['associations'] = [{'card': a.child_card.to_card_object(), 'quantity': a.quantity}
                                  for a in _assocs(s['card'])]
        return {'card': detail, 'gear': [{'card': g['card'].to_card_object(), 'quantity': g['quantity']}
                                         for g in s['gear']]}
    return {
        'name': draft['name'],
        'nation': draft['nation'],
        'mission': draft['mission'].to_card_detail() if draft['mission'] else None,
        'objectives': [c.to_card_detail() for c in draft['objectives']],
        'situation': draft['situation'].to_card_detail() if draft['situation'] else None,
        'soldiers': [soldier_json(s) for s in draft['soldiers']],
    }
