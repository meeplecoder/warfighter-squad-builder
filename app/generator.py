"""
Squad generator (spec 13) — blueprint /api/generator, login required.

  GET  /api/generator/options    what the form can offer, restricted to the user's owned modules
  POST /api/generator/generate   resolve inputs (defaults + seeded random picks) → build a squad → explain it

Engine v0: a greedy builder driven by the metric weights of the objective (spec 12 §7.3) and the
estimated card values from app/metrics.py. "Optimal" is the best squad this greedy search finds
(deterministic for the same inputs + seed); "Good enough" perturbs the card values with seeded noise,
so each seed gives a different near-best squad. Kit search (DP), beam search, annealing, band
lightening and the Interesting/Challenge twists are later phases (TODO.md).

Everything the response says about *why* is returned as codes + params; the client translates.
"""
import random
import re
import secrets

from flask import Blueprint, request, jsonify
from flask_login import current_user
from sqlalchemy import or_

from app import db, limiter
from app import metrics, skill_effects, rules as rules_module
from app.i18n import _
from app.models import Card, UserModule, CUSTOM_MODULE
from app.utils import normalize_nation, nation_filter_clause, theater_from_raw_type

generator_bp = Blueprint('generator', __name__)

ENGINE_VERSION = 2
MAX_ALTERNATIVES = 2
ALT_CANDIDATES = 4            # builds tried (each pushes one weak metric) to find the alternatives
ALT_MIN_FITNESS = 0.85        # of the main squad's fitness
ALT_MAX_SIMILARITY = 0.8      # Jaccard similarity of the card sets vs the main squad / each other
DEFAULT_MAX_SOLDIERS = 8      # table space / card burden; the form can raise or lower it
MAX_SUSTAINED_PER_PS = 1      # one real gun per Player Soldier; the rest is one-shot / thrown
MAX_ONESHOT_TYPES = 3
# Community heuristics (ytb_squadbuilding_tips.md): soft priors, not rules
FIREPOWER_FLOOR = 2.0         # "firepower first": no objective weighs ranged fire / close assault below this
PS_MIN_SHARE = 0.55           # "play the Player Soldier as the star": share of the spend in PS + their gear
PS_MIN_MOVEMENT = 2           # PS movement >= 2 (3-4 ideal)
CANTEEN_NAME = 'Canteen'      # "spare discard resource": expend to draw 3 cards (Limit 2 per Soldier)
CANTEEN_SECOND_BUDGET = 60    # a second Canteen (on another PS) from this budget up
BUNDLE_GRENADES = 3           # "thrower + Close Combat": grenades carried by the bundle soldier
BUNDLE_SKILLS = ('Close Combat', 'Pitcher')
FODDER_MAX_COST = 3           # cheap bodies that soak shots, bought with leftover RP
CLASSIC_CHECKS = ('ps_movement', 'ps_share', 'medic', 'canteen', 'bundle', 'sniper', 'anti_armour')
MEDIC_MIN_BUDGET = 30         # "always bring a medic" — only worth the slot above this budget
_ANTI_NEED = re.compile(r'\b(Vehicle|Tank|Armou?r)', re.I)
QUALITIES = ('optimal', 'good_enough')
TWISTS = ('interesting', 'challenge', 'one_hero', 'all_squad', 'no_mg', 'light_spender')
SOLDIER_TYPES = ('NPS', 'Squad', 'Vehicle', 'Team')
HOSTILE_LEVELS = ('frontline', 'elite')

# Importance of each metric by objective kind: H/M/L → 3/2/1 (spec 12 §7.3)
_GRID = {   # metric: (Elim, KillSpec, KeepClear, Destroy, Escape, Fallback, HoldLine)
    'ranged_fire':   (3, 2, 3, 1, 2, 3, 3),
    'close_assault': (3, 2, 2, 3, 2, 2, 2),
    'anti_armour':   (1, 3, 1, 2, 1, 1, 1),
    'demolition':    (1, 1, 1, 3, 1, 1, 1),
    'supplies':      (2, 1, 3, 1, 1, 3, 3),
    'mobility':      (2, 2, 2, 2, 3, 1, 1),
    'survivability': (2, 2, 2, 2, 3, 3, 3),
    'resilience':    (1, 1, 2, 1, 3, 2, 2),
    'experience':    (2, 2, 2, 1, 1, 2, 2),
}
_KIND_COL = {'Eliminate Hostiles': 0, 'Kill Specified Hostile': 1, 'Keep Clear': 2, 'Destroy Target': 3,
             'Escape': 4, 'Fallback': 5, 'Right Flank': 6}
_MISSION_COL = {'Holding Action': 5, 'Hold the Line': 6}

# Usual enemy per theater (card deck name) when the user does not choose one; unknown theaters → no default
_ENEMY_BY_THEATER = {}
for _enemy, _theaters in {
    'Japan': ('Jungle', 'Far East', 'Guadalcanal', 'Attu', 'Iwo Jima', 'Tarawa', 'Force 136'),
    'German': ('Europe', 'Russia', 'North Africa', 'Mediterannean', 'Mediterranean', 'Mokra', 'Bastogne', 'St Nazaire',
               'Crete1', 'Crete2', 'Narvik', 'Castle Itter', 'Saint-Lô', 'Pegasus Bridge', 'Dieppe', 'Rimini',
               'Italian Partisans', 'LRDG', 'Bir Hakeim'),
    'Italian': ('Bardia',),
    'Russian': ('Raate Road',),
}.items():
    for _t in _theaters:
        _ENEMY_BY_THEATER[_t] = _enemy


_AXIS = {'German', 'Japan', 'Italian'}


def _random_mission_fits(m, nation):
    """Random picks only: skip fantasy sets and keep the side sensible (Axis nations play in the theaters
    where they are the usual enemy; Allied nations in the theaters of an Axis enemy)."""
    theater = theater_from_raw_type(m.raw_type or '')
    if theater in _FANTASY_MODULES or 'Undead' in (m.raw_type or '') or 'Undead' in (m.nation or ''):
        return False
    usual = _ENEMY_BY_THEATER.get(theater)
    if nation in _AXIS:
        return usual == nation
    return usual in _AXIS and usual != nation


def _default_enemy(theater, nation):
    enemy = _ENEMY_BY_THEATER.get(theater)
    if enemy and enemy == nation:                 # playing the usual enemy: they face the Americans
        return 'US'
    return enemy

# Missions the random pick avoids: special setups that need their own cards
_SPECIAL_MISSIONS = ('Airborne', 'Shore Invasion')


# ── owned modules ─────────────────────────────────────────────────────────────

def _uid(user):
    """Anonymous visitors have no id: -1 matches no owner, so they see no custom cards."""
    return user.id if user.is_authenticated else -1


def _excluded_modules(user):
    if not user.is_authenticated:
        return set()                      # anonymous: the whole catalogue
    return {r.module for r in UserModule.query.filter_by(user_id=user.id, owned=0).all()}


def _available(query, excluded):
    return query.filter(~Card.module.in_(excluded)) if excluded else query


def _all_modules():
    return [r[0] for r in Card.catalog().with_entities(Card.module).distinct().all() if r[0]]


# ── options ───────────────────────────────────────────────────────────────────

def _light_card(c):
    return {'id': c.id, 'name': c.display_name(), 'module': c.module, 'nation': c.nation,
            'nation_base': normalize_nation(c.nation) if c.nation else None,
            'theater': theater_from_raw_type(c.raw_type or '')}


