"""
Squad metrics (Layer 1 of the squad generator — specs 11/12).

Pure functions: card data in, numbers out. No Flask request handling; the only database access is the
squad's own relationships, read by `squad_metrics(squad)`.

Everything here is a G0 *estimate* (see spec/12_squad_metrics.md): expected values computed analytically
from card tables and a Hostile / Location reference (app/metric_reference.json, built by
scripts/build_metric_reference.py from cards2.csv). Card text is parsed with small regexes on the fly
(no card_tags table yet); skill effects (Spotter, Marksman, …) are NOT applied yet.
"""

import json
import math
import os
import re
from functools import lru_cache

from app import skill_effects

METRIC_KEYS = ['ranged_fire', 'close_assault', 'anti_armour', 'demolition', 'supplies',
               'mobility', 'survivability', 'resilience', 'experience']

DEFAULT_TIME = 8            # turns, when the mission has no Time
SPRAY_CAP_FALLBACK = 2.6    # average Hostiles per card
MOVE_RESERVE = 0.3          # extra card need: Action-card plays, Location Markers
CX_XP_WEIGHT = 1.5          # provisional: 1 CX (a free card every turn) ≈ 1.5 XP

# Suppress weight α (spec 12 §7.2): a Suppress counts as α of a Kill, by objective family / mission type
ALPHA_BY_FAMILY = {'Fallback': 0.6, 'Right Flank': 0.6, 'Keep Clear': 0.4, 'Escape': 0.4}
ALPHA_BY_MISSION = {'Holding Action': 0.6, 'Hold the Line': 0.6}
ALPHA_DEFAULT = 0.2

GOOD_SKILLS = {'Guts', 'Dauntless', 'Holdfast', 'Survivor', 'Survivor 2', 'Tenacity', 'Lucky', 'Veteran'}
BAD_SKILLS = {'Panic', 'Jitters', 'Timidity', 'Green', 'Unwell', 'Unlucky', 'Demoralized', 'Slothful',
              'Unpracticed', 'Directionless', 'Disengaged', 'Tenderfoot'}

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'metric_reference.json')


# ── reference data ────────────────────────────────────────────────────────────

_FALLBACK_REFERENCE = {
    'hostiles': {'all': {
        'cover': {'1': 0.05, '2': 0.18, '3': 0.28, '4': 0.23, '5': 0.10, '6': 0.06, '7': 0.03, '8': 0.02, '9': 0.01},
        'pen': {'0': 0.6, '1': 0.28, '2': 0.07, '3': 0.02, '4': 0.02, '5': 0.01},
        'per_card': 2.6}},
    'locations': {'all': {'0': 0.09, '1': 0.16, '2': 0.30, '3': 0.24, '4': 0.15, '5': 0.06, '6': 0.01}},
    'community': {},
}