@generator_bp.route('/options', methods=['GET'])
def options():
    excluded = _excluded_modules(current_user)
    mods = _all_modules()
    base = Card.query.filter(or_(Card.module != CUSTOM_MODULE, Card.owner_user_id == _uid(current_user)))
    base = _available(base, excluded)

    ps = _available(Card.catalog(), excluded).filter(Card.card_type == 'Soldier', Card.card_subtype == 'Player').all()
    nations = {}
    for c in ps:
        if c.nation:
            nations.setdefault(normalize_nation(c.nation), set()).add(c.name)

    missions = []
    for c in base.filter(Card.card_type == 'Mission').order_by(Card.module, Card.number).all():
        d = _light_card(c)
        d.update(mission_type=c.card_subtype, resources=c.resources, time=c.time)
        missions.append(d)
    objectives = []
    for c in base.filter(Card.card_type == 'Objective').order_by(Card.module, Card.number).all():
        d = _light_card(c)
        d.update(mechanic=c._objective_mechanic(), family=c.objective_family or '')
        objectives.append(d)
    enemy = sorted({normalize_nation(r[0]) for r in Card.catalog().with_entities(Card.nation)
                    .filter(Card.card_type == 'Soldier').distinct().all() if r[0]})
    return jsonify(
        nations=[{'code': n, 'player_soldiers': len(v)} for n, v in sorted(nations.items())],
        enemy_nations=enemy,
        missions=missions, objectives=objectives,
        twists=list(TWISTS), qualities=list(QUALITIES), soldier_types=list(SOLDIER_TYPES),
        collection={'owned_modules': len(mods) - len(excluded & set(mods)), 'total_modules': len(mods)},
        engine_version=ENGINE_VERSION,
    )


# ── request parsing ───────────────────────────────────────────────────────────

class GenError(Exception):
    def __init__(self, code, message, **params):
        super().__init__(message)
        self.code, self.message, self.params = code, message, params


def _int(v, lo=None, hi=None):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _ids(v):
    return [i for i in (_int(x) for x in (v or [])) if i]


def parse_request(data):
    r = {}
    r['nation'] = (data.get('nation') or 'random').strip() or 'random'
    r['mission_card_id'] = _int(data.get('mission_card_id'))
    r['objective_card_id'] = _int(data.get('objective_card_id'))
    r['players'] = _int(data.get('players'), 1, 6)
    enemy = (data.get('enemy_nation') or '').strip()
    r['enemy_nation'] = enemy or None
    lvl = (data.get('hostile_level') or 'frontline').lower()
    r['hostile_level'] = lvl if lvl in HOSTILE_LEVELS else 'frontline'
    q = data.get('quality') or 'optimal'
    r['quality'] = q if q in QUALITIES else 'optimal'
    try:
        r['variety'] = min(1.0, max(0.0, float(data.get('variety', 0.5))))
    except (TypeError, ValueError):
        r['variety'] = 0.5
    tw = data.get('twist') or None
    r['twist'] = tw if tw in TWISTS and r['quality'] == 'good_enough' else None
    emph = {}
    for k, v in (data.get('emphasis') or {}).items():
        if k in metrics.METRIC_KEYS and _int(v) in (-1, 1):
            emph[k] = _int(v)
    r['emphasis'] = dict(list(emph.items())[:2])
    sp = data.get('spend') or {}
    r['spend'] = {'type': sp.get('type') if sp.get('type') in ('auto', 'full', 'cap') else 'auto',
                  'max_rp': _int(sp.get('max_rp'), 1, 500)}
    r['classic'] = data.get('classic', True) not in (False, 'false', 'off', 0, '0')     # community-balance preset
    r['include'] = _ids(data.get('include'))
    r['exclude'] = _ids(data.get('exclude'))
    types = data.get('soldier_types')
    r['soldier_types'] = [t for t in (types if isinstance(types, list) else SOLDIER_TYPES) if t in SOLDIER_TYPES]
    r['max_soldiers'] = _int(data.get('max_soldiers'), 1, 20)
    alts = _int(data.get('alternatives'), 0, MAX_ALTERNATIVES)
    r['alternatives'] = MAX_ALTERNATIVES if alts is None else alts
    seed = str(data.get('seed') or '').strip()[:32]
    r['seed'] = seed or secrets.token_hex(2).upper()
    return r


# ── resolution ────────────────────────────────────────────────────────────────

def _mission_ok_for_nation(m, nation):
    return not m.nation or normalize_nation(m.nation) == nation


def _objective_pool(mission, excluded, user):
    """Objectives that fit the mission (theater + mission-type pairing rules)."""
    q = Card.query.filter(Card.card_type == 'Objective',
                          or_(Card.module != CUSTOM_MODULE, Card.owner_user_id == _uid(user)))
    objs = _available(q, excluded).order_by(Card.id).all()
    mtype = mission.card_subtype or ''
    wanted = {'Holding Action': 'Fallback', 'Hold the Line': 'Right Flank'}.get(mtype)
    theater = theater_from_raw_type(mission.raw_type or '')
    out = []
    for o in objs:
        fam = o.objective_family or ''
        if wanted:
            if fam != wanted:
                continue
        elif fam in ('Fallback', 'Right Flank'):
            continue
        if mtype == 'Raid' and o.card_subtype == 'Escape':
            continue
        if mtype == 'Shore Invasion' and fam != 'Shore':
            continue
        if mtype != 'Shore Invasion' and fam in ('Shore', 'Airborne', 'Embedded'):
            continue
        out.append(o)
    same = [o for o in out if theater_from_raw_type(o.raw_type or '') == theater]
    return same or out


def resolve(req, user, rng):
    excluded = _excluded_modules(user)
    ps_all = (_available(Card.catalog(), excluded)
              .filter(Card.card_type == 'Soldier', Card.card_subtype == 'Player').order_by(Card.id).all())
    nations = sorted({normalize_nation(c.nation) for c in ps_all if c.nation})
    if not nations:
        raise GenError('NO_PLAYER_SOLDIER_OWNED', 'None of your modules has a Player Soldier.')

    mission = None
    if req['mission_card_id']:
        mission = db.session.get(Card, req['mission_card_id'])
        if not mission or mission.card_type != 'Mission' or mission.module in excluded or \
                (mission.module == CUSTOM_MODULE and mission.owner_user_id != _uid(user)):
            raise GenError('MISSION_NOT_PLAYABLE', 'That mission is not in your collection.')

    nation = req['nation']
    if nation == 'random':
        cands = [n for n in nations if mission is None or _mission_ok_for_nation(mission, n)]
        if not cands:
            raise GenError('MISSION_NOT_PLAYABLE', 'No owned nation can play that mission.')
        nation = rng.choice(cands)
    elif nation not in nations:
        raise GenError('NO_PLAYER_SOLDIER_OWNED', f'You own no {nation} Player Soldier.', nation=nation)

    if mission is None:
        q = Card.query.filter(Card.card_type == 'Mission', Card.resources.isnot(None),
                              or_(Card.module != CUSTOM_MODULE, Card.owner_user_id == _uid(user)))
        pool = [m for m in _available(q, excluded).order_by(Card.id).all()
                if _mission_ok_for_nation(m, nation) and (m.card_subtype or '') not in _SPECIAL_MISSIONS]
        fitting = [m for m in pool if _random_mission_fits(m, nation)]
        pool = fitting or pool
        if not pool:
            raise GenError('MISSION_NOT_PLAYABLE', 'No owned mission fits.')
        mission = rng.choice(pool)
    elif not _mission_ok_for_nation(mission, nation):
        raise GenError('MISSION_NOT_PLAYABLE', 'That mission belongs to another nation.')
    if not mission.resources:
        raise GenError('MISSION_NOT_PLAYABLE', 'That mission has no RP budget.')

    objective = None
    if req['objective_card_id']:
        objective = db.session.get(Card, req['objective_card_id'])
        if not objective or objective.card_type != 'Objective' or objective.module in excluded:
            raise GenError('MISSION_NOT_PLAYABLE', 'That objective is not in your collection.')
    else:
        pool = _objective_pool(mission, excluded, user)
        objective = rng.choice(pool) if pool else None

    theater = theater_from_raw_type(mission.raw_type or '')
    enemy = req['enemy_nation'] or _default_enemy(theater, nation)
    # Hostile statistics of that enemy and level (falls back to all Hostile cards when unknown)
    hostile = metrics._hostile_ref(enemy, req['hostile_level'].capitalize()) if enemy else metrics._hostile_ref()
    return {'nation': nation, 'mission': mission, 'objective': objective, 'excluded': excluded,
            'enemy': enemy, 'theater': theater, 'hostile': hostile}


# ── card values ───────────────────────────────────────────────────────────────

def _needs_anti_armour(objective):
    """The objective names a vehicle / armoured target, or asks to kill a specified Hostile."""
    return bool(objective and (objective.card_subtype == 'Kill Specified Hostile'
                               or _ANTI_NEED.search(objective.notes or '')))


def _profile(objective, mission, emphasis, classic=True):
    col = _MISSION_COL.get(mission.card_subtype or '')
    if col is None and objective is not None:
        col = _KIND_COL.get(objective.card_subtype or '', _KIND_COL.get(objective.objective_family or ''))
        if objective.objective_family in ('Fallback', 'Right Flank'):
            col = _KIND_COL[objective.objective_family]
    col = 0 if col is None else col
    w = {k: float(v[col]) for k, v in _GRID.items()}
    if classic:
        w['ranged_fire'] = max(w['ranged_fire'], FIREPOWER_FLOOR)
        w['close_assault'] = max(w['close_assault'], FIREPOWER_FLOOR)
    if classic and _needs_anti_armour(objective):
        w['anti_armour'] = max(w['anti_armour'], 3.0)
    for k, d in emphasis.items():
        w[k] = max(0.5, w[k] + 1.5 * d)
    return w


def _light_weapon(c):
    return {'id': c.id, 'name': c.name, 'name_en': c.name, 'card_subtype': c.card_subtype, 'notes_en': c.notes,
            'weapon_range_table': c.weapon_range_table, 'weapon_mode_table': c.weapon_mode_table}


def _gear_weight(c):
    """Loadout weight of a Weapon/Equipment card (same rule as rules.gear_loadout_weight)."""
    if c.loadout is not None:
        return c.loadout
    return c.resource_cost or 0


def _weapon_value(card, hostile, alpha, w):
    wp = metrics.weapon_of(_light_weapon(card))
    if wp.melee or not wp.ranges:
        return 0.0, wp
    per_card = hostile['per_card']
    cover = hostile['cover']
    high = metrics._conditional(cover, 6)
    f0 = metrics.best_fire(wp, 0, cover, alpha, per_card)
    f1 = metrics.best_fire(wp, 1, cover, alpha, per_card)
    f2 = metrics.best_fire(wp, None, cover, alpha, per_card, rng_min=2)
    bonus = wp.bonus_vs.get('Vehicles', 0)
    anti = max([metrics.attack_value(h, d, wp.pen + bonus, wp.spray or m.lower() == 'explosion', high, 0,
                                     per_card, hit_bonus=bonus)[0]
                for h in wp.ranges.values() for m, d in (wp.modes or [('Semi', 1)])] or [0])
    v = w['ranged_fire'] * (0.6 * f1 + 0.4 * f2) + w['close_assault'] * f0 + 0.6 * w['anti_armour'] * anti
    if wp.expended:
        v *= 0.55
        if wp.explosion:
            v += 0.4 * w['demolition'] * 1.0
    if wp.reload is not None and wp.ammo:      # sustained fire matters for supplies-heavy objectives
        v *= 1 + 0.04 * w['supplies']
    return v, wp


# ── skills and armor: marginal gain on the metrics ────────────────────────────