@lru_cache(maxsize=1)
def reference():
    try:
        with open(DATA_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return _FALLBACK_REFERENCE


def clear_cache():
    reference.cache_clear()
    _weapon.cache_clear()


def _dist(d):
    return {int(k): float(v) for k, v in d.items()}


def _hostile_ref(nation=None, level=None):
    h = reference().get('hostiles', {})
    key = f'{nation}|{level}' if nation and level else 'all'
    ref = h.get(key) or h.get('all') or _FALLBACK_REFERENCE['hostiles']['all']
    return {'cover': _dist(ref['cover']), 'pen': _dist(ref['pen']), 'per_card': ref.get('per_card') or SPRAY_CAP_FALLBACK}


# ── dice maths ────────────────────────────────────────────────────────────────

def p_die(hit):
    """Chance one d10 meets a hit number (0 faces count as 10)."""
    return min(1.0, max(0.0, (11 - hit) / 10.0))


def p_d6(threshold):
    """P(d6 >= threshold)."""
    if threshold <= 1:
        return 1.0
    if threshold > 6:
        return 0.0
    return (7 - threshold) / 6.0


def p_cover(pen, cover_dist):
    """P(d6 + pen >= Hostile Cover), averaged over the Hostile Cover distribution."""
    return sum(p * p_d6(c - pen) for c, p in cover_dist.items())


def _conditional(cover_dist, lo):
    """Cover distribution restricted to cover >= lo (renormalised)."""
    sub = {c: p for c, p in cover_dist.items() if c >= lo}
    tot = sum(sub.values())
    return {c: p / tot for c, p in sub.items()} if tot else {6: 1.0}


# ── weapon parsing ────────────────────────────────────────────────────────────

class Weapon:
    __slots__ = ('name', 'subtype', 'ranges', 'reload', 'modes', 'pen', 'spray', 'explosion', 'expended',
                 'ammo', 'melee', 'bonus_vs', 'dice')

    def __init__(self):
        self.name = ''
        self.subtype = ''
        self.ranges = {}      # range -> hit number
        self.reload = None    # reload number or None
        self.modes = []       # [(mode, dice)]
        self.pen = 0
        self.spray = False
        self.explosion = False
        self.expended = False
        self.ammo = None
        self.melee = []       # [(mode, dice, hit, pen)]
        self.bonus_vs = {}    # 'Vehicles'/'Structures' -> bonus to Attack and Penetration rolls
        self.dice = 1


def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        m = re.match(r'\s*(-?\d+)', str(v))
        return int(m.group(1)) if m else default


def _load(s):
    if not s:
        return None
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except ValueError:
        return None


def parse_weapon(card):
    """card: dict with name, card_subtype, notes_en/notes, weapon_range_table, weapon_mode_table."""
    w = Weapon()
    w.name = card.get('name_en') or card.get('name') or ''
    w.subtype = card.get('card_subtype') or ''
    notes = card.get('notes_en') or card.get('notes') or ''
    rt = _load(card.get('weapon_range_table'))
    if rt and rt.get('rows'):
        hdr = [h.lower() for h in rt['headers']]
        ri, hi = hdr.index('range'), hdr.index('hit')
        rl = hdr.index('reload') if 'reload' in hdr else None
        for row in rt['rows']:
            w.ranges[_num(row[ri])] = _num(row[hi], 11)
            if rl is not None and w.reload is None:
                w.reload = _num(row[rl], 0)
    mt = _load(card.get('weapon_mode_table'))
    if mt and mt.get('rows'):
        hdr = [h.lower() for h in mt['headers']]
        if 'rolls' in hdr:
            ri = hdr.index('rolls')
            w.modes = [(str(r[0]), _num(r[ri], 1)) for r in mt['rows']]
        elif 'rs' in hdr:                      # melee: Mode, Rs, St, H, P
            ri, hi, pi = hdr.index('rs'), hdr.index('h'), hdr.index('p')
            w.melee = [(str(r[0]), _num(r[ri], 1), _num(r[hi], 10), _num(r[pi], 0)) for r in mt['rows']]
    m = re.search(r'Pen(?:etration)?\s+(\d+)', notes)
    w.pen = int(m.group(1)) if m else 0
    w.spray = bool(re.search(r'\bSpray\b', notes))
    w.explosion = any(mode.lower() == 'explosion' for mode, _ in w.modes) or 'Explosion' in notes
    w.expended = bool(re.search(r'\bExpended\b', notes)) or bool(re.search(r'\bSingle Shot\b', notes))
    m = re.search(r'\((\d+)\)\s*$', notes.split('\n')[-1].strip()) or re.search(r'(?:Ammo|Fuel|Rockets)\s*\((\d+)\)', notes)
    w.ammo = int(m.group(1)) if m else None
    for m in re.finditer(r'Add (\d+) to Attack and Penetration rolls against ([A-Za-z ]+?)(?: and ([A-Za-z]+))?\.', notes):
        for target in (m.group(2), m.group(3)):
            if target:
                w.bonus_vs[target.strip()] = int(m.group(1))
    return w


@lru_cache(maxsize=4096)
def _weapon(card_id, key):
    # `key` is a hashable snapshot of the card fields (see _card_key); the weapon is rebuilt only when it changes
    return parse_weapon(dict(key))


def _card_key(card):
    return tuple(sorted({
        'name': card.get('name'), 'name_en': card.get('name_en'), 'card_subtype': card.get('card_subtype'),
        'notes_en': card.get('notes_en') or card.get('notes'),
        'weapon_range_table': json.dumps(card.get('weapon_range_table')) if not isinstance(card.get('weapon_range_table'), str) else card.get('weapon_range_table'),
        'weapon_mode_table': json.dumps(card.get('weapon_mode_table')) if not isinstance(card.get('weapon_mode_table'), str) else card.get('weapon_mode_table'),
    }.items()))


def weapon_of(card):
    return _weapon(card.get('id'), _card_key(card))


# ── attack value ──────────────────────────────────────────────────────────────

def attack_value(hit, dice, pen, spray_or_explosion, cover_dist, alpha, per_card, hit_bonus=0):
    """Expected (kills, suppresses, F) of one attack. hit = hit number; dice = attack dice."""
    pd = p_die(hit - hit_bonus)
    pc = p_cover(pen, cover_dist)
    if spray_or_explosion:
        n = min(dice, per_card) if per_card else dice
        k = n * pd * pc
        s = n * (pd + pc - 2 * pd * pc)
    else:
        ph = 1 - (1 - pd) ** dice
        k = ph * pc
        s = ph + pc - 2 * ph * pc
    return k, s, k + alpha * s


def best_fire(weapon, rng, cover_dist, alpha, per_card, pen_bonus=0, hit_bonus=0, rng_min=None,
              auto_dice=0, explosion_dice=0):
    """Best F over fire modes of a ranged/thrown weapon at range `rng` (or the best range >= rng_min)."""
    if rng_min is not None:
        hits = [h for r, h in weapon.ranges.items() if r >= rng_min]
        if not hits:
            return 0.0
        hit = min(hits)
    else:
        if rng not in weapon.ranges:
            return 0.0
        hit = weapon.ranges[rng]
    best = 0.0
    modes = weapon.modes or [('Semi', 1)]
    for mode, dice in modes:
        ml = mode.lower()
        if ml in ('auto', 'burst'):
            dice += auto_dice
        elif ml == 'explosion':
            dice += explosion_dice
        multi = weapon.spray or mode.lower() == 'explosion'
        # Spray only applies to the multi-die modes (Auto/Burst); Semi/Bolt are one die
        if weapon.spray and mode.lower() in ('semi', 'bolt', 'standard'):
            multi = False
        _, _, f = attack_value(hit, dice, weapon.pen + pen_bonus, multi, cover_dist, alpha, per_card, hit_bonus)
        best = max(best, f)
    return best


def fire_with(w, mods, cover_dist, alpha, per_card, rng=None, rng_min=None, spot=0):
    """best_fire with the soldier's skill / equipment bonuses (and a Spotter's +1 for ranged attacks)."""
    tags = skill_effects.weapon_tags(w)
    hb, cb = skill_effects.bonuses(mods, tags, rng if rng is not None else rng_min)
    if spot and 'ranged' in tags:
        hb += spot
    return best_fire(w, rng, cover_dist, alpha, per_card, pen_bonus=cb, hit_bonus=hb, rng_min=rng_min,
                     auto_dice=mods['auto_dice'], explosion_dice=mods['satchel_dice'] if 'satchel' in tags else 0)


def anti_with(w, mods, high_cover, per_card, spot=0):
    """Best kill chance of a weapon against high-Cover Hostiles (incl. +N vs Vehicles, skill bonuses)."""
    tags = skill_effects.weapon_tags(w)
    bonus = w.bonus_vs.get('Vehicles', 0)
    best = 0.0
    for r, hit in w.ranges.items():
        hb, cb = skill_effects.bonuses(mods, tags, r)
        if spot and 'ranged' in tags:
            hb += spot
        for mode, dice in (w.modes or [('Semi', 1)]):
            ml = mode.lower()
            d = dice + (mods['auto_dice'] if ml in ('auto', 'burst') else 0) \
                + (mods['satchel_dice'] if ml == 'explosion' and 'satchel' in tags else 0)
            k = attack_value(hit, d, w.pen + bonus + cb, w.spray or ml == 'explosion', high_cover, 0, per_card,
                             hit_bonus=bonus + hb)[0]
            best = max(best, k)
    return best


def hth_value(soldier, weapons, cover_dist, alpha, per_card, extra=0):
    """F of the best hand-to-hand attack (unarmed or melee weapon)."""
    hth = (soldier.get('hth') or 0) + extra
    # unarmed: d10 + HtH >= 10 and d6 >= Hostile Cover
    best = attack_value(10, 1, 0, False, cover_dist, alpha, per_card, hit_bonus=hth)[2]
    for w in weapons:
        for _mode, dice, hit, pen in w.melee:
            best = max(best, attack_value(hit, dice, pen, False, cover_dist, alpha, per_card, hit_bonus=hth)[2])
    return best


# ── squad model ───────────────────────────────────────────────────────────────

def objective_kinds(o):
    """Names an objective goes by: its family (Fallback, Right Flank, …) and its mechanic (Keep Clear,
    Escape, … — stored in card_subtype, which is what `mechanic` carries)."""
    return {o.get('objective_family') or '', o.get('mechanic') or ''} - {''}


def alpha_for(objectives, mission_type):
    a = ALPHA_BY_MISSION.get(mission_type or '', ALPHA_DEFAULT)
    for o in objectives:
        for kind in objective_kinds(o):
            a = max(a, ALPHA_BY_FAMILY.get(kind, ALPHA_DEFAULT))
    return a


def _health_actions(card):
    """(health, actions) at full health for NPS/SS/PS."""
    t = _load(card.get('health_actions_table'))
    health = card.get('health')
    actions = card.get('actions')
    if t and t.get('rows'):
        row = t['rows'][0]
        hdr = [h.lower() for h in t['headers']]
        health = health or _num(row[hdr.index('health')])
        actions = actions or _num(row[hdr.index('actions')])
    if health is None:
        m = re.search(r'Health (\d+)', card.get('notes_en') or card.get('notes') or '')
        health = int(m.group(1)) if m else 0
    if card.get('card_subtype') in ('Player', 'Team'):
        actions = actions or 2
    return health or 0, actions or 0


def _ss_hits(card):
    """Squad Soldier attack chart at full health: {range: hit}."""
    t = _load(card.get('health_actions_table'))
    if not t or not t.get('rows'):
        return {}
    hdr = t['headers']
    row = t['rows'][0]
    out = {}
    for i, h in enumerate(hdr):
        m = re.match(r'Range(\d)', h)
        if m:
            out[int(m.group(1))] = _num(row[i], 11)
    return out


def analyse(squad, mission, objectives, hostile=None, locations=None):
    """
    squad: {'soldiers': [{'card': dict, 'gear': [dict card]*, 'default_gear': [dict card]*}]}  (cards as to_card_detail)
    mission: dict (time, objective_position, mission_type); objectives: [dict] (objective_family, notes_en…)
    Returns {'metrics': {key: {'raw', 'score', 'detail'}}, 'notes': [...]}.
    """
    hostile = hostile or _hostile_ref()
    locations = locations or _dist(reference().get('locations', {}).get('all') or _FALLBACK_REFERENCE['locations']['all'])
    cover_dist, pen_dist, per_card = hostile['cover'], hostile['pen'], hostile['per_card']
    high_cover = _conditional(cover_dist, 6)
    alpha = alpha_for(objectives, mission.get('mission_type'))
    time = mission.get('time') or DEFAULT_TIME

    prep = []
    for s in squad['soldiers']:
        allgear = s['gear'] + s['default_gear']
        named = lambda kind: {(c.get('name_en') or c.get('name')) for c in allgear if c.get('card_type') == kind}
        prep.append({'s': s, 'skills': named('Skill'), 'mods': skill_effects.soldier_mods(named('Skill'), named('Equipment'))})
    lead = max([p['mods']['squad_move'] for p in prep] or [0])            # limit 1 per mission: the best copy counts
    sleader = max([p['mods']['support_move'] for p in prep] or [0])
    spotters = sum(1 for p in prep if p['mods']['spotter'])

    soldiers = []
    for p in prep:
        s, mods, skills = p['s'], p['mods'], p['skills']
        card = s['card']
        subtype = card.get('card_subtype')
        health, actions = _health_actions(card)
        if subtype in ('Player', 'Team'):
            actions += mods['actions']
            if mods['spotter']:
                actions -= 1                                         # spotting costs the Spotter 1 Action
        move = (card.get('movement') or 0) + mods['move'] + lead + (sleader if subtype in ('NPS', 'Squad') else 0)
        spot = 1 if spotters - (1 if mods['spotter'] else 0) > 0 else 0     # another soldier's Spotter helps you
        ws = [weapon_of(c) for c in s['gear'] + s['default_gear'] if c.get('card_type') == 'Weapon']
        qty = {}
        for c in s['gear']:
            qty[c.get('id')] = c.get('_qty', 1)
        info = {'card': card, 'subtype': subtype, 'health': health, 'actions': actions, 'weapons': ws,
                'skills': skills, 'gear': s['gear'], 'qty': qty, 'mods': mods, 'move': move, 'spot': spot}
        # fire value at each range
        fr = {0: 0.0, 1: 0.0, 2: 0.0}
        ar = 0.0
        if subtype == 'Squad':                 # Squad Soldier: own attack chart + pen of printed weapons
            pen = max([w.pen for w in ws] or [0])
            hb = spot
            for r, hit in _ss_hits(card).items():
                if r in fr:
                    fr[r] = attack_value(hit, 1, pen, False, cover_dist, alpha, per_card, hit_bonus=hb)[2]
            ar = max([attack_value(h, 1, pen, False, high_cover, alpha, per_card, hit_bonus=hb)[0]
                      for h in _ss_hits(card).values()] or [0])
        elif subtype != 'Vehicle':
            for w in ws:
                if w.melee:
                    continue
                fr[0] = max(fr[0], fire_with(w, mods, cover_dist, alpha, per_card, rng=0, spot=spot))
                fr[1] = max(fr[1], fire_with(w, mods, cover_dist, alpha, per_card, rng=1, spot=spot))
                fr[2] = max(fr[2], fire_with(w, mods, cover_dist, alpha, per_card, rng_min=2, spot=spot))
                ar = max(ar, anti_with(w, mods, high_cover, per_card, spot=spot))
        hth = hth_value(card, ws, cover_dist, alpha, per_card, extra=mods['hth']) \
            if subtype in ('Player', 'Team', 'NPS') else 0.0
        info['fire'] = fr
        info['hth'] = hth
        info['close'] = max(fr[0], hth)
        info['anti'] = ar
        soldiers.append(info)

    m = {}
    n_ps = sum(1 for s in soldiers if s['subtype'] in ('Player', 'Team'))

    # 1/2 fire
    rf = [s['actions'] * (0.6 * s['fire'][1] + 0.4 * s['fire'][2]) for s in soldiers]
    ca = [s['actions'] * s['close'] for s in soldiers]
    m['ranged_fire'] = {'raw': sum(rf), 'detail': f'α={alpha}'}
    m['close_assault'] = {'raw': sum(ca), 'detail': f'α={alpha}'}

    # 3 anti-armour
    m['anti_armour'] = {'raw': sum(s['actions'] * s['anti'] for s in soldiers),
                        'detail': 'vs Cover ≥ 6'}

    # 4 demolition: expected hits from explosive uses against a structure
    struct_cover, struct_note = _structure_cover(objectives)
    hits = 0.0
    uses_total = 0
    for s in soldiers:
        if s['subtype'] not in ('Player', 'Team'):
            continue
        for g in s['gear']:
            if g.get('card_type') != 'Weapon':
                continue
            w = weapon_of(g)
            if not w.explosion:
                continue
            uses = max(1, g.get('_qty', 1)) * (w.ammo if (w.ammo and not w.expended) else 1)
            bonus = w.bonus_vs.get('Structures', 0)
            tags = skill_effects.weapon_tags(w)
            for r, hit in w.ranges.items():
                hb, cb = skill_effects.bonuses(s['mods'], tags, r)
                dice = max([d for md, d in w.modes if md.lower() == 'explosion'] or [1]) \
                    + (s['mods']['satchel_dice'] if 'satchel' in tags else 0)
                pd = p_die(hit - bonus - hb)
                pc = p_d6(struct_cover - (w.pen + bonus + cb))
                hits += uses * dice * pd * pc / max(1, len(w.ranges))
            uses_total += uses
    m['demolition'] = {'raw': hits, 'detail': f'{uses_total} explosive uses · {struct_note}'}

    # 5 supplies: share of firepower that lasts the mission
    num = den = 0.0
    for s in soldiers:
        if s['subtype'] == 'Vehicle':
            continue
        best_f, best_w = 0.0, None
        for w in s['weapons']:
            if w.melee:
                continue
            f = max([fire_with(w, s['mods'], cover_dist, alpha, per_card, rng=r, spot=s['spot']) for r in (0, 1, 2)])
            if f > best_f:
                best_f, best_w = f, w
        if s['subtype'] == 'Squad' or best_w is None:
            f = max(s['fire'].values())
            cap = time * s['actions']
            num += f * cap
            den += f * cap
            continue
        turns_cap = time * s['actions']
        qty = s['qty'].get(next((c.get('id') for c in s['gear'] if c.get('name_en') == best_w.name), None), 1)
        if best_w.expended:
            attacks = max(1, qty)
        else:
            rel = best_w.reload or 0
            dice = max([d for _, d in best_w.modes] or [1])
            p_reload = 1 - (1 - rel / 10.0) ** dice if rel else 0.05
            attacks = (best_w.ammo or 4) / max(p_reload, 0.01)
        num += best_f * min(attacks, turns_cap)
        den += best_f * turns_cap
    m['supplies'] = {'raw': (num / den) if den else 0.0, 'detail': f'over {time} turns'}

    # 6 mobility
    objective_pos = mission.get('objective_position') or 4
    moves = max(1, objective_pos - 1) * (2 if mission.get('mission_type') == 'Raid' or
                                         any('Escape' in objective_kinds(o) for o in objectives) else 1)
    d_cards = sum(p * sum(max(0, e - s['move']) for s in soldiers)
                  for e, p in locations.items())
    need = moves * d_cards * (1 + MOVE_RESERVE)
    ps = [s for s in soldiers if s['subtype'] == 'Player']      # only Player Soldiers hold Action cards
    have = sum(s['health'] for s in ps)
    hand = (have / len(ps)) if ps else 0
    refills = max(0.0, need - have) / hand if hand else (moves * 2 if need else 0)
    total_actions = sum(s['actions'] for s in soldiers) or 1
    overhead = (moves * len(soldiers) + refills) / (total_actions * time)
    m['mobility'] = {'raw': max(0.0, 1 - overhead),
                     'detail': f'{moves} moves · {d_cards:.1f} cards/move · {refills:.1f} refills'}

    # 7 survivability
    pen_ref = pen_dist
    eff = 0.0
    for s in soldiers:
        if s['subtype'] == 'Vehicle':
            eff += s['health'] * 1.5
            continue
        cov = s['card'].get('cover') or 2
        hc = s['mods']['hostile_cover']
        pw = sum(p * p_d6(cov - (pen + hc)) for pen, p in pen_ref.items())   # P(a Hostile attack beats Terrain Cover)
        eff += (s['health'] + s['mods']['hp_add']) / max(pw, 0.1) * s['mods']['hp_mult']
    bodies = len(soldiers)
    m['survivability'] = {'raw': eff * (1 + 0.05 * max(0, bodies - 1)), 'detail': f'{bodies} bodies'}

    # 8 resilience
    fire_i = [s['actions'] * (s['close'] + 0.6 * s['fire'][1] + 0.4 * s['fire'][2]) for s in soldiers]
    total_fire = sum(fire_i)
    keep = ((total_fire - max(fire_i)) / total_fire) if total_fire and len(fire_i) > 1 else 0.0
    b = min(1.0, max(0, n_ps - 1) / 2.0)
    pos = sum(1 for s in soldiers for k in s['skills'] if k in GOOD_SKILLS)
    neg = sum(1 for s in soldiers for k in s['skills'] if k in BAD_SKILLS)
    c = min(1.0, max(0.0, 0.5 + 0.15 * (pos - neg)))
    m['resilience'] = {'raw': 0.5 * keep + 0.25 * b + 0.25 * c,
                       'detail': f'fire kept without top soldier {keep:.0%} · {n_ps} Player Soldier(s)'}

    # 9 experience
    xp = sum((s['card'].get('xp') or 0) + s['mods']['xp'] for s in soldiers)
    cx = sum(s['card'].get('cx') or 0 for s in soldiers)
    m['experience'] = {'raw': xp + CX_XP_WEIGHT * cx, 'detail': f'{xp} XP · {cx} CX'}

    return m


def _structure_cover(objectives):
    """Cover of the structure to destroy, from objective text ("Cover 4"), else the typical 4."""
    for o in objectives:
        notes = o.get('notes_en') or o.get('notes') or ''
        m = re.search(r'Cover (\d)', notes)
        if m and re.search(r'Explosion|Destroy|Structure', notes):
            return int(m.group(1)), f'structure Cover {m.group(1)}'
    return 4, 'generic structure (Cover 4)'


# ── scoring against community squads ─────────────────────────────────────────

def budget_band(budget):
    if not budget:
        return 'all'
    return 'lt40' if budget < 40 else 'lt80' if budget < 80 else 'lt120' if budget < 120 else 'ge120'


def percentile(value, sample):
    """Mid-rank percentile of value in sample (0..1); None when no sample."""
    if not sample:
        return None
    lo = sum(1 for x in sample if x < value - 1e-9)
    eq = sum(1 for x in sample if abs(x - value) <= 1e-9)
    return (lo + eq / 2.0) / len(sample)


def score_metrics(raw_metrics, budget):
    comm = reference().get('community', {})
    band = comm.get(budget_band(budget)) or {}
    if band.get('n', 0) < 8:
        band = comm.get('all') or {}
    out = {}
    for key in METRIC_KEYS:
        r = raw_metrics[key]
        sample = (band.get('values') or {}).get(key)
        out[key] = {'raw': round(r['raw'], 3), 'detail': r['detail'],
                    'score': None if sample is None else round(percentile(r['raw'], sample), 3)}
    return {'metrics': out, 'sample': {'band': budget_band(budget), 'n': band.get('n', 0)}}


# ── ORM bridge ────────────────────────────────────────────────────────────────

def soldier_input(card, gear_pairs):
    """One soldier for `analyse`: card (ORM) + [(gear card ORM, quantity)] + the soldier's printed gear."""
    from app.models import CardAssociation
    gear = []
    for gc, qty in gear_pairs:
        d = gc.to_card_detail()
        d['_qty'] = qty
        gear.append(d)
    default = []
    for a in CardAssociation.query.filter_by(parent_card_id=card.id).order_by(CardAssociation.id).all():
        if a.child_card is None:            # dangling association (child card removed): nothing to count
            continue
        d = a.child_card.to_card_detail()
        d['_qty'] = a.quantity
        default.append(d)
    return {'card': card.to_card_detail(), 'gear': gear, 'default_gear': default}


def squad_input(squad):
    """Build the plain-dict input for `analyse` from a Squad ORM object."""
    soldiers = [soldier_input(ss.card, [(sg.card, sg.quantity) for sg in ss.gear]) for ss in squad.soldiers]
    mc = squad.mission_card
    mission = {'time': mc.time, 'objective_position': mc.objective_position, 'mission_type': mc.card_subtype,
               'budget': mc.resources}
    objectives = [{'objective_family': so.card.objective_family, 'mechanic': so.card._objective_mechanic(),
                   'notes_en': so.card.notes} for so in squad.objectives]
    return {'soldiers': soldiers}, mission, objectives


def squad_metrics(squad):
    data, mission, objectives = squad_input(squad)
    raw = analyse(data, mission, objectives)
    res = score_metrics(raw, mission.get('budget'))
    res['alpha'] = alpha_for(objectives, mission.get('mission_type'))
    res['version'] = 0     # G0 estimate
    return res