def _scales():
    """Community median per metric — the scale that turns a raw value into a comparable 0..1 score."""
    vals = (metrics.reference().get('community', {}).get('all') or {}).get('values') or {}
    out = {}
    for k in metrics.METRIC_KEYS:
        v = sorted(vals.get(k) or [])
        out[k] = max(v[len(v) // 2], 1e-6) if v else 1.0
    return out


def _squad_score(raw, weights, scales):
    """Weighted, saturating score: x/(1+x) of raw/median, so every metric lives on the same 0..1 scale."""
    total = 0.0
    for k, w in weights.items():
        x = max(raw[k]['raw'], 0.0) / scales[k]
        total += w * x / (1.0 + x)
    return total


# Skills and equipment the engine may buy (names → effects in app/skill_effects.py)
BUYABLE_SKILLS = tuple(skill_effects.SKILL_EFFECTS)
BUYABLE_EQUIPMENT = ('Body Armor', 'Lucky Helmet')


# ── the builder ───────────────────────────────────────────────────────────────

_FANTASY_MODULES = ('Dagon', "R'lyeh")


def _off_theme(c, mission):
    """Undead / Lovecraft gear stays out of a normal mission unless the mission is from that set."""
    if c.card_subtype == 'Undead' or c.module in _FANTASY_MODULES:
        return c.module != mission.module
    return False


def _nation_ok(c, nation):
    return not c.nation or normalize_nation(c.nation) == nation


def _dedupe_by_name(cards):
    seen, out = set(), []
    for c in cards:
        if c.name not in seen:
            seen.add(c.name)
            out.append(c)
    return out


def _ps_score(c, lm, classic=True):
    cost = max(c.resource_cost or 1, 1)
    base = (c.health or 0) + 0.5 * max(0, (c.loadout or 0) + lm) + 1.2 * (c.movement or 0) \
        + 0.8 * (c.cx or 0) + 0.3 * (c.xp or 0) + 0.6 * (c.cover or 0)
    if classic and (c.movement or 0) < PS_MIN_MOVEMENT:
        base *= 0.6
    return base / (cost ** 0.5)


def _wants_bundle(weights, objective, budget):
    """The scenario rewards Range 0 / explosive work: close-assault or demolition weighted High, or the objective
    speaks of Range 0 / Explosion attacks."""
    if budget < MEDIC_MIN_BUDGET:
        return False
    notes = (objective.notes or '') if objective else ''
    return (weights['close_assault'] >= 3 or weights['demolition'] >= 3
            or bool(re.search(r'Range 0|Explosion Attacks only', notes)))


def _raw_score(ctx, chosen, weights):
    mission, objective = ctx['mission'], ctx['objective']
    objs = [{'objective_family': objective.objective_family, 'mechanic': objective._objective_mechanic(),
             'notes_en': objective.notes}] if objective else []
    mdict = {'time': mission.time, 'objective_position': mission.objective_position, 'mission_type': mission.card_subtype}
    inputs = [metrics.soldier_input(s['card'], [(g, q) for g, q in s['gear']]) for s in chosen]
    return _squad_score(metrics.analyse({'soldiers': inputs}, mdict, objs, hostile=ctx['hostile']), weights, _scales())


def _wants_sniper(objective):
    """Kill Specified Hostile whose target is screened (Officer, Sniper, VIP, gun crew…): it must be reached over the
    screen, so a long-range shot pays. Vehicles are the anti-armour case, not this one."""
    if not objective or objective.card_subtype != 'Kill Specified Hostile':
        return False
    notes = objective.notes or ''
    return 'Screen' in notes and not _ANTI_NEED.search(notes)


def build(req, ctx, rng, weights_override=None):
    """Greedy build plus optional variants, each kept only when it scores higher on the objective-weighted metrics
    (ties: without):  bundle (grenades + Close Combat, Range 0 / explosive scenarios) · sniper (long-range rifle +
    Marksman for a screened specified target) · offload (an NPS/Squad Soldier with a printed machine gun instead of
    the Player Soldier carrying one).  The winning flags are left in ctx['variant'] for the alternatives."""
    state = rng.getstate()
    plain = _build(req, ctx, rng, weights_override)
    ctx['variant'] = {}
    if not req['classic']:
        return plain
    wanted = []
    if _wants_bundle(plain[2], ctx['objective'], plain[1]):
        wanted.append('bundle')
    if _wants_sniper(ctx['objective']) and plain[1] >= MEDIC_MIN_BUDGET:
        wanted.append('sniper')
    if plain[1] >= MEDIC_MIN_BUDGET:
        wanted.append('offload')
    if not wanted:
        return plain
    best, best_score = plain, _raw_score(ctx, plain[0], plain[2]) + 1e-9
    good = []
    for flag in wanted:
        rng.setstate(state)
        cand = _build(req, ctx, rng, weights_override, **{flag: True})
        sc = _raw_score(ctx, cand[0], cand[2])
        if sc > _raw_score(ctx, plain[0], plain[2]) + 1e-9:
            good.append(flag)
            if sc > best_score:
                best, best_score, ctx['variant'] = cand, sc, {flag: True}
    if len(good) > 1:
        rng.setstate(state)
        cand = _build(req, ctx, rng, weights_override, **{f: True for f in good})
        sc = _raw_score(ctx, cand[0], cand[2])
        if sc > best_score:
            best, ctx['variant'] = cand, {f: True for f in good}
    return best


def _build(req, ctx, rng, weights_override=None, bundle=False, sniper=False, offload=False):
    nation, mission, objective, excluded = ctx['nation'], ctx['mission'], ctx['objective'], ctx['excluded']
    classic = req['classic']
    lm = mission.loadout_modifier or 0
    budget = mission.resources
    if req['spend']['type'] == 'cap' and req['spend']['max_rp']:
        budget = min(budget, req['spend']['max_rp'])
    elif req['twist'] == 'light_spender':
        budget = int(budget * 0.7)
    elif req['twist'] == 'challenge':
        budget = int(budget * 0.8)
    weights = dict(weights_override) if weights_override else _profile(objective, mission, req['emphasis'], req['classic'])
    objs = [{'objective_family': objective.objective_family, 'mechanic': objective._objective_mechanic(),
             'notes_en': objective.notes}] if objective else []
    alpha = metrics.alpha_for(objs, mission.card_subtype)
    hostile = ctx['hostile']
    variety = req['variety']
    if req['quality'] == 'good_enough':
        spread = 0.08 + 0.4 * variety
        if req['twist'] == 'interesting' and not weights_override:
            weights = {k: v * rng.uniform(0.4, 1.6) for k, v in weights.items()}
        noise = lambda: rng.uniform(1 - spread, 1 + spread)
    else:
        noise = lambda: 1.0

    excl_ids = set(req['exclude'])
    excl_names = {c.name for c in Card.query.filter(Card.id.in_(excl_ids)).all()} if excl_ids else set()
    allowed = lambda c: c.id not in excl_ids and c.name not in excl_names
    interior = bool(re.search(r'\bInterior\b', mission.notes or ''))
    shore = (mission.card_subtype or '') == 'Shore Invasion'
    airborne = (mission.card_subtype or '') == 'Airborne'

    cat = _available(Card.catalog(), excluded)
    soldier_q = cat.filter(Card.card_type == 'Soldier').order_by(Card.id).all()
    soldier_q = [c for c in soldier_q if _nation_ok(c, nation) and allowed(c) and c.resource_cost]
    if airborne:
        soldier_q = [c for c in soldier_q if 'Airborne' in (c.nation or '')]
    ps_pool = _dedupe_by_name([c for c in soldier_q if c.card_subtype == 'Player'])
    if not ps_pool:
        raise GenError('NO_PLAYER_SOLDIER_OWNED', f'You own no {nation} Player Soldier for this mission.', nation=nation)

    types = set(req['soldier_types'])
    if interior:
        types.discard('Vehicle')
    support_pool = _dedupe_by_name([c for c in soldier_q if c.card_subtype in types and c.card_subtype != 'Player'
                                    and c.card_subtype in ('NPS', 'Squad', 'Vehicle', 'Team')])
    if req['twist'] == 'all_squad':
        support_pool = [c for c in support_pool if c.card_subtype == 'Squad']
    max_soldiers = req['max_soldiers'] or DEFAULT_MAX_SOLDIERS

    # gear pool: weapons the nation can use, one printing per name
    weapons = [c for c in cat.filter(Card.card_type == 'Weapon').order_by(Card.id).all()
               if _nation_ok(c, nation) and allowed(c) and c.resource_cost]
    weapons = _dedupe_by_name([c for c in weapons if not _off_theme(c, mission)])
    if shore:
        weapons = [c for c in weapons if 'Smoke' not in c.name]
    wvals = {}
    for c in weapons:
        v, wp = _weapon_value(c, hostile, alpha, weights)
        if req['twist'] == 'no_mg' and wp.spray:
            v = 0.0
        if v > 0:
            wvals[c.id] = (v, wp)
    weapons = [c for c in weapons if c.id in wvals]
    by_id = {c.id: c for c in weapons}

    # players target
    rec = 1 if budget < 40 else 2 if budget < 80 else 3 if budget < 120 else 4
    n_ps = req['players'] or rec
    if classic and not support_pool and not req['players']:      # no NPS / Squad Soldiers to lean on (e.g. Germans): PS carry the squad
        n_ps = min(rec + 1, 4)
    if req['twist'] == 'one_hero':
        n_ps = 1

    chosen, spent = [], 0          # chosen: list of dicts {card, gear:[[card, qty]], loadout_left}
    locked = db_cards(req['include'])

    def add_soldier(c, gear_budget_ok=True):
        nonlocal spent
        chosen.append({'card': c, 'gear': [], 'left': max(0, (c.loadout or 0) + lm) if c.card_subtype == 'Player' else 0})
        spent += c.resource_cost or 0

    names_in = set()
    for c in locked:
        if c.card_type == 'Soldier' and _nation_ok(c, nation) and c.module not in excluded and c.name not in names_in \
                and spent + (c.resource_cost or 0) <= budget and len(chosen) < max_soldiers:
            add_soldier(c)
            names_in.add(c.name)

    ranked_ps = sorted(ps_pool, key=lambda c: (-_ps_score(c, lm, classic) * noise(), c.id))
    have_ps = lambda: sum(1 for s in chosen if s['card'].card_subtype == 'Player')
    for c in ranked_ps:
        if have_ps() >= n_ps or len(chosen) >= max_soldiers:
            break
        if c.name in names_in:
            continue
        if spent + c.resource_cost <= budget * 0.6 or (not have_ps() and spent + c.resource_cost <= budget):
            add_soldier(c)
            names_in.add(c.name)
    # a small budget may not fit the wanted number at the 60 % rule: keep a little RP for gear instead
    for c in ranked_ps:
        if have_ps() >= n_ps or len(chosen) >= max_soldiers:
            break
        if c.name not in names_in and spent + c.resource_cost <= budget - 6:
            add_soldier(c)
            names_in.add(c.name)
    if not have_ps():
        cheap = sorted(ps_pool, key=lambda c: (c.resource_cost, c.id))
        if not cheap or cheap[0].resource_cost > budget:
            raise GenError('BUDGET_TOO_LOW', 'The budget does not cover the cheapest Player Soldier.')
        add_soldier(cheap[0])
        names_in.add(cheap[0].name)

    def pick_for(s, cap):
        """Best next weapon for one Player Soldier within the cap, or None."""
        wgear = [g for g in s['gear'] if g[0].id in wvals]        # weapons only (gear also holds skills / armor)
        have = {g[0].id: g for g in wgear}
        sustained = [g for g in wgear if not wvals[g[0].id][1].expended]
        oneshot = [g for g in wgear if wvals[g[0].id][1].expended]
        best = None
        for c in weapons:
            wt = _gear_weight(c)
            if wt > s['left'] or spent + c.resource_cost > cap:
                continue
            v, wp = wvals[c.id]
            if offload and wp.spray and not wp.expended:
                continue          # the machine gun is carried by the NPS
            cur = have.get(c.id)
            if wp.expended:
                if not sustained and any(not wvals[x.id][1].expended and _gear_weight(x) <= s['left']
                                         and spent + x.resource_cost <= cap for x in weapons):
                    continue      # a real gun first
                if cur and cur[1] >= 2:
                    continue
                if not cur and len(oneshot) >= MAX_ONESHOT_TYPES:
                    continue
            elif len(sustained) >= MAX_SUSTAINED_PER_PS:
                continue
            score = v * noise() / max(wt, 1) ** 0.5
            if cur:
                score *= 0.6
            if best is None or score > best[0]:
                best = (score, c, wt)
        return best

    def equip(cap):
        """Round-robin gear for the Player Soldiers while total spend stays <= cap: every soldier gets a
        gun before anyone gets a second item."""
        nonlocal spent
        pss = [x for x in chosen if x['card'].card_subtype == 'Player']
        for _round in range(6):
            added = False
            for s in pss:
                best = pick_for(s, cap)
                if best is None:
                    continue
                _, c, wt = best
                cur = next((g for g in s['gear'] if g[0].id == c.id), None)
                if cur:
                    cur[1] += 1
                else:
                    s['gear'].append([c, 1])
                s['left'] -= wt
                spent += c.resource_cost
                added = True
            if not added:
                break

    # locked gear first
    for c in locked:
        if c.card_type == 'Weapon' and c.id in by_id:
            for s in chosen:
                if s['card'].card_subtype == 'Player' and _gear_weight(c) <= s['left'] and spent + c.resource_cost <= budget:
                    s['gear'].append([c, 1])
                    s['left'] -= _gear_weight(c)
                    spent += c.resource_cost
                    break

    def place_bundle():
        """Grenades (the best owned Thrown one) + Close Combat + Pitcher on the Player Soldier with the most room."""
        nonlocal spent
        nades = [c for c in weapons if c.card_subtype == 'Thrown' and c.id in wvals and wvals[c.id][1].expended]
        pss = [x for x in chosen if x['card'].card_subtype == 'Player']
        skills = {c.name: c for c in _dedupe_by_name(
            [c for c in cat.filter(Card.card_type == 'Skill', Card.name.in_(BUNDLE_SKILLS)).order_by(Card.id).all()
             if _nation_ok(c, nation) and allowed(c) and c.resource_cost is not None])}
        if not nades or not pss or 'Close Combat' not in skills:
            return
        x = max(pss, key=lambda x: (x['left'], x['card'].movement or 0, -x['card'].id))
        nade = max(nades, key=lambda c: (wvals[c.id][0] / max(_gear_weight(c), 1), -c.id))
        lim = re.search(r'Limit (\d+) per Soldier', nade.notes or '')
        qty = BUNDLE_GRENADES
        if lim:
            qty = min(qty, int(lim.group(1)))
        cc = skills['Close Combat']
        while qty and (_gear_weight(nade) * qty > x['left'] or spent + nade.resource_cost * qty + cc.resource_cost > budget):
            qty -= 1
        if not qty:
            return
        x['gear'].append([nade, qty])
        x['left'] -= _gear_weight(nade) * qty
        spent += nade.resource_cost * qty
        for name in BUNDLE_SKILLS:
            sk = skills.get(name)
            if sk and spent + sk.resource_cost <= budget and not any(g[0].name == name for g in x['gear']):
                x['gear'].append([sk, 1])
                spent += sk.resource_cost

    def place_sniper():
        """The weapon with the best fire at Range 2+ plus Marksman (and Rifleman for a rifle) on the Player Soldier
        with the most room: the shot that reaches a screened Officer / Sniper / gun crew."""
        nonlocal spent
        pss = [x for x in chosen if x['card'].card_subtype == 'Player']
        if not pss:
            return
        x = max(pss, key=lambda x: (x['left'], x['card'].movement or 0, -x['card'].id))
        cover, per_card = hostile['cover'], hostile['per_card']
        cands = []
        for c in weapons:
            wp = wvals[c.id][1]
            if wp.expended or wp.spray or _gear_weight(c) > x['left'] or spent + c.resource_cost > budget:
                continue
            cands.append((metrics.best_fire(wp, None, cover, alpha, per_card, rng_min=2) / max(c.resource_cost, 1) ** 0.3,
                          -c.id, c, wp))
        if not cands:
            return
        _, _, gun, wp = max(cands)
        x['gear'].append([gun, 1])
        x['left'] -= _gear_weight(gun)
        spent += gun.resource_cost
        skills = {c.name: c for c in _dedupe_by_name(
            [c for c in cat.filter(Card.card_type == 'Skill', Card.name.in_(('Marksman', 'Rifleman'))).order_by(Card.id).all()
             if _nation_ok(c, nation) and allowed(c) and c.resource_cost is not None])}
        for name in ('Marksman', 'Rifleman'):
            sk = skills.get(name)
            if sk and (name != 'Rifleman' or 'rifle' in skill_effects.weapon_tags(wp)) \
                    and spent + sk.resource_cost <= budget and not any(g[0].name == name for g in x['gear']):
                x['gear'].append([sk, 1])
                spent += sk.resource_cost

    def place_offload():
        """An NPS / Squad Soldier whose printed gear is a machine gun (value per RP), so no Player Soldier has to buy
        one: the Player Soldiers then keep to rifles, SMGs and grenades (pick_for skips Spray weapons)."""
        mg = []
        for c in support_pool:
            if c.name in names_in or c.card_subtype not in ('NPS', 'Squad') or c.resource_cost > budget - spent:
                continue
            printed = metrics.soldier_input(c, [])['default_gear']
            if any(g.get('card_type') == 'Weapon' and metrics.weapon_of(g).spray for g in printed):
                mg.append(c)
        if not mg or len(chosen) >= max_soldiers:
            return
        best = max(mg, key=lambda c: ((c.health or 1) + 2 * (c.actions or 0)) / c.resource_cost - 0 * c.id)
        add_soldier(best)
        names_in.add(best.name)

    # a medic first (before weapons use up the Loadout): First Aid Kit on the Player Soldier with the most room left
    aid = next(iter(_dedupe_by_name([c for c in cat.filter(Card.card_type == 'Equipment', Card.name == 'First Aid Kit')
                                     .order_by(Card.id).all() if allowed(c) and _nation_ok(c, nation)])), None)
    if classic and aid and budget >= MEDIC_MIN_BUDGET and not _has_medic(chosen):
        pss = [x for x in chosen if x['card'].card_subtype == 'Player' and x['left'] >= _gear_weight(aid)]
        if pss and spent + aid.resource_cost <= budget:
            x = max(pss, key=lambda x: (x['left'], -x['card'].id))
            x['gear'].append([aid, 1])
            x['left'] -= _gear_weight(aid)
            spent += aid.resource_cost

    # a Canteen (card refill when the hand is empty or useless), same reason to come before the weapons
    canteen = next(iter(_dedupe_by_name([c for c in cat.filter(Card.card_type == 'Equipment', Card.name == CANTEEN_NAME)
                                         .order_by(Card.id).all() if allowed(c) and _nation_ok(c, nation)])), None)
    if classic and canteen and budget >= MEDIC_MIN_BUDGET:
        want = 2 if budget >= CANTEEN_SECOND_BUDGET else 1
        for _ in range(want - _count_gear(chosen, CANTEEN_NAME)):
            pss = [x for x in chosen if x['card'].card_subtype == 'Player' and x['left'] >= _gear_weight(canteen)
                   and not any(g[0].name == CANTEEN_NAME for g in x['gear'])]
            if not pss or spent + canteen.resource_cost > budget:
                break
            x = max(pss, key=lambda x: (x['left'], -x['card'].id))
            x['gear'].append([canteen, 1])
            x['left'] -= _gear_weight(canteen)
            spent += canteen.resource_cost

    if offload:
        place_offload()
    if bundle:
        place_bundle()
    if sniper:
        place_sniper()

    equip(spent + (budget - spent) * 0.55)

    # skills + armor: marginal gain per RP on the objective's weighted metrics (same numbers the page shows)
    scales = _scales()
    skill_cards = {c.name: c for c in _dedupe_by_name(
        [c for c in cat.filter(Card.card_type == 'Skill', Card.name.in_(BUYABLE_SKILLS)).order_by(Card.id).all()
         if _nation_ok(c, nation) and allowed(c) and c.resource_cost is not None])}
    equip_cards = {}
    for c in cat.filter(Card.card_type == 'Equipment').order_by(Card.id).all():
        if not allowed(c) or not _nation_ok(c, nation) or c.resource_cost is None:
            continue
        for key in BUYABLE_EQUIPMENT:
            if c.name == key or c.name.endswith('-' + key):
                equip_cards.setdefault(key, c)
    extras = {}      # name → card row (skills first, then equipment)
    extras.update(skill_cards)
    extras.update({c.name: c for c in equip_cards.values()})
    detail_cache = {}

    def add_extras(cap):
        """Greedily buy the extra with the best score gain per RP, for any Player Soldier, while spend <= cap."""
        nonlocal spent
        if not extras:
            return
        pss = [x for x in chosen if x['card'].card_subtype == 'Player']
        mdict = {'time': mission.time, 'objective_position': mission.objective_position,
                 'mission_type': mission.card_subtype}
        inputs = [metrics.soldier_input(x['card'], [(g, q) for g, q in x['gear']]) for x in chosen]
        base = metrics.analyse({'soldiers': inputs}, mdict, objs, hostile=hostile)
        base_score = _squad_score(base, weights, scales)
        once = {'Leadership', 'Squad Leader', 'Spotter'}     # limit 1 per mission / one Spotter is enough
        for _ in range(8):
            best = None
            for x in pss:
                idx = chosen.index(x)
                owned = {g[0].name for g in x['gear']}
                for name, c in extras.items():
                    if name in owned or spent + (c.resource_cost or 0) > cap:
                        continue
                    if name in once and any(g[0].name == name for y in chosen for g in y['gear']):
                        continue
                    if name == 'Veteran' and (x['card'].resource_cost or 0) < 20:
                        continue
                    if c.card_type == 'Equipment' and _gear_weight(c) > x['left']:
                        continue
                    if c.card_type == 'Equipment' and any(g[0].card_type == 'Equipment' and g[0].name.endswith(name.split('-')[-1])
                                                          for g in x['gear']):
                        continue
                    d = detail_cache.get(c.id)
                    if d is None:
                        d = detail_cache[c.id] = c.to_card_detail()
                    trial = [dict(i, gear=list(i['gear'])) for i in inputs]
                    trial[idx]['gear'].append(dict(d, _qty=1))
                    gain = _squad_score(metrics.analyse({'soldiers': trial}, mdict, objs, hostile=hostile),
                                        weights, scales) - base_score
                    value = gain * noise() / max(c.resource_cost or 1, 1)
                    if gain > 0.004 and (best is None or value > best[0]):
                        best = (value, x, c, idx)
            if best is None:
                break
            _, x, c, idx = best
            x['gear'].append([c, 1])
            if c.card_type == 'Equipment':
                x['left'] -= _gear_weight(c)
            spent += c.resource_cost or 0
            d = detail_cache.get(c.id) or c.to_card_detail()
            inputs[idx]['gear'].append(dict(d, _qty=1))
            base = metrics.analyse({'soldiers': inputs}, mdict, objs, hostile=hostile)
            base_score = _squad_score(base, weights, scales)

    add_extras(spent + (budget - spent) * 0.5)

    # support soldiers
    def support_value(c):
        inp = metrics.soldier_input(c, [])
        res = metrics.analyse({'soldiers': [inp]}, {'time': mission.time, 'objective_position': mission.objective_position,
                                                    'mission_type': mission.card_subtype}, objs, hostile=hostile)
        return (weights['ranged_fire'] * res['ranged_fire']['raw'] + weights['close_assault'] * res['close_assault']['raw']
                + 0.1 * weights['survivability'] * res['survivability']['raw']
                + 0.3 * weights['anti_armour'] * res['anti_armour']['raw']
                - 0.25 * weights['mobility'] * max(0.0, 2.4 - (c.movement or 0)))   # PS pay cards to move them

    cands = [c for c in support_pool if c.name not in names_in and c.resource_cost <= budget - spent]
    cands = sorted(cands, key=lambda c: -((c.health or 1) + 2 * (c.actions or 0)) / max(c.resource_cost, 1))[:30]
    svals = {c.id: support_value(c) for c in cands}
    def fill_leftover(spent_now):
        """Leftover RP: a Lucky Helmet on a Player Soldier with room, then cheap (<= FODDER_MAX_COST) bodies ranked by
        Actions per RP — never across a threat-band edge (more Hostiles), and only below the soldier cap."""
        nonlocal spent
        spent = spent_now
        band = lambda rp: (_band(objective, rp) or {}).get('hostiles')
        helmet = equip_cards.get('Lucky Helmet')
        if helmet:
            for x in chosen:
                if x['card'].card_subtype == 'Player' and x['left'] >= _gear_weight(helmet) \
                        and not any(g[0].name == helmet.name for g in x['gear']) \
                        and spent + helmet.resource_cost <= budget and band(spent + helmet.resource_cost) == band(spent):
                    x['gear'].append([helmet, 1])
                    x['left'] -= _gear_weight(helmet)
                    spent += helmet.resource_cost
                    break
        cheap = sorted((c for c in support_pool if c.name not in names_in and 0 < c.resource_cost <= FODDER_MAX_COST
                        and (c.actions or 0) >= 1),
                       key=lambda c: (c.resource_cost / (c.actions or 1), -(c.health or 0), c.id))
        for c in cheap:
            if len(chosen) >= max_soldiers or spent + c.resource_cost > budget:
                continue
            if band(spent + c.resource_cost) != band(spent):
                continue
            add_soldier(c)
            names_in.add(c.name)
        return spent

    support_cap = budget * (1 - (PS_MIN_SHARE if classic else 0))        # the PS keep at least PS_MIN_SHARE of the spend
    while len(chosen) < max_soldiers:
        support_spent = sum(s['card'].resource_cost or 0 for s in chosen if s['card'].card_subtype != 'Player')
        room = min(budget - spent, support_cap - support_spent)
        opts = [c for c in cands if c.name not in names_in and c.resource_cost <= room]
        if not opts:
            break
        best = max(opts, key=lambda c: (svals[c.id] * noise() / c.resource_cost ** 0.7, -c.id))
        if svals[best.id] <= 0:
            break
        add_soldier(best)
        names_in.add(best.name)

    equip(budget)
    add_extras(budget)
    if classic:
        spent = fill_leftover(spent)
    return chosen, budget, weights, spent


def db_cards(ids):
    if not ids:
        return []
    by = {c.id: c for c in Card.query.filter(Card.id.in_(ids)).all()}
    return [by[i] for i in ids if i in by]


# ── explanation ───────────────────────────────────────────────────────────────

def _band(objective, rp):
    """(label, hostiles) of the objective's Hostile table row for this squad RP."""
    import json
    if not objective or not objective.hostile_spawn_table:
        return None
    try:
        rows = json.loads(objective.hostile_spawn_table)
    except ValueError:
        return None
    for row in rows:
        rng = row.get('range', '')
        m = re.match(r'^(\d+)-(\d+)$', rng)
        if rng.endswith('-') and not m:
            if rp <= int(rng[:-1]):
                return {'range': rng, 'hostiles': row.get('count')}
        elif rng.endswith('+'):
            if rp >= int(rng[:-1]):
                return {'range': rng, 'hostiles': row.get('count')}
        elif m and int(m.group(1)) <= rp <= int(m.group(2)):
            return {'range': rng, 'hostiles': row.get('count')}
    return None


def _fitness(rank_metrics, weights, checks):
    num = den = 0.0
    for k, w in weights.items():
        sc = rank_metrics[k]['score']
        if sc is not None:
            num += w * sc
            den += w
    score = (num / den) if den else 0.0
    for c in checks:
        score *= {'ok': 1.0, 'weak': 0.7, 'missing': 0.25}.get(c['status'], 1.0)
    label = 'strong' if score >= 0.75 else 'solid' if score >= 0.5 else 'risky' if score >= 0.3 else 'unfit'
    return {'score': round(score, 3), 'label': label}


def _count_gear(chosen, name):
    return sum(q for s in chosen for g, q in s['gear'] if g.name == name)


def _has_medic(chosen):
    for s in chosen:
        if re.search(r'medic|corpsman', s['card'].name, re.I):
            return True
        if any(re.search(r'First Aid|Corpsman|Medic', g.name, re.I) for g, _q in s['gear']):
            return True
    return False


def _checks(req, ctx, chosen, raw, mission, rank_scored=None, weights=None):
    checks = []
    ps = sum(1 for s in chosen if s['card'].card_subtype == 'Player')
    want = req['players'] or (1 if mission.resources < 40 else 2 if mission.resources < 80 else 3 if mission.resources < 120 else 4)
    diff = abs(ps - want)
    checks.append({'key': 'players', 'status': 'ok' if diff == 0 else 'weak' if diff == 1 else 'missing',
                   'params': {'have': ps, 'want': want}})
    mtype = mission.card_subtype or ''
    if mtype not in ('Holding Action', 'Hold the Line') and mission.objective_position and mission.time:
        moves = max(1, mission.objective_position - 1) * (2 if mtype == 'Raid' or
                                                          (ctx['objective'] and ctx['objective'].card_subtype == 'Escape') else 1)
        st = 'ok' if moves <= 0.75 * mission.time else 'weak' if moves <= mission.time else 'missing'
        checks.append({'key': 'route', 'status': st, 'params': {'moves': moves, 'time': mission.time}})
    o = ctx['objective']
    notes = (o.notes or '') if o else ''
    # community heuristics (ytb_squadbuilding_tips.md)
    pss = [s['card'] for s in chosen if s['card'].card_subtype == 'Player']
    low = min((c.movement or 0 for c in pss), default=0)
    checks.append({'key': 'ps_movement', 'status': 'ok' if low >= PS_MIN_MOVEMENT else 'weak',
                   'params': {'min': low, 'want': PS_MIN_MOVEMENT}})
    total = sum(s['card'].resource_cost or 0 for s in chosen) + sum((g.resource_cost or 0) * q for s in chosen for g, q in s['gear'])
    ps_rp = sum((s['card'].resource_cost or 0) + sum((g.resource_cost or 0) * q for g, q in s['gear'])
                for s in chosen if s['card'].card_subtype == 'Player')
    if len(chosen) > len(pss) and total:
        share = ps_rp / total
        checks.append({'key': 'ps_share', 'status': 'ok' if share >= PS_MIN_SHARE else 'weak',
                       'params': {'share': round(100 * share), 'want': round(100 * PS_MIN_SHARE)}})
    if mission.resources >= MEDIC_MIN_BUDGET:
        checks.append({'key': 'medic', 'status': 'ok' if _has_medic(chosen) else 'weak', 'params': {}})
    if mission.resources >= MEDIC_MIN_BUDGET:
        checks.append({'key': 'canteen', 'status': 'ok' if _count_gear(chosen, CANTEEN_NAME) else 'weak', 'params': {}})
    if weights is not None and _wants_bundle(weights, o, mission.resources):
        ok = any(g.name == 'Close Combat' for s in chosen for g, _q in s['gear']) and \
            any(g.card_subtype == 'Thrown' and q >= 2 for s in chosen for g, q in s['gear'])
        if ok:      # informational: when the engine found the bundle no better, it is simply not shown
            checks.append({'key': 'bundle', 'status': 'ok', 'params': {}})
    if _wants_sniper(o) and any(g.name == 'Marksman' for s in chosen for g, _q in s['gear']):
        checks.append({'key': 'sniper', 'status': 'ok', 'params': {}})      # informational, like the bundle
    if _needs_anti_armour(o):
        sc = rank_scored['anti_armour']['score'] if rank_scored else None
        if sc is not None:
            checks.append({'key': 'anti_armour', 'status': 'ok' if sc >= 0.5 else 'weak' if sc >= 0.25 else 'missing',
                           'params': {}})
    if 'Explosion Attacks only' in notes:
        hits = re.search(r'(\d+) Hits', notes)
        count = re.search(r'Destroy (\d+)', notes)
        need = (int(hits.group(1)) if hits else 1) * (int(count.group(1)) if count else 1)
        have = raw['demolition']['raw']
        st = 'ok' if have >= need else 'weak' if have >= need * 0.5 else 'missing'
        checks.append({'key': 'explosive', 'status': st, 'params': {'have': round(have, 1), 'need': need}})
    if not req.get('classic', True):
        checks = [c for c in checks if c['key'] not in CLASSIC_CHECKS]
    return checks


def _why(chosen, wvals_by_name=None):
    out = []
    for s in chosen:
        c = s['card']
        if c.card_subtype == 'Player':
            out.append({'card_id': c.id, 'code': 'ps', 'params': {
                'health': c.health, 'movement': c.movement, 'loadout': c.loadout, 'rp': c.resource_cost}})
        else:
            out.append({'card_id': c.id, 'code': 'support', 'params': {
                'type': c.card_subtype, 'health': c.health, 'actions': c.actions, 'rp': c.resource_cost}})
        for g, qty in s['gear']:
            out.append({'card_id': g.id, 'soldier_card_id': c.id, 'code': 'gear', 'params': {
                'rp': g.resource_cost, 'qty': qty}})
    return out


# ── generate ──────────────────────────────────────────────────────────────────

def _evaluate(req, ctx, chosen, weights):
    """Metrics, checks and fitness of a built squad — light cards only, cheap enough to run per candidate."""
    mission, objective = ctx['mission'], ctx['objective']
    inputs = [metrics.soldier_input(s['card'], [(g, q) for g, q in s['gear']]) for s in chosen]
    objs = [{'objective_family': objective.objective_family, 'mechanic': objective._objective_mechanic(),
             'notes_en': objective.notes}] if objective else []
    mdict = {'time': mission.time, 'objective_position': mission.objective_position,
             'mission_type': mission.card_subtype, 'budget': mission.resources}
    raw = metrics.analyse({'soldiers': inputs}, mdict, objs, hostile=ctx['hostile'])
    scored = metrics.score_metrics(raw, mission.resources)
    checks = _checks(req, ctx, chosen, raw, mission, scored['metrics'], weights)
    return {'raw': raw, 'scored': scored, 'checks': checks, 'fitness': _fitness(scored['metrics'], weights, checks)}


def _card_ids(chosen):
    return {s['card'].id for s in chosen} | {g.id for s in chosen for g, _q in s['gear']}


def _similarity(a, b):
    return len(a & b) / max(len(a | b), 1)


def _assemble(req, ctx, chosen, budget, spent, ev):
    """Everything the client shows for one squad: payload, validation, soldier cards, metrics, checks, reasons."""
    mission, objective = ctx['mission'], ctx['objective']
    soldiers = [{'card_id': s['card'].id, 'sort_order': i,
                 'gear': [{'card_id': g.id, 'quantity': q} for g, q in s['gear']]} for i, s in enumerate(chosen)]
    payload = {'name': '', 'mission_card_id': mission.id, 'objective_card_ids': [objective.id] if objective else [],
               'situation_card_id': None, 'nation': ctx['nation'], 'soldiers': soldiers}
    # validation by the same rules as the builder
    from app.squads import _build_soldiers_data
    sd, err = _build_soldiers_data(soldiers)
    validation = rules_module.validate_squad(payload, mission.to_card_detail(), sd) if sd else None
    warnings = [w['message'] for w in (validation or {}).get('warnings', [])]
    if validation and not validation['valid']:
        warnings += [e['message'] for e in validation['errors']]
    rp_total = (validation or {}).get('computed', {}).get('rp_total', spent)
    req_mods = sorted({s['card'].module for s in chosen} | {g.module for s in chosen for g, _q in s['gear']}
                      | {mission.module} | ({objective.module} if objective else set()))
    return {
        'squad': payload,
        'soldiers': [{'card': s['card'].to_card_object(),
                      'gear': [{'card': g.to_card_object(), 'quantity': q} for g, q in s['gear']],
                      'default_gear': []} for s in chosen],
        'fitness': ev['fitness'], 'metrics': ev['scored'], 'checks': ev['checks'], 'why': _why(chosen),
        'spend': {'rp_used': rp_total, 'budget': mission.resources, 'target': budget, 'band': _band(objective, rp_total)},
        'required_modules': req_mods, 'warnings': warnings,
    }


def _alternatives(req, ctx, main_chosen, main_eval, weights, n):
    """Up to n runner-up squads of a different shape: each candidate build pushes one of the metrics the main
    squad is weakest in (weighted by what the objective rewards); candidates that are too similar to the main
    squad / each other, or clearly worse, are dropped. Returns [(chosen, budget, spent, evaluation, focus)]."""
    if n <= 0:
        return []
    scored = main_eval['scored']['metrics']
    gaps = sorted(((weights[k] * (1 - (scored[k]['score'] if scored[k]['score'] is not None else 0.5)), k)
                   for k in metrics.METRIC_KEYS), reverse=True)
    pool = []
    for _gap, k in gaps[:ALT_CANDIDATES]:
        w = dict(weights)
        w[k] += 2.5
        try:
            chosen, budget, _w, spent = _build(req, ctx, random.Random(f"{req['seed']}|alt|{k}"), weights_override=w, **ctx.get('variant', {}))
        except GenError:
            continue
        pool.append((chosen, budget, spent, _evaluate(req, ctx, chosen, weights), k))
    pool.sort(key=lambda c: -c[3]['fitness']['score'])
    keep, seen = [], [_card_ids(main_chosen)]
    for cand in pool:
        ids = _card_ids(cand[0])
        if cand[3]['fitness']['score'] < ALT_MIN_FITNESS * main_eval['fitness']['score']:
            continue
        if any(_similarity(ids, other) >= ALT_MAX_SIMILARITY for other in seen):
            continue
        keep.append(cand)
        seen.append(ids)
        if len(keep) >= n:
            break
    return keep


@generator_bp.route('/generate', methods=['POST'])
@limiter.limit('20 per minute', key_func=lambda: f'gen:{current_user.id}' if current_user.is_authenticated
               else f'gen:ip:{request.remote_addr}')
def generate():
    req = parse_request(request.get_json(silent=True) or {})
    rng = random.Random(f"{req['seed']}|{req['nation']}|{req['mission_card_id']}|{req['objective_card_id']}|{ENGINE_VERSION}")
    try:
        ctx = resolve(req, current_user, rng)
        chosen, budget, weights, spent = build(req, ctx, rng)
    except GenError as e:
        return jsonify(error=e.message, code=e.code, params=e.params), 422

    mission, objective = ctx['mission'], ctx['objective']
    ev = _evaluate(req, ctx, chosen, weights)
    out = _assemble(req, ctx, chosen, budget, spent, ev)
    out['alternatives'] = []
    for a_chosen, a_budget, a_spent, a_ev, focus in _alternatives(req, ctx, chosen, ev, weights, req['alternatives']):
        alt = _assemble(req, ctx, a_chosen, a_budget, a_spent, a_ev)
        alt['alt'] = {'focus': focus}
        out['alternatives'].append(alt)

    excluded = ctx['excluded']
    mods = _all_modules()
    out.update(
        resolved={'nation': ctx['nation'], 'mission_card_id': mission.id,
                  'objective_card_id': objective.id if objective else None,
                  'enemy_nation': ctx['enemy'], 'theater': ctx['theater'], 'players': req['players'],
                  'hostile_level': req['hostile_level'], 'classic': req['classic'], 'quality': req['quality'], 'twist': req['twist'],
                  'seed': req['seed'], 'engine_version': ENGINE_VERSION},
        mission=mission.to_card_object(), objective=objective.to_card_object() if objective else None,
        collection={'owned_modules': len(mods) - len(excluded & set(mods)), 'total_modules': len(mods)},
    )
    return jsonify(out)
